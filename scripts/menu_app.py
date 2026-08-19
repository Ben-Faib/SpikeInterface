"""Textual front-door dashboard for SpikeInterface_Menu.py (terminal UI v2).

A single, resident full-screen app that stays usable at any window size — from a
wide desktop terminal down to a short VS Code pane. It is a *view*: all heavy
loading and the actual running of actions live in a small ``Controller`` (built
in ``SpikeInterface_Menu.py``) that this app calls back into. That keeps the app
import-light (no SpikeInterface at import time) and unit-testable with Textual's
``run_test`` / ``Pilot`` harness.

The dashboard is **actions-first** (D5, Ben's 2026-08-18 decision of record —
supersedes the DESIGN_UX §2 two-pane layout; §1 language still binds). The
numbered WORKFLOW actions are the primary full-width panel — a first-time user
lands on exactly what they can do — with the MANAGE keys as one dim line below.
The sorter list lives behind the ``t`` picker (SorterPickerScreen: live filter
input focused on open, grouped list with GPU/not-available collapsed, a one-line
description footer). A RESULTS section (label + V_pp/SNR/noise/yield) appears
only when the active sorter has a saved sort. An always-on two-line banner sits
above: the INPUTS line (#databar — DATA + PROBE, or a loud ✗ problem) and the
SORT line (#sortbar — the active sorter's ONE home, with a dim "t change" hint).
The persistent LAST RESULT line (#resultbar) keeps the newest action outcome.

Layout (responsive):

    ┌ wordmark crest (collapses full→compact→hidden as height shrinks)     ┐
    │ ── University of Pittsburgh · SpikeInterface ── (#titlebar)           │
    │ DATA  ✓ all 3 streams    PROBE  nnx-a1x16 · 16 ch @ 100 µm ✓ (#databar)│
    │ SORT  ★ tridesclous2 · 13u · 30 s · Ready to run   t change (#sortbar) │
    │ ╭ ACTIONS ────────────────────────────────────────────────────────╮   │
    │ │ 1  Explore   figures: LFP + events, no sort needed              │   │
    │ │ … (2 Sort · 3 Report · 4 Inspect · 5 Compare · 6 Traces)        │   │
    │ ╰─────────────────────────────────────────────────────────────────╯   │
    │   e params · m sorters · p probe · v verify · ? help · q quit         │
    │ ╭ RESULTS ─ tridesclous2 · 13 units · 30 s sorted ─────────────────╮  │
    │ │ V_pp 34.2 µV · SNR 5.0 · noise 4.1 µV · yield 75% (12/16)        │  │
    │ ╰──────────────────────────────────────────────────────────────────╯  │
    │ LAST  ✓ report · 14:18 → outputs/report.html   r reopen  (#resultbar) │
    │ ↑/↓ choose · Enter run · 1-6 jump · t sorter · r · ? · q    (footer)  │
    └───────────────────────────────────────────────────────────────────────┘

``t`` opens the picker; Enter there routes the choice through the normal
activate / download / enable-Docker flows. ``x`` manages the ACTIVE sorter.
Yield order on small windows: crest → RESULTS → (tiny) banner/manage/LAST —
the action list and footer never clip.

The accent colour is themeable (driven into the ``$accentcolor`` CSS variable);
the Pitt blue+gold shield is fixed. Both lists scroll, so the active sorter and
the actions are always reachable even when the body is taller than the screen.
"""
from __future__ import annotations

import asyncio
from time import monotonic
from typing import Protocol

from rich.text import Text
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

import download_stats as dlstats  # pure download progress math + formatters
import sort_progress as _sp  # pure JSON progress protocol (no SI / Textual deps)
import sort_summary as _ss  # array/yield headline metrics (pure load/format helpers)
import ui  # shield art + theme palette + plain helpers (single source)


class NavList(OptionList):
    """OptionList with the extra menu keys the UI advertises: j/k to move and
    space to select (Enter already selects)."""

    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("space", "select", show=False),
    ]

# Width below which the SORTERS + ACTIONS panes stack vertically instead of
# side-by-side. Tuned so a split/VS Code pane collapses to a single column while a
# default 80-col terminal stays two-pane.
STACK_COLS = 64
# The always-on DATA + SORT banner is a fixed two rows, so the crest reserve never
# Rows the crest must leave for title + banner + footer + a usable body, so it
# drops full→compact→mini→hidden well before it would crowd the menu off a short
# window. (The wordmark tiers are 5 / 3 rows tall — see ui._WORDMARK_FULL/COMPACT.)
# Tuned so the big crest is deferential: it only claims the full tier on a tall
# (≈40+ row) terminal, dropping to the compact crest on the common 34–40 row window
# so the panes get the vertical room they need to read.
SHIELD_RESERVE = 24
# Unfocused panel border colour (focus uses the live accent).
_BORDER_DIM = "#3a3f47"

# Status-word -> session phase, shared by the download status handler.
_DL_PHASE = {"Downloading": "downloading", "Verifying": "verifying",
             "Extracting": "extracting", "Done": "done"}

# --------------------------------------------------------------------------- #
# Controller contract (implemented by SpikeInterface_Menu.MenuController)
# --------------------------------------------------------------------------- #
class Controller(Protocol):
    """What the app needs from its host. Attributes are read every render."""

    header: str
    sorters: list[str]                  # sorter names, in tab order
    themes: dict[str, str]              # name -> accent hex
    actions: list[dict]                 # {key,title,hint,needs_data,section}
    last_result: "dict | None"          # {key,ok,when,path} — newest action outcome
    active_idx: int
    accent: str                         # current accent hex
    theme_name: str
    quick_seconds: int                  # span for the "quick" sort modal choice
    pipeline: list[dict]                # {stage,status,detail} (sorter-independent)
    infos: list[dict]                   # full catalog: {name,group,status,runnable,
                                        # recommended,description,present,units,
                                        # duration,active,summary}
    data_report: dict                   # see SpikeInterface_Menu._data_report
    use_docker: bool
    want_welcome: bool
    active_probe: str
    want_probe_setup: bool
    probe_info: dict                    # {name,label,summary,layout,density_class,match,match_detail}

    def set_active_by_name(self, name: str) -> bool: ...
    def cycle_active(self) -> None: ...
    def set_theme(self, name: str) -> str: ...      # returns the new accent hex
    def reload(self) -> None: ...                   # refresh pipeline/infos/data_report
    def set_data_dir(self, path: str | None) -> bool: ...   # repoint + reload; found?
    def toggle_docker(self) -> bool: ...
    def docker_status(self, refresh: bool = False) -> dict: ...
    def start_docker(self) -> bool: ...
    def active_blocked_on_docker(self) -> bool: ...
    def mark_welcome_seen(self) -> None: ...
    def active_probe_info(self) -> dict: ...
    def probe_catalog(self) -> list[dict]: ...
    def set_active_probe(self, name: str) -> bool: ...
    def save_probe(self, profile) -> tuple[bool, str]: ...
    def delete_probe(self, name: str) -> tuple[bool, str]: ...
    def duplicate_probe(self, name, new_name, new_label=None) -> dict: ...
    def mark_probe_setup_seen(self) -> None: ...
    def sorter_fit(self, name: str) -> dict: ...
    def catalog_manufacturers(self) -> list[str]: ...
    def catalog_models(self, manufacturer: str) -> list[str]: ...
    def run(self, key: str, span: str | None) -> tuple[bool, str, bool]: ...
    def sort_command(self, span: str | None) -> list: ...
    def report_command(self) -> list: ...
    def report_log_path(self): ...
    def sort_log_path(self, span: str | None = None): ...
    def record_result(self, key: str, ok: bool) -> None: ...
    def reopen_last(self) -> tuple[bool, str]: ...
    def sort_expectations(self) -> dict: ...   # {"span","wall_seconds"} of the last run


# --------------------------------------------------------------------------- #
# Small modal screens
# --------------------------------------------------------------------------- #
class ChoiceModal(ModalScreen):
    """Centred single-select overlay; dismisses with the chosen key or None.

    Used for the sort-span pick and the theme picker so those choices stay
    inside the TUI (the app never has to drop out for them)."""

    DEFAULT_CSS = """
    ChoiceModal { align: center middle; }
    ChoiceModal > #dialog {
        width: 64; max-width: 90%; height: auto;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ChoiceModal #dialogtitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    ChoiceModal #dialognote { color: #f0883e; padding: 0 0 1 0; }
    ChoiceModal OptionList { height: auto; max-height: 12; background: $surface; border: none; }
    ChoiceModal OptionList:focus { border: none; }
    ChoiceModal #choicefoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, options: list[tuple[str, str, str]], note: str | None = None):
        super().__init__()
        self._title = title
        self._options = options
        self._note = note          # optional amber caution line under the title

    def compose(self) -> ComposeResult:
        opts = [Option(self._opt_text(m, h), id=k) for k, m, h in self._options]
        with Vertical(id="dialog"):
            yield Static(self._title, id="dialogtitle")
            if self._note:
                yield Static(self._note, id="dialognote")
            yield NavList(*opts, id="choicelist")
            yield Static("Enter to choose · Esc to cancel", id="choicefoot")

    def _opt_text(self, main: str, hint: str) -> Text:
        t = Text(main)
        if hint:
            t.append(f"   {hint}", style="dim")
        return t

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        ol.focus()
        ol.highlighted = 0  # a visible cursor so Enter/Space select immediately

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DataSetupScreen(ModalScreen):
    """Getting-started help: which recording files are expected, which are
    present/missing, and exactly where they belong. Escape (or Enter) closes."""

    DEFAULT_CSS = """
    DataSetupScreen { align: center middle; }
    DataSetupScreen > #dialog {
        width: 86; max-width: 96%; height: 90%; max-height: 32;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    DataSetupScreen #setuptitle { text-style: bold; color: $accentcolor; height: 1; }
    DataSetupScreen #setupscroll { height: 1fr; }       /* body scrolls; title + hint stay pinned */
    DataSetupScreen #setupbody { height: auto; }
    DataSetupScreen #setupfoot { color: $text-muted; height: 1; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    def __init__(self, report: dict, accent: str):
        super().__init__()
        self._report = report
        self._accent = accent

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Recording files — setup & status", id="setuptitle")
            with VerticalScroll(id="setupscroll"):
                yield Static(_setup_body(self._report, self._accent), id="setupbody")
            yield Static("Press Esc to close", id="setupfoot")

    def action_close(self) -> None:
        self.dismiss(None)


class DataFolderScreen(ModalScreen):
    """Point the dashboard at a different recording folder without relaunching —
    so a wrong-folder start is fixable in-app instead of quit-and-relaunch.
    Dismisses with the chosen path, '' for the repo root, or None to cancel."""

    DEFAULT_CSS = """
    DataFolderScreen { align: center middle; }
    DataFolderScreen > #dialog {
        width: 80; max-width: 96%; height: auto;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    DataFolderScreen #dftitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    DataFolderScreen #dfabove { color: $text-muted; padding: 0 0 1 0; }
    DataFolderScreen #dferr { color: #f85149; height: auto; padding: 1 0 0 0; }
    DataFolderScreen #dffoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current: str | None):
        super().__init__()
        self._current = current or ""

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Choose data folder", id="dftitle")
            yield Static("Folder holding the .ns5 / .ns2 / .nev set "
                         "(leave blank for the repo root).", id="dfabove")
            yield Input(value=self._current, placeholder="/path/to/recording", id="dfinput")
            yield Static("", id="dferr")
            yield Static("Enter to use this folder · Esc to cancel", id="dffoot")

    def on_mount(self) -> None:
        self.query_one("#dfinput", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = (event.value or "").strip()
        if not raw:
            self.dismiss("")            # blank -> repo root (data_dir = None)
            return
        from pathlib import Path
        p = Path(raw).expanduser()
        if not p.is_dir():
            self.query_one("#dferr", Static).update(Text(f"Not a folder: {p}", style="#f85149"))
            return
        self.dismiss(str(p))

    def action_cancel(self) -> None:
        self.dismiss(None)


def _kill_proc_tree(proc) -> None:
    """Cross-platform best-effort kill of an asyncio subprocess AND its children
    (POSIX killpg -> Windows taskkill /T /F, rc-checked -> terminate())."""
    if proc is None or proc.returncode is not None:
        return
    import os
    import signal
    import subprocess
    import sys as _sys
    killed = False
    if hasattr(os, "killpg"):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            killed = True
        except Exception:  # noqa: BLE001 - group already gone -> fall through
            killed = False
    elif _sys.platform == "win32":
        try:
            res = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                 capture_output=True, timeout=3)
            killed = res.returncode in (0, 128)   # 128 = already gone
        except Exception:  # noqa: BLE001 - fall through to terminate()
            killed = False
    if not killed:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001 - already gone
            pass


def _read_log_tail(log_path, n_lines: int = 8, max_chars: int = 600) -> str:
    """Last few non-blank lines of a captured stderr log (the real crash cause)."""
    if log_path is None:
        return ""
    try:
        from pathlib import Path as _P
        text = _P(log_path).read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - no log -> nothing to show
        return ""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[-n_lines:])[-max_chars:] if lines else ""


class BuildProgressScreen(ModalScreen):
    """Progress modal for a protocol-speaking BUILD subprocess (the report, D3b).

    A leaner sibling of SortProgressScreen: spawns ``argv`` (a --progress json
    child), folds its events through ``sort_progress.reduce``, and renders the
    phase checklist with per-phase durations + a ticking elapsed clock. Esc
    cancels (kills the child's tree); Enter closes when done. Dismisses
    ``(ok, message)`` — the app records the result and reopens the artifact."""

    DEFAULT_CSS = """
    BuildProgressScreen { align: center middle; }
    BuildProgressScreen > #builddialog {
        width: 64; max-width: 92%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    BuildProgressScreen #buildtitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    BuildProgressScreen #buildbody { height: auto; }
    BuildProgressScreen #buildfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "close_if_done", "Close", show=False),
    ]

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, argv: list, accent: str, noun: str = "Report",
                 done_verb: str = "built", log_path=None):
        super().__init__()
        self._argv = list(argv)
        self._accent = accent
        self._noun = noun
        self._done_verb = done_verb
        self._log_path = log_path
        self._state = _sp.new_state()
        self._proc = None
        self._spin = 0
        self._t0 = monotonic()

    def compose(self) -> ComposeResult:
        with Vertical(id="builddialog"):
            yield Static("", id="buildtitle")
            yield Static("", id="buildbody")
            yield Static("Esc to cancel", id="buildfoot")

    def on_mount(self) -> None:
        self.query_one("#builddialog").border_title = f"{self._noun.upper()} BUILD"
        self._repaint()
        self._timer = self.set_interval(0.2, self._tick)
        self.run_worker(self._run(), exclusive=True)

    def on_unmount(self) -> None:
        timer = getattr(self, "_timer", None)
        if timer is not None:
            timer.stop()

    async def _run(self) -> None:
        # Capture the child's stderr so a crash BEFORE any error event (import
        # failure, SI version skew — the lab's known failure class) stays
        # diagnosable (D3b review F3, mirroring the sort modal).
        log_fh = None
        if self._log_path is not None:
            try:
                from pathlib import Path as _P
                _P(self._log_path).parent.mkdir(parents=True, exist_ok=True)
                log_fh = open(self._log_path, "w", encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - logging is best-effort
                log_fh = None
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=(log_fh if log_fh is not None else asyncio.subprocess.DEVNULL),
                start_new_session=True,
            )
        except Exception as e:  # noqa: BLE001
            self.handle_event({"t": "error", "ok": False,
                               "message": f"couldn't start: {e}"})
            return
        try:
            if self._proc.stdout is not None:
                async for raw in self._proc.stdout:
                    ev = _sp.parse_line(raw.decode("utf-8", "replace"))
                    if ev:
                        self.handle_event(ev)
            await self._proc.wait()
        finally:
            if log_fh is not None:
                try:
                    log_fh.close()
                except Exception:  # noqa: BLE001
                    pass
        if self._state["done"] is None:
            rc = self._proc.returncode
            if rc == 0:
                self.handle_event({"t": "done", "ok": True, "units": None, "out": ""})
            else:
                tail = _read_log_tail(self._log_path)
                msg = f"build exited ({rc}) without finishing"
                if tail:
                    msg += f"\n{tail}"
                self.handle_event({"t": "error", "ok": False, "message": msg})

    def handle_event(self, ev: dict) -> None:
        _sp.reduce(self._state, ev)
        self._repaint()
        if self._state["done"] is not None:
            self.query_one("#buildfoot", Static).update("Press Enter to close")

    def _tick(self) -> None:
        if self._state["done"] is None:
            self._spin = (self._spin + 1) % len(self._SPINNER)
            self._repaint()

    def _repaint(self) -> None:
        s = self._state
        running = s["done"] is None
        secs = int(monotonic() - self._t0)
        head = Text()
        head.append(f"Building {self._noun.lower()}… " if running
                    else (f"{self._noun} {self._done_verb} "
                          if s["done"].get("ok") else f"{self._noun} build failed "),
                    style=f"bold {self._accent}" if running else
                    ("bold #3fb950" if s["done"].get("ok") else "bold #f85149"))
        head.append(f"{secs // 60}:{secs % 60:02d}", style="dim")
        self.query_one("#buildtitle", Static).update(head)
        t = Text()
        for p in s["phases"]:
            done = p["done"]
            t.append("✓ " if done else f"{self._SPINNER[self._spin]} ",
                     style="#3fb950" if done else f"bold {self._accent}")
            t.append(f"{p['title']}", style="" if done else "bold")
            if done and p.get("secs") is not None:
                t.append(f"   {p['secs']:.1f} s", style="dim")
            t.append("\n")
        if s["done"]:
            d = s["done"]
            if d.get("ok"):
                out = d.get("out", "")
                t.append(f"\n✓ {self._done_verb}", style="bold #3fb950")
                if out:
                    t.append(f" → {out}", style="dim")
                t.append("\n")
            else:
                t.append(f"\n✗ {d.get('message', 'build failed')}\n",
                         style="bold #f85149")
        self.query_one("#buildbody", Static).update(t)

    def action_cancel(self) -> None:
        # A reflexive Esc AFTER completion must not discard a real result as
        # "cancelled" — the artifact is already on disk (D3b review F5).
        if self._state["done"] is not None:
            return self.action_close_if_done()
        _kill_proc_tree(self._proc)
        self.dismiss((False, f"{self._noun} build cancelled"))

    def action_close_if_done(self) -> None:
        if self._state["done"] is None:
            return
        d = self._state["done"]
        ok = bool(d.get("ok"))
        msg = (f"✓ {self._noun} {self._done_verb}" if ok
               else f"✗ {d.get('message', 'build failed')}")
        self.dismiss((ok, msg))


