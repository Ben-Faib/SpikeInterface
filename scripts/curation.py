"""The curation record: decisions saved, applied to a curated Sorting, re-scored.

    uv run python scripts/curation.py show  --sorter tridesclous2
    uv run python scripts/curation.py label --sorter tridesclous2 --unit 15 --label noise
    uv run python scripts/curation.py merge --sorter tridesclous2 --units 15,16
    uv run python scripts/curation.py split --sorter tridesclous2 --unit 4 --unit 8
    uv run python scripts/curation.py apply --sorter tridesclous2

Single source of truth for **what was decided about a sort and what that
produced**. A sort finds candidate units; the decisions a human (or a scripted
method) makes about them — merge, split, label — live here, in a record beside
the sort, and are replayed deterministically to build the curated output.

    outputs/<sorter>/                     the RAW sort (never mutated — the audit trail)
        sorting/ analyzer/ run_info.json summary.json quality_metrics.csv
        curation.json                     THE RECORD (this module owns it)
        curated/                          the applied result, a first-class output
            sorting/ analyzer/ run_info.json summary.json quality_metrics.csv

``sort_paths()`` is the ONE place any of those paths is resolved — W2's versioned
run store re-plumbs that function and nothing else.

The record
----------
``curation.json`` wraps SpikeInterface's own curation-format dict (the
interchange format ``validate_curation_dict`` / ``apply_curation`` speak) in a
sidecar that adds the provenance SI's format does not carry: which sort it
curates, when each decision was taken, and by what method with what parameters.

    {
      "kind": "spikeinterface-workbench-curation",
      "schema_version": "1",
      "created": "2026-08-18T21:40:11",     # record created
      "updated": "2026-08-18T21:52:03",     # last decision written
      "curates": {                          # WHICH sort this record curates
        "sorter": "tridesclous2",
        "output_dir": "outputs/tridesclous2",        # repo-relative, POSIX
        "run": {"created": ..., "sorter": ..., "n_units": 17, "si_version": ...,
                "probe": ..., "effective_seconds": ..., "total_seconds": ...}
      },                  # ^ the ANCHOR. Unit ids are not stable across re-sorts
                          #   (tridesclous2 is non-deterministic on this recording,
                          #   and run_sorting overwrites outputs/<sorter>/ in place),
                          #   so apply REFUSES a record whose anchor no longer
                          #   matches the sort on disk rather than curating the
                          #   wrong units quietly.
      "tools": {"python": "3.12.9", "spikeinterface": "0.104.3",
                "workbench_schema": "1"},
      "curation": { ... SpikeInterface curation-format dict ... },
      "decisions": [                        # one entry per decision, the audit trail
        {"id": "split-4", "type": "split", "units": [4], "at": "2026-08-18T21:45:02",
         "method": "kmeans", "params": {"features": "amplitude+pca", "n_pcs": 3,
                                        "n_parts": 2, "seed": 0, "peak_channel": "5"},
         "detail": {"n_spikes": 5961, "sizes": [3717, 2244]}, "note": ""}
      ]
    }

The embedded ``curation`` block is SI's format version "2":

    {"format_version": "2",
     "unit_ids": [...],                              # the RAW sort's unit ids
     "label_definitions": {"quality": {"label_options": ["good", "MUA", "noise",
                                       "unsure"], "exclusive": true}},
     "manual_labels": [{"unit_id": 15, "labels": {"quality": ["noise"]}}],
     "merges":  [{"unit_ids": [15, 16]}],
     "splits":  [{"unit_id": 4, "mode": "indices",
                  "indices": [[0, 3, 7, ...], [1, 2, 4, ...]]}],
     "removed": []}

Split indices are positions **within that unit's own spike train** (0..n-1), so
the record is a literal partition, not a recipe: applying it re-clusters nothing.
A scripted split writes the partition its method produced *and* the method and
parameters that produced it, so the decision is reproducible AND auditable; a
by-hand split (a future TUI/Phy slice) writes the same shape with
``"method": "manual"``. Removals are part of SI's format and are applied if
present; this CLI does not write them (label a unit ``noise`` instead).

Reading is pure Python
----------------------
Everything above the ``propose_splits`` / ``apply_record`` line imports **no
SpikeInterface** — ``load_record``, ``counts``, ``provenance_line``, ``state``
and ``sort_paths`` are json + pathlib only, so the menu's view process (and the
coming TUI triage slice) can read curation state without paying for SI.
``propose_splits`` and ``apply_record`` import SI inside the function.

API
---
Paths and state (pure):
    sort_paths(sorter, root=None) -> dict     every path for one sorter's run
    load_record(sorter=..., root=..., path=...) -> dict | None
    save_record(record, path) -> Path
    new_record(sorter, unit_ids, run=None, root=None) -> dict
    counts(record) -> {"total", "splits", "merges", "labels", "removed"}
    provenance_line(record, curated=True, has_curated=False) -> str
                                               the honest-surface sentence
    state(sorter, root=None) -> dict           what the surfaces need to be honest:
        {"has_record", "has_curated", "counts", "line", "stale", "stale_reason",
         "record_path", "curated_dir", "updated", "curated_units"}
    stale_reason(curated_run, record, raw_run) -> str   why a curated result no
                                               longer describes what is on disk
    structural_errors(record) -> list[str]     schema check without SI

Decisions (pure record mutation; each appends to ``decisions``):
    add_label(record, unit_id, label, note="")
    add_merge(record, unit_ids, note="")
    add_split(record, unit_id, indices, method, params, detail=None, note="")

SpikeInterface-backed:
    validate(record)                           SI's validate_curation_dict
    propose_splits(analyzer, unit_ids, ...)    -> {unit_id: (indices, params, detail)}
    apply_record(record, root=None, ...)       -> {"out", "n_units", ...}

``propose_splits`` partitions a unit's spikes by k-means on per-spike features —
spike amplitude and/or the top principal components on the unit's peak channel,
z-scored, k-means++ with a fixed seed (deterministic). It is the *scientific*
half: it decides where the split goes. ``apply_record`` never calls it — apply is
replay of the indices already in the record.

``apply_record`` reads the RAW saved Sorting, applies the record with SI's
``apply_curation``, saves ``curated/sorting``, then builds ``curated/analyzer``
and re-scores it through the existing owners: ``sort_summary`` computes the six
headline metrics and the quality rule. Quality metrics are non-fatal exactly as
in the sort pipeline — the curated Sorting is saved *before* metrics run, and a
metrics failure deletes the half-built ``analyzer/``, ``quality_metrics.csv`` and
``summary.*`` so no surface reads stale derived data.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402  (REPO_ROOT only — no SpikeInterface)
import sort_summary as _summary  # noqa: E402  (the metrics + quality-rule owner)

SCHEMA_VERSION = "1"
KIND = "spikeinterface-workbench-curation"
RECORD_NAME = "curation.json"
CURATED_DIRNAME = "curated"
# SpikeInterface's curation-format version this module writes (0.104 accepts 1|2).
CURATION_FORMAT_VERSION = "2"

# The one label category the workbench writes. Exclusive: a unit carries exactly
# one of these. "MUA" = multi-unit activity, "unsure" = looked at, not decided.
QUALITY_KEY = "quality"
QUALITY_OPTIONS = ("good", "MUA", "noise", "unsure")
LABEL_DEFINITIONS = {QUALITY_KEY: {"label_options": list(QUALITY_OPTIONS),
                                   "exclusive": True}}

# Defaults for the scripted split. Chosen once and applied to every unit — a
# per-unit tuning would make the record a story about the answer, not a method.
SPLIT_METHOD = "kmeans"
SPLIT_FEATURES = "amplitude+pca"     # also accepted: "amplitude", "pca"
SPLIT_N_PCS = 3                      # top N principal components, on the peak channel
SPLIT_N_PARTS = 2
SPLIT_SEED = 0


# --------------------------------------------------------------------------- #
# Paths — the ONE resolver (W2's versioned run store swaps this function)
# --------------------------------------------------------------------------- #
def sort_paths(sorter: str, root=None) -> dict:
    """Every path the curation lifecycle needs for one sorter's saved run.

    ``root`` defaults to the repo root (tests pass a tmp dir). Nothing else in
    this module — or in the surfaces that read curation state — builds an
    ``outputs/<sorter>/...`` path by hand.
    """
    base = Path(root) if root is not None else bio.REPO_ROOT
    out = base / "outputs" / sorter
    curated = out / CURATED_DIRNAME
    return {
        "root": base,
        "out": out,
        "sorting": out / "sorting",
        "analyzer": out / "analyzer",
        "run_info": out / "run_info.json",
        "summary": out / "summary.json",
        "record": out / RECORD_NAME,
        "curated": curated,
        "curated_sorting": curated / "sorting",
        "curated_analyzer": curated / "analyzer",
        "curated_run_info": curated / "run_info.json",
        "curated_metrics": curated / "quality_metrics.csv",
    }


def preferred_analyzer(sorter: str, root=None) -> "tuple[Path, bool]":
    """(analyzer dir to show, is_curated) — curated wins when it exists.

    The rule every surface follows: if a curated analyzer was built, that is the
    result, and the surface says so; otherwise the raw sort is the result.
    """
    p = sort_paths(sorter, root)
    if p["curated_analyzer"].is_dir():
        return p["curated_analyzer"], True
    return p["analyzer"], False


# --------------------------------------------------------------------------- #
# The record — construction and decisions (pure Python)
# --------------------------------------------------------------------------- #
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tool_versions() -> dict:
    """Versions at write time. SpikeInterface's is read from its distribution
    metadata, not by importing it — the record stays writable from the view."""
    import platform
    from importlib import metadata

    try:
        si_version = metadata.version("spikeinterface")
    except Exception:  # noqa: BLE001 - not installed / odd env
        si_version = None
    return {"python": platform.python_version(), "spikeinterface": si_version,
            "workbench_schema": SCHEMA_VERSION}


def _run_identity(run_info: dict) -> dict:
    """The subset of run_info.json that identifies the sort being curated."""
    keys = ("created", "sorter", "n_units", "si_version", "probe",
            "effective_seconds", "total_seconds")
    return {k: run_info.get(k) for k in keys}


def read_run_info(sorter: str, root=None) -> dict:
    """outputs/<sorter>/run_info.json; {} when absent/unreadable. No SI import."""
    try:
        return json.loads(sort_paths(sorter, root)["run_info"].read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return {}


def new_record(sorter: str, unit_ids, run=None, root=None) -> dict:
    """An empty record for ``sorter``'s saved sort — no decisions yet."""
    out = sort_paths(sorter, root)["out"]
    try:
        rel = out.relative_to(sort_paths(sorter, root)["root"]).as_posix()
    except ValueError:  # out lives outside the root (explicit --output-dir)
        rel = out.as_posix()
    run = run if run is not None else read_run_info(sorter, root)
    now = _now()
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "created": now,
        "updated": now,
        "curates": {"sorter": sorter, "output_dir": rel, "run": _run_identity(run)},
        "tools": _tool_versions(),
        "curation": {
            "format_version": CURATION_FORMAT_VERSION,
            "unit_ids": [_plain(u) for u in unit_ids],
            "label_definitions": {k: dict(v) for k, v in LABEL_DEFINITIONS.items()},
            "manual_labels": [],
            "merges": [],
            "splits": [],
            "removed": [],
        },
        "decisions": [],
    }


