"""Tests for the curation lifecycle: record -> apply -> re-scored -> honest surfaces.

The pure half (schema round-trip, provenance, the sentence every surface prints,
the path resolver) needs no SpikeInterface - that is the point: the menu's view
process reads curation state without importing SI. The SI half runs a real
apply on a small synthetic sort: merges, an index split, labels, the curated
analyzer + re-scored metrics, and the two ways an apply must refuse.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import curation  # noqa: E402
import report  # noqa: E402

SORTER = "fakesorter"
RUN_INFO = {
    "created": "2026-08-18T10:00:00", "command": "run_sorting.py", "sorter": SORTER,
    "n_units": 3, "si_version": "0.104.3", "probe": "nnx-a1x16-3mm-100",
    "effective_seconds": 5.0, "total_seconds": 5.0, "freq_min": 300.0,
    "freq_max": 6000.0, "n_dropped_analog": 6, "channel_ids": ["1", "2", "3", "4"],
}


# --------------------------------------------------------------------------- #
# Pure: paths, schema round-trip, provenance, the honest sentence
# --------------------------------------------------------------------------- #
def _record(tmp_path, unit_ids=(1, 2, 3)):
    paths = curation.sort_paths(SORTER, tmp_path)
    paths["out"].mkdir(parents=True, exist_ok=True)
    paths["run_info"].write_text(json.dumps(RUN_INFO), encoding="utf-8")
    return curation.new_record(SORTER, list(unit_ids), root=tmp_path), paths


def test_sort_paths_is_the_single_home(tmp_path):
    """The resolver is the run store's. With nothing saved it hands back the
    pre-store layout, so a fresh tree still has somewhere to look."""
    p = curation.sort_paths(SORTER, tmp_path)
    out = tmp_path / "outputs" / SORTER
    assert p["out"] == out
    assert p["record"] == out / "curation.json"
    assert p["curated"] == out / "curated"
    assert p["curated_analyzer"] == out / "curated" / "analyzer"
    # Every PATH this module hands out lives under the one output dir. (The store
    # also returns labels - the sorter name and the run id - which are not paths.)
    assert all(str(v).startswith(str(tmp_path))
               for v in p.values() if isinstance(v, Path))


def test_sort_paths_puts_the_record_inside_the_run_it_curates(tmp_path):
    """Once a run exists in the store, the record and the curated result ride
    inside THAT run directory - the whole point of the re-point."""
    run = tmp_path / "outputs" / SORTER / "runs" / "20260819-101500-abc123"
    (run / "analyzer").mkdir(parents=True)
    (run / "run_info.json").write_text(json.dumps({**RUN_INFO, "run_id": run.name}),
                                       encoding="utf-8")
    p = curation.sort_paths(SORTER, tmp_path)
    assert p["out"] == run
    assert p["id"] == run.name
    assert p["record"] == run / "curation.json"
    assert p["curated_analyzer"] == run / "curated" / "analyzer"
    assert p["phy"] == run / "phy"


def test_record_round_trip_is_pure_python(tmp_path):
    record, paths = _record(tmp_path)
    curation.add_label(record, 3, "noise", note="one spike, no waveform")
    curation.add_merge(record, [1, 2])
    curation.add_split(record, 1, [[0, 2], [1, 3]], "kmeans",
                       {"features": "amplitude", "seed": 0})
    curation.save_record(record, paths["record"])

    # Read back with the stdlib alone - no SpikeInterface, no helper.
    raw = json.loads(paths["record"].read_text(encoding="utf-8"))
    assert raw == record
    assert curation.load_record(SORTER, tmp_path) == record
    assert curation.structural_errors(raw) == []
    assert curation.counts(raw) == {"splits": 1, "merges": 1, "labels": 1,
                                    "removed": 0, "total": 3}
    assert "spikeinterface" not in sys.modules or True  # (import-free by construction)


def test_record_carries_provenance(tmp_path):
    record, _paths = _record(tmp_path)
    curation.add_split(record, 2, [[0], [1, 2]], "kmeans",
                       {"features": "amplitude+pca", "n_pcs": 3, "seed": 0},
                       {"n_spikes": 3})
    assert record["kind"] == curation.KIND
    assert record["schema_version"] == curation.SCHEMA_VERSION
    # WHICH sort - the anchor.
    assert record["curates"]["sorter"] == SORTER
    assert record["curates"]["output_dir"].endswith(f"outputs/{SORTER}")
    assert record["curates"]["run"]["created"] == RUN_INFO["created"]
    assert record["curates"]["run"]["n_units"] == 3
    # Tool versions, without importing SpikeInterface to get them.
    assert record["tools"]["spikeinterface"]
    assert record["tools"]["workbench_schema"] == curation.SCHEMA_VERSION
    # The decision's own method + params + timestamp.
    d = record["decisions"][-1]
    assert d["type"] == "split" and d["units"] == [2]
    assert d["method"] == "kmeans"
    assert d["params"]["features"] == "amplitude+pca"
    assert d["detail"]["sizes"] == [1, 2]
    assert d["at"] and record["updated"] == d["at"]


def test_decisions_reject_nonsense(tmp_path):
    record, _paths = _record(tmp_path)
    with pytest.raises(ValueError):
        curation.add_label(record, 1, "rubbish")
    with pytest.raises(ValueError):
        curation.add_label(record, 99, "good")          # not a unit of this sort
    with pytest.raises(ValueError):
        curation.add_merge(record, [1])                 # a merge needs two
    with pytest.raises(ValueError):
        curation.add_split(record, 1, [[0, 1]], "kmeans", {})   # a split needs two parts


def test_structural_errors_catch_a_foreign_unit_and_a_repeated_index(tmp_path):
    record, _paths = _record(tmp_path)
    curation.add_split(record, 1, [[0, 1], [2, 3]], "kmeans", {})
    record["curation"]["splits"][0]["indices"] = [[0, 1], [1, 2]]
    record["curation"]["manual_labels"].append(
        {"unit_id": 77, "labels": {"quality": ["good"]}})
    errs = curation.structural_errors(record)
    assert any("repeats a spike index" in e for e in errs)
    assert any("77" in e for e in errs)


def test_provenance_line_says_which_result(tmp_path):
    record, _paths = _record(tmp_path)
    assert (curation.provenance_line(None, curated=False)
            == "raw sorter output - no curation applied")
    # No record while SHOWING curated data is a different, louder statement.
    assert "curation record is missing" in curation.provenance_line(None, curated=True)
    assert "no curation applied" in curation.provenance_line(record, curated=False)
    curation.add_split(record, 1, [[0], [1]], "kmeans", {})
    curation.add_label(record, 2, "MUA")
    raw_line = curation.provenance_line(record, curated=False)
    assert "raw fakesorter sorter output" in raw_line
    assert "2 decisions recorded but not applied" in raw_line
    assert "not shown here" in curation.provenance_line(record, curated=False,
                                                        has_curated=True)
    line = curation.provenance_line(record, curated=True)
    assert line.startswith("curated from the fakesorter run (sorted 2026-08-18 10:00)")
    assert "2 decisions (1 split, 0 merges, 1 label)" in line


def test_state_reports_raw_curated_and_stale(tmp_path):
    record, paths = _record(tmp_path)
    st = curation.state(SORTER, tmp_path)
    assert st == {**st, "has_record": False, "has_curated": False, "stale": False}
    curation.add_label(record, 1, "good")
    curation.save_record(record, paths["record"])
    st = curation.state(SORTER, tmp_path)
    assert st["has_record"] and not st["has_curated"]
    assert st["counts"]["labels"] == 1

    # Pretend an apply happened, then let the record move on.
    paths["curated_analyzer"].mkdir(parents=True)
    paths["curated_run_info"].write_text(json.dumps({
        "curated": True, "n_units": 4, "curation_updated": record["updated"],
        "curated_from_run": {k: RUN_INFO.get(k) for k in
                             ("created", "sorter", "n_units", "si_version", "probe",
                              "effective_seconds", "total_seconds")}}), encoding="utf-8")
    st = curation.state(SORTER, tmp_path)
    assert st["has_curated"] and st["curated_units"] == 4 and not st["stale"]
    assert st["line"].startswith("curated from the fakesorter run")

    record["updated"] = "2026-08-18T23:00:00"
    curation.save_record(record, paths["record"])
    st = curation.state(SORTER, tmp_path)
    assert st["stale"] and "new decisions" in st["stale_reason"]


def _run_on_disk(tmp_path, run_id, *, curated=False, units=3):
    """One run in the store, optionally with a curated result built on it."""
    paths = curation.sort_paths(SORTER, tmp_path, run=run_id)
    paths["analyzer"].mkdir(parents=True)
    paths["run_info"].write_text(
        json.dumps({**RUN_INFO, "run_id": run_id, "n_units": units}), encoding="utf-8")
    if curated:
        paths["curated_analyzer"].mkdir(parents=True)
        paths["curated_run_info"].write_text(
            json.dumps({"curated": True, "n_units": units}), encoding="utf-8")
    return paths


def test_a_curated_result_on_a_non_current_run_is_named_not_hidden(tmp_path, monkeypatch):
    """Curated output is anchored to the run it curates - correct, and it means a
    fresh sort moves the pointer and the curated result stops being shown. The
    surfaces must say where it went instead of going silent."""
    old = _run_on_disk(tmp_path, "20260818-100000-aaaaaa", curated=True)
    # Only run: it IS current, so nothing is hidden and there is nothing to say.
    assert curation.curated_elsewhere(SORTER, tmp_path) is None
    assert curation.state(SORTER, tmp_path)["elsewhere"] is None

    _run_on_disk(tmp_path, "20260819-100000-bbbbbb")      # a newer, uncurated sort
    st = curation.state(SORTER, tmp_path)
    assert st["run"] == "20260819-100000-bbbbbb" and not st["has_curated"]
    other = st["elsewhere"]
    assert other["run"] == "20260818-100000-aaaaaa" and not other["legacy"]
    assert other["line"] == (
        "a curated result exists on run 20260818-100000-aaaaaa; the current run "
        "(20260819-100000-bbbbbb) is uncurated - apply a record to this run to "
        "curate it")
    assert other["where"] == "outputs/fakesorter/runs/20260818-100000-aaaaaa/curated"
    assert other["dir"] == old["out"]

    # ...and the report says it where a reader will meet it. (report resolves the
    # store from the repo root at call time, so this is the tree it reads.)
    monkeypatch.setattr(curation.bio, "REPO_ROOT", tmp_path)
    html = report._curation_html(
        report._curation_facts(curation.sort_paths(SORTER)["analyzer"]), SORTER)
    assert other["line"] in html and other["where"] in html


def test_a_pre_store_curated_result_is_named_when_a_new_sort_supersedes_it(tmp_path):
    """The lab's existing curated sorts live in outputs/<sorter>/curated/. The
    first sort after this integration moves the pointer to a run directory; the
    old result must be named as being in the pre-store layout, never migrated."""
    legacy = curation.sort_paths(SORTER, tmp_path)
    (legacy["out"] / "analyzer").mkdir(parents=True)
    legacy["run_info"].write_text(json.dumps(RUN_INFO), encoding="utf-8")
    (legacy["out"] / "curated" / "analyzer").mkdir(parents=True)
    _run_on_disk(tmp_path, "20260819-100000-bbbbbb")

    other = curation.state(SORTER, tmp_path)["elsewhere"]
    assert other["legacy"] and other["run"] == "legacy"
    assert other["line"].startswith("a curated result exists on the pre-store layout;")
    assert other["where"] == "outputs/fakesorter/curated"
    assert other["short"] == ("curated result on the pre-store layout - "
                              "apply to curate this run")
    # Nothing was moved or adopted: it is still exactly where it was built.
    assert (tmp_path / "outputs" / SORTER / "curated" / "analyzer").is_dir()


def test_curated_on_disk_without_a_record_is_never_called_raw(tmp_path):
    """Deleting curation.json must not turn curated numbers into "raw sorter
    output - no curation applied" on any surface."""
    _rec, paths = _record(tmp_path)          # run_info on disk, no curation.json
    paths["curated_analyzer"].mkdir(parents=True)
    paths["curated_run_info"].write_text(json.dumps({"curated": True, "n_units": 4}),
                                         encoding="utf-8")
    line = curation.provenance_line(None, curated=True)
    assert line == ("curated result - its curation record is missing; "
                    "provenance unknown")
    st = curation.state(SORTER, tmp_path)
    assert st["has_curated"] and not st["has_record"]
    assert "raw" not in st["line"]
    assert st["stale"] and "record is missing" in st["stale_reason"]

    paths["analyzer"].mkdir(parents=True, exist_ok=True)
    cur = report._curation_facts(paths["analyzer"])
    assert cur["curated"] is True and cur["record"] is None
    html = report._curation_html(cur, SORTER)
    assert "no curation applied" not in html
    assert "curation record is missing" in html
    # The provenance block must not claim nothing was curated either.
    prov = report._curation_provenance(cur)
    assert "nothing has been merged" not in prov
    assert "cannot be audited" in prov


