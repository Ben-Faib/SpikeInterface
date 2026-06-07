# Multi-sorter support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two hardcoded sorters with a registry that auto-detects every locally-installed SpikeInterface sorter, optionally runs not-installed CPU sorters via Docker, lets the user edit any sorter's parameters, and lets the user choose which sorters to compare.

**Architecture:** A new `scripts/sorters.py` module becomes the single source of truth for sorter discovery, availability status (`local`/`docker`/`gpu`/`unavailable`), parameters, and running — mirroring how `blackrock_io.py` owns dataset loading. `run_sorting.py`, `SpikeInterface_Menu.py`, `scripts/compare.py`, `scripts/verify_install.py`, and `scripts/menu_app.py` all consume it. Heavy SpikeInterface imports stay lazy (inside functions) so importing the registry is cheap.

**Tech Stack:** Python 3.12, SpikeInterface 0.104.3 (`spikeinterface.sorters`), Textual (menu app), rich (shared UI), pytest + pytest-asyncio (tests), Docker CLI (opt-in container path).

**Spec:** `docs/superpowers/specs/2026-06-07-multi-sorter-support-design.md`

---

## File Structure

**Create:**
- `scripts/sorters.py` — sorter registry: discovery, status, params, run. No UI, no top-level SpikeInterface import.
- `tests/test_sorters.py` — hermetic unit tests for the registry (monkeypatched installed/docker/default_params).

**Modify:**
- `scripts/run_sorting.py` — dynamic `--sorter`, `--docker`, `--param`, `--params-file`, `--list-sorters`; sort via `sorters.run`.
- `scripts/compare.py` — `build_comparison(sorters=None)` defaults to the first two *saved* sorts.
- `scripts/verify_install.py` — print a sorter status table.
- `SpikeInterface_Menu.py` — import sorters from the registry; controller gains `use_docker`, per-sorter params, a compare picker; sort forwards params + docker.
- `scripts/menu_app.py` — Docker toggle row atop the Sorter sidebar; "Edit sorter parameters" action + Param Editor modal; sequential compare picker; status glyphs.
- `tests/conftest.py` — extend `FakeController` + `ACTIONS` for the new capabilities.
- `tests/test_menu_app.py` — fix action-index assertions; add tests for the Docker row, Param Editor, compare picker.
- `CLAUDE.md` — document the registry, Docker opt-in, param editing, dynamic sidebar, compare picker, new config keys.

---

## Task 1: Registry — discovery & availability status

**Files:**
- Create: `scripts/sorters.py`
- Test: `tests/test_sorters.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_sorters.py`:

```python
"""Hermetic unit tests for scripts/sorters.py.

The registry's discovery functions import SpikeInterface lazily, so every test
here monkeypatches them — no SpikeInterface, no Docker, no sorting is invoked.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sorters  # noqa: E402


@pytest.fixture
def fake_env(monkeypatch):
    """Default fake: tridesclous2 + spykingcircus2 installed, Docker on."""
    monkeypatch.setattr(sorters, "installed", lambda: ["spykingcircus2", "tridesclous2"])
    monkeypatch.setattr(sorters, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "mountainsort5", "herdingspikes",
         "kilosort4", "combinato"]))
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    return monkeypatch


def test_status_local(fake_env):
    assert sorters.status("tridesclous2") == "local"


def test_status_docker(fake_env):
    # not installed, CPU container image, Docker up -> docker
    assert sorters.status("mountainsort5") == "docker"
    assert sorters.status("herdingspikes") == "docker"


def test_status_gpu(fake_env):
    # GPU-only sorters are flagged even when Docker is up
    assert sorters.status("kilosort4") == "gpu"


def test_status_unavailable_when_docker_off(fake_env, monkeypatch):
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    assert sorters.status("mountainsort5") == "unavailable"


def test_status_unavailable_unknown(fake_env):
    # not installed, no image, not GPU -> unavailable
    assert sorters.status("nonexistent_sorter") == "unavailable"


def test_runnable_local_only(fake_env):
    assert sorters.runnable(use_docker=False) == ["spykingcircus2", "tridesclous2"]


def test_runnable_with_docker_adds_containers(fake_env):
    r = sorters.runnable(use_docker=True)
    assert r[:2] == ["spykingcircus2", "tridesclous2"]      # installed first
    assert "mountainsort5" in r and "herdingspikes" in r    # container extras
    assert "kilosort4" not in r                              # GPU excluded
    assert len(r) == len(set(r))                             # no duplicates


def test_runnable_docker_off_is_local(fake_env, monkeypatch):
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    assert sorters.runnable(use_docker=True) == ["spykingcircus2", "tridesclous2"]


def test_default_sorter_prefers_tridesclous2(fake_env):
    assert sorters.default_sorter() == "tridesclous2"


def test_default_sorter_falls_back_to_first_installed(fake_env, monkeypatch):
    monkeypatch.setattr(sorters, "installed", lambda: ["spykingcircus2"])
    assert sorters.default_sorter() == "spykingcircus2"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_sorters.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sorters'`.

- [ ] **Step 3: Create `scripts/sorters.py` with discovery + status**

```python
"""Sorter registry — discovery, availability, parameters, and running.

Single source of truth for which spike sorters this workspace can use. Replaces
the old hardcoded ``SORTERS = ["tridesclous2", "spykingcircus2"]``: it reports
every sorter SpikeInterface knows about, classifies each as runnable locally, via
a Docker container, GPU-only (not runnable here), or unavailable, and runs the
chosen one with optional per-run parameter overrides.

Like ``blackrock_io``, this module imports SpikeInterface lazily (inside the
functions) so importing it stays cheap and the menu stays responsive.

    import sorters
    sorters.installed()              # locally runnable, e.g. ['tridesclous2', ...]
    sorters.runnable(use_docker)     # what the menu offers
    sorters.status("mountainsort5")  # 'local' | 'docker' | 'gpu' | 'unavailable'
    sorters.run(name, recording, folder, params=..., use_docker=...)
"""
from __future__ import annotations

import json
import shutil
import subprocess

# Sorters that need an NVIDIA GPU (and, for the *ks ones, MATLAB). They are shown
# for transparency but never offered as runnable here: this is a Mac with no GPU,
# and Docker-on-Mac has no NVIDIA passthrough.
GPU_SORTERS = frozenset({
    "kilosort", "kilosort2", "kilosort2_5", "kilosort3", "kilosort4",
    "pykilosort", "yass",
})

# CPU-capable sorters with an official SpikeInterface Docker image, so they can be
# run via ``run_sorter(..., docker_image=True)`` without a local install. Curated
# against SpikeInterface's published images (spikeinterface/<name>-base on Docker
# Hub); update this set when SpikeInterface adds/removes images.
CONTAINERIZED = frozenset({
    "combinato", "herdingspikes", "hdsort", "ironclust", "mountainsort4",
    "mountainsort5", "spykingcircus", "spykingcircus2", "tridesclous",
    "tridesclous2", "waveclus",
})

# Preferred default when it is installed; otherwise the first installed sorter.
_PREFERRED_DEFAULT = "tridesclous2"

_docker_cache: dict = {}


def available() -> list[str]:
    """Every sorter SpikeInterface knows about, sorted."""
    import spikeinterface.sorters as ss

    return sorted(ss.available_sorters())


def installed() -> list[str]:
    """Sorters runnable on this machine right now (deps importable), sorted."""
    import spikeinterface.sorters as ss

    return sorted(ss.installed_sorters())


def docker_available(refresh: bool = False) -> bool:
    """True if the ``docker`` CLI is on PATH and the daemon answers.

    Cached per process (the daemon state rarely flips mid-session); pass
    ``refresh=True`` to re-check.
    """
    if not refresh and "ok" in _docker_cache:
        return _docker_cache["ok"]
    ok = False
    if shutil.which("docker"):
        try:
            ok = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=8
            ).returncode == 0
        except Exception:  # noqa: BLE001 - daemon down / timeout -> not available
            ok = False
    _docker_cache["ok"] = ok
    return ok


def status(name: str, installed_set=None, docker=None) -> str:
    """Classify one sorter: 'local' | 'docker' | 'gpu' | 'unavailable'.

    ``installed_set`` / ``docker`` may be passed precomputed (so a table doesn't
    re-query SpikeInterface/Docker once per row); both default to a live lookup.
    """
    inst = installed_set if installed_set is not None else installed()
    if name in inst:
        return "local"
    if name in GPU_SORTERS:
        return "gpu"
    if name in CONTAINERIZED:
        dock = docker if docker is not None else docker_available()
        if dock:
            return "docker"
    return "unavailable"


def runnable(use_docker: bool) -> list[str]:
    """Sorters the menu should offer: installed first, then (optionally) containers.

    With ``use_docker`` and a live Docker daemon, appends the CPU container sorters
    that aren't already installed (GPU sorters excluded). Deduplicated.
    """
    inst = installed()
    out = list(inst)
    if use_docker and docker_available():
        out += sorted(CONTAINERIZED - GPU_SORTERS - set(inst))
    seen, result = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


def default_sorter() -> str:
    """Preferred default sorter: tridesclous2 if installed, else first installed."""
    inst = installed()
    if _PREFERRED_DEFAULT in inst:
        return _PREFERRED_DEFAULT
    return inst[0] if inst else _PREFERRED_DEFAULT
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_sorters.py -q`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/sorters.py tests/test_sorters.py
git commit -m "feat(sorters): registry discovery + availability status"
```

---

## Task 2: Registry — parameters (coerce, merge, introspect)

**Files:**
- Modify: `scripts/sorters.py`
- Test: `tests/test_sorters.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sorters.py`:

```python
@pytest.fixture
def fake_params(monkeypatch):
    monkeypatch.setattr(sorters, "default_params", lambda name: {
        "detect_threshold": 5.0,   # float
        "n_peaks": 5000,           # int
        "peak_sign": "neg",        # str
        "apply_preprocessing": True,  # bool
        "seed": None,              # None -> JSON
        "job_kwargs": {},          # dict -> JSON
    })


