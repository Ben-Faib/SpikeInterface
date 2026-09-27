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

import sort_summary as _ss  # noqa: E402 - SI-free import; the fake quotes its words

import journey  # noqa: E402 - pure; the one action table the palette lists
import settings as user_settings  # noqa: E402 - pure; the one settings schema

ACTIONS = journey.ACTIONS


class FakeController:
    """Stand-in for MenuController; no I/O, no SpikeInterface."""

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
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd, stage=st)
                        for k, t, h, nd, st in ACTIONS]
        self.cfg: dict = {}                 # the .si_menu.json stand-in (settings)
        self.commands: list = []            # command() keys the app asked for
        self.finished: list = []            # (key, ok) finish_command calls
        self.opened: list = []              # open_output / open_path targets
        self.recipes: list = []
        self.reports: dict = {}             # run id -> [reproduce report rows]
        self.made_current: list = []
        self.last_result = None
        self.reopened = 0
        # How many (non-accepted) fake units carry the merge advisory. 0 keeps
        # the dashboard/triage silent, mirroring a sort where nothing fires.
        self.split_candidates = 0
        self.ran: list[tuple[str, str | None]] = []
        self.ran_compare = None
        self.downloaded: list[str] = []
        self.deleted_images: list[str] = []
        self.cleared_sorts: list[str] = []
        # Which Docker images are cached locally. herdingspikes starts cached;
        # mountainsort5 does not - so the badge tests cover both states. A download/
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
            # must refuse it (view/duplicate/delete only) - the T3 state test.
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
        self.triage_line = "raw tridesclous2 sorter output - no curation applied"
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
                # The takeaway (sort_summary.unit_rollup's shape) as plain data -
                # the RESULTS line says "N strong units", never a raw count.
                "rollup": self._rollup(units) if present else None,
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
                {"ext": ".ns2", "label": "LFP - analog @ 1 kHz", "present": self._present},
                {"ext": ".ns5", "label": "Broadband - raw @ 30 kHz", "present": self._present},
                {"ext": ".nev", "label": "Spike events", "present": self._present},
            ],
            "error": None if self._present else "No Blackrock .nev/.nsX files found in '/data/recordings'.",
        }
        self.probe_info = self.active_probe_info()
        self._refresh_v2()

    # -- the Spike 2.0 journey, hand-built (journey.py is pinned on its own) --- #
    def _refresh_v2(self) -> None:
        info = next(i for i in self.infos if i["name"] == self.active_sorter)
        present = bool(info.get("present"))
        labels = self.labels.get(self.active_sorter, {}) if not self.triage_blocked else {}
        n = info["units"] if present else 0
        split = set(self._split_units(n)) if present else set()
        units = [{"unit": str(u), "contact": str(u % 16 + 1), "n_spikes": 1000 + u,
                  "v_pp_uV": 30.0 + u, "snr": 5.0, "strong": u % 3 == 0,
                  "advised": u in split, "label": labels.get(u)} for u in range(n)]
        run = ({"id": "20260819-035117-c7184d", "smoke": False, "created": "2026-08-19T03:51:51",
                "n_units": n, "effective_seconds": 132.0, "total_seconds": 132.0,
                "wall_seconds": 35.4, "noise_uV": 4.07,
                "channel_ids": [str(c) for c in range(1, 17)], "dir": "outputs/x"}
               if present else None)
        n_lab = sum(1 for u in units if u["label"])
        self.journey = {"sorter": self.active_sorter,
                        "data": {"present": self._present, "complete": self._present,
                                 "missing": [] if self._present else [".ns2", ".ns5", ".nev"],
                                 "unreadable": False, "n_streams": 3 if self._present else 0,
                                 "base": self.data_report.get("base"),
                                 "data_dir": self.data_report.get("data_dir"),
                                 "broadband_detail": "16 neural + 6 aux ch, 132.0s @ 30000 Hz"},
                        "probe": self.probe_info, "run": run, "units": units, "n_units": n,
                        "n_labelled": n_lab, "flagged": [u["unit"] for u in units if u["advised"]],
                        "curation": {"has_curated": False, "stale": False, "counts": {"total": n_lab},
                                     "updated": None},
                        "reproduced": list(self.reports.get(run["id"], [])) if run else []}
        mark = lambda ok: "done" if ok else "todo"  # noqa: E731
        self.stages = [
            {"key": "data", "n": 1, "label": "Data", "mark": "done" if self._present else "warn",
             "caption": "3 streams" if self._present else "no files"},
            {"key": "probe", "n": 2, "label": "Probe", "mark": "done", "caption": "16 contacts"},
            {"key": "sort", "n": 3, "label": "Sort", "mark": mark(present),
             "caption": f"{n} units" if present else "not sorted"},
            {"key": "judge", "n": 4, "label": "Judge", "mark": mark(bool(n) and n_lab >= n),
             "caption": f"{n_lab}/{n}" if n else ""},
            {"key": "apply", "n": 5, "label": "Apply", "mark": "warn" if n_lab else "todo",
             "caption": f"{n_lab} to apply" if n_lab else ""},
            {"key": "share", "n": 6, "label": "Share", "mark": "todo", "caption": ""}]
        steps = []
        if not self._present:
            steps.append({"title": "Add the recording", "detail": "Spike needs one Blackrock set.",
                          "action": "stage:1", "label": "show me where the files go", "stage": 1})
        elif not present:
            steps.append({"title": "Sort the recording", "detail": "Find the units.",
                          "action": "sort", "label": "sort the full recording", "stage": 3})
        if present and n_lab < n:
            steps.append({"title": f"Judge the {n - n_lab} units", "detail": "one key per unit",
                          "action": "stage:4", "label": "start judging", "stage": 4})
        if present:
            steps.append({"title": "Build the report", "detail": "One HTML page.",
                          "action": "report", "label": "build the report", "stage": 6})
        self.steps = steps
        by = {}
        for u in units:
            by.setdefault(u["contact"], []).append(u)
        self.probe_map = {"contacts": [str(c) for c in range(16, 0, -1)] if present else [],
                          "units": by}
        self.recent = ([{"when": "2026-08-19T03:51:51", "text": "full sort · 12 units · current"}]
                       if present else [])
        self.share_rows = [
            {"key": "report", "title": "Report", "path": "outputs/report.html", "exists": False,
             "status": "missing", "note": "not built yet", "actions": ["open", "rebuild"]},
            {"key": "phy", "title": "Phy export", "path": "outputs/x/phy", "exists": False,
             "status": "missing", "note": "not exported", "actions": ["export"]},
            {"key": "reproduce", "title": "Reproduce this run", "path": "", "exists": False,
             "status": "missing", "note": "not checked yet", "actions": ["open"]},
            {"key": "recipe", "title": "Run recipe", "path": "outputs/recipes/x.json",
             "exists": False, "status": "missing", "note": "re-runs this sort anywhere",
             "actions": ["export"]}]

    def refresh_journey(self) -> None:
        self._refresh_v2()

    @property
    def quick_seconds(self) -> int:
        return user_settings.quick_seconds(self.cfg)

    def settings_rows(self) -> list:
        rows = user_settings.rows(self.cfg)
        for r in rows:
            if r["kind"] == "link":
                r["value"] = {"active_probe": self.probe_info["label"],
                              "active_sorter": self.active_sorter,
                              "sorter_params": "all defaults",
                              "use_docker": "on" if self.use_docker else "off",
                              "theme": self.theme_name}.get(r["key"], "")
        return rows

    def set_setting(self, key, raw):
        ok, msg = user_settings.set_value(self.cfg, key, raw)
        if ok:
            self._refresh_v2()
        return ok, msg

    def reset_setting(self, key):
        return user_settings.reset(self.cfg, key)

    def sort_preview(self) -> list:
        g = user_settings.get
        return [("probe", self.probe_info["label"]),
                ("band-pass", f"{g(self.cfg, 'freq_min'):g}-{g(self.cfg, 'freq_max'):g} Hz")]

    def command(self, key, run_id=None) -> dict:
        import tempfile
        from pathlib import Path as _P

        self.commands.append((key, run_id))
        log = _P(tempfile.gettempdir()) / f"spike_fake_{key}.log"
        out = {"argv": ["true"], "title": f"Running {key}", "log": log, "open": None,
               "report": None}
        if key == "reproduce":
            rep = _P(tempfile.gettempdir()) / "spike_fake_reproduce.json"
            import json as _json
            rep.write_text(_json.dumps({"report": {
                "verdict": "REGENERATED", "recorded_run": "a", "regenerated_run": "b",
                "criteria": [{"name": "noise floor", "recorded": 4.07, "regenerated": 4.05,
                              "tolerance": "± 0.3 µV", "verdict": "WITHIN TOLERANCE",
                              "note": ""}], "failed": []}, "out": "outputs/regen/b"}),
                encoding="utf-8")
            out["report"] = rep
        return out

    def finish_command(self, key, ok) -> str:
        self.finished.append((key, ok))
        return ("✓ " if ok else "✗ ") + key

    def unit_evidence(self, unit_id):
        u = int(unit_id)
        wave = [0.0] * 10 + [-20.0 - u, -60.0 - u, -30.0, 10.0, 15.0] + [5.0] * 10
        return {"unit": str(u), "n_spikes": 1000 + u, "peak_channel": str(u % 16 + 1),
                "channels": [str(u % 16 + 1)], "waveforms": {str(u % 16 + 1): wave},
                "wave_ms": 2.9, "peak_index": 11,
                "isi": {"bin_ms": 0.5, "max_ms": 25.0, "counts": [3, 0, 1] + [10] * 47,
                        "refractory_ms": 1.5, "n_refractory": 4, "ratio": 0.2},
                "amplitude": {"t_s": [0, 1, 2], "median_uV": [-60.0, -61.0, -59.0], "n": [5, 5, 5]}}

    def apply_preview(self) -> dict:
        labels = {}
        for lab in self.labels.get(self.active_sorter, {}).values():
            labels[lab] = labels.get(lab, 0) + 1
        total = sum(labels.values())
        return {"sorter": self.active_sorter, "run": "20260819-035117-c7184d",
                "n_units": 12, "labels": labels,
                "counts": {"total": total, "merges": 0, "splits": 0, "labels": total},
                "decisions": [{"at": "2026-08-19T03:53:36", "type": "label", "units": [u],
                               "label": lab, "method": "tui"}
                              for u, lab in self.labels.get(self.active_sorter, {}).items()],
                "has_record": bool(total), "has_curated": False, "stale": False,
                "stale_reason": "", "line": "raw", "noise_uV": 4.07}

    def probe_detail(self, name=None) -> dict:
        p = next((x for x in self._probe_lib if x["name"] == (name or self.active_probe)), None)
        if p is None:
            return {}
        return {"name": p["name"], "label": p["label"], "kind": p["kind"],
                "params": dict(p.get("params") or {}), "builtin": p.get("builtin"),
                "note": p.get("note", ""), "summary": p.get("summary", ""),
                "features": {"n": p.get("n"), "layout": p.get("layout"),
                             "min_pitch_um": 100.0, "density_class": p.get("density_class")},
                "match": p.get("match"), "match_detail": p.get("match_detail"),
                "active": p["name"] == self.active_probe,
                "positions": [[0.0, 100.0 * i] for i in range(p.get("n") or 4)],
                "saved_in": "built into Spike" if p.get("builtin") else "probes.json"}

    def import_probe(self, path):
        if not str(path).strip().endswith((".json", ".prb")):
            return False, f"couldn't import {path}: not a .json or .prb file"
        self._probe_lib.append({**self._probe_lib[0], "name": "imported-x", "label": "imported x",
                                "builtin": False, "kind": "imported"})
        return True, "Imported probe imported-x - press ↵ on it to use it"

    def runs_overview(self) -> list:
        return [{"id": "20260819-035117-c7184d", "created": "2026-08-19T03:51:51",
                 "smoke": False, "legacy": False, "units": 12, "current": True,
                 "seconds": 132.0, "noise_uV": 4.07, "reproduced": None, "dir": "x"},
                {"id": "20260927-162150-5a6312", "created": "2026-09-27T16:22:17",
                 "smoke": True, "legacy": False, "units": 14, "current": False,
                 "seconds": 30.0, "noise_uV": 3.94, "reproduced": None, "dir": "y"}]

    def run_recipe(self, run_id) -> dict:
        return {"config": {"sorter": self.active_sorter},
                "rows": [("Sorter", self.active_sorter), ("Seed", "none")]}

    def reproduce_reports(self, run_id) -> list:
        return list(self.reports.get(run_id, []))

    def export_recipe(self, run_id=None):
        self.recipes.append(run_id)
        return True, "Recipe written → outputs/recipes/x.json"

    def make_current(self, run_id):
        self.made_current.append(run_id)
        return True, f"current → {run_id}"

    def open_output(self, key):
        self.opened.append(key)
        return True, f"Opened {key}"

    def open_path(self, path):
        self.opened.append(str(path))
        return True, f"Opened {path}"

    def open_data_folder(self):
        return self.open_path(self.data_report.get("data_dir"))

    def startup_checklist(self) -> list:
        return [(True, "recording", "PFCM7"), (True, "probe", self.probe_info["label"])]

    # A third of the units pass the rule, on ascending contacts - deterministic,
    # so both the RESULTS line and the strong-first triage order are assertable.
    _RULE_TEXT = ("SNR ≥ 4 · ISI ratio ≤ 0.5 · amp cutoff ≤ 0.1 · presence ≥ 0.9 "
                  "(NaN criteria skipped)")

    def _accepted(self, n_units: int) -> list:
        return [u for u in range(n_units) if u % 3 == 0]

    def _rollup(self, n_units: int) -> dict:
        # Every fake unit has 1000+ spikes, so all its passes are STRONG (none
        # thin) - the thin-evidence split is pinned against real numbers in
        # test_sort_summary.py, not simulated here.
        accepted = self._accepted(n_units)
        contacts = [str(u % 16 + 1) for u in accepted]
        return {"n_units": n_units, "n_accepted": len(accepted),
                "n_strong": len(accepted), "n_thin": 0,
                "n_unjudged": 0, "strong_contacts": contacts, "thin_contacts": [],
                "rule_text": self._RULE_TEXT,
                "headline": f"{len(accepted)} strong units (ch {'·'.join(contacts)})",
                "site_line": f"strong at ch {'·'.join(contacts)}",
                "contact_line": " · ".join(f"contact {c}: 1 accepted" for c in contacts),
                "has_matches": False, "contacts": [], "units": [],
                # The merge advisory's rollup shape (sort_summary owns the words).
                "n_split_candidates": self.split_candidates,
                "split_contacts": [str(u % 16 + 1) for u in
                                   self._split_units(n_units)],
                # The real module's own words (importable SI-free), so a future
                # rewording cannot silently drift the fake and its assertions.
                "split_line": _ss.split_line(
                    self.split_candidates,
                    [str(u % 16 + 1) for u in self._split_units(n_units)]),
                "split_chip": _ss.split_chip(self.split_candidates),
                "split_rule_text": _ss.split_rule_text()}

    def _split_units(self, n_units: int) -> list:
        rest = [u for u in range(n_units) if u not in self._accepted(n_units)]
        return rest[: self.split_candidates]

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
            self._refresh_v2()
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
            st["empty"] = (f"No saved {sorter} sort to triage yet - press 2 on the "
                           "dashboard to sort, then come back.")
            return st
        # A blocked record's labels are for a DIFFERENT sort's unit ids, so they are
        # not shown against these units (the real controller does the same).
        labels = {} if self.triage_blocked else self.labels.get(sorter, {})
        st["columns"] = list(self._TRIAGE_COLUMNS)
        st["rule_text"] = self._RULE_TEXT
        accepted = self._accepted(info["units"])

        def _unit(u):
            ok = u in accepted
            return {
                "unit": u, "label": labels.get(u),
                "label_method": "tui" if u in labels else None,
                "peak_channel": str(u % 16 + 1), "n_spikes": 1000 + u,
                "v_pp_uV": 30.0 + u,
                "verdict": ok, "strong": ok,
                "verdict_word": "strong" if ok else "sub-threshold",
                "why": "" if ok else "ISI ratio ≤ 0.5 - is 1.2",
                "isolation": "clean" if ok else "mostly separate",
                "split_advice": (_ss.SPLIT_PHRASE
                                 if u in self._split_units(info["units"]) else ""),
                # amplitude_cutoff is None: NaN on disk must render as "–", never 0.
                "metrics": {"firing_rate": 0.5 + u, "snr": 5.0 + u * 0.1,
                            "isi_violations_ratio": 0.0, "presence_ratio": 1.0,
                            "amplitude_cutoff": None},
            }

        # Strong-first, exactly as the real controller's rollup orders them.
        rest = [u for u in range(info["units"]) if u not in accepted]
        st["units"] = [_unit(u) for u in accepted] + [_unit(u) for u in rest]
        st["total"] = len(st["units"])
        st["reviewed"] = sum(1 for x in st["units"] if x["label"])
        return st

    def label_unit(self, unit_id, label: str) -> tuple[bool, str]:
        if self.triage_blocked:
            return False, self.triage_blocked          # refused: nothing written
        self.labels.setdefault(self.active_sorter, {})[int(unit_id)] = label
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
            return False, f"{path} is gone - rebuild it"
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
    """Build the Spike 2.0 app (spike_app.SpikeApp) over a FakeController. Accepts
    present/use_docker so tests can drive the no-data and Docker-on universes."""
    import spike_app

    def _build(present: bool = True, use_docker: bool = False):
        return spike_app.SpikeApp(FakeController(present=present, use_docker=use_docker))

    return _build
