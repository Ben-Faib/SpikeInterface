"""The researcher's journey: where this recording stands, and the one thing to do next.

Single source of truth for the Spike 2.0 dashboard's **rail** (the six stage marks and
their captions), its **next-step card**, the **probe map** (which units sit on which
contact), **recent activity**, the **freshness of every output** on the Share stage,
and the **runs & reproducibility** overview. The view renders what this returns and
judges nothing itself.

    snap = journey.snapshot(sorter, data_report=..., pipeline=..., probe_info=...,
                            built=cfg.get("built"), rule=...)
    journey.stage_status(snap)    # [{key, n, label, mark, caption}] x 6
    journey.next_steps(snap)      # [{title, detail, action, label, stage}], best first
    journey.probe_map(snap)       # {contacts: [...top→tip], units: {ch: [...]}}
    journey.recent(snap)          # [{when, text}] newest first
    journey.outputs(snap)         # the Share stage's rows
    journey.runs_overview(sorter) # every saved run + its reproduce verdict

Marks: ``done`` (verified: green ✓), ``warn`` (needs attention and has a next step:
amber !), ``todo`` (not started: dim ·). Pure: json + pathlib through ``runs`` and
``curation`` (which own every path); no SpikeInterface.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import blackrock_io as bio
import curation
import runs
import sort_summary

# Spike 2.0 action table - (key, title, hint, needs_data, stage). Every action the
# app can run, as the palette (`/`) lists it; ``stage`` is the rail stage (1-6) it
# lives on, 0 for the app-wide ones (settings, help, quit). The panes draw their
# own rows and key lines; this table is the one list of names the palette, the
# help and the tests read, so an action can never be findable under two names.
ACTIONS = [
    ("stage:1",     "Go to 1 Data",              "the recording files and where they are", False, 1),
    ("folder",      "Choose the data folder",    "point Spike at another recording",        False, 1),
    ("open_folder", "Open the data folder",      "in Finder / Explorer",                    False, 1),
    ("explore",     "Explore the recording",     "static figures: LFP, events, rates",       True, 1),
    ("traces",      "Watch the raw traces",      "scroll the signal in a window",            True, 1),
    ("verify",      "Check the install",         "every library and loader, pass or fail",  False, 1),
    ("stage:2",     "Go to 2 Probe",             "the electrode geometry every sort uses",  False, 2),
    ("probe_edit",  "Edit the active probe",     "contacts, pitch, layout, name",           False, 2),
    ("probe_new",   "New probe",                 "describe another probe",                  False, 2),
    ("probe_import", "Import a probe file",      "probeinterface .json or .prb",            False, 2),
    ("stage:3",     "Go to 3 Sort",              "choose a sorter and run it",              False, 3),
    ("sort",        "Sort the full recording",   "a new run; the current one stays",         True, 3),
    ("sort_quick",  "Quick test sort",           "a short check that never becomes current", True, 3),
    ("params",      "Sorter parameters",         "the active sorter's own knobs",           False, 3),
    ("manage",      "Sorters and Docker",        "download images, delete, clear sorts",    False, 3),
    ("stage:4",     "Go to 4 Judge",             "label each unit with its evidence",       False, 4),
    ("gui",         "Inspect in the GUI",        "waveforms + correlograms in a window",     True, 4),
    ("import_phy",  "Import verdicts from Phy",  "bring labels back from a Phy session",    False, 4),
    ("stage:5",     "Go to 5 Apply",             "build the curated result",                False, 5),
    ("apply",       "Apply the decisions",       "curated result, re-scored",               False, 5),
    ("stage:6",     "Go to 6 Share",             "every output and how fresh it is",        False, 6),
    ("report",      "Build the report",          "one HTML page: units, quality, provenance", True, 6),
    ("compare",     "Compare two sorts",         "how much two saved sorts agree",           True, 6),
    ("sweep",       "Build the sorter shootout", "every sorter judged against the manual sort", True, 6),
    ("phy",         "Export to Phy",             "a folder to split the hard cases",         True, 6),
    ("runs",        "Runs and reproducibility",  "every run, its recipe, re-run and compare", False, 6),
    ("reproduce",   "Reproduce this run",        "re-run from its recipe, compare values",   True, 6),
    ("recipe",      "Export the run recipe",     "a file that re-runs this sort anywhere",  False, 6),
    ("settings",    "Settings",                  "every value the next sort uses",          False, 0),
    ("theme",       "Colour theme",              "the accent colour",                       False, 0),
    ("help",        "Help",                      "keys, stages, where things are saved",    False, 0),
    ("quit",        "Quit",                      "leave Spike",                             False, 0),
]

STAGES = (("data", "Data"), ("probe", "Probe"), ("sort", "Sort"),
          ("judge", "Judge"), ("apply", "Apply"), ("share", "Share"))
REPORTS_DIRNAME = "reports"      # reproduce match reports, under runs.regen_dir


def _mtime(path) -> "str | None":
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return None


def _rel(path) -> str:
    try:
        return Path(path).resolve().relative_to(bio.REPO_ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return Path(path).as_posix()


# --------------------------------------------------------------------------- #
# The snapshot: every fact the journey needs, read once per dashboard reload
# --------------------------------------------------------------------------- #
def snapshot(sorter: str, *, data_report: dict, pipeline=None, probe_info=None,
             built=None, rule=None) -> dict:
    data_report = data_report or {}
    files = data_report.get("files") or []
    bb = next((r for r in (pipeline or []) if "Broadband" in r.get("stage", "")), None)
    data = {
        "present": bool(data_report.get("present")),
        "complete": bool(files) and all(f.get("present") for f in files),
        "missing": [f["ext"] for f in files if not f.get("present")],
        "unreadable": bool(bb is not None and bb.get("status") == "FAIL"),
        "n_streams": sum(1 for f in files if f.get("present")),
        "base": data_report.get("base"),
        "data_dir": data_report.get("data_dir"),
        "broadband_detail": (bb or {}).get("detail", ""),
    }
    snap = {"sorter": sorter, "data": data, "probe": dict(probe_info or {}),
            "built": dict(built or {}), "run": None, "units": [], "n_units": 0,
            "n_labelled": 0, "flagged": [], "curation": None, "summary": None,
            "reproduced": [], "phy_exported": False}
    entry = runs.resolve(sorter)
    if entry is None:
        return snap
    paths = runs.sort_paths(sorter)
    info = entry.get("info") or {}
    summary = sort_summary.load_summary(paths["out"]) or {}
    noise = (summary.get("noise_floor_uV") or {}).get("median")
    snap["run"] = {
        "id": entry["id"], "smoke": bool(entry.get("smoke")), "legacy": entry.get("legacy"),
        "created": entry.get("created"), "n_units": entry.get("units"),
        "effective_seconds": info.get("effective_seconds"),
        "total_seconds": info.get("total_seconds"),
        "wall_seconds": info.get("wall_seconds"), "noise_uV": noise,
        "channel_ids": [str(c) for c in (info.get("channel_ids") or [])],
        "dir": _rel(entry["dir"]),
    }
    snap["summary"] = summary or None
    rollup = (sort_summary.unit_rollup(summary, sort_summary.load_quality_metrics(paths["out"]),
                                       rule=rule) if summary else None)
    record = curation.load_record(path=paths["record"])
    labels = {}
    for m in ((record or {}).get("curation") or {}).get("manual_labels") or []:
        q = (m.get("labels") or {}).get("quality") or []
        if q:
            labels[str(m.get("unit_id"))] = q[0]
    units = []
    for row in (rollup or {}).get("units", []):
        uid = str(row["unit"])
        units.append({"unit": uid, "contact": str(row.get("contact")),
                      "n_spikes": row.get("n_spikes"), "v_pp_uV": row.get("v_pp_uV"),
                      "snr": row.get("snr"), "strong": bool(row.get("strong")),
                      "advised": bool(row.get("split_advice")),
                      "label": labels.get(uid)})
    snap["units"] = units
    snap["n_units"] = len(units) or (entry.get("units") or 0)
    snap["n_labelled"] = sum(1 for u in units if u["label"])
    snap["flagged"] = [u["unit"] for u in units if u["advised"]]
    snap["curation"] = curation.state(sorter)
    snap["phy_exported"] = paths["phy"].is_dir() or paths["curated_phy"].is_dir()
    snap["reproduced"] = reproduce_reports(sorter, entry["id"])
    return snap


# --------------------------------------------------------------------------- #
# The rail
# --------------------------------------------------------------------------- #
def _probe_caption(probe: dict) -> str:
    summ = str(probe.get("summary") or "")
    return summ.split(" · ")[0] if summ else str(probe.get("label", ""))[:14]


def _decisions_pending(snap: dict) -> int:
    """Decisions in the record that the curated result does not yet include."""
    cur = snap.get("curation") or {}
    total = (cur.get("counts") or {}).get("total", 0)
    if not total:
        return 0
    if not cur.get("has_curated") or cur.get("stale"):
        return total
    return 0


def report_state(snap: dict) -> dict:
    """{status: fresh|stale|missing|unknown, when, note} for outputs/report.html."""
    path = bio.REPO_ROOT / "outputs" / "report.html"
    when = _mtime(path)
    if when is None:
        return {"status": "missing", "when": None, "note": "not built yet"}
    b = (snap.get("built") or {}).get("report") or {}
    run = snap.get("run") or {}
    cur = snap.get("curation") or {}
    if not b:
        return {"status": "unknown", "when": when, "note": "built outside Spike"}
    # The stamp says what Spike built; a file written after it (a CLI rebuild,
    # `run.bat report`) is something else - never vouch for it from the stamp.
    try:
        stamped = datetime.fromisoformat(str(b.get("when")))
        if datetime.fromisoformat(when) > stamped.replace(second=59):
            return {"status": "unknown", "when": when, "note": "rebuilt outside Spike"}
    except (TypeError, ValueError):
        return {"status": "unknown", "when": when, "note": "built outside Spike"}
    if b.get("sorter") != snap["sorter"] or (run and b.get("run") != run.get("id")):
        return {"status": "stale", "when": when,
                "note": f"shows {b.get('sorter')} run {str(b.get('run'))[-6:]}"}
    if (cur.get("updated") or None) != (b.get("curation_updated") or None):
        return {"status": "stale", "when": when, "note": "labels changed since it was built"}
    return {"status": "fresh", "when": when, "note": "current run"}


def stage_status(snap: dict) -> list:
    d, p, run = snap["data"], snap.get("probe") or {}, snap.get("run")
    out = []

    def add(key, mark, caption):
        n = [k for k, _ in STAGES].index(key) + 1
        out.append({"key": key, "n": n, "label": dict(STAGES)[key],
                    "mark": mark, "caption": caption})

    if not d["present"]:
        add("data", "warn", "no files")
    elif d["unreadable"]:
        add("data", "warn", ".ns5 won't load")
    elif not d["complete"]:
        add("data", "warn", "missing " + "/".join(d["missing"]))
    else:
        add("data", "done", f"{d['n_streams']} streams")

    if p.get("match") == "mismatch":
        add("probe", "warn", "wrong size")
    elif p.get("name") == "independent":
        add("probe", "warn", "placeholder")
    else:
        add("probe", "done", _probe_caption(p))

    if run is None:
        add("sort", "todo", "not sorted")
    elif run["smoke"]:
        secs = run.get("effective_seconds")
        add("sort", "warn", f"{secs:.0f} s test only" if isinstance(secs, (int, float))
            else "test only")
    else:
        add("sort", "done", f"{snap['n_units']} units")

    n, lab = snap["n_units"], snap["n_labelled"]
    if not n:
        add("judge", "todo", "")
    elif lab >= n:
        add("judge", "done", f"{lab}/{n}")
    else:
        add("judge", "todo", f"{lab}/{n}")

    pending = _decisions_pending(snap)
    cur = snap.get("curation") or {}
    if pending:
        add("apply", "warn", f"{pending} to apply")
    elif cur.get("has_curated"):
        add("apply", "done", "curated")
    else:
        add("apply", "todo", "")

    rs = report_state(snap)
    if rs["status"] == "fresh":
        add("share", "done", "report")
    elif rs["status"] in ("stale", "unknown") and run:
        add("share", "warn", "report stale" if rs["status"] == "stale" else "check report")
    else:
        add("share", "todo", "")
    return out


# --------------------------------------------------------------------------- #
# The next step
# --------------------------------------------------------------------------- #
def _contacts_text(contacts) -> str:
    uniq = []
    for c in contacts:
        if c not in uniq:
            uniq.append(c)
    return " · ".join(uniq)


def next_steps(snap: dict) -> list:
    """Every sensible next move, best first. The card shows the first; `s not now`
    steps through the rest. Each: title, detail, action (an app action key), label
    (the button text), stage (1-6)."""
    d, p, run = snap["data"], snap.get("probe") or {}, snap.get("run")
    steps = []

    def add(title, detail, action, label, stage):
        steps.append({"title": title, "detail": detail, "action": action,
                      "label": label, "stage": stage})

    if not d["present"] or not d["complete"] or d["unreadable"]:
        add("Add the recording",
            "Spike needs one Blackrock set: the .ns5 to sort, plus .ns2 and .nev.",
            "stage:1", "show me where the files go", 1)
    if p.get("match") == "mismatch":
        add("Fix the probe geometry",
            p.get("match_detail") or "the probe's contact count does not match the recording",
            "stage:2", "open 2 Probe", 2)
    if d["present"] and d["complete"]:
        if run is None:
            add("Sort the recording", "Find the units in the broadband signal.",
                "sort", "sort the full recording", 3)
        elif run["smoke"]:
            add("Sort the full recording",
                "Only a quick test sort exists; it never counts as the result.",
                "sort", "sort the full recording", 3)
    n, lab, flagged = snap["n_units"], snap["n_labelled"], snap["flagged"]
    real = bool(run) and not run["smoke"]      # a test sort is never the result
    if real and n and lab < n:
        rest = n - lab
        detail = (f"{len(flagged)} flagged as likely two cells come first."
                  if flagged else "Label each good, multi-unit or noise, one key per unit.")
        add(f"Judge the {'remaining ' if lab else ''}{rest} unit{'s' if rest != 1 else ''}",
            detail, "stage:4", "start judging", 4)
    pending = _decisions_pending(snap)
    if pending:
        add(f"Apply your {pending} decision{'s' if pending != 1 else ''}",
            "Builds the curated result beside the raw sort and re-scores it.",
            "apply", "apply them", 5)
    rs = report_state(snap)
    if real and rs["status"] != "fresh":
        add("Build the report", "One HTML page: units, quality, provenance.",
            "report", "build the report", 6)
    if real and flagged and not snap.get("phy_exported"):
        contacts = [u["contact"] for u in snap["units"] if u["advised"]]
        add("Split the merged pairs in Phy",
            f"Units on contacts {_contacts_text(contacts)} fire at impossible intervals: "
            "likely two cells each. Phy is where you split them.",
            "phy", f"export {len(flagged)} flagged unit{'s' if len(flagged) != 1 else ''} "
            "to Phy", 6)
    if real and not snap.get("reproduced"):
        add("Check this run reproduces",
            "Re-run it from its own recipe and compare every value.",
            "reproduce", "reproduce the values", 6)
    if not steps:
        add("Everything is up to date", "Open the report, or share it.",
            "open:report", "open the report", 6)
    return steps


# --------------------------------------------------------------------------- #
# The probe map
# --------------------------------------------------------------------------- #
def _channel_key(c):
    try:
        return (0, float(c))
    except (TypeError, ValueError):
        return (1, str(c))


def probe_map(snap: dict) -> dict:
    """{contacts: [channel ids, top of the shank first], units: {ch: [unit rows]}}.

    Contacts come from the sorted channels of the current run (identity wiring, the
    standing assumption), else from the units' own contacts; the tip is the lowest
    channel id."""
    run = snap.get("run") or {}
    contacts = list(run.get("channel_ids") or [])
    by = {}
    for u in snap.get("units") or []:
        by.setdefault(u["contact"], []).append(u)
        if u["contact"] not in contacts:
            contacts.append(u["contact"])
    contacts = sorted(set(contacts), key=_channel_key, reverse=True)
    for ch in by:
        by[ch].sort(key=lambda u: -(u.get("v_pp_uV") or 0))
    return {"contacts": contacts, "units": by}


# --------------------------------------------------------------------------- #
# Recent activity
# --------------------------------------------------------------------------- #
def recent(snap: dict, limit: int = 5) -> list:
    sorter = snap["sorter"]
    current = (snap.get("run") or {}).get("id")
    items = []
    for r in runs.list_runs(sorter):
        if not r.get("created"):
            continue
        info = r.get("info") or {}
        n = r.get("units")
        if r.get("smoke"):
            secs = info.get("effective_seconds")
            what = f"{secs:.0f} s test sort" if isinstance(secs, (int, float)) else "test sort"
        else:
            what = "full sort"
        tail = "current" if r["id"] == current else (
            "kept off current" if r.get("smoke") else "kept")
        items.append((r["created"], f"{what} · {n if n is not None else '?'} units · {tail}"))
    cur = snap.get("curation") or {}
    if cur.get("has_curated") and cur.get("updated"):
        c = (cur.get("counts") or {}).get("total", 0)
        items.append((cur["updated"], f"{c} decision{'s' if c != 1 else ''} applied · "
                                      "curated result re-scored"))
    for key, b in (snap.get("built") or {}).items():
        if isinstance(b, dict) and b.get("when"):
            items.append((b["when"], f"{key} built"))
    for rep in snap.get("reproduced") or []:
        items.append((rep["when"], f"reproduced run {rep['run'][-6:]} · {rep['verdict']}"))
    items.sort(key=lambda t: t[0], reverse=True)
    # One line per kind of event (the newest): five test sorts in a row are one
    # fact, and they must not push the curation or a build off the list.
    seen, out = set(), []
    for w, t in items:
        kind = t.split(" · ")[0]
        if kind in seen:
            continue
        seen.add(kind)
        out.append({"when": w, "text": t})
    return out[:limit]


# --------------------------------------------------------------------------- #
# Share: every output and how fresh it is
# --------------------------------------------------------------------------- #
def outputs(snap: dict) -> list:
    sorter, run = snap["sorter"], snap.get("run")
    out_dir = bio.REPO_ROOT / "outputs"
    rows = []

    def add(key, title, path, status, note):
        rows.append({"key": key, "title": title, "path": _rel(path) if path else "",
                     "exists": bool(path) and Path(path).exists(), "status": status,
                     "note": note})

    rs = report_state(snap)
    add("report", "Report", out_dir / "report.html", rs["status"], rs["note"])
    for key, title, name in (("compare", "Comparison", "comparison.html"),
                             ("sweep", "Sorter shootout", "sweep.html"),
                             ("explore", "Recording overview", "explore.html")):
        p = out_dir / name
        when = _mtime(p)
        add(key, title, p, "present" if when else "missing",
            f"built {when[:16].replace('T', ' ')}" if when else "not built yet")
    if run:
        paths = runs.sort_paths(sorter)
        cur = snap.get("curation") or {}
        phy = paths["curated_phy"] if cur.get("has_curated") else paths["phy"]
        n_flag = len(snap.get("flagged") or [])
        if phy.is_dir():
            add("phy", "Phy export", phy, "warn" if n_flag else "present",
                f"{n_flag} flagged units to split there" if n_flag else "exported")
        else:
            add("phy", "Phy export", phy, "missing",
                f"export {n_flag} flagged units" if n_flag else "not exported")
        add("gui", "Inspect in the GUI", None, "present", "waveforms + correlograms window")
        metrics = paths["curated_metrics"] if cur.get("has_curated") else paths["metrics"]
        add("values", "Values (CSV)", metrics, "present" if metrics.exists() else "missing",
            "every unit's metrics, plus summary.csv")
        reps = snap.get("reproduced") or []
        add("reproduce", "Reproduce this run", None,
            "present" if reps else "missing",
            f"last check: {reps[0]['verdict']}" if reps else "not checked yet")
        recipe = recipe_path(sorter, run["id"])
        add("recipe", "Run recipe", recipe, "present" if recipe.exists() else "missing",
            "the file that re-runs this sort anywhere")
    deck = out_dir / "lab_meeting_deck.pptx"
    if deck.exists():
        add("deck", "Lab deck", deck, "present", f"built {(_mtime(deck) or '')[:10]}")
    return rows


# --------------------------------------------------------------------------- #
# Runs & reproducibility
# --------------------------------------------------------------------------- #
def recipe_path(sorter: str, run_id: str) -> Path:
    return bio.REPO_ROOT / "outputs" / "recipes" / f"{sorter}-{run_id}.json"


def reproduce_report_path(sorter: str, run_id: str, when=None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return runs.regen_dir(sorter) / REPORTS_DIRNAME / f"{run_id}__{stamp}.json"


def reproduce_reports(sorter: str, run_id: str) -> list:
    """Every stored match report for ``run_id``, newest first:
    [{path, when, run, verdict, failed}]."""
    d = runs.regen_dir(sorter) / REPORTS_DIRNAME
    out = []
    for p in sorted(d.glob(f"{run_id}__*.json"), reverse=True) if d.is_dir() else []:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a half-written report is not a verdict
            continue
        rep = data.get("report") or {}
        stamp = p.stem.split("__", 1)[-1]
        try:
            when = datetime.strptime(stamp, "%Y%m%d-%H%M%S").isoformat(timespec="seconds")
        except ValueError:
            when = _mtime(p)
        out.append({"path": str(p), "when": when, "run": run_id,
                    "verdict": rep.get("verdict") or "no comparison",
                    "failed": rep.get("failed") or [], "data": data})
    return out


def runs_overview(sorter: str) -> list:
    current = (runs.resolve(sorter) or {}).get("id")
    rows = []
    for r in runs.list_runs(sorter):
        info = r.get("info") or {}
        summ = sort_summary.load_summary(r["dir"]) or {}
        reps = reproduce_reports(sorter, r["id"])
        rows.append({
            "id": r["id"], "created": r.get("created"), "smoke": bool(r.get("smoke")),
            "legacy": bool(r.get("legacy")), "units": r.get("units"),
            "current": r["id"] == current,
            "seconds": info.get("effective_seconds"),
            "noise_uV": (summ.get("noise_floor_uV") or {}).get("median"),
            "reproduced": reps[0]["verdict"] if reps else None,
            "dir": _rel(r["dir"]),
        })
    return rows


def recipe(sorter: str, run_id: str) -> dict:
    """What a run's recipe says, as display rows + the committable config."""
    info = runs.read_json(runs.sort_paths(sorter, run=run_id)["run_info"])
    if not info:
        return {"config": None, "rows": []}
    cfg = runs.config_from_record(info)
    params = (info.get("params") or {})
    overrides = params.get("overrides") or {}
    pk = info.get("packages") or {}
    git = info.get("git") or {}
    seed = info.get("seed") or {}
    det = info.get("determinism") or {}
    bad = info.get("bad_channels") or {}
    rows = [
        ("Sorter", f"{info.get('sorter')}  ({det.get('class', 'determinism unverified')})"),
        ("Parameters", f"{len(params.get('effective') or {})} effective · "
                       f"{len(overrides)} changed from default"
                       + (": " + ", ".join(f"{k}={v}" for k, v in list(overrides.items())[:3])
                          if overrides else "")),
        ("Seed", f"{seed.get('key')} = {seed.get('value')}" if seed.get("key") else "none"),
        ("Probe", f"{info.get('probe_id')} · geometry {info.get('geometry_hash')}"),
        ("Signal", f"band-pass {info.get('freq_min'):g}-{info.get('freq_max'):g} Hz · "
                   f"common median reference · bad channels "
                   f"{', '.join(map(str, bad.get('excluded') or [])) or 'none'}"
                   if isinstance(info.get("freq_min"), (int, float))
                   and isinstance(info.get("freq_max"), (int, float)) else "-"),
        ("Recording", f"{(info.get('recording') or {}).get('base')} · "
                      f"{info.get('effective_seconds')} s"),
        ("Software", " · ".join(f"{k} {v}" for k, v in pk.items() if v)),
        ("Code", f"git {str(git.get('sha') or '?')[:10]}"
                 + (" (uncommitted changes)" if git.get("dirty") else "")),
    ]
    return {"config": cfg, "rows": rows}
