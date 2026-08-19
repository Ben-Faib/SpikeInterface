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
it back, and ``load_quality_metrics`` reads the per-unit ``quality_metrics.csv``
the sort wrote (NaN -> None, so a surface can render an honest "–"). The compute
side is SpikeInterface/NumPy-dependent and imported lazily, so the Textual menu —
which must import **no** SpikeInterface — can still call the pure
``load_summary`` / ``load_quality_metrics`` / ``format_card`` / ``headline_row``
helpers to render a saved sort. This mirrors the lazy-import discipline in
``sorters.py``.

Amplitudes (V_pp, noise floor) are reported in physical **µV** when the recording
carries a gain (Blackrock does: ~0.25 µV/sample); otherwise they fall back to raw
a.u. and ``units_in_uV`` is False. The noise floor is measured on the *same*
band-passed + common-median-referenced recording the sort and SNR use, so the
three are mutually consistent (SNR ≈ V_pp / (2·noise)); it is therefore a
post-CMR figure, lower than the raw broadband noise.

The **yield denominator is the electrodes actually sorted**, so when the pipeline
excludes a bad channel the denominator shrinks. That is not silent: pass the
excluded ids to ``compute_summary(excluded_channels=...)`` and they are persisted
as ``excluded_channels`` and stated in the yield cell that every surface renders.

``unit_rollup(summary, metrics, ...)`` is the module's other half: the **takeaway**
— which units pass the quality rule ("strong"), at which contact each one peaks,
how separate it looks in plain words, and how many accepted units live on each
contact — ranked strongest first. It is pure (no SpikeInterface, no NumPy) and it
is the ONE home for that synthesis: the report's strong-units block, the
dashboard's RESULTS line and the in-TUI triage order all read it rather than
each deciding for itself which units are real.
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
# How each criterion is WORDED — one home, so the rule sentence on a tile and the
# reason printed against a single unit are the same words.
_RULE_LABELS = {
    "snr_min": "SNR ≥ {v:g}",
    "isi_violations_ratio_max": "ISI ratio ≤ {v:g}",
    "amplitude_cutoff_max": "amp cutoff ≤ {v:g}",
    "presence_ratio_min": "presence ≥ {v:g}",
}


