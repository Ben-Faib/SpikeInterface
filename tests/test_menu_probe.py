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
