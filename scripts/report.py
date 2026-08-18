"""Build a single self-contained interactive HTML report for the recording.

    uv run python scripts/make_report.py   # interactive launcher (preferred)
    uv run python -c "import sys; sys.path.insert(0,'scripts'); import report; report.build_report()"

Writes outputs/report.html — one offline file (Plotly JS inlined), laid out
verdict-first per DESIGN_UX §4: a stat-tile header answering "how many units,
are they any good", a sticky table of contents with per-section status glyphs,
then the evidence in reader order — 1 Verdict · 2 Sorted units · 3 Quality
metrics · 4 Array & yield · 5 Probe & channels · 6 Recording context (the raw
streams, demoted to input context) · 7 Provenance (status table + versions).
One chart theme and one unit colormap run through every figure, so a unit keeps
its colour across raster, templates and scatter. Read-only with respect to the
data; it only writes the HTML.

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
FOLD_ROWS = 8            # tables longer than this go behind a <details> fold

# "Passes quality" is a rule of thumb for orientation, not curation — the same
# SNR/ISI rule run_sorting reports at the end of a sort. W1 (curation) owns
# changing it; the tile always states the rule next to the count.
PASS_SNR = 5.0
PASS_ISI_RATIO = 0.5

# Expected post-bandpass + CMR noise floor for this rig: an OBSERVED regression
# band (3.88-4.02 across every saved sort), not a validated quality threshold.
# The tile therefore makes no pass/fail claim; only a value outside the band is
# flagged, because that usually means the µV gain was applied twice (~1 µV).
# Trigger band deliberately WIDER than the display text's observed range: the
# canary's job is ~4-vs-~1 discrimination (double-scaling) or gross CMR damage,
# not a ±0.1 µV gate — a healthy 3.88 re-run must not be accused (D3 review #1).
NOISE_BAND_UV = (3.5, 4.5)


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


def _recording_name(data_dir=None) -> "str | None":
    """The recording's base name (no extension), or None when no data is present."""
    try:
        return bio.find_blackrock_base(data_dir).name
    except Exception:  # noqa: BLE001 - no recording on this machine
        return None


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
# The one visual system (DESIGN_UX §4.4): chart theme + shared unit colormap
# --------------------------------------------------------------------------- #
_FONT = "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
ACCENT = "#2b6cb0"
DIM_MARK = "#98a2ad"

# One restrained categorical palette. Unit colours are assigned by position in
# the analyzer's unit_ids, so unit 7 is the same colour in the raster, the
# templates and the QC scatter.
UNIT_PALETTE = ("#2b6cb0", "#c2570c", "#2f855a", "#9b2c6f", "#0b7285",
                "#8a6d1f", "#5f4b8b", "#a02c2c", "#6b7280", "#7d4f16")

_AXIS = dict(gridcolor="#eef1f4", zerolinecolor="#dfe4ea", linecolor="#cfd6dd",
             ticks="outside", ticklen=4, tickcolor="#cfd6dd",
             title=dict(font=dict(size=12.5)))
_TEMPLATE = go.layout.Template(layout=dict(
    font=dict(family=_FONT, size=13, color="#1b1f24"),
    paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
    colorway=list(UNIT_PALETTE),
    title=dict(font=dict(size=15.5, color="#1b1f24"), x=0, xanchor="left", y=0.97),
    xaxis=_AXIS, yaxis=_AXIS,
    legend=dict(font=dict(size=12), bgcolor="rgba(255,255,255,0.75)"),
    hoverlabel=dict(font=dict(family=_FONT, size=12)),
    margin=dict(t=46, b=46, l=58, r=24),
))


def _style(fig, title=None, height=None, **layout):
    """Apply the one shared chart theme and return the figure."""
    fig.update_layout(template=_TEMPLATE, **layout)
    if title is not None:
        fig.update_layout(title=dict(text=title))
    if height is not None:
        fig.update_layout(height=height)
    return fig


def _unit_colors(unit_ids) -> dict:
    """{str(unit id): colour} — the shared unit colormap, keyed by id."""
    return {str(u): UNIT_PALETTE[i % len(UNIT_PALETTE)] for i, u in enumerate(unit_ids)}


# --------------------------------------------------------------------------- #
# HTML assembly helpers
# --------------------------------------------------------------------------- #
def _fig_html(fig) -> str:
    """One Plotly figure as an embeddable div (JS is included once in <head>)."""
    return fig.to_html(full_html=False, include_plotlyjs=False, default_width="100%")


def _figure(fig, alt) -> str:
    """A themed figure with alt text (§8: alt text on every figure)."""
    return (f'<figure class="fig" aria-label="{html.escape(alt)}">'
            f'{_fig_html(fig)}<figcaption class="sr-only">{html.escape(alt)}</figcaption></figure>')


def _num(value, spec=".3g", unit="") -> str:
    """Format one numeric cell; None/NaN become an honest en-dash, never "nan"."""
    if value is None:
        return "–"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if v != v:  # NaN
        return "–"
    return f"{v:{spec}}{unit}"


