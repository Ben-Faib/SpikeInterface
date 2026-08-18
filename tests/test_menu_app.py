"""Textual Pilot tests for the v2 dashboard (scripts/menu_app.py).

The dashboard is a simultaneous three-panel layout: SORTERS (#sorterpane) and
ACTIONS (#actionpane) are both always visible; ←/→ (and Tab/Shift-Tab) MOVE FOCUS
between them; a bottom INSPECTING panel (#inspect) follows the focused pane; and an
always-on two-line DATA/SORT banner (#databar / #sortbar) sits above the panes.

These tests exercise the requirements that motivated the redesign: usable at small
window sizes, an obvious + selectable active sorter, always-reachable actions, and
clear missing-data guidance.
"""
from __future__ import annotations

import menu_app
import ui
from textual.widgets import OptionList, Static


def _sorter_row(app, name):
    ol = app.query_one("#sorters", OptionList)
    for i in range(ol.option_count):
        if ol.get_option_at_index(i).id == name:
            return i
    raise AssertionError(f"sorter row {name!r} not found")


# --- three-panel layout + focus nav -------------------------------------- #
async def test_boots_with_both_lists_and_sorter_focus(make_app):
    # Launch state: BOTH lists are visible, the actions list is fully populated, and
    # the SORTERS pane is focused with the cursor on the active sorter.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        actions = app.query_one("#actions", OptionList)
        assert sorters.get_option_at_index(0).id == "__docker__"
        assert actions.option_count == 15   # 13 actions + the gap + MANAGE header
        assert sorters.display is True and actions.display is True
        assert sorters.highlighted == _sorter_row(app, "tridesclous2")
        assert app.focused is sorters


async def test_both_lists_visible_and_focus_moves(make_app):
    app = make_app()
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters")
        actions = app.query_one("#actions")
        # both always visible now
        assert sorters.display is True and actions.display is True
        assert app.focused is sorters
        await pilot.press("right")
        await pilot.pause()
        assert app.focused is actions
        await pilot.press("left")
        await pilot.pause()
        assert app.focused is sorters
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is actions
        await pilot.press("shift+tab")
        await pilot.pause()
        assert app.focused is sorters