def _plain(value):
    """NumPy scalar / str-like -> a JSON-safe int or str (unit ids travel as both)."""
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, str)):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _touch(record: dict) -> None:
    record["updated"] = _now()


def _decide(record: dict, kind: str, units, method: str, params: dict,
            detail=None, note: str = "") -> dict:
    """Append one provenance entry and return it."""
    entry = {"id": f"{kind}-{'+'.join(str(u) for u in units)}", "type": kind,
             "units": [_plain(u) for u in units], "at": _now(),
             "method": method, "params": dict(params or {}),
             "detail": dict(detail or {}), "note": note}
    record.setdefault("decisions", []).append(entry)
    _touch(record)
    return entry


def add_label(record: dict, unit_id, label: str, note: str = "") -> dict:
    """Label one unit good/MUA/noise/unsure (replaces that unit's previous label)."""
    if label not in QUALITY_OPTIONS:
        raise ValueError(f"unknown label {label!r} — one of {list(QUALITY_OPTIONS)}")
    uid = _plain(unit_id)
    _require_unit(record, uid)
    labels = [m for m in record["curation"]["manual_labels"] if m["unit_id"] != uid]
    labels.append({"unit_id": uid, "labels": {QUALITY_KEY: [label]}})
    record["curation"]["manual_labels"] = labels
    _decide(record, "label", [uid], "manual", {"label": label}, note=note)
    return record


