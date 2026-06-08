"""Dev tool: print each neuron crest tier (rest + a fired frame) to the terminal
so the art can be eyeballed for legibility and alignment. Not imported by the app.

    uv run python scripts/_neuron_art_preview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # find ui.py
import ui  # noqa: E402


def _plain(rows):
    return "\n".join("".join(seg for _, seg in row) for row in rows)


def main() -> int:
    tiers = [("FULL", ui._NEURON_FULL), ("COMPACT", ui._NEURON_COMPACT),
             ("MINI", ui._NEURON_MINI)]
    for name, tier in tiers:
        w, h = len(tier.rest[0]), len(tier.rest)
        print(f"===== {name}: {w} cols x {h} rows — rest =====")
        print(_plain(ui.neuron_frame(tier, 0.0)))
        print(f"----- {name} — fire -----")
        print(_plain(ui.neuron_frame(tier, 0.96)))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
