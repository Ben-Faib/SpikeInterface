#!/usr/bin/env python
"""PFCM7 SpikeInterface workspace — single front-door menu launcher.

    uv run python SpikeInterface_Menu.py            # interactive status + menu
    uv run python SpikeInterface_Menu.py report     # run one action directly, then exit
    uv run python SpikeInterface_Menu.py --help
    REM Windows: double-click run.bat (or: run.bat report)

Run with no action -> opens a responsive full-screen dashboard (the Textual app
in scripts/menu_app.py; a typed menu is the fallback when Textual is absent or
off-TTY). Run with an action -> dispatches it directly (handy for scripting).
Heavy SpikeInterface imports are lazy, so the menu stays responsive.

The dashboard has a left Sorter sidebar (←/→ to focus it, ↑/↓ to choose; the
active sorter — what report/GUI/compare act on — is marked by the left accent
bar and named in the SORT banner, its one home) and a right ACTIONS list: six
numbered WORKFLOW actions (Enter or 1-6) over a dim MANAGE tier on letter keys.
It stays usable at any window size and guides you when the recording files are
missing. Styling mirrors scripts/run_sorting.py (see scripts/ui.py).

Actions:
    explore   quick static figures (LFP + .nev) via scripts/explore_data.py
    sort      spike-sort the broadband via scripts/run_sorting.py
    report    build + open the interactive HTML report (scripts/report.py)
    gui       open spikeinterface-gui on the active sort
    traces    scroll raw broadband traces in ephyviewer
    compare   agreement matrix between the two sorters (scripts/compare.py)
    verify    environment smoke test (scripts/verify_install.py)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import blackrock_io as bio  # noqa: E402
import report  # noqa: E402
import sort_summary  # noqa: E402  (array/yield headline metrics — pure load/format)
import sorters as sorter_registry  # noqa: E402  (registry: discovery/status/params/run)
import ui  # noqa: E402  (rich styling shared-look with run_sorting.py)
import probes  # noqa: E402  (probe-geometry registry: profiles/features/build/fit)

QUICK_SECONDS = 30
ACTIONS = ["explore", "sort", "report", "gui", "traces", "compare", "verify"]
# Actions that open a blocking Qt window: the menu launches them in a fresh
# child process so the menu survives and Qt gets a clean process each time.
QT_ACTIONS = {"gui", "traces"}


def _effective_params(sorter: str, overrides: dict) -> dict:
    """Keep only the keys in ``overrides`` that differ from the sorter defaults.

    Storing diffs (not full param dicts) keeps .si_menu.json small and robust to
    SpikeInterface default changes across versions.
    """
    try:
        defaults = sorter_registry.default_params(sorter)
    except Exception:  # noqa: BLE001 - if introspection fails, keep overrides as-is
        return dict(overrides)
    return {k: v for k, v in overrides.items() if k not in defaults or defaults[k] != v}


def _write_params_file(overrides: dict) -> "str | None":
    """Write overrides to a temp JSON file for run_sorting --params-file; None if empty."""
    if not overrides:
        return None
    fd, path = tempfile.mkstemp(prefix="si_params_", suffix=".json")
    import os

    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(overrides, fh)
    return path


CONFIG_PATH = bio.REPO_ROOT / ".si_menu.json"  # local, git-ignored user prefs


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/corrupt -> defaults
        return {}


def _save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - best-effort
        pass


def _apply_saved_theme(cfg: dict) -> str:
    """Set the UI accent from saved config; return the active theme name."""
    theme = cfg.get("theme", ui.DEFAULT_THEME)
    if theme not in ui.THEMES:
        theme = ui.DEFAULT_THEME
    ui.set_accent(ui.THEMES[theme])
    return theme


def _analyzer_dir(sorter: str) -> Path:
    return bio.REPO_ROOT / "outputs" / sorter / "analyzer"


# --------------------------------------------------------------------------- #
# Dashboard data (loaded once, refreshed only after a state-changing action)
# --------------------------------------------------------------------------- #
def _sorter_info(sorter: str, analyzer, active: bool, status: str = "local") -> dict:
    """Saved-sort summary for one sorter. Pass a pre-loaded analyzer or None."""
    if analyzer is None and _analyzer_dir(sorter).exists():
        try:
            import spikeinterface.full as si

            analyzer = si.load_sorting_analyzer(_analyzer_dir(sorter))
        except Exception:  # noqa: BLE001 - unreadable analyzer -> treat as absent
            analyzer = None
    if analyzer is None:
        return {"name": sorter, "present": False, "units": 0, "duration": 0.0,
                "active": active, "status": status}
    return {"name": sorter, "present": True, "units": len(analyzer.unit_ids),
            "duration": float(analyzer.get_total_duration()), "active": active,
            "status": status}


def _load_dashboard(data_dir, active: str, sorter_list, docker: bool):
    """Return (pipeline_rows, sorter_infos). Heavy: loads the data + analyzers."""
    objects, status = report._gather(data_dir, _analyzer_dir(active))
    pipeline = [r for r in status if not r["stage"].startswith("Saved sort")]
    inst = set(sorter_registry.installed())
    infos = [
        _sorter_info(
            s, objects.get("analyzer") if s == active else None, s == active,
            sorter_registry.status(s, installed_set=inst, docker=docker),
        )
        for s in sorter_list
    ]
    return pipeline, infos


def _saved_summary(sorter: str):
    """(present, units, duration) for a sorter's saved analyzer; best-effort.

    Short-circuits cheaply when there is no analyzer dir (the common case), so
    probing all ~22 sorters stays fast. Never raises.
    """
    d = _analyzer_dir(sorter)
    if not d.exists():
        return False, 0, 0.0
    try:
        import spikeinterface.full as si

        a = si.load_sorting_analyzer(d)
        return True, len(a.unit_ids), float(a.get_total_duration())
    except Exception:  # noqa: BLE001 - unreadable analyzer -> treat as absent
        return False, 0, 0.0


def _catalog(active: str, use_docker: bool, profile: dict | None = None) -> list[dict]:
    """Full sidebar catalog over EVERY sorter, annotated with geometry fit.

    ``profile`` is the active probe profile; when given, each row gets a ``fit``
    {rank,reason}, the ``recommended`` flag follows the top good-fit runnable
    sorter (falling back to RECOMMENDED), and members are re-ranked within each
    group (good→ok→poor, then name)."""
    import probes
    inst = set(sorter_registry.installed())
    docker = sorter_registry.docker_available()
    runnable = set(sorter_registry.runnable(use_docker))
    # Only probe the local image cache when Docker is at least installed; the
    # daemon-installed check is cached per process, so this stays cheap.
    docker_installed = sorter_registry.docker_state() != "not_installed"
    rec_name = sorter_registry.RECOMMENDED
    if profile is not None:
        rec_name = probes.recommended_for(profile, sorter_registry.runnable(use_docker),
                                          prefer=sorter_registry.RECOMMENDED) or rec_name
    out = []
    for name in sorter_registry.available():
        present, units, duration = _saved_summary(name)
        info = {
            "name": name,
            "group": sorter_registry.group_of(name, installed_set=inst),
            "status": sorter_registry.status(name, installed_set=inst, docker=docker),
            "runnable": name in runnable,
            "recommended": name == rec_name,
            "description": sorter_registry.description(name),
            "present": present, "units": units, "duration": duration,
            "active": name == active,
            # The array/yield headline summary (six metrics) for the INSPECTING panel;
            # a cheap SI-free JSON read, None until a sort writes summary.json.
            "summary": sort_summary.load_summary(_analyzer_dir(name).parent) if present else None,
            "fit": probes.fit(name, profile) if profile is not None else {"rank": "ok", "reason": ""},
        }
        group = info["group"]
        if group == "docker":
            img = sorter_registry.default_docker_image(name)
            present_img = bool(img) and docker_installed and \
                sorter_registry.docker_image_present(img)
            info["image"] = img
            info["img_present"] = present_img
            # Cached image size (bytes) so the Manage dialogs can show "~X GB"
            # without a second probe; only queried for an image we already have.
            info["img_size"] = sorter_registry.image_size(img) if present_img else None
        else:
            info["image"] = None
            info["img_present"] = None
            info["img_size"] = None
        out.append(info)
    # Re-rank within each group: good→ok→poor, then name. The sidebar re-buckets by
    # group preserving this order, so good-fit sorters float to the top of a group.
    rank = {"good": 0, "ok": 1, "poor": 2}
    order = {g: n for n, g in enumerate(["ready", "docker", "gpu", "unavailable"])}
    out.sort(key=lambda i: (order.get(i["group"], 9), rank.get(i["fit"]["rank"], 1), i["name"]))
    return out


def _pipeline_rows(data_dir, active: str) -> list[dict]:
    """The sorter-independent pipeline status rows (LFP/Broadband/.nev)."""
    _objects, status = report._gather(data_dir, _analyzer_dir(active))
    return [r for r in status if not r["stage"].startswith("Saved sort")]


def _data_report(data_dir) -> dict:
    """Which recording files are present/missing and where they belong.

    Powers the v2 dashboard's missing-data banner + the Data Setup screen. Never
    raises: a missing file set simply reports ``present=False`` with guidance.
    """
    d = (Path(data_dir).expanduser().resolve() if data_dir else bio.REPO_ROOT)
    base = None
    err = None
    present = True
    try:
        base = bio.find_blackrock_base(d)
    except FileNotFoundError as e:  # no .nev/.nsX at all
        present = False
        err = str(e)

    def has(ext: str) -> bool:
        # Scoped to the resolved base so the checklist matches the exact files the
        # loader would open — a folder-wide glob could falsely mark a *different*
        # recording's file as part of this set (e.g. recA.nev + recB.ns5). Fall
        # back to a folder-wide glob only when no base resolved.
        if base is not None:
            return base.with_suffix(ext).exists()
        return any(d.glob("*" + ext))

    files = [
        {"ext": ".ns2", "label": "LFP — analog @ 1 kHz", "present": has(".ns2")},
        {"ext": ".ns5", "label": "Broadband — raw @ 30 kHz (sortable)", "present": has(".ns5")},
        {"ext": ".nev", "label": "Spike events + digital markers", "present": has(".nev")},
    ]
    return {"present": present, "complete": present and all(f["present"] for f in files),
            "data_dir": str(d),
            "base": (base.name if base is not None else None), "files": files, "error": err}


HEADER = "University of Pittsburgh · SpikeInterface"


def _read_run_info(sorter: str) -> dict:
    """Load outputs/<sorter>/run_info.json (unit counts etc.); {} if unreadable."""
    try:
        return json.loads((_analyzer_dir(sorter).parent / "run_info.json")
                          .read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return {}


def _last_message(action: str, sorter: str, ok: bool) -> str:
    """One-line 'what just happened' shown at the top of the dashboard next loop.

    A leading '⚠' marks a *succeeded-but-check-this* outcome (e.g. a sort that
    found no units) so the view can colour it amber rather than green.
    """
    if not ok:
        verb = {
            "explore": "Saved exploratory figures → outputs/",
            "sort": f"Sorted {sorter}", "report": f"Built report ({sorter})",
            "gui": "Opened the GUI inspector", "traces": "Opened the trace viewer",
            "compare": "Built sorter comparison", "verify": "Ran the install check",
        }.get(action, action)
        return f"✗ {verb}"
    if action == "sort":
        info = _read_run_info(sorter)
        n, hq = info.get("n_units"), info.get("n_high_quality")
        if n == 0:
            return f"⚠ {sorter}: no units found — lower detect_threshold (Edit parameters) and re-run"
        bits = []
        if isinstance(n, int):
            bits.append(f"{n} units")
        if isinstance(hq, int):
            bits.append(f"{hq} high-quality")
        return f"✓ Sorted {sorter}" + (f" ({', '.join(bits)})" if bits else "")
    verb = {
        "explore": "Saved + opened exploratory figures → outputs/explore.html",
        "report": f"Built report ({sorter}) → outputs/report.html",
        "gui": "Closed the GUI inspector",
        "traces": "Closed the trace viewer",
        "compare": "Built sorter comparison → outputs/comparison.html",
        "verify": "Ran the install check",
    }.get(action, action)
    return f"✓ {verb}"


# --------------------------------------------------------------------------- #
# Shell-out helpers
# --------------------------------------------------------------------------- #
def _shell(script: str, *flags: str) -> bool:
    """Run a sibling script as a child process, inheriting stdout (live output)."""
    cmd = [sys.executable, str(SCRIPTS / script), *flags]
    ui.note(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd).returncode == 0


def _self(action: str, args) -> bool:
    """Re-invoke this launcher in a child process for a single (blocking Qt) action."""
    cmd = [sys.executable, str(ROOT / "SpikeInterface_Menu.py"), action, "--sorter", args.sorter]
    if args.data_dir:
        cmd += ["--data-dir", args.data_dir]
    if getattr(args, "probe", None):
        cmd += ["--probe", args.probe]
    if action == "gui" and getattr(args, "gui_mode", "auto") != "auto":
        cmd += ["--gui-mode", args.gui_mode]
    ui.note(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd).returncode == 0




# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def action_explore(args) -> bool:
    flags = ["--data-dir", args.data_dir] if args.data_dir else []
    if not _shell("explore_data.py", *flags):
        return False
    # Actually SHOW the figures (like action_report): without this the child's
    # output flashes past under the TUI and the PNGs sit unseen in outputs/.
    page = (bio.REPO_ROOT / "outputs" / "explore.html").resolve()
    if page.exists():
        uri = page.as_uri()
        ui.link("Open it:", uri)
        ui.note("Opening it in your browser…")
        _open_in_browser(uri)
    return True


def action_sort(args) -> bool:
    flags = ["--sorter", args.sorter]
    if args.duration is not None:
        flags += ["--duration", str(args.duration)]
    if getattr(args, "docker", False):
        flags += ["--docker"]
    if getattr(args, "params_file", None):
        flags += ["--params-file", args.params_file]
    if args.data_dir:
        flags += ["--data-dir", args.data_dir]
    if getattr(args, "probe", None):
        flags += ["--probe", args.probe]
    return _shell("run_sorting.py", *flags)


def action_verify(args) -> bool:
    flags = ["--data-dir", args.data_dir] if args.data_dir else []
    return _shell("verify_install.py", *flags)


def _open_in_browser(uri: str) -> None:
    if sys.stdin.isatty():
        try:
            if not webbrowser.open(uri):
                ui.note("(could not open a browser automatically — open the link above)")
        except Exception:  # noqa: BLE001
            pass


def action_report(args) -> bool:
    ui.note(f"Building the report for {args.sorter}…")
    _probe = _read_run_info(args.sorter).get("probe") or getattr(args, "probe", None)
    out = report.build_report(data_dir=args.data_dir, analyzer_dir=_analyzer_dir(args.sorter),
                              sorter_label=args.sorter, probe=_probe)
    uri = out.resolve().as_uri()
    ui.done(f"Report written → {out}")
    ui.link("Open it:", uri)
    ui.note("Opening it in your browser…")
    _open_in_browser(uri)
    return True


# Geometry note shown before any spatial view, accurate to how the sort was made
# (read from run_info.json's 'probe'). A real probe (e.g. the NeuroNexus A1x16)
# makes the probe-map / depth / multi-channel views physical; the independent-channel
# placeholder does not — so the user isn't misled either way.
_GEOMETRY_CAVEAT_PLACEHOLDER = (
    "Placeholder electrode geometry (independent-channel dummy probe — the "
    "Blackrock files carry no map). The probe map, unit-location and depth views "
    "are NOT physical; per-unit metrics, waveforms, correlograms and amplitudes "
    "ARE valid."
)


def _geometry_note(active_probe: str) -> str:
    """The geometry caveat, conditional on the active probe.

    For the 'independent' PLACEHOLDER it's the full not-physical warning; for any
    real profile (incl. the default A1x16) it states the geometry in use (spatial
    views are then meaningful)."""
    import probes
    if active_probe in (None, probes.PLACEHOLDER_PROBE):
        return _GEOMETRY_CAVEAT_PLACEHOLDER
    prof = probes.get(active_probe)
    label = prof["label"] if prof else active_probe
    return (f"Probe geometry: {active_probe} — {label}. Spatial views (probe map, "
            "unit locations, depth) reflect this geometry; verify it matches your array.")


def _has_display() -> bool:
    """Best-effort check for a desktop/window server (for the blocking Qt GUIs)."""
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True  # macOS (Quartz) / Windows always present a window server


def _resolve_gui_mode(mode: str) -> str:
    """Map a requested gui mode ('auto'/'desktop'/'web') to a concrete one."""
    if mode == "auto":
        return "desktop" if _has_display() else "web"
    return mode


def _sigui_events(data_dir):
    """Convert bio.read_events() into the ``{name: {'times': ...}}`` dict sigui wants.

    Returns None (so the event view stays cleanly empty) for a marker-less
    recording or any read error — the GUI must open regardless.
    """
    try:
        evs = bio.read_events(data_dir)
    except Exception:  # noqa: BLE001 - events are best-effort
        return None
    out = {}
    for ev in evs or []:
        times = ev.get("times")
        if times is not None and len(times):
            out[str(ev["name"])] = {"times": times}
    return out or None


def _harden_sigui_scatterview() -> None:
    """Make spikeinterface-gui's scatter views survive degenerate units.

    sigui 0.13's ``BaseScatterView.get_unit_data`` computes
    ``np.min(np.diff(np.unique(spike_data)))`` with only a ``len == 1`` special
    case. A unit whose amplitude/depth/PC values are **empty or all-identical**
    (common for online-detected noise units or very short recordings) reduces an
    empty array → ``ValueError: zero-size array to reduction`` and the whole
    window dies on construction — but only once the spike_amplitudes /
    spike_locations / principal_components extensions exist (which we now compute
    at sort time). Wrap the method so such a unit degrades to a flat single-value
    band (or is skipped if it has no spikes at all). Idempotent; a no-op if the
    library's internals have changed. (Upstream: the np.min/np.max reductions
    should guard against size-0 arrays.)
    """
    try:
        import numpy as np
        from spikeinterface_gui import basescatterview as _bsv
    except Exception:  # noqa: BLE001 - GUI not importable; the caller handles that
        return
    cls = _bsv.BaseScatterView
    if getattr(cls, "_si_menu_hardened", False):
        return
    _orig = cls.get_unit_data

    def _safe_get_unit_data(self, unit_id, segment_index=0):
        try:
            result = _orig(self, unit_id, segment_index=segment_index)
        except ValueError:  # np.min over empty array — degenerate (empty / all-equal) spike_data
            inds = self.controller.get_spike_indices(unit_id, segment_index=segment_index)
            spike_indices = self.controller.spikes["sample_index"][inds]
            spike_times = self.controller.sample_index_to_time(spike_indices)
            spike_data = self.spike_data[inds]
            if len(spike_data) == 0:  # nothing to plot -> caller skips on empty spike_times
                empty = np.array([])
                return empty, empty, np.array([1]), np.array([0.0, 1.0]), 0.0, 1.0, inds
            v = float(spike_data[0])
            pad = abs(v) * 0.1 or 1.0
            return (spike_times, spike_data, np.array([1]),
                    np.array([v - pad, v + pad]), v - pad, v + pad, inds)
        # Success path: a unit with a tiny value spread can yield a zero-bin
        # histogram, which then crashes the caller's np.max(hist_count). Coerce
        # an empty histogram to a single flat bin so the view renders instead.
        spike_times, spike_data, hist_count, hist_bins, ymin, ymax, inds = result
        if np.asarray(hist_count).size == 0:
            if ymin == ymax:
                ymin, ymax = ymin - 1.0, ymax + 1.0
            result = (spike_times, spike_data, np.array([1]),
                      np.array([ymin, ymax]), ymin, ymax, inds)
        return result

    cls.get_unit_data = _safe_get_unit_data
    cls._si_menu_hardened = True


def action_gui(args) -> bool:
    analyzer_dir = _analyzer_dir(args.sorter)
    if not analyzer_dir.exists():
        ui.warn(f"No saved sort for {args.sorter} — run 'sort' first.")
        return False
    try:
        import spikeinterface.full as si
        import spikeinterface_gui as sigui
    except Exception as e:  # noqa: BLE001
        ui.warn(f"Could not import the GUI ({e!r}). Try: python scripts/verify_install.py")
        return False
    _harden_sigui_scatterview()  # guard the amplitude/depth/PCA views against degenerate units

    mode = _resolve_gui_mode(getattr(args, "gui_mode", "auto"))
    if mode == "web" and not _can_serve_web():
        ui.warn("No display detected and web mode is unavailable (the 'panel' package "
                "is not installed). Run locally, use X forwarding (ssh -X), or "
                "`uv pip install panel` to enable the browser-based inspector.")
        return False

    analyzer = si.load_sorting_analyzer(analyzer_dir)
    events = _sigui_events(args.data_dir)  # .nev markers -> the GUI's event view
    ui.warn(_geometry_note(_read_run_info(args.sorter).get("probe") or getattr(args, "probe", None) or "independent"))
    try:
        if mode == "web":
            ui.say(f"[{ui.ACCENT}]Opening spikeinterface-gui (web mode)[/] — no display "
                   f"detected; a local browser server will start [{ui.MUTED}](Ctrl-C to return) ...[/]")
            sigui.run_mainwindow(analyzer, mode="web", events=events,
                                 address="localhost", port=0)  # blocks until you stop the server
        else:
            ui.say(f"[{ui.ACCENT}]Opening spikeinterface-gui[/] on {analyzer_dir} "
                   f"[{ui.MUTED}](close the window to return) ...[/]")
            sigui.run_mainwindow(analyzer, mode="desktop", events=events)  # blocks until closed
    except Exception as e:  # noqa: BLE001 - a GUI runtime failure is actionable, not a crash
        ui.warn(f"The GUI inspector couldn't open ({type(e).__name__}: {e}). "
                "On a remote/headless machine try web mode (--gui-mode web) or 'ssh -X'; "
                "otherwise run 'python scripts/verify_install.py' to check the install.")
        return False
    return True


def _can_serve_web() -> bool:
    try:
        import panel  # noqa: F401  (sigui web mode is a Panel/Bokeh server)
        return True
    except Exception:  # noqa: BLE001
        return False


def action_traces(args) -> bool:
    try:
        import spikeinterface.widgets as sw
    except Exception as e:  # noqa: BLE001
        ui.warn(f"Could not import the trace viewer ({e!r}). Try: python scripts/verify_install.py")
        return False
    if not _has_display():  # ephyviewer is desktop-only — fail with guidance, not a raw Qt error
        ui.warn("No display detected — the ephyviewer trace browser needs a desktop/X "
                "session. Use X forwarding (ssh -X) or run locally. (The GUI inspector "
                "has a browser-based web mode; the trace browser does not.)")
        return False
    ui.warn(_geometry_note(getattr(args, "probe", None) or "independent"))
    ui.say(f"[{ui.ACCENT}]Opening ephyviewer[/] on the broadband recording "
           f"[{ui.MUTED}](close the window to return) ...[/]")
    import probes
    rec = bio.read_broadband(args.data_dir, attach_probe=False)
    neural = bio.neural_channel_ids(rec)
    if 0 < len(neural) < rec.get_num_channels():
        rec = bio.select_channels(rec, neural)
    try:
        rec = rec.set_probe(probes.build(
            probes.get(getattr(args, "probe", None) or "independent")
            or probes.get(probes.DEFAULT_PROBE), rec.get_num_channels()))
    except Exception:  # noqa: BLE001 - fall back to the placeholder on mismatch
        rec = bio.attach_dummy_probe(rec)
    try:
        sw.plot_traces({"broadband": rec}, backend="ephyviewer", show_channel_ids=True)  # blocks
    except Exception as e:  # noqa: BLE001 - actionable hint instead of a raw Qt traceback
        ui.warn(f"The trace browser couldn't open ({type(e).__name__}: {e}). "
                "It needs a desktop session — run locally or use 'ssh -X'.")
        return False
    return True


def _compare_pair(args, sorters) -> bool:
    """Build the comparison HTML for a chosen pair, offering a re-sort on mismatch."""
    import compare  # lazy: pulls in spikeinterface

    durations = {}
    for s in sorters:
        a_dir = _analyzer_dir(s)
        if a_dir.exists():
            import spikeinterface.full as si

            durations[s] = float(si.load_sorting_analyzer(a_dir).get_total_duration())
    mismatch = (len(durations) == 2
                and abs(durations[sorters[0]] - durations[sorters[1]]) > compare.DURATION_TOLERANCE_S)
    if mismatch:
        ui.warn("The two sorts cover different windows: "
                + ", ".join(f"{s}={d:.1f}s" for s, d in durations.items()) + ".")
        choice = ui.select(
            f"Re-sort both over the first {QUICK_SECONDS}s so the comparison is meaningful?",
            [("no", "No — just show the window-mismatch caveat", ""),
             ("yes", f"Yes — re-sort both ({QUICK_SECONDS}s) then compare", "")],
            default=0)
        if choice == "yes":
            for s in sorters:
                _shell("run_sorting.py", "--sorter", s, "--duration", str(QUICK_SECONDS),
                       *(["--data-dir", args.data_dir] if args.data_dir else []))

    ui.note(f"Building the comparison ({sorters[0]} vs {sorters[1]})…")
    out = compare.build_comparison(data_dir=args.data_dir, sorters=sorters)
    uri = out.resolve().as_uri()
    ui.done(f"Comparison written → {out}")
    ui.link("Open it:", uri)
    ui.note("Opening it in your browser…")
    _open_in_browser(uri)
    return True


def action_compare(args) -> bool:
    """CLI compare: pick the active sorter + the first other saved sort (or defaults)."""
    import compare  # lazy

    found = compare.saved_sorters()
    if args.sorter in found:
        other = [s for s in found if s != args.sorter]
        pair = (args.sorter, other[0]) if other else tuple(found[:2])
    else:
        pair = tuple(found[:2]) if len(found) >= 2 else compare.DEFAULT_SORTERS
    return _compare_pair(args, pair)


DISPATCH = {
    "explore": action_explore, "sort": action_sort, "report": action_report,
    "gui": action_gui, "traces": action_traces, "compare": action_compare,
    "verify": action_verify,
}

# (key, action, title, hint)
_MENU = [
    ("1", "explore", "Explore raw data",        "static figures (LFP + .nev), no sort needed"),
    ("2", "sort",    "Run / re-run sorting",    "sorts the active sorter; pick full or quick"),
    ("3", "report",  "Build & open report",     "interactive HTML → browser"),
    ("4", "gui",     "Open GUI inspector",      "spikeinterface-gui on the active sort"),
    ("5", "traces",  "Scroll raw traces",       "ephyviewer trace browser"),
    ("6", "compare", "Compare sorters",         "pick two saved sorts → comparison.html"),
    ("7", "params",  "Edit sorter parameters",  "tune the active sorter (saved)"),
    ("8", "manage",  "Manage sorters",          "download images · delete · clear saved sorts"),
    ("9",  "probe",  "Set probe geometry",      "pick / edit the electrode geometry"),
    ("10", "docker", "Toggle Docker sorters",   "show/hide not-installed CPU sorters"),
    ("11", "verify", "Verify install",          "environment smoke test"),
    ("12", "theme",  "Change colour theme",     "pick an accent colour (saved for next time)"),
    ("13", "help",   "Help",                    "what each step does · sorters · Docker · data"),
]

# v2 (Textual) action table — (key, title, hint, needs_data, section). The first six
# rows are THE WORKFLOW (numbered 1-6 in the dashboard, DESIGN_UX §2 order: the GUI
# inspector is "Inspect", Compare precedes Traces); the rest are MANAGE — housekeeping
# rendered dim below a gap, reached by letter keys. ``needs_data`` dims the action and
# blocks it when no recording is present; MANAGE rows always work. ``help`` and
# ``quit`` are handled in-app, not by DISPATCH.
_ACTIONS = [
    ("explore", "Explore",          "figures: LFP + events, no sort needed",   True,  "workflow"),
    ("sort",    "Sort",             "run the active sorter — full or quick",   True,  "workflow"),
    ("report",  "Report",           "build + open the HTML report",            True,  "workflow"),
    ("gui",     "Inspect",          "GUI on the saved sort (desktop window)",  True,  "workflow"),
    ("compare", "Compare",          "two saved sorts → comparison.html",       True,  "workflow"),
    ("traces",  "Traces",           "scroll raw signal (desktop window)",      True,  "workflow"),
    ("params",  "Edit parameters",  "tune the active sorter (saved)",          False, "manage"),
    ("manage",  "Manage sorters",   "download images · delete · clear sorts",  False, "manage"),
    ("probe",   "Probe geometry",   "pick / edit the electrode geometry",      False, "manage"),
    ("verify",  "Verify install",   "environment smoke test",                  False, "manage"),
    ("theme",   "Colour theme",     "pick an accent colour (saved)",           False, "manage"),
    ("help",    "Help",             "steps · sorters · Docker · data files",   False, "manage"),
    ("quit",    "Quit",             "exit the menu (or press q)",              False, "manage"),
]
# Keys that need a recording present (so the fallback menu can refuse them cleanly).
_DATA_ACTIONS = {k for k, _t, _h, needs, _s in _ACTIONS if needs}

# Artifact each action leaves behind, for the dashboard's LAST RESULT line and its
# ``r`` reopen key. Only browser-openable artifacts get a reopen path.
_RESULT_PATHS = {
    "explore": "outputs/explore.html",
    "report": "outputs/report.html",
    "compare": "outputs/comparison.html",
}

# Rich per-action explanation for the dashboard's explanation pane. ``needs`` keys
# are requirement names resolved against live state in
# ``MenuController.action_explain`` (see the resolver table there); needs-nothing
# actions omit the Needs/Output footer entirely.
_ACTION_DETAIL = {
    "explore": {"what": "Make quick static figures (LFP traces, spike raster, "
                        "firing rates) from your raw data. No sorting required.",
                "needs": ["data"],
                "output": "outputs/explore.html (opens in your browser) + .png figures"},
    "sort":    {"what": "Detect neurons in the broadband (.ns5) signal with the "
                        "active sorter.",
                "choose": "full recording, or a quick 30 s test",
                "needs": ["broadband", "sort_docker"], "output": "outputs/<sorter>/"},
    "report":  {"what": "Build a single interactive HTML report of the sorted "
                        "results (run Sort first for unit results).",
                "needs": ["data"], "output": "outputs/report.html"},
    "gui":     {"what": "Open spikeinterface-gui to inspect the active sorter's "
                        "saved units.",
                "needs": ["saved_sort"], "output": "a desktop window"},
    "traces":  {"what": "Scroll the raw broadband traces in ephyviewer "
                        "(needs a desktop display).",
                "needs": ["broadband"], "output": "a desktop window"},
    "compare": {"what": "Build an agreement matrix between two saved sorts.",
                "needs": ["two_sorts"], "output": "outputs/comparison.html"},
    "params":  {"what": "Tune the active sorter's parameters (saved per sorter)."},
    "manage":  {"what": "Download Docker sorter images, delete downloaded images, "
                        "and clear saved sort outputs — all in one place."},
    "probe":   {"what": "Choose, edit, add, or remove the electrode-geometry profile. "
                        "Geometry decides which sorters fit and powers the spatial views."},
    "verify":  {"what": "Run an environment smoke test (library versions, loaders)."},
    "theme":   {"what": "Pick an accent colour for the menu (saved for next time)."},
    "help":    {"what": "What each step does, sorters, Docker, and data files."},
    "quit":    {"what": "Leave the menu."},
}


def _fallback_action_hint(key: str, fallback: str, active_info: dict | None = None) -> str:
    """Per-action hint for the typed fallback menu.

    Surfaces the same plain-language ``what`` the Textual explanation pane shows
    (falling back to the legacy ``_MENU`` hint), and — for ``sort`` when the active
    sorter already has a saved sort — appends the destructive re-run caveat so the
    typed menu still warns before overwriting. This is intentionally NON-parity with
    the Textual app (no accordion / explanation pane): a richer one-line hint only.
    """
    hint = _ACTION_DETAIL.get(key, {}).get("what") or fallback
    if key == "sort" and active_info and active_info.get("present"):
        hint += (f"  ⚠ replaces the saved {active_info['name']} sort "
                 f"({active_info['units']}u).")
    return hint


class MenuController:
    """Bridge between the Textual dashboard (view) and this launcher's logic.

    Holds the live dashboard state (pipeline rows, per-sorter infos, data report)
    and runs actions through the same ``DISPATCH`` / ``_self`` paths as the direct
    CLI, so behaviour matches ``python SpikeInterface_Menu.py <action>`` exactly.
    """

    quick_seconds = QUICK_SECONDS

    def __init__(self, args, cfg: dict):
        self.args = args
        self.cfg = cfg
        self.header = HEADER
        self.themes = dict(ui.THEMES)
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd, section=s)
                        for k, t, h, nd, s in _ACTIONS]
        self.theme_name = cfg.get("theme", ui.DEFAULT_THEME)
        if self.theme_name not in ui.THEMES:
            self.theme_name = ui.DEFAULT_THEME
        self.accent = ui.THEMES[self.theme_name]
        self.use_docker = bool(cfg.get("use_docker", False))
        self.sorter_params = dict(cfg.get("sorter_params", {}))
        self.sorters = sorter_registry.runnable(self.use_docker) or [sorter_registry.default_sorter()]
        # Explicit --sorter wins; otherwise the last session's persisted choice
        # (DESIGN_UX §2 — the active sorter survives relaunch); then the default.
        want = (args.sorter or cfg.get("active_sorter")
                or sorter_registry.default_sorter())
        self.active_sorter = want if want in self.sorters else self.sorters[0]
        self.args.sorter = self.active_sorter
        self.last_result = cfg.get("last_result") if isinstance(
            cfg.get("last_result"), dict) else None
        self.want_welcome = not bool(cfg.get("seen_welcome", False))
        self.active_probe = cfg.get("active_probe", probes.DEFAULT_PROBE)
        if probes.get(self.active_probe) is None:
            self.active_probe = probes.DEFAULT_PROBE
        self.want_probe_setup = not bool(cfg.get("seen_probe_setup", False))
        self.active_idx = 0
        self.reload()

    def set_active_by_name(self, name: str) -> bool:
        """Activate a runnable sorter by id. False (no change) if not runnable.
        Persisted, so the choice survives relaunch (DESIGN_UX §2)."""
        if name not in self.sorters:
            return False
        self.active_sorter = name
        self.args.sorter = name
        self._mark_active()
        self.cfg["active_sorter"] = name
        _save_config(self.cfg)
        return True

    def record_result(self, key: str, ok: bool) -> None:
        """Remember the newest action outcome for the dashboard's LAST RESULT line
        (persisted — results must not evaporate on the next keystroke, DESIGN_UX §1)."""
        import datetime

        path = _RESULT_PATHS.get(key)
        if key == "sort":
            path = f"outputs/{self.active_sorter}/"
        # ISO, not clock-time: the record persists across launches, and "14:18"
        # from last Tuesday must not read as today (D1 review #7). The view
        # formats it relative to the current date.
        self.last_result = {"key": key, "ok": bool(ok),
                            "when": datetime.datetime.now().isoformat(timespec="minutes"),
                            "path": path}
        self.cfg["last_result"] = self.last_result
        _save_config(self.cfg)

    def reopen_last(self) -> tuple[bool, str]:
        """``r``: reopen the last result's artifact in the browser, when it has one."""
        lr = self.last_result
        if not lr:
            return False, "Nothing to reopen yet"
        path = lr.get("path") or ""
        if not path.endswith(".html"):
            return False, f"{lr.get('key', 'last action')} has no page to reopen"
        target = bio.REPO_ROOT / path
        if not target.exists():
            return False, f"{path} is gone — rebuild it"
        _open_in_browser(target.resolve().as_uri())
        return True, f"Reopened {path}"

    def cycle_active(self) -> None:
        """`t` key: advance to the next *runnable* sorter (skips non-runnable rows)."""
        if self.active_sorter in self.sorters:
            i = (self.sorters.index(self.active_sorter) + 1) % len(self.sorters)
        else:
            i = 0
        self.set_active_by_name(self.sorters[i])

    def _mark_active(self) -> None:
        for n, info in enumerate(self.infos):
            info["active"] = (info["name"] == self.active_sorter)
            if info["active"]:
                self.active_idx = n   # index into the full catalog (footer reads this)

    def set_theme(self, name: str) -> str:
        ui.set_accent(ui.THEMES[name])
        self.theme_name = name
        self.accent = ui.THEMES[name]
        self.cfg["theme"] = name
        _save_config(self.cfg)
        return self.accent

    def reload(self) -> None:
        self.pipeline = _pipeline_rows(self.args.data_dir, self.active_sorter)
        # Snapshot the installed set so per-keystroke action_explain() reuses it via
        # uses_docker(..., installed_set=) instead of re-probing SpikeInterface each
        # key. installed() is process-cached, so this is ~0 ms after the first call.
        self._installed = sorter_registry.installed()
        self.infos = _catalog(self.active_sorter, self.use_docker,
                              probes.get(self.active_probe))
        # Surface the count of saved per-sorter param overrides so the dashboard's
        # Selected-sorter card can show "· N custom params" (invisible until now once
        # the save toast faded).
        for info in self.infos:
            info["overrides"] = len(self.sorter_params.get(info["name"], {}))
        self._mark_active()
        self.data_report = _data_report(self.args.data_dir)
        self.probe_info = self.active_probe_info()

    def set_data_dir(self, path: "str | None") -> bool:
        """Point the dashboard at a different recording folder and reload.

        Lets a wrong-folder launch be corrected in-app (``--data-dir`` is otherwise
        launch-only). Returns whether a recording set was found there.
        """
        self.args.data_dir = path
        self.reload()
        return bool(self.data_report.get("present"))

    def toggle_docker(self) -> bool:
        """Flip Docker mode, persist it, and rebuild the runnable sorter list."""
        self.use_docker = not self.use_docker
        self.cfg["use_docker"] = self.use_docker
        _save_config(self.cfg)
        if self.use_docker:
            # Re-probe the daemon so a Docker started (by us or externally) after
            # launch is picked up at once — otherwise runnable() reads the stale
            # "down" cache and shows zero container sorters despite Docker being up.
            sorter_registry.docker_state(refresh=True)
        prev = self.active_sorter
        self.sorters = sorter_registry.runnable(self.use_docker) or [sorter_registry.default_sorter()]
        self.active_sorter = prev if prev in self.sorters else self.sorters[0]
        self.args.sorter = self.active_sorter
        self.reload()
        return self.use_docker

    def default_params(self, sorter: str) -> dict:
        return sorter_registry.default_params(sorter)

    def param_descriptions(self, sorter: str) -> dict:
        try:
            return sorter_registry.param_descriptions(sorter)
        except Exception:  # noqa: BLE001 - descriptions are optional
            return {}

    def get_overrides(self, sorter: str) -> dict:
        return dict(self.sorter_params.get(sorter, {}))

    def set_params(self, sorter: str, overrides: dict) -> None:
        """Persist per-sorter overrides (stored as diffs from defaults)."""
        diffs = _effective_params(sorter, overrides)
        if diffs:
            self.sorter_params[sorter] = diffs
        else:
            self.sorter_params.pop(sorter, None)
        self.cfg["sorter_params"] = self.sorter_params
        _save_config(self.cfg)

    def docker_status(self, refresh: bool = False) -> dict:
        """{state, running, text} for the Docker confirm dialog (plain language)."""
        state = sorter_registry.docker_state(refresh=refresh)
        text = {
            "running": "✓ Docker is running",
            "installed_not_running": "✗ Docker is installed but not started",
            "not_installed": "You don't have Docker yet",
        }[state]
        return {"state": state, "running": state == "running", "text": text}

    def active_blocked_on_docker(self) -> bool:
        """True if the active sorter would need a container but the daemon isn't
        running (e.g. Docker was stopped after the sorter was selected). Re-probes
        the daemon so a mid-session stop is caught."""
        if not sorter_registry.uses_docker(self.active_sorter, self.use_docker):
            return False
        return not sorter_registry.docker_available(refresh=True)

    def start_docker(self) -> bool:
        """Best-effort: launch Docker Desktop. The dialog polls docker_status()."""
        return sorter_registry.start_docker()

    def mark_welcome_seen(self) -> None:
        self.want_welcome = False
        self.cfg["seen_welcome"] = True
        _save_config(self.cfg)

    # -- probe geometry -------------------------------------------------------- #
    def recording_channels(self) -> "int | None":
        """Best-effort neural (sortable) channel count, parsed from the pipeline detail.

        Returns the NEURAL channel count when the broadband detail distinguishes
        neural from aux (e.g. '16 neural + 6 aux ch, ...'), otherwise falls back
        to the total channel count.  Advisory only — the real count is validated by
        probes.build at sort time."""
        import re
        bb = next((r for r in self.pipeline if "Broadband" in r.get("stage", "")), None)
        if not bb or bb.get("status") == "FAIL":
            return None
        detail = bb.get("detail", "")
        m = re.search(r"(\d+)\s*neural", detail) or re.search(r"(\d+)\s*(?:ch|channel)", detail)
        return int(m.group(1)) if m else None

    def _probe_match(self, profile) -> tuple[str, str]:
        """('auto'|'fits'|'mismatch'|'unknown', human detail) vs the recording."""
        if probes.auto_sizes(profile):
            return "auto", "auto-sizes to the recording"
        want = probes.contact_count(profile)
        have = self.recording_channels()
        if want is None or have is None:
            return "unknown", "contact count checked at sort time"
        if want == have:
            return "fits", f"matches {have} channels"
        return "mismatch", f"{want} contacts ≠ {have} recording channels"

    def set_active_probe(self, name: str) -> bool:
        if probes.get(name) is None:
            return False
        self.active_probe = name
        self.cfg["active_probe"] = name
        _save_config(self.cfg)
        self.reload()
        return True

    def active_probe_info(self) -> dict:
        prof = probes.get(self.active_probe) or probes.get(probes.DEFAULT_PROBE)
        feats = probes.geometry_features(prof)
        match, detail = self._probe_match(prof)
        return {"name": prof["name"], "label": prof["label"],
                "summary": probes.summary(prof), "layout": feats["layout"],
                "density_class": feats["density_class"], "match": match,
                "match_detail": detail}

    def probe_catalog(self) -> list[dict]:
        rows = []
        for prof in probes.library():
            feats = probes.geometry_features(prof)
            match, detail = self._probe_match(prof)
            rows.append({
                "name": prof["name"], "label": prof["label"], "kind": prof["kind"],
                "params": dict(prof.get("params", {})),
                "builtin": prof.get("builtin", False),
                "active": prof["name"] == self.active_probe,
                "summary": probes.summary(prof), "n": feats["n"],
                "density_class": feats["density_class"], "layout": feats["layout"],
                "auto": probes.auto_sizes(prof), "match": match, "match_detail": detail,
                "note": prof.get("note", "")})
        return rows

    def save_probe(self, profile) -> tuple[bool, str]:
        try:
            probes.save_profile(profile)
            self.reload()
            return True, f"Saved probe {profile['name']}."
        except Exception as e:  # noqa: BLE001
            return False, f"Couldn't save probe: {e}"

    def delete_probe(self, name: str) -> tuple[bool, str]:
        ok, msg = probes.delete_profile(name)
        if ok and self.active_probe == name:
            self.active_probe = probes.DEFAULT_PROBE
            self.cfg["active_probe"] = self.active_probe
            _save_config(self.cfg)
        self.reload()
        return ok, msg

    def duplicate_probe(self, name, new_name, new_label=None) -> dict:
        dup = probes.duplicate(name, new_name, new_label)
        self.reload()
        return dup

    def mark_probe_setup_seen(self) -> None:
        self.want_probe_setup = False
        self.cfg["seen_probe_setup"] = True
        _save_config(self.cfg)

    def sorter_fit(self, name: str) -> dict:
        return probes.fit(name, probes.get(self.active_probe) or probes.get(probes.DEFAULT_PROBE))

    def catalog_manufacturers(self) -> list[str]:
        return probes.catalog_manufacturers()

    def catalog_models(self, manufacturer: str) -> list[str]:
        return probes.catalog_models(manufacturer)

    def saved_sorters(self) -> list[str]:
        """Sorters that currently have a saved analyzer (for the compare picker)."""
        return [i["name"] for i in self.infos if i.get("present")]

    def action_explain(self, key: str) -> dict:
        """Resolve an action's static metadata against live state.

        Returns ``{what, choose?, caveat?, needs:[{label, ok}], output?}`` for the
        dashboard's explanation pane. ``needs`` requirement keys are evaluated
        against the current data report / saved sorts / Docker state; needs-nothing
        actions get an empty ``needs`` list and no ``output``.
        """
        meta = _ACTION_DETAIL.get(key, {"what": key})
        info = self.infos[self.active_idx]
        present = bool(self.data_report.get("present"))
        bb = next((r for r in self.pipeline if "Broadband" in r.get("stage", "")), None)
        broadband_ok = present and (bb is None or bb.get("status") != "FAIL")
        n_saved = len(self.saved_sorters())
        # Resolvers are LAZY (each value is a thunk) so a need's live check runs only
        # when an action actually lists it. This matters for 'sort_docker': its check
        # reaches the ~1 s installed()/Docker probe via active_blocked_on_docker(), and
        # only the 'sort' action ever needs it — eager evaluation here paid that cost on
        # *every* action highlight (per-keystroke latency). See perf measurement.
        resolvers = {
            "data":       lambda: ("recording files", present),
            "broadband":  lambda: ("broadband .ns5", broadband_ok),
            "saved_sort": lambda: (f"a saved {self.active_sorter} sort", bool(info.get("present"))),
            "two_sorts":  lambda: ("two saved sorts", n_saved >= 2),
            "sort_docker": lambda: ("Docker running", not self.active_blocked_on_docker()),
        }
        needs = []
        for nkey in meta.get("needs", []):
            # The docker-running requirement is only meaningful for a Docker sorter;
            # an installed/native active sorter never uses a container, so skip it.
            if nkey == "sort_docker" and not sorter_registry.uses_docker(
                    self.active_sorter, self.use_docker,
                    installed_set=self._installed):
                continue
            label, ok = resolvers[nkey]()
            needs.append({"label": label, "ok": ok})
        out = {"what": meta["what"], "needs": needs}
        if meta.get("choose"):
            out["choose"] = meta["choose"]
        if meta.get("output"):
            out["output"] = meta["output"]
        if key == "sort" and info.get("present"):
            out["caveat"] = (f"Re-running replaces the saved {info['name']} sort "
                             f"({info['units']}u).")
        if key == "gui" and not info.get("present"):
            out["caveat"] = "No saved sort yet — run Sort first."
        return out

    def image_state(self, name: str) -> dict:
        """{image, present, size} for a sorter's Docker image (best-effort)."""
        img = sorter_registry.default_docker_image(name)
        if not img:
            return {"image": None, "present": False, "size": None}
        present = sorter_registry.docker_image_present(img)
        size = sorter_registry.image_size(img) if present else None
        return {"image": img, "present": present, "size": size}

    def download_image(self, name: str, on_progress=None, on_status=None,
                       should_cancel=None) -> tuple[bool, str]:
        """Pull a sorter's Docker image, streaming progress to the callbacks.

        ``should_cancel`` (optional callable) lets the in-UI download abort the
        pull mid-stream once the worker is detached from the modal screen."""
        img = sorter_registry.default_docker_image(name)
        if not img:
            return False, f"No Docker image is known for {name}."
        summary = {"pulled": None, "cached": None}

        def _on_summary(pulled, cached):
            summary["pulled"], summary["cached"] = pulled, cached

        ok = sorter_registry.pull_docker_image(img, on_progress, on_status,
                                               should_cancel=should_cancel,
                                               on_summary=_on_summary)
        if not ok:
            return False, f"Couldn't download {img}."
        # Be honest about cache reuse so an instant pull doesn't read as broken:
        # SpikeInterface sorter images share base layers, so re-downloading after a
        # delete often reuses most/all of them (Docker dedupes by content hash).
        pulled, cached = summary["pulled"], summary["cached"]
        if pulled == 0 and cached == 0:
            # No layers transferred and none even listed — Docker satisfied the pull
            # entirely from its on-disk layer cache (it keeps blobs after `rmi`), so
            # the image is restored instantly with no download. This is why a
            # just-deleted image can "re-download" in a blink.
            return True, (f"{img} ready instantly — Docker restored it from its "
                          f"layer cache (no download needed)")
        if pulled == 0 and cached:
            plural = "s" if cached != 1 else ""
            return True, (f"{img} ready — reused {cached} cached layer{plural} "
                          f"(shared with your other sorters; nothing to re-download)")
        if cached:
            return True, (f"Downloaded {img} — {pulled} layer"
                          f"{'s' if pulled != 1 else ''} fetched, {cached} reused from cache")
        return True, f"Downloaded {img}"

    def delete_image(self, name: str) -> tuple[bool, str]:
        img = sorter_registry.default_docker_image(name)
        if not img:
            return False, f"No Docker image is known for {name}."
        return sorter_registry.delete_docker_image(img)

    def clear_saved_sort(self, name: str) -> tuple[bool, str]:
        """Delete outputs/<name>/ (the saved sorting + analyzer). Robust to locks."""
        import shutil

        folder = bio.REPO_ROOT / "outputs" / name
        if not folder.exists():
            return False, f"No saved sort for {name}."
        try:
            shutil.rmtree(folder)
            return True, f"Cleared saved {name} sort"
        except Exception as e:  # noqa: BLE001
            return False, f"Couldn't clear {name}: {e}"

    def sort_command(self, span: str | None) -> list:
        """argv for run_sorting.py in JSON-progress mode, for the in-UI sort modal."""
        argv = [sys.executable, str(bio.REPO_ROOT / "scripts" / "run_sorting.py"),
                "--sorter", self.active_sorter, "--progress", "json"]
        if span == "quick":
            argv += ["--duration", str(QUICK_SECONDS)]
        if self.use_docker:
            argv += ["--docker"]
        if getattr(self.args, "data_dir", None):
            argv += ["--data-dir", str(self.args.data_dir)]
        argv += ["--probe", self.active_probe]
        overrides = self.get_overrides(self.active_sorter)
        for k, v in overrides.items():
            argv += ["--param", f"{k}={v}"]
        return argv

    def sort_log_path(self, span: str | None = None) -> Path:
        """Where the in-UI sort's subprocess stderr (human/rich output + any Python
        traceback) is captured. The sort screen redirects the child's stderr here so a
        hard crash that bypasses the JSON error event is still diagnosable (its tail is
        shown in the modal) instead of a blank 'sort exited (1) without finishing'."""
        return _analyzer_dir(self.active_sorter).parent / "sort.log"

    def run_compare(self, pair) -> tuple[bool, str, bool]:
        """Compare a user-chosen pair of saved sorts (mismatch caveat handled in action)."""
        self.args.sorter = pair[0]
        try:
            ok = _compare_pair(self.args, tuple(pair))
        except Exception as e:  # noqa: BLE001
            ui.warn(f"compare failed: {e!r}")
            ok = False
        self.record_result("compare", ok)
        return ok, _last_message("compare", self.args.sorter, ok), True

    def run(self, key: str, span: str | None) -> tuple[bool, str, bool]:
        self.args.sorter = self.active_sorter
        self.args.probe = self.active_probe
        params_path = None
        if key == "sort":
            self.args.duration = QUICK_SECONDS if span == "quick" else None
            self.args.docker = self.use_docker
            params_path = _write_params_file(self.get_overrides(self.active_sorter))
            self.args.params_file = params_path
        try:
            ok = _self(key, self.args) if key in QT_ACTIONS else DISPATCH[key](self.args)
        except Exception as e:  # noqa: BLE001 - surface, keep the app alive
            ui.warn(f"{key} failed: {e!r}")
            ok = False
        finally:
            if params_path:
                from pathlib import Path as _P

                _P(params_path).unlink(missing_ok=True)
                self.args.params_file = None
        self.record_result(key, ok)
        return ok, _last_message(key, self.args.sorter, ok), key in ("sort", "compare")