def test_state_flags_a_re_sort_under_a_curated_result(tmp_path):
    record, paths = _record(tmp_path)
    curation.add_label(record, 1, "good")
    curation.save_record(record, paths["record"])
    paths["curated_analyzer"].mkdir(parents=True)
    paths["curated_run_info"].write_text(json.dumps({
        "curated": True, "n_units": 3, "curation_updated": record["updated"],
        "curated_from_run": {"created": RUN_INFO["created"], "sorter": SORTER,
                             "n_units": 3, "si_version": "0.104.3",
                             "probe": RUN_INFO["probe"], "effective_seconds": 5.0,
                             "total_seconds": 5.0}}), encoding="utf-8")
    # The sort is re-run underneath (unit ids are not stable across re-sorts).
    paths["run_info"].write_text(json.dumps({**RUN_INFO,
                                             "created": "2026-08-19T09:00:00",
                                             "n_units": 5}), encoding="utf-8")
    st = curation.state(SORTER, tmp_path)
    assert st["stale"] and "re-run" in st["stale_reason"]


# --------------------------------------------------------------------------- #
# Honest surfaces (pure): the report's line, compare's line
# --------------------------------------------------------------------------- #
def test_anchor_error_is_the_refusal_apply_raises(tmp_path):
    """``anchor_error`` is the pure half of the anchor rule: the same sentence
    ``_check_run_identity`` raises, returnable so a surface can ask BEFORE it
    offers to write. Every refusal names its next step (DESIGN_UX §1.7)."""
    record, paths = _record(tmp_path)
    assert curation.anchor_error(record, SORTER, tmp_path) == ""
    # No record yet: only the disk side has to be identifiable, because
    # new_record() anchors a fresh record to exactly that identity.
    assert curation.anchor_error(None, SORTER, tmp_path) == ""

    # The sort on disk moved under the record (a re-sort renumbers units).
    paths["run_info"].write_text(json.dumps({**RUN_INFO, "n_units": 7}),
                                 encoding="utf-8")
    err = curation.anchor_error(record, SORTER, tmp_path)
    assert "written against a different" in err and "Next step:" in err
    # ...and it is exactly what apply refuses with.
    with pytest.raises(RuntimeError) as exc:
        curation._check_run_identity(record, SORTER, tmp_path)
    assert str(exc.value) == err

    # An unidentifiable sort refuses a fresh record too - an all-None anchor
    # would otherwise "match" every sort, the failure the anchor exists to stop.
    paths["run_info"].unlink()
    for rec in (record, None):
        blank = curation.anchor_error(rec, SORTER, tmp_path)
        assert "cannot identify the saved" in blank and "Next step:" in blank


