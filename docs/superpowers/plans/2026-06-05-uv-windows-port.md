# conda → uv Windows-Friendly Port - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this SpikeInterface workspace easy to run on a fresh Windows machine by switching the primary toolchain from conda to **uv** (committed `pyproject.toml` + `uv.lock`, a double-click launcher, and uv-first docs), keeping `environment.yml` as a conda fallback.

**Architecture:** Add packaging metadata so `uv sync` builds the whole env (incl. Python 3.12, PySide6 GUIs, notebooks) with no compiler; wrap launch in `run.bat`/`run.ps1` over `uv run`; rewrite conda-first docs; and apply three small Windows-robustness code edits. The Python logic is already interpreter-agnostic (every child process spawns via `sys.executable`, all paths use `pathlib`), so no dispatch/loader logic changes.

**Tech Stack:** uv 0.9.x, Python 3.12, SpikeInterface 0.104 (`[full,widgets]`), spikeinterface-gui[desktop] (PySide6), ephyviewer, tridesclous2/spykingcircus2 (CPU).

**Note on testing:** This repo has **no pytest suite**. The de-facto test is `scripts/verify_install.py`. Throughout, "verify" means run the stated `uv run …` command and confirm the stated output. Some checks (the `.exe` launcher, real Qt windows, the WinError-32 file-lock) can only be exercised on Windows - those are deferred to the Windows checklist in the final task.

**Spec:** `docs/superpowers/specs/2026-06-05-uv-windows-port-design.md`

**Branch:** `uv-windows-port` (already created; spec committed). Make all commits here.

---

## File map

| File | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | create | uv source of truth: deps, pins, `requires-python`, `[tool.uv] package=false`, `notebooks` extra |
| `.python-version` | create | pins interpreter to `3.12` for `uv run`/`uv sync` |
| `uv.lock` | create (generated) | reproducible locked resolution |
| `run.bat` | create | Windows double-click launcher (`uv run python …Menu.py`) |
| `run.ps1` | create | PowerShell launcher |
| `scripts/run_sorting.py` | modify | robust folder removal (Win file-lock); use shared muting helper |
| `scripts/blackrock_io.py` | modify | add `mute_native_chatter()` shared helper |
| `SpikeInterface_Menu.py` | modify | call muting helper in `main()`; utf-8 for `.si_menu.json`; docstring |
| `scripts/{explore_data,report,make_report,compare,verify_install}.py` | modify | docstring: conda→uv |
| `README.md` | modify | uv-first onboarding; conda demoted to fallback |
| `CLAUDE.md` | modify | Commands block, env-creation, Qt note → uv |
| `environment.yml` | modify | drop `xarray`; add uv pointer header |
| `requirements.txt` | delete | redundant with pyproject + lock |
| `notebooks/01_explore_lfp_and_spikes.ipynb` | modify | markdown cell + kernel display_name |
| `notebooks/02_spike_sorting.ipynb` | modify | kernel display_name |

---

## Task 1: Packaging foundation (pyproject + lock + smoke test)

**Files:**
- Create: `/Users/benfaib/Spike/SpikeInterface/pyproject.toml`
- Create: `/Users/benfaib/Spike/SpikeInterface/.python-version`
- Create (generated): `/Users/benfaib/Spike/SpikeInterface/uv.lock`

- [ ] **Step 1: Write `pyproject.toml`**

Create `/Users/benfaib/Spike/SpikeInterface/pyproject.toml` with exactly:

```toml
[project]
name = "spikeinterface-pfcm7"
version = "0.1.0"
description = "SpikeInterface workspace for the PFCM7 Blackrock/Ripple recording"
readme = "README.md"
requires-python = "==3.12.*"
dependencies = [
    "spikeinterface[full,widgets]>=0.104,<0.105",
    "spikeinterface-gui[desktop]>=0.13",
    "ephyviewer",
    "neo",
    "probeinterface",
    "numpy",
    "scipy>=1.10",
    "matplotlib>=3.6",
    "numba",
    "hdbscan>=0.8.33",
    "zarr>=2.18,<3",
    "plotly>=5.20,<6",
    "rich",
    "prompt_toolkit>=3.0",
    "pyqtgraph",
]

[project.optional-dependencies]
notebooks = ["jupyterlab", "ipywidgets", "ipympl"]

[tool.uv]
package = false
```

Rationale (do not add to file): `requires-python = "==3.12.*"` forces uv to a 3.12 interpreter so every compiled dep resolves to a prebuilt `cp312-win_amd64` wheel (no MSVC). `spikeinterface-gui[desktop]` pulls PySide6+pyqtgraph (verified: extra exists in 0.13.1). `[tool.uv] package = false` = install dependencies only; run scripts as files (no build backend needed).

- [ ] **Step 2: Write `.python-version`**

Create `/Users/benfaib/Spike/SpikeInterface/.python-version` containing exactly one line:

```
3.12
```

- [ ] **Step 3: Generate the lock**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv lock`
Expected: resolves and writes `uv.lock` with no error. If `spikeinterface-gui[desktop]` ever fails to resolve, fall back to replacing that line with `"spikeinterface-gui>=0.13"` + `"PySide6<6.8"` and re-run - but it is expected to succeed (extra confirmed present).

- [ ] **Step 4: Sync the environment (downloads Python 3.12 + wheels)**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv sync`
Expected: creates `.venv/`, installs all deps. Watch for any "Building wheel … / running setup.py" + a compiler error - there should be **none** (the 3.12 guarantee). PySide6 is large (~100s of MB); first sync is slow.