class BusyScreen(ModalScreen):
    """An honest in-UI wait for a blocking action running in a thread worker: the
    named step, a spinner + ticking elapsed, and a stated no-cancel. The app
    dismisses it via ``finish(result)`` from the worker; Esc/Enter are deliberate
    no-ops — pretending to offer cancel for an uncancellable step is the lie this
    screen exists to avoid (DESIGN_UX §1.6/§6)."""

    DEFAULT_CSS = """
    BusyScreen { align: center middle; }
    BusyScreen > #busydialog {
        width: 62; max-width: 92%; height: auto;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    BusyScreen #busytitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    BusyScreen #busynote { color: $text-muted; }
    """

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, title: str, accent: str, note: str = ""):
        super().__init__()
        self._title = title
        self._accent = accent
        self._note = note
        self._t0 = monotonic()
        self._spin = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="busydialog"):
            yield Static("", id="busytitle")
            yield Static(self._note, id="busynote")

    def on_mount(self) -> None:
        self._repaint()
        self._timer = self.set_interval(0.2, self._repaint)

    def on_unmount(self) -> None:
        timer = getattr(self, "_timer", None)
        if timer is not None:
            timer.stop()

    def _repaint(self) -> None:
        self._spin = (self._spin + 1) % len(self._SPINNER)
        secs = int(monotonic() - self._t0)
        t = Text()
        t.append(f"{self._SPINNER[self._spin]} ", style=f"bold {self._accent}")
        t.append(self._title, style="bold")
        t.append(f" · {secs // 60}:{secs % 60:02d}", style="dim")
        self.query_one("#busytitle", Static).update(t)

    def finish(self, result) -> None:
        try:
            self.dismiss(result)
        except Exception:  # noqa: BLE001 - screen already popped: the flow was
            pass           # abandoned; swallowing beats WorkerFailed killing the app


class ParamEditorScreen(ModalScreen):
    """Edit one sorter's parameters. Scalars get an inline field/checkbox; complex
    values (dict/list/None) are edited as JSON. Save stores only changed keys."""

    DEFAULT_CSS = """
    ParamEditorScreen { align: center middle; }
    ParamEditorScreen > #dialog {
        width: 92; max-width: 96%; height: 90%; max-height: 36;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ParamEditorScreen #ptitle { text-style: bold; color: $accentcolor; height: 1; }
    ParamEditorScreen #pscroll { height: 1fr; }
    ParamEditorScreen .prow { height: auto; padding: 0 0 1 0; }
    ParamEditorScreen .pname { color: $accentcolor; text-style: bold; }
    ParamEditorScreen .pdesc { color: $text-muted; }
    ParamEditorScreen Input { width: 100%; }
    ParamEditorScreen Input.invalid { border: tall #f85149; }
    ParamEditorScreen #perror { color: #f85149; height: auto; }
    ParamEditorScreen #pfoot { color: $text-muted; height: 1; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+r", "reset", "Reset"),
    ]

    # The knobs a newcomer actually reaches for float to the top (right under any
    # already-overridden keys — the user's own knobs lead). Everything else keeps
    # SpikeInterface's order.
    _PRIORITY_KEYS = ("detect_threshold", "detection_threshold", "freq_min",
                      "freq_max", "detect_sign")

    def __init__(self, sorter, defaults, descs, overrides, accent):
        super().__init__()
        self._sorter = sorter
        self._defaults = defaults
        self._descs = descs or {}
        self._overrides = overrides or {}
        self._accent = accent
        self._widgets: dict = {}  # key -> (kind, widget)
        self._names: dict = {}    # key -> the name Label (for the ● overridden mark)

    def _ordered_keys(self) -> list:
        over = [k for k in self._defaults if k in self._overrides]
        prio = [k for k in self._PRIORITY_KEYS if k in self._defaults and k not in over]
        rest = [k for k in self._defaults if k not in over and k not in prio]
        return over + prio + rest

    def _name_text(self, key) -> Text:
        t = Text()
        if key in self._overrides:
            t.append("● ", style=f"bold {self._accent}")
        t.append(key)
        return t

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"Parameters · {self._sorter}", id="ptitle")
            with VerticalScroll(id="pscroll"):
                for key in self._ordered_keys():
                    default = self._defaults[key]
                    cur = self._overrides.get(key, default)
                    with Vertical(classes="prow"):
                        name = Label(self._name_text(key), classes="pname")
                        self._names[key] = name
                        yield name
                        desc = self._descs.get(key)
                        if desc:
                            yield Label(str(desc), classes="pdesc")
                        if isinstance(default, bool):
                            w = Checkbox("enabled", value=bool(cur), id=f"w_{key}")
                            self._widgets[key] = ("bool", w)
                            yield w
                        elif isinstance(default, (int, float, str)) or default is None:
                            w = Input(value=_param_to_str(cur), id=f"w_{key}")
                            self._widgets[key] = ("scalar", w)
                            yield w
                        else:  # dict / list -> JSON
                            import json as _json
                            w = Input(value=_json.dumps(cur), id=f"w_{key}")
                            self._widgets[key] = ("json", w)
                            yield w
            yield Static("", id="perror")
            yield Static("Ctrl+S save · Ctrl+R reset to defaults · Esc cancel", id="pfoot")

    def on_mount(self) -> None:
        self.query_one("#pscroll").focus()

    def _key_of(self, widget) -> "str | None":
        wid = getattr(widget, "id", "") or ""
        return wid[2:] if wid.startswith("w_") else None

    def on_input_changed(self, event) -> None:
        """Live validation: coerce as the user types — invalid goes red with the
        error named in #perror; valid clears it and refreshes the ● mark."""
        key = self._key_of(event.input)
        if key is None or key not in self._defaults:
            return
        import sorters as _sorters

        default = self._defaults[key]
        kind, w = self._widgets[key]
        err = self.query_one("#perror", Static)
        try:
            val = _sorters.coerce_param(default, event.value)
        except ValueError as e:
            w.add_class("invalid")
            err.update(f"{key}: {e}")
            return
        w.remove_class("invalid")
        err.update("")
        # The ● mark follows the LIVE value (an edit back to the default un-marks).
        label = self._names.get(key)
        if label is not None:
            t = Text()
            if val != default:
                t.append("● ", style=f"bold {self._accent}")
            t.append(key)
            label.update(t)

    def on_checkbox_changed(self, event) -> None:
        """Bool params: the ● overridden mark tracks toggles live (D4 review F5)."""
        key = self._key_of(event.checkbox)
        if key is None or key not in self._defaults:
            return
        label = self._names.get(key)
        if label is not None:
            t = Text()
            if bool(event.value) != bool(self._defaults[key]):
                t.append("● ", style=f"bold {self._accent}")
            t.append(key)
            label.update(t)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_reset(self) -> None:
        self.dismiss((self._sorter, {}))  # empty overrides -> controller clears them

    def action_save(self) -> None:
        import sorters as _sorters

        overrides = {}
        for key, (kind, w) in self._widgets.items():
            default = self._defaults[key]
            if kind == "bool":
                val = bool(w.value)
            else:
                raw = w.value
                try:
                    val = _sorters.coerce_param(default, raw)
                except ValueError as e:
                    self.query_one("#perror", Static).update(f"{key}: {e}")
                    return
            if val != default:
                overrides[key] = val
        self.dismiss((self._sorter, overrides))


