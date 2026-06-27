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
    ("manage", "Manage sorters", "download · delete", False),
    ("verify", "Verify install", "smoke test", False),
    ("theme", "Change colour theme", "accent", False),
    ("help", "Help", "what each step does · sorters · Docker · data files", False),
    ("quit", "Quit", "exit", False),
]


class FakeController:
    """Stand-in for MenuController; no I/O, no SpikeInterface."""

    quick_seconds = 30
    header = "University of Pittsburgh · SpikeInterface"
    sorters = ["tridesclous2", "spykingcircus2"]
    themes = {"periwinkle": "#9b8cff", "sea-green": "#56d39a", "amber": "#e3a008"}

    def __init__(self, present: bool = True, use_docker: bool = False):
        self.theme_name = "periwinkle"
        self.accent = self.themes[self.theme_name]
        self.use_docker = use_docker
        self.sorters = (["tridesclous2", "spykingcircus2", "mountainsort5", "herdingspikes"]
                        if use_docker else ["tridesclous2", "spykingcircus2"])
        self.active_sorter = "tridesclous2"
        self.active_idx = 0
        self.sorter_params: dict[str, dict] = {}
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd) for k, t, h, nd in ACTIONS]
        self.ran: list[tuple[str, str | None]] = []
        self.ran_compare = None
        self.downloaded: list[str] = []
        self.deleted_images: list[str] = []
        self.cleared_sorts: list[str] = []
        # Which Docker images are cached locally. herdingspikes starts cached;
        # mountainsort5 does not — so the badge tests cover both states. A download/
        # delete mutates this set and SURVIVES reload() (a real reload re-probes the
        # daemon and would see the now-cached / now-removed image).
        self._cached_images: set[str] = {"herdingspikes"}
        self._cleared: set[str] = set()
        self.params_set = None
        self.docker_state = "running"   # tests flip this to exercise the dialog
        self.started_docker = False
        self.want_welcome = False       # off by default so boot tests see no modal
        self.welcome_seen = False
        self._present = present
        self.reload()

    # A small fake universe spanning all four groups. READY sorters come first so
    # the active sorter sits at infos index 0/1 (mirrors the real catalog order).
    _UNIVERSE = [
        # name, group, units (None = no saved sort)
        ("tridesclous2", "ready", 12),
        ("spykingcircus2", "ready", 7),
        ("mountainsort5", "docker", None),
        ("herdingspikes", "docker", None),
        ("kilosort4", "gpu", None),
    ]

    def reload(self) -> None:
        st = "PASS" if self._present else "FAIL"
        self.pipeline = [
            {"stage": "LFP (.ns2)", "status": st, "detail": "24 ch, 132s @ 1000 Hz"},
            {"stage": "Broadband (.ns5)", "status": st, "detail": "22 ch, 132s @ 30000 Hz"},
            {"stage": ".nev online units", "status": st, "detail": "8 units"},
        ]
        runnable = set(self.sorters)
        self.infos = []
        for name, group, units in self._UNIVERSE:
            present = (units is not None) and (name not in self._cleared)
            info = {
                "name": name, "group": group,
                "status": ("docker" if group == "docker" else
                           "gpu" if group == "gpu" else "local"),
                "runnable": name in runnable,
                "recommended": name == "tridesclous2",
                "description": f"{name} description.",
                "present": present, "units": units or 0,
                "duration": 132.0 if present else 0.0,
                "active": name == self.active_sorter,
                "overrides": len(self.sorter_params.get(name, {})),
            }
            if group == "docker":
                # Cached-image state lives in self._cached_images so a download/delete
                # survives reload() (herdingspikes starts cached, mountainsort5 not).
                cached = name in self._cached_images
                info["image"] = f"spikeinterface/{name}-base:latest"
                info["img_present"] = cached
                info["img_size"] = 1_100_000_000 if cached else None
            else:
                info["image"] = None
                info["img_present"] = None
                info["img_size"] = None
            self.infos.append(info)
        self._mark_active()
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

    def _mark_active(self) -> None:
        for n, info in enumerate(self.infos):
            info["active"] = (info["name"] == self.active_sorter)
            if info["active"]:
                self.active_idx = n

    def set_active_by_name(self, name: str) -> bool:
        if name not in self.sorters:
            return False
        self.active_sorter = name
        self._mark_active()
        return True

    def cycle_active(self) -> None:
        i = (self.sorters.index(self.active_sorter) + 1) % len(self.sorters)
        self.set_active_by_name(self.sorters[i])

    def set_theme(self, name: str) -> str:
        self.theme_name = name
        self.accent = self.themes[name]
        return self.accent

    def toggle_docker(self) -> bool:
        self.use_docker = not self.use_docker
        self.sorters = (["tridesclous2", "spykingcircus2", "mountainsort5", "herdingspikes"]
                        if self.use_docker else ["tridesclous2", "spykingcircus2"])
        if self.active_sorter not in self.sorters:
            self.active_sorter = self.sorters[0]
        self.reload()
        return self.use_docker

    def docker_status(self, refresh: bool = False) -> dict:
        text = {"running": "✓ Docker is running",
                "installed_not_running": "✗ Docker is installed but not started",
                "not_installed": "You don't have Docker yet"}[self.docker_state]
        return {"state": self.docker_state, "running": self.docker_state == "running",
                "text": text}

    def start_docker(self) -> bool:
        self.started_docker = True
        return True

    def active_blocked_on_docker(self) -> bool:
        return False

    def set_data_dir(self, path) -> bool:
        self.data_dir_set = path
        self.reload()
        return self.data_report.get("present", False)

    def mark_welcome_seen(self) -> None:
        self.want_welcome = False
        self.welcome_seen = True

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

    def action_explain(self, key: str) -> dict:
        info = self.infos[self.active_idx]
        present = self._present
        n_saved = len(self.saved_sorters())
        table = {
            "explore": ("Make quick static figures.",
                        [("recording files", present)], "outputs/*.png"),
            "sort": ("Detect neurons in the broadband signal.",
                     [("broadband .ns5", present)], "outputs/<sorter>/"),
            "report": ("Build an interactive HTML report.",
                       [("recording files", present)], "outputs/report.html"),
            "gui": ("Inspect saved units.",
                    [(f"a saved {self.active_sorter} sort", bool(info.get("present")))],
                    "a desktop window"),
            "traces": ("Scroll raw traces.",
                       [("broadband .ns5", present)], "a desktop window"),
            "compare": ("Agreement matrix between two sorts.",
                        [("two saved sorts", n_saved >= 2)], "outputs/comparison.html"),
        }
        what, needs, output = table.get(key, (key, [], None))
        out = {"what": what, "needs": [{"label": l, "ok": ok} for l, ok in needs]}
        if output:
            out["output"] = output
        if key == "sort" and info.get("present"):
            out["caveat"] = f"Re-running replaces the saved {info['name']} sort ({info['units']}u)."
        return out

    def run_compare(self, pair) -> tuple[bool, str, bool]:
        self.ran_compare = tuple(pair)
        return True, f"✓ compared {pair}", True

    def run(self, key: str, span: str | None) -> tuple[bool, str, bool]:
        self.ran.append((key, span))
        return True, f"✓ ran {key}", key in ("sort", "compare")

    def sort_command(self, span: str | None) -> list[str]:
        # A harmless argv so SortProgressScreen's worker can spawn + exit cleanly in
        # tests (no real run_sorting.py / SpikeInterface). ``true`` exits 0 at once.
        self.sort_span = span
        return ["true"]

    # -- Docker image management (Stage 4: in-UI download / state) ------------- #
    def _docker_info(self, name: str) -> dict | None:
        return next((i for i in self.infos
                     if i["name"] == name and i.get("group") == "docker"), None)

    def image_state(self, name: str) -> dict:
        info = self._docker_info(name)
        present = name in self._cached_images
        return {"image": (info or {}).get("image"),
                "present": present,
                "size": 1_100_000_000 if present else None}

    def download_image(self, name: str, on_progress=None, on_status=None) -> tuple[bool, str]:
        # Drive the screen's callbacks (so the bar/phase-label update path is
        # exercised) then return synchronously — no real ``docker pull``. on_status
        # now emits ONLY phase+count strings (the backend contract), so feed the
        # phase sequence: Downloading -> Extracting. Records the call + caches the
        # image so a post-download reload() shows ✓ ready.
        self.downloaded.append(name)
        if on_status is not None:
            on_status("Downloading 1/2 layers")
        if on_progress is not None:
            on_progress(50, 100)
        if on_status is not None:
            on_status("Extracting 1/2 layers")
        self._cached_images.add(name)
        return True, f"Downloaded {name}"

    def delete_image(self, name: str) -> tuple[bool, str]:
        if name not in self._cached_images:
            return False, f"No downloaded image for {name}."
        self._cached_images.discard(name)
        self.deleted_images.append(name)
        return True, f"Removed Docker image for {name}"

    def clear_saved_sort(self, name: str) -> tuple[bool, str]:
        info = next((i for i in self.infos if i["name"] == name), None)
        if not (info and info.get("present")):
            return False, f"No saved sort for {name}."
        self._cleared.add(name)
        self.cleared_sorts.append(name)
        self.reload()
        return True, f"Cleared saved {name} sort"


@pytest.fixture
def make_controller():
    return FakeController


@pytest.fixture
def make_app():
    """Build a SpikeMenuApp over a FakeController. Accepts present/use_docker so the
    three-panel tests can drive the broken-data and Docker-on universes."""
    import menu_app

    def _build(present: bool = True, use_docker: bool = False):
        return menu_app.SpikeMenuApp(FakeController(present=present, use_docker=use_docker))

    return _build
