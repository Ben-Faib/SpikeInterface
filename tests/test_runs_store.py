"""The versioned run store (W2): the pointer rules, the smoke rule, legacy
resolution, provenance completeness and the regeneration match report.

Every store function takes ``outputs=`` so the whole store can be built in a
tmp directory — none of this runs a sorter. The two things that cannot be faked
are pinned against the real repo instead and skip on a data-less clone: that a
saved ``run_info.json`` really carries every provenance block, and that a real
probe's geometry hash is stable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import runs  # noqa: E402
import run_sorting as rs  # noqa: E402


# --------------------------------------------------------------------------- #
# A tmp store
# --------------------------------------------------------------------------- #
@pytest.fixture
def store(tmp_path):
    """A tmp ``outputs/`` plus builders for runs, legacy layouts and corpses."""
    out = tmp_path / "outputs"

    class Store:
        outputs = out

        def run(self, sorter, run_id, *, smoke=False, units=10, seconds=132.0,
                analyzer=True, **info):
            d = out / sorter / "runs" / run_id
            (d / "analyzer").mkdir(parents=True, exist_ok=True) if analyzer else d.mkdir(
                parents=True, exist_ok=True)
            day, clock, _ = run_id.split("-")
            record = {"run_id": run_id, "sorter": sorter, "smoke": smoke,
                      "n_units": units, "effective_seconds": seconds,
                      "created": f"{day[:4]}-{day[4:6]}-{day[6:]}T"
                                 f"{clock[:2]}:{clock[2:4]}:{clock[4:]}", **info}
            (d / "run_info.json").write_text(json.dumps(record), encoding="utf-8")
            return d

        def legacy(self, sorter, *, units=7, seconds=132.0, **info):
            d = out / sorter
            (d / "analyzer").mkdir(parents=True, exist_ok=True)
            (d / "run_info.json").write_text(
                json.dumps({"sorter": sorter, "n_units": units,
                            "effective_seconds": seconds, "created": "2026-01-01T00:00:00",
                            **info}), encoding="utf-8")
            return d

        def corpse(self, sorter, run_id):
            """A run directory from a sort that died before writing its record."""
            d = out / sorter / "runs" / run_id / "sorter_output"
            d.mkdir(parents=True, exist_ok=True)
            return d.parent

    return Store()


# --------------------------------------------------------------------------- #
# Paths and ids
# --------------------------------------------------------------------------- #
def test_new_run_id_is_time_sortable():
    from datetime import datetime

    early = runs.new_run_id(datetime(2026, 8, 18, 22, 7, 36), "aaaaaa")
    late = runs.new_run_id(datetime(2026, 8, 18, 22, 9, 1), "000000")
    assert early == "20260818-220736-aaaaaa"
    assert early < late          # id order is time order even with a smaller suffix


def test_new_run_ids_do_not_collide_within_a_second():
    from datetime import datetime

    when = datetime(2026, 8, 18, 22, 7, 36)
    assert len({runs.new_run_id(when) for _ in range(50)}) == 50


def test_run_dir_maps_legacy_to_the_sorter_dir(store):
    assert runs.run_dir("tdc2", runs.LEGACY_RUN_ID, outputs=store.outputs) == \
        store.outputs / "tdc2"
    assert runs.run_dir("tdc2", "abc", outputs=store.outputs) == \
        store.outputs / "tdc2" / "runs" / "abc"


@pytest.mark.parametrize("path,expected", [
    ("outputs/tridesclous2/runs/20260818-1-aa/analyzer", "tridesclous2"),
    ("outputs/tridesclous2/regen/20260818-1-aa/analyzer", "tridesclous2"),
    ("outputs/tridesclous2/analyzer", "tridesclous2"),
])
def test_sorter_for_dir(path, expected):
    assert runs.sorter_for_dir(Path(path)) == expected


def test_sort_paths_puts_curation_inside_the_run_it_curates(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    p = runs.sort_paths("tdc2", outputs=store.outputs)
    assert p["record"].parent == p["out"]
    assert p["curated"].parent == p["out"]
    # The sort log is per SORTER, not per run: it is opened before the child
    # process (and so before the run directory) exists.
    assert p["log"] == store.outputs / "tdc2" / "sort.log"


# The keys curation.py's own sort_paths() returns on main (scripts/curation.py,
# after the Phy-export slice). Hardcoded on purpose: this worktree branched
# before that slice, so importing main's file here would test the wrong tree.
# runs.sort_paths must stay a SUPERSET — W1's seam re-points at this module at
# integration, and a key that only curation.py has is a break at that moment.
CURATION_SORT_PATHS_KEYS = (
    "root", "out", "sorting", "analyzer", "run_info", "summary", "record", "phy",
    "curated", "curated_sorting", "curated_analyzer", "curated_run_info",
    "curated_metrics", "curated_phy",
)


def test_sort_paths_is_a_superset_of_curations(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    p = runs.sort_paths("tdc2", outputs=store.outputs)
    assert [k for k in CURATION_SORT_PATHS_KEYS if k not in p] == []
    # ...with the same shapes: the export rides inside the run it exports, and
    # the curated export inside the curated output.
    assert p["phy"] == p["out"] / "phy"
    assert p["curated_phy"] == p["curated"] / "phy"


def test_sort_paths_falls_back_to_legacy_paths_when_nothing_is_saved(store):
    p = runs.sort_paths("tdc2", outputs=store.outputs)
    assert p["id"] is None
    assert p["analyzer"] == store.outputs / "tdc2" / "analyzer"   # .exists() is False


def test_sort_paths_accepts_an_explicit_run_id(store):
    d = store.run("tdc2", "20260818-000001-aaaaaa")
    store.run("tdc2", "20260818-000002-bbbbbb")
    p = runs.sort_paths("tdc2", outputs=store.outputs, run="20260818-000001-aaaaaa")
    assert p["out"] == d and p["id"] == "20260818-000001-aaaaaa"


# --------------------------------------------------------------------------- #
# The pointer and the resolution order
# --------------------------------------------------------------------------- #
def test_resolve_is_none_when_nothing_is_saved(store):
    assert runs.resolve("tdc2", outputs=store.outputs) is None
    assert runs.saved_sorters(outputs=store.outputs) == []


def test_the_pointer_wins_over_recency(store):
    old = store.run("tdc2", "20260818-000001-aaaaaa")
    store.run("tdc2", "20260818-000002-bbbbbb")
    runs.write_pointer("tdc2", "20260818-000001-aaaaaa", outputs=store.outputs)
    found = runs.resolve("tdc2", outputs=store.outputs)
    assert (found["dir"], found["how"]) == (old, "pointer")


def test_a_dangling_pointer_falls_through_to_the_newest_full_run(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    newer = store.run("tdc2", "20260818-000002-bbbbbb")
    runs.write_pointer("tdc2", "20260818-000009-deleted", outputs=store.outputs)
    found = runs.resolve("tdc2", outputs=store.outputs)
    assert (found["dir"], found["how"]) == (newer, "newest full run")


def test_a_smoke_run_never_wins_the_fallback_over_a_full_run(store):
    full = store.run("tdc2", "20260818-000001-aaaaaa")
    store.run("tdc2", "20260818-000002-bbbbbb", smoke=True, seconds=30.0)  # newer
    found = runs.resolve("tdc2", outputs=store.outputs)
    assert (found["dir"], found["how"]) == (full, "newest full run")


def test_a_smoke_run_resolves_when_it_is_all_there_is(store):
    d = store.run("tdc2", "20260818-000001-aaaaaa", smoke=True, seconds=30.0)
    found = runs.resolve("tdc2", outputs=store.outputs)
    assert found["dir"] == d and "smoke" in found["how"]


def test_the_pointer_may_name_the_legacy_layout(store):
    legacy = store.legacy("tdc2")
    store.run("tdc2", "20260818-000002-bbbbbb")
    runs.write_pointer("tdc2", runs.LEGACY_RUN_ID, outputs=store.outputs)
    found = runs.resolve("tdc2", outputs=store.outputs)
    assert (found["dir"], found["how"]) == (legacy, "pointer")


def test_write_pointer_leaves_no_temp_file_behind(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    runs.write_pointer("tdc2", "20260818-000001-aaaaaa", outputs=store.outputs,
                       reason="because")
    sd = store.outputs / "tdc2"
    assert [p.name for p in sd.iterdir() if p.name.endswith(".tmp")] == []
    payload = runs.read_pointer("tdc2", outputs=store.outputs)
    assert payload["run_id"] == "20260818-000001-aaaaaa"
    assert payload["reason"] == "because" and payload["updated"]


def test_saved_sorters_lists_only_sorters_with_a_resolvable_run(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    store.legacy("lupin")
    (store.outputs / "simple").mkdir(parents=True)          # an empty sorter dir
    assert runs.saved_sorters(outputs=store.outputs) == ["lupin", "tdc2"]


# --------------------------------------------------------------------------- #
# Legacy resolution is read-only
# --------------------------------------------------------------------------- #
def test_legacy_alone_resolves(store):
    d = store.legacy("tdc2")
    found = runs.resolve("tdc2", outputs=store.outputs)
    assert (found["dir"], found["how"], found["legacy"]) == (d, "legacy layout", True)
    assert found["id"] == runs.LEGACY_RUN_ID


def test_a_new_run_takes_over_from_legacy_without_touching_it(store):
    legacy = store.legacy("tdc2", units=7)
    fresh = store.run("tdc2", "20260818-000001-aaaaaa", units=15)
    before = (legacy / "run_info.json").read_text(encoding="utf-8")
    found = runs.resolve("tdc2", outputs=store.outputs)
    assert (found["dir"], found["how"]) == (fresh, "newest full run")
    assert (legacy / "run_info.json").read_text(encoding="utf-8") == before
    assert (legacy / "analyzer").is_dir()          # nothing was moved or deleted


def test_list_runs_puts_legacy_last(store):
    store.legacy("tdc2")
    store.run("tdc2", "20260818-000001-aaaaaa")
    listed = runs.list_runs("tdc2", outputs=store.outputs)
    assert [r["id"] for r in listed] == ["20260818-000001-aaaaaa", runs.LEGACY_RUN_ID]


def test_list_runs_can_exclude_legacy(store):
    store.legacy("tdc2")
    assert runs.list_runs("tdc2", outputs=store.outputs, include_legacy=False) == []


def test_is_smoke_reads_the_pre_w2_duration_arg(store):
    # A legacy record has no "smoke" key; --duration is what made it a smoke run.
    assert runs.is_smoke({"duration_arg": 30.0}) is True
    assert runs.is_smoke({"duration_arg": None}) is False
    assert runs.is_smoke({"smoke": False, "duration_arg": 30.0}) is False   # flag wins


# --------------------------------------------------------------------------- #
# The smoke rule: a smoke run can never clobber a full run
# --------------------------------------------------------------------------- #
def test_a_smoke_run_is_refused_and_the_full_run_is_pinned(store):
    store.run("tdc2", "20260818-000001-aaaaaa", units=17)
    store.run("tdc2", "20260818-000002-bbbbbb", smoke=True, seconds=30.0, units=13)
    ok, msg = runs.set_current("tdc2", "20260818-000002-bbbbbb", outputs=store.outputs)
    assert ok is False
    assert "did NOT become the current" in msg and "--make-current" in msg
    assert "20260818-000001-aaaaaa" in msg and "17 units" in msg
    # PINNED: the refusal is written down, not merely returned.
    pointer = runs.read_pointer("tdc2", outputs=store.outputs)
    assert pointer["run_id"] == "20260818-000001-aaaaaa"
    assert "pinned" in pointer["reason"]
    assert runs.resolve("tdc2", outputs=store.outputs)["how"] == "pointer"


def test_the_pin_survives_a_later_full_run_arriving(store):
    """The pin is a decision, not a cache: a newer full run does not silently
    steal the pointer from the run the user pinned. Only set_current moves it."""
    store.run("tdc2", "20260818-000001-aaaaaa", units=17)
    store.run("tdc2", "20260818-000002-bbbbbb", smoke=True, seconds=30.0)
    runs.set_current("tdc2", "20260818-000002-bbbbbb", outputs=store.outputs)
    store.run("tdc2", "20260818-000003-cccccc", units=15)      # a newer full run
    assert runs.resolve("tdc2", outputs=store.outputs)["id"] == "20260818-000001-aaaaaa"
    ok, _ = runs.set_current("tdc2", "20260818-000003-cccccc", outputs=store.outputs)
    assert ok and runs.resolve("tdc2", outputs=store.outputs)["id"] == "20260818-000003-cccccc"


def test_make_current_forces_a_smoke_run_over_a_full_run(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    store.run("tdc2", "20260818-000002-bbbbbb", smoke=True, seconds=30.0)
    ok, msg = runs.set_current("tdc2", "20260818-000002-bbbbbb", outputs=store.outputs,
                               force=True)
    assert ok and "forced over a full run" in msg
    assert runs.read_pointer("tdc2", outputs=store.outputs)["run_id"] == \
        "20260818-000002-bbbbbb"
    assert runs.read_pointer("tdc2", outputs=store.outputs)["reason"] == "forced"


def test_a_smoke_run_becomes_current_when_there_is_no_full_run(store):
    store.run("tdc2", "20260818-000001-aaaaaa", smoke=True, seconds=30.0)
    ok, msg = runs.set_current("tdc2", "20260818-000001-aaaaaa", outputs=store.outputs)
    assert ok and "current smoke run is now" in msg


def test_a_smoke_run_does_not_displace_a_legacy_full_sort(store):
    store.legacy("tdc2", units=7)
    store.run("tdc2", "20260818-000001-aaaaaa", smoke=True, seconds=30.0)
    ok, msg = runs.set_current("tdc2", "20260818-000001-aaaaaa", outputs=store.outputs)
    assert ok is False and runs.LEGACY_RUN_ID in msg
    assert runs.read_pointer("tdc2", outputs=store.outputs)["run_id"] == runs.LEGACY_RUN_ID


def test_a_full_run_always_becomes_current(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    store.run("tdc2", "20260818-000002-bbbbbb")
    ok, msg = runs.set_current("tdc2", "20260818-000002-bbbbbb", outputs=store.outputs)
    assert ok and "current run is now 20260818-000002-bbbbbb" in msg


def test_set_current_refuses_an_unknown_run_and_leaves_the_pointer_alone(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    runs.write_pointer("tdc2", "20260818-000001-aaaaaa", outputs=store.outputs)
    ok, msg = runs.set_current("tdc2", "nope", outputs=store.outputs)
    assert ok is False and "no run 'nope'" in msg
    assert runs.read_pointer("tdc2", outputs=store.outputs)["run_id"] == \
        "20260818-000001-aaaaaa"


def test_re_pointing_at_the_current_smoke_run_is_not_a_refusal(store):
    """Only DISPLACING a full run is refused; re-affirming the smoke run that is
    already current must not be turned into a refusal of itself."""
    store.run("tdc2", "20260818-000001-aaaaaa", smoke=True, seconds=30.0)
    runs.set_current("tdc2", "20260818-000001-aaaaaa", outputs=store.outputs)
    ok, _ = runs.set_current("tdc2", "20260818-000001-aaaaaa", outputs=store.outputs)
    assert ok is True


# --------------------------------------------------------------------------- #
# Unfinished runs (a sort that died before writing its record)
# --------------------------------------------------------------------------- #
def test_list_runs_skips_a_run_with_no_record_but_it_is_still_findable(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    corpse = store.corpse("tdc2", "20260818-000002-bbbbbb")
    assert [r["id"] for r in runs.list_runs("tdc2", outputs=store.outputs)] == \
        ["20260818-000001-aaaaaa"]
    assert runs.unfinished_runs("tdc2", outputs=store.outputs) == [corpse]
    # ...and it is left on disk: sorter_output/ is the only evidence of the crash.
    assert (corpse / "sorter_output").is_dir()


def test_unfinished_runs_is_empty_for_a_clean_store(store):
    store.run("tdc2", "20260818-000001-aaaaaa")
    assert runs.unfinished_runs("tdc2", outputs=store.outputs) == []
    assert runs.unfinished_runs("never-sorted", outputs=store.outputs) == []


def test_a_corpse_does_not_make_a_sorter_resolvable(store):
    store.corpse("tdc2", "20260818-000001-aaaaaa")
    assert runs.resolve("tdc2", outputs=store.outputs) is None
    assert runs.saved_sorters(outputs=store.outputs) == []


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
PROVENANCE_KEYS = (
    "schema_version", "created", "command", "argv", "run_id", "run_dir", "smoke",
    "sorter", "params", "seed", "determinism", "probe_id", "geometry_hash",
    "preprocessing", "packages", "platform", "git", "recording", "bad_channels",
    "channel_ids", "freq_min", "freq_max", "effective_seconds", "total_seconds",
    "n_units",
)


def _saved_records():
    """The real saved records, found by ASKING the module that owns the layout.

    A hardcoded ``outputs/*/runs/*/run_info.json`` glob is the exact trap this
    lane already fell into once: when the layout moved, the glob went empty and
    the test that guards provenance turned into a silent skip instead of a
    failure. Legacy runs are excluded — they predate every W2 block.
    """
    return [Path(r["dir"]) / runs.RUN_INFO_NAME
            for sorter in runs.saved_sorters(root=ROOT)
            for r in runs.list_runs(sorter, root=ROOT, include_legacy=False)]


def test_a_real_saved_record_carries_every_provenance_block():
    records = _saved_records()
    if not records:
        pytest.skip("no saved run in outputs/ — run scripts/run_sorting.py first")
    info = json.loads(records[0].read_text(encoding="utf-8"))
    missing = [k for k in PROVENANCE_KEYS if k not in info]
    assert not missing, f"{records[0]} is missing {missing}"
    assert set(info["params"]) >= {"effective", "defaults", "overrides"}
    assert set(info["seed"]) == {"key", "value", "pinned"}
    assert set(info["determinism"]) == {"class", "note"}
    assert [s["step"] for s in info["preprocessing"]["chain"]] == [
        "read_broadband", "drop_aux_channels", "set_probe", "bandpass_filter",
        "exclude_bad_channels", "common_reference", "frame_slice"]
    assert info["packages"]["spikeinterface"]


def test_write_run_info_writes_the_base_provenance(tmp_path):
    import argparse

    args = argparse.Namespace(duration=None, keep_analog=False, n_jobs=1,
                              probe="nnx-a1x16-3mm-100")
    rs._write_run_info(tmp_path, args, sorter="tdc2", run_id="20260818-000001-aaaaaa",
                       n_units=15)
    info = json.loads((tmp_path / "run_info.json").read_text(encoding="utf-8"))
    for key in ("schema_version", "created", "command", "argv", "duration_arg",
                "keep_analog", "n_jobs", "probe", "packages", "platform", "git"):
        assert key in info, key
    assert info["sorter"] == "tdc2" and info["n_units"] == 15   # passthrough fields


def test_write_run_info_never_fails_a_finished_sort(tmp_path):
    """Provenance is best-effort: an unwritable destination must not raise after
    the sorting is already saved."""
    import argparse

    args = argparse.Namespace(duration=None, keep_analog=False, n_jobs=1, probe=None)
    rs._write_run_info(tmp_path / "does" / "not" / "exist", args, sorter="tdc2")


def test_package_versions_reports_the_packages_that_change_a_sort():
    got = runs.package_versions()
    assert set(got) == set(runs.PROVENANCE_PACKAGES)
    assert got["spikeinterface"] and got["numpy"]


def test_package_versions_records_an_absent_package_as_none():
    assert runs.package_versions(("definitely-not-installed-xyz",)) == \
        {"definitely-not-installed-xyz": None}


def test_platform_info_names_the_machine():
    info = runs.platform_info()
    assert set(info) == {"system", "release", "machine", "python"}
    assert all(info.values())


def test_git_info_shape():
    info = runs.git_info(ROOT)
    assert set(info) == {"sha", "branch", "dirty"}
    assert info["sha"] is None or len(info["sha"]) == 40
    assert info["dirty"] in (True, False, None)


def test_git_info_degrades_on_a_non_repo(tmp_path):
    info = runs.git_info(tmp_path)
    assert set(info) == {"sha", "branch", "dirty"}


def test_seed_of_reports_whether_a_seed_was_actually_pinned():
    assert runs.seed_of("tdc2", {"seed": None}) == \
        {"key": "seed", "value": None, "pinned": False}
    assert runs.seed_of("tdc2", {"seed": 42}) == \
        {"key": "seed", "value": 42, "pinned": True}
    assert runs.seed_of("tdc2", {"random_seed": 7})["key"] == "random_seed"
    assert runs.seed_of("tdc2", {})["key"] is None


def test_determinism_is_measured_for_tridesclous2_and_unverified_otherwise():
    det = runs.determinism_of("tridesclous2")
    assert det["class"] == "measured-stochastic"
    assert "14, 16 and 18 units" in det["note"]
    other = runs.determinism_of("some-sorter-nobody-measured")
    assert other["class"] == "unverified" and "has not been measured" in other["note"]


def test_geometry_hash_is_stable_and_sensitive():
    probes = pytest.importorskip("probes")
    a = probes.build(probes.get(probes.DEFAULT_PROBE), 16)
    b = probes.build(probes.get(probes.DEFAULT_PROBE), 16)
    other = probes.build(probes.get("independent"), 16)
    assert runs.geometry_hash(a) == runs.geometry_hash(b)
    assert runs.geometry_hash(a) != runs.geometry_hash(other)
    assert len(runs.geometry_hash(a)) == 16


def test_geometry_hash_of_a_non_probe_is_none():
    assert runs.geometry_hash(object()) is None


# --------------------------------------------------------------------------- #
# Containment
# --------------------------------------------------------------------------- #
def test_containment_of_a_train_with_itself_is_one():
    t = [0.1, 0.2, 0.35, 1.0]
    assert runs.containment(t, t, 0.0004) == 1.0


def test_containment_counts_a_spike_inside_the_window():
    a = [1.0, 2.0]
    b = [1.0003, 2.0003]           # 0.3 ms late
    assert runs.containment(a, b, 0.0004) == 1.0
    assert runs.containment(a, b, 0.0002) == 0.0


def test_containment_is_asymmetric_when_one_side_has_extra_spikes():
    a = [1.0, 2.0]
    b = [1.0, 2.0, 3.0, 4.0]
    assert runs.containment(a, b, 0.0004) == 1.0     # every a spike is in b
    assert runs.containment(b, a, 0.0004) == 0.5     # half of b is not in a


def test_containment_handles_empty_sides():
    import math

    assert math.isnan(runs.containment([], [1.0], 0.0004))
    assert runs.containment([1.0], [], 0.0004) == 0.0


def test_containment_finds_a_match_on_either_side_of_a_spike():
    # searchsorted lands between two candidates; the nearer one must win.
    assert runs.containment([1.0], [0.9997, 1.5], 0.0004) == 1.0
    assert runs.containment([1.0], [0.5, 1.0003], 0.0004) == 1.0


# --------------------------------------------------------------------------- #
# The match report
# --------------------------------------------------------------------------- #
def _record(**over):
    base = {
        "run_id": "20260818-000001-aaaaaa", "sorter": "tridesclous2", "n_units": 15,
        "channel_ids": [str(i) for i in range(1, 17)],
        "freq_min": 300.0, "freq_max": 6000.0, "keep_analog": False,
        "n_dropped_analog": 6, "effective_seconds": 132.016,
        "preprocessing": {"reference": "global median"},
        "bad_channels": {"excluded": [], "method": "mad", "enabled": True},
        "geometry_hash": "bd6d13d32e1f46f7", "probe_id": "nnx-a1x16-3mm-100",
        "params": {"effective": {"detect_threshold": 5.0, "peak_sign": "neg",
                                 "n_pca_features": 6},
                   "defaults": {}, "overrides": {}},
        "recording": {"data_dir": None, "base": "PFCM7_d0ephys_Block2",
                      "sampling_rate_hz": 30000.0},
        "packages": {"spikeinterface": "0.104.3", "numpy": "2.4.6"},
        "git": {"sha": "467ed7ec604b671cd1c8668a0cd5c281c5c3f433"},
        "determinism": runs.determinism_of("tridesclous2"),
    }
    base.update(over)
    return base


def _summary(noise=4.03, v_pp=30.9, snr=5.18, yield_pct=87.5):
    return {"noise_floor_uV": {"median": noise}, "v_pp_uV": {"median": v_pp},
            "snr": {"median": snr}, "yield_pct": yield_pct}


def _verdicts(report):
    return {c["name"]: c["verdict"] for c in report["criteria"]}


SPIKES = [i / 100.0 for i in range(1000)]


def test_a_clean_pair_regenerates():
    report = runs.compare_runs(
        _record(), _record(run_id="20260818-000002-bbbbbb", n_units=16),
        recorded_summary=_summary(), regenerated_summary=_summary(4.105, 29.8, 5.01, 87.5),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    assert report["verdict"] == "REGENERATED — BIT-IDENTICAL SPIKE TRAINS"
    assert report["failed"] == []
    v = _verdicts(report)
    assert v["recording"] == runs.V_MATCH
    assert v["channels sorted"] == runs.V_MATCH
    assert v["preprocessing chain"] == runs.V_MATCH
    assert v["sorter params"] == runs.V_MATCH
    assert v["probe geometry"] == runs.V_MATCH
    assert v["noise floor (µV)"] == runs.V_WITHIN


def test_a_stochastic_but_honest_re_run_still_regenerates():
    """The measured case: different unit counts, spikes 92% contained, metrics a
    few percent apart. This must PASS — it is what tridesclous2 does here."""
    regen_spikes = [t + 0.0002 for t in SPIKES[:930]] + [50.0 + i / 100.0 for i in range(40)]
    report = runs.compare_runs(
        _record(n_units=15), _record(run_id="r2", n_units=18),
        recorded_summary=_summary(4.03, 30.985, 5.177, 87.5),
        regenerated_summary=_summary(4.142, 28.241, 5.008, 93.8),
        recorded_spikes=SPIKES, regenerated_spikes=regen_spikes)
    assert report["verdict"] == "REGENERATED"
    assert report["failed"] == []


def test_unit_count_is_never_a_criterion():
    report = runs.compare_runs(
        _record(n_units=14), _record(n_units=18),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    unit = next(c for c in report["criteria"] if c["name"] == "unit count")
    assert unit["verdict"] == runs.V_INFO and unit["tolerance"] == "NOT A CRITERION"
    assert "14, 16 and 18 units" in unit["note"]
    assert report["verdict"].startswith("REGENERATED")


def test_a_changed_band_is_a_failure():
    report = runs.compare_runs(
        _record(), _record(freq_min=500.0),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    assert report["verdict"] == "NOT REGENERATED"
    assert "preprocessing chain" in report["failed"]
    chain = next(c for c in report["criteria"] if c["name"] == "preprocessing chain")
    assert "freq_min" in chain["note"]


def test_a_different_bad_channel_set_is_a_failure():
    report = runs.compare_runs(
        _record(), _record(bad_channels={"excluded": ["7"], "method": "mad",
                                         "enabled": True}),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    assert "preprocessing chain" in report["failed"]


def test_a_hand_edited_sorter_parameter_is_a_failure_that_names_the_key():
    """The hole this criterion closes: detect_threshold 5→3 in an exported config
    changes what the sorter was ASKED, and can still land inside containment and
    inside every metric band. Without this criterion the report prints
    REGENERATED and never mentions that the knobs differ."""
    edited = _record(params={"effective": {"detect_threshold": 3.0, "peak_sign": "neg",
                                           "n_pca_features": 6}})
    report = runs.compare_runs(
        _record(), edited,
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    assert report["verdict"] == "NOT REGENERATED"
    assert report["failed"] == ["sorter params"]     # everything else matched
    par = next(c for c in report["criteria"] if c["name"] == "sorter params")
    assert par["verdict"] == runs.V_DIFFERS
    assert "detect_threshold" in par["note"] and "5.0" in par["note"] and "3.0" in par["note"]
    assert "detect_threshold" in runs.format_match_report(report)   # and it prints


def test_a_parameter_only_one_side_has_is_named_absent():
    report = runs.compare_runs(
        _record(), _record(params={"effective": {"detect_threshold": 5.0,
                                                 "peak_sign": "neg"}}),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    par = next(c for c in report["criteria"] if c["name"] == "sorter params")
    assert par["verdict"] == runs.V_DIFFERS
    assert "n_pca_features" in par["note"] and "absent" in par["note"]


def test_a_record_without_effective_parameters_is_not_compared():
    report = runs.compare_runs(
        _record(params={}), _record(),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    par = next(c for c in report["criteria"] if c["name"] == "sorter params")
    assert par["verdict"] == runs.V_SKIPPED
    assert report["failed"] == []


def test_a_different_recording_is_a_failure_that_names_itself():
    """A config re-run against another machine's file set sorts *something*, and
    every other criterion then fails obliquely. The report must name the cause."""
    report = runs.compare_runs(
        _record(), _record(recording={"base": "SomeOtherBlock",
                                      "sampling_rate_hz": 30000.0}),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    assert report["verdict"] == "NOT REGENERATED"
    assert report["failed"] == ["recording"]
    rec = next(c for c in report["criteria"] if c["name"] == "recording")
    assert rec["verdict"] == runs.V_DIFFERS and "base name" in rec["note"]
    assert "SomeOtherBlock" in rec["regenerated"]


def test_a_different_sampling_rate_is_a_failure():
    report = runs.compare_runs(
        _record(), _record(recording={"base": "PFCM7_d0ephys_Block2",
                                      "sampling_rate_hz": 20000.0}),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    rec = next(c for c in report["criteria"] if c["name"] == "recording")
    assert rec["verdict"] == runs.V_DIFFERS and "sampling rate" in rec["note"]


def test_a_record_without_a_recording_block_is_not_compared():
    """A pre-W2 record carries no recording identity — NOT COMPARED, not a pass."""
    report = runs.compare_runs(
        _record(recording={}), _record(),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    rec = next(c for c in report["criteria"] if c["name"] == "recording")
    assert rec["verdict"] == runs.V_SKIPPED
    assert report["failed"] == []


def test_a_different_channel_set_is_a_failure():
    report = runs.compare_runs(
        _record(), _record(channel_ids=[str(i) for i in range(1, 16)]),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    assert "channels sorted" in report["failed"]


def test_a_different_geometry_hash_is_a_failure():
    report = runs.compare_runs(
        _record(), _record(geometry_hash="0000000000000000"),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    assert "probe geometry" in report["failed"]


def test_a_different_environment_is_a_caveat_not_a_failure():
    report = runs.compare_runs(
        _record(), _record(packages={"spikeinterface": "0.105.0", "numpy": "2.4.6"}),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES[:-1])
    assert report["verdict"] == "REGENERATED WITH CAVEATS"
    assert report["failed"] == []
    env = next(c for c in report["criteria"] if c["name"] == "environment")
    assert env["verdict"] == runs.V_INFO and "spikeinterface" in env["note"]


def test_a_re_applied_channel_gain_fails_on_the_noise_floor():
    """The double-scaling canary: ~4 µV against ~1 µV must never pass."""
    report = runs.compare_runs(
        _record(), _record(),
        recorded_summary=_summary(noise=4.03), regenerated_summary=_summary(noise=1.007),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    assert report["verdict"] == "NOT REGENERATED"
    assert "noise floor (µV)" in report["failed"]


def test_low_containment_fails():
    report = runs.compare_runs(
        _record(), _record(),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES[:500])
    assert "spike containment" in report["failed"]
    assert report["verdict"] == "NOT REGENERATED"


def test_containment_gates_the_reverse_direction_too():
    """Forward containment alone passes a re-run that found every recorded spike
    AND a pile of spurious extras. The reverse direction is what catches it."""
    extras = [500.0 + i / 100.0 for i in range(1000)]
    report = runs.compare_runs(
        _record(), _record(),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES + extras)
    contain = next(c for c in report["criteria"] if c["name"] == "spike containment")
    assert report["containment"]["forward"] == 1.0          # forward would pass
    assert report["containment"]["reverse"] == 0.5
    assert contain["verdict"] == runs.V_OUTSIDE
    assert report["verdict"] == "NOT REGENERATED"


def test_two_runs_that_both_found_nothing_regenerate():
    """Two honest zero-unit sorts found exactly the same thing: nothing.
    Containment is undefined (NaN) on empty trains and NaN reads as outside
    tolerance, which used to score identical emptiness NOT REGENERATED."""
    report = runs.compare_runs(
        _record(n_units=0), _record(n_units=0),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=[], regenerated_spikes=[])
    contain = next(c for c in report["criteria"] if c["name"] == "spike containment")
    assert contain["verdict"] == runs.V_MATCH
    assert "found no spikes" in contain["note"]
    assert report["failed"] == []
    # ...and "BIT-IDENTICAL SPIKE TRAINS" is not a claim to make about no spikes.
    assert report["verdict"] == "REGENERATED"


def test_an_empty_regeneration_against_a_real_sort_still_fails():
    """Only BOTH sides empty is a match: a re-run that found nothing where the
    record has a thousand spikes is exactly the failure this criterion is for."""
    report = runs.compare_runs(
        _record(), _record(n_units=0),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=[])
    assert "spike containment" in report["failed"]
    assert report["verdict"] == "NOT REGENERATED"


def test_containment_at_the_calibrated_floor_passes():
    """0.85 is the measured floor; the worst honest pair observed was 0.903."""
    n = int(len(SPIKES) * 0.91)
    report = runs.compare_runs(
        _record(), _record(),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES[:n])
    assert report["containment"]["forward"] == pytest.approx(0.91, abs=0.005)
    assert report["verdict"].startswith("REGENERATED")


def test_missing_summaries_are_not_compared_rather_than_silently_passed():
    report = runs.compare_runs(_record(), _record(),
                               recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    v = _verdicts(report)
    assert v["noise floor (µV)"] == runs.V_SKIPPED
    assert v["V_pp median (µV)"] == runs.V_SKIPPED
    assert v["yield (%)"] == runs.V_SKIPPED
    assert report["failed"] == []


def test_an_unreadable_sorting_is_not_compared():
    report = runs.compare_runs(_record(), _record(),
                               recorded_summary=_summary(), regenerated_summary=_summary(),
                               recorded_spikes=None, regenerated_spikes=None)
    contain = next(c for c in report["criteria"] if c["name"] == "spike containment")
    assert contain["verdict"] == runs.V_SKIPPED
    assert report["verdict"] != "REGENERATED — BIT-IDENTICAL SPIKE TRAINS"


def test_bit_identity_is_only_claimed_when_it_is_observed():
    report = runs.compare_runs(
        _record(), _record(),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=[t + 0.0002 for t in SPIKES])
    # every spike matches within the window, but the trains are NOT identical
    assert report["containment"]["forward"] == 1.0
    assert report["verdict"] == "REGENERATED"       # not "BIT-IDENTICAL"


def test_the_stated_tolerances_are_the_module_constants():
    report = runs.compare_runs(_record(), _record(),
                               recorded_summary=_summary(), regenerated_summary=_summary(),
                               recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    tol = {c["name"]: c["tolerance"] for c in report["criteria"]}
    assert f"{runs.NOISE_TOL_UV:g}" in tol["noise floor (µV)"]
    assert f"{runs.CONTAINMENT_MIN:.0%}" in tol["spike containment"]
    assert f"{runs.METRIC_REL_TOL:.0%}" in tol["V_pp median (µV)"]
    assert f"{runs.YIELD_TOL_PP:g}" in tol["yield (%)"]


def test_format_match_report_prints_every_criterion_and_the_verdict():
    report = runs.compare_runs(
        _record(), _record(),
        recorded_summary=_summary(), regenerated_summary=_summary(),
        recorded_spikes=SPIKES, regenerated_spikes=SPIKES)
    text = runs.format_match_report(report, recorded_dir="/a", regenerated_dir="/b")
    for c in report["criteria"]:
        assert c["name"] in text
    assert "VERDICT: " in text
    # A measured-stochastic sorter must say so in the report, not only the record.
    assert "measured NON-DETERMINISTIC" in text


def test_format_match_report_names_an_unmeasured_sorter_as_unverified():
    report = runs.compare_runs(_record(sorter="simple", determinism=None),
                               _record(sorter="simple", determinism=None))
    assert "determinism: unverified" in runs.format_match_report(report)


# --------------------------------------------------------------------------- #
# Config as code
# --------------------------------------------------------------------------- #
def test_config_from_record_is_the_committable_subset():
    info = _record(params={"effective": {"detect_threshold": 5.0}, "defaults": {},
                           "overrides": {}},
                   duration_arg=None, n_jobs=1,
                   recording={"data_dir": None, "base": "PFCM7_d0ephys_Block2"})
    config = runs.config_from_record(info)
    assert config["kind"] == "spikeinterface-workbench-sort-config"
    assert config["from_run"] == "20260818-000001-aaaaaa"
    assert config["sorter"] == "tridesclous2"
    assert config["probe"] == "nnx-a1x16-3mm-100"
    assert config["params"] == {"detect_threshold": 5.0}
    assert config["freq_min"] == 300.0 and config["freq_max"] == 6000.0
    assert config["bad_channel_method"] == "mad" and config["bad_channels"] == []
    # It must be a FILE, so it must survive a JSON round trip unchanged.
    assert json.loads(json.dumps(config)) == config


def test_config_argv_pins_every_parameter_through_a_params_file(tmp_path):
    config = runs.config_from_record(
        _record(params={"effective": {"detect_threshold": 4.0}}, duration_arg=None))
    argv = runs.config_argv(config, tmp_path / "out", params_file=tmp_path / "p.json")
    assert argv[1].endswith("run_sorting.py")
    assert argv[argv.index("--sorter") + 1] == "tridesclous2"
    assert argv[argv.index("--output-dir") + 1] == str(tmp_path / "out")
    assert argv[argv.index("--probe") + 1] == "nnx-a1x16-3mm-100"
    assert argv[argv.index("--params-file") + 1] == str(tmp_path / "p.json")
    assert argv[argv.index("--freq-min") + 1] == "300"
    assert "--duration" not in argv                 # a full run
    assert "--keep-analog" not in argv


def test_config_argv_carries_the_smoke_window_and_the_channel_flags(tmp_path):
    config = runs.config_from_record(
        _record(duration_arg=30.0, keep_analog=True, n_jobs=4,
                bad_channels={"excluded": ["3"], "manual": ["3", "7"], "method": "mad",
                              "enabled": False}))
    argv = runs.config_argv(config, tmp_path / "out")
    assert argv[argv.index("--duration") + 1] == "30.0"
    assert "--keep-analog" in argv
    assert argv[argv.index("--n-jobs") + 1] == "4"
    assert argv[argv.index("--bad-channels") + 1] == "3,7"
    assert "--no-bad-channel-detection" in argv


def test_the_config_carries_the_docker_fact(tmp_path):
    """A containerized run regenerated without --docker never starts: run_sorting
    resolves the sorter natively and exits with "re-run with --docker". The lab's
    Windows box is where those runs live, so the config has to say so."""
    config = runs.config_from_record(_record(docker=True))
    assert config["docker"] is True
    assert "--docker" in runs.config_argv(config, tmp_path / "out")


def test_a_natively_run_sort_does_not_ask_for_docker(tmp_path):
    config = runs.config_from_record(_record(docker=False))
    assert config["docker"] is False
    assert "--docker" not in runs.config_argv(config, tmp_path / "out")


def test_config_argv_omits_a_params_file_it_was_not_given(tmp_path):
    argv = runs.config_argv(runs.config_from_record(_record()), tmp_path / "out")
    assert "--params-file" not in argv


def test_an_effective_param_dict_survives_run_sortings_own_validation(tmp_path,
                                                                     monkeypatch):
    """The config pins EVERY parameter, so run_sorting must accept the whole
    effective dict — an unknown key has to fail loudly, not ride along."""
    import sorters

    monkeypatch.setattr(sorters, "default_params",
                        lambda name: {"detect_threshold": 5.0, "seed": None})
    pf = tmp_path / "params.json"
    pf.write_text(json.dumps({"detect_threshold": 5.0, "seed": None}), encoding="utf-8")
    assert rs.resolve_overrides("tdc2", [], str(pf)) == {"detect_threshold": 5.0,
                                                         "seed": None}
    pf.write_text(json.dumps({"detect_threshold": 5.0, "not_a_param": 1}),
                  encoding="utf-8")
    with pytest.raises(SystemExit):
        rs.resolve_overrides("tdc2", [], str(pf))
