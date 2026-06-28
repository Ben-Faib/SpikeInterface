"""Textual front-door dashboard for SpikeInterface_Menu.py (terminal UI v2).

A single, resident full-screen app that stays usable at any window size — from a
wide desktop terminal down to a short VS Code pane. It is a *view*: all heavy
loading and the actual running of actions live in a small ``Controller`` (built
in ``SpikeInterface_Menu.py``) that this app calls back into. That keeps the app
import-light (no SpikeInterface at import time) and unit-testable with Textual's
``run_test`` / ``Pilot`` harness.

The dashboard is a **simultaneous three-panel layout**. SORTERS (#sorterpane) and
ACTIONS (#actionpane) sit side-by-side and are *both always visible*; a bottom
**INSPECTING** panel (#inspect) describes whichever pane currently has focus (the
highlighted sorter's blurb, or the highlighted action's explanation). An always-on
two-line banner sits above the panes: a DATA line (#databar) naming the loaded
streams (or a loud ✗ problem line) and a SORT line (#sortbar) naming the active
sorter and its readiness.

Layout (responsive):

    ┌ neuron crest (collapses full→compact→mini→hidden as height shrinks)┐
    │ ── University of Pittsburgh · SpikeInterface ── (#titlebar)         │
    │ DATA  ✓ LFP  ✓ Broadband  ✓ .nev   all 3 streams loaded (#databar)  │
    │ SORT  ★ tridesclous2 · 13 units saved · Ready to run     (#sortbar)  │
    │ ┌ SORTERS (#sorterpane) ───────────┬ ACTIONS — on tridesclous2 ───┐ │
    │ │ ▌ ★ tridesclous2  13u ACTIVE      │ 1  Explore raw data           │ │
    │ │   spykingcircus2  8u              │ 2  Run / re-run sorting        │ │
    │ │ …                                 │ …                              │ │
    │ └───────────────────────────────────┴────────────────────────────────┘ │
    │ ┌ INSPECTING ▸ tridesclous2 ─ <highlighted row's blurb> ───────────┐ │
    │ └───────────────────────────────────────────────────────────────────┘ │
    │ ↑/↓ choose · Enter activate · →/1-9 Actions · t · d · ? · q quit    │
    └─────────────────────────────────────────────────────────────────────┘

Navigation: ←/→ (or Tab/Shift-Tab) move *focus* between the two always-visible
panes (the focused pane gets the heavy accent border; the bottom INSPECTING panel
re-renders for the now-focused pane). ↑/↓ (or j/k) move within the focused list.
Enter on a runnable sorter activates it (the SORT banner + ACTIONS title follow);
Enter on an action runs it (the app drops out via ``suspend()`` so the action's own
output scrolls normally, then resumes). 1-9 jump-run an action (focus moves to the
actions list first). ``t`` cycles the active sorter, ``x`` manages the highlighted
sorter (Stage 5), ``d`` opens the data-files help, ``q`` quits.

The accent colour is themeable (driven into the ``$accentcolor`` CSS variable);
the Pitt blue+gold shield is fixed. Both lists scroll, so the active sorter and
the actions are always reachable even when the body is taller than the screen.
"""
from __future__ import annotations

import asyncio
from typing import Protocol

from rich.text import Text
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

import sort_progress as _sp  # pure JSON progress protocol (no SI / Textual deps)
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
# changes when the banner switches between its quiet ✓ and loud ✗ text.
BANNER_ROWS = 2
# Rows the crest must leave for title + banner + footer + a usable body, so it
# drops full→compact→mini→hidden well before it would crowd the menu off a short
# window. (The neuron ladder itself is 7 / 5 / 3 rows tall — see ui._NEURONS.)
# Tuned so the big crest is deferential: it only claims the full tier on a tall
# (≈40+ row) terminal, dropping to the compact crest on the common 34–40 row window
# so the panes get the vertical room they need to read.
SHIELD_RESERVE = 24
# Unfocused panel border colour (focus uses the live accent).
_BORDER_DIM = "#3a3f47"

# Crest animation: a slow, subtle receive->fire->rest loop. ~6 fps over a ~6 s
# cycle; most of the cycle is the (memoised) rest frame, so idle cost is ~nil.
_CREST_FPS = 6
_CREST_CYCLE_S = 6.0


