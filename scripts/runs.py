"""The versioned run store: where sorts live, which one is current, how to
regenerate one from its own record.

    uv run python scripts/runs.py list                            # every saved run
    uv run python scripts/runs.py list --sorter tridesclous2
    uv run python scripts/runs.py show --sorter tridesclous2      # the current run's record
    uv run python scripts/runs.py show --sorter X --run 20260818-221501-3f9c2a
    uv run python scripts/runs.py current --sorter X --run ID     # re-point (--force: see below)
    uv run python scripts/runs.py regenerate --sorter X           # re-run it + match report
    uv run python scripts/runs.py export --sorter X --out sort_config.json
    uv run python scripts/runs.py regenerate --config sort_config.json

Single source of truth for **where a sort's results live and which one is
current**. No other module builds an ``outputs/<sorter>/...`` path by hand:
``run_sorting`` writes into the run directory this module hands it, and
``report``/``compare``/the menu controller/``curation`` all resolve through
``sort_paths()``.

The layout
----------
::

    outputs/<sorter>/
        current.json                    THE POINTER — {"run_id": ...}, never a copy
        runs/<run_id>/                  ONE RUN, self-contained
            sorting/ analyzer/ sorter_output/
            run_info.json               the run record (provenance; see below)
            quality_metrics.csv summary.json summary.csv
            curation.json  curated/     W1's record + curated output ride INSIDE
        regen/<run_id>/                 regeneration checks (never current)
        sort.log                        the in-UI sort's stderr (per sorter, not per run)

A run id is ``YYYYmmdd-HHMMSS-<6 hex>`` — sortable by time, unique by the
discriminator, and recorded in the run's own ``run_info.json`` as ``run_id``, so
a directory that is moved or copied still says which run it is.

Runs never overwrite each other: a second sort of the same sorter lands in its
own directory and both stay readable. The **pointer** is what changes, and it is
a small JSON file replaced with ``os.replace`` (atomic on Windows and POSIX) —
no symlinks, which need an elevated account or developer mode on Windows.

Resolution order (``resolve()``), documented because the lab has saved sorts
predating the store:

1. ``current.json``, when it names a run that still exists (``"legacy"`` is a
   valid pointer target, meaning the pre-store layout).
2. the newest **full** run under ``runs/``.
3. the **legacy** layout — ``outputs/<sorter>/analyzer`` + ``sorting`` written
   directly in the sorter directory, read-only: nothing writes there any more.
4. the newest run under ``runs/`` of any kind (i.e. a smoke run, when that is
   all there is).

The smoke rule
--------------
A run made with ``--duration`` is a **smoke** run (``run_info["smoke"]``). A
smoke run **never** displaces a full run as current. ``set_current`` refuses it,
says so loudly, and *pins the incumbent* by writing the pointer to it — so the
refusal survives even step 2 of the resolution order. ``--force``
(``run_sorting.py --make-current``) is the only override, and it is recorded in
the pointer's ``reason``. A smoke run may become current when there is no full
run to displace; a full run always may.

The run record
--------------
``run_info.json`` is the run's identity — ``curation.json`` anchors on its
fields, so this module only ever *adds* keys. Beyond what the sort already
wrote (sorter, window, band, channels, unit count, ``bad_channels``), the record
carries what regeneration needs:

    run_id, run_dir, smoke, schema_version
    params      {"effective": {...}, "defaults": {...}, "overrides": {...}}
                the EFFECTIVE dict, copied at run time — defaults + the
                overrides actually applied, never a reference to .si_menu.json
    seed        {"key", "value", "pinned"} where the sorter accepts one
    determinism {"class", "note"} — measured-stochastic sorters say so here
    probe_id / probe_label / probe_kind / geometry_hash / probe_fallback
    preprocessing  the ordered chain: aux drop, probe, bandpass, bad channels,
                common median reference, frame slice
    packages    spikeinterface / neo / numpy / probeinterface / scipy versions
    git         {"sha", "branch", "dirty"} of this repo at run time
    platform    system / release / machine / python
    recording   data dir, base name, sampling rate, channel counts, duration

Regeneration
------------
``regenerate`` rebuilds ``run_sorting.py``'s argv from the record alone
(``config_argv``), re-runs it into ``outputs/<sorter>/regen/<id>/`` — never into
``runs/``, so a check cannot change what is current — and prints a match report.

Criteria are chosen to be **stable under a stochastic sorter**. tridesclous2 on
this recording produced 14, 16 and 18 units across three identical runs (PRE1,
2026-08-18), so unit counts and unit ids are reported as INFORMATIONAL and are
never a verdict. What is compared, each with its tolerance stated:

    recording            exact base name + sampling rate — a re-run pointed at a
                         different file set is named as that, not left to show up
                         indirectly as poor containment
    channels sorted      exact set
    preprocessing chain  exact (band, reference, aux drop, bad channels)
    sorter params        exact effective parameter dict; DIFFERS names the keys.
                         The tolerance bands below are wide enough to swallow a
                         hand-edited knob, so nothing else here would mention it
    probe geometry       exact geometry hash
    environment          exact package versions + git sha (a caveat, not a fail)
    noise floor          +/- NOISE_TOL_UV (a property of the recording, so it is
                         the strongest single check — and the ~4 uV canary)
    spike containment    BOTH directions: the fraction of each sort's spikes the
                         other also found within CONTAINMENT_DELTA_MS
    metric ranges        V_pp / SNR / yield within stated relative tolerance

Bit-identity is never claimed unless observed: the report says "BIT-IDENTICAL"
only when the two pooled spike trains are equal spike for spike. Containment
1.0 in both directions is not enough — two different sorts routinely find every
spike within the coincidence window without agreeing on a single timestamp.

API
---
Paths and pointers (pure json + pathlib; no SpikeInterface, no numpy):
    outputs_dir/sorter_dir/runs_dir/run_dir/pointer_path(...)   -> Path
    new_run_id(when=None, discriminator=None)                   -> str
    sort_paths(sorter, root=None, outputs=None, run=None)       -> dict of Paths
    list_runs(sorter, ...)      -> [{"id","dir","info","smoke","legacy","created"}]
    resolve(sorter, ...)        -> one of those + {"how"}, or None
    set_current(sorter, run_id, ..., force=False)  -> (ok, message)
    saved_sorters(...)          -> [sorter]        sorters with a resolvable run
    sorter_for_dir(path)        -> str             sorter that owns an analyzer dir

Provenance collectors (called by run_sorting at write time):
    package_versions() / platform_info() / git_info(root=None)
    geometry_hash(probe) / seed_of(sorter, params) / determinism_of(sorter)

Regeneration:
    config_from_record(info)        -> the committable config (slice 4)
    config_argv(config, output_dir) -> argv for run_sorting.py
    regenerate(...)                 -> {"report", "config", "argv", "out", "rc"};
                                    "report" is None when the re-run had nothing
                                    to be compared against (a config from git
                                    naming a run this machine never had)
    compare_runs(recorded, regenerated, ...) -> the match report (pure)
    format_match_report(report)     -> str
    containment(a, b, delta_s)      -> float       pure numpy, both directions
    pooled_spike_times(analyzer_dir)-> np.ndarray  (imports SpikeInterface)
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402  (REPO_ROOT only — no SpikeInterface)

SCHEMA_VERSION = "1"
OUTPUTS_DIRNAME = "outputs"
RUNS_DIRNAME = "runs"
REGEN_DIRNAME = "regen"
POINTER_NAME = "current.json"
RUN_INFO_NAME = "run_info.json"
LEGACY_RUN_ID = "legacy"
# The record and the curated output ride inside the run directory they curate, so
# this module builds their paths and therefore holds their names. curation.py
# re-exports these three rather than defining its own (it imports this module;
# this one must not import it back), so they cannot drift apart.
CURATED_DIRNAME = "curated"
RECORD_NAME = "curation.json"
PHY_DIRNAME = "phy"

# Provenance: the packages whose version can change a sort's output.
PROVENANCE_PACKAGES = ("spikeinterface", "neo", "numpy", "probeinterface", "scipy", "numba")

# Sorters measured on THIS recording rather than assumed. Anything absent is
# "unverified" — the record must not claim determinism nobody checked.
DETERMINISM = {
    "tridesclous2": ("measured-stochastic",
                     "14, 16 and 18 units across three identical full-pipeline runs on "
                     "PFCM7_d0ephys_Block2 (PRE1, 2026-08-18); one run split a unit pair "
                     "another merged. RNG state was ruled out. Unit counts and ids are "
                     "not reproduction criteria for this sorter."),
}
DETERMINISM_UNVERIFIED = ("unverified",
                          "determinism of this sorter has not been measured on this "
                          "recording; treat unit counts as unstable until it is.")

# Parameter names a sorter uses for its RNG seed, in preference order.
SEED_KEYS = ("seed", "random_seed", "rng_seed")

# --- regeneration tolerances --- #
# CALIBRATED, not guessed: every number below is set against the spread measured
# across four independent full-pipeline tridesclous2 sorts of the same 132 s
# window of PFCM7_d0ephys_Block2 (six same-window pairs, 2026-08-18). The sorter
# is measured non-deterministic here, so that spread IS the noise a legitimate
# regeneration makes; each tolerance sits above it with the stated margin, and
# far below the move that the failure it guards against would produce.
#
# Noise floor is a property of the recording (post-bandpass + CMR), so two runs
# of the same window agree closely: max |delta| measured 0.112 uV. 0.25 uV is
# ~2x that, and ~12x narrower than the ~3 uV a double-scaling bug moves it.
NOISE_TOL_UV = 0.25
# Coincidence window for "the same spike". 0.4 ms is compare.py's offline-vs-
# offline window — both sides here are peak-aligned offline sorts.
CONTAINMENT_DELTA_MS = 0.4
# Fraction of one sort's spikes that reappear in the other. A stochastic sorter
# splits and merges units between runs, but the SPIKES it finds are stable, so
# this is the criterion that survives that. Measured over fourteen directed
# comparisons (seven same-window pairs): mean 0.954, sd 0.025, worst 0.903. The
# worst case is a 30 s smoke window — a short window sees fewer spikes per unit,
# so its runs diverge more than full-recording runs do (those sit 0.925–0.991).
# A first-run floor of 0.90 was measured at 0.903 on that smoke pair, i.e. it
# would have failed honest regenerations, so the floor is 0.85: ~4 sd below the
# mean, ~5 pp below the worst observed, and far above the sub-0.5 containment a
# genuinely different pipeline (wrong band, window or channel set) produces.
#
# VALIDITY RANGE of that calibration: it was measured on 132 s (full recording)
# and 30 s windows only, and the trend across those two is monotone — the worst
# honest pair, 0.903, is the 30 s one. A shorter window sees fewer spikes per
# unit, so its runs diverge further, and an honest regeneration of, say, a 5 s
# window may sit below 0.85 legitimately. Treat a containment failure on a
# window shorter than 30 s as uncalibrated rather than as evidence, and
# re-measure before moving this number for it.
CONTAINMENT_MIN = 0.85
# Relative tolerance on the headline metrics (V_pp, SNR medians): unit membership
# shifts between runs, so the medians move more than the noise floor does. Max
# measured |delta| 9.7% (V_pp) and 4.4% (SNR); 20% is 2x the worst observed and
# still ~4x narrower than the 75% a re-applied channel gain would produce.
METRIC_REL_TOL = 0.20
# Yield is a percentage, so it gets an absolute tolerance in percentage points.
# Max measured 6.3 pp — exactly one electrode of sixteen. 15 pp is ~2.4x that.
YIELD_TOL_PP = 15.0

# Verdict vocabulary. One of these is printed for every criterion.
V_MATCH = "MATCH"
V_WITHIN = "WITHIN TOLERANCE"
V_OUTSIDE = "OUTSIDE TOLERANCE"
V_DIFFERS = "DIFFERS"
V_SKIPPED = "NOT COMPARED"
V_INFO = "INFORMATIONAL"
# Verdicts that make the overall verdict fail.
_FAILING = (V_OUTSIDE, V_DIFFERS)


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def outputs_dir(root=None, outputs=None) -> Path:
    """The store root. ``outputs`` wins (callers that own an OUTPUT_DIR pass it);
    otherwise ``root``/outputs, defaulting to the repo root read at call time so
    tests can monkeypatch ``bio.REPO_ROOT``."""
    if outputs is not None:
        return Path(outputs)
    return (Path(root) if root is not None else bio.REPO_ROOT) / OUTPUTS_DIRNAME


def sorter_dir(sorter: str, root=None, outputs=None) -> Path:
    return outputs_dir(root, outputs) / sorter


def runs_dir(sorter: str, root=None, outputs=None) -> Path:
    return sorter_dir(sorter, root, outputs) / RUNS_DIRNAME


def regen_dir(sorter: str, root=None, outputs=None) -> Path:
    return sorter_dir(sorter, root, outputs) / REGEN_DIRNAME


def pointer_path(sorter: str, root=None, outputs=None) -> Path:
    return sorter_dir(sorter, root, outputs) / POINTER_NAME


def run_dir(sorter: str, run_id: str, root=None, outputs=None) -> Path:
    """The directory for one run id. ``legacy`` maps to the pre-store layout."""
    if run_id == LEGACY_RUN_ID:
        return sorter_dir(sorter, root, outputs)
    return runs_dir(sorter, root, outputs) / run_id


def new_run_id(when=None, discriminator=None) -> str:
    """``YYYYmmdd-HHMMSS-<6 hex>`` — time-sortable, collision-proof within a second."""
    when = when or datetime.now()
    disc = discriminator or secrets.token_hex(3)
    return f"{when:%Y%m%d-%H%M%S}-{disc}"


def sorter_for_dir(path) -> str:
    """The sorter that owns an analyzer/run directory, store layout or legacy.

    ``outputs/tdc2/runs/<id>/analyzer`` -> ``tdc2``; ``outputs/tdc2/analyzer`` ->
    ``tdc2``. Used where a caller has only a path and needs the label.
    """
    p = Path(path)
    parts = p.parts
    if RUNS_DIRNAME in parts:
        i = len(parts) - 1 - parts[::-1].index(RUNS_DIRNAME)
        if i >= 1:
            return parts[i - 1]
    if REGEN_DIRNAME in parts:
        i = len(parts) - 1 - parts[::-1].index(REGEN_DIRNAME)
        if i >= 1:
            return parts[i - 1]
    return p.parent.name


def sort_paths(sorter: str, root=None, outputs=None, run=None) -> dict:
    """Every path for one sorter's run — the ONE resolver every surface uses.

    ``run`` is a run id, a run directory, or None for the current run. When
    nothing resolves (no sort yet) the legacy paths come back, so callers can
    ``.exists()``-check them instead of handling None.

    The key set is a superset of curation.py's ``sort_paths``, deliberately: the
    curation record and the curated output live INSIDE the run they curate.
    """
    base = Path(root) if root is not None else bio.REPO_ROOT
    if run is None:
        found = resolve(sorter, root, outputs)
        out = found["dir"] if found else sorter_dir(sorter, root, outputs)
        run_id = found["id"] if found else None
    elif isinstance(run, (str, os.PathLike)) and Path(run).is_absolute():
        out, run_id = Path(run), Path(run).name
    else:
        out, run_id = run_dir(sorter, str(run), root, outputs), str(run)
    curated = out / CURATED_DIRNAME
    return {
        "root": base,
        "sorter": sorter,
        "id": run_id,
        "sorter_dir": sorter_dir(sorter, root, outputs),
        "runs": runs_dir(sorter, root, outputs),
        "pointer": pointer_path(sorter, root, outputs),
        "out": out,
        "sorting": out / "sorting",
        "analyzer": out / "analyzer",
        "sorter_output": out / "sorter_output",
        "run_info": out / RUN_INFO_NAME,
        "summary": out / "summary.json",
        "metrics": out / "quality_metrics.csv",
        "record": out / RECORD_NAME,
        "phy": out / PHY_DIRNAME,
        "curated": curated,
        "curated_sorting": curated / "sorting",
        "curated_analyzer": curated / "analyzer",
        "curated_run_info": curated / RUN_INFO_NAME,
        "curated_metrics": curated / "quality_metrics.csv",
        "curated_phy": curated / PHY_DIRNAME,
        "log": sorter_dir(sorter, root, outputs) / "sort.log",
    }


# --------------------------------------------------------------------------- #
# The store — listing, the pointer, resolution
# --------------------------------------------------------------------------- #
def read_json(path) -> dict:
    """Read a JSON object; {} when missing or unreadable (records are best-effort)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - absent / truncated / not JSON
        return {}
    return data if isinstance(data, dict) else {}


