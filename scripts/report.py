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
