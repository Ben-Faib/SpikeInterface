"""Pilot tests for Spike 2.0 (scripts/spike_app.py): the rail, Home's next step,
the six stage panes, Settings, the palette, Runs and reproduce - over the
FakeController (tests/conftest.py), which mirrors MenuController's v2 contract.
The modal screens v2 reuses are tested in test_menu_app.py.
"""
from __future__ import annotations

import journey
import menu_app
import spike_app
import ui
from textual.widgets import OptionList, Static


def _plain(app, sel) -> str:
    return app.query_one(sel, Static).render().plain


def _ids(ol) -> list:
    return [ol.get_option_at_index(i).id for i in range(ol.option_count)]


async def _wait(pilot, cond, budget=5.0):
    from time import monotonic

    end = monotonic() + budget
    while monotonic() < end:
        await pilot.pause(0.05)
        if cond():
            return True
    return False


# --- the rail, the keys, Home ------------------------------------------------ #
async def test_boots_on_home_with_the_rail_and_one_next_step(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        rail = _plain(app, "#rail")
        for n, name in enumerate(spike_app.STAGE_NAMES, 1):
            assert f"{n} {name}" in rail
        card = app.query_one("#home #card", Static).render().plain
        assert app.c.steps[0]["title"] in card and app.c.steps[0]["label"] in card
        keys = _plain(app, "#keys")
        assert app.c.steps[0]["label"] in keys and "1-6" in keys and "/" in keys


async def test_number_keys_switch_stages_and_escape_returns_home_never_quits(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        for n in range(1, 7):
            await pilot.press(str(n))
            await pilot.pause()
            assert app._stage == n
            assert app.query_one("#panes").current == spike_app.SpikeApp.PANE_IDS[n]
        await pilot.press("escape")
        await pilot.pause()
        assert app._stage == 0
        await pilot.press("escape")          # on Home: a no-op, never an exit
        await pilot.pause()
        assert app.is_running and app._stage == 0


async def test_enter_on_home_does_the_next_step_and_s_offers_the_next_one(make_app):
    app = make_app(present=True)            # steps: judge the units, build the report
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        first, second = app.c.steps[0], app.c.steps[1]
        await pilot.press("s")
        await pilot.pause()
        assert second["title"] in app.query_one("#home #card", Static).render().plain
        await pilot.press("s")               # wraps back round
        await pilot.press("enter")
        await pilot.pause()
        assert first["action"] == "stage:4" and app._stage == 4


async def test_without_data_the_next_step_is_the_recording_and_data_actions_guide(make_app):
    app = make_app(present=False)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert "Add the recording" in app.query_one("#home #card", Static).render().plain
        assert "! 1 Data" in _plain(app, "#rail") or "!1" in _plain(app, "#rail")
        app.do("sort")                        # needs the recording
        await pilot.pause()
        assert app._stage == 1
        assert "needs the recording" in _plain(app, "#status")
        assert not isinstance(app.screen, menu_app.SortProgressScreen)


async def test_home_probe_map_shows_units_at_their_contacts(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        pmap = app.query_one("#home #pmap", Static).render().plain
        assert "UNITS ON THE PROBE" in pmap
        assert "·0" in pmap and "not judged" in pmap  # unit 0 sits on contact 1, unjudged


# --- 1 Data ----------------------------------------------------------------- #
async def test_data_pane_lists_the_files_and_f_changes_the_folder(make_app):
    from textual.widgets import Input

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("1")
        await pilot.pause()
        head = app.query_one("#data #head", Static).render().plain
        assert "PFCM7_d0ephys_Block2.ns5" in head and "/data/recordings" in head
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.InputModal)
        app.screen.query_one(Input).value = "/elsewhere"
        await pilot.press("enter")
        await pilot.pause()
        assert app.c.cfg["data_dir"] == "/elsewhere"
        await pilot.press("o")
        await pilot.pause()
        assert "/data/recordings" in app.c.opened


# --- 2 Probe ---------------------------------------------------------------- #
async def test_probe_pane_shows_every_value_and_enter_activates(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        vals = app.query_one("#probe #pvals", Static).render().plain
        for word in ("ACTIVE PROBE", "editable", "pitch um", "derived", "contacts",
                     "closest pitch", "this recording", "saved in"):
            assert word in vals, word
        ol = app.query_one("#plib", OptionList)
        ol.highlighted = _ids(ol).index("linear-16-50um")
        await pilot.pause()
        assert "SELECTED PROBE (not active)" in app.query_one("#probe #pvals", Static).render().plain
        await pilot.press("enter")
        await pilot.pause()
        assert app.c.active_probe == "linear-16-50um"


async def test_editing_a_builtin_probe_edits_a_copy(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ProbeEditorScreen)
        assert app.screen._profile["name"] == "nnx-a1x16-3mm-100-copy"
        assert app.screen._profile["builtin"] is False


async def test_imported_probe_edit_refused_names_next_step(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        ol = app.query_one("#plib", OptionList)
        ol.highlighted = _ids(ol).index("lab-imported-16")
        await pilot.press("e")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.ProbeEditorScreen)
        assert "import the file" in _plain(app, "#status")


async def test_probe_import_and_delete(make_app):
    from textual.widgets import Input

    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        app.screen.query_one(Input).value = "not-a-probe.txt"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.InputModal)       # refused in place
        assert "couldn't import" in app.screen.query_one("#ierror", Static).render().plain
        app.screen.query_one(Input).value = "lab.json"
        await pilot.press("enter")
        await pilot.pause()
        assert any(p["name"] == "imported-x" for p in app.c.probe_catalog())
        ol = app.query_one("#plib", OptionList)
        ol.highlighted = _ids(ol).index("imported-x")
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.ConfirmModal)
        await pilot.press("y")
        await pilot.pause()
        assert not any(p["name"] == "imported-x" for p in app.c.probe_catalog())


# --- 3 Sort ----------------------------------------------------------------- #
async def test_sort_pane_states_what_the_next_sort_uses_and_starts_it(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("3")
        await pilot.pause()
        nxt = app.query_one("#sort #snext", Static).render().plain
        assert "THE NEXT SORT WILL USE" in nxt and "300-6000 Hz" in nxt
        assert "nothing is overwritten" in nxt
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.SortProgressScreen)
        assert app.c.sort_span == "quick"


async def test_sort_pane_enter_activates_another_sorter(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("3")
        await pilot.pause()
        ol = app.query_one("#sorters", OptionList)
        ol.highlighted = _ids(ol).index("spykingcircus2")
        await pilot.press("enter")
        await pilot.pause()
        assert app.c.active_sorter == "spykingcircus2"


async def test_sort_blocked_when_the_active_sorter_needs_docker_thats_down(make_app):
    app = make_app(present=True)
    app.c.active_blocked_on_docker = lambda: True
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("3", "f")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.SortProgressScreen)
        assert "Docker" in _plain(app, "#status")


# --- 4 Judge ---------------------------------------------------------------- #
async def test_judge_queue_puts_flagged_units_first_and_shows_evidence(make_app):
    app = make_app(present=True)
    app.c.split_candidates = 2
    app.c.reload()
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("4")
        pane = app.query_one("#judge")
        assert await _wait(pilot, lambda: bool(pane._ev))
        ol = app.query_one("#queue", OptionList)
        ids = _ids(ol)
        assert ids[0] is None and ids[1] in ("1", "2")     # "flagged" heading, then a flagged unit
        card = app.query_one("#judge #card", Static).render().plain
        assert "UNIT" in card and "SHAPE ON CONTACTS" in card
        assert "refractory window" in card and "spikes inside it" in card
        assert "likely two cells" in card or "Phy" in card


async def test_judging_labels_the_record_and_moves_to_the_next_unjudged_unit(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        pane = app.query_one("#judge")
        first = pane._unit_id()
        await pilot.press("g")
        await pilot.pause()
        assert ("tridesclous2", first, "good") in app.c.labelled
        assert pane._unit_id() != first
        assert "1/12" in _plain(app, "#rail")


async def test_judge_refusal_writes_nothing(make_app):
    app = make_app(present=True)
    app.c.triage_blocked = "the record was written for a different sort"
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert app.c.labelled == []
        assert "different sort" in _plain(app, "#status")


# --- 5 Apply / 6 Share -------------------------------------------------------- #
async def test_apply_pane_shows_the_decisions_and_enter_applies_in_app(make_app):
    app = make_app(present=True)
    app.c.labels["tridesclous2"] = {0: "good", 3: "noise"}
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("5")
        await pilot.pause()
        body = app.query_one("#apply #apply", Static).render().plain
        assert "APPLY 2 DECISIONS" in body and "1 good" in body and "1 noise" in body
        await pilot.press("enter")
        await pilot.pause()
        assert ("apply", None) in app.c.commands
        assert isinstance(app.screen, spike_app.CommandScreen)
        assert await _wait(pilot, lambda: app.screen._done is not None)
        await pilot.press("enter")
        await pilot.pause()
        assert ("apply", True) in app.c.finished


async def test_share_rows_open_build_and_export(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("6")
        await pilot.pause()
        ol = app.query_one("#outs", OptionList)
        assert _ids(ol)[:2] == ["report", "phy"]
        await pilot.press("enter")                       # report not built yet: build it
        await pilot.pause()
        assert isinstance(app.screen, menu_app.BuildProgressScreen)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert app.c.recipes == [None]


# --- Settings ------------------------------------------------------------------ #
async def test_settings_lists_every_setting_with_value_and_help(make_app):
    import settings as S

    app = make_app(present=True)
    async with app.run_test(size=(110, 44)) as pilot:
        await pilot.press("comma")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.SettingsScreen)
        ids = _ids(app.screen.query_one("#slist", OptionList))
        assert [s["key"] for s in S.SCHEMA] == [i for i in ids if i is not None]
        assert ".si_menu.json" in app.screen.query_one("#sintro", Static).render().plain
        assert "run_info.json" in app.screen.query_one("#sintro", Static).render().plain


async def test_settings_edit_validates_in_place_then_saves_and_resets(make_app):
    from textual.widgets import Input

    app = make_app(present=True)
    async with app.run_test(size=(110, 44)) as pilot:
        await pilot.press("comma")
        await pilot.pause()
        scr = app.screen
        ol = scr.query_one("#slist", OptionList)
        ol.highlighted = _ids(ol).index("freq_min")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.InputModal)
        app.screen.query_one(Input).value = "9000"          # above the high edge
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.InputModal)
        assert "between" in app.screen.query_one("#ierror", Static).render().plain
        app.screen.query_one(Input).value = "250"
        await pilot.press("enter")
        await pilot.pause()
        assert app.c.cfg["sort_settings"]["freq_min"] == 250.0
        row = ol.get_option_at_index(ol.highlighted).prompt.plain
        assert "250" in row and "default 300" in row
        await pilot.press("d")
        await pilot.pause()
        assert "freq_min" not in app.c.cfg["sort_settings"]