def _f(value):
    """``value`` as a finite float, or None (absent / blank / non-numeric / NaN).

    "We could not judge this" and "it scored zero" are different facts, so a
    NaN never becomes a number here.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if v != v else v          # v != v -> NaN


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
    parts = [_RULE_LABELS[k].format(v=rule[k]) for k in DEFAULT_QUALITY_RULE if k in rule]
    return " · ".join(parts) + " (NaN criteria skipped)"


def rule_detail(row, rule=None) -> dict:
    """Judge ONE unit against the rule: ``{flag, n_evaluable, failed}``.

    The single evaluator — ``quality_pass`` counts its flags and the rollup
    below quotes its ``failed`` list, so a headline count and a per-unit reason
    can never disagree. ``failed`` is a list of ``(label, value, threshold)``
    already phrased the way ``rule_text`` phrases the rule, e.g.
    ``("ISI ratio ≤ 0.5", 1.587, 0.5)``.

    ``flag`` is TRI-STATE: True = passed every evaluable criterion, False =
    failed one, **None = no criterion was evaluable for that unit**.
    """
    rule = rule or DEFAULT_QUALITY_RULE
    evaluable = 0
    failed = []
    for key, thr in rule.items():
        col, direction = _RULE_METRICS.get(key, (None, None))
        if col is None:
            continue
        v = _f(row.get(col))
        if v is None:                      # absent or NaN — honestly not evaluable
            continue
        evaluable += 1
        if (direction == "min" and v < thr) or (direction == "max" and v > thr):
            failed.append((_RULE_LABELS[key].format(v=thr), v, thr))
    flag = None if not evaluable else not failed
    return {"flag": flag, "n_evaluable": evaluable, "failed": failed}


def quality_pass(rows, rule=None) -> "tuple[int, list]":
    """(n_pass, per-unit flags) for ``rows`` = iterable of per-unit metric dicts
    (e.g. a quality-metrics DataFrame's ``to_dict("records")``).

    Flags are TRI-STATE: True = passed every evaluable criterion, False = failed
    one, **None = no criterion was evaluable for that unit** — "we couldn't judge
    it" must never masquerade as "it failed" (or as a fake 0-pass headline).
    """
    rule = rule or DEFAULT_QUALITY_RULE
    flags = [rule_detail(row, rule)["flag"] for row in rows]
    return sum(1 for f in flags if f), flags


# --------------------------------------------------------------------------- #
# The per-contact rollup — ONE owner for the synthesis "which units look real,
# at which contact". The report's strong-units block, the dashboard RESULTS line
# and the in-TUI triage order all read ``unit_rollup``; none of them re-derives a
# verdict, a ranking or a phrase of its own.
#
# "Strong" is nothing more than the quality rule above having passed, and the
# rule is stated verbatim (``rule_text``) wherever the count is shown. A rule of
# thumb for orientation — never a certification that a unit is one neuron.
#
# The ISOLATION PHRASE is derived from the PCA-based metrics the sort saves and
# from nothing else (amplitude and SNR are the quality rule's business):
#
#   nn_hit_rate         fraction of a spike's nearest neighbours in PC space that
#                       belong to the same unit — 1.0 is a unit that never sits
#                       inside another one.
#   l_ratio             how much foreign mass leaks into the unit's cluster;
#                       small is good (Schmitzer-Torbert et al. use ~0.05-0.1).
#   isolation_distance  Mahalanobis radius at which as many foreign spikes as own
#                       spikes are enclosed; large is good (~20 is a common floor).
#
# Thresholds are rules of thumb from that same literature, and they live HERE so
# no surface invents its own. Two honesty gates come first:
#   * below ISOLATION_MIN_SPIKES a PCA cluster has too few points for any of
#     these to mean anything, so the phrase says exactly that;
#   * SpikeInterface returns an astronomically large isolation_distance
#     (1e15-ish, observed on this recording's low-rate units) when the unit has
#     too few spikes for the PC dimensionality. That is a numerical artefact, not
#     a perfectly isolated neuron, so it is discarded rather than believed.
ISOLATION_MIN_SPIKES = 100
ISOLATION_DEGENERATE_DISTANCE = 1e6
ISOLATION_CLEAN = {"nn_hit_rate": 0.9, "l_ratio": 0.1, "isolation_distance": 20.0}
ISOLATION_POOR = {"nn_hit_rate": 0.5, "l_ratio": 0.3, "isolation_distance": 10.0}
# "min" = bigger is better.
_ISOLATION_DIRECTION = {"nn_hit_rate": "min", "l_ratio": "max", "isolation_distance": "min"}

# The verdict WORD each surface prints. "strong" is the rule's pass; nothing here
# ever prints a bare boolean, and "not judged" never reads as a failure.
VERDICT_WORDS = {True: "strong", False: "sub-threshold", None: "not judged"}


def isolation_phrase(metrics, *, n_spikes=None, shares_contact_with=0,
                     contact=None) -> str:
    """How separate this unit looks, in plain words (see the thresholds above).

    ``metrics`` is one unit's row of quality metrics. ``n_spikes`` is its spike
    count when known (None = unknown, and then the too-few-spikes gate simply
    cannot fire — it is never guessed). ``shares_contact_with`` is how many OTHER
    units peak on the same contact, which is the only thing that lets a poor
    score name a concrete neighbour instead of gesturing at the array.
    """
    metrics = metrics or {}
    usable = {}
    for key in _ISOLATION_DIRECTION:
        v = _f(metrics.get(key))
        if v is None:
            continue
        if key == "isolation_distance" and v >= ISOLATION_DEGENERATE_DISTANCE:
            continue                      # numerical artefact, not a measurement
        usable[key] = v
    if n_spikes is not None and n_spikes < ISOLATION_MIN_SPIKES:
        return "too few spikes to judge"
    if not usable:
        return "no isolation metrics — cannot judge"
    poor = clean = 0
    for key, v in usable.items():
        hi_is_good = _ISOLATION_DIRECTION[key] == "min"
        if (v < ISOLATION_POOR[key]) if hi_is_good else (v > ISOLATION_POOR[key]):
            poor += 1
        elif (v >= ISOLATION_CLEAN[key]) if hi_is_good else (v <= ISOLATION_CLEAN[key]):
            clean += 1
    if poor:
        if shares_contact_with:
            other = ("another unit" if shares_contact_with == 1
                     else f"{shares_contact_with} other units")
            return f"overlaps {other} on ch {contact}"
        return "not clearly separate from the other units"
    return "clean" if clean == len(usable) else "mostly separate"


def _contact_of(row) -> str:
    """The contact a unit peaks on, as a string. '?' when the sort saved none."""
    c = row.get("best_channel")
    return "?" if c is None else str(c)


def _contact_sort_key(contact: str):
    """Numeric where the ids are numbers (ch 2 before ch 10), else lexical."""
    try:
        return (0, float(contact), "")
    except (TypeError, ValueError):
        return (1, 0.0, str(contact))


def contact_line(contacts, *, max_named=8) -> str:
    """The one-line per-contact rollup, e.g.

        contact 5: 2 accepted · contact 7: 2 accepted + 3 sub-threshold candidates

    Contacts that host an accepted unit are named (up to ``max_named``); the rest
    are summarised in a tail clause, so the line stays a line even on a 16-contact
    array where every contact holds something.
    """
    with_accepted = [i for i, c in enumerate(contacts) if c["n_accepted"]][:max_named]
    named = [contacts[i] for i in with_accepted]
    rest = [c for i, c in enumerate(contacts) if i not in set(with_accepted)]
    parts = []
    for c in named:
        bit = f"contact {c['contact']}: {c['n_accepted']} accepted"
        if c["n_other"]:
            bit += (f" + {c['n_other']} sub-threshold "
                    f"candidate{'' if c['n_other'] == 1 else 's'}")
        parts.append(bit)
    line = " · ".join(parts)
    if rest:
        n_c = len(rest)
        n_a = sum(c["n_accepted"] for c in rest)
        n_o = sum(c["n_other"] for c in rest)
        tail = (f"{n_c} further contact{'' if n_c == 1 else 's'} hold "
                f"{n_o} sub-threshold candidate{'' if n_o == 1 else 's'}"
                + (f" and {n_a} accepted unit{'' if n_a == 1 else 's'}" if n_a
                   else " and no accepted unit"))
        line = f"{line} — {tail}" if line else tail[0].upper() + tail[1:]
    return line or "no units on any contact"


def unit_rollup(summary, metrics=None, *, rule=None, spike_counts=None,
                matches=None) -> dict:
    """The takeaway for one sort: which units look real, and at which contact.

    Pure — json/csv-level inputs, no SpikeInterface, no NumPy — so the menu's
    view process reads the same synthesis the report renders.

        summary        the sort's ``summary.json`` dict (``load_summary``); its
                       ``per_unit`` block supplies peak contact, V_pp and SNR,
                       already computed once by ``compute_summary``. Nothing is
                       recomputed from traces here.
        metrics        ``load_quality_metrics`` output, or any {unit: {col: v}}
                       mapping (a quality-metrics DataFrame's ``to_dict("index")``
                       works). ``{}``/None = the sort saved none, and every unit
                       is then honestly "not judged".
        rule           ``load_quality_rule`` output; defaults to DEFAULT_QUALITY_RULE.
        spike_counts   {unit: n spikes}, when the caller has the Sorting. Absent
                       leaves ``n_spikes`` None on every unit — an honest gap,
                       never an estimate.
        matches        {unit: {"unit", "containment", ...}} from
                       ``compare.match_manual``. None = no manual reference was
                       available, and ``has_matches`` says so, so a surface can
                       drop the column instead of guessing.

    Units are RANKED: accepted (the rule passed) first by SNR descending, then
    everything else by SNR descending — a unit with no SNR ranks last inside its
    group rather than being dropped.
    """
    rule = rule or DEFAULT_QUALITY_RULE
    metrics = metrics or {}
    per_unit = (summary or {}).get("per_unit") or []
    counts = {str(k): v for k, v in (spike_counts or {}).items()}
    match_by = {str(k): v for k, v in (matches or {}).items()}

    # How many units peak on each contact — what lets a poor isolation score name
    # the neighbour it is overlapping.
    on_contact: dict = {}
    for row in per_unit:
        on_contact[_contact_of(row)] = on_contact.get(_contact_of(row), 0) + 1

    units = []
    for row in per_unit:
        uid = row.get("unit")
        key = str(uid)
        qm = metrics.get(key) or metrics.get(uid) or {}
        detail = rule_detail(qm, rule)
        contact = _contact_of(row)
        n_spikes = counts.get(key)
        units.append({
            "unit": uid,
            "contact": contact,
            "n_spikes": n_spikes,
            "snr": _f(row.get("snr")) if _f(row.get("snr")) is not None else _f(qm.get("snr")),
            "v_pp_uV": _f(row.get("v_pp_uV")),
            "verdict": detail["flag"],
            "verdict_word": VERDICT_WORDS[detail["flag"]],
            # Why it is not strong, in the rule's own words. Empty for a pass.
            "why": ("" if detail["flag"] else
                    ("no criterion could be evaluated for this unit"
                     if detail["flag"] is None else
                     " · ".join(f"{lbl} — is {v:.3g}" for lbl, v, _thr in detail["failed"]))),
            "isolation": isolation_phrase(
                qm, n_spikes=n_spikes, contact=contact,
                shares_contact_with=on_contact.get(contact, 1) - 1),
            "match": match_by.get(key),
        })

    # Accepted first, then by SNR descending; a missing SNR sinks inside its group.
    units.sort(key=lambda u: (0 if u["verdict"] else 1,
                              -(u["snr"] if u["snr"] is not None else float("-inf"))))

    accepted = [u for u in units if u["verdict"]]
    contacts = []
    for c in sorted(on_contact, key=_contact_sort_key):
        contacts.append({
            "contact": c,
            "n_accepted": sum(1 for u in accepted if u["contact"] == c),
            "n_other": sum(1 for u in units if u["contact"] == c and not u["verdict"]),
        })
    contacts.sort(key=lambda c: (-c["n_accepted"], _contact_sort_key(c["contact"])))
    chans = [u["contact"] for u in accepted]
    return {
        "rule": dict(rule),
        "rule_text": rule_text(rule),
        "units": units,
        "contacts": contacts,
        "n_units": len(units),
        "n_accepted": len(accepted),
        "n_unjudged": sum(1 for u in units if u["verdict"] is None),
        "accepted_contacts": chans,
        "contact_line": contact_line(contacts),
        "headline": headline_takeaway(len(accepted), chans),
        "has_matches": matches is not None,
    }


def headline_takeaway(n_accepted: int, contacts, max_contacts: int = 8) -> str:
    """``6 strong units (ch 2·8·1·6·10·7)`` — the takeaway in one phrase.

    Contacts are in the ranked order of the units they belong to (strongest
    first), so a repeat means two accepted units share a contact. ``0`` says so
    plainly rather than printing an empty bracket.
    """
    n = int(n_accepted)
    word = "strong unit" if n == 1 else "strong units"
    if not n or not contacts:
        return f"{n} {word}"
    shown = [str(c) for c in contacts[:max_contacts]]
    more = "…" if len(contacts) > max_contacts else ""
    return f"{n} {word} (ch {'·'.join(shown)}{more})"


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
# New columns go on the END: seven summary.csv files written before
# n_excluded_channels existed are still on disk, and stacking them positionally
# against a row with a column inserted mid-order silently misaligns every field
# after it.
CSV_COLUMNS = [
    "sorter", "n_units", "n_channels", "n_active_channels",
    "v_pp_uV_median", "snr_median", "noise_floor_uV_median",
    "yield_pct", "units_per_channel", "units_per_active_channel",
    "n_excluded_channels",
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


def compute_summary(analyzer, *, sorter: "str | None" = None,
                    excluded_channels=None) -> dict:
    """Compute the array/yield summary from a SortingAnalyzer.

    Requires the ``templates`` and ``noise_levels`` extensions (pre-computed by
    ``run_sorting``; computed on demand otherwise). ``snr`` is read from the
    ``quality_metrics`` extension when present and omitted per-unit otherwise. The
    returned dict is JSON-serialisable and is the schema persisted to summary.json.

    ``excluded_channels`` are the ids the pipeline dropped as bad *before* the
    analyzer existed — the analyzer cannot know about them, and every count here
    (``n_channels``, the yield denominator) is over the channels that survived. They
    are recorded so the surfaces can say so rather than change meaning silently.
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
        return _empty_summary(sorter, n_channels, units_in_uV, duration_s,
                              excluded_channels=excluded_channels)

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
        "excluded_channels": [str(c) for c in (excluded_channels or [])],
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


def _empty_summary(sorter, n_channels: int, units_in_uV: bool, duration_s=None,
                   excluded_channels=None) -> dict:
    """Summary for a sort that found no units (everything zero / None)."""
    empty = {"median": None, "mean": None, "min": None, "max": None}
    return {
        "sorter": sorter, "n_units": 0, "n_channels": n_channels,
        "excluded_channels": [str(c) for c in (excluded_channels or [])],
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
        "n_excluded_channels": len(summary.get("excluded_channels") or []),
    }


def load_summary(out_dir) -> "dict | None":
    """Read outputs/<sorter>/summary.json; None if missing/unreadable. No SI import."""
    try:
        return json.loads((Path(out_dir) / "summary.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - absent / malformed -> caller degrades
        return None


def load_quality_metrics(out_dir) -> dict:
    """Read outputs/<sorter>/quality_metrics.csv as ``{unit id (str): {column: value}}``.

    Pure — csv + pathlib, no SpikeInterface — so the menu's view process can show
    per-unit evidence without paying for SI, and the numbers shown are the ones
    the sort actually wrote (nothing is recomputed here).

    A blank or NaN cell becomes ``None`` — "we could not judge this unit on this
    metric" (amplitude_cutoff is honestly NaN below 500 spikes) must never render
    as 0. Column order is the file's; the unnamed index column is the unit id.
    ``{}`` when the file is absent — a non-fatal metrics failure deletes it.
    """
    path = Path(out_dir) / "quality_metrics.csv"
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - absent / unreadable -> caller degrades
        return {}
    out = {}
    for row in csv.DictReader(text.splitlines()):
        unit = row.pop("", None)
        if unit is None:
            continue
        values = {}
        for col, raw in row.items():
            try:
                v = float(raw)
            except (TypeError, ValueError):     # blank cell / non-numeric
                v = None
            values[col] = None if v is None or v != v else v    # v != v -> NaN
        out[str(unit)] = values
    return out


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
    # The denominator is the electrodes that were SORTED. When bad channels were
    # excluded that is fewer than the array has, so the cell says so — a shrinking
    # denominator must never quietly inflate the percentage.
    n_excluded = len(summary.get("excluded_channels") or [])
    denom = f"{n_active}/{n_ch} sorted; {n_excluded} excluded as bad" if n_excluded \
        else f"{n_active}/{n_ch}"
    return {
        "V_pp": _fmt(_med(summary, "v_pp_uV"), amp),
        "SNR": _fmt(_med(summary, "snr")),
        "noise floor": _fmt(_med(summary, "noise_floor_uV"), amp),
        "yield (% active electrodes)": f"{summary.get('yield_pct', 0.0):g}% ({denom})",
        "units / ch": _fmt(summary.get("units_per_channel")),
        "units / active ch": _fmt(summary.get("units_per_active_channel")),
    }


def format_card(summary: dict) -> list:
    """Headline card as a list of "label: value" lines (terminal + menu). No SI import."""
    row = headline_row(summary)
    return [f"{label}: {value}" for label, value in row.items()]
