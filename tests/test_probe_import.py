"""P1 - probeinterface import into the probe library.

All probe files are built in-test (never committed fixtures - imported probes
are user data) and every store is a tmp probes.json, so nothing here touches
the real library. Covers: materialisation (the library outlives the source
file), wiring (honoured / refused honestly), honest errors naming the exact
problem, fit scoring on imported geometry, the save_profile geometry guard,
and the CLI including its channel-count verdict.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import probes  # noqa: E402


def _write_linear_json(path, n=16, pitch=100.0, wiring=None):
    """A probeinterface .json built in-test: single linear probe, optional wiring."""
    import probeinterface as pi

    p = pi.generate_linear_probe(num_elec=n, ypitch=pitch)
    if wiring is not None:
        p.set_device_channel_indices(wiring)
    pg = pi.ProbeGroup()
    pg.add_probe(p)
    pi.write_probeinterface(path, pg)
    return path


# --------------------------------------------------------------------------- #
# Import + materialisation
# --------------------------------------------------------------------------- #

def test_import_json_materialises_geometry(tmp_path):
    src = _write_linear_json(tmp_path / "lab_probe.json", n=16, pitch=100.0)
    store = tmp_path / "probes.json"
    prof = probes.import_probe_file(src, path=store)
    assert prof["name"] == "lab-probe" and prof["kind"] == "imported"
    assert prof["builtin"] is False
    f = probes.geometry_features(prof)
    assert f["n"] == 16 and f["layout"] == "linear"
    assert f["min_pitch_um"] == pytest.approx(100.0)
    assert f["density_class"] == "sparse" and f["klass"] == "sparse"
    assert probes.contact_count(prof) == 16
    assert not probes.auto_sizes(prof)
    assert "16 contacts" in probes.summary(prof)
    assert "Imported from lab_probe.json" in prof["note"]
    # in the library alongside built-ins, flagged as a user profile
    assert probes.get("lab-probe", path=store)["kind"] == "imported"


def test_import_outlives_the_source_file(tmp_path):
    # The point of materialising: the library never depends on the file again.
    src = _write_linear_json(tmp_path / "gone.json", n=4, pitch=50.0)
    store = tmp_path / "probes.json"
    probes.import_probe_file(src, path=store)
    src.unlink()
    prof = probes.get("gone", path=store)
    probe = probes.build(prof, 4)
    assert probe.get_contact_count() == 4
    assert probe.device_channel_indices.tolist() == [0, 1, 2, 3]   # identity default
    assert probe.contact_positions[:, 1].tolist() == [0.0, 50.0, 100.0, 150.0]


def test_import_prb(tmp_path):
    prb = tmp_path / "four.prb"
    prb.write_text(
        "channel_groups = {0: {'channels': [0, 1, 2, 3],\n"
        "  'geometry': {0: [0.0, 0.0], 1: [0.0, 50.0], 2: [0.0, 100.0], 3: [0.0, 150.0]}}}\n",
        encoding="utf-8")
    store = tmp_path / "probes.json"
    prof = probes.import_probe_file(prb, path=store)
    f = probes.geometry_features(prof)
    assert f["n"] == 4 and f["min_pitch_um"] == pytest.approx(50.0)
    assert prof["params"]["format"] == "prb"


def test_import_grid_layout_classified(tmp_path):
    import probeinterface as pi

    p = pi.generate_multi_columns_probe(num_columns=4, num_contact_per_column=4,
                                        xpitch=200.0, ypitch=200.0)
    pg = pi.ProbeGroup()
    pg.add_probe(p)
    src = tmp_path / "grid.json"
    pi.write_probeinterface(src, pg)
    prof = probes.import_probe_file(src, path=tmp_path / "probes.json")
    f = probes.geometry_features(prof)
    assert f["layout"] == "grid2d" and f["n"] == 16
    assert f["density_class"] == "independent"       # 200 µm pitch


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #

def test_wiring_permutation_is_preserved_and_applied(tmp_path):
    src = _write_linear_json(tmp_path / "rev.json", n=8, pitch=25.0,
                             wiring=list(range(7, -1, -1)))
    store = tmp_path / "probes.json"
    prof = probes.import_probe_file(src, path=store)
    assert prof["params"]["device_channel_indices"] == [7, 6, 5, 4, 3, 2, 1, 0]
    assert "Wiring: from file" in prof["note"]
    probe = probes.build(prof, 8)
    assert probe.device_channel_indices.tolist() == [7, 6, 5, 4, 3, 2, 1, 0]


def test_identity_wiring_is_not_stored(tmp_path):
    src = _write_linear_json(tmp_path / "ident.json", n=4, pitch=50.0,
                             wiring=[0, 1, 2, 3])
    prof = probes.import_probe_file(src, path=tmp_path / "probes.json")
    assert "device_channel_indices" not in prof["params"]
    assert "identity" in prof["note"]


def test_partial_wiring_refused(tmp_path):
    src = _write_linear_json(tmp_path / "partial.json", n=4, pitch=50.0,
                             wiring=[0, 1, 2, -1])
    with pytest.raises(ValueError, match="unconnected"):
        probes.import_probe_file(src, path=tmp_path / "probes.json")
    assert probes.user_profiles(path=tmp_path / "probes.json") == []   # nothing written


def test_non_permutation_wiring_refused(tmp_path):
    src = _write_linear_json(tmp_path / "dup.json", n=4, pitch=50.0,
                             wiring=[0, 1, 1, 3])
    with pytest.raises(ValueError, match="permutation"):
        probes.import_probe_file(src, path=tmp_path / "probes.json")


# --------------------------------------------------------------------------- #
# Honest errors
# --------------------------------------------------------------------------- #

def test_multiprobe_file_imports_since_p2(tmp_path):
    # P1 refused ProbeGroups; P2 imports them as one multi-shank profile
    # (probes = shanks). The refusal contract was retired deliberately.
    import probeinterface as pi

    pg = pi.ProbeGroup()
    for k in range(2):
        p = pi.generate_linear_probe(num_elec=4, ypitch=50.0)
        p.move([k * 150.0, 0.0])
        pg.add_probe(p)
    src = tmp_path / "two.json"
    pi.write_probeinterface(src, pg)
    prof = probes.import_probe_file(src, path=tmp_path / "probes.json")
    assert probes.geometry_features(prof)["n_shanks"] == 2


def test_unreadable_and_unsupported_files(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not a readable probeinterface"):
        probes.import_probe_file(bad, path=tmp_path / "probes.json")
    csv = tmp_path / "probe.csv"
    csv.write_text("x,y\n0,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"supported: \.json"):
        probes.import_probe_file(csv, path=tmp_path / "probes.json")
    with pytest.raises(ValueError, match="No such file"):
        probes.import_probe_file(tmp_path / "missing.json", path=tmp_path / "probes.json")


def test_name_collisions_refused(tmp_path):
    store = tmp_path / "probes.json"
    src = _write_linear_json(tmp_path / "independent.json", n=4, pitch=50.0)
    with pytest.raises(ValueError, match="built-in"):
        probes.import_probe_file(src, path=store)            # name from stem collides
    prof = probes.import_probe_file(src, name="mine", path=store)
    assert prof["name"] == "mine"
    with pytest.raises(ValueError, match="already exists"):
        probes.import_probe_file(src, name="mine", path=store)


def test_build_mismatch_names_both_counts(tmp_path):
    src = _write_linear_json(tmp_path / "eight.json", n=8, pitch=100.0)
    store = tmp_path / "probes.json"
    prof = probes.import_probe_file(src, path=store)
    with pytest.raises(ValueError, match=r"8 contacts.*16 channels"):
        probes.build(prof, 16)


# --------------------------------------------------------------------------- #
# Fit scoring + the save_profile geometry guard
# --------------------------------------------------------------------------- #

def test_fit_uses_imported_density(tmp_path):
    dense = probes.import_probe_file(
        _write_linear_json(tmp_path / "dense.json", n=16, pitch=25.0),
        path=tmp_path / "probes.json")
    assert probes.fit("kilosort4", dense)["rank"] == "good"
    assert probes.fit("tridesclous2", dense)["rank"] == "ok"
    sparse = probes.import_probe_file(
        _write_linear_json(tmp_path / "sparse.json", n=16, pitch=100.0),
        path=tmp_path / "probes.json")
    assert probes.fit("tridesclous2", sparse)["rank"] == "good"
    assert probes.fit("kilosort4", sparse)["rank"] == "poor"


def test_save_profile_guard_preserves_imported_geometry(tmp_path):
    # A generic upsert without params (e.g. a label-only edit surface) must not
    # strip materialised geometry - or the provenance note.
    store = tmp_path / "probes.json"
    src = _write_linear_json(tmp_path / "keep.json", n=4, pitch=50.0)
    probes.import_probe_file(src, path=store)
    probes.save_profile({"name": "keep", "label": "renamed label",
                         "kind": "imported", "params": {}}, path=store)
    prof = probes.get("keep", path=store)
    assert prof["label"] == "renamed label"
    assert len(prof["params"]["positions"]) == 4
    assert prof["params"]["min_pitch_um"] == pytest.approx(50.0)
    assert "Imported from keep.json" in prof["note"]      # provenance survives


def test_save_profile_refuses_orphaned_imported_geometry(tmp_path):
    # A rename-style upsert (new name, no params) has no stored geometry to
    # carry forward - it must refuse loudly, never save a broken probe.
    store = tmp_path / "probes.json"
    probes.import_probe_file(
        _write_linear_json(tmp_path / "orig.json", n=4, pitch=50.0), path=store)
    with pytest.raises(ValueError, match="without its geometry"):
        probes.save_profile({"name": "renamed", "label": "x",
                             "kind": "imported", "params": {}}, path=store)
    assert probes.get("renamed", path=store) is None       # nothing written


def test_build_refuses_geometry_less_imported_profile(tmp_path):
    # A degenerate stored record (e.g. written by an older tool) fails with a
    # named error at build, not an IndexError traceback.
    store = tmp_path / "probes.json"
    store.write_text(json.dumps({"profiles": [
        {"name": "broken", "label": "b", "kind": "imported", "params": {},
         "builtin": False, "note": ""}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="no stored geometry"):
        probes.build(probes.get("broken", path=store), 4)


def test_import_raises_when_store_unwritable(tmp_path):
    # The store layer swallows write errors; import must not report success
    # unless the profile actually landed in the library.
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory", encoding="utf-8")
    src = _write_linear_json(tmp_path / "ok.json", n=4, pitch=50.0)
    with pytest.raises(ValueError, match="Couldn't write the probe library"):
        probes.import_probe_file(src, path=blocker / "probes.json")


def test_wrong_length_wiring_refused(tmp_path):
    # device_channel_indices with fewer entries than contacts -> named error.
    src = _write_linear_json(tmp_path / "short.json", n=4, pitch=50.0)
    doc = json.loads(src.read_text(encoding="utf-8"))
    doc["probes"][0]["device_channel_indices"] = [0, 1, 2]
    src.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match=r"3 entries for 4 contacts"):
        probes.import_probe_file(src, path=tmp_path / "probes.json")


def test_duplicate_copies_imported_geometry(tmp_path):
    store = tmp_path / "probes.json"
    probes.import_probe_file(
        _write_linear_json(tmp_path / "orig.json", n=4, pitch=50.0), path=store)
    dup = probes.duplicate("orig", "orig-copy", path=store)
    assert probes.contact_count(dup) == 4
    assert probes.build(probes.get("orig-copy", path=store), 4).get_contact_count() == 4


# --------------------------------------------------------------------------- #
# P2 - multi-shank / ProbeGroup
# --------------------------------------------------------------------------- #

def _write_group_json(path, n_probes=2, n=8, pitch=100.0, spacing=150.0, wiring="global"):
    """A ProbeGroup file: probes-as-shanks, moved apart on x. wiring: 'global'
    (one permutation across the group), 'mixed' (only the first probe wired),
    or None."""
    import probeinterface as pi

    pg = pi.ProbeGroup()
    for k in range(n_probes):
        p = pi.generate_linear_probe(num_elec=n, ypitch=pitch)
        p.move([k * spacing, 0.0])
        if wiring == "global" or (wiring == "mixed" and k == 0):
            p.set_device_channel_indices(list(range(k * n, k * n + n)))
        pg.add_probe(p)
    pi.write_probeinterface(path, pg)
    return path


def test_probegroup_imports_as_one_multishank_profile(tmp_path):
    src = _write_group_json(tmp_path / "group.json")
    store = tmp_path / "probes.json"
    prof = probes.import_probe_file(src, path=store)
    f = probes.geometry_features(prof)
    assert f["n"] == 16 and f["n_shanks"] == 2 and f["layout"] == "multishank"
    assert f["min_pitch_um"] == pytest.approx(100.0)
    assert f["density_class"] == "sparse"
    assert set(f["per_shank"]) == {"0", "1"}
    assert f["per_shank"]["0"]["density_class"] == "sparse"
    assert "2 shanks" in probes.summary(prof)
    assert probes.contact_count(prof) == 16


def test_multishank_build_roundtrip_outlives_source(tmp_path):
    src = _write_group_json(tmp_path / "gone_group.json")
    store = tmp_path / "probes.json"
    prof = probes.import_probe_file(src, path=store)
    src.unlink()
    probe = probes.build(probes.get(prof["name"], path=store), 16)
    assert probe.get_contact_count() == 16
    assert sorted(set(probe.shank_ids.tolist())) == ["0", "1"]
    assert sorted(set(probe.contact_positions[:, 0].tolist())) == [0.0, 150.0]
    assert probe.device_channel_indices.tolist() == list(range(16))


def test_native_multishank_probe_and_density_is_physical(tmp_path):
    # A single Probe carrying its own shank ids; dense within-shank contacts far
    # apart across shanks must class DENSE (proximity is physics, not labels).
    import probeinterface as pi

    p = pi.generate_multi_shank(num_shank=2, shank_pitch=[300, 0], num_columns=1,
                                num_contact_per_column=8, ypitch=25.0)
    pg = pi.ProbeGroup()
    pg.add_probe(p)
    src = tmp_path / "native.json"
    pi.write_probeinterface(src, pg)
    prof = probes.import_probe_file(src, path=tmp_path / "probes.json")
    f = probes.geometry_features(prof)
    assert f["n_shanks"] == 2 and f["density_class"] == "dense"
    assert probes.fit("kilosort4", prof)["rank"] == "good"


def test_group_wiring_must_be_one_permutation(tmp_path):
    store = tmp_path / "probes.json"
    # mixed: some probes wired, some not -> refused
    mixed = _write_group_json(tmp_path / "mixed.json", wiring="mixed")
    with pytest.raises(ValueError, match="some probes in the group"):
        probes.import_probe_file(mixed, path=store)
    # overlapping indices across probes -> refused with the reason named.
    # probeinterface's reader catches this case itself ("not unique across
    # probes") and the import wraps it honestly; the import's own permutation
    # check stays as the defense for paths the reader doesn't validate.
    dup = _write_group_json(tmp_path / "dup.json", n=4, wiring="global")
    doc = json.loads(dup.read_text(encoding="utf-8"))
    doc["probes"][1]["device_channel_indices"] = [0, 1, 2, 3]   # duplicates probe 0
    dup.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="not unique across probes|permutation"):
        probes.import_probe_file(dup, path=store)
    # per-probe blocks in concatenation order ARE the global identity -> not stored
    good = _write_group_json(tmp_path / "wired.json", wiring="global")
    prof = probes.import_probe_file(good, path=store)
    assert "device_channel_indices" not in prof["params"]
    assert probes.build(prof, 16).device_channel_indices.tolist() == list(range(16))


def test_group_nonidentity_wiring_is_honoured(tmp_path):
    # The highest-stakes path: reversed per-probe blocks (probe 0 -> channels
    # 8..15, probe 1 -> 0..7) must survive import + build verbatim, so a
    # specific CHANNEL provably lands on a specific shank and position. A
    # regression that reorders probes or renormalises indices scrambles every
    # cross-shank channel->site association - this pins it.
    import probeinterface as pi

    pg = pi.ProbeGroup()
    for k, blk in enumerate([range(8, 16), range(0, 8)]):
        p = pi.generate_linear_probe(num_elec=8, ypitch=100.0)
        p.move([k * 150.0, 0.0])
        p.set_device_channel_indices(list(blk))
        pg.add_probe(p)
    src = tmp_path / "rev_group.json"
    pi.write_probeinterface(src, pg)
    prof = probes.import_probe_file(src, path=tmp_path / "probes.json")
    expect = list(range(8, 16)) + list(range(0, 8))
    assert prof["params"]["device_channel_indices"] == expect
    probe = probes.build(prof, 16)
    assert probe.device_channel_indices.tolist() == expect
    # channel 0 = the first contact of probe 1: shank "1", x = 150, y = 0
    idx = probe.device_channel_indices.tolist().index(0)
    assert probe.shank_ids[idx] == "1"
    assert probe.contact_positions[idx].tolist() == [150.0, 0.0]


def test_save_profile_guard_preserves_wiring_and_shanks(tmp_path):
    # An upsert that carries positions but omits the other materialised keys
    # must not silently strip shank labels or revert wiring to identity.
    import probeinterface as pi

    store = tmp_path / "probes.json"
    pg = pi.ProbeGroup()
    for k in range(2):
        p = pi.generate_linear_probe(num_elec=4, ypitch=50.0)
        p.move([k * 150.0, 0.0])
        p.set_device_channel_indices(list(range((1 - k) * 4, (1 - k) * 4 + 4)))
        pg.add_probe(p)
    src = tmp_path / "wired2.json"
    pi.write_probeinterface(src, pg)
    prof = probes.import_probe_file(src, path=store)
    probes.save_profile({"name": prof["name"], "label": "edited", "kind": "imported",
                         "params": {"positions": prof["params"]["positions"]}},
                        path=store)
    kept = probes.get(prof["name"], path=store)
    assert kept["params"]["device_channel_indices"] == prof["params"]["device_channel_indices"]
    assert kept["params"]["shank_ids"] == prof["params"]["shank_ids"]


def test_prb_channel_groups_become_shanks(tmp_path):
    prb = tmp_path / "two_shank.prb"
    prb.write_text(
        "channel_groups = {\n"
        " 0: {'channels': [0, 1, 2, 3],\n"
        "     'geometry': {0: [0.0, 0.0], 1: [0.0, 100.0], 2: [0.0, 200.0], 3: [0.0, 300.0]}},\n"
        " 1: {'channels': [4, 5, 6, 7],\n"
        "     'geometry': {4: [150.0, 0.0], 5: [150.0, 100.0], 6: [150.0, 200.0], 7: [150.0, 300.0]}},\n"
        "}\n", encoding="utf-8")
    prof = probes.import_probe_file(prb, path=tmp_path / "probes.json")
    f = probes.geometry_features(prof)
    assert f["n"] == 8 and f["n_shanks"] == 2 and f["layout"] == "multishank"


def test_single_shank_import_shape_unchanged(tmp_path):
    # P1 backward compatibility: a plain single probe stores no shank keys and
    # keeps its P1 layout classing.
    src = _write_linear_json(tmp_path / "plain.json", n=16, pitch=100.0)
    prof = probes.import_probe_file(src, path=tmp_path / "probes.json")
    assert "shank_ids" not in prof["params"] and "per_shank" not in prof["params"]
    f = probes.geometry_features(prof)
    assert f["layout"] == "linear" and "n_shanks" not in f


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "probes.py"), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, cwd=ROOT)


def test_cli_import_and_list(tmp_path):
    src = _write_linear_json(tmp_path / "cli_probe.json", n=16, pitch=100.0)
    store = tmp_path / "probes.json"
    empty = tmp_path / "nodata"
    empty.mkdir()
    res = _cli("import", str(src), "--library", str(store), "--data-dir", str(empty))
    assert res.returncode == 0, res.stderr
    assert "✓ imported 'cli-probe'" in res.stdout
    assert "identity" in res.stdout
    assert "channel check skipped" in res.stdout           # no recording in --data-dir
    res = _cli("list", "--library", str(store))
    assert res.returncode == 0
    assert "cli-probe" in res.stdout and "[imported]" in res.stdout


def test_cli_import_failure_is_honest(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("nope", encoding="utf-8")
    res = _cli("import", str(bad), "--library", str(tmp_path / "probes.json"))
    assert res.returncode == 1
    assert "not a readable probeinterface" in res.stderr


def test_cli_count_verdict_against_recording(tmp_path):
    # Uses the real recording when present (16 neural channels): an 8-contact
    # import must warn loudly, naming both counts; skips on a data-less clone.
    import blackrock_io as bio

    try:
        bio.find_blackrock_base()
    except FileNotFoundError:
        pytest.skip("no recording on this machine")
    src = _write_linear_json(tmp_path / "eight.json", n=8, pitch=100.0)
    res = _cli("import", str(src), "--library", str(tmp_path / "probes.json"))
    assert res.returncode == 0
    assert "MISMATCH" in res.stdout
    assert "8 contacts" in res.stdout and "16" in res.stdout