class DockerConfirmScreen(ModalScreen):
    """Guided 'enable Docker?' dialog. Reads the live three-state status from the
    controller and adapts: running → just Enable; installed-not-running → Start
    Docker for me + Re-check; not-installed → Open download page + Re-check. Enable
    is always allowed (container sorters appear once Docker is up). Dismisses
    'enable' or None."""

    DOWNLOAD_URL = "https://www.docker.com/products/docker-desktop/"

    DEFAULT_CSS = """
    DockerConfirmScreen { align: center middle; }
    DockerConfirmScreen > #dialog {
        width: 64; max-width: 92%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    DockerConfirmScreen #dtitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    DockerConfirmScreen #dstatus { height: auto; }
    DockerConfirmScreen #dfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("e", "enable", "Enable"),
        Binding("s", "start_docker", "Start Docker"),
        Binding("o", "open_download", "Open download"),
        Binding("r", "recheck", "Re-check"),
        Binding("enter", "enable", "Enable", show=False),
    ]

    def __init__(self, controller, accent: str):
        super().__init__()
        self._c = controller
        self._accent = accent
        self._polls = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Enable Docker sorters?", id="dtitle")
            yield Static("", id="dstatus")
            yield Static("", id="dfoot")

    def on_mount(self) -> None:
        self._render_status()

    def _render_status(self) -> None:
        st = self._c.docker_status(refresh=False)
        t = Text()
        t.append("These run extra sorters your computer doesn't have installed.\n", style="")
        t.append("• First run downloads a large image (~1 GB) and is slower.\n", style="dim")
        t.append("• Needs Docker Desktop running.\n\n", style="dim")
        colour = "#3fb950" if st["running"] else "#f0883e"
        t.append(st["text"] + "\n", style=f"bold {colour}")
        if st["state"] == "not_installed":
            t.append("It's a free app that unlocks extra sorters.\n", style="dim")
        self.query_one("#dstatus", Static).update(t)
        self.query_one("#dfoot", Static).update(self._foot_text(st["state"]))

    def _foot_text(self, state: str) -> Text:
        f = Text()
        if state == "not_installed":
            f.append("[o] open download page   ", style="dim")
        elif state == "installed_not_running":
            f.append("[s] start Docker for me   ", style="dim")
        f.append("[r] re-check   [e] enable   [Esc] cancel", style="dim")
        return f

    def action_enable(self) -> None:
        self.dismiss("enable")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_open_download(self) -> None:
        import webbrowser
        try:
            webbrowser.open(self.DOWNLOAD_URL)
        except Exception:  # noqa: BLE001
            pass

    def action_recheck(self) -> None:
        self._c.docker_status(refresh=True)
        self._render_status()

    def action_start_docker(self) -> None:
        self._c.start_docker()
        self.query_one("#dstatus", Static).update(
            Text("Starting Docker…  (~30–60s — press [r] to re-check)", style="dim"))
        self._polls = 0
        self._stop_poll()                        # cancel any prior poll loop first
        self._poll_timer = self.set_interval(2.0, self._poll)

    def on_unmount(self) -> None:
        self._stop_poll()                        # never leave a 2s probe running

    def _stop_poll(self) -> None:
        timer = getattr(self, "_poll_timer", None)
        if timer is not None:
            timer.stop()
            self._poll_timer = None

    def _poll(self) -> None:
        self._polls += 1
        st = self._c.docker_status(refresh=True)
        if st["running"]:
            self._stop_poll()                    # done — don't keep probing every 2s
            self._render_status()                # advances to the 'running' view
            return
        if self._polls >= 45:                    # ~90s timeout -> manual fallback
            self._stop_poll()
            self.query_one("#dstatus", Static).update(
                Text("Still not ready — open Docker Desktop, then press [r].", style="#f0883e"))
            return


class SortProgressScreen(ModalScreen):
    """Runs a sort subprocess and renders its JSON progress events in-UI.

    The Textual app never imports SpikeInterface; instead we spawn
    ``run_sorting.py --progress json`` (the ``argv`` from
    ``MenuController.sort_command``) and read its newline-delimited JSON events on
    stdout, folding each through ``sort_progress.reduce`` into ``self._state`` and
    re-rendering. The subprocess gets its own session (``start_new_session=True``)
    so Esc can kill the whole process *group* (SI spawns worker children) with one
    ``os.killpg``.

    A phase checklist (✓ done / ▶ current) sits above the live detail for the
    current phase, which stacks (any that apply, in order): a ``→ {substep} (i/n)``
    line (a named sub-step within the phase), a dim ``→ {detail}`` line (the latest
    forwarded sorter step print, e.g. "detect_peaks(): 562 peaks found"), an
    optional determinate bar (drawn only when a ``bar`` event carries a ``total``),
    and — during indeterminate stretches — a spinner + "still working (Ns)" line fed
    by ``heartbeat`` events. These coexist: a phase can show a substep, the latest
    detail, AND a bar/heartbeat at once. On done/error the result line shows and the
    footer flips to "Press Enter to close". Esc cancels.

    ``handle_event`` is a *synchronous* reduce-then-render entry point so a Pilot
    test can drive the screen with synthetic events (no real subprocess)."""

    DEFAULT_CSS = """
    SortProgressScreen { align: center middle; }
    SortProgressScreen > #sortdialog {
        width: 70; max-width: 92%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    SortProgressScreen #sorttitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    SortProgressScreen #sortbody { height: auto; }
    SortProgressScreen #sortfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "close_if_done", "Close", show=False),
        # Result-card chaining (DESIGN_UX §3): after an OK sort, 3/4 close the modal
        # AND queue the next step — dispatched by the app after the pop (the modal
        # contract carries an optional next_action; a running sort ignores them).
        Binding("3", "chain('report')", "Build report", show=False),
        Binding("4", "chain('gui')", "Inspect in GUI", show=False),
    ]

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    # Friendly names for the sorter internals that leak into detail lines — the
    # counts stay (they're real information); only the jargon head is translated.
    _DETAIL_FRIENDLY = {
        "detect_peaks": "detecting peaks",
        "select_peaks": "selecting peaks",
        "extract_waveforms": "extracting waveforms",
        "split_clusters": "splitting clusters",
        "merge_clusters": "merging clusters",
        "find_spikes": "finding spikes",
    }

    def __init__(self, argv: list, accent: str, log_path=None):
        super().__init__()
        self._argv = list(argv)
        self._accent = accent
        # The child's stderr (human/rich output + any Python traceback) is captured
        # here so a hard crash that bypasses the JSON error event is still readable.
        self._log_path = log_path
        self._state = _sp.new_state()
        self._proc = None
        self._spin = 0
        # Context for the header + result card, read off the argv (the modal knows
        # no controller): the sorter name and whether this is the quick span.
        try:
            self._sorter = argv[argv.index("--sorter") + 1]
        except (ValueError, IndexError):
            self._sorter = ""
        self._quick = "--duration" in argv
        # Local wall clock for the ticking header; the emitter's `elapsed` is the
        # authoritative number and lands on the result card.
        self._t0 = monotonic()

    def compose(self) -> ComposeResult:
        with Vertical(id="sortdialog"):
            yield Static("Sorting…", id="sorttitle")
            yield Static("", id="sortbody")
            yield Static("Esc to cancel", id="sortfoot")

    def on_mount(self) -> None:
        self.query_one("#sortdialog").border_title = "SORTING"
        self._repaint()
        # A slow spinner tick keeps the indeterminate-phase glyph alive even while
        # the subprocess is quiet (between heartbeats). Cheap — no work when done.
        self._spin_timer = self.set_interval(0.2, self._tick_spinner)
        self.run_worker(self._run(), exclusive=True)

    def on_unmount(self) -> None:
        timer = getattr(self, "_spin_timer", None)
        if timer is not None:
            timer.stop()

    async def _run(self) -> None:
        # Capture the child's stderr to a log file (not DEVNULL) so a hard crash that
        # never reaches the JSON error event is still diagnosable: its tail is shown in
        # the modal and the full traceback is on disk. Falls back to DEVNULL if the log
        # can't be opened (read-only dir etc.).
        log_fh = None
        if self._log_path is not None:
            try:
                from pathlib import Path as _P
                _P(self._log_path).parent.mkdir(parents=True, exist_ok=True)
                log_fh = open(self._log_path, "w", encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - logging is best-effort
                log_fh = None
        self._log_fh = log_fh
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=(log_fh if log_fh is not None else asyncio.subprocess.DEVNULL),
                start_new_session=True,
            )
        except Exception as e:  # noqa: BLE001 - bad argv / no python -> friendly error
            self.handle_event({"t": "error", "ok": False,
                               "message": f"couldn't start sort: {e}"})
            return
        try:
            if self._proc.stdout is not None:
                async for raw in self._proc.stdout:
                    ev = _sp.parse_line(raw.decode("utf-8", "replace"))
                    if ev:
                        self.handle_event(ev)
            await self._proc.wait()
        finally:
            if log_fh is not None:
                try:
                    log_fh.close()
                except Exception:  # noqa: BLE001
                    pass
        if self._state["done"] is None:
            # The process ended without emitting done/error (e.g. argv was a plain
            # 'true' in tests, or a hard crash — segfault / OOM-kill — that bypasses
            # even run_sorting's last-resort error event) — synthesise a close state,
            # surfacing the captured stderr tail so the user sees the real cause.
            rc = self._proc.returncode
            if rc == 0:
                self.handle_event({"t": "done", "ok": True, "units": "?", "out": ""})
            else:
                tail = self._log_tail()
                msg = f"sort exited ({rc}) without finishing"
                if tail:
                    msg += f"\n{tail}"
                self.handle_event({"t": "error", "ok": False, "message": msg})

    def _log_tail(self, n_lines: int = 8, max_chars: int = 600) -> str:
        """Last few non-blank lines of the captured stderr log (the real error)."""
        if self._log_path is None:
            return ""
        try:
            from pathlib import Path as _P
            text = _P(self._log_path).read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - no log -> nothing to show
            return ""
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return ""
        tail = "\n".join(lines[-n_lines:])
        return tail[-max_chars:]

    def handle_event(self, ev: dict) -> None:
        """Synchronous: fold one event into the state and re-render. Safe to call
        from the reader worker or directly from a test."""
        _sp.reduce(self._state, ev)
        self._repaint()
        if self._state["done"] is not None:
            # The result card carries the chaining keys (one home, §1.1); the
            # footer stays the plain close hint.
            self.query_one("#sortfoot", Static).update("Press Enter to close")

    def _tick_spinner(self) -> None:
        # While running, every tick advances the spinner AND the header's elapsed
        # clock — a quiet subprocess must still look alive (DESIGN_UX §1.6).
        s = self._state
        if s["done"] is None:
            self._spin = (self._spin + 1) % len(self._SPINNER)
            self._repaint()

    @staticmethod
    def _fmt_mmss(secs: float) -> str:
        secs = max(0, int(secs))
        return f"{secs // 60}:{secs % 60:02d}"

    def _friendly_detail(self, detail: str) -> str:
        # Translate the jargon head, keep EVERYTHING after it verbatim — counts and
        # qualifiers are real information (D2v review F3).
        for head, nice in self._DETAIL_FRIENDLY.items():
            if detail.startswith(head):
                rest = detail[len(head):]
                if rest.startswith("()"):
                    rest = rest[2:]
                return (nice + rest).strip()
        return detail

    # NB: deliberately NOT named ``_render`` — that collides with Textual's
    # ``Widget._render`` (the layout engine calls it expecting a Visual).
    def _repaint(self) -> None:
        s = self._state
        running = s["done"] is None
        # Header: what · how much · a ticking clock — the run always looks alive.
        head = Text()
        span = "quick test" if self._quick else "full recording"
        head.append("Sorting… " if running else
                    ("Sorted " if s["done"].get("ok") else "Sort failed "),
                    style=f"bold {self._accent}" if running else
                    ("bold #3fb950" if s["done"].get("ok") else "bold #f85149"))
        if self._sorter:
            head.append(f"{self._sorter} · ", style="bold")
        head.append(f"{span} · {self._fmt_mmss(monotonic() - self._t0)}", style="dim")
        self.query_one("#sorttitle", Static).update(head)
        t = Text()
        # The phase checklist — finished phases carry their real (emitter-side)
        # durations; the running one carries the live detail below it.
        for p in s["phases"]:
            done = p["done"]
            t.append("✓ " if done else "▶ ",
                     style="#3fb950" if done else f"bold {self._accent}")
            t.append(f"{p['title']}", style="" if done else "bold")
            if done and p.get("secs") is not None:
                t.append(f"   {p['secs']:.1f} s", style="dim")
            t.append("\n")
        if running and s.get("phase_n"):
            i = s.get("phase_i") or len(s["phases"])
            t.append(f"  phase {i} of {s['phase_n']}\n", style="dim")
        # Live detail for the current phase — substep, latest (translated) sorter
        # step line, the determinate bar, and the heartbeat stack (whichever apply);
        # the reducer clears them at each new phase.
        if running:
            if s.get("substep_name"):
                t.append(f"  → {s['substep_name']} "
                         f"({s['substep_i']}/{s['substep_n']})\n",
                         style=f"bold {self._accent}")
            if s.get("detail"):
                t.append(f"  → {self._friendly_detail(s['detail'])}\n", style="dim")
        bar = s["bar"]
        # Honest progress (§3): a full bar under a still-running step reads as a
        # finished phase — the bar yields to the spinner/heartbeat before ROUNDING
        # can print "100%" (F1: 0.996 must not display as a full-looking 100%).
        if running and bar and bar.get("total") and (bar.get("frac") or 0.0) < 0.995:
            frac = bar.get("frac") or 0.0
            fill = int(frac * 24)
            t.append(f"  {bar.get('desc', '')} ", style="dim")
            t.append("█" * fill + "░" * (24 - fill), style=self._accent)
            t.append(f"  {int(frac * 100):3d}%\n", style="dim")
        if s["heartbeat"] and running:
            spin = self._SPINNER[self._spin]
            t.append(f"  {spin} {s['heartbeat']} … still working "
                     f"({s['heartbeat_secs']}s)\n", style="dim")
        # The array/yield headline card, once emitted — shown both during the run and
        # on the final screen so the six metrics stay visible after the sort finishes.
        card = (s.get("summary") or {}).get("card")
        if card:
            t.append("\nArray / yield summary\n", style=f"bold {self._accent}")
            for line in card:
                t.append(f"  {line}\n", style="dim")
        if s["done"]:
            t.append(self._result_card())
        self.query_one("#sortbody", Static).update(t)

    def _result_card(self) -> Text:
        """The run's closing card (DESIGN_UX §3): the result presented, never a
        green-and-gone. Success leads with the numbers; 0 units is amber with the
        fix named; failure is red with the log's tail."""
        s = self._state
        d = s["done"]
        r = s.get("result") or {}
        t = Text()
        if not d.get("ok"):
            t.append(f"\n✗ {d.get('message', 'sort failed')}\n", style="bold #f85149")
            tail = self._log_tail()
            msg = str(d.get("message", ""))
            if tail and tail not in msg:
                t.append(tail + "\n", style="dim")
            if self._log_path:
                t.append(f"log → {self._log_path}\n", style="dim")
            return t
        units = r.get("units", d.get("units", "?"))
        is_zero = isinstance(units, int) and units == 0
        if is_zero:
            t.append("\n⚠ 0 units found", style="bold #d29922")
            t.append(f" · {self._fmt_mmss(r.get('elapsed') or 0)}\n", style="dim")
            t.append("  lower detect_threshold (close, then e Edit parameters) and "
                     "re-run — the recording loaded and preprocessed fine.\n",
                     style="#d29922")
        else:
            t.append(f"\n✓ {units} units", style="bold #3fb950")
            good = r.get("good", d.get("good"))
            if good is not None:
                # The rule TEXT rides the result event — the emitting process is
                # the one that computed `good`, so the label can never lie about
                # which rule produced the number (W1 review F1).
                rule = r.get("rule") or "the quality rule"
                t.append(f" · {good} pass {rule}" if r.get("rule")
                         else f" · {good} pass the quality rule", style="")
            if r.get("elapsed") is not None:
                t.append(f" · {self._fmt_mmss(r['elapsed'])}", style="dim")
            t.append("\n")
            nf = r.get("noise_floor_uV")
            if nf is not None:
                # The canary is a verdict here (F5): in the observed band it reads
                # as checked; outside it goes amber with the known cause named —
                # never displayed as a mute number.
                if 3.5 <= nf <= 4.5:
                    t.append(f"  noise floor {nf:.2f} µV ✓", style="#3fb950")
                    t.append(" (expected ≈3.9–4.1 for this rig)\n", style="dim")
                else:
                    t.append(f"  ⚠ noise floor {nf:.2f} µV — outside the expected "
                             "≈3.9–4.1 band; check the run (a ~1 µV reading means "
                             "the µV scaling was applied twice)\n", style="#d29922")
        # The window fact matters in BOTH branches (F8): a 0-unit quick test's
        # likeliest fix is running the full recording.
        eff, tot = r.get("effective_seconds"), r.get("total_seconds")
        if eff and tot and eff < tot - 1.0:
            t.append(f"  partial: first {eff:.0f} s of {tot:.0f} s — re-run "
                     "full for the whole recording\n", style="#d29922")
        out = r.get("out", d.get("out", ""))
        if out:
            t.append(f"  saved → {out}\n", style="dim")
        if d.get("note"):
            t.append(f"  ⚠ {d['note']}\n", style="#d29922")
        # Chain keys only where the chained action can SUCCEED (F2): with 0 units
        # or failed metrics run_sorting deleted the analyzer, so report/GUI would
        # dead-end — offering them as next steps would be the dishonesty this
        # card exists to kill.
        if self._chainable():
            t.append("\n  ↵ close · 3 build report · 4 inspect in GUI",
                     style=f"bold {self._accent}")
        else:
            t.append("\n  ↵ close", style=f"bold {self._accent}")
        return t

    def _chainable(self) -> bool:
        """3/4 chaining is offered/allowed only when the saved analyzer exists:
        an OK sort with units and no metrics-failure note."""
        s = self._state
        d = s.get("done") or {}
        if not d.get("ok") or d.get("note"):
            return False
        units = (s.get("result") or {}).get("units", d.get("units"))
        return not (isinstance(units, int) and units == 0)

    def action_cancel(self) -> None:
        # A reflexive Esc AFTER completion closes normally — the sort already
        # happened; calling it "cancelled" would misrecord a real result (F5).
        if self._state["done"] is not None:
            return self.action_close_if_done()
        # Kill the whole worker tree, cross-platform (T2/T3 review found the lab-box
        # gap: os.killpg is POSIX-only and the old blanket except swallowed the
        # AttributeError — Windows showed "Sort cancelled" while the sort kept
        # burning CPU). POSIX: SIGTERM the process group (start_new_session gave us
        # one). Windows: taskkill /T /F takes the tree, since terminate() alone
        # would orphan SpikeInterface's spawn workers. Last resort: terminate().
        _kill_proc_tree(self._proc)
        self.dismiss((False, "Sort cancelled", False, None))

    def _dismiss_message(self) -> tuple:
        """(ok, message, changed) for the current terminal state. The 0-unit case
        carries the detect_threshold fix so it lands amber on the dashboard too —
        the same hint the result card shows (never a green '0 units')."""
        d = self._state["done"]
        ok = bool(d.get("ok"))
        units = (self._state.get("result") or {}).get("units", d.get("units", ""))
        if ok and isinstance(units, int) and units == 0:
            sorter = self._sorter or "sort"
            return (ok, f"⚠ {sorter}: no units found — lower detect_threshold "
                        f"(Edit parameters) and re-run", ok)
        if ok:
            return (ok, f"✓ Sorted {units} units".rstrip(), ok)
        return (ok, f"✗ {d.get('message', 'sort failed')}", ok)

    def action_close_if_done(self) -> None:
        if self._state["done"] is None:
            return                                  # still running — Enter is a no-op
        ok, msg, changed = self._dismiss_message()
        # Only an OK sort changed the saved-sort universe (cancel/error did not).
        self.dismiss((ok, msg, changed, None))

    def action_chain(self, next_action: str) -> None:
        """3/4 on the result card: close AND hand the app the next step. Only an
        OK finished sort chains — running or failed, the keys are no-ops."""
        if self._state["done"] is None or not self._chainable():
            return
        ok, msg, changed = self._dismiss_message()
        self.dismiss((ok, msg, changed, next_action))