def is_smoke(info: dict) -> bool:
    """A run limited with ``--duration``. Reads the recorded flag, falling back to
    the pre-W2 ``duration_arg`` so legacy runs classify correctly too."""
    if isinstance(info.get("smoke"), bool):
        return info["smoke"]
    return info.get("duration_arg") is not None


def _has_sort(d: Path) -> bool:
    return (d / "analyzer").is_dir() or (d / "sorting").is_dir()


def _entry(sorter: str, run_id: str, d: Path, *, legacy: bool = False) -> dict:
    info = read_json(d / RUN_INFO_NAME)
    return {"id": run_id, "sorter": sorter, "dir": d, "info": info,
            "smoke": is_smoke(info), "legacy": legacy,
            "created": info.get("created") or "",
            "units": info.get("n_units")}


def list_runs(sorter: str, root=None, outputs=None, include_legacy: bool = True) -> list:
    """Every run for ``sorter``, newest first; the legacy layout last when present.

    A run directory without ``run_info.json`` is an unfinished run (the sort died
    before the record was written) — it is skipped here but left on disk, because
    its ``sorter_output/`` is the only evidence of what went wrong.
    """
    out = []
    rd = runs_dir(sorter, root, outputs)
    if rd.is_dir():
        for d in rd.iterdir():
            if d.is_dir() and (d / RUN_INFO_NAME).is_file():
                out.append(_entry(sorter, d.name, d))
    # Ids lead with the timestamp, so id order IS time order; `created` breaks
    # ties for ids made by hand.
    out.sort(key=lambda e: (e["id"], e["created"]), reverse=True)
    sd = sorter_dir(sorter, root, outputs)
    if include_legacy and _has_sort(sd):
        out.append(_entry(sorter, LEGACY_RUN_ID, sd, legacy=True))
    return out


