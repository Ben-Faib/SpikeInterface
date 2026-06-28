# Probe Geometry Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an editable, library-based probe-geometry layer that flows into the sort/report/GUI pipeline and softly re-ranks the sorter suggestions by geometry, with a one-time skippable first-run probe-setup prompt.

**Architecture:** A new `scripts/probes.py` is the single source of truth for probe geometry — shaped exactly like `scripts/sorters.py` (plain-data API, lazy `probeinterface`/`numpy` imports, never imported by the Textual process). `MenuController` (in `SpikeInterface_Menu.py`) wraps it and exposes plain dicts to the view. `run_sorting.py` gains `--probe`/`--probe-file` and applies the resolved probe after the analog-channel drop. The Textual app gains a PROBE banner line, a first-run `ProbeSetupScreen`, a `ProbeManagerScreen`/`ProbeEditorScreen`, and geometry-aware sorter badges. Persistence: built-in presets in code, user profiles in a git-ignored `probes.json`, the active-probe name + a `seen_probe_setup` flag in `.si_menu.json`.

**Tech Stack:** Python 3.12, `probeinterface` 0.3.2, `numpy`, `spikeinterface` (sort subprocess only), `textual` (TUI), `rich.text.Text`, `pytest` + `pytest-asyncio` (Pilot).

## Global Constraints

- **Python 3.12** only (`requires-python == "==3.12.*"`).
- **The Textual process imports NO SpikeInterface and NO probeinterface.** `scripts/menu_app.py` and `tests/conftest.py::FakeController` call controller methods that return plain data only. All `probeinterface`/`numpy`/SpikeInterface work lives in `scripts/probes.py`, `SpikeInterface_Menu.py` (the controller), `scripts/run_sorting.py`, or `scripts/report.py`.
- **`probeinterface` 0.3.2 API** (verified): `generate_linear_probe(num_elec, ypitch)`, `generate_multi_columns_probe(num_columns, num_contact_per_column, xpitch, ypitch)`, `generate_tetrode(r)`, `get_probe(manufacturer, probe_name)`, `read_probeinterface(path)`. Contact positions are the **attribute** `probe.contact_positions` (an `(N, ndim)` ndarray), **not** a method. `probe.get_contact_count()` exists.
- **Lazy heavy imports:** `import probeinterface` / `import numpy` happen *inside* `probes.py` functions, so `import probes` stays cheap (mirrors `blackrock_io`/`sorters`).
- **Every `probes.py` public function degrades gracefully (returns a safe default, never raises) EXCEPT `build()`,** which raises `ValueError` on a contact-count mismatch; callers catch it and show a friendly message.
- **`get_probe()` (the `library` kind) needs network.** Built-in presets are therefore all parametric/offline; the `library` kind + catalog are reached live and degrade to `[]`/`None` offline.
- **Persistence split:** built-ins in `probes.BUILTINS`; user profiles in git-ignored `probes.json` (`{"profiles":[...]}`); `active_probe` (str) + `seen_probe_setup` (bool) in `.si_menu.json` (controller-owned, via `_load_config`/`_save_config`).
- **Default active probe = `"independent"`** → behaviour identical to today (the placeholder dummy probe).
- **Test command:** `uv run python -m pytest tests/ -q`. Pure-logic tests monkeypatch like `tests/test_sorters.py`; UI tests use Pilot + `FakeController` like `tests/test_menu_app.py`.
- **Every git commit message ends with the trailer:**
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  Work happens on the worktree branch `worktree-probe-geometry`.

---

## Prior tactical work (superseded by this plan)

A separate session shipped a **tactical, hardcoded** fix in the **main checkout's
working tree** (`wordmark-crest`, **uncommitted**): `attach_a1x16_probe()` +
`A1X16_*` constants in `blackrock_io.py`, a `--probe {a1x16,independent}` enum in
`run_sorting.py`, the `sparse=False` analyzer fix, `"probe"` in `run_info.json`,
and a rebuilt `outputs/tridesclous2/analyzer/` (original at
`analyzer__indep_sparse_backup/`). It proved that **real A1x16 geometry + a dense
analyzer fixes the single-channel GUI**.

This plan is the **general, editable-library** version that subsumes it:
`probes.build(get("nnx-a1x16-3mm-100"), 16)` produces the *identical* geometry as
`attach_a1x16_probe`, and `--probe <profile-name>` generalizes the enum. The
**`sparse=False` fix is adopted** here (Task 4). Because the tactical edits are
uncommitted and live only in the main checkout (not this worktree), nothing needs
removing here — but when merging `worktree-probe-geometry` → `main`, **discard the
uncommitted `run_sorting.py`/`blackrock_io.py` tactical edits** (the general
feature replaces them); keep the rebuilt analyzer data (or re-sort to regenerate
it). The `wordmark-crest` commits are unrelated and stay.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `scripts/probes.py` | Probe library, geometry features, summary, `build()`, sorter fit. Source of truth. | **Create** |
| `tests/test_probes.py` | Hermetic unit tests for `probes.py`. | **Create** |
| `scripts/blackrock_io.py` | `attach_dummy_probe` stays; one comment tweak. | Modify |
| `scripts/run_sorting.py` | `--probe`/`--probe-file`; apply resolved probe after analog drop; `resolve_probe()`. | Modify |
| `tests/test_run_sorting.py` | `resolve_probe()` + `--probe` threading tests. | Modify |
| `SpikeInterface_Menu.py` | Controller probe API, `_catalog` fit/re-rank, `sort_command --probe`, report/traces probe, conditional caveat, `_ACTIONS` probe action, fallback parity. | Modify |
| `tests/test_menu_controller.py` | active-probe persistence + geometry-aware `_catalog`. | Modify |
| `scripts/report.py` | Apply active probe; conditional geometry caveat. | Modify |
| `scripts/menu_app.py` | PROBE banner, `ProbeSetupScreen`, `ProbeManagerScreen`, `ProbeEditorScreen`, fit badges/explain, `p` hotkey, probe action. | Modify |
| `tests/conftest.py` | `FakeController` gains probe methods + fit fields. | Modify |
| `tests/test_menu_probe.py` | Pilot tests for the probe UI. | **Create** |
| `scripts/ui.py` | `HELP_TOPICS` "Probe geometry" topic; fallback probe listing. | Modify |
| `.gitignore` | add `probes.json`. | Modify |
| `CLAUDE.md` | document the probe layer. | Modify |

---

## Phase 1 — `probes.py`: data model, store, geometry features

### Task 1: Probe profiles, persistence store, and geometry features

**Files:**
- Create: `scripts/probes.py`
- Create: `tests/test_probes.py`

**Interfaces:**
- Consumes: `blackrock_io.REPO_ROOT` (for the default `probes.json` path).
- Produces:
  - Constants `BUILTINS: list[dict]`, `DEFAULT_PROBE = "independent"`, `PROBES_PATH: Path`, `DENSE_MAX_UM = 60.0`, `INDEP_MIN_UM = 150.0`.
  - `builtins() -> list[dict]`
  - `user_profiles(path=PROBES_PATH) -> list[dict]`
  - `library(path=PROBES_PATH) -> list[dict]` (built-ins then user, deduped by name; built-in wins)
  - `get(name, path=PROBES_PATH) -> dict | None`
  - `save_profile(profile, path=PROBES_PATH) -> None` (upsert into the user store; never writes built-ins)
  - `delete_profile(name, path=PROBES_PATH) -> tuple[bool, str]` (user profiles only)
  - `duplicate(name, new_name, new_label=None, path=PROBES_PATH) -> dict`
  - `auto_sizes(profile) -> bool` (True only for `kind == "independent"`)
  - `contact_count(profile) -> int | None` (parametric kinds → int; `independent`/`library`/`file` → `None`)
  - `density_class(min_pitch_um) -> str` (`"dense"`/`"sparse"`/`"independent"`)
  - `geometry_features(profile) -> dict` (`{"n", "layout", "min_pitch_um", "density_class", "klass"}` where `layout ∈ {independent,linear,grid2d,tetrode,unknown}` and `klass ∈ {independent,tetrode,sparse,dense}`)
  - `summary(profile) -> str`

- [ ] **Step 1: Write the failing tests** — `tests/test_probes.py`:

```python
"""Hermetic unit tests for scripts/probes.py (no probeinterface/numpy needed for
the pure data-model + feature paths; build/catalog tests live separately)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import probes  # noqa: E402


def test_builtins_default_is_nnx_a1x16():
    bs = probes.builtins()
    assert bs[0]["name"] == "nnx-a1x16-3mm-100"          # this recording's real probe
    assert probes.DEFAULT_PROBE == "nnx-a1x16-3mm-100"
    assert probes.get("nnx-a1x16-3mm-100")["params"] == {"n": 16, "pitch_um": 100.0}
    assert any(p["name"] == "independent" for p in bs)   # placeholder still available
    # every built-in is flagged builtin and has the required keys
    for p in bs:
        assert p["builtin"] is True
        assert set(p) >= {"name", "label", "kind", "params", "builtin", "note"}


def test_library_merges_builtins_and_user(tmp_path):
    store = tmp_path / "probes.json"
    mine = {"name": "mine-8", "label": "Mine 8", "kind": "linear",
            "params": {"n": 8, "pitch_um": 40.0}, "builtin": False, "note": ""}
    probes.save_profile(mine, path=store)
    lib = probes.library(path=store)
    names = [p["name"] for p in lib]
    assert "independent" in names and "mine-8" in names
    assert probes.get("mine-8", path=store)["params"]["n"] == 8


def test_save_profile_roundtrips_and_upserts(tmp_path):
    store = tmp_path / "probes.json"
    p = {"name": "x", "label": "X", "kind": "linear",
         "params": {"n": 4, "pitch_um": 50.0}, "builtin": False, "note": ""}
    probes.save_profile(p, path=store)
    p2 = dict(p, label="X2")
    probes.save_profile(p2, path=store)        # upsert, not duplicate
    users = probes.user_profiles(path=store)
    assert [u["name"] for u in users] == ["x"]
    assert users[0]["label"] == "X2"
    # the on-disk file is the documented shape
    assert json.loads(store.read_text())["profiles"][0]["name"] == "x"


def test_delete_profile_user_only(tmp_path):
    store = tmp_path / "probes.json"
    probes.save_profile({"name": "y", "label": "Y", "kind": "linear",
                         "params": {"n": 4, "pitch_um": 50.0}, "builtin": False,
                         "note": ""}, path=store)
    ok, _ = probes.delete_profile("y", path=store)
    assert ok and probes.get("y", path=store) is None
    # built-ins are never deletable
    ok2, msg = probes.delete_profile("independent", path=store)
    assert ok2 is False and "built-in" in msg.lower()


def test_geometry_features_classes():
    # independent default -> independent class (250 um column, no sharing)
    f = probes.geometry_features(probes.get("independent"))
    assert f["layout"] == "independent" and f["klass"] == "independent"
    # a 100 um linear -> sparse; a 25 um linear -> dense
    assert probes.density_class(100.0) == "sparse"
    assert probes.density_class(25.0) == "dense"
    assert probes.density_class(400.0) == "independent"
    # tetrode -> tetrode class regardless of within-pitch
    tet = {"name": "t", "label": "t", "kind": "tetrode",
           "params": {"n_tetrodes": 4, "within_um": 25.0, "between_um": 300.0},
           "builtin": False, "note": ""}
    assert probes.geometry_features(tet)["klass"] == "tetrode"
    assert probes.contact_count(tet) == 16


def test_contact_count_and_auto_sizes():
    assert probes.auto_sizes(probes.get("independent")) is True
    assert probes.contact_count(probes.get("independent")) is None
    grid = {"name": "g", "label": "g", "kind": "grid",
            "params": {"rows": 8, "cols": 4, "xpitch_um": 50.0, "ypitch_um": 50.0},
            "builtin": False, "note": ""}
    assert probes.contact_count(grid) == 32


def test_summary_is_human_text():
    s = probes.summary(probes.get("nnx-a1x16-3mm-100"))
    assert "16" in s and "µm" in s


def test_default_probe_is_sparse_not_independent():
    # 100 µm pitch -> 'sparse' class (so dense-only sorters aren't recommended, and
    # tridesclous2 stays the geometry-aware default for this recording).
    f = probes.geometry_features(probes.get(probes.DEFAULT_PROBE))
    assert f["klass"] == "sparse" and f["layout"] == "linear"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/benfaib/Spike/SpikeInterface/.claude/worktrees/probe-geometry && uv run python -m pytest tests/test_probes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'probes'`.

