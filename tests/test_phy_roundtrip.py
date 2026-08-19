"""Tests for the Phy round trip: export → a curator's verdicts → back in the record.

The import half is pure Python (csv + json), so all of it runs on a fake Phy
folder in a tmp dir - no SpikeInterface, no recording. What the real export
writes is fixed by SI's exporter and verified structurally on the real sort; what
these pin is the part this repo owns: which file is the verdict, how Phy's
cluster_id maps back to a unit id, the refusals that stop verdicts landing on the
wrong units, and the collision rule.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import curation  # noqa: E402

SORTER = "fakesorter"
RUN_ID = "20260818-100000-a1b2c3"
UNITS = [0, 2, 5, 7]
RUN_INFO = {
    "created": "2026-08-18T10:00:00", "command": "run_sorting.py", "sorter": SORTER,
    "n_units": len(UNITS), "si_version": "0.104.3", "probe": "nnx-a1x16-3mm-100",
    "effective_seconds": 5.0, "total_seconds": 5.0,
}


def _write_tsv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(header)
        w.writerows(rows)


def _sort_on_disk(tmp_path, labels=None, run=RUN_ID):
    """A saved sort + its record, as curation.py's own CLI would leave them.

    In the RUN STORE by default - a run directory under ``outputs/<sorter>/runs/``
    with the record and (where a test builds one) the curated result inside it,
    which is what a post-W2 sort produces. ``run=None`` writes the pre-store
    layout instead, for the tests that claim to exercise that.
    """
    paths = curation.sort_paths(SORTER, tmp_path, run=run)
    paths["out"].mkdir(parents=True, exist_ok=True)
    if run is None:
        # What makes the pre-store layout resolvable at all is a sort sitting
        # directly in the sorter directory.
        paths["analyzer"].mkdir(parents=True, exist_ok=True)
    paths["run_info"].write_text(
        json.dumps(RUN_INFO if run is None else {**RUN_INFO, "run_id": run}),
        encoding="utf-8")
    record = curation.new_record(SORTER, list(UNITS), root=tmp_path)
    for unit, label in (labels or {}).items():
        curation.add_label(record, unit, label)
    curation.save_record(record, paths["record"])
    return paths


def _phy_folder(tmp_path, groups=None, qualities=None, manifest=None, folder=None):
    """A Phy folder shaped exactly like the one SI's exporter writes.

    cluster_id is a 0-based INDEX; cluster_si_unit_ids.tsv carries the real ids.
    """
    d = Path(folder) if folder else curation.sort_paths(SORTER, tmp_path)["phy"]
    d.mkdir(parents=True, exist_ok=True)
    _write_tsv(d / "cluster_si_unit_ids.tsv", ("cluster_id", "si_unit_id"),
               [(i, u) for i, u in enumerate(UNITS)])
    _write_tsv(d / "cluster_group.tsv", ("cluster_id", "group"),
               [(i, (groups or {}).get(i, "unsorted")) for i in range(len(UNITS))])
    _write_tsv(d / f"cluster_{curation.QUALITY_KEY}.tsv",
               ("cluster_id", curation.QUALITY_KEY),
               [(i, (qualities or {}).get(i, "")) for i in range(len(UNITS))])
    base = {"kind": curation.PHY_MANIFEST_KIND, "schema_version": "1",
            "exported": "2026-08-18T11:00:00", "sorter": SORTER, "curated": False,
            "n_units": len(UNITS), "run": curation._run_identity(RUN_INFO)}
    base.update(manifest or {})
    (d / curation.PHY_MANIFEST_NAME).write_text(json.dumps(base), encoding="utf-8")
    return d


# --------------------------------------------------------------------------- #
# The verdict: which file says what, and what "no verdict" means
# --------------------------------------------------------------------------- #
def test_group_is_the_verdict_and_quality_only_fills_the_gaps(tmp_path):
    d = _phy_folder(tmp_path,
                    groups={0: "good", 1: "mua", 2: "noise"},
                    # cluster 0's quality is the STALE exported value; the curator
                    # changed the group to good. Group must win.
                    qualities={0: "noise", 3: "unsure"})
    verdicts, rejected = curation.phy_verdicts(d)
    assert verdicts[str(0)] == ("good", curation.PHY_GROUP_FILE)
    assert verdicts[str(1)] == ("MUA", curation.PHY_GROUP_FILE)
    assert verdicts[str(2)] == ("noise", curation.PHY_GROUP_FILE)
    # Only where group says nothing does the workbench's own column speak.
    assert verdicts[str(3)] == ("unsure", curation.PHY_QUALITY_FILE)
    assert rejected == []


def test_unsorted_is_not_a_decision(tmp_path):
    verdicts, rejected = curation.phy_verdicts(_phy_folder(tmp_path))
    assert verdicts == {} and rejected == []


def test_values_outside_the_vocabulary_are_reported_not_dropped(tmp_path):
    d = _phy_folder(tmp_path, groups={0: "maybe"}, qualities={1: "dubious"})
    verdicts, rejected = curation.phy_verdicts(d)
    assert verdicts == {}
    assert len(rejected) == 2
    assert "maybe" in rejected[0] and "dubious" in rejected[1]


# --------------------------------------------------------------------------- #
# The import: cluster ids map back, and every write goes through the record owner
# --------------------------------------------------------------------------- #
def test_import_maps_phy_cluster_ids_back_to_unit_ids(tmp_path):
    _sort_on_disk(tmp_path)
    _phy_folder(tmp_path, groups={1: "good", 3: "noise"})
    result = curation.import_phy_labels(SORTER, root=tmp_path)

    # cluster 1 is unit 2 and cluster 3 is unit 7 - NOT units 1 and 3.
    assert [(e["unit"], e["label"]) for e in result["imported"]] == [(2, "good"),
                                                                    (7, "noise")]
    record = curation.load_record(SORTER, tmp_path)
    assert curation.label_of(record, 2) == "good"
    assert curation.label_of(record, 7) == "noise"
    assert curation.counts(record)["labels"] == 2


def test_the_round_trip_lands_inside_the_run_it_curates(tmp_path):
    """Post-W2 the export, the record and the curated result all live in the run
    directory, not beside the sorter - so a later sort in its own run directory
    cannot leave any of them attached to a sort they do not describe."""
    paths = _sort_on_disk(tmp_path)
    run = tmp_path / "outputs" / SORTER / "runs" / RUN_ID
    assert paths["out"] == run
    assert paths["record"] == run / "curation.json"
    assert paths["phy"] == run / "phy"
    assert paths["curated_phy"] == run / "curated" / "phy"
    # ...and resolving by name (what every surface does) finds the same run.
    assert curation.sort_paths(SORTER, tmp_path)["record"] == run / "curation.json"


def test_the_round_trip_still_works_on_a_pre_store_sort(tmp_path):
    """A curated sort made before the run store keeps working, read-only: the
    store resolves outputs/<sorter>/ when no run directory exists, so the record
    and the Phy folder are found exactly where that sort left them."""
    paths = _sort_on_disk(tmp_path, run=None)
    legacy = tmp_path / "outputs" / SORTER
    assert paths["out"] == legacy
    assert paths["phy"] == legacy / "phy"

    _phy_folder(tmp_path, groups={1: "good"})
    result = curation.import_phy_labels(SORTER, root=tmp_path)
    assert [(e["unit"], e["label"]) for e in result["imported"]] == [(2, "good")]
    assert curation.label_of(curation.load_record(SORTER, tmp_path), 2) == "good"


def test_imported_decisions_carry_phy_provenance(tmp_path):
    _sort_on_disk(tmp_path)
    _phy_folder(tmp_path, groups={0: "good"})
    curation.import_phy_labels(SORTER, root=tmp_path)

    record = curation.load_record(SORTER, tmp_path)
    (decision,) = record["decisions"]
    assert decision["method"] == "phy"
    assert decision["params"] == {"label": "good", "cluster_id": "0",
                                  "source_file": curation.PHY_GROUP_FILE}
    assert curation.label_method_of(record, 0) == "phy"
    assert curation.structural_errors(record) == []


def test_a_matching_verdict_writes_nothing(tmp_path):
    _sort_on_disk(tmp_path, labels={0: "good"})
    _phy_folder(tmp_path, groups={0: "good"})
    result = curation.import_phy_labels(SORTER, root=tmp_path)

    assert result["imported"] == [] and result["saved"] is False
    assert result["unchanged"] == [{"unit": 0, "label": "good"}]
    # Re-importing the same folder must not grow the decision log.
    assert len(curation.load_record(SORTER, tmp_path)["decisions"]) == 1


def test_a_hand_written_label_is_never_overwritten_silently(tmp_path):
    _sort_on_disk(tmp_path, labels={0: "noise"})
    _phy_folder(tmp_path, groups={0: "good"})
    result = curation.import_phy_labels(SORTER, root=tmp_path)

    # Newest wins...
    record = curation.load_record(SORTER, tmp_path)
    assert curation.label_of(record, 0) == "good"
    # ...and the caller is told, by unit, what it replaced.
    (override,) = result["overridden"]
    assert override["previous"] == "noise" and override["previous_method"] == "manual"
    # ...and the record keeps the replaced verdict in the audit trail.
    assert record["decisions"][-1]["detail"] == {"replaced": "noise",
                                                 "replaced_method": "manual"}
    assert record["decisions"][0]["params"]["label"] == "noise"


def test_clusters_phy_created_are_skipped_and_named(tmp_path):
    _sort_on_disk(tmp_path)
    d = _phy_folder(tmp_path, groups={0: "good"})
    # A merge in Phy's UI appends a cluster id this sort never had.
    with open(d / "cluster_group.tsv", "a", newline="", encoding="utf-8") as fh:
        csv.writer(fh, delimiter="\t").writerow([99, "good"])
    result = curation.import_phy_labels(SORTER, root=tmp_path)

    assert len(result["imported"]) == 1
    assert result["skipped"] == ["cluster 99 (good) is not a unit of this sort"]


def test_dry_run_reports_without_writing(tmp_path):
    paths = _sort_on_disk(tmp_path)
    before = paths["record"].read_text(encoding="utf-8")
    _phy_folder(tmp_path, groups={0: "good"})
    result = curation.import_phy_labels(SORTER, root=tmp_path, dry_run=True)

    assert len(result["imported"]) == 1 and result["saved"] is False
    assert paths["record"].read_text(encoding="utf-8") == before


def test_import_is_pure_python(tmp_path):
    """The record's read/write path never pays for SpikeInterface - the view
    process and the coming TUI triage slice depend on that."""
    _sort_on_disk(tmp_path)
    _phy_folder(tmp_path, groups={0: "good"})
    loaded = set(sys.modules)
    curation.import_phy_labels(SORTER, root=tmp_path)
    assert not [m for m in set(sys.modules) - loaded if m.startswith("spikeinterface")]


# --------------------------------------------------------------------------- #
# The refusals: a verdict must never land on the wrong units
# --------------------------------------------------------------------------- #
def test_import_refuses_a_folder_from_a_different_sort(tmp_path):
    paths = _sort_on_disk(tmp_path)
    _phy_folder(tmp_path, groups={0: "good"})
    # The sort was re-run underneath the export: same sorter, new units.
    paths["run_info"].write_text(
        json.dumps({**RUN_INFO, "created": "2026-08-18T20:00:00", "n_units": 6}),
        encoding="utf-8")

    with pytest.raises(RuntimeError) as e:
        curation.import_phy_labels(SORTER, root=tmp_path)
    assert "different fakesorter sort" in str(e.value)
    assert "sorted at" in str(e.value) and "units" in str(e.value)
    assert "Next step" in str(e.value)          # the refusal names what to do


def test_import_refuses_a_curated_export(tmp_path):
    _sort_on_disk(tmp_path)
    d = _phy_folder(tmp_path, groups={0: "good"}, manifest={"curated": True},
                    folder=curation.sort_paths(SORTER, tmp_path)["curated_phy"])

    with pytest.raises(RuntimeError) as e:
        curation.import_phy_labels(SORTER, folder=d, root=tmp_path)
    # The curated ids are not the record's ids - say so, and name the way round it.
    assert "CURATED" in str(e.value) and "--raw" in str(e.value)


def test_import_refuses_a_folder_with_no_manifest(tmp_path):
    _sort_on_disk(tmp_path)
    d = _phy_folder(tmp_path, groups={0: "good"})
    (d / curation.PHY_MANIFEST_NAME).unlink()

    with pytest.raises(RuntimeError) as e:
        curation.import_phy_labels(SORTER, root=tmp_path)
    assert curation.PHY_MANIFEST_NAME in str(e.value)


def test_import_refuses_another_sorters_export(tmp_path):
    _sort_on_disk(tmp_path)
    _phy_folder(tmp_path, groups={0: "good"}, manifest={"sorter": "othersorter"})

    with pytest.raises(RuntimeError) as e:
        curation.import_phy_labels(SORTER, root=tmp_path)
    assert "othersorter" in str(e.value)


def test_import_refuses_when_the_cluster_id_map_is_missing(tmp_path):
    _sort_on_disk(tmp_path)
    d = _phy_folder(tmp_path, groups={0: "good"})
    (d / curation.PHY_UNIT_ID_FILE).unlink()

    with pytest.raises(RuntimeError) as e:
        curation.import_phy_labels(SORTER, root=tmp_path)
    assert curation.PHY_UNIT_ID_FILE in str(e.value)


def test_import_refuses_when_there_is_no_folder(tmp_path):
    _sort_on_disk(tmp_path)
    with pytest.raises(RuntimeError) as e:
        curation.import_phy_labels(SORTER, root=tmp_path)
    assert "export-phy" in str(e.value)


# --------------------------------------------------------------------------- #
# The export's label seeding (the folder-writing half that needs no analyzer)
# --------------------------------------------------------------------------- #
def test_seeding_maps_labels_onto_phy_cluster_ids(tmp_path):
    d = _phy_folder(tmp_path)
    # Unit 5 is cluster 2, unit 7 is cluster 3 - the index, not the id.
    n = curation._seed_phy_labels(d, {5: "noise", 7: "unsure"})

    assert n == 2
    groups = dict(curation._read_tsv(d / curation.PHY_GROUP_FILE))
    assert groups == {"0": "unsorted", "1": "unsorted", "2": "noise",
                      # "unsure" has no Phy group - it travels in cluster_quality.tsv
                      "3": "unsorted"}
    quality = dict(curation._read_tsv(d / curation.PHY_QUALITY_FILE))
    assert quality["2"] == "noise" and quality["3"] == "unsure"


def test_a_seeded_export_round_trips_unchanged(tmp_path):
    """Export → import with nobody touching Phy must be a no-op, "unsure" included."""
    _sort_on_disk(tmp_path, labels={2: "unsure", 5: "MUA"})
    d = _phy_folder(tmp_path)
    record = curation.load_record(SORTER, tmp_path)
    curation._seed_phy_labels(d, {m["unit_id"]: m["labels"]["quality"][0]
                                  for m in record["curation"]["manual_labels"]})
    result = curation.import_phy_labels(SORTER, root=tmp_path)

    assert result["imported"] == [] and result["rejected"] == []
    assert {e["unit"]: e["label"] for e in result["unchanged"]} == {2: "unsure",
                                                                   5: "MUA"}


# --------------------------------------------------------------------------- #
# The menu wiring: one MANAGE row on its letter key
# --------------------------------------------------------------------------- #
async def test_phy_runs_from_its_manage_letter(make_app):
    """``y`` dispatches the export through the controller, like the other MANAGE
    letters - under the headless driver suspend() is unsupported, so this also
    pins that the fallback in-place run does not crash the app."""
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert ("phy", None) in app.c.ran
        assert app.is_running


async def test_phy_is_blocked_without_the_recording(make_app):
    """The export copies the preprocessed traces Phy needs, so it needs the data -
    with none present it must guide rather than dispatch."""
    app = make_app(present=False)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert ("phy", None) not in app.c.ran


# --------------------------------------------------------------------------- #
# The rmtree guard: an export target must never eat anything but an old export
# --------------------------------------------------------------------------- #
def test_export_out_dir_refuses_the_sort_itself(tmp_path):
    paths = _sort_on_disk(tmp_path)
    for key in ("out", "sorting", "analyzer", "curated", "curated_analyzer"):
        with pytest.raises(RuntimeError, match="audit trail"):
            curation._check_phy_out_dir(paths[key], paths, SORTER)


def test_export_out_dir_refuses_any_ancestor_of_the_sort(tmp_path):
    paths = _sort_on_disk(tmp_path)
    # Clearing outputs/ (or the root above it) would delete every sort.
    with pytest.raises(RuntimeError, match="audit trail"):
        curation._check_phy_out_dir(paths["out"].parent, paths, SORTER)
    with pytest.raises(RuntimeError, match="audit trail"):
        curation._check_phy_out_dir(tmp_path, paths, SORTER)


def test_export_out_dir_refuses_a_nonempty_stranger(tmp_path):
    paths = _sort_on_disk(tmp_path)
    stranger = tmp_path / "thesis_chapter"
    stranger.mkdir()
    (stranger / "draft.txt").write_text("irreplaceable", encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not look"):
        curation._check_phy_out_dir(stranger, paths, SORTER)
    # ...but a previous export, an empty dir, or a fresh path are all fine.
    old_export = tmp_path / "old_export"
    old_export.mkdir()
    (old_export / "params.py").write_text("", encoding="utf-8")
    curation._check_phy_out_dir(old_export, paths, SORTER)
    empty = tmp_path / "empty"
    empty.mkdir()
    curation._check_phy_out_dir(empty, paths, SORTER)
    curation._check_phy_out_dir(tmp_path / "not_yet", paths, SORTER)


# --------------------------------------------------------------------------- #
# Blank anchors refuse on BOTH sides of the trip (a blank compares as
# "matches everything" - the exact failure the anchor exists to prevent)
# --------------------------------------------------------------------------- #
def test_import_refuses_a_blank_anchored_manifest(tmp_path):
    _sort_on_disk(tmp_path)
    _phy_folder(tmp_path, groups={0: "good"}, manifest={"run": {}})
    with pytest.raises(RuntimeError, match="no usable run anchor"):
        curation.import_phy_labels(SORTER, root=tmp_path)


def test_export_refuses_a_sort_with_no_run_anchor(tmp_path):
    # The pre-store layout: a sort resolves on its analyzer alone, so it can be
    # found with no run_info.json at all. (In the store a run without a record is
    # an unfinished run and does not resolve, so there is nothing to export.)
    paths = _sort_on_disk(tmp_path, run=None)
    paths["run_info"].unlink()  # the export would carry a blank anchor
    with pytest.raises(RuntimeError, match="cannot identify the saved"):
        curation.export_phy(SORTER, tmp_path, verbose=False)


# --------------------------------------------------------------------------- #
# A stale curated result must not travel with a fresh sort's anchor
# --------------------------------------------------------------------------- #
def test_export_refuses_a_stale_curated_result(tmp_path):
    paths = _sort_on_disk(tmp_path, labels={0: "good"})
    paths["curated_analyzer"].mkdir(parents=True)
    record = curation.load_record(SORTER, tmp_path)
    curated_run = {
        "curation_updated": record["updated"],
        # anchored to a DIFFERENT raw run than the one now on disk
        "curated_from_run": curation._run_identity(
            {**RUN_INFO, "created": "2026-08-17T09:00:00", "n_units": 9}),
    }
    paths["curated_run_info"].write_text(json.dumps(curated_run),
                                         encoding="utf-8")
    with pytest.raises(RuntimeError, match="no longer describes"):
        curation.export_phy(SORTER, tmp_path, verbose=False)
    # --raw is the stated escape: it must not hit the staleness wall (it fails
    # later, honestly, on the fake analyzer being unloadable).
    with pytest.raises(Exception) as err:
        curation.export_phy(SORTER, tmp_path, raw=True, verbose=False)
    assert "no longer describes" not in str(err.value)
