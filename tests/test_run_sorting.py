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


def test_friendly_message_when_docker_not_running(monkeypatch):
    # docker requested AND the daemon actually down -> the start-Docker hint.
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    msg = rs._friendly_sort_error(
        RuntimeError("Docker was requested but the Docker daemon isn't reachable."),
        use_docker=True)
    assert "Docker" in msg and "try again" in msg.lower()


def test_friendly_message_does_not_misblame_docker_when_running(monkeypatch):
    # Regression: an error that merely mentions "docker" must NOT be reported as
    # "Docker isn't running" when the daemon is up — that substring match masked a
    # real failure (a missing SDK / sorter crash) and sent users to a dead end.
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    msg = rs._friendly_sort_error(
        RuntimeError("The python docker package must be installed."), use_docker=True)
    assert "isn't running" not in msg
    assert "docker package" in msg          # the real cause is surfaced, not hidden


def test_friendly_message_local_failure_passthrough():
    msg = rs._friendly_sort_error(RuntimeError("kaboom"), use_docker=False)
    assert "Sorting failed" in msg and "kaboom" in msg


def test_quality_summary_counts_good_units():
    import pandas as pd
    qm = pd.DataFrame({
        "snr": [6.0, 4.0, 9.0, 5.0],                 # >=5: rows 0,2,3
        "isi_violations_ratio": [0.1, 0.0, 0.9, 0.2]  # <=0.5: rows 0,1,3
    })
    n_total, n_good = rs._quality_summary(qm)         # both: rows 0,3 -> 2
    assert n_total == 4 and n_good == 2


def test_quality_summary_handles_missing_columns():
    import pandas as pd
    n_total, n_good = rs._quality_summary(pd.DataFrame({"firing_rate": [1.0, 2.0]}))
    assert n_total == 2 and n_good is None


def test_prepare_docker_image_uses_cache(monkeypatch):
    monkeypatch.setattr(sorters, "default_docker_image", lambda s: "img:latest")
    monkeypatch.setattr(sorters, "docker_image_present", lambda i: True)

    def _no_pull(*a, **k):
        raise AssertionError("must not pull when the image is already cached")
    monkeypatch.setattr(sorters, "pull_docker_image", _no_pull)
    rs._prepare_docker_image(rs.ConsoleUI(quiet=True, total_phases=4), "mountainsort5")


def test_prepare_docker_image_pulls_when_absent(monkeypatch):
    calls = {}
    monkeypatch.setattr(sorters, "default_docker_image", lambda s: "img:latest")
    monkeypatch.setattr(sorters, "docker_image_present", lambda i: False)
    monkeypatch.setattr(sorters, "pull_docker_image",
                        lambda *a, **k: calls.setdefault("pulled", True) or True)
    rs._prepare_docker_image(rs.ConsoleUI(quiet=True, total_phases=4), "mountainsort5")
    assert calls.get("pulled") is True


def test_prepare_docker_image_noop_without_image(monkeypatch):
    monkeypatch.setattr(sorters, "default_docker_image", lambda s: None)

    def _boom(i):
        raise AssertionError("should not probe presence when there is no image")
    monkeypatch.setattr(sorters, "docker_image_present", _boom)
    rs._prepare_docker_image(rs.ConsoleUI(quiet=True, total_phases=4), "weird")


def test_reporter_emits_events_to_stdout(monkeypatch):
    import io

    import sort_progress as sp

    buf = io.StringIO()
    rep = rs.Reporter(enabled=True, stream=buf, total_phases=4)
    rep.phase("Read broadband", "22 ch")
    rep.bar("detect", frac=0.5, n=5, total=10)
    rep.done_ok(units=13, good=9, out="outputs/x")

    events = [sp.parse_line(l) for l in buf.getvalue().splitlines()]
    events = [e for e in events if e]
    assert events[0]["t"] == "phase" and events[0]["title"] == "Read broadband"
    assert any(e["t"] == "bar" and e["frac"] == 0.5 for e in events)
    assert events[-1]["t"] == "done" and events[-1]["units"] == 13


def test_reporter_disabled_emits_nothing():
    import io

    buf = io.StringIO()
    rep = rs.Reporter(enabled=False, stream=buf, total_phases=4)
    rep.phase("X")
    rep.done_ok(units=0, out="o")
    assert buf.getvalue() == ""