async def test_settings_toggle_choice_and_link_rows(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 44)) as pilot:
        await pilot.press("comma")
        await pilot.pause()
        ol = app.screen.query_one("#slist", OptionList)
        ol.highlighted = _ids(ol).index("keep_analog")
        await pilot.press("enter")
        await pilot.pause()
        assert app.c.cfg["sort_settings"]["keep_analog"] is True
        ol.highlighted = _ids(ol).index("bad_channel_method")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)
        await pilot.press("escape")
        await pilot.pause()
        ol.highlighted = _ids(ol).index("active_probe")
        await pilot.press("enter")
        await pilot.pause()
        assert app._stage == 2 and not isinstance(app.screen, spike_app.SettingsScreen)


# --- palette, runs, reproduce, help -------------------------------------------- #
async def test_palette_filters_and_runs(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press("slash")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.PaletteScreen)
        await pilot.press("p", "h", "y")
        await pilot.pause()
        ids = _ids(app.screen.query_one("#plist", OptionList))
        assert ids[0] == "phy" and "import_phy" in ids
        await pilot.press("escape")
        await pilot.press("slash")
        await pilot.pause()
        for ch in "settings":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.SettingsScreen)


async def test_every_palette_action_is_wired(make_app):
    app = make_app(present=True)
    skip = {"quit", "traces", "gui"}      # quit exits; the Qt windows suspend the app
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        for key, *_rest in journey.ACTIONS:
            if key in skip:
                continue
            app.do(key)
            await pilot.pause()
            assert "nothing is wired" not in _plain(app, "#status"), key
            while app.screen is not app.screen_stack[0]:
                app.pop_screen()
                await pilot.pause()


