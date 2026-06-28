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


def test_action_explain_sort_shows_docker_block(monkeypatch, tmp_path):
    # Active sorter is a not-installed CONTAINERIZED sorter with Docker requested but
    # down: action_explain('sort') must surface the docker-block as an unmet need, so
    # #explain never reads 'ready' while Enter would immediately bounce (matches the
    # active_blocked_on_docker guard in _activate_action).
    import argparse
    import report
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(["tridesclous2", "mountainsort5"]))
    # Daemon was up when the sorter was picked (runnable() probes it with refresh=False),
    # then went down — active_blocked_on_docker re-probes with refresh=True. Model both:
    # available unless a fresh re-probe is requested.
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: not k.get("refresh", False))
    monkeypatch.setattr(report, "_gather", lambda *a, **k: ({}, []))
    monkeypatch.setattr(M, "_save_config", lambda cfg: None)
    monkeypatch.setattr(M, "_saved_summary", lambda name: (False, 0, 0.0))
    args = argparse.Namespace(data_dir=str(tmp_path), sorter="mountainsort5",
                              duration=None, docker=False, params_file=None, gui_mode="auto")
    c = M.MenuController(args, {"use_docker": True})
    assert c.active_sorter == "mountainsort5"            # runnable via the Docker fallback
    needs = {n["label"]: n["ok"] for n in c.action_explain("sort")["needs"]}
    docker_label = next(k for k in needs if "docker" in k.lower())
    assert needs[docker_label] is False                 # Docker required but not running


def test_action_explain_sort_no_docker_need_for_native(monkeypatch, tmp_path):
    # An installed/native active sorter must NOT show a docker need at all.
    c = _ctrl_with_two_sorters(monkeypatch, tmp_path)   # tridesclous2 active, installed
    labels = [n["label"].lower() for n in c.action_explain("sort")["needs"]]
    assert not any("docker" in l for l in labels)


def test_action_explain_non_sort_action_never_probes_docker(monkeypatch, tmp_path):
    # Regression guard for the per-keystroke latency fix: action_explain() resolvers
    # are LAZY, so a non-sort action ('explore') must NOT evaluate the sort_docker
    # check (which reaches Docker/installed()). After the controller is built, make
    # any Docker probe explode; if action_explain still returns, laziness held. Docker
    # is ON (use_docker gates the uses_docker()/sort_docker path that WOULD probe).
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "mountainsort5"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: True)   # benign at build
    monkeypatch.setattr(M, "_saved_summary", lambda name: (False, 0, 0.0))
    c = _controller(monkeypatch, tmp_path, use_docker=True)   # tridesclous2 active

    # Now arm the trap: the sort_docker resolver is the only one reaching Docker, and
    # it routes through active_blocked_on_docker(). Make THAT explode. If the lazy
    # resolver table is ever made eager again, building the resolvers dict for ANY
    # action evaluates sort_docker -> active_blocked_on_docker() -> boom. With the
    # lazy thunks, a non-sort action never calls it, so these keys must stay quiet.
    def _boom(*a, **k):
        raise AssertionError("non-sort action_explain must not probe Docker")

    monkeypatch.setattr(c, "active_blocked_on_docker", _boom)
    monkeypatch.setattr(reg, "docker_available", _boom)
    monkeypatch.setattr(reg, "docker_state", _boom)
    for key in ("explore", "report", "verify", "gui", "compare"):
        ex = c.action_explain(key)                  # must not raise -> resolver was lazy
        labels = [n["label"].lower() for n in ex["needs"]]
        assert not any("docker" in l for l in labels)


def test_installed_is_process_cached(monkeypatch):
    # Regression guard: sorters.installed() must memoise the ~1 s SpikeInterface
    # installed_sorters() probe so per-keystroke menu code can call it freely. Patch
    # the underlying spikeinterface probe with a call-counter and assert it runs at
    # most once across many installed() calls (then re-probes only on refresh=True).
    import spikeinterface.sorters as ss
    import sorters as reg

    calls = {"n": 0}

    def _counting(*a, **k):
        calls["n"] += 1
        return ["tridesclous2", "spykingcircus2"]

    monkeypatch.setattr(ss, "installed_sorters", _counting)
    # Start from a cold cache (an earlier test may have warmed it) and restore it
    # afterward so this test neither sees nor leaks per-process cache state.
    saved = dict(reg._installed_cache)
    reg._installed_cache.clear()
    try:
        first = reg.installed()
        for _ in range(50):
            assert reg.installed() == first
        assert calls["n"] == 1                       # probed once, then served from cache
        # An explicit refresh re-probes (the documented escape hatch).
        reg.installed(refresh=True)
        assert calls["n"] == 2
    finally:
        reg._installed_cache.clear()
        reg._installed_cache.update(saved)           # don't leak cache state to other tests


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


