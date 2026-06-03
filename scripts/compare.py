"""Build a standalone interactive comparison of the two sorters.

    conda activate si_env
    python scripts/compare.py            # builds outputs/comparison.html

Compares the saved tridesclous2 and spykingcircus2 sorts with SpikeInterface's
compare_two_sorters: an agreement-score heatmap + a matched/unmatched unit table.

IMPORTANT: the comparison is only meaningful if both sorts cover the SAME
recording window. Sorts are read from outputs/<sorter>/analyzer (the single
source of truth, same as report.py). If the two durations differ, the page shows
a clear caveat instead of a misleading matrix; re-sort both over a common window
first (the SpikeInterface_Menu.py 'compare' action offers to do this).
"""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import report  # noqa: E402  (reuse the HTML scaffolding helpers)

OUTPUT_DIR = bio.REPO_ROOT / "outputs"
DEFAULT_SORTERS = ("tridesclous2", "spykingcircus2")
DELTA_TIME_MS = 0.4   # coincidence window for a "match"
MATCH_SCORE = 0.5     # min agreement to call two units matched
# Two sorts whose durations differ by more than this (seconds) are treated as
# non-commensurate: comparing them would just measure the window mismatch.
DURATION_TOLERANCE_S = 1.0


def _load(sorter: str):
    """Return (sorting, duration_s) from outputs/<sorter>/analyzer, or (None, None)."""
    import spikeinterface.full as si

    analyzer_dir = OUTPUT_DIR / sorter / "analyzer"
    if not analyzer_dir.exists():
        return None, None
    a = si.load_sorting_analyzer(analyzer_dir)
    return a.sorting, float(a.get_total_duration())


def _heatmap(cmp) -> go.Figure:
    ag = cmp.get_ordered_agreement_scores()
    fig = go.Figure(go.Heatmap(
        z=ag.to_numpy(), x=[str(c) for c in ag.columns], y=[str(r) for r in ag.index],
        colorscale="Blues", zmin=0, zmax=1, colorbar=dict(title="agreement")))
    fig.update_layout(title="Agreement scores (Hungarian-ordered)",
                      xaxis_title=f"{cmp.sorting2_name} unit",
                      yaxis_title=f"{cmp.sorting1_name} unit",
                      height=480, margin=dict(t=40, b=40))
    return fig


def _match_table(cmp) -> str:
    # Hungarian optimal 1:1 assignment. The unmatched sentinel varies by
    # SpikeInterface version / dtype: it can be "" (empty string, the case in
    # 0.104.3) or -1, and matched partner ids may be ints or numeric strings.
    # int()-parsing handles every encoding: "" / None / NaN -> unmatched (int()
    # raises), -1 -> unmatched.
    hm = cmp.hungarian_match_12  # sorter1 unit id -> partner unit id

    def _partner(v):
        try:
            iv = int(v)
        except (TypeError, ValueError):
            return None
        return None if iv == -1 else iv

    rows = ""
    n_matched = 0
    for u1, u2 in hm.items():
        p = _partner(u2)
        if p is None:
            partner, frac = "—", 0.0
        else:
            partner, frac = str(p), cmp.get_agreement_fraction(u1, u2)
            n_matched += 1
        rows += f"<tr><td>{int(u1)}</td><td>{partner}</td><td>{frac:.3g}</td></tr>"
    n_unmatched = len(hm) - n_matched
    summary = (f'<p class="note">{n_matched} matched · {n_unmatched} unmatched '
               f'{cmp.sorting1_name} units · delta_time={DELTA_TIME_MS} ms · '
               f'match_score={MATCH_SCORE}. Click a header to sort.</p>')
    return (summary + '<table class="qc"><thead><tr>'
            f'<th onclick="sortTable(this.closest(\'table\'),0,true)">{cmp.sorting1_name} unit</th>'
            f'<th onclick="sortTable(this.closest(\'table\'),1,false)">{cmp.sorting2_name} match</th>'
            f'<th onclick="sortTable(this.closest(\'table\'),2,true)">agreement</th>'
            f'</tr></thead><tbody>' + rows + '</tbody></table>')


def build_comparison(data_dir=None, sorters=DEFAULT_SORTERS, out_path=None) -> Path:
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "comparison.html")
    OUTPUT_DIR.mkdir(exist_ok=True)
    s1_name, s2_name = sorters

    s1, d1 = _load(s1_name)
    s2, d2 = _load(s2_name)

    if s1 is None or s2 is None:
        missing = [n for n, s in [(s1_name, s1), (s2_name, s2)] if s is None]
        body = ('<div class="caveat">Cannot compare — no saved sort for: '
                f'{", ".join(missing)}. Run a sort for each sorter first.</div>')
    elif abs(d1 - d2) > DURATION_TOLERANCE_S:
        body = ('<div class="caveat">The two sorts cover different windows '
                f'({s1_name}: {d1:.1f}s, {s2_name}: {d2:.1f}s), so an agreement '
                'matrix would just measure the window mismatch, not genuine sorter '
                'disagreement. Re-sort both over the same window first.</div>')
    else:
        import spikeinterface.comparison as sc

        cmp = sc.compare_two_sorters(s1, s2, sorting1_name=s1_name, sorting2_name=s2_name,
                                     delta_time=DELTA_TIME_MS, match_score=MATCH_SCORE)
        body = (f'<p class="note">Both sorts cover {d1:.1f}s.</p>'
                + report._fig_html(_heatmap(cmp)) + _match_table(cmp))

    section = {"id": "compare", "title": f"{s1_name} vs {s2_name}", "html": body}
    out_path.write_text(report._html_document("Sorter comparison", [section]), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    print(build_comparison())