def add_merge(record: dict, unit_ids, note: str = "") -> dict:
    """Record a merge group (>= 2 units of the raw sort)."""
    ids = [_plain(u) for u in unit_ids]
    if len(ids) < 2:
        raise ValueError("a merge needs at least two units")
    for uid in ids:
        _require_unit(record, uid)
    record["curation"]["merges"].append({"unit_ids": ids})
    _decide(record, "merge", ids, "manual", {}, note=note)
    return record


def add_split(record: dict, unit_id, indices, method: str, params: dict,
              detail=None, note: str = "") -> dict:
    """Record a split of one unit as an explicit spike-index partition.

    ``indices`` is a list of lists of spike positions *within that unit's spike
    train*. ``method``/``params`` say how the partition was produced (the audit
    trail); applying the record replays the indices and re-clusters nothing.
    """
    uid = _plain(unit_id)
    _require_unit(record, uid)
    parts = [[int(i) for i in part] for part in indices]
    if len(parts) < 2 or any(len(p) == 0 for p in parts):
        raise ValueError("a split needs at least two non-empty parts")
    record["curation"]["splits"] = [
        s for s in record["curation"]["splits"] if s["unit_id"] != uid]
    record["curation"]["splits"].append(
        {"unit_id": uid, "mode": "indices", "indices": parts})
    det = dict(detail or {})
    det.setdefault("sizes", [len(p) for p in parts])
    _decide(record, "split", [uid], method, params, det, note=note)
    return record


def _require_unit(record: dict, unit_id) -> None:
    if unit_id not in record["curation"]["unit_ids"]:
        raise ValueError(f"unit {unit_id!r} is not in this sort "
                         f"({record['curation']['unit_ids']})")


# --------------------------------------------------------------------------- #
# Reading + honest-surface text (pure Python — no SpikeInterface)
# --------------------------------------------------------------------------- #
def load_record(sorter: str = None, root=None, path=None) -> "dict | None":
    """Read a record by sorter (or an explicit path). None if absent/unreadable."""
    p = Path(path) if path is not None else sort_paths(sorter, root)["record"]
    try:
        record = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - absent / malformed -> caller degrades
        return None
    return record if isinstance(record, dict) else None