def unfinished_runs(sorter: str, root=None, outputs=None) -> list:
    """Run directories with no ``run_info.json``: a sort that died before it could
    write its record. ``list_runs`` cannot include them — there is no record to
    read — so without this they exist on disk and are named by nothing.

    Nothing deletes them automatically: their ``sorter_output/`` is the only
    evidence of what went wrong. ``runs.py list`` names them so the disk is not
    quietly filling with runs no surface mentions; clearing a sorter's saved sort
    from the menu removes the whole store, corpses included.
    """
    rd = runs_dir(sorter, root, outputs)
    if not rd.is_dir():
        return []
    return sorted((d for d in rd.iterdir()
                   if d.is_dir() and not (d / RUN_INFO_NAME).is_file()),
                  key=lambda d: d.name)


def read_pointer(sorter: str, root=None, outputs=None) -> dict:
    return read_json(pointer_path(sorter, root, outputs))


def write_pointer(sorter: str, run_id: str, root=None, outputs=None, reason: str = "") -> Path:
    """Point ``sorter`` at ``run_id``. Atomic: write a sibling temp file, then
    ``os.replace`` — which is atomic on Windows too, unlike a symlink swap."""
    path = pointer_path(sorter, root, outputs)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"run_id": run_id, "updated": datetime.now().isoformat(timespec="seconds"),
               "reason": reason, "schema_version": SCHEMA_VERSION}
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def resolve(sorter: str, root=None, outputs=None) -> "dict | None":
    """The current run for ``sorter`` (see the module docstring's resolution
    order), plus ``how`` — which rule chose it. None when nothing is saved."""
    runs = list_runs(sorter, root, outputs)
    if not runs:
        return None
    by_id = {r["id"]: r for r in runs}
    want = read_pointer(sorter, root, outputs).get("run_id")
    if want and want in by_id:
        return {**by_id[want], "how": "pointer"}
    full = [r for r in runs if not r["smoke"] and not r["legacy"]]
    if full:
        return {**full[0], "how": "newest full run"}
    legacy = [r for r in runs if r["legacy"]]
    if legacy:
        return {**legacy[0], "how": "legacy layout"}
    return {**runs[0], "how": "newest run (smoke — no full run saved)"}


