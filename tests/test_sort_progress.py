"""Tests for the pure sort-progress event protocol (no SI / Textual)."""
import io
import sys

sys.path.insert(0, "scripts")
import sort_progress as sp


def test_emit_parse_roundtrip():
    buf = io.StringIO()
    sp.emit({"t": "phase", "i": 1, "n": 4, "title": "Read broadband"}, stream=buf)
    line = buf.getvalue()
    assert line.endswith("\n")
    ev = sp.parse_line(line)
    assert ev == {"t": "phase", "i": 1, "n": 4, "title": "Read broadband"}


def test_parse_line_ignores_non_events():
    assert sp.parse_line("not json at all") is None
    assert sp.parse_line("") is None
    assert sp.parse_line('{"no":"t key"}') is None
    assert sp.parse_line('{"t": 123}') is None  # t must be a known str


def test_reduce_tracks_phases_and_bar():
    state = sp.new_state()
    for ev in [
        {"t": "phase", "i": 1, "n": 4, "title": "Read broadband", "sub": "22 ch"},
        {"t": "detail", "text": "bandpass 300-6000"},
        {"t": "phase", "i": 2, "n": 4, "title": "Run sorter"},
        {"t": "bar", "desc": "detect", "frac": 0.5, "n": 5, "total": 10},
        {"t": "heartbeat", "label": "running sorter", "secs": 30},
    ]:
        sp.reduce(state, ev)
    assert state["phase_i"] == 2 and state["phase_n"] == 4
    assert state["phase_title"] == "Run sorter"
    assert state["phases"][0]["done"] is True   # phase 1 completed when 2 started
    assert state["bar"]["frac"] == 0.5 and state["bar"]["total"] == 10
    assert state["heartbeat"] == "running sorter" and state["heartbeat_secs"] == 30
    assert state["done"] is None


def test_reduce_done_and_error():
    s1 = sp.new_state()
    sp.reduce(s1, {"t": "done", "ok": True, "units": 13, "good": 9, "out": "outputs/x"})
    assert s1["done"]["ok"] is True and s1["done"]["units"] == 13

    s2 = sp.new_state()
    sp.reduce(s2, {"t": "error", "ok": False, "message": "Docker isn't running"})
    assert s2["done"]["ok"] is False and "Docker" in s2["done"]["message"]


def test_reduce_metrics_rows():
    state = sp.new_state()
    sp.reduce(state, {"t": "metrics", "rows": [{"unit": 1, "snr": 7.2}], "csv": "q.csv"})
    assert state["metrics"]["rows"][0]["unit"] == 1
    assert state["metrics"]["csv"] == "q.csv"


def test_substep_roundtrip():
    buf = io.StringIO()
    sp.emit({"t": "substep", "name": "snr", "i": 2, "n": 8}, stream=buf)
    ev = sp.parse_line(buf.getvalue())
    assert ev == {"t": "substep", "name": "snr", "i": 2, "n": 8}


def test_reduce_tracks_substep():
    state = sp.new_state()
    assert state["substep_name"] == "" and state["substep_i"] == 0 and state["substep_n"] == 0
    sp.reduce(state, {"t": "phase", "i": 4, "n": 4, "title": "Quality metrics"})
    sp.reduce(state, {"t": "substep", "name": "firing_rate", "i": 1, "n": 8})
    assert state["substep_name"] == "firing_rate"
    assert state["substep_i"] == 1 and state["substep_n"] == 8
    sp.reduce(state, {"t": "substep", "name": "snr", "i": 2, "n": 8})
    assert state["substep_name"] == "snr" and state["substep_i"] == 2


def test_reduce_phase_clears_substep():
    state = sp.new_state()
    sp.reduce(state, {"t": "substep", "name": "snr", "i": 2, "n": 8})
    assert state["substep_name"] == "snr"
    # a new phase resets per-substep progress so it never bleeds across phases
    sp.reduce(state, {"t": "phase", "i": 2, "n": 4, "title": "Sort"})
    assert state["substep_name"] == "" and state["substep_i"] == 0 and state["substep_n"] == 0