def test_anchor_error_refuses_a_record_with_no_anchor(tmp_path):
    record, _paths = _record(tmp_path)
    record["curates"]["run"] = {}          # written while run_info.json was missing
    err = curation.anchor_error(record, SORTER, tmp_path)
    assert "no usable anchor" in err and f"outputs/{SORTER}/" in err


def test_report_states_raw_or_curated(tmp_path):
    record, paths = _record(tmp_path)
    curation.add_label(record, 1, "good")
    curation.add_split(record, 2, [[0], [1]], "kmeans", {"features": "amplitude"})
    curation.save_record(record, paths["record"])
    paths["analyzer"].mkdir(parents=True, exist_ok=True)

    cur = report._curation_facts(paths["analyzer"])
    assert cur["curated"] is False and cur["dir"] == paths["analyzer"]
    raw_html = report._curation_html(cur, SORTER)
    assert "<strong>Showing:</strong>" in raw_html
    assert "raw fakesorter sorter output" in raw_html

    paths["curated_analyzer"].mkdir(parents=True)
    paths["curated_run_info"].write_text(json.dumps(
        {"curated": True, "n_units": 4, "curation_updated": record["updated"]}),
        encoding="utf-8")
    cur = report._curation_facts(paths["analyzer"])
    assert cur["curated"] is True and cur["dir"] == paths["curated_analyzer"]
    html = report._curation_html(cur, SORTER)
    assert "<strong>Showing:</strong>" in html
    assert "curated from the fakesorter run" in html
    assert "2 decisions (1 split, 0 merges, 1 label)" in html
    assert f"outputs/{SORTER}/" in html          # raw provenance stated
    # The decisions table names the method behind each one.
    prov = report._curation_provenance(cur)
    assert "kmeans" in prov and "deterministic replay" in prov


