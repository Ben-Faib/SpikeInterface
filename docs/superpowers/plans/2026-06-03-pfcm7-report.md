# PFCM7 HTML report + interactive re-sort launcher — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a single self-contained interactive HTML report that re-exercises the loaders and visualizes the saved tridesclous2 sort, with an interactive terminal launcher that can trigger a quick/full re-sort.

**Architecture:** Two new files in `scripts/`. `report.py` loads everything through the existing `blackrock_io` loaders (each stage isolated in try/except → red ✗ instead of a crash), reads sorting+templates+QC exclusively from the saved `SortingAnalyzer`, builds Plotly figures, and writes one offline `outputs/report.html` (Plotly JS inlined). `make_report.py` prints loader health + live sort provenance, offers a reuse / quick re-sort / full re-sort terminal menu, runs `run_sorting.py` as a subprocess when asked (coupling only to its CLI + output dir, never its stdout), then calls the builder.

**Tech Stack:** Python 3.12, SpikeInterface (`spikeinterface.full`), Plotly (graph_objects + offline), numpy 2.4.6, scipy.signal.welch. Env: conda `si_env`.

> **Testing note — this repo has NO pytest suite** (see `CLAUDE.md`: "no test suite"; `verify_install.py` is "the closest thing to a test"). Strict red-green TDD does not fit visual HTML output here, so each task is verified by a **runnable smoke check** (`conda run -n si_env python -c "..."` that asserts on the generated HTML / printed output) and a commit — matching the project's established `verify_install.py` idiom. This deliberately adapts the TDD default to the project's reality.

> **Run all commands from the repo root** `/Users/benfaib/Spike/SpikeInterface`. The data set `PFCM7_d0ephys_Block2.{ns2,ns5,nev}` must be present in the root (it is).

---

### Task 1: Add Plotly to the environment

**Files:**
- Modify: `environment.yml`
- Modify: `requirements.txt`

- [ ] **Step 1: Confirm Plotly is absent (baseline)**

Run:
```bash
conda run -n si_env python -c "import plotly" 2>&1 | tail -1
```
Expected: `ModuleNotFoundError: No module named 'plotly'`

- [ ] **Step 2: Install Plotly into si_env**

Run:
```bash
conda run -n si_env python -m pip install "plotly>=5.20,<6"
```
Expected: ends with `Successfully installed ... plotly-5.x ...`

- [ ] **Step 3: Verify the import works**

Run:
```bash
conda run -n si_env python -c "import plotly, plotly.graph_objects as go; from plotly.offline import get_plotlyjs; print('plotly', plotly.__version__, 'js_bytes', len(get_plotlyjs()))"
```
Expected: `plotly 5.x js_bytes <a few million>`

- [ ] **Step 4: Pin it in both env files**

In `environment.yml`, under the `pip:` list (the project installs SpikeInterface via pip there), add a line:
```yaml
      - plotly>=5.20,<6
```
In `requirements.txt`, add a line:
```
plotly>=5.20,<6
```
Match the existing indentation/format of each file (open them first to copy the surrounding style).

- [ ] **Step 5: Commit**

```bash
git add environment.yml requirements.txt
git commit -m "deps: add plotly for the HTML report"
```

---

### Task 2: `report.py` scaffold — document shell, status banner, footer

**Files:**
- Create: `scripts/report.py`

This task produces a working `outputs/report.html` containing the status banner and footer. Later tasks add one section each.

- [ ] **Step 1: Create `scripts/report.py` with the scaffold**

