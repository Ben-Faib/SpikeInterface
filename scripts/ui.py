"""Small rich-based terminal UI for SpikeInterface_Menu.py.

Mirrors the look of scripts/run_sorting.py's ConsoleUI (banner rules, cyan/bold
accents, boxed SIMPLE_HEAVY tables, dim detail, green ✓) so the launcher and the
sorter feel like one tool. Everything degrades to plain ``print`` if ``rich`` is
unavailable, and ``rich`` auto-disables colour when stdout is not a TTY.

The palette intentionally matches run_sorting.ConsoleUI.PALETTE.
"""
from __future__ import annotations

import re
import shutil
import sys
from collections import namedtuple

# Selectable accent themes for the UI chrome (headers, tabs, pointer, rules).
# The blue+gold shield is fixed and not affected. Picked via the menu's Theme
# action and persisted locally; see SpikeInterface_Menu.py.
THEMES = {
    "periwinkle": "#9b8cff",
    "sea-green": "#56d39a",
    "steel-blue": "#6ea8fe",
    "amber": "#e3a008",
    "cyan": "#33c5c5",
}
DEFAULT_THEME = "periwinkle"
# ACCENT is mutated by set_accent(); functions read it at call time so a theme
# change takes effect on the next render. MUTED/OK/WARN/BAD are fixed.
ACCENT, MUTED, OK, WARN, BAD = THEMES[DEFAULT_THEME], "dim", "bold green", "#e3a008", "bold red"
# Three-tier neutral text ramp so "secondary but readable" (unit counts, sorter
# descriptions, action hints) is distinct from "disabled" (MUTED/dim). SECONDARY is
# a mid grey (~7:1 contrast on the dark bg) and theme-independent; PRIMARY = "" is
# the terminal's default foreground. Under NO_COLOR both flatten to the default fg.
PRIMARY, SECONDARY = "", "#9aa0a6"

# Shared, plain-language Help content (single source for the Textual HelpScreen
# AND the typed-fallback help). Each entry is (topic_key, title, body_lines).
HELP_TOPICS = [
    ("overview", "Overview",
     ["This tool finds neurons (spike sorting) in a Blackrock/Ripple recording.",
      "Put your recording files in the data folder, then: Explore → Sort → Report."]),
    ("steps", "The 3 steps",
     ["Explore  – quick static figures of your raw data (no sorting needed).",
      "Sort     – detect neurons in the broadband signal with a chosen sorter.",
      "Report   – build an interactive HTML report of the sorted results."]),
    ("sorters", "Sorters",
     ["A 'sorter' is the algorithm that detects neurons. tridesclous2 is the ★",
      "recommended default: fast, reliable, needs no GPU. Others appear in the",
      "sidebar grouped by what your computer can run right now."]),
    ("docker", "Docker (optional)",
     ["Docker lets you run extra sorters your computer doesn't have installed,",
      "without installing them yourself. It's optional — the ★ recommended sorter",
      "needs no Docker. Turning it on downloads a large image the first time and",
      "runs a bit slower; the menu can start Docker Desktop for you."]),
    ("data", "Data files",
     []),   # filled at render time from the live data report (present/missing checklist)
    ("keys", "Keyboard",
     ["↑/↓ or j/k move · ←/→ or Tab/Shift-Tab switch panes · Enter run/activate",
      "1-9 jump to an action · t switch sorter · m animation · ? help · d data files",
      "f choose data folder · q or Ctrl-C quit  (Esc cancels a dialog, not the app)"]),
    ("about", "About",
     ["University of Pittsburgh · SpikeInterface.",
      "A friendly front-end to the SpikeInterface spike-sorting toolkit.",
      "(The Pitt shield also greets you on the Welcome screen.)"]),
]


def set_accent(color: str) -> None:
    """Set the UI accent colour (any rich/prompt_toolkit colour, e.g. a hex)."""
    global ACCENT
    ACCENT = color
