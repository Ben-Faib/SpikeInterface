"""Per-sort array / yield summary — the group-requested headline metrics.

Single source of truth for the six numbers the lab wants out of every sort:

    V_pp              peak-to-peak template amplitude (per unit, on its best channel)
    SNR               signal-to-noise ratio (per unit; SpikeInterface quality metric)
    noise floor       per-channel noise level of the sorted (band-passed + CMR) signal
    yield             % of electrodes that are the peak channel of >=1 sorted unit
    units per ch      n_units / n_channels
    units per active ch   n_units / n_active_channels

``compute_summary(analyzer)`` builds the full record (per-unit V_pp/SNR + the
aggregates above); ``write_summary`` persists it to ``summary.json`` (+ a one-row
``summary.csv`` of the headline numbers) next to the sort; ``load_summary`` reads
it back. The compute side is SpikeInterface/NumPy-dependent and imported lazily,
so the Textual menu — which must import **no** SpikeInterface — can still call the
pure ``load_summary`` / ``format_card`` / ``headline_row`` helpers to render a
saved summary. This mirrors the lazy-import discipline in ``sorters.py``.

Amplitudes (V_pp, noise floor) are reported in physical **µV** when the recording
carries a gain (Blackrock does: ~0.25 µV/sample); otherwise they fall back to raw
a.u. and ``units_in_uV`` is False. The noise floor is measured on the *same*
band-passed + common-median-referenced recording the sort and SNR use, so the
three are mutually consistent (SNR ≈ V_pp / (2·noise)); it is therefore a
post-CMR figure, lower than the raw broadband noise.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path


# --------------------------------------------------------------------------- #
# The unit quality rule (W1 slice 1) — ONE owner for "n of m pass quality".
#
# Grounded in common practice (SpikeInterface docs / Allen-style criteria), and
# a rule of thumb for ORIENTATION, never a substitute for curation. Configurable:
# a `quality_rule` object in .si_menu.json overrides any subset of the defaults
# (numeric values only; junk entries are dropped, and rule_text() always states
# the EFFECTIVE rule so what you read is what ran).
#
# Per-unit semantics are NaN-honest: a criterion whose metric is absent or NaN
# for a unit is SKIPPED for that unit (e.g. presence_ratio is honestly NaN on a
# 30 s quick sort with 60 s bins); a unit passes if it satisfies every criterion
# that could be evaluated, and at least one could.
DEFAULT_QUALITY_RULE = {
    "snr_min": 4.0,
    "isi_violations_ratio_max": 0.5,
    "amplitude_cutoff_max": 0.1,
    "presence_ratio_min": 0.9,
}
# rule key -> (metric column, direction): "min" = value must be >= threshold.
_RULE_METRICS = {
    "snr_min": ("snr", "min"),
    "isi_violations_ratio_max": ("isi_violations_ratio", "max"),
    "amplitude_cutoff_max": ("amplitude_cutoff", "max"),
    "presence_ratio_min": ("presence_ratio", "min"),
}


def load_quality_rule(config_path=None) -> dict:
    """DEFAULT_QUALITY_RULE overlaid with the user's `quality_rule` config.

    ``config_path`` is the .si_menu.json path (callers pass it; this module
    stays path-agnostic). Unknown keys and non-numeric values are dropped.
    """
    rule = dict(DEFAULT_QUALITY_RULE)
    if config_path:
        try:
            user = json.loads(Path(config_path).read_text(encoding="utf-8")
                              ).get("quality_rule", {})
        except Exception:  # noqa: BLE001 - no config / unreadable -> defaults
            user = {}
        if not isinstance(user, dict):    # "quality_rule": "strict" / 5 / [..] -> defaults
            user = {}
        for k, v in user.items():
            if k in _RULE_METRICS and isinstance(v, (int, float)) and not isinstance(v, bool):
                rule[k] = float(v)
    return rule


def rule_text(rule=None) -> str:
    """The effective rule, human-readable — shown wherever the count is shown."""
    rule = rule or DEFAULT_QUALITY_RULE
    parts = []
    labels = {"snr_min": ("SNR ≥ {v:g}"), "isi_violations_ratio_max": ("ISI ratio ≤ {v:g}"),
              "amplitude_cutoff_max": ("amp cutoff ≤ {v:g}"),
              "presence_ratio_min": ("presence ≥ {v:g}")}
    for k in DEFAULT_QUALITY_RULE:
        if k in rule:
            parts.append(labels[k].format(v=rule[k]))
    return " · ".join(parts) + " (NaN criteria skipped)"


def quality_pass(rows, rule=None) -> "tuple[int, list]":
    """(n_pass, per-unit flags) for ``rows`` = iterable of per-unit metric dicts
    (e.g. a quality-metrics DataFrame's ``to_dict("records")``).

    Flags are TRI-STATE: True = passed every evaluable criterion, False = failed
    one, **None = no criterion was evaluable for that unit** — "we couldn't judge
    it" must never masquerade as "it failed" (or as a fake 0-pass headline).
    """
    rule = rule or DEFAULT_QUALITY_RULE
    flags = []
    for row in rows:
        evaluable = 0
        ok = True
        for key, thr in rule.items():
            col, direction = _RULE_METRICS.get(key, (None, None))
            if col is None:
                continue
            v = row.get(col)
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if v != v:                     # NaN — honestly not evaluable
                continue
            evaluable += 1
            if direction == "min" and v < thr:
                ok = False
            elif direction == "max" and v > thr:
                ok = False
        flags.append(None if not evaluable else bool(ok))
    return sum(1 for f in flags if f), flags

# Stable order + display labels for the six headline metrics. Used by the report,
# the comparison table, the terminal card and the menu so every surface agrees.
HEADLINE_KEYS = [
    "v_pp", "snr", "noise_floor", "yield_pct", "units_per_ch", "units_per_active_ch",
]
HEADLINE_LABELS = {
    "v_pp": "V_pp",
    "snr": "SNR",
    "noise_floor": "noise floor",
    "yield_pct": "yield (% active electrodes)",
    "units_per_ch": "units / ch",
    "units_per_active_ch": "units / active ch",
}
# CSV column order (the headline card as a single row, ready to stack across sorters).
CSV_COLUMNS = [
    "sorter", "n_units", "n_channels", "n_active_channels",
    "v_pp_uV_median", "snr_median", "noise_floor_uV_median",
    "yield_pct", "units_per_channel", "units_per_active_channel",
]


# --------------------------------------------------------------------------- #
# Compute (SpikeInterface + NumPy — imported lazily inside the function)
# --------------------------------------------------------------------------- #
def _ensure(analyzer, ext: str) -> bool:
    """Best-effort: make sure ``ext`` is available on ``analyzer``. Returns presence.

    Used when summarising a saved analyzer that might predate one of the
    extensions we need. ``run_sorting`` always pre-computes them, so this is a
    no-op there. Never raises — a compute failure just leaves the extension absent
    and the caller degrades (e.g. SNR omitted).
    """
    if analyzer.get_extension(ext) is not None:
        return True
    try:
        analyzer.compute(ext)
    except Exception:  # noqa: BLE001 - optional; caller handles absence
        pass
    return analyzer.get_extension(ext) is not None


def _agg(values) -> dict:
    """{median, mean, min, max} of a 1-D array, rounded; zeros for an empty array."""
    import numpy as np

    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"median": None, "mean": None, "min": None, "max": None}
    return {
        "median": round(float(np.median(v)), 3),
        "mean": round(float(np.mean(v)), 3),
        "min": round(float(np.min(v)), 3),
        "max": round(float(np.max(v)), 3),
    }


def _py(x):
    """NumPy scalar -> plain Python (JSON-serialisable) int/float/str."""
    try:
        import numpy as np

        if isinstance(x, np.generic):
            return x.item()
    except Exception:  # noqa: BLE001
        pass
    return x


def compute_summary(analyzer, *, sorter: "str | None" = None) -> dict:
    """Compute the array/yield summary from a SortingAnalyzer.

    Requires the ``templates`` and ``noise_levels`` extensions (pre-computed by
    ``run_sorting``; computed on demand otherwise). ``snr`` is read from the
    ``quality_metrics`` extension when present and omitted per-unit otherwise. The
    returned dict is JSON-serialisable and is the schema persisted to summary.json.
    """
    import numpy as np

    rec = analyzer.recording
    channel_ids = [str(c) for c in analyzer.channel_ids]
    n_channels = len(channel_ids)
    unit_ids = list(analyzer.unit_ids)
    n_units = len(unit_ids)
    try:
        duration_s = round(float(analyzer.get_total_duration()), 3)
    except Exception:  # noqa: BLE001 - duration is best-effort context
        duration_s = None

    # Are the analyzer's trace-derived extensions (templates, noise_levels) ALREADY in
    # µV? create_sorting_analyzer(return_in_uV=True) — the SI default — scales them when
    # the recording carries gains, so multiplying by the gain again here would
    # double-apply it (V_pp/noise would come out ~gain× too small). SI 0.104 exposes
    # the flag as analyzer.return_in_uV (older: return_scaled). Derive a per-channel
    # ``scale`` that converts extension values to µV without ever double-counting:
    #   already-µV extensions  -> scale 1 (units are µV)
    #   native extensions + gain -> scale = gain (native -> µV)
    #   no gain anywhere        -> scale 1, values stay raw a.u.
    returns_uV = bool(getattr(analyzer, "return_in_uV",
                              getattr(analyzer, "return_scaled", True)))
    gain = None
    try:
        g = rec.get_channel_gains() if rec is not None else None
        if g is not None:
            gain = np.asarray(g, dtype=float)
    except Exception:  # noqa: BLE001 - some recordings carry no gain
        gain = None
    has_gain = gain is not None
    if has_gain and returns_uV:
        scale = np.ones(n_channels, dtype=float)   # extensions already in µV
        units_in_uV = True
    elif has_gain:
        scale = gain                               # native extensions -> µV
        units_in_uV = True
    else:
        scale = np.ones(n_channels, dtype=float)   # no gain -> raw a.u.
        units_in_uV = False

    if n_units == 0:
        return _empty_summary(sorter, n_channels, units_in_uV, duration_s)

    _ensure(analyzer, "random_spikes")
    _ensure(analyzer, "waveforms")
    have_templates = _ensure(analyzer, "templates")
    have_noise = _ensure(analyzer, "noise_levels")
    if not have_templates:
        raise RuntimeError("templates extension unavailable — cannot compute V_pp / yield")

    templates = analyzer.get_extension("templates").get_data()  # (units, samples, ch)

    # Noise floor per channel, in µV (median across channels is the headline figure).
    # ``scale`` is 1 when the extension is already µV, so this never double-applies gain.
    if have_noise:
        noise_native = np.asarray(analyzer.get_extension("noise_levels").get_data(), dtype=float)
        noise_uV = noise_native * scale
    else:
        noise_uV = np.full(n_channels, np.nan)

    # SNR per unit from the quality-metrics extension (already CMR-consistent).
    snr_by_unit: dict = {}
    qm_ext = analyzer.get_extension("quality_metrics")
    if qm_ext is not None:
        qm = qm_ext.get_data()
        if "snr" in getattr(qm, "columns", []):
            for u in unit_ids:
                try:
                    snr_by_unit[u] = float(qm.loc[u, "snr"])
                except Exception:  # noqa: BLE001 - missing/NaN -> omit
                    pass

    per_unit = []
    active_idx: set = set()
    for i, u in enumerate(unit_ids):
        ptp = np.ptp(templates[i], axis=0)            # per channel, native units
        best = int(np.argmax(ptp))                    # "best channel" = max peak-to-peak
        active_idx.add(best)
        snr = snr_by_unit.get(u)
        per_unit.append({
            "unit": _py(u),
            "v_pp_uV": round(float(ptp[best] * scale[best]), 3),
            "snr": round(float(snr), 3) if snr is not None else None,
            "best_channel": channel_ids[best],
        })

    n_active = len(active_idx)
    vpp_vals = [p["v_pp_uV"] for p in per_unit]
    snr_vals = [p["snr"] for p in per_unit if p["snr"] is not None]

    return {
        "sorter": sorter,
        "n_units": n_units,
        "n_channels": n_channels,
        "n_active_channels": n_active,
        "duration_s": duration_s,
        "units_in_uV": bool(units_in_uV),
        "gain_to_uV": round(float(np.median(gain)), 6) if units_in_uV else None,
        "v_pp_uV": _agg(vpp_vals),
        "snr": _agg(snr_vals),
        "noise_floor_uV": {**_agg(noise_uV),
                           "per_channel": [None if not np.isfinite(x) else round(float(x), 3)
                                           for x in noise_uV]},
        "yield_pct": round(100.0 * n_active / n_channels, 1) if n_channels else 0.0,
        "units_per_channel": round(n_units / n_channels, 3) if n_channels else 0.0,
        "units_per_active_channel": round(n_units / n_active, 3) if n_active else 0.0,
        "active_channels": [channel_ids[i] for i in sorted(active_idx)],
        "per_unit": per_unit,
    }


def _empty_summary(sorter, n_channels: int, units_in_uV: bool, duration_s=None) -> dict:
    """Summary for a sort that found no units (everything zero / None)."""
    empty = {"median": None, "mean": None, "min": None, "max": None}
    return {
        "sorter": sorter, "n_units": 0, "n_channels": n_channels,
        "n_active_channels": 0, "duration_s": duration_s,
        "units_in_uV": bool(units_in_uV), "gain_to_uV": None,
        "v_pp_uV": dict(empty), "snr": dict(empty),
        "noise_floor_uV": {**empty, "per_channel": []},
        "yield_pct": 0.0, "units_per_channel": 0.0, "units_per_active_channel": 0.0,
        "active_channels": [], "per_unit": [],
    }


# --------------------------------------------------------------------------- #
# Persistence + pure (SpikeInterface-free) formatting
# --------------------------------------------------------------------------- #
def write_summary(summary: dict, out_dir) -> Path:
    """Write summary.json (full record) + summary.csv (one headline row) to out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "summary.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerow(csv_row(summary))
    return json_path


def csv_row(summary: dict) -> dict:
    """The headline numbers as a flat dict keyed by CSV_COLUMNS (None -> '')."""
    return {
        "sorter": summary.get("sorter") or "",
        "n_units": summary.get("n_units", 0),
        "n_channels": summary.get("n_channels", 0),
        "n_active_channels": summary.get("n_active_channels", 0),
        "v_pp_uV_median": _med(summary, "v_pp_uV"),
        "snr_median": _med(summary, "snr"),
        "noise_floor_uV_median": _med(summary, "noise_floor_uV"),
        "yield_pct": summary.get("yield_pct", 0.0),
        "units_per_channel": summary.get("units_per_channel", 0.0),
        "units_per_active_channel": summary.get("units_per_active_channel", 0.0),
    }


def load_summary(out_dir) -> "dict | None":
    """Read outputs/<sorter>/summary.json; None if missing/unreadable. No SI import."""
    try:
        return json.loads((Path(out_dir) / "summary.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - absent / malformed -> caller degrades
        return None


def _med(summary: dict, key: str):
    block = summary.get(key) or {}
    return block.get("median")


def _fmt(value, unit: str = "") -> str:
    if value is None:
        return "—"
    suffix = f" {unit}" if unit else ""
    return f"{value:g}{suffix}"


def headline_row(summary: dict) -> dict:
    """{label: formatted-string} for the six headline metrics (for tables/cards)."""
    amp = "µV" if summary.get("units_in_uV", True) else "a.u."
    n_active = summary.get("n_active_channels", 0)
    n_ch = summary.get("n_channels", 0)
    return {
        "V_pp": _fmt(_med(summary, "v_pp_uV"), amp),
        "SNR": _fmt(_med(summary, "snr")),
        "noise floor": _fmt(_med(summary, "noise_floor_uV"), amp),
        "yield (% active electrodes)": f"{summary.get('yield_pct', 0.0):g}% ({n_active}/{n_ch})",
        "units / ch": _fmt(summary.get("units_per_channel")),
        "units / active ch": _fmt(summary.get("units_per_active_channel")),
    }


def format_card(summary: dict) -> list:
    """Headline card as a list of "label: value" lines (terminal + menu). No SI import."""
    row = headline_row(summary)
    return [f"{label}: {value}" for label, value in row.items()]