```python
"""Build a single self-contained interactive HTML report for the recording.

    conda activate si_env
    python scripts/make_report.py          # interactive launcher (preferred)
    python -c "import sys; sys.path.insert(0,'scripts'); import report; report.build_report()"

Writes outputs/report.html — one offline file (Plotly JS inlined) covering loader
health, LFP, .nev online units, the tridesclous2 sort, quality metrics and
events. Read-only with respect to the data; it only writes the HTML.

Single source of truth for the sort = the saved SortingAnalyzer (sorting +
templates + quality_metrics all come from it, so they can never disagree). The
loose outputs/<sorter>/sorting/ folder and quality_metrics.csv are ignored.
"""
from __future__ import annotations

import html
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402

OUTPUT_DIR = bio.REPO_ROOT / "outputs"
DEFAULT_ANALYZER_DIR = OUTPUT_DIR / "tridesclous2" / "analyzer"
LFP_WINDOW_S = 10.0
LFP_MAX_CHANNELS = 8


# --------------------------------------------------------------------------- #
# Loading: every stage isolated so one failure -> a red row, never a crash.
# --------------------------------------------------------------------------- #
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
          lambda r: f"{r.get_num_channels()} ch, {r.get_total_duration():.1f}s @ {r.get_sampling_frequency():g} Hz")
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
def _render_status(status) -> str:
    rows = "".join(
        f'<tr><td><span class="badge {r["status"]}">{r["status"]}</span></td>'
        f'<td>{html.escape(r["stage"])}</td><td>{html.escape(r["detail"])}</td></tr>'
        for r in status
    )
    return ('<p class="note">One row per pipeline stage — PASS means it loaded, '
            'SKIP means optional/absent, FAIL means broken.</p>'
            f'<table><thead><tr><th>Status</th><th>Stage</th><th>Detail</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>')


def _render_footer(status) -> str:
    import importlib
    versions = []
    for mod in ["spikeinterface", "neo", "plotly", "numpy", "scipy"]:
        try:
            versions.append(f"{mod} {importlib.import_module(mod).__version__}")
        except Exception:  # noqa: BLE001
            versions.append(f"{mod} (not importable)")
    return (f'<p class="note">{html.escape(" · ".join(versions))}</p>'
            '<div class="caveat">Geometry caveat: the Blackrock files carry no electrode map, '
            'so sorting uses a placeholder independent-channel probe — per-unit results are valid, '
            'but cross-channel spatial information is not physical. The broadband stream also mixes '
            '16 neural channels (raw 1–16) with 6 analog aux channels (analog 1–6).</div>')


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def build_report(data_dir=None, analyzer_dir=None, out_path=None) -> Path:
    analyzer_dir = Path(analyzer_dir) if analyzer_dir else DEFAULT_ANALYZER_DIR
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "report.html")
    OUTPUT_DIR.mkdir(exist_ok=True)

    objects, status = _gather(data_dir, analyzer_dir)
    sections = [
        _safe_section("status", "Status & provenance", _render_status, status),
        _safe_section("footer", "About", _render_footer, status),
    ]
    out_path.write_text(_html_document("PFCM7 recording report", sections), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    print(build_report())
```

- [ ] **Step 2: Build and smoke-check the scaffold**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import report; p=report.build_report(); h=p.read_text(); assert 'Status &amp; provenance' in h; assert 'badge PASS' in h; assert 'Plotly' in h; print('ok', p, len(h), 'bytes')"
```
Expected: `ok .../outputs/report.html <a few million> bytes` (the size is large because Plotly JS is inlined — that is intended).

- [ ] **Step 3: Commit**

```bash
git add scripts/report.py
git commit -m "feat(report): scaffold report.py with status banner + footer"
```

---

### Task 3: LFP section — stacked traces + power spectrum

**Files:**
- Modify: `scripts/report.py`

- [ ] **Step 1: Add `_render_lfp` above `build_report`**

```python
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
```

- [ ] **Step 2: Wire it into `build_report`'s `sections` list** (insert after the status section, before footer):

```python
        _safe_section("status", "Status & provenance", _render_status, status),
        _safe_section("lfp", "LFP (.ns2 @ 1 kHz)", _render_lfp, objects.get("lfp")),
        _safe_section("footer", "About", _render_footer, status),
```

- [ ] **Step 3: Build and smoke-check**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import report; p=report.build_report(); h=p.read_text(); assert 'id=\"lfp\"' in h; assert h.count('Plotly.newPlot') >= 2; assert 'power spectrum' in h.lower(); print('ok lfp', len(h))"
```
Expected: `ok lfp <bytes>` (≥2 Plotly plots: traces + PSD).

- [ ] **Step 4: Commit**

```bash
git add scripts/report.py
git commit -m "feat(report): LFP traces + power-spectrum section"
```

---

### Task 4: `.nev` online units section — raster + firing rates

**Files:**
- Modify: `scripts/report.py`

- [ ] **Step 1: Add a shared raster/rate helper and `_render_nev` above `build_report`**

```python
def _spike_figs(unit_ids, train_seconds, title_prefix):
    """Build (raster_fig, rate_fig) from a {unit_id: spike_times_seconds} provider."""
    trains = {u: np.asarray(train_seconds(u), dtype=float) for u in unit_ids}
    duration = max((tr[-1] for tr in trains.values() if tr.size), default=1.0) or 1.0

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
    raster, rate = _spike_figs(unit_ids, lambda u: nev.get_unit_spike_train(u) / fs,
                               "Online (.nev) units")
    return ('<p class="note">Already-detected online units from the .nev. '
            'Blackrock convention: unit 0 = unsorted threshold crossings, 1..n = sorted, 255 = noise.</p>'
            + _fig_html(raster) + _fig_html(rate))
```

