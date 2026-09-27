#!/usr/bin/env python
"""Headless launch check for the SpikeInterface front-door menu.

The front door (``SpikeInterface_Menu.py`` with no action) is a full-screen
Textual TUI, so it can't be "just run" from a non-interactive shell to confirm it
works - it needs a real terminal, or a driver. This drives the *real* Spike 2.0
app (``spike_app.SpikeApp``) exactly as ``_menu()`` builds it - splash ON - through
Textual's Pilot harness: it lets the splash leave on its OWN timer (the path a real
launch takes and a keypress skips; it crashed once, 2026-09-27), visits every stage,
Settings, the palette and help, snapshots Home + an SVG, and confirms a clean exit.
A non-zero exit here means the app does not launch.

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
import spike_app  # noqa: E402
from rich.console import Console  # noqa: E402
from textual.widgets import Static  # noqa: E402

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


async def drive(data_dir: "str | None") -> bool:
    args = argparse.Namespace(action=None, data_dir=data_dir, sorter=None, probe=None,
                              duration=None, docker=False, gui_mode="auto")
    cfg = launcher._load_config()
    launcher._apply_saved_theme(cfg)
    controller = launcher.MenuController(args, cfg)
    app = spike_app.SpikeApp(controller, splash=True)      # as _menu() builds it

    buf, svg_len = [], 0
    # Textual owns stdout while the app runs, and its capture is cp1252 on Windows -
    # so collect everything and write it out (UTF-8) AFTER the app closes.
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        assert type(app.screen).__name__ == "SplashScreen", "no launch splash"
        for _ in range(int((spike_app.SplashScreen.SECONDS + 3) / 0.1)):
            await pilot.pause(0.1)                 # let the splash leave on its own
            if type(app.screen).__name__ != "SplashScreen":
                break
        assert type(app.screen).__name__ != "SplashScreen", "the splash never left"
        for name, sel in (("HEADER", "#header"), ("RAIL", "#rail"), ("KEYS", "#keys")):
            buf.append(f"=== {name} ===")
            buf.append(_text(app.query_one(sel, Static)))
        buf.append("=== NEXT STEP ===")
        buf.append(_text(app.query_one("#home #card", Static)))
        for key in ("1", "2", "3", "4", "5", "6", "escape"):
            await pilot.press(key)
            await pilot.pause(0.3)
            status = _text(app.query_one("#status", Static))
            assert "couldn't draw" not in status, f"stage {key}: {status}"
        for key, screen in (("comma", "SettingsScreen"), ("slash", "PaletteScreen"),
                            ("question_mark", "HelpScreen")):
            await pilot.press(key)
            await pilot.pause()
            assert type(app.screen).__name__ == screen, f"{key} opened {type(app.screen).__name__}"
            await pilot.press("escape")
            await pilot.pause()
        buf.append("=== after every stage + Settings/palette/help ===")
        buf.append(_text(app.query_one("#status", Static)))

        svg = app.export_screenshot(title="Spike 2.0")
        OUT.mkdir(exist_ok=True)
        (OUT / "menu_launch.svg").write_text(svg, encoding="utf-8")
        svg_len = len(svg)

    (OUT / "menu_launch_capture.txt").write_text("\n".join(buf), encoding="utf-8")
    ok = svg_len > 0 and app.return_code in (None, 0)
    status = ("OK: Spike 2.0 launched (splash left on its timer), every stage drew, exited cleanly. "
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
