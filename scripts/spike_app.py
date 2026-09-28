"""Spike 2.0 - the Textual app: the journey rail over six stage panes.

The view for ``SpikeInterface_Menu.py`` (goals/GOAL_V2.md is its spec). Like the
screens it reuses from ``menu_app``, it imports no SpikeInterface: every fact comes
from the controller (``SpikeInterface_Menu.MenuController``) as plain data, and
every decision about what is done / stale / next is made there (``journey.py``) -
this module only paints it and routes keys.

    ┌ spike  PFCM7_d0ephys_Block2                 tridesclous2 · run c7184d · curated ┐
    │ ✓ 1 Data ──── ✓ 2 Probe ──── ✓ 3 Sort ──── ▸ 4 Judge ──── · 5 Apply ──── · 6 Share│
    │   3 streams     16 contacts    16 units      4/16                                │
    │ ───────────────────────────────────────────────────────────────────────────────  │
    │ the active pane: Home (next step, where things stand, units on the probe) or a   │
    │ stage: 1 Data · 2 Probe · 3 Sort · 4 Judge · 5 Apply · 6 Share                   │
    │ status line                                                                      │
    │  ↵  next step   1-6  stages   /  find anything   ,  settings   ?  help   q  quit  │
    └──────────────────────────────────────────────────────────────────────────────────┘

Keys: ``1``-``6`` jump to a stage, ``Esc`` returns Home (and never exits), ``/``
finds any action by name, ``,`` opens Settings, ``?`` help, ``q`` quit. Letters act
only inside the pane that prints them on its key line.
"""
from __future__ import annotations

import os
import subprocess
from time import monotonic
from typing import Protocol

from rich.text import Text
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import ContentSwitcher, Input, OptionList, Static
from textual.widgets.option_list import Option

import download_stats as dlstats
import menu_app as _m
import ui
from menu_app import (BuildProgressScreen, BusyScreen, ChoiceModal, DockerConfirmScreen,
                      DownloadProgressScreen, ManageSortersScreen, NavList,
                      ParamEditorScreen, ProbeEditorScreen, SortProgressScreen)

GREEN, AMBER, RED = "#3fb950", "#e3a008", "#f85149"
SEC, MUTED, FAINT = "#9aa0a6", "#6e7681", "#3a3f47"
INK_ON_ACCENT = "#15141f"
CHIP_BG = "#2c2a44"
CHIP_FG = "#c8d0fb"
STAGE_NAMES = ("Data", "Probe", "Sort", "Judge", "Apply", "Share")
_MARK = {"done": ("✓", GREEN), "warn": ("!", AMBER), "todo": ("·", MUTED)}
_LABEL_STYLE = {"good": GREEN, "MUA": AMBER, "noise": MUTED, "unsure": SEC}
_LABEL_GLYPH = {"good": "●", "MUA": "◆", "noise": "×", "unsure": "○"}
_TRIAGE_KEYS = (("g", "good"), ("m", "MUA"), ("n", "noise"), ("u", "unsure"))
SPARK = "▁▂▃▄▅▆▇█"


class Controller(Protocol):
    """What the app reads and calls (implemented by SpikeInterface_Menu.MenuController;
    tests drive a FakeController with the same shape). Attributes are read on every
    paint; everything is plain data."""

    accent: str
    theme_name: str
    themes: dict
    active_sorter: str
    active_probe: str
    use_docker: bool
    quick_seconds: int
    data_report: dict           # files present / missing, data_dir, base
    probe_info: dict            # the active probe: label, summary, match
    infos: list                 # every sorter: group, runnable, present, units ...
    actions: list               # the palette: {key, title, hint, needs_data, stage}
    journey: dict               # journey.snapshot(): data, run, units, curation ...
    stages: list                # journey.stage_status(): the rail
    steps: list                 # journey.next_steps(): the next-step card, best first
    probe_map: dict             # journey.probe_map(): units at their contacts
    recent: list                # journey.recent()
    share_rows: list            # journey.outputs(): the Share stage

    def reload(self) -> None: ...
    def refresh_journey(self) -> None: ...
    def settings_rows(self) -> list: ...
    def set_setting(self, key: str, raw) -> "tuple[bool, str]": ...
    def reset_setting(self, key: str) -> "tuple[bool, str]": ...
    def sort_preview(self) -> list: ...
    def sort_command(self, span) -> list: ...
    def sort_log_path(self, span=None): ...
    def sort_expectations(self) -> dict: ...
    def command(self, key: str, run_id=None) -> dict: ...
    def finish_command(self, key: str, ok: bool) -> str: ...
    def report_command(self) -> list: ...
    def triage_state(self) -> dict: ...
    def label_unit(self, unit_id, label: str) -> "tuple[bool, str]": ...
    def unit_evidence(self, unit_id) -> "dict | None": ...
    def apply_preview(self) -> dict: ...
    def probe_catalog(self) -> list: ...
    def probe_detail(self, name=None) -> dict: ...
    def set_active_probe(self, name: str) -> bool: ...
    def save_probe(self, profile) -> "tuple[bool, str]": ...
    def delete_probe(self, name: str) -> "tuple[bool, str]": ...
    def duplicate_probe(self, name, new_name, new_label=None) -> dict: ...
    def import_probe(self, path: str) -> "tuple[bool, str]": ...
    def runs_overview(self) -> list: ...
    def run_recipe(self, run_id: str) -> dict: ...
    def reproduce_reports(self, run_id: str) -> list: ...
    def export_recipe(self, run_id=None) -> "tuple[bool, str]": ...
    def make_current(self, run_id: str) -> "tuple[bool, str]": ...
    def open_output(self, key: str) -> "tuple[bool, str]": ...
    def open_path(self, path) -> "tuple[bool, str]": ...
    def open_data_folder(self) -> "tuple[bool, str]": ...
    def startup_checklist(self) -> list: ...
    def units_page_exists(self) -> bool: ...
    def open_units(self, unit=None) -> "tuple[bool, str]": ...
    # the sorter catalog, Docker and the reused modals
    def set_active_by_name(self, name: str) -> bool: ...
    def saved_sorters(self) -> list: ...
    def active_blocked_on_docker(self) -> bool: ...
    def docker_status(self, refresh: bool = False) -> dict: ...
    def toggle_docker(self) -> bool: ...
    def start_docker(self) -> bool: ...
    def download_image(self, name, on_progress=None, on_status=None, should_cancel=None): ...
    def delete_image(self, name: str) -> "tuple[bool, str]": ...
    def clear_saved_sort(self, name: str) -> "tuple[bool, str]": ...
    def default_params(self, sorter: str) -> dict: ...
    def param_descriptions(self, sorter: str) -> dict: ...
    def get_overrides(self, sorter: str) -> dict: ...
    def set_params(self, sorter: str, overrides: dict) -> None: ...
    def set_theme(self, name: str) -> str: ...
    def run(self, key: str, span) -> "tuple[bool, str, bool]": ...
    def run_compare(self, pair) -> "tuple[bool, str, bool]": ...
    def record_result(self, key: str, ok: bool) -> None: ...
    def reopen_last(self) -> "tuple[bool, str]": ...
    def report_log_path(self): ...


# --------------------------------------------------------------------------- #
# Pure painters (Text in, Text out - unit-testable without an app)
# --------------------------------------------------------------------------- #
def chip(key: str, style: str = f"bold {CHIP_FG} on {CHIP_BG}") -> Text:
    t = Text()
    t.append(f" {key} ", style=style)
    return t


def key_line(items, width: int) -> Text:
    """The pane's key line: every key the pane accepts, as a chip + a word. When the
    width runs out, trailing items drop whole (never half a label); the first items
    are the pane's own, the last are the app-wide ones that Help also lists."""
    parts = []
    for k, label in items:
        t = chip(k)
        t.append(f" {label}", style=SEC)
        parts.append(t)
    for gap in ("   ", "  "):
        out, used = Text(no_wrap=True), 0
        for i, p in enumerate(parts):
            need = len(p) + (len(gap) if i else 0)
            if used + need > width:
                break
            if i:
                out.append(gap)
            out.append_text(p)
            used += need
        else:
            return out
    return out