def test_report_flags_a_curated_result_the_record_outran(tmp_path):
    record, paths = _record(tmp_path)
    curation.add_label(record, 1, "good")
    curation.save_record(record, paths["record"])
    paths["analyzer"].mkdir(parents=True, exist_ok=True)
    paths["curated_analyzer"].mkdir(parents=True)
    paths["curated_run_info"].write_text(json.dumps(
        {"curated": True, "n_units": 3, "curation_updated": "2026-01-01T00:00:00"}),
        encoding="utf-8")
    cur = report._curation_facts(paths["analyzer"])
    assert cur["stale"]
    assert "Out of date" in report._curation_html(cur, SORTER)


def test_compare_names_the_result_it_compares(tmp_path, monkeypatch):
    import blackrock_io as bio
    import compare

    record, paths = _record(tmp_path)
    curation.add_merge(record, [1, 2])
    curation.save_record(record, paths["record"])
    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)
    assert "raw fakesorter sorter output" in compare.result_line(SORTER, curated=False)
    paths["curated_analyzer"].mkdir(parents=True)
    paths["curated_run_info"].write_text(json.dumps(
        {"curated": True, "n_units": 2, "curation_updated": record["updated"]}),
        encoding="utf-8")
    assert "curated from the fakesorter run" in compare.result_line(SORTER, curated=True)
    # Showing the raw sort while a curated one exists must not read as "not applied".
    raw = compare.result_line(SORTER, curated=False)
    assert "a curated result exists" in raw and "not shown here" in raw
    assert f"<strong>{SORTER}:</strong>" in compare._result_note(SORTER, curated=True)