# PASS/SKIP/FAIL -> (rich style, glyph) for the pipeline status table.
_BADGE = {"PASS": ("bold green", "✓"), "SKIP": ("dim", "–"), "FAIL": ("bold red", "✗")}
# Same, as prompt_toolkit style-class names (used by the full-screen dashboard).
_BADGE_PT = {"PASS": ("class:pass", "✓"), "SKIP": ("class:skip", "–"), "FAIL": ("class:fail", "✗")}

# University of Pittsburgh shield — authentic blue + gold (the rest of the UI keeps
# its accent). Drawn on a fixed grid of ONLY the full block █ and spaces, so every
# row is exactly the same width in any monospace font/terminal — no ambiguous-width
# glyphs (●, quadrant blocks) that misalign across machines. The empty interior reads
# as the white field; the heraldry sits in negative space, matching the real crest:
# three crenellated turrets, a centre keystone notch, two roundels in the upper field,
# a blue/gold checky band, one roundel below, tapering to the base point.
# B = blue pixel, G = gold pixel, '.'/space = empty.  Each grid is internally square
# (all rows equal width); three sizes feed the responsive ladder (pick_logo) so the
# shield shrinks — full → compact → mini → none — to fit small terminal windows.
_LOGO_BLUE, _LOGO_GOLD = "#1f6feb", "#ffb81c"
_LOGO_ART = [                  # full crest — 21 columns
    ".B.B.B..B.B.B..B.B.B.",   # three crenellated turrets
    ".BBBBB..BBBBB..BBBBB.",   # turret bodies
    "BBBBBBBBBB.BBBBBBBBBB",   # shield top edge + centre keystone notch
    "B...................B",   # upper white field
    "B....BBB.....BBB....B",   # two roundels
    "B...................B",   # upper white field
    "BGGGGGGGGGGGGGGGGGGGB",   # gold band — top margin
    "BGBBGGBBGGBBGGBBGGBGB",   # checky band, row A
    "BGGGBBGGBBGGBBGGBBGGB",   # checky band, row B (offset)
    "BGGGGGGGGGGGGGGGGGGGB",   # gold band — bottom margin
    "B...................B",   # lower white field
    "B........BBB........B",   # one roundel
    ".BB...............BB.",   # taper
    "...BB...........BB...",   # taper
    ".....BB.......BB.....",   # taper
    ".......BB...BB.......",   # taper
    ".........BBB.........",   # base point
]
_LOGO_ART_COMPACT = [          # medium crest — 15 columns
    ".B.B..B.B..B.B.",         # turrets
    ".BBB..BBB..BBB.",         # bodies
    "BBBBBBB.BBBBBBB",         # top edge + notch
    "B..BB.....BB..B",         # two roundels
    "BGBBGGBBGGBBGGB",         # checky band, row A
    "BGGGBBGGBBGGBGB",         # checky band, row B
    "B.............B",         # lower white field
    ".BB.........BB.",         # taper
    "...BB.....BB...",         # taper
    ".....BB.BB.....",         # taper
    "......BBB......",         # base point
]
_LOGO_ART_MINI = [             # small crest — 11 columns
    ".B...B...B.",             # turret nubs
    "BBBBB.BBBBB",             # top edge + notch
    "B..B...B..B",             # two roundels
    "BGBGBGBGBGB",             # gold/checky band
    ".B.......B.",             # taper
    "...B...B...",             # taper
    "....BBB....",             # base point
]


def _build_logo(art):
    """Turn the B/G/space grid into per-row (style, text) fragments (run-length)."""
    rows = []
    for line in art:
        frags, i = [], 0
        while i < len(line):
            j = i
            while j < len(line) and line[j] == line[i]:
                j += 1
            run, ch = line[i:j], line[i]
            style = _LOGO_BLUE if ch == "B" else _LOGO_GOLD if ch == "G" else ""
            frags.append((style, ("█" if ch in "BG" else " ") * len(run)))
            i = j
        rows.append(frags)
    return rows