def rail_lines(stages, current: int, accent: str, width: int) -> "tuple[Text, Text]":
    """The journey rail: six stage chips joined by rules, and their captions."""
    chips = []
    for s in stages or [{"n": i + 1, "label": n, "mark": "todo", "caption": ""}
                        for i, n in enumerate(STAGE_NAMES)]:
        glyph, color = _MARK.get(s["mark"], _MARK["todo"])
        chips.append((s, glyph, color, f" {glyph} {s['n']} {s['label']} "))
    base = sum(len(c[3]) for c in chips)
    compact = base + 5 * 2 > width
    if compact:
        chips = [(s, g, c, f" {g}{s['n']} {s['label'][:1]}" + " ") for s, g, c, _ in chips]
        base = sum(len(c[3]) for c in chips)
    gap = max(1, min(8, (width - base) // 5))
    top, cap = Text(no_wrap=True), Text(no_wrap=True)
    for i, (s, glyph, color, label) in enumerate(chips):
        x0 = len(top)
        if s["n"] == current:
            top.append(label, style=f"bold {INK_ON_ACCENT} on {accent}")
        else:
            top.append(label[:2], style=f"bold {color}")
            top.append(label[2:], style="bold" if s["mark"] != "todo" else MUTED)
        room = (len(label) + gap - 1) if i < 5 else max(1, width - x0 - 1)
        caption = (s.get("caption") or "")[:max(0, room)]
        cap.append(" " * max(0, x0 + 1 - len(cap)))
        cap.append(caption, style=MUTED)
        if i < 5:
            top.append("─" * gap, style=FAINT)
    top.truncate(width)
    cap.truncate(width)
    return top, cap


def _px_text(grid) -> "list[Text]":
    """A pixel grid (rows of colour or None; even height) as two-tone half blocks."""
    out = []
    for r in range(0, len(grid), 2):
        top = grid[r]
        bot = grid[r + 1] if r + 1 < len(grid) else [None] * len(top)
        t = Text(no_wrap=True)
        for a, b in zip(top, bot):
            if a is None and b is None:
                t.append(" ")
            elif a == b:
                t.append("█", style=a)
            elif a and b:
                t.append("▀", style=f"{a} on {b}")
            elif a:
                t.append("▀", style=a)
            else:
                t.append("▄", style=b)
        out.append(t)
    return out


def line_plot(values, width: int, rows: int, color: str, lo=None, hi=None) -> "list[Text]":
    """A connected line through ``values`` (resampled to ``width``) in half blocks."""
    if not values:
        return [Text(" " * width) for _ in range(rows)]
    n = len(values)
    vals = [values[min(n - 1, int(i * n / width))] for i in range(width)]
    lo = min(vals) if lo is None else lo
    hi = max(vals) if hi is None else hi
    span = (hi - lo) or 1.0
    ph = rows * 2
    grid = [[None] * width for _ in range(ph)]
    prev = None
    for x, v in enumerate(vals):
        py = int(round((hi - v) / span * (ph - 1)))
        py = max(0, min(ph - 1, py))
        a, b = (py, py) if prev is None else (min(py, prev), max(py, prev))
        for y in range(a, b + 1):
            grid[y][x] = color
        prev = py
    return _px_text(grid)


def bar_rows(counts, rows: int, color: str, hot: int = 0, hot_color: str = AMBER) -> "list[Text]":
    """Vertical bars with eighth-block tops; the first ``hot`` bars in ``hot_color``."""
    top = max(counts) if counts and max(counts) > 0 else 1
    out = []
    for r in range(rows):
        t = Text(no_wrap=True)
        for i, c in enumerate(counts):
            h8 = c / top * rows * 8
            lvl = h8 - (rows - 1 - r) * 8
            ch = "█" if lvl >= 8 else (SPARK[int(lvl) - 1] if lvl >= 1 else " ")
            t.append(ch, style=hot_color if i < hot else color)
        out.append(t)
    return out


def spark(values) -> str:
    vals = [abs(v) for v in values if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    return "".join(SPARK[min(7, int((v - lo) / span * 7.999))] for v in vals)


_BOLD_FONT = {
    "S": [" ####### ", "#########", "###      ", "###      ", "######## ",
          " ########", "      ###", "      ###", "#########", " ####### "],
    "P": ["######## ", "#########", "###   ###", "###   ###", "#########",
          "######## ", "###      ", "###      ", "###      ", "###      "],
    "I": ["#########", "#########", "   ###   ", "   ###   ", "   ###   ",
          "   ###   ", "   ###   ", "   ###   ", "#########", "#########"],
    "K": ["###   ###", "###  ### ", "### ###  ", "######   ", "#####    ",
          "######   ", "### ###  ", "###  ### ", "###   ###", "###   ###"],
    "E": ["#########", "#########", "###      ", "###      ", "#######  ",
          "#######  ", "###      ", "###      ", "#########", "#########"],
}
WORDMARK_COLS = 5 * 9 + 4 * 2 + 1


def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def wordmark(accent: str) -> "list[Text]":
    """The SPIKE wordmark: a bold pixel face with a drop shadow, shaded from near
    white at the top to the accent at the base (5 text rows, WORDMARK_COLS wide)."""
    h, word, gap = 10, "SPIKE", 2
    rows = ["".join(_BOLD_FONT[c][r] + (" " * gap if i < len(word) - 1 else "")
                    for i, c in enumerate(word)) for r in range(h)]
    w = len(rows[0]) + 1
    grid = [[None] * w for _ in range(h + 2)]
    shadow = "#2b2a3a"
    for r in range(h):
        for x, c in enumerate(rows[r]):
            if c == "#":
                grid[r + 1][x + 1] = shadow
    for r in range(h):
        col = _mix("#e6e8ff", accent, r / (h - 1))
        for x, c in enumerate(rows[r]):
            if c == "#":
                grid[r][x] = col
    return _px_text(grid[:h + 2])


def fmt_when(when) -> str:
    if not when:
        return ""
    try:
        return _m._fmt_when(str(when)[:19])
    except Exception:  # noqa: BLE001
        return str(when)


def _row_text(key: str, title: str, hint: str, width: int, *, disabled=False,
              note: str = "") -> Text:
    """A pane action row: key chip, title, and what it produces (or why it can't)."""
    t = Text(no_wrap=True)
    t.append_text(chip(key, style=f"bold {MUTED} on #24232f" if disabled
                       else f"bold {CHIP_FG} on {CHIP_BG}"))
    t.append("  ")
    t.append(f"{title:<26}", style=MUTED if disabled else "bold")
    if note:
        t.append(note, style=AMBER)
    elif hint:
        t.append(hint, style=MUTED)
    t.truncate(max(8, width))
    return t


def _section(label: str) -> Text:
    return Text(label, style=f"bold {SEC}")


# --------------------------------------------------------------------------- #
# Small modals
# --------------------------------------------------------------------------- #
class InputModal(ModalScreen):
    """One value, typed: a title, what it affects, the input, and the validator's
    answer in place. ``submit(value) -> (ok, message)`` decides; the modal stays
    open on a refusal so the researcher can fix the value."""

    DEFAULT_CSS = """
    InputModal { align: center middle; }
    InputModal > #dialog { width: 70; max-width: 94%; height: auto;
        border: round $accentcolor; background: $surface; padding: 1 2; }
    InputModal #ititle { text-style: bold; color: $accentcolor; }
    InputModal #ihelp { color: $text-muted; padding: 0 0 1 0; }
    InputModal #ierror { color: #f85149; height: auto; }
    InputModal #ifoot { color: $text-muted; padding: 1 0 0 0; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, title: str, value: str, help_text: str, submit):
        super().__init__()
        self._title, self._value, self._help, self._submit = title, value, help_text, submit

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="ititle")
            yield Static(self._help, id="ihelp")
            yield Input(value=self._value, id="ivalue")
            yield Static("", id="ierror")
            yield Static("↵ save · esc cancel", id="ifoot")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        ok, msg = self._submit(event.value)
        if ok:
            self.dismiss(msg)
        else:
            self.query_one("#ierror", Static).update(Text("✗ " + msg, style=RED))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen):
    """A destructive action, stated in full, confirmed with y."""

    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    ConfirmModal > #dialog { width: 64; max-width: 94%; height: auto;
        border: round #f85149; background: $surface; padding: 1 2; }
    ConfirmModal #ctitle { text-style: bold; color: #f85149; }
    ConfirmModal #cfoot { color: $text-muted; padding: 1 0 0 0; }
    """
    BINDINGS = [Binding("escape", "no", "Cancel", show=False),
                Binding("n", "no", "No", show=False),
                Binding("y", "yes", "Yes", show=False)]

    def __init__(self, title: str, body: str):
        super().__init__()
        self._title, self._body = title, body

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="ctitle")
            yield Static(self._body)
            yield Static("y yes, do it · n / esc keep it", id="cfoot")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class CommandScreen(ModalScreen):
    """Run one child process in-app: its name, a ticking clock, the last lines of
    its output (the full output goes to a log), Esc to cancel, ↵ to close when it
    is done. Dismisses ``(ok, message)``. Used for everything that is not a sort or
    a report build (those have their own protocol-speaking screens)."""

    DEFAULT_CSS = """
    CommandScreen { align: center middle; }
    CommandScreen > #dialog { width: 90; max-width: 96%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2; }
    CommandScreen #ctitle { text-style: bold; color: $accentcolor; }
    CommandScreen #cbody { height: auto; padding: 1 0 0 0; }
    CommandScreen #cfoot { color: $text-muted; padding: 1 0 0 0; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False),
                Binding("enter", "close", "Close", show=False)]
    _SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    TAIL = 8

    def __init__(self, argv: list, title: str, log_path, accent: str):
        super().__init__()
        self._argv, self._title, self._log, self._accent = argv, title, log_path, accent
        self._proc = None
        self._t0 = monotonic()
        self._done = None           # (ok, message) once finished
        self._tick = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="ctitle")
            yield Static("", id="cbody")
            yield Static("esc cancel", id="cfoot")

    def on_mount(self) -> None:
        self._log.parent.mkdir(parents=True, exist_ok=True)
        self.run_worker(self._run, thread=True)
        self.set_interval(0.25, self._repaint)

    def _run(self) -> None:
        try:
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            with open(self._log, "w", encoding="utf-8", errors="replace") as fh:
                kw = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                      if os.name == "nt" else {"start_new_session": True})
                self._proc = subprocess.Popen(self._argv, stdout=fh, stderr=subprocess.STDOUT,
                                              stdin=subprocess.DEVNULL, env=env, **kw)
                rc = self._proc.wait()
            ok = rc == 0
            self._done = (ok, "" if ok else f"exited ({rc})")
        except Exception as e:  # noqa: BLE001 - a launch failure is a result, not a crash
            self._done = (False, f"couldn't start: {e}")

    def _tail(self) -> "list[str]":
        try:
            with open(self._log, encoding="utf-8", errors="replace") as fh:
                lines = [ln.rstrip() for ln in fh.read().replace("\r", "\n").splitlines()]
        except OSError:
            return []
        return [ln for ln in lines if ln.strip()][-self.TAIL:]

    def _repaint(self) -> None:
        self._tick += 1
        el = int(monotonic() - self._t0)
        t = Text()
        if self._done is None:
            t.append(self._SPIN[self._tick % len(self._SPIN)] + " ", style=self._accent)
            t.append(f"running · {el // 60}:{el % 60:02d}\n", style="bold")
        else:
            ok, msg = self._done
            t.append(("✓ done" if ok else "✗ failed " + msg) + f" · {el // 60}:{el % 60:02d}\n",
                     style=f"bold {GREEN if ok else RED}")
        t.append("\n")
        for ln in self._tail():
            t.append(ln[:84] + "\n", style=SEC)
        t.append(f"\nfull output: {self._log}", style=MUTED)
        self.query_one("#cbody", Static).update(t)
        self.query_one("#cfoot", Static).update(
            "↵ close" if self._done is not None else "esc cancel")

    def action_cancel(self) -> None:
        if self._done is None and self._proc is not None:
            _m._kill_proc_tree(self._proc)
            self._done = (False, "cancelled")
        self.dismiss((False, "cancelled") if self._done is None or
                     self._done[1] == "cancelled" else self._done)

    def action_close(self) -> None:
        if self._done is not None:
            self.dismiss(self._done)


# --------------------------------------------------------------------------- #
# Full screens: Splash, Help, Palette, Settings, Runs, Reproduce report
# --------------------------------------------------------------------------- #
class SplashScreen(Screen):
    """The launch: the wordmark and the real startup checklist. Any key skips it;
    it leaves on its own after a moment."""

    DEFAULT_CSS = """
    SplashScreen { align: center middle; background: $background; }
    SplashScreen #splash { width: auto; height: auto; }
    """
    SECONDS = 1.6

    def __init__(self, controller, accent: str):
        super().__init__()
        self._c, self._accent = controller, accent

    def compose(self) -> ComposeResult:
        yield Static(self._body(), id="splash")

    def _body(self) -> Text:
        t = Text(no_wrap=True)
        for row in wordmark(self._accent):
            t.append_text(row)
            t.append("\n")
        t.append("\n")
        t.append("  the SpikeInterface workbench · University of Pittsburgh\n\n", style=SEC)
        for ok, label, text in getattr(self._c, "startup_checklist", lambda: [])():
            g, col = ("✓", GREEN) if ok else (("·", MUTED) if ok is None else ("!", AMBER))
            t.append(f"  {g}  ", style=f"bold {col}")
            t.append(f"{label:<11}", style=MUTED)
            t.append(str(text)[:70] + "\n")
        t.append("\n  press any key", style=MUTED)
        return t

    def on_mount(self) -> None:
        self._left = False
        self.set_timer(self.SECONDS, self._leave)

    def _leave(self) -> None:
        """Dismiss once, returning nothing: a timer awaits whatever its callback
        returns, and awaiting dismiss() from this screen's own handler raises
        ScreenError (the crash a real launch hit when the timer fired)."""
        if self._left:
            return
        self._left = True
        self.dismiss(None)

    def on_key(self, event) -> None:
        event.stop()
        self._leave()

    def on_click(self, _event) -> None:
        self._leave()


class HelpScreen(Screen):
    DEFAULT_CSS = """
    HelpScreen { background: $background; }
    HelpScreen #helpscroll { height: 1fr; padding: 1 2; }
    HelpScreen #helpfoot { dock: bottom; height: 1; padding: 0 2; }
    """
    BINDINGS = [Binding("escape", "close", "Back", show=False),
                Binding("question_mark", "close", "Back", show=False),
                Binding("q", "close", "Back", show=False)]

    def __init__(self, accent: str, data_report: "dict | None" = None):
        super().__init__()
        self._accent = accent
        self._data = data_report or {}

    def _data_lines(self) -> list:
        d = self._data
        out = [f"folder  {d.get('data_dir', '?')}"]
        for f in d.get("files") or []:
            mark = "✓" if f.get("present") else "✗ missing"
            out.append(f"{mark:<10}{(d.get('base') or '<name>') + f['ext']:<32}{f['label']}")
        if not d.get("present"):
            out.append("Put the three files in that folder, or press f on 1 Data.")
        return out

    def compose(self) -> ComposeResult:
        t = Text()
        for key, title, lines in ui.HELP_TOPICS:
            if key == "data":
                lines = self._data_lines()
            if not lines:
                continue
            t.append(title.upper() + "\n", style=f"bold {self._accent}")
            for ln in lines:
                t.append("  " + ln + "\n")
            t.append("\n")
        with VerticalScroll(id="helpscroll"):
            yield Static(t, id="helpbody")
        yield Static(key_line([("esc", "back")], 80), id="helpfoot")

    def action_close(self) -> None:
        self.dismiss(None)


def _fuzzy(query: str, text: str) -> "tuple[int, list] | None":
    """Subsequence match: (score, matched positions) or None. Lower score = better:
    contiguous and early matches win."""
    q, t = query.lower().strip(), text.lower()
    if not q:
        return 0, []
    start = t.find(q)
    if start >= 0:
        return start, list(range(start, start + len(q)))
    pos, i = [], 0
    for ch in q:
        if ch == " ":
            continue
        i = t.find(ch, i)
        if i < 0:
            return None
        pos.append(i)
        i += 1
    return 100 + (pos[-1] - pos[0]), pos


class PaletteScreen(ModalScreen):
    """`/`: type part of any action's name; ↵ runs it. Dismisses the action key."""

    DEFAULT_CSS = """
    PaletteScreen { align: center top; }
    PaletteScreen > #dialog { width: 72; max-width: 96%; height: auto; max-height: 80%;
        margin: 3 0 0 0; border: round $accentcolor; background: $surface; padding: 0 1; }
    PaletteScreen #ptitle { text-style: bold; color: $accentcolor; padding: 1 1 0 1; }
    PaletteScreen Input { border: none; background: $surface; }
    PaletteScreen #plist { height: auto; max-height: 20; border: none; background: $surface; }
    PaletteScreen #pfoot { color: $text-muted; padding: 0 1 1 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Close", show=False),
                Binding("down", "move(1)", show=False), Binding("up", "move(-1)", show=False)]

    def __init__(self, actions: list, accent: str):
        super().__init__()
        self._actions, self._accent = actions, accent

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("FIND ANYTHING", id="ptitle")
            yield Input(placeholder="type part of a name: sort, probe, phy, reproduce…",
                        id="pinput")
            yield OptionList(id="plist")
            yield Static("↑↓ choose · ↵ run · esc close", id="pfoot")

    def on_mount(self) -> None:
        self._fill("")
        self.query_one(Input).focus()

    def _fill(self, query: str) -> None:
        ol = self.query_one("#plist", OptionList)
        ol.clear_options()
        hits = []
        for a in self._actions:
            m = _fuzzy(query, a["title"])
            on_title = m is not None
            if m is None and query and query.lower().strip() in a.get("hint", "").lower():
                m = (0, [])
            if m is None:
                continue
            hits.append((m[0] + (0 if on_title else 500), a, m[1] if on_title else []))
        hits.sort(key=lambda h: h[0])
        for _score, a, pos in hits:
            t = Text(no_wrap=True)
            for i, ch in enumerate(a["title"]):
                t.append(ch, style=f"bold {self._accent}" if i in pos else "")
            where = f"{a['stage']} {STAGE_NAMES[a['stage'] - 1]}" if a.get("stage") else ""
            t.truncate(30)
            t.append(" " * max(2, 32 - len(t)))
            t.append(f"{a.get('hint', '')[:21]:<23}", style=MUTED)
            t.append(where, style=SEC)
            t.truncate(64)
            ol.add_option(Option(t, id=a["key"]))
        if ol.option_count:
            ol.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._fill(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        ol = self.query_one("#plist", OptionList)
        if ol.highlighted is not None and ol.option_count:
            self.dismiss(ol.get_option_at_index(ol.highlighted).id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def action_move(self, step: int) -> None:
        ol = self.query_one("#plist", OptionList)
        if ol.option_count:
            cur = ol.highlighted or 0
            ol.highlighted = max(0, min(ol.option_count - 1, cur + step))

    def action_cancel(self) -> None:
        self.dismiss(None)


class SettingsScreen(Screen):
    """`,`: every setting, grouped, each a row with its value, its default when it
    was changed, and what it affects (settings.py owns the list). ↵ edits in place,
    d resets. Link rows name the screen that edits them and go there."""

    DEFAULT_CSS = """
    SettingsScreen { background: $background; }
    SettingsScreen #stitle { height: 1; padding: 0 2; margin: 1 0 0 0; }
    SettingsScreen #sintro { height: auto; padding: 0 2 1 2; color: $text-muted; }
    SettingsScreen #slist { height: 1fr; border: none; padding: 0 1; }
    SettingsScreen #slist:focus { border: none; }
    SettingsScreen #shelp { height: 3; padding: 0 2; }
    SettingsScreen #sfoot { dock: bottom; height: 2; padding: 0 2; }
    """
    BINDINGS = [Binding("escape", "close", "Back", show=False),
                Binding("d", "reset", "Reset", show=False),
                Binding("comma", "close", "Back", show=False)]

    def __init__(self, app_ref, focus_key: "str | None" = None):
        super().__init__()
        self._a = app_ref
        self._c = app_ref.c
        self._focus_key = focus_key
        self._msg = None

    def compose(self) -> ComposeResult:
        yield Static(Text("SETTINGS", style=f"bold {self._a._accent}"), id="stitle")
        yield Static("Every value the next sort uses. Saved in .si_menu.json in this folder; "
                     "each sort records what it ran with in its run_info.json.", id="sintro")
        yield NavList(id="slist")
        yield Static("", id="shelp")
        yield Static("", id="sfoot")

    def on_mount(self) -> None:
        self._fill()
        self.query_one("#slist").focus()

    def _rows(self):
        return self._c.settings_rows()

    def _fill(self) -> None:
        ol = self.query_one("#slist", OptionList)
        keep = self._current_key() or self._focus_key
        ol.clear_options()
        group = None
        width = max(40, self.size.width - 6)
        for r in self._rows():
            if r["group"] != group:
                group = r["group"]
                ol.add_option(Option(Text(("\n" if ol.option_count else "") + group.upper(),
                                          style=f"bold {SEC}"), disabled=True))
            t = Text(no_wrap=True)
            t.append(f"  {r['label']:<30}", style="bold")
            if r["kind"] == "link":
                t.append(f"{r['value']}", style=self._a._accent)
                t.append("   ↵ opens its screen", style=MUTED)
            else:
                t.append(f"{r['value']}", style=AMBER if not r["is_default"] else "")
                if r.get("invalid") is not None:
                    t.append(f"   saved {r['invalid']} is not usable: default in use",
                             style=RED)
                elif not r["is_default"]:
                    t.append(f"   default {r['default']}", style=MUTED)
            t.truncate(width)
            ol.add_option(Option(t, id=r["key"]))
        want = next((i for i in range(ol.option_count)
                     if keep is not None and ol.get_option_at_index(i).id == keep), None)
        if want is None:
            want = next(i for i in range(ol.option_count)
                        if not ol.get_option_at_index(i).disabled)
        ol.highlighted = want
        self._show_help()

    def _current_key(self):
        try:
            ol = self.query_one("#slist", OptionList)
        except Exception:  # noqa: BLE001 - not mounted yet
            return None
        if ol.highlighted is None or not ol.option_count:
            return None
        return ol.get_option_at_index(ol.highlighted).id

    def _row(self, key):
        return next((r for r in self._rows() if r["key"] == key), None)

    def _show_help(self) -> None:
        r = self._row(self._current_key())
        t = Text()
        if r:
            t.append(r["help"] + "\n", style=SEC)
            if r["kind"] in ("float", "int") and "min" in r:
                t.append(f"allowed {r['min']:g} to {r['max']:g}", style=MUTED)
            elif r["kind"] == "choice":
                t.append("one of: " + ", ".join(r["choices"]), style=MUTED)
        self.query_one("#shelp", Static).update(t)
        foot = Text()
        if self._msg is not None:
            foot.append_text(self._msg)
        foot.append("\n")
        foot.append_text(key_line([("↑↓", "setting"), ("↵", "edit"), ("d", "back to default"),
                                   ("esc", "done")], max(20, self.size.width - 4)))
        self.query_one("#sfoot", Static).update(foot)

    def on_option_list_option_highlighted(self, _event) -> None:
        self._show_help()

    def say(self, ok: bool, msg: str) -> None:
        self._msg = Text(("✓ " if ok else "✗ ") + msg, style=GREEN if ok else RED)
        self._fill()
        self._a.refresh_all()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        r = self._row(event.option.id)
        if r is None:
            return
        kind, key = r["kind"], r["key"]
        if kind == "link":
            self._a.open_link(r["link"], self)
        elif kind == "bool":
            ok, msg = self._c.set_setting(key, r["value"] != "on")
            self.say(ok, msg)
        elif kind == "choice":
            opts = [(c, c, "(current)" if c == r["value"] else "") for c in r["choices"]]
            self.app.push_screen(ChoiceModal(r["label"], opts),
                                 lambda v: v and self.say(*self._c.set_setting(key, v)))
        else:
            value = "" if r["value"] in ("none", "this project folder") and kind != "path" \
                else r["value"]
            if kind == "path":
                value = r["value"]
            self.app.push_screen(
                InputModal(r["label"], value, r["help"],
                           lambda raw: self._c.set_setting(key, raw)),
                lambda msg: msg and self.say(True, msg))

    def action_reset(self) -> None:
        key = self._current_key()
        if key:
            self.say(*self._c.reset_setting(key))

    def action_close(self) -> None:
        self.dismiss(None)


def _verdict_style(verdict: str) -> str:
    v = (verdict or "").upper()
    if v.startswith("NOT") or "OUTSIDE" in v or "DIFFERS" in v:
        return RED
    if "CAVEAT" in v or "INFORMATIONAL" in v:
        return AMBER
    if v.startswith("REGENERATED") or v in ("MATCH", "WITHIN TOLERANCE"):
        return GREEN
    return SEC


class ReproduceReportScreen(Screen):
    """The match report of one reproduce check, criterion by criterion."""

    DEFAULT_CSS = """
    ReproduceReportScreen { background: $background; }
    ReproduceReportScreen #rscroll { height: 1fr; padding: 1 2; }
    ReproduceReportScreen #rfoot { dock: bottom; height: 1; padding: 0 2; }
    """
    BINDINGS = [Binding("escape", "close", "Back", show=False)]

    def __init__(self, data: dict, accent: str):
        super().__init__()
        self._d, self._accent = data or {}, accent

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="rscroll"):
            yield Static(self._body(), id="rbody")
        yield Static(key_line([("esc", "back")], 60), id="rfoot")

    def _body(self) -> Text:
        rep = self._d.get("report")
        t = Text()
        t.append("REPRODUCE CHECK\n", style=f"bold {self._accent}")
        if not rep:
            t.append("\nThe sort ran, but there was nothing to compare it with.\n", style=AMBER)
            t.append(f"output: {self._d.get('out', '?')}\n", style=MUTED)
            return t
        t.append(f"recorded run     {rep.get('recorded_run')}\n", style=SEC)
        t.append(f"re-run from its recipe  {rep.get('regenerated_run')}\n", style=SEC)
        t.append(f"output           {self._d.get('out')}\n\n", style=MUTED)
        t.append(f"{'':2}{'what':<22}{'recorded':<18}{'re-run':<18}{'tolerance':<18}verdict\n",
                 style=f"bold {SEC}")
        for c in rep.get("criteria") or []:
            t.append(f"  {str(c['name'])[:21]:<22}")
            t.append(f"{str(c['recorded'])[:17]:<18}")
            t.append(f"{str(c['regenerated'])[:17]:<18}")
            t.append(f"{str(c['tolerance'])[:17]:<18}", style=MUTED)
            t.append(f"{c['verdict']}\n", style=_verdict_style(c["verdict"]))
            if c.get("note"):
                t.append(f"      {c['note'][:92]}\n", style=MUTED)
        t.append("\n")
        t.append(f"VERDICT  {rep.get('verdict')}\n", style=f"bold {_verdict_style(rep.get('verdict'))}")
        det = rep.get("determinism") or {}
        if det:
            t.append(f"determinism: {det.get('class')} - {det.get('note', '')}\n", style=SEC)
        return t

    def action_close(self) -> None:
        self.dismiss(None)


class RunsScreen(Screen):
    """Every saved run of the active sorter, its recipe, and the reproduce check."""

    DEFAULT_CSS = """
    RunsScreen { background: $background; }
    RunsScreen #rtitle { height: 1; padding: 0 2; margin: 1 0 0 0; }
    RunsScreen #rintro { height: auto; padding: 0 2 1 2; color: $text-muted; }
    RunsScreen #rlist { height: 12; border: none; padding: 0 1; }
    RunsScreen #rlist:focus { border: none; }
    RunsScreen #rdetail { height: 1fr; padding: 1 2 0 2; }
    RunsScreen #rfoot { dock: bottom; height: 2; padding: 0 2; }
    """
    BINDINGS = [Binding("escape", "close", "Back", show=False),
                Binding("c", "make_current", "Make current", show=False),
                Binding("x", "export", "Export recipe", show=False),
                Binding("v", "view", "View last check", show=False)]

    def __init__(self, app_ref):
        super().__init__()
        self._a, self._c = app_ref, app_ref.c
        self._msg = None

    def compose(self) -> ComposeResult:
        yield Static(Text(f"RUNS AND REPRODUCIBILITY · {self._c.active_sorter}",
                          style=f"bold {self._a._accent}"), id="rtitle")
        yield Static("Every sort is kept in its own folder with its full recipe. Re-run one "
                     "from that recipe to check its values reproduce; nothing current changes.",
                     id="rintro")
        yield NavList(id="rlist")
        with VerticalScroll(id="rdetail"):
            yield Static("", id="rdetailbody")
        yield Static("", id="rfoot")

    def on_mount(self) -> None:
        self._fill()
        self.query_one("#rlist").focus()

    def _fill(self) -> None:
        ol = self.query_one("#rlist", OptionList)
        keep = self._run_id()
        ol.clear_options()
        self._runs = self._c.runs_overview()
        for r in self._runs:
            t = Text(no_wrap=True)
            t.append("● " if r["current"] else "  ", style=GREEN)
            t.append(f"{r['id']:<24}", style="bold" if r["current"] else "")
            t.append(f"{fmt_when(r['created']):<14}", style=MUTED)
            secs = r.get("seconds")
            span = ("legacy" if r["legacy"] else
                    (f"test {secs:.0f} s" if r["smoke"] and secs else
                     (f"full {secs:.0f} s" if secs else "?")))
            t.append(f"{span:<12}")
            t.append(f"{r['units'] if r['units'] is not None else '?':>3} units  ")
            n = r.get("noise_uV")
            t.append(f"{n:.2f} µV  " if isinstance(n, (int, float)) else "   -    ", style=SEC)
            if r["reproduced"]:
                t.append(r["reproduced"][:28], style=_verdict_style(r["reproduced"]))
            ol.add_option(Option(t, id=r["id"]))
        if ol.option_count:
            idx = next((i for i, r in enumerate(self._runs) if r["id"] == keep), None)
            if idx is None:
                idx = next((i for i, r in enumerate(self._runs) if r["current"]), 0)
            ol.highlighted = idx
        self._detail()

    def _run_id(self):
        try:
            ol = self.query_one("#rlist", OptionList)
        except Exception:  # noqa: BLE001
            return None
        if ol.highlighted is None or not ol.option_count:
            return None
        return ol.get_option_at_index(ol.highlighted).id

    def _detail(self) -> None:
        rid = self._run_id()
        t = Text()
        if rid and rid != "legacy":
            rec = self._c.run_recipe(rid)
            t.append("RECIPE  (what this run was made with)\n", style=f"bold {SEC}")
            avail = max(20, self.size.width - 20)
            for k, v in rec.get("rows") or []:
                t.append(f"  {k:<12}", style=MUTED)
                v = str(v)
                t.append((v if len(v) <= avail else v[:avail - 1] + "…") + "\n")
            reps = self._c.reproduce_reports(rid)
            t.append("\nREPRODUCE CHECKS\n", style=f"bold {SEC}")
            if reps:
                for r in reps[:3]:
                    t.append(f"  {fmt_when(r['when']):<14}", style=MUTED)
                    t.append(f"{r['verdict']}\n", style=_verdict_style(r["verdict"]))
            else:
                t.append("  none yet - ↵ re-runs this sort from its recipe and compares\n",
                         style=MUTED)
        elif rid == "legacy":
            t.append("A pre-store sort: it has no recipe to re-run.", style=MUTED)
        self.query_one("#rdetailbody", Static).update(t)
        foot = Text()
        if self._msg is not None:
            foot.append_text(self._msg)
        foot.append("\n")
        foot.append_text(key_line([("↑↓", "run"), ("↵", "reproduce it"), ("v", "last check"),
                                   ("c", "make current"), ("x", "export recipe"),
                                   ("esc", "back")], max(20, self.size.width - 4)))
        self.query_one("#rfoot", Static).update(foot)

    def on_option_list_option_highlighted(self, _event) -> None:
        self._detail()

    def _say(self, ok, msg) -> None:
        self._msg = Text(("✓ " if ok else "✗ ") + msg, style=GREEN if ok else RED)
        self._fill()
        self._a.refresh_all()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        rid = event.option.id
        if rid == "legacy":
            self._say(False, "a pre-store sort has no recipe to re-run")
            return
        self._a.reproduce(rid, on_done=lambda: self._fill())

    def action_view(self) -> None:
        rid = self._run_id()
        reps = self._c.reproduce_reports(rid) if rid else []
        if not reps:
            self._say(False, "no reproduce check for this run yet - press ↵")
            return
        self.app.push_screen(ReproduceReportScreen(reps[0]["data"], self._a._accent))

    def action_make_current(self) -> None:
        rid = self._run_id()
        if rid:
            self._say(*self._c.make_current(rid))

    def action_export(self) -> None:
        rid = self._run_id()
        if rid and rid != "legacy":
            self._say(*self._c.export_recipe(rid))

    def action_close(self) -> None:
        self.dismiss(None)


# --------------------------------------------------------------------------- #
# The panes
# --------------------------------------------------------------------------- #
class Pane(Vertical, can_focus=True):
    """One stage (or Home). ``keys()`` is its key line; ``paint()`` redraws it
    from the controller; ``focus_target()`` is where focus lands on arrival."""

    stage = 0

    def __init__(self, app_ref, **kw):
        super().__init__(**kw)
        self.a = app_ref

    @property
    def c(self):
        return self.a.c

    def keys(self) -> list:
        return []

    def paint(self) -> None:  # pragma: no cover - every pane overrides
        pass

    def focus_target(self):
        return self


class HomePane(Pane):
    DEFAULT_CSS = """
    HomePane #homerow { height: 1fr; }
    HomePane #homeleft { width: 1fr; height: 1fr; }
    HomePane #card { height: auto; border: round $accentcolor; padding: 0 2;
        border-title-color: $accentcolor; border-title-style: bold; margin: 0 0 1 0; }
    HomePane #stand { height: auto; }
    HomePane #recent { height: auto; margin: 1 0 0 0; }
    HomePane #pmap { width: 38; height: 1fr; padding: 0 0 0 2;
        border-left: vkey $panel-lighten-1; }
    HomePane #pmap.hidden { display: none; }
    """
    BINDINGS = [Binding("enter", "go", "Do it", show=False),
                Binding("s", "skip", "Not now", show=False)]

    def __init__(self, app_ref, **kw):
        super().__init__(app_ref, **kw)
        self._step_idx = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="homerow"):
            with VerticalScroll(id="homeleft"):
                yield Static("", id="card")
                yield Static("", id="stand")
                yield Static("", id="recent")
            yield Static("", id="pmap")

    def _steps(self):
        return getattr(self.c, "steps", None) or []

    def step(self):
        steps = self._steps()
        return steps[self._step_idx % len(steps)] if steps else None

    def keys(self):
        st = self.step()
        items = [("↵", st["label"] if st else "next step")]
        if len(self._steps()) > 1:
            items.append(("s", "not now"))
        return items

    def paint(self) -> None:
        width = self.a.size.width
        st = self.step()
        card = self.query_one("#card", Static)
        card.border_title = "NEXT STEP"
        t = Text()
        if st:
            t.append(st["title"] + "\n", style="bold")
            t.append(st["detail"] + "\n\n", style=SEC)
            t.append_text(chip("↵", style=f"bold {INK_ON_ACCENT} on {self.a._accent}"))
            t.append(" " + st["label"])
            n = len(self._steps())
            if n > 1:
                t.append("     ")
                t.append_text(chip("s"))
                t.append(f" not now ({self._step_idx % n + 1} of {n})", style=MUTED)
        card.update(t)
        self.query_one("#stand", Static).update(self._stand())
        self.query_one("#recent", Static).update(self._recent())
        pmap = self.query_one("#pmap", Static)
        pmap.set_class(width < 92, "hidden")
        pmap.update(self._pmap())

    def _stand(self) -> Text:
        c = self.c
        snap = getattr(c, "journey", None) or {}
        d = snap.get("data") or {}
        run = snap.get("run")
        t = Text()
        t.append("WHERE THINGS STAND\n", style=f"bold {SEC}")

        wide = self.a.size.width >= 92
        avail = max(20, self.a.size.width - (48 if wide else 8) - 12 - 3)

        def row(label, value, mark=None, style=""):
            t.append(f"{label:<12}", style=MUTED)
            value = str(value)
            t.append(value if len(value) <= avail else value[:avail - 1] + "…", style=style)
            if mark:
                g, col = mark
                t.append(f"  {g}", style=f"bold {col}")
            t.append("\n")

        if d.get("present"):
            row("Recording", f"{d.get('base')} · {d.get('broadband_detail') or 'loaded'}",
                ("✓", GREEN) if d.get("complete") else ("!", AMBER))
        else:
            row("Recording", "no recording found - press 1", ("!", AMBER), AMBER)
        pi = c.probe_info or {}
        row("Probe", pi.get("label", "?"),
            ("!", AMBER) if pi.get("match") == "mismatch" else ("✓", GREEN))
        if run:
            ws = run.get("wall_seconds")
            took = f" · took {int(ws) // 60}:{int(ws) % 60:02d}" if isinstance(ws, (int, float)) else ""
            kind = "test sort" if run.get("smoke") else "sort"
            row("Sort", f"{c.active_sorter} · {snap.get('n_units', 0)} units{took} · "
                        f"{kind} {run['id'][-6:]}")
            n = run.get("noise_uV")
            if isinstance(n, (int, float)):
                bad = n < 2.0
                row("Noise floor", f"{n:.2f} µV after band-pass + reference"
                    + ("  - looks ~4x too small: gain applied twice?" if bad else ""),
                    ("!", RED) if bad else None, RED if bad else "")
            units = snap.get("units") or []
            lab = snap.get("n_labelled", 0)
            total = snap.get("n_units", 0)
            if total:
                filled = round(16 * lab / total)
                t.append(f"{'Judged':<12}", style=MUTED)
                t.append("█" * filled, style=self.a._accent)
                t.append("░" * (16 - filled), style=FAINT)
                t.append(f" {lab} / {total}\n")
                counts = {}
                for u in units:
                    if u.get("label"):
                        counts[u["label"]] = counts.get(u["label"], 0) + 1
                if counts:
                    t.append(" " * 12)
                    t.append(" · ".join(f"{v} {k}" for k, v in counts.items()) + "\n", style=SEC)
            cur = snap.get("curation") or {}
            if cur.get("has_curated"):
                row("Curated", "stale: " + cur.get("stale_reason", "") if cur.get("stale")
                    else f"{(cur.get('counts') or {}).get('total', 0)} decisions applied",
                    ("!", AMBER) if cur.get("stale") else ("✓", GREEN))
        else:
            row("Sort", f"{c.active_sorter} · not sorted yet", None, MUTED)
        n_changed = sum(1 for r in (c.settings_rows() if hasattr(c, "settings_rows") else [])
                        if r["kind"] != "link" and not r["is_default"])
        if n_changed:
            row("Settings", f"{n_changed} changed from default · press , to see them", None, SEC)
        return t

    def _recent(self) -> Text:
        items = getattr(self.c, "recent", None) or []
        t = Text()
        if not items:
            return t
        t.append("RECENT\n", style=f"bold {SEC}")
        avail = max(20, self.a.size.width - (48 if self.a.size.width >= 92 else 8) - 14 - 2)
        for it in items[:4]:
            t.append(f"{fmt_when(it['when']):<14}", style=MUTED)
            text = it["text"]
            t.append((text if len(text) <= avail else text[:avail - 1] + "…") + "\n", style=SEC)
        return t

    def _pmap(self) -> Text:
        pm = getattr(self.c, "probe_map", None) or {}
        contacts = pm.get("contacts") or []
        units = pm.get("units") or {}
        t = Text(no_wrap=True)
        t.append("UNITS ON THE PROBE\n", style=f"bold {SEC}")
        t.append("tip at the bottom\n\n", style=MUTED)
        if not contacts:
            t.append("sort the recording to\nsee units at their contacts", style=MUTED)
            return t
        t.append("      ╭─╮\n", style=FAINT)
        for ch in contacts:
            us = units.get(ch, [])
            adv = any(u.get("advised") for u in us)
            good = any(u.get("label") == "good" for u in us)
            col = AMBER if adv else GREEN if good else (SEC if us else FAINT)
            t.append(f"{ch:>4}  ", style=MUTED)
            t.append("│", style=FAINT)
            t.append("▪", style=col)
            t.append("│", style=FAINT)
            if us:
                t.append(" ─ ", style=FAINT)
                for u in us[:4]:
                    g = _LABEL_GLYPH.get(u.get("label"), "·")
                    ucol = AMBER if u.get("advised") else _LABEL_STYLE.get(u.get("label"), SEC)
                    t.append(f"{g}{u['unit']} ", style=f"{'bold ' if u.get('label') == 'good' else ''}{ucol}")
                if len(us) > 4:
                    t.append(f"+{len(us) - 4}", style=MUTED)
            t.append("\n")
        t.append("      ╲ ╱\n\n", style=FAINT)
        t.append("● ", style=GREEN)
        t.append("good  ", style=MUTED)
        t.append("○ ", style=SEC)
        t.append("unsure  ", style=MUTED)
        t.append("×", style=MUTED)
        t.append(" noise\n", style=MUTED)
        t.append("·", style=SEC)
        t.append(" not judged yet\n", style=MUTED)
        t.append("amber", style=AMBER)
        t.append(" = likely two cells", style=MUTED)
        return t

    def action_go(self) -> None:
        st = self.step()
        if st:
            self.a.do(st["action"])

    def action_skip(self) -> None:
        if len(self._steps()) > 1:
            self._step_idx += 1
            self.a.refresh_all()


class ListPane(Pane):
    """A stage whose rows are its actions: a head block, then a list of rows each
    carrying its own key; ↵ runs the highlighted row, the key runs it directly."""

    ROWS: tuple = ()          # (key, action, title, hint, needs_data)

    DEFAULT_CSS = """
    ListPane #head { height: auto; margin: 0 0 1 0; }
    ListPane #rows { height: auto; max-height: 12; border: none; padding: 0; }
    ListPane #rows:focus { border: none; }
    ListPane #rows > .option-list--option-highlighted { background: $accentcolor 20%; }
    ListPane #tail { height: auto; margin: 1 0 0 0; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("", id="head")
            yield NavList(id="rows")
            yield Static("", id="tail")

    def focus_target(self):
        return self.query_one("#rows")

    def head(self) -> Text:
        return Text()

    def tail(self) -> Text:
        return Text()

    def paint(self) -> None:
        self.query_one("#head", Static).update(self.head())
        ol = self.query_one("#rows", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        present = bool((self.c.data_report or {}).get("present"))
        width = self.a.size.width - 6
        for key, action, title, hint, needs in self.ROWS:
            off = needs and not present
            ol.add_option(Option(_row_text(key, title, hint, width, disabled=off,
                                           note="needs the recording" if off else ""),
                                 id=action, disabled=off))
        if ol.option_count:
            ol.highlighted = keep if keep is not None and keep < ol.option_count else \
                next((i for i in range(ol.option_count)
                      if not ol.get_option_at_index(i).disabled), None)
        self.query_one("#tail", Static).update(self.tail())

    def keys(self):
        return [(k, t.split(" ")[0].lower() if len(t) > 16 else t.lower())
                for k, _a, t, _h, _n in self.ROWS][:6]

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.a.do(event.option.id)

    def on_key(self, event) -> None:
        for key, action, *_rest in self.ROWS:
            if event.key == key:
                event.stop()
                self.a.do(action)
                return


class DataPane(ListPane):
    stage = 1
    ROWS = (("f", "folder", "Choose the data folder", "point Spike at another recording", False),
            ("o", "open_folder", "Open the data folder", "in Finder / Explorer", False),
            ("e", "explore", "Explore the recording", "figures: LFP, events, rates", True),
            ("t", "traces", "Watch the raw traces", "scroll the signal in a window", True),
            ("v", "verify", "Check the install", "every library and loader", False))

    def keys(self):
        return [("f", "folder"), ("o", "open"), ("e", "explore"), ("t", "traces"),
                ("v", "check install")]

    def head(self) -> Text:
        dr = self.c.data_report or {}
        t = Text()
        t.append("THE RECORDING\n", style=f"bold {SEC}")
        t.append(f"{'folder':<10}", style=MUTED)
        t.append(f"{dr.get('data_dir', '?')}\n")
        if dr.get("present"):
            t.append(f"{'name':<10}", style=MUTED)
            t.append(f"{dr.get('base')}\n", style="bold")
            snap = getattr(self.c, "journey", None) or {}
            det = (snap.get("data") or {}).get("broadband_detail")
            if det:
                t.append(f"{'signal':<10}", style=MUTED)
                t.append(det + "\n")
            t.append("\n")
        else:
            t.append("\nNo recording here yet.\n", style=f"bold {AMBER}")
            t.append("Spike reads one Blackrock set: one name, three extensions.\n"
                     "Put the three files in this folder, or press f to point Spike at "
                     "theirs.\n\n", style=SEC)
        for f in dr.get("files") or []:
            ok = f.get("present")
            t.append("  ✓ " if ok else "  ✗ ", style=f"bold {GREEN if ok else AMBER}")
            name = (dr.get("base") or "<name>") + f["ext"]
            t.append(f"{name:<34}", style="" if ok else AMBER)
            t.append(f["label"] + "\n", style=MUTED)
        if dr.get("error") and not dr.get("present"):
            t.append("\n" + str(dr["error"])[:300] + "\n", style=MUTED)
        return t


def _shank(positions, height: int) -> Text:
    """A probe's contacts drawn to scale-ish in characters, contact 1 at the tip."""
    t = Text(no_wrap=True)
    if not positions:
        t.append("(drawing unavailable)", style=MUTED)
        return t
    xs = sorted({round(p[0], 1) for p in positions})
    ys = [p[1] for p in positions]
    lo, hi = min(ys), max(ys)
    rows = max(2, min(height, len({round(y, 1) for y in ys})))
    grid = [[" "] * max(1, len(xs)) for _ in range(rows)]
    labels = [""] * rows
    for i, (x, y) in enumerate(positions):
        r = 0 if hi == lo else int(round((hi - y) / (hi - lo) * (rows - 1)))
        cidx = xs.index(round(x, 1))
        grid[r][cidx] = "▪"
        if not labels[r]:
            labels[r] = str(i + 1)
    w = len(xs)
    t.append("       ╭" + "─" * w + "╮\n", style=FAINT)
    for r in range(rows):
        t.append(f"{labels[r]:>5}  ", style=MUTED)
        t.append("│", style=FAINT)
        t.append("".join(grid[r]), style=CHIP_FG)
        t.append("│\n", style=FAINT)
    t.append("       ╲" + " " * w + "╱\n", style=FAINT)
    return t


class ProbePane(Pane):
    """Every value of the highlighted probe, its drawing, and the library."""

    stage = 2
    DEFAULT_CSS = """
    ProbePane #prow { height: 1fr; }
    ProbePane #pleft { width: 1fr; height: 1fr; }
    ProbePane #pvals { height: auto; margin: 0 0 1 0; }
    ProbePane #plib { height: 1fr; min-height: 4; border: none; padding: 0; }
    ProbePane #plib:focus { border: none; }
    ProbePane #pdraw { width: 30; height: 1fr; padding: 0 0 0 2; border-left: vkey $panel-lighten-1; }
    ProbePane #pdraw.hidden { display: none; }
    """
    BINDINGS = [Binding("e", "edit", "Edit", show=False),
                Binding("n", "new", "New", show=False),
                Binding("d", "duplicate", "Duplicate", show=False),
                Binding("i", "import_file", "Import", show=False),
                Binding("x", "delete", "Delete", show=False)]

    def compose(self) -> ComposeResult:
        with Horizontal(id="prow"):
            with Vertical(id="pleft"):
                yield Static("", id="pvals")
                yield Static(_section("PROBE LIBRARY  (● = the active probe)"), id="plibhead")
                yield NavList(id="plib")
            with VerticalScroll(id="pdraw"):
                yield Static("", id="pdrawbody")

    def focus_target(self):
        return self.query_one("#plib")

    def keys(self):
        return [("↑↓", "probe"), ("↵", "use it"), ("e", "edit"), ("n", "new"),
                ("d", "duplicate"), ("i", "import file"), ("x", "delete")]

    def _probe_name(self):
        ol = self.query_one("#plib", OptionList)
        if ol.highlighted is None or not ol.option_count:
            return self.c.active_probe
        return ol.get_option_at_index(ol.highlighted).id

    def paint(self) -> None:
        ol = self.query_one("#plib", OptionList)
        keep = self._probe_name() if ol.option_count else self.c.active_probe
        ol.clear_options()
        rows = self.c.probe_catalog()
        width = self.a.size.width - 40
        for r in rows:
            t = Text(no_wrap=True)
            t.append("● " if r["active"] else "  ", style=GREEN)
            t.append(f"{r['label'][:30]:<32}", style="bold" if r["active"] else "")
            t.append(r["summary"][:max(0, width - 34)], style=MUTED)
            if r.get("match") == "mismatch":
                t.append("  ✗ wrong size", style=AMBER)
            t.truncate(max(20, width))
            ol.add_option(Option(t, id=r["name"]))
        idx = next((i for i, r in enumerate(rows) if r["name"] == keep), 0)
        if ol.option_count:
            ol.highlighted = idx
        self._paint_detail()
        self.query_one("#pdraw").set_class(self.a.size.width < 90, "hidden")

    def _paint_detail(self) -> None:
        det = self.c.probe_detail(self._probe_name()) if hasattr(self.c, "probe_detail") else {}
        t = Text()
        t.append("ACTIVE PROBE\n" if det.get("active") else "SELECTED PROBE (not active)\n",
                 style=f"bold {SEC if det.get('active') else AMBER}")
        if not det:
            self.query_one("#pvals", Static).update(t)
            return
        feats = det.get("features") or {}

        avail = max(20, self.a.size.width - (34 if self.a.size.width >= 90 else 4) - 22)

        def row(label, value, style=""):
            t.append(f"  {label:<16}", style=MUTED)
            value = str(value)
            t.append((value if len(value) <= avail else value[:avail - 1] + "…") + "\n",
                     style=style)

        row("name", det["label"], "bold")
        row("id", det["name"])
        row("kind", det["kind"])
        params = det.get("params") or {}
        if params and det["kind"] not in ("imported", "file"):
            t.append("  editable (e)\n", style=f"bold {SEC}")
        for k, v in params.items():
            if isinstance(v, (list, dict)):
                v = f"{len(v)} values"
            row(k.replace("_", " "), v, "bold" if det["kind"] not in ("imported", "file") else "")
        t.append("  derived\n", style=f"bold {SEC}")
        row("contacts", feats.get("n", "?"))
        row("layout", feats.get("layout", "?"))
        row("closest pitch", f"{feats.get('min_pitch_um', '?')} µm")
        row("density", feats.get("density_class", "?"))
        fits = det.get("match")
        row("this recording", det.get("match_detail", ""),
            AMBER if fits == "mismatch" else GREEN)
        row("saved in", det.get("saved_in", ""), SEC)
        if det.get("note"):
            row("note", det["note"][:60], SEC)
        self.query_one("#pvals", Static).update(t)
        draw = Text()
        draw.append("GEOMETRY\n", style=f"bold {SEC}")
        draw.append("contact 1 at the tip\n\n", style=MUTED)
        draw.append_text(_shank(det.get("positions"), 20))
        self.query_one("#pdrawbody", Static).update(draw)

    def on_option_list_option_highlighted(self, _event) -> None:
        self._paint_detail()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        name = event.option.id
        if self.c.set_active_probe(name):
            self.a.say(f"✓ {name} is now the active probe - every sort from Spike uses it",
                       GREEN)
        self.a.after_change()

    def _profile(self, name):
        return next((r for r in self.c.probe_catalog() if r["name"] == name), None)

    def action_edit(self) -> None:
        prof = self._profile(self._probe_name())
        if prof is None:
            return
        if prof.get("kind") in ("imported", "file"):
            self.a.say("an imported probe's geometry comes from its file: import the file "
                       "again to change it, or d to duplicate it", AMBER)
            return
        seed = {"name": prof["name"], "label": prof["label"], "kind": prof["kind"],
                "params": dict(prof.get("params") or {}), "builtin": False,
                "note": prof.get("note", "")}
        if prof.get("builtin"):          # built-ins are read-only: edit a copy
            seed["name"], seed["label"] = f"{prof['name']}-copy", f"{prof['label']} (copy)"
            self.a.say("built-in probes are read-only - you are editing a copy", SEC)
        self.a.push_screen(ProbeEditorScreen(seed, self.a._accent), self._after_edit)

    def action_new(self) -> None:
        opts = [("linear", "Linear (one column)", "most shanks"),
                ("grid", "2-D grid", "columns x rows"),
                ("tetrode", "Tetrodes", "groups of 4"),
                ("independent", "Independent", "no two contacts neighbours")]
        self.a.push_screen(ChoiceModal("New probe - what kind?", opts), self._after_kind)

    def _after_kind(self, kind) -> None:
        if not kind:
            return
        blank = {"name": f"my-{kind}", "label": f"My {kind} probe", "kind": kind,
                 "params": {}, "builtin": False, "note": ""}
        self.a.push_screen(ProbeEditorScreen(blank, self.a._accent), self._after_edit)

    def _after_edit(self, profile) -> None:
        if not profile:
            return
        ok, msg = self.c.save_probe(profile)
        self.a.say(("✓ " if ok else "✗ ") + msg, GREEN if ok else RED)
        self.a.after_change()

    def action_duplicate(self) -> None:
        name = self._probe_name()

        def submit(raw):
            new = raw.strip()
            if not new:
                return False, "type a name for the copy"
            try:
                dup = self.c.duplicate_probe(name, new)
            except Exception as e:  # noqa: BLE001
                return False, str(e)
            return True, f"duplicated as {dup.get('name', new)} - press e to edit it"

        self.a.push_screen(InputModal(f"Duplicate {name}", f"{name}-copy",
                                      "a short id for the copy (letters, digits, dashes)",
                                      submit),
                           lambda msg: msg and (self.a.say("✓ " + msg, GREEN),
                                                self.a.after_change()))

    def action_import_file(self) -> None:
        self.a.push_screen(
            InputModal("Import a probe file", "",
                       "the path of a probeinterface .json or .prb file; its geometry "
                       "is copied into the library (probes.json)",
                       lambda raw: self.c.import_probe(raw)),
            lambda msg: msg and (self.a.say("✓ " + msg, GREEN), self.a.after_change()))

    def action_delete(self) -> None:
        prof = self._profile(self._probe_name())
        if prof is None:
            return
        if prof.get("builtin"):
            self.a.say("built-in probes can't be deleted", AMBER)
            return
        name = prof["name"]
        self.a.push_screen(
            ConfirmModal(f"Delete probe {name}?",
                         "It leaves probes.json. Sorts already made with it keep their "
                         "recorded geometry."),
            lambda yes: yes and (self.a.say(*(lambda r: (("✓ " if r[0] else "✗ ") + r[1],
                                                          GREEN if r[0] else RED))(
                self.c.delete_probe(name))), self.a.after_change()))


class SortPane(Pane):
    stage = 3
    DEFAULT_CSS = """
    SortPane #srow { height: 1fr; }
    SortPane #sleft { width: 1fr; height: 1fr; }
    SortPane #slisthead { height: 1; }
    SortPane #sorters { height: 1fr; min-height: 4; border: none; padding: 0; }
    SortPane #sorters:focus { border: none; }
    SortPane #snote { height: auto; }
    SortPane #sright { width: 46; height: 1fr; padding: 0 0 0 2; border-left: vkey $panel-lighten-1; }
    """
    BINDINGS = [Binding("f", "full", "Full sort", show=False),
                Binding("t", "quick", "Quick test", show=False),
                Binding("e", "params", "Parameters", show=False),
                Binding("s", "settings", "Settings", show=False),
                Binding("m", "manage", "Sorters & Docker", show=False),
                Binding("r", "runs", "Runs", show=False)]

    def compose(self) -> ComposeResult:
        with Horizontal(id="srow"):
            with Vertical(id="sleft"):
                yield Static(_section("CHOOSE A SORTER  (ranked for this probe)"), id="slisthead")
                yield NavList(id="sorters")
                yield Static("", id="snote")
            with VerticalScroll(id="sright"):
                yield Static("", id="snext")

    def focus_target(self):
        return self.query_one("#sorters")

    def keys(self):
        return [("↵", "use sorter"), ("f", "full sort"), ("t", f"{self.c.quick_seconds} s test"),
                ("e", "parameters"), ("s", "settings"), ("m", "sorters & Docker"),
                ("r", "runs")]

    def paint(self) -> None:
        ol = self.query_one("#sorters", OptionList)
        keep = (ol.get_option_at_index(ol.highlighted).id
                if ol.highlighted is not None and ol.option_count else self.c.active_sorter)
        ol.clear_options()
        infos = [i for i in self.c.infos if i.get("group") in ("ready", "docker")]
        width = self.a.size.width - 54
        for i in infos:
            t = Text(no_wrap=True)
            t.append("● " if i.get("active") else "  ", style=GREEN)
            t.append(f"{i['name'][:15]:<16}", style="bold" if i.get("active") else "")
            if i.get("recommended"):
                tag, style = "recommended", self.a._accent
            elif i.get("group") == "docker":
                tag, style = ("Docker" if i.get("img_present") else "get image"), MUTED
            else:
                tag, style = "", ""
            t.append(f"{tag:<12}", style=style)
            if i.get("present"):
                t.append(f"{i['units']}u · {i['duration']:.0f} s", style=SEC)
            else:
                t.append("not run", style=MUTED)
            t.truncate(max(20, width))
            ol.add_option(Option(t, id=i["name"]))
        idx = next((n for n, i in enumerate(infos) if i["name"] == keep), 0)
        if ol.option_count:
            ol.highlighted = idx
        note = Text("Kilosort4 and other GPU sorters appear on a computer with an NVIDIA GPU.",
                    style=MUTED)
        self.query_one("#snote", Static).update(note)
        self.query_one("#snext", Static).update(self._next())
        self.query_one("#sright").styles.width = 46 if self.a.size.width >= 100 else 36

    def _next(self) -> Text:
        c = self.c
        t = Text()
        t.append("THE NEXT SORT WILL USE\n", style=f"bold {SEC}")
        t.append(f"  {'sorter':<14}", style=MUTED)
        t.append(f"{c.active_sorter}\n", style=f"bold {self.a._accent}")
        for label, value in (c.sort_preview() if hasattr(c, "sort_preview") else []):
            t.append(f"  {label:<14}", style=MUTED)
            value = str(value)
            t.append((value if len(value) <= 27 else value[:26] + "…") + "\n")
        t.append("\n  e ", style=CHIP_FG)
        t.append("parameters  ", style=MUTED)
        t.append("s ", style=CHIP_FG)
        t.append("every other setting\n\n", style=MUTED)
        t.append("HOW MUCH\n", style=f"bold {SEC}")
        t.append("  f ", style=CHIP_FG)
        exp = {}
        try:
            exp = c.sort_expectations() or {}
        except Exception:  # noqa: BLE001
            exp = {}
        last = ""
        if exp.get("wall_seconds") and exp.get("span") == "full":
            last = f" · last time {int(exp['wall_seconds']) // 60}:{int(exp['wall_seconds']) % 60:02d}"
        t.append(f"the full recording{last}\n")
        t.append("  t ", style=CHIP_FG)
        t.append(f"first {c.quick_seconds} s · a test, never current\n\n")
        snap = getattr(c, "journey", None) or {}
        if snap.get("run"):
            t.append("A sort makes a NEW run. The current run (", style=SEC)
            t.append(snap["run"]["id"][-6:], style="bold")
            t.append(") stays current until the new one finishes; nothing is overwritten.\n",
                     style=SEC)
            t.append("  r ", style=CHIP_FG)
            t.append("every run, its recipe, reproduce\n", style=MUTED)
        return t

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.a.select_sorter(event.option.id)

    def action_full(self) -> None:
        self.a.do("sort")

    def action_quick(self) -> None:
        self.a.do("sort_quick")

    def action_params(self) -> None:
        self.a.do("params")

    def action_settings(self) -> None:
        self.a.open_settings("freq_min")

    def action_manage(self) -> None:
        self.a.do("manage")

    def action_runs(self) -> None:
        self.a.do("runs")


class JudgePane(Pane):
    """The queue (flagged first) and the unit card with its evidence."""

    stage = 4
    DEFAULT_CSS = """
    JudgePane #jrow { height: 1fr; }
    JudgePane #jleft { width: 26; height: 1fr; }
    JudgePane #queue { height: 1fr; border: none; padding: 0; }
    JudgePane #queue:focus { border: none; }
    JudgePane #jcard { width: 1fr; height: 1fr; padding: 0 0 0 2; border-left: vkey $panel-lighten-1; }
    """
    BINDINGS = [*[Binding(k, f"label('{v}')", f"Label {v}", show=False) for k, v in _TRIAGE_KEYS],
                Binding("v", "plots", "Full plots", show=False),
                Binding("i", "inspect", "Inspect", show=False),
                Binding("a", "apply", "Apply", show=False)]

    def __init__(self, app_ref, **kw):
        super().__init__(app_ref, **kw)
        self._state = {}
        self._ev = {}
        self._ev_run = None          # the run the cached evidence was read from
        self._ev_loading = False
        self._ev_error = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="jrow"):
            with Vertical(id="jleft"):
                yield Static(_section("QUEUE  flagged first"), id="qhead")
                yield NavList(id="queue")
            with VerticalScroll(id="jcard"):
                yield Static("", id="card")

    def focus_target(self):
        return self.query_one("#queue")

    def keys(self):
        return [("↑↓", "unit"), ("v", "full plots"), ("g", "good"), ("m", "multi-unit"),
                ("n", "noise"), ("u", "unsure"), ("i", "inspect in GUI"), ("a", "apply")]

    def _ordered(self, units):
        flagged = [u for u in units if u.get("split_advice")]
        rest = [u for u in units if not u.get("split_advice")]
        return flagged, rest

    def paint(self) -> None:
        run = ((getattr(self.c, "journey", None) or {}).get("run") or {}).get("id")
        if run != self._ev_run:            # a new sort: never draw the old run's evidence
            self._ev, self._ev_error, self._ev_run = {}, None, run
        try:
            self._state = self.c.triage_state() or {}
        except Exception as e:  # noqa: BLE001 - an unreadable sort is a message, not a crash
            self._state = {"units": [], "empty": f"couldn't read the sort: {e}"}
        ol = self.query_one("#queue", OptionList)
        keep = self._unit_id()
        ol.clear_options()
        flagged, rest = self._ordered(self._state.get("units") or [])
        for title, group in (("flagged", flagged), ("the rest", rest)):
            if not group:
                continue
            if flagged and rest:
                ol.add_option(Option(Text(("\n" if title == "the rest" else "") + title,
                                          style=MUTED), disabled=True))
            for u in group:
                lab = u.get("label")
                t = Text(no_wrap=True)
                t.append(_LABEL_GLYPH.get(lab, "·") + " ",
                         style=f"bold {_LABEL_STYLE.get(lab, MUTED)}")
                t.append(f"u{u['unit']:<4}", style="bold" if not lab else "")
                t.append(f"ch{u.get('peak_channel', '?'):<4}", style=MUTED)
                t.append(lab or "", style=_LABEL_STYLE.get(lab, MUTED))
                ol.add_option(Option(t, id=str(u["unit"])))
        if ol.option_count:
            want = next((i for i in range(ol.option_count)
                         if keep is not None and ol.get_option_at_index(i).id == keep), None)
            if want is None:
                want = next((i for i in range(ol.option_count)
                             if not ol.get_option_at_index(i).disabled), None)
            ol.highlighted = want
        self._paint_card()
        if not self._ev and not self._ev_loading and self._state.get("units"):
            self._load_evidence()

    def _load_evidence(self) -> None:
        if not hasattr(self.c, "unit_evidence"):
            return
        self._ev_loading = True
        run = self._ev_run
        units = [str(u["unit"]) for u in self._state.get("units") or []]

        def work():
            out, err = {}, None
            try:
                for uid in units:
                    ev = self.c.unit_evidence(uid)
                    if ev:
                        out[uid] = ev
            except Exception as e:  # noqa: BLE001
                err = str(e)
            self.a.call_from_thread(self._evidence_ready, out, err, run)

        self.a.run_worker(work, thread=True, exclusive=False)

    def _evidence_ready(self, ev, err, run=None) -> None:
        self._ev_loading = False
        if run != self._ev_run:          # the sort changed while this loaded: drop it
            self.paint()
            return
        self._ev, self._ev_error = ev, err
        self._paint_card()

    def _unit_id(self):
        ol = self.query_one("#queue", OptionList)
        if ol.highlighted is None or not ol.option_count:
            return None
        return ol.get_option_at_index(ol.highlighted).id

    def _unit(self):
        uid = self._unit_id()
        return next((u for u in self._state.get("units") or [] if str(u["unit"]) == uid), None)

    def on_option_list_option_highlighted(self, _event) -> None:
        self._paint_card()

    def _paint_card(self) -> None:
        st = self._state
        t = Text()
        if st.get("empty"):
            t.append(st["empty"] + "\n", style=AMBER)
            t.append("\nSort the recording on 3 Sort, then come back.", style=SEC)
            self.query_one("#card", Static).update(t)
            return
        u = self._unit()
        if st.get("blocked"):
            t.append("✗ " + st["blocked"] + "\n", style=AMBER)
        if u is None:
            self.query_one("#card", Static).update(t)
            return
        m = u.get("metrics") or {}
        t.append(f"UNIT {u['unit']}", style=f"bold {self.a._accent}")
        n = u.get("n_spikes")
        vpp = u.get("v_pp_uV")
        snr = m.get("snr")
        bits = [f"contact {u.get('peak_channel')}",
                f"{n:,} spikes" if isinstance(n, int) else "spikes -",
                f"{vpp:.1f} µV" if isinstance(vpp, (int, float)) else None,
                f"SNR {float(snr):.2f}" if _num(snr) else None]
        t.append("   " + " · ".join(b for b in bits if b) + "\n", style=SEC)
        lab = u.get("label")
        t.append("your call: ", style=MUTED)
        t.append(f"{lab}\n" if lab else "not judged yet\n",
                 style=f"bold {_LABEL_STYLE.get(lab, MUTED)}")
        t.append(f"quality rule: {u.get('verdict_word', '')}\n", style=SEC)
        if u.get("split_advice"):
            t.append("! " + u["split_advice"] + "\n", style=f"bold {AMBER}")
            t.append("  label it, then split it in Phy (6 Share → Phy export)\n", style=SEC)
        width = max(30, self.a.size.width - 40)
        ev = self._ev.get(str(u["unit"]))
        t.append("\n")
        if ev:
            t.append("AT A GLANCE", style=f"bold {SEC}")
            t.append("  ", style=MUTED)
            t.append_text(chip("v"))
            t.append(" full plots, to judge by\n", style=MUTED)
            self._evidence(t, ev, u, width)
        elif self._ev_loading:
            t.append("loading waveforms and spike intervals…\n", style=MUTED)
        elif self._ev_error:
            t.append(f"evidence unavailable: {self._ev_error[:100]}\n", style=MUTED)
        if m:
            t.append("\nMETRICS\n", style=f"bold {SEC}")
            for k in ("firing_rate", "snr", "isi_violations_ratio", "presence_ratio",
                      "amplitude_cutoff", "amplitude_median"):
                if k in m:
                    v = m[k]
                    t.append(f"  {k:<22}", style=MUTED)
                    t.append(f"{float(v):.3g}\n" if _num(v) else "-\n")
        self.query_one("#card", Static).update(t)

    def _evidence(self, t: Text, ev: dict, u: dict, width: int) -> None:
        chans = ev.get("channels") or []
        waves = ev.get("waveforms") or {}
        if waves:
            t.append(f"SHAPE ON CONTACTS {' · '.join(map(str, chans))}", style=f"bold {SEC}")
            t.append(f"   {ev.get('wave_ms', 0):.1f} ms, µV, same scale\n", style=MUTED)
            vals = [v for ch in chans for v in (waves.get(str(ch)) or [])]
            lo, hi = (min(vals), max(vals)) if vals else (0, 1)
            each = max(12, min(22, (width - 4) // max(1, len(chans)) - 2))
            plots = [line_plot(waves.get(str(ch)) or [], each, 5,
                               self.a._accent if str(ch) == str(ev.get("peak_channel")) else "#5d64ca",
                               lo, hi) for ch in chans]
            for r in range(5):
                for p in plots:
                    t.append_text(p[r])
                    t.append("  ")
                t.append("\n")
            for ch in chans:
                lab = f"ch {ch}"
                t.append(f"{lab:^{each}}  ", style="bold" if str(ch) == str(ev.get("peak_channel")) else MUTED)
            t.append("\n\n")
        isi = ev.get("isi") or {}
        counts = isi.get("counts") or []
        if counts:
            bin_ms = isi.get("bin_ms") or 0.5
            hot = int(round((isi.get("refractory_ms") or 0) / bin_ms))
            t.append("TIME BETWEEN SPIKES", style=f"bold {SEC}")
            t.append(f"   0-{isi.get('max_ms', 25):g} ms · amber = inside the "
                     f"{isi.get('refractory_ms', 0):g} ms refractory window\n", style=MUTED)
            for row in bar_rows(counts, 4, "#5d64ca", hot=hot):
                t.append_text(row)
                t.append("\n")
            nr = isi.get("n_refractory")
            t.append(f"{nr if nr is not None else '-'}", style=f"bold {AMBER if nr else GREEN}")
            t.append(" spikes inside it", style=SEC)
            if _num(isi.get("ratio")):
                t.append(f" · ISI ratio {float(isi['ratio']):.2f}", style=SEC)
            t.append("\n\n")
        amp = ev.get("amplitude")
        if amp and amp.get("median_uV"):
            med = [abs(v) for v in amp["median_uV"] if v is not None]
            t.append("AMPLITUDE OVER THE RECORDING  ", style=f"bold {SEC}")
            t.append(spark(med), style="#5d64ca")
            if med:
                t.append(f"  {min(med):.0f}-{max(med):.0f} µV\n", style=MUTED)

    def action_label(self, label: str) -> None:
        uid = self._unit_id()
        if uid is None:
            return
        ok, msg = self.c.label_unit(uid, label)
        self.a.say(("✓ " if ok else "✗ ") + msg, GREEN if ok else AMBER)
        if ok:
            if hasattr(self.c, "refresh_journey"):
                self.c.refresh_journey()
            self.paint()
            self._advance()
            self.a.refresh_chrome()

    def _advance(self) -> None:
        """Move to the next unit not yet judged, if any."""
        ol = self.query_one("#queue", OptionList)
        units = {str(u["unit"]): u for u in self._state.get("units") or []}
        start = (ol.highlighted or 0) + 1
        for i in list(range(start, ol.option_count)) + list(range(0, start)):
            opt = ol.get_option_at_index(i)
            if not opt.disabled and not (units.get(opt.id) or {}).get("label"):
                ol.highlighted = i
                return

    def action_plots(self) -> None:
        self.a.open_units(self._unit_id())

    def action_inspect(self) -> None:
        self.a.do("gui")

    def action_apply(self) -> None:
        self.a.go(5)


def _num(v) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


class ApplyPane(Pane):
    stage = 5
    DEFAULT_CSS = """
    ApplyPane #abody { height: 1fr; }
    """
    BINDINGS = [Binding("enter", "apply", "Apply", show=False),
                Binding("i", "import_phy", "Import from Phy", show=False),
                Binding("y", "phy", "Export to Phy", show=False)]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="abody"):
            yield Static("", id="apply")

    def keys(self):
        return [("↵", "apply"), ("y", "export to Phy"), ("i", "import from Phy")]

    def paint(self) -> None:
        pv = self.c.apply_preview() if hasattr(self.c, "apply_preview") else {}
        t = Text()
        total = (pv.get("counts") or {}).get("total", 0)
        t.append(f"APPLY {total} DECISION{'S' if total != 1 else ''}", style=f"bold {self.a._accent}")
        if pv.get("run"):
            t.append(f"   to run {pv['run']}\n", style=SEC)
        else:
            t.append("\n")
        t.append("The raw sort is never changed. Applying builds a curated copy beside it and "
                 "re-scores every metric on it.\n\n", style=MUTED)
        if not total:
            t.append("No decisions yet - label units on 4 Judge (or import them from Phy "
                     "with i).\n", style=AMBER)
            self.query_one("#apply", Static).update(t)
            return
        labels = pv.get("labels") or {}
        counts = pv.get("counts") or {}
        t.append("BEFORE", style=f"bold {SEC}")
        t.append(" " * 26)
        t.append("AFTER\n", style=f"bold {self.a._accent}")
        t.append(f"{pv.get('n_units', '?')} units, raw sorter output".ljust(32))
        t.append(f"{pv.get('n_units', '?')} units · " + " · ".join(
            f"{v} {k}" for k, v in labels.items()) + "\n")
        t.append("no labels".ljust(32), style=MUTED)
        t.append(f"{counts.get('merges', 0)} merges · {counts.get('splits', 0)} splits · "
                 "metrics re-scored\n\n", style=MUTED)
        if pv.get("has_curated") and not pv.get("stale"):
            t.append("✓ Already applied - the curated result is current.\n", style=GREEN)
        elif pv.get("stale"):
            t.append("! " + str(pv.get("stale_reason")) + " - apply again to bring it up to "
                     "date.\n", style=AMBER)
        else:
            t.append("Not applied yet.\n", style=AMBER)
        t.append("\nDECISIONS  newest last\n", style=f"bold {SEC}")
        for d in (pv.get("decisions") or [])[-14:]:
            t.append(f"  {str(d['at'])[11:19]:<10}", style=MUTED)
            units = ",".join(map(str, d["units"]))
            t.append(f"{d['type']:<7}u{units:<8}")
            lab = d.get("label") or ""
            t.append(f"{lab:<9}", style=_LABEL_STYLE.get(lab, ""))
            t.append(f"{d.get('method', '')}\n", style=MUTED)
        self.query_one("#apply", Static).update(t)

    def action_apply(self) -> None:
        self.a.do("apply")

    def action_import_phy(self) -> None:
        self.a.do("import_phy")

    def action_phy(self) -> None:
        self.a.do("phy")


class SharePane(Pane):
    stage = 6
    DEFAULT_CSS = """
    SharePane #shrow { height: 1fr; }
    SharePane #outs { width: 1fr; height: 1fr; border: none; padding: 0; }
    SharePane #outs:focus { border: none; }
    SharePane #sdetail { width: 40; height: 1fr; padding: 0 0 0 2; border-left: vkey $panel-lighten-1; }
    SharePane #sdetail.hidden { display: none; }
    """
    BINDINGS = [Binding("r", "rebuild", "Rebuild", show=False),
                Binding("f", "folder", "Show in folder", show=False),
                Binding("x", "recipe", "Export recipe", show=False)]
    _PRIMARY = {"units": "units", "report": "open:report", "compare": "open:compare", "sweep": "open:sweep",
                "explore": "open:explore", "phy": "phy", "gui": "gui", "values": "open:values",
                "reproduce": "runs", "recipe": "recipe", "deck": "open:deck"}
    _REBUILD = {"units": "units_rebuild", "report": "report", "compare": "compare", "sweep": "sweep",
                "explore": "explore", "phy": "phy", "recipe": "recipe", "reproduce": "reproduce"}

    def compose(self) -> ComposeResult:
        with Horizontal(id="shrow"):
            yield NavList(id="outs")
            with VerticalScroll(id="sdetail"):
                yield Static("", id="sdetailbody")

    def focus_target(self):
        return self.query_one("#outs")

    def keys(self):
        return [("↑↓", "output"), ("↵", "open / run"), ("r", "rebuild"),
                ("f", "show in folder"), ("x", "export recipe")]

    def _rows(self):
        return getattr(self.c, "share_rows", None) or []

    def paint(self) -> None:
        ol = self.query_one("#outs", OptionList)
        keep = (ol.get_option_at_index(ol.highlighted).id
                if ol.highlighted is not None and ol.option_count else None)
        ol.clear_options()
        width = self.a.size.width - (48 if self.a.size.width >= 96 else 6)
        for r in self._rows():
            t = Text(no_wrap=True)
            status = r["status"]
            g, col = {"fresh": ("✓", GREEN), "present": ("✓", GREEN), "warn": ("!", AMBER),
                      "stale": ("!", AMBER), "unknown": ("?", AMBER),
                      "missing": ("·", MUTED)}.get(status, ("·", MUTED))
            t.append(f"{g} ", style=f"bold {col}")
            t.append(f"{r['title']:<22}", style="bold")
            t.append(r["note"][:40], style=col if status in ("warn", "stale", "unknown") else MUTED)
            t.truncate(max(20, width))
            ol.add_option(Option(t, id=r["key"]))
        idx = next((i for i, r in enumerate(self._rows()) if r["key"] == keep), 0)
        if ol.option_count:
            ol.highlighted = idx
        self.query_one("#sdetail").set_class(self.a.size.width < 96, "hidden")
        self._detail()

    def _key(self):
        ol = self.query_one("#outs", OptionList)
        if ol.highlighted is None or not ol.option_count:
            return None
        return ol.get_option_at_index(ol.highlighted).id

    def _detail(self) -> None:
        r = next((x for x in self._rows() if x["key"] == self._key()), None)
        t = Text()
        if r:
            t.append(r["title"].upper() + "\n", style=f"bold {SEC}")
            if r.get("path"):
                t.append(r["path"] + "\n", style=MUTED)
            t.append(r["note"] + "\n\n", style=SEC)
            acts = []
            if r["key"] in self._PRIMARY:
                acts.append(("↵", {"open:report": "open it", "phy": "export",
                                   "gui": "open the GUI", "runs": "runs and reproduce",
                                   "recipe": "write it"}.get(self._PRIMARY[r["key"]], "open it")))
            if r["key"] in self._REBUILD:
                acts.append(("r", "rebuild / re-run"))
            if r.get("path"):
                acts.append(("f", "show in folder"))
            for k, label in acts:
                t.append_text(chip(k))
                t.append(f" {label}\n")
        self.query_one("#sdetailbody", Static).update(t)

    def on_option_list_option_highlighted(self, _event) -> None:
        self._detail()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        key = event.option.id
        row = next((x for x in self._rows() if x["key"] == key), None)
        action = self._PRIMARY.get(key)
        if action and action.startswith("open:") and row and not row["exists"] \
                and key in self._REBUILD:
            action = self._REBUILD[key]       # not built yet: build it
        if action:
            self.a.do(action)

    def action_rebuild(self) -> None:
        key = self._key()
        if key in self._REBUILD:
            self.a.do(self._REBUILD[key])

    def action_folder(self) -> None:
        r = next((x for x in self._rows() if x["key"] == self._key()), None)
        if r and r.get("path"):
            ok, msg = self.c.open_path(str(r["path"]).rsplit("/", 1)[0]
                                       if not r["key"] in ("phy",) else r["path"])
            self.a.say(msg, GREEN if ok else AMBER)

    def action_recipe(self) -> None:
        self.a.do("recipe")


# --------------------------------------------------------------------------- #
# The app
# --------------------------------------------------------------------------- #
class SpikeApp(App):
    """Spike 2.0: the rail over the stage panes (see the module docstring)."""

    CSS = """
    Screen { background: $background; }
    * { scrollbar-size-vertical: 1; }
    #header { height: 1; padding: 0 1; margin: 1 0 0 0; }
    #rail { height: 2; padding: 0 1; margin: 1 0 0 0; }
    #hair { height: 1; padding: 0 1; color: $panel-lighten-2; }
    #panes { height: 1fr; padding: 1 2 0 2; }
    #status { height: 1; padding: 0 1; }
    #keys { height: 1; padding: 0 1; margin: 0 0 1 0; }
    OptionList { background: $background; }
    OptionList:focus > .option-list--option-highlighted { background: $accentcolor 22%; }
    """

    BINDINGS = [
        *[Binding(str(n), f"stage({n})", f"Stage {n}", show=False) for n in range(1, 7)],
        Binding("escape", "home", "Home", show=False),
        Binding("slash", "palette", "Find", show=False),
        Binding("comma", "settings", "Settings", show=False),
        Binding("question_mark", "help", "Help", show=False),
        Binding("q", "quit_key", "Quit", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    PANE_IDS = ("home", "data", "probe", "sort", "judge", "apply", "share")

    def __init__(self, controller, splash: bool = False):
        self.c = controller
        self._accent = controller.accent
        self._splash = splash
        self._stage = 0
        self._msg = None
        self._download = None
        self._compare_first = None
        super().__init__()

    def get_css_variables(self) -> dict:
        v = super().get_css_variables()
        v["accentcolor"] = self._accent
        return v

    def compose(self) -> ComposeResult:
        yield Static("", id="header")
        yield Static("", id="rail")
        yield Static("", id="hair")
        with ContentSwitcher(id="panes", initial="home"):
            yield HomePane(self, id="home")
            yield DataPane(self, id="data")
            yield ProbePane(self, id="probe")
            yield SortPane(self, id="sort")
            yield JudgePane(self, id="judge")
            yield ApplyPane(self, id="apply")
            yield SharePane(self, id="share")
        yield Static("", id="status")
        yield Static("", id="keys")

    def on_mount(self) -> None:
        self.go(0)
        if self._splash:
            self.push_screen(SplashScreen(self.c, self._accent))

    def on_resize(self, _event) -> None:
        self.refresh_all()

    # -- painting ------------------------------------------------------------ #
    def pane(self, n: "int | None" = None) -> Pane:
        return self.query_one(f"#{self.PANE_IDS[self._stage if n is None else n]}", Pane)

    def refresh_chrome(self) -> None:
        w = max(20, self.size.width - 2)
        snap = getattr(self.c, "journey", None) or {}
        run = snap.get("run") or {}
        head = Text(no_wrap=True)
        head.append(" spike ", style=f"bold {INK_ON_ACCENT} on {self._accent}")
        head.append("  " + str((snap.get("data") or {}).get("base")
                               or (self.c.data_report or {}).get("base") or "no recording"),
                    style=SEC)
        right = self.c.active_sorter
        if run:
            cur = snap.get("curation") or {}
            right += f" · run {run['id'][-6:]} · " + ("curated" if cur.get("has_curated")
                                                    else ("test sort" if run.get("smoke") else "raw"))
        if len(head) + len(right) + 2 <= w:
            head.append(" " * (w - len(head) - len(right)))
            head.append(right, style=MUTED)
        self.query_one("#header", Static).update(head)
        top, cap = rail_lines(getattr(self.c, "stages", None), self._stage, self._accent, w)
        self.query_one("#rail", Static).update(Text("\n").join([top, cap]))
        self.query_one("#hair", Static).update(Text("─" * w, style=FAINT))
        status = Text(no_wrap=True)
        if self._msg is not None:
            status.append_text(self._msg)
        sess = self._download
        if sess is not None and sess.result is None:
            status.append(f"   ⬇ {sess.name} {sess.stats.pct:d}%", style=self._accent)
        status.truncate(w)
        self.query_one("#status", Static).update(status)
        items = list(self.pane().keys())
        if self._stage:
            items.append(("esc", "home"))
        else:
            items.append(("1-6", "stages"))
        items += [("/", "find"), (",", "settings"), ("?", "help"), ("q", "quit")]
        self.query_one("#keys", Static).update(key_line(items, w))

    def refresh_all(self) -> None:
        try:
            self.pane().paint()
        except Exception as e:  # noqa: BLE001 - a paint bug must say so, not kill the app
            self._msg = Text(f"✗ couldn't draw this pane: {e!r}"[:200], style=RED)
        self.refresh_chrome()

    def say(self, text, style: str = "") -> None:
        self._msg = text if isinstance(text, Text) else Text(str(text), style=style)
        self.refresh_chrome()

    def after_change(self) -> None:
        """Something on disk changed: reload the controller, repaint everything."""
        try:
            self.c.reload()
        except Exception as e:  # noqa: BLE001
            self._msg = Text(f"reload failed: {e!r}", style=RED)
        self.refresh_all()

    # -- navigation ---------------------------------------------------------- #
    def go(self, n: int) -> None:
        self._stage = n
        self.query_one("#panes", ContentSwitcher).current = self.PANE_IDS[n]
        self.refresh_all()
        try:
            self.pane().focus_target().focus()
        except Exception:  # noqa: BLE001
            pass

    def action_stage(self, n: int) -> None:
        self.go(int(n))

    def action_home(self) -> None:
        if self._stage:
            self.go(0)

    def action_quit_key(self) -> None:
        """`q` quits from the stages only. Over a dialog or a running sort/task it
        would orphan the child process or skip a confirmation, so it says so."""
        if len(self.screen_stack) > 1:
            self.bell()
            return
        self.exit()

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self._accent, self.c.data_report))

    def action_palette(self) -> None:
        self.push_screen(PaletteScreen(self.c.actions, self._accent),
                         lambda key: key and self.do(key))

    def action_settings(self) -> None:
        self.open_settings()

    def open_settings(self, focus_key: "str | None" = None) -> None:
        self.push_screen(SettingsScreen(self, focus_key), lambda _r: self.refresh_all())

    def open_link(self, link: str, screen) -> None:
        """A Settings link row: open the screen that edits it."""
        if link == "probe":
            screen.dismiss(None)
            self.go(2)
        elif link == "sorter":
            screen.dismiss(None)
            self.go(3)
        elif link == "params":
            self._open_params(lambda: screen._fill())
        elif link == "docker":
            self._toggle_docker(after=lambda: screen._fill())
        elif link == "theme":
            self._open_theme(after=lambda: screen._fill())

    # -- the one action router ------------------------------------------------ #
    def do(self, key: str) -> None:
        c = self.c
        present = bool((c.data_report or {}).get("present"))
        needs = {a["key"]: a.get("needs_data") for a in c.actions}
        if key.startswith("stage:"):
            self.go(int(key.split(":")[1]))
            return
        if key.startswith("open:"):
            ok, msg = c.open_output(key.split(":", 1)[1])
            self.say(msg, GREEN if ok else AMBER)
            return
        if needs.get(key) and not present:
            self.say("✗ that needs the recording files - see 1 Data", AMBER)
            self.go(1)
            return
        if key == "quit":
            self.exit()
        elif key == "help":
            self.action_help()
        elif key == "settings":
            self.open_settings()
        elif key == "theme":
            self._open_theme()
        elif key == "folder":
            dr = c.data_report or {}
            self.push_screen(InputModal("Data folder", str(dr.get("data_dir", "")),
                                        "the folder holding the .ns5 / .ns2 / .nev set; "
                                        "remembered next launch",
                                        lambda raw: c.set_setting("data_dir", raw)),
                             lambda msg: msg and (self.say("✓ " + msg, GREEN), self.refresh_all()))
        elif key == "open_folder":
            ok, msg = c.open_data_folder()
            self.say(msg, GREEN if ok else AMBER)
        elif key in ("explore", "verify", "phy", "import_phy", "apply", "sweep"):
            self._command(key)
        elif key == "reproduce":
            self.reproduce(None)
        elif key == "units_rebuild":
            self.open_units(None, rebuild=True)
        elif key == "runs":
            self.push_screen(RunsScreen(self), lambda _r: self.after_change())
        elif key == "recipe":
            ok, msg = c.export_recipe()
            self.say(("✓ " if ok else "✗ ") + msg, GREEN if ok else AMBER)
            self.refresh_all()
        elif key in ("sort", "sort_quick"):
            self._sort("quick" if key == "sort_quick" else "full")
        elif key == "params":
            self._open_params()
        elif key == "manage":
            self.push_screen(ManageSortersScreen(c, self._accent), lambda _r: self.after_change())
        elif key == "report":
            self._report()
        elif key == "compare":
            self._compare()
        elif key in ("gui", "traces"):
            self._suspend_run(key)
        elif key == "units":
            self.open_units(None)
        elif key in ("probe_edit", "probe_new", "probe_import"):
            self.go(2)
            pane = self.pane(2)
            {"probe_edit": pane.action_edit, "probe_new": pane.action_new,
             "probe_import": pane.action_import_file}[key]()
        elif key == "docker":
            self._toggle_docker()
        else:
            self.say(f"nothing is wired to {key}", AMBER)

    # -- actions ------------------------------------------------------------- #
    def _command(self, key: str, run_id=None, on_done=None) -> None:
        try:
            cmd = self.c.command(key, run_id) if key == "reproduce" else self.c.command(key)
        except LookupError as e:
            self.say(f"✗ {e}", AMBER)
            return

        def done(res):
            ok, _detail = res or (False, "cancelled")
            if key == "reproduce":
                self._after_reproduce(cmd, res, on_done)
                return
            msg = self.c.finish_command(key, ok) if res and res[1] != "cancelled" else \
                f"{key} cancelled"
            self.say(msg, GREEN if ok else (MUTED if "cancel" in msg else RED))
            if ok and cmd.get("open"):
                self.c.open_output(cmd["open"])
            self.refresh_all()
            if on_done:
                on_done()

        self.push_screen(CommandScreen(cmd["argv"], cmd["title"], cmd["log"], self._accent), done)

    def open_units(self, unit=None, rebuild: bool = False) -> None:
        """The unit pages (real plots) at ``unit``: open them when this run's page
        exists, else draw them first (a few seconds) and then open."""
        if not rebuild and self.c.units_page_exists():
            ok, msg = self.c.open_units(unit)
            self.say(msg, GREEN if ok else AMBER)
            return
        self._command("units", on_done=lambda: self.c.units_page_exists()
                      and self.say(self.c.open_units(unit)[1], GREEN))

    def reproduce(self, run_id, on_done=None) -> None:
        if not (self.c.data_report or {}).get("present"):
            self.say("✗ reproducing needs the recording files - see 1 Data", AMBER)
            return
        self._command("reproduce", run_id, on_done)

    def _after_reproduce(self, cmd, res, on_done) -> None:
        import json

        data = None
        try:
            data = json.loads(cmd["report"].read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - no report: the run failed before comparing
            data = None
        self.c.finish_command("reproduce", data is not None)
        if data is not None:
            verdict = (data.get("report") or {}).get("verdict") or "ran; nothing to compare"
            self.say(f"Reproduce check: {verdict}", _verdict_style(verdict))
            self.push_screen(ReproduceReportScreen(data, self._accent))
        else:
            cancelled = res and res[1] == "cancelled"
            self.say("reproduce cancelled" if cancelled else
                     f"✗ the re-run failed before it could compare - log: {cmd['log']}",
                     MUTED if cancelled else RED)
        self.refresh_all()
        if on_done:
            on_done()

    def _sort(self, span: str) -> None:
        c = self.c
        if c.active_blocked_on_docker():
            self.say(f"{c.active_sorter} runs in Docker, which isn't running - start Docker "
                     "(m) or choose another sorter on 3 Sort", AMBER)
            self.go(3)
            return
        argv = c.sort_command(span)
        log = c.sort_log_path(span)
        self.push_screen(SortProgressScreen(argv, self._accent, log), self._after_sort)

    def _after_sort(self, result) -> None:
        ok, message, changed, next_action = result or (False, "Sort cancelled", False, None)
        if result is not None and not _m._is_cancel_msg(message):
            self.c.record_result("sort", ok)
        self._msg = Text(message, style=_m._result_style(ok, message))
        if changed:
            self.after_change()
        self.go(0)
        if next_action:
            self.do({"report": "report", "gui": "gui"}.get(next_action, next_action))

    def _report(self) -> None:
        try:
            log = self.c.report_log_path()
        except Exception:  # noqa: BLE001
            log = None
        self.push_screen(BuildProgressScreen(self.c.report_command(), self._accent,
                                             noun="Report", log_path=log), self._after_report)

    def _after_report(self, res) -> None:
        ok, message = res or (False, "report build failed")
        if not _m._is_cancel_msg(message):
            self.c.record_result("report", ok)
        self._msg = Text(message, style=_m._result_style(ok, message))
        if ok:
            self.c.reopen_last()
        self.after_change()

    def _compare(self) -> None:
        saved = self.c.saved_sorters()
        if len(saved) < 2:
            self.say("Comparing needs two saved sorts - sort a second sorter on 3 Sort", AMBER)
            return
        self.push_screen(ChoiceModal("Compare which sort?", [(s, s, "") for s in saved]),
                         self._compare_second)

    def _compare_second(self, first) -> None:
        if not first:
            return
        self._compare_first = first
        rest = [(s, s, "") for s in self.c.saved_sorters() if s != first]
        self.push_screen(ChoiceModal(f"…against which?  (vs {first})", rest), self._compare_run)

    def _compare_run(self, second) -> None:
        if not second:
            return
        pair = (self._compare_first, second)
        busy = BusyScreen(f"Comparing {pair[0]} vs {pair[1]}", self._accent,
                          "builds the agreement matrix (no cancel)")

        def done(res):
            ok, message, _changed = res or (False, "compare failed", False)
            self._msg = Text(message, style=_m._result_style(ok, message))
            self.after_change()
            if ok:
                self.c.open_output("compare")

        def work():
            import contextlib
            import io

            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    res = self.c.run_compare(pair)
            except Exception as e:  # noqa: BLE001
                res = (False, f"compare failed: {e!r}", False)
            self.call_from_thread(busy.finish, res)

        self.push_screen(busy, done)
        self.run_worker(work, thread=True)

    def _suspend_run(self, key: str) -> None:
        try:
            with self.suspend():
                ok, message, changed = self.c.run(key, None)
        except SuspendNotSupported:
            ok, message, changed = self.c.run(key, None)
        except Exception as e:  # noqa: BLE001
            ok, message, changed = False, f"{key} failed: {e!r}", False
        self._msg = Text(message, style=_m._result_style(ok, message))
        if changed:
            self.after_change()
        else:
            self.refresh_all()

    def _open_params(self, after=None) -> None:
        sorter = self.c.active_sorter
        try:
            defaults = self.c.default_params(sorter)
            descs = self.c.param_descriptions(sorter)
        except Exception as e:  # noqa: BLE001
            self.say(f"can't read {sorter} parameters: {e!r}", RED)
            return

        def done(result):
            if result is not None:
                s, overrides = result
                self.c.set_params(s, overrides)
                n = len(overrides)
                self.say(f"✓ {s}: {n} parameter{'s' if n != 1 else ''} changed from default"
                         if n else f"✓ {s}: parameters back to defaults", GREEN)
            self.refresh_all()
            if after:
                after()

        self.push_screen(ParamEditorScreen(sorter, defaults, descs,
                                           self.c.get_overrides(sorter), self._accent), done)

    def _open_theme(self, after=None) -> None:
        opts = [(n, n, "(current)" if n == self.c.theme_name else "") for n in self.c.themes]

        def done(name):
            if name:
                self._accent = self.c.set_theme(name)
                self.refresh_css()
                self.say(f"✓ accent colour → {name}", self._accent)
                self.refresh_all()
            if after:
                after()

        self.push_screen(ChoiceModal("Accent colour", opts), done)

    def _toggle_docker(self, after=None, offer: bool = False) -> None:
        """Flip Docker sorters. Turning OFF is immediate; turning ON - or ``offer``,
        when a Docker sorter was chosen and the daemon is not up - goes through the
        confirm dialog, which can also start Docker. ``offer`` never turns it off."""
        def apply_toggle():
            if offer and self.c.use_docker:      # already on: the dialog was for the daemon
                self.refresh_all()
                if after:
                    after()
                return
            on = self.c.toggle_docker()
            self.say("✓ Docker sorters on - choose one on 3 Sort" if on else "Docker sorters off",
                     GREEN if on else MUTED)
            self.refresh_all()
            if after:
                after()

        if self.c.use_docker and not offer:
            apply_toggle()
            return
        self.push_screen(DockerConfirmScreen(self.c, self._accent),
                         lambda r: apply_toggle() if r == "enable" else (after and after()))

    # -- choosing a sorter (the old picker's decision table) ------------------ #
    def select_sorter(self, name: str) -> None:
        info = next((i for i in self.c.infos if i["name"] == name), None)
        if info is None:
            return
        if info.get("group") == "docker" and not info.get("img_present"):
            if self.c.docker_status(refresh=False).get("running"):
                self.start_download(name)
            else:
                self._toggle_docker(offer=True)     # get Docker running first
        elif info.get("runnable"):
            if self.c.set_active_by_name(name):
                self.say(f"✓ {name} will run the next sort - f full sort, t quick test", GREEN)
            self.after_change()
        elif info.get("group") == "docker":
            self._toggle_docker(offer=True)         # image cached; Docker sorters off
        else:
            self.say(f"{name}: needs an NVIDIA GPU build - not offered on this computer"
                     if info.get("group") == "gpu" else f"{name}: not available on this computer",
                     AMBER)

    def start_download(self, name: str) -> None:
        if self._download is not None and self._download.result is None:
            self.say("a download is already running", AMBER)
            return
        sess = dlstats.DownloadSession(name=name, image="")
        sess.phase_caption = "starting…"
        sess.bytes_done = sess.bytes_total = None
        sess.has_bytes = False
        self._download = sess

        def on_progress(done, total, is_bytes=True):
            self.call_from_thread(self._dl_progress, sess, done, total, is_bytes)

        def on_status(text):
            self.call_from_thread(self._dl_status, sess, text)

        def work():
            try:
                ok, msg = self.c.download_image(name, on_progress, on_status,
                                                should_cancel=lambda: sess.cancelled)
            except Exception as e:  # noqa: BLE001
                ok, msg = False, f"download failed: {e}"
            self.call_from_thread(self._dl_finish, sess, ok, msg)

        self.run_worker(work, thread=True)
        self.push_screen(DownloadProgressScreen(self.c, name, self._accent),
                         lambda _r: self.refresh_chrome())

    def _dl_progress(self, sess, done, total, is_bytes=True) -> None:
        now = monotonic()
        if is_bytes != getattr(sess, "has_bytes", None):
            sess.stats.reset_window(now)
        sess.stats.update(done, total, now=now)
        sess.has_bytes = is_bytes
        sess.bytes_done, sess.bytes_total = (done, total) if is_bytes else (None, None)
        self.refresh_chrome()

    def _dl_status(self, sess, text) -> None:
        sess.phase_caption = text
        word = text.split()[0] if text else ""
        phase = _m._DL_PHASE.get(word)
        if phase and phase != sess.phase:
            sess.phase = phase
            sess.stats.set_phase(phase, now=monotonic())
        self.refresh_chrome()

    def _dl_finish(self, sess, ok, msg) -> None:
        sess.result = (ok, msg)
        if self._download is sess:
            self._download = None
        self._msg = Text(msg, style=_m._result_style(ok, msg))
        self.after_change()
