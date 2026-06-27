"""Preview the dashboard wordmark tiers in the terminal (dev aid).

    uv run python scripts/_wordmark_preview.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui  # noqa: E402


def main() -> int:
    for label, tier in (("FULL", ui._WORDMARK_FULL), ("COMPACT", ui._WORDMARK_COMPACT)):
        print(f"\n{label}  ({len(tier[0])} cols x {len(tier)} rows)")
        for row in tier:
            print("  " + row)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
