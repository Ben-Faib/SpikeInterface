"""Interactive launcher for the PFCM7 HTML report.

    conda activate si_env
    python scripts/make_report.py                 # prints health, offers re-sort menu
    python scripts/make_report.py --data-dir /path/to/recording

Prints loader health + live sort provenance, then offers a terminal menu:
reuse the saved sort / quick re-sort / full re-sort. Re-sorting shells out to
run_sorting.py (coupling only to its CLI flags + outputs/<sorter>/ layout, never
its stdout), then builds outputs/report.html. Non-interactive stdin -> reuse.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import report  # noqa: E402

SORTER = "tridesclous2"
QUICK_SECONDS = 30
SCRIPTS_DIR = Path(__file__).resolve().parent


def _provenance(analyzer_dir: Path):
    """Live provenance of the saved sort (None if absent, {'error':...} if unreadable)."""
    if not analyzer_dir.exists():
        return None
    try:
        import spikeinterface.full as si
        a = si.load_sorting_analyzer(analyzer_dir)
        when = datetime.fromtimestamp(analyzer_dir.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return {"units": len(a.unit_ids), "duration": a.get_total_duration(), "when": when}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def _print_status(data_dir, analyzer_dir):
    _objects, status = report._gather(data_dir, analyzer_dir)
    print("\nPipeline status:")
    for r in status:
        print(f"  [{r['status']:4}] {r['stage']:22} {r['detail']}")


def _choose(prov) -> str:
    if prov is None:
        print("\nSaved sort: none found.")
    elif "error" in prov:
        print(f"\nSaved sort: present but unreadable ({prov['error']}).")
    else:
        print(f"\nSaved sort: {prov['units']} units, {prov['duration']:.1f}s sorted, run {prov['when']}.")
    if not sys.stdin.isatty():
        print("(non-interactive stdin -> reusing saved sort)")
        return "reuse"
    print("\n  [Enter] reuse saved sort and build the report")
    print(f"  [q]     quick re-sort (first {QUICK_SECONDS}s) then build")
    print("  [f]     full re-sort (whole recording) then build")
    return {"": "reuse", "q": "quick", "f": "full"}.get(input("> ").strip().lower(), "reuse")


def _resort(duration, data_dir) -> bool:
    cmd = [sys.executable, str(SCRIPTS_DIR / "run_sorting.py"), "--sorter", SORTER]
    if duration is not None:
        cmd += ["--duration", str(duration)]
    if data_dir:
        cmd += ["--data-dir", str(data_dir)]
    print(f"\n$ {' '.join(cmd)}\n")
    return subprocess.run(cmd).returncode == 0  # inherit stdout/stderr: live progress


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None, help="Folder with the .nev/.nsX (default: repo root).")
    args = parser.parse_args()

    analyzer_dir = bio.REPO_ROOT / "outputs" / SORTER / "analyzer"
    _print_status(args.data_dir, analyzer_dir)
    action = _choose(_provenance(analyzer_dir))

    if action in ("quick", "full"):
        ok = _resort(QUICK_SECONDS if action == "quick" else None, args.data_dir)
        if not ok:
            print("\nRe-sort failed (non-zero exit).")
            if not analyzer_dir.exists():
                print("No analyzer to report on — aborting.")
                return 1
            print("Building the report against the existing analyzer instead.")

    print("\nBuilding report ...")
    out = report.build_report(data_dir=args.data_dir, analyzer_dir=analyzer_dir)
    print(f"Report written: {out}")
    print(f"Open it:        file://{out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
