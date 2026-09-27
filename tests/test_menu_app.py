"""Textual Pilot tests for the modal screens Spike 2.0 reuses (scripts/menu_app.py):
the in-UI sort and its result card, the report build, the parameter editor, the
Docker download and the Sorters and Docker hub - plus the shared help text and the
small formatting helpers. The v2 dashboard itself (the rail, the stage panes,
Settings, the palette, Runs) is tested in test_spike_app.py.
"""
from __future__ import annotations

import menu_app
import ui
from textual.widgets import Static


def test_help_teaches_the_real_workflow():
    # F2: help is "which question → which surface → which key", and it teaches the
    # workflow the workbench ACTUALLY has. The June three-step app (Explore → Sort
    # → Report, no curation, no Phy, no runs) is the defect this replaces.
    topics = {k: (t, b) for k, t, b in ui.HELP_TOPICS}
    assert "steps" not in topics                       # the old three-step topic
    for key in ("questions", "getdata", "sortcurate", "lookshare", "words", "wrong"):
        assert key in topics, key
    everything = "\n".join(l for _t, b in topics.values() for l in b).lower()
    # the surfaces that exist today, each named where a researcher would ask for it
    for word in ("judge the units", "export to phy", "curated", "curation.py",
                 "runs.py", "compare", "strong", "noise floor"):
        assert word in everything, word
    # the same vocabulary docs/WORKFLOW.md uses (one workflow, one set of words)
    for word in ("unit", "contact", "run", "curation"):
        assert word in "\n".join(topics["words"][1]).lower(), word


def test_help_lines_fit_the_help_pane():
    # The help body is a LAID-OUT pane (key/answer columns), not free prose: at the
    # default 80-col terminal it is 50 content columns wide, and a line that wraps
    # breaks the columns. Titles must fit the 20-column topic list.
    for key, title, lines in ui.HELP_TOPICS:
        assert len(title) <= 18, (key, title)
        for line in lines:
            assert len(line) <= 50, (key, len(line), line)


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


class _LiveSortScreen(menu_app.SortProgressScreen):
    """SortProgressScreen with no subprocess, so the run stays RUNNING until the
    test says otherwise (the ``["true"]`` child exits at once and the reader
    synthesises `done`, which would end the run mid-assertion)."""

    async def _run(self) -> None:
        pass


async def test_sort_progress_shows_the_pending_phases_up_front(make_app):
    # D2b: the run announces its whole checklist before doing anything, so the
    # modal shows what is still coming instead of growing one line at a time -
    # and the phases that never ran vanish when the run ends, rather than sitting
    # there looking queued.
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = _LiveSortScreen(["true"], app._accent)
        await app.push_screen(screen)
        await pilot.pause()
        screen.handle_event({"t": "plan", "n": 3, "phases": [
            {"i": 1, "title": "Read broadband"}, {"i": 2, "title": "Preprocess"},
            {"i": 3, "title": "Sort"}]})
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        # every phase named before any work started, none of them claimed as running
        assert all(t in body for t in ("Read broadband", "Preprocess", "Sort"))
        assert "▶" not in body and "✓" not in body

        screen.handle_event({"t": "phase", "i": 1, "n": 3, "title": "Read broadband"})
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "▶ Read broadband" in body and "· Preprocess" in body

        screen.handle_event({"t": "error", "ok": False, "message": "boom"})
        await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "Read broadband" in body and "Preprocess" not in body


async def test_sort_progress_renders_summary_card_and_note(make_app):
    # The array/yield headline card shows on the final screen, and a non-fatal
    # metrics caveat (done.note) renders as a ⚠ line alongside the ✓ success - so a
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
        # carries a metrics-failure note, so the analyzer is GONE - the card must
        # not offer report/GUI chaining (F2), only the close.
        assert "7 units" in body and "r build the report" not in body
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
    # coexist with the heartbeat spinner - none of them fight. Neuter the worker so
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
        # Collapse: modal closes, the status line carries the live download.
        await pilot.press("c")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.DownloadProgressScreen)
        assert "mountainsort5" in app.query_one("#status", Static).render().plain
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


async def test_escape_does_not_quit_the_app(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.is_running           # Esc no longer hard-quits the dashboard


async def test_manage_hub_clears_saved_sort(make_app):
    # In the hub, pressing 'c' on a saved sorter clears it via the controller.
    app = make_app(present=True)
    c = app.c
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.do("manage")
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
        app.do("manage")
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


def test_fmt_when_relative_dates():
    from datetime import datetime, timedelta
    today = datetime.now().replace(hour=14, minute=18).isoformat(timespec="minutes")
    assert menu_app._fmt_when(today) == "14:18"
    old = (datetime.now() - timedelta(days=6)).replace(hour=9, minute=5)
    out = menu_app._fmt_when(old.isoformat(timespec="minutes"))
    assert out.endswith("09:05") and len(out) > len("09:05")   # carries its date
    assert menu_app._fmt_when("12:00") == "12:00"              # pre-ISO fallback


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
        assert "14 units" in body and "9 pass the quality rule" in body
        assert "noise floor 4.02 µV" in body and "expected" in body
        assert "0:15" in body                                   # emitter elapsed
        assert "partial: first 30 s of 132 s" in body           # honest window
        assert "0.1 s" in body                                  # per-phase duration
        assert "r build the report" in body and "i inspect in GUI" in body
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
        await pilot.press("3")            # 3 Sort
        await pilot.pause()
        await pilot.press("f")            # f: sort the full recording -> progress modal
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, menu_app.SortProgressScreen)
        _drive_finished_sort(screen)
        await pilot.pause()
        await pilot.press("r")            # chain: close + build report (D3b modal)
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
        await pilot.press("r")
        await pilot.pause()
        assert app.screen is screen       # still up - no chain mid-run


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
    # frac 0.996 would round to a displayed "100%" under a running step - the bar
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
        assert "r build the report" not in body and "↵ close" in body
        await pilot.press("r")            # must be a no-op
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
        assert "r build the report" not in body
        assert "partial: first 30 s" in body          # F8: window fact on amber too
        await pilot.press("i")
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
# T2 - journeys: whole flows through the real screens and the real event pipe
# ========================================================================== #

def _events_argv(tmp_path, events):
    """argv for a child that speaks the real protocol on stdout - the sort worker
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


async def test_chain_suppression_states_name_why(make_app):
    # When the card withholds report/GUI chaining (analyzer gone), the reason is
    # ON the card - a silently missing option is a dead-end without a name.
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
        assert "r build the report" not in body
        assert "quality metrics failed" in body   # the why, on the card


async def test_param_editor_orders_and_marks_overrides(make_app):
    app = make_app(present=True)
    app.c.sorter_params["tridesclous2"] = {"freq_min": 250.0}
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("3", "e")       # e on 3 Sort: the sorter parameters
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
        await pilot.press("3", "e")       # e on 3 Sort: the sorter parameters
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
        app.do("manage")
        await pilot.pause()
        hub = app.screen.query_one("#hublist")
        assert isinstance(hub, menu_app.NavList)
        before = hub.highlighted
        await pilot.press("j")
        await pilot.pause()
        assert hub.highlighted == (before or 0) + 1
