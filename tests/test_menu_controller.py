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