async def test_down_moves_action_highlight(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")        # focus ACTIONS
        await pilot.pause()
        actions = app.query_one("#actions", OptionList)
        assert actions.highlighted == 0
        await pilot.press("down")
        await pilot.pause()
        assert actions.highlighted == 1


async def test_jk_navigation(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")        # focus ACTIONS
        await pilot.pause()
        actions = app.query_one("#actions", OptionList)
        await pilot.press("j")
        await pilot.pause()
        assert actions.highlighted == 1
        await pilot.press("k")
        await pilot.pause()
        assert actions.highlighted == 0


# --- DATA / SORT banner --------------------------------------------------- #
async def test_databar_healthy_lists_streams(make_app):
    app = make_app()                       # FakeController(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        data = app.query_one("#databar").render().plain
        assert "✓" in data and ("LFP" in data or "stream" in data.lower())


async def test_databar_broken_is_loud(make_app):
    app = make_app(present=False)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        data = app.query_one("#databar").render().plain
        assert "✗" in data and ("no recording" in data.lower() or "press f" in data.lower())


async def test_databar_unreadable_broadband_is_loud(make_app):
    app = make_app(present=True)
    app.c.pipeline[1]["status"] = "FAIL"   # Broadband (.ns5) row
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        data = app.query_one("#databar").render().plain
        assert "✗" in data and "Broadband" in data and "won't load" in data


async def test_sortbar_shows_active_and_readiness(make_app):
    app = make_app()
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sort = app.query_one("#sortbar").render().plain
        assert "tridesclous2" in sort and "Ready" in sort


async def test_sortbar_follows_active_sorter(make_app):
    c_app = make_app()
    async with c_app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("t")             # cycle to spykingcircus2
        await pilot.pause()
        assert "spykingcircus2" in c_app.query_one("#sortbar").render().plain


async def test_action_title_is_static_actions(make_app):
    # One fact, one place (§1.1, D1 review #5): the SORT banner is the active
    # sorter's only at-rest home — the pane title no longer restates it.
    app = make_app()
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        title = str(app.query_one("#actionpane").border_title)
        assert title == "ACTIONS"
        assert "tridesclous2" in app.query_one("#sortbar").render().plain


# --- merged INSPECTING ---------------------------------------------------- #
async def test_inspect_follows_focused_pane(make_app):
    app = make_app()
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        body = app.query_one("#inspectbody").render().plain
        assert "tridesclous2" in body          # sorter highlighted at boot
        await pilot.press("right")             # focus ACTIONS (row 0 = explore)
        await pilot.pause()
        body = app.query_one("#inspectbody").render().plain
        assert "figures" in body.lower() or "explore" in body.lower()


async def test_inspect_shows_block_reason_for_nonrunnable_sorter(make_app):
    # Highlighting a non-runnable (Docker) sorter must show WHY it can't run in the
    # INSPECTING panel — spec State A.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = _sorter_row(app, "mountainsort5")   # group=docker, not runnable
        await pilot.pause()
        body = app.query_one("#inspectbody", Static).render().plain
        assert "Docker" in body                                   # block reason / how to enable


# --- sorter activation + cycle -------------------------------------------- #
async def test_enter_on_sorter_sets_active(make_app):
    # Enter on a runnable sorter activates it AND moves focus to the ACTIONS pane.
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = _sorter_row(app, "spykingcircus2")
        app.set_focus(sorters)
        await pilot.press("enter")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"
        # focus moved to the (always-visible) actions list; SORT banner names it
        assert app.focused is app.query_one("#actions", OptionList)
        assert "spykingcircus2" in app.query_one("#sortbar").render().plain


async def test_space_selects_sorter(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = _sorter_row(app, "spykingcircus2")
        app.set_focus(sorters)
        await pilot.press("space")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"


async def test_t_cycles_sorter(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert c.active_sorter == "tridesclous2"
        await pilot.press("t")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"
        await pilot.press("t")
        await pilot.pause()
        assert c.active_sorter == "tridesclous2"


async def test_active_marker_in_sorter_row(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        row = _sorter_row(app, "tridesclous2")
        prompt = sorters.get_option_at_index(row).prompt.plain
        # D1 signal budget: the active sorter is marked by the left-bar SHAPE only —
        # no ACTIVE chip, no ★ (the SORT banner is that fact's home).
        assert prompt.startswith("▌")
        assert "ACTIVE" not in prompt and "★" not in prompt


# --- responsive ladder ---------------------------------------------------- #
async def test_narrow_stacks_and_keeps_both_lists(make_app):
    app = make_app()
    async with app.run_test(size=(60, 24)) as pilot:
        await pilot.pause()
        assert app.query_one("#body").has_class("stacked")
        for wid in ("#sorters", "#actions"):
            r = app.query_one(wid).region
            assert r.intersection(app.screen.region).height > 0


async def test_tiny_never_clips_lists(make_app):
    for size in [(40, 12), (30, 8), (24, 6), (20, 5)]:
        app = make_app()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for wid in ("#sorters", "#actions"):
                vis = app.query_one(wid).region.intersection(app.screen.region)
                assert vis.height > 0, f"{wid} clipped at {size}"
            assert app.is_running


async def test_tiny_never_clips_lists_when_data_broken(make_app):
    # The loud DATA line is a fixed one row now, so the lists still never clip even
    # with broken data at the shortest sizes.
    for size in [(40, 12), (30, 8), (24, 6), (20, 5)]:
        app = make_app(present=False)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for wid in ("#sorters", "#actions"):
                vis = app.query_one(wid).region.intersection(app.screen.region)
                assert vis.height > 0, f"{wid} clipped at {size}"
            assert app.is_running


async def test_crest_drops_before_lists(make_app):
    app = make_app()
    async with app.run_test(size=(100, 14)) as pilot:
        await pilot.pause()
        assert app.query_one("#crest").display is False


async def test_inspect_hidden_on_extreme_short(make_app):
    # On an extreme-short window the INSPECTING panel is hidden so the lists keep
    # their rows; the lists themselves stay on screen.
    app = make_app()
    async with app.run_test(size=(100, 14)) as pilot:
        await pilot.pause()
        assert app.query_one("#inspect").has_class("hidden")
        for wid in ("#sorters", "#actions"):
            vis = app.query_one(wid).region.intersection(app.screen.region)
            assert vis.height > 0


async def test_resize_wide_to_narrow_to_wide(make_app):
    app = make_app()
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause()
        assert not app.query_one("#body").has_class("stacked")
        await pilot.resize_terminal(50, 30)
        await pilot.pause()
        assert app.query_one("#body").has_class("stacked")
        await pilot.resize_terminal(120, 44)
        await pilot.pause()
        assert not app.query_one("#body").has_class("stacked")


async def test_actions_stay_on_screen_at_every_size(make_app):
    # The redesign's core promise: the actions list is never pushed off-screen.
    for size in [(77, 24), (60, 22), (50, 18), (40, 12), (34, 30)]:
        app = make_app(present=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            actions = app.query_one("#actions", OptionList)
            visible = actions.region.intersection(app.screen.region)
            assert visible.height > 0, f"Actions off-screen at {size}: {actions.region}"


# --- missing data --------------------------------------------------------- #
async def test_missing_data_dims_actions(make_app):
    app = make_app(present=False)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        # loud DATA line
        assert "✗" in app.query_one("#databar").render().plain
        # data-dependent actions disabled; help/verify/theme/quit are not
        actions = app.query_one("#actions", OptionList)
        by_id = {o.id: o for o in actions._options}
        assert by_id["explore"].disabled is True
        assert by_id["verify"].disabled is False
        assert by_id["help"].disabled is False


async def test_help_screen_opens_via_d_at_data_topic(make_app):
    app = make_app(present=False)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")            # d -> Help, jumped to the Data files topic
        await pilot.pause()
        assert isinstance(app.screen, menu_app.HelpScreen)
        body = app.screen.query_one("#helpbody", Static).render().plain
        assert ".ns5" in body and ".ns2" in body and ".nev" in body
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.HelpScreen)


async def test_help_screen_opens_via_question_mark(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")   # the ? key
        await pilot.pause()
        assert isinstance(app.screen, menu_app.HelpScreen)
        assert "spike sorting" in app.screen.query_one("#helpbody", Static).render().plain.lower()


async def test_help_action_runs(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")        # focus actions
        await pilot.pause()
        actions = app.query_one("#actions", OptionList)
        idx = next(i for i in range(actions.option_count)
                   if actions.get_option_at_index(i).id == "help")
        actions.highlighted = idx
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.HelpScreen)


async def test_data_help_shows_stream_detail(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        body = app.screen.query_one("#helpbody", Static).render().plain
        assert "30000 Hz" in body or "22 ch" in body     # per-stream detail present


# --- theme / params / number-key dispatch --------------------------------- #
async def test_theme_modal_changes_accent(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        before = app._accent
        app._open_theme()              # opens the accent picker modal
        await pilot.pause()
        await pilot.press("down")      # move off the current theme
        await pilot.press("enter")     # choose it
        await pilot.pause()
        assert app._accent != before
        assert app._accent == c.accent


async def test_number_key_opens_param_editor(make_app):
    # D1: params is a MANAGE action on the letter `e`; numbers are workflow-only,
    # so "7" must be a no-op (there are six workflow actions).
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("7")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.ParamEditorScreen)
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ParamEditorScreen)


async def test_action_run_path_is_guarded(make_app):
    # A non-data action (verify) runs via the suspend() path; under the headless test
    # driver suspend() is unsupported, so the guard must fall back to an in-place run
    # instead of crashing. After 'probe' was inserted at index 8 (key "9"), verify
    # shifted to index 9 (the 10th slot) and lost its single-digit key. Navigate to
    # it by option id instead.
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        # Focus the ACTIONS pane and highlight the verify option by id.
        actions = app.query_one("#actions", OptionList)
        verify_idx = next(
            i for i in range(actions.option_count)
            if actions.get_option_at_index(i).id == "verify"
        )
        actions.highlighted = verify_idx
        actions.focus()
        await pilot.press("enter")      # verify (navigated to by id, not number key)
        await pilot.pause()
        assert ("verify", None) in c.ran
        assert app.is_running           # did not crash out


async def test_disabled_action_does_not_run(make_app):
    # With no data, a data-dependent action is blocked (not dispatched).
    app = make_app(present=False)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("1")          # explore (needs data)
        await pilot.pause()
        assert c.ran == []
        assert "needs" in app.query_one("#footer", Static).render().plain.lower()


async def test_sort_opens_progress_screen(make_app):
    # Sort now runs IN-UI: the span ChoiceModal first, then (on confirm) a
    # SortProgressScreen that spawns the sort subprocess — not the old suspend+stdout
    # _run path. The FakeController.sort_command returns ['true'] so the worker
    # spawns + exits cleanly.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")      # focus the ACTIONS pane
        await pilot.press("2")          # sort -> opens the span modal
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)   # span picker first
        await pilot.press("enter")      # choose the highlighted "full"
        await pilot.pause()
        assert isinstance(app.screen, menu_app.SortProgressScreen)


async def test_sort_progress_screen_renders_events(make_app):
    # Drive the screen with synthetic events (no real subprocess) via the
    # synchronous handle_event hook, then assert the phase checklist + done line.
    import sort_progress as sp  # noqa: F401 - imported for symmetry with the emitter
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = menu_app.SortProgressScreen(["true"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        for ev in [
            {"t": "phase", "i": 1, "n": 4, "title": "Read broadband"},
            {"t": "bar", "desc": "detect", "frac": 0.5, "n": 5, "total": 10},
            {"t": "phase", "i": 2, "n": 4, "title": "Run sorter"},
            {"t": "done", "ok": True, "units": 13, "out": "outputs/tridesclous2"},
        ]:
            screen.handle_event(ev)        # synchronous reducer + render
            await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "Read broadband" in body and "Run sorter" in body
        assert ("13" in body or "Done" in body)
        assert screen._state["done"]["ok"] is True
        foot = screen.query_one("#sortfoot").render().plain
        assert "Enter" in foot


async def test_sort_progress_renders_summary_card_and_note(make_app):
    # The array/yield headline card shows on the final screen, and a non-fatal
    # metrics caveat (done.note) renders as a ⚠ line alongside the ✓ success — so a
    # metrics hiccup never masquerades as a total failure.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = menu_app.SortProgressScreen(["true"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        for ev in [
            {"t": "phase", "i": 4, "n": 4, "title": "Quality metrics"},
            {"t": "summary", "card": ["V_pp: 22.9 µV", "yield (% active electrodes): 43.8% (7/16)"],
             "summary": {"n_units": 7}},
            {"t": "done", "ok": True, "units": 7, "out": "outputs/x",
             "note": "quality metrics failed: ValueError: boom"},
        ]:
            screen.handle_event(ev)
            await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "Array / yield summary" in body and "V_pp: 22.9" in body
        assert "Done" in body and "7 units" in body
        assert "quality metrics failed" in body          # non-fatal caveat surfaced


async def test_sort_progress_surfaces_real_error_from_log(make_app, tmp_path):
    # End-to-end: a subprocess that dies non-zero WITHOUT emitting a done/error event
    # (a hard crash) must not collapse to a blank "sort exited (1)". The screen
    # captures the child's stderr to the log, then surfaces its tail as the real cause.
    log = tmp_path / "sort.log"
    argv = ["sh", "-c",
            "echo 'TypeError: unexpected keyword argument gap_tolerance_ms' >&2; exit 1"]
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = menu_app.SortProgressScreen(argv, app._accent, log_path=str(log))
        await app.push_screen(screen)
        # Let the worker spawn the child, capture its stderr, exit, and synthesise the
        # close state from the non-zero return code + the captured tail.
        for _ in range(100):
            await pilot.pause()
            if screen._state["done"] is not None:
                break
        assert screen._state["done"] is not None
        assert screen._state["done"]["ok"] is False
        body = screen.query_one("#sortbody").render().plain
        assert "exited (1)" in body
        assert "gap_tolerance_ms" in body          # the REAL cause, not just the exit code


async def test_sort_progress_renders_substep_and_detail(make_app):
    # Under the current (▶) phase the screen renders both the named substep
    # (→ name (i/n)) and the latest forwarded sorter step line (→ detail), and they
    # coexist with the heartbeat spinner — none of them fight. Neuter the worker so
    # the screen stays mid-sort (no auto-injected 'done' wipes the live view).
    class _NoRun(menu_app.SortProgressScreen):
        async def _run(self):
            pass

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = _NoRun(["true"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        for ev in [
            {"t": "phase", "i": 2, "n": 4, "title": "Run sorter"},
            {"t": "detail", "text": "detect_peaks: 562 peaks found"},
            {"t": "substep", "name": "computing waveforms", "i": 2, "n": 8},
            {"t": "heartbeat", "label": "sorting", "secs": 12},
        ]:
            screen.handle_event(ev)
            await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "computing waveforms" in body and "2/8" in body       # substep line
        assert "detect_peaks: 562 peaks found" in body               # forwarded detail
        assert "still working" in body and "12s" in body             # heartbeat coexists
        # a new phase clears the prior substep/detail (reducer contract)
        screen.handle_event({"t": "phase", "i": 3, "n": 4, "title": "Quality metrics"})
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "computing waveforms" not in body
        assert "detect_peaks: 562 peaks found" not in body


async def test_sort_modal_warns_before_overwriting(make_app):
    # active sorter (tridesclous2) already has a saved sort in the fake universe.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")          # action 2 = sort -> span modal
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)
        note = app.screen.query_one("#dialognote", Static).render().plain
        assert "already has a saved sort" in note


async def test_sort_blocked_without_data(make_app):
    # sort is data-dependent: with no data it must be refused BEFORE its span modal.
    app = make_app(present=False)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")          # sort
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.ChoiceModal)
        assert c.ran == []
        assert "needs" in app.query_one("#footer", Static).render().plain.lower()


async def test_sort_blocked_when_active_needs_docker_thats_down(make_app):
    app = make_app(present=True)
    c = app.c
    c.active_blocked_on_docker = lambda: True       # container sorter, daemon down
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")          # sort
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.ChoiceModal)   # guarded, no modal
        assert app._last is not None and "Docker" in app._last.plain


# --- docker toggle -------------------------------------------------------- #
async def test_docker_toggle_row_is_first_and_toggles(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        assert sorters.get_option_at_index(0).id == "__docker__"
        assert next(i for i in c.infos if i["name"] == "mountainsort5")["runnable"] is False
        sorters.highlighted = 0           # the Docker toggle row
        app.set_focus(sorters)
        await pilot.press("enter")        # opens the confirm dialog (state defaults to running)
        await pilot.pause()
        app.screen.action_enable()
        await pilot.pause()
        assert c.use_docker is True
        assert next(i for i in c.infos if i["name"] == "mountainsort5")["runnable"] is True


async def test_toggle_does_not_change_active_sorter(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        app.set_focus(sorters)
        await pilot.press("enter")        # toggle docker
        await pilot.pause()
        assert c.active_sorter == "tridesclous2"   # active sorter unchanged


async def test_docker_enable_opens_confirm_when_running(make_app):
    app = make_app(present=True)
    c = app.c
    c.docker_state = "running"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        app.set_focus(sorters)
        await pilot.press("enter")        # turning ON -> confirm dialog
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DockerConfirmScreen)
        assert "running" in app.screen.query_one("#dstatus", Static).render().plain.lower()
        assert c.use_docker is False      # not enabled until confirmed


async def test_docker_confirm_enable_turns_on(make_app):
    app = make_app(present=True)
    c = app.c
    c.docker_state = "running"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        app.set_focus(sorters)
        await pilot.press("enter")
        await pilot.pause()
        app.screen.action_enable()        # the [Enable] button/action
        await pilot.pause()
        assert c.use_docker is True


async def test_docker_confirm_not_installed_shows_download(make_app):
    app = make_app(present=True)
    c = app.c
    c.docker_state = "not_installed"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        app.set_focus(sorters)
        await pilot.press("enter")
        await pilot.pause()
        body = app.screen.query_one("#dstatus", Static).render().plain.lower()
        assert "don't have docker" in body or "download" in body


async def test_docker_confirm_start_calls_controller(make_app):
    app = make_app(present=True)
    c = app.c
    c.docker_state = "installed_not_running"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        app.set_focus(sorters)
        await pilot.press("enter")
        await pilot.pause()
        app.screen.action_start_docker()  # [Start Docker for me]
        await pilot.pause()
        assert c.started_docker is True


# --- docker image download (Stage 4) -------------------------------------- #
async def test_docker_row_shows_download_badge(make_app):
    # A Docker sorter whose image isn't cached shows the "get it" badge; a cached
    # one shows "ready" — both states drawn straight on the catalog row.
    app = make_app()
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        labels = {sorters.get_option_at_index(i).id:
                  sorters.get_option_at_index(i).prompt.plain
                  for i in range(sorters.option_count)}
        # D1 availability glyphs: with Docker OFF both docker rows are obtainable
        # (◌); the cached-vs-not detail lives in INSPECTING now. The legend is the
        # pane's border subtitle.
        assert labels["mountainsort5"].rstrip().endswith("◌")
        assert labels["herdingspikes"].rstrip().endswith("◌")
        assert "●" in labels["tridesclous2"]         # runnable now
        assert app.query_one("#sorterpane").border_subtitle


async def test_docker_on_glyph_honest_about_pull(make_app):
    # Docker ON: a cached image really runs on Enter (●); an uncached one would
    # start a multi-GB pull first, so it stays ◌ — a ● over a download is a lie
    # (D1 review #2).
    app = make_app(use_docker=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        labels = {sorters.get_option_at_index(i).id:
                  sorters.get_option_at_index(i).prompt.plain
                  for i in range(sorters.option_count)}
        assert labels["herdingspikes"].rstrip().endswith("●")    # cached + toggle on
        assert labels["mountainsort5"].rstrip().endswith("◌")    # needs the pull


async def test_inspecting_carries_cached_vs_not(make_app):
    # The distinction the row glyph elides lives in INSPECTING (spec §2/critique #6).
    app = make_app(use_docker=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._highlight_sorter_by_name("mountainsort5")
        await pilot.pause()
        assert "not downloaded" in app.query_one("#inspectbody", Static).render().plain
        app._highlight_sorter_by_name("herdingspikes")
        await pilot.pause()
        assert "cached" in app.query_one("#inspectbody", Static).render().plain


async def test_enter_on_undownloaded_docker_opens_download(make_app):
    # With Docker on and the daemon running, Enter on an un-cached Docker sorter
    # opens the in-UI download (separate from running a sort).
    app = make_app(use_docker=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._highlight_sorter_by_name("mountainsort5")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DownloadProgressScreen)


async def test_download_shows_telemetry_then_collapses_and_expands(make_app):
    import threading
    app = make_app(present=True, use_docker=True)
    app.c.dl_gate = threading.Event()           # hold the worker at the gate step
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        # Start the gated download directly (avoids depending on row indices).
        app.start_download("mountainsort5")
        await pilot.pause()
        # The expanded modal is up and shows the stats line (downloaded/total + /s).
        screen = app.screen
        assert isinstance(screen, menu_app.DownloadProgressScreen)
        await pilot.pause()
        body = app.screen.query_one("#dlbody", Static).render().plain
        assert "100" in body or "/" in body   # a size readout rendered
        assert "complete" not in body.lower()   # never a false "complete" mid-pull
        # Collapse: modal closes, the dashboard indicator shows.
        await pilot.press("c")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.DownloadProgressScreen)
        dlbar = app.query_one("#dlbar", Static)
        assert dlbar.has_class("hidden") is False
        assert "mountainsort5" in dlbar.render().plain
        # Re-expand with w.
        await pilot.press("w")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DownloadProgressScreen)
        # Let the worker finish. With the session-scoped clear timer, `_download`
        # is only nulled 4s after finish, so poll the session's own result flag.
        sess = app._download
        app.c.dl_gate.set()
        for _ in range(50):
            await pilot.pause()
            if sess.result is not None:
                break
        assert sess.result is not None
        assert "mountainsort5" in app.c.downloaded
        # The catalog badge flips: the freshly-pulled image now reads as present.
        ms = next(i for i in app.c.infos if i["name"] == "mountainsort5")
        assert ms["img_present"] is True


async def test_download_cancel_sets_flag_and_closes(make_app):
    # Escape on the expanded download modal cancels: it sets the session's cancel
    # flag (the worker's should_cancel hook breaks the pull) and closes the modal.
    import threading
    app = make_app(present=True, use_docker=True)
    app.c.dl_gate = threading.Event()           # hold the worker at the gate step
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.start_download("mountainsort5")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DownloadProgressScreen)
        sess = app._download
        await pilot.press("escape")             # the screen's action_cancel
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.DownloadProgressScreen)
        assert sess.cancelled is True
        assert app._download is None or app._download.cancelled is True
        # Release the gate so the worker exits cleanly (returns a cancelled result).
        app.c.dl_gate.set()
        for _ in range(50):
            await pilot.pause()
            if sess.result is not None:
                break


async def test_download_indicator_hidden_when_idle(make_app):
    app = make_app(present=True, use_docker=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert app.query_one("#dlbar", Static).has_class("hidden") is True


async def test_enter_on_undownloaded_docker_offers_docker_when_daemon_down(make_app):
    # Same row, but the Docker daemon isn't running: Enter must guide the user to
    # start Docker first (the confirm dialog), not open a download that can't run.
    app = make_app(use_docker=True)
    app.c.docker_state = "installed_not_running"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._highlight_sorter_by_name("mountainsort5")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DockerConfirmScreen)


async def test_docker_off_is_immediate(make_app):
    app = make_app(present=True, use_docker=True)   # already on
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert c.use_docker is True
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        app.set_focus(sorters)
        await pilot.press("enter")        # turning OFF -> immediate, no dialog
        await pilot.pause()
        assert c.use_docker is False
        assert not isinstance(app.screen, menu_app.DockerConfirmScreen)


# --- param editor --------------------------------------------------------- #
async def test_param_editor_saves_only_changed_keys(make_app):
    from textual.widgets import Input
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._open_params()
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ParamEditorScreen)
        field = app.screen.query_one("#w_detect_threshold", Input)
        field.value = "6.5"
        app.screen.action_save()
        await pilot.pause()
        assert c.params_set is not None
        sorter, overrides = c.params_set
        assert sorter == "tridesclous2"
        assert overrides == {"detect_threshold": 6.5}  # only the changed key


async def test_param_editor_reset_clears_overrides(make_app):
    app = make_app(present=True)
    c = app.c
    c.sorter_params["tridesclous2"] = {"detect_threshold": 9.0}
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._open_params()
        await pilot.pause()
        app.screen.action_reset()
        await pilot.pause()
        assert c.params_set == ("tridesclous2", {})


async def test_param_editor_bad_value_shows_error_and_stays(make_app):
    from textual.widgets import Input
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._open_params()
        await pilot.pause()
        app.screen.query_one("#w_freq_min", Input).value = "notanumber"
        app.screen.action_save()
        await pilot.pause()
        # still on the editor, with an error message; nothing saved
        assert isinstance(app.screen, menu_app.ParamEditorScreen)
        assert "freq_min" in app.screen.query_one("#perror", Static).render().plain
        assert c.params_set is None


# --- compare -------------------------------------------------------------- #
async def test_compare_opens_picker_when_two_saved(make_app):
    app = make_app(present=True)   # both sorters present in the fake
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("5")          # compare (workflow slot 5 in D1 order)
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)


async def test_compare_picks_pair_and_runs(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("5")          # compare -> first picker
        await pilot.pause()
        await pilot.press("enter")      # choose highlighted (tridesclous2)
        await pilot.pause()
        await pilot.press("enter")      # choose highlighted of the remaining
        await pilot.pause()
        assert c.ran_compare is not None
        assert len(c.ran_compare) == 2 and c.ran_compare[0] != c.ran_compare[1]


# --- welcome / data folder / esc ------------------------------------------ #
async def test_welcome_shows_when_wanted(make_app):
    app = make_app(present=True)
    app.c.want_welcome = True
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, menu_app.WelcomeScreen)
        await pilot.press("enter")        # [Get started] dismisses + marks seen
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.WelcomeScreen)
        assert app.c.welcome_seen is True


async def test_welcome_hidden_when_seen(make_app):
    app = make_app(present=True)   # want_welcome defaults False
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.WelcomeScreen)


