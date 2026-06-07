"""Textual front-door dashboard for SpikeInterface_Menu.py (terminal UI v2).

A single, resident full-screen app that stays usable at any window size — from a
wide desktop terminal down to a short VS Code pane. It is a *view*: all heavy
loading and the actual running of actions live in a small ``Controller`` (built
in ``SpikeInterface_Menu.py``) that this app calls back into. That keeps the app
import-light (no SpikeInterface at import time) and unit-testable with Textual's
``run_test`` / ``Pilot`` harness.

Layout (responsive):

    ┌ shield (Pitt crest, collapses full→compact→mini→hidden as height shrinks) ┐
    │ ── University of Pittsburgh · SpikeInterface ──                            │
    │ ⚠ missing-data banner (only when no recording is found)                    │
    │ ┌ SORTER ───────────┬ ACTIONS ───────────────────────┐                    │
    │ │ ● tridesclous2  …  │ ❯ Explore raw data            … │  (panes go        │
    │ │ ○ spykingcircus2…  │   Run / re-run sorting        … │   side-by-side on  │
    │ │ PIPELINE           │   …                             │   wide terminals,  │
    │ │ ✓ LFP  ✓ Broadband │                                 │   stack on narrow) │
    │ └────────────────────┴─────────────────────────────────┘                    │
    │ Active sorter: … · last action …                                            │
    │ ↑/↓ move · ←/→ or Tab switch focus · Enter run · 1-9 jump · t · d · q quit   │
    └─────────────────────────────────────────────────────────────────────────────┘

Navigation: ←/→ (or Tab/Shift-Tab) move focus between the Sorter sidebar and the
Actions pane; ↑/↓ (or j/k) move within the focused list; Enter on a sorter makes
it active, Enter on an action runs it (the app drops out via ``suspend()`` so the
action's own output scrolls normally, then resumes). 1-9 jump-run an action,
``t`` cycles the active sorter, ``d`` opens the data-setup help, ``q`` quits.

The accent colour is themeable (driven into the ``$accentcolor`` CSS variable);
the Pitt blue+gold shield is fixed. Both lists scroll, so the active sorter and
the actions are always reachable even when the body is taller than the screen.
"""
from __future__ import annotations

from typing import Protocol

from rich.text import Text
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

import ui  # shield art + theme palette + plain helpers (single source)


class NavList(OptionList):
    """OptionList with the extra menu keys the UI advertises: j/k to move and
    space to select (Enter already selects)."""

    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("space", "select", show=False),
    ]

# Width below which the two panes stack vertically instead of side-by-side. Tuned
# so a default 80-col terminal stays two-pane but a split/VS Code pane collapses.
NARROW_COLS = 78
# Rows the shield must leave for title + footer + a usable body, so it drops
# full→compact→mini→hidden well before it would crowd the menu off a short window.
# (The shield ladder itself is 17 / 11 / 7 rows tall — see ui._LOGOS.) The
# missing-data banner adds 2 more (passed through from _relayout).
SHIELD_RESERVE = 21
# Unfocused panel border colour (focus uses the live accent).
_BORDER_DIM = "#3a3f47"


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
    want_welcome: bool

    def set_active_by_name(self, name: str) -> bool: ...
    def cycle_active(self) -> None: ...
    def set_theme(self, name: str) -> str: ...      # returns the new accent hex
    def reload(self) -> None: ...                   # refresh pipeline/infos/data_report
    def toggle_docker(self) -> bool: ...
    def docker_status(self, refresh: bool = False) -> dict: ...
    def start_docker(self) -> bool: ...
    def mark_welcome_seen(self) -> None: ...
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
    ChoiceModal OptionList { height: auto; max-height: 12; background: $surface; border: none; }
    ChoiceModal OptionList:focus { border: none; }
    ChoiceModal #choicefoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, options: list[tuple[str, str, str]]):
        super().__init__()
        self._title = title
        self._options = options

    def compose(self) -> ComposeResult:
        opts = [Option(self._opt_text(m, h), id=k) for k, m, h in self._options]
        with Vertical(id="dialog"):
            yield Static(self._title, id="dialogtitle")
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
        self.set_interval(2.0, self._poll)

    def _poll(self) -> None:
        self._polls += 1
        st = self._c.docker_status(refresh=True)
        if st["running"]:
            self._render_status()                # advances to the 'running' view
            return
        if self._polls >= 45:                    # ~90s timeout -> manual fallback
            self.query_one("#dstatus", Static).update(
                Text("Still not ready — open Docker Desktop, then press [r].", style="#f0883e"))
            return


