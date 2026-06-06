"""Pytest setup for the menu tests.

Adds ``scripts/`` to ``sys.path`` (the project isn't an installed package) and
provides a lightweight ``FakeController`` so the Textual app can be driven with
Textual's ``run_test`` / ``Pilot`` harness without loading SpikeInterface or any
recording. The fake mirrors the real ``MenuController`` interface that
``scripts/menu_app.py`` depends on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# Action table mirroring SpikeInterface_Menu._ACTIONS (keys + needs_data), so
# number-key indices and the data-dimming behaviour match the real app.
ACTIONS = [
    ("explore", "Explore raw data", "static figures", True),
    ("sort", "Run / re-run sorting", "full or quick", True),
    ("report", "Build & open report", "interactive HTML", True),
    ("gui", "Open GUI inspector", "sigui", True),
    ("traces", "Scroll raw traces", "ephyviewer", True),
    ("compare", "Compare the two sorters", "agreement matrix", True),
    ("verify", "Verify install", "smoke test", False),
    ("theme", "Change colour theme", "accent", False),
    ("data-setup", "Data files & setup help", "where files go", False),
    ("quit", "Quit", "exit", False),
]


class FakeController:
    """Stand-in for MenuController; no I/O, no SpikeInterface."""

    quick_seconds = 30
    header = "University of Pittsburgh · SpikeInterface"
    sorters = ["tridesclous2", "spykingcircus2"]
    themes = {"periwinkle": "#9b8cff", "sea-green": "#56d39a", "amber": "#e3a008"}

    def __init__(self, present: bool = True):
        self.theme_name = "periwinkle"
        self.accent = self.themes[self.theme_name]
        self.active_idx = 0
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd) for k, t, h, nd in ACTIONS]
        self.ran: list[tuple[str, str | None]] = []
        self._present = present
        self.reload()

    def reload(self) -> None:
        st = "PASS" if self._present else "FAIL"
        self.pipeline = [
            {"stage": "LFP (.ns2)", "status": st, "detail": "24 ch, 132s @ 1000 Hz"},
            {"stage": "Broadband (.ns5)", "status": st, "detail": "22 ch, 132s @ 30000 Hz"},
            {"stage": ".nev online units", "status": st, "detail": "8 units"},
        ]
        self.infos = [
            {"name": "tridesclous2", "present": True, "units": 12, "duration": 132.0, "active": True},
            {"name": "spykingcircus2", "present": False, "units": 0, "duration": 0.0, "active": False},
        ]
        for i, info in enumerate(self.infos):
            info["active"] = (i == self.active_idx)
        self.data_report = {
            "present": self._present,
            "data_dir": "/data/recordings",
            "base": "PFCM7_d0ephys_Block2" if self._present else None,
            "files": [
                {"ext": ".ns2", "label": "LFP — analog @ 1 kHz", "present": self._present},
                {"ext": ".ns5", "label": "Broadband — raw @ 30 kHz", "present": self._present},
                {"ext": ".nev", "label": "Spike events", "present": self._present},
            ],
            "error": None if self._present else "No Blackrock .nev/.nsX files found in '/data/recordings'.",
        }

    def set_active(self, idx: int) -> None:
        self.active_idx = idx % len(self.sorters)
        for i, info in enumerate(self.infos):
            info["active"] = (i == self.active_idx)

    def set_theme(self, name: str) -> str:
        self.theme_name = name
        self.accent = self.themes[name]
        return self.accent

    def run(self, key: str, span: str | None) -> tuple[bool, str, bool]:
        self.ran.append((key, span))
        return True, f"✓ ran {key}", key in ("sort", "compare")


@pytest.fixture
def make_controller():
    return FakeController