- [ ] **Step 5: Verify imports resolve under uv**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv run python -c "import spikeinterface, spikeinterface_gui, PySide6, ephyviewer, numba, hdbscan, zarr, plotly; import spikeinterface; print('spikeinterface', spikeinterface.__version__); print('imports OK')"`
Expected: prints the version and `imports OK` (no `ModuleNotFoundError`).

- [ ] **Step 6: Run the repo's de-facto test under uv**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv run python scripts/verify_install.py`
Expected: prints library versions + LFP/broadband/sorters summary, ending with `All good - SpikeInterface can read your data. ✓` (assumes the `PFCM7_d0ephys_Block2.*` data is present in the repo root, which it is locally).

- [ ] **Step 7: Confirm `.venv`/lock are git-handled correctly**

Run: `cd /Users/benfaib/Spike/SpikeInterface && git status --short && git check-ignore .venv uv.lock .python-version pyproject.toml`
Expected: `.venv` is ignored (already in `.gitignore`); `uv.lock`, `.python-version`, `pyproject.toml` are NOT ignored (they print nothing from `check-ignore` and appear as untracked in status).

- [ ] **Step 8: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add pyproject.toml .python-version uv.lock
git commit -m "feat(uv): add pyproject.toml + uv.lock for uv-first installs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Windows launchers (run.bat + run.ps1)

**Files:**
- Create: `/Users/benfaib/Spike/SpikeInterface/run.bat`
- Create: `/Users/benfaib/Spike/SpikeInterface/run.ps1`

- [ ] **Step 1: Write `run.bat`**

Create `/Users/benfaib/Spike/SpikeInterface/run.bat` with exactly:

```bat
@echo off
REM Double-click (or `run.bat report`) to launch the SpikeInterface menu via uv.
REM PYTHONUTF8=1 keeps the full-screen Unicode shield/box-drawing legible on
REM legacy cmd.exe; %~dp0 = this script's folder, so cwd does not matter.
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
uv run python "%~dp0SpikeInterface_Menu.py" %*
endlocal
```

- [ ] **Step 2: Write `run.ps1`**

Create `/Users/benfaib/Spike/SpikeInterface/run.ps1` with exactly:

```powershell
# Launch the SpikeInterface menu via uv (PowerShell).
#   .\run.ps1            # interactive menu
#   .\run.ps1 report     # run one action directly
$env:PYTHONUTF8 = "1"
Set-Location -Path $PSScriptRoot
uv run python (Join-Path $PSScriptRoot "SpikeInterface_Menu.py") @args
```

