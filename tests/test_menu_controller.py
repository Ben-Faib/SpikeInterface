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


def test_geometry_caveat_conditional(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    assert M._geometry_note("independent").startswith("Placeholder")
    real = M._geometry_note("linear-16-50um")
    assert "Placeholder" not in real and "linear-16-50um" in real


def test_probe_match_uses_neural_count(monkeypatch, tmp_path):
    """recording_channels() must return the NEURAL count (16) not the total (22).

    The default nnx-a1x16 has 16 contacts: it should read 'fits' against a
    recording reported as '16 neural + 6 aux ch, ...', not 'mismatch'.
    A 32-contact probe against the same recording must still read 'mismatch'.
    """
    import SpikeInterface_Menu as M
    import report
    import argparse

    monkeypatch.setattr(report, "_gather", lambda *a, **k: ({}, [
        {"stage": "Broadband (.ns5)", "status": "PASS",
         "detail": "16 neural + 6 aux ch, 132.0s @ 30000 Hz"}]))
    monkeypatch.setattr(M, "_save_config", lambda cfg: None)
    args = argparse.Namespace(data_dir=str(tmp_path), sorter=None, duration=None,
                              docker=False, params_file=None, gui_mode="auto")
    c = M.MenuController(args, {"use_docker": False})

    assert c.recording_channels() == 16, (
        "expected neural count 16, got something else — "
        "recording_channels() is not parsing the neural count from the detail string")
    assert c.active_probe_info()["match"] == "fits", (
        "default nnx-a1x16 (16 contacts) should 'fit' 16 neural channels, not 'mismatch'")
    assert c._probe_match(M.probes.get("linear-32-25um"))[0] == "mismatch", (
        "linear-32-25um (32 contacts) must not fit 16 neural channels")


# --- D1: active-sorter persistence + the LAST RESULT record ---------------- #
def _mock_registry(monkeypatch):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "kilosort4"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)


def test_active_sorter_restored_from_cfg(monkeypatch, tmp_path):
    _mock_registry(monkeypatch)
    c = _controller(monkeypatch, tmp_path, cfg={"active_sorter": "spykingcircus2"})
    assert c.active_sorter == "spykingcircus2"
    # A persisted sorter that is no longer runnable falls back safely.
    c2 = _controller(monkeypatch, tmp_path, cfg={"active_sorter": "kilosort4"})
    assert c2.active_sorter in ("tridesclous2", "spykingcircus2")


def test_explicit_sorter_flag_beats_persisted(monkeypatch, tmp_path):
    _mock_registry(monkeypatch)
    import argparse
    import SpikeInterface_Menu as M
    import report
    monkeypatch.setattr(report, "_gather", lambda *a, **k: ({}, []))
    monkeypatch.setattr(M, "_save_config", lambda cfg: None)
    args = argparse.Namespace(data_dir=str(tmp_path), sorter="tridesclous2",
                              duration=None, docker=False, params_file=None,
                              gui_mode="auto")
    c = M.MenuController(args, {"active_sorter": "spykingcircus2"})
    assert c.active_sorter == "tridesclous2"


def test_set_active_persists_to_cfg(monkeypatch, tmp_path):
    _mock_registry(monkeypatch)
    saved = []
    import SpikeInterface_Menu as M
    c = _controller(monkeypatch, tmp_path)
    monkeypatch.setattr(M, "_save_config", lambda cfg: saved.append(dict(cfg)))
    assert c.set_active_by_name("spykingcircus2") is True
    assert saved and saved[-1]["active_sorter"] == "spykingcircus2"