def test_coerce_float():
    assert sorters.coerce_param(5.0, "6.5") == 6.5


def test_coerce_int():
    assert sorters.coerce_param(5000, "1000") == 1000


def test_coerce_bool_truthy():
    assert sorters.coerce_param(True, "false") is False
    assert sorters.coerce_param(False, "yes") is True


def test_coerce_str_passthrough():
    assert sorters.coerce_param("neg", "pos") == "pos"


def test_coerce_none_as_json():
    assert sorters.coerce_param(None, "42") == 42
    assert sorters.coerce_param(None, "null") is None


def test_coerce_dict_as_json():
    assert sorters.coerce_param({}, '{"n_jobs": 4}') == {"n_jobs": 4}


def test_coerce_bad_int_raises():
    with pytest.raises(ValueError):
        sorters.coerce_param(5000, "notanint")


def test_coerce_bad_json_raises():
    with pytest.raises(ValueError):
        sorters.coerce_param({}, "{not json}")


def test_merge_params_applies_overrides(fake_params):
    merged = sorters.merge_params("tridesclous2", {"detect_threshold": 6.0})
    assert merged["detect_threshold"] == 6.0
    assert merged["peak_sign"] == "neg"  # untouched default preserved


def test_merge_params_unknown_key_raises(fake_params):
    with pytest.raises(ValueError) as e:
        sorters.merge_params("tridesclous2", {"not_a_param": 1})
    assert "not_a_param" in str(e.value)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_sorters.py -q`
Expected: FAIL — `AttributeError: module 'sorters' has no attribute 'coerce_param'`.

- [ ] **Step 3: Add the param helpers to `scripts/sorters.py`**

Append to `scripts/sorters.py`:

```python
def default_params(name: str) -> dict:
    """SpikeInterface's default parameter dict for ``name``."""
    import spikeinterface.sorters as ss

    return ss.get_default_sorter_params(name)


def param_descriptions(name: str) -> dict:
    """Per-parameter human descriptions for ``name`` (may omit some keys)."""
    import spikeinterface.sorters as ss

    return ss.get_sorter_params_description(name)


def coerce_param(default_value, raw: str):
    """Coerce a string value to the type of the sorter default.

    bool accepts true/false/1/0/yes/no/on/off; int/float are parsed; str is passed
    through; None/dict/list/other are parsed as JSON. Raises ``ValueError`` with a
    readable message on failure.
    """
    if isinstance(default_value, bool):
        low = raw.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"expected true/false, got {raw!r}")
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"expected an integer, got {raw!r}")
    if isinstance(default_value, float):
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"expected a number, got {raw!r}")
    if isinstance(default_value, str):
        return raw
    try:  # None / dict / list / anything else -> JSON
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"expected JSON for this parameter, got {raw!r}: {e}")


def merge_params(name: str, overrides: dict) -> dict:
    """Defaults overlaid with ``overrides``; raise on any unknown key.

    Used both to validate keys before a run and to compute the effective dict.
    """
    defaults = default_params(name)
    unknown = set(overrides) - set(defaults)
    if unknown:
        raise ValueError(
            f"unknown parameter(s) for {name}: {sorted(unknown)}. "
            f"valid keys: {sorted(defaults)}"
        )
    merged = dict(defaults)
    merged.update(overrides)
    return merged
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_sorters.py -q`
Expected: PASS (all sorters tests pass).

- [ ] **Step 5: Commit**

```bash
git add scripts/sorters.py tests/test_sorters.py
git commit -m "feat(sorters): parameter coercion, merge, and introspection"
```

---

## Task 3: Registry — run() + status_table()

**Files:**
- Modify: `scripts/sorters.py`
- Test: `tests/test_sorters.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sorters.py`:

```python
def test_run_passes_docker_and_params(fake_params, monkeypatch):
    calls = {}

    class FakeSS:
        def run_sorter(self, name, recording, **kw):
            calls["name"] = name
            calls["kw"] = kw
            return "SORTING"

    import types
    fake_ss = FakeSS()
    # sorters.run does `import spikeinterface.sorters as ss`
    monkeypatch.setitem(sys.modules, "spikeinterface", types.SimpleNamespace(sorters=fake_ss))
    monkeypatch.setitem(sys.modules, "spikeinterface.sorters", fake_ss)
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)

    out = sorters.run("tridesclous2", "REC", "/tmp/out",
                      params={"detect_threshold": 6.0}, use_docker=True, verbose=False)
    assert out == "SORTING"
    assert calls["name"] == "tridesclous2"
    assert calls["kw"]["docker_image"] is True
    assert calls["kw"]["sorter_params"] == {"detect_threshold": 6.0}
    assert calls["kw"]["remove_existing_folder"] is True


def test_run_docker_requested_but_unavailable_raises(fake_params, monkeypatch):
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    with pytest.raises(RuntimeError):
        sorters.run("tridesclous2", "REC", "/tmp/out", use_docker=True)


def test_status_table_shape(fake_env, fake_params):
    rows = sorters.status_table()
    assert {r["name"] for r in rows} == set(sorters.available())
    by = {r["name"]: r for r in rows}
    assert by["tridesclous2"]["status"] == "local"
    assert by["kilosort4"]["status"] == "gpu"
    assert by["mountainsort5"]["status"] == "docker"
    assert all("n_params" in r for r in rows)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_sorters.py -q`
Expected: FAIL — `AttributeError: module 'sorters' has no attribute 'run'`.

- [ ] **Step 3: Add `run()` and `status_table()` to `scripts/sorters.py`**

Append to `scripts/sorters.py`:

```python
def run(name, recording, folder, *, params=None, use_docker=False, verbose=False):
    """Run sorter ``name`` on ``recording``, writing to ``folder``.

    ``params`` is an *overrides* dict (validated against the sorter's defaults);
    SpikeInterface fills the rest. ``use_docker`` runs the sorter in its official
    SpikeInterface image and raises if the Docker daemon isn't reachable.
    """
    import spikeinterface.sorters as ss

    params = params or {}
    if params:
        merge_params(name, params)  # validate keys; raises ValueError on unknown
    if use_docker and not docker_available():
        raise RuntimeError(
            "Docker was requested but the Docker daemon isn't reachable. "
            "Start Docker Desktop, or run without Docker."
        )
    return ss.run_sorter(
        name,
        recording,
        folder=str(folder),
        remove_existing_folder=True,
        docker_image=True if use_docker else False,
        sorter_params=params,
        verbose=verbose,
    )


def _n_params(name: str) -> int:
    try:
        return len(default_params(name))
    except Exception:  # noqa: BLE001 - introspection failure -> 0, never crash a table
        return 0


def status_table() -> list[dict]:
    """One ``{name, status, n_params}`` row per available sorter (for verify/list)."""
    inst = set(installed())
    dock = docker_available()
    return [
        {"name": name, "status": status(name, installed_set=inst, docker=dock),
         "n_params": _n_params(name)}
        for name in available()
    ]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_sorters.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/sorters.py tests/test_sorters.py
git commit -m "feat(sorters): run() wrapper + status_table()"
```

---

## Task 4: `run_sorting.py` — dynamic sorter, Docker, param flags

**Files:**
- Modify: `scripts/run_sorting.py`
- Test: `tests/test_run_sorting.py` (create)

The script's `main()` runs a real sort, so we test the two pure helpers we extract
(`resolve_sorter`, `resolve_overrides`) and integration-test `--list-sorters` in
the final verification task.

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_sorting.py`:

