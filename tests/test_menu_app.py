"""Textual Pilot tests for the v2 dashboard (scripts/menu_app.py).

These directly exercise the requirements that motivated the redesign: usable at
small window sizes, an obvious + selectable active sorter, always-reachable
actions, and clear missing-data guidance.
"""
from __future__ import annotations

import menu_app
import ui
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
    # Launch state is SORTER mode: the sorter list is shown + focused, the actions
    # list is hidden (but its options are not cleared — option_count stays 11).
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        actions = app.query_one("#actions", OptionList)
        assert sorters.get_option_at_index(0).id == "__docker__"
        assert actions.option_count == 11
        assert sorters.display is True
        assert actions.display is False
        # the cursor sits on the active sorter row
        assert sorters.highlighted == _sorter_row(app, "tridesclous2")
        assert app.focused is sorters


async def test_left_right_switch_focus(make_controller):
    # →/Tab enters action mode (sorter list hidden, actions shown + focused,
    # #activebar visible); ←/Shift-Tab restores sorter mode.
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        actions = app.query_one("#actions", OptionList)
        activebar = app.query_one("#activebar", Static)
        # boot = sorter mode
        assert app.focused is sorters and activebar.display is False
        await pilot.press("right")
        await pilot.pause()
        assert app.focused is actions
        assert sorters.display is False and actions.display is True
        assert activebar.display is True
        await pilot.press("left")
        await pilot.pause()
        assert app.focused is sorters
        assert sorters.display is True and actions.display is False
        assert activebar.display is False
        # Tab also enters action mode; Shift-Tab restores sorter mode.
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is actions
        await pilot.press("shift+tab")
        await pilot.pause()
        assert app.focused is sorters


