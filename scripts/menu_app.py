"""Reusable modal screens for the Spike 2.0 app (``scripts/spike_app.py``).

The dashboard itself - the journey rail, the stage panes, Settings, the palette,
Runs - lives in ``spike_app``. This module holds the modals it pushes, each a
self-contained view over the controller (``SpikeInterface_Menu.MenuController``),
importing no SpikeInterface: the in-UI sort (``SortProgressScreen``, which speaks
``run_sorting.py --progress json``), the report build (``BuildProgressScreen``),
the in-process compare (``BusyScreen``), the sorter-parameter editor, the probe
profile editor, Docker confirm / download / the Sorters and Docker hub, the data
folder picker and the generic single-choice modal.
"""
from __future__ import annotations

import asyncio
from time import monotonic

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

import download_stats as dlstats  # pure download progress math + formatters
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

    # PageUp/PageDown can clamp onto a disabled row (a stage/group heading at a
    # list edge), which drops the highlight to None and deadens Enter until an
    # arrow press. Land on the nearest enabled option instead.
    def _highlight_first_enabled(self, indices) -> None:
        for i in indices:
            if not self.get_option_at_index(i).disabled:
                self.highlighted = i
                return

    def action_page_up(self) -> None:
        super().action_page_up()
        if self.highlighted is None and self.option_count:
            self._highlight_first_enabled(range(self.option_count))

    def action_page_down(self) -> None:
        super().action_page_down()
        if self.highlighted is None and self.option_count:
            self._highlight_first_enabled(range(self.option_count - 1, -1, -1))

# Status-word -> session phase, shared by the download status handler.
_DL_PHASE = {"Downloading": "downloading", "Verifying": "verifying",
             "Extracting": "extracting", "Done": "done"}

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


