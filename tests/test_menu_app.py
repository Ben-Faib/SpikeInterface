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


async def test_action_title_never_restates_active_sorter(make_app):
    # One fact, one place (§1.1, D1 review #5): the SORT banner is the active
    # sorter's only at-rest home — the pane title never restates it. (T2: the
    # old exact-string match pinned the title's wording, not this contract.)
    app = make_app()
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        title = str(app.query_one("#actionpane").border_title)
        assert "tridesclous2" not in title
        assert "tridesclous2" in app.query_one("#sortbar").render().plain


# --- merged INSPECTING ---------------------------------------------------- #


async def test_crest_drops_before_lists(make_app):
    app = make_app()
    async with app.run_test(size=(100, 14)) as pilot:
        await pilot.pause()
        assert app.query_one("#crest").display is False


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
        # All six workflow rows need data -> all disabled; the MANAGE letters
        # (help/verify/theme/quit) still work from the dim line (D5).
        actions = app.query_one("#actions", OptionList)
        by_id = {o.id: o for o in actions._options}
        assert all(o.disabled for o in by_id.values())
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.HelpScreen)


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
    # D5: help lives on the MANAGE line -> `?` runs it directly.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
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
    # instead of crashing. D5: verify runs from its MANAGE letter.
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("v")          # verify, from the MANAGE letter line
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
        # D2: completion renders the RESULT CARD, not a bare Done line. This run
        # carries a metrics-failure note, so the analyzer is GONE — the card must
        # not offer report/GUI chaining (F2), only the close.
        assert "7 units" in body and "3 build report" not in body
        assert "↵ close" in body
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
        # D2: known sorter jargon is translated; the real counts stay.
        assert "detecting peaks: 562 peaks found" in body
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
        assert "█" in crest.render().plain           # block letters


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


# --- D2 view half: result cards, chaining, honest progress ------------------ #
def _drive_finished_sort(screen, units=14, good=9):
    for ev in [
        {"t": "phase", "i": 1, "n": 5, "title": "Read broadband", "elapsed": 0.1},
        {"t": "phase_done", "i": 1, "title": "Read broadband", "secs": 0.09},
        {"t": "phase", "i": 5, "n": 5, "title": "Analyze + metrics", "elapsed": 7.0},
        {"t": "phase_done", "i": 5, "title": "Analyze + metrics", "secs": 8.5},
        {"t": "result", "units": units, "good": good, "noise_floor_uV": 4.02,
         "out": "outputs/tridesclous2", "effective_seconds": 30.0,
         "total_seconds": 132.0, "elapsed": 15.4},
        {"t": "done", "ok": True, "units": units, "good": good,
         "out": "outputs/tridesclous2", "note": None},
    ]:
        screen.handle_event(ev)