async def test_down_moves_action_highlight(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")        # enter action mode
        await pilot.pause()
        actions = app.query_one("#actions", OptionList)
        assert actions.highlighted == 0
        await pilot.press("down")
        await pilot.pause()
        assert actions.highlighted == 1


async def test_enter_on_sorter_sets_active(make_controller):
    # Enter on a runnable sorter activates it AND auto-advances into action mode.
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
        # auto-advanced into action mode, #activebar names the now-active sorter
        assert app.query_one("#actions", OptionList).display is True
        bar = app.query_one("#activebar", Static)
        assert bar.display is True and "spykingcircus2" in bar.render().plain


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
        await pilot.press("right")        # enter action mode -> actions list shown
        await pilot.pause()
        # narrow -> panes stack; short -> crest hidden; actions still all present
        assert app.query_one("#body").has_class("stacked")
        assert app.query_one("#crest").display is False
        assert app.query_one("#actions", OptionList).option_count == 11


async def test_very_short_window_does_not_crash(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(30, 6)) as pilot:
        await pilot.pause()
        await pilot.press("right")        # enter action mode
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
        banner = app.query_one("#statusline", Static)
        assert banner.display is True
        plain = banner.render().plain
        assert "No recording found" in plain
        assert "⚠" in plain and "┌" in plain          # loud = bordered ⚠ banner
        # data-dependent actions are disabled, help/verify/theme/quit are not
        actions = app.query_one("#actions", OptionList)
        by_id = {o.id: o for o in actions._options}
        assert by_id["explore"].disabled is True
        assert by_id["verify"].disabled is False
        assert by_id["help"].disabled is False


async def test_help_screen_opens_via_d_at_data_topic(make_controller):
    app = _app(make_controller(present=False))
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


async def test_help_screen_opens_via_question_mark(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")   # the ? key
        await pilot.pause()
        assert isinstance(app.screen, menu_app.HelpScreen)
        # overview topic by default
        assert "spike sorting" in app.screen.query_one("#helpbody", Static).render().plain.lower()


async def test_help_action_runs(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")        # enter action mode so Enter hits #actions
        await pilot.pause()
        # 'help' is the action at index 9 (number keys only reach 1-9, so open via the list)
        actions = app.query_one("#actions", OptionList)
        idx = next(i for i in range(actions.option_count)
                   if actions.get_option_at_index(i).id == "help")
        actions.highlighted = idx
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.HelpScreen)


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
    # The redesign's core promise: the active list is never pushed off-screen, at
    # any size. Enter action mode so #actions is the shown list, then assert.
    for size in [(77, 24), (60, 22), (50, 18), (40, 12), (34, 30)]:
        app = _app(make_controller(present=True))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.press("right")        # action mode -> #actions shown
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
        await pilot.press("right")        # enter action mode
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
    # The loud missing-data banner must not push the active list off-screen at the
    # shortest sizes (it is suppressed there instead of wrapping). Check both modes'
    # lists by switching focus.
    for size in [(40, 12), (30, 8), (30, 6), (24, 6), (20, 5)]:
        app = _app(make_controller(present=False))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            # sorter mode: #sorters is the shown list
            w = app.query_one("#sorters", OptionList)
            vis = w.region.intersection(app.screen.region)
            assert vis.height > 0, f"#sorters off-screen at {size}"
            await pilot.press("right")        # action mode: #actions is the shown list
            await pilot.pause()
            w = app.query_one("#actions", OptionList)
            vis = w.region.intersection(app.screen.region)
            assert vis.height > 0, f"#actions off-screen at {size}"


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
    # A complete set whose broadband won't load surfaces an explicit loud banner,
    # not a hidden/quiet "all good" line.
    c = make_controller(present=True)
    c.pipeline[1]["status"] = "FAIL"   # Broadband (.ns5) row
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        banner = app.query_one("#statusline", Static)
        assert banner.display is True
        plain = banner.render().plain
        assert "⚠" in plain and "┌" in plain                 # loud = bordered ⚠
        assert "Broadband" in plain and "won't load" in plain


async def test_healthy_status_is_quiet_no_banner(make_controller):
    # A complete, readable set: quiet borderless ✓ line, no bordered ⚠ banner.
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        line = app.query_one("#statusline", Static).render().plain
        assert "✓" in line and "Recording loaded" in line
        assert "┌" not in line and "⚠" not in line           # quiet = no border


async def test_active_sorter_visible_in_action_mode_bar(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")                 # -> action mode
        await pilot.pause()
        bar = app.query_one("#activebar", Static)
        assert bar.display is True and "tridesclous2" in bar.render().plain


async def test_action_explain_shows_in_action_mode(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        ex = app.query_one("#explainbody", Static).render().plain
        assert "figures" in ex.lower() or "explore" in ex.lower()   # row 0 = explore


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
        await pilot.press("enter")        # opens the confirm dialog (state defaults to running)
        await pilot.pause()
        app.screen.action_enable()
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


async def test_docker_enable_opens_confirm_when_running(make_controller):
    c = make_controller(present=True)
    c.docker_state = "running"
    app = _app(c)
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


async def test_docker_confirm_enable_turns_on(make_controller):
    c = make_controller(present=True)
    c.docker_state = "running"
    app = _app(c)
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


async def test_docker_confirm_not_installed_shows_download(make_controller):
    c = make_controller(present=True)
    c.docker_state = "not_installed"
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        app.set_focus(sorters)
        await pilot.press("enter")
        await pilot.pause()
        body = app.screen.query_one("#dstatus", Static).render().plain.lower()
        assert "don't have docker" in body or "download" in body


async def test_docker_confirm_start_calls_controller(make_controller):
    c = make_controller(present=True)
    c.docker_state = "installed_not_running"
    app = _app(c)
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


async def test_docker_off_is_immediate(make_controller):
    c = make_controller(present=True)
    c.toggle_docker()                     # turn ON first (no dialog needed off->on in fake)
    app = _app(c)
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


async def test_welcome_shows_when_wanted(make_controller):
    c = make_controller(present=True)
    c.want_welcome = True
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, menu_app.WelcomeScreen)
        await pilot.press("enter")        # [Get started] dismisses + marks seen
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.WelcomeScreen)
        assert c.welcome_seen is True


async def test_welcome_hidden_when_seen(make_controller):
    c = make_controller(present=True)   # want_welcome defaults False
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.WelcomeScreen)


async def test_escape_does_not_quit_the_app(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.is_running           # Esc no longer hard-quits the dashboard


async def test_f_opens_data_folder_picker_and_sets_dir(make_controller):
    from textual.widgets import Input
    c = make_controller(present=True)
    app = _app(c)
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


async def test_sort_modal_warns_before_overwriting(make_controller):
    # active sorter (tridesclous2) already has a saved sort in the fake universe.
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")          # action 2 = sort -> span modal
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)
        note = app.screen.query_one("#dialognote", Static).render().plain
        assert "already has a saved sort" in note


async def test_sort_blocked_when_active_needs_docker_thats_down(make_controller):
    c = make_controller(present=True)
    c.active_blocked_on_docker = lambda: True       # container sorter, daemon down
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")          # sort
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.ChoiceModal)   # guarded, no modal
        assert app._last is not None and "Docker" in app._last.plain


async def test_nonrunnable_sorter_shows_block_reason_in_explain(make_controller):
    # Highlighting a non-runnable (Docker) sorter must show WHY it can't run in the
    # explanation pane (priority 2: info about the sorter) — spec State A.
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = _sorter_row(app, "mountainsort5")   # group=docker, not runnable
        await pilot.pause()
        body = app.query_one("#explainbody", Static).render().plain
        assert "Docker" in body                                   # the block reason / how to enable