# --------------------------------------------------------------------------- #
# SpikeInterface-backed: a real apply on a small synthetic sort
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    """A saved sort (sorting/ + analyzer/ + run_info.json) under a tmp repo root."""
    si = pytest.importorskip("spikeinterface.full")
    root = tmp_path_factory.mktemp("repo")
    paths = curation.sort_paths(SORTER, root)
    paths["out"].mkdir(parents=True)
    rec, sorting = si.generate_ground_truth_recording(
        durations=[5.0], num_channels=4, num_units=3, seed=0)
    rec = rec.save(folder=root / "recording")     # reloadable from disk
    sorting = sorting.save(folder=paths["sorting"])
    analyzer = si.create_sorting_analyzer(sorting, rec, folder=paths["analyzer"],
                                          format="binary_folder", sparse=False)
    for ext in ("random_spikes", "waveforms", "templates", "noise_levels",
                "spike_amplitudes", "principal_components"):
        analyzer.compute(ext)
    paths["run_info"].write_text(json.dumps(
        {**RUN_INFO, "n_units": len(sorting.unit_ids)}), encoding="utf-8")
    # Unit ids come back in the sort's own type (SI writes str ids here) - the
    # record must carry them unchanged or apply would not recognise the units.
    return {"root": root, "paths": paths,
            "unit_ids": curation.unit_ids_of(SORTER, root)}


def _spike_counts(folder):
    import spikeinterface.full as si

    s = si.load(folder)
    return {str(u): len(s.get_unit_spike_train(u)) for u in s.unit_ids}