async def test_escape_does_not_quit_the_app(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.is_running           # Esc no longer hard-quits the dashboard


async def test_f_opens_data_folder_picker_and_sets_dir(make_app):
    from textual.widgets import Input
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DataFolderScreen)
        app.screen.query_one("#dfinput", Input).value = ""    # blank -> repo root
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.DataFolderScreen)
        assert getattr(c, "data_dir_set", "unset") is None    # "" coerced to None


# --- x manage (per-sorter) + Manage hub ----------------------------------- #
async def test_x_opens_manage_for_saved_sorter(make_app):
    # Highlight a sorter that has a saved sort, press x -> the per-sorter manage
    # confirm opens and offers to clear the saved sort.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._highlight_sorter_by_name("tridesclous2")   # has saved units in the fake
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ManageSorterScreen)
        body = app.screen.query_one("#mgbody").render().plain
        assert "saved" in body.lower()


async def test_x_clears_saved_sort_via_manage(make_app):
    # Choosing "clear saved sort" in the per-sorter manage dialog calls the
    # controller and reloads so the row's saved state flips.
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._highlight_sorter_by_name("tridesclous2")
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ManageSorterScreen)
        await pilot.press("enter")        # the clear-saved-sort option is the cursor
        await pilot.pause()
        assert "tridesclous2" in c.cleared_sorts
        td = next(i for i in c.infos if i["name"] == "tridesclous2")
        assert td["present"] is False


