"""Contract tests for the sort-progress JSON event protocol.

``scripts/sort_progress.py`` is the wire protocol between ``run_sorting.py``
(emitter subprocess) and the TUI's ``SortProgressScreen`` (consumer). D2
EXTENDED it (emitter-side ``elapsed``, ``phase_done``, a terminal ``result``
riding alongside ``done``) and D2b added the up-front ``plan`` manifest - these
tests pin the whole surface:

- the event vocabulary and each event's required keys (``SHAPES``),
- extension safety: unknown event types are ignored by consumers, unknown
  extra keys on known events flow through parse/reduce unharmed,
- ordering semantics: phases advance monotonically, a new phase resets
  per-phase transients, done/error are terminal,
- the emitter (``run_sorting.Reporter``) speaks exactly this protocol,
- stdout purity in ``--progress json`` mode, including failure paths.

To add a new event type: extend ``EVENT_TYPES`` + the module docstring in
``sort_progress.py``, then add the type and its required keys to ``SHAPES``
here - ``test_shapes_table_covers_event_types`` fails until you do, which is
the point. Adding optional keys to an existing event needs no changes here.

Behavioural reducer details are covered in ``test_sort_progress.py``; this
module is only about the contract surface.
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "scripts")
import sort_progress as sp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Required keys per event type (beyond "t"). Optional keys - phase.sub,
# phase.elapsed, bar.n/total/elapsed/remaining, result.elapsed, done.good/note -
# are deliberately absent: consumers must not require them.
SHAPES = {
    "plan":       {"n", "phases"},
    "phase":      {"i", "n", "title"},
    "phase_done": {"i", "title", "secs"},
    "detail":     {"text"},
    "substep":    {"name", "i", "n"},
    "bar":        {"desc", "frac"},
    "heartbeat":  {"label", "secs"},
    "metrics":    {"rows", "csv"},
    "summary":    {"card", "summary"},
    "result":     {"units", "good", "noise_floor_uV", "out",
                   "effective_seconds", "total_seconds"},
    "done":       {"ok", "units", "out"},
    "error":      {"ok", "message"},
}

# One canonical, fully-populated example of every event type.
EXAMPLES = {
    "plan":       {"t": "plan", "n": 5,
                   "phases": [{"i": 1, "title": "Read broadband"},
                              {"i": 2, "title": "Preprocess"},
                              {"i": 3, "title": "Sort"},
                              {"i": 4, "title": "Save sorting"},
                              {"i": 5, "title": "Analyze + metrics"}]},
    "phase":      {"t": "phase", "i": 2, "n": 5, "title": "Preprocess",
                   "sub": "bandpass + CMR", "elapsed": 3.24},
    "phase_done": {"t": "phase_done", "i": 2, "title": "Preprocess", "secs": 4.11},
    "detail":     {"t": "detail", "text": "detect_peaks: 562 peaks found"},
    "substep":    {"t": "substep", "name": "snr", "i": 2, "n": 8},
    "bar":        {"t": "bar", "desc": "detect", "frac": 0.5, "n": 5, "total": 10,
                   "elapsed": 3.2, "remaining": 3.1},
    "heartbeat":  {"t": "heartbeat", "label": "running sorter", "secs": 30},
    "metrics":    {"t": "metrics", "rows": [{"unit": 1, "snr": 7.2}], "csv": "q.csv"},
    "summary":    {"t": "summary", "card": ["V_pp: 22.9 µV"], "summary": {"n_units": 7}},
    "result":     {"t": "result", "units": 7, "good": 5, "noise_floor_uV": 4.01,
                   "out": "outputs/x", "effective_seconds": 132.1, "total_seconds": 132.1,
                   "elapsed": 247.3},
    "done":       {"t": "done", "ok": True, "units": 7, "good": 5, "out": "outputs/x",
                   "note": None},
    "error":      {"t": "error", "ok": False, "message": "Docker isn't running"},
}


# --------------------------------------------------------------------------- #
# Vocabulary and shapes
# --------------------------------------------------------------------------- #

def test_shapes_table_covers_event_types():
    # Extending the protocol means adding the new type HERE too (with its
    # required keys) - a conscious act, not an accident.
    assert set(SHAPES) == set(sp.EVENT_TYPES)
    assert set(EXAMPLES) == set(sp.EVENT_TYPES)


@pytest.mark.parametrize("etype", sorted(SHAPES))
def test_example_roundtrips_with_required_keys(etype):
    buf = io.StringIO()
    sp.emit(EXAMPLES[etype], stream=buf)
    raw = buf.getvalue()
    assert raw.endswith("\n") and "\n" not in raw[:-1]   # exactly one line
    ev = sp.parse_line(raw)
    assert ev == EXAMPLES[etype]
    assert SHAPES[etype] <= set(ev)


@pytest.mark.parametrize("etype", sorted(SHAPES))
def test_reduce_is_total_on_minimal_events(etype):
    # A bare {"t": ...} must never crash the consumer: every payload key is
    # read with defaults, so an emitter can add fields without breaking an
    # older UI mid-extension.
    state = sp.new_state()
    sp.reduce(state, {"t": etype})     # must not raise
    sp.reduce(state, EXAMPLES[etype])  # nor the full example after it


def test_unknown_event_type_is_ignored():
    # Forward compatibility: a NEW event type from a newer emitter must be
    # dropped by parse_line (None), never crash or half-apply. The specimen is
    # deliberately impossible so a real future type never collides with it.
    assert sp.parse_line('{"t": "__unknown__", "secs": 12}') is None
    assert sp.parse_line('[1, 2, 3]') is None


def test_unknown_extra_keys_flow_through():
    # The planned extension adds keys to existing events (e.g. bar.eta).
    # parse_line must keep them, and reduce must tolerate them.
    line = '{"t": "bar", "desc": "detect", "frac": 0.5, "eta_s": 12.5}'
    ev = sp.parse_line(line)
    assert ev is not None and ev["eta_s"] == 12.5
    state = sp.new_state()
    sp.reduce(state, ev)               # must not raise
    # done/error carry their whole payload into state["done"] - the extension
    # point for richer result events.
    state = sp.new_state()
    sp.reduce(state, {"t": "done", "ok": True, "units": 3, "out": "x", "report_path": "r.html"})
    assert state["done"]["report_path"] == "r.html"


# --------------------------------------------------------------------------- #
# Ordering semantics
# --------------------------------------------------------------------------- #

def test_phase_progression_and_transient_reset():
    state = sp.new_state()
    for i, title in enumerate(["Read broadband", "Preprocess", "Sort", "Quality metrics"], 1):
        sp.reduce(state, {"t": "phase", "i": i, "n": 4, "title": title})
        sp.reduce(state, {"t": "detail", "text": f"in {title}"})
        sp.reduce(state, {"t": "bar", "desc": "work", "frac": 0.5, "total": 10})
        # every earlier phase is done, the current one is not
        assert [p["done"] for p in state["phases"]] == [True] * (i - 1) + [False]
        assert state["phase_i"] == i and state["phase_n"] == 4
    # each new phase had cleared the previous phase's bar/detail/substep
    sp.reduce(state, {"t": "substep", "name": "snr", "i": 1, "n": 8})
    sp.reduce(state, {"t": "phase", "i": 5, "n": 5, "title": "Extra"})
    assert state["bar"] is None
    assert state["substep_name"] == "" and state["substep_i"] == 0
    assert state["detail"] == ""


def test_plan_announces_without_starting_anything():
    # The manifest is INTENT: it may not mark work as started or finished, so a
    # consumer can never show a phase as run because the emitter merely planned it.
    state = sp.new_state()
    sp.reduce(state, EXAMPLES["plan"])
    assert state["phases"] == [] and state["phase_i"] == 0
    assert state["phase_n"] == 5                       # the total IS known up front
    rows = sp.phase_rows(state)
    assert [r["state"] for r in rows] == ["pending"] * 5
    # ...and a started phase leaves the manifest's row list, never duplicating it
    sp.reduce(state, {"t": "phase", "i": 1, "n": 5, "title": "Read broadband"})
    rows = sp.phase_rows(state)
    assert [r["state"] for r in rows] == ["running"] + ["pending"] * 4
    assert [r["title"] for r in rows][0] == "Read broadband"


def test_phase_rows_without_a_plan_are_exactly_the_started_phases():
    # Extension safety in the other direction: an emitter that sends no manifest
    # (report.py's build path) must render exactly as it did before D2b.
    state = sp.new_state()
    sp.reduce(state, {"t": "phase", "i": 1, "n": 3, "title": "A"})
    sp.reduce(state, {"t": "phase_done", "i": 1, "title": "A", "secs": 1.5})
    sp.reduce(state, {"t": "phase", "i": 2, "n": 3, "title": "B"})
    assert [(r["title"], r["state"]) for r in sp.phase_rows(state)] == [
        ("A", "done"), ("B", "running")]


def test_pending_rows_disappear_when_the_run_ends():
    # A phase that never ran is not "pending" after an error - it is never
    # happening (§1.7: no queued-looking rows under a dead run).
    state = sp.new_state()
    sp.reduce(state, EXAMPLES["plan"])
    sp.reduce(state, {"t": "phase", "i": 1, "n": 5, "title": "Read broadband"})
    sp.reduce(state, {"t": "error", "ok": False, "message": "boom"})
    assert [r["state"] for r in sp.phase_rows(state)] == ["done"]


def test_phase_done_closes_that_phase_with_its_duration():
    state = sp.new_state()
    sp.reduce(state, {"t": "phase", "i": 1, "n": 5, "title": "Read broadband", "elapsed": 0.01})
    sp.reduce(state, {"t": "phase_done", "i": 1, "title": "Read broadband", "secs": 3.2})
    assert state["phases"][0]["done"] is True
    assert state["phases"][0]["secs"] == 3.2
    # Timing is the EMITTER's: the consumer shows what it is told, keeping a
    # replayed event log faithful to the run.
    sp.reduce(state, {"t": "phase", "i": 2, "n": 5, "title": "Preprocess", "elapsed": 3.21})
    assert state["elapsed"] == 3.21
    assert state["phases"][1]["secs"] is None      # still running


def test_result_rides_alongside_done_and_never_replaces_it():
    state = sp.new_state()
    sp.reduce(state, {"t": "phase", "i": 1, "n": 5, "title": "Read broadband"})
    sp.reduce(state, EXAMPLES["result"])
    # a result on its own is NOT terminal - done still has to arrive
    assert state["result"]["units"] == 7 and state["done"] is None
    sp.reduce(state, {"t": "done", "ok": True, "units": 7, "good": 5, "out": "outputs/x"})
    assert state["done"]["ok"] is True
    assert state["result"]["noise_floor_uV"] == 4.01      # survives the terminal event


def test_done_without_a_result_still_closes_the_run():
    # The TUI synthesises `done` from a silent rc-0 exit, so a run can end with
    # no result event at all: the terminal contract must not depend on one.
    state = sp.new_state()
    sp.reduce(state, {"t": "done", "ok": True, "units": "?", "out": ""})
    assert state["done"] is not None and state["result"] is None


@pytest.mark.parametrize("terminal", [
    {"t": "done", "ok": True, "units": 3, "out": "outputs/x"},
    {"t": "error", "ok": False, "message": "boom"},
])
def test_terminal_event_completes_all_phases(terminal):
    state = sp.new_state()
    sp.reduce(state, {"t": "phase", "i": 1, "n": 2, "title": "A"})
    sp.reduce(state, {"t": "phase", "i": 2, "n": 2, "title": "B"})
    sp.reduce(state, terminal)
    assert all(p["done"] for p in state["phases"])
    assert state["done"] is not None
    assert state["done"]["ok"] is terminal["ok"]


# --------------------------------------------------------------------------- #
# The emitter speaks this protocol (Reporter <-> sort_progress lock)
# --------------------------------------------------------------------------- #

def test_reporter_emits_exactly_this_protocol():
    # run_sorting imports SpikeInterface lazily inside main(), so this module
    # import is fast. Every Reporter method must produce a parseable event with
    # its SHAPES keys, and together they must cover the whole vocabulary.
    import run_sorting as rs

    buf = io.StringIO()
    rep = rs.Reporter(enabled=True, stream=buf, total_phases=4)
    rep.plan(["Read broadband", "Preprocess", "Sort", "Save sorting"])
    rep.phase("Read broadband", "(.ns5)")
    rep.phase("Preprocess", "bandpass + CMR")
    rep.detail("detect_peaks: 562 peaks found")
    rep.substep("snr", 2, 8)
    rep.bar("detect", frac=0.5, n=5, total=10, elapsed=3.2, remaining=3.1)
    rep.heartbeat("running sorter", 30)
    rep.metrics([{"unit": 1, "snr": 7.2}], "q.csv")
    rep.summary(["V_pp: 22.9 µV"], {"n_units": 7})
    rep.result(units=7, good=5, noise_floor_uV=4.01, out="outputs/x",
               effective_seconds=132.1, total_seconds=132.1)
    rep.done_ok(units=7, out="outputs/x", good=5)
    rep.error("boom")

    events = [sp.parse_line(line) for line in buf.getvalue().splitlines()]
    assert all(ev is not None for ev in events), "Reporter emitted a non-protocol line"
    for ev in events:
        assert SHAPES[ev["t"]] <= set(ev)
    assert {ev["t"] for ev in events} == set(sp.EVENT_TYPES)
    # phase counter is 1-based and monotonic
    phases = [ev for ev in events if ev["t"] == "phase"]
    assert [p["i"] for p in phases] == [1, 2] and all(p["n"] == 4 for p in phases)
    # ...and carries the emitter's clock, monotonically
    stamps = [p["elapsed"] for p in phases]
    assert all(isinstance(e, float) and e >= 0 for e in stamps) and stamps == sorted(stamps)
    # every phase the emitter left behind is closed by a phase_done naming it
    closed = [ev for ev in events if ev["t"] == "phase_done"]
    assert [(c["i"], c["title"]) for c in closed] == [(1, "Read broadband"), (2, "Preprocess")]
    assert all(c["secs"] >= 0 for c in closed)
    # the rich result rides alongside done, before it - never instead of it
    types = [ev["t"] for ev in events]
    assert types.index("result") < types.index("done")
    # the manifest is UP FRONT: it precedes every phase it announces
    assert types.index("plan") < types.index("phase")
    plan = events[types.index("plan")]
    assert [p["i"] for p in plan["phases"]] == [1, 2, 3, 4] and plan["n"] == 4


def test_error_does_not_close_the_running_phase():
    # A phase that died did not finish, so no phase_done is claimed for it; the
    # consumer's terminal handling is what closes the checklist.
    import run_sorting as rs

    buf = io.StringIO()
    rep = rs.Reporter(enabled=True, stream=buf, total_phases=4)
    rep.phase("Sort")
    rep.error("boom")
    assert [sp.parse_line(ln)["t"] for ln in buf.getvalue().splitlines()] == ["phase", "error"]


def test_abandoned_phase_gets_no_phase_done():
    # The non-fatal-metrics path: the metrics phase CRASHED but the run still ends
    # ok (sort saved). abandon_phase() forgets it, so the later result()/done_ok()
    # close must not fabricate a completed phase with a duration (D2 review #1).
    import run_sorting as rs

    buf = io.StringIO()
    rep = rs.Reporter(enabled=True, stream=buf, total_phases=5)
    rep.phase("Analyze + metrics")
    rep.abandon_phase()
    rep.result(units=2, good=None, noise_floor_uV=None, out="x",
               effective_seconds=30.0, total_seconds=132.0)
    rep.done_ok(units=2, out="x", note="quality metrics failed: …")
    types = [sp.parse_line(ln)["t"] for ln in buf.getvalue().splitlines()]
    assert types == ["phase", "result", "done"]   # no phase_done anywhere


def test_disabled_reporter_is_silent():
    import run_sorting as rs

    buf = io.StringIO()
    rep = rs.Reporter(enabled=False, stream=buf, total_phases=4)
    rep.phase("Read broadband")
    rep.error("boom")
    assert buf.getvalue() == ""


# --------------------------------------------------------------------------- #
# stdout purity in --progress json mode (real subprocess, failure paths)
# --------------------------------------------------------------------------- #

def _run_sorting(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    # Explicit utf-8 (not the locale code page - cp1252 on the lab's Windows
    # box) because the child forces utf-8 output full of multibyte glyphs.
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_sorting.py"), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=ROOT,
    )


def test_missing_data_keeps_stdout_pure_and_errors(tmp_path):
    # No recording in --data-dir: the run must fail (rc != 0) with EVERY stdout
    # line a parseable protocol event, ending in an error event with a
    # non-empty message - never a bare traceback on the event channel.
    # --output-dir keeps the run fully hermetic (no dir created in outputs/).
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    res = _run_sorting("--progress", "json", "--data-dir", str(data_dir),
                       "--output-dir", str(tmp_path / "out"))
    assert res.returncode != 0
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    events = [sp.parse_line(ln) for ln in lines]
    assert events, "expected at least an error event on stdout"
    bad = [ln for ln, ev in zip(lines, events) if ev is None]
    assert not bad, f"non-protocol stdout lines in --progress json mode: {bad[:3]}"
    last = events[-1]
    assert last["t"] == "error" and last["ok"] is False
    assert last["message"].strip()


def test_usage_error_keeps_stdout_empty():
    # An argparse rejection happens before the sort starts: usage goes to
    # stderr (rc 2), and the JSON event channel stays completely silent.
    res = _run_sorting("--progress", "json", "--duration", "-5")
    assert res.returncode != 0
    assert res.stdout.strip() == ""
    assert res.stderr.strip()