- [ ] **Step 3: Verify the wrapped command works (macOS proxy for the launcher body)**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv run python SpikeInterface_Menu.py --help`
Expected: prints the launcher's argparse help listing actions `explore|sort|report|gui|traces|compare|verify`. (The `.bat`/`.ps1` wrappers themselves are Windows-only; they are validated in Task 11's Windows checklist.)

- [ ] **Step 4: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add run.bat run.ps1
git commit -m "feat(uv): add Windows run.bat/run.ps1 launchers over uv run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Windows hardening #1 - robust folder removal in run_sorting.py

**Files:**
- Modify: `/Users/benfaib/Spike/SpikeInterface/scripts/run_sorting.py` (imports; new helper; calls before `sorting.save` and `create_sorting_analyzer`)

**Why:** On Windows, deleting a `sorting`/`analyzer` binary_folder still memory-mapped by a just-closed `spikeinterface-gui`/ephyviewer raises `PermissionError` (WinError 32). POSIX unlinks silently. Retry with a gc sweep + short backoff.

- [ ] **Step 1: Add `gc`, `shutil`, `time` imports (keep `os`/`warnings` for now - Task 4 removes them)**

Replace this block (lines ~37–42):

```python
import argparse
import os
import re
import sys
import warnings
from pathlib import Path
```

with:

```python
import argparse
import gc
import os
import re
import shutil
import sys
import time
import warnings
from pathlib import Path
```

- [ ] **Step 2: Add the `_robust_rmtree` helper**

Insert this function immediately **before** `def main() -> int:` (currently line ~251):

```python
def _robust_rmtree(path: Path, attempts: int = 5, delay: float = 0.5) -> None:
    """Remove a directory tree, retrying past transient Windows file locks.

    SpikeInterface writes ``sorting``/``analyzer`` as memory-mapped binary
    folders. On Windows a just-closed ``spikeinterface-gui``/ephyviewer can leave
    a lagging handle, so deleting the folder to overwrite it raises
    ``PermissionError`` (WinError 32) - POSIX unlinks an open file silently, so
    this only bites on Windows. Retry with a gc sweep + short backoff; re-raise
    if the lock never clears.
    """
    for attempt in range(attempts):
        try:
            if path.exists():
                shutil.rmtree(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            gc.collect()
            time.sleep(delay)
```

- [ ] **Step 3: Pre-remove the `sorting` folder before saving**

Replace (line ~322):

```python
    sorting = sorting.save(folder=str(out / "sorting"), overwrite=True)
```

with:

```python
    _robust_rmtree(out / "sorting")  # retry past Windows GUI file-locks before overwrite
    sorting = sorting.save(folder=str(out / "sorting"), overwrite=True)
```

- [ ] **Step 4: Pre-remove the `analyzer` folder before creating it**

Replace (lines ~326–328):

```python
        analyzer = si.create_sorting_analyzer(
            sorting, rec, folder=str(out / "analyzer"), format="binary_folder", overwrite=True
        )
```

with:

```python
        _robust_rmtree(out / "analyzer")  # retry past Windows GUI file-locks before overwrite
        analyzer = si.create_sorting_analyzer(
            sorting, rec, folder=str(out / "analyzer"), format="binary_folder", overwrite=True
        )
```

- [ ] **Step 5: Verify a short sort still runs end-to-end under uv**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv run python scripts/run_sorting.py --duration 5 --verbosity normal`
Expected: completes through "Sort" + "Quality metrics", prints the metrics table and `Done. ✓  Results in outputs/tridesclous2`. (Run twice in a row to exercise the overwrite path: the second run must also succeed.)

- [ ] **Step 6: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add scripts/run_sorting.py
git commit -m "fix(sort): retry folder removal past Windows file-locks (WinError 32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Windows hardening #2 - shared native-chatter muting helper

**Files:**
- Modify: `/Users/benfaib/Spike/SpikeInterface/scripts/blackrock_io.py` (add `mute_native_chatter()`)
- Modify: `/Users/benfaib/Spike/SpikeInterface/scripts/run_sorting.py` (use it; drop `_MUTED_WARNINGS` + now-unused `os`/`warnings` imports)
- Modify: `/Users/benfaib/Spike/SpikeInterface/SpikeInterface_Menu.py` (call it in `main()`)

**Why:** `run_sorting.py` mutes OpenMP/Numba/probe/resource-tracker noise before importing SI. The menu's in-process `report`/`compare` actions don't, so they're noisier (worse on Windows: per-process OpenMP banner). Hoist the muting into `blackrock_io` (imported by both, no heavy deps) and call it from the menu too.

- [ ] **Step 1: Add `mute_native_chatter()` to `blackrock_io.py`**

In `/Users/benfaib/Spike/SpikeInterface/scripts/blackrock_io.py`, insert the following immediately **after** the `use_utf8_stdout()` function (after its closing, around line 59, before the first `read_*` section):

```python
# Library/native chatter that is never useful signal - only clutter that breaks
# the clean terminal formatting. Muted everywhere it can leak: the verbose
# progress output, the in-process report/compare paths, and spawned sorter
# workers. Each entry is a regex matched against the START of a warning message
# (warnings uses re.match), so it silences the noise regardless of the Warning
# subclass that raised it:
#   - probe warning: sorters rebuild an internal recording that drops our probe
#   - resource_tracker: known multiprocessing shared-memory cleanup chatter
#   - non-persistent recording: expected - we register an in-memory recording
_MUTED_WARNINGS = (
    "There is no Probe attached",
    "resource_tracker",
    "The registered recording will not be persistent",
)


def mute_native_chatter() -> None:
    """Silence OpenMP/Numba/probe/resource-tracker noise.

    Call *before* importing spikeinterface so ``KMP_WARNINGS`` lands before
    OpenMP initialises and ``PYTHONWARNINGS=ignore`` propagates to any spawned
    sorter worker subprocess (whose warnings the in-process filters never see).
    Idempotent; safe to call from every entry point.
    """
    import os
    import warnings

    os.environ.setdefault("KMP_WARNINGS", "0")
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    for msg in _MUTED_WARNINGS:
        warnings.filterwarnings("ignore", message=msg)
    try:  # numba may be absent; its cast note is muted by category because numba
        from numba.core.errors import NumbaWarning  # prepends ANSI codes -> a message regex misses it

        warnings.filterwarnings("ignore", category=NumbaWarning)
    except Exception:
        pass
```

- [ ] **Step 2: Remove the old `_MUTED_WARNINGS` block from `run_sorting.py`**

In `/Users/benfaib/Spike/SpikeInterface/scripts/run_sorting.py`, delete the comment + tuple (lines ~50–63):

```python
# Library/native chatter muted at every level - it is never the "verbose"
# signal the user wants, it only breaks up the progress-bar formatting. Each
# entry is a regex matched against the start of a warning message (warnings uses
# re.match), so it silences the noise regardless of which Warning subclass raised it:
#   - probe warning: sorters rebuild an internal recording that drops our probe
#   - resource_tracker: known multiprocessing shared-memory cleanup chatter
#   - non-persistent recording: expected - we register an in-memory recording
# (The numba "unsafe cast" note is muted by category instead - numba prepends
# ANSI colour codes to its message, so a message regex would never match.)
_MUTED_WARNINGS = (
    "There is no Probe attached",
    "resource_tracker",
    "The registered recording will not be persistent",
)
```

Delete the entire block above (leave one blank line where it was, so the following `_TQDM_DESC_WIDTH` comment block is still separated).

- [ ] **Step 3: Swap the inline muting for the shared helper in `configure_output()`**

In `/Users/benfaib/Spike/SpikeInterface/scripts/run_sorting.py`, replace this block inside `configure_output` (lines ~227–243):

```python
    # UTF-8 stdout/stderr first, before rich/tqdm/SI build any console - so the
    # ✓ / → / … glyphs below never raise UnicodeEncodeError on a legacy Windows
    # console code page (cp1252/cp437) when output is redirected or piped.
    bio.use_utf8_stdout()
    # Set before the heavy imports: KMP_WARNINGS kills the "OMP: Info #276 ..."
    # banner; PYTHONWARNINGS=ignore also covers any spawned worker subprocesses,
    # whose warnings the main process's filters below would never see.
    os.environ.setdefault("KMP_WARNINGS", "0")
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    for msg in _MUTED_WARNINGS:
        warnings.filterwarnings("ignore", message=msg)
    try:  # numba may be absent; its cast warning is muted by category
        from numba.core.errors import NumbaWarning

        warnings.filterwarnings("ignore", category=NumbaWarning)
    except Exception:
        pass
```

with:

```python
    # UTF-8 stdout/stderr first, before rich/tqdm/SI build any console - so the
    # ✓ / → / … glyphs below never raise UnicodeEncodeError on a legacy Windows
    # console code page (cp1252/cp437) when output is redirected or piped. Then
    # mute OpenMP/Numba/probe/resource-tracker noise before the heavy imports.
    bio.use_utf8_stdout()
    bio.mute_native_chatter()
```

- [ ] **Step 4: Drop the now-unused `os` and `warnings` imports from `run_sorting.py`**

Confirm they're unused: `cd /Users/benfaib/Spike/SpikeInterface && grep -n "\bos\.\|\bwarnings\." scripts/run_sorting.py`
Expected: **no output** (their only uses were the muting block just removed).

Then replace (the import block, post-Task-3 state):

```python
import argparse
import gc
import os
import re
import shutil
import sys
import time
import warnings
from pathlib import Path
```

with:

```python
import argparse
import gc
import re
import shutil
import sys
import time
from pathlib import Path
```

- [ ] **Step 5: Call the helper in the menu's `main()`**

In `/Users/benfaib/Spike/SpikeInterface/SpikeInterface_Menu.py`, replace (lines ~328–329):

```python
def main() -> int:
    bio.use_utf8_stdout()
```

with:

```python
def main() -> int:
    bio.use_utf8_stdout()
    bio.mute_native_chatter()  # quiet OpenMP/Numba/probe noise for in-process report/compare too
```

- [ ] **Step 6: Verify run_sorting still works and the menu report path is quiet**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv run python scripts/run_sorting.py --duration 5 --verbosity quiet`
Expected: only the final metrics table + `Done.` (no probe/OpenMP/numba warnings).

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv run python SpikeInterface_Menu.py report`
Expected: builds `outputs/report.html` and opens it, with no probe/resource_tracker warnings spewed to the console.

- [ ] **Step 7: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add scripts/blackrock_io.py scripts/run_sorting.py SpikeInterface_Menu.py
git commit -m "refactor(output): share native-chatter muting; apply it in the menu too

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Windows hardening #3 - utf-8 for `.si_menu.json`

**Files:**
- Modify: `/Users/benfaib/Spike/SpikeInterface/SpikeInterface_Menu.py` (`_load_config`/`_save_config`)

- [ ] **Step 1: Add explicit utf-8 encoding to the config read/write**

In `/Users/benfaib/Spike/SpikeInterface/SpikeInterface_Menu.py`, replace (lines ~54–65):

```python
def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:  # noqa: BLE001 - missing/corrupt -> defaults
        return {}


def _save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:  # noqa: BLE001 - best-effort
        pass
```

with:

```python
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
```

- [ ] **Step 2: Verify the menu still loads/saves config**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv run python SpikeInterface_Menu.py --help`
Expected: help prints with no error (config read path executes on launch via `_apply_saved_theme(_load_config())`).

- [ ] **Step 3: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add SpikeInterface_Menu.py
git commit -m "fix(config): read/write .si_menu.json as utf-8

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Docstring sweep - conda → uv

**Files:** modify the leading usage lines in 7 files. Each currently shows `conda activate si_env` followed by `python …`. Replace the two-line pair with a single `uv run python …` line (drop the activate step - uv needs no activation).

- [ ] **Step 1: `SpikeInterface_Menu.py` docstring (lines ~4–7)**

Replace:

```python
    conda activate si_env
    python SpikeInterface_Menu.py            # interactive status + menu
    python SpikeInterface_Menu.py report     # run one action directly, then exit
    python SpikeInterface_Menu.py --help
```

with:

```python
    uv run python SpikeInterface_Menu.py            # interactive status + menu
    uv run python SpikeInterface_Menu.py report     # run one action directly, then exit
    uv run python SpikeInterface_Menu.py --help
    REM Windows: double-click run.bat (or: run.bat report)
```

- [ ] **Step 2: `scripts/explore_data.py` docstring (lines ~3–5)**

Replace:

```python
    conda activate si_env
    python scripts/explore_data.py            # uses the data in the repo root
    python scripts/explore_data.py --data-dir /path/to/another/recording
```

with:

```python
    uv run python scripts/explore_data.py            # uses the data in the repo root
    uv run python scripts/explore_data.py --data-dir /path/to/another/recording
```

- [ ] **Step 3: `scripts/run_sorting.py` docstring (lines ~3–9)**

Replace:

```python
    conda activate si_env
    python scripts/run_sorting.py                          # tridesclous2, full recording
    python scripts/run_sorting.py --sorter spykingcircus2  # the other installed sorter
    python scripts/run_sorting.py --duration 30            # quick test: first 30 s only
    python scripts/run_sorting.py --data-dir /path/to/recording
    python scripts/run_sorting.py --verbosity normal       # step messages + table, no bars
    python scripts/run_sorting.py --verbosity quiet        # only the final result + table
```

with:

```python
    uv run python scripts/run_sorting.py                          # tridesclous2, full recording
    uv run python scripts/run_sorting.py --sorter spykingcircus2  # the other installed sorter
    uv run python scripts/run_sorting.py --duration 30            # quick test: first 30 s only
    uv run python scripts/run_sorting.py --data-dir /path/to/recording
    uv run python scripts/run_sorting.py --verbosity normal       # step messages + table, no bars
    uv run python scripts/run_sorting.py --verbosity quiet        # only the final result + table
```

- [ ] **Step 4: `scripts/report.py` docstring (lines ~3–5)**

Replace:

```python
    conda activate si_env
    python scripts/make_report.py          # interactive launcher (preferred)
    python -c "import sys; sys.path.insert(0,'scripts'); import report; report.build_report()"
```

with:

```python
    uv run python scripts/make_report.py   # interactive launcher (preferred)
    uv run python -c "import sys; sys.path.insert(0,'scripts'); import report; report.build_report()"
```

- [ ] **Step 5: `scripts/make_report.py` docstring (lines ~3–6)**

Replace:

```python
    conda activate si_env
    python scripts/make_report.py                 # builds + opens the report
    python scripts/make_report.py --data-dir DIR
    python scripts/make_report.py --sorter spykingcircus2
```

with:

```python
    uv run python scripts/make_report.py                 # builds + opens the report
    uv run python scripts/make_report.py --data-dir DIR
    uv run python scripts/make_report.py --sorter spykingcircus2
```

- [ ] **Step 6: `scripts/compare.py` docstring (lines ~3–4)**

Replace:

```python
    conda activate si_env
    python scripts/compare.py            # builds outputs/comparison.html
```

with:

```python
    uv run python scripts/compare.py     # builds outputs/comparison.html
```

- [ ] **Step 7: `scripts/verify_install.py` docstring (lines ~3–6)**

Replace:

```python
Run it after creating the environment:

    conda activate si_env
    python scripts/verify_install.py
```

with:

```python
Run it after creating the environment:

    uv run python scripts/verify_install.py
```

- [ ] **Step 8: Verify nothing broke (modules still import + run)**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv run python SpikeInterface_Menu.py --help && uv run python scripts/run_sorting.py --help`
Expected: both print help with no syntax/import error.

Run: `cd /Users/benfaib/Spike/SpikeInterface && grep -rn "conda activate si_env" SpikeInterface_Menu.py scripts/*.py`
Expected: **no output** (all script docstrings converted).

- [ ] **Step 9: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add SpikeInterface_Menu.py scripts/explore_data.py scripts/run_sorting.py scripts/report.py scripts/make_report.py scripts/compare.py scripts/verify_install.py
git commit -m "docs(scripts): docstring usage examples use uv run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: README - uv-first onboarding

**Files:** modify `/Users/benfaib/Spike/SpikeInterface/README.md` in place, section by section.

- [ ] **Step 1: Rewrite the "First-time setup" intro + install section (lines 32–58)**

Replace from `## First-time setup (macOS & Windows)` through the end of the PowerShell paragraph (the block currently lines 32–58, ending `...RemoteSigned`.)`) with:

```markdown
## First-time setup (macOS & Windows)

From a clean machine to a working install. Install **uv** once (step 1); after
that everything runs with `uv run …` - no environment to "activate".

### 1. Install uv (one-time)

[uv](https://docs.astral.sh/uv/) is a fast Python package/environment manager. It
installs Python itself, so you do **not** need conda or a system Python.

**Windows** (PowerShell or cmd):

```powershell
winget install --id=astral-sh.uv -e
```

**macOS / Linux:**

```bash
brew install uv        # or: curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen the terminal afterwards so `uv` is on `PATH`.

> **Prefer conda?** It still works as a fallback - see *Fallback: conda* at the
> bottom of this section.
```

- [ ] **Step 2: Rewrite "Create the environment" (lines 82–101)**

Replace from `### 4. Create the environment (one-time, ~5–10 min)` through the end of the `> uv is a faster drop-in…` blockquote (lines 82–101) with:

```markdown
### 4. Create the environment (one-time, ~5–10 min)

```bash
uv sync          # builds .venv from the committed uv.lock (Python 3.12 + all deps)
```

`uv sync` downloads a private **Python 3.12** (if you don't have one), then
installs the locked scientific stack (numpy/scipy/numba/hdbscan/…),
`spikeinterface[full,widgets]` with the `tridesclous2` and `spykingcircus2`
sorters, the PySide6 desktop GUIs, and Plotly. **Python 3.12 is pinned on
purpose** - it has prebuilt wheels for every dependency on Windows, so the
install never needs a C/C++ compiler. To include the Jupyter notebook tools:

```bash
uv sync --extra notebooks
```

> **Fallback: conda.** Prefer conda? `conda env create -f environment.yml` then
> `conda activate si_env` still works (it installs PyQt5 instead of PySide6 for
> the GUIs). Use this only if you can't or won't install uv.
```

- [ ] **Step 3: Rewrite "Verify it works" (lines 103–113)**

Replace:

```markdown
### 5. Verify it works

```bash
conda activate si_env          # if not already active
python scripts/verify_install.py
```
```

with:

```markdown
### 5. Verify it works

```bash
uv run python scripts/verify_install.py
```
```

(Leave the "Prints library versions…you're ready." paragraph that follows unchanged.)

- [ ] **Step 4: Rewrite "Running everything" intro + Quick start (lines 115–146)**

Replace from `## Running everything` through the second ```` ```bash ```` / `conda activate si_env` / ```` ``` ```` block and the run-list (lines 115–146) with:

```markdown
## Running everything

No activation step - every command is just `uv run …` (or, on Windows,
double-click `run.bat`).

### Quick start - the menu

The simplest way in is the single launcher at the repo root:

```bash
uv run python SpikeInterface_Menu.py        # status dashboard + a numbered menu
```

On **Windows** you can instead double-click **`run.bat`** (or run `run.bat` /
`.\run.ps1` from a terminal) - it wraps the same command.

Pick a number to explore the data, run a sort, build & open the interactive HTML
report, open the `spikeinterface-gui` inspector, scroll raw traces, or compare
the two sorters. Power users can run a single action directly, e.g.
`uv run python SpikeInterface_Menu.py report` or `uv run python SpikeInterface_Menu.py gui`.

The whole workflow, in order:

```bash
uv run python scripts/verify_install.py     # 1. sanity-check the env + that the data loads
uv run python scripts/explore_data.py       # 2. save LFP / raster / firing-rate PNGs to outputs/
uv run python scripts/run_sorting.py        # 3. spike-sort the .ns5 broadband -> outputs/tridesclous2/
uv run jupyter lab notebooks/01_explore_lfp_and_spikes.ipynb   # 4a. explore LFP + units interactively
uv run jupyter lab notebooks/02_spike_sorting.ipynb            # 4b. sort interactively, with plots
```
```

- [ ] **Step 5: Fix the notebook-kernel bullet (line 156)**

Replace:

```markdown
- **Notebooks:** after `jupyter lab` opens, pick the **`si_env`** kernel
  (Kernel ▸ Change Kernel) - it was registered in setup step 4.
```

with:

```markdown
- **Notebooks:** `uv run jupyter lab` uses the project's own `.venv` kernel -
  no `ipykernel install` step needed. Just open a notebook and run.
```

- [ ] **Step 6: Fix the "Use the loaders" + Project layout (lines 161, 180–181)**

Replace (line 161):

```markdown
**Use the loaders in your own code** (`scripts/blackrock_io.py`):
```

- leave as-is (no change). Then in the Project-layout code block replace:

```
├── environment.yml      # conda environment (Option A)
├── requirements.txt     # pip/uv environment (Option B)
```

with:

```
├── pyproject.toml       # uv environment (primary) - `uv sync`
├── uv.lock              # locked, reproducible resolution
├── environment.yml      # conda environment (fallback)
├── run.bat / run.ps1    # Windows launchers (uv run …)
```

- [ ] **Step 7: Spike-sorting + report command examples (lines 200–205, 240–241, 254–255)**

In the Spike-sorting code block (lines 200–205) replace each `python scripts/run_sorting.py` with `uv run python scripts/run_sorting.py` (4 lines).

In the report block (lines 239–242) replace:

```bash
conda activate si_env
python SpikeInterface_Menu.py report   # build + open outputs/report.html
# scripts/make_report.py still works - it's now a thin shim that calls the above
```

with:

```bash
uv run python SpikeInterface_Menu.py report   # build + open outputs/report.html
# scripts/make_report.py still works - it's now a thin shim that calls the above
```

In the paragraph at lines 253–255 replace `python SpikeInterface_Menu.py` (both occurrences) and `python scripts/run_sorting.py` with their `uv run python …` forms.

- [ ] **Step 8: Windows notes - shells + UTF-8 (lines 263–268)**

Replace:

```markdown
- **Any shell works.** The sorters are pure in-process Python, so cmd, PowerShell
  and the Anaconda Prompt are all fine - use whichever has `conda` initialised
  (the Anaconda Prompt needs no setup).
- **Console output is UTF-8-safe.** The scripts force UTF-8 stdout so the `✓`/`→`
  status glyphs don't `UnicodeEncodeError` when you redirect output to a file on a
  legacy console code page (`python scripts\run_sorting.py > log.txt`).
```

with:

```markdown
- **Any shell works.** cmd and PowerShell are both fine; `run.bat` / `run.ps1`
  set `PYTHONUTF8=1` for you. For the full-screen menu, **Windows Terminal** (or
  Windows 10 1903+) renders the Unicode shield/box-drawing best.
- **Console output is UTF-8-safe.** The scripts force UTF-8 stdout so the `✓`/`→`
  status glyphs don't `UnicodeEncodeError` when you redirect output to a file on a
  legacy console code page (`uv run python scripts\run_sorting.py > log.txt`).
```

- [ ] **Step 9: Troubleshooting (lines 277–286)**

Replace:

```markdown
- **`No module named 'spikeinterface'`** - activate the env first
  (`conda activate si_env`).
- **Jupyter uses the wrong Python** - install/select the kernel:
  `python -m ipykernel install --user --name si_env`, then pick `si_env` in
  Jupyter.
- **A dependency tries to compile from source on Windows** (e.g. an
  `error: Microsoft Visual C++ 14.0 ... is required`) - you're probably on a
  Python version that lacks a prebuilt wheel for it. Recreate the env with
  **Python 3.12**, which has wheels for every dependency (or use the conda path,
  which installs binaries). On 3.12 no compiler is needed.
```

with:

```markdown
- **`No module named 'spikeinterface'`** - run scripts with `uv run python …`
  (uv resolves the env automatically), or run `uv sync` first.
- **Jupyter uses the wrong Python** - launch it with `uv run jupyter lab`; it
  uses the project `.venv` kernel, so no `ipykernel install` is needed.
- **A dependency tries to compile from source on Windows** (e.g. an
  `error: Microsoft Visual C++ 14.0 ... is required`) - uv is pinned to
  **Python 3.12** via `.python-version`, which has prebuilt wheels for every
  dependency, so this should not happen. If you bypassed uv and used a different
  Python, switch back to `uv sync`.
```

- [ ] **Step 10: Verify the README has no stale conda-first instructions in the primary flow**

Run: `cd /Users/benfaib/Spike/SpikeInterface && grep -n "conda activate si_env\|ipykernel install\|requirements.txt\|Miniconda\|Anaconda Prompt" README.md`
Expected: the only remaining hits are inside the clearly-labelled conda **fallback** blocks (setup step 4 fallback + a possible References line). No conda commands remain in the primary setup/run/troubleshooting flow.

- [ ] **Step 11: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add README.md
git commit -m "docs(readme): uv-first onboarding; conda demoted to a fallback

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: CLAUDE.md - uv-first commands + Qt note

**Files:** modify `/Users/benfaib/Spike/SpikeInterface/CLAUDE.md`

- [ ] **Step 1: Commands block (lines 24–41)**

Replace the first line of the ```` ```bash ```` Commands block:

```
conda activate si_env                  # env is conda, Python 3.12, named si_env
python SpikeInterface_Menu.py          # ⭐ single front door: status dashboard + menu (explore/sort/report/gui/traces/compare/verify)
```

with:

```
uv sync                                # build .venv from uv.lock (Python 3.12 + all deps); conda fallback: conda env create -f environment.yml
uv run python SpikeInterface_Menu.py   # ⭐ single front door: status dashboard + menu (explore/sort/report/gui/traces/compare/verify)
```

Then replace every remaining bare `python ` at the start of a command line in that block (lines 27–41: `python SpikeInterface_Menu.py …`, `python scripts/…`, `jupyter lab …`) with the `uv run ` prefix (`uv run python SpikeInterface_Menu.py …`, `uv run python scripts/…`, `uv run jupyter lab …`). There are 13 such lines (27–41).

- [ ] **Step 2: Env (re)creation line (line 46)**

Replace:

```
Env (re)creation: `conda env create -f environment.yml` (Option A) or `uv pip install -r requirements.txt` into a 3.12 venv (Option B). `verify_install.py` is the closest thing to a test - run it to confirm changes to the loaders still read the data.
```

with:

```
Env (re)creation: `uv sync` (Option A - primary; reads `pyproject.toml` + `uv.lock`, fetches Python 3.12) or `conda env create -f environment.yml` (Option B - conda fallback). `uv run python scripts/verify_install.py` is the closest thing to a test - run it to confirm changes to the loaders still read the data.
```

- [ ] **Step 3: Python 3.12 / pins note (line 48)**

Replace:

```
**Use Python 3.12, not 3.13** - broadest prebuilt-wheel coverage across the whole dependency set on Windows, so the install never needs a C/C++ compiler (current `hdbscan` 0.8.44 *does* now ship 3.13 Windows wheels, but other deps may still lag, so 3.12 stays the tested choice). Pins that matter: `zarr<3` (SpikeInterface doesn't support zarr 3.x), `PySide6<6.8`.
```

with:

```
**Use Python 3.12, not 3.13** - broadest prebuilt-wheel coverage across the whole dependency set on Windows, so the install never needs a C/C++ compiler (current `hdbscan` 0.8.44 *does* now ship 3.13 Windows wheels, but other deps may still lag, so 3.12 stays the tested choice). uv enforces this via `requires-python = "==3.12.*"` in `pyproject.toml` + a `.python-version` file. Pins that matter (carried in `pyproject.toml`): `zarr<3` (SpikeInterface doesn't support zarr 3.x), `plotly<6` (report.py inlines `plotly.offline.get_plotlyjs`), and the PySide6 desktop GUI binding.
```

- [ ] **Step 4: Qt-binding note (lines 114–116)**

Replace:

```
The Qt
binding in `si_env` is **PyQt5** (the `PySide6<6.8` pin is satisfied by a pip
install but the conda env resolves to PyQt5; either works).
```

with:

```
The Qt
binding under uv is **PySide6** (pulled by `spikeinterface-gui[desktop]`); the
conda fallback (`environment.yml`) resolves to **PyQt5** instead - either works,
but don't install both into one env.
```

- [ ] **Step 5: Verify no stale conda-primary command remains**

Run: `cd /Users/benfaib/Spike/SpikeInterface && grep -n "uv pip install -r requirements\|conda activate si_env" CLAUDE.md`
Expected: **no output** (the `conda env create` fallback reference may remain in the env-creation line - that's intended).

- [ ] **Step 6: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add CLAUDE.md
git commit -m "docs(claude): uv-first commands + PySide6 Qt note

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: environment.yml cleanup + drop requirements.txt

**Files:**
- Modify: `/Users/benfaib/Spike/SpikeInterface/environment.yml`
- Delete: `/Users/benfaib/Spike/SpikeInterface/requirements.txt`

- [ ] **Step 1: Add a uv pointer to the top of environment.yml**

Replace the first two comment lines:

```yaml
# Conda environment for SpikeInterface - works on macOS, Windows and Linux.
#
```

with:

```yaml
# Conda environment for SpikeInterface - works on macOS, Windows and Linux.
#
# NOTE: the PRIMARY install path is now uv (`uv sync`, see pyproject.toml /
# README.md). This conda file is kept as a fallback for conda users. Under conda
# the Qt GUIs resolve to PyQt5; under uv they resolve to PySide6.
#
```

- [ ] **Step 2: Drop the unused `xarray` dependency**

Remove this line from the `dependencies:` list:

```yaml
  - xarray
```

(`grep -rn "import xarray\|xarray" scripts SpikeInterface_Menu.py notebooks` returns nothing - it's dead weight.)

- [ ] **Step 3: Delete requirements.txt (tracked file → git rm)**

Run: `cd /Users/benfaib/Spike/SpikeInterface && git rm requirements.txt`
Expected: `rm 'requirements.txt'`.

- [ ] **Step 4: Verify the conda file still parses (optional, mac has conda)**

Run: `cd /Users/benfaib/Spike/SpikeInterface && python -c "import yaml,sys; d=yaml.safe_load(open('environment.yml')); assert 'xarray' not in (d['dependencies']); print('environment.yml OK, deps:', len(d['dependencies']))"`
Expected: prints `environment.yml OK, deps: N` with no `xarray`. (If PyYAML isn't on the base python, run it via `uv run python …` instead.)

- [ ] **Step 5: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add environment.yml
git commit -m "chore(deps): drop requirements.txt + unused xarray; point env.yml at uv

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Notebooks - kernel labels + setup note

**Files:**
- Modify: `/Users/benfaib/Spike/SpikeInterface/notebooks/01_explore_lfp_and_spikes.ipynb`
- Modify: `/Users/benfaib/Spike/SpikeInterface/notebooks/02_spike_sorting.ipynb`

These are JSON. Edit the exact strings (kernelspec `display_name` and one markdown line). The `"name": "python3"` is generic and already resolves under uv - only the label/markdown are misleading.

- [ ] **Step 1: Notebook 01 - markdown setup note (line 16)**

In `notebooks/01_explore_lfp_and_spikes.ipynb` replace the string:

```
    "Make sure you launched Jupyter from the `si_env` environment (see `README.md`)."
```

with:

```
    "Make sure you launched Jupyter from the project venv: `uv run jupyter lab` (see `README.md`)."
```

- [ ] **Step 2: Notebook 01 - kernel display_name (line 187)**

Replace:

```
   "display_name": "Python 3 (si_env)",
```

with:

```
   "display_name": "Python 3",
```

- [ ] **Step 3: Notebook 02 - kernel display_name (line 160)**

In `notebooks/02_spike_sorting.ipynb` replace:

```
   "display_name": "si_env",
```

with:

```
   "display_name": "Python 3",
```

- [ ] **Step 4: Verify both notebooks are still valid JSON**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv run python -c "import json; [json.load(open(f)) for f in ['notebooks/01_explore_lfp_and_spikes.ipynb','notebooks/02_spike_sorting.ipynb']]; print('notebooks valid JSON')"`
Expected: `notebooks valid JSON` (no `JSONDecodeError`).

- [ ] **Step 5: Commit**

```bash
cd /Users/benfaib/Spike/SpikeInterface
git add notebooks/01_explore_lfp_and_spikes.ipynb notebooks/02_spike_sorting.ipynb
git commit -m "docs(notebooks): drop si_env kernel labels; uv run jupyter lab note

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Final verification + branch finish

**Files:** none (verification only).

- [ ] **Step 1: Clean re-sync from the committed lock**

Run: `cd /Users/benfaib/Spike/SpikeInterface && uv sync --frozen`
Expected: succeeds using the committed `uv.lock` with no re-resolution (`--frozen` fails loudly if the lock is stale vs pyproject).

- [ ] **Step 2: Full smoke test under uv (macOS)**

Run each and confirm:
- `uv run python scripts/verify_install.py` → ends with `All good … ✓`
- `uv run python scripts/run_sorting.py --duration 5 --verbosity normal` → completes, metrics table printed
- `uv run python SpikeInterface_Menu.py report` → writes `outputs/report.html`
- `uv run python SpikeInterface_Menu.py --help` → action list prints

- [ ] **Step 3: Grep for any leftover conda-primary references**

Run: `cd /Users/benfaib/Spike/SpikeInterface && grep -rn "conda activate si_env" --include=*.py --include=*.md --include=*.ipynb . | grep -v docs/superpowers`
Expected: no output outside the conda-fallback prose in README/CLAUDE (the `conda env create -f environment.yml` fallback mentions are intended and use a different string).

- [ ] **Step 4: Confirm the full file set is committed**

Run: `cd /Users/benfaib/Spike/SpikeInterface && git status --short`
Expected: clean working tree except the pre-existing unrelated edits (`CLAUDE.md` was committed by Task 8; `scripts/ui.py` may still show as `M` from before this work - leave it).

- [ ] **Step 5: Windows verification checklist (hand off to Ben - cannot run here)**

On a Windows machine:
1. `winget install --id=astral-sh.uv -e`, reopen terminal.
2. `cd` into the clone (with the `PFCM7_*` data present), run `uv sync` - confirm **no compiler / MSVC** message appears.
3. `uv run python scripts/verify_install.py` → `All good … ✓`.
4. Double-click `run.bat` (and try `run.bat report`) → menu opens; report builds.
5. Menu → `gui` and `traces` → confirm real Qt windows open (PySide6) via the `_self` child process.
6. Open the GUI, close it, then run a sort again from the menu → confirm **no WinError 32 / PermissionError** (the Task 3 retry).
7. `uv run jupyter lab notebooks/01_explore_lfp_and_spikes.ipynb` → kernel resolves, cells run.

- [ ] **Step 6: Finish the branch**

Use the superpowers:finishing-a-development-branch skill to choose merge / PR / cleanup for `uv-windows-port`.

---

## Self-review notes (author checklist - completed)

- **Spec coverage:** every spec section maps to a task - §3.1 new files → Tasks 1–2; §3.2 deps/PySide6/drop-xarray/drop-requirements → Tasks 1, 9; §3.3 docs → Tasks 6–8; §3.4 notebooks → Task 10; §3.5 the three hardenings → Tasks 3–5; §6 verification → Tasks 1, 11.
- **No placeholders:** every code/doc step shows exact before/after text and an explicit verify command + expected output.
- **Consistency:** helper named `mute_native_chatter` and `_robust_rmtree` everywhere; import edits sequenced so each commit leaves a working tree (Task 3 adds `gc/shutil/time` keeping `os/warnings`; Task 4 removes `os/warnings` only after deleting their last use).
- **Windows-only checks** (`.bat`/`.ps1`, Qt windows, WinError 32) are explicitly deferred to Task 11 step 5, since they can't be exercised on macOS.
