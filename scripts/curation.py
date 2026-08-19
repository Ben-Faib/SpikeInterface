"""The curation record: decisions saved, applied to a curated Sorting, re-scored.

    uv run python scripts/curation.py show  --sorter tridesclous2
    uv run python scripts/curation.py label --sorter tridesclous2 --unit 15 --label noise
    uv run python scripts/curation.py merge --sorter tridesclous2 --units 15,16
    uv run python scripts/curation.py split --sorter tridesclous2 --unit 4 --unit 8
    uv run python scripts/curation.py apply --sorter tridesclous2
    uv run python scripts/curation.py export-phy --sorter tridesclous2
    uv run python scripts/curation.py import-phy --sorter tridesclous2

Single source of truth for **what was decided about a sort and what that
produced**. A sort finds candidate units; the decisions a human (or a scripted
method) makes about them — merge, split, label — live here, in a record beside
the sort, and are replayed deterministically to build the curated output.

    outputs/<sorter>/runs/<run_id>/       the RAW sort (never mutated — the audit trail)
        sorting/ analyzer/ run_info.json summary.json quality_metrics.csv
        curation.json                     THE RECORD (this module owns it)
        phy/                              the raw sort exported for Phy
        curated/                          the applied result, a first-class output
            sorting/ analyzer/ run_info.json summary.json quality_metrics.csv
            phy/                          the curated result exported for Phy

``sort_paths()`` is the ONE place any of those paths is resolved, and it delegates
to the versioned run store (``runs.py``), which decides WHICH run those paths
name. The record and the curated output live inside the run they curate, so a
re-sort — which lands in a new run directory — leaves them attached to the sort
they describe. A pre-store ``outputs/<sorter>/`` layout still resolves, read-only,
so curated results built before the store are still readable where they are.

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
        "output_dir": "outputs/tridesclous2/runs/<id>",   # repo-relative, POSIX
        "run": {"created": ..., "sorter": ..., "n_units": 17, "si_version": ...,
                "probe": ..., "effective_seconds": ..., "total_seconds": ...}
      },                  # ^ the ANCHOR. Unit ids are not stable across re-sorts
                          #   (tridesclous2 is non-deterministic on this recording,
                          #   and a record can be read beside a pre-store layout or
                          #   a copied run dir), so apply REFUSES a record whose anchor no longer
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
``import_phy_labels`` is pure too — bringing verdicts back is json + csv.
``propose_splits``, ``apply_record`` and ``export_phy`` import SI inside the
function.

The Phy round trip
------------------
The sorter merges what a human splits, and on this recording two of the three
merged pairs provably do not separate in the feature space the scripted split
sees. Phy is the path for those: the export goes out, a human decides, the
verdicts come back into this record.

    1. uv run python scripts/curation.py export-phy --sorter tridesclous2
       Writes the current run's ``phy/`` (or its ``curated/phy/`` — the CURATED result
       is exported when one exists, mirroring the report's rule; ``--raw`` forces
       the raw sort). Labels already in the record are seeded into the export, so
       Phy opens showing what was decided rather than a blank slate.
    2. Copy that folder to a machine with Phy and open it:
       ``phy template-gui params.py``. Mark clusters good / mua / noise (and
       ``:quality unsure`` for the workbench's fourth verdict). Save.
    3. Copy the folder back and:
       uv run python scripts/curation.py import-phy --sorter tridesclous2
       Each verdict becomes a labelled decision in the record with
       ``method: "phy"``. Then ``apply`` as usual.

Phy's ``cluster_id`` is a 0-based INDEX, not a unit id — SI's exporter writes the
mapping to ``cluster_si_unit_ids.tsv`` and the import reads verdicts back through
it. The export drops ``workbench_phy.json`` beside it carrying the run-identity
anchor, so an import onto a different sort is refused (unit ids
are not stable across re-sorts) rather than labelling the wrong units.

**Which file is the verdict:** ``cluster_group.tsv`` — the column Phy's own UI
edits — and ``cluster_quality.tsv`` fills in ONLY where group is ``unsorted``.
That ordering is deliberate: quality is a column *we* exported, so letting it win
would let a stale exported value override the curator's group edit.
``unsorted`` means "no verdict", never a decision.

**Collision rule — newest wins, loudly.** A Phy verdict that disagrees with a
label already in the record replaces it, and the decision entry keeps what it
replaced (``detail: {"replaced": "good", "replaced_method": "manual"}``) so the
audit trail still shows the hand-written verdict. The import prints every
override. A verdict identical to the recorded one writes nothing at all, so
re-importing the same folder is a no-op.

**Labels only.** Merges and splits performed *inside* Phy are not imported —
they create cluster ids this sort never had. Those clusters are skipped and
named in the import's report, never silently dropped. A curated export cannot be
imported at all: its unit ids are the curated ones, and the record is keyed to
the raw sort's.

API
---
Paths and state (pure):
    sort_paths(sorter, root=None, run=None) -> dict
                                               every path for one sorter's run;
                                               delegates to runs.sort_paths
    load_record(sorter=..., root=..., path=...) -> dict | None
    save_record(record, path) -> Path
    new_record(sorter, unit_ids, run=None, root=None) -> dict
    counts(record) -> {"total", "splits", "merges", "labels", "removed"}
    provenance_line(record, curated=True, has_curated=False) -> str
                                               the honest-surface sentence
    state(sorter, root=None, run=None) -> dict what the surfaces need to be honest:
        {"run", "has_record", "has_curated", "counts", "line", "stale",
         "stale_reason", "record_path", "curated_dir", "updated", "curated_units",
         "elsewhere"}
    curated_elsewhere(sorter, root=None) -> dict | None
                                               a curated result on a run that is
                                               NOT current (or the pre-store
                                               layout), so no surface goes silent
                                               about it when the pointer moves
    stale_reason(curated_run, record, raw_run) -> str   why a curated result no
                                               longer describes what is on disk
    anchor_error(record, sorter, root=None) -> str      why a decision must not be
                                               written into this record for the
                                               sort on disk ("" when it may be);
                                               ``record=None`` asks it of a record
                                               that does not exist yet
    structural_errors(record) -> list[str]     schema check without SI
    import_phy_labels(sorter, folder=..., root=..., dry_run=False) -> dict
                                               Phy's verdicts -> labelled decisions

Decisions (pure record mutation; each appends to ``decisions``):
    add_label(record, unit_id, label, note="", source="manual", params=None,
              detail=None)
                                               source = where the decision came
                                               from ("manual", "phy", "tui", a
                                               rule name); it lands in the
                                               decision's ``method``
    add_merge(record, unit_ids, note="")
    add_split(record, unit_id, indices, method, params, detail=None, note="")

Path/state rule (one home):
    preferred_analyzer_dir(analyzer_dir) / preferred_analyzer(sorter, root)
        -> (analyzer dir to show, is_curated). "Curated wins when it exists" is
        decided HERE; report, compare and the menu controller call it rather than
        each testing for the folder.

SpikeInterface-backed:
    validate(record)                           SI's validate_curation_dict
    propose_splits(analyzer, unit_ids, ...)    -> {unit_id: (indices, params, detail)}
    apply_record(record, root=None, ...)       -> {"out", "n_units", ...}
    export_phy(sorter, root=None, raw=False, ...)  -> {"out", "curated", ...}

``propose_splits`` partitions a unit's spikes by k-means on per-spike features —
spike amplitude and/or the top principal components on the unit's peak channel,
z-scored, k-means++ with a fixed seed (deterministic). It is the *scientific*
half: it decides where the split goes. ``apply_record`` never calls it — apply is
replay of the indices already in the record.

What ``curated/run_info.json`` adds, for the surfaces and the slices after this
one: ``curated: true``, ``curated_from`` (repo-relative raw output dir),
``curation_record`` (repo-relative), ``curation_updated`` + ``curation_counts`` +
``curation_line``, ``curated_from_run`` (the raw run's identity, so a later
re-sort under the curated result is visible), ``n_units``/``n_units_raw``, and
``unit_id_map`` — ``{"curated_to_raw": {curated id: [{"unit", "n_spikes"}, ...]},
"raw_to_curated": {raw id: [curated id, ...]}}``, unit ids as strings, read off
the saved spike trains. That map is how a Phy round-trip (or any later import)
says which sorter unit a curated unit came from. The window/geometry/band fields
are copied from the raw run — same recording, same preprocessing, different units.

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
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402  (REPO_ROOT only — no SpikeInterface)
import runs  # noqa: E402  (the versioned run store: where a run lives, which is current)
import sort_summary as _summary  # noqa: E402  (the metrics + quality-rule owner)

SCHEMA_VERSION = "1"
KIND = "spikeinterface-workbench-curation"
# The store builds the record's and the curated output's paths, so it holds the
# literals; they are re-exported here because callers name them through this
# module (curation.RECORD_NAME, curation.CURATED_DIRNAME). One definition, so a
# rename cannot leave the record and the path that carries it disagreeing.
RECORD_NAME = runs.RECORD_NAME
CURATED_DIRNAME = runs.CURATED_DIRNAME
PHY_DIRNAME = runs.PHY_DIRNAME
# SpikeInterface's curation-format version this module writes (0.104 accepts 1|2).
CURATION_FORMAT_VERSION = "2"

# The one label category the workbench writes. Exclusive: a unit carries exactly
# one of these. "MUA" = multi-unit activity, "unsure" = looked at, not decided.
QUALITY_KEY = "quality"
QUALITY_OPTIONS = ("good", "MUA", "noise", "unsure")
LABEL_DEFINITIONS = {QUALITY_KEY: {"label_options": list(QUALITY_OPTIONS),
                                   "exclusive": True}}

# The Phy boundary. Phy's cluster_group vocabulary is good/mua/noise/unsorted;
# "unsure" has no Phy group, so it exports as "unsorted" (no verdict) and makes
# the round trip through cluster_quality.tsv instead. "unsorted" coming back is
# the absence of a verdict, never a decision.
PHY_MANIFEST_NAME = "workbench_phy.json"
PHY_MANIFEST_KIND = "spikeinterface-workbench-phy-export"
PHY_GROUP_FILE = "cluster_group.tsv"
PHY_QUALITY_FILE = f"cluster_{QUALITY_KEY}.tsv"
PHY_UNIT_ID_FILE = "cluster_si_unit_ids.tsv"      # SI's cluster_id -> unit id map
PHY_GROUP_FOR_LABEL = {"good": "good", "MUA": "mua", "noise": "noise",
                       "unsure": "unsorted"}
LABEL_FOR_PHY_GROUP = {"good": "good", "mua": "MUA", "noise": "noise"}

# Defaults for the scripted split. Chosen once and applied to every unit — a
# per-unit tuning would make the record a story about the answer, not a method.
SPLIT_METHOD = "kmeans"
SPLIT_FEATURES = "amplitude+pca"     # also accepted: "amplitude", "pca"
SPLIT_N_PCS = 3                      # top N principal components, on the peak channel
SPLIT_N_PARTS = 2
SPLIT_SEED = 0


# --------------------------------------------------------------------------- #
# Paths — the ONE resolver, delegated to the versioned run store
# --------------------------------------------------------------------------- #
def sort_paths(sorter: str, root=None, *, run=None) -> dict:
    """Every path the curation lifecycle needs for one sorter's saved run.

    Delegates to ``runs.sort_paths``: the store owns where a run lives and which
    one is current, and the curation record and the curated output ride INSIDE
    the run directory they curate — so a re-sort lands in its own directory and
    can never leave a record beside a sort it does not describe.

    ``root`` defaults to the repo root (tests pass a tmp dir); ``run`` pins an
    explicit run id or directory instead of the current one. The store's key set
    is a superset of the keys this module uses, so callers keep reading the same
    names. A pre-store ``outputs/<sorter>/`` layout still resolves, read-only.
    """
    return runs.sort_paths(sorter, root=root, run=run)


def preferred_analyzer_dir(analyzer_dir) -> "tuple[Path, bool]":
    """(analyzer dir to show, is_curated) for a run's RAW ``analyzer``.

    THE "curated wins" RULE, in one place: if a curated analyzer was built beside
    the raw sort, that is the result and the surface says so; otherwise the raw
    sort is the result. report, compare and the menu controller all call this (or
    ``preferred_analyzer``) rather than each testing for the folder themselves.
    """
    raw = Path(analyzer_dir)
    curated = raw.parent / CURATED_DIRNAME / "analyzer"
    if raw.name == "analyzer" and raw.parent.name != CURATED_DIRNAME and curated.is_dir():
        return curated, True
    return raw, False


def preferred_analyzer(sorter: str, root=None, *, run=None) -> "tuple[Path, bool]":
    """(analyzer dir to show, is_curated) for a sorter — the same rule, by name.

    ``run`` pins a specific run instead of the current one (``sort_paths``)."""
    return preferred_analyzer_dir(sort_paths(sorter, root, run=run)["analyzer"])


def curated_elsewhere(sorter: str, root=None) -> "dict | None":
    """A curated result that exists but is NOT on the run the surfaces are showing.

    Curated output is anchored to the run it curates, which is correct and which
    means a fresh sort moves the pointer and the older curated result stops being
    shown anywhere. Correct anchoring, unacceptable silence: this finds it so the
    surfaces can name it. Returns {"run", "legacy", "dir", "current", "line"} for
    the newest such run, or None — including None when the current run is itself
    curated, because then nothing is being hidden.

    Nothing is migrated or adopted: the curated result stays where it was built,
    and the only way to curate the current run is to apply a record to it.
    """
    current = runs.resolve(sorter, root)
    if current is None or preferred_analyzer(sorter, root)[1]:
        return None
    for entry in runs.list_runs(sorter, root):
        if entry["id"] == current["id"]:
            continue
        if not (entry["dir"] / CURATED_DIRNAME / "analyzer").is_dir():
            continue
        which = "the pre-store layout" if entry["legacy"] else f"run {entry['id']}"
        return {"run": entry["id"], "legacy": entry["legacy"], "dir": entry["dir"],
                "where": _rel(entry["dir"] / CURATED_DIRNAME, root),
                "current": current["id"],
                "line": (f"a curated result exists on {which}; the current run "
                         f"({current['id']}) is uncurated — apply a record to this "
                         f"run to curate it"),
                # The same fact for a width-constrained surface. Both sentences
                # live here so no surface composes curation language itself.
                "short": f"curated result on {which} — apply to curate this run"}
    return None


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


def _identity_mismatch(want: dict, have: dict, want_label: str = "record") -> list:
    """Human-readable differences between two run identities ([] when they agree).

    Only the fields that actually pin a sort are compared, and a field missing on
    either side is not a mismatch — an older run_info without it must not read as
    a different sort. ``want_label`` names what is being compared against disk
    (the curation record, or a Phy export's manifest).
    """
    out = []
    for key, label in (("sorter", "sorter"), ("created", "sorted at"),
                       ("n_units", "units"), ("effective_seconds", "window (s)")):
        a, b = (want or {}).get(key), (have or {}).get(key)
        if a is not None and b is not None and a != b:
            out.append(f"{label}: {want_label} {a!r}, on disk {b!r}")
    return out


def read_run_info(sorter: str, root=None, *, run=None) -> dict:
    """The current run's run_info.json; {} when absent/unreadable. No SI import."""
    try:
        return json.loads(
            sort_paths(sorter, root, run=run)["run_info"].read_text(encoding="utf-8"))
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


def add_label(record: dict, unit_id, label: str, note: str = "",
              source: str = "manual", params=None, detail=None) -> dict:
    """Label one unit good/MUA/noise/unsure (replaces that unit's previous label).

    ``source`` is where the decision came from and lands in the decision's
    ``method``: "manual" for a person here, "phy" for a label round-tripped back
    from a Phy export, "tui" for the in-menu triage, a rule name for an
    automatic pass. A label's origin decides how much it is worth, so it is
    recorded rather than assumed. ``params``/``detail`` ride into the decision
    entry for sources that carry extra provenance (the Phy import records the
    cluster id and folder it read the verdict from).
    """
    if label not in QUALITY_OPTIONS:
        raise ValueError(f"unknown label {label!r} — one of {list(QUALITY_OPTIONS)}")
    uid = _plain(unit_id)
    _require_unit(record, uid)
    labels = [m for m in record["curation"]["manual_labels"] if m["unit_id"] != uid]
    labels.append({"unit_id": uid, "labels": {QUALITY_KEY: [label]}})
    record["curation"]["manual_labels"] = labels
    p = {"label": label}
    p.update(params or {})
    _decide(record, "label", [uid], source, p, detail=detail, note=note)
    return record


def label_of(record: "dict | None", unit_id) -> "str | None":
    """The unit's current quality label in the record (None when unlabelled)."""
    uid = _plain(unit_id)
    for m in (record or {}).get("curation", {}).get("manual_labels") or []:
        if m.get("unit_id") == uid:
            got = (m.get("labels") or {}).get(QUALITY_KEY) or []
            return got[0] if got else None
    return None


def label_method_of(record: "dict | None", unit_id) -> "str | None":
    """How the unit's current label was decided ("manual", "phy", …), or None.

    The last label decision for that unit wins — decisions are append-only, and
    ``add_label`` replaces the unit's entry in ``manual_labels`` each time.
    """
    uid = _plain(unit_id)
    for d in reversed((record or {}).get("decisions") or []):
        if d.get("type") == "label" and d.get("units") == [uid]:
            return d.get("method")
    return None


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


def _match_unit(unit_ids, text):
    """The id in ``unit_ids`` that ``text`` names, or None.

    SpikeInterface unit ids are ints here but may be strings in another sort, and
    a "4" arriving from a CLI flag or a Phy TSV must mean the same unit either
    way — so resolve against the ids the sort actually has, never by guessing.
    """
    if text in unit_ids:
        return text
    try:
        number = int(text)
    except (TypeError, ValueError):
        return None
    return number if number in unit_ids else None


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
    No record but a curated result on disk (someone deleted curation.json, or
    the folder was copied without it) — the numbers ARE curated and must never be
    labelled raw:
              "curated result — its curation record is missing; provenance unknown"
    """
    if not record:
        if curated:
            return ("curated result — its curation record is missing; "
                    "provenance unknown")
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
    """Why a curated result cannot be trusted as-is ("" when it can).

    Three ways: the record is gone (nothing says what these units are), the
    record gained decisions after it was applied, or the raw sort was re-run
    underneath it (a re-sort renumbers units, so the curated result then
    describes units that no longer exist).
    """
    curated_run = curated_run or {}
    if record is None:
        return ("the curation record is missing — nothing on disk says which "
                "decisions produced this result")
    if curated_run.get("curation_updated") \
            and curated_run["curation_updated"] != record.get("updated"):
        return "the curation record has new decisions since it was applied"
    anchor = curated_run.get("curated_from_run")
    if anchor and raw_run and anchor != _run_identity(raw_run):
        return "the raw sort was re-run after this curated result was built"
    return ""


def anchor_error(record: "dict | None", sorter: str, root=None) -> str:
    """Why a decision must NOT be written into ``record`` for the sort on disk.

    "" when the record is anchored to the sorter's CURRENT run (``sort_paths``,
    i.e. the store) and may be decided on or applied. Pure — json + pathlib, so
    the menu can ask before offering to label. ``record=None`` asks the same
    question about a record that does not exist yet: only the disk side has to be
    identifiable, because ``new_record`` anchors a fresh record to exactly that
    identity.

    An anchor only binds if BOTH sides carry it. All-None compares as "matches
    everything", which is the exact failure the anchor exists to prevent — so a
    missing/corrupt run_info.json, or a record written when one was missing, is a
    refusal, not a pass. Every refusal names its next step (DESIGN_UX §1.7).
    """
    want = (record or {}).get("curates", {}).get("run", {})
    have = _run_identity(read_run_info(sorter, root))
    KEY = ("sorter", "created", "n_units")
    blank_disk = [k for k in KEY if have.get(k) is None]
    if blank_disk:
        return (
            f"cannot identify the saved {sorter} sort: "
            f"{sort_paths(sorter, root)['run_info']} is missing or unreadable "
            f"(no {', '.join(blank_disk)}). Without it there is nothing to check the "
            "curation record against, and unit ids are not stable across re-sorts, so "
            "a decision could silently land on the wrong unit. Next step: restore that "
            f"run_info.json, or re-sort (uv run python scripts/run_sorting.py --sorter "
            f"{sorter}) and write a fresh record against the new sort.")
    if record is None:
        return ""
    blank_record = [k for k in KEY if want.get(k) is None]
    if blank_record:
        return (
            f"this curation record has no usable anchor (no {', '.join(blank_record)} "
            "under 'curates.run'), so it cannot be tied to the sort on disk. It was "
            "most likely written while run_info.json was missing. Next step: write a "
            f"fresh record against the sort now in outputs/{sorter}/ — the old record "
            "stays as the audit trail of what was decided.")
    mismatch = _identity_mismatch(want, have)
    if not mismatch:
        return ""
    return (
        f"this curation record was written against a different {sorter} sort — "
        + "; ".join(mismatch)
        + ". Unit ids are not stable across re-sorts, so replaying these decisions "
          "would curate the wrong units. Next step: re-run the comparison against "
          "this sort and write a fresh record (curation.py split/label/merge on the "
          f"sort now in outputs/{sorter}/), or restore the sort the record was made "
          "on. The old record is not deleted — it stays as the audit trail of what "
          "was decided about that run.")


def state(sorter: str, root=None, *, run=None) -> dict:
    """What a surface needs to be honest about curated-vs-raw. No SI import.

    ``stale`` is True when the curated result cannot be trusted as-is — the
    record moved on, the raw sort was re-run under it, or the record is gone
    (see ``stale_reason``). ``has_record`` False with ``has_curated`` True is
    exactly that last case: the numbers are curated, their provenance is not on
    disk, and no surface may call them raw.

    ``elsewhere`` is the other silence: a curated result built on a run that is
    no longer current (or in the pre-store layout) would otherwise vanish from
    every surface the moment a new sort moves the pointer. It carries a line
    naming where that result is; None when there is none, or when the run being
    shown is itself curated. ``run`` pins a specific run instead of the current
    one, in which case ``elsewhere`` is not looked for — it is a fact about which
    run is current, and a pinned view is not making that claim.
    """
    p = sort_paths(sorter, root, run=run)
    record = load_record(path=p["record"])
    _dir, has_curated = preferred_analyzer(sorter, root, run=run)
    curated_run = {}
    if has_curated:
        try:
            curated_run = json.loads(p["curated_run_info"].read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - provenance is best-effort
            curated_run = {}
    reason = (stale_reason(curated_run, record, read_run_info(sorter, root, run=run))
              if has_curated else "")
    return {
        "sorter": sorter,
        "run": p["id"],
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
        "elsewhere": curated_elsewhere(sorter, root) if run is None else None,
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
# The Phy round trip, half 2: verdicts back into the record (pure — csv + json)
# --------------------------------------------------------------------------- #
def _read_tsv(path) -> list:
    """[(first column, second column), …] from a Phy TSV; [] when it isn't there.

    Phy's TSVs are tab-separated with a one-line header. ``newline=""`` is the
    csv module's contract and is what keeps the reader honest about the CRLF a
    Windows-side Phy writes.
    """
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh, delimiter="\t")
            if next(reader, None) is None:
                return []
            for row in reader:
                if len(row) >= 2 and row[0].strip():
                    rows.append((row[0].strip(), row[1].strip()))
    except OSError:
        return []
    return rows


def _write_tsv(path, header, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)


def phy_verdicts(folder) -> tuple:
    """``({cluster_id: (label, file)}, [rejected values])`` for a Phy folder.

    ``cluster_group.tsv`` is the verdict — it is the column Phy's own UI edits.
    ``cluster_quality.tsv`` (the workbench's exported column, which a curator can
    set in Phy with ``:quality unsure``) fills in ONLY where group says
    ``unsorted``: quality is a column *we* wrote, so letting it win would let a
    stale exported value override the curator's group edit.

    ``unsorted`` (and an empty quality cell) means "no verdict" and is not a
    decision. Anything else outside the two vocabularies is REJECTED and named in
    the second return value — a curator's typo is not a thing to drop quietly.
    """
    found, rejected = {}, []
    for cid, value in _read_tsv(Path(folder) / PHY_GROUP_FILE):
        label = LABEL_FOR_PHY_GROUP.get(value.lower())
        if label is not None:
            found[cid] = (label, PHY_GROUP_FILE)
        elif value.lower() != "unsorted":
            rejected.append(f"cluster {cid}: {PHY_GROUP_FILE} says {value!r}, which "
                            f"is not one of {sorted(LABEL_FOR_PHY_GROUP)} or 'unsorted'")
    for cid, value in _read_tsv(Path(folder) / PHY_QUALITY_FILE):
        if cid in found or not value:
            continue                      # group already carries a verdict / no verdict
        match = next((o for o in QUALITY_OPTIONS if o.lower() == value.lower()), None)
        if match is not None:
            found[cid] = (match, PHY_QUALITY_FILE)
        else:
            rejected.append(f"cluster {cid}: {PHY_QUALITY_FILE} says {value!r}, which "
                            f"is not one of {list(QUALITY_OPTIONS)}")
    return found, rejected


def _cluster_order(cid: str):
    """Sort key for Phy cluster ids: numeric where they are numbers ("10" after
    "2"), lexical otherwise — decisions land in the record in cluster order."""
    try:
        return (0, int(cid), "")
    except (TypeError, ValueError):
        return (1, 0, str(cid))


def phy_manifest(folder) -> "dict | None":
    """The ``workbench_phy.json`` an export drops beside the Phy files, or None."""
    try:
        data = json.loads((Path(folder) / PHY_MANIFEST_NAME).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - absent / malformed -> caller degrades
        return None
    return data if isinstance(data, dict) else None


def import_phy_labels(sorter: str, folder=None, root=None, *,
                      dry_run: bool = False) -> dict:
    """Bring a curator's Phy verdicts back in as labelled decisions in the record.

    ``folder`` defaults to the current run's ``phy/``. The export's manifest is the
    contract: it names the sort the folder came from, and this refuses to write
    when that no longer matches the sort on disk (unit ids are not stable across
    re-sorts) or when the folder is a CURATED export (its ids are the curated
    ones; the record is keyed to the raw sort's).

    Every verdict is written through ``add_label`` with ``method="phy"``. A
    verdict that disagrees with a label already in the record replaces it and
    keeps what it replaced in the decision entry; an identical one writes
    nothing. Merges and splits made inside Phy are not imported — the cluster ids
    they create are reported as skipped, never silently dropped.

    Returns ``{"folder", "record_path", "imported", "unchanged", "overridden",
    "skipped", "saved"}``; ``imported`` and ``overridden`` are lists of dicts.
    """
    paths = sort_paths(sorter, root)
    folder = Path(folder) if folder is not None else paths["phy"]
    if not folder.is_dir():
        raise RuntimeError(
            f"no Phy folder at {folder} — export one first: "
            f"python scripts/curation.py export-phy --sorter {sorter}")

    manifest = phy_manifest(folder)
    if manifest is None or manifest.get("kind") != PHY_MANIFEST_KIND:
        raise RuntimeError(
            f"{folder} carries no {PHY_MANIFEST_NAME}, so there is no way to tell "
            "which sort its cluster ids belong to. Next step: re-export with "
            f"python scripts/curation.py export-phy --sorter {sorter}, curate that "
            "folder in Phy, and import it.")
    if manifest.get("curated"):
        raise RuntimeError(
            f"{folder} is an export of the CURATED result — its cluster ids are the "
            "curated units', and the curation record is keyed to the raw sort's, so "
            "these verdicts cannot be attached to it. Next step: export the raw sort "
            f"(python scripts/curation.py export-phy --sorter {sorter} --raw), curate "
            "that in Phy, import it, then apply.")
    if manifest.get("sorter") != sorter:
        raise RuntimeError(
            f"{folder} was exported from the {manifest.get('sorter')!r} sort, not "
            f"{sorter!r}. Next step: import it against that sorter, or re-export.")

    # An anchor only binds when the manifest actually carries one. A blank or
    # missing run block would compare as "matches everything" — the exact
    # failure the anchor exists to prevent (unit ids are not stable across
    # re-sorts) — so it is a refusal, not a pass.
    want = manifest.get("run") or {}
    blank = [k for k in ("sorter", "created", "n_units") if want.get(k) is None]
    if blank:
        raise RuntimeError(
            f"{folder} carries no usable run anchor (no {', '.join(blank)} in "
            f"{PHY_MANIFEST_NAME}'s 'run'), so there is no way to tell which "
            "sort its cluster ids belong to — these verdicts could land on the "
            "wrong units. It was most likely exported while run_info.json was "
            "missing. Next step: re-export the sort now on disk (python "
            f"scripts/curation.py export-phy --sorter {sorter} --raw), curate "
            "that folder in Phy, and import it.")
    mismatch = _identity_mismatch(want,
                                  _run_identity(read_run_info(sorter, root)),
                                  want_label="export")
    if mismatch:
        raise RuntimeError(
            f"{folder} was exported from a different {sorter} sort — "
            + "; ".join(mismatch)
            + ". Unit ids are not stable across re-sorts, so these verdicts would "
              "land on the wrong units. Next step: re-export the sort now in "
              f"outputs/{sorter}/ (python scripts/curation.py export-phy --sorter "
              f"{sorter}), curate that folder in Phy, and import it.")

    record = open_record(sorter, root)
    _check_run_identity(record, sorter, root)
    unit_ids = record["curation"]["unit_ids"]
    cluster_to_unit = dict(_read_tsv(folder / PHY_UNIT_ID_FILE))
    if not cluster_to_unit:
        raise RuntimeError(
            f"{folder / PHY_UNIT_ID_FILE} is missing or empty, so Phy's cluster ids "
            "cannot be mapped back to unit ids. Next step: re-export with "
            f"python scripts/curation.py export-phy --sorter {sorter}.")

    verdicts, rejected = phy_verdicts(folder)
    imported, overridden, unchanged, skipped = [], [], [], []
    for cid, (label, source_file) in sorted(verdicts.items(),
                                            key=lambda kv: _cluster_order(kv[0])):
        named = cluster_to_unit.get(cid)
        uid = _match_unit(unit_ids, named) if named is not None else None
        if uid is None:
            # A cluster Phy created (a merge or split done in its UI) — this
            # imports labels only, and silence here would look like agreement.
            skipped.append(f"cluster {cid} ({label}) is not a unit of this sort")
            continue
        previous = label_of(record, uid)
        if previous == label:
            unchanged.append({"unit": uid, "label": label})
            continue
        entry = {"unit": uid, "label": label, "cluster": cid, "from": source_file,
                 "previous": previous,
                 "previous_method": label_method_of(record, uid) if previous else None}
        detail = None
        if previous is not None:
            detail = {"replaced": previous,
                      "replaced_method": entry["previous_method"]}
            overridden.append(entry)
        add_label(record, uid, label, source="phy",
                  params={"cluster_id": cid, "source_file": source_file},
                  detail=detail)
        imported.append(entry)

    saved = False
    if imported and not dry_run:
        save_record(record, paths["record"])
        saved = True
    return {"folder": folder, "record_path": paths["record"], "imported": imported,
            "unchanged": unchanged, "overridden": overridden, "skipped": skipped,
            "rejected": rejected, "saved": saved}


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

    WHAT A SPLIT CAN AND CANNOT DO HERE (measured on this recording, 2026-08-18,
    against Ben's manual re-export). Splitting reproduced the manual pair on the
    ch7 unit (each manual unit mapping to its own curated unit) but not on the
    ch5 and ch9 units. The reason is not the clustering: those merged units are
    **3.6-5.4x residue-contaminated** — tridesclous2's unit holds several
    thousand events the human never assigned to either manual unit — so any
    within-unit split, by any method, hands back children that are still mostly
    residue and are not defensible single units. The leverage is upstream of the
    split: label or remove the residue, or sort better. Read a split as "this
    unit contains more than one thing", never as "these children are clean".
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
    and 18 units), and a record can be read beside a pre-store layout, a copied run
    directory, or a run the pointer has since moved off. So a record replayed onto
    a different sort would merge, split and label the wrong
    units, quietly. The record's ``curates.run`` block is the anchor: sorter, the
    run's created timestamp, its unit count and its effective window all have to
    match the sort on disk.
    """
    err = anchor_error(record, sorter, root)
    if err:
        raise RuntimeError(err)


def _check_out_dir(out, paths: dict, sorter: str) -> None:
    """Refuse an output dir that would write the curated result INTO the raw sort.

    ``apply`` clears ``<out>/sorting`` and ``<out>/analyzer`` before rebuilding
    them, so ``--out <the run directory>`` would delete the raw sort — the audit
    trail the whole design rests on. Resolved, so ``.`` / ``..`` / a symlink
    cannot sneak past.
    """
    target = Path(out).resolve()
    for key in ("out", "sorting", "analyzer"):
        if target == paths[key].resolve():
            raise RuntimeError(
                f"refusing to write the curated result to {target} — that is the raw "
                f"{sorter} sort itself ({key}/), and applying would delete it. The raw "
                "sort is the audit trail: it is never written to. Leave --out unset to "
                f"use {paths['curated']}, or pass a directory outside "
                f"{paths['out']}.")


def _check_phy_out_dir(out, paths: dict, sorter: str) -> None:
    """Refuse an export target the wholesale rmtree below must never eat.

    ``export_phy`` clears its target before SI writes the folder, so ``--out``
    pointed at anything that is not a previous Phy export would delete it —
    the run directory itself (the raw sort, the audit trail), ``outputs/``,
    or an unrelated directory. Resolved, so ``.``/``..``/symlinks cannot sneak
    past. A non-empty existing target is only cleared when it carries a previous
    export's manifest or ``params.py``.
    """
    target = Path(out).resolve()
    for key in ("out", "sorting", "analyzer", "curated", "curated_sorting",
                "curated_analyzer"):
        p = paths[key].resolve()
        if target == p or p.is_relative_to(target):
            raise RuntimeError(
                f"refusing to export to {target} — clearing it would delete the "
                f"{sorter} sort's {key.replace('_', ' ')} ({p}). The raw sort and "
                "its curated result are the audit trail: they are never written "
                "to. Leave --out unset, or pass a directory outside "
                f"{paths['out']}.")
    if target.is_dir() and any(target.iterdir()) \
            and not (target / PHY_MANIFEST_NAME).exists() \
            and not (target / "params.py").exists():
        raise RuntimeError(
            f"refusing to clear {target} — it is not empty and does not look "
            f"like a previous Phy export (no {PHY_MANIFEST_NAME}, no params.py). "
            "Pass an empty directory, a previous export, or a path that does "
            "not exist yet.")


def _unit_id_map(raw_sorting, curated_sorting) -> dict:
    """Which raw unit(s) each curated unit's spikes came from, with counts.

    Read off the saved spike trains rather than replayed from SpikeInterface's
    id-assignment internals, so it stays true if those change. Keys are unit ids
    as strings (JSON object keys); a merge shows several sources, a split shows
    the same source under several curated units, an untouched unit shows itself.
    """
    import numpy as np

    raw = {str(u): np.asarray(raw_sorting.get_unit_spike_train(u))
           for u in raw_sorting.unit_ids}
    curated_to_raw, raw_to_curated = {}, {str(u): [] for u in raw}
    for c in curated_sorting.unit_ids:
        c_key = str(c)
        c_frames = np.asarray(curated_sorting.get_unit_spike_train(c))
        sources = []
        for r_key, r_frames in raw.items():
            n = int(np.intersect1d(c_frames, r_frames, assume_unique=False).size)
            if n:
                sources.append({"unit": r_key, "n_spikes": n})
                raw_to_curated[r_key].append(c_key)
        sources.sort(key=lambda s: -s["n_spikes"])
        curated_to_raw[c_key] = sources
    return {"curated_to_raw": curated_to_raw, "raw_to_curated": raw_to_curated}


def _rel(path, root=None) -> str:
    """A repo-relative POSIX path (absolute paths break on merge-back / Windows)."""
    base = Path(root) if root is not None else bio.REPO_ROOT
    path = Path(path)
    try:
        return path.relative_to(base).as_posix()
    except ValueError:      # outside the root (an explicit --out) — keep it whole
        return path.as_posix()


def apply_record(record: dict, root=None, *, out_dir=None, verbose: bool = True,
                 n_jobs: int = 1) -> dict:
    """Apply a validated record to the RAW saved Sorting; write the run's curated/.

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
    _check_out_dir(out, paths, sorter)
    out.mkdir(parents=True, exist_ok=True)
    _sort._robust_rmtree(out / "sorting")
    curated = curated.save(folder=str(out / "sorting"), overwrite=True)
    unit_map = _unit_id_map(raw_sorting, curated)
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
    except Exception as e:  # noqa: BLE001 - metrics are non-fatal; the units are saved
        import traceback

        traceback.print_exc()
        metrics_note = f"quality metrics failed: {type(e).__name__}: {e}"
        print(f"! {metrics_note} — the curated sorting itself is saved.")
        # Never leave half-built derived data for a surface to read as this result.
        _sort._robust_rmtree(out / "analyzer")
        for stale in ("quality_metrics.csv", "summary.json", "summary.csv"):
            (out / stale).unlink(missing_ok=True)
    else:
        # The array/yield summary gets its OWN try (run_sorting's semantics): a
        # summary hiccup must not delete a perfectly good analyzer + metrics.
        try:
            summary = _summary.compute_summary(analyzer, sorter=sorter)
            _summary.write_summary(summary, out)
            if verbose:
                for line in _summary.format_card(summary):
                    print("  " + line)
        except Exception as e:  # noqa: BLE001 - summary is best-effort
            import traceback

            traceback.print_exc()
            summary = None
            print(f"! array/yield summary couldn't be computed: {type(e).__name__}: {e}"
                  " — the curated analyzer and quality metrics are saved.")

    raw_info = read_run_info(sorter, root)
    c = counts(record)
    info = {
        "created": _now(),
        "command": "curation.py apply",
        "curated": True,
        "sorter": sorter,
        "curated_from": record["curates"]["output_dir"],
        "curation_record": _rel(paths["record"], root),
        "curation_updated": record.get("updated"),
        # Raw unit id -> curated unit id(s) and back, with per-source spike counts:
        # the trace a Phy round-trip (and any later re-import) needs to say which
        # sorter unit a curated unit came from. Keys are unit ids as strings.
        "unit_id_map": unit_map,
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
            "summary": summary, "unit_id_map": unit_map}


# --------------------------------------------------------------------------- #
# The Phy round trip, half 1: the export (SpikeInterface-backed)
# --------------------------------------------------------------------------- #
def _seed_phy_labels(folder: Path, labels: dict) -> int:
    """Put the labels already decided into the exported folder. Returns how many.

    SI's exporter writes every cluster ``unsorted``; a curator opening this in Phy
    should see the verdicts that already exist, not a blank slate. Both files are
    written keyed by Phy's ``cluster_id`` (a 0-based index), mapped through the
    exporter's own ``cluster_si_unit_ids.tsv``.
    """
    pairs = _read_tsv(folder / PHY_UNIT_ID_FILE)
    known = list(labels)
    groups, qualities, n = [], [], 0
    for cid, unit in pairs:
        uid = _match_unit(known, unit)
        label = labels.get(uid) if uid is not None else None
        groups.append((cid, PHY_GROUP_FOR_LABEL.get(label, "unsorted")))
        qualities.append((cid, label or ""))
        n += label is not None
    _write_tsv(folder / PHY_GROUP_FILE, ("cluster_id", "group"), groups)
    _write_tsv(folder / PHY_QUALITY_FILE, ("cluster_id", QUALITY_KEY), qualities)
    return n


def export_phy(sorter: str, root=None, *, raw: bool = False, out_dir=None,
               verbose: bool = True, n_jobs: int = 1) -> dict:
    """Export the sort a curator should open in Phy → a Phy folder.

    Which sort: the CURATED result when one has been built, else the raw sort —
    the same curated-supersedes-raw rule the report follows (``preferred_analyzer``).
    ``raw=True`` forces the raw sort even when a curated result exists. The
    returned dict says which was exported; so does ``workbench_phy.json`` in the
    folder, alongside the run-identity anchor that lets an import refuse a folder
    exported from a sort that has since been re-run.
    """
    import spikeinterface.full as si
    from spikeinterface.exporters import export_to_phy

    import run_sorting as _sort  # the sort pipeline's Windows-safe rmtree

    paths = sort_paths(sorter, root)
    analyzer_dir, curated = preferred_analyzer(sorter, root)
    if raw:
        analyzer_dir, curated = paths["analyzer"], False
    if not analyzer_dir.is_dir():
        raise RuntimeError(
            f"no saved {sorter} analyzer at {analyzer_dir} — run a sort first: "
            f"uv run python scripts/run_sorting.py --sorter {sorter}")

    # An export that cannot be anchored could never be safely imported back —
    # a blank anchor would let verdicts land on the wrong units of a later sort.
    run_anchor = _run_identity(read_run_info(sorter, root))
    blank = [k for k in ("sorter", "created", "n_units")
             if run_anchor.get(k) is None]
    if blank:
        raise RuntimeError(
            f"cannot identify the saved {sorter} sort: {paths['run_info']} is "
            f"missing or unreadable (no {', '.join(blank)}), so this export "
            "would carry no run anchor and its verdicts could never be safely "
            "imported back. Next step: re-sort (uv run python "
            f"scripts/run_sorting.py --sorter {sorter}) and export that.")

    record = load_record(sorter, root)
    if curated:
        # A curated result the record or sort has moved past must not travel:
        # the manifest would stamp the CURRENT sort's anchor onto an analyzer
        # built from a different one — provenance that is actively wrong.
        try:
            curated_run = json.loads(
                paths["curated_run_info"].read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - provenance is best-effort
            curated_run = {}
        stale = stale_reason(curated_run, record, read_run_info(sorter, root))
        if stale:
            raise RuntimeError(
                f"the curated {sorter} result no longer describes what is on "
                f"disk — {stale}. Next step: re-apply the record (uv run python "
                f"scripts/curation.py apply --sorter {sorter}) and export that, "
                f"or export the raw sort (uv run python scripts/curation.py "
                f"export-phy --sorter {sorter} --raw).")

    out = Path(out_dir) if out_dir else (paths["curated_phy"] if curated
                                         else paths["phy"])
    _check_phy_out_dir(out, paths, sorter)
    analyzer = si.load_sorting_analyzer(analyzer_dir)
    if verbose:
        which = "curated result" if curated else "raw sort"
        print(f"exporting the {which} ({len(analyzer.unit_ids)} units, "
              f"{analyzer_dir}) for Phy → {out}")
    _sort._robust_rmtree(out)
    # use_relative_path: params.py then points at "recording.dat" beside it rather
    # than at this machine's absolute path — the export is meant to be COPIED to a
    # machine that has Phy, and an absolute dat_path would not survive the trip
    # (least of all across macOS -> Windows).
    export_to_phy(analyzer, out, verbose=verbose, use_relative_path=True,
                  n_jobs=n_jobs, progress_bar=verbose)

    if curated:
        # The curated sorting carries the labels apply_curation replayed onto it;
        # the record's labels name RAW units, which these ids are not.
        prop = analyzer.sorting.get_property(QUALITY_KEY)
        labels = {} if prop is None else {
            _plain(u): str(v) for u, v in zip(analyzer.unit_ids, prop)
            if str(v) in QUALITY_OPTIONS}
    else:
        labels = {m["unit_id"]: (m.get("labels") or {}).get(QUALITY_KEY, [None])[0]
                  for m in (record or {}).get("curation", {}).get("manual_labels") or []}
        labels = {u: v for u, v in labels.items() if v in QUALITY_OPTIONS}
    n_seeded = _seed_phy_labels(out, labels)

    manifest = {
        "kind": PHY_MANIFEST_KIND,
        "schema_version": SCHEMA_VERSION,
        "exported": _now(),
        "sorter": sorter,
        "curated": curated,
        "analyzer": _rel(analyzer_dir, root),
        "n_units": len(analyzer.unit_ids),
        "labels_seeded": n_seeded,
        # The anchor: which raw sort these cluster ids belong to. An import
        # against a different sort is refused on this; a blank
        # anchor was already refused above, so this always binds.
        "run": run_anchor,
        "record_updated": (record or {}).get("updated"),
        "tools": _tool_versions(),
    }
    (out / PHY_MANIFEST_NAME).write_text(json.dumps(manifest, indent=2),
                                         encoding="utf-8")
    if verbose:
        print(f"{n_seeded} of {len(analyzer.unit_ids)} clusters carry a label "
              "already decided")
        print(f"open it with: phy template-gui {out / 'params.py'}")
        if curated:
            print("this is the CURATED result — its verdicts cannot be imported "
                  "back into the record (export --raw for a round trip)")
        else:
            print(f"bring verdicts back with: python scripts/curation.py "
                  f"import-phy --sorter {sorter}")
    return {"out": out, "curated": curated, "n_units": len(analyzer.unit_ids),
            "analyzer": analyzer_dir, "labels_seeded": n_seeded}


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
        if st["elsewhere"]:
            print(f"  ! {st['elsewhere']['line']}")
            print(f"    it is at {st['elsewhere']['where']}")
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
    if st["elsewhere"]:
        print(f"  ! {st['elsewhere']['line']}")
        print(f"    it is at {st['elsewhere']['where']}")
    errs = structural_errors(record)
    if errs:
        print("  ! " + "; ".join(errs))
        return 1
    return 0


def _report_import(result: dict, sorter: str, dry_run: bool = False) -> int:
    """Print what an import did (or would do). Overrides are named, never implied."""
    n = len(result["imported"])
    verb = "would import" if dry_run else "imported"
    print(f"{verb} {_plural(n, 'label')} from {result['folder']}")
    for e in result["imported"]:
        was = (f"  (was {e['previous']}, {e['previous_method']})"
               if e["previous"] else "")
        print(f"  unit {e['unit']}: {e['label']}   "
              f"[phy cluster {e['cluster']}, {e['from']}]{was}")
    if result["overridden"]:
        print(f"! {_plural(len(result['overridden']), 'label')} already in the record "
              "changed — the replaced value is kept in the decision log")
    if result["unchanged"]:
        print(f"  {_plural(len(result['unchanged']), 'unit')} already carried the "
              "same verdict — nothing written for them")
    for s in result["skipped"]:
        print(f"  skipped: {s}")
    if result["skipped"]:
        print("  (this imports labels only — merges/splits made in Phy are not "
              "brought back)")
    for s in result["rejected"]:
        print(f"! not a verdict this workbench understands — {s}")
    if result["saved"]:
        print(result["record_path"])
        print(f"next step: python scripts/curation.py apply --sorter {sorter}")
    elif n and dry_run:
        print("--dry-run: the record was not written")
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
        "apply", help="replay the record onto the raw sort -> the run's curated/"))
    p_apply.add_argument("--out", default=None, help="write the curated result here "
                         "instead of the run's curated/")
    p_apply.add_argument("--n-jobs", type=int, default=1)
    p_export = _common(sub.add_parser(
        "export-phy", help="export the sort for Phy (the curated result when one exists)"))
    p_export.add_argument("--raw", action="store_true",
                          help="export the raw sort even when a curated result exists")
    p_export.add_argument("--out", default=None,
                          help="write the Phy folder here instead of the run's phy/")
    p_export.add_argument("--n-jobs", type=int, default=1)
    p_import = _common(sub.add_parser(
        "import-phy", help="import Phy's edited labels back into the record"))
    p_import.add_argument("--from", dest="folder", default=None,
                          help="the Phy folder to read (default: the run's phy/)")
    p_import.add_argument("--dry-run", action="store_true",
                          help="report what would change without writing the record")
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

    if args.cmd == "export-phy":
        try:
            result = export_phy(args.sorter, root, raw=args.raw, out_dir=args.out,
                                n_jobs=args.n_jobs)
        except Exception as e:  # noqa: BLE001 - one honest line, not a traceback
            print(f"export-phy failed: {e}", file=sys.stderr)
            return 1
        print(result["out"])
        return 0

    if args.cmd == "import-phy":
        try:
            result = import_phy_labels(args.sorter, folder=args.folder, root=root,
                                       dry_run=args.dry_run)
        except Exception as e:  # noqa: BLE001 - one honest line, not a traceback
            print(f"import-phy failed: {e}", file=sys.stderr)
            return 1
        return _report_import(result, args.sorter, dry_run=args.dry_run)

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
    """Match a --unit argument to a real unit id of this sort."""
    ids = record["curation"]["unit_ids"]
    uid = _match_unit(ids, text)
    if uid is None:
        raise ValueError(f"unit {text!r} is not in this sort ({ids})")
    return uid


if __name__ == "__main__":
    raise SystemExit(main())