def current_dir(sorter: str, root=None, outputs=None) -> "Path | None":
    found = resolve(sorter, root, outputs)
    return found["dir"] if found else None


def saved_sorters(root=None, outputs=None) -> list:
    """Sorter names with a resolvable saved run, sorted."""
    base = outputs_dir(root, outputs)
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir()
                  if p.is_dir() and resolve(p.name, root, outputs) is not None)


def smoke_refusal_message(sorter: str, incumbent: dict, candidate_id: str) -> str:
    """The loud line when a smoke run would have replaced a full run."""
    info = incumbent.get("info") or {}
    eff = info.get("effective_seconds")
    span = f"{eff:.0f}s" if isinstance(eff, (int, float)) else "?s"
    where = LEGACY_RUN_ID if incumbent.get("legacy") else incumbent.get("id")
    return (f"this is a --duration smoke run, so it did NOT become the current {sorter} "
            f"sort: the full run {where} ({info.get('n_units', '?')} units over {span}, "
            f"sorted {info.get('created', '?')}) stays current. The smoke run is saved as "
            f"{candidate_id} and every surface still reads the full run. "
            "Pass --make-current to override.")


def set_current(sorter: str, run_id: str, root=None, outputs=None, *,
                force: bool = False, reason: str = "") -> "tuple[bool, str]":
    """Point ``sorter`` at ``run_id``, enforcing the smoke rule.

    Refusing is not passive: the incumbent is PINNED (the pointer is written to
    it), so a later resolution cannot drift onto the smoke run through the
    fallback rules. Returns ``(ok, message)``; ``ok`` False means the pointer
    still names the incumbent.
    """
    entry = next((r for r in list_runs(sorter, root, outputs) if r["id"] == run_id), None)
    if entry is None:
        return False, f"no run {run_id!r} for {sorter}"
    incumbent = resolve(sorter, root, outputs)
    if (entry["smoke"] and not force and incumbent is not None
            and incumbent["id"] != run_id and not incumbent["smoke"]):
        write_pointer(sorter, incumbent["id"], root, outputs,
                      reason=f"pinned: smoke run {run_id} refused")
        return False, smoke_refusal_message(sorter, incumbent, run_id)
    write_pointer(sorter, run_id, root, outputs,
                  reason=reason or ("forced" if force and entry["smoke"] else ""))
    kind = "smoke run" if entry["smoke"] else "run"
    forced = " (forced over a full run)" if force and entry["smoke"] else ""
    return True, f"{sorter}: current {kind} is now {run_id}{forced}"


# --------------------------------------------------------------------------- #
# Provenance collectors
# --------------------------------------------------------------------------- #
def package_versions(names=PROVENANCE_PACKAGES) -> dict:
    """Installed versions by distribution metadata — no imports, so collecting
    provenance never drags SpikeInterface into a view process."""
    from importlib import metadata

    out = {}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except Exception:  # noqa: BLE001 - not installed in this env
            out[name] = None
    return out


