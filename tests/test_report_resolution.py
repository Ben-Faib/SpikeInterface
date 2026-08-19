"""B1 regression - a bare ``report`` (no --sorter) must resolve a sorter and
never crash joining a None into the analyzer path.

Unit tests pin the resolution precedence (explicit > persisted-with-saved-sort >
recommended-with-saved-sort > most-complete-saved-sort > honest error) over a
tmp outputs universe; one subprocess test pins the exact reported command
(``uv run python scripts/make_report.py``), skipped when no saved sort exists.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import SpikeInterface_Menu as sim  # noqa: E402


def _args(sorter=None, data_dir=None):
    return argparse.Namespace(sorter=sorter, data_dir=data_dir, probe=None)


@pytest.fixture
def universe(tmp_path, monkeypatch):
    """Redirect every saved-sort lookup to a tmp outputs tree + a mutable cfg."""
    cfg = {}
    monkeypatch.setattr(sim.bio, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sim.report, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(sim.report, "DEFAULT_ANALYZER_DIR",
                        tmp_path / "outputs" / "tridesclous2" / "analyzer")
    monkeypatch.setattr(sim, "_load_config", lambda: cfg)

    def save(*sorters):
        for s in sorters:
            (tmp_path / "outputs" / s / "analyzer").mkdir(parents=True, exist_ok=True)

    return cfg, save


def test_explicit_sorter_wins(universe):
    cfg, save = universe
    cfg["active_sorter"] = "lupin"
    save("lupin")
    assert sim._resolve_report_sorter(_args(sorter="simple")) == "simple"


def test_persisted_active_sorter_with_saved_sort(universe):
    cfg, save = universe
    cfg["active_sorter"] = "lupin"
    save("lupin", "tridesclous2")
    assert sim._resolve_report_sorter(_args()) == "lupin"


def test_persisted_without_saved_sort_falls_to_the_pick(universe):
    cfg, save = universe
    cfg["active_sorter"] = "spykingcircus2"        # persisted but nothing saved
    save("tridesclous2")
    assert sim._resolve_report_sorter(_args()) == "tridesclous2"


def test_no_intent_prefers_the_most_complete_sort(universe, tmp_path):
    # Deliberately NO recommended-default step: with no explicit or persisted
    # intent, a full-recording lupin sort must beat a tridesclous2 30 s smoke
    # (run_info.json's effective_seconds drives the report module's pick).
    import json

    cfg, save = universe
    save("tridesclous2", "lupin")
    for sorter, secs in (("tridesclous2", 30.0), ("lupin", 132.1)):
        (tmp_path / "outputs" / sorter / "run_info.json").write_text(
            json.dumps({"effective_seconds": secs}), encoding="utf-8")
    assert sim._resolve_report_sorter(_args()) == "lupin"


def test_falls_to_the_only_saved_sort(universe):
    cfg, save = universe
    save("lupin")                                  # nothing persisted, one sort saved
    assert sim._resolve_report_sorter(_args()) == "lupin"


def test_the_pick_names_the_sorter_not_the_run_id(universe, tmp_path):
    # Every other test here saves the pre-store layout, where the analyzer's
    # parent IS the sorter - so reading that path segment passed them all while
    # being wrong under the run store, which puts a RUN ID there. A bare report
    # on a store-only tree then built for a "sorter" named 20260819-... and every
    # section degraded to "No saved analyzer".
    import json

    run_id = sim.runs.new_run_id()
    run = tmp_path / "outputs" / "lupin" / "runs" / run_id
    (run / "analyzer").mkdir(parents=True)
    (run / "run_info.json").write_text(
        json.dumps({"sorter": "lupin", "run_id": run_id, "smoke": False,
                    "effective_seconds": 132.1}), encoding="utf-8")
    assert sim._resolve_report_sorter(_args()) == "lupin"


def test_nothing_saved_resolves_none(universe):
    assert sim._resolve_report_sorter(_args()) is None


def test_action_report_errors_honestly_when_nothing_saved(universe):
    # The B1 crash shape: bare report on a data-less/sort-less tree must return
    # False with a message, never raise TypeError.
    assert sim.action_report(_args()) is False


def test_action_report_builds_with_resolved_sorter(universe, tmp_path, monkeypatch):
    cfg, save = universe
    save("tridesclous2")
    calls = {}

    def fake_build(data_dir=None, analyzer_dir=None, out_path=None,
                   sorter_label=None, probe=None):
        calls.update(analyzer_dir=Path(analyzer_dir), sorter_label=sorter_label)
        return tmp_path / "outputs" / "report.html"

    monkeypatch.setattr(sim.report, "build_report", fake_build)
    monkeypatch.setattr(sim, "_open_in_browser", lambda uri: None)
    assert sim.action_report(_args()) is True
    assert calls["sorter_label"] == "tridesclous2"
    assert calls["analyzer_dir"] == tmp_path / "outputs" / "tridesclous2" / "analyzer"


def test_bare_make_report_invocation():
    # The exact reported crash command. stdin=DEVNULL pins the non-TTY path
    # even under `pytest -s`, so no browser ever opens. Rebuilding the real
    # outputs/report.html is the command's documented job (a conscious choice);
    # the mtime check proves a fresh build, not a stale-file pass. Skips on a
    # data-less clone.
    import runs   # the store knows where a sort lives; a raw glob no longer does

    if not runs.saved_sorters(outputs=ROOT / "outputs"):
        pytest.skip("no saved sort - the bare invocation would honestly error")
    out = ROOT / "outputs" / "report.html"
    before = out.stat().st_mtime if out.exists() else 0.0
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_report.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=300, cwd=ROOT)
    assert res.returncode == 0, res.stderr[-800:]
    assert "TypeError" not in res.stderr
    assert out.exists() and out.stat().st_mtime > before