class DataFolderScreen(ModalScreen):
    """Point the dashboard at a different recording folder without relaunching -
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
    ``(ok, message)`` - the app records the result and reopens the artifact."""

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
        # failure, SI version skew - the lab's known failure class) stays
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
        # "cancelled" - the artifact is already on disk (D3b review F5).
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
    no-ops - pretending to offer cancel for an uncancellable step is the lie this
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
    # already-overridden keys - the user's own knobs lead). Everything else keeps
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
                            w = Input(value=_param_to_str(cur, default), id=f"w_{key}")
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
        """Live validation: coerce as the user types - invalid goes red with the
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
            Text("Starting Docker…  (~30–60s - press [r] to re-check)", style="dim"))
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
            self._stop_poll()                    # done - don't keep probing every 2s
            self._render_status()                # advances to the 'running' view
            return
        if self._polls >= 45:                    # ~90s timeout -> manual fallback
            self._stop_poll()
            self.query_one("#dstatus", Static).update(
                Text("Still not ready - open Docker Desktop, then press [r].", style="#f0883e"))
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
    and - during indeterminate stretches - a spinner + "still working (Ns)" line fed
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
        # AND queue the next step - dispatched by the app after the pop (the modal
        # contract carries an optional next_action; a running sort ignores them).
        Binding("r", "chain('report')", "Build report", show=False),
        Binding("i", "chain('gui')", "Inspect in GUI", show=False),
    ]

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    # Friendly names for the sorter internals that leak into detail lines - the
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
        # the subprocess is quiet (between heartbeats). Cheap - no work when done.
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
            # 'true' in tests, or a hard crash - segfault / OOM-kill - that bypasses
            # even run_sorting's last-resort error event) - synthesise a close state,
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
        # clock - a quiet subprocess must still look alive (DESIGN_UX §1.6).
        s = self._state
        if s["done"] is None:
            self._spin = (self._spin + 1) % len(self._SPINNER)
            self._repaint()

    @staticmethod
    def _fmt_mmss(secs: float) -> str:
        secs = max(0, int(secs))
        return f"{secs // 60}:{secs % 60:02d}"

    def _friendly_detail(self, detail: str) -> str:
        # Translate the jargon head, keep EVERYTHING after it verbatim - counts and
        # qualifiers are real information (D2v review F3).
        for head, nice in self._DETAIL_FRIENDLY.items():
            if detail.startswith(head):
                rest = detail[len(head):]
                if rest.startswith("()"):
                    rest = rest[2:]
                return (nice + rest).strip()
        return detail

    # NB: deliberately NOT named ``_render`` - that collides with Textual's
    # ``Widget._render`` (the layout engine calls it expecting a Visual).
    def _repaint(self) -> None:
        s = self._state
        running = s["done"] is None
        # Header: what · how much · a ticking clock - the run always looks alive.
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
        # The phase checklist - finished phases carry their real (emitter-side)
        # durations; the running one carries the live detail below it; the ones the
        # run announced but has not reached yet sit dim below it (DESIGN_UX §3), so
        # the pipeline's shape is visible from the first frame.
        for p in _sp.phase_rows(s):
            kind = p["state"]
            t.append({"done": "✓ ", "running": "▶ ", "pending": "· "}[kind],
                     style={"done": "#3fb950", "running": f"bold {self._accent}",
                            "pending": "dim"}[kind])
            t.append(f"{p['title']}",
                     style={"done": "", "running": "bold", "pending": "dim"}[kind])
            if kind == "done" and p.get("secs") is not None:
                t.append(f"   {p['secs']:.1f} s", style="dim")
            t.append("\n")
        if running and s.get("phase_n") and s["phases"]:
            i = s.get("phase_i") or len(s["phases"])
            t.append(f"  phase {i} of {s['phase_n']}\n", style="dim")
        # Live detail for the current phase - substep, latest (translated) sorter
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
        # finished phase - the bar yields to the spinner/heartbeat before ROUNDING
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
        # The array/yield headline card, once emitted - shown both during the run and
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
                     "re-run - the recording loaded and preprocessed fine.\n",
                     style="#d29922")
        else:
            t.append(f"\n✓ {units} units", style="bold #3fb950")
            good = r.get("good", d.get("good"))
            if good is not None:
                # The rule TEXT rides the result event - the emitting process is
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
                # as checked; outside it goes amber with the known cause named -
                # never displayed as a mute number.
                if 3.5 <= nf <= 4.5:
                    t.append(f"  noise floor {nf:.2f} µV ✓", style="#3fb950")
                    t.append(" (expected ≈3.9–4.1 for this rig)\n", style="dim")
                else:
                    t.append(f"  ⚠ noise floor {nf:.2f} µV - outside the expected "
                             "≈3.9–4.1 band; check the run (a ~1 µV reading means "
                             "the µV scaling was applied twice)\n", style="#d29922")
        # The window fact matters in BOTH branches (F8): a 0-unit quick test's
        # likeliest fix is running the full recording.
        eff, tot = r.get("effective_seconds"), r.get("total_seconds")
        if eff and tot and eff < tot - 1.0:
            t.append(f"  partial: first {eff:.0f} s of {tot:.0f} s - re-run "
                     "full for the whole recording\n", style="#d29922")
        out = r.get("out", d.get("out", ""))
        if out:
            t.append(f"  saved → {out}\n", style="dim")
        if d.get("note"):
            t.append(f"  ⚠ {d['note']}\n", style="#d29922")
        # Chain keys only where the chained action can SUCCEED (F2): with 0 units
        # or failed metrics run_sorting deleted the analyzer, so report/GUI would
        # dead-end - offering them as next steps would be the dishonesty this
        # card exists to kill.
        if self._chainable():
            t.append("\n  ↵ close · r build the report · i inspect in GUI",
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
        # A reflexive Esc AFTER completion closes normally - the sort already
        # happened; calling it "cancelled" would misrecord a real result (F5).
        if self._state["done"] is not None:
            return self.action_close_if_done()
        # Kill the whole worker tree, cross-platform (T2/T3 review found the lab-box
        # gap: os.killpg is POSIX-only and the old blanket except swallowed the
        # AttributeError - Windows showed "Sort cancelled" while the sort kept
        # burning CPU). POSIX: SIGTERM the process group (start_new_session gave us
        # one). Windows: taskkill /T /F takes the tree, since terminate() alone
        # would orphan SpikeInterface's spawn workers. Last resort: terminate().
        _kill_proc_tree(self._proc)
        self.dismiss((False, "Sort cancelled", False, None))

    def _dismiss_message(self) -> tuple:
        """(ok, message, changed) for the current terminal state. The 0-unit case
        carries the detect_threshold fix so it lands amber on the dashboard too -
        the same hint the result card shows (never a green '0 units')."""
        d = self._state["done"]
        ok = bool(d.get("ok"))
        units = (self._state.get("result") or {}).get("units", d.get("units", ""))
        if ok and isinstance(units, int) and units == 0:
            sorter = self._sorter or "sort"
            return (ok, f"⚠ {sorter}: no units found - lower detect_threshold "
                        f"(Edit parameters) and re-run", ok)
        if ok:
            return (ok, f"✓ Sorted {units} units".rstrip(), ok)
        return (ok, f"✗ {d.get('message', 'sort failed')}", ok)

    def action_close_if_done(self) -> None:
        if self._state["done"] is None:
            return                                  # still running - Enter is a no-op
        ok, msg, changed = self._dismiss_message()
        # Only an OK sort changed the saved-sort universe (cancel/error did not).
        self.dismiss((ok, msg, changed, None))

    def action_chain(self, next_action: str) -> None:
        """3/4 on the result card: close AND hand the app the next step. Only an
        OK finished sort chains - running or failed, the keys are no-ops."""
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
        # so we show just the elapsed clock there - never a nonsensical "3 B / 9 B".
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
    operations for ONE sorter - delete its downloaded Docker image (only when the
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
        self._options = options          # [(op_key, label), ...] - only applicable ops
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
        start = getattr(self.app, "start_download", None)
        if start is not None:               # the app owns the worker (survives this screen)
            start(info["name"])
            return
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
                        note="Removes only the cached image - you can re-download it later."),
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
        # Curation decisions live in outputs/<name>/ too, and a re-run sort cannot
        # get them back (unit ids are not stable across re-sorts) - say so.
        note = f"Deletes outputs/{name}/ - you can re-run the sort later."
        if info.get("curated"):
            n = info["curated"].get("counts", {}).get("total", 0)
            note = (f"Deletes outputs/{name}/ - the sort, its curation record "
                    f"({n} decision{'' if n == 1 else 's'}) and the curated result. "
                    "A re-run sort cannot restore the decisions.")
        self.app.push_screen(
            ChoiceModal(f"Clear the saved {name} sort ({units}u)?",
                        [("confirm", "Clear saved sort", ""), ("cancel", "Keep it", "")],
                        note=note),
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


# The four verdicts the TUI writes, in key order. The vocabulary itself is
# curation.py's (QUALITY_OPTIONS) - these strings must match it exactly; this is
# only its keyboard half, so the view still imports no curation module.
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


def _fmt_when(when: str) -> str:
    """Format a LAST RESULT timestamp for display: today's read as a clock time,
    older ones carry their date - persisted results must not masquerade as fresh.
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


def _param_to_str(value, default=None) -> str:
    """Render a value for a scalar Input field ('' for None).

    A None-default parameter round-trips through JSON (coerce_param json-loads
    whatever is typed), so its saved value must render as JSON here too: str()
    of a dict would repopulate the field with Python repr, which the editor
    then refuses to save.
    """
    if value is None:
        return ""
    if default is None:
        import json
        return json.dumps(value)
    return str(value)
