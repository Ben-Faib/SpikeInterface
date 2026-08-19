"""Pilot tests for the probe-geometry UI (ProbeSetupScreen/Manager/Editor)."""
from __future__ import annotations

import menu_app
from conftest import FakeController
from textual.widgets import OptionList, Static


def _app(**kw):
    return menu_app.SpikeMenuApp(FakeController(**kw))


async def test_probe_setup_shows_on_first_run():
    c = FakeController(present=True)
    c.want_probe_setup = True
    app = menu_app.SpikeMenuApp(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        # the welcome gate is off (want_welcome False), so probe setup is on top
        assert isinstance(app.screen, menu_app.ProbeSetupScreen)


async def test_probe_setup_skip_keeps_default():
    c = FakeController(present=True)
    c.want_probe_setup = True
    before = c.active_probe                      # the real NNX default
    app = menu_app.SpikeMenuApp(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")             # Esc = keep the current default
        await pilot.pause()
        assert c.want_probe_setup is False
        assert c.active_probe == before          # default kept, not forced to placeholder


async def test_probe_setup_lists_builtin_profiles():
    c = FakeController(present=True)
    c.want_probe_setup = True
    app = menu_app.SpikeMenuApp(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        ol = app.screen.query_one(OptionList)
        assert ol.option_count >= 3   # ≥1 built-in profile + "Manage probes…" + "Keep this probe"


async def test_p_opens_probe_manager():
    app = _app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ProbeManagerScreen)


async def test_probe_manager_activate_changes_active():
    c = FakeController(present=True)
    app = menu_app.SpikeMenuApp(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        mgr = app.screen
        ol = mgr.query_one("#probelist", OptionList)
        # move to the second profile (linear-16) and activate it
        for i in range(ol.option_count):
            if ol.get_option_at_index(i).id == "linear-16-50um":
                ol.highlighted = i
                break
        await pilot.press("enter")
        await pilot.pause()
        assert c.active_probe == "linear-16-50um"


async def test_probe_reachable_from_manage_line():
    # D5: probe is a MANAGE action — on the dim line and the p key, not a list row.
    app = _app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert "p probe" in app.query_one("#footer").render().plain  # D6: merged key line
        await pilot.press("p")
        await pilot.pause()
        import menu_app
        assert isinstance(app.screen, menu_app.ProbeManagerScreen)