def _print_setup_plain(report: dict, pipeline=None) -> None:
    """Plain-text missing-data guidance for the typed fallback menu.

    Handles both 'nothing found' and 'incomplete set' (e.g. the sortable .ns5 is
    absent) so the no-Textual / off-TTY path warns just like the Textual app. When
    ``pipeline`` rows are supplied, each present file also shows its per-stream
    channels/rate/duration (via ``ui.stream_detail``), matching the ``d`` Data-files
    help so the typed fallback reads the same load detail as the Textual app.
    """
    if not report["present"]:
        ui.warn(f"No recording found in {report['data_dir']}")
    else:
        missing = ", ".join(f["ext"] for f in report["files"] if not f["present"])
        ui.warn(f"Incomplete recording set in {report['data_dir']} (missing {missing})")
    detail = ui.stream_detail(report["files"], pipeline)
    ui.note("Expected one file set sharing a base name:")
    for f in report["files"]:
        mark = "[bold green]✓[/]" if f["present"] else "[bold red]✗[/]"
        name = (report["base"] or "<RECORDING_NAME>") + f["ext"]
        det = detail.get(f["ext"])
        tail = f"   [dim]· {det}[/]" if det else ""
        ui.say(f"  {mark} {name:32} [dim]{f['label']}[/]{tail}")
    ui.note(f"Drop the set into {report['data_dir']} (or pass --data-dir).")
    ui.note("The raw .ns5/.ns2/.nev are git-ignored, so a fresh clone has none.")