class DownloadProgressScreen(ModalScreen):
    """Expanded telemetry view over the App's live ``DownloadSession``.

    The pull worker is owned by ``SpikeMenuApp`` (so it survives this modal being
    collapsed), not by this screen. This screen is a pure renderer: it reads
    ``self.app._download`` each tick and draws the phase caption + spinner, a
    determinate bar + percent, and a stats block (downloaded/total · speed; ETA ·
    elapsed). ``c`` collapses back to the dashboard indicator while the download
    continues; ``Esc`` cancels the download; Enter closes once finished."""

    DEFAULT_CSS = """
    DownloadProgressScreen { align: center middle; }
    DownloadProgressScreen > #dldialog {
        width: 70; max-width: 92%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    DownloadProgressScreen #dltitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    DownloadProgressScreen #dlbody { height: auto; }
    DownloadProgressScreen #dlfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("c", "collapse", "Collapse", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "close_if_done", "Close", show=False),
    ]

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, controller, name: str, accent: str):
        super().__init__()
        self._c = controller
        self._name = name
        self._accent = accent
        self._spin = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="dldialog"):
            yield Static(f"Downloading {self._name}", id="dltitle")
            yield Static("", id="dlbody")
            yield Static("This runs once (~1 GB).  [c] collapse · [Esc] cancel",
                         id="dlfoot")

    def on_mount(self) -> None:
        self.query_one("#dldialog").border_title = "DOWNLOAD"
        self._repaint()
        # Repaint on a timer: the App's worker mutates the shared session from a
        # thread; this pull-based redraw avoids cross-thread widget touches and also
        # animates the spinner during indeterminate (verify/extract) stretches.
        self._timer = self.set_interval(1.0 / 6, self._tick)

    def on_unmount(self) -> None:
        t = getattr(self, "_timer", None)
        if t is not None:
            t.stop()
            self._timer = None

    def _session(self):
        return getattr(self.app, "_download", None)

    def _tick(self) -> None:
        sess = self._session()
        if sess is not None and sess.result is None:
            self._spin = (self._spin + 1) % len(self._SPINNER)
        self._repaint()

    def _repaint(self) -> None:
        sess = self._session()
        t = Text()
        if sess is None:
            t.append("download finished", style="dim")
            self.query_one("#dlbody", Static).update(t)
            return
        st = sess.stats
        live = sess.result is None
        # Phase caption + spinner.
        if live:
            t.append(self._SPINNER[self._spin] + " ", style=self._accent)
        t.append(sess.phase_caption + "\n", style="dim")
        # Bar + percent.
        pct = st.pct
        fill = int(pct / 100 * 24)
        t.append("█" * fill + "░" * (24 - fill), style=self._accent)
        t.append(f"  {pct:3d}%\n\n", style="dim")
        # Stats block. Size · speed · ETA only make sense for a real byte transfer;
        # the extract / cached-layer phases report a layer-count fraction (no bytes),
        # so we show just the elapsed clock there — never a nonsensical "3 B / 9 B".
        if getattr(sess, "has_bytes", False) and sess.bytes_total:
            t.append(f"{dlstats.fmt_bytes(sess.bytes_done)} / "
                     f"{dlstats.fmt_bytes(sess.bytes_total)}"
                     f"   {dlstats.fmt_speed(st.speed)}\n", style="dim")
            t.append(f"ETA {dlstats.fmt_clock(st.eta)}"
                     f"          elapsed {dlstats.fmt_clock(st.elapsed)}", style="dim")
        else:
            # Extract / cached phase: Docker reports no bytes, but the layer-completion
            # rate gives an estimated ETA (tilde = estimate). Falls back to elapsed-only
            # until the rate warms up.
            eta = st.eta
            if eta is not None:
                t.append(f"~ETA {dlstats.fmt_clock(eta)}"
                         f"          elapsed {dlstats.fmt_clock(st.elapsed)}", style="dim")
            else:
                t.append(f"elapsed {dlstats.fmt_clock(st.elapsed)}", style="dim")
        if sess.result is not None:
            ok, msg = sess.result
            t.append("\n" + ("✓ " if ok else "✗ ") + msg,
                     style="bold " + ("#3fb950" if ok else "#f85149"))
        self.query_one("#dlbody", Static).update(t)
        if not live:
            self.query_one("#dlfoot", Static).update("Press Enter to close")

    def action_collapse(self) -> None:
        # Leave the worker running; the dashboard #dlbar takes over the display.
        self.dismiss("collapsed")

    def action_cancel(self) -> None:
        sess = self._session()
        if sess is not None and sess.result is None:
            sess.cancelled = True          # the worker's should_cancel hook breaks
        self.dismiss("collapsed")          # close now; finish handling runs on the App

    def action_close_if_done(self) -> None:
        sess = self._session()
        if sess is None or sess.result is not None:
            self.dismiss("collapsed")


class ManageSorterScreen(ModalScreen):
    """Quick per-sorter 'x' confirm: a short list of the *applicable* destructive
    operations for ONE sorter — delete its downloaded Docker image (only when the
    image is cached) and/or clear its saved sort (only when one exists). Each is a
    confirmed choice; dismisses with the chosen op key ('del_image'/'clear_sort')
    or None to cancel. The caller (``SpikeMenuApp.action_manage_highlighted``) only
    builds this screen when at least one op applies, so the list is never empty."""

    DEFAULT_CSS = """
    ManageSorterScreen { align: center middle; }
    ManageSorterScreen > #mgdialog {
        width: 64; max-width: 92%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ManageSorterScreen #mgtitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    ManageSorterScreen #mgbody { height: auto; padding: 0 0 1 0; }
    ManageSorterScreen OptionList { height: auto; max-height: 8; background: $surface; border: none; }
    ManageSorterScreen OptionList:focus { border: none; }
    ManageSorterScreen #mgfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, name: str, options: list[tuple[str, str]], accent: str):
        super().__init__()
        self._name = name
        self._options = options          # [(op_key, label), ...] — only applicable ops
        self._accent = accent

    def compose(self) -> ComposeResult:
        body = Text()
        body.append("These permanently delete saved data for this sorter:\n",
                    style="#f0883e")
        # List the applicable ops in the body too (not only as selectable rows) so
        # the dialog reads at a glance and is testable without the OptionList.
        for _key, label in self._options:
            body.append(f"  • {label}\n", style=ui.PRIMARY)
        with Vertical(id="mgdialog"):
            yield Static(f"Manage {self._name}", id="mgtitle")
            yield Static(body, id="mgbody")
            yield NavList(*[Option(label, id=key) for key, label in self._options],
                          id="mglist")
            yield Static("Enter to confirm · Esc to cancel", id="mgfoot")

    def on_mount(self) -> None:
        self.query_one("#mgdialog").border_title = "MANAGE SORTER"
        ol = self.query_one("#mglist", OptionList)
        ol.focus()
        ol.highlighted = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ManageSortersScreen(ModalScreen):
    """The full 'Manage sorters' hub: a scrollable, grouped list of every sorter
    showing its install / image-download / saved-sort state, with per-row keys to
    download an image (enter/g), delete a downloaded image (x), clear a saved sort
    (c), reload (r), and close (Esc). Destructive ops call the matching controller
    method directly, then reload + re-render the list (the in-UI download still
    routes through ``DownloadProgressScreen``)."""

    DEFAULT_CSS = """
    ManageSortersScreen { align: center middle; }
    ManageSortersScreen > #hubdialog {
        width: 86; max-width: 96%; height: 90%; max-height: 32;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ManageSortersScreen #hubtitle { text-style: bold; color: $accentcolor; height: 1; }
    ManageSortersScreen #hublist { height: 1fr; border: none; background: $surface; }
    ManageSortersScreen #hublist:focus { border: none; }
    ManageSortersScreen #hubfoot { color: $text-muted; height: auto; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        # Enter is handled via OptionList.OptionSelected (the focused list consumes the
        # keypress first); `g` is the spelled-out alternate so both reach download.
        Binding("g", "download", "Download", show=False),
        Binding("x", "delete_image", "Delete image", show=False),
        Binding("c", "clear_sort", "Clear saved", show=False),
        Binding("r", "reload", "Reload", show=False),
    ]

    # Same grouping/labels as the dashboard sidebar so the hub reads the same.
    _GROUP_ORDER = ["ready", "docker", "gpu", "unavailable"]
    _GROUP_LABEL = {
        "ready": "READY TO USE",
        "docker": "DOCKER SORTERS",
        "gpu": "NEEDS A GPU",
        "unavailable": "NOT AVAILABLE",
    }
    _GROUP_COLOR = {
        "ready": "#3fb950", "docker": "#d29922",
        "gpu": "#f0883e", "unavailable": "#6e7681",
    }

    def __init__(self, controller, accent: str):
        super().__init__()
        self._c = controller
        self._accent = accent
        self._last = None              # a one-line result of the last op

    def compose(self) -> ComposeResult:
        with Vertical(id="hubdialog"):
            yield Static("Manage sorters", id="hubtitle")
            yield NavList(id="hublist")
            yield Static("", id="hubfoot")

    def on_mount(self) -> None:
        self.query_one("#hubdialog").border_title = "MANAGE SORTERS"
        ol = self.query_one("#hublist", OptionList)
        ol.focus()
        self._rebuild()

    # -- list building -------------------------------------------------------- #
    def _rebuild(self) -> None:
        ol = self.query_one("#hublist", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        by_group: dict[str, list[dict]] = {}
        for info in self._c.infos:
            by_group.setdefault(info.get("group", "unavailable"), []).append(info)
        for group in self._GROUP_ORDER:
            members = by_group.get(group)
            if not members:
                continue
            ol.add_option(Option(Text(self._GROUP_LABEL[group],
                                       style=f"bold {self._GROUP_COLOR[group]}"),
                                  id=f"__grp_{group}__", disabled=True))
            for info in members:
                ol.add_option(Option(self._row_text(info), id=info["name"]))
        if ol.option_count:
            ol.highlighted = (keep if (keep is not None and keep < ol.option_count)
                              else self._first_selectable())
        self._render_foot()

    def _first_selectable(self) -> int:
        ol = self.query_one("#hublist", OptionList)
        for i in range(ol.option_count):
            opt = ol.get_option_at_index(i)
            if opt.id and not str(opt.id).startswith("__grp_"):
                return i
        return 0

    def _row_text(self, info: dict) -> Text:
        t = Text()
        t.append("  ")
        t.append(info["name"], style="bold" if info.get("active") else "")
        # Saved-sort state.
        if info.get("present"):
            t.append(f"   {info['units']}u saved", style="#3fb950")
        else:
            t.append("   no saved sort", style="dim")
        # Docker image state.
        if info.get("group") == "docker":
            if info.get("img_present"):
                size = (info.get("img_size") or 0) / 1e9
                t.append(f"   image: ~{size:.1f} GB" if size else "   image: downloaded",
                         style="dim #3fb950")
            else:
                t.append("   image: not downloaded", style="#d29922")
        return t

    def _render_foot(self) -> None:
        f = Text()
        if self._last is not None:
            f.append(self._last)
            f.append("\n")
        f.append("enter/g download · x delete image · c clear saved · r reload · Esc close",
                 style="dim")
        self.query_one("#hubfoot", Static).update(f)

    def _highlight_by_name(self, name: str) -> bool:
        """Move the hub cursor onto a sorter row by name (used by the keyboard flow
        + tests)."""
        ol = self.query_one("#hublist", OptionList)
        for i in range(ol.option_count):
            if ol.get_option_at_index(i).id == name:
                ol.highlighted = i
                return True
        return False

    def _highlighted_info(self) -> "dict | None":
        ol = self.query_one("#hublist", OptionList)
        if ol.highlighted is None:
            return None
        oid = ol.get_option_at_index(ol.highlighted).id
        if not oid or str(oid).startswith("__grp_"):
            return None
        return next((i for i in self._c.infos if i["name"] == oid), None)

    # -- per-row operations --------------------------------------------------- #
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        # Enter on a row: download its image (no-op for non-docker / already-cached).
        event.stop()
        self.action_download()

    def action_download(self) -> None:
        info = self._highlighted_info()
        if info is None or info.get("group") != "docker" or info.get("img_present"):
            return                          # nothing to download for this row
        self.app.push_screen(
            DownloadProgressScreen(self._c, info["name"], self._accent),
            self._after_download)

    def _after_download(self, result) -> None:
        ok, message = (result[0], result[1]) if isinstance(result, tuple) else (False, str(result))
        self._set_last(ok, message)
        self._reload_and_rebuild()

    def action_delete_image(self) -> None:
        # Destructive: confirm first (never delete on a single keystroke).
        info = self._highlighted_info()
        if info is None or not info.get("img_present"):
            self._set_last(False, "no downloaded image to delete")
            self._render_foot()
            return
        name = info["name"]
        size = (info.get("img_size") or 0) / 1e9
        sz = f" (~{size:.1f} GB)" if size else ""
        self.app.push_screen(
            ChoiceModal(f"Delete the downloaded image for {name}{sz}?",
                        [("confirm", "Delete image", ""), ("cancel", "Keep it", "")],
                        note="Removes only the cached image — you can re-download it later."),
            lambda r: self._confirmed_delete_image(name) if r == "confirm" else None)

    def _confirmed_delete_image(self, name: str) -> None:
        ok, msg = self._c.delete_image(name)
        self._set_last(ok, msg)
        self._reload_and_rebuild()

    def action_clear_sort(self) -> None:
        # Destructive: confirm first (never clear on a single keystroke).
        info = self._highlighted_info()
        if info is None or not info.get("present"):
            self._set_last(False, "no saved sort to clear")
            self._render_foot()
            return
        name, units = info["name"], info.get("units", "?")
        self.app.push_screen(
            ChoiceModal(f"Clear the saved {name} sort ({units}u)?",
                        [("confirm", "Clear saved sort", ""), ("cancel", "Keep it", "")],
                        note=f"Deletes outputs/{name}/ — you can re-run the sort later."),
            lambda r: self._confirmed_clear_sort(name) if r == "confirm" else None)

    def _confirmed_clear_sort(self, name: str) -> None:
        ok, msg = self._c.clear_saved_sort(name)
        self._set_last(ok, msg)
        self._reload_and_rebuild()

    def action_reload(self) -> None:
        self._reload_and_rebuild()
        self._set_last(True, "reloaded")
        self._render_foot()

    def _reload_and_rebuild(self) -> None:
        try:
            self._c.reload()
        except Exception as e:  # noqa: BLE001 - a reload failure must not kill the modal
            self._set_last(False, f"reload failed: {e!r}")
        self._rebuild()

    def _set_last(self, ok: bool, message: str) -> None:
        self._last = Text(message, style=_result_style(ok, message))

    def action_close(self) -> None:
        # Tell the caller whether anything changed so the dashboard reloads its own
        # sidebar/banner after the hub closes.
        self.dismiss(True)


# Kind -> editable numeric params (label, default) for the probe editor.
_PROBE_KIND_FIELDS = {
    "independent": [("pitch_um", 250.0)],
    "linear": [("n", 16), ("pitch_um", 50.0)],
    "grid": [("rows", 8), ("cols", 4), ("xpitch_um", 50.0), ("ypitch_um", 50.0)],
    "tetrode": [("n_tetrodes", 4), ("within_um", 25.0), ("between_um", 300.0)],
}


class ProbeEditorScreen(ModalScreen):
    """Create/edit a parametric probe profile. Numeric fields per kind + name/label."""

    DEFAULT_CSS = """
    ProbeEditorScreen { align: center middle; }
    ProbeEditorScreen > #dialog {
        width: 72; max-width: 94%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ProbeEditorScreen #petitle { text-style: bold; color: $accentcolor; height: 1; }
    ProbeEditorScreen .perow { height: auto; padding: 0 0 1 0; }
    ProbeEditorScreen .pelabel { color: $accentcolor; text-style: bold; }
    ProbeEditorScreen Input { width: 100%; }
    ProbeEditorScreen #peerror { color: #f85149; height: auto; }
    ProbeEditorScreen #pefoot { color: $text-muted; height: 1; padding: 1 0 0 0; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("ctrl+s", "save", "Save")]

    def __init__(self, profile, accent):
        super().__init__()
        self._profile = profile          # the seed profile (a copy to edit)
        self._accent = accent
        self._fields = {}

    def compose(self) -> ComposeResult:
        kind = self._profile["kind"]
        params = self._profile.get("params", {})
        with Vertical(id="dialog"):
            yield Static(f"Edit probe · {kind}", id="petitle")
            with Vertical(classes="perow"):
                yield Label("name (unique id)", classes="pelabel")
                self._fields["name"] = Input(value=self._profile["name"], id="f_name")
                yield self._fields["name"]
            with Vertical(classes="perow"):
                yield Label("label (shown in the UI)", classes="pelabel")
                self._fields["label"] = Input(value=self._profile.get("label", ""), id="f_label")
                yield self._fields["label"]
            for key, default in _PROBE_KIND_FIELDS.get(kind, []):
                with Vertical(classes="perow"):
                    yield Label(key, classes="pelabel")
                    w = Input(value=str(params.get(key, default)), id=f"f_{key}")
                    self._fields[key] = w
                    yield w
            yield Static("", id="peerror")
            yield Static("Ctrl+S save · Esc cancel", id="pefoot")

    def on_mount(self) -> None:
        self._fields["name"].focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        kind = self._profile["kind"]
        name = self._fields["name"].value.strip()
        if not name:
            self.query_one("#peerror", Static).update("name is required")
            return
        params = {}
        for key, default in _PROBE_KIND_FIELDS.get(kind, []):
            raw = self._fields[key].value.strip()
            try:
                params[key] = int(raw) if isinstance(default, int) else float(raw)
            except ValueError:
                self.query_one("#peerror", Static).update(f"{key}: expected a number")
                return
        self.dismiss({"name": name, "label": self._fields["label"].value.strip() or name,
                      "kind": kind, "params": params, "builtin": False, "note": ""})


class ProbeManagerScreen(ModalScreen):
    """Manage probe profiles: activate (enter), new (n), edit (e), duplicate (g),
    delete (x, user profiles only, confirmed). Shows each profile's summary + match."""

    DEFAULT_CSS = """
    ProbeManagerScreen { align: center middle; }
    ProbeManagerScreen > #pmdialog {
        width: 86; max-width: 96%; height: 90%; max-height: 30;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ProbeManagerScreen #pmtitle { text-style: bold; color: $accentcolor; height: 1; }
    ProbeManagerScreen #probelist { height: 1fr; border: none; background: $surface; }
    ProbeManagerScreen #probelist:focus { border: none; }
    ProbeManagerScreen #pmfoot { color: $text-muted; height: auto; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("n", "new", "New", show=False),
        Binding("e", "edit", "Edit", show=False),
        Binding("g", "duplicate", "Duplicate", show=False),
        Binding("x", "delete", "Delete", show=False),
    ]
    _NEW_KINDS = [("linear", "Linear"), ("grid", "2-D grid"), ("tetrode", "Tetrodes"),
                  ("independent", "Independent")]

    def __init__(self, controller, accent: str):
        super().__init__()
        self._c = controller
        self._accent = accent
        self._last = None

    def compose(self) -> ComposeResult:
        with Vertical(id="pmdialog"):
            yield Static("Probe geometry", id="pmtitle")
            yield OptionList(id="probelist")
            yield Static("", id="pmfoot")

    def on_mount(self) -> None:
        self.query_one("#pmdialog").border_title = "PROBES"
        self.query_one("#probelist", OptionList).focus()
        self._rebuild()

    def _rebuild(self) -> None:
        ol = self.query_one("#probelist", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        for row in self._c.probe_catalog():
            ol.add_option(Option(self._row_text(row), id=row["name"]))
        if ol.option_count:
            ol.highlighted = keep if (keep is not None and keep < ol.option_count) else 0
        self._render_foot()

    def _row_text(self, row: dict) -> Text:
        t = Text()
        t.append("▌ " if row.get("active") else "  ",
                 style=self._accent if row.get("active") else "")
        t.append(row["label"], style="bold" if row.get("active") else "")
        t.append(f"   {row['summary']}", style="dim")
        if not row.get("builtin"):
            t.append("  · custom", style="dim")
        match = row.get("match")
        if match == "mismatch":
            t.append(f"   ⚠ {row.get('match_detail','')}", style="#f0883e")
        elif match in ("fits", "auto"):
            t.append("   ✓", style="#3fb950")
        return t

    def _highlighted(self) -> "dict | None":
        ol = self.query_one("#probelist", OptionList)
        if ol.highlighted is None:
            return None
        oid = ol.get_option_at_index(ol.highlighted).id
        return next((r for r in self._c.probe_catalog() if r["name"] == oid), None)

    def _render_foot(self) -> None:
        f = Text()
        if self._last is not None:
            f.append(self._last); f.append("\n")
        f.append("enter activate · n new · e edit · g duplicate · x delete · Esc close",
                 style="dim")
        self.query_one("#pmfoot", Static).update(f)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        row = self._highlighted()
        if row and self._c.set_active_probe(row["name"]):
            self._last = Text(f"Active probe → {row['label']}", style=f"bold {self._accent}")
            self._rebuild()

    def action_new(self) -> None:
        opts = [(k, lbl, "") for k, lbl in self._NEW_KINDS]
        self.app.push_screen(ChoiceModal("New probe — which kind?", opts),
                             self._after_new_kind)

    def _after_new_kind(self, kind) -> None:
        if not kind:
            return
        seed = {"name": f"my-{kind}", "label": f"My {kind}", "kind": kind,
                "params": {}, "builtin": False, "note": ""}
        self.app.push_screen(ProbeEditorScreen(seed, self._accent), self._after_edit)

    def action_edit(self) -> None:
        row = self._highlighted()
        if row is None:
            return
        # Imported probes are view/duplicate/delete-only (P1 handoff, 2026-08-18):
        # the generic field form knows no params for kind 'imported' and a rename
        # would orphan the materialised geometry — refuse with the next step named
        # rather than offering a flow that ends in an error.
        if row.get("kind") == "imported":
            self._last = Text("imported probes can't be edited — duplicate or "
                              "re-import instead", style="#f0883e")
            self._rebuild()
            return
        seed = {"name": row["name"], "label": row["label"], "kind": row["kind"],
                "params": dict(row.get("params", {})), "builtin": row.get("builtin"),
                "note": ""}
        if row.get("builtin"):     # built-ins are immutable -> edit a copy
            seed["name"] = f"{row['name']}-copy"
            seed["label"] = f"{row['label']} (copy)"
        self.app.push_screen(ProbeEditorScreen(seed, self._accent), self._after_edit)

    def _after_edit(self, profile) -> None:
        if not profile:
            return
        ok, msg = self._c.save_probe(profile)
        self._last = Text(msg, style=_result_style(ok, msg))
        self._rebuild()

    def action_duplicate(self) -> None:
        row = self._highlighted()
        if row is None:
            return
        self._c.duplicate_probe(row["name"], f"{row['name']}-copy", f"{row['label']} (copy)")
        self._last = Text(f"Duplicated {row['name']}", style="#3fb950")
        self._rebuild()

    def action_delete(self) -> None:
        row = self._highlighted()
        if row is None or row.get("builtin"):
            self._last = Text("built-in profiles can't be deleted (duplicate to edit)",
                              style="#f0883e")
            self._render_foot()
            return
        name = row["name"]
        self.app.push_screen(
            ChoiceModal(f"Delete the probe profile {name}?",
                        [("confirm", "Delete it", ""), ("cancel", "Keep it", "")]),
            lambda r: self._confirmed_delete(name) if r == "confirm" else None)

    def _confirmed_delete(self, name: str) -> None:
        ok, msg = self._c.delete_probe(name)
        self._last = Text(msg, style=_result_style(ok, msg))
        self._rebuild()

    def action_close(self) -> None:
        self.dismiss(True)


class WelcomeScreen(ModalScreen):
    """First-launch onboarding (shown once; re-openable from Help)."""

    DEFAULT_CSS = """
    WelcomeScreen { align: center middle; }
    WelcomeScreen > #dialog {
        width: 60; max-width: 92%; height: auto;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    WelcomeScreen #wcrest { height: auto; content-align: center top; padding: 0 0 1 0; }
    WelcomeScreen #wtitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    WelcomeScreen #wfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("enter", "start", "Get started"),
        Binding("escape", "start", "Get started", show=False),
    ]

    def compose(self) -> ComposeResult:
        body = Text()
        body.append("This finds neurons in your recording, in 3 steps:\n\n")
        body.append("  1. Explore", style="bold"); body.append("  – see your data\n", style="dim")
        body.append("  2. Sort", style="bold");    body.append("     – detect neurons\n", style="dim")
        body.append("  3. Report", style="bold");  body.append("   – view results\n\n", style="dim")
        body.append("Put your recording files in this folder ", style="")
        body.append("(press d for help, f to pick a different folder).", style="dim")
        with Vertical(id="dialog"):
            yield Static(_crest_text(ui.SHIELD_FULL), id="wcrest")
            yield Static("Welcome to the Spike Sorter", id="wtitle")
            yield Static(body)
            yield Static("[ Get started ]  ·  Enter", id="wfoot")

    def action_start(self) -> None:
        self.dismiss(None)


