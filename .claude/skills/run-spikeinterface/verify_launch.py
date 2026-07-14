#!/usr/bin/env python
"""Headless launch check for the SpikeInterface front-door menu.

The front door (``SpikeInterface_Menu.py`` with no action) is a full-screen
Textual TUI, so it can't be "just run" from a non-interactive shell to confirm it
works — it needs a real terminal, or a driver. This drives the *real*
``SpikeMenuApp`` through Textual's Pilot harness: it mounts the app, dismisses any
first-run modal, snapshots the key dashboard panels + an SVG, exercises
navigation, and confirms a clean exit. A non-zero exit here means the menu does
not launch.

    uv run python .claude/skills/run-spikeinterface/verify_launch.py

Writes outputs/menu_launch_capture.txt (panel text) and outputs/menu_launch.svg
(full-screen screenshot); both land in the git-ignored outputs/ folder.
"""
import argparse
import asyncio
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # <repo>/.claude/skills/run-spikeinterface/ -> <repo>
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import SpikeInterface_Menu as launcher  # noqa: E402
import menu_app  # noqa: E402
from rich.console import Console  # noqa: E402
from textual.widgets import Static, OptionList  # noqa: E402

OUT = ROOT / "outputs"


def _text(widget) -> str:
    """Render a widget's current content to plain text (no colour)."""
    try:
        renderable = widget.render()
    except Exception as e:  # noqa: BLE001
        return f"<render error: {e!r}>"
    console = Console(file=io.StringIO(), width=100, no_color=True)
    console.print(renderable)
    return console.file.getvalue().rstrip("\n")


def _optionlist_text(ol) -> str:
    lines = []
    for opt in ol._options:  # Textual OptionList internal Option list
        console = Console(file=io.StringIO(), width=100, no_color=True)
        console.print(opt.prompt)
        lines.append(console.file.getvalue().rstrip("\n"))
    return "\n".join(lines)


async def drive(data_dir: "str | None") -> bool:
    args = argparse.Namespace(action=None, data_dir=data_dir, sorter=None, probe=None,
                              duration=None, docker=False, gui_mode="auto")
    cfg = launcher._load_config()
    launcher._apply_saved_theme(cfg)
    controller = launcher.MenuController(args, cfg)
    app = menu_app.SpikeMenuApp(controller)

    buf, svg_len = [], 0
    # Textual owns stdout while the app runs, and its capture is cp1252 on Windows —
    # so collect everything and write it out (UTF-8) AFTER the app closes.
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        for _ in range(4):  # dismiss any first-run Welcome / Probe-setup modal
            if len(app.screen_stack) > 1:
                await pilot.press("escape")
                await pilot.pause()
            else:
                break
        await pilot.pause()

        panels = [
            ("TITLEBAR", "#titlebar"), ("DATABAR", "#databar"), ("SORTBAR", "#sortbar"),
            ("PROBEBAR", "#probebar"), ("FOOTER", "#footer"),
        ]
        for name, sel in panels:
            buf.append(f"=== {name} ===")
            buf.append(_text(app.query_one(sel, Static)))
        buf.append("=== SORTERS ===")
        buf.append(_optionlist_text(app.query_one("#sorters", OptionList)))
        buf.append("=== ACTIONS ===")
        buf.append(_optionlist_text(app.query_one("#actions", OptionList)))

        # Exercise navigation: focus the Actions pane and move — must not crash.
        await pilot.press("right")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        buf.append("=== FOOTER after right,down ===")
        buf.append(_text(app.query_one("#footer", Static)))

        svg = app.export_screenshot(title="SpikeInterface Menu")
        OUT.mkdir(exist_ok=True)
        (OUT / "menu_launch.svg").write_text(svg, encoding="utf-8")
        svg_len = len(svg)

    (OUT / "menu_launch_capture.txt").write_text("\n".join(buf), encoding="utf-8")
    ok = svg_len > 0 and app.return_code in (None, 0)
    status = ("OK: menu mounted, rendered, navigated, exited cleanly. "
              f"SVG bytes={svg_len}. See outputs/menu_launch_capture.txt\n"
              if ok else f"FAIL: return_code={app.return_code!r} svg_bytes={svg_len}\n")
    sys.stdout.buffer.write(status.encode("ascii", "replace"))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=None, help="Recording folder (default: repo root).")
    args = ap.parse_args()
    return 0 if asyncio.run(drive(args.data_dir)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