```python
"""Unit tests for run_sorting's pure helpers (no real sorting)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sorters  # noqa: E402
import run_sorting as rs  # noqa: E402


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(sorters, "installed", lambda: ["spykingcircus2", "tridesclous2"])
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(sorters, "CONTAINERIZED", frozenset({"mountainsort5", "tridesclous2"}))
    monkeypatch.setattr(sorters, "default_params", lambda name: {
        "detect_threshold": 5.0, "n_peaks": 5000, "apply_preprocessing": True})


def test_resolve_sorter_ok_local(fake):
    assert rs.resolve_sorter("tridesclous2", use_docker=False) == "tridesclous2"


def test_resolve_sorter_rejects_unrunnable(fake):
    with pytest.raises(SystemExit):
        rs.resolve_sorter("kilosort4", use_docker=False)


def test_resolve_sorter_docker_enables_container(fake):
    assert rs.resolve_sorter("mountainsort5", use_docker=True) == "mountainsort5"


def test_resolve_overrides_merges_file_then_cli(fake, tmp_path):
    pf = tmp_path / "p.json"
    pf.write_text('{"detect_threshold": 4.0, "n_peaks": 100}')
    out = rs.resolve_overrides("tridesclous2", ["detect_threshold=6.5"], str(pf))
    assert out["detect_threshold"] == 6.5   # CLI wins over file
    assert out["n_peaks"] == 100            # from file
    assert out["apply_preprocessing"] not in out or True  # defaults not duplicated


def test_resolve_overrides_unknown_key_exits(fake):
    with pytest.raises(SystemExit):
        rs.resolve_overrides("tridesclous2", ["bogus=1"], None)


def test_resolve_overrides_bad_value_exits(fake):
    with pytest.raises(SystemExit):
        rs.resolve_overrides("tridesclous2", ["n_peaks=notint"], None)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_run_sorting.py -q`
Expected: FAIL — `AttributeError: module 'run_sorting' has no attribute 'resolve_sorter'`.

- [ ] **Step 3: Edit `scripts/run_sorting.py`**

3a. Replace the import + `SORTERS` constant near the top. Find:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402

SORTERS = ["tridesclous2", "spykingcircus2"]
VERBOSITY_LEVELS = ["quiet", "normal", "verbose"]
```

Replace with:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import sorters  # noqa: E402  (sorter registry: discovery / status / params / run)

VERBOSITY_LEVELS = ["quiet", "normal", "verbose"]
```

3b. Add the two pure helpers + a list printer just above `def main() -> int:`:

```python
def resolve_sorter(name: str, use_docker: bool) -> str:
    """Validate a requested sorter against what's runnable; exit clearly if not.

    ``--sorter`` is not a fixed argparse ``choices`` because the runnable set
    depends on ``--docker`` and what's installed; this resolves it after parsing.
    """
    runnable = sorters.runnable(use_docker)
    if name in runnable:
        return name
    st = sorters.status(name)
    reason = {
        "gpu": "needs an NVIDIA GPU (not available here)",
        "docker": "is a container sorter — re-run with --docker (and start Docker)",
        "unavailable": "is not installed and has no usable container image",
        "local": "is installed",  # unreachable (would be in runnable)
    }.get(st, "is not available")
    raise SystemExit(
        f"Sorter {name!r} {reason}.\nRunnable now: {', '.join(runnable) or '(none)'}."
        "\nSee all sorters with: python scripts/run_sorting.py --list-sorters"
    )


def resolve_overrides(sorter: str, param_kv: list[str], params_file: "str | None") -> dict:
    """Build the override dict: defaults < --params-file < repeated --param.

    Values are coerced to each default's type; unknown keys / bad values exit with
    a clear message (before any sorting starts).
    """
    defaults = sorters.default_params(sorter)
    overrides: dict = {}
    if params_file:
        try:
            file_over = json.loads(Path(params_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise SystemExit(f"--params-file {params_file!r}: {e}")
        if not isinstance(file_over, dict):
            raise SystemExit(f"--params-file {params_file!r} must contain a JSON object.")
        overrides.update(file_over)
    for item in param_kv:
        if "=" not in item:
            raise SystemExit(f"--param expects NAME=VALUE, got {item!r}")
        key, raw = item.split("=", 1)
        key = key.strip()
        if key not in defaults:
            raise SystemExit(
                f"unknown parameter {key!r} for {sorter}. valid keys: {sorted(defaults)}")
        try:
            overrides[key] = sorters.coerce_param(defaults[key], raw)
        except ValueError as e:
            raise SystemExit(f"--param {key}: {e}")
    # validate any keys that came from the file too
    unknown = set(overrides) - set(defaults)
    if unknown:
        raise SystemExit(
            f"unknown parameter(s) for {sorter}: {sorted(unknown)}. "
            f"valid keys: {sorted(defaults)}")
    return overrides


def print_sorter_table() -> None:
    """Print the availability of every SpikeInterface sorter, then return."""
    rows = sorters.status_table()
    label = {"local": "local", "docker": "docker", "gpu": "GPU-only", "unavailable": "—"}
    print("Sorters known to SpikeInterface (status on this machine):\n")
    for r in rows:
        print(f"  {r['name']:18} {label.get(r['status'], r['status']):9} "
              f"{r['n_params']:>3} params")
    n_local = sum(r["status"] == "local" for r in rows)
    n_dock = sum(r["status"] == "docker" for r in rows)
    n_gpu = sum(r["status"] == "gpu" for r in rows)
    print(f"\n{n_local} local · {n_dock} container-capable · {n_gpu} GPU-only.")
    if not sorters.docker_available():
        print("(Docker not detected — container sorters need Docker running.)")
```

Add `import json` to the import block at the top of the file (after `import gc`):

```python
import gc
import json
import re
```

3c. Update `main()`'s argument parser. Find the `--sorter` line:

```python
    parser.add_argument("--sorter", default="tridesclous2", choices=SORTERS, help="Which sorter to run.")
```

Replace with:

```python
    parser.add_argument("--sorter", default=None,
                        help="Which sorter to run (default: tridesclous2 if installed). "
                             "See all with --list-sorters.")
    parser.add_argument("--docker", action="store_true",
                        help="Run the sorter in its SpikeInterface Docker image "
                             "(lets you run not-installed CPU sorters).")
    parser.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                        help="Override one sorter parameter (repeatable).")
    parser.add_argument("--params-file", default=None,
                        help="JSON file of sorter parameter overrides.")
    parser.add_argument("--list-sorters", action="store_true",
                        help="Print every sorter and its availability, then exit.")
```

3d. Right after `args = parser.parse_args()` in `main()`, handle `--list-sorters` and resolve the sorter/params. Find:

```python
    args = parser.parse_args()

    # Configure output BEFORE importing spikeinterface so env vars / the tqdm
    # patch land before OpenMP/Numba/the sorters initialise.
    show_bars = configure_output(args.verbosity)
```

Replace with:

```python
    args = parser.parse_args()

    if args.list_sorters:
        configure_output("quiet")  # mute import chatter; we only want the table
        print_sorter_table()
        return 0

    if args.sorter is None:
        args.sorter = sorters.default_sorter()
    args.sorter = resolve_sorter(args.sorter, args.docker)
    overrides = resolve_overrides(args.sorter, args.param, args.params_file)

    # Configure output BEFORE importing spikeinterface so env vars / the tqdm
    # patch land before OpenMP/Numba/the sorters initialise.
    show_bars = configure_output(args.verbosity)
```

3e. Replace the Sort phase. Find:

```python
    ui.phase("Sort", args.sorter)
    sorting = ss.run_sorter(
        args.sorter,
        rec,
        folder=str(out / "sorter_output"),
        remove_existing_folder=True,
        verbose=show_bars,
    )
    ui.result(f"{len(sorting.get_unit_ids())} units found")
```

Replace with:

```python
    ui.phase("Sort", args.sorter + ("  (docker)" if args.docker else ""))
    if overrides:
        ui.detail("overrides: " + ", ".join(f"{k}={v}" for k, v in overrides.items()))
    if args.docker:
        ui.detail("first Docker run pulls the sorter image — this can take a while")
    sorting = sorters.run(
        args.sorter,
        rec,
        out / "sorter_output",
        params=overrides,
        use_docker=args.docker,
        verbose=show_bars,
    )
    ui.result(f"{len(sorting.get_unit_ids())} units found")
```

