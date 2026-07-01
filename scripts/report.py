"""Build a single self-contained interactive HTML report for the recording.

    uv run python scripts/make_report.py   # interactive launcher (preferred)
    uv run python -c "import sys; sys.path.insert(0,'scripts'); import report; report.build_report()"

Writes outputs/report.html — one offline file (Plotly JS inlined) covering loader
health, LFP, .nev online units, the saved sort (the most complete saved analyzer
by default), quality metrics and events. Read-only with respect to the data; it
only writes the HTML.

Single source of truth for the sort = the saved SortingAnalyzer (sorting +
templates + quality_metrics all come from it, so they can never disagree). The
loose outputs/<sorter>/sorting/ folder and quality_metrics.csv are ignored.
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import sort_summary  # noqa: E402  (array/yield headline metrics: load/compute/format)

OUTPUT_DIR = bio.REPO_ROOT / "outputs"
DEFAULT_ANALYZER_DIR = OUTPUT_DIR / "tridesclous2" / "analyzer"
LFP_WINDOW_S = 10.0
LFP_MAX_CHANNELS = 8


def _run_info(analyzer_dir) -> dict:
    """Read outputs/<sorter>/run_info.json (sort provenance). {} if absent."""
    try:
        return json.loads((Path(analyzer_dir).parent / "run_info.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - provenance is optional
        return {}


def _analyzer_window_seconds(analyzer_dir) -> float:
    """The sorted window length of a saved analyzer (its own total duration).

    Prefers the cheap run_info.json value; falls back to loading the analyzer.
    Returns -1.0 if neither is readable (so it ranks below any real sort).
    """
    eff = _run_info(analyzer_dir).get("effective_seconds")
    if isinstance(eff, (int, float)):
        return float(eff)
    try:
        import spikeinterface.full as si
        return float(si.load_sorting_analyzer(analyzer_dir).get_total_duration())
    except Exception:  # noqa: BLE001 - unreadable analyzer
        return -1.0


def _pick_default_analyzer() -> Path:
    """Choose the saved analyzer to report when none is given.

    Prefers the **most complete** sort — the largest sorted window, tie-broken by
    recency — so a bare ``build_report()`` shows a full-recording sort rather than
    whichever sorter happens to be hardcoded or a leftover short ``--duration``
    smoke test. Falls back to the legacy path when nothing is saved.
    """
    candidates = []
    for d in sorted(OUTPUT_DIR.glob("*/analyzer")):
        if not d.is_dir():
            continue
        try:
            mtime = d.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append((_analyzer_window_seconds(d), mtime, d))
    if not candidates:
        return DEFAULT_ANALYZER_DIR
    candidates.sort(key=lambda c: (c[0], c[1]))  # largest window, then most recent
    return candidates[-1][2]


def _probe_caveat(probe, n_drop=0) -> str:
    """Geometry note HTML, conditional on the active probe NAME (or None).

    Placeholder/independent → the not-physical warning; a real probe → a calm
    'geometry: <name>' note (spatial views are then meaningful)."""
    drop = (f' {n_drop} non-neural analog aux channel(s) were excluded from the sort.'
            if n_drop else "")
    if probe in (None, "independent"):
        return ('<div class="caveat">Placeholder independent-channel probe — cross-channel '
                'spatial structure (depth / probe map) is not physical.' + drop + '</div>')
    import probes as _probes  # lazy import (probeinterface; not needed unless a real probe is active)
    prof = _probes.get(probe)
    label = prof["label"] if prof else str(probe)
    return (f'<div class="note">Probe geometry: <strong>{html.escape(label)}</strong>. '
            'Spatial views reflect this geometry; verify it matches your array.' + drop + '</div>')


def _getting_started_html(data_dir) -> str:
    """Prominent fresh-clone guidance shown when no recording is present."""
    folder = str(Path(data_dir).expanduser().resolve()) if data_dir else str(bio.REPO_ROOT)
    rows = "".join(
        f"<li><code>&lt;RECORDING&gt;{ext}</code> — {html.escape(label)}</li>"
        for ext, label in (
            (".ns2", "LFP — analog @ 1 kHz"),
            (".ns5", "Broadband — raw @ 30 kHz (spike-sortable)"),
            (".nev", "Spike events + digital markers"),
        )
    )
    return ('<div class="caveat"><strong>No recording found — nothing to report yet.</strong> '
            'Drop a Blackrock file set (three files sharing one base name) into '
            f'<code>{html.escape(folder)}</code> (or pass <code>--data-dir</code>):'
            f'<ul>{rows}</ul>'
            'The raw <code>.ns5/.ns2/.nev</code> are git-ignored, so a fresh clone has none.</div>')


# --------------------------------------------------------------------------- #
# Loading: every stage isolated so one failure -> a red row, never a crash.
# --------------------------------------------------------------------------- #
def _broadband_detail(r) -> str:
    """Format the broadband stage detail, distinguishing neural vs aux channels.

    When the recording has a mix of neural and non-neural (aux/analog) channels
    the detail reads "16 neural + 6 aux ch, ..." so downstream tools can parse
    the NEURAL count directly (e.g. MenuController.recording_channels()).
    Falls back to the total count when the split cannot be determined.
    """
    total = r.get_num_channels()
    try:
        n_neural = len(bio.neural_channel_ids(r))
    except Exception:  # noqa: BLE001 - detail is best-effort
        n_neural = total
    base = f"{r.get_total_duration():.1f}s @ {r.get_sampling_frequency():g} Hz"
    if 0 < n_neural < total:
        return f"{n_neural} neural + {total - n_neural} aux ch, {base}"
    return f"{total} ch, {base}"


def _gather(data_dir, analyzer_dir):
    """Load each stage independently. Returns (objects: dict, status: list[dict])."""
    objects, status = {}, []

    def stage(key, label, loader, ok_detail, fail_status="FAIL"):
        try:
            obj = loader()
            objects[key] = obj
            status.append({"stage": label, "status": "PASS", "detail": ok_detail(obj)})
        except Exception as e:  # noqa: BLE001 - report the failure, don't abort
            objects[key] = None
            status.append({"stage": label, "status": fail_status, "detail": repr(e)})

    stage("lfp", "LFP (.ns2)", lambda: bio.read_lfp(data_dir),
          lambda r: f"{r.get_num_channels()} ch, {r.get_total_duration():.1f}s @ {r.get_sampling_frequency():g} Hz")
    stage("broadband", "Broadband (.ns5)", lambda: bio.read_broadband(data_dir),
          _broadband_detail)
    stage("nev", ".nev online units", lambda: bio.read_spikes(data_dir),
          lambda s: f"{len(s.get_unit_ids())} units (id 0 = unsorted)")

    def load_analyzer():
        import spikeinterface.full as si
        return si.load_sorting_analyzer(analyzer_dir)
    stage("analyzer", "Saved sort (analyzer)", load_analyzer,
          lambda a: f"{len(a.unit_ids)} units, {a.get_total_duration():.1f}s sorted @ {a.sampling_frequency:g} Hz",
          fail_status="SKIP")

    def detail_events(ev):
        n = sum(len(e["times"]) for e in ev)
        nonempty = [e["name"] for e in ev if len(e["times"])]
        return f"{len(ev)} channels, {n} markers" + (f" on {', '.join(nonempty)}" if nonempty else " (all empty)")
    stage("events", "Events (.nev markers)", lambda: bio.read_events(data_dir),
          detail_events, fail_status="SKIP")

    return objects, status


# --------------------------------------------------------------------------- #
# HTML assembly helpers
# --------------------------------------------------------------------------- #
def _fig_html(fig) -> str:
    """One Plotly figure as an embeddable div (JS is included once in <head>)."""
    return fig.to_html(full_html=False, include_plotlyjs=False, default_width="100%")


def _safe_section(sec_id, title, render, *args) -> dict:
    """Render one section; a failure becomes a visible red box, not a crash."""
    try:
        body = render(*args)
    except Exception as e:  # noqa: BLE001
        body = f'<div class="err">Section failed to render: {html.escape(repr(e))}</div>'
    return {"id": sec_id, "title": title, "html": body}


_CSS = """
:root { --fg:#1b1f24; --muted:#6a737d; --line:#e1e4e8; --bg:#fff; --accent:#2b6cb0; }
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       color: var(--fg); margin: 0; background: var(--bg); line-height: 1.5; }
nav { position: sticky; top: 0; background: var(--bg); border-bottom: 1px solid var(--line);
      padding: 10px 24px; display: flex; gap: 16px; flex-wrap: wrap; z-index: 10; font-size: 14px; }
