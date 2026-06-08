"""Hermetic unit tests for scripts/sorters.py.

The registry's discovery functions import SpikeInterface lazily, so every test
here monkeypatches them — no SpikeInterface, no Docker, no sorting is invoked.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sorters  # noqa: E402


@pytest.fixture
def fake_env(monkeypatch):
    """Default fake: tridesclous2 + spykingcircus2 installed, Docker on."""
    monkeypatch.setattr(sorters, "installed", lambda: ["spykingcircus2", "tridesclous2"])
    monkeypatch.setattr(sorters, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "mountainsort5", "herdingspikes",
         "kilosort4", "combinato"]))
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    return monkeypatch


def test_status_local(fake_env):
    assert sorters.status("tridesclous2") == "local"


def test_status_docker(fake_env):
    # not installed, CPU container image, Docker up -> docker
    assert sorters.status("mountainsort5") == "docker"
    assert sorters.status("herdingspikes") == "docker"


def test_status_gpu(fake_env):
    # GPU-only sorters are flagged even when Docker is up
    assert sorters.status("kilosort4") == "gpu"


def test_status_unavailable_when_docker_off(fake_env, monkeypatch):
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    assert sorters.status("mountainsort5") == "unavailable"


def test_status_unavailable_unknown(fake_env):
    # not installed, no image, not GPU -> unavailable
    assert sorters.status("nonexistent_sorter") == "unavailable"


def test_runnable_local_only(fake_env):
    assert sorters.runnable(use_docker=False) == ["spykingcircus2", "tridesclous2"]


def test_runnable_with_docker_adds_containers(fake_env):
    r = sorters.runnable(use_docker=True)
    assert r[:2] == ["spykingcircus2", "tridesclous2"]      # installed first
    assert "mountainsort5" in r and "herdingspikes" in r    # container extras
    assert "kilosort4" not in r                              # GPU excluded
    assert len(r) == len(set(r))                             # no duplicates


def test_runnable_docker_off_is_local(fake_env, monkeypatch):
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    assert sorters.runnable(use_docker=True) == ["spykingcircus2", "tridesclous2"]


def test_default_sorter_prefers_tridesclous2(fake_env):
    assert sorters.default_sorter() == "tridesclous2"


def test_default_sorter_falls_back_to_first_installed(fake_env, monkeypatch):
    monkeypatch.setattr(sorters, "installed", lambda: ["spykingcircus2"])
    assert sorters.default_sorter() == "spykingcircus2"


@pytest.fixture
def fake_params(monkeypatch):
    monkeypatch.setattr(sorters, "default_params", lambda name: {
        "detect_threshold": 5.0,   # float
        "n_peaks": 5000,           # int
        "peak_sign": "neg",        # str
        "apply_preprocessing": True,  # bool
        "seed": None,              # None -> JSON
        "job_kwargs": {},          # dict -> JSON
    })


def test_coerce_float():
    assert sorters.coerce_param(5.0, "6.5") == 6.5


def test_coerce_int():
    assert sorters.coerce_param(5000, "1000") == 1000


def test_coerce_bool_truthy():
    assert sorters.coerce_param(True, "false") is False
    assert sorters.coerce_param(False, "yes") is True


def test_coerce_str_passthrough():
    assert sorters.coerce_param("neg", "pos") == "pos"


def test_coerce_none_as_json():
    assert sorters.coerce_param(None, "42") == 42
    assert sorters.coerce_param(None, "null") is None


def test_coerce_dict_as_json():
    assert sorters.coerce_param({}, '{"n_jobs": 4}') == {"n_jobs": 4}


def test_coerce_bad_int_raises():
    with pytest.raises(ValueError):
        sorters.coerce_param(5000, "notanint")


def test_coerce_bad_json_raises():
    with pytest.raises(ValueError):
        sorters.coerce_param({}, "{not json}")


def test_merge_params_applies_overrides(fake_params):
    merged = sorters.merge_params("tridesclous2", {"detect_threshold": 6.0})
    assert merged["detect_threshold"] == 6.0
    assert merged["peak_sign"] == "neg"  # untouched default preserved


def test_merge_params_unknown_key_raises(fake_params):
    with pytest.raises(ValueError) as e:
        sorters.merge_params("tridesclous2", {"not_a_param": 1})
    assert "not_a_param" in str(e.value)


def test_run_passes_docker_and_params(fake_params, monkeypatch):
    calls = {}

    class FakeSS:
        def run_sorter(self, name, recording, **kw):
            calls["name"] = name
            calls["kw"] = kw
            return "SORTING"

    import types
    fake_ss = FakeSS()
    # sorters.run does `import spikeinterface.sorters as ss`
    monkeypatch.setitem(sys.modules, "spikeinterface", types.SimpleNamespace(sorters=fake_ss))
    monkeypatch.setitem(sys.modules, "spikeinterface.sorters", fake_ss)
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    # Docker is a fallback for NOT-installed sorters, so the container path only
    # triggers when the sorter isn't installed locally.
    monkeypatch.setattr(sorters, "installed", lambda: [])
    # the Docker path dumps the recording to binary first; that needs a real
    # recording, so bypass it here to focus on parameter passing.
    monkeypatch.setattr(sorters, "_as_container_recording", lambda rec, folder: rec)

    out = sorters.run("mountainsort5", "REC", "/tmp/out",
                      params={"detect_threshold": 6.0}, use_docker=True, verbose=False)
    assert out == "SORTING"
    assert calls["name"] == "mountainsort5"
    assert calls["kw"]["docker_image"] is True
    # SpikeInterface takes sorter params as **kwargs, NOT a sorter_params= keyword.
    assert calls["kw"]["detect_threshold"] == 6.0
    assert "sorter_params" not in calls["kw"]
    assert calls["kw"]["remove_existing_folder"] is True


def test_run_installed_sorter_runs_native_even_with_docker_on(fake_params, monkeypatch):
    """An installed sorter runs natively even when Docker mode is on (Docker is a
    fallback only — there's no image for the local-only sorters)."""
    calls = {}

    class FakeSS:
        def run_sorter(self, name, recording, **kw):
            calls["recording"] = recording
            calls["kw"] = kw
            return "SORTING"

    import types
    fake_ss = FakeSS()
    monkeypatch.setitem(sys.modules, "spikeinterface", types.SimpleNamespace(sorters=fake_ss))
    monkeypatch.setitem(sys.modules, "spikeinterface.sorters", fake_ss)
    monkeypatch.setattr(sorters, "installed", lambda: ["tridesclous2"])
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)

    def _boom(rec, folder):
        raise AssertionError("an installed sorter must not be containerised")
    monkeypatch.setattr(sorters, "_as_container_recording", _boom)

    sorters.run("tridesclous2", "REC", "/tmp/out", use_docker=True)
    assert calls["recording"] == "REC"          # not the binary-dumped recording
    assert calls["kw"]["docker_image"] is False