_LOGO = _build_logo(_LOGO_ART)
_LOGO_COMPACT = _build_logo(_LOGO_ART_COMPACT)
_LOGO_MINI = _build_logo(_LOGO_ART_MINI)

# Responsive ladder, widest first: (width, height, built rows). The dashboard and the
# scrolling banner both pick the largest shield that fits the live terminal, so it
# never wraps a narrow window or crowds the menu off a short one.
_LOGOS = [
    (len(_LOGO_ART[0]), len(_LOGO_ART), _LOGO),
    (len(_LOGO_ART_COMPACT[0]), len(_LOGO_ART_COMPACT), _LOGO_COMPACT),
    (len(_LOGO_ART_MINI[0]), len(_LOGO_ART_MINI), _LOGO_MINI),
]
_LOGO_INDENT = 2  # leading "  " before every shield row

# Public aliases: the built shield rows, by size, for screens that render the
# Pitt crest at a fixed spot (the v2 Welcome screen + Help "About" topic) now
# that the firing neuron — not the shield — is the dashboard's top crest.
SHIELD_FULL, SHIELD_COMPACT, SHIELD_MINI = _LOGO, _LOGO_COMPACT, _LOGO_MINI

# --------------------------------------------------------------------------- #
# Firing-neuron hero — the v2 Textual dashboard's animated top crest (replaces
# the brain). A single neuron: dendrites -> soma -> axon -> action-potential
# spike, drawn in width-safe glyphs ONLY (box-drawing U+2500.. + the full block
# █; NO ●/quadrant blocks, which misalign across fonts — same discipline as the
# shield). menu_app.CrestWidget walks `phase` on a slow timer (receive -> fire ->
# rest); Welcome/Help/the legacy fallback keep the shield. Preview the art with
# `uv run python scripts/_neuron_art_preview.py`.
# --------------------------------------------------------------------------- #
NEURON_BODY = "#ff6fb5"     # calm pink — the resting neuron body
NEURON_SPARK = "#ffe066"    # electric yellow — the travelling pulse + firing AP
NEURON_REST_PHASE = 0.0

# Phase bands over one [0,1) cycle. Most of the cycle is REST (identical frames
# the widget memoises away); the travel+fire window is brief and subtle.
_N_TRAVEL = 0.74   # [0,0.74)    rest          (flat, body colour only)
_N_FIRE = 0.92     # [0.74,0.92) pulse travels the conduction path
                   # [0.92,1.0)  the action potential fires

# rest      : list[str]      equal-width rows, the resting pose
# path      : list[(r,c)]    ordered conduction line (dendrite root -> soma ->
#                            axon terminal); the bright pulse walks it on travel
# soma      : list[(r,c)]    cells that flash on fire
# dendrites : list[(r,c)]    tip cells that flash as the signal first arrives
# ap        : list[(r,c,ch)] action-potential glyphs drawn (spark) over the rest
#                            pose during the fire band (replace blank cells)
_NeuronTier = namedtuple("_NeuronTier", "rest path soma dendrites ap")

_NEURON_FULL = _NeuronTier(           # 28 cols x 7 rows
    rest=[
        " ╲                          ",
        "  ╲                         ",
        "   ███                      ",
        "───███━━━━━━━━━━━━━━━━┳─────",
        "   ███                      ",
        "  ╱                         ",
        " ╱                          ",
    ],
    path=[(3, c) for c in range(0, 28)],
    soma=[(2, 3), (2, 4), (2, 5), (3, 3), (3, 4), (3, 5), (4, 3), (4, 4), (4, 5)],
    dendrites=[(0, 1), (1, 2), (5, 2), (6, 1), (3, 0), (3, 1), (3, 2)],
    ap=[(2, 24, "╱"), (1, 25, "╱"), (1, 26, "╲"), (2, 27, "╲")],
)