def test_record_result_and_reopen_paths(monkeypatch, tmp_path):
    _mock_registry(monkeypatch)
    c = _controller(monkeypatch, tmp_path)
    # Resolve artifacts against a sandbox, not the real repo's outputs/.
    import blackrock_io as bio
    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)
    opened = []
    import SpikeInterface_Menu as M
    monkeypatch.setattr(M, "_open_in_browser", lambda uri: opened.append(uri))
    # A verify run leaves no page: nothing to reopen, said honestly.
    c.record_result("verify", True)
    assert c.last_result["key"] == "verify" and c.last_result["path"] is None
    ok, msg = c.reopen_last()
    assert ok is False and "no page" in msg
    # A report records its artifact path; a missing file is an honest miss…
    c.record_result("report", True)
    assert c.last_result["path"] == "outputs/report.html"
    assert c.last_result["when"]
    ok, msg = c.reopen_last()
    assert ok is False and "gone" in msg and not opened
    # …and an existing one reopens in the browser.
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "report.html").write_text("<title>x</title>")
    ok, msg = c.reopen_last()
    assert ok is True and len(opened) == 1
    # A sort records its output dir (no reopenable page).
    c.record_result("sort", True)
    assert c.last_result["path"].startswith("outputs/")
    ok, _msg = c.reopen_last()
    assert ok is False


# --- D4: bare-action resolution, geometry caveat, sort expectations --------- #
def test_action_sort_bare_resolves_sorter(monkeypatch, tmp_path):
    import SpikeInterface_Menu as M
    import argparse
    calls = []
    monkeypatch.setattr(M, "_shell", lambda script, *flags: calls.append(flags) or True)
    monkeypatch.setattr(M, "_load_config", lambda: {"active_sorter": "spykingcircus2"})
    args = argparse.Namespace(sorter=None, duration=None, docker=False,
                              params_file=None, data_dir=None, probe=None)
    assert M.action_sort(args) is True
    assert calls and calls[0][:2] == ("--sorter", "spykingcircus2")


def test_action_gui_bare_errors_honestly_when_nothing_saved(monkeypatch, tmp_path):
    import SpikeInterface_Menu as M
    import argparse
    monkeypatch.setattr(M, "_load_config", lambda: {})
    import report
    monkeypatch.setattr(report, "_pick_default_analyzer",
                        lambda: tmp_path / "nothing" / "analyzer")
    args = argparse.Namespace(sorter=None, data_dir=None, gui_mode="auto")
    assert M.action_gui(args) is False        # honest refusal, no TypeError


def test_gui_explain_carries_geometry_caveat_on_placeholder(monkeypatch, tmp_path):
    _mock_registry(monkeypatch)
    c = _controller(monkeypatch, tmp_path)
    c.active_probe = "independent"
    meta = c.action_explain("gui")
    assert "NOT physical" in (meta.get("caveat") or "")
    meta_t = c.action_explain("traces")
    assert "NOT physical" in (meta_t.get("caveat") or "")
    # A real probe carries no geometry caveat.
    c.active_probe = "nnx-a1x16-3mm-100"
    assert "NOT physical" not in (c.action_explain("traces").get("caveat") or "")


def test_sort_expectations_reads_provenance(monkeypatch, tmp_path):
    _mock_registry(monkeypatch)
    c = _controller(monkeypatch, tmp_path)
    import blackrock_io as bio
    import json as _json
    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)
    run_dir = tmp_path / "outputs" / c.active_sorter
    run_dir.mkdir(parents=True)
    (run_dir / "run_info.json").write_text(_json.dumps(
        {"effective_seconds": 30.0, "total_seconds": 132.0, "wall_seconds": 61.5}))
    exp = c.sort_expectations()
    assert exp == {"span": "quick", "eff_seconds": 30.0, "wall_seconds": 61.5}
    # An old run_info without wall_seconds degrades honestly.
    (run_dir / "run_info.json").write_text(_json.dumps(
        {"effective_seconds": 132.0, "total_seconds": 132.0}))
    exp = c.sort_expectations()
    assert exp["span"] == "full" and exp["wall_seconds"] is None