- [ ] **Step 2: Wire into `build_report`'s `sections`** (after the LFP section):

```python
        _safe_section("lfp", "LFP (.ns2 @ 1 kHz)", _render_lfp, objects.get("lfp")),
        _safe_section("nev", ".nev online units", _render_nev, objects.get("nev")),
        _safe_section("footer", "About", _render_footer, status),
```

- [ ] **Step 3: Build and smoke-check**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import report; p=report.build_report(); h=p.read_text(); assert 'id=\"nev\"' in h; assert 'firing rate' in h.lower(); print('ok nev', len(h))"
```
Expected: `ok nev <bytes>`.

- [ ] **Step 4: Commit**

```bash
git add scripts/report.py
git commit -m "feat(report): .nev online-units raster + firing rates"
```

---

### Task 5: Sorted-units section — raster, rates, waveform templates

**Files:**
- Modify: `scripts/report.py`

- [ ] **Step 1: Add `_render_sorted` above `build_report`** (reuses `_spike_figs` from Task 4)

```python
def _render_sorted(analyzer) -> str:
    if analyzer is None:
        return ('<p class="skip">No saved analyzer found — run a sort from the launcher '
                '(<code>python scripts/make_report.py</code>).</p>')
    sorting = analyzer.sorting
    fs = analyzer.sampling_frequency
    unit_ids = list(analyzer.unit_ids)
    dur = analyzer.get_total_duration()

    raster, rate = _spike_figs(unit_ids, lambda u: sorting.get_unit_spike_train(u) / fs,
                               "Sorted (tridesclous2) units")

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
                     xaxis_title="time from trough (ms)", yaxis_title="amplitude (a.u.)",
                     height=440, margin=dict(t=40, b=40))

    return (f'<p class="note">Sorted with tridesclous2 over {dur:.1f}s sorted data, '
            f'{len(unit_ids)} units. Toggle units via the legend.</p>'
            '<div class="caveat">Placeholder independent-channel probe + 6 analog aux channels '
            'are included — cross-channel spatial structure is not physical.</div>'
            + _fig_html(raster) + _fig_html(rate) + _fig_html(wf))
```

- [ ] **Step 2: Wire into `build_report`'s `sections`** (after the `.nev` section):

```python
        _safe_section("nev", ".nev online units", _render_nev, objects.get("nev")),
        _safe_section("sorted", "Sorted units (tridesclous2)", _render_sorted, objects.get("analyzer")),
        _safe_section("footer", "About", _render_footer, status),
```

- [ ] **Step 3: Build and smoke-check**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import report; p=report.build_report(); h=p.read_text(); assert 'id=\"sorted\"' in h; assert 'Waveform template' in h; print('ok sorted', len(h))"
```
Expected: `ok sorted <bytes>`.

- [ ] **Step 4: Commit**

```bash
git add scripts/report.py
git commit -m "feat(report): sorted-units raster, rates, waveform templates"
```

---

### Task 6: Quality-metrics section — sortable table + SNR scatter

**Files:**
- Modify: `scripts/report.py`

- [ ] **Step 1: Add `_render_qc` above `build_report`**

```python
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
```

- [ ] **Step 2: Wire into `build_report`'s `sections`** (after the sorted section):

```python
        _safe_section("sorted", "Sorted units (tridesclous2)", _render_sorted, objects.get("analyzer")),
        _safe_section("qc", "Quality metrics", _render_qc, objects.get("analyzer")),
        _safe_section("footer", "About", _render_footer, status),
```

- [ ] **Step 3: Build and smoke-check**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import report; p=report.build_report(); h=p.read_text(); assert 'id=\"qc\"' in h; assert 'sortTable' in h; assert 'SNR vs firing rate' in h; print('ok qc', len(h))"
```
Expected: `ok qc <bytes>`.

- [ ] **Step 4: Commit**

```bash
git add scripts/report.py
git commit -m "feat(report): quality-metrics sortable table + SNR scatter"
```

---

### Task 7: Events section — digital-marker timeline

**Files:**
- Modify: `scripts/report.py`

- [ ] **Step 1: Add `_render_events` above `build_report`**

```python
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
```

- [ ] **Step 2: Wire into `build_report`'s `sections`** (after the QC section):

```python
        _safe_section("qc", "Quality metrics", _render_qc, objects.get("analyzer")),
        _safe_section("events", "Events", _render_events, objects.get("events")),
        _safe_section("footer", "About", _render_footer, status),