async def test_runs_screen_reproduces_and_shows_the_match_report(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        app.do("runs")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.RunsScreen)
        detail = app.screen.query_one("#rdetailbody", Static).render().plain
        assert "RECIPE" in detail and "REPRODUCE CHECKS" in detail
        await pilot.press("c")
        await pilot.pause()
        assert app.c.made_current == ["20260819-035117-c7184d"]
        await pilot.press("enter")                        # reproduce the highlighted run
        await pilot.pause()
        assert isinstance(app.screen, spike_app.CommandScreen)
        assert await _wait(pilot, lambda: app.screen._done is not None)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, spike_app.ReproduceReportScreen)
        body = app.screen.query_one("#rbody", Static).render().plain
        assert "noise floor" in body and "WITHIN TOLERANCE" in body and "REGENERATED" in body


def test_help_names_every_global_key_and_every_pane_key():
    lines = dict((k, b) for k, _t, b in ui.HELP_TOPICS)["keys"]
    text = "\n".join(lines)
    for key in ("1-6", "esc", "/", ",", "?", "q", "Ctrl-C"):
        assert key in text, key
    panes = {spike_app.DataPane: "1 Data", spike_app.ProbePane: "2 Probe",
             spike_app.SortPane: "3 Sort", spike_app.JudgePane: "4 Judge",
             spike_app.ApplyPane: "5 Apply", spike_app.SharePane: "6 Share"}
    for cls, label in panes.items():
        start = next(i for i, ln in enumerate(lines) if ln.startswith(label))
        block = lines[start]
        for ln in lines[start + 1:]:
            if not ln.startswith(" "):
                break
            block += "\n" + ln
        keys = {b.key for b in cls.BINDINGS} | {r[0] for r in getattr(cls, "ROWS", ())}
        for k in keys - {"enter"}:
            assert f"{k} " in block, (label, k)