class ProbeSetupScreen(ModalScreen):
    """One-time first-run probe confirmation. The active default is highlighted;
    keep it (Esc), pick another profile, or open the manager."""

    DEFAULT_CSS = """
    ProbeSetupScreen { align: center middle; }
    ProbeSetupScreen > #dialog {
        width: 72; max-width: 94%; height: auto;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ProbeSetupScreen #pstitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    ProbeSetupScreen #psblurb { color: $text-muted; padding: 0 0 1 0; }
    ProbeSetupScreen OptionList { height: auto; max-height: 14; background: $surface; border: none; }
    ProbeSetupScreen #psfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [Binding("escape", "skip", "Skip")]

    def __init__(self, controller, accent: str):
        super().__init__()
        self._c = controller
        self._accent = accent

    def compose(self) -> ComposeResult:
        active = self._c.active_probe
        self._active_idx = 0
        opts = []
        for n, row in enumerate(r for r in self._c.probe_catalog() if r.get("builtin")):
            is_active = row["name"] == active
            t = Text("▌ " if is_active else "  ", style=self._accent if is_active else "")
            t.append(row["label"], style="bold" if is_active else "")
            t.append(f"   {row['summary']}", style="dim")
            if is_active:
                self._active_idx = n
            opts.append(Option(t, id=f"probe:{row['name']}"))
        opts.append(Option(Text("Manage probes…", style="bold"), id="__manage__"))
        opts.append(Option(Text("Keep this probe (change any time with 'p')", style="dim"),
                           id="__skip__"))
        info = self._c.active_probe_info()
        with Vertical(id="dialog"):
            yield Static("Your probe geometry", id="pstitle")
            yield Static(f"Active probe: {info['label']}. Keep it, pick another, or open the "
                         "manager — you can change it any time with 'p'.", id="psblurb")
            yield NavList(*opts, id="pslist")
            yield Static("Enter to choose · Esc to keep", id="psfoot")

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        ol.focus()
        ol.highlighted = getattr(self, "_active_idx", 0)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        oid = event.option.id or "__skip__"
        if oid.startswith("probe:"):
            self._c.set_active_probe(oid.split(":", 1)[1])
            self.dismiss("set")
        elif oid == "__manage__":
            self.dismiss("manage")
        else:
            self.dismiss(None)

    def action_skip(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen):
    """Interactive Help: a topic list (left) ↔ scrollable content (right). Absorbs
    the old data-setup checklist as the 'Data files' topic."""

    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    HelpScreen > #dialog {
        width: 90; max-width: 96%; height: 90%; max-height: 34;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    HelpScreen #htitle { text-style: bold; color: $accentcolor; height: 1; }
    HelpScreen #hrow { height: 1fr; }
    HelpScreen #htopics { width: 24; height: 1fr; border: round #3a3f47; }
    HelpScreen #hscroll { width: 1fr; height: 1fr; padding: 0 1; }
    HelpScreen #helpbody { height: auto; }
    HelpScreen #hfoot { color: $text-muted; height: 1; padding: 1 0 0 0; }
    HelpScreen.stacked #hrow { layout: vertical; }
    HelpScreen.stacked #htopics { width: 1fr; height: auto; max-height: 30%; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close", show=False),
    ]

    def __init__(self, controller, accent: str, topic: str = "overview"):
        super().__init__()
        self._c = controller
        self._accent = accent
        self._topic = topic

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Help", id="htitle")
            with Horizontal(id="hrow"):
                topics = NavList(
                    *[Option(title, id=key) for key, title, _body in ui.HELP_TOPICS],
                    id="htopics")
                yield topics
                with VerticalScroll(id="hscroll"):
                    yield Static(id="helpbody")
            yield Static("↑/↓ choose topic · Esc to close", id="hfoot")

    def on_mount(self) -> None:
        topics = self.query_one("#htopics", OptionList)
        start = next((n for n, (k, _t, _b) in enumerate(ui.HELP_TOPICS) if k == self._topic), 0)
        topics.highlighted = start
        topics.focus()
        self._show(self._topic)
        self._relayout()

    def on_resize(self, event) -> None:
        self._relayout(event.size)

    def _relayout(self, size=None) -> None:
        size = size if size is not None else self.size
        self.set_class(size.width < STACK_COLS, "stacked")

    def _show(self, key: str) -> None:
        title, lines = next(((t, b) for k, t, b in ui.HELP_TOPICS if k == key),
                            ("Help", []))
        if key == "data":
            body = _setup_body(self._c.data_report, self._accent, self._c.pipeline)
        elif key == "about":
            # The Pitt shield lives here (and on Welcome): the dashboard's top
            # crest is now the wordmark, so the shield still has a home here.
            body = _crest_text(ui.SHIELD_COMPACT)
            body.append("\n\n")
            body.append(title + "\n\n", style=f"bold {self._accent}")
            for ln in lines:
                body.append(ln + "\n")
        else:
            body = Text()
            body.append(title + "\n\n", style=f"bold {self._accent}")
            for ln in lines:
                body.append(ln + "\n")
        self.query_one("#helpbody", Static).update(body)

    def action_close(self) -> None:
        self.dismiss(None)


def _setup_body(report: dict, accent: str, pipeline=None) -> Text:
    """Render the present/missing checklist + where the files belong.

    ``pipeline`` (the controller's sorter-independent status rows) is optional: when
    given, each present file gets its per-stream channels/rate/duration detail
    appended (relocated here from the removed dashboard pipeline panel)."""
    t = Text()
    detail = ui.stream_detail(report.get("files", []), pipeline)
    data_dir = report.get("data_dir", "")
    base = report.get("base")
    files = report.get("files", [])
    complete = bool(files) and all(f.get("present") for f in files)
    missing = [f["ext"] for f in files if not f.get("present")]
    if report.get("present") and complete:
        t.append("A complete file set was found", style="bold #3fb950")
        t.append(f" in {data_dir}\n", style="dim")
        t.append("Base name: ", style="dim")
        t.append(f"{base}\n\n", style=f"bold {accent}")
    elif report.get("present") and missing:
        t.append("Incomplete recording set", style="bold #e3a008")
        t.append(f" in {data_dir}", style="dim")
        t.append(f"  (missing {', '.join(missing)})\n", style="#e3a008")
        t.append("Base name: ", style="dim")
        t.append(f"{base}\n\n", style=f"bold {accent}")
    else:
        t.append("No recording found", style="bold #f85149")
        t.append(f" in {data_dir}\n\n", style="dim")
    t.append("Expected files", style=f"bold {accent}")
    t.append("  (one file set sharing a base name):\n")
    name = base or "<RECORDING_NAME>"
    for f in report.get("files", []):
        ok = f.get("present")
        glyph, gstyle = ("✓", "bold #3fb950") if ok else ("✗", "bold #f85149")
        t.append(f"  {glyph} ", style=gstyle)
        t.append(f"{name}{f['ext']}".ljust(34))
        t.append(f"{f['label']}\n", style="dim")
        info = detail.get(f["ext"])
        if info:                                   # ch/rate/duration for a loaded stream
            t.append(f"      {info}\n", style="dim")
    t.append("\nWhere to put them\n", style=f"bold {accent}")
    t.append(f"  Drop the file set into:  ")
    t.append(f"{data_dir}\n", style="bold")
    t.append("  (or launch with ", style="dim")
    t.append("--data-dir /path/to/recording", style="bold")
    t.append(" to point elsewhere).\n", style="dim")
    t.append(
        "\nThe raw .nev / .ns1–.ns6 files are git-ignored (the .ns5 exceeds GitHub's\n"
        "100 MB limit), so a fresh clone has none — copy your own set in.\n",
        style="dim",
    )
    err = report.get("error")
    if err:
        t.append("\nLoader said: ", style="dim")
        t.append(err + "\n", style="italic #f85149")
    return t


# --------------------------------------------------------------------------- #
# Responsive Pitt shield
# --------------------------------------------------------------------------- #
def _crest_text(rows) -> Text:
    """Build a Text from built crest rows (each row = a list of (style, seg)).
    Works for both the wordmark (multi-fragment rows) and the blue+gold
    shield (one fragment/row)."""
    t = Text()
    for n, line in enumerate(rows):
        if n:
            t.append("\n")
        for style, seg in line:
            t.append(seg, style=style or None)
    return t


class CrestWidget(Static):
    """The dashboard's static block-letter "SPIKE" wordmark. ``fit(cols, rows)``
    picks the largest tier that fits the live window (and hides the widget when
    none fits). Painted once, in the live accent colour; re-fit on resize/theme."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._tier = None

    def fit(self, cols: int, rows: int, reserve: int = SHIELD_RESERVE) -> None:
        tier = ui.pick_wordmark(cols - 4, rows, reserve=reserve)
        self.display = bool(tier)
        self._tier = tier or None
        self._repaint()

    def _tier_fragments(self):
        """Flat list of the current (style, segment) fragments — a test seam and
        the source for _repaint."""
        if self._tier is None:
            return []
        accent = getattr(self.app, "_accent", "")
        return [frag for row in ui.wordmark_rows(self._tier, accent) for frag in row]

    # NB: deliberately NOT named ``_render`` — that collides with Textual's
    # ``Widget._render`` (the layout engine calls it expecting a Visual).
    def _repaint(self) -> None:
        if self._tier is None:
            return
        accent = getattr(self.app, "_accent", "")
        self.update(_crest_text(ui.wordmark_rows(self._tier, accent)))


# --------------------------------------------------------------------------- #
# Main application
# --------------------------------------------------------------------------- #
# Group order + vocabulary for the sorter picker. Empty groups are omitted.
_GROUP_ORDER = ["ready", "docker", "gpu", "unavailable"]
_GROUP_LABEL = {
    "ready": "READY TO USE",
    "docker": "DOCKER SORTERS (heavier)",
    "gpu": "NEEDS A GPU",
    "unavailable": "NOT AVAILABLE",
}
# Plain-language "why is this sorter here" reason per group.
_GROUP_REASON = {
    "ready": "Ready to run",
    "docker": "Runs via Docker (~1 GB)",
    "gpu": "Needs an NVIDIA GPU",
    "unavailable": "Not installed here",
}
# Semantic colour per readiness tier (degrades to bold text under NO_COLOR).
_GROUP_COLOR = {
    "ready": "#3fb950",         # green  — go
    "docker": "#d29922",        # amber  — works, but heavier
    "gpu": "#f0883e",           # orange — needs hardware you don't have
    "unavailable": "#6e7681",   # grey   — not an option here
}


class SorterPickerScreen(ModalScreen):
    """The sorter picker (D5): sorters are chosen once per session, so the list
    lives behind ``t`` instead of owning half the main screen.

    A filter Input (focused on open — typing filters live) over the grouped
    list; the GPU and not-available groups start collapsed (Enter on their
    header expands; a filter match auto-expands). ↑/↓ move the highlight from
    the filter box, Enter selects and closes (the app routes the choice through
    its normal activate/download/enable flows), Esc closes. A one-line footer
    describes the highlighted sorter — the old INSPECTING prose, one line."""

    DEFAULT_CSS = """
    SorterPickerScreen { align: center middle; }
    SorterPickerScreen > #pickdialog {
        width: 74; max-width: 96%; height: auto; max-height: 80%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    SorterPickerScreen #pickfilter { margin: 0 0 1 0; border: round #3a3f47; }
    SorterPickerScreen #pickfilter:focus { border: round $accentcolor; }
    SorterPickerScreen #picklist { height: auto; max-height: 18; border: none; }
    SorterPickerScreen #pickdesc { height: auto; color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Close", show=False),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
        Binding("enter", "choose", "Choose", show=False, priority=True),
    ]

    def __init__(self, controller, accent: str):
        super().__init__()
        self._c = controller
        self._accent = accent
        self._expanded: set = set()        # gpu/unavailable start collapsed
        self._last_filter = ""             # detects filter changes (highlight policy)

    def compose(self) -> ComposeResult:
        with Vertical(id="pickdialog"):
            yield Input(placeholder="filter sorters…", id="pickfilter")
            yield NavList(id="picklist")
            yield Static("", id="pickdesc")

    def on_mount(self) -> None:
        self.query_one("#pickdialog").border_title = "SORTERS"
        self.query_one("#pickdialog").border_subtitle = "↑/↓ move · Enter choose · Esc close"
        # The list is driven from the filter box — it never takes focus itself.
        self.query_one("#picklist", NavList).can_focus = False
        self._rebuild()
        self.query_one("#pickfilter", Input).focus()

    def _filter(self) -> str:
        try:
            return self.query_one("#pickfilter", Input).value.strip().lower()
        except Exception:  # noqa: BLE001 - during mount
            return ""

    def _row_text(self, info: dict) -> Text:
        active = info.get("active", False)
        runnable = info.get("runnable", False)
        t = Text()
        t.append("▌ " if active else "  ", style=self._accent if active else "")
        t.append(info["name"], style="bold" if active else ("" if runnable else ui.SECONDARY))
        t.append(f"  {info['units']}u" if info.get("present") else "  —",
                 style=ui.SECONDARY if info.get("present") else "dim")
        needs_pull = info.get("group") == "docker" and not info.get("img_present")
        if info.get("downloading") is not None:
            t.append(f"  ⬇ {info['downloading']}%", style=self._accent)
        elif runnable and not needs_pull:
            t.append("  ●", style="#3fb950")
        elif info.get("group") == "docker":
            t.append("  ◌", style=ui.DL_GET_COLOUR)
        else:
            t.append("  –", style="dim")
        return t

    def _rebuild(self) -> None:
        ol = self.query_one("#picklist", NavList)
        keep = ol.highlighted
        ol.clear_options()
        flt = self._filter()
        ol.add_option(Option(self._docker_row_text(), id="__docker__"))
        by_group: dict = {}
        for info in self._c.infos:
            by_group.setdefault(info.get("group", "unavailable"), []).append(info)
        for group in _GROUP_ORDER:
            members = by_group.get(group)
            if not members:
                continue
            if flt:
                members = [m for m in members if flt in m["name"].lower()]
                if not members:
                    continue
            collapsed = (group in ("gpu", "unavailable")
                         and group not in self._expanded and not flt)
            label = _GROUP_LABEL[group]
            suffix = f"  ({len(members)}) — Enter to expand" if collapsed else ""
            ol.add_option(Option(
                Text(label + suffix,
                     style=f"bold {_GROUP_COLOR[group]}" if not collapsed
                     else f"dim {_GROUP_COLOR[group]}"),
                id=f"__grp_{group}__", disabled=not collapsed))
            if collapsed:
                continue
            for info in members:
                ol.add_option(Option(self._row_text(info), id=info["name"]))
        # Cursor policy (D5 review F2): a CHANGED filter must re-target Enter at a
        # matching SORTER row — a stale index silently landing on the Docker toggle
        # made Enter flip Docker instead of choosing the filtered sorter. Otherwise
        # keep position; a fresh build lands on the active sorter; the toggle row
        # is only ever the last resort.
        def _first_sorter_row():
            return next((i for i in range(ol.option_count)
                         if not str(ol.get_option_at_index(i).id or "").startswith("__")),
                        None)
        filter_changed = flt != self._last_filter
        self._last_filter = flt
        if filter_changed:
            ol.highlighted = (_first_sorter_row()
                              if _first_sorter_row() is not None else 0)
        elif keep is not None and keep < ol.option_count:
            ol.highlighted = keep
        else:
            active_row = next((i for i in range(ol.option_count)
                               if (self._c.infos[self._c.active_idx]["name"]
                                   == ol.get_option_at_index(i).id)), None)
            if active_row is not None:
                ol.highlighted = active_row
            else:
                ol.highlighted = (_first_sorter_row()
                                  if _first_sorter_row() is not None else 0)
        self._render_desc()

    def _docker_row_text(self) -> Text:
        on = getattr(self._c, "use_docker", False)
        t = Text()
        t.append("[x] " if on else "[ ] ", style=f"bold {self._accent}" if on else "dim")
        t.append("Docker sorters: ", style=ui.SECONDARY)
        t.append("on" if on else "off", style=f"bold {self._accent}" if on else "dim")
        return t

    def on_input_changed(self, event) -> None:
        if getattr(event.input, "id", "") == "pickfilter":
            self._rebuild()

    def action_move(self, delta: int) -> None:
        ol = self.query_one("#picklist", NavList)
        if ol.option_count == 0:
            return
        i = ol.highlighted if ol.highlighted is not None else 0
        for _ in range(ol.option_count):
            i = (i + delta) % ol.option_count
            if not ol.get_option_at_index(i).disabled:
                break
        ol.highlighted = i
        self._render_desc()

    def _render_desc(self) -> None:
        ol = self.query_one("#picklist", NavList)
        desc = self.query_one("#pickdesc", Static)
        oid = (ol.get_option_at_index(ol.highlighted).id
               if ol.highlighted is not None and ol.option_count else None)
        flt = self._filter()
        if flt and not any(not str(ol.get_option_at_index(i).id or "").startswith("__")
                           for i in range(ol.option_count)):
            desc.update(Text(f"no sorters match ‹{flt}›", style="#d29922"))
            return
        if oid == "__docker__":
            desc.update(Text("Enter toggles Docker — runs not-installed CPU sorters "
                             "via containers", style="dim"))
            return
        if oid and oid.startswith("__grp_"):
            g = oid[6:-2]
            desc.update(Text(_GROUP_REASON.get(g, ""), style="dim"))
            return
        info = next((i for i in self._c.infos if i["name"] == oid), None)
        if info is None:
            desc.update("")
            return
        t = Text()
        first = (info.get("description") or _GROUP_REASON.get(info.get("group"), ""))
        t.append(first.split(". ")[0].rstrip(".") + ".", style="dim")
        fit = (info.get("fit") or {}).get("rank")
        if fit == "good":
            t.append("  ✓ fits this probe", style="#3fb950")
        elif fit == "poor":
            t.append("  △ weak fit here", style="#d29922")
        desc.update(t)

    def on_option_list_option_highlighted(self, event) -> None:
        self._render_desc()

    def action_choose(self) -> None:
        ol = self.query_one("#picklist", NavList)
        if ol.highlighted is None or ol.option_count == 0:
            return
        oid = ol.get_option_at_index(ol.highlighted).id
        if oid and oid.startswith("__grp_"):
            self._expanded.add(oid[6:-2])
            self._rebuild()
            # Land INSIDE the group just opened (F6), not on its now-disabled header.
            for i in range(ol.option_count):
                cand = ol.get_option_at_index(i)
                if not str(cand.id or "").startswith("__") and not cand.disabled:
                    if i > 0 and str(ol.get_option_at_index(i - 1).id or ""
                                     ) == f"__grp_{oid[6:-2]}__":
                        ol.highlighted = i
                        break
            self._render_desc()
            return
        if oid == "__docker__" and self._filter() and not any(
                not str(ol.get_option_at_index(i).id or "").startswith("__")
                for i in range(ol.option_count)):
            return                         # zero-match filter: Enter must not toggle (F3)
        self.dismiss(oid)                  # sorter name or "__docker__"

    def action_cancel(self) -> None:
        self.dismiss(None)


class SpikeMenuApp(App):
    """The resident dashboard (D5, actions-first). One instance per session; the
    numbered actions are the primary panel, the sorter list lives behind the
    ``t`` picker, and a results section appears once a saved sort exists."""

    CSS = """
    Screen { background: $background; }

    /* D6 (the airy dashboard): NO boxed panels — sections are whitespace +
       hairline rules. The blank-line air lives in these margins and collapses
       (the Screen-level .dense class) BEFORE any content yields. */
    #crest { height: auto; content-align: center top; padding: 1 0 0 0; }
    #titlebar { height: 1; content-align: left middle; }

    /* Always-on banner: one row for the INPUTS (DATA + PROBE), one for the
       workbench STATE (the active sorter), one dim context sentence. Fixed at
       one row each so the crest reserve never shifts between quiet/loud text. */
    #databar { height: 1; margin: 1 2 0 2; }
    #sortbar { height: 1; margin: 0 2 0 2; }
    #contextbar { height: 1; margin: 0 2 1 2; color: $text-muted; }
    #databar.collapsed, #sortbar.collapsed, #titlebar.collapsed,
    #contextbar.collapsed { display: none; }
    .dense #databar { margin: 0 2 0 2; }

    /* In-UI download indicator: a one-row banner-area line shown only while a
       download is live (or just finished, briefly). Hidden otherwise. */
    #dlbar { height: 1; margin: 0 2 0 2; color: $accentcolor; }
    #dlbar.hidden { display: none; }

    #body { height: 1fr; padding: 0 2 0 2; layout: vertical; }

    /* ACTIONS: the primary section — a hairline-ruled label over a borderless
       full-width list. Focus shows on the highlighted row, not on chrome. */
    #actionshead { height: 1; margin: 0 0 1 0; }
    #actionshead.collapsed { display: none; }
    #actionpane { width: 1fr; height: 1fr; min-height: 3; border: none; padding: 0 1; }
    #actions { height: 1fr; border: none; }
    OptionList:focus { border: none; }

    OptionList:focus > .option-list--option-highlighted {
        background: $accentcolor 25%; color: $foreground; text-style: none;
    }
    OptionList > .option-list--option-highlighted {
        background: transparent; text-style: underline;
    }

    /* RESULTS — present only when the active sorter has a saved sort: a hairline
       label + name line + one metrics line. Borderless; air above. */
    #results { height: auto; padding: 0 0; margin: 1 2 0 2; }
    #results.hidden, #results.collapsed { display: none; }
    .dense #results { margin: 0 2 0 2; }

    /* LAST RESULT — the newest action outcome, persistent until the next one
       (results must not evaporate on a keystroke, DESIGN_UX §1). */
    #resultbar { height: 1; margin: 0 2; }
    #resultbar.hidden, #resultbar.collapsed { display: none; }

    /* Pinned to the bottom at a fixed 2 rows (transient status + the merged
       manage/help key line) so a long line can never wrap and steal body rows. */
    #footer { dock: bottom; height: 2; padding: 0 2; }
    """

    BINDINGS = [
        # D5: the sorter list lives behind the picker — `t` opens it (the SORT
        # banner carries the dim "t change" hint).
        Binding("t", "pick_sorter", "Change sorter", show=False),
        Binding("w", "watch_download", "Download", show=False),
        # x manages the ACTIVE sorter (delete image / clear saved sort) — there is
        # no highlighted sorter row on the main screen any more.
        Binding("x", "manage_active", "Manage active sorter", show=False),
        # MANAGE letter keys: housekeeping runs by letter, numbers stay with the
        # six WORKFLOW actions.
        Binding("p", "probe", "Probe", show=False),
        Binding("e", "run_key('params')", "Edit parameters", show=False),
        Binding("m", "run_key('manage')", "Manage sorters", show=False),
        Binding("c", "run_key('theme')", "Colour theme", show=False),
        Binding("v", "run_key('verify')", "Verify install", show=False),
        Binding("r", "reopen_last", "Reopen last result", show=False),
        Binding("d", "data_help", "Data files", show=False),
        Binding("f", "choose_folder", "Data folder", show=False),
        Binding("question_mark", "help", "Help", show=False),
        Binding("q", "quit", "Quit", show=False),
        # NOTE: Esc is deliberately NOT bound to quit — a reflexive "go back" press
        # should never hard-exit the dashboard and lose the user's place. Modals
        # keep their own Esc=cancel; q / Ctrl-C still quit the app.
        Binding("ctrl+c", "quit", "Quit", show=False),
        # number-key jump: 1..6 -> the WORKFLOW actions (the first six table rows).
        *[Binding(str(n), f"run_index({n - 1})", show=False) for n in range(1, 7)],
    ]

    def __init__(self, controller: Controller):
        # Set before super().__init__(): App.__init__ builds the stylesheet, which
        # calls get_css_variables() -> reads self._accent.
        self.c = controller
        self._accent = controller.accent
        self._last = None
        self._download = None          # the single live DownloadSession (or None)
        super().__init__()

    # -- CSS variable plumbing: $accentcolor follows the live theme ----------- #
    def get_css_variables(self) -> dict:
        v = super().get_css_variables()
        v["accentcolor"] = self._accent
        return v

    # -- layout --------------------------------------------------------------- #
    def compose(self) -> ComposeResult:
        yield CrestWidget(id="crest")
        yield Static(id="titlebar")
        yield Static(id="databar")
        yield Static(id="sortbar")
        yield Static(id="contextbar")
        yield Static(id="dlbar")
        with Vertical(id="body"):
            yield Static(id="actionshead")
            with Vertical(id="actionpane"):
                yield NavList(id="actions")
        yield Static(id="results")
        yield Static(id="resultbar")
        yield Static(id="footer")

    def on_mount(self) -> None:
        self._refresh_action_title()
        self._rebuild_actions()
        self._render_results()
        # The actions ARE the screen (D5) — first-time users land on what to do.
        self.query_one("#actions", OptionList).focus()
        self._refresh_footer()
        self._relayout()
        if getattr(self.c, "want_welcome", False):
            self.push_screen(WelcomeScreen(), self._after_welcome)
        elif getattr(self.c, "want_probe_setup", False):
            self.push_screen(ProbeSetupScreen(self.c, self._accent), self._after_probe_setup)

    def _after_welcome(self, _result) -> None:
        self.c.mark_welcome_seen()
        if getattr(self.c, "want_probe_setup", False):
            self.push_screen(ProbeSetupScreen(self.c, self._accent), self._after_probe_setup)

    def _after_probe_setup(self, result) -> None:
        self.c.mark_probe_setup_seen()
        if result == "manage":
            self._open_probes()
        self._render_databar(self.size.width)
        self._render_results()

    def on_resize(self, event) -> None:
        # self.size lags during a resize event; event.size carries the new size.
        self._relayout(event.size)

    def _relayout(self, size=None) -> None:
        size = size if size is not None else self.size
        w, h = size.width, size.height
        self._render_databar(w)
        self._render_sortbar(w)
        self._render_contextbar(w)
        self._render_dlbar(w)
        self._render_actionshead(w)
        self._render_results_text(w)   # the RESULTS rule tracks the live width
        # Yield order (§1, D6): the blank-line AIR and the context/section chrome
        # collapse first (dense), then the crest (tall terminals only anyway),
        # then RESULTS, then (tiny) everything but the actions + footer.
        tiny = h < self.TINY_ROWS
        dense = h < self.AIR_ROWS
        for wid in ("#titlebar", "#databar", "#sortbar", "#resultbar", "#results"):
            self.query_one(wid).set_class(tiny, "collapsed")
        # air-adjacent chrome yields at dense, BEFORE any content shrinks
        for wid in ("#contextbar", "#actionshead"):
            self.query_one(wid).set_class(tiny or dense, "collapsed")
        # The DASHBOARD's screen, never self.screen: a resize under a modal must
        # not stamp the air tier onto the modal and leave the base screen stale
        # (D6 review #2 — that clipped the sixth action after Esc).
        self.query_one("#body").screen.set_class(dense and not tiny, "dense")
        self.query_one("#body").set_class(tiny, "tiny")
        # ---- the yield budget (arithmetic, never hand-tuned) --------------------
        # non-tiny fixed rows: footer 2 · title 1 · databar 1(+1 air) · sortbar 1
        # · contextbar 1+1 (air tier only) · actionshead 1+1 (air tier only)
        dl_rows = 1 if getattr(self, "_download", None) is not None else 0
        result_rows = 0 if tiny else (1 if getattr(self.c, "last_result", None) else 0)
        has_results = (not tiny) and bool(
            self.c.infos[self.c.active_idx].get("present"))
        if tiny:
            fixed, body_min = 2 + dl_rows, 3
        elif dense:
            fixed, body_min = 5 + dl_rows + result_rows, 7
        else:
            fixed, body_min = 10 + dl_rows + result_rows, 7
        results_rows = (3 if dense else 4) if has_results else 0  # head+2 content(+air)
        # RESULTS yields before the action list: hide it when the budget is tight.
        if has_results and h - fixed - results_rows < body_min:
            has_results = False
            results_rows = 0
        self.query_one("#results").set_class(not has_results, "hidden")
        reserve = fixed + results_rows + body_min
        # D6: the crest is a tall-terminal luxury, never a mid-size squeeze.
        tall = h >= self.TALL_ROWS
        self.query_one("#crest", CrestWidget).fit(w, h if tall else 0, reserve)
        self.query_one("#titlebar", Static).update(self._render_titlerule(w))
        self._refresh_footer(w)

    STACK_COLS = STACK_COLS
        # Below TINY the title + banner + results collapse so the actions still fit;
        # below AIR the blank-line air + context/section chrome collapse (before any
        # content); at/above TALL the crest is allowed back (D6: tall terminals only).
    TINY_ROWS = 14
    AIR_ROWS = 30
    TALL_ROWS = 34

    # -- the always-on DATA / SORT banner ------------------------------------- #
    def _render_databar(self, width: int) -> None:
        """The INPUTS row — DATA and PROBE share one line (DESIGN_UX §2: both are
        verified inputs; the workbench state gets its own row). The quiet path is
        'DATA ✓ all 3 streams · PROBE <label> ✓' — the label carries ch/pitch, so
        the probe is stated ONCE (D6, §1.1); a loud data problem (missing /
        incomplete / unreadable broadband) takes the whole row — the probe half
        yields to the thing that needs attention."""
        dr = self.c.data_report
        files = dr.get("files", [])
        complete = bool(files) and all(f.get("present") for f in files)
        bb = next((r for r in self.c.pipeline if "Broadband" in r.get("stage", "")), None)
        unreadable = complete and bb is not None and bb.get("status") == "FAIL"
        t = Text()
        t.append("DATA  ", style=ui.SECONDARY)
        if dr.get("present") and complete and not unreadable:
            loaded = [f for f in files if f.get("present")]
            t.append("✓ ", style="#3fb950")
            t.append(f"all {len(loaded)} streams", style=ui.PRIMARY)
            # The probe half — one glance answers "which geometry am I sorting with?"
            # A MISMATCH is correctness-relevant (wrong geometry feeds the sort), so
            # it goes loud and LEADS the probe half — label/summary are dropped so
            # the warning can never be the part the ellipsis eats (D1 review #3).
            pinfo = self.c.probe_info
            match = pinfo.get("match", "")
            if match == "mismatch":
                t.append("      PROBE  ", style=ui.SECONDARY)
                t.append("✗ channel count mismatch", style="bold #f0883e")
                t.append(" — p to fix", style="#f0883e")
            else:
                t.append("      PROBE  ", style=ui.SECONDARY)
                # ONE probe summary (D6, §1.1): the label already says what it is
                # (ch/pitch live in it) — never restated by a second summary here.
                t.append(pinfo.get("label", pinfo.get("name", "unknown probe")),
                         style=f"bold {self._accent}")
                if match in ("fits", "auto"):
                    t.append(" ✓", style="#3fb950")
        elif not dr.get("present"):
            t.append("✗ no recording in ", style="bold #f0883e")
            t.append(f"{dr.get('data_dir', '.')} ", style="#f0883e")
            t.append("— press f to choose · d for help", style="dim")
        elif unreadable:
            t.append("✗ Broadband (.ns5) won't load ", style="bold #f0883e")
            t.append("— press d for help", style="dim")
        else:
            missing = ", ".join(f["ext"] for f in files if not f.get("present"))
            t.append(f"✗ incomplete set — missing {missing} ", style="bold #f0883e")
            t.append("· press f / d", style="dim")
        t.truncate(max(1, width - 2), overflow="ellipsis")
        self.query_one("#databar", Static).update(t)

    def _render_sortbar(self, width: int) -> None:
        """The SORT row: the active sorter (★ if recommended), its saved-units/duration
        (or 'not sorted yet'), its readiness, and any custom-param count."""
        info = self.c.infos[self.c.active_idx]
        t = Text()
        t.append("SORT  ", style=ui.SECONDARY)
        if info.get("recommended"):
            t.append("★ ", style=f"bold {self._accent}")
        t.append(info["name"], style=f"bold {self._accent}")
        if info.get("present"):
            t.append(f" · {info['units']} units · {info['duration']:.0f} s saved",
                     style=ui.PRIMARY)
        else:
            t.append(" · not sorted yet", style="dim")
        if info.get("runnable"):
            ready = ("Ready to run (Docker)"
                     if self.c.use_docker and info.get("group") == "docker"
                     else "Ready to run")
        elif info.get("group") == "docker":
            ready = ("Docker image not downloaded — t to get it"
                     if not info.get("img_present") else "Turn on Docker sorters to run")
        elif info.get("group") == "gpu":
            ready = "Needs an NVIDIA GPU"
        else:
            ready = "Not installed here"
        t.append(f" · {ready}",
                 style="#3fb950" if info.get("runnable") else "#f0883e")
        n = info.get("overrides", 0)
        if n:
            t.append(f" · {n} custom params", style="dim")
        # The pressable "change" control (D6): a key chip + verb. Clicking the
        # SORT row opens the picker (on_click); the visible `t` chip IS the
        # degradation path on mouse-less terminals.
        t.append("   ")
        t.append(" t ", style="reverse dim")
        t.append(" change", style="dim")
        t.truncate(max(1, width - 2), overflow="ellipsis")
        self.query_one("#sortbar", Static).update(t)

    def _render_contextbar(self, width: int) -> None:
        """One dim context sentence under SORT (D6): what the active sorter is +
        how it fits the active probe. Never green — §1.5 reserves green for
        verified results, and this is description, not verification."""
        info = self.c.infos[self.c.active_idx]
        desc = (info.get("description") or "").strip().rstrip(".")
        fit = (info.get("fit") or {}).get("reason", "").strip().rstrip(".")
        t = Text()
        if desc:
            t.append(desc, style="dim")
        if desc and fit:
            t.append("  —  ", style="dim")
        if fit:
            t.append(fit, style="dim")
        t.truncate(max(1, width - 2), overflow="ellipsis")
        self.query_one("#contextbar", Static).update(t)

    def _section_rule(self, label: str, avail: int) -> Text:
        """The D6 section language: a small dim-bold label with a hairline rule
        filling exactly ``avail`` content columns — whitespace + hairline, never
        a box, and never a wrapped-away rule (D6 review #1)."""
        # no_wrap: a Rich Text renderable wraps by Rich's rules (Textual's
        # text-wrap doesn't reach it) — any residual overlength must CLIP, never
        # wrap the rule out of a 1-row widget.
        t = Text(no_wrap=True)
        t.append(label + " ", style=f"bold {ui.SECONDARY}")
        t.append("─" * max(0, avail - len(label) - 1), style=_BORDER_DIM)
        return t

    # Rule widths: the widget's content_region is the truth once laid out, but it
    # is STALE mid-resize (relayout runs on the event, before the layout pass) —
    # so the live event width caps it (#actionshead paints at width-8 in the
    # current CSS, #results at width-4). A rule capped a frame short self-heals
    # on the next relayout; a rule a frame long would wrap out of the 1-row clip.
    def _render_actionshead(self, width: int) -> None:
        head = self.query_one("#actionshead", Static)
        avail = head.content_region.width or max(10, width - 8)
        avail = min(avail, max(10, width - 8))
        head.update(self._section_rule("ACTIONS", avail))

    def on_click(self, event) -> None:
        # The SORT row (and its context sentence) is a pressable control: a click
        # anywhere on it opens the sorter picker — same action as the `t` chip.
        if getattr(event.widget, "id", None) in ("sortbar", "contextbar"):
            self.action_pick_sorter()

    def _render_dlbar(self, width: int) -> None:
        """The collapsed download indicator. Hidden when no session; while live shows
        '⬇ <name>  NN%  <speed>  ETA m:ss   [w expand]'; on finish a transient
        '✓ <name> ready' / '✗ …' until _clear_download hides it."""
        bar = self.query_one("#dlbar", Static)
        sess = getattr(self, "_download", None)
        if sess is None:
            bar.add_class("hidden")
            bar.update("")
            return
        bar.remove_class("hidden")
        t = Text()
        if sess.result is not None:
            ok, msg = sess.result
            if sess.cancelled or _is_cancel_msg(msg):
                # Benign: a cancel reads as neutral, not a failure.
                t.append("⊘ ", style="bold #8b949e")
                t.append(f"{sess.name} cancelled", style="#8b949e")
            else:
                t.append(("✓ " if ok else "✗ "),
                         style="bold " + ("#3fb950" if ok else "#f85149"))
                t.append(f"{sess.name} {'ready' if ok else 'failed'}",
                         style="#3fb950" if ok else "#f85149")
        else:
            st = sess.stats
            t.append("⬇ ", style=self._accent)
            t.append(f"{sess.name}  ", style="bold")
            # Speed/ETA only when we have real bytes; otherwise just the percent
            # (the extract / cached phases have no byte rate to quote).
            if getattr(sess, "has_bytes", False) and sess.bytes_total:
                t.append(f"{st.pct:d}%  {dlstats.fmt_speed(st.speed)}  "
                         f"ETA {dlstats.fmt_clock(st.eta)}", style="dim")
            elif st.eta is not None:
                t.append(f"{st.pct:d}%  ~ETA {dlstats.fmt_clock(st.eta)}", style="dim")
            else:
                t.append(f"{st.pct:d}%", style="dim")
            t.append("   [w expand]", style="#6e7681")
        bar.update(t)

    def _render_results(self) -> None:
        """State-change entry point: repaint RESULTS, then re-run the layout
        budget (the text itself is also repainted by _relayout on every resize,
        via _render_results_text, so the hairline rule tracks the live width)."""
        self._render_results_text()
        self._relayout()

    def _render_results_text(self, width: int | None = None) -> None:
        """RESULTS: shown only when the active sorter has a saved sort — a
        hairline label + name line + one metrics line. No prose, no recursion."""
        panel = self.query_one("#results", Static)
        info = self.c.infos[self.c.active_idx]
        if not info.get("present"):
            panel.add_class("hidden")
            panel.update("")
            return
        panel.remove_class("hidden")
        width = width if width is not None else self.size.width
        # The live width wins over content_region (stale mid-resize): margin 2+2,
        # zero padding -> width-4.
        avail = min(panel.content_region.width or 10_000, max(10, width - 4))
        t = self._section_rule("RESULTS", avail)
        t.append("\n")
        t.append(info["name"], style=f"bold {self._accent}")
        t.append(f" · {info['units']} units · {info['duration']:.0f} s sorted\n",
                 style=ui.PRIMARY)
        summary = info.get("summary")
        if summary:
            row = _ss.headline_row(summary)
            t.append("V_pp " + row["V_pp"] + " · SNR " + row["SNR"]
                     + " · noise " + row["noise floor"]
                     + " · yield " + row["yield (% active electrodes)"],
                     style=ui.SECONDARY)
        else:
            t.append("metrics not computed for this sort", style="dim")
        panel.update(t)

    def _refresh_action_title(self) -> None:
        # D6: the section head (hairline rule) carries the plain "ACTIONS" label —
        # the active sorter's one at-rest home stays the SORT banner (§1.1).
        self._render_actionshead(self.size.width)

    # -- rendering helpers ---------------------------------------------------- #
    def _render_titlerule(self, width: int) -> Text:
        """A centred title rule: ── University of Pittsburgh · SpikeInterface ──.
        Falls back to a shorter header (then a bare truncation) on narrow windows
        so the title never clips mid-word."""
        header = next((c for c in (self.c.header, "Pitt · SpikeInterface", "SpikeInterface")
                       if len(c) + 4 <= width), None)
        if header is None:
            return Text(_trunc("SpikeInterface", max(1, width)), style=f"bold {self._accent}")
        avail = width - len(header) - 4
        left, right = avail // 2, avail - avail // 2
        return (Text("─" * left + " ", style=_BORDER_DIM)
                + Text(header, style=f"bold {self._accent}")
                + Text(" " + "─" * right, style=_BORDER_DIM))

    # MANAGE rows run by letter (DESIGN_UX §2); this map is the row-prefix AND the
    # binding contract (`?`/`q` are app-level keys shown for completeness).
    _MANAGE_KEYS = {"params": "e", "manage": "m", "probe": "p", "verify": "v",
                    "theme": "c", "help": "?", "quit": "q"}

    def _workflow_actions(self) -> list[dict]:
        return [a for a in self.c.actions if a.get("section", "workflow") == "workflow"]

    def _rebuild_actions(self) -> None:
        """The six WORKFLOW actions, full width, each with its one-line description
        (D5). The MANAGE housekeeping is NOT in the list — it runs by letter key,
        shown on the footer's merged key line (D6)."""
        ol = self.query_one("#actions", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        present = self.c.data_report.get("present")
        first_enabled = None
        for n, a in enumerate(self._workflow_actions()):
            disabled = bool(a.get("needs_data")) and not present
            if not disabled and first_enabled is None:
                first_enabled = ol.option_count
            ol.add_option(Option(self._action_text(a, disabled, n),
                                 id=a["key"], disabled=disabled))
        ol.highlighted = keep if (keep is not None and keep < ol.option_count) else first_enabled

    def _action_text(self, a: dict, disabled: bool, index: int) -> Text:
        t = Text()
        # D6: the jump-key is an inverse-video chip — a visibly pressable
        # affordance at every width (the footer hint drops on narrow terminals).
        t.append(f" {index + 1} ", style="reverse dim" if disabled else "reverse")
        t.append("  ")
        t.append(a["title"], style="dim" if disabled else "bold")
        if a.get("hint"):
            t.append(f"   {a['hint']}", style="dim")
        if disabled:
            t.append("   (needs data)", style="italic #f0883e")
        return t


    def _refresh_footer(self, width: int | None = None, focus: str | None = None) -> None:
        """Footer: a transient-status line + the key hints. The active sorter is NOT
        echoed here (DESIGN_UX §1 one-fact-one-place — the SORT banner is its home);
        durable results live on the LAST RESULT line, repainted alongside."""
        width = width if width is not None else self.size.width
        line1 = Text()
        if self._last:
            line1.append(self._last if isinstance(self._last, Text) else Text(str(self._last)))
        line2 = Text(self._footer_hint(width, focus), style="dim")
        cap = max(1, width - 2)
        line1.truncate(cap, overflow="ellipsis")
        line2.truncate(cap, overflow="ellipsis")
        self.query_one("#footer", Static).update(line1 + Text("\n") + line2)
        self._render_resultbar(width)

    def _render_resultbar(self, width: int | None = None) -> None:
        """The LAST RESULT line: newest action outcome + artifact + reopen key."""
        width = width if width is not None else self.size.width
        bar = self.query_one("#resultbar", Static)
        lr = getattr(self.c, "last_result", None)
        if not lr:
            bar.add_class("hidden")
            bar.update("")
            return
        bar.remove_class("hidden")
        ok = lr.get("ok")
        t = Text()
        t.append("LAST  ", style=ui.SECONDARY)
        t.append("✓ " if ok else "✗ ", style="bold " + ("#3fb950" if ok else "#f85149"))
        t.append(str(lr.get("key", "")), style=ui.PRIMARY)
        if lr.get("when"):
            t.append(f" · {_fmt_when(lr['when'])}", style="dim")
        path = lr.get("path")
        if path:
            t.append(f" → {path}", style=ui.SECONDARY)
            if str(path).endswith(".html"):
                t.append("   r reopen", style="dim")
        t.truncate(max(1, width - 2), overflow="ellipsis")
        bar.update(t)

    def _footer_hint(self, width: int, focus: str | None = None) -> str:
        """Width-adaptive key line — D6 merges the MANAGE keys and help into this
        ONE bottom line (the old separate managebar row became air)."""
        if width >= 110:
            return ("↑/↓ ↵ · 1-6 run · t sorter · e params · m sorters · p probe · "
                    "v verify · r reopen · d data · ? help · q quit")
        if width >= 100:
            return ("↑/↓ ↵ · 1-6 run · t sorter · e params · m sorters · p probe · "
                    "r reopen · ? help · q quit")
        if width >= 72:
            return "↵ run · 1-6 · t sorter · e params · m sorters · p probe · ? help · q quit"
        if width >= 48:
            return "↵ · 1-6 · t sorter · m · p · ? help · q quit"
        return "↑↓ run · t · ? · q"

    def action_manage_active(self) -> None:
        """``x``: manage the ACTIVE sorter — a small confirm offering only the
        applicable destructive ops (delete its cached Docker image, clear its
        saved sort). If neither applies, a footer hint instead of an empty modal.
        (Per-row management for OTHER sorters lives in the m Manage hub.)"""
        info = self.c.infos[self.c.active_idx]
        name = info["name"]
        opts: list[tuple[str, str]] = []
        if info.get("img_present"):
            size = (info.get("img_size") or 0) / 1e9
            label = (f"Delete downloaded image (~{size:.1f} GB)" if size
                     else "Delete downloaded image")
            opts.append(("del_image", label))
        if info.get("present"):
            opts.append(("clear_sort", f"Clear saved sort ({info['units']}u)"))
        if not opts:
            self._last = Text(f"nothing to delete for {name}", style="dim")
            self._refresh_footer()
            return
        self.push_screen(ManageSorterScreen(name, opts, self._accent),
                         lambda choice: self._do_manage(name, choice))

    def _do_manage(self, name: str, choice) -> None:
        """Apply the per-sorter manage choice, then reload + re-render the sidebar,
        SORT banner, and INSPECTING panel so the deleted state shows at once."""
        if choice == "del_image":
            ok, msg = self.c.delete_image(name)
        elif choice == "clear_sort":
            ok, msg = self.c.clear_saved_sort(name)
        else:
            return                          # cancelled
        self._last = Text(msg, style=_result_style(ok, msg))
        try:
            self.c.reload()
            self._render_results()
            self._rebuild_actions()
        except Exception as e:  # noqa: BLE001 - a reload failure must not kill the app
            self._last = Text(f"reload after manage failed: {e!r}", style="#f85149")
        self._render_sortbar(self.size.width)
        self._refresh_footer()

    def action_probe(self) -> None:
        self._open_probes()

    def _open_probes(self) -> None:
        self.push_screen(ProbeManagerScreen(self.c, self._accent), self._after_probes)

    def _after_probes(self, _result) -> None:
        try:
            self.c.reload()
            self._render_results()
            self._rebuild_actions()
        except Exception as e:  # noqa: BLE001
            self._last = Text(f"reload after probe change failed: {e!r}", style="#f85149")
        self._render_sortbar(self.size.width)
        self._render_databar(self.size.width)
        self._refresh_footer()

    def action_pick_sorter(self) -> None:
        """``t``: the sorter picker (D5) — filter, choose, done."""
        self.push_screen(SorterPickerScreen(self.c, self._accent), self._after_pick)

    def _after_pick(self, choice) -> None:
        if choice is None:
            return
        if choice == "__docker__":
            self._toggle_docker()
            return
        # Route through the normal decision table: activate / download / enable.
        self._select_sorter(choice)

    def action_data_help(self) -> None:
        self.push_screen(HelpScreen(self.c, self._accent, topic="data"))

    def action_choose_folder(self) -> None:
        self.push_screen(DataFolderScreen(self.c.data_report.get("data_dir")),
                         self._after_choose_folder)

    def _after_choose_folder(self, result) -> None:
        if result is None:
            return                                  # cancelled
        found = self.c.set_data_dir(result or None)
        self._render_results()
        self._rebuild_actions()
        self._last = (Text("Data folder updated ✓", style="bold #3fb950") if found
                      else Text("⚠ No recording found in that folder", style="#f0883e"))
        self._refresh_footer()
        self._relayout()

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self.c, self._accent, topic="overview"))

    def action_run_index(self, i: int) -> None:
        """1-6 jump-run WORKFLOW action ``i``. Both lists are always visible, so just
        move focus to the actions list, highlight row ``i`` (the workflow rows are the
        list's first rows), and run it. MANAGE actions have letter keys instead."""
        workflow = self._workflow_actions()
        if not (0 <= i < len(workflow)):
            return
        ol = self.query_one("#actions", OptionList)
        ol.focus()
        if i < ol.option_count:
            ol.highlighted = i                 # fires the highlight -> renders INSPECTING
        self._activate_action(workflow[i]["key"])

    def action_run_key(self, key: str) -> None:
        """A MANAGE letter key (D5: manage actions live on the dim line, not in
        the list) — run it directly."""
        self._activate_action(key)

    def action_reopen_last(self) -> None:
        """``r``: reopen the LAST RESULT's artifact (report/comparison/explore page)."""
        ok, msg = self.c.reopen_last()
        self._last = Text(msg, style=(f"bold {self._accent}" if ok else "dim"))
        self._refresh_footer()

    def _set_active_by_name(self, name: str) -> bool:
        if self.c.set_active_by_name(name):
            self._render_results()
            self._render_sortbar(self.size.width)
            self._refresh_action_title()
            self._refresh_footer()
            return True
        return False

    # -- list selection ------------------------------------------------------- #
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list is self.query_one("#actions", OptionList):
            self._activate_action(event.option.id)

    def _select_sorter(self, name: str) -> None:
        """Enter on a sorter row. Decision table:

          • Docker sorter whose image is NOT downloaded → if the Docker daemon is
            running, open the in-UI download (DownloadProgressScreen); otherwise
            offer to enable/start Docker first (DockerConfirmScreen).
          • Runnable sorter → activate it and advance to the ACTIONS pane.
          • Other Docker sorter (image present, but the Docker toggle is off) →
            offer to enable the Docker toggle.
          • GPU / unavailable → a footer hint (nothing to download).
        """
        info = next((i for i in self.c.infos if i["name"] == name), None)
        if info is None:
            return
        if info.get("group") == "docker" and not info.get("img_present"):
            # Download path — the image must be pulled before this can ever run, and
            # it needs the daemon up. Pulling is SEPARATE from running a sort.
            if self.c.docker_status(refresh=False).get("running"):
                self.start_download(name)
            else:
                self._toggle_docker(offer_from=name)   # get Docker running first
        elif info.get("runnable"):
            self._set_active_by_name(name)
        elif info.get("group") == "docker":
            # Image is cached but the Docker toggle is off — offer to enable it.
            self._toggle_docker(offer_from=name)
        else:
            hint = ("needs a GPU build installed — see Help" if info.get("group") == "gpu"
                    else "not available on this computer")
            self._last = Text(f"{name}: {hint}", style="#f0883e")
            self._refresh_footer()

    # -- in-UI Docker download (worker owned HERE so it survives a collapse) ---- #
    def start_download(self, name: str) -> None:
        """Begin pulling ``name``'s image in an App-owned worker and open the
        expanded view. Refuses a second concurrent download with a footer hint."""
        if getattr(self, "_download", None) is not None and self._download.result is None:
            self._last = Text("a download is already running · w to view",
                              style="#f0883e")
            self._refresh_footer()
            return
        sess = dlstats.DownloadSession(name=name, image="")
        sess.phase_caption = "starting…"
        sess.bytes_done = None
        sess.bytes_total = None
        sess.has_bytes = False         # True only once real byte progress arrives
        self._download = sess
        self._render_dlbar(self.size.width)
        self.run_worker(lambda: self._download_worker(sess), thread=True)
        self.push_screen(DownloadProgressScreen(self.c, name, self._accent),
                         self._after_download)

    def _download_worker(self, sess) -> None:
        def on_progress(done, total, is_bytes=True):
            self.call_from_thread(self._dl_progress, sess, done, total, is_bytes)

        def on_status(text):
            self.call_from_thread(self._dl_status, sess, text)

        def should_cancel():
            return sess.cancelled

        try:
            ok, msg = self.c.download_image(sess.name, on_progress, on_status,
                                            should_cancel=should_cancel)
        except Exception as e:  # noqa: BLE001 - never let a worker crash the app
            ok, msg = False, f"download failed: {e}"
        self.call_from_thread(self._dl_finish, sess, ok, msg)

    # -- thread-marshalled session mutations (only via call_from_thread) -------- #
    def _dl_progress(self, sess, done, total, is_bytes=True) -> None:
        # stats.update drives the bar percent + elapsed for both unit kinds. The rate
        # window must never mix bytes with layer-counts, so reset it when the unit
        # flips. Speed (B/s) is shown only for bytes; for the byte-less extract phase
        # the same window yields a *layers/sec* rate we turn into an estimated ETA.
        now = monotonic()
        if is_bytes != getattr(sess, "has_bytes", None):
            sess.stats.reset_window(now)
        sess.stats.update(done, total, now=now)
        sess.has_bytes = is_bytes
        sess.bytes_done, sess.bytes_total = (done, total) if is_bytes else (None, None)
        self._render_dlbar(self.size.width)

    def _dl_status(self, sess, text) -> None:
        sess.phase_caption = text
        word = text.split()[0] if text else ""
        new_phase = _DL_PHASE.get(word)
        if new_phase and new_phase != sess.phase:
            sess.phase = new_phase
            sess.stats.set_phase(new_phase, now=monotonic())
        self._render_dlbar(self.size.width)

    def _dl_finish(self, sess, ok, msg) -> None:
        sess.result = (ok, msg)
        # The catalog reload reflects the finished image regardless of which session
        # is current, so always do it.
        try:
            self.c.reload()
            self._render_results()
            self._rebuild_actions()
            reload_err = None
        except Exception as e:  # noqa: BLE001
            reload_err = f"reload after download failed: {e!r}"
        # A newer download may have superseded this one within its finish window —
        # don't let this stale finish repaint over the live session or schedule a
        # clear that would null the newer one.
        if self._download is not sess:
            return
        if reload_err is not None:
            self._last = Text(reload_err, style="#f85149")
        elif sess.cancelled or _is_cancel_msg(msg):
            self._last = Text(f"{sess.name} cancelled", style="dim")
        else:
            self._last = Text(msg, style=_result_style(ok, msg))
        self._render_sortbar(self.size.width)
        self._refresh_footer()
        # Show a transient ✓/✗/⊘ in the indicator, then clear the session + hide it.
        self._render_dlbar(self.size.width)
        self.set_timer(4.0, lambda: self._clear_download(sess))

    def _clear_download(self, sess) -> None:
        # Only clear if this is still the same finished session — a newer download
        # started within the 4s window must not be nulled out.
        if self._download is sess:
            self._download = None
            self._render_dlbar(self.size.width)

    def action_watch_download(self) -> None:
        """`w`: re-open the expanded view over the still-running download."""
        sess = getattr(self, "_download", None)
        if sess is None or sess.result is not None:
            self._last = Text("no download in progress", style="dim")
            self._refresh_footer()
            return
        if isinstance(self.screen, DownloadProgressScreen):
            return
        self.push_screen(DownloadProgressScreen(self.c, sess.name, self._accent),
                         self._after_download)

    def _after_download(self, result) -> None:
        """The expanded modal was dismissed (collapsed / cancelled / closed). The
        download worker is owned by the App and keeps running; the actual finish
        (catalog reload, badge flip) happens in ``_dl_finish``. Here we only echo a
        status so a collapse reads clearly."""
        if result == "collapsed":
            sess = getattr(self, "_download", None)
            # Only claim it's still downloading when it genuinely is — a cancelled or
            # already-finished session must not say "downloading".
            if sess is not None and sess.result is None and not sess.cancelled:
                self._last = Text(f"{sess.name} downloading · w to expand", style="dim")
        self._refresh_footer()

    def _toggle_docker(self, offer_from: str | None = None) -> None:
        if self.c.use_docker and offer_from is None:
            self._apply_docker_toggle()          # turning OFF is immediate
            return
        self.push_screen(DockerConfirmScreen(self.c, self._accent), self._after_docker_confirm)

    def _after_docker_confirm(self, result) -> None:
        if result != "enable":
            self._last = Text("Docker sorters unchanged", style="dim")
            self._refresh_footer()
            return
        if not self.c.use_docker:
            self._apply_docker_toggle()

    def _apply_docker_toggle(self) -> None:
        on = self.c.toggle_docker()
        self._render_results()
        self._rebuild_actions()
        if on:
            self._last = Text("Docker sorters on ✓ — pick one, then run a sort to use it",
                              style=f"bold {self._accent}")
        else:
            self._last = Text("Docker sorters off", style="dim")
        self._refresh_footer()
        self._relayout()

    def _activate_action(self, key: str) -> None:
        if key == "quit":
            self.exit()
        elif key == "theme":
            self._open_theme()
        elif key == "help":
            self.action_help()
        elif key == "params":
            self._open_params()
        elif key == "manage":
            self.push_screen(ManageSortersScreen(self.c, self._accent), self._after_manage)
        elif key == "probe":
            self._open_probes()
        elif key == "report" and self.c.data_report.get("present"):
            log_path = None
            try:
                log_path = self.c.report_log_path()
            except Exception:  # noqa: BLE001 - logging is best-effort
                log_path = None
            self.push_screen(
                BuildProgressScreen(self.c.report_command(), self._accent,
                                    noun="Report", log_path=log_path),
                self._after_report)
        elif self._needs_data(key) and not self.c.data_report.get("present"):
            # Guarded BEFORE the sort branch so sort can't open its modal with no data.
            self._last = Text("✗ ", style="bold #f85149") + Text(
                f"{key} needs the recording files — press d for help")
            self._refresh_footer()
        elif key == "sort":
            # Active sorter needs a container but Docker isn't running (e.g. it was
            # stopped after the sorter was picked) — guide instead of failing mid-sort.
            if self.c.active_blocked_on_docker():
                self._last = Text(
                    f"{self.c.active_sorter} runs in Docker, which isn't running. "
                    "Start Docker (t → the Docker row) or pick a READY sorter.",
                    style="#f0883e")
                self._refresh_footer()
                return
            info = self.c.infos[self.c.active_idx]
            note = None
            if info.get("present"):     # warn before silently replacing a saved sort
                note = (f"⚠ {info['name']} already has a saved sort "
                        f"({info['units']}u · {info['duration']:.0f}s) — running again replaces it.")
            exp = {}
            try:
                exp = self.c.sort_expectations() or {}
            except Exception:  # noqa: BLE001 - provenance is optional
                exp = {}
            hint = ""
            if exp.get("wall_seconds"):
                mm, ss = divmod(int(exp["wall_seconds"]), 60)
                hint = f"~{mm}:{ss:02d} last time"
            full_hint = hint if exp.get("span") == "full" else ""
            # A CLI --duration 100 run is neither of these choices — its wall time
            # must not decorate the 30 s row (D4 review F7): the quick hint only
            # attaches when the last cut actually WAS the quick span.
            eff = exp.get("eff_seconds")
            quick_ok = (exp.get("span") == "quick" and isinstance(eff, (int, float))
                        and abs(eff - self.c.quick_seconds) <= 2)
            quick_hint = hint if quick_ok else ""
            self.push_screen(
                ChoiceModal("Sort how much?", [
                    ("full", "Full recording", full_hint),
                    ("quick", f"Quick test — first {self.c.quick_seconds}s", quick_hint),
                ], note=note),
                self._after_sort_span,
            )
        elif key == "compare":
            self._open_compare_picker()
        else:
            self._run(key, None)

    def _needs_data(self, key: str) -> bool:
        return next((a.get("needs_data", False) for a in self.c.actions if a["key"] == key), False)

    def _after_sort_span(self, span: str | None) -> None:
        if span is None:
            self._last = Text("Sort cancelled", style="dim")
            self._refresh_footer()
        else:
            self._start_sort(span)

    def _start_sort(self, span: str) -> None:
        """Run the sort *in-UI* via SortProgressScreen instead of dropping to
        scrolling stdout: build the run_sorting.py argv (JSON-progress mode) and push
        the modal that spawns it and renders its progress events live."""
        argv = self.c.sort_command(span)
        log_path = self.c.sort_log_path(span)
        self.push_screen(SortProgressScreen(argv, self._accent, log_path), self._after_sort)

    def _after_sort(self, result) -> None:
        # The modal contract (DESIGN_UX §3): (ok, message, changed, next_action) —
        # next_action set when the result card chained into report/inspect.
        ok, message, changed, next_action = result or (False, "Sort cancelled", False, None)
        # Record real outcomes on the LAST RESULT line; a cancel is benign noise,
        # not a result (the modal ran nothing to completion).
        if result is not None and not _is_cancel_msg(message):
            self.c.record_result("sort", ok)
        self._last = Text(message, style=_result_style(ok, message))
        if changed:
            try:
                self.c.reload()
                self._render_results()
                self._rebuild_actions()
            except Exception as e:  # noqa: BLE001 - reload failure must not kill the app
                self._last = Text(f"reload after sort failed: {e!r}", style="#f85149")
        self._refresh_footer()
        self._relayout()
        self.refresh()
        if next_action:
            # Dispatch through the normal action path so its guards (needs_data,
            # Docker, the _self fresh-process route for gui) all apply.
            self._activate_action(next_action)

    def _after_report(self, res) -> None:
        ok, message = res or (False, "report build failed")
        cancelled = _is_cancel_msg(message)
        if not cancelled:
            self.c.record_result("report", ok)
        self._last = Text(message, style=_result_style(ok, message))
        self._refresh_footer()
        if ok:
            # The child never opens a browser; the LAST RESULT path is the opener.
            self.c.reopen_last()

    def _open_theme(self) -> None:
        opts = [(n, n, "(current)" if n == self.c.theme_name else "") for n in self.c.themes]
        self.push_screen(ChoiceModal("Accent colour  (saved for next time)", opts),
                         self._after_theme)

    def _after_theme(self, name: str | None) -> None:
        if not name:
            return
        self._accent = self.c.set_theme(name)
        self.refresh_css()
        self._render_results()
        self._rebuild_actions()
        self._render_databar(self.size.width)
        self._render_sortbar(self.size.width)
        self._relayout()                                  # repaint crest in new accent
        self._last = Text(f"Theme → {name}", style=f"bold {self._accent}")
        self._refresh_footer()

    def _open_params(self) -> None:
        sorter = self.c.active_sorter
        try:
            defaults = self.c.default_params(sorter)
            descs = self.c.param_descriptions(sorter)
        except Exception as e:  # noqa: BLE001 - introspection failure -> report, no crash
            self._last = Text(f"can't read {sorter} params: {e!r}", style="#f85149")
            self._refresh_footer()
            return
        overrides = self.c.get_overrides(sorter)
        self.push_screen(
            ParamEditorScreen(sorter, defaults, descs, overrides, self._accent),
            self._after_params,
        )

    def _after_params(self, result) -> None:
        if result is None:
            self._last = Text("Parameter edit cancelled", style="dim")
        else:
            sorter, overrides = result
            self.c.set_params(sorter, overrides)
            n = len(overrides)
            self._last = Text(
                f"{sorter}: {n} override{'s' if n != 1 else ''} saved" if n
                else f"{sorter}: parameters reset to defaults",
                style=f"bold {self._accent}")
        self._refresh_footer()

    def _after_manage(self, _result) -> None:
        """The Manage hub closed. It already mutated the controller + reloaded its
        own view; refresh the dashboard's sidebar, SORT banner, and INSPECTING panel
        so any deleted image / cleared sort shows on the main screen too."""
        try:
            self.c.reload()
            self._render_results()
            self._rebuild_actions()
        except Exception as e:  # noqa: BLE001 - a reload failure must not kill the app
            self._last = Text(f"reload after manage failed: {e!r}", style="#f85149")
        self._render_sortbar(self.size.width)
        self._refresh_footer()

    def _open_compare_picker(self) -> None:
        if self._needs_data("compare") and not self.c.data_report.get("present"):
            self._last = Text("✗ ", style="bold #f85149") + Text(
                "compare needs the recording files — press d for help")
            self._refresh_footer()
            return
        saved = self.c.saved_sorters()
        if len(saved) < 2:
            self._last = Text(
                "Need two saved sorts to compare — run 'sort' for two sorters first.",
                style="#f0883e")
            self._refresh_footer()
            return
        opts = [(s, s, "") for s in saved]
        self.push_screen(ChoiceModal("Compare which sorter?", opts), self._after_compare_first)

    def _after_compare_first(self, first) -> None:
        if first is None:
            self._last = Text("Compare cancelled", style="dim")
            self._refresh_footer()
            return
        self._compare_first = first
        rest = [(s, s, "") for s in self.c.saved_sorters() if s != first]
        self.push_screen(ChoiceModal(f"…compared against?  (vs {first})", rest),
                         self._after_compare_second)

    def _after_compare_second(self, second) -> None:
        if second is None:
            self._last = Text("Compare cancelled", style="dim")
            self._refresh_footer()
            return
        self._run_compare((self._compare_first, second))

    def _run_compare(self, pair) -> None:
        """Run the (blocking, in-process) compare in a thread worker behind an
        honest BusyScreen — named step, ticking elapsed, a stated no-cancel —
        instead of a silent suspend() (DESIGN_UX §6; the audit's quiet-terminal
        friction). Stdout is buffered so the controller's prints can't garble
        the live TUI; a failure surfaces the buffer's tail."""
        a, b = pair
        busy = BusyScreen(f"Comparing {a} vs {b}", self._accent,
                          "builds the agreement matrix — runs to completion "
                          "(no cancel)")
        self.push_screen(busy, self._after_compare_done)
        self.run_worker(lambda: self._compare_worker(pair, busy), thread=True)

    def _compare_worker(self, pair, busy) -> None:
        # NOTE: the redirect swaps the GLOBAL sys.stdout/stderr for the compare's
        # whole (minutes-long) window — Textual paints via its own driver handle so
        # the TUI is unaffected, but any other thread's prints land in this buffer
        # for the duration (D4 review F6, accepted with this note).
        import contextlib
        import io

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                res = self.c.run_compare(pair)
        except Exception as e:  # noqa: BLE001
            res = (False, f"compare failed: {e!r}", False)
        # The real controller CATCHES compare failures internally and warns into
        # the (redirected) buffer, returning a bare False — so the tail must be
        # surfaced on ANY failure, not only on an exception here (D4 review F1:
        # otherwise the cause exists nowhere, not even scrollback).
        if res and not res[0]:
            tail = [ln for ln in buf.getvalue().strip().splitlines() if ln.strip()][-2:]
            if tail:
                res = (res[0], f"{res[1]} · " + " / ".join(t[:120] for t in tail), res[2])
        self.call_from_thread(busy.finish, res)

    def _after_compare_done(self, res) -> None:
        ok, message, changed = res or (False, "compare failed", False)
        self._last = Text(message, style=_result_style(ok, message))
        if changed:
            try:
                self.c.reload()
                self._render_results()
                self._rebuild_actions()
            except Exception as e:  # noqa: BLE001
                self._last = Text(f"reload after compare failed: {e!r}", style="#f85149")
        self._refresh_footer()
        self._relayout()
        self.refresh()

    # -- the suspend-and-run path -------------------------------------------- #
    def _run(self, key: str, span: str | None) -> None:
        # Drop out of the alt-screen so the action's own stdout scrolls; if the
        # driver can't suspend (headless/unsupported), run in place rather than
        # crash. Any failure surfaces as a red 'last action' line — never a crash.
        try:
            with self.suspend():
                ok, message, changed = self.c.run(key, span)
        except SuspendNotSupported:
            ok, message, changed = self.c.run(key, span)
        except Exception as e:  # noqa: BLE001 - keep the app alive, report the failure
            ok, message, changed = False, f"{key} failed: {e!r}", False
        self._last = Text(message, style=_result_style(ok, message))
        try:
            if changed:
                self.c.reload()
                self._render_results()
                self._rebuild_actions()
        except Exception as e:  # noqa: BLE001 - a reload failure must not kill the app
            self._last = Text(f"reload after {key} failed: {e!r}", style="#f85149")
        self._refresh_footer()
        self._relayout()
        self.refresh()


def _fmt_when(when: str) -> str:
    """Format a LAST RESULT timestamp for display: today's read as a clock time,
    older ones carry their date — persisted results must not masquerade as fresh.
    A value that isn't ISO (or a pre-ISO record in an existing .si_menu.json) is
    shown as-is rather than dropped."""
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(when)
    except ValueError:
        return when
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%b %d %H:%M")


def _is_cancel_msg(message) -> bool:
    """A finish message that reads as a user cancellation, not a genuine failure."""
    return "cancel" in str(message).lower()


def _result_style(ok: bool, message) -> str:
    """Colour for a 'last action' line: red on failure, amber for a succeeded-but-
    check-this outcome (message starts with '⚠', e.g. a sort that found 0 units),
    green otherwise."""
    if not ok:
        return "#f85149"
    return "#f0883e" if str(message).lstrip().startswith("⚠") else "#3fb950"


def _trunc(text: str, n: int) -> str:
    return text if len(text) <= n else text[: max(0, n - 1)] + "…"



def _param_to_str(value) -> str:
    """Render a scalar/None default for an Input field ('' for None)."""
    if value is None:
        return ""
    return str(value)