def save_record(record: dict, path) -> Path:
    """Write the record (pretty JSON, UTF-8). Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def counts(record: "dict | None") -> dict:
    """{total, splits, merges, labels, removed} for a record (zeros for None)."""
    cur = (record or {}).get("curation", {}) if isinstance(record, dict) else {}
    c = {"splits": len(cur.get("splits") or []),
         "merges": len(cur.get("merges") or []),
         "labels": len(cur.get("manual_labels") or []),
         "removed": len(cur.get("removed") or [])}
    c["total"] = c["splits"] + c["merges"] + c["labels"] + c["removed"]
    return c


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def provenance_line(record: "dict | None", curated: bool = True,
                    has_curated: bool = False) -> str:
    """The one sentence every surface uses to say what it is showing.

    Curated:  "curated from the tridesclous2 run (sorted 2026-08-18 21:15),
               4 decisions (3 splits, 0 merges, 1 label), 2026-08-18 21:52"
    Raw:      "raw tridesclous2 sorter output — no curation applied"
              "... — 4 decisions recorded but not applied"        (record, nothing built)
              "... — a curated result exists (4 decisions) and is not shown here"
                                                                 (``has_curated``)
    """
    if not record:
        return "raw sorter output — no curation applied"
    sorter = record.get("curates", {}).get("sorter") or "sorter"
    run_created = str(record.get("curates", {}).get("run", {}).get("created") or "")
    run_created = run_created.replace("T", " ")[:16]
    c = counts(record)
    parts = (f"{_plural(c['splits'], 'split')}, {_plural(c['merges'], 'merge')}, "
             f"{_plural(c['labels'], 'label')}")
    if c["removed"]:
        parts += f", {_plural(c['removed'], 'removal')}"
    when = str(record.get("updated") or "").replace("T", " ")[:16]
    if not curated:
        if c["total"] == 0:
            return f"raw {sorter} sorter output — no curation applied"
        if has_curated:
            return (f"raw {sorter} sorter output — a curated result exists "
                    f"({_plural(c['total'], 'decision')}) and is not shown here")
        return (f"raw {sorter} sorter output — {_plural(c['total'], 'decision')} "
                f"recorded but not applied")
    run_bit = f" (sorted {run_created})" if run_created else ""
    return (f"curated from the {sorter} run{run_bit}, {_plural(c['total'], 'decision')} "
            f"({parts}), {when}")


def stale_reason(curated_run: dict, record: "dict | None", raw_run: dict) -> str:
    """Why a curated result no longer describes what is on disk ("" when it does).

    Two ways it goes stale: the record gained decisions after it was applied, or
    the raw sort was re-run underneath it (a re-sort renumbers units, so the
    curated result then describes units that no longer exist).
    """
    curated_run = curated_run or {}
    if record and curated_run.get("curation_updated") \
            and curated_run["curation_updated"] != record.get("updated"):
        return "the curation record has new decisions since it was applied"
    anchor = curated_run.get("curated_from_run")
    if anchor and raw_run and anchor != _run_identity(raw_run):
        return "the raw sort was re-run after this curated result was built"
    return ""


def state(sorter: str, root=None) -> dict:
    """What a surface needs to be honest about curated-vs-raw. No SI import.

    ``stale`` is True when the record changed after the curated output was built
    (the curated result no longer reflects every recorded decision).
    """
    p = sort_paths(sorter, root)
    record = load_record(sorter, root)
    has_curated = p["curated_analyzer"].is_dir()
    curated_run = {}
    if has_curated:
        try:
            curated_run = json.loads(p["curated_run_info"].read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - provenance is best-effort
            curated_run = {}
    reason = (stale_reason(curated_run, record, read_run_info(sorter, root))
              if has_curated else "")
    return {
        "sorter": sorter,
        "has_record": record is not None,
        "has_curated": has_curated,
        "counts": counts(record),
        "line": provenance_line(record, curated=has_curated, has_curated=has_curated),
        "stale": bool(reason),
        "stale_reason": reason,
        "record_path": str(p["record"]),
        "curated_dir": str(p["curated"]),
        "updated": (record or {}).get("updated"),
        "curated_units": curated_run.get("n_units"),
    }


def structural_errors(record: "dict | None") -> list:
    """Schema problems in a record, as plain sentences. Pure — no SI import.

    Catches the shape mistakes (wrong kind, missing curation block, a decision
    naming a unit the sort never had); SI's ``validate_curation_dict`` — run by
    ``validate()`` and by ``apply_record`` — is the authority on the embedded
    curation dict itself.
    """
    errs = []
    if not isinstance(record, dict):
        return ["not a curation record (expected a JSON object)"]
    if record.get("kind") != KIND:
        errs.append(f"kind is {record.get('kind')!r}, expected {KIND!r}")
    if record.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version {record.get('schema_version')!r} "
                    f"(this build writes {SCHEMA_VERSION!r})")
    cur = record.get("curation")
    if not isinstance(cur, dict):
        return errs + ["no 'curation' block"]
    unit_ids = cur.get("unit_ids")
    if not isinstance(unit_ids, list) or not unit_ids:
        return errs + ["'curation.unit_ids' is missing or empty"]
    known = set(unit_ids)
    for m in cur.get("manual_labels") or []:
        if m.get("unit_id") not in known:
            errs.append(f"label names unit {m.get('unit_id')!r}, not in this sort")
    for m in cur.get("merges") or []:
        ids = m.get("unit_ids") if isinstance(m, dict) else m
        for uid in ids or []:
            if uid not in known:
                errs.append(f"merge names unit {uid!r}, not in this sort")
    for s in cur.get("splits") or []:
        if s.get("unit_id") not in known:
            errs.append(f"split names unit {s.get('unit_id')!r}, not in this sort")
        parts = s.get("indices") or []
        if len(parts) < 2:
            errs.append(f"split of unit {s.get('unit_id')!r} has fewer than two parts")
        flat = [i for part in parts for i in part]
        if len(flat) != len(set(flat)):
            errs.append(f"split of unit {s.get('unit_id')!r} repeats a spike index")
    return errs


def unit_ids_of(sorter: str, root=None) -> list:
    """The saved sort's unit ids. Pure when summary.json is present (it names
    every unit); falls back to loading the Sorting with SpikeInterface."""
    summary = _summary.load_summary(sort_paths(sorter, root)["out"])
    if summary and summary.get("per_unit"):
        return [p["unit"] for p in summary["per_unit"]]
    import spikeinterface.full as si

    sorting = si.load(sort_paths(sorter, root)["sorting"])
    return [_plain(u) for u in sorting.get_unit_ids()]


def open_record(sorter: str, root=None) -> dict:
    """The sorter's record, created (empty) from the saved sort if it has none."""
    record = load_record(sorter, root)
    if record is None:
        record = new_record(sorter, unit_ids_of(sorter, root), root=root)
    return record


