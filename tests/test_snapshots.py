"""Visual regression snapshots of Spike 2.0 (pytest-textual-snapshot).

These pin the v2 app (the rail over Home and the stage panes, Settings, the
palette) and the modals it reuses as SVG baselines, so a redesign lands as
reviewable visual diffs instead of silent churn. They assert *what the whole
screen looks like*, complementing the Pilot tests in ``test_spike_app.py`` and
``test_menu_app.py`` (which assert behaviour and stay layout-agnostic).

A snapshot failure is not automatically a bug: if the change is an intended
redesign, re-baseline deliberately - see ``tests/README.md``. Baselines live in
``tests/__snapshots__/test_snapshots/``.

Everything runs over ``FakeController`` (no SpikeInterface, no recording), and
the sort-progress screen is frozen (no subprocess, no spinner animation) so
every snapshot is deterministic.
"""
from __future__ import annotations

import pytest_textual_snapshot

import menu_app  # conftest puts scripts/ on sys.path

# syrupy >= 5 renamed the extension attribute ``_file_extension`` ->
# ``file_extension``; pytest-textual-snapshot 1.0.0 still sets the old name, so
# baselines would land as ".raw". Point the new name at "svg" so the stored
# snapshots stay directly viewable SVG files. Guarded so a future plugin release
# that fixes the attribute itself makes this a no-op instead of a fight.
if getattr(pytest_textual_snapshot.SVGImageExtension, "file_extension", None) == "raw":
    pytest_textual_snapshot.SVGImageExtension.file_extension = "svg"

# Representative terminal sizes: a roomy window (the probe map shows), the
# default 80x24 terminal, and a narrow split pane.
FULL = (110, 40)
DEFAULT = (80, 24)
NARROW = (64, 22)


class FrozenSortScreen(menu_app.SortProgressScreen):
    """SortProgressScreen with no subprocess and no spinner animation.

    ``_run`` is neutered so no worker injects a synthetic done event, and
    ``_tick_spinner`` is a no-op so the heartbeat glyph stays at frame 0 -
    the screen renders only the synthetic events the test feeds it.
    """

    async def _run(self) -> None:
        pass

    def _tick_spinner(self) -> None:
        pass

    # Freeze the header's wall clock: a loaded machine crossing 1 s between push
    # and snapshot would otherwise flip the baseline's "0:00" (flaky snapshot).
    @staticmethod
    def _fmt_mmss(secs: float) -> str:
        return "0:00"


# A believable mid-sort event sequence: two phases done, the Sort phase live
# with a substep + forwarded sorter print + determinate bar + heartbeat all
# stacked (the "everything at once" rendering the redesign must preserve).
MID_SORT_EVENTS = [
    {"t": "phase", "i": 1, "n": 4, "title": "Read broadband", "sub": "(.ns5)"},
    {"t": "phase", "i": 2, "n": 4, "title": "Preprocess", "sub": "bandpass + common median reference"},
    {"t": "phase", "i": 3, "n": 4, "title": "Sort", "sub": "tridesclous2"},
    {"t": "detail", "text": "detect_peaks: 562 peaks found"},
    {"t": "substep", "name": "computing waveforms", "i": 2, "n": 8},
    {"t": "bar", "desc": "detect", "frac": 0.5, "n": 5, "total": 10},
    {"t": "heartbeat", "label": "running tridesclous2", "secs": 42},
]

# The final screen: all phases done, the six-metric array/yield card, and a
# success WITH a non-fatal metrics caveat (the ✓ + ⚠ coexistence contract).
DONE_EVENTS = [
    {"t": "phase", "i": 1, "n": 4, "title": "Read broadband", "sub": "(.ns5)"},
    {"t": "phase", "i": 2, "n": 4, "title": "Preprocess", "sub": "bandpass + common median reference"},
    {"t": "phase", "i": 3, "n": 4, "title": "Sort", "sub": "tridesclous2"},
    {"t": "phase", "i": 4, "n": 4, "title": "Quality metrics", "sub": "(SortingAnalyzer)"},
    {"t": "summary",
     "card": ["V_pp: 22.9 µV (median)", "SNR: 9.84 (median)", "noise floor: 3.96 µV",
              "yield (% active electrodes): 43.8% (7/16)", "units/ch: 0.44", "units/active-ch: 1.0"],
     "summary": {"n_units": 7}},
    {"t": "done", "ok": True, "units": 7, "good": 5, "out": "outputs/tridesclous2",
     "note": "quality metrics failed: ValueError: boom"},
]