async def test_sort_result_card_shows_numbers_and_durations(make_app):
    class _NoRun(menu_app.SortProgressScreen):
        async def _run(self):
            pass

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        argv = ["python", "run_sorting.py", "--sorter", "tridesclous2",
                "--progress", "json", "--duration", "30"]
        screen = _NoRun(argv, app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        _drive_finished_sort(screen)
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "14 units" in body and "9 high-quality" in body
        assert "noise floor 4.02 µV" in body and "expected" in body
        assert "0:15" in body                                   # emitter elapsed
        assert "partial: first 30 s of 132 s" in body           # honest window
        assert "0.1 s" in body                                  # per-phase duration
        assert "3 build report" in body and "4 inspect in GUI" in body
        title = screen.query_one("#sorttitle").render().plain
        assert "tridesclous2" in title and "quick test" in title


async def test_sort_zero_units_is_amber_with_fix(make_app):
    class _NoRun(menu_app.SortProgressScreen):
        async def _run(self):
            pass

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = _NoRun(["python", "x", "--sorter", "simple"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        screen.handle_event({"t": "result", "units": 0, "good": 0,
                             "noise_floor_uV": None, "out": "outputs/simple",
                             "effective_seconds": 30.0, "total_seconds": 132.0,
                             "elapsed": 9.0})
        screen.handle_event({"t": "done", "ok": True, "units": 0, "good": 0,
                             "out": "outputs/simple", "note": None})
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "0 units found" in body and "detect_threshold" in body
        # The dismissal message carries the same amber hint (no green 0-unit).
        ok, msg, changed = screen._dismiss_message()
        assert ok and msg.startswith("⚠") and "detect_threshold" in msg


async def test_sort_result_card_chains_into_report(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("2")            # sort -> span modal
        await pilot.pause()
        await pilot.press("enter")        # full recording -> progress modal
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.SortProgressScreen)
        _drive_finished_sort(screen)
        await pilot.pause()
        await pilot.press("3")            # chain: close + build report (D3b modal)
        await pilot.pause()
        screen2 = app.screen
        assert isinstance(screen2, menu_app.BuildProgressScreen)
        for _ in range(20):               # fake argv exits 0 -> synthesized done
            await pilot.pause()
            if screen2._state["done"] is not None:
                break
        await pilot.press("enter")
        await pilot.pause()
        assert c.last_result["key"] == "report"   # the chained action recorded last
        assert c.reopened == 1                    # the app opened the built page


async def test_sort_chain_keys_noop_while_running(make_app):
    class _NoRun(menu_app.SortProgressScreen):
        async def _run(self):
            pass

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = _NoRun(["python", "x", "--sorter", "simple"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        screen.handle_event({"t": "phase", "i": 3, "n": 5, "title": "Sort"})
        await pilot.pause()
        await pilot.press("3")
        await pilot.pause()
        assert app.screen is screen       # still up — no chain mid-run


async def test_sort_full_bar_yields_to_heartbeat(make_app):
    # A bar at 100% under a still-running step is a lie of completion (§3): once
    # frac hits 1.0 it disappears and the heartbeat carries aliveness.
    class _NoRun(menu_app.SortProgressScreen):
        async def _run(self):
            pass

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = _NoRun(["python", "x", "--sorter", "simple"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        screen.handle_event({"t": "phase", "i": 3, "n": 5, "title": "Sort"})
        screen.handle_event({"t": "bar", "desc": "clustering", "frac": 0.6,
                             "n": 6, "total": 10})
        await pilot.pause()
        assert "60%" in screen.query_one("#sortbody").render().plain
        screen.handle_event({"t": "bar", "desc": "clustering", "frac": 1.0,
                             "n": 10, "total": 10})
        screen.handle_event({"t": "heartbeat", "label": "clustering", "secs": 8})
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "100%" not in body and "still working" in body


async def test_sort_bar_hides_before_rounding_lies(make_app):
    # frac 0.996 would round to a displayed "100%" under a running step — the bar
    # must yield before rounding can lie (D2v review F1).
    class _NoRun(menu_app.SortProgressScreen):
        async def _run(self):
            pass

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = _NoRun(["python", "x", "--sorter", "simple"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        screen.handle_event({"t": "phase", "i": 3, "n": 5, "title": "Sort"})
        screen.handle_event({"t": "bar", "desc": "clustering", "frac": 0.996,
                             "n": 996, "total": 1000})
        await pilot.pause()
        assert "100%" not in screen.query_one("#sortbody").render().plain


async def test_chain_suppressed_when_analyzer_missing(make_app):
    # 0 units or failed metrics -> run_sorting deleted the analyzer -> report/GUI
    # would dead-end; the card must not offer them (D2v review F2).
    class _NoRun(menu_app.SortProgressScreen):
        async def _run(self):
            pass

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        # note case (metrics failed on a units-found sort)
        screen = _NoRun(["python", "x", "--sorter", "simple"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        screen.handle_event({"t": "done", "ok": True, "units": 7, "good": None,
                             "out": "outputs/simple",
                             "note": "quality metrics failed: boom"})
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "3 build report" not in body and "↵ close" in body
        await pilot.press("3")            # must be a no-op
        await pilot.pause()
        assert app.screen is screen
        await pilot.press("enter")
        await pilot.pause()
        # zero-unit case
        screen2 = _NoRun(["python", "x", "--sorter", "simple"], app._accent)
        await app.push_screen(screen2)
        await pilot.pause()
        screen2.handle_event({"t": "result", "units": 0, "good": 0,
                              "noise_floor_uV": None, "out": "outputs/simple",
                              "effective_seconds": 30.0, "total_seconds": 132.0,
                              "elapsed": 9.0})
        screen2.handle_event({"t": "done", "ok": True, "units": 0, "good": 0,
                              "out": "outputs/simple", "note": None})
        await pilot.pause()
        body = screen2.query_one("#sortbody").render().plain
        assert "3 build report" not in body
        assert "partial: first 30 s" in body          # F8: window fact on amber too
        await pilot.press("4")
        await pilot.pause()
        assert app.screen is screen2


async def test_noise_floor_verdict_amber_out_of_band(make_app):
    # The canary renders as a verdict (D2v review F5): ~1 uV means double-scaling.
    class _NoRun(menu_app.SortProgressScreen):
        async def _run(self):
            pass

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = _NoRun(["python", "x", "--sorter", "simple"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        screen.handle_event({"t": "result", "units": 5, "good": 2,
                             "noise_floor_uV": 1.02, "out": "o",
                             "effective_seconds": 132.0, "total_seconds": 132.0,
                             "elapsed": 20.0})
        screen.handle_event({"t": "done", "ok": True, "units": 5, "good": 2,
                             "out": "o", "note": None})
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "outside the expected" in body and "twice" in body


def test_result_style_amber_for_warning_message():
    # The false-green kill end-to-end: a ⚠-message renders amber on the dashboard.
    assert menu_app._result_style(True, "⚠ simple: no units found") != "bold #3fb950"


# ========================================================================== #
# T2 — journeys: whole flows through the real screens and the real event pipe
# ========================================================================== #

def _events_argv(tmp_path, events):
    """argv for a child that speaks the real protocol on stdout — the sort worker
    parses it exactly as it parses run_sorting.py, so the journey crosses the
    actual subprocess pipe, not a handle_event shortcut."""
    import json
    import sys as _sys

    evfile = tmp_path / "events.jsonl"
    evfile.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    # The path travels as argv, never embedded in the -c source: a quote in a
    # tmp path (Windows usernames) must not become a child SyntaxError.
    return [_sys.executable, "-c",
            "import sys; sys.stdout.write(open(sys.argv[1], encoding='utf-8').read())",
            str(evfile)]


async def _wait_until(pilot, cond, budget_s=10.0, what="condition"):
    # Deadline-based, not iteration-count-based: pause() cost is a textual
    # implementation detail, and a cold interpreter under AV scanning is slow.
    from time import monotonic

    deadline = monotonic() + budget_s
    while monotonic() < deadline:
        await pilot.pause(0.05)
        if cond():
            return
    raise AssertionError(f"timed out waiting for {what}")


async def _wait_done(pilot, screen):
    await _wait_until(pilot, lambda: screen._state["done"] is not None,
                      what="the sort screen's terminal state")


async def test_journey_explore_sort_report_happy_path(make_app, tmp_path):
    # The workbench's whole point, end to end in one session: explore records a
    # result -> sort runs through the real subprocess pipe to a result card ->
    # 3 chains into the report -> LAST RESULT remembers it and r reopens it.
    app = make_app(present=True)
    c = app.c
    c.sort_command = lambda span: _events_argv(tmp_path, [
        {"t": "phase", "i": 1, "n": 5, "title": "Read broadband"},
        {"t": "result", "units": 14, "good": 9, "noise_floor_uV": 4.0,
         "out": "outputs/tridesclous2", "effective_seconds": 132.0,
         "total_seconds": 132.0, "elapsed": 12.0},
        {"t": "done", "ok": True, "units": 14, "good": 9,
         "out": "outputs/tridesclous2", "note": None},
    ])
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("1")                    # explore
        await pilot.pause()
        assert ("explore", None) in c.ran
        await pilot.press("2")                    # sort -> span modal
        await pilot.pause()
        await pilot.press("enter")                # full recording
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.SortProgressScreen)
        await _wait_done(pilot, screen)
        body = screen.query_one("#sortbody").render().plain
        assert "14 units" in body and "3 build report" in body
        await pilot.press("3")                    # chain into the report (modal)
        await pilot.pause()
        screen2 = app.screen
        assert isinstance(screen2, menu_app.BuildProgressScreen)
        for _ in range(20):
            await pilot.pause()
            if screen2._state["done"] is not None:
                break
        await pilot.press("enter")
        await pilot.pause()
        assert c.last_result["key"] == "report"
        bar = app.query_one("#resultbar")
        assert not bar.has_class("hidden") and "report" in bar.render().plain
        before = c.reopened
        await pilot.press("r")                    # the result stays reachable
        await pilot.pause()
        assert c.reopened == before + 1


async def test_journey_cancel_mid_sort(make_app):
    # Esc mid-run: the modal closes with an honest "cancelled" (never a success),
    # and the worker child does not outlive it.
    import sys as _sys

    app = make_app(present=True)
    app.c.sort_command = lambda span: [_sys.executable, "-c",
                                       "import time; time.sleep(60)"]
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.SortProgressScreen)
        await _wait_until(pilot, lambda: screen._proc is not None, what="child spawn")
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.SortProgressScreen)
        assert "cancel" in app._last.plain.lower()
        # Cross-platform since D4 (f115015): killpg on POSIX, a taskkill/terminate
        # fallback on Windows — cancel must never leave the child running anywhere.
        await _wait_until(pilot, lambda: screen._proc.returncode is not None,
                          what="the cancelled child to die")
        assert screen._proc.returncode is not None


async def test_journey_failure_card(make_app, tmp_path):
    # A hard crash (non-zero exit, no protocol error event): the red card carries
    # the REAL cause from the captured stderr, the log path as the next step
    # (§1.7), offers no chaining, and dismisses as a failure — never a success.
    import sys as _sys

    app = make_app(present=True)
    log = tmp_path / "sort.log"
    app.c.sort_command = lambda span: [
        _sys.executable, "-c",
        "import sys; sys.stderr.write('RuntimeError: boom_cause\\n'); sys.exit(1)"]
    app.c.sort_log_path = lambda span=None: str(log)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.SortProgressScreen)
        await _wait_done(pilot, screen)
        assert screen._state["done"]["ok"] is False
        body = screen.query_one("#sortbody").render().plain
        assert "exited (1)" in body and "boom_cause" in body
        assert "log →" in body                      # where to look next
        assert "3 build report" not in body         # no chaining off a failure
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.SortProgressScreen)
        assert "✗" in app._last.plain


async def test_journey_zero_units_amber_reaches_dashboard(make_app, tmp_path):
    # The 0-unit amber path through the REAL pipe: card names the fix, and the
    # dashboard's memory of the run keeps the ⚠ + hint (no green-and-gone).
    app = make_app(present=True)
    app.c.sort_command = lambda span: _events_argv(tmp_path, [
        {"t": "result", "units": 0, "good": 0, "noise_floor_uV": None,
         "out": "outputs/tridesclous2", "effective_seconds": 30.0,
         "total_seconds": 132.0, "elapsed": 9.0},
        {"t": "done", "ok": True, "units": 0, "good": 0,
         "out": "outputs/tridesclous2", "note": None},
    ])
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.SortProgressScreen)
        await _wait_done(pilot, screen)
        body = screen.query_one("#sortbody").render().plain
        assert "0 units found" in body and "detect_threshold" in body
        await pilot.press("enter")
        await pilot.pause()
        assert app._last.plain.startswith("⚠") and "detect_threshold" in app._last.plain


# ========================================================================== #
# T3 — honesty states (§1.7): every dead-end names its next step
# ========================================================================== #

async def test_reopen_gone_names_next_step(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("1")                    # explore records a reopenable page
        await pilot.pause()
        app.c.gone.add(app.c.last_result["path"])  # the artifact vanished from disk
        await pilot.press("r")
        await pilot.pause()
        assert "gone" in app._last.plain and "rebuild" in app._last.plain


async def test_reopen_with_no_result_yet_hints(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("r")                    # nothing has run yet
        await pilot.pause()
        assert "Nothing to reopen yet" in app._last.plain


async def test_imported_probe_edit_refused_names_next_step(make_app):
    # P1 handoff: imported probes are view/duplicate/delete-only — Edit must
    # refuse with the next step named, never open the geometry-stripping form.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.ProbeManagerScreen)
        ol = screen.query_one("#probelist", OptionList)
        ol.highlighted = next(i for i in range(ol.option_count)
                              if ol.get_option_at_index(i).id == "lab-imported-16")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.ProbeEditorScreen)
        foot = screen.query_one("#pmfoot", Static).render().plain
        assert "can't be edited" in foot and ("duplicate" in foot or "re-import" in foot)


async def test_chain_suppression_states_name_why(make_app):
    # When the card withholds report/GUI chaining (analyzer gone), the reason is
    # ON the card — a silently missing option is a dead-end without a name.
    class _NoRun(menu_app.SortProgressScreen):
        async def _run(self):
            pass

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = _NoRun(["python", "x", "--sorter", "simple"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        screen.handle_event({"t": "done", "ok": True, "units": 7, "good": None,
                             "out": "outputs/simple",
                             "note": "quality metrics failed: boom"})
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "3 build report" not in body
        assert "quality metrics failed" in body   # the why, on the card


# --- D4: flow modals — informed choices, live validation, honest waits ------ #
async def test_sort_span_modal_shows_last_duration(make_app):
    app = make_app(present=True)
    app.c.sort_expectations = lambda: {"span": "full", "wall_seconds": 247.0}
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("2")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, menu_app.ChoiceModal)
        ol = modal.query_one("#choicelist", OptionList)
        texts = [ol.get_option_at_index(i).prompt.plain for i in range(ol.option_count)]
        full_row = next(t for t in texts if "Full recording" in t)
        assert "~4:07 last time" in full_row
        quick_row = next(t for t in texts if "Quick test" in t)
        assert "last time" not in quick_row     # the estimate names ITS span only


async def test_param_editor_orders_and_marks_overrides(make_app):
    app = make_app(present=True)
    app.c.sorter_params["tridesclous2"] = {"freq_min": 250.0}
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        ed = app.screen
        assert isinstance(ed, menu_app.ParamEditorScreen)
        # Overridden keys lead, then priority keys, then the rest.
        assert ed._ordered_keys() == ["freq_min", "detect_threshold",
                                      "apply_preprocessing"]
        assert "●" in ed._names["freq_min"].render().plain     # the overridden mark


async def test_param_editor_live_validation(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        ed = app.screen
        w = ed.query_one("#w_detect_threshold")
        w.focus()
        await pilot.pause()
        w.value = "not-a-number"
        await pilot.pause()
        assert w.has_class("invalid")
        assert "detect_threshold" in ed.query_one("#perror").render().plain
        w.value = "6.5"
        await pilot.pause()
        assert not w.has_class("invalid")
        assert ed.query_one("#perror").render().plain == ""


async def test_manage_hub_list_is_navlist(make_app):
    # Every list in the app answers j/k (D1 review-era consistency; D4 fix).
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        hub = app.screen.query_one("#hublist")
        assert isinstance(hub, menu_app.NavList)
        before = hub.highlighted
        await pilot.press("j")
        await pilot.pause()
        assert hub.highlighted == (before or 0) + 1


async def test_compare_runs_behind_busy_screen(make_app):
    # Compare no longer silently suspends: an honest BusyScreen fronts the thread
    # worker and the result lands on the dashboard when it finishes. A gate holds
    # the fake compare mid-flight so the BusyScreen's APPEARANCE is asserted, not
    # merely tolerated (D4 review F8a).
    import threading

    app = make_app(present=True)
    c = app.c
    gate = threading.Event()
    orig_compare = c.run_compare

    def gated_compare(pair):
        gate.wait(timeout=10)
        return orig_compare(pair)

    c.run_compare = gated_compare
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await _wait_until(pilot, lambda: isinstance(app.screen, menu_app.BusyScreen),
                          what="the compare BusyScreen to appear")
        gate.set()
        await _wait_until(pilot,
                          lambda: not isinstance(app.screen, menu_app.BusyScreen),
                          what="the BusyScreen to dismiss")
        assert c.ran_compare is not None and len(c.ran_compare) == 2
        # ...and the outcome reaches the dashboard's memory, not just the modal.
        assert c.last_result["key"] == "compare"
        bar = app.query_one("#resultbar")
        assert not bar.has_class("hidden") and "compare" in bar.render().plain


# =========================================================================== #
# D5 — the actions-first main screen + the sorter picker (Ben, 2026-08-18)
# =========================================================================== #
async def _open_picker(pilot, app):
    await pilot.press("t")
    await pilot.pause()
    picker = app.screen
    assert isinstance(picker, menu_app.SorterPickerScreen)
    return picker


def _picker_rows(picker):
    ol = picker.query_one("#picklist", OptionList)
    return ol, {ol.get_option_at_index(i).id: (i, ol.get_option_at_index(i))
                for i in range(ol.option_count)}


async def _pick(pilot, app, row_id):
    picker = await _open_picker(pilot, app)
    ol, rows = _picker_rows(picker)
    assert row_id in rows, f"{row_id} not in picker rows {list(rows)}"
    ol.highlighted = rows[row_id][0]
    await pilot.press("enter")
    await pilot.pause()


# --- boot + layout --------------------------------------------------------- #
async def test_boots_actions_first(make_app):
    # D5: the actions ARE the screen — full-width panel focused on launch, the
    # MANAGE keys as one dim line, no sorters pane, no INSPECTING.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        actions = app.query_one("#actions", OptionList)
        assert app.focused is actions
        assert actions.option_count == 6     # the six WORKFLOW actions only (D5)
        assert not app.query("#sorters") and not app.query("#inspect")
        manage = app.query_one("#managebar").render().plain
        for key in ("e params", "m sorters", "p probe", "v verify"):
            assert key in manage


async def test_sortbar_names_active_with_change_hint(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        bar = app.query_one("#sortbar").render().plain
        assert "tridesclous2" in bar and "t change" in bar


async def test_results_section_only_with_saved_sort(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        res = app.query_one("#results")
        assert not res.has_class("hidden")
        text = res.render().plain
        assert "tridesclous2" in text and "12 units" in text
        assert "V_pp" in text and "noise" in text and "yield" in text
        # Clearing the saved sort hides the section (no empty frame).
        app.c.clear_saved_sort("tridesclous2")
        app.c.reload()
        app._render_results()
        await pilot.pause()
        assert app.query_one("#results").has_class("hidden")


async def test_actions_keep_rows_at_common_sizes(make_app):
    # The primary panel never starves: real painted rows at the sizes people use.
    for size in [(110, 40), (100, 24), (80, 24), (60, 24)]:
        app = make_app(present=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            r = app.query_one("#actionpane").region
            assert r.height >= 6, f"actions squeezed to {r.height} rows at {size}"


async def test_tiny_never_clips_actions(make_app):
    for size in [(40, 12), (30, 8), (24, 6), (20, 5)]:
        app = make_app(present=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            r = app.query_one("#actions").region
            assert r.intersection(app.screen.region).height > 0


async def test_resize_wide_to_tiny_to_wide(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        for size in [(30, 8), (110, 40)]:
            await pilot.resize_terminal(*size)
            await pilot.pause()
        assert not app.query_one("#results").has_class("collapsed")
        assert app.query_one("#actionpane").region.height >= 6


# --- the sorter picker ----------------------------------------------------- #
async def test_picker_opens_with_filter_focused(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        picker = await _open_picker(pilot, app)
        assert app.focused is picker.query_one("#pickfilter")
        ol, rows = _picker_rows(picker)
        assert ol.get_option_at_index(0).id == "__docker__"   # toggle row first
        assert "tridesclous2" in rows
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.SorterPickerScreen)


async def test_picker_filter_narrows_live(make_app):
    app = make_app(use_docker=True)
    async with app.run_test(size=(110, 40)) as pilot:
        picker = await _open_picker(pilot, app)
        await pilot.press(*"mount")
        await pilot.pause()
        _ol, rows = _picker_rows(picker)
        sorter_rows = [k for k in rows if not str(k).startswith("__")]
        assert sorter_rows == ["mountainsort5"]


async def test_picker_select_activates_and_closes(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _pick(pilot, app, "spykingcircus2")
        assert c.active_sorter == "spykingcircus2"
        assert not isinstance(app.screen, menu_app.SorterPickerScreen)
        assert "spykingcircus2" in app.query_one("#sortbar").render().plain
        # RESULTS follows the new active sorter.
        assert "spykingcircus2" in app.query_one("#results").render().plain


async def test_picker_marks_active_and_shows_desc(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        picker = await _open_picker(pilot, app)
        ol, rows = _picker_rows(picker)
        i, opt = rows["tridesclous2"]
        assert opt.prompt.plain.startswith("▌")          # active marked as a shape
        ol.highlighted = i
        picker._render_desc()
        await pilot.pause()
        desc = picker.query_one("#pickdesc").render().plain
        assert "tridesclous2 description" in desc
        assert "fits this probe" in desc                  # fit lives in the footer


async def test_picker_groups_start_collapsed_and_expand(make_app):
    app = make_app(present=True)   # gpu group exists in the fake universe
    async with app.run_test(size=(110, 40)) as pilot:
        picker = await _open_picker(pilot, app)
        ol, rows = _picker_rows(picker)
        assert "kilosort4" not in rows                    # collapsed by default
        gi, gopt = rows["__grp_gpu__"]
        assert "Enter to expand" in gopt.prompt.plain
        ol.highlighted = gi
        await pilot.press("enter")                        # expands, stays open
        await pilot.pause()
        assert isinstance(app.screen, menu_app.SorterPickerScreen)
        _ol, rows = _picker_rows(picker)
        assert "kilosort4" in rows


async def test_picker_glyphs_honest_about_pull(make_app):
    app = make_app(use_docker=True)
    async with app.run_test(size=(110, 40)) as pilot:
        picker = await _open_picker(pilot, app)
        _ol, rows = _picker_rows(picker)
        assert rows["herdingspikes"][1].prompt.plain.rstrip().endswith("●")   # cached
        assert rows["mountainsort5"][1].prompt.plain.rstrip().endswith("◌")   # needs pull


# --- docker flows, routed through the picker ------------------------------- #
async def test_picker_docker_row_toggles_via_confirm(make_app):
    app = make_app(present=True)
    c = app.c
    c.docker_state = "running"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _pick(pilot, app, "__docker__")     # turning ON -> confirm dialog
        assert isinstance(app.screen, menu_app.DockerConfirmScreen)
        assert "running" in app.screen.query_one("#dstatus", Static).render().plain.lower()
        assert c.use_docker is False              # not enabled until confirmed
        app.screen.action_enable()
        await pilot.pause()
        assert c.use_docker is True
        assert c.active_sorter == "tridesclous2"  # toggle never changes the active


async def test_picker_docker_off_is_immediate(make_app):
    app = make_app(present=True, use_docker=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _pick(pilot, app, "__docker__")     # turning OFF -> immediate
        assert c.use_docker is False
        assert not isinstance(app.screen, menu_app.DockerConfirmScreen)


async def test_docker_confirm_start_calls_controller(make_app):
    app = make_app(present=True)
    c = app.c
    c.docker_state = "installed_not_running"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _pick(pilot, app, "__docker__")
        assert isinstance(app.screen, menu_app.DockerConfirmScreen)
        app.screen.action_start_docker()
        await pilot.pause()
        assert c.started_docker is True


async def test_picker_undownloaded_docker_opens_download(make_app):
    app = make_app(use_docker=True)
    app.c.docker_state = "running"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _pick(pilot, app, "mountainsort5")
        assert isinstance(app.screen, menu_app.DownloadProgressScreen)


async def test_picker_undownloaded_docker_offers_docker_when_daemon_down(make_app):
    app = make_app(use_docker=True)
    app.c.docker_state = "installed_not_running"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _pick(pilot, app, "mountainsort5")
        assert isinstance(app.screen, menu_app.DockerConfirmScreen)


# --- x manages the ACTIVE sorter ------------------------------------------- #
async def test_x_opens_manage_for_active_saved_sorter(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.ManageSorterScreen)
        assert screen._name == "tridesclous2"


async def test_x_clears_saved_sort_via_manage(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("enter")                # cursor on "Clear saved sort"
        await pilot.pause()
        assert "tridesclous2" in c.cleared_sorts


async def test_x_on_nothing_to_delete_hints(make_app):
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        info = c.infos[c.active_idx]
        info["present"] = False
        info["img_present"] = None
        await pilot.press("x")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.ManageSorterScreen)
        assert "nothing to delete" in app.query_one("#footer").render().plain


# --- D5 review regressions -------------------------------------------------- #
async def test_picker_desc_footer_actually_paints(make_app):
    # F1: height:1 + padding-top:1 left ZERO content rows — the desc rendered in
    # memory but never painted. Pin the painted region, not render().plain.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        picker = await _open_picker(pilot, app)
        picker._render_desc()
        await pilot.pause()
        desc = picker.query_one("#pickdesc")
        assert desc.content_region.height > 0
        assert "description" in desc.render().plain


async def test_picker_filter_retargets_enter_at_a_sorter(make_app):
    # F2: a stale highlight index made Enter hit the Docker toggle after filtering.
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        picker = await _open_picker(pilot, app)
        ol, _rows = _picker_rows(picker)
        picker.action_move(1)             # wander off the default row
        await pilot.press(*"spyk")
        await pilot.pause()
        oid = ol.get_option_at_index(ol.highlighted).id
        assert oid == "spykingcircus2"    # first matching SORTER, never __docker__
        await pilot.press("enter")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"
        assert c.use_docker is False      # the toggle was never touched


async def test_picker_zero_match_filter_is_inert_and_says_so(make_app):
    # F3: "zzz" left Enter armed on the Docker row with no feedback.
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        picker = await _open_picker(pilot, app)
        await pilot.press(*"zzz")
        await pilot.pause()
        assert "no sorters match" in picker.query_one("#pickdesc").render().plain
        await pilot.press("enter")        # must NOT toggle Docker
        await pilot.pause()
        assert isinstance(app.screen, menu_app.SorterPickerScreen)
        assert c.use_docker is False


async def test_picker_gpu_pick_gives_honest_hint(make_app):
    # F9a: choosing a never-runnable sorter names the reason, not a silent no-op.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        picker = await _open_picker(pilot, app)
        ol, rows = _picker_rows(picker)
        gi, _ = rows["__grp_gpu__"]
        ol.highlighted = gi
        await pilot.press("enter")        # expand — lands on the first member (F6)
        await pilot.pause()
        ol, rows = _picker_rows(picker)
        assert ol.get_option_at_index(ol.highlighted).id == "kilosort4"
        await pilot.press("enter")        # choose it
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.SorterPickerScreen)
        foot = app.query_one("#footer").render().plain
        assert "GPU" in foot
