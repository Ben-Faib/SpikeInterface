"""Tests for the typed / prompt_toolkit fallback menu (no Textual).

The fallback is intentionally NON-parity with the Textual app (no accordion,
no explanation pane) — it keeps the always-visible Sorters + Pipeline + Actions.
What it DOES borrow is the per-action ``what`` blurb and the destructive-sort
caveat (so the typed menu still warns before a re-sort), plus the shared
``stream_detail`` per-stream channels/rate/duration in the Data-files guidance.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import sorters  # noqa: E402,F401
import ui  # noqa: E402
import SpikeInterface_Menu as M  # noqa: E402


def test_print_catalog_groups_and_recommends(monkeypatch, capsys):
    catalog = [
        {"name": "tridesclous2", "group": "ready", "runnable": True,
         "recommended": True, "description": "fast", "present": True, "units": 12},
        {"name": "mountainsort5", "group": "docker", "runnable": False,
         "recommended": False, "description": "container", "present": False, "units": 0},
        {"name": "kilosort4", "group": "gpu", "runnable": False,
         "recommended": False, "description": "gpu", "present": False, "units": 0},
    ]
    ui.print_catalog(catalog)
    out = capsys.readouterr().out
    assert "READY TO USE" in out and "DOCKER SORTERS" in out and "NEEDS A GPU" in out
    assert "tridesclous2" in out and "★" in out


def test_docker_confirm_text_per_state():
    assert "download" in ui.docker_confirm_text("not_installed").lower()
    assert "start" in ui.docker_confirm_text("installed_not_running").lower()
    assert "running" in ui.docker_confirm_text("running").lower()


def test_fallback_action_hint_surfaces_what():
    # Each typed action surfaces the same plain-language `what` the Textual
    # explanation pane shows (here for `sort`), not just the terse legacy hint.
    hint = M._fallback_action_hint("sort", "legacy fallback hint", active_info=None)
    assert "Detect neurons" in hint            # the `what` text, not the fallback
    assert "legacy fallback hint" not in hint


def test_fallback_action_hint_falls_back_for_unknown_key():
    # A key without a _ACTION_DETAIL entry keeps the legacy _MENU hint.
    hint = M._fallback_action_hint("__quit__", "exit the menu", active_info=None)
    assert hint == "exit the menu"


def test_fallback_sort_hint_warns_when_saved_sort_exists():
    # With a saved sort for the active sorter, the typed `sort` hint carries the
    # destructive re-run caveat so the user is warned before overwriting.
    active = {"name": "tridesclous2", "present": True, "units": 13}
    hint = M._fallback_action_hint("sort", "sort the active sorter", active_info=active)
    assert "replaces" in hint and "tridesclous2" in hint and "13u" in hint


def test_fallback_sort_hint_no_caveat_without_saved_sort():
    active = {"name": "tridesclous2", "present": False, "units": 0}
    hint = M._fallback_action_hint("sort", "sort the active sorter", active_info=active)
    assert "replaces" not in hint and "Detect neurons" in hint


def test_setup_plain_shows_stream_detail_for_present_files(capsys):
    # The Data-files guidance pipes per-stream channels/rate/duration through the
    # shared ui.stream_detail helper, matching the Textual `d` help.
    report = {
        "present": True, "complete": False, "data_dir": "/data/rec",
        "base": "REC", "error": None,
        "files": [
            {"ext": ".ns2", "label": "LFP — analog @ 1 kHz", "present": True},
            {"ext": ".ns5", "label": "Broadband — raw @ 30 kHz (sortable)", "present": True},
            {"ext": ".nev", "label": "Spike events + digital markers", "present": False},
        ],
    }
    pipeline = [
        {"stage": "LFP (.ns2)", "status": "PASS", "detail": "24 ch, 132.0s @ 1000 Hz"},
        {"stage": "Broadband (.ns5)", "status": "PASS", "detail": "22 ch, 132.0s @ 30000 Hz"},
        {"stage": ".nev online units", "status": "FAIL", "detail": "no events"},
    ]
    M._print_setup_plain(report, pipeline)
    # rich soft-wraps at the console width, so collapse whitespace before matching.
    out = " ".join(capsys.readouterr().out.split())
    assert "30000 Hz" in out and "22 ch" in out      # present broadband detail surfaced
    assert "no events" not in out                     # FAIL/.nev row contributes no detail