def _edit_params_typed(sorter: str, cfg: dict) -> None:
    """Typed per-sorter parameter editor: pick a param, enter a value, repeat."""
    try:
        defaults = sorter_registry.default_params(sorter)
    except Exception as e:  # noqa: BLE001
        ui.warn(f"can't read {sorter} parameters: {e!r}")
        return
    overrides = dict(cfg.get("sorter_params", {}).get(sorter, {}))
    descs = sorter_registry.param_descriptions(sorter) if hasattr(sorter_registry, "param_descriptions") else {}
    while True:
        opts = [(k, k, f"{overrides.get(k, defaults[k])}") for k in defaults]
        opts.append(("__done__", "Done — save & return", ""))
        key = ui.select(f"Edit which parameter of {sorter}?", opts, default=len(opts) - 1)
        if key in (None, "__done__"):
            break
        ui.note(descs.get(key, ""))
        raw = ui.prompt(f"{key} [{overrides.get(key, defaults[key])}] = ").strip()
        if raw == "":
            continue
        try:
            val = sorter_registry.coerce_param(defaults[key], raw)
        except ValueError as e:
            ui.warn(str(e))
            continue
        if val == defaults[key]:
            overrides.pop(key, None)
        else:
            overrides[key] = val
    sp = dict(cfg.get("sorter_params", {}))
    if overrides:
        sp[sorter] = overrides
    else:
        sp.pop(sorter, None)
    cfg["sorter_params"] = sp
    _save_config(cfg)


