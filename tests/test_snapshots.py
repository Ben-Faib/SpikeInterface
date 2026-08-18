"""Visual regression snapshots of the menu UI (pytest-textual-snapshot).

These pin the CURRENT dashboard and modals as SVG baselines so the D-track
redesign lands as reviewable visual diffs instead of silent churn. They assert
*what the whole screen looks like*, complementing the Pilot journey tests in
``test_menu_app.py`` (which assert behaviour and must stay layout-agnostic).

A snapshot failure is not automatically a bug: if the change is an intended
redesign, re-baseline deliberately — see ``tests/README.md``. Baselines live in
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

# Representative terminal sizes, matching the breakpoints the Pilot tests pin:
# full three-panel, narrow (stacked), and short (chrome yields so lists fit).
FULL = (110, 40)
NARROW = (60, 24)
SHORT = (100, 14)


class FrozenSortScreen(menu_app.SortProgressScreen):
    """SortProgressScreen with no subprocess and no spinner animation.

    ``_run`` is neutered so no worker injects a synthetic done event, and
    ``_tick_spinner`` is a no-op so the heartbeat glyph stays at frame 0 —
    the screen renders only the synthetic events the test feeds it.
    """

    async def _run(self) -> None:
        pass

    def _tick_spinner(self) -> None:
        pass


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
# The dashboard at the three representative sizes
# --------------------------------------------------------------------------- #

def test_dashboard_full(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=FULL)


def test_dashboard_narrow_stacked(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=NARROW)


def test_dashboard_short(snap_compare, make_app):
    assert snap_compare(make_app(present=True), terminal_size=SHORT)


def test_dashboard_no_data(snap_compare, make_app):
    # The honest empty state: pipeline FAILs, data-needing actions dimmed.
    assert snap_compare(make_app(present=False), terminal_size=FULL)


# --------------------------------------------------------------------------- #
# Modals
# --------------------------------------------------------------------------- #

def test_sort_span_modal(snap_compare, make_app):
    # Pressing 2 (sort) opens the span ChoiceModal, including the overwrite
    # caveat (the fake active sorter already has a 12-unit saved sort).
    async def open_modal(pilot):
        await pilot.pause()
        await pilot.press("2")
        await pilot.pause()

    assert snap_compare(make_app(present=True), terminal_size=FULL, run_before=open_modal)


def test_docker_confirm_modal(snap_compare, make_app):
    # The real journey: Enter on the SORTERS list opens the Docker confirm.
    # installed-not-running is the richest state ([s] start + [r] re-check).
    app = make_app(present=True)
    app.c.docker_state = "installed_not_running"

    async def open_modal(pilot):
        await pilot.pause()
        sorters = pilot.app.query_one("#sorters")
        sorters.highlighted = 0
        pilot.app.set_focus(sorters)
        await pilot.press("enter")
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
