"""The em-dash pin: U+2014 is banned from this repo (Ben, 2026-08-19).

Hard boundary from the GOAL_PRESENT interview: the character disappears from
UI strings, HTML surfaces, docs, code, tests, board files, and stays gone.
This test walks every git-tracked file and fails on any occurrence, naming
file and line. Exempt: nothing.

Substitutes that read well: hyphen, colon, period, middot. New surfaces
(the sweep page, the deck) are born clean; this pin keeps them that way.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EM_DASH = "—"


def test_no_em_dash_in_any_tracked_file():
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True,
    ).stdout.decode("utf-8", errors="replace").split("\0")
    offenders = []
    for name in tracked:
        if not name:
            continue
        path = REPO / name
        if not path.is_file():          # e.g. a tracked path deleted locally
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue                    # binary or unreadable: not a text surface
        for lineno, line in enumerate(text.splitlines(), start=1):
            if EM_DASH in line:
                offenders.append(f"{name}:{lineno}: {line.strip()[:80]}")
                if len(offenders) >= 20:
                    break
        if len(offenders) >= 20:
            break
    assert not offenders, (
        "U+2014 is banned from this repo (hard boundary, goals/GOAL_PRESENT.md "
        "decision 4). Replace with hyphen/colon/period/middot:\n"
        + "\n".join(offenders)
    )


if __name__ == "__main__":
    sys.exit(0 if not subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-q"]).returncode else 1)
