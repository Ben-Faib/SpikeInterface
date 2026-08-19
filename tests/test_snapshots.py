"""Visual regression snapshots of the menu UI (pytest-textual-snapshot).

These pin the CURRENT dashboard and modals as SVG baselines so the D-track
redesign lands as reviewable visual diffs instead of silent churn. They assert
*what the whole screen looks like*, complementing the Pilot journey tests in
``test_menu_app.py`` (which assert behaviour and must stay layout-agnostic).

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

# Representative terminal sizes, matching the breakpoints the Pilot tests pin:
# full three-panel, narrow (stacked), and short (chrome yields so lists fit).
FULL = (110, 40)
NARROW = (60, 24)
SHORT = (100, 14)


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
    # The real journey (D5): the Docker toggle row lives in the sorter picker.
    # installed-not-running is the richest state ([s] start + [r] re-check).
    app = make_app(present=True)
    app.c.docker_state = "installed_not_running"

    async def open_modal(pilot):
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        picklist = pilot.app.screen.query_one("#picklist")
        picklist.highlighted = 0                    # the [ ] Docker toggle row
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


# --------------------------------------------------------------------------- #
# The unit triage screen (W1 slice 4)
# --------------------------------------------------------------------------- #
async def _open_triage(pilot):
    await pilot.pause()
    await pilot.press("u")
    await pilot.pause()


def test_triage_screen(snap_compare, make_app):
    # Mid-pass: two verdicts already recorded, the cursor on the third unit.
    app = make_app(present=True)
    app.c.labels["tridesclous2"] = {0: "good", 1: "noise"}
    assert snap_compare(app, terminal_size=FULL, run_before=_open_triage)


def test_triage_screen_default_terminal(snap_compare, make_app):
    # 80x24 stays fully usable: the list, the card and the verdict keys all fit.
    assert snap_compare(make_app(present=True), terminal_size=(80, 24),
                        run_before=_open_triage)


def test_triage_screen_refused(snap_compare, make_app):
    # The anchor refusal owns the screen's body: what happened + the next step.
    app = make_app(present=True)
    app.c.triage_blocked = (
        "this curation record was written against a different tridesclous2 sort - "
        "units: record 12, on disk 18. Unit ids are not stable across re-sorts, so "
        "replaying these decisions would curate the wrong units. Next step: write a "
        "fresh record against the sort now in outputs/tridesclous2/ - the old record "
        "stays as the audit trail of what was decided about that run.")
    assert snap_compare(app, terminal_size=FULL, run_before=_open_triage)
