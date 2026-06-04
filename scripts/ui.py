"""Small rich-based terminal UI for SpikeInterface_Menu.py.

Mirrors the look of scripts/run_sorting.py's ConsoleUI (banner rules, cyan/bold
accents, boxed SIMPLE_HEAVY tables, dim detail, green ✓) so the launcher and the
sorter feel like one tool. Everything degrades to plain ``print`` if ``rich`` is
unavailable, and ``rich`` auto-disables colour when stdout is not a TTY.

The palette intentionally matches run_sorting.ConsoleUI.PALETTE.
"""
from __future__ import annotations

import re
import sys

# Palette — same values as run_sorting.ConsoleUI.PALETTE.
ACCENT, MUTED, OK, WARN, BAD = "cyan", "dim", "bold green", "yellow", "bold red"
# PASS/SKIP/FAIL -> (rich style, glyph) for the pipeline status table.
_BADGE = {"PASS": ("bold green", "✓"), "SKIP": ("dim", "–"), "FAIL": ("bold red", "✗")}

try:  # rich is a declared dependency; the fallback is just safety.
    from rich.console import Console

    _C: Console | None = Console(highlight=False)
except Exception:  # pragma: no cover - rich missing
    _C = None

try:  # prompt_toolkit drives the arrow-key menu (cross-platform); typed fallback otherwise.
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    _PT = True
except Exception:  # pragma: no cover - prompt_toolkit missing
    _PT = False

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


def _select_typed(title, options, default):
    """Numbered typed fallback for select() (no prompt_toolkit / not a TTY)."""
    say(f"\n[bold]{title}[/]")
    for n, (key, main, hint) in enumerate(options, 1):
        h = f"   [{MUTED}]{hint}[/]" if hint else ""
        say(f"  [bold {ACCENT}]{n}[/]) {main}{h}")
    raw = prompt(f"[bold {ACCENT}]> [/][{MUTED}][{default + 1}] [/]").strip().lower()
    if not raw:
        return options[default][0]
    if raw in ("q", "quit"):
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1][0]
    for key, main, hint in options:
        if raw == str(key).lower() or raw == main.lower():
            return key
    warn("Unknown choice.")
    return _select_typed(title, options, default)


def select(title, options, default: int = 0, _input=None, _output=None):
    """Single-select navigated with arrow keys (or j/k), number shortcuts, Enter.

    ``options`` is a list of ``(key, main, hint)`` tuples; returns the chosen
    ``key``, or ``None`` if the user cancels (``q`` / Ctrl-C). Falls back to a
    typed numbered prompt when prompt_toolkit is unavailable or stdin is not a
    TTY, so piping/CI still work. ``_input``/``_output`` are test injection hooks.
    """
    default = max(0, min(default, len(options) - 1))
    interactive = _input is not None or (_PT and sys.stdin.isatty())
    if not interactive:
        return _select_typed(title, options, default)

    idx = [default]

    def _move(delta):
        def handler(_event):
            idx[0] = (idx[0] + delta) % len(options)
        return handler

    kb = KeyBindings()
    for key in ("up", "k", "c-p"):
        kb.add(key)(_move(-1))
    for key in ("down", "j", "c-n"):
        kb.add(key)(_move(1))

    @kb.add("enter")
    def _enter(event):
        event.app.exit(result=options[idx[0]][0])

    @kb.add("q")
    @kb.add("c-c")
    def _cancel(event):
        event.app.exit(result=None)

    for _n in range(1, min(len(options), 9) + 1):
        @kb.add(str(_n))
        def _pick(event, i=_n - 1):
            event.app.exit(result=options[i][0])

    def render():
        frags = [("class:title", f"{title}\n")]
        for n, (_key, main, hint) in enumerate(options):
            sel = n == idx[0]
            frags.append(("class:pointer", "❯ ") if sel else ("", "  "))
            frags.append(("class:selected", main) if sel else ("", main))
            if hint:
                frags.append(("class:hint", f"   {hint}"))
            frags.append(("", "\n"))
        return frags

    window = Window(FormattedTextControl(render, focusable=True, show_cursor=False))
    style = Style.from_dict({"title": "bold", "pointer": "bold cyan",
                             "selected": "bold cyan", "hint": "#808080"})
    kwargs = dict(layout=Layout(HSplit([window])), key_bindings=kb, style=style,
                  full_screen=False, mouse_support=False, erase_when_done=True)
    if _input is not None:
        kwargs["input"] = _input
    if _output is not None:
        kwargs["output"] = _output
    return Application(**kwargs).run()