- [ ] **Step 3: Create `scripts/probes.py` (data model + store + features)**

```python
"""Probe-geometry registry — the single source of truth for electrode geometry.

Like ``scripts/sorters.py`` this module returns plain Python data and imports the
heavy libraries (``probeinterface``/``numpy``) lazily, so importing it is cheap and
the Textual menu can stay free of probeinterface/SpikeInterface. The Blackrock
files carry no geometry, so geometry is a *user choice*: a library of profiles
(built-in presets + user-editable ones), one of which is "active" at a time.

    import probes
    probes.library()                 # all profiles (built-in + user), ordered
    probes.geometry_features(p)       # {n, layout, min_pitch_um, density_class, klass}
    probes.build(p, n_channels)       # -> probeinterface.Probe (raises on mismatch)
    probes.fit("herdingspikes", p)    # {rank, reason} for a sorter on geometry p
"""
from __future__ import annotations

import json
from pathlib import Path

import blackrock_io as bio

# Active-probe default + the user-profile store (git-ignored, like .si_menu.json).
# The default is THIS recording's real probe (confirmed: channels raw 1–16 = a
# NeuroNexus A1x16-3mm-100-703; analog 1–6 are aux and dropped before sorting).
DEFAULT_PROBE = "nnx-a1x16-3mm-100"
PROBES_PATH = bio.REPO_ROOT / "probes.json"
# Kept as a constant so the placeholder is still addressable by name everywhere.
PLACEHOLDER_PROBE = "independent"

# Density boundaries (µm). dense: real waveform sharing; independent: none.
DENSE_MAX_UM = 60.0
INDEP_MIN_UM = 150.0


def _profile(name, label, kind, params, note=""):
    return {"name": name, "label": label, "kind": kind, "params": params,
            "builtin": True, "note": note}


# Built-in presets (ordered; the real default first, then the placeholder, then
# standards). All parametric so they build offline (the probeinterface catalog
# needs network — see build()). The A1x16-3mm-100-703 IS this recording's probe
# (channels raw 1–16); a 100 µm pitch is the 'sparse' class, so the geometry-aware
# default sorter stays tridesclous2. The single-shank identity mapping (contact i ↔
# raw i) gives the correct 16-site × 100 µm linear geometry; users who want the
# exact NeuroNexus site permutation can add the catalog (library-kind) probe.
BUILTINS = [
    _profile("nnx-a1x16-3mm-100", "NeuroNexus A1x16-3mm-100-703 · 16 ch @ 100 µm",
             "linear", {"n": 16, "pitch_um": 100.0},
             "This recording's probe: NeuroNexus A1x16-3mm-100-703 "
             "(1 shank, 16 sites, 100 µm pitch, ~30 µm contacts) on channels raw 1–16."),
    _profile("independent", "Independent channels (placeholder)", "independent",
             {"pitch_um": 250.0},
             "No real geometry — channels treated as independent (the old default; "
             "use when a recording's probe is unknown)."),
    _profile("linear-16-50um", "Linear · 16 ch @ 50 µm", "linear",
             {"n": 16, "pitch_um": 50.0}, "Single-shank dense linear array."),
    _profile("linear-32-25um", "Linear · 32 ch @ 25 µm", "linear",
             {"n": 32, "pitch_um": 25.0}, "Dense 32-site shank."),
    _profile("tetrode-4", "Tetrodes · 4 × 4 ch", "tetrode",
             {"n_tetrodes": 4, "within_um": 25.0, "between_um": 300.0},
             "Four tetrodes (16 ch)."),
    _profile("grid-8x4-50um", "Grid · 8 × 4 @ 50 µm", "grid",
             {"rows": 8, "cols": 4, "xpitch_um": 50.0, "ypitch_um": 50.0},
             "Generic dense 2-D grid."),
    _profile("utah-10x10-400um", "Utah array · 10 × 10 @ 400 µm", "grid",
             {"rows": 10, "cols": 10, "xpitch_um": 400.0, "ypitch_um": 400.0},
             "Blackrock Utah array — at 400 µm contacts are electrically independent."),
    _profile("cui-flexible-16-300um", "Cui flexible MEA · 16 ch @ 300 µm", "linear",
             {"n": 16, "pitch_um": 300.0},
             "Cui-lab custom flexible polyimide array (effectively independent)."),
    _profile("cui-transparent-4x4-200um", "Cui transparent MEA · 4 × 4 @ 200 µm",
             "grid", {"rows": 4, "cols": 4, "xpitch_um": 200.0, "ypitch_um": 200.0},
             "Cui-lab transparent MEA for ephys + 2-photon."),
]


def builtins() -> list[dict]:
    """The built-in presets (fresh copies so callers can't mutate the constants)."""
    return [dict(p, params=dict(p["params"])) for p in BUILTINS]


# --------------------------------------------------------------------------- #
# User-profile store (probes.json)
# --------------------------------------------------------------------------- #
def _load_store(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("profiles"), list):
            return data
    except Exception:  # noqa: BLE001 - missing/corrupt -> empty
        pass
    return {"profiles": []}


def _save_store(store, path) -> None:
    try:
        Path(path).write_text(json.dumps(store, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - best-effort
        pass


def user_profiles(path=PROBES_PATH) -> list[dict]:
    """User-created/edited profiles from probes.json (each flagged builtin=False)."""
    out = []
    for p in _load_store(path)["profiles"]:
        if isinstance(p, dict) and p.get("name"):
            out.append(dict(p, builtin=False))
    return out


def library(path=PROBES_PATH) -> list[dict]:
    """Built-ins then user profiles, deduped by name (a built-in name wins)."""
    seen = set()
    out = []
    for p in builtins() + user_profiles(path):
        if p["name"] in seen:
            continue
        seen.add(p["name"])
        out.append(p)
    return out


def get(name, path=PROBES_PATH) -> "dict | None":
    return next((p for p in library(path) if p["name"] == name), None)


def _is_builtin(name) -> bool:
    return any(p["name"] == name for p in BUILTINS)


def save_profile(profile, path=PROBES_PATH) -> None:
    """Upsert a user profile into probes.json (built-in names are stored as user
    copies — callers should rename a built-in before saving; see duplicate())."""
    store = _load_store(path)
    rec = {"name": profile["name"], "label": profile.get("label", profile["name"]),
           "kind": profile["kind"], "params": dict(profile.get("params", {})),
           "builtin": False, "note": profile.get("note", "")}
    profiles = [p for p in store["profiles"] if p.get("name") != rec["name"]]
    profiles.append(rec)
    store["profiles"] = profiles
    _save_store(store, path)


def delete_profile(name, path=PROBES_PATH) -> "tuple[bool, str]":
    if _is_builtin(name):
        return False, f"{name} is a built-in profile and can't be deleted (duplicate it to edit)."
    store = _load_store(path)
    before = len(store["profiles"])
    store["profiles"] = [p for p in store["profiles"] if p.get("name") != name]
    if len(store["profiles"]) == before:
        return False, f"No saved probe named {name}."
    _save_store(store, path)
    return True, f"Deleted probe {name}."


def duplicate(name, new_name, new_label=None, path=PROBES_PATH) -> dict:
    """Copy a profile (built-in or user) to a new editable user profile."""
    src = get(name, path) or get(DEFAULT_PROBE)
    dup = {"name": new_name, "label": new_label or f"{src['label']} (copy)",
           "kind": src["kind"], "params": dict(src["params"]),
           "builtin": False, "note": src.get("note", "")}
    save_profile(dup, path)
    return dup


# --------------------------------------------------------------------------- #
# Geometry introspection (analytic for parametric kinds; no probeinterface)
# --------------------------------------------------------------------------- #
def auto_sizes(profile) -> bool:
    """True iff the profile resizes to the recording (only ``independent``)."""
    return profile.get("kind") == "independent"


def contact_count(profile) -> "int | None":
    """Fixed contact count for parametric kinds; None for auto/unknown kinds."""
    k, p = profile.get("kind"), profile.get("params", {})
    if k == "linear":
        return int(p.get("n", 0))
    if k == "grid":
        return int(p.get("rows", 0)) * int(p.get("cols", 0))
    if k == "tetrode":
        return int(p.get("n_tetrodes", 0)) * 4
    return None  # independent (auto), library/file (unknown until built)


def density_class(min_pitch_um) -> str:
    if min_pitch_um is None:
        return "sparse"
    if min_pitch_um <= DENSE_MAX_UM:
        return "dense"
    if min_pitch_um >= INDEP_MIN_UM:
        return "independent"
    return "sparse"


def geometry_features(profile) -> dict:
    """{n, layout, min_pitch_um, density_class, klass}. Analytic for parametric
    kinds; library/file return a neutral 'unknown' feature set (no network)."""
    k, p = profile.get("kind"), profile.get("params", {})
    if k == "independent":
        pitch = float(p.get("pitch_um", 250.0))
        return {"n": None, "layout": "independent", "min_pitch_um": pitch,
                "density_class": density_class(pitch), "klass": "independent"}
    if k == "linear":
        pitch = float(p.get("pitch_um", 50.0))
        return {"n": int(p.get("n", 0)), "layout": "linear", "min_pitch_um": pitch,
                "density_class": density_class(pitch), "klass": density_class(pitch)}
    if k == "grid":
        pitch = min(float(p.get("xpitch_um", 50.0)), float(p.get("ypitch_um", 50.0)))
        return {"n": contact_count(profile), "layout": "grid2d", "min_pitch_um": pitch,
                "density_class": density_class(pitch), "klass": density_class(pitch)}
    if k == "tetrode":
        within = float(p.get("within_um", 25.0))
        return {"n": contact_count(profile), "layout": "tetrode", "min_pitch_um": within,
                "density_class": density_class(within), "klass": "tetrode"}
    # library / file: unknown without building -> neutral sparse class.
    return {"n": None, "layout": "unknown", "min_pitch_um": None,
            "density_class": "sparse", "klass": "sparse"}


def summary(profile) -> str:
    """Human one-liner: '16 contacts · linear · 50 µm pitch'. Never raises."""
    f = geometry_features(profile)
    n = f["n"]
    layout = {"independent": "independent channels", "linear": "linear",
              "grid2d": "2-D grid", "tetrode": "tetrodes",
              "unknown": profile.get("kind", "probe")}[f["layout"]]
    bits = []
    if profile.get("kind") == "independent":
        bits.append("auto-sizes to the recording")
    elif n:
        bits.append(f"{n} contacts")
    bits.append(layout)
    if f["min_pitch_um"]:
        bits.append(f"{f['min_pitch_um']:g} µm pitch")
    return " · ".join(bits)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_probes.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/probes.py tests/test_probes.py
git commit -m "feat(probes): probe-profile library, store, and geometry features

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — `probes.py`: probe construction + sorter fit

### Task 2: `build()` — construct a probeinterface.Probe from a profile

**Files:**
- Modify: `scripts/probes.py`
- Modify: `tests/test_probes.py`

**Interfaces:**
- Consumes: `geometry_features`, `contact_count`, `auto_sizes` (Task 1).
- Produces:
  - `build(profile, n_channels) -> "probeinterface.Probe"` — sets device-channel indices `0..n-1`; raises `ValueError` on a contact-count mismatch (for fixed-count kinds) with a clear message.
  - `catalog_manufacturers() -> list[str]` and `catalog_models(manufacturer) -> list[str]` — live probeinterface catalog, `[]` on any failure (offline).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_probes.py`:

