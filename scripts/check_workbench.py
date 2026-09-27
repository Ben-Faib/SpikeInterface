#!/usr/bin/env python
"""The confidence harness: drive every workbench function against the real recording.

    uv run python scripts/check_workbench.py                    # every function, quick sorts
    uv run python scripts/check_workbench.py --full             # full-length sorts instead
    uv run python scripts/check_workbench.py --only judge       # one step (+ the steps it needs)
    uv run python scripts/check_workbench.py --data-dir D:\\rec  # a recording elsewhere
    uv run python scripts/check_workbench.py --keep             # keep the sandbox to look inside
    REM Windows: the same lines - this is the lab box's acceptance test

What it proves: that a researcher can do everything Spike offers, end to end, on
this computer - install check, finding the recording, the probe (fit, create,
activate, import), every setting reaching the sort, a real sort with the ~4 µV
noise-floor canary, explore, judging units with their evidence, applying the
decisions, the report, the Phy export, a two-sorter comparison, reproducing a run
from its recipe, exporting the recipe, the run store's smoke rule, and the app
itself drawing every pane. Every step goes through the same controller
(``SpikeInterface_Menu.MenuController``) and the same child-process commands the
app runs, so a PASS here means the button works, not that a unit test does.

It never touches your real state. The harness copies ``scripts/`` and
``SpikeInterface_Menu.py`` into a throwaway temp folder (the sandbox), writes a
sandbox ``.si_menu.json`` whose ``data_dir`` points at the recording (read in
place, never copied or linked), and re-runs itself from the sandbox copy. There,
``blackrock_io.REPO_ROOT`` is the sandbox, so every output, setting, probe and
curation record lands under the sandbox and is deleted at the end (``--keep``
keeps it; its path is printed either way). As a last line it proves the point:
your real ``outputs/``, ``.si_menu.json`` and ``probes.json`` are byte-for-byte
where they were (all three are git-ignored, so ``git status`` could not tell you).

Each line is one function::

    PASS     sort        31.2s  tridesclous2 run ...: 14 units · noise floor 3.97 µV ...
    status   step        time   the evidence (a number, a path)

    PASS     it works, and the evidence says why you can believe it
    FAIL     it does not; the error and the tail of its log follow the line
    MANUAL   a desktop window a person has to look at; the line says what to click
             (the libraries it needs were checked automatically)
    SKIPPED  not run because a step it needs did not pass (named on the line)

The exit code is 0 only when nothing FAILed. ``--only`` takes a comma list of step
names (install, data, probe, settings, sort, explore, judge, apply, report, phy,
compare, reproduce, recipe, runs, app, gui) and also runs whatever those steps
need - the sandbox starts empty, so judging needs a sort first.

Windows notes: no symlinks anywhere, pathlib throughout, children started with
``sys.executable`` and never through a shell, UTF-8 output forced.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import blackrock_io as bio  # noqa: E402  (REPO_ROOT + UTF-8 output; no SpikeInterface)

INNER_FLAG = "--_inner"
LAUNCHER = "SpikeInterface_Menu.py"
SANDBOX_MARKER = ".spike-check-sandbox"   # the inner run refuses to start without it
RESULTS_NAME = "check_results.json"
STATE_FILES = (".si_menu.json", "probes.json")
# The two quickest internal sorters here (saved 30 s smokes: simple ~13 s, lupin ~28 s).
FAST_SORTERS = ("simple", "lupin")
NOISE_CANARY_UV = (3.5, 4.5)   # CLAUDE.md: ~4 µV for every sorter; ~1 µV = gain applied twice
QUICK_TEST_SECONDS = 20
CHILD_TIMEOUT_S = 3600
TAIL_LINES = 12

# (name, the steps it needs) in the journey's order.
STEPS = [
    ("install", ()), ("data", ()), ("probe", ("data",)), ("settings", ()),
    ("sort", ("data", "settings")), ("explore", ("data",)), ("judge", ("sort",)),
    ("apply", ("judge",)), ("report", ("apply",)), ("phy", ("sort",)),
    ("compare", ("sort",)), ("reproduce", ("sort",)), ("recipe", ("sort",)),
    ("runs", ("sort",)), ("app", ()), ("gui", ()),
]
NEEDS = dict(STEPS)


# --------------------------------------------------------------------------- #
# The sandbox and the real-state proof (outer process; stdlib only)
# --------------------------------------------------------------------------- #
def snapshot_state(root) -> dict:
    """Fingerprint of the real state the harness promises not to touch: the two
    settings files by content hash, every path under outputs/ by size + mtime."""
    root = Path(root)
    state = {}
    for name in STATE_FILES:
        p = root / name
        state[name] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    out = root / "outputs"
    if out.is_dir():
        for p in out.rglob("*"):
            try:
                st = p.stat()
            except OSError:
                continue
            key = p.relative_to(root).as_posix()
            state[key] = "dir" if p.is_dir() else (st.st_size, st.st_mtime_ns)
    return state


def state_changes(before: dict, after: dict) -> list:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def build_sandbox(repo_root, data_dir, parent=None) -> Path:
    """A throwaway copy of the code (never the data) whose REPO_ROOT is itself."""
    repo_root = Path(repo_root).resolve()
    box = Path(tempfile.mkdtemp(prefix="spike-check-", dir=parent)).resolve()
    if box == repo_root or repo_root in box.parents:
        shutil.rmtree(box, ignore_errors=True)
        raise RuntimeError(f"refusing a sandbox inside the repo: {box}")
    shutil.copytree(repo_root / "scripts", box / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(repo_root / LAUNCHER, box / LAUNCHER)
    (box / "outputs").mkdir()
    (box / ".si_menu.json").write_text(
        json.dumps({"data_dir": str(Path(data_dir).expanduser().resolve())}, indent=2),
        encoding="utf-8")
    (box / SANDBOX_MARKER).write_text(f"copied from {repo_root}\n", encoding="utf-8")
    return box


def remove_sandbox(box) -> bool:
    def _force(func, path, _exc):          # read-only files block rmtree on Windows
        os.chmod(path, stat.S_IWRITE)
        func(path)
    try:
        shutil.rmtree(box, onexc=_force)
    except OSError:
        return False
    return True


def _child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _line(status: str, name: str, secs: float, evidence: str) -> str:
    return f"  {status:<8} {name:<10} {secs:6.1f}s  {evidence}"


def _selected(only: "str | None") -> list:
    """The steps to run: all, or the named ones plus everything they need."""
    if not only:
        return [n for n, _ in STEPS]
    want = {w.strip() for w in only.split(",") if w.strip()}
    unknown = want - set(NEEDS)
    if unknown:
        raise SystemExit(f"unknown step(s): {', '.join(sorted(unknown))} - "
                         f"choose from {', '.join(NEEDS)}")
    todo = list(want)
    while todo:
        for dep in NEEDS[todo.pop()]:
            if dep not in want:
                want.add(dep)
                todo.append(dep)
    return [n for n, _ in STEPS if n in want]


def outer(args) -> int:
    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else ROOT
    _selected(args.only)                       # a typo fails before any work
    t0 = time.monotonic()
    before = snapshot_state(ROOT)
    box = build_sandbox(ROOT, data_dir)
    print(f"Spike workbench check · {time.strftime('%Y-%m-%d %H:%M')} · "
          f"{platform.platform(terse=True)} · Python {platform.python_version()}")
    print(f"  recording  {data_dir}")
    print(f"  sandbox    {box}")
    print("             (a throwaway copy of the code: your outputs, settings, probes and "
          "curation records are never touched)\n", flush=True)
    argv = [sys.executable, str(box / "scripts" / Path(__file__).name), INNER_FLAG]
    if args.only:
        argv += ["--only", args.only]
    if args.full:
        argv += ["--full"]
    rc = subprocess.run(argv, cwd=box, stdin=subprocess.DEVNULL, env=_child_env()).returncode
    try:
        results = json.loads((box / RESULTS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        results = []
    if rc not in (0, 1) or not results:
        results.append({"name": "harness", "status": "FAIL", "secs": 0.0,
                        "evidence": f"the check run itself stopped (exit {rc}) - see above"})
        print(_line("FAIL", "harness", 0.0, results[-1]["evidence"]))

    t = time.monotonic()
    changed = state_changes(before, snapshot_state(ROOT))
    n_out = sum(1 for k in before if k.startswith("outputs/"))
    if changed:
        iso = ("FAIL", f"real state changed during the run: {', '.join(changed[:3])}"
               + (f" (+{len(changed) - 3} more)" if len(changed) > 3 else "")
               + " - if another program was writing there, re-run to confirm")
    else:
        iso = ("PASS", f"your outputs/ ({n_out} entries), .si_menu.json and probes.json "
                       "are exactly as they were")
    results.append({"name": "isolation", "status": iso[0], "secs": time.monotonic() - t,
                    "evidence": iso[1]})
    print(_line(iso[0], "isolation", results[-1]["secs"], iso[1]))

    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in ("PASS", "FAIL", "MANUAL", "SKIPPED")}
    total = time.monotonic() - t0
    print("\n  " + " · ".join(f"{n} {s}" for s, n in counts.items())
          + f"   in {int(total // 60)}m{int(total % 60):02d}s")
    if args.keep:
        print(f"  sandbox kept at {box}")
    elif remove_sandbox(box):
        print(f"  sandbox removed ({box})")
    else:
        print(f"  ! could not fully remove the sandbox - delete it by hand: {box}")
    if counts["FAIL"]:
        print("  RESULT: FAIL - the lines marked FAIL above say what broke and why.")
        return 1
    print("  RESULT: PASS - every automatic check passed"
          + (f"; {counts['MANUAL']} line(s) need a person (MANUAL above)."
             if counts["MANUAL"] else "."))
    return 0


# --------------------------------------------------------------------------- #
# The checks (inner process, running from the sandbox copy)
# --------------------------------------------------------------------------- #
class Fail(Exception):
    def __init__(self, message: str, log=None):
        super().__init__(message)
        self.log = log


class Ctx:
    def __init__(self, controller, full: bool):
        self.c = controller
        self.full = full
        self.span = None if full else "quick"
        self.n_neural = None
        self.sort = None          # the first sort's result (sort_active)


def _rel(path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _has_pair(argv, flag: str, value: str) -> bool:
    return any(a == flag and b == value for a, b in zip(argv, argv[1:]))


def run_child(argv, log, *, json_events: bool = False):
    """Run one of the app's child commands with its output in ``log``.
    json_events: read stdout as the sort_progress protocol -> (rc, events, stray)."""
    import sort_progress

    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8") as fh:
        if not json_events:
            p = subprocess.run([str(a) for a in argv], stdout=fh, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, cwd=ROOT, env=_child_env(),
                               timeout=CHILD_TIMEOUT_S)
            return p.returncode, [], []
        proc = subprocess.Popen([str(a) for a in argv], stdout=subprocess.PIPE, stderr=fh,
                                stdin=subprocess.DEVNULL, cwd=ROOT, env=_child_env(),
                                text=True, encoding="utf-8", errors="replace")
        timer = threading.Timer(CHILD_TIMEOUT_S, proc.kill)
        timer.start()
        events, stray = [], []
        try:
            for raw in proc.stdout:
                ev = sort_progress.parse_line(raw)
                if ev is not None:
                    events.append(ev)
                elif raw.strip():
                    stray.append(raw.rstrip())
            rc = proc.wait()
        finally:
            timer.cancel()
        return rc, events, stray


def _terminal(events) -> dict:
    return next((e for e in reversed(events) if e.get("t") in ("done", "error")), {})


def _canary(noise, what: str, log=None) -> None:
    lo, hi = NOISE_CANARY_UV
    if not isinstance(noise, (int, float)):
        raise Fail(f"{what}: no noise floor in its summary", log)
    if not lo <= noise <= hi:
        hint = " - ~1 µV means the 0.25 µV/count gain was applied twice" if noise < 2 else ""
        raise Fail(f"{what}: noise floor {noise:.2f} µV is outside the "
                   f"{lo:g}-{hi:g} µV canary{hint}", log)


def _run_command(ctx, key: str, run_id=None) -> dict:
    """An app command exactly as the app runs it: command() -> child -> finish_command()."""
    cmd = ctx.c.command(key, run_id) if run_id else ctx.c.command(key)
    rc, _, _ = run_child(cmd["argv"], cmd["log"])
    ctx.c.finish_command(key, rc == 0)
    if rc != 0:
        raise Fail(f"{cmd['title']} exited {rc}", cmd["log"])
    return cmd


def sort_active(ctx) -> dict:
    """One sort of the active sorter, started exactly as the app starts it."""
    import runs
    import sort_summary

    c = ctx.c
    argv = c.sort_command(ctx.span)
    log = c.sort_log_path(ctx.span)
    rc, events, stray = run_child(argv, log, json_events=True)
    end = _terminal(events)
    if rc != 0 or not end.get("ok"):
        raise Fail(f"{c.active_sorter} sort exited {rc}: "
                   f"{end.get('message') or 'no done event'}", log)
    if stray:
        raise Fail(f"--progress json stdout is not pure: {len(stray)} non-event line(s), "
                   f"first: {stray[0][:100]!r}", log)
    out = Path(end["out"])
    out = out if out.is_absolute() else ROOT / out
    summary = sort_summary.load_summary(out) or {}
    info = runs.read_json(out / "run_info.json")
    c.reload()
    return {"sorter": c.active_sorter, "out": out, "units": end.get("units"), "log": log,
            "noise": (summary.get("noise_floor_uV") or {}).get("median"), "info": info,
            "run_id": info.get("run_id"), "argv": argv}


def check_install(ctx):
    from importlib.metadata import version

    _run_command(ctx, "verify")
    return "PASS", (f"verify_install passed · spikeinterface {version('spikeinterface')} · "
                    f"Python {platform.python_version()} on {platform.system()}")


def check_data(ctx):
    c = ctx.c
    dr = c.data_report or {}
    if not dr.get("present"):
        raise Fail(dr.get("error") or f"no recording found in {dr.get('data_dir')}")
    missing = [f["ext"] for f in dr["files"] if not f["present"]]
    if missing:
        raise Fail(f"{dr['base']} is missing {', '.join(missing)} in {dr['data_dir']}")
    rec = bio.read_broadband(dr["data_dir"], attach_probe=False)
    neural = list(bio.neural_channel_ids(rec))
    lfp = bio.read_lfp(dr["data_dir"])
    spikes = bio.read_spikes(dr["data_dir"])
    ctx.n_neural = len(neural)
    shown = c.recording_channels()
    if shown != len(neural):
        raise Fail(f"the app reads {shown} neural channels, the loader {len(neural)}")
    return "PASS", (f"{dr['base']}: .ns2 .ns5 .nev all read · {len(neural)} neural + "
                    f"{rec.get_num_channels() - len(neural)} aux channels · "
                    f"{rec.get_total_duration():.1f} s @ {rec.get_sampling_frequency() / 1000:g} kHz"
                    f" · LFP @ {lfp.get_sampling_frequency():g} Hz · .nev {spikes.get_num_units()}"
                    " unit ids")


def check_probe(ctx):
    import probeinterface as pif
    import probes

    c = ctx.c
    fits = ("fits", "auto")
    orig = c.active_probe
    info = c.probe_info or {}
    if info.get("match") not in fits:
        raise Fail(f"the active probe {orig} does not fit: {info.get('match_detail')}")
    n = ctx.n_neural
    mine = {"name": "check-linear", "label": f"Harness linear {n} @ 100 um",
            "kind": "linear", "params": {"n": n, "pitch_um": 100.0}}
    ok, msg = c.save_probe(mine)
    stored = json.loads(probes.PROBES_PATH.read_text(encoding="utf-8")) if ok else {}
    if not ok or mine["name"] not in [p.get("name") for p in stored.get("profiles", [])]:
        raise Fail(f"save_probe: {msg}")
    if not c.set_active_probe(mine["name"]) or c.active_probe != mine["name"]:
        raise Fail(f"could not activate {mine['name']}")
    saved_cfg = json.loads((ROOT / ".si_menu.json").read_text(encoding="utf-8"))
    if saved_cfg.get("active_probe") != mine["name"] or c.probe_info.get("match") not in fits:
        raise Fail(f"{mine['name']} active but not saved/fitting: {c.probe_info}")
    drawn = len(c.probe_detail(mine["name"]).get("positions") or [])
    if drawn != n:
        raise Fail(f"{mine['name']} draws {drawn} contacts, expected {n}")
    src = ROOT / "outputs" / "check-import.json"
    pr = pif.generate_linear_probe(num_elec=n, ypitch=50)
    pr.set_device_channel_indices(list(range(n)))
    pif.write_probeinterface(src, pr)
    ok, msg = c.import_probe(str(src))
    imported = probes.get("check-import")
    if not ok or imported is None or imported.get("kind") != "imported":
        raise Fail(f"import_probe: {msg}")
    imp = c.probe_detail("check-import")
    if imp.get("match") not in fits:
        raise Fail(f"the imported probe does not fit: {imp.get('match_detail')}")
    if not c.set_active_probe(orig) or c.active_probe != orig:
        raise Fail(f"could not switch back to {orig}")
    return "PASS", (f"{orig} fits ({info.get('match_detail')}) · saved, activated and "
                    f"switched back from {mine['name']} · imported a probeinterface .json "
                    f"as check-import ({len(imp.get('positions') or [])} contacts, {imp['match']})")


def check_settings(ctx):
    import run_sorting
    import settings

    c = ctx.c
    alt = next(m for m in run_sorting.BAD_CHANNEL_METHODS
               if m != run_sorting.DEFAULT_BAD_CHANNEL_METHOD)
    for key, value in (("freq_min", "250"), ("quick_seconds", str(QUICK_TEST_SECONDS)),
                       ("bad_channel_method", alt)):
        ok, msg = c.set_setting(key, value)
        if not ok:
            raise Fail(f"set_setting({key}={value}) refused: {msg}")
    bad = [("freq_min", "abc"), ("freq_min", "7000"), ("bad_channel_method", "bogus"),
           ("quick_seconds", "2.5")]
    accepted = [f"{k}={v}" for k, v in bad if c.set_setting(k, v)[0]]
    if accepted:
        raise Fail(f"invalid values were accepted: {', '.join(accepted)}")
    disk = json.loads((ROOT / ".si_menu.json").read_text(encoding="utf-8"))
    box = disk.get("sort_settings") or {}
    if (box.get("freq_min"), box.get("quick_seconds"), box.get("bad_channel_method")) != (
            250.0, QUICK_TEST_SECONDS, alt):
        raise Fail(f".si_menu.json does not hold the edits: {box}")
    row = next(r for r in c.settings_rows() if r["key"] == "freq_min")
    if row["value"] != "250" or row["is_default"]:
        raise Fail(f"the Settings row does not show the edit: {row}")
    argv = c.sort_command("quick")
    want = [("--freq-min", "250"), ("--freq-max", f"{settings.get(c.cfg, 'freq_max'):g}"),
            ("--bad-channel-method", alt), ("--duration", str(QUICK_TEST_SECONDS)),
            ("--n-jobs", str(settings.get(c.cfg, "n_jobs"))), ("--probe", c.active_probe),
            ("--progress", "json"), ("--data-dir", str(c.args.data_dir))]
    absent = [f"{f} {v}" for f, v in want if not _has_pair(argv, f, v)]
    if absent:
        raise Fail(f"the sort argv lacks {', '.join(absent)}: {' '.join(map(str, argv))}")
    for key in ("freq_min", "bad_channel_method"):   # back to defaults: a representative sort
        ok, msg = c.reset_setting(key)
        if not ok:
            raise Fail(f"reset_setting({key}): {msg}")
    argv = c.sort_command("quick")
    if not (_has_pair(argv, "--freq-min", "300")
            and _has_pair(argv, "--bad-channel-method", run_sorting.DEFAULT_BAD_CHANNEL_METHOD)):
        raise Fail(f"after reset the argv still carries the edits: {' '.join(map(str, argv))}")
    return "PASS", (f"3 edits saved to .si_menu.json and shown · {len(bad)} invalid values "
                    f"refused · the sort argv carried all {len(want)} flags · band-pass low and "
                    f"method reset to default, quick-test length stays {QUICK_TEST_SECONDS} s")


def check_sort(ctx):
    import settings

    c = ctx.c
    t = time.monotonic()
    r = sort_active(ctx)
    info = r["info"]
    if not r["units"]:
        raise Fail(f"{r['sorter']} found 0 units", r["log"])
    _canary(r["noise"], f"{r['sorter']} sort", r["log"])
    want_fmin = settings.get(c.cfg, "freq_min")
    problems = []
    if info.get("freq_min") != want_fmin:
        problems.append(f"freq_min {info.get('freq_min')} (settings say {want_fmin:g})")
    if info.get("probe_id") != c.active_probe:
        problems.append(f"probe_id {info.get('probe_id')} (active {c.active_probe})")
    eff = info.get("effective_seconds")
    if not ctx.full and not (isinstance(eff, (int, float))
                             and abs(eff - c.quick_seconds) < 0.5):
        problems.append(f"effective_seconds {eff} (quick-test length {c.quick_seconds})")
    if problems:
        raise Fail("run_info.json does not record the settings: " + "; ".join(problems), r["log"])
    ctx.sort = r
    return "PASS", (f"{r['sorter']} run {r['run_id']}: {r['units']} units · noise floor "
                    f"{r['noise']:.2f} µV (canary {NOISE_CANARY_UV[0]:g}-{NOISE_CANARY_UV[1]:g}) · "
                    f"run_info: {eff:g} s, band-pass {info.get('freq_min'):g}-"
                    f"{info.get('freq_max'):g} Hz, probe {info.get('probe_id')} · "
                    f"sort took {time.monotonic() - t:.0f} s")


def check_explore(ctx):
    _run_command(ctx, "explore")
    page = ROOT / "outputs" / "explore.html"
    if not page.is_file():
        raise Fail("explore ran but wrote no outputs/explore.html", ctx.c.log_path("explore"))
    return "PASS", f"outputs/explore.html ({page.stat().st_size / 1e6:.1f} MB)"


def check_judge(ctx):
    import curation

    c = ctx.c
    st = c.triage_state()
    if st.get("blocked"):
        raise Fail(st["blocked"])
    units = st["units"]
    if not units:
        raise Fail(st.get("empty") or "the Judge queue is empty")
    picks = list(zip([u["unit"] for u in units[:2]], ("good", "MUA")))
    for uid, label in picks:
        ok, msg = c.label_unit(uid, label)
        if not ok:
            raise Fail(f"label_unit({uid}, {label}): {msg}")
    record = curation.load_record(c.active_sorter)
    wrong = [f"{u}={curation.label_of(record, u)}" for u, lab in picks
             if curation.label_of(record, u) != lab]
    if wrong:
        raise Fail(f"the curation record does not hold the labels: {', '.join(wrong)}")
    u = max(units, key=lambda x: x.get("n_spikes") or 0)   # the busiest unit: a full ISI
    ev = c.unit_evidence(u["unit"])
    if not ev or not ev.get("waveforms") or not (ev.get("isi") or {}).get("counts"):
        raise Fail(f"unit {u['unit']}: no waveform/ISI evidence ({sorted(ev or {})})")
    wf = ev["waveforms"]
    peak = wf.get(str(ev.get("peak_channel"))) or max(wf.values(), key=lambda w: max(w) - min(w))
    p2p = max(peak) - min(peak)
    vpp = u.get("v_pp_uV")
    if not isinstance(vpp, (int, float)) or vpp <= 0 or not 0.1 <= p2p / vpp <= 10:
        raise Fail(f"unit {u['unit']}: waveform {p2p:.1f} µV p-p vs V_pp {vpp} µV - "
                   "not the same scale")
    return "PASS", (f"{len(units)} units in the queue · labelled "
                    + ", ".join(f"{uid}={lab}" for uid, lab in picks)
                    + f" in the curation record · unit {u['unit']}: {len(wf)} channels of "
                    f"waveform, {sum(ev['isi']['counts'])} ISIs under {ev['isi']['max_ms']:g} ms, "
                    f"{p2p:.0f} µV p-p vs V_pp "
                    f"{vpp:.0f} µV")


def check_apply(ctx):
    import curation
    import runs
    import sort_summary

    c = ctx.c
    cmd = _run_command(ctx, "apply")
    paths = runs.sort_paths(c.active_sorter)
    if not paths["curated_analyzer"].is_dir():
        raise Fail("apply ran but built no curated analyzer", cmd["log"])
    summ = sort_summary.load_summary(paths["curated"]) or {}
    noise = (summ.get("noise_floor_uV") or {}).get("median")
    _canary(noise, "curated result", cmd["log"])
    st = curation.state(c.active_sorter)
    if not st.get("has_curated") or st.get("stale"):
        raise Fail(f"curation state after apply: {st.get('line')} "
                   f"(stale: {st.get('stale_reason')})", cmd["log"])
    return "PASS", (f"curated result built in {_rel(paths['curated'])} · curated noise floor "
                    f"{noise:.2f} µV · {st.get('line')}")


def check_report(ctx):
    c = ctx.c
    rc, events, stray = run_child(c.report_command(), c.report_log_path(), json_events=True)
    end = _terminal(events)
    ok = rc == 0 and bool(end.get("ok"))
    c.record_result("report", ok)
    if not ok:
        raise Fail(f"report exited {rc}: {end.get('message') or 'no done event'}",
                   c.report_log_path())
    if stray:
        raise Fail(f"report --progress json stdout is not pure: {stray[0][:100]!r}",
                   c.report_log_path())
    page = ROOT / "outputs" / "report.html"
    if not page.is_file():
        raise Fail("no outputs/report.html", c.report_log_path())
    if f"curated from the {c.active_sorter} run" not in page.read_text(encoding="utf-8"):
        raise Fail("outputs/report.html does not say it shows the curated result",
                   c.report_log_path())
    return "PASS", (f"outputs/report.html ({page.stat().st_size / 1e6:.1f} MB) says: "
                    f"curated from the {c.active_sorter} run")


def check_phy(ctx):
    import runs

    cmd = _run_command(ctx, "phy")
    paths = runs.sort_paths(ctx.c.active_sorter)
    folder = next((d for d in (paths["curated_phy"], paths["phy"])
                   if (d / "params.py").is_file()), None)
    if folder is None:
        raise Fail("the Phy export wrote no params.py", cmd["log"])
    kind = "curated" if folder == paths["curated_phy"] else "raw"
    return "PASS", (f"{_rel(folder)} ({sum(1 for _ in folder.iterdir())} files, the {kind} "
                    "sort) ready for Phy")


def check_compare(ctx):
    c = ctx.c
    first = c.active_sorter
    second = next((s for s in (*FAST_SORTERS, *c.sorters) if s in c.sorters and s != first),
                  None)
    if second is None:
        raise Fail(f"only one sorter is runnable here ({first})")
    if not c.set_active_by_name(second):
        raise Fail(f"could not switch the active sorter to {second}")
    try:
        r = sort_active(ctx)
    finally:
        c.set_active_by_name(first)
    _canary(r["noise"], f"{second} sort", r["log"])
    ok, msg, _ = c.run_compare((first, second))
    page = ROOT / "outputs" / "comparison.html"
    if not ok or not page.is_file():
        raise Fail(f"run_compare: {msg}")
    return "PASS", (f"{second} sort: {r['units']} units, noise floor {r['noise']:.2f} µV · "
                    f"outputs/comparison.html ({first} vs {second}, "
                    f"{page.stat().st_size / 1e6:.1f} MB)")


def check_reproduce(ctx):
    import runs

    c = ctx.c
    sorter, run_id = c.active_sorter, ctx.sort["run_id"]
    before = ([r["id"] for r in runs.list_runs(sorter)], runs.read_pointer(sorter))
    cmd = c.command("reproduce", run_id)
    rc, _, _ = run_child(cmd["argv"], cmd["log"])
    c.finish_command("reproduce", rc == 0)
    rep = Path(cmd["report"])
    if not rep.is_file():
        raise Fail(f"no match report written (exit {rc})", cmd["log"])
    report = json.loads(rep.read_text(encoding="utf-8")).get("report")
    if not report:
        raise Fail("the regeneration had nothing to compare against", cmd["log"])
    after = ([r["id"] for r in runs.list_runs(sorter)], runs.read_pointer(sorter))
    if before != after:
        raise Fail("reproducing changed runs/ or the current pointer", cmd["log"])
    noise = next((cr for cr in report["criteria"] if cr["name"].startswith("noise floor")), None)
    if noise is None or noise["verdict"] != runs.V_WITHIN:
        raise Fail(f"noise-floor criterion: {noise}", cmd["log"])
    failed = report.get("failed") or []
    return "PASS", (f"{_rel(rep)}: noise floor {noise['recorded']} vs {noise['regenerated']} µV "
                    f"{noise['verdict'].lower()} ({noise['tolerance']}) · overall "
                    f"{report['verdict']}"
                    + (f" (informational: {', '.join(failed)})" if failed else "")
                    + " · runs/ and the pointer untouched")


def check_recipe(ctx):
    import journey

    c = ctx.c
    run_id = (c.journey.get("run") or {}).get("id")
    ok, msg = c.export_recipe()
    path = journey.recipe_path(c.active_sorter, run_id) if run_id else None
    if not ok or path is None or not path.is_file():
        raise Fail(f"export_recipe: {msg}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("sorter") != c.active_sorter or cfg.get("from_run") != run_id:
        raise Fail(f"the recipe names sorter {cfg.get('sorter')} run {cfg.get('from_run')}")
    return "PASS", (f"{_rel(path)} names {cfg['sorter']} run {run_id} · probe "
                    f"{cfg.get('probe')} · band-pass {cfg.get('freq_min'):g}-"
                    f"{cfg.get('freq_max'):g} Hz · {len(cfg.get('params') or {})} params")


def check_runs(ctx):
    import runs

    c = ctx.c
    sorter = c.active_sorter
    rows = c.runs_overview()
    if ctx.sort["run_id"] not in [r["id"] for r in rows]:
        raise Fail(f"runs_overview does not list {ctx.sort['run_id']}: {[r['id'] for r in rows]}")
    listed = f"{len(rows)} {sorter} run(s) listed, reproduce verdict: {rows[0].get('reproduced')}"
    smoke = [r for r in rows if r["smoke"]]
    if not smoke:
        return "PASS", listed + " · no smoke run in this sandbox, so the smoke rule was not exercised"
    full_current = any(r["current"] and not r["smoke"] for r in rows)
    target = next((r for r in smoke if not r["current"]), smoke[0])["id"]
    ok, msg = c.make_current(target)
    pointer = runs.read_pointer(sorter).get("run_id")
    if full_current:
        if ok or pointer == target:
            raise Fail(f"a smoke run displaced the current full run: {msg}")
        return "PASS", listed + f" · make_current(smoke {target}) refused - a full run is current"
    if not ok or pointer != target:
        raise Fail(f"make_current(smoke {target}) with no full run: {msg} (pointer {pointer})")
    return "PASS", listed + (f" · make_current(smoke {target}) accepted - no full run exists "
                             "to displace (refusal not exercised)")


def check_app(ctx):
    import asyncio

    import spike_app

    screens = ((",", "comma", "SettingsScreen"), ("/", "slash", "PaletteScreen"))

    async def drive(w, h) -> list:
        bad = []
        # As _menu() builds it: splash ON, left to leave on its own timer - the path a
        # real launch takes (a keypress skips it; it once crashed only there).
        app = spike_app.SpikeApp(ctx.c, splash=True)
        async with app.run_test(size=(w, h)) as pilot:
            await pilot.pause()
            for _ in range(int((spike_app.SplashScreen.SECONDS + 3) / 0.1)):
                await pilot.pause(0.1)
                if not isinstance(app.screen, spike_app.SplashScreen):
                    break
            if isinstance(app.screen, spike_app.SplashScreen):
                bad.append(f"splash never left @ {w}x{h}")
            for n, pane in enumerate(spike_app.SpikeApp.PANE_IDS):
                await pilot.press("escape")
                app._msg = None
                if n:
                    await pilot.press(str(n))
                await pilot.pause(0.5 if pane == "judge" else 0.05)
                msg = app._msg.plain if app._msg is not None else ""
                if "couldn't draw" in msg:
                    bad.append(f"{pane} @ {w}x{h}: {msg}")
            for label, key, name in screens:
                await pilot.press("escape")
                await pilot.press(key)
                await pilot.pause(0.1)
                if type(app.screen).__name__ != name:
                    bad.append(f"'{label}' @ {w}x{h} opened {type(app.screen).__name__}")
                await pilot.press("escape")
                await pilot.pause(0.05)
            app.do("runs")
            await pilot.pause(0.2)
            if type(app.screen).__name__ != "RunsScreen":
                bad.append(f"Runs @ {w}x{h} opened {type(app.screen).__name__}")
            await pilot.press("escape")
            await pilot.pause(0.1)
            msg = app._msg.plain if app._msg is not None else ""
            if "couldn't draw" in msg or "failed" in msg:
                bad.append(f"after Runs @ {w}x{h}: {msg}")
        return bad

    bad = []
    for size in ((100, 34), (80, 24)):
        bad += asyncio.run(drive(*size))
    if bad:
        raise Fail("; ".join(bad))
    return "PASS", ("Home + 6 stage panes, Settings, the palette and Runs all drew over the "
                    "real controller at 100x34 and 80x24")


def check_gui(ctx):
    import importlib

    found, broken = [], []
    for mod in ("spikeinterface_gui", "ephyviewer"):
        try:
            m = importlib.import_module(mod)
            found.append(f"{mod} {getattr(m, '__version__', '')}".strip())
        except Exception as e:  # noqa: BLE001 - any import failure is the finding
            broken.append(f"{mod}: {type(e).__name__}: {e}")
    qt = None
    for binding in ("PySide6", "PyQt5"):
        try:
            importlib.import_module(f"{binding}.QtWidgets")
            qt = binding
            break
        except Exception:  # noqa: BLE001 - try the other binding
            continue
    if qt is None:
        broken.append("no Qt binding (PySide6 or PyQt5) imports")
    if broken:
        raise Fail("the desktop windows cannot open: " + "; ".join(broken))
    return "MANUAL", (f"gui + traces: {', '.join(found)}, {qt} import. By hand: run "
                      "`uv run python SpikeInterface_Menu.py`, press 4 (Judge) then i - the "
                      "spikeinterface-gui window opens on the sort; press 1 (Data) then t - the "
                      "trace viewer window scrolls the raw signal")


CHECKS = {name: globals()[f"check_{name}"] for name, _ in STEPS}


def _tail(log) -> list:
    try:
        lines = Path(log).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [ln for ln in lines if ln.strip()][-TAIL_LINES:]


def inner(args) -> int:
    real_out = sys.stdout
    if not (ROOT / SANDBOX_MARKER).is_file() or bio.REPO_ROOT.resolve() != ROOT.resolve():
        print(f"{INNER_FLAG} runs only inside a sandbox built by check_workbench.py "
              f"(this is {ROOT})", file=sys.stderr)
        return 2
    sys.path.insert(0, str(ROOT))
    logs = ROOT / "outputs" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    results = []

    def report(name, status, secs, evidence, log=None):
        results.append({"name": name, "status": status, "secs": round(secs, 1),
                        "evidence": evidence})
        print(_line(status, name, secs, evidence), file=real_out, flush=True)
        if status == "FAIL" and log:
            tail = _tail(log)
            if tail:
                print(f"           last lines of {_rel(log)}:", file=real_out)
                for ln in tail:
                    print(f"             | {ln[:160]}", file=real_out)
            real_out.flush()
        (ROOT / RESULTS_NAME).write_text(json.dumps(results, indent=2), encoding="utf-8")

    t = time.monotonic()
    boot_log = logs / "check-controller.log"
    try:
        with open(boot_log, "w", encoding="utf-8") as fh, \
                contextlib.redirect_stdout(fh), contextlib.redirect_stderr(fh):
            import SpikeInterface_Menu as menu

            ns = argparse.Namespace(action=None, data_dir=None, sorter=None, probe=None,
                                    duration=None, docker=False, gui_mode="auto",
                                    params_file=None)
            ctx = Ctx(menu.MenuController(ns, menu._load_config()), args.full)
    except Exception as e:  # noqa: BLE001 - nothing can run without the controller
        with open(boot_log, "a", encoding="utf-8") as fh:
            traceback.print_exc(file=fh)
        report("controller", "FAIL", time.monotonic() - t,
               f"the app's controller did not start: {type(e).__name__}: {e}", boot_log)
        return 1

    for name in _selected(args.only):
        blocked = next((n for n in NEEDS[name]
                        if next((r["status"] for r in results if r["name"] == n), None)
                        != "PASS"), None)
        if blocked:
            report(name, "SKIPPED", 0.0, f"needs {blocked}, which did not pass")
            continue
        t = time.monotonic()
        log = logs / f"check-{name}.log"
        status, evidence, tail_log = "FAIL", "", log
        with open(log, "w", encoding="utf-8") as fh, \
                contextlib.redirect_stdout(fh), contextlib.redirect_stderr(fh):
            try:
                status, evidence = CHECKS[name](ctx)
            except Fail as e:
                evidence, tail_log = str(e), (e.log or log)
                print(f"FAIL: {e}")
            except Exception as e:  # noqa: BLE001 - a crash is a FAIL with its traceback
                evidence = f"{type(e).__name__}: {e}"
                traceback.print_exc()
        report(name, status, time.monotonic() - t, evidence, tail_log)
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


def main() -> int:
    bio.use_utf8_stdout()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None,
                        help="folder holding the .ns5/.ns2/.nev set (default: this project folder)")
    parser.add_argument("--keep", action="store_true", help="keep the sandbox afterwards")
    parser.add_argument("--only", default=None, metavar="NAMES",
                        help="comma list of steps to run (plus the steps they need)")
    parser.add_argument("--full", action="store_true",
                        help="full-length sorts instead of the quick test")
    parser.add_argument(INNER_FLAG, dest="inner", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    return inner(args) if args.inner else outer(args)


if __name__ == "__main__":
    raise SystemExit(main())
