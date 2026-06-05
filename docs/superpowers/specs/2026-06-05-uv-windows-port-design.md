# Design: Port the SpikeInterface workspace from conda to uv (Windows-friendly)

**Date:** 2026-06-05
**Status:** Approved (pending spec review)
**Author:** brainstorming session (Claude + Ben)

## 1. Problem & goal

The workspace is onboarded via **conda** (`environment.yml`, `conda activate si_env`).
Conda is painful to install and get on `PATH` on Windows, which is the target
deployment OS. The goal is to make the project **easy to run on a fresh Windows
machine** by switching the primary toolchain to **uv** (Astral's fast Python
package/environment manager) — which installs Python itself, resolves a committed
lockfile, and runs scripts in one command, with **no compiler and no PATH
wrangling**.

> Note on naming: the original request said "uvicorn". Uvicorn is an ASGI web
> server and is unrelated to packaging. The correct tool is **uv**. This spec
> uses uv throughout.

### Decisions locked in brainstorming

| # | Decision | Choice |
|---|----------|--------|
| 1 | Scope of switch | **uv primary, keep conda** — add `pyproject.toml` + `uv.lock`; leave `environment.yml` as a conda fallback |
| 2 | Launch ergonomics | **Both** a double-click Windows launcher (`run.bat`/`run.ps1`) *and* a documented `uv run` command |
| 3 | GUIs/notebooks | **Include everything** — Qt desktop GUIs + Jupyter must work through uv on Windows with prebuilt wheels |
| 4 | Packaging shape | **A**: `pyproject.toml` + committed `uv.lock`, run scripts as files (no `[project.scripts]`) |
| 5 | Qt binding | **PySide6** via `spikeinterface-gui[desktop]` (resolves the env.yml-vs-requirements divergence) |
| 6 | `requirements.txt` | **Drop it** — `pyproject.toml` + `uv.lock` is the uv source of truth; `environment.yml` stays as the non-uv (conda) fallback |
| 7 | Windows code hardening (§3.5) | **In scope** — the 3 small robustness edits |

### Success criteria

- On a fresh Windows machine with only uv installed (one `winget` line), a user
  can go from clone → working menu with **`uv sync` then `run.bat`** (or
  `uv run python SpikeInterface_Menu.py`), with **no C/C++ compiler invoked**.
- Every previously documented command works with a `uv run` prefix; the argparse
  surface and behaviour are unchanged.
- All features work through uv: explore, sort, report, **gui**, **traces**,
  compare, verify, and both notebooks.
- The conda path (`environment.yml`) still works as a documented fallback.
- `uv run python scripts/verify_install.py` passes on macOS (de-facto test), and
  the Windows verification checklist passes.

## 2. Background facts (from read-only analysis)

The executable Python is already interpreter-agnostic and Windows-aware, so this
is **predominantly a packaging + docs job, not a logic job**:

- Every child process spawns via `[sys.executable, ...]` — never a bare
  `"python"`/`"sigui"`/`"jupyter"`, never `shell=True`
  (`SpikeInterface_Menu.py:128-141` `_shell`/`_self`; `make_report.py:24`). So the
  whole process tree inherits the correct interpreter **iff the top-level launcher
  is started by uv**.
- `sigui`/`ephyviewer` are launched by **import** (`spikeinterface_gui` at
  `SpikeInterface_Menu.py:193`; `plot_traces(backend="ephyviewer")` at `:213`),
  not by a console-script `.exe` on PATH — so the classic Windows shim/stale-PATH
  problem does not apply; they only need to be installed in the uv env.
- All paths use `pathlib`; every CLI has `if __name__=="__main__": raise
  SystemExit(main())` (correct for Windows `spawn` + `n_jobs>1`);
  `matplotlib.use("Agg")` is set before `pyplot`; `use_utf8_stdout()`
  (`blackrock_io.py:41-58`) already hardens the Windows console for the rich/print
  path.
- Installed versions in the live `si_env` (targets to match): spikeinterface
  **0.104.3**, numpy 2.4.6, scipy 1.17.1, numba 0.65.1, zarr 2.18.7, plotly
  5.24.1, Python 3.12.13.

## 3. Architecture / what changes

Three new packaging files, a launcher pair, doc rewrites, and three small code
hardenings. No change to the loader logic, the menu's action dispatch, or the
subprocess-spawning pattern (those are already uv-correct and must **not** be
regressed).

### 3.1 New files

**`pyproject.toml`** — single uv source of truth:

```toml
[project]
name = "spikeinterface-pfcm7"
version = "0.1.0"
description = "SpikeInterface workspace for the PFCM7 Blackrock/Ripple recording"
requires-python = "==3.12.*"
dependencies = [
  "spikeinterface[full,widgets]>=0.104,<0.105",
  "spikeinterface-gui[desktop]>=0.13",   # [desktop] => PySide6 + pyqtgraph
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
package = false   # run scripts as files; do not build/install this as a package
```

Rationale for each pin is in §4.

