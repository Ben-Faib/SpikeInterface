"""Thin shim — the report flow now lives in the root SpikeInterface_Menu.py.

    uv run python scripts/make_report.py                 # builds + opens the report
    uv run python scripts/make_report.py --data-dir DIR
    uv run python scripts/make_report.py --sorter spykingcircus2

Kept for backwards compatibility; it just invokes the launcher's 'report'
action with whatever flags you pass. For the full menu (sort / GUI / compare /
trace browser / ...), run the launcher directly:

    uv run python SpikeInterface_Menu.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent.parent / "SpikeInterface_Menu.py"


def main() -> int:
    cmd = [sys.executable, str(LAUNCHER), "report", *sys.argv[1:]]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