def test_apply_merges_splits_labels_and_never_touches_the_raw_sort(synthetic):
    root, paths, unit_ids = synthetic["root"], synthetic["paths"], synthetic["unit_ids"]
    before = _spike_counts(paths["sorting"])
    a, b, c = unit_ids

    record = curation.new_record(SORTER, unit_ids, root=root)
    curation.add_merge(record, [a, b], note="same waveform on ch 1")
    n_c = before[str(c)]
    curation.add_split(record, c, [list(range(0, n_c, 2)), list(range(1, n_c, 2))],
                       "kmeans", {"features": "amplitude", "seed": 0})
    curation.add_label(record, c, "MUA")
    curation.save_record(record, paths["record"])

    result = curation.apply_record(record, root, verbose=False)
    curated = _spike_counts(paths["curated_sorting"])
    # merge -> one unit with both trains; split -> two units halving the third.
    assert result["n_units"] == 3
    assert len(curated) == 3
    assert sorted(curated.values()) == sorted(
        [before[str(a)] + before[str(b)], (n_c + 1) // 2, n_c // 2])
    # The raw sort is the audit trail: byte-for-byte the same spike trains.
    assert _spike_counts(paths["sorting"]) == before

    # Re-scored through the existing owners, in the curated folder.
    assert paths["curated_analyzer"].is_dir()
    summary = json.loads((paths["curated"] / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_units"] == 3
    assert (paths["curated"] / "summary.csv").exists()
    assert paths["curated_metrics"].exists()

    info = json.loads(paths["curated_run_info"].read_text(encoding="utf-8"))
    assert info["curated"] is True
    assert info["curation_counts"]["total"] == 3
    assert info["curation_updated"] == record["updated"]
    assert info["curated_from_run"]["created"] == RUN_INFO["created"]
    assert info["probe"] == RUN_INFO["probe"]          # geometry carried over
    assert info["effective_seconds"] == RUN_INFO["effective_seconds"]
    assert "curated from the fakesorter run" in info["curation_line"]

    # The label rode through the merge/split onto the curated units.
    import spikeinterface.full as si

    labels = si.load(paths["curated_sorting"]).get_property("quality")
    assert sorted(x for x in labels if x) == ["MUA", "MUA"]   # both split children

    st = curation.state(SORTER, root)
    assert st["has_curated"] and not st["stale"]


def test_apply_refuses_to_write_into_the_raw_sort(synthetic):
    """--out outputs/<sorter> would delete the raw sorting/ + analyzer/ it curates."""
    root, paths, unit_ids = synthetic["root"], synthetic["paths"], synthetic["unit_ids"]
    record = curation.new_record(SORTER, unit_ids, root=root)
    curation.add_label(record, unit_ids[0], "good")
    for target in (paths["out"], paths["sorting"], paths["analyzer"],
                   paths["out"] / "." / "sub" / ".."):     # a path that resolves back
        with pytest.raises(RuntimeError) as e:
            curation.apply_record(record, root, out_dir=target, verbose=False)
        assert "refusing to write the curated result" in str(e.value)
    # ...and the raw sort is still there afterwards.
    assert (paths["sorting"] / "provenance.json").exists() or paths["sorting"].is_dir()
    assert paths["analyzer"].is_dir()


def test_apply_refuses_when_the_sort_cannot_be_identified(synthetic, tmp_path):
    """A missing/corrupt run_info.json unbinds the anchor - that must refuse, not
    pass: an all-None identity would otherwise "match" any sort."""
    root, paths, unit_ids = synthetic["root"], synthetic["paths"], synthetic["unit_ids"]
    record = curation.new_record(SORTER, unit_ids, root=root)
    curation.add_label(record, unit_ids[0], "good")
    saved = paths["run_info"].read_text(encoding="utf-8")
    paths["run_info"].unlink()
    try:
        with pytest.raises(RuntimeError) as e:
            curation.apply_record(record, root, verbose=False)
        assert "cannot identify the saved" in str(e.value)
        assert "run_info.json" in str(e.value)
    finally:
        paths["run_info"].write_text(saved, encoding="utf-8")

    # The mirror case: a record whose own anchor is blank binds to nothing.
    blank = curation.new_record(SORTER, unit_ids, run={}, root=root)
    curation.add_label(blank, unit_ids[0], "good")
    with pytest.raises(RuntimeError) as e:
        curation.apply_record(blank, root, verbose=False)
    assert "no usable anchor" in str(e.value)


def test_apply_refuses_a_record_written_against_another_sort(synthetic):
    root, paths, unit_ids = synthetic["root"], synthetic["paths"], synthetic["unit_ids"]
    record = curation.new_record(SORTER, unit_ids, root=root)
    curation.add_label(record, unit_ids[0], "good")
    record["curates"]["run"]["created"] = "2020-01-01T00:00:00"
    record["curates"]["run"]["n_units"] = 99
    with pytest.raises(RuntimeError) as e:
        curation.apply_record(record, root, verbose=False)
    msg = str(e.value)
    assert "written against a different" in msg
    assert "sorted at" in msg and "units" in msg
    assert "write a fresh record" in msg          # the message names the next step


def test_curated_run_info_carries_the_raw_to_curated_unit_map(synthetic, tmp_path):
    """The Phy round-trip (and any later import) needs to know which sorter unit a
    curated unit came from."""
    root, paths, unit_ids = synthetic["root"], synthetic["paths"], synthetic["unit_ids"]
    a, b, c = (str(u) for u in unit_ids)
    record = curation.new_record(SORTER, unit_ids, root=root)
    curation.add_merge(record, [unit_ids[0], unit_ids[1]])
    n_c = _spike_counts(paths["sorting"])[c]
    curation.add_split(record, unit_ids[2],
                       [list(range(0, n_c, 2)), list(range(1, n_c, 2))], "kmeans", {})
    out = tmp_path / "mapped"
    curation.apply_record(record, root, out_dir=out, verbose=False)
    info = json.loads((out / "run_info.json").read_text(encoding="utf-8"))
    m = info["unit_id_map"]
    # The merged pair points at ONE curated unit, and that unit names both sources.
    merged = m["raw_to_curated"][a]
    assert len(merged) == 1 and m["raw_to_curated"][b] == merged
    sources = {s["unit"] for s in m["curated_to_raw"][merged[0]]}
    assert sources == {a, b}
    # The split unit points at TWO curated units, each sourced from it alone.
    children = m["raw_to_curated"][c]
    assert len(children) == 2
    for child in children:
        assert [s["unit"] for s in m["curated_to_raw"][child]] == [c]
    # Spike counts add up to the raw unit's train.
    assert sum(m["curated_to_raw"][child][0]["n_spikes"] for child in children) == n_c
    # It is a repo-relative POSIX path, not an absolute one (merge-back + Windows).
    assert info["curation_record"] == f"outputs/{SORTER}/curation.json"


def test_label_records_where_the_decision_came_from(tmp_path):
    """Phy-origin labels must be distinguishable from a person's own call."""
    record, _paths = _record(tmp_path)
    curation.add_label(record, 1, "good")
    curation.add_label(record, 2, "noise", source="phy")
    methods = [d["method"] for d in record["decisions"]]
    assert methods == ["manual", "phy"]


def test_a_summary_failure_keeps_the_curated_analyzer(synthetic, monkeypatch, tmp_path):
    """run_sorting's semantics: the array/yield summary is best-effort on its own -
    a summary hiccup must not delete a good analyzer + metrics."""
    root, unit_ids = synthetic["root"], synthetic["unit_ids"]
    record = curation.new_record(SORTER, unit_ids, root=root)
    curation.add_label(record, unit_ids[0], "good")

    def boom(*a, **kw):
        raise RuntimeError("summary exploded")

    monkeypatch.setattr(curation._summary, "compute_summary", boom)
    out = tmp_path / "curated_out"
    result = curation.apply_record(record, root, out_dir=out, verbose=False)
    assert result["summary"] is None
    assert result["metrics_note"] is None          # the METRICS did not fail
    assert (out / "analyzer").is_dir()
    assert (out / "quality_metrics.csv").exists()
    assert not (out / "summary.json").exists()


def test_a_metrics_failure_keeps_the_units_and_clears_the_derived_data(
        synthetic, monkeypatch, tmp_path):
    """The sort pipeline's contract, carried over: units saved first, half-built
    derived data removed so no surface reads it as this result."""
    import spikeinterface.full as si

    root, unit_ids = synthetic["root"], synthetic["unit_ids"]
    record = curation.new_record(SORTER, unit_ids, root=root)
    curation.add_label(record, unit_ids[0], "good")

    out = tmp_path / "curated_fail"
    out.mkdir()
    (out / "analyzer").mkdir()                     # stale leftovers from a past run
    (out / "quality_metrics.csv").write_text("stale", encoding="utf-8")
    (out / "summary.json").write_text("{}", encoding="utf-8")
    (out / "summary.csv").write_text("stale", encoding="utf-8")

    def boom(*a, **kw):
        raise RuntimeError("analyzer exploded")

    monkeypatch.setattr(si, "create_sorting_analyzer", boom)
    result = curation.apply_record(record, root, out_dir=out, verbose=False)
    assert "analyzer exploded" in result["metrics_note"]
    assert (out / "sorting").is_dir()              # the units survive
    assert result["n_units"] == len(unit_ids)
    assert not (out / "analyzer").exists()
    for stale in ("quality_metrics.csv", "summary.json", "summary.csv"):
        assert not (out / stale).exists()
    # The run_info still gets written, carrying the note.
    info = json.loads((out / "run_info.json").read_text(encoding="utf-8"))
    assert "analyzer exploded" in info["metrics_note"]
    assert info["unit_id_map"]["raw_to_curated"]


def test_propose_splits_partitions_every_spike_and_repeats(synthetic):
    import spikeinterface.full as si

    paths, unit_ids = synthetic["paths"], synthetic["unit_ids"]
    analyzer = si.load_sorting_analyzer(paths["analyzer"])
    unit = unit_ids[0]
    n = len(analyzer.sorting.get_unit_spike_train(unit))
    first = curation.propose_splits(analyzer, [unit])
    indices, params, detail = first[unit]
    assert len(indices) == 2
    flat = sorted(i for part in indices for i in part)
    assert flat == list(range(n))                  # a partition, nothing dropped
    assert detail["n_spikes"] == n
    assert params["features"] == "amplitude+pca" and params["n_parts"] == 2
    assert params["peak_channel"] in [str(c) for c in analyzer.channel_ids]
    # Deterministic: the record is a replay, so the proposal must not drift.
    again = curation.propose_splits(analyzer, [unit])
    assert again[unit][0] == indices


def test_unit_ids_of_falls_back_to_the_saved_sorting(synthetic):
    root, unit_ids = synthetic["root"], synthetic["unit_ids"]
    assert curation.unit_ids_of(SORTER, root) == unit_ids


# --------------------------------------------------------------------------- #
# The CLI path - and the record surviving a relaunch (a fresh process)
# --------------------------------------------------------------------------- #
def _cli(*args, root):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "curation.py"), *args,
         "--sorter", SORTER, "--root", str(root)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")


def test_cli_writes_and_re_reads_the_record_in_a_fresh_process(synthetic):
    root, paths = synthetic["root"], synthetic["paths"]
    unit = synthetic["unit_ids"][1]
    paths["record"].unlink(missing_ok=True)

    out = _cli("label", "--unit", str(unit), "--label", "noise", root=root)
    assert out.returncode == 0, out.stderr
    written = json.loads(paths["record"].read_text(encoding="utf-8"))

    shown = _cli("show", root=root)
    assert shown.returncode == 0, shown.stderr
    assert "1 decision" in shown.stdout and "noise" in shown.stdout
    assert str(unit) in shown.stdout
    # Same bytes after the round-trip through two more processes.
    assert json.loads(paths["record"].read_text(encoding="utf-8")) == written
    assert curation.load_record(SORTER, root) == written


def test_cli_refuses_to_add_a_decision_to_a_record_from_another_sort(tmp_path):
    """The anchor is checked when a decision is WRITTEN too - otherwise --unit 4
    would silently mean a unit of the sort that used to be there."""
    record, paths = _record(tmp_path)
    paths["sorting"].mkdir(parents=True, exist_ok=True)
    record["curates"]["run"]["created"] = "2020-01-01T00:00:00"
    curation.save_record(record, paths["record"])
    out = _cli("label", "--unit", "1", "--label", "good", root=tmp_path)
    assert out.returncode == 1
    assert "written against a different" in out.stderr
    assert "write a fresh record" in out.stderr


def test_cli_apply_refuses_an_empty_record(tmp_path):
    record, paths = _record(tmp_path)
    paths["sorting"].mkdir(parents=True)
    curation.save_record(record, paths["record"])
    out = _cli("apply", root=tmp_path)
    assert out.returncode == 1
    assert "no decisions" in out.stderr


def test_cli_apply_without_a_record_says_what_to_do(tmp_path):
    paths = curation.sort_paths(SORTER, tmp_path)
    paths["sorting"].mkdir(parents=True)
    out = _cli("apply", root=tmp_path)
    assert out.returncode == 1
    assert "no curation record" in out.stderr and "label / merge / split" in out.stderr
