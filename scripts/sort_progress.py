"""Pure, dependency-free progress protocol between ``run_sorting.py`` (emitter,
in a subprocess) and the Textual ``SortProgressScreen`` (consumer).

Events are newline-delimited JSON objects, each with a ``t`` (type) field:

    phase     {t,i,n,title,sub?}     a numbered pipeline phase started
    detail    {t,text}               a dim sub-step line
    bar       {t,desc,frac,n,total,elapsed?,remaining?}  determinate progress
    heartbeat {t,label,secs}         "still working" pulse during quiet stretches
    metrics   {t,rows:[...],csv}     quality-metrics table
    done      {t,ok:true,units,good?,out}     finished OK
    error     {t,ok:false,message}   finished with a friendly error

No SpikeInterface / Textual imports here so it is trivially unit-testable and
importable from both sides.
"""
from __future__ import annotations

import json
import sys
from typing import Any

EVENT_TYPES = frozenset(
    {"phase", "detail", "bar", "heartbeat", "metrics", "done", "error"}
)


def emit(event: dict, stream=None) -> None:
    """Write one event as a JSON line. Defaults to stdout (the event channel)."""
    stream = stream if stream is not None else sys.stdout
    stream.write(json.dumps(event, separators=(",", ":")) + "\n")
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
        "phases": [],          # [{i,title,done}]
        "detail": "",
        "bar": None,           # {desc,frac,n,total,elapsed,remaining} or None
        "heartbeat": "",
        "heartbeat_secs": 0,
        "metrics": None,       # {rows,csv} or None
        "done": None,          # {ok,...} or None
    }


def reduce(state: dict, ev: dict) -> dict:
    """Fold one event into ``state`` (mutates and returns it)."""
    t = ev.get("t")
    if t == "phase":
        # mark the previous phase done when a new one starts
        for p in state["phases"]:
            p["done"] = True
        state["phase_i"] = ev.get("i", state["phase_i"])
        state["phase_n"] = ev.get("n", state["phase_n"])
        state["phase_title"] = ev.get("title", "")
        state["phases"].append(
            {"i": ev.get("i"), "title": ev.get("title", ""), "sub": ev.get("sub", ""), "done": False}
        )
        state["bar"] = None            # a new phase clears the old determinate bar
        state["detail"] = ev.get("sub", "")
    elif t == "detail":
        state["detail"] = ev.get("text", "")
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
    elif t in ("done", "error"):
        for p in state["phases"]:
            p["done"] = True
        state["done"] = {k: v for k, v in ev.items() if k != "t"}
    return state