async def test_x_on_nothing_to_delete_hints(make_app):
    # A READY sorter with no saved sort + no Docker image: x has nothing to do, so
    # it must NOT open the modal — it just sets a footer hint.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._highlight_sorter_by_name("spykingcircus2")   # ready, no saved sort? it has 7u
        await pilot.pause()
        # spykingcircus2 actually has a saved sort; use a docker row with no image.
        app._highlight_sorter_by_name("mountainsort5")    # docker, no image, no sort
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.ManageSorterScreen)
        foot = app.query_one("#footer", Static).render().plain
        assert "nothing to delete" in foot.lower()


async def test_x_offers_image_delete_for_cached_docker(make_app):
    # A Docker sorter whose image is cached offers "Delete downloaded image".
    app = make_app(use_docker=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._highlight_sorter_by_name("herdingspikes")    # cached image in the fake
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ManageSorterScreen)
        body = app.screen.query_one("#mgbody").render().plain
        assert "image" in body.lower() and "gb" in body.lower()


async def test_manage_action_opens_hub(make_app):
    # D1: 'manage' is a MANAGE action on the letter `m`. Pressing it opens the hub.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ManageSortersScreen)


async def test_manage_hub_clears_saved_sort(make_app):
    # In the hub, pressing 'c' on a saved sorter clears it via the controller.
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.ManageSortersScreen)
        # the hub list starts on the first sorter (tridesclous2, saved); 'c' asks first
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)   # confirm before clearing
        assert "tridesclous2" not in c.cleared_sorts          # nothing cleared yet
        await pilot.press("enter")                            # confirm (cursor on "Clear saved sort")
        await pilot.pause()
        assert "tridesclous2" in c.cleared_sorts