# --------------------------------------------------------------------------- #
# SpikeInterface-backed: validation, the scripted split, apply
# --------------------------------------------------------------------------- #
def validate(record: dict) -> None:
    """Raise unless the record is structurally sound AND SI accepts its curation
    dict (``validate_curation_dict``)."""
    errs = structural_errors(record)
    if errs:
        raise ValueError("invalid curation record: " + "; ".join(errs))
    from spikeinterface.curation import validate_curation_dict

    validate_curation_dict(record["curation"])


def _peak_channel_index(analyzer, unit_id) -> int:
    """Index of the unit's best (max peak-to-peak template) channel."""
    import numpy as np

    unit_ids = list(analyzer.unit_ids)
    templates = analyzer.get_extension("templates").get_data()
    return int(np.argmax(np.ptp(templates[unit_ids.index(unit_id)], axis=0)))


def propose_splits(analyzer, unit_ids, *, n_parts: int = SPLIT_N_PARTS,
                   features: str = SPLIT_FEATURES, n_pcs: int = SPLIT_N_PCS,
                   seed: int = SPLIT_SEED, verbose: bool = False) -> dict:
    """Partition each unit's spikes by k-means on per-spike features.

    Features (``features``): ``amplitude`` = the spike-amplitude extension (one
    value per spike, already in µV via the analyzer); ``pca`` = the top ``n_pcs``
    principal components on the unit's peak channel, projected for EVERY spike
    (the saved PCA extension only holds the random-spikes subset, so this runs
    ``run_for_all_spikes`` once for all requested units, ~13 s on this
    recording); ``amplitude+pca`` = both. Columns are z-scored, then
    ``scipy.cluster.vq.kmeans2`` with k-means++ init and a fixed ``seed`` — the
    same inputs always give the same partition. Parts come back ordered by
    descending mean |amplitude|, so part 0 is the larger-amplitude cluster.

    Returns ``{unit_id: (indices, params, detail)}`` ready for ``add_split``.
    """
    import tempfile

    import numpy as np
    from scipy.cluster.vq import kmeans2

    if features not in ("amplitude", "pca", "amplitude+pca"):
        raise ValueError(f"unknown features {features!r} — one of "
                         "'amplitude', 'pca', 'amplitude+pca'")
    sorting = analyzer.sorting
    all_ids = list(sorting.unit_ids)
    spikes = sorting.to_spike_vector()
    amps = None
    if "amplitude" in features:
        ext = analyzer.get_extension("spike_amplitudes")
        if ext is None:
            raise RuntimeError("this sort has no spike_amplitudes extension — "
                               "re-run the sort, or split with --features pca")
        amps = np.asarray(ext.get_data(), dtype=float)

    projections = None
    tmpdir = None
    if "pca" in features:
        pc_ext = analyzer.get_extension("principal_components")
        if pc_ext is None:
            raise RuntimeError("this sort has no principal_components extension — "
                               "re-run the sort, or split with --features amplitude")
        tmpdir = tempfile.TemporaryDirectory()
        npy = Path(tmpdir.name) / "all_spike_pcs.npy"
        if verbose:
            print(f"projecting all {len(spikes)} spikes on the saved PCA model …")
        pc_ext.run_for_all_spikes(npy, n_jobs=1)
        # Read it whole rather than mmap: a live memory-map would hold the file
        # open and Windows refuses to delete the temp dir under an open handle.
        projections = np.load(npy)

    out = {}
    try:
        for unit_id in unit_ids:
            uid = _plain(unit_id)
            index = all_ids.index(unit_id) if unit_id in all_ids else all_ids.index(uid)
            mask = spikes["unit_index"] == index
            n_spikes = int(mask.sum())
            if n_spikes < n_parts * 2:
                raise ValueError(f"unit {uid} has {n_spikes} spikes — too few to "
                                 f"split into {n_parts}")
            peak = _peak_channel_index(analyzer, all_ids[index])
            cols, names = [], []
            if amps is not None:
                cols.append(amps[mask])
                names.append("amplitude")
            if projections is not None:
                take = min(n_pcs, projections.shape[1])
                for c in range(take):
                    cols.append(np.asarray(projections[mask][:, c, peak], dtype=float))
                    names.append(f"pc{c}@peak")
            X = np.column_stack(cols)
            Xz = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-12)
            _centroids, labels = kmeans2(Xz, n_parts, minit="++", seed=seed)
            parts = [np.flatnonzero(labels == k) for k in range(n_parts)]
            if any(len(p) == 0 for p in parts):
                raise ValueError(f"unit {uid}: k-means returned an empty cluster — "
                                 "these spikes do not separate into "
                                 f"{n_parts} groups")
            # Deterministic part order: biggest mean |amplitude| first (falls back
            # to the first feature column when amplitudes were not used).
            key_col = X[:, 0]
            parts.sort(key=lambda idx: -float(np.mean(np.abs(key_col[idx]))))
            indices = [[int(i) for i in part] for part in parts]
            params = {"features": features, "n_pcs": (n_pcs if projections is not None
                                                      else 0),
                      "n_parts": n_parts, "seed": seed,
                      "peak_channel": str(analyzer.channel_ids[peak]),
                      "feature_columns": names}
            detail = {"n_spikes": n_spikes, "sizes": [len(p) for p in indices],
                      "mean_amplitude": [round(float(np.mean(key_col[p])), 3)
                                         for p in parts]}
            out[uid] = (indices, params, detail)
            if verbose:
                print(f"unit {uid}: {n_spikes} spikes -> "
                      f"{' + '.join(str(len(p)) for p in indices)} "
                      f"(peak channel {params['peak_channel']})")
    finally:
        if tmpdir is not None:
            projections = None
            tmpdir.cleanup()
    return out