class WelcomeScreen(ModalScreen):
    """First-launch onboarding (shown once; re-openable from Help)."""

    DEFAULT_CSS = """
    WelcomeScreen { align: center middle; }
    WelcomeScreen > #dialog {
        width: 60; max-width: 92%; height: auto;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
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
        body.append("(press d for help).", style="dim")
        with Vertical(id="dialog"):
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
        self.set_class(size.width < NARROW_COLS, "stacked")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id:
            self._show(event.option.id)

    def _show(self, key: str) -> None:
        title, lines = next(((t, b) for k, t, b in ui.HELP_TOPICS if k == key),
                            ("Help", []))
        if key == "data":
            body = _setup_body(self._c.data_report, self._accent)
        else:
            body = Text()
            body.append(title + "\n\n", style=f"bold {self._accent}")
            for ln in lines:
                body.append(ln + "\n")
        self.query_one("#helpbody", Static).update(body)

    def action_close(self) -> None:
        self.dismiss(None)


def _setup_body(report: dict, accent: str) -> Text:
    """Render the present/missing checklist + where the files belong."""
    t = Text()
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
class ShieldWidget(Static):
    """The blue+gold University of Pittsburgh crest, sized to the live window.

    ``fit(cols, rows)`` (called from the app's relayout) picks the largest shield
    that fits and hides the widget entirely when even the mini crest won't."""

    def fit(self, cols: int, rows: int, reserve: int = SHIELD_RESERVE) -> None:
        logo = ui.pick_logo(cols - 4, rows, reserve=reserve)
        if not logo:
            self.display = False
            return
        t = Text()
        for n, line in enumerate(logo):
            if n:
                t.append("\n")
            for style, seg in line:
                t.append(seg, style=style or None)
        self.update(t)
        self.display = True


# --------------------------------------------------------------------------- #
# Main application
# --------------------------------------------------------------------------- #
class SpikeMenuApp(App):
    """The resident dashboard. One instance per session; actions run via
    ``suspend()`` and the app re-renders from the controller afterwards."""

    CSS = """
    Screen { background: $background; }

    #shield { height: auto; content-align: center top; padding: 1 0 0 0; }
    #titlebar { height: 1; content-align: left middle; }

    #banner {
        height: 1; display: none; margin: 1 2 0 2; padding: 0 1;
        color: #ffd9d4; background: #5a1d1d; text-style: bold;
    }

    #body { height: 1fr; padding: 1 1 0 1; }
    #body.stacked { layout: vertical; }

    /* Two-pane: fixed sidebar + flexible actions. Stacked (narrow): the sidebar is
       capped at half the body so the Actions pane is ALWAYS at least half-height
       and never starved off-screen. */
    #sidebar { width: 36; height: 1fr; }
    #body.stacked #sidebar { width: 1fr; height: auto; max-height: 50%; }
    #mainpane { width: 1fr; height: 1fr; min-height: 6; }

    .sectionlabel { text-style: bold; color: $accentcolor; padding: 0 0 0 1; }

    #sorters { height: auto; max-height: 5; border: round #3a3f47; padding: 0 1; }
    #pipeline { height: auto; border: round #3a3f47; padding: 0 1; margin: 1 0 0 0; }
    #actions { height: 1fr; min-height: 3; border: round #3a3f47; padding: 0 1; }
    /* Focused pane: accent colour AND a heavier border, so the focus cue
       survives on NO_COLOR / monochrome terminals (shape, not colour alone). */
    OptionList:focus { border: heavy $accentcolor; }

    /* Pinned to the bottom at a fixed 2 rows so a long key-hint can never wrap and
       steal body rows from the Actions pane. */
    #footer { dock: bottom; height: 2; padding: 0 2; }
    """

    BINDINGS = [
        Binding("left", "focus_sorter", "Sorter", show=False),
        Binding("right", "focus_actions", "Actions", show=False),
        Binding("t", "cycle_sorter", "Switch sorter", show=False),
        Binding("d", "data_help", "Data files", show=False),
        Binding("question_mark", "help", "Help", show=False),
        Binding("q", "quit", "Quit", show=False),
        Binding("escape", "quit", "Quit", show=False),
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
        self._sorter_hint = None
        super().__init__()

    # -- CSS variable plumbing: $accentcolor follows the live theme ----------- #
    def get_css_variables(self) -> dict:
        v = super().get_css_variables()
        v["accentcolor"] = self._accent
        return v

    # -- layout --------------------------------------------------------------- #
    def compose(self) -> ComposeResult:
        yield ShieldWidget(id="shield")
        yield Static(id="titlebar")
        yield Static(id="banner")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("SORTER", classes="sectionlabel")
                yield NavList(id="sorters")
                yield Static("PIPELINE", id="l-pipeline", classes="sectionlabel")
                yield Static(id="pipeline")
            with Vertical(id="mainpane"):
                yield Static("ACTIONS", classes="sectionlabel")
                yield NavList(id="actions")
        yield Static(id="footer")

    def on_mount(self) -> None:
        self._rebuild_sorters()
        self._rebuild_actions()
        self._refresh_footer()
        self._relayout()
        self.query_one("#actions", OptionList).focus()
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
        stacked = w < NARROW_COLS
        self.query_one("#body").set_class(stacked, "stacked")
        banner_on = self._update_banner(w, h)
        # Shield yields rows for title + footer + a usable body (+ the banner when
        # it is showing), dropping full→compact→mini→hidden as the window shrinks.
        reserve = SHIELD_RESERVE + (3 if banner_on else 0)
        self.query_one("#shield", ShieldWidget).fit(w, h, reserve)
        self.query_one("#titlebar", Static).update(self._render_titlerule(w))
        # Priority on short windows: drop the (secondary) pipeline so the active
        # sorter + actions always stay on screen.
        show_pipe = h >= 22 and bool(self.c.pipeline)
        self.query_one("#l-pipeline", Static).display = show_pipe
        pipe = self.query_one("#pipeline", Static)
        pipe.display = show_pipe
        if show_pipe:
            pipe.update(self._render_pipeline(w, stacked))
        self._refresh_footer(w)

    # Banner needs this much height before it is worth a row; below it (very short
    # windows) it is suppressed so it can never push the body off-screen.
    _BANNER_MIN_ROWS = 9

    def _update_banner(self, width: int, height: int) -> bool:
        """Show/hide the one-row top banner. Returns True while it occupies rows.

        States: hidden (a complete, readable set is present, or the window is too
        short to spare a row), red (nothing found), amber (present-but-incomplete,
        or present-but-unreadable). The text is truncated to one row — the Data
        Setup screen carries the full detail."""
        dr = self.c.data_report
        files = dr.get("files", [])
        complete = bool(files) and all(f.get("present") for f in files)
        # Files exist but the sortable broadband stream won't load (empty/corrupt).
        bb = next((r for r in self.c.pipeline if "Broadband" in r.get("stage", "")), None)
        unreadable = complete and bb is not None and bb.get("status") == "FAIL"
        healthy = dr.get("present") and complete and not unreadable
        banner = self.query_one("#banner", Static)
        if healthy or height < self._BANNER_MIN_ROWS:
            banner.display = False
            return False
        banner.display = True
        if not dr.get("present"):
            msg = "⚠  No recording found  —  press  d  for setup help"
        elif unreadable:
            msg = "⚠  Files present but unreadable  —  press  d  /  run Verify"
        else:
            missing = ", ".join(f["ext"] for f in files if not f.get("present"))
            msg = f"⚠  Incomplete set — missing {missing}  —  press  d  for help"
        t = Text(msg)
        t.truncate(max(1, width - 2), overflow="ellipsis")
        banner.update(t)
        return True

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
            ol.add_option(Option(Text(self._GROUP_LABEL[group], style="dim bold"),
                                  id=f"__grp_{group}__", disabled=True))
            for info in members:
                ol.add_option(Option(self._sorter_text(info), id=info["name"]))
                if info.get("active"):
                    active_row = ol.option_count - 1
        ol.highlighted = (keep if (keep is not None and keep < ol.option_count)
                          else active_row)

    def _docker_row_text(self) -> Text:
        on = getattr(self.c, "use_docker", False)
        t = Text()
        t.append("⊞ Docker sorters: ", style="dim")
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
    # Per-group row glyph: ◇ = runs via Docker, · = gpu/unavailable, (none) = ready.
    _GROUP_GLYPH = {"docker": "◇", "gpu": "·", "unavailable": "·"}

    def _sorter_text(self, info: dict) -> Text:
        # Compact for the 36-col sidebar. ★ recommended, ●/○ active, group glyph,
        # name, saved-unit count; dim when not runnable. Footer carries the
        # description + full units · duration.
        active = info.get("active", False)
        runnable = info.get("runnable", False)
        t = Text()
        t.append("★ " if info.get("recommended") else "  ",
                 style=f"bold {self._accent}" if info.get("recommended") else "")
        t.append("● " if active else "○ ", style=self._accent if active else "dim")
        glyph = self._GROUP_GLYPH.get(info.get("group"))
        if glyph:
            t.append(glyph + " ", style="dim")
        name_style = f"bold {self._accent}" if active else ("" if runnable else "dim")
        t.append(info["name"], style=name_style)
        t.append(f"  {info['units']}u" if info.get("present") else "  —", style="dim")
        if active:
            t.append("  ACTIVE", style=f"bold {self._accent}")
        return t

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

    def _render_pipeline(self, width: int | None = None, stacked: bool = False) -> Text:
        """Glyph + stage (+ detail if it fits), hard-fit to the pipeline box so a
        long ``detail`` is truncated with … rather than wrapping. The box is the
        36-col sidebar when two-pane, or near full-width when stacked."""
        badge = {"PASS": ("✓", "#3fb950"), "SKIP": ("–", "#7d8590"), "FAIL": ("✗", "#f85149")}
        w = width if width is not None else self.size.width
        interior = max(12, (w - 8) if stacked else 30)  # text width inside the box
        body = interior - 2  # after the "glyph " prefix
        t = Text()
        for n, r in enumerate(self.c.pipeline):
            if n:
                t.append("\n")
            glyph, color = badge.get(r["status"], ("?", "#7d8590"))
            line = r["stage"]
            room = body - len(line)
            if room > 6 and r.get("detail"):
                line += "  " + _trunc(r["detail"], room - 2)
            t.append(f"{glyph} ", style=f"bold {color}")
            t.append(_trunc(line, body))
        return t

    def _refresh_footer(self, width: int | None = None) -> None:
        width = width if width is not None else self.size.width
        info = self.c.infos[self.c.active_idx]
        summary = (f"{info['units']}u · {info['duration']:.0f}s" if info.get("present")
                   else "no saved sort")
        line1 = Text()
        line1.append("Active sorter: ", style="dim")
        line1.append(info["name"], style=f"bold {self._accent}")
        line1.append(f"  ({summary})", style="dim")
        hint = getattr(self, "_sorter_hint", None)
        if hint is not None:
            line1.append("    ")
            line1.append(hint)
        elif self._last:
            line1.append("    ")
            line1.append(self._last if isinstance(self._last, Text) else Text(str(self._last)))
        # Width-aware key hint, so a fixed 2-row footer never wraps and steals rows.
        if width >= 92:
            hint = "↑/↓ move · ←/→ or Tab switch focus · Enter run · 1-9 jump · t sorter · d data · q quit"
        elif width >= 60:
            hint = "↑/↓ move · ←/→ focus · Enter run · t sorter · d data · q quit"
        else:
            hint = "↑↓ move · ←→ focus · Enter · q quit"
        line2 = Text(hint, style="dim")
        cap = max(1, width - 2)
        line1.truncate(cap, overflow="ellipsis")
        line2.truncate(cap, overflow="ellipsis")
        self.query_one("#footer", Static).update(line1 + Text("\n") + line2)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list is not self.query_one("#sorters", OptionList):
            return
        oid = event.option.id
        info = next((i for i in self.c.infos if i["name"] == oid), None)
        self._sorter_hint = Text(info["description"], style="dim") if info else None
        self._refresh_footer()

    # -- focus / sorter actions ---------------------------------------------- #
    def action_focus_sorter(self) -> None:
        self.query_one("#sorters", OptionList).focus()

    def action_focus_actions(self) -> None:
        self.query_one("#actions", OptionList).focus()

    def action_cycle_sorter(self) -> None:
        self.c.cycle_active()
        self._rebuild_sorters()
        self._refresh_footer()

    def action_data_help(self) -> None:
        self.push_screen(HelpScreen(self.c, self._accent, topic="data"))

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self.c, self._accent, topic="overview"))

    def action_run_index(self, i: int) -> None:
        if 0 <= i < len(self.c.actions):
            self._activate_action(self.c.actions[i]["key"])

    def _set_active_by_name(self, name: str) -> None:
        if self.c.set_active_by_name(name):
            self._rebuild_sorters()
            self._refresh_footer()

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
        info = next((i for i in self.c.infos if i["name"] == name), None)
        if info is None:
            return
        if info.get("runnable"):
            self._set_active_by_name(name)
        elif info.get("group") == "docker":
            self._toggle_docker(offer_from=name)     # offer to enable Docker
        else:
            hint = ("needs a GPU build installed — see Help" if info.get("group") == "gpu"
                    else "not available on this computer")
            self._last = Text(f"{name}: {hint}", style="#f0883e")
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
        self._rebuild_sorters()
        self._rebuild_actions()
        self._last = Text(f"Docker sorters {'on' if on else 'off'}",
                          style=f"bold {self._accent}")
        self._refresh_footer()
        self._relayout()

    def _activate_action(self, key: str) -> None:
        self._sorter_hint = None   # an action result takes the footer over the highlight hint
        if key == "quit":
            self.exit()
        elif key == "theme":
            self._open_theme()
        elif key == "help":
            self.action_help()
        elif key == "params":
            self._open_params()
        elif self._needs_data(key) and not self.c.data_report.get("present"):
            # Guarded BEFORE the sort branch so sort can't open its modal with no data.
            self._last = Text("✗ ", style="bold #f85149") + Text(
                f"{key} needs the recording files — press d for help")
            self._refresh_footer()
        elif key == "sort":
            self.push_screen(
                ChoiceModal("Sort how much?", [
                    ("full", "Full recording", ""),
                    ("quick", f"Quick test — first {self.c.quick_seconds}s", ""),
                ]),
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
            self._run("sort", span)

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
        self._last = Text(message, style="#3fb950" if ok else "#f85149")
        if changed:
            try:
                self.c.reload()
                self._rebuild_sorters()
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
        self._last = Text(message, style="#3fb950" if ok else "#f85149")
        try:
            if changed:
                self.c.reload()
                self._rebuild_sorters()
                self._rebuild_actions()
        except Exception as e:  # noqa: BLE001 - a reload failure must not kill the app
            self._last = Text(f"reload after {key} failed: {e!r}", style="#f85149")
        self._refresh_footer()
        self._relayout()
        self.refresh()


def _trunc(text: str, n: int) -> str:
    return text if len(text) <= n else text[: max(0, n - 1)] + "…"


def _param_to_str(value) -> str:
    """Render a scalar/None default for an Input field ('' for None)."""
    if value is None:
        return ""
    return str(value)