async def test_manage_hub_deletes_image(make_app):
    # In the hub, pressing 'x' on a cached Docker sorter deletes its image.
    app = make_app(use_docker=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.ManageSortersScreen)
        screen._highlight_by_name("herdingspikes")        # cached image
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)   # confirm before deleting
        assert "herdingspikes" not in c.deleted_images        # nothing deleted yet
        await pilot.press("enter")                            # confirm (cursor on "Delete image")
        await pilot.pause()
        assert "herdingspikes" in c.deleted_images


def test_result_style_amber_for_warning():
    assert menu_app._result_style(True, "✓ Sorted x (5 units)") == "#3fb950"
    assert menu_app._result_style(True, "⚠ x: no units found") == "#f0883e"
    assert menu_app._result_style(False, "✗ Sorted x") == "#f85149"


# --- wordmark crest ------------------------------------------------------- #
def test_wordmark_tiers_equal_width():
    for tier in (ui._WORDMARK_FULL, ui._WORDMARK_COMPACT):
        widths = {len(row) for row in tier}
        assert len(widths) == 1, f"ragged wordmark tier widths: {widths}"


def test_wordmark_uses_only_block_and_space():
    chars = {ch for row in ui._WORDMARK_FULL for ch in row}
    assert chars <= {"█", " "}, f"non-block glyphs in wordmark: {chars}"


