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
    ("compare", "Compare sorters", "agreement matrix", True),
    ("params", "Edit sorter parameters", "tune the active sorter", False),
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
        self.use_docker = False
        self.sorters = ["tridesclous2", "spykingcircus2"]
        self.sorter_params: dict[str, dict] = {}
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd) for k, t, h, nd in ACTIONS]
        self.ran: list[tuple[str, str | None]] = []
        self.ran_compare = None
        self.params_set = None
        self._present = present
        self.reload()

    def reload(self) -> None:
        st = "PASS" if self._present else "FAIL"
        self.pipeline = [
            {"stage": "LFP (.ns2)", "status": st, "detail": "24 ch, 132s @ 1000 Hz"},
            {"stage": "Broadband (.ns5)", "status": st, "detail": "22 ch, 132s @ 30000 Hz"},
            {"stage": ".nev online units", "status": st, "detail": "8 units"},
        ]
        rows = [("tridesclous2", True, 12, 132.0), ("spykingcircus2", True, 7, 132.0),
                ("mountainsort5", False, 0, 0.0)]
        self.infos = [
            {"name": n, "present": p, "units": u, "duration": d, "active": False,
             "status": "docker" if n == "mountainsort5" else "local"}
            for n, p, u, d in rows if n in self.sorters
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

    def toggle_docker(self) -> bool:
        self.use_docker = not self.use_docker
        # simulate the runnable list growing/shrinking with Docker
        self.sorters = (["tridesclous2", "spykingcircus2", "mountainsort5"]
                        if self.use_docker else ["tridesclous2", "spykingcircus2"])
        if self.active_idx >= len(self.sorters):
            self.active_idx = 0
        self.reload()
        return self.use_docker

    def default_params(self, sorter: str) -> dict:
        return {"detect_threshold": 5.0, "freq_min": 300.0, "apply_preprocessing": True}

    def param_descriptions(self, sorter: str) -> dict:
        return {"detect_threshold": "spike detection threshold (MAD)",
                "freq_min": "high-pass cutoff (Hz)",
                "apply_preprocessing": "run the built-in filtering"}

    def get_overrides(self, sorter: str) -> dict:
        return dict(self.sorter_params.get(sorter, {}))

    def set_params(self, sorter: str, overrides: dict) -> None:
        self.params_set = (sorter, overrides)
        self.sorter_params[sorter] = overrides

    def saved_sorters(self) -> list[str]:
        return [i["name"] for i in self.infos if i.get("present")]

    def run_compare(self, pair) -> tuple[bool, str, bool]:
        self.ran_compare = tuple(pair)
        return True, f"✓ compared {pair}", True

    def run(self, key: str, span: str | None) -> tuple[bool, str, bool]:
        self.ran.append((key, span))
        return True, f"✓ ran {key}", key in ("sort", "compare")


@pytest.fixture
def make_controller():
    return FakeController