_NEURON_COMPACT = _NeuronTier(        # 18 cols x 5 rows
    rest=[
        " ╲                ",
        "  ██              ",
        "──██━━━━━━━━━━┳───",
        "  ██              ",
        " ╱                ",
    ],
    path=[(2, c) for c in range(0, 18)],
    soma=[(1, 2), (1, 3), (2, 2), (2, 3), (3, 2), (3, 3)],
    dendrites=[(0, 1), (4, 1), (2, 0), (2, 1)],
    ap=[(1, 15, "╱"), (0, 16, "╱"), (1, 17, "╲")],
)

_NEURON_MINI = _NeuronTier(           # 11 cols x 3 rows
    rest=[
        " ╲         ",
        "─██━━━━━┳──",
        " ╱         ",
    ],
    path=[(1, c) for c in range(0, 11)],
    soma=[(1, 1), (1, 2)],
    dendrites=[(0, 1), (2, 1), (1, 0)],
    ap=[(0, 9, "╱"), (0, 10, "╲")],
)

_NEURONS = [
    (len(_NEURON_FULL.rest[0]), len(_NEURON_FULL.rest), _NEURON_FULL),
    (len(_NEURON_COMPACT.rest[0]), len(_NEURON_COMPACT.rest), _NEURON_COMPACT),
    (len(_NEURON_MINI.rest[0]), len(_NEURON_MINI.rest), _NEURON_MINI),
]


def _encode_neuron_row(chars, styles):
    """Run-length-merge adjacent cells of equal style into (style, segment)
    fragments — the same row shape _build_logo produces, so _crest_text renders
    the neuron unchanged."""
    frags, i, n = [], 0, len(chars)
    while i < n:
        j = i
        while j < n and styles[j] == styles[i]:
            j += 1
        frags.append((styles[i], "".join(chars[i:j])))
        i = j
    return frags


def neuron_frame(tier, phase=NEURON_REST_PHASE):
    """Built crest rows for `tier` at animation `phase` in [0,1). Body cells are
    NEURON_BODY; the travelling pulse and firing AP are NEURON_SPARK; blanks are
    unstyled. Width is invariant across phases (cells are recoloured/replaced in
    place, never added/removed)."""
    H = len(tier.rest)
    grid = [list(row) for row in tier.rest]
    styles = [[NEURON_BODY if ch != " " else "" for ch in row] for row in tier.rest]

    def spark(r, c):
        if 0 <= r < H and 0 <= c < len(grid[r]) and grid[r][c] != " ":
            styles[r][c] = NEURON_SPARK

    if _N_TRAVEL <= phase < _N_FIRE:                      # signal travels in
        t = (phase - _N_TRAVEL) / (_N_FIRE - _N_TRAVEL)
        head = int(t * len(tier.path))
        for k in (head - 1, head):                        # a 2-cell bright pulse
            if 0 <= k < len(tier.path):
                spark(*tier.path[k])
        if t < 0.25:                                      # tips light as it arrives
            for rc in tier.dendrites:
                spark(*rc)
    elif phase >= _N_FIRE:                                # the AP fires
        for rc in tier.soma:
            spark(*rc)
        for (r, c, ch) in tier.ap:
            if 0 <= r < H and 0 <= c < len(grid[r]):
                grid[r][c] = ch
                styles[r][c] = NEURON_SPARK

    return [_encode_neuron_row(grid[r], styles[r]) for r in range(H)]


def neuron_rest(tier):
    """The resting pose — for static contexts and tests."""
    return neuron_frame(tier, NEURON_REST_PHASE)


def pick_neuron(cols, rows=None, reserve=0):
    """Largest neuron tier (full -> compact -> mini -> none) that fits — same fit
    rules as pick_logo. Returns the _NeuronTier (truthy) or [] when even mini
    won't fit."""
    return _pick(_NEURONS, cols, rows, reserve)