def _check_run_identity(record: dict, sorter: str, root=None) -> None:
    """Refuse to apply a record whose sort is not the sort it was written against.

    **Unit ids are not stable across re-sorts here** — tridesclous2 is
    non-deterministic on this recording (repeat full runs have returned 14, 16, 17
    and 18 units), and run_sorting overwrites outputs/<sorter>/ in place. So a
    record replayed onto a different sort would merge, split and label the wrong
    units, quietly. The record's ``curates.run`` block is the anchor: sorter, the
    run's created timestamp, its unit count and its effective window all have to
    match the sort on disk.
    """
    want = record.get("curates", {}).get("run", {})
    have = _run_identity(read_run_info(sorter, root))
    mismatch = []
    for key, label in (("sorter", "sorter"), ("created", "sorted at"),
                       ("n_units", "units"), ("effective_seconds", "window (s)")):
        a, b = want.get(key), have.get(key)
        if a is not None and b is not None and a != b:
            mismatch.append(f"{label}: record {a!r}, on disk {b!r}")
    if not mismatch:
        return
    raise RuntimeError(
        f"this curation record was written against a different {sorter} sort — "
        + "; ".join(mismatch)
        + ". Unit ids are not stable across re-sorts, so replaying these decisions "
          "would curate the wrong units. Next step: re-run the comparison against "
          "this sort and write a fresh record (curation.py split/label/merge on the "
          f"sort now in outputs/{sorter}/), or restore the sort the record was made "
          "on. The old record is not deleted — it stays as the audit trail of what "
          "was decided about that run.")