async def test_every_pane_draws_at_small_and_wide_sizes(make_app):
    for size in ((80, 24), (64, 20), (150, 50)):
        app = make_app(present=True)
        async with app.run_test(size=size) as pilot:
            for n in range(0, 7):
                app.go(n)
                await pilot.pause()
                assert "couldn't draw" not in _plain(app, "#status"), (size, n)
                keys = _plain(app, "#keys")
                assert len(keys) <= size[0] - 2


async def test_splash_shows_the_checklist_and_any_key_skips_it():
    from conftest import FakeController

    app = spike_app.SpikeApp(FakeController(), splash=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, spike_app.SplashScreen)
        body = app.screen.query_one("#splash", Static).render().plain
        assert "recording" in body and "probe" in body
        await pilot.press("space")
        await pilot.pause()
        assert not isinstance(app.screen, spike_app.SplashScreen)


# --- pure painters --------------------------------------------------------------- #
def test_key_line_drops_whole_items_never_half_a_label():
    items = [("f", "folder"), ("o", "open"), ("e", "explore"), ("t", "traces")]
    for width in (10, 20, 30, 80):
        t = spike_app.key_line(items, width)
        assert len(t) <= width
        for _k, label in items:
            assert (label in t.plain) or (label[:3] not in t.plain)


def test_rail_fits_every_width_and_marks_the_current_stage():
    stages = [{"n": i + 1, "label": n, "mark": "done", "caption": "x" * 20}
              for i, n in enumerate(spike_app.STAGE_NAMES)]
    for width in (40, 60, 78, 98, 140):
        top, cap = spike_app.rail_lines(stages, 3, "#9b8cff", width)
        assert len(top) <= width and len(cap) <= width
    top, _ = spike_app.rail_lines(stages, 3, "#9b8cff", 98)
    assert "3 Sort" in top.plain and "✓" in top.plain


def test_fuzzy_prefers_contiguous_and_early_matches():
    assert spike_app._fuzzy("phy", "Export to Phy")[0] < spike_app._fuzzy("phy", "p h y")[0]
    assert spike_app._fuzzy("zzz", "Export to Phy") is None
    assert spike_app._fuzzy("", "anything") == (0, [])


def test_plots_are_the_size_asked_for():
    rows = spike_app.line_plot([0, -5, -60, 10, 3, 0], 20, 5, "#fff")
    assert len(rows) == 5 and all(len(r) == 20 for r in rows)
    bars = spike_app.bar_rows([0, 3, 9, 1], 4, "#fff", hot=1)
    assert len(bars) == 4 and all(len(r) == 4 for r in bars)
    assert len(spike_app.wordmark("#9b8cff")) == 6


def test_no_member_shadows_a_textual_internal():
    """LESSONS S10: `_render`, `_name` and `run_action` each silently broke v2 by
    overriding a Textual internal. Any private member (or run_action) our classes
    define must not already exist on the Textual base they extend."""
    import inspect

    from textual.app import App
    from textual.widget import Widget

    for _n, cls in inspect.getmembers(spike_app, inspect.isclass):
        if cls.__module__ != "spike_app" or not issubclass(cls, (Widget, App)):
            continue
        base = App if issubclass(cls, App) else Widget
        base_names = set(dir(base))
        generated = set(vars(type("_Blank", (base,), {})))   # what Textual adds to any subclass
        for name in set(vars(cls)) - generated:
            private = name.startswith("_") and not name.startswith("__")
            if (private or name == "run_action") and name in base_names:
                raise AssertionError(f"{cls.__name__}.{name} shadows Textual's {base.__name__}.{name}")
