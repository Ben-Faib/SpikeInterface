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

    out = sorters.run("tridesclous2", "REC", "/tmp/out",
                      params={"detect_threshold": 6.0}, use_docker=True, verbose=False)
    assert out == "SORTING"
    assert calls["name"] == "tridesclous2"
    assert calls["kw"]["docker_image"] is True
    assert calls["kw"]["sorter_params"] == {"detect_threshold": 6.0}
    assert calls["kw"]["remove_existing_folder"] is True


def test_run_docker_requested_but_unavailable_raises(fake_params, monkeypatch):
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    with pytest.raises(RuntimeError):
        sorters.run("tridesclous2", "REC", "/tmp/out", use_docker=True)


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
