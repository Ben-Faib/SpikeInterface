#!/usr/bin/env python
"""PFCM7 SpikeInterface workspace — single front-door menu launcher.

    conda activate si_env
    python SpikeInterface_Menu.py            # interactive status + menu
    python SpikeInterface_Menu.py report     # run one action directly, then exit
    python SpikeInterface_Menu.py --help

Run with no action -> prints a pipeline-status dashboard and a numbered menu
(friendly for everyone). Run with an action -> dispatches it directly (handy for
scripting). Heavy SpikeInterface imports are lazy, so the menu stays responsive.

Actions:
    explore   quick static figures (LFP + .nev) via scripts/explore_data.py
    sort      spike-sort the broadband via scripts/run_sorting.py
    report    build + open the interactive HTML report (scripts/report.py)
    gui       open spikeinterface-gui on the saved sort
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
from run_sorting import SORTERS  # noqa: E402  (single-source the sorter list)

QUICK_SECONDS = 30
ACTIONS = ["explore", "sort", "report", "gui", "traces", "compare", "verify"]
# Actions that open a blocking Qt window: the menu launches them in a fresh
# child process so the menu survives and Qt gets a clean process each time.
QT_ACTIONS = {"gui", "traces"}


def _analyzer_dir(sorter: str) -> Path:
    return bio.REPO_ROOT / "outputs" / sorter / "analyzer"


def _status(data_dir, sorter: str) -> None:
    _objects, rows = report._gather(data_dir, _analyzer_dir(sorter))
    print(f"\nPFCM7 workspace · active sorter: {sorter}")
    for r in rows:
        print(f"  [{r['status']:4}] {r['stage']:22} {r['detail']}")


def _shell(script: str, *flags: str) -> bool:
    """Run a sibling script as a child process, inheriting stdout (live output)."""
    cmd = [sys.executable, str(SCRIPTS / script), *flags]
    print(f"\n$ {' '.join(cmd)}\n")
    return subprocess.run(cmd).returncode == 0


def _self(action: str, args) -> bool:
    """Re-invoke this launcher in a child process for a single (blocking Qt) action."""
    cmd = [sys.executable, str(ROOT / "SpikeInterface_Menu.py"), action, "--sorter", args.sorter]
    if args.data_dir:
        cmd += ["--data-dir", args.data_dir]
    print(f"\n$ {' '.join(cmd)}\n")
    return subprocess.run(cmd).returncode == 0


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


def action_report(args) -> bool:
    out = report.build_report(data_dir=args.data_dir, analyzer_dir=_analyzer_dir(args.sorter),
                              sorter_label=args.sorter)
    uri = out.resolve().as_uri()
    print(f"\nReport written: {out}\nOpen it:        {uri}")
    if sys.stdin.isatty():
        try:
            if not webbrowser.open(uri):
                print("(could not open a browser automatically — open the link above)")
        except Exception:  # noqa: BLE001
            pass
    return True


def action_gui(args) -> bool:
    analyzer_dir = _analyzer_dir(args.sorter)
    if not analyzer_dir.exists():
        print(f"No saved sort for {args.sorter} — run 'sort' first.")
        return False
    try:
        import spikeinterface.full as si
        import spikeinterface_gui as sigui
    except Exception as e:  # noqa: BLE001
        print(f"Could not import the GUI ({e!r}). Try: python scripts/verify_install.py")
        return False
    print(f"Opening spikeinterface-gui on {analyzer_dir} (close the window to return) ...")
    analyzer = si.load_sorting_analyzer(analyzer_dir)
    sigui.run_mainwindow(analyzer, mode="desktop")  # blocks until the window closes
    return True


def action_traces(args) -> bool:
    try:
        import spikeinterface.widgets as sw
    except Exception as e:  # noqa: BLE001
        print(f"Could not import the trace viewer ({e!r}). Try: python scripts/verify_install.py")
        return False
    print("Opening ephyviewer on the broadband recording (close the window to return) ...")
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
        print("\nThe two sorts cover different windows: "
              + ", ".join(f"{s}={d:.1f}s" for s, d in durations.items()) + ".")
        if sys.stdin.isatty() and input(
                f"Re-sort both over the first {QUICK_SECONDS}s to compare? [y/N] ").strip().lower() == "y":
            for s in sorters:
                _shell("run_sorting.py", "--sorter", s, "--duration", str(QUICK_SECONDS),
                       *(["--data-dir", args.data_dir] if args.data_dir else []))

    out = compare.build_comparison(data_dir=args.data_dir, sorters=sorters)
    uri = out.resolve().as_uri()
    print(f"\nComparison written: {out}\nOpen it:            {uri}")
    if sys.stdin.isatty():
        try:
            webbrowser.open(uri)
        except Exception:  # noqa: BLE001
            pass
    return True


DISPATCH = {
    "explore": action_explore, "sort": action_sort, "report": action_report,
    "gui": action_gui, "traces": action_traces, "compare": action_compare,
    "verify": action_verify,
}

_MENU = [
    ("1", "explore", "Explore raw data         quick static figures (LFP + .nev)"),
    ("2", "sort",    "Run / re-run sorting     tridesclous2 or spykingcircus2"),
    ("3", "report",  "Build & open report      interactive HTML -> browser"),
    ("4", "gui",     "Open GUI inspector       spikeinterface-gui on the saved sort"),
    ("5", "traces",  "Scroll raw traces        ephyviewer trace browser"),
    ("6", "compare", "Compare the two sorters  agreement matrix"),
    ("7", "verify",  "Verify install"),
]


def _menu(args) -> int:
    if not sys.stdin.isatty():
        print("\n(non-interactive stdin -> building the report)")
        return 0 if DISPATCH["report"](args) else 1
    while True:
        print()
        for key, _action, label in _MENU:
            print(f"  {key}) {label}")
        print("  t) Switch active sorter")
        print("  q) Quit")
        choice = input("> ").strip().lower()
        if choice in ("q", ""):
            return 0
        if choice == "t":
            args.sorter = SORTERS[(SORTERS.index(args.sorter) + 1) % len(SORTERS)]
            _status(args.data_dir, args.sorter)
            continue
        action = next((a for k, a, _ in _MENU if k == choice), None)
        if action is None:
            print("Unknown choice.")
            continue
        if action == "sort":
            args.duration = (QUICK_SECONDS
                             if input(f"Quick {QUICK_SECONDS}s test? [y/N] ").strip().lower() == "y"
                             else None)
        if action in QT_ACTIONS:
            _self(action, args)        # fresh child process for the blocking Qt window
        else:
            DISPATCH[action](args)
        _status(args.data_dir, args.sorter)


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
        _status(args.data_dir, args.sorter)
        return _menu(args)
    ok = DISPATCH[args.action](args)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