# --- D3b: the report progress plumbing -------------------------------------- #
def test_report_command_argv(monkeypatch, tmp_path):
    _mock_registry(monkeypatch)
    c = _controller(monkeypatch, tmp_path)
    import SpikeInterface_Menu as M
    # No saved analyzer for the active sorter -> --sorter is OMITTED so the
    # child's default pick serves (D3b review F2)…
    monkeypatch.setattr(M, "_analyzer_dir", lambda name: tmp_path / name / "analyzer")
    argv = c.report_command()
    assert argv[1].endswith("report.py")
    assert "--sorter" not in argv
    assert ("--probe" in argv and c.active_probe in argv)   # geometry truth (F1)
    assert "--progress" in argv and "json" in argv
    assert "--data-dir" in argv           # the controller was built with one
    # …and with a saved analyzer, the active sorter IS passed.
    (tmp_path / c.active_sorter / "analyzer").mkdir(parents=True)
    argv = c.report_command()
    assert "--sorter" in argv and c.active_sorter in argv


def test_report_cli_speaks_the_protocol(tmp_path):
    # The report's json mode emits protocol-pure stdout ending in done/error —
    # even on an empty data dir (honest-skip report, rc 0).
    import subprocess
    import sys as _sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import sort_progress as sp
    res = subprocess.run(
        [_sys.executable, str(ROOT / "scripts" / "report.py"),
         "--data-dir", str(tmp_path), "--out", str(tmp_path / "r.html"),
         "--progress", "json"],
        capture_output=True, encoding="utf-8", errors="replace", timeout=300)
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    events = [sp.parse_line(ln) for ln in lines]
    assert all(e is not None for e in events), f"non-protocol stdout: {lines}"
    types = [e["t"] for e in events]
    assert types[-1] in ("done", "error")
    assert "phase" in types and "phase_done" in types
    if types[-1] == "done":
        assert res.returncode == 0 and (tmp_path / "r.html").exists()


# --- W1 slice 4: the in-TUI triage seam (controller half) ------------------- #
TRIAGE_SORTER = "tridesclous2"
TRIAGE_RUN = {"created": "2026-08-19T09:00:00", "sorter": TRIAGE_SORTER,
              "n_units": 3, "si_version": "0.104.3", "probe": "nnx-a1x16-3mm-100",
              "effective_seconds": 30.0, "total_seconds": 132.0}


def _saved_sort(tmp_path, monkeypatch, run=None, metrics=True):
    """A saved sort on disk under a tmp repo root: run_info + summary + metrics."""
    import blackrock_io as bio
    import curation

    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)
    paths = curation.sort_paths(TRIAGE_SORTER)
    paths["out"].mkdir(parents=True, exist_ok=True)
    paths["run_info"].write_text(json.dumps(run or TRIAGE_RUN), encoding="utf-8")
    paths["out"].joinpath("summary.json").write_text(json.dumps({
        "sorter": TRIAGE_SORTER, "n_units": 3, "units_in_uV": True,
        "per_unit": [{"unit": 0, "v_pp_uV": 23.868, "snr": 5.041, "best_channel": "1"},
                     {"unit": 1, "v_pp_uV": 22.482, "snr": 5.215, "best_channel": "2"},
                     {"unit": 2, "v_pp_uV": 61.311, "snr": 4.517, "best_channel": "3"}],
    }), encoding="utf-8")
    if metrics:
        paths["out"].joinpath("quality_metrics.csv").write_text(
            ",firing_rate,snr,amplitude_cutoff\n"
            "0,0.2045,5.0409,\n1,0.4772,5.2151,0.031\n2,19.79,4.5170,0.004\n",
            encoding="utf-8")
    return paths


def _triage_controller(monkeypatch, tmp_path, **kw):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: [TRIAGE_SORTER])
    monkeypatch.setattr(reg, "available", lambda: [TRIAGE_SORTER])
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    paths = _saved_sort(tmp_path, monkeypatch, **kw)
    c = _controller(monkeypatch, tmp_path)
    assert c.active_sorter == TRIAGE_SORTER
    return c, paths