def _table(headers, rows, sortable=True, cls="tbl") -> str:
    """A styled table. headers = [(label, numeric?)]; rows = [[cell html, ...]].

    Numeric columns are right-aligned and sort numerically; "–" gap cells sink
    to the bottom either way (see sortTable).
    """
    ths = []
    for j, (label, numeric) in enumerate(headers):
        cls_attr = ' class="num"' if numeric else ""
        onclick = (f' onclick="sortTable(this.closest(\'table\'),{j},{"true" if numeric else "false"})"'
                   if sortable else "")
        ths.append(f'<th{cls_attr}{onclick}>{label}</th>')
    body = "".join(
        "<tr>" + "".join(
            ('<td class="num">' if headers[j][1] else "<td>") + f"{cell}</td>"
            for j, cell in enumerate(row)
        ) + "</tr>"
        for row in rows
    )
    if not sortable:
        cls += " static"        # headers that don't sort must not look clickable
    return (f'<div class="tbl-wrap"><table class="{cls}"><thead><tr>{"".join(ths)}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def _fold(summary_line, body, open_when=False) -> str:
    """Long tables live behind a fold whose summary line states what is inside."""
    attr = " open" if open_when else ""
    return f'<details{attr}><summary>{summary_line}</summary>{body}</details>'


def _tile(label, value, note="", state="") -> str:
    """One verdict stat tile. state: "" (neutral) or "warn" (amber, §1.5)."""
    cls = f"tile {state}".strip()
    note_html = f'<p class="rule">{note}</p>' if note else ""
    return (f'<div class="{cls}"><p class="label">{html.escape(label)}</p>'
            f'<p class="value">{value}</p>{note_html}</div>')


def _safe_section(sec_id, title, render, *args, state="ok") -> dict:
    """Render one section; a failure becomes a visible red box, not a crash."""
    try:
        body = render(*args)
    except Exception as e:  # noqa: BLE001
        body = f'<div class="err">Section failed to render: {html.escape(repr(e))}</div>'
        state = "warn"
    return {"id": sec_id, "title": title, "html": body, "state": state}


_CSS = """
:root { --fg:#1b1f24; --muted:#5b6470; --line:#e3e7eb; --bg:#fff; --panel:#f7f9fb;
        --accent:#2b6cb0; --amber:#8a5a00; --amber-bg:#fff8e6; --amber-line:#f0dca8;
        --red:#8c2d24; --red-bg:#fdeceb; --red-line:#f3c9c5; --green:#1f6f3d; --radius:10px; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       color: var(--fg); margin: 0; background: var(--bg); line-height: 1.6; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden;
           clip:rect(0,0,0,0); white-space:nowrap; border:0; }
a { color: var(--accent); }
a:focus-visible, summary:focus-visible, th:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* --- table of contents: top bar by default, left rail from 1100px --------- */
.page { max-width: 1440px; margin: 0 auto; }
nav { position: sticky; top: 0; z-index: 20; background: var(--bg);
      border-bottom: 1px solid var(--line); padding: 8px 24px; }
nav .toc-title { display: none; }
nav ol.toc { list-style: none; display: flex; flex-wrap: wrap; gap: 2px 14px; margin: 0; padding: 0; }
nav ol.toc a { display: inline-flex; align-items: baseline; gap: 6px; text-decoration: none;
               font-size: 13.5px; padding: 3px 2px; border-radius: 4px; }
nav ol.toc a:hover { text-decoration: underline; }
nav .n { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 12px; }
nav .glyph { font-size: 12px; }
nav .glyph.ok, nav .glyph.skip { color: var(--muted); }
nav .glyph.skip { opacity: 0.75; }
nav .glyph.warn { color: var(--amber); }
nav .toc-legend { color: var(--muted); font-size: 12px; margin: 4px 0 0; }
main { max-width: 1100px; margin: 0 auto; padding: 8px 24px 80px; }
section { scroll-margin-top: 96px; }
@media (min-width: 1100px) {
  .page { display: grid; grid-template-columns: 244px minmax(0, 1fr); gap: 40px; padding: 0 28px; }
  nav { border-bottom: none; border-right: 1px solid var(--line); height: 100vh; overflow: auto;
        align-self: start; padding: 32px 20px 32px 0; }
  nav .toc-title { display: block; font-size: 11.5px; letter-spacing: .09em; text-transform: uppercase;
                   color: var(--muted); margin: 0 0 10px; }
  nav ol.toc { display: block; }
  nav ol.toc li { margin: 1px 0; }
  nav ol.toc a { display: flex; width: 100%; }
  nav ol.toc .label { flex: 1; }
  nav .toc-legend { margin-top: 14px; }
  main { margin: 0; padding: 8px 0 96px; }
  section { scroll-margin-top: 28px; }
}

/* --- rhythm ---------------------------------------------------------------- */
h1 { font-size: 30px; letter-spacing: -0.01em; margin: 32px 0 4px; }
h2 { font-size: 21px; margin: 56px 0 10px; padding-bottom: 8px; border-bottom: 1px solid var(--line);
     display: flex; align-items: baseline; gap: 10px; }
h2 .n { color: var(--muted); font-size: 14px; font-weight: 500; font-variant-numeric: tabular-nums; }
h3 { font-size: 16px; margin: 32px 0 6px; }
.sub { color: var(--muted); margin: 0 0 8px; }
.subsec { margin: 0 0 8px; }
.note { color: var(--muted); font-size: 13.5px; margin: 10px 0; }
.skip { color: var(--muted); font-style: italic; }
.fig { margin: 18px 0 26px; }
.page-foot { color: var(--muted); font-size: 12.5px; margin: 56px 0 0;
             border-top: 1px solid var(--line); padding-top: 14px; }

/* --- verdict tiles --------------------------------------------------------- */
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(212px, 1fr)); gap: 16px; margin: 20px 0 10px; }
.tile { border: 1px solid var(--line); border-radius: var(--radius); padding: 16px 18px; background: var(--panel); }
.tile .label { font-size: 11.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin: 0; }
.tile .value { font-size: 29px; font-weight: 600; line-height: 1.2; margin: 6px 0 4px;
               font-variant-numeric: tabular-nums; }
.tile .value .u { font-size: 15px; font-weight: 500; color: var(--muted); }
.tile .rule { font-size: 12.5px; color: var(--muted); margin: 0; }
.tile.warn { background: var(--amber-bg); border-color: var(--amber-line); }
.tile.warn .rule { color: var(--amber); }

/* --- tables ---------------------------------------------------------------- */
.tbl-wrap { max-height: 520px; overflow: auto; border: 1px solid var(--line); border-radius: var(--radius); }
table { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 13.5px; }
th, td { text-align: left; padding: 7px 12px; border-bottom: 1px solid var(--line); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
th { position: sticky; top: 0; z-index: 1; background: var(--panel); cursor: pointer; user-select: none;
     font-weight: 600; white-space: nowrap; border-bottom: 1px solid var(--line); }
table.static th { cursor: default; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover { background: #fafbfc; }
details { margin: 14px 0 22px; }
summary { cursor: pointer; color: var(--fg); font-size: 13.5px; padding: 8px 12px;
          background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); }
details[open] summary { border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
details[open] .tbl-wrap { border-top: none; border-top-left-radius: 0; border-top-right-radius: 0; }

/* --- status + honesty artifacts -------------------------------------------- */
.badge { font-weight: 600; padding: 1px 8px; border-radius: 10px; font-size: 12px; color: #fff; }
.PASS { background: #2a8a3e; } .FAIL { background: #c0392b; } .SKIP { background: #7d858e; }
.err { background: var(--red-bg); border: 1px solid var(--red-line); color: var(--red);
       padding: 10px 14px; border-radius: var(--radius); }
.caveat { background: var(--amber-bg); border: 1px solid var(--amber-line); padding: 11px 15px;
          border-radius: var(--radius); font-size: 13.5px; margin: 14px 0; }
.caveat ul { margin: 8px 0 0; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px;
       background: var(--panel); padding: 1px 5px; border-radius: 4px; }
"""

_SORT_JS = """
function sortTable(table, col, numeric) {
  var tbody = table.tBodies[0];
  var rows = Array.prototype.slice.call(tbody.rows);
  var asc = !(table.getAttribute('data-col') == col && table.getAttribute('data-dir') == 'asc');
  rows.sort(function(a, b) {
    var x = a.cells[col].innerText, y = b.cells[col].innerText;
    if (numeric) {
      x = parseFloat(x); y = parseFloat(y);
      // "–" gap cells parse to NaN; pin them to the bottom in either direction
      // (a NaN comparator is inconsistent and would interleave rows arbitrarily).
      if (isNaN(x)) x = asc ? Infinity : -Infinity;
      if (isNaN(y)) y = asc ? Infinity : -Infinity;
    }
    return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1);
  });
  rows.forEach(function(r) { tbody.appendChild(r); });
  table.setAttribute('data-col', col);
  table.setAttribute('data-dir', asc ? 'asc' : 'desc');
}
"""

# TOC status glyphs: shape first, with a text neighbour in the legend (§8).
_TOC_STATE = {"ok": ("✓", "present"), "skip": ("○", "absent"),
              "warn": ("!", "needs attention")}


def _html_document(title, sections, heading=None, subtitle=None) -> str:
    """Wrap rendered sections in the shell: sticky TOC + single content column.

    ``sections`` are {id, title, html, state?} dicts; ``state`` drives the TOC
    glyph ("ok" when absent). Shared with compare.py's comparison.html.
    """
    items, body = [], []
    for i, s in enumerate(sections, 1):
        state = s.get("state", "ok")
        glyph, word = _TOC_STATE.get(state, _TOC_STATE["ok"])
        items.append(f'<li><a href="#{s["id"]}"><span class="n">{i}</span>'
                     f'<span class="label">{html.escape(s["title"])}</span>'
                     f'<span class="glyph {state}" title="{word}">{glyph}</span></a></li>')
        body.append(f'<section id="{s["id"]}"><h2><span class="n">{i}</span>'
                    f'{html.escape(s["title"])}</h2>{s["html"]}</section>')
    nav = ('<p class="toc-title">Contents</p>'
           f'<ol class="toc">{"".join(items)}</ol>'
           '<p class="toc-legend">✓ present · ○ absent · ! needs attention</p>')
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    subtitle = subtitle or "Self-contained — works offline."
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
<script>{get_plotlyjs()}</script>
<script>{_SORT_JS}</script>
</head><body>
<div class="page">
<nav>{nav}</nav>
<main>
<h1>{html.escape(heading or title)}</h1>
<p class="sub">{subtitle}</p>
{''.join(body)}
<p class="page-foot">Generated {generated} — self-contained, works offline.</p>
</main>
</div>
</body></html>"""


# --------------------------------------------------------------------------- #
# Section renderers (each returns inner HTML; wrapped by _safe_section)
# --------------------------------------------------------------------------- #
def _pass_quality(analyzer) -> "tuple[int | None, int]":
    """(n units passing the SNR/ISI rule of thumb, n units). n_pass is None when
    the metrics needed for the rule are absent."""
    n_units = len(analyzer.unit_ids)
    try:
        qm = analyzer.get_extension("quality_metrics").get_data()
        good = (qm["snr"] >= PASS_SNR) & (qm["isi_violations_ratio"] <= PASS_ISI_RATIO)
        return int(good.sum()), len(qm)
    except Exception:  # noqa: BLE001 - metric columns vary; degrade to "unknown"
        return None, n_units


def _render_verdict(analyzer, analyzer_dir, info, sorter_label, status, data_dir=None) -> str:
    """The answer first: four stat tiles (DESIGN_UX §4.1).

    When no raw data loaded at all (fresh clone / wrong folder) this is also the
    one home for the getting-started guidance — the reader meets it before the
    wall of FileNotFoundError reprs in the provenance table.
    """
    data_stages = [r for r in status if r["stage"] in ("LFP (.ns2)", "Broadband (.ns5)",
                                                       ".nev online units")]
    lead = (_getting_started_html(data_dir)
            if data_stages and all(r["status"] != "PASS" for r in data_stages) else "")
    if analyzer is None:
        return (lead + '<p class="skip">No saved sort for '
                f'{html.escape(str(sorter_label))} — run one from the launcher '
                '(<code>uv run python SpikeInterface_Menu.py sort</code>), then rebuild '
                'this report.</p>')

    summary = sort_summary.load_summary(Path(analyzer_dir).parent) if analyzer_dir else None
    n_units = len(analyzer.unit_ids)
    tiles = []

    # 1 — units.
    tiles.append(_tile(
        "units", f"{n_units}",
        note=("no units at this detect threshold — lower detect_threshold in Edit parameters "
              "and re-run" if n_units == 0 else ""),
        state="warn" if n_units == 0 else ""))

    # 2 — pass-quality count (a rule of thumb, stated on the tile).
    n_pass, n_scored = _pass_quality(analyzer)
    rule = f"SNR ≥ {PASS_SNR:g} · ISI violations ≤ {PASS_ISI_RATIO:g} — a rule of thumb, not curation"
    if n_pass is None:
        tiles.append(_tile("pass quality", "–", note="SNR / ISI metrics were not computed for this sort"))
    else:
        tiles.append(_tile("pass quality", f'{n_pass}<span class="u"> of {n_scored}</span>', note=rule))

    # 3 — noise floor: the number and its expected band, never a pass/fail claim.
    in_uV = bool((summary or {}).get("units_in_uV", True))
    noise = ((summary or {}).get("noise_floor_uV") or {}).get("median")
    lo, hi = NOISE_BAND_UV
    if noise is None:
        zero = not ((summary or {}).get("n_units") or 0)
        tiles.append(_tile("noise floor", "–",
                           note=("not computed for a 0-unit sort" if summary and zero
                                 else "no saved summary for this sort")))
    elif not in_uV:
        tiles.append(_tile("noise floor", f'{noise:.3g}<span class="u"> a.u.</span>',
                           note="no µV gain on this recording — amplitudes are raw a.u."))
    else:
        outside = not (lo <= float(noise) <= hi)
        band = f"expected ≈{lo:g}–{hi:g} µV for this rig, post-bandpass + CMR"
        tiles.append(_tile(
            "noise floor", f'{noise:.3g}<span class="u"> µV</span>',
            note=(f"outside the {band} — a value near 1 µV means the µV gain was applied "
                  "twice; check the sort's scaling before trusting any amplitude here"
                  if outside else band),
            state="warn" if outside else ""))

    # 4 — window sorted, with the partial-sort caveat inline.
    eff, tot = info.get("effective_seconds"), info.get("total_seconds")
    if not isinstance(eff, (int, float)):
        eff = analyzer.get_total_duration()
    partial = isinstance(tot, (int, float)) and isinstance(eff, (int, float)) and eff < tot - 1.0
    if partial:
        note = (f"of the {tot:.0f} s recording ({eff / tot * 100:.0f}%) — unit counts are not "
                "comparable across windows; re-run without --duration for the full sort")
    elif isinstance(tot, (int, float)):
        note = f"the full {tot:.0f} s recording"
    else:
        note = "the analyzer's own duration"
    tiles.append(_tile("window sorted", f'{eff:.0f}<span class="u"> s</span>',
                       note=note, state="warn" if partial else ""))

    return lead + '<div class="tiles">' + "".join(tiles) + "</div>"


def _spike_figs(unit_ids, train_seconds, title_prefix, total_duration=None, colors=None):
    """Build (raster_fig, rate_fig) from a {unit_id: spike_times_seconds} provider.

    Firing rates use total_duration (the recording length) when given, so they
    match the quality-metrics table; otherwise they fall back to the last spike
    time across units. ``colors`` is the shared unit colormap (§4.4).
    """
    trains = {u: np.asarray(train_seconds(u), dtype=float) for u in unit_ids}
    duration = total_duration if total_duration else max(
        (tr[-1] for tr in trains.values() if tr.size), default=1.0)
    duration = duration or 1.0
    colors = colors or _unit_colors(unit_ids)
    pal = [colors.get(str(u), UNIT_PALETTE[i % len(UNIT_PALETTE)]) for i, u in enumerate(unit_ids)]

    raster = go.Figure()
    for row, u in enumerate(unit_ids):
        tr = trains[u]
        raster.add_trace(go.Scatter(x=tr, y=np.full(tr.shape, row), mode="markers",
                                    marker=dict(symbol="line-ns-open", size=6, color=pal[row]),
                                    name=f"unit {int(u)}"))
    raster.update_yaxes(tickvals=list(range(len(unit_ids))),
                        ticktext=[str(int(u)) for u in unit_ids], title="unit id")
    _style(raster, title=f"{title_prefix} — spike raster ({len(unit_ids)} units · {duration:.0f} s)",
           height=max(320, 22 * len(unit_ids) + 80), xaxis_title="time (s)", showlegend=False)

    rates = [trains[u].size / duration for u in unit_ids]
    rate = go.Figure(go.Bar(x=[str(int(u)) for u in unit_ids], y=rates, marker_color=pal))
    _style(rate, title=f"{title_prefix} — mean firing rate ({len(unit_ids)} units)",
           height=360, xaxis_title="unit id", yaxis_title="rate (Hz)")
    return raster, rate


def _render_sorted(analyzer, sorter_label, info=None, probe=None) -> str:
    if analyzer is None:
        return ('<p class="skip">No saved analyzer found — run a sort first: '
                '<code>uv run python scripts/run_sorting.py</code>.</p>')
    sorting = analyzer.sorting
    fs = analyzer.sampling_frequency
    unit_ids = list(analyzer.unit_ids)
    dur = analyzer.get_total_duration()
    colors = _unit_colors(unit_ids)

    raster, rate = _spike_figs(unit_ids, lambda u: sorting.get_unit_spike_train(u) / fs,
                               f"Sorted ({sorter_label})", total_duration=dur, colors=colors)

    # Waveform templates: each unit on its peak-to-peak best channel.
    tex = analyzer.get_extension("templates")
    templates = tex.get_data()            # (n_units, n_samples, n_channels)
    nbefore = tex.nbefore
    chan_ids = list(analyzer.channel_ids)
    n_samples = templates.shape[1]
    tms = (np.arange(n_samples) - nbefore) / fs * 1000.0
    # The analyzer already returns µV when the recording carries gains — label it
    # as such, never re-apply the gain (CLAUDE.md: the double-scaling trap).
    amp_unit = ("µV" if bool(getattr(analyzer, "return_in_uV",
                                     getattr(analyzer, "return_scaled", True))) else "a.u.")
    wf = go.Figure()
    for i, u in enumerate(unit_ids):
        best = int(np.argmax(np.ptp(templates[i], axis=0)))   # numpy 2.x: ndarray.ptp() removed
        wf.add_trace(go.Scatter(x=tms, y=templates[i][:, best], mode="lines",
                                line=dict(color=colors[str(u)]),
                                name=f"unit {int(u)} (ch {chan_ids[best]})"))
    _style(wf, title=f"Waveform template per unit, best channel ({len(unit_ids)} units)",
           height=440, xaxis_title="time relative to spike (ms)",
           yaxis_title=f"amplitude ({amp_unit})")

    # Partial-sort caveat: a --duration smoke test sorts a window far shorter than
    # the full recording the context section covers. Flag it loudly so a reader
    # never conflates a 20 s sort with the 132 s recording.
    info = info or {}
    eff, tot = info.get("effective_seconds"), info.get("total_seconds")
    partial = isinstance(eff, (int, float)) and isinstance(tot, (int, float)) and eff < tot - 1.0
    partial_html = (
        f'<div class="caveat"><strong>Partial sort:</strong> only the first {eff:.0f}s of the '
        f'{tot:.0f}s recording were sorted (e.g. a quick <code>--duration</code> test). The '
        f'recording-context section covers the full recording — unit counts are not comparable '
        f'across different windows.</div>' if partial else "")
    probe_html = _probe_caveat(probe, info.get("n_dropped_analog") or 0)
    return (f'<p class="note">Sorted with {html.escape(str(sorter_label))} over {dur:.1f}s of data, '
            f'{len(unit_ids)} units. Every figure shares one unit colour. Toggle units via the legend.</p>'
            + partial_html + probe_html
            + _figure(raster, f"Spike raster: {len(unit_ids)} sorted units over {dur:.0f} seconds, "
                              "one row of spike ticks per unit.")
            + _figure(rate, f"Bar chart of mean firing rate in Hz for each of the {len(unit_ids)} sorted units.")
            + _figure(wf, f"Waveform template of each of the {len(unit_ids)} units on its best channel, "
                          f"amplitude in {amp_unit} against time in milliseconds around the spike."))


# Quality-metric columns: header label (units where they exist) + fixed format.
_QC_COLS = {
    "firing_rate": ("firing rate (Hz)", ".2f"),
    "snr": ("SNR", ".2f"),
    "presence_ratio": ("presence ratio", ".2f"),
    "amplitude_median": ("amplitude median (µV)", ".1f"),
    "amplitude_cutoff": ("amplitude cutoff", ".3f"),
    "isolation_distance": ("isolation distance", ".3g"),
    "l_ratio": ("L-ratio", ".3f"),
    "d_prime": ("d-prime", ".2f"),
    "nn_hit_rate": ("NN hit rate", ".3f"),
    "nn_miss_rate": ("NN miss rate", ".3f"),
    "isi_violations_ratio": ("ISI violations ratio", ".3f"),
    "isi_violations_count": ("ISI violations (n)", ".0f"),
}


def _render_qc(analyzer) -> str:
    if analyzer is None:
        return '<p class="skip">No saved analyzer — quality metrics unavailable.</p>'
    try:
        qm = analyzer.get_extension("quality_metrics").get_data()  # DataFrame, index = unit ids
    except Exception:  # noqa: BLE001 - metrics are non-fatal, so a sort can lack them
        return ('<p class="skip">This sort has no saved quality metrics — they are computed '
                'after the units are saved, and are skipped when that step fails.</p>')
    # Render whatever the analyzer computed (old saved sorts carry fewer columns):
    # a preferred reading order first, then any remaining columns appended as-is.
    cols = [c for c in _QC_COLS if c in qm.columns]
    cols += [c for c in qm.columns if c not in cols]
    qm = qm.sort_values("snr", ascending=False) if "snr" in qm.columns else qm
    colors = _unit_colors(analyzer.unit_ids)

    headers = [("unit", True)] + [(html.escape(_QC_COLS.get(c, (c, ".3g"))[0]), True) for c in cols]
    rows = [[f"{int(uid)}"] + [_num(r[c], _QC_COLS.get(c, (c, ".3g"))[1]) for c in cols]
            for uid, r in qm.iterrows()]
    n_pass, _ = _pass_quality(analyzer)
    pass_line = ("" if n_pass is None else
                 f' — {n_pass} pass the SNR ≥ {PASS_SNR:g} · ISI ≤ {PASS_ISI_RATIO:g} rule of thumb')
    fold_summary = (f'Per-unit quality metrics — {len(qm)} units × {len(cols)} metrics{pass_line}. '
                    'Click a column header to sort; "–" = not computable for that unit.')
    table = _fold(fold_summary, _table(headers, rows), open_when=len(qm) <= FOLD_ROWS)
    if "isolation_distance" in qm.columns:
        table += ('<p class="note">PCA isolation metrics are unreliable for units with '
                  'very few spikes — an astronomically large isolation distance with a '
                  'blank L-ratio means a degenerate fit, not superb isolation.</p>')

    scatter = ""
    if {"firing_rate", "snr"} <= set(qm.columns):
        size = None
        if "isi_violations_ratio" in qm.columns:
            viol = qm["isi_violations_ratio"].to_numpy(dtype=float)
            size = 8 + 18 * (viol / viol.max()) if viol.max() > 0 else None
        fig = go.Figure(go.Scatter(
            x=qm["firing_rate"], y=qm["snr"], mode="markers+text",
            text=[str(int(u)) for u in qm.index], textposition="top center",
            textfont=dict(size=11, color="#5b6470"),
            marker=dict(size=size if size is not None else 12,
                        color=[colors.get(str(u), ACCENT) for u in qm.index],
                        line=dict(width=0)),
            hovertemplate="unit %{text}<br>rate %{x:.2f} Hz<br>SNR %{y:.2f}<extra></extra>"))
        _style(fig, title=f"SNR vs firing rate ({len(qm)} units · marker size = ISI-violation ratio)",
               height=420, xaxis_title="firing rate (Hz)", yaxis_title="SNR")
        scatter = _figure(fig, f"Scatter plot of SNR against firing rate for {len(qm)} units; "
                               "each point is labelled with its unit id and sized by ISI-violation ratio.")
    return scatter + table


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
    head_table = _table([("metric", False), ("value", True)],
                        [[html.escape(k), html.escape(str(v))] for k, v in row.items()],
                        sortable=False)

    # Per-unit V_pp / SNR table (the per-unit basis of the V_pp & SNR headlines).
    per_unit = summary.get("per_unit", [])
    pu_rows = [[f"{p['unit']}", _num(p.get("v_pp_uV"), ".1f"), _num(p.get("snr"), ".2f"),
                html.escape(str(p.get("best_channel", "")))] for p in per_unit]
    pu_table = _fold(
        f"Per-unit amplitude &amp; SNR — {len(pu_rows)} units, peak-to-peak on the best channel. "
        "Click a column header to sort.",
        _table([("unit", True), (f"V_pp ({amp})", True), ("SNR", True), ("best ch", False)], pu_rows),
        open_when=len(pu_rows) <= FOLD_ROWS)

    # Per-channel noise floor, active channels highlighted.
    noise = (summary.get("noise_floor_uV") or {}).get("per_channel") or []
    active = set(summary.get("active_channels", []))
    chan_ids = [str(c) for c in (analyzer.channel_ids if analyzer is not None else range(len(noise)))]
    noise_html = ""
    if noise and len(noise) == len(chan_ids):
        colours = [ACCENT if c in active else DIM_MARK for c in chan_ids]
        fig = go.Figure(go.Bar(x=chan_ids, y=[0 if v is None else v for v in noise],
                               marker_color=colours))
        _style(fig, title=(f"Noise floor per channel ({amp}) — "
                           f"{len(active)} of {len(chan_ids)} electrodes active (darker)"),
               height=360, xaxis_title="channel", yaxis_title=f"noise floor ({amp})")
        noise_html = _figure(fig, f"Bar chart of noise floor in {amp} for each of the {len(chan_ids)} "
                                  "channels; active electrodes are drawn in the accent colour.")

    note = ('<p class="note">Amplitudes are in µV via the recording gain. '
            'Noise floor is measured on the band-passed + common-median-referenced '
            'signal the sort uses (so it is a post-CMR figure, consistent with SNR). '
            '"Active electrode" = the peak channel of ≥1 sorted unit.</p>'
            if summary.get("units_in_uV", True) else
            '<p class="note">No µV gain on this recording — amplitudes are raw a.u.</p>')
    return note + head_table + noise_html + pu_table


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
    marker = dict(size=18, line=dict(color="#1b1f24", width=1))
    if noise and len(noise) == len(chan_ids) and any(v is not None for v in noise):
        marker.update(color=[np.nan if v is None else v for v in noise], colorscale="Viridis",
                      colorbar=dict(title="noise (µV)"), showscale=True)
        hover = [f"ch {c}<br>({xi:.0f}, {yi:.0f}) µm<br>noise {('' if v is None else f'{v:.2f} µV')}"
                 for c, xi, yi, v in zip(chan_ids, x, y, noise)]
    else:
        marker.update(color=[ACCENT if c in active else DIM_MARK for c in chan_ids])
        hover = [f"ch {c}<br>({xi:.0f}, {yi:.0f}) µm" for c, xi, yi in zip(chan_ids, x, y)]
    fig.add_trace(go.Scatter(x=x, y=y, mode="markers+text", marker=marker,
                             text=chan_ids, textposition="middle right",
                             hovertext=hover, hoverinfo="text", name="sites"))
    if active:
        ax = [xi for c, xi in zip(chan_ids, x) if c in active]
        ay = [yi for c, yi in zip(chan_ids, y) if c in active]
        fig.add_trace(go.Scatter(x=ax, y=ay, mode="markers", name="active electrode",
                                 marker=dict(size=30, color="rgba(0,0,0,0)",
                                             line=dict(color=ACCENT, width=3))))
    _style(fig, title=f"Collection sites — {len(chan_ids)} contacts, electrode geometry",
           height=560, xaxis_title="x (µm)", yaxis_title="depth y (µm)",
           yaxis=dict(autorange="reversed"),
           xaxis=dict(range=[x.min() - max((x.max() - x.min()) * 0.6, 60),
                             x.max() + max((x.max() - x.min()) * 0.6, 120)]))
    n_active = sum(1 for c in chan_ids if c in active)
    note = (f'<p class="note">{len(chan_ids)} contacts'
            + (f'; {n_active} are active (peak channel of ≥1 unit, ringed). '
               'Marker colour = per-channel noise floor. ' if active else '. ')
            + 'For an interactive channel scroll use the menu’s "Scroll raw traces" '
            '(ephyviewer); <code>scripts/show_channels.py</code> writes probe_map.png + '
            'channels.png headless.</p>')
    return note + _figure(fig, f"Map of {len(chan_ids)} electrode contacts at their x and depth "
                               "positions in micrometres, coloured by per-channel noise floor, "
                               "with active electrodes ringed.")


def _render_lfp(lfp) -> str:
    if lfp is None:
        return '<p class="skip">LFP failed to load — see the provenance section.</p>'
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
    _style(traces_fig, title=f"LFP — first {LFP_WINDOW_S:g}s, {len(chan_ids)} channels @ {fs:g} Hz",
           height=460, xaxis_title="time (s)")

    # Power spectrum (Welch) over the same channels.
    psd_fig = go.Figure()
    for i, ch in enumerate(chan_ids):
        f, pxx = welch(traces[:, i], fs=fs, nperseg=min(1024, n))
        psd_fig.add_trace(go.Scatter(x=f, y=pxx, mode="lines", name=str(ch), line=dict(width=1)))
    _style(psd_fig, title=f"LFP power spectrum (Welch, {len(chan_ids)} channels)",
           height=380, xaxis_title="frequency (Hz)", yaxis_title="power", yaxis_type="log")

    return ('<p class="note">First few channels shown stacked; toggle channels via the legend.</p>'
            + _figure(traces_fig, f"Stacked LFP traces for the first {LFP_WINDOW_S:g} seconds on "
                                  f"{len(chan_ids)} channels.")
            + _figure(psd_fig, f"Log-power Welch spectrum against frequency for the same "
                               f"{len(chan_ids)} LFP channels."))


def _render_nev(nev) -> str:
    if nev is None:
        return '<p class="skip">.nev units failed to load — see the provenance section.</p>'
    fs = nev.get_sampling_frequency()
    unit_ids = list(nev.get_unit_ids())
    try:
        total = nev.get_total_duration()
    except Exception:  # noqa: BLE001 - a bare .nev Sorting may not know its duration
        total = None
    raster, rate = _spike_figs(unit_ids, lambda u: nev.get_unit_spike_train(u) / fs,
                               "Online (.nev)", total_duration=total)
    return ('<p class="note">Already-detected online units from the .nev — the rig\'s own '
            'threshold crossings, not this sort. Blackrock convention: unit 0 = unsorted '
            'threshold crossings, 1..n = sorted, 255 = noise.</p>'
            + _figure(raster, f"Spike raster of the {len(unit_ids)} online .nev units, one row per unit.")
            + _figure(rate, f"Bar chart of mean firing rate in Hz for the {len(unit_ids)} online .nev units."))


def _render_events(events) -> str:
    if events is None:
        return '<p class="skip">Events could not be read (best-effort) — see the provenance section.</p>'
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
    _style(fig, title=f"Event markers over time ({len(nonempty)} channels with markers)",
           height=max(280, 40 * len(nonempty) + 120), xaxis_title="time (s)", showlegend=False)
    note = (f'<p class="note">Empty channels: {html.escape(", ".join(empty_names))}.</p>'
            if empty_names else "")
    return _figure(fig, f"Event markers over time on {len(nonempty)} event channels, "
                        "one row of ticks per channel.") + note


def _render_context(lfp, nev, events) -> str:
    """LFP + online .nev units + event markers: the recording as recorded.

    Demoted below the sort (§4.3) — it is input context, not results. Each
    sub-block degrades to its own honest note, never a crashed section.
    """
    out = ['<p class="note">The raw streams as recorded, covering the <em>full</em> recording — '
           'input context for the sort above, not results of it.</p>']
    for sub_id, title, render, obj in (
            ("lfp", "LFP (.ns2 @ 1 kHz)", _render_lfp, lfp),
            ("nev", "Online units (.nev)", _render_nev, nev),
            ("events", "Event markers (.nev)", _render_events, events)):
        try:
            body = render(obj)
        except Exception as e:  # noqa: BLE001 - one broken stream must not take the section
            body = f'<div class="err">Failed to render: {html.escape(repr(e))}</div>'
        out.append(f'<div class="subsec" id="{sub_id}"><h3>{html.escape(title)}</h3>{body}</div>')
    return "".join(out)


def _render_provenance(status, probe=None, info=None) -> str:
    """One home for provenance (§4.3): the pipeline status table + versions +
    the probe/aux notes that used to sit in a separate About section."""
    import importlib

    rows = [[f'<span class="badge {r["status"]}">{r["status"]}</span>',
             html.escape(r["stage"]), html.escape(r["detail"])] for r in status]
    table = _table([("status", False), ("stage", False), ("detail", False)], rows, sortable=False)

    info = info or {}
    prov = []
    if info.get("created"):
        prov.append(f'sorted {html.escape(str(info["created"]).replace("T", " "))}')
    if info.get("sorter"):
        prov.append(f'sorter {html.escape(str(info["sorter"]))}')
    if isinstance(info.get("freq_min"), (int, float)) and isinstance(info.get("freq_max"), (int, float)):
        prov.append(f'bandpass {info["freq_min"]:g}–{info["freq_max"]:g} Hz, common median reference')
    if info.get("si_version"):
        prov.append(f'SpikeInterface {html.escape(str(info["si_version"]))} at sort time')
    prov_html = f'<p class="note">Run: {" · ".join(prov)}.</p>' if prov else ""

    versions = []
    for mod in ["spikeinterface", "neo", "plotly", "numpy", "scipy"]:
        try:
            versions.append(f"{mod} {importlib.import_module(mod).__version__}")
        except Exception:  # noqa: BLE001
            versions.append(f"{mod} (not importable)")

    return ('<p class="note">One row per pipeline stage — PASS means it loaded, '
            'SKIP means optional/absent, FAIL means broken.</p>'
            + table + prov_html
            + _probe_caveat(probe)
            + '<p class="note">The broadband stream mixes 16 neural channels (raw 1–16) '
              'with 6 analog aux channels (analog 1–6); the sort excludes the analog aux '
              'channels by default.</p>'
            + f'<p class="note">Report built with {html.escape(" · ".join(versions))}.</p>')


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
    analyzer = objects.get("analyzer")

    # TOC glyphs: what a reader will actually find in each section.
    sorted_state = "ok" if analyzer is not None else "skip"
    ctx_rows = [r for r in status if r["stage"] in ("LFP (.ns2)", ".nev online units",
                                                    "Events (.nev markers)")]
    ctx_state = ("warn" if any(r["status"] == "FAIL" for r in ctx_rows)
                 else "ok" if any(r["status"] == "PASS" for r in ctx_rows) else "skip")
    prov_state = "warn" if any(r["status"] == "FAIL" for r in status) else "ok"

    sections = [
        _safe_section("verdict", "Verdict", _render_verdict, analyzer, analyzer_dir, info,
                      sorter_label, status, data_dir, state=sorted_state),
        _safe_section("sorted", f"Sorted units ({sorter_label})", _render_sorted, analyzer,
                      sorter_label, info, probe, state=sorted_state),
        _safe_section("qc", "Quality metrics", _render_qc, analyzer, state=sorted_state),
        _safe_section("summary", "Array & yield", _render_summary, analyzer, analyzer_dir,
                      state=sorted_state),
        _safe_section("probe", "Probe & channels", _render_probe, analyzer, analyzer_dir,
                      state=sorted_state),
        _safe_section("context", "Recording context", _render_context, objects.get("lfp"),
                      objects.get("nev"), objects.get("events"), state=ctx_state),
        _safe_section("provenance", "Provenance", _render_provenance, status, probe, info,
                      state=prov_state),
    ]

    # The TOC glyph must describe what actually RENDERED (D3 review #2/#3): a
    # section whose body opens with an honest skip is ○ absent, and one carrying
    # an error box is ! needs-attention — never a ✓ over missing/broken content.
    for sec in sections:
        body = sec.get("html", "")
        if 'class="err"' in body:
            sec["state"] = "warn"
        elif sec.get("state") == "ok" and body.lstrip().startswith('<p class="skip">'):
            sec["state"] = "skip"

    rec = _recording_name(data_dir) or "Recording"
    sorted_at = str(info.get("created", "")).replace("T", " ")[:16]
    subtitle = " · ".join([html.escape(str(sorter_label))]
                          + ([f"sorted {html.escape(sorted_at)}"] if sorted_at else []))
    out_path.write_text(
        _html_document(f"{rec} — sort report", sections, heading=rec, subtitle=subtitle),
        encoding="utf-8")
    return out_path


if __name__ == "__main__":
    print(build_report())