def test_uses_docker_only_for_not_installed():
    inst = ["tridesclous2", "spykingcircus2"]
    assert sorters.uses_docker("tridesclous2", True, installed_set=inst) is False
    assert sorters.uses_docker("mountainsort5", True, installed_set=inst) is True
    assert sorters.uses_docker("mountainsort5", False, installed_set=inst) is False


def test_default_docker_image_uses_sorter_map():
    # Exact image+tag SpikeInterface would pull (names aren't always <sorter>-base).
    assert sorters.default_docker_image("mountainsort5") == "spikeinterface/mountainsort5-base:latest"
    assert sorters.default_docker_image("spykingcircus") == "spikeinterface/spyking-circus-base:latest"
    assert sorters.default_docker_image("definitely_not_a_sorter") is None


def test_run_local_passes_flat_params_and_no_binary_dump(fake_params, monkeypatch):
    """Non-docker run sends params as **kwargs and never touches the binary dump."""
    calls = {}

    class FakeSS:
        def run_sorter(self, name, recording, **kw):
            calls["recording"] = recording
            calls["kw"] = kw
            return "SORTING"

    import types
    fake_ss = FakeSS()
    monkeypatch.setitem(sys.modules, "spikeinterface", types.SimpleNamespace(sorters=fake_ss))
    monkeypatch.setitem(sys.modules, "spikeinterface.sorters", fake_ss)

    def _boom(rec, folder):
        raise AssertionError("binary dump must not run on a local (non-docker) sort")
    monkeypatch.setattr(sorters, "_as_container_recording", _boom)

    sorters.run("tridesclous2", "REC", "/tmp/out",
                params={"detect_threshold": 6.0}, use_docker=False)
    assert calls["recording"] == "REC"
    assert calls["kw"]["docker_image"] is False
    assert calls["kw"]["detect_threshold"] == 6.0
    assert "sorter_params" not in calls["kw"]


def test_run_param_named_like_run_sorter_kwarg_does_not_collide(fake_params, monkeypatch):
    """A sorter param sharing run_sorter's own name (e.g. herdingspikes 'verbose')
    must override our default, not raise 'multiple values for keyword argument'."""
    calls = {}

    class FakeSS:
        def run_sorter(self, name, recording, **kw):
            calls["kw"] = kw
            return "SORTING"

    import types
    fake_ss = FakeSS()
    monkeypatch.setitem(sys.modules, "spikeinterface", types.SimpleNamespace(sorters=fake_ss))
    monkeypatch.setitem(sys.modules, "spikeinterface.sorters", fake_ss)
    monkeypatch.setattr(sorters, "installed", lambda: ["herdingspikes"])
    monkeypatch.setattr(sorters, "default_params",
                        lambda n: {"verbose": True, "detect_threshold": 5.0})

    sorters.run("herdingspikes", "REC", "/tmp/out", params={"verbose": False}, use_docker=False)
    assert calls["kw"]["verbose"] is False          # the user's sorter-verbose wins
    assert calls["kw"]["docker_image"] is False
    assert calls["kw"]["folder"] == "/tmp/out"