def _pick_compare_pair(data_dir):
    """Pick two saved sorts to compare (typed/arrow select); None if <2 or cancelled."""
    import compare

    found = compare.saved_sorters()
    if len(found) < 2:
        ui.warn("Need two saved sorts to compare — run 'sort' for two sorters first.")
        return None
    first = ui.select("Compare which sorter?", [(s, s, "") for s in found], default=0)
    if first is None:
        return None
    rest = [s for s in found if s != first]
    second = ui.select(f"…compared against?  (vs {first})", [(s, s, "") for s in rest], default=0)
    if second is None:
        return None
    return (first, second)


def _probe_typed(cfg: dict) -> None:
    """Typed 'Set probe geometry' helper: list available probe profiles, then
    activate one.  Mirrors the Textual ProbeManager in plain text (one round-trip
    — intentionally non-parity, no editor, just pick & activate)."""
    lib = probes.library()
    active_name = cfg.get("active_probe", probes.DEFAULT_PROBE)
    rows = [
        {
            "name": p["name"],
            "active": p["name"] == active_name,
            "summary": probes.summary(p),
            "builtin": p.get("builtin", False),
        }
        for p in lib
    ]
    ui.print_probes(rows)
    opts = [(p["name"], p["name"], probes.summary(p)) for p in lib]
    opts.append(("__done__", "Done — back to menu", ""))
    default_idx = next((i for i, (n, _, _) in enumerate(opts) if n == active_name), 0)
    name = ui.select("Set which probe?", opts, default=default_idx)
    if name not in (None, "__done__"):
        cfg["active_probe"] = name
        _save_config(cfg)
        ui.note(f"Active probe → {name}")