**`.python-version`** — contains `3.12` so `uv run`/`uv sync` auto-select the
right interpreter (uv will download it if absent).

**`uv.lock`** — generated via `uv lock`, committed for reproducible installs.
Generated on macOS; uv produces a **universal** lock (cross-platform markers,
e.g. `cuda-python` on non-Darwin). Validate on Windows during verification.

**`run.bat`** (Windows double-click launcher):

```bat
@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
uv run python "%~dp0SpikeInterface_Menu.py" %*
```

`PYTHONUTF8=1` keeps the full-screen Unicode shield/box-drawing legible on legacy
cmd.exe. `cd /d "%~dp0"` + absolute path make it cwd-independent. `%*` forwards
any action args (`run.bat report`).

**`run.ps1`** — PowerShell equivalent (`$env:PYTHONUTF8=1`; `uv run python`).

### 3.2 Dependency reconciliation

- **PySide6** is the chosen Qt binding (via `spikeinterface-gui[desktop]`).
  Do **not** also ship PyQt5 — they can clash at import.
- **Drop `requirements.txt`** — redundant with `pyproject.toml` + `uv.lock` (the
  uv source of truth). Non-uv users use the conda fallback (`environment.yml`).
  (No `[build-system]` is declared and `[tool.uv] package = false`, so the project
  installs deps only — it is not built/installed as an importable package; scripts
  run as files.)
- **Drop `xarray`** from `environment.yml` — zero references anywhere in the code.
- Promote to explicit deps (imported by name, previously transitive/conda-only):
  `numba` (run_sorting.py NumbaWarning + tqdm patch), `neo` + `probeinterface`
  (blackrock_io.py), `numpy`, `scipy`, `matplotlib`.
- `hdbscan` stays explicit — **not** pulled by `spikeinterface[full]`; the CPU
  sorters (tridesclous2/spykingcircus2) need it.

### 3.3 Doc rewrites

- **README.md** — uv-first onboarding. Install uv
  (`winget install --id=astral-sh.uv` on Windows / `brew install uv` on macOS),
  then `uv sync`, then `uv run ...`. Demote conda to a clearly-labelled "Fallback"
  section. Keep the Python-3.12 rationale text. Specific blocks:
  `README.md:32-58` (install), `:82-101` (env create), `:103-136` (run commands),
  `:156` (notebook kernel), `:180-181`/`:263-265` (relabel pip path),
  `:240`/`:277-285` (report block + troubleshooting).
- **CLAUDE.md** — `:25` Commands block leads with `uv run python
  SpikeInterface_Menu.py`; `:46` env-creation makes uv Option A / conda Option B;
  `:48`/`:115-116` Qt note → "uv installs PySide6; PyQt5 only under the conda
  fallback." Keep the zarr<3 / PySide6<6.8 / 3.12 pin rationale.
- **7 script docstrings** — swap the `conda activate si_env` lead-in for `uv run`:
  `SpikeInterface_Menu.py:4`, `scripts/explore_data.py:3`, `run_sorting.py:3`,
  `report.py:3`, `make_report.py:3`, `compare.py:3`, `verify_install.py:5`.
- **environment.yml** — keep as conda fallback; add a header line pointing to the
  uv path; drop `xarray`.

### 3.4 Notebooks