# --------------------------------------------------------------------------- #
# Home, and each stage
# --------------------------------------------------------------------------- #
def _at(*keys):
    async def go(pilot):
        await pilot.pause()
        for k in keys:
            await pilot.press(k)
        await pilot.pause()
    return go


def test_home_full(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=FULL)


def test_home_default_terminal(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=DEFAULT)


def test_home_narrow(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=NARROW)


def test_home_no_data(snap_compare, make_app):
    # The honest empty state: the rail's 1 Data needs attention, the next step
    # is the recording.
    assert snap_compare(make_app(present=False), terminal_size=FULL)


def test_data_stage_no_data(snap_compare, make_app):
    assert snap_compare(make_app(present=False), terminal_size=FULL, run_before=_at("1"))


def test_probe_stage(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=FULL, run_before=_at("2"))


def test_sort_stage(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=FULL, run_before=_at("3"))


def test_judge_stage_with_evidence(snap_compare, make_app):
    # Mid-pass: two verdicts recorded, two units flagged, the evidence loaded.
    app = make_app(present=True)
    app.c.labels["tridesclous2"] = {0: "good", 1: "noise"}
    app.c.split_candidates = 2
    app.c.reload()

    async def go(pilot):
        await pilot.pause()
        await pilot.press("4")
        pane = pilot.app.query_one("#judge")
        for _ in range(200):
            await pilot.pause(0.02)
            if pane._ev:
                break
        await pilot.pause()

    assert snap_compare(app, terminal_size=FULL, run_before=go)


def test_judge_stage_default_terminal(snap_compare, make_app):
    async def go(pilot):
        await pilot.pause()
        await pilot.press("4")
        pane = pilot.app.query_one("#judge")
        for _ in range(200):
            await pilot.pause(0.02)
            if pane._ev:
                break
        await pilot.pause()

    assert snap_compare(make_app(present=True), terminal_size=DEFAULT, run_before=go)


def test_apply_stage(snap_compare, make_app):
    app = make_app(present=True)
    app.c.labels["tridesclous2"] = {0: "good", 1: "noise", 4: "unsure"}
    assert snap_compare(app, terminal_size=FULL, run_before=_at("5"))


def test_share_stage(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=FULL, run_before=_at("6"))


def test_settings_screen(snap_compare, make_app):
    app = make_app(present=True)
    app.c.cfg = {"sort_settings": {"freq_min": 250.0}, "quality_rule": {"snr_min": 5.0}}
    assert snap_compare(app, terminal_size=(110, 44), run_before=_at("comma"))


def test_palette(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=FULL,
                        run_before=_at("slash", "p", "h", "y"))


# --------------------------------------------------------------------------- #
# Modals
# --------------------------------------------------------------------------- #
def test_docker_confirm_modal(snap_compare, make_app):
    # installed-not-running is the richest state ([s] start + [r] re-check).
    app = make_app(present=True)
    app.c.docker_state = "installed_not_running"

    async def open_modal(pilot):
        await pilot.pause()
        pilot.app._toggle_docker()
        await pilot.pause()

    assert snap_compare(app, terminal_size=FULL, run_before=open_modal)


def test_sort_progress_mid_sort(snap_compare, make_app):
    app = make_app(present=True)

    async def push_and_feed(pilot):
        await pilot.pause()
        screen = FrozenSortScreen(["true"], pilot.app._accent)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        for ev in MID_SORT_EVENTS:
            screen.handle_event(ev)
        await pilot.pause()

    assert snap_compare(app, terminal_size=FULL, run_before=push_and_feed)


def test_sort_progress_done_with_note(snap_compare, make_app):
    app = make_app(present=True)

    async def push_and_feed(pilot):
        await pilot.pause()
        screen = FrozenSortScreen(["true"], pilot.app._accent)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        for ev in DONE_EVENTS:
            screen.handle_event(ev)
        await pilot.pause()

    assert snap_compare(app, terminal_size=FULL, run_before=push_and_feed)