def _manage_sorters_typed(args, use_docker: bool) -> None:
    """Typed 'Manage sorters' hub: list each sorter's install / image-download /
    saved-sort state, then download an image (blocking, simple progress), delete a
    downloaded image, or clear a saved sort. Mirrors the Textual ManageSorters hub
    in plain text (intentionally non-parity — no live list, one round-trip pick)."""
    catalog = _catalog(args.sorter or sorter_registry.default_sorter(), use_docker)

    def _state_line(info: dict) -> str:
        bits = []
        if info.get("present"):
            bits.append(f"{info['units']}u saved")
        else:
            bits.append("no saved sort")
        if info.get("group") == "docker":
            if info.get("img_present"):
                size = (info.get("img_size") or 0) / 1e9
                bits.append(f"image ~{size:.1f} GB" if size else "image downloaded")
            else:
                bits.append("image not downloaded")
        return " · ".join(bits)

    while True:
        opts = [(info["name"], info["name"], _state_line(info)) for info in catalog]
        opts.append(("__done__", "Done — back to menu", ""))
        name = ui.select("Manage which sorter?", opts, default=len(opts) - 1)
        if name in (None, "__done__"):
            return
        info = next((i for i in catalog if i["name"] == name), None)
        if info is None:
            continue
        ops = []
        if info.get("group") == "docker" and not info.get("img_present"):
            ops.append(("download", "Download the Docker image (~1 GB, one time)", ""))
        if info.get("group") == "docker" and info.get("img_present"):
            size = (info.get("img_size") or 0) / 1e9
            ops.append(("delete", f"Delete the downloaded image (~{size:.1f} GB)"
                        if size else "Delete the downloaded image", ""))
        if info.get("present"):
            ops.append(("clear", f"Clear the saved sort ({info['units']}u)", ""))
        ops.append(("__back__", "Back", ""))
        op = ui.select(f"{name} — {_state_line(info)}", ops, default=len(ops) - 1)
        if op in (None, "__back__"):
            continue
        if op == "download":
            img = sorter_registry.default_docker_image(name)
            ui.note(f"Downloading {img} … (first run is ~1 GB)")

            def _on_status(text):
                ui.note(str(text))

            def _on_progress(done, total, is_bytes=True):
                pct = int(done / total * 100) if total else 0
                ui.note(f"  … {pct}%")

            ok = sorter_registry.pull_docker_image(img, _on_progress, _on_status)
            ui.say("✓ downloaded" if ok else "✗ download failed")
        elif op == "delete":
            img = sorter_registry.default_docker_image(name)
            ok, msg = sorter_registry.delete_docker_image(img)
            ui.say(("✓ " if ok else "✗ ") + msg)
        elif op == "clear":
            folder = bio.REPO_ROOT / "outputs" / name
            if not folder.exists():
                ui.warn(f"No saved sort for {name}.")
            else:
                import shutil
                try:
                    shutil.rmtree(folder)
                    ui.say(f"✓ Cleared saved {name} sort")
                except Exception as e:  # noqa: BLE001
                    ui.warn(f"Couldn't clear {name}: {e}")
        # Rebuild the catalog so the state lines reflect the change.
        catalog = _catalog(args.sorter or sorter_registry.default_sorter(), use_docker)