```python
def test_build_independent_autosizes():
    probe = probes.build(probes.get("independent"), 22)
    assert probe.get_contact_count() == 22


def test_build_linear_matches_count():
    probe = probes.build(probes.get("linear-16-50um"), 16)
    assert probe.get_contact_count() == 16
    import numpy as np
    ys = sorted(probe.contact_positions[:, 1])
    assert np.isclose(ys[1] - ys[0], 50.0)


def test_build_grid_count():
    probe = probes.build(probes.get("grid-8x4-50um"), 32)
    assert probe.get_contact_count() == 32


def test_build_tetrode_count():
    probe = probes.build(probes.get("tetrode-4"), 16)
    assert probe.get_contact_count() == 16


def test_build_mismatch_raises():
    with pytest.raises(ValueError) as e:
        probes.build(probes.get("linear-16-50um"), 22)
    assert "16" in str(e.value) and "22" in str(e.value)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_probes.py -k build -q`
Expected: FAIL — `AttributeError: module 'probes' has no attribute 'build'`.

- [ ] **Step 3: Append `build()` + catalog helpers to `scripts/probes.py`**

```python
# --------------------------------------------------------------------------- #
# Construction (lazy probeinterface / numpy)
# --------------------------------------------------------------------------- #
def _require_count(profile, n_channels) -> None:
    want = contact_count(profile)
    if want is not None and want != n_channels:
        raise ValueError(
            f"Probe '{profile['name']}' has {want} contacts but the recording has "
            f"{n_channels} channels. Pick a matching probe (or 'independent', which "
            "auto-sizes), or edit this probe's contact count.")


def build(profile, n_channels):
    """Build a probeinterface.Probe for ``profile`` sized to ``n_channels``.

    Sets identity device-channel indices (contact i ↔ channel i), matching the old
    attach_dummy_probe. Raises ValueError on a fixed-count mismatch.
    """
    import numpy as np
    import probeinterface as pi

    _require_count(profile, n_channels)
    k, p = profile["kind"], profile.get("params", {})

    if k in ("independent", "linear"):
        pitch = float(p.get("pitch_um", 250.0 if k == "independent" else 50.0))
        n = n_channels if k == "independent" else int(p["n"])
        probe = pi.generate_linear_probe(num_elec=n, ypitch=pitch)
    elif k == "grid":
        probe = pi.generate_multi_columns_probe(
            num_columns=int(p["cols"]), num_contact_per_column=int(p["rows"]),
            xpitch=float(p["xpitch_um"]), ypitch=float(p["ypitch_um"]))
    elif k == "tetrode":
        within, between = float(p["within_um"]), float(p["between_um"])
        offs = np.array([[0, 0], [within, 0], [0, within], [within, within]], dtype=float)
        pos = np.vstack([offs + [t * between, 0.0] for t in range(int(p["n_tetrodes"]))])
        probe = pi.Probe(ndim=2)
        probe.set_contacts(positions=pos, shapes="circle", shape_params={"radius": 5})
        probe.create_auto_shape("tip")
    elif k == "library":
        probe = pi.get_probe(p["manufacturer"], p["model"])
    elif k == "file":
        group = pi.read_probeinterface(p["path"])
        probe = group.probes[0]
    else:
        raise ValueError(f"Unknown probe kind: {k!r}")

    # library/file can carry their own count; validate now that it's known.
    if probe.get_contact_count() != n_channels:
        raise ValueError(
            f"Probe '{profile['name']}' built {probe.get_contact_count()} contacts "
            f"but the recording has {n_channels} channels.")
    probe.set_device_channel_indices(np.arange(n_channels))
    return probe


def catalog_manufacturers() -> list[str]:
    """probeinterface library manufacturers (network); [] on any failure."""
    try:
        from probeinterface.library import probe_dict  # type: ignore
        return sorted(probe_dict().keys())
    except Exception:  # noqa: BLE001 - older/newer layout or offline
        return ["neuronexus", "cambridgeneurotech"]


def catalog_models(manufacturer) -> list[str]:
    try:
        from probeinterface.library import probe_dict  # type: ignore
        return sorted(probe_dict().get(manufacturer, {}).keys())
    except Exception:  # noqa: BLE001
        return []
```

> Note: `probeinterface.library.probe_dict` may not exist in 0.3.2; the `except` returns sensible fallbacks so the catalog never crashes. The `library` kind always works at `build()` time via `get_probe` (network) regardless of the dict helper.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_probes.py -k build -q`
Expected: PASS (5 build tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/probes.py tests/test_probes.py
git commit -m "feat(probes): build() constructs probes from profiles; catalog helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3: Sorter fit scoring

**Files:**
- Modify: `scripts/probes.py`
- Modify: `tests/test_probes.py`

**Interfaces:**
- Consumes: `geometry_features` (Task 1).
- Produces:
  - `fit(name, profile) -> dict` → `{"rank": "good"|"ok"|"poor", "reason": str}`.
  - `ranked(names, profile) -> list[dict]` → `[{"name","rank","reason"}]`, stable-sorted good→ok→poor by the input order.
  - `recommended_for(profile, runnable_names) -> str | None` — the top good-fit runnable sorter (None if none good).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_probes.py`:

```python
def test_fit_independent_favours_tridesclous_over_herdingspikes():
    indep = probes.get("independent")
    assert probes.fit("tridesclous2", indep)["rank"] == "good"
    assert probes.fit("herdingspikes", indep)["rank"] == "poor"
    assert "reason" in probes.fit("herdingspikes", indep)


def test_fit_dense_favours_dense_sorters():
    dense = probes.get("linear-32-25um")          # 25 µm -> dense
    assert probes.fit("spykingcircus2", dense)["rank"] == "good"
    assert probes.fit("herdingspikes", dense)["rank"] == "good"
    assert probes.fit("waveclus", dense)["rank"] == "poor"


def test_fit_tetrode_favours_low_count_sorters():
    tet = probes.get("tetrode-4")
    assert probes.fit("mountainsort4", tet)["rank"] == "good"
    assert probes.fit("waveclus", tet)["rank"] == "good"
    assert probes.fit("kilosort4", tet)["rank"] == "poor"


def test_ranked_orders_good_first_and_recommends():
    indep = probes.get("independent")
    names = ["herdingspikes", "tridesclous2", "spykingcircus2"]
    order = [r["name"] for r in probes.ranked(names, indep)]
    assert order[0] == "tridesclous2" and order[-1] == "herdingspikes"
    assert probes.recommended_for(indep, ["spykingcircus2", "tridesclous2"]) == "tridesclous2"
    # no good-fit runnable -> None (caller falls back to RECOMMENDED)
    assert probes.recommended_for(probes.get("linear-32-25um"), ["waveclus"]) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_probes.py -k fit -q`
Expected: FAIL — `AttributeError: module 'probes' has no attribute 'fit'`.

- [ ] **Step 3: Append the fit engine to `scripts/probes.py`**

