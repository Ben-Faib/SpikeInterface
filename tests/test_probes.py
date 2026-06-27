"""Hermetic unit tests for scripts/probes.py (no probeinterface/numpy needed for
the pure data-model + feature paths; build/catalog tests live separately)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import probes  # noqa: E402


def test_builtins_default_is_nnx_a1x16():
    bs = probes.builtins()
    assert bs[0]["name"] == "nnx-a1x16-3mm-100"          # this recording's real probe
    assert probes.DEFAULT_PROBE == "nnx-a1x16-3mm-100"
    assert probes.get("nnx-a1x16-3mm-100")["params"] == {"n": 16, "pitch_um": 100.0}
    assert any(p["name"] == "independent" for p in bs)   # placeholder still available
    # every built-in is flagged builtin and has the required keys
    for p in bs:
        assert p["builtin"] is True
        assert set(p) >= {"name", "label", "kind", "params", "builtin", "note"}


def test_library_merges_builtins_and_user(tmp_path):
    store = tmp_path / "probes.json"
    mine = {"name": "mine-8", "label": "Mine 8", "kind": "linear",
            "params": {"n": 8, "pitch_um": 40.0}, "builtin": False, "note": ""}
    probes.save_profile(mine, path=store)
    lib = probes.library(path=store)
    names = [p["name"] for p in lib]
    assert "independent" in names and "mine-8" in names
    assert probes.get("mine-8", path=store)["params"]["n"] == 8


def test_save_profile_roundtrips_and_upserts(tmp_path):
    store = tmp_path / "probes.json"
    p = {"name": "x", "label": "X", "kind": "linear",
         "params": {"n": 4, "pitch_um": 50.0}, "builtin": False, "note": ""}
    probes.save_profile(p, path=store)
    p2 = dict(p, label="X2")
    probes.save_profile(p2, path=store)        # upsert, not duplicate
    users = probes.user_profiles(path=store)
    assert [u["name"] for u in users] == ["x"]
    assert users[0]["label"] == "X2"
    # the on-disk file is the documented shape
    assert json.loads(store.read_text())["profiles"][0]["name"] == "x"


def test_delete_profile_user_only(tmp_path):
    store = tmp_path / "probes.json"
    probes.save_profile({"name": "y", "label": "Y", "kind": "linear",
                         "params": {"n": 4, "pitch_um": 50.0}, "builtin": False,
                         "note": ""}, path=store)
    ok, _ = probes.delete_profile("y", path=store)
    assert ok and probes.get("y", path=store) is None
    # built-ins are never deletable
    ok2, msg = probes.delete_profile("independent", path=store)
    assert ok2 is False and "built-in" in msg.lower()


def test_geometry_features_classes():
    # independent default -> independent class (250 um column, no sharing)
    f = probes.geometry_features(probes.get("independent"))
    assert f["layout"] == "independent" and f["klass"] == "independent"
    # a 100 um linear -> sparse; a 25 um linear -> dense
    assert probes.density_class(100.0) == "sparse"
    assert probes.density_class(25.0) == "dense"
    assert probes.density_class(400.0) == "independent"
    # tetrode -> tetrode class regardless of within-pitch
    tet = {"name": "t", "label": "t", "kind": "tetrode",
           "params": {"n_tetrodes": 4, "within_um": 25.0, "between_um": 300.0},
           "builtin": False, "note": ""}
    assert probes.geometry_features(tet)["klass"] == "tetrode"
    assert probes.contact_count(tet) == 16


def test_contact_count_and_auto_sizes():
    assert probes.auto_sizes(probes.get("independent")) is True
    assert probes.contact_count(probes.get("independent")) is None
    grid = {"name": "g", "label": "g", "kind": "grid",
            "params": {"rows": 8, "cols": 4, "xpitch_um": 50.0, "ypitch_um": 50.0},
            "builtin": False, "note": ""}
    assert probes.contact_count(grid) == 32


def test_summary_is_human_text():
    s = probes.summary(probes.get("nnx-a1x16-3mm-100"))
    assert "16" in s and "µm" in s


def test_default_probe_is_sparse_not_independent():
    # 100 µm pitch -> 'sparse' class (so dense-only sorters aren't recommended, and
    # tridesclous2 stays the geometry-aware default for this recording).
    f = probes.geometry_features(probes.get(probes.DEFAULT_PROBE))
    assert f["klass"] == "sparse" and f["layout"] == "linear"


def test_introspection_is_none_safe():
    # Global constraint: never raises (except build()). A missing profile -> safe defaults.
    assert probes.geometry_features(None)["klass"] == "sparse"
    assert probes.contact_count(None) is None
    assert probes.auto_sizes(None) is False
    assert isinstance(probes.summary(None), str)   # no AttributeError
    # get() miss -> None -> summary must not crash
    assert isinstance(probes.summary(probes.get("does-not-exist")), str)


def test_build_independent_autosizes():
    probe = probes.build(probes.get("independent"), 22)
    assert probe.get_contact_count() == 22


def test_build_linear_matches_count():
    probe = probes.build(probes.get("linear-16-50um"), 16)
    assert probe.get_contact_count() == 16
    import numpy as np
    ys = sorted(probe.contact_positions[:, 1])
    assert np.isclose(ys[1] - ys[0], 50.0)


def test_build_grid_count():
    probe = probes.build(probes.get("grid-8x4-50um"), 32)
    assert probe.get_contact_count() == 32


def test_build_tetrode_count():
    probe = probes.build(probes.get("tetrode-4"), 16)
    assert probe.get_contact_count() == 16


def test_build_mismatch_raises():
    with pytest.raises(ValueError) as e:
        probes.build(probes.get("linear-16-50um"), 22)
    assert "16" in str(e.value) and "22" in str(e.value)