def test_triage_state_reads_the_evidence_off_disk(monkeypatch, tmp_path):
    """Per-unit evidence is READ (summary.json + quality_metrics.csv as written),
    never recomputed, and a NaN metric stays None so the surface can say "–"."""
    c, _paths = _triage_controller(monkeypatch, tmp_path)
    st = c.triage_state()
    assert st["sorter"] == TRIAGE_SORTER and st["empty"] == "" and st["blocked"] == ""
    assert st["total"] == 3 and st["reviewed"] == 0
    assert st["columns"] == ["firing_rate", "snr", "amplitude_cutoff"]
    first = st["units"][0]
    assert first["unit"] == 0 and first["peak_channel"] == "1"
    assert first["v_pp_uV"] == 23.868
    assert first["metrics"]["snr"] == 5.0409
    assert first["metrics"]["amplitude_cutoff"] is None      # blank on disk
    assert st["units"][1]["metrics"]["amplitude_cutoff"] == 0.031
    # No saved Sorting here -> an honest unknown, never an invented count.
    assert first["n_spikes"] is None
    # curation.state() is the one source for what is being shown.
    assert st["line"] == "raw sorter output — no curation applied"
    assert st["stale"] is False and st["stale_reason"] == ""
    assert f"--sorter {TRIAGE_SORTER}" in st["apply_hint"]


def test_triage_spike_counts_come_from_the_saved_sorting(monkeypatch, tmp_path):
    si = __import__("pytest").importorskip("spikeinterface.full")
    c, paths = _triage_controller(monkeypatch, tmp_path)
    sorting = si.NumpySorting.from_samples_and_labels(
        [[10, 20, 30, 40, 50, 60]], [[0, 0, 0, 1, 1, 2]], sampling_frequency=30000.0)
    sorting.save(folder=paths["sorting"])
    counts = {u["unit"]: u["n_spikes"] for u in c.triage_state()["units"]}
    assert counts == {0: 3, 1: 2, 2: 1}


def test_label_unit_writes_a_tui_verdict_that_survives_a_relaunch(monkeypatch, tmp_path):
    import curation

    c, paths = _triage_controller(monkeypatch, tmp_path)
    ok, msg = c.label_unit(1, "noise")
    assert ok and "noise" in msg
    assert c.label_unit(2, "good")[0]

    # It is the real record, with the decision's origin recorded as the TUI.
    record = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert curation.structural_errors(record) == []
    assert curation.label_of(record, 1) == "noise"
    assert curation.label_method_of(record, 1) == "tui"
    assert record["curates"]["run"]["created"] == TRIAGE_RUN["created"]

    # Relaunch: a fresh controller over the same repo reads the verdicts back.
    fresh, _paths = _triage_controller(monkeypatch, tmp_path)
    st = fresh.triage_state()
    assert st["reviewed"] == 2 and st["total"] == 3
    assert [u["label"] for u in st["units"]] == [None, "noise", "good"]
    assert st["units"][1]["label_method"] == "tui"


def test_triage_refuses_a_record_written_against_another_sort(monkeypatch, tmp_path):
    """Unit ids are not stable across re-sorts: a record for a different run is
    refused, its labels are NOT shown against these units, and nothing is written."""
    import curation

    c, paths = _triage_controller(monkeypatch, tmp_path)
    assert c.label_unit(1, "noise")[0]
    before = paths["record"].read_text(encoding="utf-8")
    # ...then the sort is re-run underneath it (18 units, a new timestamp).
    paths["run_info"].write_text(json.dumps(
        {**TRIAGE_RUN, "created": "2026-08-19T11:00:00", "n_units": 18}),
        encoding="utf-8")

    ok, msg = c.label_unit(2, "good")
    assert not ok
    assert "written against a different" in msg and "Next step:" in msg
    assert paths["record"].read_text(encoding="utf-8") == before   # nothing written

    st = c.triage_state()
    assert st["blocked"] == msg
    assert st["reviewed"] == 0
    assert all(u["label"] is None for u in st["units"])   # never on the wrong units
    assert curation.label_of(curation.load_record(TRIAGE_SORTER), 1) == "noise"


def test_triage_with_no_saved_sort_names_the_next_step(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: [TRIAGE_SORTER])
    monkeypatch.setattr(reg, "available", lambda: [TRIAGE_SORTER])
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    import blackrock_io as bio
    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)
    c = _controller(monkeypatch, tmp_path)
    st = c.triage_state()
    assert st["units"] == [] and st["total"] == 0
    assert "No saved" in st["empty"] and "sort" in st["empty"]
