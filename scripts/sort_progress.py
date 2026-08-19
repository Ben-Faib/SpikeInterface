"""Pure, dependency-free progress protocol between ``run_sorting.py`` (emitter,
in a subprocess) and the Textual ``SortProgressScreen`` (consumer).

Events are newline-delimited JSON objects, each with a ``t`` (type) field:

    plan       {t,n,phases:[{i,title,sub?}]}  the whole checklist, announced UP FRONT
    phase      {t,i,n,title,sub?,elapsed?}  a numbered pipeline phase started
    phase_done {t,i,title,secs}       the phase that was running finished, with its duration
    detail     {t,text}               a dim sub-step line (also: a mirrored sorter step print)
    substep    {t,name,i,n}           a named sub-step within a phase (e.g. one metric of N)
    bar        {t,desc,frac,n,total,elapsed?,remaining?}  determinate progress
    heartbeat  {t,label,secs}         "still working" pulse during quiet stretches
    metrics    {t,rows:[...],csv}     quality-metrics table
    summary    {t,card:[...],summary} array/yield headline card (six metrics)
    result     {t,units,good,noise_floor_uV,out,effective_seconds,total_seconds,elapsed?}
                                      the finished run's headline numbers, ready to render
    done       {t,ok:true,units,good?,out,note?}   finished OK (note = non-fatal caveat)
    error      {t,ok:false,message}   finished with a friendly error

``elapsed`` is measured by the *emitter* (seconds since run start), so a captured
event log replays with the run's real timing and no consumer-side clock skew.
``result`` rides ALONGSIDE ``done`` and never replaces it: ``done`` is the
terminal event a consumer can also synthesise from a silent rc-0 exit.

``plan`` is the pipeline's *intent*: it lets a consumer show what is still
pending from the first second instead of learning the checklist one phase at a
time. It is advisory - ``phase`` remains the only claim that work has started,
and an emitter that sends no ``plan`` simply has no pending rows to show. Use
:func:`phase_rows` to render the two together.

No SpikeInterface / Textual imports here so it is trivially unit-testable and
importable from both sides.
"""
from __future__ import annotations

import json
import sys
from typing import Any

EVENT_TYPES = frozenset(
    {"plan", "phase", "phase_done", "detail", "substep", "bar", "heartbeat", "metrics",
     "summary", "result", "done", "error"}
)


def emit(event: dict, stream=None) -> None:
    """Write one event as a JSON line. Defaults to stdout (the event channel)."""
    stream = stream if stream is not None else sys.stdout
    # allow_nan=False: a NaN/Infinity payload raises HERE, loudly, instead of
    # writing a token that kills any strict-JSON consumer downstream.
    stream.write(json.dumps(event, separators=(",", ":"), allow_nan=False) + "\n")
    stream.flush()


def parse_line(line: str) -> "dict | None":
    """Parse one line into an event dict, or None if it isn't a known event."""
    line = line.strip()
    if not line:
        return None
    try:
        ev = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(ev, dict):
        return None
    if ev.get("t") not in EVENT_TYPES:
        return None
    return ev


def new_state() -> dict:
    """Fresh consumer state the reducer mutates."""
    return {
        "phase_i": 0,
        "phase_n": 0,
        "phase_title": "",
        "planned": [],         # [{i,title,sub}] the announced checklist (plan), if any
        "phases": [],          # [{i,title,sub,done,secs}]  phases that STARTED; secs
                               # filled in by phase_done
        "elapsed": 0.0,        # emitter-side seconds since run start (latest phase/result)
        "detail": "",
        "substep_name": "",    # named sub-step within the current phase
        "substep_i": 0,        # 1-based index of the current sub-step
        "substep_n": 0,        # total sub-steps in the current phase
        "bar": None,           # {desc,frac,n,total,elapsed,remaining} or None
        "heartbeat": "",
        "heartbeat_secs": 0,
        "metrics": None,       # {rows,csv} or None
        "summary": None,       # {card:[...],summary} array/yield headline card or None
        "result": None,        # {units,good,noise_floor_uV,out,...} headline payload or None
        "done": None,          # {ok,...} or None
    }