```

- [ ] **Step 3: Build and smoke-check (full report, all 7 sections)**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import report; p=report.build_report(); h=p.read_text(); [print('has', s) or (s in h) for s in ['id=\"status\"','id=\"lfp\"','id=\"nev\"','id=\"sorted\"','id=\"qc\"','id=\"events\"','id=\"footer\"']]; assert all(s in h for s in ['id=\"status\"','id=\"lfp\"','id=\"nev\"','id=\"sorted\"','id=\"qc\"','id=\"events\"','id=\"footer\"']); print('ok full', len(h))"
```
Expected: prints each `has ...` line then `ok full <bytes>`.

- [ ] **Step 4: Open it and eyeball (manual)**

Run:
```bash
open outputs/report.html
```
Confirm: status banner all PASS, LFP traces pan/zoom, rasters/rates render, waveform templates show, QC table sorts on header click, events timeline shows `analog_input_channel_*`.

- [ ] **Step 5: Commit**

```bash
git add scripts/report.py
git commit -m "feat(report): events timeline; full 7-section report"
```

---

### Task 8: `make_report.py` — interactive launcher

**Files:**
- Create: `scripts/make_report.py`

- [ ] **Step 1: Create `scripts/make_report.py`**

```python
"""Interactive launcher for the PFCM7 HTML report.

    conda activate si_env
    python scripts/make_report.py                 # prints health, offers re-sort menu
    python scripts/make_report.py --data-dir /path/to/recording

Prints loader health + live sort provenance, then offers a terminal menu:
reuse the saved sort / quick re-sort / full re-sort. Re-sorting shells out to
run_sorting.py (coupling only to its CLI flags + outputs/<sorter>/ layout, never
its stdout), then builds outputs/report.html. Non-interactive stdin -> reuse.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import report  # noqa: E402

SORTER = "tridesclous2"
QUICK_SECONDS = 30
SCRIPTS_DIR = Path(__file__).resolve().parent


def _provenance(analyzer_dir: Path):
    if not analyzer_dir.exists():
        return None
    try:
        import spikeinterface.full as si
        a = si.load_sorting_analyzer(analyzer_dir)
        when = datetime.fromtimestamp(analyzer_dir.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return {"units": len(a.unit_ids), "duration": a.get_total_duration(), "when": when}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def _print_status(data_dir, analyzer_dir):
    _objects, status = report._gather(data_dir, analyzer_dir)
    print("\nPipeline status:")
    for r in status:
        print(f"  [{r['status']:4}] {r['stage']:22} {r['detail']}")


def _choose(prov) -> str:
    if prov is None:
        print("\nSaved sort: none found.")
    elif "error" in prov:
        print(f"\nSaved sort: present but unreadable ({prov['error']}).")
    else:
        print(f"\nSaved sort: {prov['units']} units, {prov['duration']:.1f}s sorted, run {prov['when']}.")
    if not sys.stdin.isatty():
        print("(non-interactive stdin -> reusing saved sort)")
        return "reuse"
    print("\n  [Enter] reuse saved sort and build the report")
    print(f"  [q]     quick re-sort (first {QUICK_SECONDS}s) then build")
    print("  [f]     full re-sort (whole recording) then build")
    return {"": "reuse", "q": "quick", "f": "full"}.get(input("> ").strip().lower(), "reuse")


def _resort(duration, data_dir) -> bool:
    cmd = [sys.executable, str(SCRIPTS_DIR / "run_sorting.py"), "--sorter", SORTER]
    if duration is not None:
        cmd += ["--duration", str(duration)]
    if data_dir:
        cmd += ["--data-dir", str(data_dir)]
    print(f"\n$ {' '.join(cmd)}\n")
    return subprocess.run(cmd).returncode == 0  # inherit stdout/stderr: live progress


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None, help="Folder with the .nev/.nsX (default: repo root).")
    args = parser.parse_args()

    analyzer_dir = bio.REPO_ROOT / "outputs" / SORTER / "analyzer"
    _print_status(args.data_dir, analyzer_dir)
    action = _choose(_provenance(analyzer_dir))

    if action in ("quick", "full"):
        ok = _resort(QUICK_SECONDS if action == "quick" else None, args.data_dir)
        if not ok:
            print("\nRe-sort failed (non-zero exit).")
            if not analyzer_dir.exists():
                print("No analyzer to report on — aborting.")
                return 1
            print("Building the report against the existing analyzer instead.")

    print("\nBuilding report ...")
    out = report.build_report(data_dir=args.data_dir, analyzer_dir=analyzer_dir)
    print(f"Report written: {out}")
    print(f"Open it:        file://{out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the non-interactive (piped stdin) path reuses + builds**

Run:
```bash
echo "" | conda run -n si_env python scripts/make_report.py
```
Expected: prints `Pipeline status:` with rows, `Saved sort: ... units ...`, `(non-interactive stdin -> reusing saved sort)`, then `Report written: .../outputs/report.html`. Exit code 0.

- [ ] **Step 3: Verify the interactive reuse path (simulate pressing Enter)**

Run:
```bash
printf "\n" | conda run -n si_env python scripts/make_report.py 2>&1 | tail -5
```
Expected: ends with `Report written:` / `Open it:` lines. (Because stdin is piped, it follows the non-interactive branch — that is fine; this just confirms it never blocks.)

- [ ] **Step 4: Commit**

```bash
git add scripts/make_report.py
git commit -m "feat(report): interactive make_report.py launcher with re-sort menu"
```

---

### Task 9: Graceful degradation check + docs + wrap-up

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Verify graceful degradation (missing analyzer → SKIP, not crash)**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import report; p=report.build_report(analyzer_dir='outputs/does_not_exist'); h=p.read_text(); assert 'badge SKIP' in h; assert 'No saved analyzer' in h; assert 'id=\"qc\"' in h; print('ok degraded', len(h))"
```
Expected: `ok degraded <bytes>` — the report still builds; sorted + QC sections show SKIP, status banner has a SKIP badge for the analyzer.

