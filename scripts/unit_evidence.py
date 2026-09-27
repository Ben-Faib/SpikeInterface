"""Per-unit evidence for judging a unit by eye - as plain data.

    uv run python scripts/unit_evidence.py --sorter tridesclous2 --unit 16
    uv run python scripts/unit_evidence.py --sorter tridesclous2        # every unit

Single source of truth for **what the Judge screen shows about one unit**: its
average waveform on the peak contact and its physical neighbours, its
inter-spike-interval histogram against the refractory window, and its amplitude
over the recording (drift, or a second amplitude cluster, shows up there). The
Textual view imports no SpikeInterface, so everything here comes back as lists
of floats / ints / strings the controller hands straight to the view.

``evidence_for_units(analyzer_dir)`` loads the saved ``SortingAnalyzer`` once
and returns ``{str(unit_id): evidence}``; ``unit_evidence`` is the one-unit
wrapper. Each evidence dict is JSON-serialisable::

    unit, n_spikes, peak_channel, channels     the peak contact + up to `neighbors`
                                               each side, ordered along the probe
    units_in_uV                                False only when the recording has no gain
    waveforms {channel: [µV, ...]} | None      the mean template, <= wave_points points
    wave_ms, peak_index                        span of those (evenly spaced) points;
                                               the peak sample's index among them
    isi {bin_ms, max_ms, counts, refractory_ms, n_refractory, ratio}
    amplitude {t_s, median_uV, n} | None       None when spike_amplitudes was not saved

Decisions that are not free choices:

- **µV, never double-scaled.** The analyzer's templates are already µV when
  ``analyzer.return_in_uV`` is set (this repo's analyzers are); the gain is
  applied only for a native-unit analyzer, exactly as ``sort_summary``'s
  ``compute_summary`` gates it. Re-applying the 0.25 µV/count gain would make
  every waveform ~4x too small.
- **The peak channel** is the template's max peak-to-peak channel, the same
  "best channel" ``sort_summary`` reports as ``best_channel``.
- **The refractory window** is ``report._refractory_ms``: the window the saved
  quality metrics were counted against, so ``n_refractory`` (counted here in
  the same arithmetic SpikeInterface counts ``isi_violations_count`` in) can
  never disagree with the metrics table. ``ratio`` is the saved ``isi_violations_ratio`` or None -
  never a recomputed stand-in under the same name.
- **Decimation keeps the true peak.** The template is strided down to at most
  ``wave_points`` samples on a grid anchored at the peak sample, so the trough
  the eye judges is the real one, not an interpolated shoulder.
- **Amplitudes are the saved ones** (``sort_summary.spike_amplitudes_by_unit``,
  the one decoder of that extension); absent extension -> None, never an estimate.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sort_summary  # noqa: E402  (the one decoder of spike_amplitudes)


def _to_uV_scale(analyzer) -> "tuple[np.ndarray, bool]":
    """Per-channel factor that turns extension values into µV, and whether they are µV.

    Mirrors ``sort_summary.compute_summary``'s gate: already-µV extensions -> 1;
    native extensions on a recording with gains -> the gain; no gain -> 1 (a.u.).
    """
    n = len(analyzer.channel_ids)
    returns_uV = bool(getattr(analyzer, "return_in_uV",
                              getattr(analyzer, "return_scaled", True)))
    gain = None
    try:
        rec = analyzer.recording
        g = rec.get_channel_gains() if rec is not None else None
        if g is not None:
            gain = np.asarray(g, dtype=float)
    except Exception:  # noqa: BLE001 - some recordings carry no gain
        gain = None
    if gain is not None and returns_uV:
        return np.ones(n, dtype=float), True
    if gain is not None:
        return gain, True
    return np.ones(n, dtype=float), False


def _probe_order(analyzer) -> list:
    """Channel indices ordered by position along the probe (else channel order)."""
    n = len(analyzer.channel_ids)
    try:
        loc = np.asarray(analyzer.get_channel_locations(), dtype=float)
    except Exception:  # noqa: BLE001 - no probe attached
        return list(range(n))
    spread = np.ptp(loc, axis=0)
    if loc.ndim != 2 or loc.shape[0] != n or float(spread.max()) == 0.0:
        return list(range(n))
    return [int(i) for i in np.argsort(loc[:, int(np.argmax(spread))], kind="stable")]


def _saved_ratios(analyzer) -> dict:
    """{str(unit): isi_violations_ratio} from the saved quality metrics, or {}."""
    ext = analyzer.get_extension("quality_metrics")
    if ext is None:
        return {}
    qm = ext.get_data()
    if "isi_violations_ratio" not in getattr(qm, "columns", []):
        return {}
    out = {}
    for u, v in qm["isi_violations_ratio"].items():
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            out[str(u)] = float(v)
    return out


def _evidence(analyzer, u, i, *, templates, scale, units_in_uV, order, fs, seg_starts,
              duration_s, refractory_ms, ratios, amplitudes, neighbors, wave_points,
              isi_max_ms, isi_bin_ms, amp_bins) -> dict:
    """The evidence dict for unit ``u`` (row ``i`` of the templates array)."""
    channel_ids = [str(c) for c in analyzer.channel_ids]
    sorting = analyzer.sorting

    # Waveforms: peak = max peak-to-peak channel, neighbours along the probe.
    wave = {"peak_channel": None, "channels": [], "waveforms": None,
            "wave_ms": None, "peak_index": None}
    peak_scale = 1.0
    if templates is not None:
        tmpl = np.asarray(templates[i], dtype=float)             # (samples, channels)
        peak = int(np.argmax(np.ptp(tmpl, axis=0)))
        peak_scale = scale[peak]
        pos = order.index(peak)
        shown = order[max(0, pos - neighbors): pos + neighbors + 1]
        n_samp = tmpl.shape[0]
        peak_sample = int(np.argmax(np.abs(tmpl[:, peak])))
        step = max(1, math.ceil(n_samp / wave_points))
        idx = np.arange(peak_sample % step, n_samp, step)
        wave = {
            "peak_channel": channel_ids[peak],
            "channels": [channel_ids[c] for c in shown],
            "waveforms": {channel_ids[c]: [round(float(v), 3) for v in tmpl[idx, c] * scale[c]]
                          for c in shown},
            "wave_ms": round(float((idx[-1] - idx[0]) / fs * 1000.0), 4),
            "peak_index": int(np.flatnonzero(idx == peak_sample)[0]),
        }

    # ISI: per-segment intervals, in the exact arithmetic SpikeInterface's
    # isi_violations uses (seconds, diff, strict <). An interval of exactly the
    # window can land either side of it in float, and matching SI's arithmetic
    # is what keeps n_refractory equal to the saved isi_violations_count.
    trains = [np.asarray(sorting.get_unit_spike_train(u, segment_index=s))
              for s in range(len(seg_starts))]
    n_spikes = int(sum(t.size for t in trains))
    isi_s = np.concatenate([np.diff(t / fs) for t in trains]) if trains else np.zeros(0)
    isi_ms = isi_s * 1000.0
    n_bins = max(1, int(round(isi_max_ms / isi_bin_ms)))
    edges = np.linspace(0.0, n_bins * isi_bin_ms, n_bins + 1)
    counts, _ = np.histogram(isi_ms[isi_ms < edges[-1]], bins=edges)
    n_refractory = int(np.sum(isi_s < refractory_ms / 1000.0))

    # Amplitude over time: the saved per-spike amplitudes, binned by spike time.
    amplitude = None
    amps = amplitudes.get(str(u))
    if amps is not None:
        t_s = np.concatenate([t / fs + start for t, start in zip(trains, seg_starts)])
        amps = np.asarray(amps, dtype=float) * peak_scale
        t_edges = np.linspace(0.0, duration_s, amp_bins + 1)
        which = np.clip(np.digitize(t_s, t_edges) - 1, 0, amp_bins - 1)
        med, cnt = [], []
        for b in range(amp_bins):
            sel = amps[which == b]
            cnt.append(int(sel.size))
            med.append(round(float(np.median(sel)), 3) if sel.size else None)
        amplitude = {"t_s": [round(float(t), 3) for t in (t_edges[:-1] + t_edges[1:]) / 2],
                     "median_uV": med, "n": cnt}

    return {
        "unit": str(u),
        "n_spikes": n_spikes,
        "units_in_uV": units_in_uV,
        **wave,
        "isi": {"bin_ms": float(isi_bin_ms), "max_ms": float(edges[-1]),
                "counts": [int(c) for c in counts], "refractory_ms": float(refractory_ms),
                "n_refractory": n_refractory, "ratio": ratios.get(str(u))},
        "amplitude": amplitude,
    }


def evidence_for_units(analyzer_dir, unit_ids=None, *, neighbors=1, wave_points=40,
                       isi_max_ms=25.0, isi_bin_ms=0.5, amp_bins=24) -> "dict[str, dict]":
    """``{str(unit_id): evidence}`` for ``unit_ids`` (all units when None).

    Loads the SortingAnalyzer at ``analyzer_dir`` once. Raises KeyError naming the
    available ids when a requested unit is not in the sort. A missing extension
    degrades its block: no ``templates`` -> ``waveforms``/``peak_channel``/
    ``wave_ms``/``peak_index`` None and ``channels`` empty; no
    ``spike_amplitudes`` -> ``amplitude`` None. The ISI block needs only the sorting.
    """
    import spikeinterface.full as si

    import report  # the refractory window's one home (see the module docstring)

    analyzer = si.load_sorting_analyzer(Path(analyzer_dir))
    by_str = {str(u): (i, u) for i, u in enumerate(analyzer.unit_ids)}
    wanted = list(by_str) if unit_ids is None else [str(u) for u in unit_ids]
    missing = [u for u in wanted if u not in by_str]
    if missing:
        raise KeyError(f"unit {', '.join(missing)} is not in this sort "
                       f"(units: {', '.join(by_str)})")

    ext = analyzer.get_extension("templates")
    templates = ext.get_data(operator="average") if ext is not None else None  # (u, s, ch)
    scale, units_in_uV = _to_uV_scale(analyzer)
    fs = float(analyzer.sampling_frequency)
    n_seg = analyzer.get_num_segments()
    seg_lengths = [analyzer.get_num_samples(s) / fs for s in range(n_seg)]
    seg_starts = [float(sum(seg_lengths[:s])) for s in range(n_seg)]

    shared = dict(templates=templates, scale=scale, units_in_uV=units_in_uV,
                  order=_probe_order(analyzer), fs=fs, seg_starts=seg_starts,
                  duration_s=float(sum(seg_lengths)),
                  refractory_ms=report._refractory_ms(analyzer),
                  ratios=_saved_ratios(analyzer),
                  amplitudes=sort_summary.spike_amplitudes_by_unit(analyzer),
                  neighbors=neighbors, wave_points=wave_points, isi_max_ms=isi_max_ms,
                  isi_bin_ms=isi_bin_ms, amp_bins=amp_bins)
    return {key: _evidence(analyzer, by_str[key][1], by_str[key][0], **shared)
            for key in wanted}


def unit_evidence(analyzer_dir, unit_id, **kw) -> dict:
    """The evidence dict for one unit (see ``evidence_for_units``)."""
    return evidence_for_units(analyzer_dir, [unit_id], **kw)[str(unit_id)]


def main() -> int:
    import argparse

    import runs

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sorter", required=True)
    parser.add_argument("--unit", default=None, help="unit id (default: every unit)")
    args = parser.parse_args()

    analyzer_dir = runs.sort_paths(args.sorter)["analyzer"]
    if not analyzer_dir.is_dir():
        print(f"no saved analyzer for {args.sorter} at {analyzer_dir}", file=sys.stderr)
        return 1
    try:
        out = (unit_evidence(analyzer_dir, args.unit) if args.unit is not None
               else evidence_for_units(analyzer_dir))
    except KeyError as exc:
        print(exc.args[0], file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