async def test_explain_hidden_on_extreme_short_wide(make_controller):
    # Side-by-side panes are co-equal height, so on an extreme-short WIDE window the
    # explanation pane is dropped to give the active list the full width.
    app = _app(make_controller(present=True))
    async with app.run_test(size=(100, 14)) as pilot:
        await pilot.pause()
        assert not app.query_one("#body").has_class("stacked")    # wide, not stacked
        assert app.query_one("#explain").has_class("hidden")


async def test_stacked_keeps_activebar_and_caps_explain(make_controller):
    # Narrow -> panes stack; the active list keeps the majority (#explain capped at
    # 40%) and, in action mode, #activebar stays visible as the mode's shape cue.
    app = _app(make_controller(present=True))
    async with app.run_test(size=(60, 40)) as pilot:
        await pilot.pause()
        assert app.query_one("#body").has_class("stacked")
        await pilot.press("right")                                # -> action mode
        await pilot.pause()
        bar = app.query_one("#activebar", Static)
        assert bar.display is True and "tridesclous2" in bar.render().plain
        explain = app.query_one("#explain")
        activepane = app.query_one("#activepane")
        assert explain.region.height <= activepane.region.height  # list keeps the majority


def test_result_style_amber_for_warning():
    assert menu_app._result_style(True, "✓ Sorted x (5 units)") == "#3fb950"
    assert menu_app._result_style(True, "⚠ x: no units found") == "#f0883e"
    assert menu_app._result_style(False, "✗ Sorted x") == "#f85149"


# --- firing-neuron crest + preserved Pitt shield -------------------------- #

def test_neuron_tiers_equal_width():
    # Every row in each tier's rest pose must be the same width or Textual's
    # centred crest shifts row-to-row.
    for tier in (ui._NEURON_FULL, ui._NEURON_COMPACT, ui._NEURON_MINI):
        widths = {len(row) for row in tier.rest}
        assert len(widths) == 1, f"ragged neuron tier widths: {widths}"


def test_neuron_frame_width_invariant():
    # Animation only recolours / replaces cells in place — it never changes a
    # row's display width, at any phase.
    for tier in (ui._NEURON_FULL, ui._NEURON_COMPACT, ui._NEURON_MINI):
        W = len(tier.rest[0])
        for phase in (0.0, 0.5, 0.80, 0.96):
            for row in ui.neuron_frame(tier, phase):
                assert sum(len(seg) for _, seg in row) == W


def test_neuron_rest_has_no_spark():
    styles = {s for row in ui.neuron_frame(ui._NEURON_FULL, 0.0) for s, _ in row}
    assert ui.NEURON_SPARK not in styles
    assert ui.NEURON_BODY in styles


def test_neuron_fire_has_spark():
    styles = {s for row in ui.neuron_frame(ui._NEURON_FULL, 0.96) for s, _ in row}
    assert ui.NEURON_SPARK in styles


async def test_dashboard_crest_is_the_neuron(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest.display is True
        plain = crest.render().plain
        assert "━" in plain and "█" in plain        # axon + soma, not the shield


async def test_crest_advances_phase_when_animated(make_controller):
    c = make_controller(present=True)
    c.animate = True
    app = _app(c)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest._animate is True
        p0 = crest._phase
        crest._tick(); crest._tick()
        assert crest._phase != p0                    # the timer callback walks phase


async def test_crest_static_when_disabled(make_controller):
    c = make_controller(present=True)
    c.animate = False
    app = _app(c)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest._animate is False
        before = crest.render().plain
        crest._tick()                                # no-op while disabled
        assert crest._phase == 0.0
        assert crest.render().plain == before


async def test_m_key_toggles_animation(make_controller):
    c = make_controller(present=True)
    c.animate = True
    app = _app(c)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest._animate is True
        await pilot.press("m")
        await pilot.pause()
        assert c.animate is False and crest._animate is False
        await pilot.press("m")
        await pilot.pause()
        assert c.animate is True and crest._animate is True


async def test_welcome_screen_shows_pitt_shield(make_controller):
    c = make_controller(present=True)
    c.want_welcome = True                              # first-launch greeting
    app = _app(c)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, menu_app.WelcomeScreen)
        crest = app.screen.query_one("#wcrest", Static).render().plain
        assert "█" in crest                            # blue+gold shield (block art)


async def test_help_about_topic_shows_pitt_shield(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(menu_app.HelpScreen(c, c.accent, topic="about"))
        await pilot.pause()
        body = app.screen.query_one("#helpbody", Static).render().plain
        assert "█" in body and "University of Pittsburgh" in body


async def test_data_help_shows_stream_detail(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        body = app.screen.query_one("#helpbody", Static).render().plain
        assert "30000 Hz" in body or "22 ch" in body     # per-stream detail present
