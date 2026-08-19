"""Structural golden checks for the generated HTML report.

Builds a FRESH report with today's ``report.py`` into a pytest tmp dir (never
touching ``outputs/report.html``) and checks its structure - sections present
and in order, nav wired to every section, figures/tables non-empty where the
saved data says they must be, no crashed sections, fully self-contained.
Deliberately not pixel-perfect: the D-track redesign may restyle everything,
but this structural contract must survive it.

Skips cleanly when no saved sort exists (fresh clone / CI without data): the
report's sorted-unit content comes only from a saved SortingAnalyzer.

Re-baselining: if a redesign legitimately renames/reorders/adds sections,
update ``REQUIRED_SECTION_ORDER`` (and only it) in the same commit - see
``tests/README.md``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "scripts")

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"

# The section ids the report must carry, in this relative order. Additions
# between/around them are fine; removals and reorders are a conscious
# re-baseline (edit this list in the redesign commit).
# Re-baselined for the D3 report redesign (DESIGN_UX §4.3): verdict first,
# evidence in reader order, the raw streams demoted into one "recording context"
# section, provenance merged into one home at the end.
# Re-baselined again 2026-08-19 (GOAL_PRESENT item 6, the content audit): "evidence"
# is a new section holding the ISI and amplitude histograms the verdict's merge
# advisory cites in words. It sits directly after the verdict because it is that
# claim's proof, and the advisory's callout links down into it.
REQUIRED_SECTION_ORDER = [
    "verdict", "evidence", "sorted", "qc", "summary", "probe", "context", "provenance",
]

# Attributes after the id are redesign-legal; the id staying first is not
# load-bearing beyond keeping this parse simple.
_SECTION_RE = re.compile(r'<section id="([^"]+)"[^>]*>.*?</section>', re.S)

# Sub-blocks inside a section (the LFP / .nev / events blocks of "context"),
# which carry their own anchors and their own honest-skip degradation.
_SUB_RE = re.compile(r'<div class="subsec" id="([^"]+)"[^>]*>(.*?)(?=<div class="subsec" id="|</section>)', re.S)


@pytest.fixture(scope="module")
def built_report(tmp_path_factory):
    """(html, analyzer_dir, data_present) for a fresh report, or a module skip."""
    import blackrock_io as bio
    import report
    import runs

    # Ask the run store, not the old outputs/<sorter>/analyzer shape: since W2 a
    # sort lands in outputs/<sorter>/runs/<run_id>/, so a literal glob would skip
    # this whole module on a machine that HAS saved sorts.
    if not runs.saved_sorters(outputs=OUTPUTS):
        pytest.skip("no saved sort in outputs/ - run a sort first")

    try:
        bio.find_blackrock_base()
        data_present = True
    except FileNotFoundError:
        data_present = False
    analyzer_dir = report._pick_default_analyzer()
    out = tmp_path_factory.mktemp("report") / "report.html"
    written = report.build_report(analyzer_dir=analyzer_dir, out_path=out)
    return written.read_text(encoding="utf-8"), Path(analyzer_dir), data_present


def _sections(html: str) -> dict[str, str]:
    """Ordered {section id: full section html}; asserts the parse found some."""
    secs = {m.group(1): m.group(0) for m in _SECTION_RE.finditer(html)}
    assert secs, "no <section id=...> blocks parsed - markup shape changed?"
    return secs


def test_required_sections_present_in_order(built_report):
    html, _, _ = built_report
    found = list(_sections(html))
    missing = [s for s in REQUIRED_SECTION_ORDER if s not in found]
    assert not missing, f"report lost sections: {missing}"
    positions = [found.index(s) for s in REQUIRED_SECTION_ORDER]
    assert positions == sorted(positions), (
        f"required sections out of order: found {found}"
    )


def test_nav_links_every_section(built_report):
    html, _, _ = built_report
    nav = re.search(r"<nav>(.*?)</nav>", html, re.S)
    assert nav, "report has no <nav>"
    for sec_id in _sections(html):
        assert f'href="#{sec_id}"' in nav.group(1), f"nav missing link to #{sec_id}"


def test_no_section_crashed(built_report):
    # _safe_section turns a renderer exception into a visible red box instead
    # of a crash - good for the reader, but any such box in a freshly built
    # report is a regression the suite must surface.
    html, _, _ = built_report
    # Both the section-level and sub-block-level crash boxes are defects
    # (D3 review #3: the sub-block string is "Failed to render").
    assert "failed to render" not in html.lower()


def test_no_section_is_empty(built_report):
    html, _, _ = built_report
    for sec_id, sec_html in _sections(html).items():
        body = re.sub(r"<h2>.*?</h2>", "", sec_html, flags=re.S)
        body = re.sub(r"<[^>]+>", "", body).strip()
        assert body, f"section #{sec_id} has an empty body (not even an honest note)"


def test_report_is_self_contained(built_report):
    # The report must open offline: Plotly JS inlined, no external fetches.
    html, _, _ = built_report
    assert "plotly" in html.lower()
    assert not re.search(r"<script[^>]+\bsrc\s*=", html), "external <script src>"
    assert not re.search(r'<link[^>]+rel="stylesheet"', html), "external stylesheet"


def test_has_rendered_figures(built_report):
    # At least one real Plotly figure (LFP window / raster / probe map). Zero
    # figures with a saved analyzer present means rendering silently died.
    html, _, _ = built_report
    assert html.count("plotly-graph-div") >= 1


def test_sorted_section_shows_units(built_report):
    # The analyzer exists (fixture guarantee), so the sorted section must show
    # real unit content - an "unavailable" fallback here means the report
    # could not load a sort that is actually on disk.
    html, _, _ = built_report
    sorted_html = _sections(html)["sorted"]
    assert "unavailable" not in sorted_html.lower()
    assert "plotly-graph-div" in sorted_html or "<table" in sorted_html


def test_data_sections_render_when_data_present(built_report):
    # With the recording on disk, a silently broken loader must NOT stay green:
    # _safe_section would turn a loader failure into an honest note (non-empty,
    # no crash box), which the generic checks above accept. So when the data
    # exists, require the loaders to have actually delivered: no FAIL badge in
    # the provenance table, and real figures in the LFP and .nev sub-blocks of
    # the recording-context section.
    html, _, data_present = built_report
    if not data_present:
        pytest.skip("no raw recording on this machine")
    secs = _sections(html)
    assert 'class="badge FAIL"' not in secs["provenance"]
    subs = dict(_SUB_RE.findall(secs["context"]))
    assert "plotly-graph-div" in subs["lfp"]
    assert "plotly-graph-div" in subs["nev"]


def test_verdict_tiles_lead_the_report(built_report):
    # The answer a researcher opens the report for (DESIGN_UX §4.1): four stat
    # tiles, with the noise-floor tile stating its expected band and making no
    # pass/fail claim.
    html, _, _ = built_report
    verdict = _sections(html)["verdict"]
    assert verdict.count('<p class="label">') == 4
    for label in ("units", "pass quality", "noise floor", "window sorted"):
        assert f">{label}</p>" in verdict, f"verdict tile missing: {label}"
    assert "expected" in verdict and "post-bandpass" in verdict


def test_no_raw_nan_cells(built_report):
    # Non-computable metrics render as an en-dash; a raw "nan" in a table cell
    # is the honesty artifact leaking through a new formatter.
    html, _, _ = built_report
    assert not re.search(r">\s*nan\s*<", html, re.I)


def test_figures_have_alt_text(built_report):
    # §8: every figure carries alt text.
    html, _, _ = built_report
    assert html.count("plotly-graph-div") <= html.count('<figcaption class="sr-only">')


def test_summary_metrics_when_saved(built_report):
    # If the picked sort saved its array/yield summary, the six-metric card
    # must render (spot-checked by its most distinctive label + a table).
    html, analyzer_dir, _ = built_report
    if not (analyzer_dir.parent / "summary.json").exists():
        pytest.skip("picked sort has no summary.json (metrics were skipped)")
    summary_html = _sections(html)["summary"]
    assert "yield (% active electrodes)" in summary_html
    assert "<table" in summary_html


def _advised_units(verdict_html: str) -> list[str]:
    """Unit ids the verdict block carries a merge advisory against."""
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", verdict_html, re.S):
        if 'class="advice"' not in row:
            continue
        cell = re.search(r"<code>([^<]+)</code>", row)
        if cell:
            out.append(cell.group(1))
    return out


def test_evidence_section_shows_what_the_advisory_cites(built_report):
    # The audit's whole point (GOAL_PRESENT item 6): the report told the reader a
    # unit "fires at impossible intervals" without ever drawing the intervals. If
    # the advisory fires, its evidence must be on the page, per advised unit.
    html, _, _ = built_report
    secs = _sections(html)
    advised = _advised_units(secs["verdict"])
    if not advised:
        pytest.skip("no unit meets the advisory criteria on the picked sort")
    ev = secs["evidence"]
    assert "plotly-graph-div" in ev, "the advisory fired but drew no evidence"
    assert "refractory" in ev.lower()
    for unit in advised:
        assert f"unit {unit} ·" in ev, f"advised unit {unit} has no evidence panel"


@pytest.fixture(scope="module")
def advised_evidence():
    """(evidence html, advised unit ids) for a saved sort whose advisory fires.

    ``built_report`` reports whichever sort is most complete, and that one need
    not have a merge in it - which would leave the check above skipping quietly on
    the machine that has the merges. This finds a sort the advisory actually fires
    on and renders the evidence for THAT one.
    """
    import report
    import runs

    import spikeinterface.full as si

    for sorter in runs.saved_sorters(outputs=OUTPUTS):
        raw = report.analyzer_dir_for(sorter)
        if not raw.is_dir():
            continue
        shown = report._curation_facts(raw)["dir"]
        try:
            analyzer = si.load_sorting_analyzer(shown)
        except Exception:                                  # noqa: BLE001
            continue
        roll = report._rollup_for(analyzer, shown)
        rollup = roll.get("rollup")
        if not rollup or not rollup["n_split_candidates"]:
            continue
        return (report._render_evidence(analyzer, roll),
                [str(u["unit"]) for u in rollup["units"] if u["split_advice"]])
    pytest.skip("no saved sort has a unit the merge advisory fires on")


def test_every_advised_unit_gets_its_isi_and_amplitude_panel(advised_evidence):
    ev, advised = advised_evidence
    assert ev.count("plotly-graph-div") == 3        # both gates + ISI + amplitude
    assert "refractory" in ev.lower()
    assert "isi_violations_count" in ev             # SI's own count, not a recount
    for unit in advised:
        # Once in the ISI grid, once in the amplitude grid.
        assert ev.count(f"unit {unit} \\u00b7") >= 2, f"unit {unit} is missing a panel"


def test_the_advisory_links_to_its_evidence(built_report):
    html, _, _ = built_report
    verdict = _sections(html)["verdict"]
    if 'class="advice"' not in verdict:
        pytest.skip("no unit meets the advisory criteria on the picked sort")
    assert 'href="#evidence"' in verdict


def test_qc_table_when_metrics_computed(built_report):
    # If the analyzer carries computed quality metrics, the QC section must
    # render them as a non-empty table.
    html, analyzer_dir, _ = built_report
    if not (analyzer_dir / "extensions" / "quality_metrics").is_dir():
        pytest.skip("picked analyzer has no quality_metrics extension")
    qc_html = _sections(html)["qc"]
    assert "<table" in qc_html and "<td" in qc_html