def _tab_menu_typed(actions, tabs, active, default):
    """Typed fallback for tab_menu (no prompt_toolkit / not a TTY)."""
    say("\n[bold]Sorter:[/] " + "   ".join(
        (f"[bold {ACCENT}]▸ {t}[/]" if i == active else t) for i, t in enumerate(tabs)))
    opts = list(actions) + [("__sorter__", "Switch sorter", "cycle to the next sorter")]
    return _select_typed("Choose an action", opts, default), active


def tab_menu(actions, tabs, active: int = 0, default: int = 0, _input=None, _output=None):
    """Tabbed action menu: a top tab bar (one tab per sorter) + an action list.

    Keys: ←/→ (or Tab / Shift-Tab) switch the active tab, ↑/↓ (or j/k) move the
    action list, Enter runs the highlighted action, a number jumps to that action,
    q / Ctrl-C quits. ``actions`` = list of (key, title, hint); ``tabs`` = list of
    display strings. Returns ``(action_key_or_None, active_tab_index)``. Falls back
    to a typed prompt when prompt_toolkit is unavailable or stdin is not a TTY
    (the fallback can return the sentinel key ``"__sorter__"`` to cycle sorter).
    """
    active = max(0, min(active, len(tabs) - 1))
    default = max(0, min(default, len(actions) - 1))
    interactive = _input is not None or (_PT and sys.stdin.isatty())
    if not interactive:
        return _tab_menu_typed(actions, tabs, active, default)

    tab = [active]
    cur = [default]

    def _step(target, delta, n):
        def handler(_event):
            target[0] = (target[0] + delta) % n
        return handler

    kb = KeyBindings()
    for key in ("left", "c-b", "s-tab"):
        kb.add(key)(_step(tab, -1, len(tabs)))
    for key in ("right", "c-f", "tab"):
        kb.add(key)(_step(tab, 1, len(tabs)))
    for key in ("up", "k", "c-p"):
        kb.add(key)(_step(cur, -1, len(actions)))
    for key in ("down", "j", "c-n"):
        kb.add(key)(_step(cur, 1, len(actions)))

    @kb.add("enter")
    def _enter(event):
        event.app.exit(result=(actions[cur[0]][0], tab[0]))

    @kb.add("q")
    @kb.add("c-c")
    def _cancel(event):
        event.app.exit(result=(None, tab[0]))

    for _n in range(1, min(len(actions), 9) + 1):
        @kb.add(str(_n))
        def _pick(event, i=_n - 1):
            event.app.exit(result=(actions[i][0], tab[0]))

    def render():
        frags = [("class:label", "Sorter   ")]
        for i, t in enumerate(tabs):
            frags.append(("class:tab.active", f" {t} ") if i == tab[0] else ("class:tab", f" {t} "))
            frags.append(("", "  "))
        frags.append(("", "\n\n"))
        for n, (_key, title, hint) in enumerate(actions):
            sel = n == cur[0]
            frags.append(("class:pointer", "❯ ") if sel else ("", "  "))
            frags.append(("class:selected", title) if sel else ("", title))
            if hint:
                frags.append(("class:hint", f"   {hint}"))
            frags.append(("", "\n"))
        frags.append(("class:hint", "\n[ ↑/↓ move · ←/→ or Tab switch sorter · Enter select · q quit ]\n"))
        return frags

    window = Window(FormattedTextControl(render, focusable=True, show_cursor=False))
    style = Style.from_dict({
        "label": "bold", "tab": "#808080", "tab.active": "reverse bold cyan",
        "pointer": "bold cyan", "selected": "bold cyan", "hint": "#808080",
    })
    kwargs = dict(layout=Layout(HSplit([window])), key_bindings=kb, style=style,
                  full_screen=False, mouse_support=False, erase_when_done=True)
    if _input is not None:
        kwargs["input"] = _input
    if _output is not None:
        kwargs["output"] = _output
    return Application(**kwargs).run()