def test_animate_defaults_on(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path)
    assert c.animate is True


def test_animate_reads_saved_off(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, cfg={"animate": False})
    assert c.animate is False


def test_set_animate_updates_attr_and_persists(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path)
    saved = {}
    monkeypatch.setattr(M, "_save_config", lambda cfg: saved.update(cfg))
    assert c.set_animate(False) is False
    assert c.animate is False
    assert c.cfg["animate"] is False
    assert saved.get("animate") is False


def test_clear_saved_sort_removes_outputs(monkeypatch, tmp_path):
    import SpikeInterface_Menu as M
    import blackrock_io as bio

    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)
    saved = tmp_path / "outputs" / "tridesclous2"
    saved.mkdir(parents=True)
    (saved / "run_info.json").write_text("{}")

    c = M.MenuController.__new__(M.MenuController)   # no __init__ I/O
    ok, msg = c.clear_saved_sort("tridesclous2")
    assert ok is True and not saved.exists()


def test_delete_image_resolves_and_calls_registry(monkeypatch):
    import SpikeInterface_Menu as M
    calls = {}
    monkeypatch.setattr(M.sorter_registry, "default_docker_image", lambda n: "img:latest")
    monkeypatch.setattr(M.sorter_registry, "delete_docker_image",
                        lambda img: (calls.update(img=img), (True, "ok"))[1])
    c = M.MenuController.__new__(M.MenuController)
    ok, msg = c.delete_image("mountainsort5")
    assert ok is True and calls["img"] == "img:latest"


def test_sort_command_builds_argv(monkeypatch, tmp_path):
    import SpikeInterface_Menu as M
    c = M.MenuController.__new__(M.MenuController)
    c.active_sorter = "tridesclous2"
    c.active_probe = "nnx-a1x16-3mm-100"
    c.use_docker = False
    c.args = type("A", (), {"data_dir": None})()
    c.get_overrides = lambda name: {}
    argv = c.sort_command(span="quick")
    assert "run_sorting.py" in " ".join(argv)
    assert "--progress" in argv and "json" in argv
    assert "--sorter" in argv and "tridesclous2" in argv
    assert "--duration" in argv  # quick → duration set


def test_active_probe_defaults_to_nnx_a1x16(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    assert c.active_probe == "nnx-a1x16-3mm-100"        # this recording's real probe
    assert c.active_probe_info()["name"] == "nnx-a1x16-3mm-100"


def test_active_probe_honours_saved_cfg(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={"active_probe": "independent"})
    assert c.active_probe == "independent"


def test_set_active_probe_persists(monkeypatch, tmp_path):
    saved = {}
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    monkeypatch.setattr(M, "_save_config", lambda cfg: saved.update(cfg))
    assert c.set_active_probe("linear-16-50um") is True
    assert c.active_probe == "linear-16-50um"
    assert saved.get("active_probe") == "linear-16-50um"


def test_sort_command_includes_probe(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    c.set_active_probe("linear-16-50um")
    argv = c.sort_command(None)
    assert "--probe" in argv and "linear-16-50um" in argv


def test_probe_catalog_marks_active_and_match(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    rows = c.probe_catalog()
    default = next(r for r in rows if r["name"] == "nnx-a1x16-3mm-100")
    assert default["active"] is True
    indep = next(r for r in rows if r["name"] == "independent")
    assert indep["auto"] is True and indep["active"] is False


def test_catalog_has_fit_and_reranks_for_dense_probe(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=True, cfg={})
    c.set_active_probe("independent")
    # independent -> tridesclous2 is the recommended (good) default
    td = next(i for i in c.infos if i["name"] == "tridesclous2")
    assert "fit" in td and td["fit"]["rank"] == "good"
    assert td["recommended"] is True