nav a { color: var(--accent); text-decoration: none; }
main { max-width: 1100px; margin: 0 auto; padding: 0 24px 64px; }
h1 { margin: 28px 0 4px; } h2 { margin: 40px 0 8px; border-bottom: 1px solid var(--line); padding-bottom: 6px; }
.sub { color: var(--muted); margin: 0 0 16px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); }
th { cursor: pointer; user-select: none; background: #f6f8fa; }
.badge { font-weight: 600; padding: 1px 8px; border-radius: 10px; font-size: 12px; color: #fff; }
.PASS { background: #2a8a3e; } .FAIL { background: #c0392b; } .SKIP { background: #8a8f95; }
.err { background: #fdecea; border: 1px solid #f5c6cb; color: #842029; padding: 10px 14px; border-radius: 6px; }
.skip { color: var(--muted); font-style: italic; }
.note { color: var(--muted); font-size: 13px; }
.caveat { background: #fff8e1; border: 1px solid #ffe0a3; padding: 10px 14px; border-radius: 6px; font-size: 13px; }
"""

_SORT_JS = """
function sortTable(table, col, numeric) {
  var tbody = table.tBodies[0];
  var rows = Array.prototype.slice.call(tbody.rows);
  var asc = !(table.getAttribute('data-col') == col && table.getAttribute('data-dir') == 'asc');
  rows.sort(function(a, b) {
    var x = a.cells[col].innerText, y = b.cells[col].innerText;
    if (numeric) { x = parseFloat(x); y = parseFloat(y); }
    return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1);
  });
  rows.forEach(function(r) { tbody.appendChild(r); });
  table.setAttribute('data-col', col);
  table.setAttribute('data-dir', asc ? 'asc' : 'desc');
}
"""


def _html_document(title, sections) -> str:
    nav = " ".join(f'<a href="#{s["id"]}">{html.escape(s["title"])}</a>' for s in sections)
    body = []
    for s in sections:
        body.append(f'<section id="{s["id"]}"><h2>{html.escape(s["title"])}</h2>{s["html"]}</section>')
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
<script>{get_plotlyjs()}</script>
<script>{_SORT_JS}</script>
</head><body>
<nav>{nav}</nav>
<main>
<h1>{html.escape(title)}</h1>
<p class="sub">Generated {generated} — self-contained, works offline.</p>
{''.join(body)}
</main></body></html>"""


# --------------------------------------------------------------------------- #
# Section renderers (each returns inner HTML; wrapped by _safe_section)
# --------------------------------------------------------------------------- #
def _render_status(status, data_dir=None) -> str:
    # When no raw data loaded at all (fresh clone / wrong folder), lead with
    # actionable guidance instead of a wall of FileNotFoundError reprs.
    data_stages = [r for r in status if r["stage"] in ("LFP (.ns2)", "Broadband (.ns5)", ".nev online units")]
    intro = _getting_started_html(data_dir) if data_stages and all(r["status"] != "PASS" for r in data_stages) else ""
    rows = "".join(
        f'<tr><td><span class="badge {r["status"]}">{r["status"]}</span></td>'
        f'<td>{html.escape(r["stage"])}</td><td>{html.escape(r["detail"])}</td></tr>'
        for r in status
    )
    return (intro
            + '<p class="note">One row per pipeline stage — PASS means it loaded, '
            'SKIP means optional/absent, FAIL means broken.</p>'
            f'<table><thead><tr><th>Status</th><th>Stage</th><th>Detail</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>')


def _render_footer(status, probe=None) -> str:
    import importlib
    versions = []
    for mod in ["spikeinterface", "neo", "plotly", "numpy", "scipy"]:
        try:
            versions.append(f"{mod} {importlib.import_module(mod).__version__}")
        except Exception:  # noqa: BLE001
            versions.append(f"{mod} (not importable)")
    return (f'<p class="note">{html.escape(" · ".join(versions))}</p>'
            + _probe_caveat(probe)
            + '<p class="note">The broadband stream mixes 16 neural channels (raw 1–16) '
              'with 6 analog aux channels (analog 1–6); the sort excludes the analog aux '
              'channels by default.</p>')


def _render_lfp(lfp) -> str:
    if lfp is None:
        return '<p class="skip">LFP failed to load — see the status banner.</p>'
    from scipy.signal import welch

    fs = lfp.get_sampling_frequency()
    n = int(min(LFP_WINDOW_S, lfp.get_total_duration()) * fs)
    chan_ids = list(lfp.get_channel_ids())[:LFP_MAX_CHANNELS]
    traces = lfp.get_traces(start_frame=0, end_frame=n, channel_ids=chan_ids)
    t = np.arange(n) / fs

    # Stacked traces with a vertical offset so channels don't overlap.
    spacing = 1.2 * float(np.nanpercentile(np.abs(traces), 99)) if traces.size else 1.0
    spacing = spacing or 1.0
    traces_fig = go.Figure()
    for i, ch in enumerate(chan_ids):
        traces_fig.add_trace(go.Scatter(x=t, y=traces[:, i] + i * spacing, mode="lines",
                                        name=str(ch), line=dict(width=0.8)))
    traces_fig.update_yaxes(tickvals=[i * spacing for i in range(len(chan_ids))],
                            ticktext=[str(c) for c in chan_ids], title="channel")
    traces_fig.update_layout(title=f"LFP — first {LFP_WINDOW_S:g}s, {len(chan_ids)} channels @ {fs:g} Hz",
                             xaxis_title="time (s)", height=460, margin=dict(t=40, b=40))

    # Power spectrum (Welch) over the same channels.
    psd_fig = go.Figure()
    for i, ch in enumerate(chan_ids):
        f, pxx = welch(traces[:, i], fs=fs, nperseg=min(1024, n))
        psd_fig.add_trace(go.Scatter(x=f, y=pxx, mode="lines", name=str(ch), line=dict(width=1)))
    psd_fig.update_layout(title="LFP power spectrum (Welch)", xaxis_title="frequency (Hz)",
                          yaxis_title="power", yaxis_type="log", height=380, margin=dict(t=40, b=40))

    return ('<p class="note">First few channels shown stacked; toggle channels via the legend.</p>'
            + _fig_html(traces_fig) + _fig_html(psd_fig))


def _spike_figs(unit_ids, train_seconds, title_prefix, total_duration=None):
    """Build (raster_fig, rate_fig) from a {unit_id: spike_times_seconds} provider.

    Firing rates use total_duration (the recording length) when given, so they
    match the quality-metrics table; otherwise they fall back to the last spike
    time across units.
    """
    trains = {u: np.asarray(train_seconds(u), dtype=float) for u in unit_ids}
    duration = total_duration if total_duration else max(
        (tr[-1] for tr in trains.values() if tr.size), default=1.0)
    duration = duration or 1.0

    raster = go.Figure()
    for row, u in enumerate(unit_ids):
        tr = trains[u]
        raster.add_trace(go.Scatter(x=tr, y=np.full(tr.shape, row), mode="markers",
                                    marker=dict(symbol="line-ns-open", size=6),
                                    name=f"unit {int(u)}"))
    raster.update_yaxes(tickvals=list(range(len(unit_ids))),
                        ticktext=[str(int(u)) for u in unit_ids], title="unit id")
    raster.update_layout(title=f"{title_prefix} — spike raster ({len(unit_ids)} units)",
                         xaxis_title="time (s)", height=max(320, 22 * len(unit_ids) + 80),
                         margin=dict(t=40, b=40), showlegend=False)

    rates = [trains[u].size / duration for u in unit_ids]
    rate = go.Figure(go.Bar(x=[str(int(u)) for u in unit_ids], y=rates))
    rate.update_layout(title=f"{title_prefix} — mean firing rate", xaxis_title="unit id",
                       yaxis_title="rate (Hz)", height=360, margin=dict(t=40, b=40))
    return raster, rate


def _render_nev(nev) -> str:
    if nev is None:
        return '<p class="skip">.nev units failed to load — see the status banner.</p>'
    fs = nev.get_sampling_frequency()
    unit_ids = list(nev.get_unit_ids())
    try:
        total = nev.get_total_duration()
    except Exception:  # noqa: BLE001 - a bare .nev Sorting may not know its duration
        total = None
    raster, rate = _spike_figs(unit_ids, lambda u: nev.get_unit_spike_train(u) / fs,
                               "Online (.nev) units", total_duration=total)
    return ('<p class="note">Already-detected online units from the .nev. '
            'Blackrock convention: unit 0 = unsorted threshold crossings, 1..n = sorted, 255 = noise.</p>'
            + _fig_html(raster) + _fig_html(rate))


def _render_sorted(analyzer, sorter_label, info=None, probe=None) -> str:
    if analyzer is None:
        return ('<p class="skip">No saved analyzer found — run a sort from the launcher '
                '(<code>python scripts/make_report.py</code>).</p>')
    sorting = analyzer.sorting
    fs = analyzer.sampling_frequency
    unit_ids = list(analyzer.unit_ids)
    dur = analyzer.get_total_duration()

    raster, rate = _spike_figs(unit_ids, lambda u: sorting.get_unit_spike_train(u) / fs,
                               f"Sorted ({sorter_label}) units", total_duration=dur)

    # Waveform templates: each unit on its peak-to-peak best channel.
    tex = analyzer.get_extension("templates")
    templates = tex.get_data()            # (n_units, n_samples, n_channels)
    nbefore = tex.nbefore
    chan_ids = list(analyzer.channel_ids)
    n_samples = templates.shape[1]
    tms = (np.arange(n_samples) - nbefore) / fs * 1000.0
    wf = go.Figure()
    for i, u in enumerate(unit_ids):
        best = int(np.argmax(np.ptp(templates[i], axis=0)))   # numpy 2.x: ndarray.ptp() removed
        wf.add_trace(go.Scatter(x=tms, y=templates[i][:, best], mode="lines",
                                name=f"unit {int(u)} (ch {chan_ids[best]})"))
    wf.update_layout(title="Waveform template per unit (best channel)",
                     xaxis_title="time relative to spike (ms)", yaxis_title="amplitude (a.u.)",
                     height=440, margin=dict(t=40, b=40))

    # Partial-sort caveat: a --duration smoke test sorts a window far shorter than
    # the full recording the LFP/.nev sections above cover. Flag it loudly so a
    # reader never conflates a 20 s sort with the 132 s recording.
    info = info or {}
    eff, tot = info.get("effective_seconds"), info.get("total_seconds")
    partial = isinstance(eff, (int, float)) and isinstance(tot, (int, float)) and eff < tot - 1.0
    partial_html = (
        f'<div class="caveat"><strong>Partial sort:</strong> only the first {eff:.0f}s of the '
        f'{tot:.0f}s recording were sorted (e.g. a quick <code>--duration</code> test). The LFP '
        f'and .nev sections above cover the full recording — unit counts are not comparable '
        f'across different windows.</div>' if partial else "")
    probe_html = _probe_caveat(probe, info.get("n_dropped_analog") or 0)
    return (f'<p class="note">Sorted with {sorter_label} over {dur:.1f}s sorted data, '
            f'{len(unit_ids)} units. Toggle units via the legend.</p>'
            + partial_html + probe_html
            + _fig_html(raster) + _fig_html(rate) + _fig_html(wf))


def _render_qc(analyzer) -> str:
    if analyzer is None:
        return '<p class="skip">No saved analyzer — quality metrics unavailable.</p>'
    qm = analyzer.get_extension("quality_metrics").get_data()  # DataFrame, index = unit ids
    cols = [c for c in ["firing_rate", "snr", "isi_violations_ratio", "isi_violations_count"]
            if c in qm.columns]
    qm = qm.sort_values("snr", ascending=False) if "snr" in qm.columns else qm

    headers = "".join(
        f'<th onclick="sortTable(this.closest(\'table\'),{j + 1},true)">{html.escape(c)}</th>'
        for j, c in enumerate(cols)
    )
    rows = ""
    for uid, r in qm.iterrows():
        cells = "".join(f"<td>{r[c]:.3g}</td>" for c in cols)
        rows += (f'<tr><td onclick="sortTable(this.closest(\'table\'),0,true)">{int(uid)}</td>{cells}</tr>')
    table = (f'<p class="note">Click a column header to sort.</p>'
             f'<table class="qc"><thead><tr>'
             f'<th onclick="sortTable(this.closest(\'table\'),0,true)">unit</th>{headers}</tr></thead>'
             f'<tbody>{rows}</tbody></table>')

    scatter = ""
    if {"firing_rate", "snr"} <= set(qm.columns):
        size = None
        if "isi_violations_ratio" in qm.columns:
            viol = qm["isi_violations_ratio"].to_numpy(dtype=float)
            size = 8 + 18 * (viol / viol.max()) if viol.max() > 0 else None
        fig = go.Figure(go.Scatter(
            x=qm["firing_rate"], y=qm["snr"], mode="markers+text",
            text=[str(int(u)) for u in qm.index], textposition="top center",
            marker=dict(size=size if size is not None else 12),
            hovertemplate="unit %{text}<br>rate %{x:.2f} Hz<br>SNR %{y:.2f}<extra></extra>"))
        fig.update_layout(title="SNR vs firing rate (marker size = ISI-violation ratio)",
                          xaxis_title="firing rate (Hz)", yaxis_title="SNR",
                          height=420, margin=dict(t=40, b=40))
        scatter = _fig_html(fig)
    return table + scatter


def _render_summary(analyzer, analyzer_dir) -> str:
    """Array / yield headline block: the six lab-requested metrics for this sort.

    Prefers the persisted summary.json (written by run_sorting); falls back to
    computing it from the saved analyzer for older sorts that predate it.
    """
    summary = sort_summary.load_summary(Path(analyzer_dir).parent) if analyzer_dir else None
    if summary is None and analyzer is not None:
        try:
            summary = sort_summary.compute_summary(analyzer)
        except Exception:  # noqa: BLE001 - degrade to a skip row rather than crash
            summary = None
    if summary is None:
        return '<p class="skip">No saved analyzer — array/yield summary unavailable.</p>'
    if summary.get("n_units", 0) == 0:
        return '<p class="skip">No units in this sort — array/yield summary is empty.</p>'

    amp = "µV" if summary.get("units_in_uV", True) else "a.u."
    row = sort_summary.headline_row(summary)
    # Headline 6-metric table.
    head_rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>"
                        for k, v in row.items())
    head_table = ('<table class="qc"><thead><tr><th>metric</th><th>value</th></tr></thead>'
                  f'<tbody>{head_rows}</tbody></table>')

    # Per-unit V_pp / SNR table (the per-unit basis of the V_pp & SNR headlines).
    per_unit = summary.get("per_unit", [])
    pu_rows = ""
    for p in per_unit:
        snr = "—" if p.get("snr") is None else f"{p['snr']:.3g}"
        pu_rows += (f"<tr><td onclick=\"sortTable(this.closest('table'),0,true)\">{p['unit']}</td>"
                    f"<td>{p['v_pp_uV']:.3g}</td><td>{snr}</td>"
                    f"<td>{html.escape(str(p.get('best_channel', '')))}</td></tr>")
    pu_table = (
        '<p class="note">Per-unit peak-to-peak amplitude on the best channel. Click a header to sort.</p>'
        '<table class="qc"><thead><tr>'
        '<th onclick="sortTable(this.closest(\'table\'),0,true)">unit</th>'
        f'<th onclick="sortTable(this.closest(\'table\'),1,true)">V_pp ({amp})</th>'
        '<th onclick="sortTable(this.closest(\'table\'),2,true)">SNR</th>'
        '<th onclick="sortTable(this.closest(\'table\'),3,false)">best ch</th>'
        f'</tr></thead><tbody>{pu_rows}</tbody></table>')

    # Per-channel noise floor, active channels highlighted.
    noise = (summary.get("noise_floor_uV") or {}).get("per_channel") or []
    active = set(summary.get("active_channels", []))
    chan_ids = [str(c) for c in (analyzer.channel_ids if analyzer is not None else range(len(noise)))]
    noise_html = ""
    if noise and len(noise) == len(chan_ids):
        colours = ["#3fb950" if c in active else "#8b949e" for c in chan_ids]
        fig = go.Figure(go.Bar(x=chan_ids, y=[0 if v is None else v for v in noise],
                               marker_color=colours))
        fig.update_layout(title=f"Noise floor per channel ({amp}) — green = active electrode",
                          xaxis_title="channel", yaxis_title=f"noise floor ({amp})",
                          height=360, margin=dict(t=40, b=40))
        noise_html = _fig_html(fig)

    note = ('<p class="note">Amplitudes are in µV via the recording gain. '
            'Noise floor is measured on the band-passed + common-median-referenced '
            'signal the sort uses (so it is a post-CMR figure, consistent with SNR). '
            '"Active electrode" = the peak channel of ≥1 sorted unit.</p>'
            if summary.get("units_in_uV", True) else
            '<p class="note">No µV gain on this recording — amplitudes are raw a.u.</p>')
    return note + head_table + pu_table + noise_html


def _render_probe(analyzer, analyzer_dir) -> str:
    """Collection-sites map: each electrode contact at its physical (x, y) µm
    position, labelled by channel, coloured by per-channel noise floor, with the
    sort's active electrodes ringed. Shows the geometry the sort actually used."""
    if analyzer is None:
        return '<p class="skip">No saved analyzer — probe geometry unavailable.</p>'
    try:
        loc = np.asarray(analyzer.get_channel_locations())
    except Exception:  # noqa: BLE001 - no geometry attached
        return '<p class="skip">This sort has no probe geometry attached.</p>'
    chan_ids = [str(c) for c in analyzer.channel_ids]
    summary = sort_summary.load_summary(Path(analyzer_dir).parent) if analyzer_dir else None
    active = set((summary or {}).get("active_channels", []))
    noise = (summary or {}).get("noise_floor_uV", {}).get("per_channel") if summary else None
    x, y = loc[:, 0].astype(float), loc[:, 1].astype(float)

    fig = go.Figure()
    marker = dict(size=18, line=dict(color="black", width=1))
    if noise and len(noise) == len(chan_ids) and any(v is not None for v in noise):
        marker.update(color=[np.nan if v is None else v for v in noise], colorscale="Viridis",
                      colorbar=dict(title="noise (µV)"), showscale=True)
        hover = [f"ch {c}<br>({xi:.0f}, {yi:.0f}) µm<br>noise {('' if v is None else f'{v:.2f} µV')}"
                 for c, xi, yi, v in zip(chan_ids, x, y, noise)]
    else:
        marker.update(color=["#3fb950" if c in active else "#8b949e" for c in chan_ids])
        hover = [f"ch {c}<br>({xi:.0f}, {yi:.0f}) µm" for c, xi, yi in zip(chan_ids, x, y)]
    fig.add_trace(go.Scatter(x=x, y=y, mode="markers+text", marker=marker,
                             text=chan_ids, textposition="middle right",
                             hovertext=hover, hoverinfo="text", name="sites"))
    if active:
        ax = [xi for c, xi in zip(chan_ids, x) if c in active]
        ay = [yi for c, yi in zip(chan_ids, y) if c in active]
        fig.add_trace(go.Scatter(x=ax, y=ay, mode="markers", name="active electrode",
                                 marker=dict(size=30, color="rgba(0,0,0,0)",
                                             line=dict(color="#3fb950", width=3))))
    fig.update_layout(title="Collection sites (electrode geometry)",
                      xaxis_title="x (µm)", yaxis_title="depth y (µm)",
                      yaxis=dict(autorange="reversed"), height=560,
                      margin=dict(t=40, b=40),
                      xaxis=dict(range=[x.min() - max((x.max() - x.min()) * 0.6, 60),
                                        x.max() + max((x.max() - x.min()) * 0.6, 120)]))
    n_active = sum(1 for c in chan_ids if c in active)
    note = (f'<p class="note">{len(chan_ids)} contacts'
            + (f'; {n_active} are active (peak channel of ≥1 unit, ringed green). '
               'Marker colour = per-channel noise floor. ' if active else '. ')
            + 'For an interactive channel scroll use the menu’s "Scroll raw traces" '
            '(ephyviewer); <code>scripts/show_channels.py</code> writes probe_map.png + '
            'channels.png headless.</p>')
    return note + _fig_html(fig)


def _render_events(events) -> str:
    if events is None:
        return '<p class="skip">Events could not be read (best-effort) — see the status banner.</p>'
    nonempty = [e for e in events if len(e["times"])]
    empty_names = [e["name"] for e in events if not len(e["times"])]
    if not nonempty:
        return ('<p class="skip">No event markers present in this recording '
                f'({len(events)} event channel(s), all empty).</p>')
    fig = go.Figure()
    for row, e in enumerate(nonempty):
        times = np.asarray(e["times"], dtype=float)
        fig.add_trace(go.Scatter(x=times, y=np.full(times.shape, row), mode="markers",
                                 marker=dict(symbol="line-ns-open", size=8),
                                 name=f'{e["name"]} ({times.size})'))
    fig.update_yaxes(tickvals=list(range(len(nonempty))),
                     ticktext=[e["name"] for e in nonempty], title="event channel")
    fig.update_layout(title="Digital / analog event markers over time",
                      xaxis_title="time (s)", height=max(280, 40 * len(nonempty) + 120),
                      margin=dict(t=40, b=40), showlegend=False)
    note = (f'<p class="note">Empty channels: {html.escape(", ".join(empty_names))}.</p>'
            if empty_names else "")
    return _fig_html(fig) + note


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def build_report(data_dir=None, analyzer_dir=None, out_path=None, sorter_label=None, probe=None) -> Path:
    analyzer_dir = Path(analyzer_dir) if analyzer_dir else _pick_default_analyzer()
    sorter_label = sorter_label or analyzer_dir.parent.name
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "report.html")
    OUTPUT_DIR.mkdir(exist_ok=True)

    info = _run_info(analyzer_dir)
    objects, status = _gather(data_dir, analyzer_dir)
    sections = [
        _safe_section("status", "Status & provenance", _render_status, status, data_dir),
        _safe_section("lfp", "LFP (.ns2 @ 1 kHz)", _render_lfp, objects.get("lfp")),
        _safe_section("nev", ".nev online units", _render_nev, objects.get("nev")),
        _safe_section("sorted", f"Sorted units ({sorter_label})", _render_sorted, objects.get("analyzer"), sorter_label, info, probe),
        _safe_section("summary", "Array / yield summary", _render_summary, objects.get("analyzer"), analyzer_dir),
        _safe_section("probe", "Probe geometry & channels", _render_probe, objects.get("analyzer"), analyzer_dir),
        _safe_section("qc", "Quality metrics", _render_qc, objects.get("analyzer")),
        _safe_section("events", "Events", _render_events, objects.get("events")),
        _safe_section("footer", "About", _render_footer, status, probe),
    ]
    out_path.write_text(_html_document("PFCM7 recording report", sections), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    print(build_report())
