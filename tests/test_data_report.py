"""Tests for SpikeInterface_Menu._data_report (the missing-data classifier).

Guards the base-scoped presence check: the present/missing checklist must reflect
the *resolved* recording's files, not a folder-wide glob — otherwise a second
recording sharing the folder would make an incomplete set look complete.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))           # SpikeInterface_Menu lives at the repo root
sys.path.insert(0, str(ROOT / "scripts"))

import SpikeInterface_Menu as M  # noqa: E402


def _touch(d: Path, *names: str) -> None:
    for n in names:
        (d / n).touch()


def _by_ext(report: dict) -> dict:
    return {f["ext"]: f["present"] for f in report["files"]}


def test_absent(tmp_path):
    r = M._data_report(str(tmp_path))
    assert r["present"] is False
    assert r["base"] is None
    assert _by_ext(r) == {".ns2": False, ".ns5": False, ".nev": False}
    assert r["error"]


def test_complete_set(tmp_path):
    _touch(tmp_path, "rec.ns2", "rec.ns5", "rec.nev")
    r = M._data_report(str(tmp_path))
    assert r["present"] is True
    assert r["base"] == "rec"
    assert _by_ext(r) == {".ns2": True, ".ns5": True, ".nev": True}


def test_incomplete_missing_ns5(tmp_path):
    _touch(tmp_path, "rec.ns2", "rec.nev")
    r = M._data_report(str(tmp_path))
    assert r["present"] is True
    assert _by_ext(r)[".ns5"] is False


def test_two_recordings_one_folder_is_base_scoped(tmp_path):
    # recA owns the .nev/.ns2; the .ns5 belongs to recB. The resolved base is recA
    # (first .nev), so recA's checklist must report .ns5 MISSING — not borrow recB's.
    _touch(tmp_path, "recA.ns2", "recB.ns5", "recA.nev")
    r = M._data_report(str(tmp_path))
    assert r["base"] == "recA"
    by = _by_ext(r)
    assert by[".ns2"] is True and by[".nev"] is True
    assert by[".ns5"] is False, "folder-wide glob leaked recB.ns5 into recA's set"


def test_stream_detail_merges_pipeline_into_files():
    import ui
    files = [{"ext": ".ns5", "label": "Broadband — raw @ 30 kHz", "present": True}]
    pipeline = [{"stage": "Broadband (.ns5)", "status": "PASS",
                 "detail": "22 ch, 132.0s @ 30000 Hz"}]
    out = ui.stream_detail(files, pipeline)
    assert ".ns5" in out and "22 ch" in out[".ns5"] and "30000 Hz" in out[".ns5"]
