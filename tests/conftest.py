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

# Action table mirroring SpikeInterface_Menu._ACTIONS (keys + needs_data + section),
# so number-key indices, the WORKFLOW/MANAGE split, and the data-dimming behaviour
# match the real app. D1 order of record: gui ("Inspect") 4th, compare 5th, traces 6th.
ACTIONS = [
    ("explore", "Explore", "figures: LFP + events", True, "workflow"),
    ("sort", "Sort", "full or quick", True, "workflow"),
    ("report", "Report", "build + open HTML", True, "workflow"),
    ("gui", "Inspect", "GUI on the saved sort", True, "workflow"),
    ("compare", "Compare", "two saved sorts", True, "workflow"),
    ("traces", "Traces", "scroll raw signal", True, "workflow"),
    ("params", "Edit parameters", "tune the active sorter", False, "manage"),
    ("manage", "Manage sorters", "download · delete", False, "manage"),
    ("triage", "Triage units", "label the saved sort's units", False, "manage"),
    ("phy", "Export to Phy", "saved sort → a Phy folder", True, "manage"),
    ("probe", "Probe geometry", "pick / edit geometry", False, "manage"),
    ("verify", "Verify install", "smoke test", False, "manage"),
    ("theme", "Colour theme", "accent", False, "manage"),
    ("help", "Help", "steps · sorters · Docker · data files", False, "manage"),
    ("quit", "Quit", "exit", False, "manage"),
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
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd, section=s)
                        for k, t, h, nd, s in ACTIONS]
        self.last_result = None
        self.reopened = 0
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
        self.active_probe = "nnx-a1x16-3mm-100"
        self.want_probe_setup = False
        self._probe_lib = [
            {"name": "nnx-a1x16-3mm-100",
             "label": "NeuroNexus A1x16-3mm-100-703 · 16 ch @ 100 µm", "kind": "linear",
             "params": {"n": 16, "pitch_um": 100.0}, "builtin": True, "auto": False,
             "match": "fits", "match_detail": "matches 16 channels",
             "summary": "16 contacts · linear · 100 µm pitch", "n": 16,
             "density_class": "sparse", "layout": "linear", "note": ""},
            {"name": "independent", "label": "Independent channels (placeholder)",
             "kind": "independent", "params": {"pitch_um": 250.0}, "builtin": True,
             "auto": True, "match": "auto", "match_detail": "auto-sizes to the recording",
             "summary": "auto-sizes · independent channels", "n": None,
             "density_class": "independent", "layout": "independent", "note": ""},
            {"name": "linear-16-50um", "label": "Linear · 16 ch @ 50 µm", "kind": "linear",
             "params": {"n": 16, "pitch_um": 50.0}, "builtin": True, "auto": False,
             "match": "fits", "match_detail": "matches 16 channels",
             "summary": "16 contacts · linear · 50 µm pitch", "n": 16,
             "density_class": "dense", "layout": "linear", "note": ""},
            # A P1-imported probe: geometry materialised at import, so the editor
            # must refuse it (view/duplicate/delete only) — the T3 state test.
            {"name": "lab-imported-16", "label": "lab_probe · 16 ch (imported)",
             "kind": "imported",
             "params": {"positions": [[0.0, 100.0 * i] for i in range(16)],
                        "min_pitch_um": 100.0, "layout": "linear"},
             "builtin": False, "auto": False,
             "match": "fits", "match_detail": "matches 16 channels",
             "summary": "16 contacts · linear · 100 µm pitch", "n": 16,
             "density_class": "sparse", "layout": "linear",
             "note": "Imported from lab_probe.json"},
        ]
        # Paths a test marks as vanished-from-disk, so reopen_last can mirror the
        # real controller's is-it-still-there check.
        self.gone: set[str] = set()
        # Unit triage (W1 slice 4). The verdicts written so far stand in for the
        # curation record on disk: they survive a "relaunch" over the same
        # controller exactly as the real record survives one over the same repo.
        self.labels: dict[str, dict] = {}
        self.labelled: list[tuple] = []
        self.triage_blocked = ""            # tests set the anchor refusal here
        self.triage_stale_reason = ""
        self.triage_line = "raw tridesclous2 sorter output — no curation applied"
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
                "fit": {"rank": "good" if name == "tridesclous2" else "ok",
                        "reason": f"{name} fit."},
                # Array/yield headline (sort_summary shape) for saved sorts, so the
                # D5 RESULTS section renders real metric text in tests.
                "summary": ({"n_units": units, "units_in_uV": True,
                             "v_pp_uV": {"median": 34.2}, "snr": {"median": 5.0},
                             "noise_floor_uV": {"median": 4.07},
                             "yield_pct": 75.0, "n_active_channels": 12,
                             "n_channels": 16, "units_per_channel": 0.81,
                             "units_per_active_channel": 1.08} if present else None),
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
        self.probe_info = self.active_probe_info()

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

    def active_probe_info(self) -> dict:
        return next((p for p in self._probe_lib if p["name"] == self.active_probe),
                    self._probe_lib[0])

    def probe_catalog(self) -> list[dict]:
        return [dict(p, active=(p["name"] == self.active_probe)) for p in self._probe_lib]

    def set_active_probe(self, name: str) -> bool:
        if any(p["name"] == name for p in self._probe_lib):
            self.active_probe = name
            self.probe_info = self.active_probe_info()
            return True
        return False

    def save_probe(self, profile) -> tuple[bool, str]:
        self._probe_lib = [p for p in self._probe_lib if p["name"] != profile["name"]]
        self._probe_lib.append(profile)
        return True, f"Saved probe {profile['name']}."

    def delete_probe(self, name: str) -> tuple[bool, str]:
        self._probe_lib = [p for p in self._probe_lib if p["name"] != name]
        if self.active_probe == name:
            self.active_probe = self._probe_lib[0]["name"] if self._probe_lib else "independent"
        return True, f"Deleted probe {name}."

    def duplicate_probe(self, name, new_name, new_label=None) -> dict:
        src = next((p for p in self._probe_lib if p["name"] == name), None) or {}
        dup = dict(src, name=new_name,
                   label=new_label or f"{src.get('label', name)} copy")
        self._probe_lib.append(dup)
        return dup

    def mark_probe_setup_seen(self) -> None:
        self.want_probe_setup = False

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

    # -- unit triage (mirrors MenuController.triage_state / label_unit) --------- #
    _TRIAGE_COLUMNS = ["firing_rate", "snr", "isi_violations_ratio",
                       "presence_ratio", "amplitude_cutoff"]

    def triage_state(self) -> dict:
        sorter = self.active_sorter
        info = self.infos[self.active_idx]
        st = {"sorter": sorter, "line": self.triage_line,
              "stale": bool(self.triage_stale_reason),
              "stale_reason": self.triage_stale_reason,
              "apply_hint": f"uv run python scripts/curation.py apply --sorter {sorter}",
              "blocked": self.triage_blocked, "empty": "",
              "columns": [], "units": [], "reviewed": 0, "total": 0}
        if not info.get("present"):
            st["empty"] = (f"No saved {sorter} sort to triage yet — press 2 on the "
                           "dashboard to sort, then come back.")
            return st
        # A blocked record's labels are for a DIFFERENT sort's unit ids, so they are
        # not shown against these units (the real controller does the same).
        labels = {} if self.triage_blocked else self.labels.get(sorter, {})
        st["columns"] = list(self._TRIAGE_COLUMNS)
        st["units"] = [{
            "unit": u, "label": labels.get(u),
            "label_method": "tui" if u in labels else None,
            "peak_channel": str(u % 16 + 1), "n_spikes": 1000 + u,
            "v_pp_uV": 30.0 + u,
            # amplitude_cutoff is None: NaN on disk must render as "–", never 0.
            "metrics": {"firing_rate": 0.5 + u, "snr": 5.0 + u * 0.1,
                        "isi_violations_ratio": 0.0, "presence_ratio": 1.0,
                        "amplitude_cutoff": None},
        } for u in range(info["units"])]
        st["total"] = len(st["units"])
        st["reviewed"] = sum(1 for x in st["units"] if x["label"])
        return st

    def label_unit(self, unit_id, label: str) -> tuple[bool, str]:
        if self.triage_blocked:
            return False, self.triage_blocked          # refused: nothing written
        self.labels.setdefault(self.active_sorter, {})[unit_id] = label
        self.labelled.append((self.active_sorter, unit_id, label))
        return True, f"unit {unit_id} → {label}"

    def run_compare(self, pair) -> tuple[bool, str, bool]:
        self.ran_compare = tuple(pair)
        self.record_result("compare", True)
        return True, f"✓ compared {pair}", True

    def run(self, key: str, span: str | None) -> tuple[bool, str, bool]:
        self.ran.append((key, span))
        self.record_result(key, True)
        return True, f"✓ ran {key}", key in ("sort", "compare")

    def record_result(self, key: str, ok: bool) -> None:
        path = {"explore": "outputs/explore.html", "report": "outputs/report.html",
                "compare": "outputs/comparison.html"}.get(key)
        if key == "sort":
            path = f"outputs/{self.active_sorter}/"
        self.last_result = {"key": key, "ok": bool(ok), "when": "12:00", "path": path}

    def reopen_last(self) -> tuple[bool, str]:
        if not self.last_result:
            return False, "Nothing to reopen yet"
        path = self.last_result.get("path") or ""
        if not path.endswith(".html"):
            return False, f"{self.last_result.get('key')} has no page to reopen"
        if path in self.gone:                       # mirrors the real existence check
            return False, f"{path} is gone — rebuild it"
        self.reopened += 1
        return True, f"Reopened {path}"

    def sort_expectations(self) -> dict:
        """Expected-duration facts for the span picker (D4). None = no history yet."""
        return {"span": None, "wall_seconds": None}

    def report_command(self) -> list[str]:
        # Harmless argv for BuildProgressScreen tests (exits 0 at once).
        return ["true"]

    def report_log_path(self):
        return None

    def sort_command(self, span: str | None) -> list[str]:
        # A harmless argv so SortProgressScreen's worker can spawn + exit cleanly in
        # tests (no real run_sorting.py / SpikeInterface). ``true`` exits 0 at once.
        self.sort_span = span
        return ["true"]

    def sort_log_path(self, span: str | None = None):
        # No stderr capture in tests (the fake argv writes nothing); None makes the
        # screen fall back to DEVNULL, exercising that path too.
        return None

    # -- Docker image management (Stage 4: in-UI download / state) ------------- #
    def download_image(self, name, on_progress=None, on_status=None, should_cancel=None):
        # Stepped fake pull: emit a scripted sequence, polling should_cancel between
        # steps and pausing on a threading.Event the test can release. With no gate
        # set (the default) it runs straight through, preserving old test behaviour.
        self.downloaded.append(name)
        gate = getattr(self, "dl_gate", None)        # a threading.Event or None
        steps = [
            ("status", "Downloading 1/2 layers"),
            ("progress", (25, 100)),
            ("gate", None),                            # test may pause the worker here
            ("progress", (50, 100)),
            ("status", "Extracting 1/2 layers"),
            ("progress", (100, 100)),
        ]
        for kind, payload in steps:
            if should_cancel is not None and should_cancel():
                return False, f"Download of {name} cancelled"
            if kind == "status" and on_status is not None:
                on_status(payload)
            elif kind == "progress" and on_progress is not None:
                on_progress(*payload)
            elif kind == "gate" and gate is not None:
                while not gate.wait(timeout=0.02):
                    if should_cancel is not None and should_cancel():
                        return False, f"Download of {name} cancelled"
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