# --------------------------------------------------------------------------- #
# Controller contract (implemented by SpikeInterface_Menu.MenuController)
# --------------------------------------------------------------------------- #
class Controller(Protocol):
    """What the app needs from its host. Attributes are read every render."""

    header: str
    sorters: list[str]                  # sorter names, in tab order
    themes: dict[str, str]              # name -> accent hex
    actions: list[dict]                 # {key,title,hint,needs_data}
    active_idx: int
    accent: str                         # current accent hex
    theme_name: str
    quick_seconds: int                  # span for the "quick" sort modal choice
    pipeline: list[dict]                # {stage,status,detail} (sorter-independent)
    infos: list[dict]                   # full catalog: {name,group,status,runnable,
                                        # recommended,description,present,units,
                                        # duration,active}
    data_report: dict                   # see SpikeInterface_Menu._data_report
    use_docker: bool
    animate: bool                       # crest animation on/off (persisted)
    want_welcome: bool
    active_probe: str
    want_probe_setup: bool
    probe_info: dict                    # {name,label,summary,layout,density_class,match,match_detail}

    def set_active_by_name(self, name: str) -> bool: ...
    def cycle_active(self) -> None: ...
    def set_theme(self, name: str) -> str: ...      # returns the new accent hex
    def set_animate(self, on: bool) -> bool: ...    # persist + return the new state
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
    ParamEditorScreen #perror { color: #f85149; height: auto; }
    ParamEditorScreen #pfoot { color: $text-muted; height: 1; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+r", "reset", "Reset"),
    ]

    def __init__(self, sorter, defaults, descs, overrides, accent):
        super().__init__()
        self._sorter = sorter
        self._defaults = defaults
        self._descs = descs or {}
        self._overrides = overrides or {}
        self._accent = accent
        self._widgets: dict = {}  # key -> (kind, widget)

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"Parameters · {self._sorter}", id="ptitle")
            with VerticalScroll(id="pscroll"):
                for key, default in self._defaults.items():
                    cur = self._overrides.get(key, default)
                    with Vertical(classes="prow"):
                        yield Label(key, classes="pname")
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
    ]

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, argv: list, accent: str):
        super().__init__()
        self._argv = list(argv)
        self._accent = accent
        self._state = _sp.new_state()
        self._proc = None
        self._spin = 0

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
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:  # noqa: BLE001 - bad argv / no python -> friendly error
            self.handle_event({"t": "error", "ok": False,
                               "message": f"couldn't start sort: {e}"})
            return
        if self._proc.stdout is not None:
            async for raw in self._proc.stdout:
                ev = _sp.parse_line(raw.decode("utf-8", "replace"))
                if ev:
                    self.handle_event(ev)
        await self._proc.wait()
        if self._state["done"] is None:
            # The process ended without emitting done/error (e.g. argv was a plain
            # 'true' in tests, or a hard crash) — synthesise a friendly close state.
            rc = self._proc.returncode
            if rc == 0:
                self.handle_event({"t": "done", "ok": True, "units": "?", "out": ""})
            else:
                self.handle_event({"t": "error", "ok": False,
                                   "message": f"sort exited ({rc}) without finishing"})

    def handle_event(self, ev: dict) -> None:
        """Synchronous: fold one event into the state and re-render. Safe to call
        from the reader worker or directly from a test."""
        _sp.reduce(self._state, ev)
        self._repaint()
        if self._state["done"] is not None:
            self.query_one("#sortfoot", Static).update("Press Enter to close")

    def _tick_spinner(self) -> None:
        # The heartbeat ("still working") line carries the live spinner glyph; it can
        # now coexist with a bar/substep/detail, so animate whenever it will show.
        s = self._state
        if s["done"] is None and s["heartbeat"]:
            self._spin = (self._spin + 1) % len(self._SPINNER)
            self._repaint()

    # NB: deliberately NOT named ``_render`` — that collides with Textual's
    # ``Widget._render`` (the layout engine calls it expecting a Visual).
    def _repaint(self) -> None:
        s = self._state
        t = Text()
        for p in s["phases"]:
            done = p["done"]
            t.append("✓ " if done else "▶ ",
                     style="#3fb950" if done else f"bold {self._accent}")
            t.append(f"{p['title']}\n", style="" if done else "bold")
        # Live detail for the current phase — substep, latest sorter step line, the
        # determinate bar, and the heartbeat all stack (whichever apply). They're
        # cleared on each new phase by the reducer, so this only ever shows the
        # running phase's progress.
        if s["done"] is None:
            if s.get("substep_name"):
                t.append(f"  → {s['substep_name']} "
                         f"({s['substep_i']}/{s['substep_n']})\n",
                         style=f"bold {self._accent}")
            if s.get("detail"):
                t.append(f"  → {s['detail']}\n", style="dim")
        bar = s["bar"]
        if bar and bar.get("total"):
            frac = bar.get("frac") or 0.0
            fill = int(frac * 24)
            t.append(f"  {bar.get('desc', '')} ", style="dim")
            t.append("█" * fill + "░" * (24 - fill), style=self._accent)
            t.append(f"  {frac * 100:3.0f}%\n", style="dim")
        if s["heartbeat"] and s["done"] is None:
            spin = self._SPINNER[self._spin]
            t.append(f"  {spin} {s['heartbeat']} … still working "
                     f"({s['heartbeat_secs']}s)\n", style="dim")
        if s["done"]:
            d = s["done"]
            if d.get("ok"):
                units = d.get("units", "?")
                out = d.get("out", "")
                line = f"\n✓ Done · {units} units"
                if out:
                    line += f" → {out}"
                t.append(line + "\n", style="bold #3fb950")
            else:
                t.append(f"\n✗ {d.get('message', 'sort failed')}\n", style="bold #f85149")
        self.query_one("#sortbody", Static).update(t)

    def action_cancel(self) -> None:
        # Kill the whole process group so SpikeInterface's worker children die too.
        if self._proc is not None and self._proc.returncode is None:
            import os
            import signal
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except Exception:  # noqa: BLE001 - already gone / no group -> ignore
                pass
        self.dismiss((False, "Sort cancelled", False))

    def action_close_if_done(self) -> None:
        if self._state["done"] is None:
            return                                  # still running — Enter is a no-op
        d = self._state["done"]
        ok = bool(d.get("ok"))
        if ok:
            units = d.get("units", "")
            msg = f"✓ Sorted {units} units".rstrip()
        else:
            msg = f"✗ {d.get('message', 'sort failed')}"
        # Only an OK sort changed the saved-sort universe (cancel/error did not).
        self.dismiss((ok, msg, ok))


