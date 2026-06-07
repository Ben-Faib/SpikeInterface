"""Unit tests for run_sorting's pure helpers (no real sorting)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sorters  # noqa: E402
import run_sorting as rs  # noqa: E402


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(sorters, "installed", lambda: ["spykingcircus2", "tridesclous2"])
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(sorters, "CONTAINERIZED", frozenset({"mountainsort5", "tridesclous2"}))
    monkeypatch.setattr(sorters, "default_params", lambda name: {
        "detect_threshold": 5.0, "n_peaks": 5000, "apply_preprocessing": True})


def test_resolve_sorter_ok_local(fake):
    assert rs.resolve_sorter("tridesclous2", use_docker=False) == "tridesclous2"


def test_resolve_sorter_rejects_unrunnable(fake):
    with pytest.raises(SystemExit):
        rs.resolve_sorter("kilosort4", use_docker=False)


def test_resolve_sorter_docker_enables_container(fake):
    assert rs.resolve_sorter("mountainsort5", use_docker=True) == "mountainsort5"


def test_resolve_overrides_merges_file_then_cli(fake, tmp_path):
    pf = tmp_path / "p.json"
    pf.write_text('{"detect_threshold": 4.0, "n_peaks": 100}')
    out = rs.resolve_overrides("tridesclous2", ["detect_threshold=6.5"], str(pf))
    assert out["detect_threshold"] == 6.5   # CLI wins over file
    assert out["n_peaks"] == 100            # from file
    assert "apply_preprocessing" not in out  # defaults not duplicated


def test_resolve_overrides_unknown_key_exits(fake):
    with pytest.raises(SystemExit):
        rs.resolve_overrides("tridesclous2", ["bogus=1"], None)


def test_resolve_overrides_bad_value_exits(fake):
    with pytest.raises(SystemExit):
        rs.resolve_overrides("tridesclous2", ["n_peaks=notint"], None)


def test_friendly_message_when_docker_not_running():
    msg = rs._friendly_sort_error(
        RuntimeError("Docker was requested but the Docker daemon isn't reachable."))
    assert "Docker" in msg and "try again" in msg.lower()