- [ ] **Step 2: Rebuild the normal report (restore good state)**

Run:
```bash
conda run -n si_env python -c "import sys; sys.path.insert(0,'scripts'); import report; print(report.build_report())"
```
Expected: prints the path; report is back to all-PASS.

- [ ] **Step 3: Add the new commands to `CLAUDE.md`**

In the `## Commands` fenced block, after the `run_sorting.py` lines, add:
```bash
python scripts/make_report.py          # interactive: health check + re-sort menu -> outputs/report.html
python scripts/make_report.py --data-dir /path/to/recording
```
And add a short sentence to the `## Architecture` section near the `run_sorting.py` paragraph:
> `scripts/report.py` builds a single self-contained `outputs/report.html` (Plotly inlined) from the loaders + the saved `SortingAnalyzer` (its single source of truth — the loose `sorting/` folder and `quality_metrics.csv` come from other runs and are ignored). `scripts/make_report.py` is the interactive launcher: it prints loader health + live sort provenance and offers reuse / quick / full re-sort (shelling out to `run_sorting.py`) before building.

- [ ] **Step 4: Add a "Report" subsection to `README.md`**

After the spike-sorting section, add:
```markdown
## One-glance HTML report

```bash
conda activate si_env
python scripts/make_report.py     # prints a health check, offers a re-sort menu,
                                  # then writes outputs/report.html
```

`outputs/report.html` is a single self-contained file (open it in any browser,
works offline) with: a PASS/FAIL status banner, LFP traces + power spectrum, the
`.nev` online units, the sorted units (raster + waveform templates), quality
metrics (sortable table + SNR scatter), and the event-marker timeline. Press
Enter to reuse the saved sort, or choose a quick/full re-sort first.
```
(Match the README's existing heading style; place it sensibly relative to surrounding sections.)

- [ ] **Step 5: Confirm `report.html` is git-ignored (no accidental commit of the big file)**

Run:
```bash
git status --porcelain outputs/report.html
```
Expected: **no output** (it's under `outputs/`, already git-ignored). If it appears, do not add it.

- [ ] **Step 6: Final commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: document make_report.py / report.html"
```

- [ ] **Step 7: Show the result**

Run:
```bash
git log --oneline -9 && echo "---" && ls -la outputs/report.html
```
Expected: the task commits listed; `outputs/report.html` present.

---

## Self-review notes (author)

- **Spec coverage:** status banner (T2), LFP+spectrum (T3), .nev units (T4), sorted units+waveforms (T5), QC table+scatter (T6), events (T7), footer/versions (T2), interactive launcher with reuse/quick/full menu + non-TTY default + subprocess re-sort coupling only to CLI+output dir (T8), plotly dependency (T1), graceful degradation + docs (T9). All spec sections mapped.
- **No-stdout-parsing rule:** enforced in T8 (`subprocess.run(cmd)` inherits stdio; success = returncode + analyzer existence).
- **numpy 2.x `ptp`:** T5 uses `np.ptp(...)`, not `.ptp()`.
- **Analyzer as single source of truth:** T5/T6 read sorting+templates+QC from the analyzer only.
- **Types:** `_spike_figs` defined in T4, reused in T5; `_fig_html`/`_safe_section`/`_gather` defined in T2, used throughout; `build_report(data_dir, analyzer_dir, out_path)` signature stable across T2–T9.
