"""Tests for the launcher's pure helpers (no SpikeInterface / no controller I/O)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import SpikeInterface_Menu as M  # noqa: E402


def test_effective_params_overlays_defaults(monkeypatch):
    import sorters
    monkeypatch.setattr(sorters, "default_params",
                        lambda name: {"a": 1.0, "b": "x", "c": True})
    eff = M._effective_params("tdc", {"a": 2.0})
    assert eff == {"a": 2.0}  # only overrides are returned (diffs), not full defaults


def test_write_params_file_roundtrip(tmp_path):
    p = M._write_params_file({"detect_threshold": 6.0})
    try:
        assert json.loads(Path(p).read_text()) == {"detect_threshold": 6.0}
    finally:
        Path(p).unlink(missing_ok=True)


def test_write_params_file_empty_returns_none():
    assert M._write_params_file({}) is None


def _controller(monkeypatch, tmp_path, use_docker=False, cfg=None):
    import SpikeInterface_Menu as M
    import report
    monkeypatch.setattr(report, "_gather", lambda *a, **k: ({}, []))
    import argparse
    args = argparse.Namespace(data_dir=str(tmp_path), sorter=None, duration=None,
                              docker=False, params_file=None, gui_mode="auto")
    monkeypatch.setattr(M, "_save_config", lambda cfg: None)  # don't write real files
    return M.MenuController(args, dict(cfg or {}, use_docker=use_docker))


def test_catalog_covers_all_sorters_with_groups(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "mountainsort5", "kilosort4"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)
    by = {i["name"]: i for i in c.infos}
    assert set(by) == {"tridesclous2", "spykingcircus2", "mountainsort5", "kilosort4"}
    assert by["tridesclous2"]["group"] == "ready" and by["tridesclous2"]["runnable"] is True
    assert by["tridesclous2"]["recommended"] is True
    assert by["tridesclous2"]["description"]
    assert by["mountainsort5"]["group"] == "docker" and by["mountainsort5"]["runnable"] is False
    assert by["kilosort4"]["group"] == "gpu" and by["kilosort4"]["runnable"] is False


def test_set_active_by_name_guards_non_runnable(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "kilosort4"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)
    assert c.set_active_by_name("spykingcircus2") is True
    assert c.active_sorter == "spykingcircus2"
    assert c.set_active_by_name("kilosort4") is False   # not runnable -> no change
    assert c.active_sorter == "spykingcircus2"


def test_cycle_active_skips_non_runnable(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "kilosort4"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)
    start = c.active_sorter
    c.cycle_active()
    assert c.active_sorter != start and c.active_sorter in ("tridesclous2", "spykingcircus2")


def test_docker_status_text_per_state(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2"])
    monkeypatch.setattr(reg, "available", lambda: ["tridesclous2"])
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)
    monkeypatch.setattr(reg, "docker_state", lambda *a, **k: "running")
    s = c.docker_status(refresh=True)
    assert s["state"] == "running" and s["running"] is True and s["text"]
    monkeypatch.setattr(reg, "docker_state", lambda *a, **k: "not_installed")
    assert c.docker_status(refresh=True)["running"] is False


def _ctrl_with_two_sorters(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "mountainsort5"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    # Saved-sort detection reads the repo's outputs/<sorter>/ analyzers, which a
    # developer's machine may already have from prior runs; pin it to "nothing
    # saved" so "fresh tmp -> 0 saved sorts" holds regardless of local state.
    monkeypatch.setattr(M, "_saved_summary", lambda name: (False, 0, 0.0))
    return _controller(monkeypatch, tmp_path, use_docker=False)


def test_action_explain_explore_needs_data(monkeypatch, tmp_path):
    c = _ctrl_with_two_sorters(monkeypatch, tmp_path)
    ex = c.action_explain("explore")
    assert ex["what"]                                   # has a description
    needs = {n["label"]: n["ok"] for n in ex["needs"]}
    assert any("recording" in k.lower() or "data" in k.lower() for k in needs)


def test_action_explain_compare_needs_two_saved_sorts(monkeypatch, tmp_path):
    c = _ctrl_with_two_sorters(monkeypatch, tmp_path)   # fresh tmp -> 0 saved sorts
    ex = c.action_explain("compare")
    needs = {n["label"]: n["ok"] for n in ex["needs"]}
    assert any("two" in k.lower() or "second" in k.lower() for k in needs)
    assert all(v is False for v in needs.values())      # nothing saved yet


def test_action_explain_no_need_actions_have_empty_needs(monkeypatch, tmp_path):
    c = _ctrl_with_two_sorters(monkeypatch, tmp_path)
    for key in ("params", "verify", "theme", "help", "quit"):
        ex = c.action_explain(key)
        assert ex["needs"] == [] and not ex.get("output")


def test_welcome_shown_once_and_persisted(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2"])
    monkeypatch.setattr(reg, "available", lambda: ["tridesclous2"])
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)   # fresh cfg -> first run
    assert c.want_welcome is True
    c.mark_welcome_seen()
    assert c.want_welcome is False
    assert c.cfg.get("seen_welcome") is True
