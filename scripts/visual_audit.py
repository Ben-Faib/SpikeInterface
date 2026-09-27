#!/usr/bin/env python
"""Screenshot every screen of Spike 2.0, at several terminal sizes, into one gallery.

    uv run python scripts/visual_audit.py                 # -> outputs/visual_audit/index.html
    uv run python scripts/visual_audit.py --sizes 100x34,80x24
    uv run python scripts/visual_audit.py --data-dir D:\\rec

For a visual audit (WINDOWS_AUDIT.md): it drives the REAL app over the real
controller and the real recording - launched exactly as a start from the terminal
does, splash included - and saves each screen as an SVG (Textual's own renderer),
plus ``index.html`` showing them all side by side with their names. Screens:
the splash, Home, the six stages (4 Judge after its evidence has loaded), Settings,
the palette with a query typed, Runs and reproducibility, help, and the sort
progress screen mid-sort and finished (fed synthetic events, so no sort runs).

It is read-only: it never writes .si_menu.json (the save hook is disabled), never
sorts, labels, applies or builds anything, and writes only under
``outputs/visual_audit/``. What it cannot show is how a particular terminal (font,
colour scheme, Windows Terminal vs the old console) draws those cells - for that,
``scripts/windows/terminal_screenshots.ps1`` screenshots the app in a real window.
"""
from __future__ import annotations

import argparse
import asyncio
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import blackrock_io as bio  # noqa: E402

OUT = ROOT / "outputs" / "visual_audit"

MID_SORT = [
    {"t": "plan", "n": 5, "phases": [{"i": 1, "title": "Read broadband"},
                                     {"i": 2, "title": "Preprocess"}, {"i": 3, "title": "Sort"},
                                     {"i": 4, "title": "Save sorting"},
                                     {"i": 5, "title": "Analyze + metrics"}]},
    {"t": "phase", "i": 1, "n": 5, "title": "Read broadband"},
    {"t": "phase", "i": 2, "n": 5, "title": "Preprocess"},
    {"t": "phase", "i": 3, "n": 5, "title": "Sort", "sub": "tridesclous2"},
    {"t": "detail", "text": "detect_peaks: 562 peaks found"},
    {"t": "bar", "desc": "detect", "frac": 0.5, "n": 5, "total": 10},
]
DONE = MID_SORT[1:4] + [
    {"t": "phase", "i": 5, "n": 5, "title": "Analyze + metrics"},
    {"t": "summary", "card": ["V_pp: 34.4 µV (median)", "SNR: 5.31 (median)",
                              "noise floor: 4.09 µV", "yield (% active electrodes): 81.2% (13/16)"],
     "summary": {"n_units": 16}},
    {"t": "done", "ok": True, "units": 16, "out": "outputs/tridesclous2"},
]


def _controller(data_dir):
    import SpikeInterface_Menu as M

    M._save_config = lambda cfg: None          # read-only: never touch .si_menu.json
    args = argparse.Namespace(action=None, data_dir=data_dir, sorter=None, probe=None,
                              duration=None, docker=False, gui_mode="auto")
    cfg = M._load_config()
    M._apply_saved_theme(cfg)
    return M.MenuController(args, cfg)


async def _shoot_size(c, w: int, h: int) -> list:
    import menu_app
    import spike_app

    class Frozen(menu_app.SortProgressScreen):
        async def _run(self):
            pass

        def _tick_spinner(self):
            pass

    shots = []
    app = spike_app.SpikeApp(c, splash=True)

    def shot(name):
        path = OUT / f"{w}x{h}" / f"{len(shots):02d}_{name}.svg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(app.export_screenshot(title=f"Spike 2.0 · {name} · {w}x{h}"),
                        encoding="utf-8")
        shots.append((name, path))

    async def settle(pilot, secs=0.3):
        await pilot.pause(secs)

    async with app.run_test(size=(w, h)) as pilot:
        await settle(pilot, 0.2)
        shot("splash")
        for _ in range(60):                         # let it leave on its own timer
            await pilot.pause(0.1)
            if not isinstance(app.screen, spike_app.SplashScreen):
                break
        await settle(pilot)
        shot("home")
        for n, name in enumerate(("data", "probe", "sort", "judge", "apply", "share"), 1):
            await pilot.press(str(n))
            if name == "judge":
                pane = app.query_one("#judge")
                for _ in range(100):
                    await pilot.pause(0.1)
                    if pane._ev or pane._ev_error or not pane._state.get("units"):
                        break
            await settle(pilot)
            shot(f"{n}_{name}")
        await pilot.press("escape")
        await pilot.press("comma")
        await settle(pilot)
        shot("settings")
        await pilot.press("escape")
        await pilot.press("slash", "p", "h", "y")
        await settle(pilot)
        shot("palette")
        await pilot.press("escape")
        app.do("runs")
        await settle(pilot, 0.6)
        shot("runs")
        await pilot.press("escape")
        await pilot.press("question_mark")
        await settle(pilot)
        shot("help")
        await pilot.press("escape")
        for name, events in (("sort_running", MID_SORT), ("sort_done", DONE)):
            screen = Frozen(["true"], app._accent)
            await app.push_screen(screen)
            await settle(pilot, 0.1)
            for ev in events:
                screen.handle_event(ev)
            await settle(pilot, 0.1)
            shot(name)
            app.pop_screen()
            await settle(pilot, 0.1)
    return shots


def _gallery(all_shots: dict) -> str:
    rows = []
    for size, shots in all_shots.items():
        cards = "".join(
            f'<figure><figcaption>{html.escape(name)}</figcaption>'
            f'<img src="{html.escape(path.relative_to(OUT).as_posix())}" loading="lazy"></figure>'
            for name, path in shots)
        rows.append(f"<h2>{html.escape(size)}</h2><div class=grid>{cards}</div>")
    return ("<!doctype html><meta charset=utf-8><title>Spike 2.0 visual audit</title>"
            "<style>body{background:#101016;color:#e6e6f0;font:14px system-ui;margin:24px}"
            ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(560px,1fr));gap:24px}"
            "figure{margin:0}figcaption{color:#9aa0a6;margin:0 0 6px}"
            "img{width:100%;border:1px solid #2c2b38;border-radius:8px;background:#000}</style>"
            "<h1>Spike 2.0 visual audit</h1>" + "".join(rows))


def main() -> int:
    bio.use_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--sizes", default="120x40,100x34,80x24,64x22",
                    help="comma list of COLSxROWS terminal sizes")
    args = ap.parse_args()
    sizes = [tuple(int(v) for v in s.lower().split("x")) for s in args.sizes.split(",") if s]
    c = _controller(args.data_dir)
    OUT.mkdir(parents=True, exist_ok=True)
    all_shots = {}
    for w, h in sizes:
        all_shots[f"{w}x{h}"] = asyncio.run(_shoot_size(c, w, h))
        print(f"{w}x{h}: {len(all_shots[f'{w}x{h}'])} screens")
    index = OUT / "index.html"
    index.write_text(_gallery(all_shots), encoding="utf-8")
    print(f"gallery: {index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