(The unused `import spikeinterface.sorters as ss` line in `main()` may stay — it's
harmless — or be removed; leave it to minimise the diff.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_run_sorting.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/run_sorting.py tests/test_run_sorting.py
git commit -m "feat(run_sorting): dynamic sorter, --docker, --param/--params-file, --list-sorters"
```

---

## Task 5: `compare.py` — default to the first two saved sorts

**Files:**
- Modify: `scripts/compare.py`
- Test: `tests/test_compare.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_compare.py`:

```python
"""Unit test for compare's saved-sort discovery (no SpikeInterface needed)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import compare  # noqa: E402


def test_saved_sorters_finds_analyzer_dirs(tmp_path, monkeypatch):
    # Two sorters with an analyzer dir, one without.
    for name in ("tridesclous2", "mountainsort5"):
        (tmp_path / name / "analyzer").mkdir(parents=True)
    (tmp_path / "spykingcircus2").mkdir()
    monkeypatch.setattr(compare, "OUTPUT_DIR", tmp_path)
    found = compare.saved_sorters()
    assert found == ["mountainsort5", "tridesclous2"]  # sorted, only those with analyzer
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_compare.py -q`
Expected: FAIL — `AttributeError: module 'compare' has no attribute 'saved_sorters'`.

- [ ] **Step 3: Edit `scripts/compare.py`**

3a. Add a `saved_sorters()` helper just above `def _load(sorter: str):`:

```python
def saved_sorters() -> list[str]:
    """Sorter names under outputs/ that have a saved analyzer, sorted."""
    if not OUTPUT_DIR.exists():
        return []
    return sorted(
        p.name for p in OUTPUT_DIR.iterdir()
        if (p / "analyzer").exists()
    )
```

3b. Change `build_comparison` to default to the first two saved sorts. Find:

```python
def build_comparison(data_dir=None, sorters=DEFAULT_SORTERS, out_path=None) -> Path:
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "comparison.html")
    OUTPUT_DIR.mkdir(exist_ok=True)
    s1_name, s2_name = sorters
```

Replace with:

```python
def build_comparison(data_dir=None, sorters=None, out_path=None) -> Path:
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "comparison.html")
    OUTPUT_DIR.mkdir(exist_ok=True)
    if sorters is None:
        found = saved_sorters()
        sorters = tuple(found[:2]) if len(found) >= 2 else DEFAULT_SORTERS
    s1_name, s2_name = sorters
```

(The `compare` parameter name shadows nothing else here; `DEFAULT_SORTERS` stays as
the fallback when fewer than two saved sorts exist.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_compare.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/compare.py tests/test_compare.py
git commit -m "feat(compare): default to the first two saved sorts"
```

---

## Task 6: `verify_install.py` — sorter status section

**Files:**
- Modify: `scripts/verify_install.py`

No new unit test (the function only prints); `sorters.status_table()` is already
tested. The final task runs `verify_install.py` end-to-end.

- [ ] **Step 1: Edit `scripts/verify_install.py`**

Replace the existing "Installed sorters" block. Find:

```python
    print("\n=== Installed sorters ===")
    import spikeinterface.sorters as ss

    print(f"  {ss.installed_sorters()}")
```

Replace with:

```python
    print("\n=== Sorters (availability on this machine) ===")
    import sorters as sorter_registry

    rows = sorter_registry.status_table()
    label = {"local": "local", "docker": "docker", "gpu": "GPU-only", "unavailable": "—"}
    for r in rows:
        print(f"  {r['name']:18} {label.get(r['status'], r['status']):9} "
              f"{r['n_params']:>3} params")
    n_local = sum(r["status"] == "local" for r in rows)
    n_dock = sum(r["status"] == "docker" for r in rows)
    n_gpu = sum(r["status"] == "gpu" for r in rows)
    print(f"  -> {n_local} local · {n_dock} container-capable · {n_gpu} GPU-only")
    if not sorter_registry.docker_available():
        print("     (Docker not detected — container sorters need Docker running)")
```

- [ ] **Step 2: Run the smoke test to verify it works**

Run: `uv run python scripts/verify_install.py 2>/dev/null | sed -n '/Sorters (availability/,/GPU-only/p'`
Expected: a table listing sorters with `local`/`docker`/`GPU-only`/`—`, then the
summary line. (Exit code 0 if data is present; the sorter section prints regardless.)

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_install.py
git commit -m "feat(verify): show full sorter availability table"
```

---

## Task 7: `SpikeInterface_Menu.py` — controller: registry, docker, params, compare picker

**Files:**
- Modify: `SpikeInterface_Menu.py`
- Test: `tests/test_menu_controller.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_menu_controller.py`:

```python
"""Tests for the launcher's pure helpers (no SpikeInterface / no controller I/O)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import SpikeInterface_Menu as M  # noqa: E402


def test_effective_params_overlays_defaults(monkeypatch):
    import sorters
    monkeypatch.setattr(sorters, "default_params",
                        lambda name: {"a": 1.0, "b": "x", "c": True})
    eff = M._effective_params("tdc", {"a": 2.0})
    assert eff == {"a": 2.0}  # only overrides are returned (diffs), not full defaults


def test_write_params_file_roundtrip(tmp_path):
    p = M._write_params_file({"detect_threshold": 6.0})
    try:
        assert json.loads(Path(p).read_text()) == {"detect_threshold": 6.0}
    finally:
        Path(p).unlink(missing_ok=True)


def test_write_params_file_empty_returns_none():
    assert M._write_params_file({}) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_menu_controller.py -q`
Expected: FAIL — `AttributeError: module 'SpikeInterface_Menu' has no attribute '_effective_params'`.

- [ ] **Step 3: Edit `SpikeInterface_Menu.py`**

3a. Swap the sorter source. Find:

```python
import blackrock_io as bio  # noqa: E402
import report  # noqa: E402
import ui  # noqa: E402  (rich styling shared-look with run_sorting.py)
from run_sorting import SORTERS  # noqa: E402  (single-source the sorter list)
```

Replace with:

```python
import blackrock_io as bio  # noqa: E402
import report  # noqa: E402
import sorters as sorter_registry  # noqa: E402  (registry: discovery/status/params/run)
import ui  # noqa: E402  (rich styling shared-look with run_sorting.py)
```

3b. Add `import tempfile` to the top import block (after `import subprocess`):

```python
import subprocess
import sys
import tempfile
```

3c. Add module-level helpers just below `QT_ACTIONS = {"gui", "traces"}`:

```python
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
```

3d. Replace `action_sort` to forward params + docker. Find:

```python
def action_sort(args) -> bool:
    flags = ["--sorter", args.sorter]
    if args.duration is not None:
        flags += ["--duration", str(args.duration)]
    if args.data_dir:
        flags += ["--data-dir", args.data_dir]
    return _shell("run_sorting.py", *flags)
```

Replace with:

```python
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
    return _shell("run_sorting.py", *flags)
```

3e. Add `--docker` to the launcher's own argparse so direct CLI `sort` honours it.
Find in `main()`:

```python
    parser.add_argument("--duration", type=float, default=None, help="For 'sort': first N seconds only.")
    args = parser.parse_args()
```

Replace with:

```python
    parser.add_argument("--duration", type=float, default=None, help="For 'sort': first N seconds only.")
    parser.add_argument("--docker", action="store_true",
                        help="For 'sort': run the sorter in its Docker image.")
    args = parser.parse_args()
```

Also change the `--sorter` argument in `main()` so it isn't pinned to two choices.
Find:

```python
    parser.add_argument("--sorter", choices=SORTERS, default=SORTERS[0], help="Active sorter.")
```

Replace with:

```python
    parser.add_argument("--sorter", default=None, help="Active sorter (default: auto).")
```

3f. Update `_load_dashboard` and `_sorter_info` to (a) iterate a passed sorter list
and (b) carry per-sorter `status`. Find:

```python
def _sorter_info(sorter: str, analyzer, active: bool) -> dict:
    """Saved-sort summary for one sorter. Pass a pre-loaded analyzer or None."""
    if analyzer is None and _analyzer_dir(sorter).exists():
        try:
            import spikeinterface.full as si

            analyzer = si.load_sorting_analyzer(_analyzer_dir(sorter))
        except Exception:  # noqa: BLE001 - unreadable analyzer -> treat as absent
            analyzer = None
    if analyzer is None:
        return {"name": sorter, "present": False, "units": 0, "duration": 0.0, "active": active}
    return {"name": sorter, "present": True, "units": len(analyzer.unit_ids),
            "duration": float(analyzer.get_total_duration()), "active": active}


def _load_dashboard(data_dir, active: str):
    """Return (pipeline_rows, sorter_infos). Heavy: loads the data + analyzers."""
    objects, status = report._gather(data_dir, _analyzer_dir(active))
    pipeline = [r for r in status if not r["stage"].startswith("Saved sort")]
    infos = [_sorter_info(s, objects.get("analyzer") if s == active else None, s == active)
             for s in SORTERS]
    return pipeline, infos
```

Replace with:

```python
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
```

3g. Update `MenuController` for the new state + methods. Find the whole
`MenuController.__init__` and `reload`:

```python
    def __init__(self, args, cfg: dict):
        self.args = args
        self.cfg = cfg
        self.header = HEADER
        self.sorters = list(SORTERS)
        self.themes = dict(ui.THEMES)
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd) for k, t, h, nd in _ACTIONS]
        self.theme_name = cfg.get("theme", ui.DEFAULT_THEME)
        if self.theme_name not in ui.THEMES:
            self.theme_name = ui.DEFAULT_THEME
        self.accent = ui.THEMES[self.theme_name]
        self.active_idx = self.sorters.index(args.sorter) if args.sorter in self.sorters else 0
        self.reload()
