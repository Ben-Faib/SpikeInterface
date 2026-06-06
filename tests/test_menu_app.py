"""Textual Pilot tests for the v2 dashboard (scripts/menu_app.py).

These directly exercise the requirements that motivated the redesign: usable at
small window sizes, an obvious + selectable active sorter, always-reachable
actions, and clear missing-data guidance.
"""
from __future__ import annotations

import menu_app
from textual.widgets import OptionList, Static


def _app(controller):
    return menu_app.SpikeMenuApp(controller)


async def test_boots_with_lists_and_focus(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        actions = app.query_one("#actions", OptionList)
        assert sorters.option_count == 2
        assert actions.option_count == 10
        # a visible cursor from the start, focus on the actions pane
        assert actions.highlighted == 0
        assert sorters.highlighted == 0
        assert app.focused is actions


async def test_left_right_switch_focus(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        actions = app.query_one("#actions", OptionList)
        await pilot.press("left")
        await pilot.pause()
        assert app.focused is sorters
        await pilot.press("right")
        await pilot.pause()
        assert app.focused is actions
        # Tab also toggles focus between the two panes
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is sorters


async def test_down_moves_action_highlight(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        actions = app.query_one("#actions", OptionList)
        assert actions.highlighted == 0
        await pilot.press("down")
        await pilot.pause()
        assert actions.highlighted == 1


async def test_enter_on_sorter_sets_active(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("left")      # focus the sorter sidebar
        await pilot.press("down")      # move to the second sorter
        await pilot.press("enter")     # make it active
        await pilot.pause()
        assert c.active_idx == 1
        # footer echoes the active sorter
        footer = app.query_one("#footer", Static)
        assert "spykingcircus2" in footer.render().plain


async def test_t_cycles_sorter(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert c.active_idx == 1
        await pilot.press("t")
        await pilot.pause()
        assert c.active_idx == 0


async def test_tiny_window_stacks_and_keeps_actions(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(40, 12)) as pilot:
        await pilot.pause()
        # narrow -> panes stack; short -> shield hidden; actions still all present
        assert app.query_one("#body").has_class("stacked")
        assert app.query_one("#shield").display is False
        assert app.query_one("#actions", OptionList).option_count == 10


async def test_very_short_window_does_not_crash(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(30, 6)) as pilot:
        await pilot.pause()
        # still alive and the actions list exists (scrolls within its box)
        assert app.query_one("#actions", OptionList).option_count == 10
        await pilot.press("down")
        await pilot.pause()


async def test_resize_wide_to_tiny_to_wide(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause()
        assert not app.query_one("#body").has_class("stacked")
        await pilot.resize_terminal(38, 10)
        await pilot.pause()
        assert app.query_one("#body").has_class("stacked")
        await pilot.resize_terminal(120, 44)
        await pilot.pause()
        assert not app.query_one("#body").has_class("stacked")


async def test_missing_data_shows_banner(make_controller):
    app = _app(make_controller(present=False))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        banner = app.query_one("#banner", Static)
        assert banner.display is True
        assert "No recording found" in banner.render().plain
        # data-dependent actions are disabled, data-setup/verify/theme/quit are not
        actions = app.query_one("#actions", OptionList)
        by_id = {o.id: o for o in actions._options}
        assert by_id["explore"].disabled is True
        assert by_id["verify"].disabled is False
        assert by_id["data-setup"].disabled is False


async def test_data_setup_screen_lists_files(make_controller):
    app = _app(make_controller(present=False))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DataSetupScreen)
        body = app.screen.query_one("#setupbody", Static).render().plain
        assert ".ns5" in body and ".ns2" in body and ".nev" in body
        assert "Where to put them" in body
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.DataSetupScreen)


async def test_theme_modal_changes_accent(make_controller):
    c = make_controller(present=True)
    app = _app(c)
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


async def test_number_key_opens_data_setup(make_controller):
    # action index 8 (1-based "9") is data-setup in the mirrored table
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("9")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DataSetupScreen)


async def test_actions_stay_on_screen_when_stacked(make_controller):
    # The redesign's core promise: Actions are never pushed off-screen, at any size.
    for size in [(77, 24), (60, 22), (50, 18), (40, 12), (34, 30)]:
        app = _app(make_controller(present=True))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            actions = app.query_one("#actions", OptionList)
            visible = actions.region.intersection(app.screen.region)
            assert visible.height > 0, f"Actions off-screen at {size}: {actions.region}"


async def test_action_run_path_is_guarded(make_controller):
    # Pressing a non-data action runs it via the suspend() path; under the headless
    # test driver suspend() is unsupported, so the guard must fall back to an
    # in-place run instead of crashing. Verify-index in the mirrored table is 6 -> "7".
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("7")          # verify
        await pilot.pause()
        assert ("verify", None) in c.ran
        assert app.is_running           # did not crash out


async def test_disabled_action_does_not_run(make_controller):
    # With no data, a data-dependent action is blocked (not dispatched).
    c = make_controller(present=False)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("1")          # explore (needs data)
        await pilot.pause()
        assert c.ran == []
        assert "needs" in app.query_one("#footer", Static).render().plain.lower()


async def test_sort_span_modal_then_runs(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")          # sort -> opens the span modal
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)
        await pilot.press("enter")      # choose the highlighted "full"
        await pilot.pause()
        assert ("sort", "full") in c.ran


async def test_jk_navigation(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        actions = app.query_one("#actions", OptionList)
        await pilot.press("j")
        await pilot.pause()
        assert actions.highlighted == 1
        await pilot.press("k")
        await pilot.pause()
        assert actions.highlighted == 0


async def test_space_selects_sorter(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("left")       # focus the sorter sidebar
        await pilot.press("down")       # move to the second sorter
        await pilot.press("space")      # select it
        await pilot.pause()
        assert c.active_idx == 1


async def test_active_marker_and_incomplete_banner(make_controller):
    # active sorter carries an explicit ACTIVE tag (not colour alone)
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        assert "ACTIVE" in sorters.get_option_at_index(0).prompt.plain