def apply_record(record: dict, root=None, *, out_dir=None, verbose: bool = True,
                 n_jobs: int = 1) -> dict:
    """Apply a validated record to the RAW saved Sorting; write outputs/<sorter>/curated/.

    The raw sort is read, never written. Produces ``curated/sorting`` (saved
    first — the units are the result), then ``curated/analyzer`` with the same
    extensions the sort computes, ``quality_metrics.csv``, ``summary.json``/``.csv``
    via ``sort_summary``, and ``run_info.json`` naming the record it replayed.

    A metrics failure is NON-FATAL: the curated Sorting stays, the half-built
    analyzer/metrics/summary are removed, and the returned dict carries a
    ``metrics_note``.
    """
    import spikeinterface.full as si
    from spikeinterface.curation import apply_curation

    import run_sorting as _sort  # the sort pipeline's extension lists + helpers

    sorter = record["curates"]["sorter"]
    paths = sort_paths(sorter, root)
    validate(record)
    _check_run_identity(record, sorter, root)

    si.set_global_job_kwargs(n_jobs=n_jobs, progress_bar=verbose)
    raw_sorting = si.load(paths["sorting"])
    raw_analyzer = si.load_sorting_analyzer(paths["analyzer"])
    recording = raw_analyzer.recording
    if recording is None:
        raise RuntimeError(
            f"the saved {sorter} analyzer cannot reach its recording, so a curated "
            "analyzer cannot be built on the same preprocessed signal — check that "
            "the raw data is where it was at sort time.")

    if verbose:
        c = counts(record)
        print(f"applying {c['total']} decision(s) to the saved {sorter} sort "
              f"({len(raw_sorting.unit_ids)} units): {c['splits']} split(s), "
              f"{c['merges']} merge(s), {c['labels']} label(s)")
    curated = apply_curation(raw_sorting, record["curation"])
    n_units = len(curated.unit_ids)

    out = Path(out_dir) if out_dir else paths["curated"]
    out.mkdir(parents=True, exist_ok=True)
    _sort._robust_rmtree(out / "sorting")
    curated = curated.save(folder=str(out / "sorting"), overwrite=True)
    if verbose:
        print(f"curated sorting saved: {n_units} units -> {out / 'sorting'}")

    summary = None
    n_high_quality = None
    metrics_note = None
    try:
        _sort._robust_rmtree(out / "analyzer")
        analyzer = si.create_sorting_analyzer(
            curated, recording, folder=str(out / "analyzer"),
            format="binary_folder", overwrite=True, sparse=False)
        for ext in ("random_spikes", "waveforms", "templates", "noise_levels"):
            analyzer.compute(ext)
        deps_ok = set()
        for ext in _sort._METRIC_DEP_EXTENSIONS:
            try:
                analyzer.compute(ext)
                deps_ok.add(ext)
            except Exception as e:  # noqa: BLE001 - drop dependent metrics, keep the rest
                print(f"  skipped {ext} ({type(e).__name__}) — its metrics dropped")
        metric_names = ["firing_rate", "snr", "isi_violation", "presence_ratio"]
        if "spike_amplitudes" in deps_ok:
            metric_names += ["amplitude_cutoff", "amplitude_median"]
        if "principal_components" in deps_ok:
            metric_names += ["mahalanobis", "d_prime", "nearest_neighbor"]
        analyzer.compute("quality_metrics", metric_names=metric_names)
        qm = analyzer.get_extension("quality_metrics").get_data()
        qm.to_csv(out / "quality_metrics.csv")
        for ext in _sort._CURATION_EXTENSIONS:
            try:
                analyzer.compute(ext)
            except Exception as e:  # noqa: BLE001 - optional inspector data
                print(f"  skipped {ext} ({type(e).__name__})")
        _n_total, n_high_quality, _rule, _unknown = _sort._quality_summary(qm)
        summary = _summary.compute_summary(analyzer, sorter=sorter)
        _summary.write_summary(summary, out)
        if verbose:
            for line in _summary.format_card(summary):
                print("  " + line)
    except Exception as e:  # noqa: BLE001 - metrics are non-fatal; the units are saved
        import traceback

        traceback.print_exc()
        metrics_note = f"quality metrics failed: {type(e).__name__}: {e}"
        print(f"! {metrics_note} — the curated sorting itself is saved.")
        # Never leave half-built derived data for a surface to read as this result.
        _sort._robust_rmtree(out / "analyzer")
        for stale in ("quality_metrics.csv", "summary.json", "summary.csv"):
            (out / stale).unlink(missing_ok=True)

    raw_info = read_run_info(sorter, root)
    c = counts(record)
    info = {
        "created": _now(),
        "command": "curation.py apply",
        "curated": True,
        "sorter": sorter,
        "curated_from": record["curates"]["output_dir"],
        "curation_record": str(paths["record"]),
        "curation_updated": record.get("updated"),
        # The raw run this was built from, so a later re-sort under it is visible
        # (unit ids are not stable across re-sorts).
        "curated_from_run": _run_identity(raw_info),
        "curation_counts": c,
        "curation_line": provenance_line(record, curated=True),
        "n_units": n_units,
        "n_units_raw": raw_info.get("n_units"),
        "n_high_quality": n_high_quality,
        "metrics_note": metrics_note,
        "quality_rule": _summary.load_quality_rule(bio.REPO_ROOT / ".si_menu.json"),
        "quality_rule_text": _summary.rule_text(
            _summary.load_quality_rule(bio.REPO_ROOT / ".si_menu.json")),
        "si_version": si.__version__,
        # The recording window / geometry / band are the raw run's — the curated
        # result is the same recording, the same preprocessing, different units.
        "probe": raw_info.get("probe"),
        "channel_ids": raw_info.get("channel_ids"),
        "n_dropped_analog": raw_info.get("n_dropped_analog"),
        "effective_seconds": raw_info.get("effective_seconds"),
        "total_seconds": raw_info.get("total_seconds"),
        "freq_min": raw_info.get("freq_min"),
        "freq_max": raw_info.get("freq_max"),
    }
    (out / "run_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    if verbose:
        print(f"done — {provenance_line(record, curated=True)}")
        print(f"results in {out}")
    return {"out": out, "n_units": n_units, "n_units_raw": raw_info.get("n_units"),
            "n_high_quality": n_high_quality, "metrics_note": metrics_note,
            "summary": summary}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _show(sorter: str, root=None) -> int:
    """Print the record + curated state (pure read — no SpikeInterface)."""
    st = state(sorter, root)
    record = load_record(sorter, root)
    if record is None:
        print(f"{sorter}: no curation record yet ({st['record_path']} absent).")
        print(f"  {st['line']}")
        return 0
    c = st["counts"]
    print(f"{sorter}: {st['line']}")
    print(f"  record   {st['record_path']}  (updated {record.get('updated')})")
    print(f"  curates  {record['curates']['output_dir']} — sort of "
          f"{record['curates']['run'].get('created')} "
          f"({record['curates']['run'].get('n_units')} units)")
    print("  tools    " + ", ".join(f"{k} {v}" for k, v in record.get("tools", {}).items()))
    print(f"  decisions {c['total']} — {c['splits']} split(s), {c['merges']} merge(s), "
          f"{c['labels']} label(s), {c['removed']} removal(s)")
    for d in record.get("decisions", []):
        detail = d.get("detail", {})
        extra = f" sizes={detail['sizes']}" if detail.get("sizes") else ""
        print(f"    {d['at']}  {d['type']:6} units={d['units']} "
              f"method={d['method']} params={d.get('params', {})}{extra}")
    if st["has_curated"]:
        print(f"  curated  {st['curated_dir']} — {st['curated_units']} units")
        if st["stale"]:
            print(f"  ! {st['stale_reason']} — re-run 'curation.py apply "
                  f"--sorter {sorter}'")
    else:
        print(f"  curated  not built yet — run: python scripts/curation.py apply "
              f"--sorter {sorter}")
    errs = structural_errors(record)
    if errs:
        print("  ! " + "; ".join(errs))
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p):
        p.add_argument("--sorter", required=True, help="which saved sort to curate")
        p.add_argument("--root", default=None,
                       help="repo root holding outputs/ (default: this repo)")
        return p

    _common(sub.add_parser("show", help="print the record and the curated state"))
    p_label = _common(sub.add_parser("label", help="label a unit good/MUA/noise/unsure"))
    p_label.add_argument("--unit", required=True)
    p_label.add_argument("--label", required=True, choices=list(QUALITY_OPTIONS))
    p_label.add_argument("--note", default="")
    p_merge = _common(sub.add_parser("merge", help="merge two or more units"))
    p_merge.add_argument("--units", required=True,
                         help="comma-separated unit ids, e.g. 15,16")
    p_merge.add_argument("--note", default="")
    p_split = _common(sub.add_parser(
        "split", help="split a unit by clustering its spikes' features"))
    p_split.add_argument("--unit", action="append", required=True,
                         help="unit to split (repeatable)")
    p_split.add_argument("--parts", type=int, default=SPLIT_N_PARTS)
    p_split.add_argument("--features", default=SPLIT_FEATURES,
                         choices=["amplitude", "pca", "amplitude+pca"])
    p_split.add_argument("--n-pcs", type=int, default=SPLIT_N_PCS)
    p_split.add_argument("--seed", type=int, default=SPLIT_SEED)
    p_split.add_argument("--note", default="")
    p_apply = _common(sub.add_parser(
        "apply", help="replay the record onto the raw sort -> outputs/<sorter>/curated/"))
    p_apply.add_argument("--out", default=None, help="write the curated result here "
                         "instead of outputs/<sorter>/curated/")
    p_apply.add_argument("--n-jobs", type=int, default=1)
    args = ap.parse_args(argv)

    root = args.root
    paths = sort_paths(args.sorter, root)
    if args.cmd == "show":
        return _show(args.sorter, root)

    if not paths["sorting"].is_dir():
        print(f"no saved {args.sorter} sort in {paths['out']} — run one first: "
              f"uv run python scripts/run_sorting.py --sorter {args.sorter}",
              file=sys.stderr)
        return 1

    if args.cmd == "apply":
        record = load_record(args.sorter, root)
        if record is None:
            print(f"no curation record for {args.sorter} ({paths['record']}) — "
                  "record a decision first (label / merge / split).", file=sys.stderr)
            return 1
        if counts(record)["total"] == 0:
            print(f"the {args.sorter} curation record holds no decisions — nothing "
                  "to apply.", file=sys.stderr)
            return 1
        try:
            result = apply_record(record, root, out_dir=args.out, n_jobs=args.n_jobs)
        except Exception as e:  # noqa: BLE001 - one honest line, not a traceback
            print(f"apply failed: {e}", file=sys.stderr)
            return 1
        print(result["out"])
        return 0

    record = open_record(args.sorter, root)
    try:
        # Check the anchor before WRITING a decision too, not only at apply: a
        # record made against an earlier sort would resolve --unit against unit
        # ids that no longer mean the same thing.
        _check_run_identity(record, args.sorter, root)
        if args.cmd == "label":
            add_label(record, _resolve_unit(record, args.unit), args.label, note=args.note)
            print(f"labelled unit {args.unit} {args.label}")
        elif args.cmd == "merge":
            ids = [_resolve_unit(record, u.strip())
                   for u in args.units.split(",") if u.strip()]
            add_merge(record, ids, note=args.note)
            print(f"recorded a merge of units {ids}")
        elif args.cmd == "split":
            import spikeinterface.full as si

            analyzer = si.load_sorting_analyzer(paths["analyzer"])
            units = [_resolve_unit(record, u) for u in args.unit]
            proposals = propose_splits(analyzer, units, n_parts=args.parts,
                                       features=args.features, n_pcs=args.n_pcs,
                                       seed=args.seed, verbose=True)
            for uid, (indices, params, detail) in proposals.items():
                add_split(record, uid, indices, SPLIT_METHOD, params, detail,
                          note=args.note)
                print(f"recorded a {len(indices)}-way split of unit {uid} "
                      f"({' + '.join(str(len(p)) for p in indices)} spikes)")
    except Exception as e:  # noqa: BLE001 - honest one-liner for a CLI
        print(f"{args.cmd} failed: {e}", file=sys.stderr)
        return 1
    save_record(record, paths["record"])
    print(paths["record"])
    return 0


def _resolve_unit(record: dict, text: str):
    """Match a --unit argument to a real unit id of this sort.

    SpikeInterface unit ids are ints here but may be strings in another sort, and
    "4" must mean the same unit either way — so resolve against the record rather
    than guessing a type.
    """
    ids = record["curation"]["unit_ids"]
    if text in ids:
        return text
    try:
        number = int(text)
    except (TypeError, ValueError):
        number = None
    if number is not None and number in ids:
        return number
    raise ValueError(f"unit {text!r} is not in this sort ({ids})")


if __name__ == "__main__":
    raise SystemExit(main())