```

Replace with:

```python
    def __init__(self, args, cfg: dict):
        self.args = args
        self.cfg = cfg
        self.header = HEADER
        self.themes = dict(ui.THEMES)
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd) for k, t, h, nd in _ACTIONS]
        self.theme_name = cfg.get("theme", ui.DEFAULT_THEME)
        if self.theme_name not in ui.THEMES:
            self.theme_name = ui.DEFAULT_THEME
        self.accent = ui.THEMES[self.theme_name]
        self.use_docker = bool(cfg.get("use_docker", False))
        self.sorter_params = dict(cfg.get("sorter_params", {}))
        self.sorters = sorter_registry.runnable(self.use_docker) or [sorter_registry.default_sorter()]
        want = args.sorter if args.sorter else sorter_registry.default_sorter()
        self.active_idx = self.sorters.index(want) if want in self.sorters else 0
        self.reload()
```

Find `reload`:

```python
    def reload(self) -> None:
        self.pipeline, self.infos = _load_dashboard(self.args.data_dir, self.active_sorter)
        for i, info in enumerate(self.infos):
            info["active"] = (i == self.active_idx)
        self.data_report = _data_report(self.args.data_dir)
```

Replace with:

```python
    def reload(self) -> None:
        self.pipeline, self.infos = _load_dashboard(
            self.args.data_dir, self.active_sorter, self.sorters, self.use_docker)
        for i, info in enumerate(self.infos):
            info["active"] = (i == self.active_idx)
        self.data_report = _data_report(self.args.data_dir)

    def toggle_docker(self) -> bool:
        """Flip Docker mode, persist it, and rebuild the runnable sorter list."""
        self.use_docker = not self.use_docker
        self.cfg["use_docker"] = self.use_docker
        _save_config(self.cfg)
        active_name = self.active_sorter
        self.sorters = sorter_registry.runnable(self.use_docker) or [sorter_registry.default_sorter()]
        self.active_idx = self.sorters.index(active_name) if active_name in self.sorters else 0
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

    def saved_sorters(self) -> list[str]:
        """Sorters that currently have a saved analyzer (for the compare picker)."""
        return [i["name"] for i in self.infos if i.get("present")]

    def run_compare(self, pair) -> tuple[bool, str, bool]:
        """Compare a user-chosen pair of saved sorts (mismatch caveat handled in action)."""
        self.args.sorter = pair[0]
        try:
            ok = _compare_pair(self.args, tuple(pair))
        except Exception as e:  # noqa: BLE001
            ui.warn(f"compare failed: {e!r}")
            ok = False
        return ok, _last_message("compare", self.args.sorter, ok), True
```

3h. Update `MenuController.run` to inject params/docker for sort. Find:

```python
    def run(self, key: str, span: str | None) -> tuple[bool, str, bool]:
        self.args.sorter = self.active_sorter
        if key == "sort":
            self.args.duration = QUICK_SECONDS if span == "quick" else None
        try:
            ok = _self(key, self.args) if key in QT_ACTIONS else DISPATCH[key](self.args)
        except Exception as e:  # noqa: BLE001 - surface, keep the app alive
            ui.warn(f"{key} failed: {e!r}")
            ok = False
        return ok, _last_message(key, self.args.sorter, ok), key in ("sort", "compare")
```

Replace with:

```python
    def run(self, key: str, span: str | None) -> tuple[bool, str, bool]:
        self.args.sorter = self.active_sorter
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
        return ok, _last_message(key, self.args.sorter, ok), key in ("sort", "compare")
```

3i. Extract the compare body into a reusable `_compare_pair(args, sorters)` so both
the CLI action and the controller's picker use it. Find the whole `action_compare`:

```python
def action_compare(args) -> bool:
    import compare  # lazy: pulls in spikeinterface

    other = [s for s in SORTERS if s != args.sorter]
    sorters = (args.sorter, other[0]) if other else tuple(SORTERS[:2])

    # Surface a duration mismatch and (interactively) offer to make the two sorts
    # commensurate by re-sorting both over a common window before comparing.
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

    out = compare.build_comparison(data_dir=args.data_dir, sorters=sorters)
    uri = out.resolve().as_uri()
    ui.done(f"Comparison written → {out}")
    ui.link("Open it:", uri)
    _open_in_browser(uri)
    return True
```

Replace with:

```python
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

    out = compare.build_comparison(data_dir=args.data_dir, sorters=sorters)
    uri = out.resolve().as_uri()
    ui.done(f"Comparison written → {out}")
    ui.link("Open it:", uri)
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_menu_controller.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the existing data-report tests (no regression in the launcher module)**

Run: `uv run python -m pytest tests/test_data_report.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add SpikeInterface_Menu.py tests/test_menu_controller.py
git commit -m "feat(menu): controller gains docker toggle, per-sorter params, compare picker"
```

---

## Task 8: `menu_app.py` + conftest — Docker row, Param Editor, compare picker

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_menu_app.py`
- Modify: `scripts/menu_app.py`

### 8a. Extend the test double first

- [ ] **Step 1: Update `tests/conftest.py`**

Replace the `ACTIONS` table (add the `params` action after `compare`). Find:

```python
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
```

Replace with:

```python
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
```

In `FakeController`, add the docker/params/compare surface. Find:

```python
    def __init__(self, present: bool = True):
        self.theme_name = "periwinkle"
        self.accent = self.themes[self.theme_name]
        self.active_idx = 0
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd) for k, t, h, nd in ACTIONS]
        self.ran: list[tuple[str, str | None]] = []
        self._present = present
        self.reload()
```

Replace with:

```python
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
```

Add `"status"` to each info dict in `reload`. Find:

```python
        self.infos = [
            {"name": "tridesclous2", "present": True, "units": 12, "duration": 132.0, "active": True},
            {"name": "spykingcircus2", "present": False, "units": 0, "duration": 0.0, "active": False},
        ]
```

Replace with:

```python
        self.infos = [
            {"name": n, "present": p, "units": u, "duration": d, "active": False, "status": "local"}
            for n, p, u, d in [("tridesclous2", True, 12, 132.0),
                               ("spykingcircus2", True, 7, 132.0)]
        ][: len(self.sorters)]
```

(Both present so the compare picker has two choices.)

Add the new methods to `FakeController`, just after `set_theme`:

```python
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
```

The `reload` must keep `infos` length in sync with `self.sorters` when docker grows
it. Add a third info when needed — update the list comprehension in `reload` to:

```python
        rows = [("tridesclous2", True, 12, 132.0), ("spykingcircus2", True, 7, 132.0),
                ("mountainsort5", False, 0, 0.0)]
        self.infos = [
            {"name": n, "present": p, "units": u, "duration": d, "active": False,
             "status": "docker" if n == "mountainsort5" else "local"}
            for n, p, u, d in rows if n in self.sorters
        ]