def _menu(args) -> int:
    """Interactive front door: Textual dashboard if possible, else typed fallback."""
    if not sys.stdin.isatty():
        ui.note("(non-interactive stdin -> building the report)")
        return 0 if DISPATCH["report"](args) else 1

    cfg = _load_config()
    theme = _apply_saved_theme(cfg)

    try:
        import menu_app  # imports textual; any failure -> typed fallback
        have_textual = True
    except Exception:  # noqa: BLE001 - missing/broken textual must degrade, not crash
        have_textual = False

    if have_textual:
        # The controller loads the recording + every saved analyzer before the app
        # paints its first frame, so without this the launch looks like a multi-
        # second black screen. One line keeps it alive.
        ui.note("Loading recording and saved sorts…")
        controller = MenuController(args, cfg)
        app = menu_app.SpikeMenuApp(controller)
        app.run()
        return app.return_code or 0
    return _menu_fallback(args, cfg, theme)


def _menu_fallback(args, cfg: dict, theme: str) -> int:
    """Typed / prompt_toolkit dashboard used when Textual is unavailable."""
    report = _data_report(args.data_dir)
    if not report["complete"]:  # nothing found OR an incomplete set (e.g. no sortable .ns5)
        _print_setup_plain(report)

    use_docker = bool(cfg.get("use_docker", False))
    if not cfg.get("seen_welcome", False):
        ui.note("Welcome! This finds neurons in your recording in 3 steps: "
                "Explore → Sort → Report.  Put your files in the data folder.")
        cfg["seen_welcome"] = True
        _save_config(cfg)
    catalog = _catalog(args.sorter or sorter_registry.default_sorter(), use_docker)
    ui.print_catalog(catalog)
    sorter_list = sorter_registry.runnable(use_docker) or [sorter_registry.default_sorter()]
    if not args.sorter or args.sorter not in sorter_list:
        args.sorter = sorter_list[0]
    pipeline, infos = _load_dashboard(args.data_dir, args.sorter, sorter_list, use_docker)
    active_idx = sorter_list.index(args.sorter)
    cursor = 0
    last = None
    while True:
        # Rebuild the action hints each loop so the active sorter's destructive-sort
        # caveat tracks the currently-selected tab (the typed fallback is intentionally
        # non-parity with the Textual accordion, but it surfaces the same `what`/caveat).
        active_name = sorter_list[active_idx]
        active_info = next((i for i in infos if i["name"] == active_name), None)
        actions = [(action, title, _fallback_action_hint(action, hint, active_info))
                   for _k, action, title, hint in _MENU] + [("__quit__", "Quit", "")]
        # One pinned, in-place view: header + sorter tabs + pipeline + last action + menu.
        action, active_idx = ui.dashboard_menu(HEADER, pipeline, infos, active_idx, actions,
                                               default=cursor, last=last)
        args.sorter = sorter_list[active_idx]       # the active tab IS the sorter
        for i in infos:
            i["active"] = i["name"] == args.sorter
        if action in (None, "__quit__"):
            return 0
        if action == "__sorter__":  # typed-fallback only: cycle to the next sorter
            active_idx = (active_idx + 1) % len(sorter_list)
            continue
        cursor = next((n for n, a in enumerate(actions) if a[0] == action), 0)
        if action in _DATA_ACTIONS and not report["present"]:
            ui.warn(f"{action} needs the recording files (see the setup notes above).")
            last = f"✗ {action} needs data"
            continue
        if action == "theme":
            names = list(ui.THEMES)
            choice = ui.select("Accent colour  (saved for next time)",
                               [(n, n, "(current)" if n == theme else "") for n in names],
                               default=names.index(theme) if theme in names else 0)
            if choice:
                theme = choice
                ui.set_accent(ui.THEMES[theme])
                cfg["theme"] = theme
                _save_config(cfg)
                last = f"Theme → {theme}"
            continue
        if action == "docker":
            turning_on = not bool(cfg.get("use_docker", False))
            if turning_on:
                state = sorter_registry.docker_state(refresh=True)
                ui.note(ui.docker_confirm_text(state))
                if state == "not_installed":
                    if ui.prompt("Open the Docker download page? [y/N] ").strip().lower().startswith("y"):
                        webbrowser.open("https://www.docker.com/products/docker-desktop/")
                elif state == "installed_not_running":
                    if ui.prompt("Start Docker Desktop now? [y/N] ").strip().lower().startswith("y"):
                        sorter_registry.start_docker()
                        ui.note("Starting Docker… give it ~30–60s, then toggle again.")
                if ui.prompt("Enable Docker sorters? [y/N] ").strip().lower() != "y":
                    last = "Docker sorters unchanged"
                    continue
            use_docker = not use_docker
            cfg["use_docker"] = use_docker
            _save_config(cfg)
            sorter_list = sorter_registry.runnable(use_docker) or [sorter_registry.default_sorter()]
            if args.sorter not in sorter_list:
                args.sorter = sorter_list[0]
            pipeline, infos = _load_dashboard(args.data_dir, args.sorter, sorter_list, use_docker)
            active_idx = sorter_list.index(args.sorter)
            last = f"Docker sorters {'on' if use_docker else 'off'}"
            continue
        if action == "params":
            _edit_params_typed(args.sorter, cfg)
            last = f"Edited {args.sorter} parameters"
            continue
        if action == "manage":
            _manage_sorters_typed(args, use_docker)
            # State may have changed (image deleted / saved sort cleared) — refresh.
            pipeline, infos = _load_dashboard(args.data_dir, args.sorter, sorter_list, use_docker)
            active_idx = sorter_list.index(args.sorter) if args.sorter in sorter_list else 0
            last = "Managed sorters"
            continue
        if action == "probe":
            _probe_typed(cfg)
            last = f"Active probe → {cfg.get('active_probe', probes.DEFAULT_PROBE)}"
            continue
        if action == "help":
            topics = [(k, t, "") for k, t, _b in ui.HELP_TOPICS]
            while True:
                topic = ui.select("Help — choose a topic", topics + [("__done__", "Back", "")],
                                  default=0)
                if topic in (None, "__done__"):
                    break
                if topic == "data":
                    _print_setup_plain(_data_report(args.data_dir), pipeline)
                    continue
                title, lines = next((t, b) for k, t, b in ui.HELP_TOPICS if k == topic)
                ui.say(f"\n[bold {ui.ACCENT}]{title}[/]")
                for ln in lines:
                    ui.say(f"  {ln}")
            last = "Closed help"
            continue
        if action == "compare":
            pair = _pick_compare_pair(args.data_dir)
            if pair is None:
                last = "Compare cancelled (need two saved sorts)"
                continue
            ok = _compare_pair(args, pair)
            last = _last_message("compare", args.sorter, ok)
            pipeline, infos = _load_dashboard(args.data_dir, args.sorter, sorter_list, use_docker)
            active_idx = sorter_list.index(args.sorter) if args.sorter in sorter_list else 0
            continue
        if action == "sort":
            span = ui.select("Sort how much?",
                             [("full", "Full recording", ""),
                              ("quick", f"Quick test — first {QUICK_SECONDS}s", "")],
                             default=0)
            if span is None:  # cancelled -> back to the menu without sorting
                last = "Sort cancelled"
                continue
            args.duration = QUICK_SECONDS if span == "quick" else None
            args.docker = use_docker
            params_path = _write_params_file(_load_config().get("sorter_params", {}).get(args.sorter, {}))
            args.params_file = params_path
            ok = DISPATCH["sort"](args)
            if params_path:
                Path(params_path).unlink(missing_ok=True)
            last = _last_message("sort", args.sorter, ok)
            pipeline, infos = _load_dashboard(args.data_dir, args.sorter, sorter_list, use_docker)
            active_idx = sorter_list.index(args.sorter) if args.sorter in sorter_list else 0
            continue
        ok = _self(action, args) if action in QT_ACTIONS else DISPATCH[action](args)
        last = _last_message(action, args.sorter, ok)


def main() -> int:
    bio.use_utf8_stdout()
    bio.mute_native_chatter()  # quiet OpenMP/Numba/probe noise for in-process report/compare too
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", nargs="?", choices=ACTIONS, default=None,
                        help="Run one action directly (default: interactive menu).")
    parser.add_argument("--data-dir", default=None, help="Folder with the .nev/.nsX (default: repo root).")
    parser.add_argument("--sorter", default=None, help="Active sorter (default: auto).")
    parser.add_argument("--probe", default=None, help="Active probe profile (internal).")
    parser.add_argument("--duration", type=float, default=None, help="For 'sort': first N seconds only.")
    parser.add_argument("--docker", action="store_true",
                        help="For 'sort': run the sorter in its Docker image.")
    parser.add_argument("--gui-mode", choices=["auto", "desktop", "web"], default="auto",
                        help="For 'gui': desktop window, browser (web), or auto-detect (default).")
    args = parser.parse_args()

    if args.action is None:
        return _menu(args)
    _apply_saved_theme(_load_config())  # honour the saved accent for direct actions too
    ok = DISPATCH[args.action](args)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