- Use `uv run jupyter lab notebooks/...` (venv's own kernel — no `ipykernel
  install` step). Fix the misleading kernel `display_name`
  (`notebooks/01...:187` `Python 3 (si_env)`, `notebooks/02...:160` `si_env`) to a
  generic `Python 3`, and the markdown cell `notebooks/01...:16` ("launched from
  the `si_env` environment" → "from the project venv via `uv run jupyter lab`").

### 3.5 Windows robustness (code edits, approved in scope)

1. **Re-sort file-lock** (`scripts/run_sorting.py`, around `:285/:316/:322`): wrap
   analyzer-folder removal in a retry-on-`PermissionError` (with a `gc.collect()`
   and short backoff). Windows raises WinError 32 where POSIX silently unlinks an
   open memory-mapped file; this is exactly the open-GUI → close → re-sort flow.
2. **In-process output muting**: hoist `run_sorting.configure_output()`'s
   OpenMP/Numba/warning muting into a shared helper (e.g. in `blackrock_io` or
   `ui`) and call it at the very top of `SpikeInterface_Menu.main()` **before any
   spikeinterface import**, so the in-process `report`/`compare` actions get the
   same clean output as `run_sorting.py`. Behaviour unchanged; cosmetic on
   Windows (per-process OpenMP banner).
3. **`.si_menu.json` encoding** (`SpikeInterface_Menu.py:54-65`): add
   `encoding="utf-8"` to the `read_text`/`write_text` calls.

### 3.6 Explicitly NOT changed (do not regress)

- `_shell`/`_self`/`make_report.py` `[sys.executable, ...]` spawning — keep
  exactly. Do **not** switch to bare `"python"`, `shutil.which`, or re-prefix `uv
  run` (would pick up a stale interpreter or double-spawn uv).
- The argparse action surface (`explore|sort|report|gui|traces|compare|verify`).
- Loader logic, probe handling, NEV timestamp conventions.
- The `if __name__=="__main__"` spawn guards and `main()->int` returns.

## 4. Dependency pins & rationale

| Pin | Reason |
|-----|--------|
| `requires-python = "==3.12.*"` | THE guarantee that every compiled dep gets a prebuilt `cp312-win_amd64` wheel — no MSVC. 3.13 risks an sdist build for whichever dep lags. |
| `spikeinterface[full,widgets]>=0.104,<0.105` | `[full]` = scientific stack (numba/sklearn/h5py/pandas); `[widgets]` = matplotlib/ipympl/ipywidgets/figpack. Cap to the tested 0.104 line; `uv.lock` pins exact. |
| `spikeinterface-gui[desktop]>=0.13` | `[desktop]` pulls PySide6 + pyqtgraph — chosen Qt binding. |
| `zarr>=2.18,<3` | SpikeInterface does not support zarr 3.x. |
| `plotly>=5.20,<6` | `report.py:186` relies on `plotly.offline.get_plotlyjs` to inline JS for the offline report; Plotly 6 reorganised this. |
| `hdbscan>=0.8.33` | Not pulled by `[full]`; sorters need it. 0.8.44 ships `cp312-win_amd64`. |
| `numba`, `neo`, `probeinterface`, `numpy`, `scipy>=1.10`, `matplotlib>=3.6` | Imported directly by name; list explicitly so the code's imports are guaranteed. |

**Windows-wheel verification:** every classic compiler-risk package ships a
`cp312-win_amd64` wheel (numpy, scipy, numba/llvmlite, h5py, hdbscan 0.8.44,
numcodecs, scikit-learn); the rest are pure-Python; PySide6 ships a stable-ABI
wheel with Qt bundled. **No compiler required at 3.12.** Note: `cuda-python` is
pulled transitively by `spikeinterface[full]` on non-Darwin — a pure-Python
metapackage, harmless but heavy; cannot be excluded without dropping `[full]`.

## 5. Entry-point mapping (current → uv)

| Current | uv equivalent |
|---------|---------------|
| `conda activate si_env; python SpikeInterface_Menu.py` | `uv run python SpikeInterface_Menu.py` (or `run.bat`) |
| `python SpikeInterface_Menu.py <action> [args]` | `uv run python SpikeInterface_Menu.py <action> [args]` |
| `python scripts/<name>.py [args]` | `uv run python scripts/<name>.py [args]` |
| `conda activate si_env; jupyter lab notebooks/...` | `uv run jupyter lab notebooks/...` |
| `conda env create -f environment.yml` | `uv sync` (primary) — conda still works as fallback |

## 6. Verification plan

**On macOS (now, by Claude):**
1. `uv lock` then `uv sync` — confirm clean resolution, commit `uv.lock`.
2. `uv run python scripts/verify_install.py` — the repo's de-facto test (lib
   versions + LFP + broadband + sorters summary).
3. `uv run python SpikeInterface_Menu.py report` — confirm the in-process report
   path works under uv (and the §3.5.2 muting).

**On Windows (checklist for Ben):**
1. Install uv (`winget install --id=astral-sh.uv`), `uv sync` — assert no MSVC /
   compiler is invoked during install.
2. `uv run python scripts/verify_install.py`.
3. `run.bat` → exercise sort, report, **gui**, **traces**, compare. Validate:
   (a) `gui`/`traces` open real Qt windows via the `_self` child; (b) a re-sort
   **after closing** the GUI does not hit WinError 32 (the §3.5.1 retry).
4. `uv run jupyter lab notebooks/01_explore_lfp_and_spikes.ipynb` — kernel
   resolves and cells run.

## 7. Out of scope

Real probe geometry, GPU sorters (Kilosort), any new analysis feature, and
`[project.scripts]` console commands. Historical `docs/.../plans/*` conda
references are left as an archival record.

## 8. Implementation order

1. **Packaging foundation** — write `pyproject.toml`, `.python-version`; `uv lock`
   + `uv sync`; commit `uv.lock`. Smoke test `verify_install.py` on macOS.
2. **Launchers** — `run.bat` + `run.ps1`.
3. **Windows hardening** — the 3 edits in §3.5.
4. **Docs** — README, CLAUDE.md, 7 docstrings, environment.yml (drop xarray +
   pointer), delete requirements.txt.
5. **Notebooks** — markdown cell + display_name fixes.
6. **Verify & finalize** — re-run `verify_install.py`; confirm report builds.

## 9. Open risks / notes

- `uv.lock` is generated on macOS; Windows resolution should be validated (it is
  universal by default, but confirm during the Windows checklist).
- The re-sort file-lock retry is a mitigation, not a guarantee; README also keeps
  a "close the GUI before re-sorting" note as belt-and-suspenders.
- PySide6 wheels are large (~100s of MB) — first `uv sync` will take a while.