def reduce(state: dict, ev: dict) -> dict:
    """Fold one event into ``state`` (mutates and returns it)."""
    t = ev.get("t")
    if t == "plan":
        # The manifest states what the run INTENDS to do; it never marks work as
        # started or done - only `phase` does that.
        state["planned"] = [
            {"i": p.get("i"), "title": p.get("title", ""), "sub": p.get("sub", "")}
            for p in (ev.get("phases") or []) if isinstance(p, dict)
        ]
        if ev.get("n") is not None:
            state["phase_n"] = ev["n"]
    elif t == "phase":
        # mark the previous phase done when a new one starts
        for p in state["phases"]:
            p["done"] = True
        state["phase_i"] = ev.get("i", state["phase_i"])
        state["phase_n"] = ev.get("n", state["phase_n"])
        state["phase_title"] = ev.get("title", "")
        state["phases"].append(
            {"i": ev.get("i"), "title": ev.get("title", ""), "sub": ev.get("sub", ""),
             "done": False, "secs": None}
        )
        if ev.get("elapsed") is not None:
            state["elapsed"] = ev["elapsed"]
        state["bar"] = None            # a new phase clears the old determinate bar
        state["detail"] = ev.get("sub", "")
        # a new phase clears any per-substep progress from the previous phase
        state["substep_name"] = ""
        state["substep_i"] = 0
        state["substep_n"] = 0
    elif t == "phase_done":
        # Close the phase it names (by index; a phase_done with no/unknown index
        # closes the one currently running) and record how long it took.
        target = next((p for p in state["phases"] if p.get("i") == ev.get("i")), None)
        if target is None and state["phases"]:
            target = state["phases"][-1]
        if target is not None:
            target["done"] = True
            target["secs"] = ev.get("secs")
    elif t == "detail":
        state["detail"] = ev.get("text", "")
    elif t == "substep":
        state["substep_name"] = ev.get("name", "")
        state["substep_i"] = ev.get("i", 0)
        state["substep_n"] = ev.get("n", 0)
    elif t == "bar":
        state["bar"] = {
            "desc": ev.get("desc", ""),
            "frac": ev.get("frac"),
            "n": ev.get("n"),
            "total": ev.get("total"),
            "elapsed": ev.get("elapsed"),
            "remaining": ev.get("remaining"),
        }
    elif t == "heartbeat":
        state["heartbeat"] = ev.get("label", "")
        state["heartbeat_secs"] = ev.get("secs", 0)
    elif t == "metrics":
        state["metrics"] = {"rows": ev.get("rows", []), "csv": ev.get("csv", "")}
    elif t == "summary":
        state["summary"] = {"card": ev.get("card", []), "summary": ev.get("summary", {})}
    elif t == "result":
        state["result"] = {k: v for k, v in ev.items() if k != "t"}
        if ev.get("elapsed") is not None:
            state["elapsed"] = ev["elapsed"]
    elif t in ("done", "error"):
        for p in state["phases"]:
            p["done"] = True
        state["done"] = {k: v for k, v in ev.items() if k != "t"}
    return state


def phase_rows(state: dict) -> list:
    """The checklist to render: the phases that ran, then the ones still pending.

    Each row is ``{i, title, sub, secs, state}`` with ``state`` one of ``done`` /
    ``running`` / ``pending``. Pending rows come from the ``plan`` manifest and
    exist only while the run is alive - once it is over (``done`` or ``error``)
    the phases that never started are not "pending", they are never happening, so
    they are dropped rather than left looking queued.
    """
    rows = [{"i": p.get("i"), "title": p.get("title", ""), "sub": p.get("sub", ""),
             "secs": p.get("secs"), "state": "done" if p.get("done") else "running"}
            for p in state.get("phases", [])]
    if state.get("done") is not None:
        return rows
    started = {r["i"] for r in rows}
    rows += [{"i": p.get("i"), "title": p.get("title", ""), "sub": p.get("sub", ""),
              "secs": None, "state": "pending"}
             for p in state.get("planned", []) if p.get("i") not in started]
    return rows