```python
# --------------------------------------------------------------------------- #
# Sorter fit (geometry -> which sorters suit it). Backs the soft re-rank.
# Classes: independent | tetrode | sparse | dense (see the design's fit table).
# --------------------------------------------------------------------------- #
_RANKS = {"good": 0, "ok": 1, "poor": 2}
_DEFAULT_FIT = {"independent": "ok", "tetrode": "ok", "sparse": "ok", "dense": "ok"}
_FIT = {
    "tridesclous2":   {"independent": "good", "tetrode": "good", "sparse": "good", "dense": "ok"},
    "tridesclous":    {"independent": "good", "tetrode": "good", "sparse": "ok",   "dense": "ok"},
    "mountainsort4":  {"independent": "good", "tetrode": "good", "sparse": "good", "dense": "ok"},
    "mountainsort5":  {"independent": "ok",   "tetrode": "ok",   "sparse": "good", "dense": "good"},
    "spykingcircus2": {"independent": "ok",   "tetrode": "ok",   "sparse": "good", "dense": "good"},
    "spykingcircus":  {"independent": "ok",   "tetrode": "ok",   "sparse": "ok",   "dense": "ok"},
    "waveclus":       {"independent": "good", "tetrode": "good", "sparse": "ok",   "dense": "poor"},
    "combinato":      {"independent": "good", "tetrode": "good", "sparse": "ok",   "dense": "poor"},
    "herdingspikes":  {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "ironclust":      {"independent": "poor", "tetrode": "poor", "sparse": "ok",   "dense": "good"},
    "hdsort":         {"independent": "poor", "tetrode": "poor", "sparse": "ok",   "dense": "good"},
    "kilosort4":      {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "kilosort3":      {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "kilosort2_5":    {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "kilosort2":      {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "kilosort":       {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "pykilosort":     {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "yass":           {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
}
_FIT_NOTE = {
    "tridesclous2": "general-purpose, robust at low channel counts",
    "tridesclous": "tetrode-oriented legacy sorter",
    "mountainsort4": "isolation clustering, best at low channel counts",
    "mountainsort5": "density clustering, scales to many channels",
    "spykingcircus2": "template matching, strong on dense arrays",
    "spykingcircus": "legacy template matching",
    "waveclus": "wavelet clustering for single channels / tetrodes",
    "combinato": "single-unit clustering for sparse / long recordings",
    "herdingspikes": "needs dense neighbours (poor above ~60 µm)",
    "ironclust": "density-based, built for high-density arrays",
    "hdsort": "dense-array sorter",
    "kilosort4": "template matching, built for dense probes (≤~40 µm)",
}
_KLASS_LABEL = {"independent": "independent channels", "tetrode": "tetrodes",
                "sparse": "low-density geometry", "dense": "high-density arrays"}


def fit(name, profile) -> dict:
    """{rank, reason} for sorter ``name`` on geometry ``profile``."""
    klass = geometry_features(profile)["klass"]
    rank = _FIT.get(name, _DEFAULT_FIT)[klass]
    note = _FIT_NOTE.get(name, "")
    label = _KLASS_LABEL[klass]
    if note:
        reason = f"{note}; {rank} fit for {label}."
    else:
        reason = f"{rank} fit for {label}."
    return {"rank": rank, "reason": reason[0].upper() + reason[1:]}


def ranked(names, profile) -> list[dict]:
    """Sorters annotated with fit, stable-sorted good→ok→poor (input order breaks ties)."""
    rows = [dict(name=n, **fit(n, profile)) for n in names]
    return sorted(rows, key=lambda r: _RANKS[r["rank"]])


def recommended_for(profile, runnable_names, prefer=None) -> "str | None":
    """Top good-fit runnable sorter for ``profile``; None if none rank 'good'.

    ``prefer`` (e.g. ``sorters.RECOMMENDED``) wins when it is runnable AND a good
    fit, so the established default is kept whenever geometry doesn't argue against
    it (e.g. the 100 µm 'sparse' A1x16 keeps tridesclous2)."""
    names = list(runnable_names)
    if prefer in names and fit(prefer, profile)["rank"] == "good":
        return prefer
    for r in ranked(names, profile):
        if r["rank"] == "good":
            return r["name"]
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_probes.py -q`
Expected: PASS (all Task 1–3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/probes.py tests/test_probes.py
git commit -m "feat(probes): geometry-driven sorter fit scoring (fit/ranked/recommended_for)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Sort pipeline: apply the probe

### Task 4: `run_sorting.py --probe` / `--probe-file`

**Files:**
- Modify: `scripts/run_sorting.py` (argparse `:714-755`; recording build `:819`/`:830-838`; add `resolve_probe`)
- Modify: `scripts/blackrock_io.py:835`-context (comment only) — no behaviour change there
- Modify: `tests/test_run_sorting.py`

**Interfaces:**
- Consumes: `probes.get`, `probes.build`, `probes.DEFAULT_PROBE` (Tasks 1–2).
- Produces: a CLI where `--probe <name>` resolves a library profile and `--probe-file <path>` builds a `file`-kind profile; the resolved probe is applied to the recording **after** the analog-channel drop. New helper `resolve_probe(name, probe_file) -> dict`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_run_sorting.py`:

```python
def test_resolve_probe_defaults_to_active_default():
    import run_sorting, probes
    p = run_sorting.resolve_probe(None, None)
    assert p["name"] == probes.DEFAULT_PROBE == "nnx-a1x16-3mm-100"
    assert p["kind"] == "linear"


def test_resolve_probe_named():
    import run_sorting
    p = run_sorting.resolve_probe("linear-16-50um", None)
    assert p["kind"] == "linear" and p["params"]["n"] == 16


def test_resolve_probe_file():
    import run_sorting
    p = run_sorting.resolve_probe(None, "/tmp/x.json")
    assert p["kind"] == "file" and p["params"]["path"] == "/tmp/x.json"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_run_sorting.py -k probe -q`
Expected: FAIL — `AttributeError: module 'run_sorting' has no attribute 'resolve_probe'`.

- [ ] **Step 3: Add the CLI flags + `resolve_probe`, and apply the probe**

In `scripts/run_sorting.py`, after the `--params-file` argument (around line 728) add:

```python
    parser.add_argument("--probe", default=None,
                        help="Probe-geometry profile name from the library "
                             "(default: the active profile, else 'independent').")
    parser.add_argument("--probe-file", default=None,
                        help="A probeinterface JSON file to use as the probe geometry.")
```

Add the resolver near `resolve_overrides` (module level):

```python
def resolve_probe(name, probe_file):
    """Resolve --probe/--probe-file to a probe profile dict.

    --probe-file wins (a one-off file profile); else a named library profile; else
    the 'independent' placeholder (today's behaviour)."""
    import probes

    if probe_file:
        return {"name": "file", "label": probe_file, "kind": "file",
                "params": {"path": probe_file}, "builtin": False, "note": ""}
    return probes.get(name) if name else probes.get(probes.DEFAULT_PROBE)
```

In `main()`, after `overrides = resolve_overrides(...)` (line 775) add:

```python
    probe_profile = resolve_probe(args.probe, args.probe_file)
```

Replace the analog-drop re-attach block (lines 830-838) so the resolved probe is applied after the drop. Change line 819 read to skip the dummy probe, and apply the profile after dropping analog channels:

```python
    rec = bio.read_broadband(args.data_dir, attach_probe=False)  # probe applied below
```

then replace the `if not args.keep_analog:` block body with:

```python
    if not args.keep_analog:
        neural = bio.neural_channel_ids(rec)
        n_dropped = rec.get_num_channels() - len(neural)
        if 0 < len(neural) < rec.get_num_channels():
            rec = bio.select_channels(rec, neural)
            _drop_msg = (f"excluded {n_dropped} non-neural analog aux channel(s) → "
                         f"sorting {len(neural)} electrode(s)")
            ui.detail(_drop_msg)

    # Apply the chosen probe geometry to the kept neural channels. 'independent'
    # reproduces the old placeholder; a real profile gives physical geometry. An
    # EXPLICIT --probe/--probe-file that doesn't fit is an error; the DEFAULT probe
    # not fitting (e.g. a different recording) falls back to the placeholder so a
    # default run never hard-fails on geometry.
    import probes
    explicit = bool(args.probe or args.probe_file)
    try:
        rec = rec.set_probe(probes.build(probe_profile, rec.get_num_channels()))
        _probe_msg = f"probe geometry: {probe_profile.get('label', probe_profile.get('name'))}"
    except Exception as e:  # noqa: BLE001 - bad geometry / count mismatch
        if explicit:
            ui.warn(f"Probe '{probe_profile.get('name', '?')}' couldn't be applied: {e}")
            rep.error(str(e))
            return 1
        rec = bio.attach_dummy_probe(rec)
        probe_profile = probes.get(probes.PLACEHOLDER_PROBE)
        _probe_msg = (f"default probe didn't match this recording ({e}) — using the "
                      "independent-channel placeholder; pass --probe to set geometry.")
        ui.warn(_probe_msg)
    ui.detail(_probe_msg)
    rep.detail(_probe_msg)
```

(Delete the old `rec = bio.attach_dummy_probe(rec)` re-attach line — the probe is now applied unconditionally here.)

In `scripts/blackrock_io.py`, update the `attach_dummy_probe` docstring's "swap in" sentence to point at the new module (comment-only, around line 184):

```python
    To swap in real geometry, build a probe with ``probes.build(profile, n)`` (or a
    raw ``probeinterface.Probe``) and call ``recording.set_probe(...)`` instead.
```

Also build the **`SortingAnalyzer` dense (`sparse=False`)** — a proven fix from
prior tactical work. SpikeInterface defaults to `sparse=True`, which keeps only
channels within ~100 µm of each unit's peak; with the old 250 µm placeholder probe
that collapsed every unit to a single channel, so `spikeinterface-gui` could only
ever show one site per unit. Dense is cheap for this 16-channel array and always
shows the full layout. Find the `si.create_sorting_analyzer(...)` call in `main()`
(`run_sorting.py:~939`) and add `sparse=False`:

```python
            analyzer = si.create_sorting_analyzer(
                sorting, rec, folder=str(out / "analyzer"), format="binary_folder",
                overwrite=True, sparse=False,
            )
```

And record the probe in `run_info.json` for provenance — in `_write_run_info`'s
payload (`run_sorting.py:~403`) add `"probe": getattr(args, "probe", None),`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_run_sorting.py -q`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Smoke-test the pipeline wiring end-to-end (no real data needed for the resolver path; verify import)**

Run: `uv run python -c "import sys; sys.path.insert(0,'scripts'); import run_sorting; print(run_sorting.resolve_probe('cui-neuronexus-a1x16-100um', None)['kind'])"`
Expected: prints `linear`.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_sorting.py scripts/blackrock_io.py tests/test_run_sorting.py
git commit -m "feat(sort): --probe/--probe-file apply real probe geometry before sorting

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Controller: probe state, catalog fit, sort wiring

### Task 5: Controller probe API + config persistence + sort_command

**Files:**
- Modify: `SpikeInterface_Menu.py` (imports `:43-46`; `MenuController.__init__` `:687-706`; `reload` `:745-758`; `sort_command` `:924-937`; add probe methods)
- Modify: `tests/test_menu_controller.py`

**Interfaces:**
- Consumes: `probes.*` (Tasks 1–3).
- Produces (on `MenuController`):
  - attrs `self.active_probe: str`, `self.want_probe_setup: bool`, `self.probe_info: dict` (set in `reload`).
  - `set_active_probe(name) -> bool`
  - `probe_catalog() -> list[dict]` (rows: `name,label,kind,builtin,active,summary,n,density_class,layout,auto,match,match_detail`)
  - `active_probe_info() -> dict` (`name,label,summary,layout,density_class,match,match_detail`)
  - `recording_channels() -> int | None`
  - `save_probe(profile) -> tuple[bool,str]`, `delete_probe(name) -> tuple[bool,str]`, `duplicate_probe(name,new_name,new_label=None) -> dict`
  - `mark_probe_setup_seen() -> None`
  - `sorter_fit(name) -> dict` (`{rank,reason}` for the active probe)
  - `sort_command(span)` now appends `--probe <active_probe>`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_menu_controller.py`:

```python
def test_active_probe_defaults_to_nnx_a1x16(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    assert c.active_probe == "nnx-a1x16-3mm-100"        # this recording's real probe
    assert c.active_probe_info()["name"] == "nnx-a1x16-3mm-100"


def test_active_probe_honours_saved_cfg(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={"active_probe": "independent"})
    assert c.active_probe == "independent"


def test_set_active_probe_persists(monkeypatch, tmp_path):
    saved = {}
    monkeypatch.setattr(M, "_save_config", lambda cfg: saved.update(cfg))
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    assert c.set_active_probe("linear-16-50um") is True
    assert c.active_probe == "linear-16-50um"
    assert saved.get("active_probe") == "linear-16-50um"


def test_sort_command_includes_probe(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    c.set_active_probe("linear-16-50um")
    argv = c.sort_command(None)
    assert "--probe" in argv and "linear-16-50um" in argv


def test_probe_catalog_marks_active_and_match(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    rows = c.probe_catalog()
    default = next(r for r in rows if r["name"] == "nnx-a1x16-3mm-100")
    assert default["active"] is True
    indep = next(r for r in rows if r["name"] == "independent")
    assert indep["auto"] is True and indep["active"] is False
```

> `_controller(...)` is the existing helper in `tests/test_menu_controller.py` (builds a real `MenuController` with `report._gather` monkeypatched and `_save_config` stubbed). `report._gather` is patched to return a broadband row whose detail contains a channel count, so `recording_channels()` has something to parse.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_controller.py -k probe -q`
Expected: FAIL — `AttributeError: 'MenuController' object has no attribute 'active_probe'`.

- [ ] **Step 3: Wire the controller**

Add the import next to the others (after line 45):

```python
import probes  # noqa: E402  (probe-geometry registry: profiles/features/build/fit)
```

In `MenuController.__init__`, after the `self.want_welcome = ...` line (704) add:

```python
        self.active_probe = cfg.get("active_probe", probes.DEFAULT_PROBE)
        if probes.get(self.active_probe) is None:
            self.active_probe = probes.DEFAULT_PROBE
        self.want_probe_setup = not bool(cfg.get("seen_probe_setup", False))
```

In `reload()`, after `self.data_report = _data_report(...)` (758) add:

```python
        self.probe_info = self.active_probe_info()
```

Add these methods to `MenuController` (e.g. after `mark_welcome_seen`):

```python
    # -- probe geometry -------------------------------------------------------- #
    def recording_channels(self) -> "int | None":
        """Best-effort broadband channel count, parsed from the pipeline detail.
        Advisory only — the real count is validated by probes.build at sort time."""
        import re
        bb = next((r for r in self.pipeline if "Broadband" in r.get("stage", "")), None)
        if not bb or bb.get("status") == "FAIL":
            return None
        m = re.search(r"(\d+)\s*(?:ch|channel)", bb.get("detail", ""))
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
```

In `sort_command`, after the `--data-dir` block (933) add:

```python
        argv += ["--probe", self.active_probe]
```

Also thread the probe into the `run()`/`action_sort` CLI path: in `run()` (`:949`) under `if key == "sort":` add `self.args.probe = self.active_probe`, and in `action_sort` (`:326`) add `if getattr(args, "probe", None): flags += ["--probe", args.probe]`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SpikeInterface_Menu.py tests/test_menu_controller.py
git commit -m "feat(menu): controller probe API, persistence, and sort_command --probe

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6: Geometry-aware sorter catalog (fit + re-rank + recommended)

**Files:**
- Modify: `SpikeInterface_Menu.py` (`_catalog` `:163-203`; `reload` `:745-758`)
- Modify: `tests/test_menu_controller.py`

**Interfaces:**
- Consumes: `probes.fit`, `probes.ranked`, `probes.recommended_for`, `self.active_probe`, `sorter_registry.runnable`, `sorter_registry.RECOMMENDED`.
- Produces: each catalog `info` gains `"fit": {"rank","reason"}`; `info["recommended"]` is the **geometry-aware** default (top good-fit runnable, else `RECOMMENDED`); members are re-ranked within each group (good→ok→poor, then name).

- [ ] **Step 1: Write the failing test** — append to `tests/test_menu_controller.py`:

```python
def test_catalog_has_fit_and_reranks_for_dense_probe(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=True, cfg={})
    c.set_active_probe("independent")
    # independent -> tridesclous2 is the recommended (good) default
    td = next(i for i in c.infos if i["name"] == "tridesclous2")
    assert "fit" in td and td["fit"]["rank"] == "good"
    assert td["recommended"] is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_menu_controller.py -k fit -q`
Expected: FAIL — `KeyError: 'fit'`.

- [ ] **Step 3: Make `_catalog` geometry-aware**

Change `_catalog`'s signature and body. Replace its header (`:163`) and the `recommended` line and add fit + re-rank:

```python
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
            "fit": probes.fit(name, profile) if profile is not None else {"rank": "ok", "reason": ""},
        }
        group = info["group"]
        if group == "docker":
            img = sorter_registry.default_docker_image(name)
            present_img = bool(img) and docker_installed and \
                sorter_registry.docker_image_present(img)
            info["image"] = img
            info["img_present"] = present_img
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
```

In `reload()` change the `_catalog` call (`:751`) to pass the active profile:

```python
        self.infos = _catalog(self.active_sorter, self.use_docker,
                              probes.get(self.active_probe))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SpikeInterface_Menu.py tests/test_menu_controller.py
git commit -m "feat(menu): geometry-aware sorter catalog (fit + soft re-rank + recommended)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Report & spatial views honour the active probe

### Task 7: report.py probe + conditional geometry caveat

**Files:**
- Modify: `scripts/report.py` (the broadband-load path + the geometry-caveat notices at `:248-249`/`:377-378`)
- Modify: `SpikeInterface_Menu.py` (`_GEOMETRY_CAVEAT` use in `action_gui` `:486` / `action_traces` `:524`; `action_traces` recording load `:527`; launcher argparse `--probe`; `_self` threading `:307-311`; `action_report` `:353-356`)

**Interfaces:**
- Consumes: `probes.get`, `probes.build`, `probes.DEFAULT_PROBE`, `self.active_probe`.
- Produces: the report and the trace browser load the recording with the active probe; the geometry caveat is shown **only** when the active probe is `independent`, otherwise it states the active geometry.

- [ ] **Step 1: Write the failing test** — append to `tests/test_menu_controller.py`:

```python
def test_geometry_caveat_conditional(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, use_docker=False, cfg={})
    assert M._geometry_note("independent").startswith("Placeholder")
    real = M._geometry_note("linear-16-50um")
    assert "Placeholder" not in real and "linear-16-50um" in real
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_menu_controller.py -k caveat -q`
Expected: FAIL — `AttributeError: module 'SpikeInterface_Menu' has no attribute '_geometry_note'`.

- [ ] **Step 3: Add a conditional caveat helper and use the probe in the spatial paths**

In `SpikeInterface_Menu.py`, after the `_GEOMETRY_CAVEAT` definition (`:374`) add:

```python
def _geometry_note(active_probe: str) -> str:
    """The geometry caveat, conditional on the active probe.

    For the 'independent' PLACEHOLDER it's the full not-physical warning; for any
    real profile (incl. the default A1x16) it states the geometry in use (spatial
    views are then meaningful)."""
    import probes
    if active_probe in (None, probes.PLACEHOLDER_PROBE):
        return _GEOMETRY_CAVEAT
    prof = probes.get(active_probe)
    label = prof["label"] if prof else active_probe
    return (f"Probe geometry: {active_probe} — {label}. Spatial views (probe map, "
            "unit locations, depth) reflect this geometry; verify it matches your array.")
```

In `action_gui` replace `ui.warn(_GEOMETRY_CAVEAT)` (`:486`) with:

```python
    ui.warn(_geometry_note(getattr(args, "probe", None) or "independent"))
```

In `action_traces` replace `ui.warn(_GEOMETRY_CAVEAT)` (`:524`) the same way, and load the recording with the active probe — replace `rec = bio.read_broadband(args.data_dir)` (`:527`) with:

```python
    import probes
    rec = bio.read_broadband(args.data_dir, attach_probe=False)
    try:
        rec = rec.set_probe(probes.build(
            probes.get(getattr(args, "probe", None) or "independent")
            or probes.get(probes.DEFAULT_PROBE), rec.get_num_channels()))
    except Exception:  # noqa: BLE001 - fall back to the placeholder on mismatch
        rec = bio.attach_dummy_probe(rec)
```

Add a launcher `--probe` argument (in `main()`'s argparse, near `--sorter` `:1303-1309`):

```python
    parser.add_argument("--probe", default=None, help="Active probe profile (internal).")
```

Thread it through `_self` (after the `--data-dir` block `:309`):

```python
    if getattr(args, "probe", None):
        cmd += ["--probe", args.probe]
```

In `MenuController.run()` set `self.args.probe = self.active_probe` for QT actions too — change the top of `run()` (`:950`) from `self.args.sorter = self.active_sorter` to also set `self.args.probe = self.active_probe`.

In `action_report` pass the probe to the report builder (`:355`):

```python
    out = report.build_report(data_dir=args.data_dir, analyzer_dir=_analyzer_dir(args.sorter),
                              sorter_label=args.sorter, probe=getattr(args, "probe", None))
```

In `scripts/report.py`:

1. Add a module-level helper (it reuses report.py's existing `html` import):

```python
def _probe_caveat(probe, n_drop=0) -> str:
    """Geometry note HTML, conditional on the active probe NAME (or None).

    Placeholder/independent → the not-physical warning; a real probe → a calm
    'geometry: <name>' note (spatial views are then meaningful)."""
    drop = (f' {n_drop} non-neural analog aux channel(s) were excluded from the sort.'
            if n_drop else "")
    if probe in (None, "independent"):
        return ('<div class="caveat">Placeholder independent-channel probe — cross-channel '
                'spatial structure (depth / probe map) is not physical.' + drop + '</div>')
    return (f'<div class="note">Probe geometry: <strong>{html.escape(str(probe))}</strong>. '
            'Spatial views reflect this geometry; verify it matches your array.' + drop + '</div>')
```

2. Add `probe=None` to `build_report` (`:454`): `def build_report(data_dir=None, analyzer_dir=None, out_path=None, sorter_label=None, probe=None) -> Path:`. Thread `probe` into the two renderer functions that emit the caveats (the status/versions renderer that owns lines `:247-252`, and the sorted-units renderer that owns `:376-381`) by giving each a `probe=None` parameter and passing `probe` from `build_report`'s call sites.

3. Replace the hard-coded geometry caveat in the status/versions renderer (`:247-252`) with the helper + a factual channel-composition note:

```python
    return (f'<p class="note">{html.escape(" · ".join(versions))}</p>'
            + _probe_caveat(probe)
            + '<p class="note">The broadband stream mixes 16 neural channels (raw 1–16) '
              'with 6 analog aux channels (analog 1–6); the sort excludes the analog aux '
              'channels by default.</p>')
```

4. Replace `probe_html` in the sorted-units renderer (`:377-381`) with:

```python
    probe_html = _probe_caveat(probe, info.get("n_dropped_analog") or 0)
```

The report's broadband read (`:119`, via `_gather`) is left unchanged: the sorted-unit/spatial sections read the saved analyzer, which already carries the real geometry from sort time, so no probe threading into `_gather` is needed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Manually verify the launcher still parses**

Run: `uv run python SpikeInterface_Menu.py --help`
Expected: shows the new `--probe` option, exits 0.

- [ ] **Step 6: Commit**

```bash
git add SpikeInterface_Menu.py scripts/report.py tests/test_menu_controller.py
git commit -m "feat(report): report + trace views honour the active probe; conditional caveat

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 — Textual UI

### Task 8: PROBE banner line + FakeController probe surface

**Files:**
- Modify: `tests/conftest.py` (`FakeController`)
- Modify: `scripts/menu_app.py` (CSS `:1338-1396`; `Controller` Protocol `:100-131`; `compose` `:1438-1450`; `_relayout` `:1475-1519`; add `_render_probebar`)
- Modify: `tests/test_menu_app.py`

**Interfaces:**
- Consumes (from the controller): `active_probe: str`, `probe_info: dict`, `want_probe_setup: bool`, and the methods from Task 5.
- Produces: a `#probebar` Static rendered by `_render_probebar(width)`; `FakeController` gains `active_probe`, `want_probe_setup`, `probe_info`, `probe_catalog()`, `active_probe_info()`, `set_active_probe()`, `save_probe()`, `delete_probe()`, `duplicate_probe()`, `mark_probe_setup_seen()`, `sorter_fit()`, and a `fit` field on each `info`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_menu_app.py`:

```python
async def test_probe_banner_shows_active_probe(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        bar = app.query_one("#probebar", Static)
        text = bar.render().plain if hasattr(bar.render(), "plain") else str(bar.render())
        assert "PROBE" in text and "A1x16" in text   # the default = the real NNX probe
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_menu_app.py -k probe_banner -q`
Expected: FAIL — `NoMatches: #probebar`.

- [ ] **Step 3a: Extend `FakeController`** (in `tests/conftest.py`)

In `__init__` (after `self.want_welcome = False`):

```python
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
        ]
```

Add a `fit` field inside the `reload()` info dict (after `"overrides": ...`):

```python
                "fit": {"rank": "good" if name == "tridesclous2" else "ok",
                        "reason": f"{name} fit."},
```

Set `recommended` to follow the active probe trivially (leave `name == "tridesclous2"` — independent's good-fit default).

Add the probe methods (after `mark_welcome_seen`):

```python
    def active_probe_info(self) -> dict:
        return next(p for p in self._probe_lib if p["name"] == self.active_probe)

    def probe_catalog(self) -> list[dict]:
        return [dict(p, active=p["name"] == self.active_probe) for p in self._probe_lib]

    def set_active_probe(self, name: str) -> bool:
        if name not in [p["name"] for p in self._probe_lib]:
            return False
        self.active_probe = name
        self.reload()
        return True

    def save_probe(self, profile) -> tuple[bool, str]:
        self._probe_lib.append(dict(profile, builtin=False, active=False, auto=False,
                                    match="unknown", match_detail="", summary="",
                                    n=None, density_class="sparse", layout="linear"))
        return True, f"Saved probe {profile['name']}."

    def delete_probe(self, name: str) -> tuple[bool, str]:
        self._probe_lib = [p for p in self._probe_lib if p["name"] != name]
        return True, f"Deleted probe {name}."

    def duplicate_probe(self, name, new_name, new_label=None) -> dict:
        dup = {"name": new_name, "label": new_label or f"{name} copy", "kind": "linear",
               "builtin": False}
        self.save_probe(dup)
        return dup

    def mark_probe_setup_seen(self) -> None:
        self.want_probe_setup = False

    def sorter_fit(self, name: str) -> dict:
        return {"rank": "good" if name == "tridesclous2" else "ok", "reason": f"{name} fit."}

    def catalog_manufacturers(self) -> list[str]:
        return ["neuronexus"]

    def catalog_models(self, manufacturer: str) -> list[str]:
        return ["A1x16-...", "A1x32-..."]
```

Also set `self.probe_info` at the end of `reload()`:

```python
        self.probe_info = self.active_probe_info()
```

Add to the `Controller` Protocol in `menu_app.py` (after `want_welcome`):

```python
    active_probe: str
    want_probe_setup: bool
    probe_info: dict

    def set_active_probe(self, name: str) -> bool: ...
    def probe_catalog(self) -> list[dict]: ...
    def active_probe_info(self) -> dict: ...
    def save_probe(self, profile: dict) -> tuple[bool, str]: ...
    def delete_probe(self, name: str) -> tuple[bool, str]: ...
    def duplicate_probe(self, name: str, new_name: str, new_label=None) -> dict: ...
    def mark_probe_setup_seen(self) -> None: ...
    def sorter_fit(self, name: str) -> dict: ...
```

- [ ] **Step 3b: Add the `#probebar` widget**

CSS: after the `#sortbar` rule (`:1349`) add:

```css
    #probebar { height: 1; margin: 0 2 1 2; }
    #probebar.collapsed { display: none; }
```

(and add `#probebar` to the `.collapsed` display:none rule on line 1352.)

`compose`: after `yield Static(id="sortbar")` (`:1442`) add:

```python
        yield Static(id="probebar")
```

`_relayout`: after `self._render_sortbar(w)` (`:1481`) add `self._render_probebar(w)`; in the `tiny` collapse loop (`:1492`) add `"#probebar"` to the widget tuple.

Add the renderer (after `_render_sortbar`):

```python
    def _render_probebar(self, width: int) -> None:
        """The PROBE row: active geometry profile + layout/pitch + match flag."""
        pi = self.c.probe_info
        t = Text()
        t.append("PROBE ", style=ui.SECONDARY)
        t.append("▸ ", style=self._accent)
        t.append(pi.get("label", pi.get("name", "?")), style=f"bold {self._accent}")
        t.append(f" · {pi.get('summary', '')}", style=ui.PRIMARY)
        match = pi.get("match")
        glyph, gstyle = {
            "auto": ("✓ auto-fit", "#3fb950"), "fits": ("✓ fits", "#3fb950"),
            "mismatch": ("⚠ " + pi.get("match_detail", "size mismatch"), "#f0883e"),
            "unknown": ("· size at sort time", "dim"),
        }.get(match, ("", "dim"))
        if glyph:
            t.append(f" · {glyph}", style=gstyle)
        t.truncate(max(1, width - 2), overflow="ellipsis")
        self.query_one("#probebar", Static).update(t)
```

> The crest reserve (`_relayout`) already leaves room; adding one banner row is within the existing slack. If a never-clip Pilot test fails at the smallest sizes, bump `chrome` by 1 in the non-tiny branch and re-run.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_app.py -k "probe_banner or boots" -q`
Expected: PASS (the new test + the boot tests still green).

- [ ] **Step 5: Run the FULL suite (catch banner/never-clip regressions)**

Run: `uv run python -m pytest tests/ -q`
Expected: PASS. (If a `(60,24)`/never-clip test now clips, adjust the crest reserve as noted, then re-run.)

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): PROBE banner line + FakeController probe surface

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 9: First-run ProbeSetupScreen

**Files:**
- Modify: `scripts/menu_app.py` (add `ProbeSetupScreen`; `on_mount` gating `:1465-1469`)
- Create/extend: `tests/test_menu_probe.py`

**Interfaces:**
- Consumes: `controller.probe_catalog()`, `controller.set_active_probe()`, `controller.mark_probe_setup_seen()`, `controller.want_probe_setup`.
- Produces: `ProbeSetupScreen(controller, accent)` shown after Welcome when `want_probe_setup` is true; choices = each built-in profile, "Open the probe manager", and "Skip — use placeholder for now"; dismissal marks setup seen.

- [ ] **Step 1: Write the failing tests** — create `tests/test_menu_probe.py`:

```python
"""Pilot tests for the probe-geometry UI (ProbeSetupScreen/Manager/Editor)."""
from __future__ import annotations

import menu_app
from conftest import FakeController
from textual.widgets import OptionList, Static


def _app(**kw):
    return menu_app.SpikeMenuApp(FakeController(**kw))


async def test_probe_setup_shows_on_first_run():
    c = FakeController(present=True)
    c.want_probe_setup = True
    app = menu_app.SpikeMenuApp(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        # the welcome gate is off (want_welcome False), so probe setup is on top
        assert isinstance(app.screen, menu_app.ProbeSetupScreen)


async def test_probe_setup_skip_keeps_default():
    c = FakeController(present=True)
    c.want_probe_setup = True
    before = c.active_probe                      # the real NNX default
    app = menu_app.SpikeMenuApp(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")             # Esc = keep the current default
        await pilot.pause()
        assert c.want_probe_setup is False
        assert c.active_probe == before          # default kept, not forced to placeholder
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_probe.py -k setup -q`
Expected: FAIL — `AttributeError: module 'menu_app' has no attribute 'ProbeSetupScreen'`.

- [ ] **Step 3: Add `ProbeSetupScreen` and gate it after Welcome**

Add the screen (near `WelcomeScreen`):

```python
class ProbeSetupScreen(ModalScreen):
    """One-time first-run probe confirmation. The active default is highlighted;
    keep it (Esc), pick another profile, or open the manager."""

    DEFAULT_CSS = """
    ProbeSetupScreen { align: center middle; }
    ProbeSetupScreen > #dialog {
        width: 72; max-width: 94%; height: auto;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ProbeSetupScreen #pstitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    ProbeSetupScreen #psblurb { color: $text-muted; padding: 0 0 1 0; }
    ProbeSetupScreen OptionList { height: auto; max-height: 14; background: $surface; border: none; }
    ProbeSetupScreen #psfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [Binding("escape", "skip", "Skip")]

    def __init__(self, controller, accent: str):
        super().__init__()
        self._c = controller
        self._accent = accent

    def compose(self) -> ComposeResult:
        active = self._c.active_probe
        self._active_idx = 0
        opts = []
        for n, row in enumerate(r for r in self._c.probe_catalog() if r.get("builtin")):
            is_active = row["name"] == active
            t = Text("▌ " if is_active else "  ", style=self._accent if is_active else "")
            t.append(row["label"], style="bold" if is_active else "")
            t.append(f"   {row['summary']}", style="dim")
            if is_active:
                self._active_idx = n
            opts.append(Option(t, id=f"probe:{row['name']}"))
        opts.append(Option(Text("Manage probes…", style="bold"), id="__manage__"))
        opts.append(Option(Text("Keep this probe (change any time with 'p')", style="dim"),
                           id="__skip__"))
        info = self._c.active_probe_info()
        with Vertical(id="dialog"):
            yield Static("Your probe geometry", id="pstitle")
            yield Static(f"Active probe: {info['label']}. Keep it, pick another, or open the "
                         "manager — you can change it any time with 'p'.", id="psblurb")
            yield NavList(*opts, id="pslist")
            yield Static("Enter to choose · Esc to keep", id="psfoot")

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        ol.focus()
        ol.highlighted = getattr(self, "_active_idx", 0)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        oid = event.option.id or "__skip__"
        if oid.startswith("probe:"):
            self._c.set_active_probe(oid.split(":", 1)[1])
            self.dismiss("set")
        elif oid == "__manage__":
            self.dismiss("manage")
        else:
            self.dismiss(None)

    def action_skip(self) -> None:
        self.dismiss(None)
```

In `on_mount` change the welcome gate (`:1465-1466`) so probe setup runs *after* welcome:

```python
        if getattr(self.c, "want_welcome", False):
            self.push_screen(WelcomeScreen(), self._after_welcome)
        elif getattr(self.c, "want_probe_setup", False):
            self.push_screen(ProbeSetupScreen(self.c, self._accent), self._after_probe_setup)
```

Change `_after_welcome` to chain into probe setup:

```python
    def _after_welcome(self, _result) -> None:
        self.c.mark_welcome_seen()
        if getattr(self.c, "want_probe_setup", False):
            self.push_screen(ProbeSetupScreen(self.c, self._accent), self._after_probe_setup)

    def _after_probe_setup(self, result) -> None:
        self.c.mark_probe_setup_seen()
        if result == "manage":
            self._open_probes()
        self._render_probebar(self.size.width)
        self._rebuild_sorters()
```

(`_open_probes` is added in Task 10; the call is forward-referenced and exercised there.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_probe.py -k setup -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_probe.py
git commit -m "feat(menu): one-time first-run ProbeSetupScreen after Welcome

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 10: Probe manager + editor + `p` hotkey + Probe action

**Files:**
- Modify: `scripts/menu_app.py` (add `ProbeManagerScreen`, `ProbeEditorScreen`, `action_probe`, `_open_probes`, `_after_probes`; BINDINGS `:1398-1421`; `_activate_action` `:2193`)
- Modify: `SpikeInterface_Menu.py` (`_ACTIONS` `:611-624` + `_ACTION_DETAIL` `:632-658`: add a `probe` action)
- Modify: `tests/conftest.py` (`ACTIONS` list: add `probe`)
- Modify: `tests/test_menu_probe.py`

**Interfaces:**
- Consumes: `controller.probe_catalog()`, `set_active_probe`, `save_probe`, `delete_probe`, `duplicate_probe`, `catalog_manufacturers`, `catalog_models`.
- Produces: `ProbeManagerScreen(controller, accent)` (list/activate/new/edit/duplicate/delete + add-from-catalog/import) and `ProbeEditorScreen(profile, accent)`; `p` hotkey + a `probe` entry in ACTIONS both open the manager.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_menu_probe.py`:

```python
async def test_p_opens_probe_manager():
    app = _app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ProbeManagerScreen)


async def test_probe_manager_activate_changes_active():
    c = FakeController(present=True)
    app = menu_app.SpikeMenuApp(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        mgr = app.screen
        ol = mgr.query_one("#probelist", OptionList)
        # move to the second profile (linear-16) and activate it
        for i in range(ol.option_count):
            if ol.get_option_at_index(i).id == "linear-16-50um":
                ol.highlighted = i
                break
        await pilot.press("enter")
        await pilot.pause()
        assert c.active_probe == "linear-16-50um"


async def test_probe_action_in_actions_list():
    app = _app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        actions = app.query_one("#actions", OptionList)
        ids = [actions.get_option_at_index(i).id for i in range(actions.option_count)]
        assert "probe" in ids
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_probe.py -k "manager or action" -q`
Expected: FAIL — `AttributeError: module 'menu_app' has no attribute 'ProbeManagerScreen'` (and the `probe` action missing).

- [ ] **Step 3a: Add the `probe` action to the action tables**

In `SpikeInterface_Menu.py` `_ACTIONS` (after the `manage` row `:619`):

```python
    ("probe",      "Set probe geometry",     "pick / edit the electrode geometry",          False),
```

In `_ACTION_DETAIL` (`:632`) add:

```python
    "probe":   {"what": "Choose, edit, add, or remove the electrode-geometry profile. "
                        "Geometry decides which sorters fit and powers the spatial views."},
```

In `tests/conftest.py` `ACTIONS` (after the `manage` row `:29`):

```python
    ("probe", "Set probe geometry", "pick / edit geometry", False),
```

- [ ] **Step 3b: Add `ProbeEditorScreen`** (modeled on `ParamEditorScreen`)

```python
# Kind -> editable numeric params (label, default) for the probe editor.
_PROBE_KIND_FIELDS = {
    "independent": [("pitch_um", 250.0)],
    "linear": [("n", 16), ("pitch_um", 50.0)],
    "grid": [("rows", 8), ("cols", 4), ("xpitch_um", 50.0), ("ypitch_um", 50.0)],
    "tetrode": [("n_tetrodes", 4), ("within_um", 25.0), ("between_um", 300.0)],
}


class ProbeEditorScreen(ModalScreen):
    """Create/edit a parametric probe profile. Numeric fields per kind + name/label."""

    DEFAULT_CSS = """
    ProbeEditorScreen { align: center middle; }
    ProbeEditorScreen > #dialog {
        width: 72; max-width: 94%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ProbeEditorScreen #petitle { text-style: bold; color: $accentcolor; height: 1; }
    ProbeEditorScreen .perow { height: auto; padding: 0 0 1 0; }
    ProbeEditorScreen .pelabel { color: $accentcolor; text-style: bold; }
    ProbeEditorScreen Input { width: 100%; }
    ProbeEditorScreen #peerror { color: #f85149; height: auto; }
    ProbeEditorScreen #pefoot { color: $text-muted; height: 1; padding: 1 0 0 0; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("ctrl+s", "save", "Save")]

    def __init__(self, profile, accent):
        super().__init__()
        self._profile = profile          # the seed profile (a copy to edit)
        self._accent = accent
        self._fields = {}

    def compose(self) -> ComposeResult:
        kind = self._profile["kind"]
        params = self._profile.get("params", {})
        with Vertical(id="dialog"):
            yield Static(f"Edit probe · {kind}", id="petitle")
            with Vertical(classes="perow"):
                yield Label("name (unique id)", classes="pelabel")
                self._fields["name"] = Input(value=self._profile["name"], id="f_name")
                yield self._fields["name"]
            with Vertical(classes="perow"):
                yield Label("label (shown in the UI)", classes="pelabel")
                self._fields["label"] = Input(value=self._profile.get("label", ""), id="f_label")
                yield self._fields["label"]
            for key, default in _PROBE_KIND_FIELDS.get(kind, []):
                with Vertical(classes="perow"):
                    yield Label(key, classes="pelabel")
                    w = Input(value=str(params.get(key, default)), id=f"f_{key}")
                    self._fields[key] = w
                    yield w
            yield Static("", id="peerror")
            yield Static("Ctrl+S save · Esc cancel", id="pefoot")

    def on_mount(self) -> None:
        self._fields["name"].focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        kind = self._profile["kind"]
        name = self._fields["name"].value.strip()
        if not name:
            self.query_one("#peerror", Static).update("name is required")
            return
        params = {}
        for key, default in _PROBE_KIND_FIELDS.get(kind, []):
            raw = self._fields[key].value.strip()
            try:
                params[key] = int(raw) if isinstance(default, int) else float(raw)
            except ValueError:
                self.query_one("#peerror", Static).update(f"{key}: expected a number")
                return
        self.dismiss({"name": name, "label": self._fields["label"].value.strip() or name,
                      "kind": kind, "params": params, "builtin": False, "note": ""})
```

- [ ] **Step 3c: Add `ProbeManagerScreen`** (modeled on `ManageSortersScreen`)

```python
class ProbeManagerScreen(ModalScreen):
    """Manage probe profiles: activate (enter), new (n), edit (e), duplicate (g),
    delete (x, user profiles only, confirmed). Shows each profile's summary + match."""

    DEFAULT_CSS = """
    ProbeManagerScreen { align: center middle; }
    ProbeManagerScreen > #pmdialog {
        width: 86; max-width: 96%; height: 90%; max-height: 30;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ProbeManagerScreen #pmtitle { text-style: bold; color: $accentcolor; height: 1; }
    ProbeManagerScreen #probelist { height: 1fr; border: none; background: $surface; }
    ProbeManagerScreen #probelist:focus { border: none; }
    ProbeManagerScreen #pmfoot { color: $text-muted; height: auto; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("n", "new", "New", show=False),
        Binding("e", "edit", "Edit", show=False),
        Binding("g", "duplicate", "Duplicate", show=False),
        Binding("x", "delete", "Delete", show=False),
    ]
    _NEW_KINDS = [("linear", "Linear"), ("grid", "2-D grid"), ("tetrode", "Tetrodes"),
                  ("independent", "Independent")]

    def __init__(self, controller, accent: str):
        super().__init__()
        self._c = controller
        self._accent = accent
        self._last = None

    def compose(self) -> ComposeResult:
        with Vertical(id="pmdialog"):
            yield Static("Probe geometry", id="pmtitle")
            yield OptionList(id="probelist")
            yield Static("", id="pmfoot")

    def on_mount(self) -> None:
        self.query_one("#pmdialog").border_title = "PROBES"
        self.query_one("#probelist", OptionList).focus()
        self._rebuild()

    def _rebuild(self) -> None:
        ol = self.query_one("#probelist", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        for row in self._c.probe_catalog():
            ol.add_option(Option(self._row_text(row), id=row["name"]))
        if ol.option_count:
            ol.highlighted = keep if (keep is not None and keep < ol.option_count) else 0
        self._render_foot()

    def _row_text(self, row: dict) -> Text:
        t = Text()
        t.append("▌ " if row.get("active") else "  ",
                 style=self._accent if row.get("active") else "")
        t.append(row["label"], style="bold" if row.get("active") else "")
        t.append(f"   {row['summary']}", style="dim")
        if not row.get("builtin"):
            t.append("  · custom", style="dim")
        match = row.get("match")
        if match == "mismatch":
            t.append(f"   ⚠ {row.get('match_detail','')}", style="#f0883e")
        elif match in ("fits", "auto"):
            t.append("   ✓", style="#3fb950")
        return t

    def _highlighted(self) -> "dict | None":
        ol = self.query_one("#probelist", OptionList)
        if ol.highlighted is None:
            return None
        oid = ol.get_option_at_index(ol.highlighted).id
        return next((r for r in self._c.probe_catalog() if r["name"] == oid), None)

    def _render_foot(self) -> None:
        f = Text()
        if self._last is not None:
            f.append(self._last); f.append("\n")
        f.append("enter activate · n new · e edit · g duplicate · x delete · Esc close",
                 style="dim")
        self.query_one("#pmfoot", Static).update(f)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        row = self._highlighted()
        if row and self._c.set_active_probe(row["name"]):
            self._last = Text(f"Active probe → {row['label']}", style=f"bold {self._accent}")
            self._rebuild()

    def action_new(self) -> None:
        opts = [(k, lbl, "") for k, lbl in self._NEW_KINDS]
        self.app.push_screen(ChoiceModal("New probe — which kind?", opts),
                             self._after_new_kind)

    def _after_new_kind(self, kind) -> None:
        if not kind:
            return
        seed = {"name": f"my-{kind}", "label": f"My {kind}", "kind": kind,
                "params": {}, "builtin": False, "note": ""}
        self.app.push_screen(ProbeEditorScreen(seed, self._accent), self._after_edit)

    def action_edit(self) -> None:
        row = self._highlighted()
        if row is None:
            return
        seed = {"name": row["name"], "label": row["label"], "kind": row["kind"],
                "params": dict(row.get("params", {})), "builtin": row.get("builtin"),
                "note": ""}
        if row.get("builtin"):     # built-ins are immutable -> edit a copy
            seed["name"] = f"{row['name']}-copy"
            seed["label"] = f"{row['label']} (copy)"
        self.app.push_screen(ProbeEditorScreen(seed, self._accent), self._after_edit)

    def _after_edit(self, profile) -> None:
        if not profile:
            return
        ok, msg = self._c.save_probe(profile)
        self._last = Text(msg, style=_result_style(ok, msg))
        self._rebuild()

    def action_duplicate(self) -> None:
        row = self._highlighted()
        if row is None:
            return
        self._c.duplicate_probe(row["name"], f"{row['name']}-copy", f"{row['label']} (copy)")
        self._last = Text(f"Duplicated {row['name']}", style="#3fb950")
        self._rebuild()

    def action_delete(self) -> None:
        row = self._highlighted()
        if row is None or row.get("builtin"):
            self._last = Text("built-in profiles can't be deleted (duplicate to edit)",
                              style="#f0883e")
            self._render_foot()
            return
        name = row["name"]
        self.app.push_screen(
            ChoiceModal(f"Delete the probe profile {name}?",
                        [("confirm", "Delete it", ""), ("cancel", "Keep it", "")]),
            lambda r: self._confirmed_delete(name) if r == "confirm" else None)

    def _confirmed_delete(self, name: str) -> None:
        ok, msg = self._c.delete_probe(name)
        self._last = Text(msg, style=_result_style(ok, msg))
        self._rebuild()

    def action_close(self) -> None:
        self.dismiss(True)
```

> The editor seeds `params` empty for a brand-new profile; the `_PROBE_KIND_FIELDS` defaults fill the inputs, so a new profile always saves with valid params. "Add from catalog" / "Import file" can be added later via extra `_NEW_KINDS` entries that push manufacturer/model `ChoiceModal`s using `controller.catalog_manufacturers()/catalog_models()` and `controller.save_probe({kind:"library",...})` / `{kind:"file",...}` — out of scope for v1's required tests but the controller hooks exist.

- [ ] **Step 3d: Wire the hotkey + action**

In `SpikeMenuApp.BINDINGS` (after the `x` binding `:1410`) add:

```python
        Binding("p", "probe", "Probe", show=False),
```

Add the action handlers (near `action_manage_highlighted`):

```python
    def action_probe(self) -> None:
        self._open_probes()

    def _open_probes(self) -> None:
        self.push_screen(ProbeManagerScreen(self.c, self._accent), self._after_probes)

    def _after_probes(self, _result) -> None:
        try:
            self.c.reload()
            self._rebuild_sorters()
            self._rebuild_actions()
        except Exception as e:  # noqa: BLE001
            self._last = Text(f"reload after probe change failed: {e!r}", style="#f85149")
        self._render_sortbar(self.size.width)
        self._render_probebar(self.size.width)
        self._refresh_footer()
        self._render_inspect()
```

In `_activate_action` (`:2196`) add a branch (after the `theme` branch):

```python
        elif key == "probe":
            self._open_probes()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_probe.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite (action_count tests shift: +1 action)**

Run: `uv run python -m pytest tests/ -q`
Expected: PASS. Note: `tests/test_menu_app.py::test_boots_with_both_lists_and_sorter_focus` asserts `actions.option_count == 12` — update it to `13` (added the `probe` action) as part of this task.

- [ ] **Step 6: Commit**

```bash
git add scripts/menu_app.py SpikeInterface_Menu.py tests/conftest.py tests/test_menu_probe.py tests/test_menu_app.py
git commit -m "feat(menu): probe manager + editor, p hotkey, and Probe action

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 11: Sorter fit badge + INSPECTING fit line

**Files:**
- Modify: `scripts/menu_app.py` (`_sorter_text` `:1687-1726`; `_render_sorter_explain` `:1742-1802`)
- Modify: `tests/test_menu_app.py`

**Interfaces:**
- Consumes: `info["fit"]` (Task 6 / FakeController Task 8).
- Produces: a "✓ fits" / "△ weak" badge on sorter rows and a "Fit for \<probe\>:" line in the sorter INSPECTING blurb.

- [ ] **Step 1: Write the failing test** — append to `tests/test_menu_app.py`:

```python
async def test_inspecting_shows_fit_line(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        body = app.query_one("#inspectbody", Static)
        text = body.render().plain if hasattr(body.render(), "plain") else str(body.render())
        assert "Fit" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_menu_app.py -k fit_line -q`
Expected: FAIL — assertion error ("Fit" not in the blurb yet).

- [ ] **Step 3: Add the fit badge + fit line**

In `_sorter_text`, before the Docker-badge block (`:1717`) add a fit badge for runnable rows:

```python
        fit = info.get("fit") or {}
        if fit.get("rank") == "good" and not active:
            t.append("  ✓ fits", style="#3fb950")
        elif fit.get("rank") == "poor":
            t.append("  △ weak", style="#d29922")
```

In `_render_sorter_explain`, after the description block (`:1784`) add the fit line:

```python
        fit = info.get("fit") or {}
        if fit.get("reason"):
            t.append("Fit for this probe  ", style=ui.SECONDARY)
            colour = {"good": "#3fb950", "poor": "#d29922"}.get(fit.get("rank"), ui.PRIMARY)
            t.append(fit["reason"] + "\n\n", style=colour)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_app.py -k fit_line -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): geometry fit badge on sorter rows + INSPECTING fit line

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 7 — Fallback parity, Help, gitignore, docs

### Task 12: Fallback menu parity, Help topic, .gitignore, CLAUDE.md

**Files:**
- Modify: `scripts/ui.py` (`HELP_TOPICS` `:47-74`; add a `print_probes` helper)
- Modify: `SpikeInterface_Menu.py` (`_menu_fallback` — add a typed "Probe" option; the fallback `data` help already uses `HELP_TOPICS`)
- Modify: `.gitignore`
- Modify: `CLAUDE.md`
- Modify: `tests/test_fallback.py`

**Interfaces:**
- Consumes: `controller.probe_catalog`, `set_active_probe` (Task 5); `ui.HELP_TOPICS`.
- Produces: a typed "Set probe geometry" option in the non-Textual fallback (list + activate), a "Probe geometry" Help topic shared by both UIs, `probes.json` git-ignored, and CLAUDE.md documenting the layer.

- [ ] **Step 1: Write the failing test** — append to `tests/test_fallback.py` (or create a small new test if absent):

```python
def test_help_has_probe_topic():
    import ui
    keys = [k for k, _t, _b in ui.HELP_TOPICS]
    assert "probe" in keys
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_fallback.py -k probe_topic -q`
Expected: FAIL — `"probe" not in keys`.

- [ ] **Step 3a: Add the Help topic** (in `scripts/ui.py`, insert into `HELP_TOPICS` after the `sorters` entry `:58`):

```python
    ("probe", "Probe geometry",
     ["The Blackrock files carry no electrode map, so you choose the geometry.",
      "Press p (or the 'Set probe geometry' action) to pick a profile: a placeholder",
      "(independent channels), a standard layout, a Cui-lab preset, or your own.",
      "Geometry decides which sorters fit — good-fit sorters are badged ✓ and float up.",
      "NeuroNexus model decoder:  A{shanks}x{sites}-{length}-{pitch_um}-{site_area}."]),
```

- [ ] **Step 3b: Add a fallback probe listing + a typed Probe option**

In `scripts/ui.py` (near `print_catalog`) add:

```python
def print_probes(rows) -> None:
    """Plain grouped probe listing for the typed fallback (read-only overview)."""
    say(f"\n[bold {ACCENT}]PROBE GEOMETRY[/]")
    for r in rows:
        mark = "▸" if r.get("active") else " "
        tag = "" if r.get("builtin") else "  (custom)"
        say(f"  {mark} {r['name']:26} {r.get('summary','')}{tag}")
```

In `SpikeInterface_Menu.py` `_menu_fallback`, where the typed action list is assembled, add a "probe" choice that lists `controller.probe_catalog()` via `ui.print_probes` and then `ui.select(...)`s a profile to `controller.set_active_probe(name)`. (Mirror the existing `_manage_sorters_typed` shape — a small helper `_probe_typed(controller)` that prints the list, prompts for a name, and activates it.)

- [ ] **Step 3c: Ignore `probes.json`** — append to `.gitignore`:

```
# Probe-geometry user library (local, like .si_menu.json)
probes.json
```

- [ ] **Step 3d: Document in `CLAUDE.md`** — add a short "Probe geometry" paragraph under the "Sorting status & the probe gap" section, summarizing: `scripts/probes.py` is the source of truth; `independent` is the default placeholder; profiles persist in `probes.json` + `active_probe` in `.si_menu.json`; geometry softly re-ranks sorters; first-run `ProbeSetupScreen`; `--probe`/`--probe-file` on `run_sorting.py`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/ -q`
Expected: PASS (full suite).

- [ ] **Step 5: Verify `probes.json` is ignored**

Run: `cd /Users/benfaib/Spike/SpikeInterface/.claude/worktrees/probe-geometry && echo '{}' > probes.json && git check-ignore probes.json && rm probes.json`
Expected: prints `probes.json` (ignored).

- [ ] **Step 6: Commit**

```bash
git add scripts/ui.py SpikeInterface_Menu.py .gitignore CLAUDE.md tests/test_fallback.py
git commit -m "feat(menu): fallback probe parity, Help topic, gitignore probes.json, docs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Run the full suite:** `uv run python -m pytest tests/ -q` — expect all green (187 prior + the new probe tests).
- [ ] **Smoke the launcher:** `uv run python SpikeInterface_Menu.py --help` (shows `--probe`) and `uv run python scripts/run_sorting.py --help` (shows `--probe`/`--probe-file`).
- [ ] **Smoke the registry:** `uv run python -c "import sys; sys.path.insert(0,'scripts'); import probes; print(probes.summary(probes.get('independent'))); print(probes.fit('herdingspikes', probes.get('independent')))"`.
- [ ] **Optional real-data smoke (if the recording is present):** `uv run python scripts/run_sorting.py --duration 10 --probe nnx-a1x16-3mm-100` then `--probe independent` — confirm the probe line appears in the output and an explicit mismatch (`--probe linear-32-25um`) fails with the friendly message while the default falls back to the placeholder.
- [ ] **Headless geometry / GUI-data check (verifies the single-channel-collapse fix without opening a GUI):** after a real-geometry sort, run:

```bash
uv run python -c "import sys; sys.path.insert(0,'scripts'); import spikeinterface.full as si; \
a=si.load_sorting_analyzer('outputs/tridesclous2/analyzer'); \
import numpy as np; t=a.get_extension('templates').get_data(); \
print('probe contacts:', a.get_num_channels(), '| template shape:', t.shape); \
assert a.get_num_channels()==16, 'expected 16 A1x16 contacts'; \
print('OK: templates span all', t.shape[-1], 'channels')"
```

Expected: `probe contacts: 16` and templates spanning 16 channels (not 1) — proving the real geometry + dense analyzer reached the saved sort.