def _term_size():
    """Live (cols, rows). Inside a running prompt_toolkit app, read its output size (so
    the dashboard tracks live resizes); otherwise use the real terminal via shutil.

    NB: ``get_app()`` returns a *DummyApplication* (fixed 80x40) when no app is running,
    which would mask the true terminal — so use ``get_app_or_none()`` and fall through."""
    try:
        from prompt_toolkit.application import get_app_or_none

        app = get_app_or_none()
        if app is not None:
            s = app.output.get_size()
            if s.columns and s.rows:
                return s.columns, s.rows
    except Exception:
        pass
    ts = shutil.get_terminal_size(fallback=(80, 24))
    return ts.columns, ts.lines


def _pick(ladder, cols, rows, reserve):
    """Largest crest in ``ladder`` whose width (+indent) fits ``cols`` and whose
    height fits ``rows - reserve``; ``[]`` if even the smallest tier won't fit.
    ``rows=None`` ignores height (e.g. for scrolling output)."""
    for w, h, art in ladder:
        if w + _LOGO_INDENT > cols:
            continue
        if rows is not None and h > rows - reserve:
            continue
        return art
    return []


def pick_logo(cols, rows=None, reserve=0):
    """Largest Pitt shield (full -> compact -> mini -> none) that fits."""
    return _pick(_LOGOS, cols, rows, reserve)


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


def banner(header: str) -> None:
    """Print the Pitt shield + header line (rich path / typed fallback).

    Output here scrolls, so only width matters: pick the largest shield that fits the
    terminal so a narrow window never wraps the art (and very narrow windows drop it)."""
    cols, _ = _term_size()
    for line in pick_logo(cols):
        say("  " + "".join((f"[{style}]{text}[/]" if style else text) for style, text in line))
    say(f"  [bold {ACCENT}]{header}[/]")


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


_CATALOG_LABEL = {"ready": "READY TO USE", "docker": "DOCKER SORTERS (heavier)",
                  "gpu": "NEEDS A GPU", "unavailable": "NOT AVAILABLE"}
_CATALOG_ORDER = ["ready", "docker", "gpu", "unavailable"]


def print_catalog(catalog) -> None:
    """Plain grouped sorter listing for the typed fallback (read-only overview)."""
    by = {}
    for info in catalog:
        by.setdefault(info.get("group", "unavailable"), []).append(info)
    for group in _CATALOG_ORDER:
        members = by.get(group)
        if not members:
            continue
        say(f"\n[bold {ACCENT}]{_CATALOG_LABEL[group]}[/]")
        for info in members:
            star = "★ " if info.get("recommended") else "  "
            units = f"{info['units']}u" if info.get("present") else "—"
            dim = "" if info.get("runnable") else f"[{MUTED}]"
            dimend = "" if info.get("runnable") else "[/]"
            say(f"  {dim}{star}{info['name']:18} {units:>5}   "
                f"{info.get('description', '')}{dimend}")


def stream_detail(files, pipeline):
    """Map each present file's ext -> the pipeline detail string (ch/rate/duration),
    matching by extension so the 'd' help (and the fallback) can show load detail
    even though the dashboard no longer renders the pipeline panel. Best-effort."""
    out = {}
    for f in files or []:
        ext = f.get("ext", "")
        row = next((r for r in (pipeline or []) if ext in r.get("stage", "")), None)
        if f.get("present") and row and row.get("detail"):
            out[ext] = row["detail"]
    return out


def docker_confirm_text(state: str) -> str:
    """One-line plain-language Docker guidance for the typed fallback, per state."""
    return {
        "running": "Docker is running. Enable extra sorters?",
        "installed_not_running":
            "Docker is installed but not started — start Docker Desktop, then retry.",
        "not_installed":
            "You don't have Docker — download Docker Desktop (docker.com), then retry.",
    }.get(state, "Enable Docker sorters?")


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
    if not options:                       # nothing to choose -> treat as a cancel
        return None
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
    style = Style.from_dict({"title": "bold", "pointer": f"bold {ACCENT}",
                             "selected": f"bold {ACCENT}", "hint": "#808080"})
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