def platform_info() -> dict:
    import platform

    return {"system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "python": platform.python_version()}


def _git(root: Path, *args: str) -> "str | None":
    try:
        res = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=15)
    except Exception:  # noqa: BLE001 - git missing, or not a repo
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def git_info(root=None) -> dict:
    """``{"sha", "branch", "dirty"}`` for this repo; values None when git can't
    answer (no git on the lab box, an exported tree). ``dirty`` counts tracked
    modifications — a sort from an edited tree is not the sort the sha names."""
    base = Path(root) if root is not None else bio.REPO_ROOT
    sha = _git(base, "rev-parse", "HEAD")
    status = _git(base, "status", "--porcelain", "--untracked-files=no")
    return {"sha": sha,
            "branch": _git(base, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": None if status is None else bool(status.strip())}


def geometry_hash(probe) -> "str | None":
    """A stable sha256 over what a probe means to a sorter: contact positions,
    shank ids and the device-channel wiring. Positions are rounded to 1 nm so an
    innocent float difference between platforms cannot change the hash.
    """
    import hashlib

    import numpy as np

    try:
        pos = np.asarray(probe.contact_positions, dtype=float).round(3).tolist()
        shanks = [str(s) for s in (probe.shank_ids if probe.shank_ids is not None else [])]
        wiring = probe.device_channel_indices
        wiring = [] if wiring is None else [int(i) for i in wiring]
        payload = json.dumps({"ndim": int(probe.ndim), "positions": pos,
                              "shank_ids": shanks, "device_channel_indices": wiring},
                             sort_keys=True)
    except Exception:  # noqa: BLE001 - an odd probe object still gets a record
        return None
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def seed_of(sorter: str, params: dict) -> dict:
    """The run's RNG seed, honestly: which key the sorter uses, its effective
    value, and whether it was actually pinned (SpikeInterface's internal sorters
    all accept ``seed`` but default it to None)."""
    for key in SEED_KEYS:
        if key in (params or {}):
            value = params[key]
            return {"key": key, "value": value, "pinned": value is not None}
    return {"key": None, "value": None, "pinned": False}


def determinism_of(sorter: str) -> dict:
    cls, note = DETERMINISM.get(sorter, DETERMINISM_UNVERIFIED)
    return {"class": cls, "note": note}


# --------------------------------------------------------------------------- #
# Config-as-code — the committable description of a run
# --------------------------------------------------------------------------- #
def config_from_record(info: dict) -> dict:
    """The small, committable subset of a run record that fully describes how to
    re-run it. Everything else in the record describes what happened, not what to do."""
    params = (info.get("params") or {})
    pre = (info.get("preprocessing") or {})
    bad = (info.get("bad_channels") or {})
    return {
        "kind": "spikeinterface-workbench-sort-config",
        "schema_version": SCHEMA_VERSION,
        "from_run": info.get("run_id"),
        "sorter": info.get("sorter"),
        "probe": info.get("probe_id") or info.get("probe"),
        "params": params.get("effective") or {},
        "duration": info.get("duration_arg"),
        "freq_min": info.get("freq_min", pre.get("freq_min")),
        "freq_max": info.get("freq_max", pre.get("freq_max")),
        "keep_analog": bool(info.get("keep_analog")),
        # Whether the sort ACTUALLY ran in a container (run_sorting records the
        # resolved fact, not the raw flag). Without it the config's claim to
        # fully describe the re-run is false for every containerized sort — and
        # the lab's Windows box is where those live.
        "docker": bool(info.get("docker")),
        "n_jobs": info.get("n_jobs", 1),
        "bad_channel_method": bad.get("method"),
        "bad_channels": list(bad.get("manual") or []),
        "bad_channel_detection": bool(bad.get("enabled", True)),
        "data_dir": info.get("recording", {}).get("data_dir"),
    }


def config_argv(config: dict, output_dir, *, params_file=None) -> list:
    """argv for ``run_sorting.py`` that reproduces ``config``.

    The EFFECTIVE parameter dict is passed through ``--params-file`` — pinning
    every value, not just the overrides, so a change in the installed sorter's
    defaults cannot silently ride along. An unknown key then fails loudly in
    ``resolve_overrides``, which is the honest outcome.
    """
    argv = [sys.executable, str(Path(__file__).resolve().parent / "run_sorting.py"),
            "--sorter", str(config["sorter"]), "--output-dir", str(output_dir)]
    if config.get("docker"):
        # A sorter that only exists in a container needs this before it needs
        # anything else: without it run_sorting resolves the sorter natively and
        # exits with "re-run with --docker", so the regeneration never starts.
        argv += ["--docker"]
    if config.get("probe"):
        argv += ["--probe", str(config["probe"])]
    if params_file is not None:
        argv += ["--params-file", str(params_file)]
    if config.get("duration") is not None:
        argv += ["--duration", str(config["duration"])]
    for flag, key in (("--freq-min", "freq_min"), ("--freq-max", "freq_max")):
        if isinstance(config.get(key), (int, float)):
            argv += [flag, f"{config[key]:g}"]
    if config.get("keep_analog"):
        argv += ["--keep-analog"]
    if config.get("n_jobs"):
        argv += ["--n-jobs", str(int(config["n_jobs"]))]
    if config.get("bad_channel_method"):
        argv += ["--bad-channel-method", str(config["bad_channel_method"])]
    if config.get("bad_channels"):
        argv += ["--bad-channels", ",".join(str(c) for c in config["bad_channels"])]
    if not config.get("bad_channel_detection", True):
        argv += ["--no-bad-channel-detection"]
    if config.get("data_dir"):
        argv += ["--data-dir", str(config["data_dir"])]
    return argv


# --------------------------------------------------------------------------- #
# Regeneration + the match report
# --------------------------------------------------------------------------- #
def containment(times_a, times_b, delta_s: float) -> float:
    """Fraction of ``times_a`` with a ``times_b`` spike within ``delta_s``.

    Pure numpy over two sorted second-arrays. This is deliberately unit-blind:
    a stochastic sorter reshuffles unit membership between runs, but the spike
    train it detects is stable, so containment measures what actually survives.
    """
    import numpy as np

    a = np.asarray(times_a, dtype=float)
    b = np.asarray(times_b, dtype=float)
    if a.size == 0:
        return float("nan")
    if b.size == 0:
        return 0.0
    b = np.sort(b)
    idx = np.searchsorted(b, a)
    left = np.clip(idx - 1, 0, b.size - 1)
    right = np.clip(idx, 0, b.size - 1)
    nearest = np.minimum(np.abs(b[left] - a), np.abs(b[right] - a))
    return float(np.mean(nearest <= delta_s))


def pooled_spike_times(analyzer_dir) -> "list | None":
    """Every spike time (seconds) in a saved analyzer's sorting, pooled across
    units and sorted. None when the analyzer can't be read."""
    try:
        import numpy as np
        import spikeinterface.full as si

        a = si.load_sorting_analyzer(Path(analyzer_dir))
        sorting = a.sorting
        fs = float(sorting.get_sampling_frequency())
        trains = [np.asarray(sorting.get_unit_spike_train(u), dtype=float) / fs
                  for u in sorting.get_unit_ids()]
        if not trains:
            return []
        return np.sort(np.concatenate(trains)).tolist()
    except Exception:  # noqa: BLE001 - unreadable analyzer -> criterion not compared
        return None


def _criterion(name, compared, tolerance, recorded, regenerated, verdict, note="") -> dict:
    return {"name": name, "compared": compared, "tolerance": tolerance,
            "recorded": recorded, "regenerated": regenerated,
            "verdict": verdict, "note": note}


def _fmt(value, digits=2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, (list, tuple, set)):
        return f"{len(value)}"
    return str(value)


def _param_value(params: dict, key: str, limit: int = 20) -> str:
    """One parameter value, short enough to sit in a report note. A key that is
    absent says so rather than reading as a recorded ``None``."""
    if key not in params:
        return "absent"
    text = json.dumps(params[key], default=str)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _chain_signature(info: dict) -> dict:
    """The preprocessing facts two runs must share, flattened for comparison."""
    bad = info.get("bad_channels") or {}
    return {
        "freq_min": info.get("freq_min"),
        "freq_max": info.get("freq_max"),
        "reference": (info.get("preprocessing") or {}).get("reference", "global median"),
        "keep_analog": bool(info.get("keep_analog")),
        "n_dropped_analog": info.get("n_dropped_analog"),
        "bad_excluded": sorted(str(c) for c in (bad.get("excluded") or [])),
        "bad_method": bad.get("method"),
        "bad_detection": bad.get("enabled"),
        "effective_seconds": (round(float(info["effective_seconds"]), 1)
                              if isinstance(info.get("effective_seconds"), (int, float))
                              else None),
    }


def compare_runs(recorded: dict, regenerated: dict, *,
                 recorded_summary=None, regenerated_summary=None,
                 recorded_spikes=None, regenerated_spikes=None,
                 delta_ms: float = CONTAINMENT_DELTA_MS) -> dict:
    """Build the match report. Pure: every input is a dict or a list of times.

    ``recorded``/``regenerated`` are run records (run_info.json); the summaries
    are ``summary.json`` (sort_summary's six metrics); the spike lists are pooled
    spike times in seconds. Anything passed as None becomes a NOT COMPARED
    criterion rather than a silent pass.
    """
    crit = []

    # 0. the recording itself. A config re-run on a machine holding a different
    #    file set still sorts something, and every other criterion then fails
    #    obliquely (containment, noise) without naming the actual cause.
    a_rec = recorded.get("recording") or {}
    b_rec = regenerated.get("recording") or {}
    a_base, b_base = a_rec.get("base"), b_rec.get("base")
    a_fs, b_fs = a_rec.get("sampling_rate_hz"), b_rec.get("sampling_rate_hz")
    rec_diffs = ([] if a_base == b_base else ["base name"]) + \
                ([] if a_fs == b_fs else ["sampling rate"])
    crit.append(_criterion(
        "recording", "file set base name + sampling rate", "exact",
        f"{a_base or '?'} @ {_fmt(a_fs, 0)} Hz", f"{b_base or '?'} @ {_fmt(b_fs, 0)} Hz",
        V_SKIPPED if not a_base or not b_base else (V_MATCH if not rec_diffs else V_DIFFERS),
        "" if not rec_diffs else "differs: " + ", ".join(rec_diffs)))

    # 1. channels sorted — exact set. The sort's own definition of what it saw.
    a_ch = sorted(str(c) for c in (recorded.get("channel_ids") or []))
    b_ch = sorted(str(c) for c in (regenerated.get("channel_ids") or []))
    crit.append(_criterion(
        "channels sorted", "channel id set", "exact",
        f"{len(a_ch)}: {', '.join(a_ch) if len(a_ch) <= 6 else a_ch[0] + '…' + a_ch[-1]}",
        f"{len(b_ch)}: {', '.join(b_ch) if len(b_ch) <= 6 else b_ch[0] + '…' + b_ch[-1]}",
        V_MATCH if a_ch and a_ch == b_ch else (V_SKIPPED if not a_ch or not b_ch else V_DIFFERS)))

    # 2. preprocessing chain — band, reference, aux drop, bad channels, window.
    a_pre, b_pre = _chain_signature(recorded), _chain_signature(regenerated)
    diffs = [k for k in a_pre if a_pre[k] != b_pre[k]]
    crit.append(_criterion(
        "preprocessing chain", "band · reference · aux drop · bad channels · window", "exact",
        f"{a_pre['freq_min']:g}–{a_pre['freq_max']:g} Hz, {a_pre['reference']}"
        if isinstance(a_pre["freq_min"], (int, float)) else "—",
        f"{b_pre['freq_min']:g}–{b_pre['freq_max']:g} Hz, {b_pre['reference']}"
        if isinstance(b_pre["freq_min"], (int, float)) else "—",
        V_MATCH if not diffs else V_DIFFERS,
        "" if not diffs else "differs: " + ", ".join(diffs)))

    # 2b. sorter parameters — the knobs, exactly, all ~31 of them. Every other
    #     criterion is a tolerance band wide enough to swallow a changed
    #     detect_threshold: a regeneration from a hand-edited config can land
    #     inside containment AND inside the metric bands and print REGENERATED
    #     while having asked the sorter a different question. Nothing else in the
    #     report would say so, which is the one thing it exists not to do.
    a_par = (recorded.get("params") or {}).get("effective")
    b_par = (regenerated.get("params") or {}).get("effective")
    if not isinstance(a_par, dict) or not isinstance(b_par, dict) or not (a_par and b_par):
        # Named by size, never dumped: a 31-key dict in a table column would push
        # every other row off the terminal.
        crit.append(_criterion(
            "sorter params", "the effective parameter dict", "exact",
            f"{len(a_par)} keys" if isinstance(a_par, dict) else "—",
            f"{len(b_par)} keys" if isinstance(b_par, dict) else "—",
            V_SKIPPED, "no effective parameters recorded on one side"))
    else:
        par_diffs = sorted(k for k in set(a_par) | set(b_par) if a_par.get(k) != b_par.get(k))
        shown = ", ".join(f"{k} {_param_value(a_par, k)}→{_param_value(b_par, k)}"
                          for k in par_diffs[:6])
        crit.append(_criterion(
            "sorter params", "the effective parameter dict", "exact",
            f"{len(a_par)} keys", f"{len(b_par)} keys",
            V_MATCH if not par_diffs else V_DIFFERS,
            "" if not par_diffs else "differs: " + shown
            + ("" if len(par_diffs) <= 6 else f", and {len(par_diffs) - 6} more")))

    # 3. probe geometry — the hash, not the label: a renamed profile with the
    #    same contacts is the same geometry, and vice versa.
    a_g, b_g = recorded.get("geometry_hash"), regenerated.get("geometry_hash")
    crit.append(_criterion(
        "probe geometry", "geometry hash (positions · shanks · wiring)", "exact",
        f"{recorded.get('probe_id') or '?'} / {a_g or '—'}",
        f"{regenerated.get('probe_id') or '?'} / {b_g or '—'}",
        V_SKIPPED if not a_g or not b_g else (V_MATCH if a_g == b_g else V_DIFFERS)))

    # 4. environment — a caveat, not a failure: a different SI version can change
    #    the answer legitimately, and the reader must be told which it was.
    a_env = {**(recorded.get("packages") or {}), "git": (recorded.get("git") or {}).get("sha")}
    b_env = {**(regenerated.get("packages") or {}), "git": (regenerated.get("git") or {}).get("sha")}
    env_diffs = [k for k in set(a_env) | set(b_env) if a_env.get(k) != b_env.get(k)]
    crit.append(_criterion(
        "environment", "package versions + repo git sha", "exact (a caveat, not a gate)",
        f"SI {a_env.get('spikeinterface', '?')} · git {str(a_env.get('git'))[:8]}",
        f"SI {b_env.get('spikeinterface', '?')} · git {str(b_env.get('git'))[:8]}",
        V_MATCH if not env_diffs else V_INFO,
        "" if not env_diffs else "differs: " + ", ".join(sorted(env_diffs))))

    # 5. noise floor — a property of the recording after bandpass + CMR, so it is
    #    the strongest single number here (and the ~4 uV double-scaling canary).
    a_n = ((recorded_summary or {}).get("noise_floor_uV") or {}).get("median")
    b_n = ((regenerated_summary or {}).get("noise_floor_uV") or {}).get("median")
    if isinstance(a_n, (int, float)) and isinstance(b_n, (int, float)):
        verdict = V_WITHIN if abs(a_n - b_n) <= NOISE_TOL_UV else V_OUTSIDE
        note = f"Δ {abs(a_n - b_n):.3f} µV"
    else:
        verdict, note = V_SKIPPED, "no summary.json on one side"
    crit.append(_criterion("noise floor (µV)", "median across channels",
                           f"±{NOISE_TOL_UV:g} µV absolute", _fmt(a_n, 3), _fmt(b_n, 3),
                           verdict, note))

    # 6. spike containment — the unit-blind reproduction check.
    delta_s = delta_ms / 1000.0
    if recorded_spikes is None or regenerated_spikes is None:
        crit.append(_criterion("spike containment", f"recorded spikes found again (±{delta_ms:g} ms)",
                               f"≥{CONTAINMENT_MIN:.0%} both ways", "—", "—", V_SKIPPED,
                               "a sorting could not be read"))
        fwd = back = None
    else:
        fwd = containment(recorded_spikes, regenerated_spikes, delta_s)
        back = containment(regenerated_spikes, recorded_spikes, delta_s)
        if len(recorded_spikes) == 0 and len(regenerated_spikes) == 0:
            # Containment is undefined on an empty train (NaN), and NaN reads as
            # outside tolerance — so two honest zero-unit runs used to be scored
            # NOT REGENERATED for identically finding nothing. Finding nothing
            # twice IS the recorded result reproduced.
            verdict, found, note = V_MATCH, "0 spikes", \
                "both sorts found no spikes — the empty result was reproduced"
        else:
            # BOTH directions gate. Forward alone passes a regeneration that
            # found every recorded spike AND a pile of new ones — the reverse
            # direction is the only thing that sees that. Measured, the two sit
            # in the same band (0.925–0.991 over six same-window pairs), so
            # requiring the smaller costs nothing a legitimate re-run needs.
            ok = fwd == fwd and back == back and min(fwd, back) >= CONTAINMENT_MIN
            verdict = V_WITHIN if ok else V_OUTSIDE
            found = f"{fwd:.1%} of them" if fwd == fwd else "—"
            note = (f"reverse containment {back:.1%} ({len(regenerated_spikes)} spikes)"
                    if back == back else "")
        crit.append(_criterion(
            "spike containment", f"recorded spikes found again (±{delta_ms:g} ms)",
            f"≥{CONTAINMENT_MIN:.0%} both ways", f"{len(recorded_spikes)} spikes",
            found, verdict, note))

    # 7. headline metrics — medians move as units split/merge, so relative.
    for key, label, digits in (("v_pp_uV", "V_pp median (µV)", 1), ("snr", "SNR median", 2)):
        a_v = ((recorded_summary or {}).get(key) or {}).get("median")
        b_v = ((regenerated_summary or {}).get(key) or {}).get("median")
        if isinstance(a_v, (int, float)) and isinstance(b_v, (int, float)) and a_v:
            rel = abs(b_v - a_v) / abs(a_v)
            crit.append(_criterion(label, "median over units",
                                   f"±{METRIC_REL_TOL:.0%} relative", _fmt(a_v, digits),
                                   _fmt(b_v, digits),
                                   V_WITHIN if rel <= METRIC_REL_TOL else V_OUTSIDE,
                                   f"Δ {rel:.1%}"))
        else:
            crit.append(_criterion(label, "median over units", f"±{METRIC_REL_TOL:.0%} relative",
                                   _fmt(a_v, digits), _fmt(b_v, digits), V_SKIPPED))

    a_y = (recorded_summary or {}).get("yield_pct")       # a plain percentage
    b_y = (regenerated_summary or {}).get("yield_pct")
    if isinstance(a_y, (int, float)) and isinstance(b_y, (int, float)):
        crit.append(_criterion("yield (%)", "electrodes that are a unit's peak channel",
                               f"±{YIELD_TOL_PP:g} percentage points", _fmt(a_y, 1), _fmt(b_y, 1),
                               V_WITHIN if abs(a_y - b_y) <= YIELD_TOL_PP else V_OUTSIDE,
                               f"Δ {abs(a_y - b_y):.1f} pp"))
    else:
        crit.append(_criterion("yield (%)", "electrodes that are a unit's peak channel",
                               f"±{YIELD_TOL_PP:g} percentage points", _fmt(a_y, 1), _fmt(b_y, 1),
                               V_SKIPPED))

    # 8. units — reported, never a criterion. This is the PRE1 evidence in force.
    det = recorded.get("determinism") or determinism_of(recorded.get("sorter", ""))
    crit.append(_criterion("unit count", "units in each sort", "NOT A CRITERION",
                           _fmt(recorded.get("n_units")), _fmt(regenerated.get("n_units")),
                           V_INFO, det.get("note", "")))

    failed = [c for c in crit if c["verdict"] in _FAILING]
    # Bit-identity means the trains ARE the same, sample for sample — not that
    # every spike found a partner inside a +/-0.4 ms window, which two different
    # sorts routinely do. Claiming it on containment alone would be the report
    # telling its strongest lie in its strongest words.
    # Two EMPTY trains are trivially equal spike for spike; saying "bit-identical
    # spike trains" about no spikes at all is the same overclaim in a quieter
    # form, so an empty pair regenerates without the superlative.
    identical = (recorded_spikes is not None and regenerated_spikes is not None
                 and len(recorded_spikes) > 0
                 and len(recorded_spikes) == len(regenerated_spikes)
                 and all(x == y for x, y in zip(recorded_spikes, regenerated_spikes)))
    if failed:
        verdict = "NOT REGENERATED"
    elif identical:
        verdict = "REGENERATED — BIT-IDENTICAL SPIKE TRAINS"
    elif any(c["verdict"] == V_INFO and c["name"] == "environment" for c in crit):
        verdict = "REGENERATED WITH CAVEATS"
    else:
        verdict = "REGENERATED"
    return {"verdict": verdict, "criteria": crit, "failed": [c["name"] for c in failed],
            "sorter": recorded.get("sorter"), "determinism": det,
            "recorded_run": recorded.get("run_id"), "regenerated_run": regenerated.get("run_id"),
            "containment": {"forward": fwd, "reverse": back, "delta_ms": delta_ms}}


def format_match_report(report: dict, *, recorded_dir=None, regenerated_dir=None) -> str:
    """The honest match report, as printed by ``runs.py regenerate``."""
    lines = [f"Regeneration match report — {report.get('sorter')}",
             f"  recorded    {report.get('recorded_run') or '?'}"
             + (f"   {recorded_dir}" if recorded_dir else ""),
             f"  regenerated {report.get('regenerated_run') or '?'}"
             + (f"   {regenerated_dir}" if regenerated_dir else ""), ""]
    head = ("criterion", "recorded", "regenerated", "tolerance", "verdict")
    rows = [(c["name"], str(c["recorded"]), str(c["regenerated"]), c["tolerance"], c["verdict"])
            for c in report["criteria"]]
    widths = [max(len(str(r[i])) for r in [head, *rows]) for i in range(5)]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    lines.append(fmt.format(*head))
    lines.append("  " + "  ".join("-" * w for w in widths))
    for c, row in zip(report["criteria"], rows):
        lines.append(fmt.format(*row).rstrip())
        if c["note"]:
            lines.append(" " * (widths[0] + 4) + f"↳ {c['note']}")
    lines += ["", f"  VERDICT: {report['verdict']}"]
    if report["failed"]:
        lines.append("  failed: " + ", ".join(report["failed"]))
    det = report.get("determinism") or {}
    if det.get("class") == "measured-stochastic":
        lines.append(f"  {report.get('sorter')} is measured NON-DETERMINISTIC here — "
                     f"{det.get('note')}")
    else:
        lines.append(f"  determinism: {det.get('class', 'unverified')} — {det.get('note', '')}")
    return "\n".join(lines)


def regenerate(sorter=None, run=None, config=None, root=None, outputs=None,
               out=None, stream=None) -> dict:
    """Re-run a sort from its record alone and compare. Returns the match report.

    Writes into ``outputs/<sorter>/regen/<id>/`` — never ``runs/`` — so checking
    a run can never change which run is current.
    """
    import sort_summary as _summary

    stream = stream if stream is not None else sys.stderr
    if config is None:
        paths = sort_paths(sorter, root, outputs, run=run)
        recorded = read_json(paths["run_info"])
        if not recorded:
            raise SystemExit(f"no run record for {sorter}"
                             + (f" run {run}" if run else " (nothing saved yet)"))
        config = config_from_record(recorded)
    else:
        sorter = config.get("sorter")
        # A config file names the run it came from, and THAT is what a re-run has
        # to be scored against — never whatever happens to be current, which is a
        # different sort entirely. A config with no source run, or one whose run
        # lives on another machine (it travelled through git), gets no comparison.
        want = run or config.get("from_run")
        paths = sort_paths(sorter, root, outputs, run=want)
        recorded = read_json(paths["run_info"]) if want else {}
    if not config.get("sorter"):
        raise SystemExit("config names no sorter")

    dest = Path(out) if out else (regen_dir(config["sorter"], root, outputs) / new_run_id())
    dest.mkdir(parents=True, exist_ok=True)
    params_file = dest / "params.json"
    params_file.write_text(json.dumps(config.get("params") or {}, indent=2), encoding="utf-8")
    argv = config_argv(config, dest, params_file=params_file)
    print(f"regenerating {config['sorter']} from "
          f"{config.get('from_run') or 'a config file'} → {dest}", file=stream, flush=True)
    print("$ " + " ".join(argv), file=stream, flush=True)
    # Inherit stdio: the child's own progress belongs on the terminal, and there
    # is nothing to capture (its record on disk is what we compare).
    rc = subprocess.run(argv).returncode
    if rc != 0:
        raise SystemExit(f"regeneration sort failed (rc {rc}) — see the output above")

    regenerated = read_json(dest / RUN_INFO_NAME)
    if not recorded:
        note = (f"this machine has no record for run {config.get('from_run')}"
                if config.get("from_run") else "the config names no source run")
        print(f"the sort ran ({dest}), but there is nothing to compare it against: "
              f"{note}.", file=stream, flush=True)
        return {"report": None, "config": config, "argv": argv, "out": dest,
                "recorded_dir": None, "rc": rc}
    report = compare_runs(
        recorded, regenerated,
        recorded_summary=_summary.load_summary(paths["out"]),
        regenerated_summary=_summary.load_summary(dest),
        recorded_spikes=pooled_spike_times(paths["analyzer"]),
        regenerated_spikes=pooled_spike_times(dest / "analyzer"),
    )
    # The regenerated sort is written with --output-dir, so it is outside the
    # store and carries no run id — name it by its directory instead of "?".
    report["regenerated_run"] = regenerated.get("run_id") or dest.name
    return {"report": report, "config": config, "argv": argv, "out": dest,
            "recorded_dir": paths["out"], "rc": rc}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_runs(sorter: str, root=None, outputs=None) -> None:
    runs = list_runs(sorter, root, outputs)
    dead = unfinished_runs(sorter, root, outputs)
    if not runs and not dead:
        return
    cur = resolve(sorter, root, outputs)
    if cur is None:
        print(f"{sorter}  (no finished run)")
    else:
        print(f"{sorter}  ({len(runs)} run(s); current: {cur['id']} via {cur['how']})")
    for r in runs:
        info = r["info"]
        eff = info.get("effective_seconds")
        span = f"{eff:.0f}s" if isinstance(eff, (int, float)) else "?"
        mark = "*" if cur and r["id"] == cur["id"] else " "
        kind = "smoke" if r["smoke"] else ("legacy" if r["legacy"] else "full")
        print(f"  {mark} {r['id']:<26} {kind:<6} {str(info.get('n_units', '?')):>3} units  "
              f"{span:>6}  {info.get('created', '?')}")
    # Corpses: directories from sorts that died before writing a record. Nothing
    # else names them, so without this line they accumulate unseen.
    for d in dead:
        print(f"  ! {d.name:<26} unfinished — the sort died before writing its record; "
              f"kept for {d.name}/sorter_output")


def main() -> int:
    import argparse

    bio.use_utf8_stdout()   # this CLI prints ✓ ↳ µ Δ ≥ ±; a redirected run on a
                            # Windows console would die on the code page instead
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="every saved run, newest first")
    p_list.add_argument("--sorter", default=None)

    p_show = sub.add_parser("show", help="one run's record")
    p_show.add_argument("--sorter", required=True)
    p_show.add_argument("--run", default=None, help="run id (default: the current run)")

    p_cur = sub.add_parser("current", help="re-point the current run")
    p_cur.add_argument("--sorter", required=True)
    p_cur.add_argument("--run", required=True)
    p_cur.add_argument("--force", action="store_true",
                       help="allow a smoke run to displace a full run")

    p_reg = sub.add_parser("regenerate", help="re-run a sort from its record + match report")
    p_reg.add_argument("--sorter", default=None)
    p_reg.add_argument("--run", default=None, help="run id (default: the current run)")
    p_reg.add_argument("--config", default=None, help="a config file from `runs.py export`")
    p_reg.add_argument("--out", default=None, help="where to write the regenerated sort")

    p_exp = sub.add_parser("export", help="write the committable config for a run")
    p_exp.add_argument("--sorter", required=True)
    p_exp.add_argument("--run", default=None)
    p_exp.add_argument("--out", default=None, help="config file to write (default: stdout)")

    args = parser.parse_args()
    if args.cmd in (None, "list"):
        if getattr(args, "sorter", None):
            names = [args.sorter]
        else:
            # Sorters with a resolvable run PLUS any whose only runs are corpses —
            # a sorter that has never finished a sort must still be listable.
            base = outputs_dir()
            names = sorted(set(saved_sorters()) | {
                p.name for p in (sorted(base.iterdir()) if base.is_dir() else [])
                if p.is_dir() and unfinished_runs(p.name)})
        if not names:
            print("no saved sorts yet — run: uv run python scripts/run_sorting.py")
            return 0
        for name in names:
            _print_runs(name)
        return 0

    if args.cmd == "show":
        paths = sort_paths(args.sorter, run=args.run)
        info = read_json(paths["run_info"])
        if not info:
            print(f"no run record at {paths['run_info']}")
            return 1
        print(json.dumps(info, indent=2))
        return 0

    if args.cmd == "current":
        ok, msg = set_current(args.sorter, args.run, force=args.force)
        print(("✓ " if ok else "! ") + msg)
        return 0 if ok else 1

    if args.cmd == "export":
        info = read_json(sort_paths(args.sorter, run=args.run)["run_info"])
        if not info:
            print(f"no run record for {args.sorter}")
            return 1
        text = json.dumps(config_from_record(info), indent=2)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
        return 0

    if args.cmd == "regenerate":
        config = read_json(args.config) if args.config else None
        sorter = args.sorter or (config or {}).get("sorter")
        if not sorter:
            print("regenerate needs --sorter or --config")
            return 2
        result = regenerate(sorter=sorter, run=args.run, config=config, out=args.out)
        if result["report"] is None:      # ran, but had nothing to compare against
            return 0
        print()
        print(format_match_report(result["report"], recorded_dir=result["recorded_dir"],
                                  regenerated_dir=result["out"]))
        return 0 if result["report"]["verdict"].startswith("REGENERATED") else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