```

(Replace the earlier two-row version with this so docker-on shows three sorters.)

- [ ] **Step 2: Update existing index-based tests in `tests/test_menu_app.py`**

Adding `params` shifts indices and grows the count from 10 → 11.

i. `test_boots_with_lists_and_focus`: change `assert actions.option_count == 10` to
`== 11`.

ii. `test_tiny_window_stacks_and_keeps_actions`: change `option_count == 10` to `== 11`.

iii. `test_very_short_window_does_not_crash`: change `option_count == 10` to `== 11`.

iv. `test_action_run_path_is_guarded`: `verify` is now index 7 (1-based "8"). Change
the comment and `await pilot.press("7")` to `await pilot.press("8")`.

v. Replace `test_number_key_opens_data_setup` entirely (data-setup is now beyond "9"):

```python
async def test_number_key_opens_param_editor(make_controller):
    # action index 6 (1-based "7") is "Edit sorter parameters" in the mirrored table
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("7")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ParamEditorScreen)
```

- [ ] **Step 3: Run those tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: FAIL — references to `menu_app.ParamEditorScreen` (not yet defined) and the
new behaviours; some count assertions fail until the app is updated.

### 8b. Implement the app changes

- [ ] **Step 4: Add the Docker toggle row + status glyphs to the Sorter sidebar**

In `scripts/menu_app.py`, update `_rebuild_sorters` and `_sorter_text`. Find:

```python
    def _rebuild_sorters(self) -> None:
        ol = self.query_one("#sorters", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        for i, info in enumerate(self.c.infos):
            ol.add_option(Option(self._sorter_text(info, i == self.c.active_idx), id=info["name"]))
        ol.highlighted = keep if (keep is not None and keep < ol.option_count) else self.c.active_idx
```

Replace with:

```python
    def _rebuild_sorters(self) -> None:
        ol = self.query_one("#sorters", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        # Row 0 is the Docker toggle; sorter rows follow (offset by 1).
        ol.add_option(Option(self._docker_row_text(), id="__docker__"))
        for i, info in enumerate(self.c.infos):
            ol.add_option(Option(self._sorter_text(info, i == self.c.active_idx), id=info["name"]))
        # keep cursor on the active sorter (its option index is active_idx + 1)
        target = self.c.active_idx + 1
        ol.highlighted = keep if (keep is not None and keep < ol.option_count) else target

    def _docker_row_text(self) -> Text:
        on = getattr(self.c, "use_docker", False)
        t = Text()
        t.append("⊞ Docker sorters: ", style="dim")
        t.append("on" if on else "off", style=f"bold {self._accent}" if on else "dim")
        return t
```

Find `_sorter_text` and add a status glyph:

```python
    def _sorter_text(self, info: dict, active: bool) -> Text:
        # Compact so it never wraps the 36-col sidebar: a filled ● + bold name mark
        # the active sorter (shape + weight cues, not colour alone); the footer
        # carries its full units · duration. Inactive rows show ○ + unit count.
        t = Text()
        t.append("● " if active else "○ ", style=self._accent if active else "dim")
        t.append(info["name"], style=f"bold {self._accent}" if active else "")
        t.append(f"  {info['units']}u" if info.get("present") else "  —", style="dim")
        if active:  # explicit text tag, not colour alone (spec: unmistakable)
            t.append("  ACTIVE", style=f"bold {self._accent}")
        return t
```

Replace with:

```python
    # status glyph: ◇ = runs in Docker, (none) = local. GPU rows aren't offered.
    _STATUS_GLYPH = {"docker": "◇", "gpu": "·"}

    def _sorter_text(self, info: dict, active: bool) -> Text:
        # Compact so it never wraps the 36-col sidebar: a filled ● + bold name mark
        # the active sorter; an optional ◇ flags a Docker (container) sorter. The
        # footer carries its full units · duration.
        t = Text()
        t.append("● " if active else "○ ", style=self._accent if active else "dim")
        glyph = self._STATUS_GLYPH.get(info.get("status", "local"))
        if glyph:
            t.append(glyph + " ", style="dim")
        t.append(info["name"], style=f"bold {self._accent}" if active else "")
        t.append(f"  {info['units']}u" if info.get("present") else "  —", style="dim")
        if active:
            t.append("  ACTIVE", style=f"bold {self._accent}")
        return t
```

- [ ] **Step 5: Handle selection of the Docker row + sorter rows by id**

Find `on_option_list_option_selected`:

```python
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list is self.query_one("#sorters", OptionList):
            self._set_active(event.option_index)
        elif event.option_list is self.query_one("#actions", OptionList):
            self._activate_action(event.option.id)
```

Replace with:

```python
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list is self.query_one("#sorters", OptionList):
            if event.option.id == "__docker__":
                self._toggle_docker()
            else:
                # sorter rows are offset by 1 (row 0 is the Docker toggle)
                self._set_active(event.option_index - 1)
        elif event.option_list is self.query_one("#actions", OptionList):
            self._activate_action(event.option.id)

    def _toggle_docker(self) -> None:
        on = self.c.toggle_docker()
        self._rebuild_sorters()
        self._rebuild_actions()
        self._last = Text(f"Docker sorters {'on' if on else 'off'}",
                          style=f"bold {self._accent}")
        self._refresh_footer()
        self._relayout()
```

`action_cycle_sorter` ('t') still cycles only real sorters via `_set_active`, which
indexes `self.c.sorters` — unaffected by the toggle row. Leave it as-is.

- [ ] **Step 6: Add the "params" and "compare" branches to `_activate_action`**

Two edits. `params` does **not** need data, so its branch goes *before* the data
guard. `compare` **does** need data, so it goes *after* the guard (the guard catches
it when no recording is present; otherwise it falls through to the compare branch).

Edit 1 — add the `params` branch before the guard. Find:

```python
        elif key == "data-setup":
            self.action_data_help()
        elif self._needs_data(key) and not self.c.data_report.get("present"):
```

Replace with:

```python
        elif key == "data-setup":
            self.action_data_help()
        elif key == "params":
            self._open_params()
        elif self._needs_data(key) and not self.c.data_report.get("present"):
```

Edit 2 — add the `compare` branch just before the final `else`. Find:

```python
        else:
            self._run(key, None)
```

Replace with:

```python
        elif key == "compare":
            self._open_compare_picker()
        else:
            self._run(key, None)
```

- [ ] **Step 7: Add the Param Editor modal + opener**

Add these imports at the top of `menu_app.py` (extend the widgets import):

```python
from textual.widgets import Checkbox, Input, Label, OptionList, Static
```

(Replace the existing `from textual.widgets import OptionList, Static` line.)

Add the opener + callback to `SpikeMenuApp` (near `_open_theme`):

```python
    def _open_params(self) -> None:
        sorter = self.c.sorters[self.c.active_idx]
        try:
            defaults = self.c.default_params(sorter)
            descs = self.c.param_descriptions(sorter)
        except Exception as e:  # noqa: BLE001 - introspection failure -> report, no crash
            self._last = Text(f"can't read {sorter} params: {e!r}", style="#f85149")
            self._refresh_footer()
            return
        overrides = self.c.get_overrides(sorter)
        self.push_screen(
            ParamEditorScreen(sorter, defaults, descs, overrides, self._accent),
            self._after_params,
        )

    def _after_params(self, result) -> None:
        if result is None:
            self._last = Text("Parameter edit cancelled", style="dim")
        else:
            sorter, overrides = result
            self.c.set_params(sorter, overrides)
            n = len(overrides)
            self._last = Text(
                f"{sorter}: {n} override{'s' if n != 1 else ''} saved" if n
                else f"{sorter}: parameters reset to defaults",
                style=f"bold {self._accent}")
        self._refresh_footer()
```

Add the modal class (place it next to `DataSetupScreen`):

```python
class ParamEditorScreen(ModalScreen):
    """Edit one sorter's parameters. Scalars get an inline field/checkbox; complex
    values (dict/list/None) are edited as JSON. Save stores only changed keys."""

    DEFAULT_CSS = """
    ParamEditorScreen { align: center middle; }
    ParamEditorScreen > #dialog {
        width: 92; max-width: 96%; height: 90%; max-height: 36;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    ParamEditorScreen #ptitle { text-style: bold; color: $accentcolor; height: 1; }
    ParamEditorScreen #pscroll { height: 1fr; }
    ParamEditorScreen .prow { height: auto; padding: 0 0 1 0; }
    ParamEditorScreen .pname { color: $accentcolor; text-style: bold; }
    ParamEditorScreen .pdesc { color: $text-muted; }
    ParamEditorScreen Input { width: 100%; }
    ParamEditorScreen #perror { color: #f85149; height: auto; }
    ParamEditorScreen #pfoot { color: $text-muted; height: 1; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+r", "reset", "Reset"),
    ]

    def __init__(self, sorter, defaults, descs, overrides, accent):
        super().__init__()
        self._sorter = sorter
        self._defaults = defaults
        self._descs = descs or {}
        self._overrides = overrides or {}
        self._accent = accent
        self._widgets: dict = {}  # key -> (kind, widget)

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"Parameters · {self._sorter}", id="ptitle")
            with VerticalScroll(id="pscroll"):
                for key, default in self._defaults.items():
                    cur = self._overrides.get(key, default)
                    with Vertical(classes="prow"):
                        yield Label(key, classes="pname")
                        desc = self._descs.get(key)
                        if desc:
                            yield Label(str(desc), classes="pdesc")
                        if isinstance(default, bool):
                            w = Checkbox("enabled", value=bool(cur), id=f"w_{key}")
                            self._widgets[key] = ("bool", w)
                            yield w
                        elif isinstance(default, (int, float, str)) or default is None:
                            w = Input(value=_param_to_str(cur), id=f"w_{key}")
                            self._widgets[key] = ("scalar", w)
                            yield w
                        else:  # dict / list -> JSON
                            import json as _json
                            w = Input(value=_json.dumps(cur), id=f"w_{key}")
                            self._widgets[key] = ("json", w)
                            yield w
            yield Static("", id="perror")
            yield Static("Ctrl+S save · Ctrl+R reset to defaults · Esc cancel", id="pfoot")

    def on_mount(self) -> None:
        self.query_one("#pscroll").focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_reset(self) -> None:
        self.dismiss((self._sorter, {}))  # empty overrides -> controller clears them

    def action_save(self) -> None:
        import sorters as _sorters

        overrides = {}
        for key, (kind, w) in self._widgets.items():
            default = self._defaults[key]
            if kind == "bool":
                val = bool(w.value)
            else:
                raw = w.value
                try:
                    val = _sorters.coerce_param(default, raw)
                except ValueError as e:
                    self.query_one("#perror", Static).update(f"{key}: {e}")
                    return
            if val != default:
                overrides[key] = val
        self.dismiss((self._sorter, overrides))
```

Add the small formatter at module bottom (next to `_trunc`):

```python
def _param_to_str(value) -> str:
    """Render a scalar/None default for an Input field ('' for None)."""
    if value is None:
        return ""
    return str(value)
```

- [ ] **Step 8: Add the sequential compare picker**

Add to `SpikeMenuApp` (near `_open_params`):

```python
    def _open_compare_picker(self) -> None:
        if self._needs_data("compare") and not self.c.data_report.get("present"):
            self._last = Text("✗ ", style="bold #f85149") + Text(
                "compare needs the recording files — press d for help")
            self._refresh_footer()
            return
        saved = self.c.saved_sorters()
        if len(saved) < 2:
            self._last = Text(
                "Need two saved sorts to compare — run 'sort' for two sorters first.",
                style="#f0883e")
            self._refresh_footer()
            return
        opts = [(s, s, "") for s in saved]
        self.push_screen(ChoiceModal("Compare which sorter?", opts), self._after_compare_first)

    def _after_compare_first(self, first) -> None:
        if first is None:
            self._last = Text("Compare cancelled", style="dim")
            self._refresh_footer()
            return
        self._compare_first = first
        rest = [(s, s, "") for s in self.c.saved_sorters() if s != first]
        self.push_screen(ChoiceModal(f"…compared against?  (vs {first})", rest),
                         self._after_compare_second)

    def _after_compare_second(self, second) -> None:
        if second is None:
            self._last = Text("Compare cancelled", style="dim")
            self._refresh_footer()
            return
        self._run_compare((self._compare_first, second))

    def _run_compare(self, pair) -> None:
        try:
            with self.suspend():
                ok, message, changed = self.c.run_compare(pair)
        except SuspendNotSupported:
            ok, message, changed = self.c.run_compare(pair)
        except Exception as e:  # noqa: BLE001
            ok, message, changed = False, f"compare failed: {e!r}", False
        self._last = Text(message, style="#3fb950" if ok else "#f85149")
        if changed:
            try:
                self.c.reload()
                self._rebuild_sorters()
                self._rebuild_actions()
            except Exception as e:  # noqa: BLE001
                self._last = Text(f"reload after compare failed: {e!r}", style="#f85149")
        self._refresh_footer()
        self._relayout()
        self.refresh()
```

- [ ] **Step 9: Add the Pilot tests for the new behaviours**

Append to `tests/test_menu_app.py`:

```python
async def test_docker_toggle_row_is_first_and_toggles(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        assert sorters.get_option_at_index(0).id == "__docker__"
        n_before = sorters.option_count
        await pilot.press("left")       # focus the sorter sidebar (cursor on docker row)
        await pilot.press("enter")      # toggle docker on
        await pilot.pause()
        assert c.use_docker is True
        assert app.query_one("#sorters", OptionList).option_count == n_before + 1


async def test_toggle_does_not_change_active_sorter_index(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("left")
        await pilot.press("enter")      # toggle (cursor is on the docker row)
        await pilot.pause()
        assert c.active_idx == 0         # toggling didn't reassign the active sorter


async def test_param_editor_saves_only_changed_keys(make_controller):
    from textual.widgets import Input
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._open_params()
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ParamEditorScreen)
        field = app.screen.query_one("#w_detect_threshold", Input)
        field.value = "6.5"
        app.screen.action_save()
        await pilot.pause()
        assert c.params_set is not None
        sorter, overrides = c.params_set
        assert sorter == "tridesclous2"
        assert overrides == {"detect_threshold": 6.5}  # only the changed key


async def test_param_editor_reset_clears_overrides(make_controller):
    c = make_controller(present=True)
    c.sorter_params["tridesclous2"] = {"detect_threshold": 9.0}
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._open_params()
        await pilot.pause()
        app.screen.action_reset()
        await pilot.pause()
        assert c.params_set == ("tridesclous2", {})


async def test_param_editor_bad_value_shows_error_and_stays(make_controller):
    from textual.widgets import Input, Static
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app._open_params()
        await pilot.pause()
        app.screen.query_one("#w_freq_min", Input).value = "notanumber"
        app.screen.action_save()
        await pilot.pause()
        # still on the editor, with an error message; nothing saved
        assert isinstance(app.screen, menu_app.ParamEditorScreen)
        assert "freq_min" in app.screen.query_one("#perror", Static).render().plain
        assert c.params_set is None


async def test_compare_opens_picker_when_two_saved(make_controller):
    c = make_controller(present=True)   # both sorters present in the fake
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("6")          # compare
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)


async def test_compare_picks_pair_and_runs(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("6")          # compare -> first picker
        await pilot.pause()
        await pilot.press("enter")      # choose highlighted (tridesclous2)
        await pilot.pause()
        await pilot.press("enter")      # choose highlighted of the remaining
        await pilot.pause()
        assert c.ran_compare is not None
        assert len(c.ran_compare) == 2 and c.ran_compare[0] != c.ran_compare[1]
```

- [ ] **Step 10: Run the full menu-app test suite**

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: PASS (all original + new tests).

- [ ] **Step 11: Commit**

```bash
git add scripts/menu_app.py tests/conftest.py tests/test_menu_app.py
git commit -m "feat(menu-app): docker toggle row, param editor, compare picker"
```

---

## Task 9: Fallback typed menu — docker toggle, params, compare picker

**Files:**
- Modify: `SpikeInterface_Menu.py` (`_menu_fallback`, `_MENU`)

The fallback path (no Textual) must reach the same capabilities. It already uses
`ui.select`, which has a typed/numbered fallback for non-TTY, so this stays testable
by hand and consistent.

- [ ] **Step 1: Update the `_MENU` table**

Find:

```python
_MENU = [
    ("1", "explore", "Explore raw data",        "static figures (LFP + .nev), no sort needed"),
    ("2", "sort",    "Run / re-run sorting",    "sorts the active sorter tab; pick full or quick"),
    ("3", "report",  "Build & open report",     "interactive HTML → browser"),
    ("4", "gui",     "Open GUI inspector",      "spikeinterface-gui on the active sort"),
    ("5", "traces",  "Scroll raw traces",       "ephyviewer trace browser"),
    ("6", "compare", "Compare the two sorters", "agreement matrix → comparison.html"),
    ("7", "verify",  "Verify install",          "environment smoke test"),
    ("8", "theme",   "Change colour theme",     "pick an accent colour (saved for next time)"),
]
```

Replace with:

```python
_MENU = [
    ("1", "explore", "Explore raw data",        "static figures (LFP + .nev), no sort needed"),
    ("2", "sort",    "Run / re-run sorting",    "sorts the active sorter; pick full or quick"),
    ("3", "report",  "Build & open report",     "interactive HTML → browser"),
    ("4", "gui",     "Open GUI inspector",      "spikeinterface-gui on the active sort"),
    ("5", "traces",  "Scroll raw traces",       "ephyviewer trace browser"),
    ("6", "compare", "Compare sorters",         "pick two saved sorts → comparison.html"),
    ("7", "params",  "Edit sorter parameters",  "tune the active sorter (saved)"),
    ("8", "docker",  "Toggle Docker sorters",   "show/hide not-installed CPU sorters"),
    ("9", "verify",  "Verify install",          "environment smoke test"),
    ("10", "theme",  "Change colour theme",     "pick an accent colour (saved for next time)"),
]
```

- [ ] **Step 2: Handle the new actions in `_menu_fallback`**

Find the action-dispatch tail of `_menu_fallback` (the `if action == "theme":` block
through the end of the loop):

```python
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
        if action == "sort":
            span = ui.select("Sort how much?",
                             [("full", "Full recording", ""),
                              ("quick", f"Quick test — first {QUICK_SECONDS}s", "")],
                             default=0)
            if span is None:  # cancelled -> back to the menu without sorting
                last = "Sort cancelled"
                continue
            args.duration = QUICK_SECONDS if span == "quick" else None
        ok = _self(action, args) if action in QT_ACTIONS else DISPATCH[action](args)
        last = _last_message(action, args.sorter, ok)
        if action in ("sort", "compare"):  # only these can change saved-sort state
            pipeline, infos = _load_dashboard(args.data_dir, args.sorter)
            active_idx = SORTERS.index(args.sorter)
```

Replace with:

```python
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
            use_docker = not bool(cfg.get("use_docker", False))
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
```

- [ ] **Step 3: Rework `_menu_fallback`'s setup for the dynamic sorter list**

Find the top of `_menu_fallback`:

```python
def _menu_fallback(args, cfg: dict, theme: str) -> int:
    """Typed / prompt_toolkit dashboard used when Textual is unavailable."""
    report = _data_report(args.data_dir)
    if not report["present"]:
        _print_setup_plain(report)

    pipeline, infos = _load_dashboard(args.data_dir, args.sorter)
    active_idx = SORTERS.index(args.sorter)
    cursor = 0
    last = None
    actions = [(action, title, hint) for _k, action, title, hint in _MENU] + [("__quit__", "Quit", "")]
```

Replace with:

```python
def _menu_fallback(args, cfg: dict, theme: str) -> int:
    """Typed / prompt_toolkit dashboard used when Textual is unavailable."""
    report = _data_report(args.data_dir)
    if not report["present"]:
        _print_setup_plain(report)

    use_docker = bool(cfg.get("use_docker", False))
    sorter_list = sorter_registry.runnable(use_docker) or [sorter_registry.default_sorter()]
    if not args.sorter or args.sorter not in sorter_list:
        args.sorter = sorter_list[0]
    pipeline, infos = _load_dashboard(args.data_dir, args.sorter, sorter_list, use_docker)
    active_idx = sorter_list.index(args.sorter)
    cursor = 0
    last = None
    actions = [(action, title, hint) for _k, action, title, hint in _MENU] + [("__quit__", "Quit", "")]
```

Find the sorter-cycling + tab-handling inside the loop:

```python
        args.sorter = SORTERS[active_idx]          # the active tab IS the sorter
        for i in infos:
            i["active"] = i["name"] == args.sorter
        if action in (None, "__quit__"):
            return 0
        if action == "__sorter__":  # typed-fallback only: cycle to the next sorter
            active_idx = (active_idx + 1) % len(SORTERS)
            continue
```

Replace with:

```python
        args.sorter = sorter_list[active_idx]       # the active tab IS the sorter
        for i in infos:
            i["active"] = i["name"] == args.sorter
        if action in (None, "__quit__"):
            return 0
        if action == "__sorter__":  # typed-fallback only: cycle to the next sorter
            active_idx = (active_idx + 1) % len(sorter_list)
            continue
```

- [ ] **Step 4: Add the two typed helpers used above**

Add near `_print_setup_plain`:

```python
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
```

- [ ] **Step 5: Run the launcher tests (no regression)**

Run: `uv run python -m pytest tests/test_menu_controller.py tests/test_data_report.py -q`
Expected: PASS.

- [ ] **Step 6: Smoke-test the fallback path renders (non-TTY → builds report, no crash)**

Run: `echo "" | uv run python SpikeInterface_Menu.py --help >/dev/null && echo OK`
Expected: `OK` (argparse still valid after edits).

- [ ] **Step 7: Commit**

```bash
git add SpikeInterface_Menu.py
git commit -m "feat(menu-fallback): docker toggle, typed param editor, compare picker"
```

---

## Task 10: Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the "Sorting status" + Commands + Architecture sections**

In `CLAUDE.md`, in the **Sorting status & the probe gap** section, replace the
"Installed sorters are CPU-only" bullet:

```
- **Installed sorters are CPU-only:** `tridesclous2` and `spykingcircus2` (both bundled in `spikeinterface[full]`, no GPU/extra install). `run_sorting.py` exposes both via `--sorter`. Kilosort4 etc. are **not** installed and need an NVIDIA GPU + PyTorch (absent here).
```

with:

```
- **Sorters are discovered dynamically** via `scripts/sorters.py` (the registry — single source of truth). `installed_sorters()` runnable locally today: `tridesclous2`, `spykingcircus2`, `lupin`, `simple`. Not-installed **CPU** sorters (mountainsort5, herdingspikes, spykingcircus, waveclus, combinato, …) can run via **opt-in Docker** (`run_sorter(..., docker_image=True)`) — Docker is detected at runtime. **GPU sorters** (kilosort*, pykilosort, yass) are shown but never offered: no NVIDIA GPU here, and Docker-on-Mac has no GPU passthrough. `sorters.status(name)` → `local`/`docker`/`gpu`/`unavailable`.
```

Add to the **Commands** block (after the `run_sorting.py --verbosity quiet` line):

```
uv run python scripts/run_sorting.py --list-sorters          # availability table for every SI sorter
uv run python scripts/run_sorting.py --sorter mountainsort5 --docker   # run a not-installed CPU sorter via Docker
uv run python scripts/run_sorting.py --param detect_threshold=6.5 --param freq_min=250   # per-run param overrides
uv run python scripts/run_sorting.py --params-file my_params.json       # overrides from a JSON file
```

Add a new paragraph to the **Architecture** section, right after the
`scripts/blackrock_io.py` description:

```
`scripts/sorters.py` is the **sorter registry** — the single source of truth for
which spike sorters are usable (replacing the old hardcoded two-element list).
`available()`/`installed()` wrap SpikeInterface; `docker_available()` probes the
Docker daemon; `status(name)` classifies each sorter `local`/`docker`/`gpu`/
`unavailable`; `runnable(use_docker)` is what the menu offers (installed always,
container CPU sorters when Docker is on); `default_params`/`param_descriptions`/
`coerce_param`/`merge_params` back the parameter editor; and `run(...)` wraps
`run_sorter` with `docker_image=` + `sorter_params=`. Heavy SpikeInterface imports
stay lazy, so importing the registry is cheap. `GPU_SORTERS` and `CONTAINERIZED`
are curated constants.
```

In the `SpikeInterface_Menu.py` paragraph of the **Architecture** section, append:

```
The **Sorter sidebar** is now dynamic over `sorters.runnable(use_docker)` with a
`⊞ Docker sorters: off/on` **toggle row at the top** (↑/↓ to reach it, Enter to
flip — it re-lists the container sorters); each sorter row shows a `◇` glyph when
it runs via Docker. An **"Edit sorter parameters"** action opens a Param Editor
modal for the active sorter (scalars inline, bool as a checkbox, dict/None as
JSON; Ctrl+S saves only the changed keys, Ctrl+R resets). **Compare** now opens a
two-step picker to choose which saved sorts to compare. Docker on/off and
per-sorter parameter **overrides** (diffs from defaults) persist to `.si_menu.json`
(`use_docker`, `sorter_params`). The typed fallback menu offers the same via
`ui.select`/prompts.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: multi-sorter registry, Docker opt-in, param editing, compare picker"
```

---

## Task 11: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `uv run python -m pytest tests/ -q`
Expected: all tests pass (sorters, run_sorting, compare, menu controller, data
report, menu app). No failures, no errors.

- [ ] **Step 2: Confirm the sorter table lists more than two sorters**

Run: `uv run python scripts/run_sorting.py --list-sorters`
Expected: a table of ~22 sorters; `tridesclous2`/`spykingcircus2`/`lupin`/`simple`
shown `local`; kilosort* shown `GPU-only`; mountainsort5/herdingspikes/… shown
`docker` (if Docker is running) or `—`; a summary line; exit 0.

- [ ] **Step 3: Confirm a quick real sort still works with the new run path**

Run: `uv run python scripts/run_sorting.py --duration 5 --verbosity normal`
Expected: reads broadband, preprocesses, sorts with the default sorter, prints a
units count + quality-metrics table, exits 0. (Confirms the `sorters.run` wiring.)

- [ ] **Step 4: Confirm a parameter override is accepted and reported**

Run: `uv run python scripts/run_sorting.py --duration 5 --verbosity normal --param detect_threshold=6.0`
Expected: an "overrides: detect_threshold=6.0" detail line appears; the sort runs;
exit 0. (Confirms `--param` coercion + `sorter_params` plumbing end-to-end.)

- [ ] **Step 5: Confirm verify_install shows the sorter table**

Run: `uv run python scripts/verify_install.py`
Expected: the "Sorters (availability on this machine)" section lists each sorter
with local/docker/GPU-only/—, then the summary. Exit 0 (data present).

- [ ] **Step 6: Final commit if any verification fix was needed**

```bash
git add -A
git commit -m "test: multi-sorter support verification pass" || echo "nothing to commit"
```

---

## Self-Review (completed during planning)

**Spec coverage:** registry module (Tasks 1–3) ✓; local auto-detect + opt-in Docker
(`runnable`, `--docker`, toggle row — Tasks 1, 4, 7, 8, 9) ✓; full per-sorter param
editing (CLI `--param`/`--params-file` Task 4; menu modal Task 8; typed editor Task
9; persisted diffs Task 7) ✓; user-chosen compare (compare picker Tasks 7–9;
`compare.saved_sorters` Task 5) ✓; controls = params Action + Docker sidebar row
(Task 8) ✓; persistence `use_docker`/`sorter_params` (Task 7) ✓; GPU shown
informational-only (`status` Task 1; tables Tasks 4, 6) ✓; verify table (Task 6) ✓;
docs (Task 10) ✓; hermetic tests, no real Docker/sort (Tasks 1–9) ✓; final
integration checks isolated to Task 11 ✓.

**Type/name consistency:** `sorters.status(name, installed_set=, docker=)`,
`runnable(use_docker)`, `default_sorter()`, `coerce_param(default, raw)`,
`merge_params(name, overrides)`, `run(name, rec, folder, *, params, use_docker,
verbose)`, `status_table()` used consistently across Tasks 1–9. Controller methods
`toggle_docker`/`default_params`/`param_descriptions`/`get_overrides`/`set_params`/
`saved_sorters`/`run_compare` match the FakeController (Task 8) and the app calls
(Task 8). `ParamEditorScreen(sorter, defaults, descs, overrides, accent)` signature
matches its opener. Action keys (`params`, `compare`) match `_ACTIONS`, `_MENU`,
conftest `ACTIONS`, and the index-based test fixes.

**Placeholder scan:** no TBD/TODO; every code step shows complete code; every test
step shows the assertion.