def _sorter_summary(info) -> str:
    return f"{info['units']}u · {info['duration']:.0f}s" if info.get("present") else "no sort"


def dashboard_menu(header, pipeline, infos, active: int = 0, actions=(), default: int = 0,
                   last=None, _input=None, _output=None):
    """Single, in-place full-screen TUI: pinned header + sorter tabs + pipeline
    status + a 'last action' line + the action list, with a key-hint footer.

    The high-level info stays at the top and updates in place; choosing an action
    exits the app (so the action's own output prints below in the normal terminal),
    then the caller re-enters with refreshed data — so there is never more than one
    dashboard on screen. Keys: ←/→ (or Tab/Shift-Tab) switch the sorter tab, ↑/↓
    (or j/k) move the action list, Enter runs it, a number jumps, q/Ctrl-C quits.
    Returns ``(action_key_or_None, active_tab_index)``. Without prompt_toolkit or
    off-TTY it prints a scrolling status panel + a typed menu (which can return the
    sentinel ``"__sorter__"`` to cycle the active sorter).
    """
    active = max(0, min(active, len(infos) - 1))
    default = max(0, min(default, len(actions) - 1))
    interactive = _input is not None or (_PT and sys.stdin.isatty())
    if not interactive:
        banner(header)
        for i, info in enumerate(infos):
            info["active"] = i == active
        sorters_panel(infos)
        status_table(pipeline)
        tabs = [f"{i['name']} · {_sorter_summary(i)}" for i in infos]
        return _tab_menu_typed(actions, tabs, active, default)

    tab = [active]
    cur = [default]

    def _step(target, delta, n):
        def handler(_event):
            target[0] = (target[0] + delta) % n
        return handler

    kb = KeyBindings()
    for key in ("left", "c-b", "s-tab"):
        kb.add(key)(_step(tab, -1, len(infos)))
    for key in ("right", "c-f", "tab"):
        kb.add(key)(_step(tab, 1, len(infos)))
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

    def _saved(info):
        return (f"{info['units']} units · {info['duration']:.1f}s"
                if info.get("present") else "no saved sort")

    def _chip(info):
        # Compact tab label: name + unit count, so both sorters compare at a glance.
        tail = f" · {info['units']}u" if info.get("present") else " · no sort"
        return f" {info['name']}{tail} "

    # The sorter tab bar is horizontal; pipeline stays a column table with an underline.
    tabbar_w = 2 + sum(len(_chip(i)) for i in infos) + 2 * max(0, len(infos) - 1)
    stage_w = max([len("stage")] + [len(r["stage"]) for r in pipeline])
    detail_w = min(max([len("detail")] + [len(r["detail"]) for r in pipeline]), 64)
    W = min(max(tabbar_w, 2 + stage_w + 3 + detail_w, len(header) + 10), 92)
    pipe_uline = "  " + "─" * (stage_w + 3 + detail_w)
    # Lines the body() control emits — so the responsive shield can yield enough rows
    # to keep the whole menu visible on a short terminal. 12 fixed newline-blocks +
    # the variable rows + 1 line of safety so the last action is never clipped.
    body_rows = 13 + (2 if last else 0) + len(pipeline) + len(actions)

    def _trunc(text, n):
        return text if len(text) <= n else text[: max(0, n - 1)] + "…"

    def body():
        f = [("", "\n")]
        if last:
            f += [("class:last", f"  {last}"), ("", "\n\n")]
        # Sorters — a horizontal tab bar; ←/→ (or Tab) switches the active tab.
        f += [("class:section", "  Sorters"),
              ("class:tabhint", "    ‹ ← / → ›"), ("class:hint", " switch"), ("", "\n\n")]
        f.append(("", "  "))
        for i, info in enumerate(infos):
            sel = i == tab[0]
            f.append(("class:tab.active" if sel else "class:tab", _chip(info)))
            if i != len(infos) - 1:
                f.append(("", "  "))
        f += [("", "\n\n")]
        # The active sorter's full saved-sort detail, below the bar.
        f += [("class:hint", "  " + _saved(infos[tab[0]])), ("", "\n\n")]
        # Pipeline — a table
        f += [("class:section", "  Pipeline"), ("", "\n")]
        f += [("class:colhead", "  " + "stage".ljust(stage_w) + "   detail"), ("", "\n")]
        f += [("class:rule", pipe_uline), ("", "\n")]
        for r in pipeline:
            st, glyph = _BADGE_PT.get(r["status"], ("class:skip", r["status"]))
            f += [(st, glyph + " "), ("class:stage", r["stage"].ljust(stage_w)),
                  ("class:hint", "   " + _trunc(r["detail"], detail_w)), ("", "\n")]
        f += [("", "\n")]
        # Actions — the navigable menu (↑/↓ move, Enter runs)
        f += [("class:section", "  Actions"), ("", "\n")]
        for n, (_key, title, hint) in enumerate(actions):
            sel = n == cur[0]
            f.append(("class:pointer", "❯ ") if sel else ("", "  "))
            f.append(("class:selected" if sel else "class:action", title))
            if hint:
                f.append(("class:hint", f"   {hint}"))
            f.append(("", "\n"))
        return f

    # Reserve = body + footer (1) + the banner's own blank line and rule (2).
    def _fit_logo():
        cols, rows = _term_size()
        return cols, pick_logo(cols, rows, reserve=body_rows + 3)

    def banner_ft():
        cols, logo = _fit_logo()
        f = [("", "\n")]
        for line in logo:
            f.append(("", "  "))
            f.extend(line)
            f.append(("", "\n"))
        # Centred title rule (no full border), sized to the body but never past the edge.
        rule_w = min(W, max(len(header) + 2, cols - 1))
        pad = max(0, rule_w - len(header) - 2)
        rule_l, rule_r = "─" * (pad // 2), "─" * (pad - pad // 2)
        f += [("class:rule", rule_l + " "), ("class:header", header), ("class:rule", " " + rule_r)]
        return f

    # Re-evaluated every render (incl. on resize), so the banner height tracks the
    # chosen shield — full → compact → mini → none — as the window grows or shrinks.
    banner_win = Window(FormattedTextControl(banner_ft), height=lambda: len(_fit_logo()[1]) + 2)
    body_win = Window(FormattedTextControl(body, focusable=True, show_cursor=False))
    footer_win = Window(
        FormattedTextControl(lambda: [("class:hint",
            "  ↑/↓ move   ·   ←/→ or Tab switch sorter   ·   Enter select   ·   q quit")]),
        height=1)

    a = ACCENT  # current theme accent (read at call time)
    style = Style.from_dict({
        "header": f"bold {a}",
        "section": f"bold italic {a}",
        "colhead": "bold #d0d7de",
        "rule": "#4a5058",
        "pointer": f"bold {a}",
        "selected": f"bold {a}",
        "tab": "#7d8590",
        "tab.active": f"bold {a} reverse",   # accent-filled pill = the active tab
        "tabhint": f"bold {a}",
        "action": "#d0d7de",
        "stage": "#d0d7de",
        "hint": "#7d8590",
        "last": f"bold {a}",
        "pass": "#3fb950", "fail": "#f85149", "skip": "#7d8590",
    })
    kwargs = dict(layout=Layout(HSplit([banner_win, body_win, footer_win])),
                  key_bindings=kb, style=style, full_screen=True, mouse_support=False)
    if _input is not None:
        kwargs["input"] = _input
    if _output is not None:
        kwargs["output"] = _output
    return Application(**kwargs).run()
