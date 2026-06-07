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


def _sorter_row(app, name):
    ol = app.query_one("#sorters", OptionList)
    for i in range(ol.option_count):
        if ol.get_option_at_index(i).id == name:
            return i
    raise AssertionError(f"sorter row {name!r} not found")


async def test_boots_with_lists_and_focus(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        actions = app.query_one("#actions", OptionList)
        assert sorters.get_option_at_index(0).id == "__docker__"
        assert actions.option_count == 11
        assert actions.highlighted == 0
        # the cursor sits on the active sorter row
        assert sorters.highlighted == _sorter_row(app, "tridesclous2")
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
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = _sorter_row(app, "spykingcircus2")
        app.set_focus(sorters)
        await pilot.press("enter")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"
        assert "spykingcircus2" in app.query_one("#footer", Static).render().plain


async def test_t_cycles_sorter(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert c.active_sorter == "tridesclous2"
        await pilot.press("t")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"
        await pilot.press("t")
        await pilot.pause()
        assert c.active_sorter == "tridesclous2"


async def test_tiny_window_stacks_and_keeps_actions(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(40, 12)) as pilot:
        await pilot.pause()
        # narrow -> panes stack; short -> shield hidden; actions still all present
        assert app.query_one("#body").has_class("stacked")
        assert app.query_one("#shield").display is False
        assert app.query_one("#actions", OptionList).option_count == 11


async def test_very_short_window_does_not_crash(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(30, 6)) as pilot:
        await pilot.pause()
        # still alive and the actions list exists (scrolls within its box)
        assert app.query_one("#actions", OptionList).option_count == 11
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


async def test_number_key_opens_param_editor(make_controller):
    # action index 6 (1-based "7") is "Edit sorter parameters" in the mirrored table
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("7")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ParamEditorScreen)


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
    # in-place run instead of crashing. Verify-index in the mirrored table is 7 -> "8".
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("8")          # verify
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
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = _sorter_row(app, "spykingcircus2")
        app.set_focus(sorters)
        await pilot.press("space")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"


async def test_active_marker_and_incomplete_banner(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        row = _sorter_row(app, "tridesclous2")
        assert "ACTIVE" in sorters.get_option_at_index(row).prompt.plain
        assert "★" in sorters.get_option_at_index(row).prompt.plain   # recommended badge


async def test_missing_banner_never_clips_actions_on_tiny_windows(make_controller):
    # The missing-data banner must not push the Actions/sorter off-screen at the
    # shortest sizes (it is suppressed there instead of wrapping).
    for size in [(40, 12), (30, 8), (30, 6), (24, 6), (20, 5)]:
        app = _app(make_controller(present=False))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for sel in ("#actions", "#sorters"):
                w = app.query_one(sel, OptionList)
                vis = w.region.intersection(app.screen.region)
                assert vis.height > 0, f"{sel} off-screen at {size}"


async def test_sort_blocked_without_data(make_controller):
    # sort is data-dependent: with no data it must be refused BEFORE its span modal.
    c = make_controller(present=False)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")          # sort
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.ChoiceModal)
        assert c.ran == []
        assert "needs" in app.query_one("#footer", Static).render().plain.lower()


async def test_unreadable_files_show_amber_banner(make_controller):
    # A complete set whose broadband won't load surfaces an explicit warning,
    # not a hidden/green "all good" banner.
    c = make_controller(present=True)
    c.pipeline[1]["status"] = "FAIL"   # Broadband (.ns5) row
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        banner = app.query_one("#banner", Static)
        assert banner.display is True
        assert "unreadable" in banner.render().plain.lower()


async def test_docker_toggle_row_is_first_and_toggles(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        assert sorters.get_option_at_index(0).id == "__docker__"
        assert next(i for i in c.infos if i["name"] == "mountainsort5")["runnable"] is False
        sorters.highlighted = 0           # the Docker toggle row
        app.set_focus(sorters)
        await pilot.press("enter")
        await pilot.pause()
        assert c.use_docker is True
        assert next(i for i in c.infos if i["name"] == "mountainsort5")["runnable"] is True


async def test_toggle_does_not_change_active_sorter_index(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        app.set_focus(sorters)
        await pilot.press("enter")        # toggle docker
        await pilot.pause()
        assert c.active_sorter == "tridesclous2"   # active sorter unchanged


async def test_param_editor_saves_only_changed_keys(make_controller):
    from textual.widgets import Input
    c = make_controller(present=True)
    app = _app(c)
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


async def test_param_editor_reset_clears_overrides(make_controller):
    c = make_controller(present=True)
    c.sorter_params["tridesclous2"] = {"detect_threshold": 9.0}
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._open_params()
        await pilot.pause()
        app.screen.action_reset()
        await pilot.pause()
        assert c.params_set == ("tridesclous2", {})


async def test_param_editor_bad_value_shows_error_and_stays(make_controller):
    from textual.widgets import Input, Static
    c = make_controller(present=True)
    app = _app(c)
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


async def test_compare_opens_picker_when_two_saved(make_controller):
    c = make_controller(present=True)   # both sorters present in the fake
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("6")          # compare
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)


async def test_compare_picks_pair_and_runs(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("6")          # compare -> first picker
        await pilot.pause()
        await pilot.press("enter")      # choose highlighted (tridesclous2)
        await pilot.pause()
        await pilot.press("enter")      # choose highlighted of the remaining
        await pilot.pause()
        assert c.ran_compare is not None
        assert len(c.ran_compare) == 2 and c.ran_compare[0] != c.ran_compare[1]
