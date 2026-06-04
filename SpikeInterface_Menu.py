#!/usr/bin/env python
"""PFCM7 SpikeInterface workspace — single front-door menu launcher.

    conda activate si_env
    python SpikeInterface_Menu.py            # interactive status + menu
    python SpikeInterface_Menu.py report     # run one action directly, then exit
    python SpikeInterface_Menu.py --help

Run with no action -> prints a pipeline-status dashboard and a numbered menu
(friendly for everyone). Run with an action -> dispatches it directly (handy for
scripting). Heavy SpikeInterface imports are lazy, so the menu stays responsive.

The dashboard shows BOTH sorters (with their saved-sort summary and an "active"
marker) plus the sorter-independent pipeline status. The active sorter is what
report / GUI / compare act on; switch it with 't', or just pick a sorter when you
run a sort. Terminal styling mirrors scripts/run_sorting.py (see scripts/ui.py).

Actions:
    explore   quick static figures (LFP + .nev) via scripts/explore_data.py
    sort      spike-sort the broadband via scripts/run_sorting.py
    report    build + open the interactive HTML report (scripts/report.py)
    gui       open spikeinterface-gui on the active sort
    traces    scroll raw broadband traces in ephyviewer
    compare   agreement matrix between the two sorters (scripts/compare.py)
    verify    environment smoke test (scripts/verify_install.py)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import blackrock_io as bio  # noqa: E402
import report  # noqa: E402
import ui  # noqa: E402  (rich styling shared-look with run_sorting.py)
from run_sorting import SORTERS  # noqa: E402  (single-source the sorter list)

QUICK_SECONDS = 30
ACTIONS = ["explore", "sort", "report", "gui", "traces", "compare", "verify"]
# Actions that open a blocking Qt window: the menu launches them in a fresh
# child process so the menu survives and Qt gets a clean process each time.
QT_ACTIONS = {"gui", "traces"}


def _analyzer_dir(sorter: str) -> Path:
    return bio.REPO_ROOT / "outputs" / sorter / "analyzer"


# --------------------------------------------------------------------------- #
# Dashboard data (loaded once, refreshed only after a state-changing action)
# --------------------------------------------------------------------------- #
def _sorter_info(sorter: str, analyzer, active: bool) -> dict:
    """Saved-sort summary for one sorter. Pass a pre-loaded analyzer or None."""
    if analyzer is None and _analyzer_dir(sorter).exists():
        try:
            import spikeinterface.full as si

            analyzer = si.load_sorting_analyzer(_analyzer_dir(sorter))
        except Exception:  # noqa: BLE001 - unreadable analyzer -> treat as absent
            analyzer = None
    if analyzer is None:
        return {"name": sorter, "present": False, "units": 0, "duration": 0.0, "active": active}
    return {"name": sorter, "present": True, "units": len(analyzer.unit_ids),
            "duration": float(analyzer.get_total_duration()), "active": active}


def _load_dashboard(data_dir, active: str):
    """Return (pipeline_rows, sorter_infos). Heavy: loads the data + analyzers."""
    objects, status = report._gather(data_dir, _analyzer_dir(active))
    pipeline = [r for r in status if not r["stage"].startswith("Saved sort")]
    infos = [_sorter_info(s, objects.get("analyzer") if s == active else None, s == active)
             for s in SORTERS]
    return pipeline, infos


def _render_dashboard(pipeline, infos) -> None:
    ui.rule("PFCM7 workspace")
    ui.sorters_panel(infos)
    ui.status_table(pipeline)


# --------------------------------------------------------------------------- #
# Shell-out helpers
# --------------------------------------------------------------------------- #
def _shell(script: str, *flags: str) -> bool:
    """Run a sibling script as a child process, inheriting stdout (live output)."""
    cmd = [sys.executable, str(SCRIPTS / script), *flags]
    ui.note(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd).returncode == 0


def _self(action: str, args) -> bool:
    """Re-invoke this launcher in a child process for a single (blocking Qt) action."""
    cmd = [sys.executable, str(ROOT / "SpikeInterface_Menu.py"), action, "--sorter", args.sorter]
    if args.data_dir:
        cmd += ["--data-dir", args.data_dir]
    ui.note(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd).returncode == 0


def _tab_label(sorter: str, infos) -> str:
    """One sorter-tab label, e.g. 'tridesclous2 · 19u/132s' or 'spykingcircus2 · no sort'."""
    info = next((i for i in infos if i["name"] == sorter), None)
    if info and info["present"]:
        return f"{sorter} · {info['units']}u/{info['duration']:.0f}s"
    return f"{sorter} · no sort"


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def action_explore(args) -> bool:
    flags = ["--data-dir", args.data_dir] if args.data_dir else []
    return _shell("explore_data.py", *flags)


def action_sort(args) -> bool:
    flags = ["--sorter", args.sorter]
    if args.duration is not None:
        flags += ["--duration", str(args.duration)]
    if args.data_dir:
        flags += ["--data-dir", args.data_dir]
    return _shell("run_sorting.py", *flags)


def action_verify(args) -> bool:
    return _shell("verify_install.py")  # takes no flags


def _open_in_browser(uri: str) -> None:
    if sys.stdin.isatty():
        try:
            if not webbrowser.open(uri):
                ui.note("(could not open a browser automatically — open the link above)")
        except Exception:  # noqa: BLE001
            pass


def action_report(args) -> bool:
    out = report.build_report(data_dir=args.data_dir, analyzer_dir=_analyzer_dir(args.sorter),
                              sorter_label=args.sorter)
    uri = out.resolve().as_uri()
    ui.done(f"Report written → {out}")
    ui.link("Open it:", uri)
    _open_in_browser(uri)
    return True


def action_gui(args) -> bool:
    analyzer_dir = _analyzer_dir(args.sorter)
    if not analyzer_dir.exists():
        ui.warn(f"No saved sort for {args.sorter} — run 'sort' first.")
        return False
    try:
        import spikeinterface.full as si
        import spikeinterface_gui as sigui
    except Exception as e:  # noqa: BLE001
        ui.warn(f"Could not import the GUI ({e!r}). Try: python scripts/verify_install.py")
        return False
    ui.say(f"[{ui.ACCENT}]Opening spikeinterface-gui[/] on {analyzer_dir} "
           f"[{ui.MUTED}](close the window to return) ...[/]")
    analyzer = si.load_sorting_analyzer(analyzer_dir)
    sigui.run_mainwindow(analyzer, mode="desktop")  # blocks until the window closes
    return True


def action_traces(args) -> bool:
    try:
        import spikeinterface.widgets as sw
    except Exception as e:  # noqa: BLE001
        ui.warn(f"Could not import the trace viewer ({e!r}). Try: python scripts/verify_install.py")
        return False
    ui.say(f"[{ui.ACCENT}]Opening ephyviewer[/] on the broadband recording "
           f"[{ui.MUTED}](close the window to return) ...[/]")
    rec = bio.read_broadband(args.data_dir)
    sw.plot_traces({"broadband": rec}, backend="ephyviewer", show_channel_ids=True)  # blocks
    return True


def action_compare(args) -> bool:
    import compare  # lazy: pulls in spikeinterface

    other = [s for s in SORTERS if s != args.sorter]
    sorters = (args.sorter, other[0]) if other else tuple(SORTERS[:2])

    # Surface a duration mismatch and (interactively) offer to make the two sorts
    # commensurate by re-sorting both over a common window before comparing.
    durations = {}
    for s in sorters:
        a_dir = _analyzer_dir(s)
        if a_dir.exists():
            import spikeinterface.full as si

            durations[s] = float(si.load_sorting_analyzer(a_dir).get_total_duration())
    mismatch = (len(durations) == 2
                and abs(durations[sorters[0]] - durations[sorters[1]]) > compare.DURATION_TOLERANCE_S)
    if mismatch:
        ui.warn("The two sorts cover different windows: "
                + ", ".join(f"{s}={d:.1f}s" for s, d in durations.items()) + ".")
        choice = ui.select(
            f"Re-sort both over the first {QUICK_SECONDS}s so the comparison is meaningful?",
            [("no", "No — just show the window-mismatch caveat", ""),
             ("yes", f"Yes — re-sort both ({QUICK_SECONDS}s) then compare", "")],
            default=0)
        if choice == "yes":
            for s in sorters:
                _shell("run_sorting.py", "--sorter", s, "--duration", str(QUICK_SECONDS),
                       *(["--data-dir", args.data_dir] if args.data_dir else []))

    out = compare.build_comparison(data_dir=args.data_dir, sorters=sorters)
    uri = out.resolve().as_uri()
    ui.done(f"Comparison written → {out}")
    ui.link("Open it:", uri)
    _open_in_browser(uri)
    return True


DISPATCH = {
    "explore": action_explore, "sort": action_sort, "report": action_report,
    "gui": action_gui, "traces": action_traces, "compare": action_compare,
    "verify": action_verify,
}

# (key, action, title, hint)
_MENU = [
    ("1", "explore", "Explore raw data",        "static figures (LFP + .nev), no sort needed"),
    ("2", "sort",    "Run / re-run sorting",    "asks which sorter (tridesclous2 / spykingcircus2)"),
    ("3", "report",  "Build & open report",     "interactive HTML → browser"),
    ("4", "gui",     "Open GUI inspector",      "spikeinterface-gui on the active sort"),
    ("5", "traces",  "Scroll raw traces",       "ephyviewer trace browser"),
    ("6", "compare", "Compare the two sorters", "agreement matrix → comparison.html"),
    ("7", "verify",  "Verify install",          "environment smoke test"),
]


def _menu(args) -> int:
    if not sys.stdin.isatty():
        ui.note("(non-interactive stdin -> building the report)")
        return 0 if DISPATCH["report"](args) else 1

    pipeline, infos = _load_dashboard(args.data_dir, args.sorter)
    active_idx = SORTERS.index(args.sorter)
    cursor = 0
    actions = [(action, title, hint) for _k, action, title, hint in _MENU] + [("__quit__", "Quit", "")]
    while True:
        _render_dashboard(pipeline, infos)
        tabs = [_tab_label(s, infos) for s in SORTERS]
        action, active_idx = ui.tab_menu(actions, tabs, active=active_idx, default=cursor)
        args.sorter = SORTERS[active_idx]          # the active tab IS the sorter
        for i in infos:  # keep the at-a-glance panel's active marker in sync
            i["active"] = i["name"] == args.sorter
        if action in (None, "__quit__"):
            return 0
        if action == "__sorter__":  # typed-fallback only: cycle to the next sorter
            active_idx = (active_idx + 1) % len(SORTERS)
            continue
        cursor = next((n for n, a in enumerate(actions) if a[0] == action), 0)
        if action == "sort":
            span = ui.select("Sort how much?",
                             [("full", "Full recording", ""),
                              ("quick", f"Quick test — first {QUICK_SECONDS}s", "")],
                             default=0)
            if span is None:  # cancelled -> back to the menu without sorting
                continue
            args.duration = QUICK_SECONDS if span == "quick" else None
        if action in QT_ACTIONS:
            _self(action, args)        # fresh child process for the blocking Qt window
        else:
            DISPATCH[action](args)
        if action in ("sort", "compare"):  # only these can change saved-sort state
            pipeline, infos = _load_dashboard(args.data_dir, args.sorter)
            active_idx = SORTERS.index(args.sorter)


def main() -> int:
    bio.use_utf8_stdout()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", nargs="?", choices=ACTIONS, default=None,
                        help="Run one action directly (default: interactive menu).")
    parser.add_argument("--data-dir", default=None, help="Folder with the .nev/.nsX (default: repo root).")
    parser.add_argument("--sorter", choices=SORTERS, default=SORTERS[0], help="Active sorter.")
    parser.add_argument("--duration", type=float, default=None, help="For 'sort': first N seconds only.")
    args = parser.parse_args()

    if args.action is None:
        return _menu(args)
    ok = DISPATCH[args.action](args)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