class DownloadProgressScreen(ModalScreen):
    """Pulls a sorter's Docker image in-UI, separate from running a sort.

    The Textual app never imports the Docker SDK or SpikeInterface; the actual
    ``docker pull`` happens inside ``MenuController.download_image`` (the registry
    hook), which we run in a **worker thread** (``run_worker(self._pull,
    thread=True)``) so the event loop never blocks. The SDK's ``on_progress`` /
    ``on_status`` callbacks fire on that thread, so every UI touch is marshalled
    back with ``self.app.call_from_thread(...)``.

    ``on_status`` now emits only a phase+count string ("Downloading N/M layers" /
    "Verifying…" / "Extracting N/M layers" / "Done"), and ``on_progress`` aggregates
    correctly over all layers of the current phase. So the layout is: the phase
    string is a **label above** a determinate bar (the aggregate %), with a **spinner**
    next to the label that ticks on a ``set_interval`` (~6 fps) while the pull is live
    — so indeterminate stretches (Waiting / Verifying, which emit no progress) still
    read as alive. On finish a ✓/✗ line shows, the spinner stops, and Esc/Enter close
    (returning the ``(ok, message)`` result to ``_after_download``)."""

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
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
    ]

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, controller, name: str, accent: str):
        super().__init__()
        self._c = controller
        self._name = name
        self._accent = accent
        self._pct = 0
        # The phase string from on_status ("Downloading N/M layers" / "Verifying…" /
        # "Extracting N/M layers" / "Done") — never a raw per-layer status. It is the
        # label drawn ABOVE the bar.
        self._status = "starting…"
        self._done = None              # (ok, message) once the pull finishes
        self._spin = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="dldialog"):
            yield Static(f"Downloading {self._name}", id="dltitle")
            yield Static("", id="dlbody")
            yield Static("This runs once (~1 GB). Esc to close.", id="dlfoot")

    def on_mount(self) -> None:
        self.query_one("#dldialog").border_title = "DOWNLOAD"
        self._repaint()
        # A slow spinner tick keeps the status line visibly alive even while the pull
        # is in an indeterminate stretch (Waiting / Verifying emit no progress). Cheap
        # — it stops the moment the pull finishes / the screen unmounts.
        self._spin_timer = self.set_interval(1.0 / 6, self._tick_spinner)
        # The pull blocks (network + disk); run it OFF the event loop. The two
        # callbacks fire on this worker thread, so they hop back via call_from_thread.
        self.run_worker(self._pull, thread=True, exclusive=True)

    def on_unmount(self) -> None:
        self._stop_spinner()

    def _stop_spinner(self) -> None:
        timer = getattr(self, "_spin_timer", None)
        if timer is not None:
            timer.stop()
            self._spin_timer = None

    def _tick_spinner(self) -> None:
        # Only animate while the pull is live — once done the ✓/✗ line is the cue.
        if self._done is not None:
            return
        self._spin = (self._spin + 1) % len(self._SPINNER)
        self._repaint()

    def _pull(self) -> None:
        def on_progress(done, total):
            pct = int(done / total * 100) if total else 0
            self.app.call_from_thread(self._set_pct, pct)

        def on_status(text):
            self.app.call_from_thread(self._set_status, text)

        try:
            ok, msg = self._c.download_image(self._name, on_progress, on_status)
        except Exception as e:  # noqa: BLE001 - never let a worker crash kill the app
            ok, msg = False, f"download failed: {e}"
        self.app.call_from_thread(self._finish, ok, msg)

    # -- thread-marshalled UI updates (only ever called via call_from_thread) -- #
    def _set_pct(self, pct: int) -> None:
        self._pct = pct
        self._repaint()

    def _set_status(self, text: str) -> None:
        self._status = text
        self._repaint()

    def _finish(self, ok: bool, msg: str) -> None:
        self._done = (ok, msg)
        if ok:
            self._pct = 100
        self._stop_spinner()           # no live spinner once the ✓/✗ line shows
        self._repaint()
        self.query_one("#dlfoot", Static).update("Press Enter to close")

    # NB: NOT named ``_render`` — that collides with Textual's Widget._render.
    def _repaint(self) -> None:
        t = Text()
        # Phase string (from on_status) ABOVE the bar, with a live spinner alongside
        # so an indeterminate stretch (Waiting / Verifying) clearly reads as alive.
        if self._done is None:
            t.append(self._SPINNER[self._spin] + " ", style=self._accent)
        t.append(self._status + "\n", style="dim")
        fill = int(self._pct / 100 * 24)
        t.append("█" * fill + "░" * (24 - fill), style=self._accent)
        t.append(f"  {self._pct:3d}%\n", style="dim")
        if self._done is not None:
            ok, msg = self._done
            t.append(("✓ " if ok else "✗ ") + msg,
                     style="bold " + ("#3fb950" if ok else "#f85149"))
        self.query_one("#dlbody", Static).update(t)

    def action_close(self) -> None:
        # Before the pull finishes, Esc/Enter close with a not-done sentinel so the
        # caller doesn't treat an interrupted view as a completed download.
        self.dismiss(self._done or (False, "download still running", False))


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
            yield OptionList(id="hublist")
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

    # -- the highlighted sorter ----------------------------------------------- #
    def _highlighted_info(self) -> "dict | None":
        ol = self.query_one("#hublist", OptionList)
        if ol.highlighted is None:
            return None
        oid = ol.get_option_at_index(ol.highlighted).id
        if not oid or str(oid).startswith("__grp_"):
            return None
        return next((i for i in self._c.infos if i["name"] == oid), None)

    def _highlight_by_name(self, name: str) -> bool:
        """Move the hub cursor onto a sorter row by name (used by the keyboard flow
        + tests)."""
        ol = self.query_one("#hublist", OptionList)
        for i in range(ol.option_count):
            if ol.get_option_at_index(i).id == name:
                ol.highlighted = i
                return True
        return False

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

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id:
            self._show(event.option.id)

    def _show(self, key: str) -> None:
        title, lines = next(((t, b) for k, t, b in ui.HELP_TOPICS if k == key),
                            ("Help", []))
        if key == "data":
            body = _setup_body(self._c.data_report, self._accent, self._c.pipeline)
        elif key == "about":
            # The Pitt shield lives here (and on Welcome): the dashboard's top
            # crest is now the firing neuron, so the shield still has a home here.
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
    Works for both the firing neuron (multi-fragment rows) and the blue+gold
    shield (one fragment/row)."""
    t = Text()
    for n, line in enumerate(rows):
        if n:
            t.append("\n")
        for style, seg in line:
            t.append(seg, style=style or None)
    return t


class CrestWidget(Static):
    """The dashboard's animated firing-neuron crest. ``fit(cols, rows)`` picks the
    largest tier that fits the live window (and hides the widget when even mini
    won't). A slow timer walks ``phase`` (receive -> fire -> rest); identical rest
    frames are memoised away. Honours the controller's ``animate`` flag."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._tier = None
        self._phase = 0.0
        self._animate = True
        self._last = None
        self._timer = None

    def on_mount(self) -> None:
        self._animate = bool(getattr(self.app.c, "animate", True))
        self._timer = self.set_interval(
            1.0 / _CREST_FPS, self._tick, pause=not self._animate
        )

    def fit(self, cols: int, rows: int, reserve: int = SHIELD_RESERVE) -> None:
        tier = ui.pick_neuron(cols - 4, rows, reserve=reserve)
        self.display = bool(tier)
        self._tier = tier or None
        self._repaint()

    def set_animate(self, on: bool) -> None:
        self._animate = bool(on)
        if self._timer is not None:
            self._timer.resume() if on else self._timer.pause()
        if not on:
            self._phase = 0.0
        self._repaint()

    def _tick(self) -> None:
        if not self._animate or not self.display or self._tier is None:
            return
        self._phase = (self._phase + 1.0 / (_CREST_FPS * _CREST_CYCLE_S)) % 1.0
        self._repaint()

    # NB: deliberately NOT named ``_render`` — that collides with Textual's
    # ``Widget._render`` (the layout engine calls it expecting a Visual).
    def _repaint(self) -> None:
        if self._tier is None:
            return
        phase = self._phase if self._animate else ui.NEURON_REST_PHASE
        rows = ui.neuron_frame(self._tier, phase)
        if rows != self._last:
            self._last = rows
            self.update(_crest_text(rows))


# --------------------------------------------------------------------------- #
# Main application
# --------------------------------------------------------------------------- #
class SpikeMenuApp(App):
    """The resident dashboard. One instance per session; actions run via
    ``suspend()`` and the app re-renders from the controller afterwards."""

    CSS = """
    Screen { background: $background; }

    #crest { height: auto; content-align: center top; padding: 1 0 0 0; }
    #titlebar { height: 1; content-align: left middle; }

    /* Always-on two-line banner (replaces statusline + activebar): a DATA row
       naming the loaded streams (or a loud ✗ problem line) and a SORT row naming
       the active sorter + its readiness. Fixed at one row each so the crest reserve
       never shifts when the banner switches between its quiet/loud text. */
    #databar { height: 1; margin: 1 2 0 2; }
    #sortbar { height: 1; margin: 0 2 0 2; }
    #probebar { height: 1; margin: 0 2 1 2; }
    /* On an extreme-short window the banner + title yield their rows to the lists
       (the DATA/SORT info still lives in the d Help topic + the footer). */
    #databar.collapsed, #sortbar.collapsed, #titlebar.collapsed, #probebar.collapsed { display: none; }

    #body { height: 1fr; padding: 1 1 0 1; }
    #body.stacked { layout: vertical; }

    /* SORTERS and ACTIONS are co-equal and BOTH always shown (no accordion). The
       low min-height (border + one content row) lets BOTH panes keep a visible row
       when stacked on a short window — the lists scroll rather than clip. */
    #sorterpane, #actionpane { width: 1fr; height: 1fr; min-height: 3;
        border: round #3a3f47; padding: 0 1; }
    #actionpane { margin: 0 0 0 1; }
    #body.stacked #actionpane { margin: 1 0 0 0; }
    /* Tiny windows: drop the pane borders + the stacked top-margin so two stacked
       panes fit in the few body rows that remain (the lists still scroll). */
    #body.tiny #sorterpane, #body.tiny #actionpane { border: none; min-height: 1; }
    #body.tiny.stacked #actionpane { margin: 0; }
    /* Focused pane: accent + heavy border (the shape cue survives NO_COLOR). */
    #sorterpane:focus-within { border: heavy $accentcolor; }
    #actionpane:focus-within { border: heavy $accentcolor; }

    #sorters, #actions { height: 1fr; border: none; }
    OptionList:focus { border: none; }

    /* The CURSOR (where up/down is) must read differently from the ACTIVE sorter
       (the persistent left-bar + reverse chip drawn in the row text). Focused: a
       faint accent wash + default fg. Blurred: no filled bar — just an underline —
       so the cursor never masquerades as the active selection. Underline is a shape
       cue, so it survives NO_COLOR too. */
    OptionList:focus > .option-list--option-highlighted {
        background: $accentcolor 25%; color: $foreground; text-style: none;
    }
    OptionList > .option-list--option-highlighted {
        background: transparent; text-style: underline;
    }

    /* Bottom INSPECTING panel — full width, capped height, scrolls. Follows the
       focused pane's highlighted row. */
    #inspect { height: auto; max-height: 7; border: round #3a3f47;
        padding: 0 1; margin: 1 1 0 1; }
    #inspect.hidden { display: none; }

    /* Pinned to the bottom at a fixed 2 rows so a long key-hint can never wrap and
       steal body rows from the lists. */
    #footer { dock: bottom; height: 2; padding: 0 2; }
    """

    BINDINGS = [
        # Both lists are always visible: ←/→ (and Tab/Shift-Tab) MOVE FOCUS between
        # the two panes (no display flip). Tab bindings are priority so they beat the
        # Screen's default focus-next/previous traversal.
        Binding("left", "focus_sorters", "Sorters", show=False),
        Binding("right", "focus_actions", "Actions", show=False),
        Binding("tab", "focus_actions", "Actions", show=False, priority=True),
        Binding("shift+tab", "focus_sorters", "Sorters", show=False, priority=True),
        Binding("t", "cycle_sorter", "Switch sorter", show=False),
        Binding("m", "toggle_motion", "Motion", show=False),
        # x manages the highlighted sorter (delete image / clear saved sort) — wired
        # to a no-op-safe action now; Stage 5 fills it in.
        Binding("x", "manage_highlighted", "Manage", show=False),
        Binding("d", "data_help", "Data files", show=False),
        Binding("f", "choose_folder", "Data folder", show=False),
        Binding("question_mark", "help", "Help", show=False),
        Binding("q", "quit", "Quit", show=False),
        # NOTE: Esc is deliberately NOT bound to quit — a reflexive "go back" press
        # should never hard-exit the dashboard and lose the user's place. Modals
        # keep their own Esc=cancel; q / Ctrl-C still quit the app.
        Binding("ctrl+c", "quit", "Quit", show=False),
        # number-key jump: 1..9 -> action index 0..8
        *[Binding(str(n), f"run_index({n - 1})", show=False) for n in range(1, 10)],
    ]

    def __init__(self, controller: Controller):
        # Set before super().__init__(): App.__init__ builds the stylesheet, which
        # calls get_css_variables() -> reads self._accent.
        self.c = controller
        self._accent = controller.accent
        self._last = None
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
        yield Static(id="probebar")
        with Horizontal(id="body"):
            with Vertical(id="sorterpane"):
                yield NavList(id="sorters")
            with Vertical(id="actionpane"):
                yield NavList(id="actions")
        with VerticalScroll(id="inspect"):
            yield Static(id="inspectbody")
        yield Static(id="footer")

    def on_mount(self) -> None:
        # The INSPECTING panel is a pure display surface — keep it OUT of the Tab
        # focus order so Tab/Shift-Tab only ever move between the two lists.
        self.query_one("#inspect", VerticalScroll).can_focus = False
        self.query_one("#sorterpane").border_title = "SORTERS"
        self._rebuild_sorters()
        self._rebuild_actions()
        self._refresh_action_title()
        # Launch with the SORTERS pane focused; both lists are always visible.
        self.query_one("#sorters", OptionList).focus()
        self._render_inspect()
        self._refresh_footer()
        self._relayout()
        if getattr(self.c, "want_welcome", False):
            self.push_screen(WelcomeScreen(), self._after_welcome)

    def _after_welcome(self, _result) -> None:
        self.c.mark_welcome_seen()

    def on_resize(self, event) -> None:
        # self.size lags during a resize event; event.size carries the new size.
        self._relayout(event.size)

    def _relayout(self, size=None) -> None:
        size = size if size is not None else self.size
        w, h = size.width, size.height
        stacked = w < self.STACK_COLS
        self.query_one("#body").set_class(stacked, "stacked")
        self._render_databar(w)
        self._render_sortbar(w)
        self._render_probebar(w)
        self._refresh_action_title()
        # Hide the INSPECTING panel on shortness so the lists keep their rows (its
        # blurb is non-essential; the lists themselves must never clip). Stacked panes
        # share the body height, so they need the room sooner — drop it earlier there.
        hide_inspect = h < (self.STACK_SHORT_ROWS if stacked else 16)
        self.query_one("#inspect").set_class(hide_inspect, "hidden")
        # On an extreme-short window (no room for two stacked panes once chrome is
        # subtracted), collapse the title + banner so the lists keep their rows. The
        # footer + the d Help topic still carry the DATA/SORT info.
        tiny = h < self.TINY_ROWS
        for wid in ("#titlebar", "#databar", "#sortbar", "#probebar"):
            self.query_one(wid).set_class(tiny, "collapsed")
        # Tiny: drop the pane borders too so two stacked panes fit the few body rows.
        self.query_one("#body").set_class(tiny, "tiny")
        # Crest reserve = chrome (title + banner + its top margin + footer + the
        # crest's own padding row, ~7 rows; ~3 when tiny-collapsed) + a usable min
        # body. Side by side, one pane is ~8 rows; stacked, the two panes need ~6 rows
        # between them PLUS the inspect panel when shown, so reserve more so the crest
        # drops a tier rather than the lists losing rows.
        chrome = 3 if tiny else 8
        if tiny:
            body_min = 2 if stacked else 1     # borderless panes: 1 content row each
        elif stacked:
            body_min = 6 + (0 if hide_inspect else 6)
        else:
            body_min = 8
        reserve = chrome + body_min
        self.query_one("#crest", CrestWidget).fit(w, h, reserve)
        self.query_one("#titlebar", Static).update(self._render_titlerule(w))
        self._refresh_footer(w)

    STACK_COLS = STACK_COLS
    BANNER_ROWS = BANNER_ROWS
    # Stacked windows shorter than this hide the INSPECTING panel so both stacked
    # panes keep a visible row (each pane is a 2-row border + ≥1 content row).
    STACK_SHORT_ROWS = 24
    # Below this the title + banner collapse so two stacked panes still fit.
    TINY_ROWS = 14

    # -- the always-on DATA / SORT banner ------------------------------------- #
    def _render_databar(self, width: int) -> None:
        """The DATA row: a quiet ✓ line naming the loaded streams (Events listed only
        when the .nev loaded — an empty Events set is NOT a failure), or a loud ✗ line
        naming the exact problem (missing / incomplete / unreadable broadband)."""
        dr = self.c.data_report
        files = dr.get("files", [])
        complete = bool(files) and all(f.get("present") for f in files)
        bb = next((r for r in self.c.pipeline if "Broadband" in r.get("stage", "")), None)
        unreadable = complete and bb is not None and bb.get("status") == "FAIL"
        t = Text()
        t.append("DATA  ", style=ui.SECONDARY)
        if dr.get("present") and complete and not unreadable:
            labels = {".ns2": "LFP", ".ns5": "Broadband", ".nev": ".nev"}
            loaded = [f for f in files if f.get("present")]
            for f in loaded:
                if f["ext"] == ".nev" and not f.get("present"):
                    continue
                t.append("✓ ", style="#3fb950")
                t.append(f"{labels.get(f['ext'], f['ext'])}   ", style=ui.PRIMARY)
            t.append(f"  all {len(loaded)} streams loaded", style="dim")
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
            ready = ("Docker image not downloaded — Enter to get it"
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
        t.truncate(max(1, width - 2), overflow="ellipsis")
        self.query_one("#sortbar", Static).update(t)

    def _render_probebar(self, width: int) -> None:
        """The PROBE row: active probe label, summary, and channel-match status."""
        info = self.c.probe_info
        t = Text()
        t.append("PROBE  ", style=ui.SECONDARY)
        label = info.get("label", info.get("name", "unknown probe"))
        t.append(label, style=f"bold {self._accent}")
        summary = info.get("summary", "")
        if summary:
            t.append(f" · {summary}", style=ui.PRIMARY)
        match = info.get("match", "")
        if match in ("fits", "auto"):
            t.append(" · ✓", style="#3fb950")
        elif match == "mismatch":
            t.append(" · ✗ channel count mismatch", style="bold #f0883e")
        t.truncate(max(1, width - 2), overflow="ellipsis")
        self.query_one("#probebar", Static).update(t)

    def _refresh_action_title(self) -> None:
        self.query_one("#actionpane").border_title = f"ACTIONS — on {self.c.active_sorter}"

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

    def _rebuild_sorters(self) -> None:
        ol = self.query_one("#sorters", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        ol.add_option(Option(self._docker_row_text(), id="__docker__"))
        active_row = 0
        by_group: dict[str, list[dict]] = {}
        for info in self.c.infos:
            by_group.setdefault(info.get("group", "unavailable"), []).append(info)
        for group in self._GROUP_ORDER:
            members = by_group.get(group)
            if not members:                      # omit empty groups
                continue
            # Header brighter than its rows (was "dim bold", which read as just
            # another disabled item) so the grouping reads as structure.
            ol.add_option(Option(Text(self._GROUP_LABEL[group],
                                       style=f"bold {self._GROUP_COLOR[group]}"),
                                  id=f"__grp_{group}__", disabled=True))
            for info in members:
                ol.add_option(Option(self._sorter_text(info), id=info["name"]))
                if info.get("active"):
                    active_row = ol.option_count - 1
        ol.highlighted = (keep if (keep is not None and keep < ol.option_count)
                          else active_row)
        # Now that the list flexes (height: 1fr) it can scroll — keep the cursor (and,
        # on a fresh build, the active sorter) in view so "which sorter is active" is
        # never scrolled off. Guarded: a no-op under the headless test driver.
        if ol.highlighted is not None:
            try:
                ol.scroll_to_highlight()
            except Exception:  # noqa: BLE001 - cosmetic only
                pass
        # Keep the INSPECTING panel in sync after any rebuild (cycle/activate/docker
        # toggle/post-run reload) when SORTERS is the focused pane.
        if self._sorters_focused():
            self._render_sorter_explain(self._highlighted_info())

    def _sorters_focused(self) -> bool:
        try:
            return self.focused is self.query_one("#sorters", OptionList)
        except Exception:  # noqa: BLE001 - during mount/teardown
            return False

    def _docker_row_text(self) -> Text:
        # A [x]/[ ] checkbox affordance reads as a toggle on any font and under
        # NO_COLOR; the old ⊞ (U+229E) has patchy monospace coverage (often tofu).
        on = getattr(self.c, "use_docker", False)
        t = Text()
        t.append("[x] " if on else "[ ] ", style=f"bold {self._accent}" if on else "dim")
        t.append("Docker sorters: ", style=ui.SECONDARY)
        t.append("on" if on else "off", style=f"bold {self._accent}" if on else "dim")
        return t

    # Group order + headers for the grouped sidebar. Empty groups are omitted.
    _GROUP_ORDER = ["ready", "docker", "gpu", "unavailable"]
    _GROUP_LABEL = {
        "ready": "READY TO USE",
        "docker": "DOCKER SORTERS (heavier)",
        "gpu": "NEEDS A GPU",
        "unavailable": "NOT AVAILABLE",
    }
    # Plain-language "why is this sorter here" reason per group, for the detail card.
    _GROUP_REASON = {
        "ready": "Ready to run",
        "docker": "Runs via Docker (~1 GB)",
        "gpu": "Needs an NVIDIA GPU",
        "unavailable": "Not installed here",
    }
    # Semantic colour per readiness tier, so the group headers signal go/caution/no
    # at a glance (degrades to bold text under NO_COLOR).
    _GROUP_COLOR = {
        "ready": "#3fb950",         # green  — go
        "docker": "#d29922",        # amber  — works, but heavier
        "gpu": "#f0883e",           # orange — needs hardware you don't have
        "unavailable": "#6e7681",   # grey   — not an option here
    }
    # Compact inline tag on a NON-runnable row so the block reason is scannable
    # without moving the cursor to read the detail card.
    _GROUP_ROW_TAG = {"docker": "docker", "gpu": "GPU", "unavailable": "n/a"}

    def _sorter_text(self, info: dict) -> Text:
        # A persistent left accent BAR + bold name + reverse ACTIVE chip mark the
        # active sorter as a SHAPE: it reads at a glance regardless of focus or where
        # the cursor sits, and is structurally different from the cursor highlight
        # (so active ≠ cursor). Survives NO_COLOR (▌ is a filled block, `reverse`
        # swaps fg/bg). ★ = recommended; the section header already says the group, so
        # the old per-row ◇/· glyph is gone. The SELECTED card carries the full info.
        active = info.get("active", False)
        runnable = info.get("runnable", False)
        t = Text()
        t.append("▌ " if active else "  ", style=self._accent if active else "")
        t.append("★ " if info.get("recommended") else "  ",
                 style=f"bold {self._accent}" if info.get("recommended") else "")
        # No accent fg on the name: when the cursor lands on the active row, the
        # cursor's own foreground keeps it legible (accent-on-cursor was low-contrast).
        name_style = "bold" if active else ("" if runnable else ui.SECONDARY)
        t.append(info["name"], style=name_style)
        # Saved-unit count: readable secondary grey (real info), em-dash when none.
        t.append(f"  {info['units']}u" if info.get("present") else "  —",
                 style=ui.SECONDARY if info.get("present") else "dim")
        if active:
            t.append("  ")
            t.append(" ACTIVE ", style=f"reverse bold {self._accent}")
        elif not runnable:
            # Why this row can't be picked, inline (docker off / GPU / not installed).
            tag = self._GROUP_ROW_TAG.get(info.get("group"))
            if tag:
                t.append(f"  ·{tag}", style="dim")
        # Docker rows carry a download badge so the cached/get-it state is scannable
        # without opening INSPECTING: ✓ ready (cached), ⬇ NN% (pulling), or ⬇ get.
        if info.get("group") == "docker":
            if info.get("img_present"):
                label, style = ui.DL_READY
                t.append(label, style=style)
            elif info.get("downloading") is not None:
                t.append(f"  ⬇ {info['downloading']}%", style=self._accent)
            else:
                label, style = ui.DL_GET
                t.append(label, style=style)
        return t

    def _highlighted_info(self) -> dict:
        """The catalog info dict for the row the cursor is on (header/docker/unknown
        rows fall back to the active sorter), for the Selected-sorter card."""
        try:
            ol = self.query_one("#sorters", OptionList)
            if ol.highlighted is not None:
                oid = ol.get_option_at_index(ol.highlighted).id
                info = next((i for i in self.c.infos if i["name"] == oid), None)
                if info is not None:
                    return info
        except Exception:  # noqa: BLE001 - fall back to the active sorter
            pass
        return self.c.infos[self.c.active_idx]

    def _render_sorter_explain(self, info: dict | None) -> None:
        """Paint the explanation pane for a sorter: a header line (name + ★/ACTIVE
        chip / 'press Enter to make active' / block reason), the full (un-truncated)
        description, a generic tuning hint, the saved-sort + custom-params lines, and
        a 'Press → or Tab for actions.' call-to-action.

        ``info`` is the highlighted catalog row; for a header/docker/None row it
        falls back to the active sorter (matching the State-A spec)."""
        if info is None:
            info = self.c.infos[self.c.active_idx]
        active = info.get("active", False)
        runnable = info.get("runnable", False)
        group = info.get("group")
        t = Text()
        # Header: text-first so it survives NO_COLOR (the ACTIVE chip is a reverse
        # block; the active name keeps default fg so the chip stays legible under the
        # focused cursor wash).
        t.append(info["name"], style="bold")
        if active:
            t.append("   ", style="")
            if info.get("recommended"):
                t.append("★ · ", style=f"bold {self._accent}")
            t.append(" ACTIVE ", style=f"reverse bold {self._accent}")
        elif runnable:
            t.append("  ·  press Enter to make active", style="dim")
        else:
            reason = self._GROUP_REASON.get(group, "Not available")
            t.append(f"  ·  {reason}", style="#f0883e")
        t.append("\n\n")
        # Non-runnable rows lead with how to enable, before the description.
        if not runnable:
            if group == "docker":
                t.append("Turn on the Docker sorters toggle at the top of the list "
                         "to run this.\n\n", style="#f0883e")
            elif group == "gpu":
                t.append("Needs an NVIDIA GPU build installed — see Help.\n\n",
                         style="#f0883e")
            else:
                t.append("Not installed on this computer.\n\n", style="#f0883e")
        # Full description (no truncation — the pane is full-width and scrolls).
        desc = info.get("description") or ""
        if desc:
            t.append(desc + "\n\n", style=ui.PRIMARY)
        # Generic tuning hint (kept generic — no brittle action-index references).
        t.append("Too few / too many units? Edit the sorter parameters "
                 "(Edit sorter parameters).\n\n", style=ui.SECONDARY)
        # Saved-sort + custom-params summary.
        t.append("Saved sort  ", style=ui.SECONDARY)
        if info.get("present"):
            t.append(f"{info['units']} units · {info['duration']:.0f} s\n", style=ui.PRIMARY)
        else:
            t.append("none yet\n", style="dim")
        n_over = info.get("overrides", 0)
        t.append("Custom params  ", style=ui.SECONDARY)
        if n_over:
            t.append(f"{n_over} override" + ("s" if n_over != 1 else "") + "\n",
                     style=ui.PRIMARY)
        else:
            t.append("none\n", style="dim")
        t.append("\nPress → or Tab for actions.", style=f"bold {self._accent}")
        self.query_one("#inspectbody", Static).update(t)

    def _render_action_explain(self, meta: dict) -> None:
        """Paint the explanation pane for an action from the controller's resolved
        metadata: a *what* paragraph, an optional *you'll choose* line, an optional
        ⚠ caveat, and a compact Needs ✓/✗ + Output footer (omitted entirely for
        needs-nothing actions)."""
        t = Text()
        t.append((meta.get("what") or "") + "\n", style=ui.PRIMARY)
        if meta.get("choose"):
            t.append("\nYou'll choose: ", style=ui.SECONDARY)
            t.append(str(meta["choose"]) + "\n", style=ui.PRIMARY)
        if meta.get("caveat"):
            t.append("\n⚠ ", style="bold #f0883e")
            t.append(str(meta["caveat"]) + "\n", style="#f0883e")
        needs = meta.get("needs") or []
        output = meta.get("output")
        if needs or output:
            t.append("\n")
            for need in needs:
                ok = need.get("ok")
                glyph, gstyle = ("✓", "bold #3fb950") if ok else ("✗", "bold #f85149")
                t.append("Needs   ", style=ui.SECONDARY)
                t.append(f"{need.get('label', '')}  ", style=ui.PRIMARY if ok else "#f85149")
                t.append(f"{glyph}\n", style=gstyle)
            if output:
                t.append("Output  ", style=ui.SECONDARY)
                t.append(str(output) + "\n", style=ui.PRIMARY)
        self.query_one("#inspectbody", Static).update(t)

    def _render_inspect(self, focus: str | None = None) -> None:
        """Paint the bottom INSPECTING panel for the focused pane's highlighted row:
        the action explanation when ACTIONS has focus, otherwise the highlighted
        sorter's blurb. ``focus`` ('actions'/'sorters') overrides the live
        ``self.focused`` (which lags right after a programmatic ``.focus()`` call).
        The panel's border-title names what's being inspected."""
        try:
            actions = self.query_one("#actions", OptionList)
            inspect = self.query_one("#inspect")
        except Exception:  # noqa: BLE001 - during mount/teardown
            return
        on_actions = (focus == "actions") if focus is not None else (self.focused is actions)
        if on_actions:
            key = self._highlighted_action_key(actions)
            label = key or "action"
            inspect.border_title = f"INSPECTING ▸ {label}"
            self._render_action_explain(self.c.action_explain(key) if key else {"what": ""})
        else:
            info = self._highlighted_info()
            inspect.border_title = f"INSPECTING ▸ {info['name']}"
            self._render_sorter_explain(info)

    def _highlighted_action_key(self, ol: OptionList) -> str | None:
        try:
            if ol.highlighted is not None:
                return ol.get_option_at_index(ol.highlighted).id
        except Exception:  # noqa: BLE001
            pass
        return None

    def _rebuild_actions(self) -> None:
        ol = self.query_one("#actions", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        present = self.c.data_report.get("present")
        first_enabled = None
        for n, a in enumerate(self.c.actions):
            disabled = bool(a.get("needs_data")) and not present
            if not disabled and first_enabled is None:
                first_enabled = n
            ol.add_option(Option(self._action_text(a, disabled, n), id=a["key"], disabled=disabled))
        ol.highlighted = keep if (keep is not None and keep < ol.option_count) else first_enabled

    def _action_text(self, a: dict, disabled: bool, index: int) -> Text:
        t = Text()
        # Prefix the first nine rows with their jump-key so 1-9 is self-documenting
        # at every width (the footer hint is dropped on narrow terminals).
        t.append(f"{index + 1}  " if index < 9 else "   ", style="dim")
        t.append(a["title"], style="dim" if disabled else "")
        if a.get("hint"):
            t.append(f"   {a['hint']}", style="dim")
        if disabled:
            t.append("   (needs data)", style="italic #f0883e")
        return t

    def _refresh_footer(self, width: int | None = None, focus: str | None = None) -> None:
        width = width if width is not None else self.size.width
        info = self.c.infos[self.c.active_idx]
        summary = (f"{info['units']}u · {info['duration']:.0f}s" if info.get("present")
                   else "no saved sort")
        line1 = Text()
        line1.append("Active sorter: ", style=ui.SECONDARY)
        line1.append(info["name"], style=f"bold {self._accent}")
        line1.append(f"  ({summary})", style=ui.SECONDARY)
        # The footer just confirms the ACTIVE sorter and echoes the last action's
        # result; the per-sorter description lives in the INSPECTING panel.
        if self._last:
            line1.append("    ")
            line1.append(self._last if isinstance(self._last, Text) else Text(str(self._last)))
        line2 = Text(self._footer_hint(width, focus), style="dim")
        cap = max(1, width - 2)
        line1.truncate(cap, overflow="ellipsis")
        line2.truncate(cap, overflow="ellipsis")
        self.query_one("#footer", Static).update(line1 + Text("\n") + line2)

    def _footer_hint(self, width: int, focus: str | None = None) -> str:
        """Per-focus, width-adaptive key hint. With ACTIONS focused it leads with the
        run/jump keys; with SORTERS focused it leads with the activate/Actions bridge.
        Both keep ``t d ? q``. ``focus`` overrides the live (lagging) ``self.focused``."""
        actions_focused = (focus == "actions") if focus is not None else self._actions_focused()
        if actions_focused:
            if width >= 92:
                return ("↑/↓ choose · Enter run · 1-9 jump · ← Sorters · "
                        "t switch · d data · ? help · q quit")
            if width >= 60:
                return "↑/↓ choose · Enter run · 1-9 jump · ← Sorters · t · d · ? · q quit"
            return "↑↓ run · ← Sorters · ? · q quit"
        # sorters focused — never drop the "→/1-9 Actions" bridge first.
        if width >= 92:
            return ("↑/↓ choose · Enter activate · →/1-9 Actions · "
                    "t switch · d data · ? help · q quit")
        if width >= 60:
            return "↑/↓ choose · Enter activate · →/1-9 Actions · t · d · ? · q quit"
        return "↑↓ choose · →/1-9 Actions · ? · q quit"

    def _actions_focused(self) -> bool:
        try:
            return self.focused is self.query_one("#actions", OptionList)
        except Exception:  # noqa: BLE001 - during mount/teardown
            return False

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Keep the INSPECTING panel in sync with the highlighted row of the FOCUSED
        list. A highlight event from the non-focused list (e.g. fired while rebuilding
        it) must not overwrite the focused list's blurb."""
        try:
            sorters = self.query_one("#sorters", OptionList)
            actions = self.query_one("#actions", OptionList)
        except Exception:  # noqa: BLE001 - during teardown
            return
        if event.option_list is sorters and self.focused is sorters:
            oid = event.option.id
            info = next((i for i in self.c.infos if i["name"] == oid), None)
            # header/docker rows (info None) fall back to the active sorter.
            self.query_one("#inspect").border_title = (
                f"INSPECTING ▸ {info['name']}" if info
                else f"INSPECTING ▸ {self.c.active_sorter}")
            self._render_sorter_explain(info)
        elif event.option_list is actions and self.focused is actions:
            key = event.option.id
            if key:
                self.query_one("#inspect").border_title = f"INSPECTING ▸ {key}"
                self._render_action_explain(self.c.action_explain(key))

    # -- focus moves (both lists always visible — just move focus) ------------ #
    def action_focus_actions(self) -> None:
        """Move focus to the ACTIONS pane and re-render the INSPECTING panel for its
        highlighted action. No-op-safe if already focused there."""
        ol = self.query_one("#actions", OptionList)
        ol.focus()
        self._scroll_into_view(ol)
        self._render_inspect(focus="actions")
        self._refresh_footer(focus="actions")

    def action_focus_sorters(self) -> None:
        """Move focus to the SORTERS pane and re-render the INSPECTING panel for its
        highlighted sorter. No-op-safe if already focused there."""
        ol = self.query_one("#sorters", OptionList)
        ol.focus()
        self._scroll_into_view(ol)
        self._render_inspect(focus="sorters")
        self._refresh_footer(focus="sorters")

    def _scroll_into_view(self, ol: OptionList) -> None:
        try:
            ol.scroll_to_highlight()
        except Exception:  # noqa: BLE001 - cosmetic only
            pass

    def action_manage_highlighted(self) -> None:
        """``x``: manage the highlighted sorter. Only when the SORTERS pane is
        focused — open a small confirm offering ONLY the applicable destructive ops
        (delete its downloaded Docker image when cached, clear its saved sort when
        one exists). If neither applies, set a footer hint instead of opening an
        empty modal."""
        if not self._sorters_focused():
            return
        info = self._highlighted_info()
        if info is None:
            return
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
            self._rebuild_sorters()
            self._rebuild_actions()
        except Exception as e:  # noqa: BLE001 - a reload failure must not kill the app
            self._last = Text(f"reload after manage failed: {e!r}", style="#f85149")
        self._render_sortbar(self.size.width)
        self._refresh_footer()
        self._render_inspect()

    def action_cycle_sorter(self) -> None:
        self.c.cycle_active()
        self._rebuild_sorters()
        self._render_sortbar(self.size.width)     # the SORT banner names the new active
        self._refresh_action_title()
        if self._sorters_focused():
            self._render_inspect()
        self._refresh_footer()

    def action_toggle_motion(self) -> None:
        on = self.c.set_animate(not self.c.animate)
        self.query_one("#crest", CrestWidget).set_animate(on)
        self.notify(f"Crest animation {'on' if on else 'off'}")

    def action_data_help(self) -> None:
        self.push_screen(HelpScreen(self.c, self._accent, topic="data"))

    def action_choose_folder(self) -> None:
        self.push_screen(DataFolderScreen(self.c.data_report.get("data_dir")),
                         self._after_choose_folder)

    def _after_choose_folder(self, result) -> None:
        if result is None:
            return                                  # cancelled
        found = self.c.set_data_dir(result or None)
        self._rebuild_sorters()
        self._rebuild_actions()
        self._last = (Text("Data folder updated ✓", style="bold #3fb950") if found
                      else Text("⚠ No recording found in that folder", style="#f0883e"))
        self._refresh_footer()
        self._relayout()
        self._render_inspect()

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self.c, self._accent, topic="overview"))

    def action_run_index(self, i: int) -> None:
        """1-9 jump-run action ``i``. Both lists are always visible, so just move
        focus to the actions list, highlight action ``i`` (rendering its blurb), and
        run it."""
        if not (0 <= i < len(self.c.actions)):
            return
        ol = self.query_one("#actions", OptionList)
        ol.focus()
        if i < ol.option_count:
            ol.highlighted = i                 # fires the highlight -> renders INSPECTING
        self._render_inspect(focus="actions")
        self._activate_action(self.c.actions[i]["key"])

    def _set_active_by_name(self, name: str) -> bool:
        if self.c.set_active_by_name(name):
            self._rebuild_sorters()
            self._render_sortbar(self.size.width)
            self._refresh_action_title()
            self._refresh_footer()
            return True
        return False

    # -- list selection ------------------------------------------------------- #
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list is self.query_one("#sorters", OptionList):
            oid = event.option.id
            if oid == "__docker__":
                self._toggle_docker()
            elif oid and oid.startswith("__grp_"):
                return
            else:
                self._select_sorter(oid)
        elif event.option_list is self.query_one("#actions", OptionList):
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
                self.push_screen(DownloadProgressScreen(self.c, name, self._accent),
                                 self._after_download)
            else:
                self._toggle_docker(offer_from=name)   # get Docker running first
        elif info.get("runnable"):
            # Activate AND move focus to the (always-visible) ACTIONS pane — the
            # choose→run flow is one motion.
            if self._set_active_by_name(name):
                self.action_focus_actions()
        elif info.get("group") == "docker":
            # Image is cached but the Docker toggle is off — offer to enable it.
            self._toggle_docker(offer_from=name)
        else:
            hint = ("needs a GPU build installed — see Help" if info.get("group") == "gpu"
                    else "not available on this computer")
            self._last = Text(f"{name}: {hint}", style="#f0883e")
            self._refresh_footer()

    def _after_download(self, result) -> None:
        """A finished/interrupted in-UI download. Reload the catalog so the row's
        download badge + readiness flip, then re-render the sidebar, banner, and
        INSPECTING panel."""
        if isinstance(result, tuple):
            ok, message = result[0], result[1]
        else:
            ok, message = False, str(result)
        self._last = Text(message, style=_result_style(ok, message))
        try:
            self.c.reload()
            self._rebuild_sorters()
            self._rebuild_actions()
        except Exception as e:  # noqa: BLE001 - a reload failure must not kill the app
            self._last = Text(f"reload after download failed: {e!r}", style="#f85149")
        self._render_sortbar(self.size.width)
        self._refresh_footer()
        self._render_inspect()

    def _highlight_sorter_by_name(self, name: str) -> bool:
        """Move the SORTERS cursor onto a sorter row by name (focusing the pane so a
        following Enter dispatches there). Used by the keyboard flow + tests."""
        ol = self.query_one("#sorters", OptionList)
        for i in range(ol.option_count):
            if ol.get_option_at_index(i).id == name:
                ol.focus()
                ol.highlighted = i
                self._render_inspect(focus="sorters")
                return True
        return False

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
        self._rebuild_sorters()
        self._rebuild_actions()
        if on:
            self._last = Text("Docker sorters on ✓ — pick one, then run a sort to use it",
                              style=f"bold {self._accent}")
        else:
            self._last = Text("Docker sorters off", style="dim")
        self._refresh_footer()
        self._relayout()
        self._render_inspect()

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
                    "Start Docker (the Docker row) or pick a READY sorter.",
                    style="#f0883e")
                self._refresh_footer()
                return
            info = self.c.infos[self.c.active_idx]
            note = None
            if info.get("present"):     # warn before silently replacing a saved sort
                note = (f"⚠ {info['name']} already has a saved sort "
                        f"({info['units']}u · {info['duration']:.0f}s) — running again replaces it.")
            self.push_screen(
                ChoiceModal("Sort how much?", [
                    ("full", "Full recording", ""),
                    ("quick", f"Quick test — first {self.c.quick_seconds}s", ""),
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
        self.push_screen(SortProgressScreen(argv, self._accent), self._after_sort)

    def _after_sort(self, result) -> None:
        ok, message, changed = result or (False, "Sort cancelled", False)
        self._last = Text(message, style=_result_style(ok, message))
        if changed:
            try:
                self.c.reload()
                self._rebuild_sorters()
                self._rebuild_actions()
            except Exception as e:  # noqa: BLE001 - reload failure must not kill the app
                self._last = Text(f"reload after sort failed: {e!r}", style="#f85149")
        self._refresh_footer()
        self._relayout()
        self._render_inspect()
        self.refresh()

    def _open_theme(self) -> None:
        opts = [(n, n, "(current)" if n == self.c.theme_name else "") for n in self.c.themes]
        self.push_screen(ChoiceModal("Accent colour  (saved for next time)", opts),
                         self._after_theme)

    def _after_theme(self, name: str | None) -> None:
        if not name:
            return
        self._accent = self.c.set_theme(name)
        self.refresh_css()
        self._rebuild_sorters()
        self._rebuild_actions()
        self._render_inspect()
        self._render_databar(self.size.width)
        self._render_sortbar(self.size.width)
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
            self._rebuild_sorters()
            self._rebuild_actions()
        except Exception as e:  # noqa: BLE001 - a reload failure must not kill the app
            self._last = Text(f"reload after manage failed: {e!r}", style="#f85149")
        self._render_sortbar(self.size.width)
        self._refresh_footer()
        self._render_inspect()

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
        try:
            with self.suspend():
                ok, message, changed = self.c.run_compare(pair)
        except SuspendNotSupported:
            ok, message, changed = self.c.run_compare(pair)
        except Exception as e:  # noqa: BLE001
            ok, message, changed = False, f"compare failed: {e!r}", False
        self._last = Text(message, style=_result_style(ok, message))
        if changed:
            try:
                self.c.reload()
                self._rebuild_sorters()
                self._rebuild_actions()
            except Exception as e:  # noqa: BLE001
                self._last = Text(f"reload after compare failed: {e!r}", style="#f85149")
        self._refresh_footer()
        self._relayout()
        self._render_inspect()
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
                self._rebuild_sorters()
                self._rebuild_actions()
        except Exception as e:  # noqa: BLE001 - a reload failure must not kill the app
            self._last = Text(f"reload after {key} failed: {e!r}", style="#f85149")
        self._refresh_footer()
        self._relayout()
        self._render_inspect()
        self.refresh()


def _result_style(ok: bool, message) -> str:
    """Colour for a 'last action' line: red on failure, amber for a succeeded-but-
    check-this outcome (message starts with '⚠', e.g. a sort that found 0 units),
    green otherwise."""
    if not ok:
        return "#f85149"
    return "#f0883e" if str(message).lstrip().startswith("⚠") else "#3fb950"


def _trunc(text: str, n: int) -> str:
    return text if len(text) <= n else text[: max(0, n - 1)] + "…"


def _ljust_trunc(text: str, n: int) -> str:
    """Truncate to ``n`` cols then pad to ``n`` so a bordered banner's right edge
    lines up regardless of the message length."""
    return _trunc(text, n).ljust(n)


def _param_to_str(value) -> str:
    """Render a scalar/None default for an Input field ('' for None)."""
    if value is None:
        return ""
    return str(value)
