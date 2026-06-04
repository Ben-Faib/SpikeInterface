"""Small rich-based terminal UI for SpikeInterface_Menu.py.

Mirrors the look of scripts/run_sorting.py's ConsoleUI (banner rules, cyan/bold
accents, boxed SIMPLE_HEAVY tables, dim detail, green ✓) so the launcher and the
sorter feel like one tool. Everything degrades to plain ``print`` if ``rich`` is
unavailable, and ``rich`` auto-disables colour when stdout is not a TTY.

The palette intentionally matches run_sorting.ConsoleUI.PALETTE.
"""
from __future__ import annotations

import re

# Palette — same values as run_sorting.ConsoleUI.PALETTE.
ACCENT, MUTED, OK, WARN, BAD = "cyan", "dim", "bold green", "yellow", "bold red"
# PASS/SKIP/FAIL -> (rich style, glyph) for the pipeline status table.
_BADGE = {"PASS": ("bold green", "✓"), "SKIP": ("dim", "–"), "FAIL": ("bold red", "✗")}

try:  # rich is a declared dependency; the fallback is just safety.
    from rich.console import Console

    _C: Console | None = Console(highlight=False)
except Exception:  # pragma: no cover - rich missing
    _C = None

_TAG = re.compile(r"\[/?[a-z0-9 #]*\]")  # crude markup stripper for the plain fallback


def _plain(markup: str) -> str:
    return _TAG.sub("", markup)


def say(markup: str) -> None:
    """Print one line, rendering rich markup (or stripping it without rich)."""
    if _C is not None:
        _C.print(markup)
    else:
        print(_plain(markup))


def prompt(markup: str = "> ") -> str:
    if _C is not None:
        return _C.input(markup)
    return input(_plain(markup))


def rule(title: str) -> None:
    if _C is not None:
        _C.print()
        _C.rule(f"[bold]{title}[/]")
    else:
        print(f"\n=== {title} ===")


def note(text: str) -> None:
    say(f"[{MUTED}]{text}[/]")


def warn(text: str) -> None:
    say(f"[{WARN}]{text}[/]")


def done(text: str) -> None:
    say(f"[{OK}]✓[/] {text}")


def link(label: str, uri: str) -> None:
    say(f"[{MUTED}]{label}[/] {uri}")


def sorters_panel(infos) -> None:
    """Render both sorters with their saved-sort summary + an 'active' marker.

    ``infos`` is a list of dicts: {name, present, units, duration, active}.
    """
    if _C is None:
        print("\nSorters:")
        for i in infos:
            mark = "->" if i["active"] else "  "
            saved = f"{i['units']} units · {i['duration']:.1f}s" if i["present"] else "no saved sort"
            print(f"  {mark} {i['name']:15} {saved}" + ("  (active)" if i["active"] else ""))
        return
    from rich import box
    from rich.table import Table

    t = Table(box=box.SIMPLE_HEAVY, header_style=f"bold {ACCENT}", pad_edge=False,
              title="[bold]Sorters[/]", title_justify="left")
    t.add_column("", justify="center", no_wrap=True)
    t.add_column("sorter", no_wrap=True)
    t.add_column("saved sort")
    for i in infos:
        mark = f"[bold {ACCENT}]→[/]" if i["active"] else ""
        name = f"[bold]{i['name']}[/]" if i["active"] else i["name"]
        saved = (f"{i['units']} units · {i['duration']:.1f}s"
                 if i["present"] else f"[{MUTED}]no saved sort[/]")
        if i["active"]:
            saved += f"   [{MUTED}](active)[/]"
        t.add_row(mark, name, saved)
    _C.print(t)


def status_table(rows) -> None:
    """Render the sorter-independent pipeline status (LFP/Broadband/.nev/Events)."""
    if _C is None:
        for r in rows:
            print(f"  [{r['status']:4}] {r['stage']:22} {r['detail']}")
        return
    from rich import box
    from rich.table import Table

    t = Table(box=box.SIMPLE_HEAVY, header_style=f"bold {ACCENT}", pad_edge=False,
              title="[bold]Pipeline[/]", title_justify="left")
    t.add_column("", justify="center", no_wrap=True)
    t.add_column("stage", no_wrap=True)
    t.add_column("detail", overflow="fold")
    for r in rows:
        style, glyph = _BADGE.get(r["status"], ("", r["status"]))
        t.add_row(f"[{style}]{glyph}[/]", r["stage"], f"[{MUTED}]{r['detail']}[/]")
    _C.print(t)


def menu(items, active: str) -> None:
    """Render the numbered action menu. ``items`` = list of (key, action, title, hint)."""
    width = max((len(title) for _k, _a, title, _h in items), default=0)
    if _C is None:
        print()
        for key, _a, title, hint in items:
            print(f"  {key}) {title.ljust(width)}   {hint}")
        print(f"  t) Switch active sorter for report/GUI/compare (now: {active})")
        print("  q) Quit")
        return
    _C.print()
    for key, _a, title, hint in items:
        _C.print(f"  [bold {ACCENT}]{key}[/]) [bold]{title.ljust(width)}[/]   [{MUTED}]{hint}[/]")
    _C.print(f"  [bold {ACCENT}]t[/]) [{MUTED}]Switch active sorter for report/GUI/compare "
             f"(now: [/][bold]{active}[/][{MUTED}])[/]")
    _C.print(f"  [bold {ACCENT}]q[/]) [{MUTED}]Quit[/]")
