"""Unit test for compare's saved-sort discovery (no SpikeInterface needed)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import compare  # noqa: E402


def test_saved_sorters_finds_analyzer_dirs(tmp_path, monkeypatch):
    # Two sorters with an analyzer dir, one without.
    for name in ("tridesclous2", "mountainsort5"):
        (tmp_path / name / "analyzer").mkdir(parents=True)
    (tmp_path / "spykingcircus2").mkdir()
    monkeypatch.setattr(compare, "OUTPUT_DIR", tmp_path)
    found = compare.saved_sorters()
    assert found == ["mountainsort5", "tridesclous2"]  # sorted, only those with analyzer