def test_pick_wordmark_drops_then_hides():
    assert ui.pick_wordmark(200, 60) == ui._WORDMARK_FULL          # roomy -> full
    assert ui.pick_wordmark(200, 60, reserve=58) == ui._WORDMARK_COMPACT  # short -> compact
    assert ui.pick_wordmark(4, 60) == []                            # too narrow -> hidden


def test_wordmark_rows_colours_blocks_with_accent():
    rows = ui.wordmark_rows(ui._WORDMARK_FULL, "#abcdef")
    styles = {s for row in rows for s, seg in row if seg.strip()}
    assert styles == {"#abcdef"}                                    # every block run is accent
    # width is preserved row-for-row
    for src, frags in zip(ui._WORDMARK_FULL, rows):
        assert sum(len(seg) for _, seg in frags) == len(src)


async def test_dashboard_crest_is_the_wordmark(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest.display is True
        plain = crest.render().plain
        assert "█" in plain                          # block letters
        assert "━" not in plain                      # not the old axon glyph


async def test_crest_has_no_animation(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        # Our animation machinery is gone. Assert on attrs that are unambiguously
        # ours (NB: not Textual's own ``_animate`` BoundAnimator slot, which every
        # Widget carries regardless of version).
        assert not hasattr(crest, "_tick")
        assert not hasattr(crest, "set_animate")
        assert not hasattr(crest, "_phase")


async def test_crest_recolours_with_theme(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        before = {s for s, _ in crest._tier_fragments()}   # accent style in use
        app.c.theme_name = "amber"                          # fake controller swaps accent
        # drive the theme-applied path directly (no modal in the test)
        app._accent = app.c.themes["amber"]
        app._relayout()
        after = {s for s, _ in crest._tier_fragments()}
        assert before != after


async def test_welcome_screen_shows_pitt_shield(make_app):
    app = make_app(present=True)
    app.c.want_welcome = True                          # first-launch greeting
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, menu_app.WelcomeScreen)
        crest = app.screen.query_one("#wcrest", Static).render().plain
        assert "█" in crest                            # blue+gold shield (block art)


async def test_help_about_topic_shows_pitt_shield(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(menu_app.HelpScreen(c, c.accent, topic="about"))
        await pilot.pause()
        body = app.screen.query_one("#helpbody", Static).render().plain
        assert "█" in body and "University of Pittsburgh" in body


# --- PROBE banner -------------------------------------------------------- #
async def test_probe_banner_shows_active_probe(make_app):
    # D1: DATA and PROBE share the inputs row — the merged banner shows the active
    # probe label (contains 'A1x16' for the FakeController default).
    app = make_app()
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        bar = app.query_one("#databar").render().plain
        assert "PROBE" in bar and "A1x16" in bar


# --- Sorter fit badge + INSPECTING fit line ------------------------------ #
async def test_inspecting_shows_fit_line(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        body = app.query_one("#inspectbody", Static)
        text = body.render().plain if hasattr(body.render(), "plain") else str(body.render())
        assert "Fit" in text


async def test_sorter_row_fit_badges(make_app):
    # D1 signal budget: rows carry NO fit badges at rest — fit detail lives in
    # INSPECTING for the row under the cursor. The availability glyph is the one
    # allowed mark beyond name + unit count.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        def plain(info):
            t = app._sorter_text(info)
            return t.plain if hasattr(t, "plain") else str(t)
        base = {"name": "x", "group": "ready", "runnable": True, "recommended": False,
                "present": False, "units": 0, "duration": 0.0, "active": False,
                "img_present": None}
        for fit in ({"rank": "good", "reason": "g"}, {"rank": "poor", "reason": "p"},
                    {"rank": "ok", "reason": "o"}):
            row = plain({**base, "fit": fit})
            assert "fits" not in row and "weak" not in row
        assert plain(base).rstrip().endswith("●")                       # runnable
        assert plain({**base, "runnable": False,
                      "group": "gpu"}).rstrip().endswith("–")           # not here
        assert plain({**base, "runnable": False,
                      "group": "docker"}).rstrip().endswith("◌")        # obtainable


# --- D1: the LAST RESULT line + r reopen ----------------------------------- #
async def test_last_result_bar_appears_and_reopens(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        # No result yet: the bar is hidden.
        assert app.query_one("#resultbar").has_class("hidden")
        # Run a workflow action that records a result (explore, via its number key).
        await pilot.press("1")
        await pilot.pause()
        bar = app.query_one("#resultbar")
        assert not bar.has_class("hidden")
        text = bar.render().plain
        assert "LAST" in text and "explore" in text and "r reopen" in text
        # r reopens the artifact through the controller.
        before = app.c.reopened
        await pilot.press("r")
        await pilot.pause()
        assert app.c.reopened == before + 1


async def test_footer_no_longer_echoes_active_sorter(make_app):
    # One fact, one place (DESIGN_UX §1): the SORT banner owns the active sorter;
    # the footer carries transient status + keys only.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        footer = app.query_one("#footer").render().plain
        assert "Active sorter:" not in footer
        sortbar = app.query_one("#sortbar").render().plain
        assert "tridesclous2" in sortbar



# --- D1 review #1: the yield budget actually feeds the lists ---------------- #
async def test_lists_get_real_rows_at_common_sizes(make_app):
    # Region-intersection > 0 can stay true for a starved pane; pin PAINTED room:
    # both panes keep enough rows for content at the sizes people actually use,
    # including 80x24 (the default macOS/Windows terminal).
    for size in [(110, 40), (100, 24), (80, 24), (60, 24)]:
        app = make_app(present=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for wid in ("#sorterpane", "#actionpane"):
                r = app.query_one(wid).region
                assert r.height >= 4, f"{wid} squeezed to {r.height} rows at {size}"


async def test_resultbar_visible_at_default_terminal(make_app):
    # The flagship "results don't evaporate" line must be PAINTED at 80x24, not
    # merely display=True while an ancestor clips it (D1 review #1).
    app = make_app(present=True)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("1")          # explore -> records a result
        await pilot.pause()
        bar = app.query_one("#resultbar")
        assert not bar.has_class("hidden") and not bar.has_class("collapsed")
        assert bar.region.height >= 1
        assert bar.region.y < app.size.height - 2   # above the docked footer


def test_fmt_when_relative_dates():
    from datetime import datetime, timedelta
    today = datetime.now().replace(hour=14, minute=18).isoformat(timespec="minutes")
    assert menu_app._fmt_when(today) == "14:18"
    old = (datetime.now() - timedelta(days=6)).replace(hour=9, minute=5)
    out = menu_app._fmt_when(old.isoformat(timespec="minutes"))
    assert out.endswith("09:05") and len(out) > len("09:05")   # carries its date
    assert menu_app._fmt_when("12:00") == "12:00"              # pre-ISO fallback