def test_coerce_none_default_empty_means_none():
    # Empty field for a None-default param (e.g. tridesclous2 seed) -> None, not error.
    assert sorters.coerce_param(None, "") is None
    assert sorters.coerce_param(None, "   ") is None
    assert sorters.coerce_param(None, "42") == 42   # a real value still parses


def test_run_docker_requested_but_unavailable_raises(fake_params, monkeypatch):
    # Docker only matters for a NOT-installed sorter; with the daemon down that
    # must raise rather than silently fall through.
    monkeypatch.setattr(sorters, "installed", lambda: [])
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    with pytest.raises(RuntimeError):
        sorters.run("mountainsort5", "REC", "/tmp/out", use_docker=True)


def test_status_table_shape(fake_env, fake_params):
    rows = sorters.status_table()
    assert {r["name"] for r in rows} == set(sorters.available())
    by = {r["name"]: r for r in rows}
    assert by["tridesclous2"]["status"] == "local"
    assert by["kilosort4"]["status"] == "gpu"
    assert by["mountainsort5"]["status"] == "docker"
    assert all("n_params" in r for r in rows)


def test_recommended_is_the_preferred_default():
    # The badged ★ sorter must match what default_sorter() prefers.
    assert sorters.RECOMMENDED == "tridesclous2"


def test_description_known_and_fallback():
    assert "GPU" not in sorters.description("tridesclous2")  # local sorter, no GPU mention
    assert sorters.description("tridesclous2")               # non-empty
    # an unknown sorter gets the generic fallback, never a KeyError
    assert sorters.description("totally_made_up_sorter") == "A spike-sorting algorithm."


def test_group_of_membership_precedence(monkeypatch):
    inst = {"tridesclous2", "kilosort4"}   # note: kilosort4 installed -> READY, not GPU
    monkeypatch.setattr(sorters, "installed", lambda: sorted(inst))
    g = lambda n: sorters.group_of(n, installed_set=inst)
    assert g("tridesclous2") == "ready"      # installed
    assert g("kilosort4") == "ready"         # installed beats GPU membership (Windows+GPU target)
    assert g("kilosort3") == "gpu"           # GPU family, not installed
    assert g("mountainsort5") == "docker"    # containerized, not installed
    assert g("totally_made_up_sorter") == "unavailable"


def test_group_of_uses_live_installed_when_omitted(monkeypatch):
    monkeypatch.setattr(sorters, "installed", lambda: ["tridesclous2"])
    assert sorters.group_of("tridesclous2") == "ready"
    assert sorters.group_of("mountainsort5") == "docker"


import subprocess as _subprocess


class _Ret:
    def __init__(self, rc):
        self.returncode = rc


def test_docker_state_not_installed(monkeypatch):
    sorters._docker_cache.clear()
    monkeypatch.setattr(sorters.shutil, "which", lambda _n: None)
    assert sorters.docker_state(refresh=True) == "not_installed"
    assert sorters.docker_available(refresh=True) is False


def test_docker_state_installed_not_running(monkeypatch):
    sorters._docker_cache.clear()
    monkeypatch.setattr(sorters.shutil, "which", lambda _n: "/usr/bin/docker")
    monkeypatch.setattr(sorters.subprocess, "run", lambda *a, **k: _Ret(1))
    assert sorters.docker_state(refresh=True) == "installed_not_running"
    assert sorters.docker_available(refresh=True) is False


def test_docker_state_running(monkeypatch):
    sorters._docker_cache.clear()
    monkeypatch.setattr(sorters.shutil, "which", lambda _n: "/usr/bin/docker")
    monkeypatch.setattr(sorters.subprocess, "run", lambda *a, **k: _Ret(0))
    assert sorters.docker_state(refresh=True) == "running"
    assert sorters.docker_available(refresh=True) is True


def test_start_docker_never_raises(monkeypatch):
    called = {}

    def _popen(cmd, *a, **k):
        called["cmd"] = cmd
        class _P:  # noqa: D401 - dummy Popen
            pass
        return _P()

    monkeypatch.setattr(sorters.subprocess, "Popen", _popen)
    assert sorters.start_docker() is True
    assert called["cmd"]  # a launch command was issued

    def _boom(*a, **k):
        raise OSError("no such app")

    monkeypatch.setattr(sorters.subprocess, "Popen", _boom)
    assert sorters.start_docker() is False   # swallowed, returns False
