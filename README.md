# SpikeInterface workspace - PFCM7 LFP + spike events

A ready-to-run [SpikeInterface](https://spikeinterface.readthedocs.io/en/stable/)
setup for analysing the Blackrock/Ripple recording in this repo. Works on
**macOS and Windows** (and Linux).

## The data

| File | Format | Contents |
|------|--------|----------|
| `PFCM7_d0ephys_Block2.ns2` | Blackrock `NEURALCD` v2.2, **1 kHz** | Analog **LFP** (channels labelled `lfp N`) |
| `PFCM7_d0ephys_Block2.ns5` | Blackrock `NEURALCD` v2.2, **30 kHz** | Raw **broadband** (22 channels) - spike-sortable |
| `PFCM7_d0ephys_Block2.nev` | Blackrock `NEURALEV` v2.2, 30 kHz clock | **Spike events** / waveform snippets + digital event markers |

Recorded with Trellis (Ripple), April 2025.

> 📁 **Getting the data.** These recordings are **not committed** to git (they're
> `.gitignore`d - the `.ns5` alone is ~176 MB, over GitHub's 100 MB/file limit).
> A fresh clone has no data: drop the `PFCM7_d0ephys_Block2.{ns2,ns5,nev}` file
> set into the repo root (or point any script at it with `--data-dir /path/...`).
> The scripts auto-discover the Blackrock file set by base name, so any
> `.nev`/`.nsX` set works.

> ℹ️ **Spike sorting is enabled** by the raw broadband `.ns5` (30 kHz). Run it
> with [`scripts/run_sorting.py`](#spike-sorting). The files carry **no electrode
> geometry**, so the pipeline attaches a placeholder *independent-channel* probe
> - sorting runs and per-unit metrics are valid, but cross-channel spatial
> information isn't physical until a real probe map is supplied. You can also
> still explore the LFP, load the already-detected `.nev` units, and do
> peri-event/LFP analysis.

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

### 2. Get the code

```bash
git clone <this-repo-url> SpikeInterface
cd SpikeInterface
```

(Or download the repo as a ZIP and `cd` into the unzipped folder.)

### 3. Add the recording

The data is **not** in git (see *Getting the data* above). Copy the file set into
the repo root, next to `environment.yml`:

```
PFCM7_d0ephys_Block2.ns2     # LFP, 1 kHz
PFCM7_d0ephys_Block2.ns5     # raw broadband, 30 kHz (~176 MB)
PFCM7_d0ephys_Block2.nev     # spike events
```

(Or keep the data anywhere and pass `--data-dir /path/to/folder` to each script.)

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

### 5. Verify it works

```bash
uv run python scripts/verify_install.py
```

Prints library versions and a summary of the LFP recording, the broadband
(spike-sortable) recording, the installed sorters, the spike units, and the
event channels. When it ends with `All good - SpikeInterface can read your data. ✓`,
you're ready.

## Running everything

No activation step - every command is just `uv run …` (or, on Windows,
double-click `run.bat`).

> **New here, or want the whole loop in one place?** Read
> **[docs/WORKFLOW.md](docs/WORKFLOW.md)** - sort → read the strong-units block →
> triage → apply → Phy for the hard cases → import verdicts → benchmark against
> the manual `.nev` → regenerate from the record, each step with its exact
> command and where its output lands, plus a glossary and a table of which
> surface answers which question.

### Quick start - the menu

The simplest way in is the single launcher at the repo root:

```bash
uv run python SpikeInterface_Menu.py        # full-screen status dashboard + menu
```

On **Windows** you can instead double-click **`run.bat`** (or run `run.bat` /
`.\run.ps1` from a terminal) - it wraps the same command.

This opens the dashboard: a state block on top (DATA and PROBE · SORT · RESULTS -
which files loaded, the probe geometry, the active sorter and its saved sort, and
the headline result) over **one list of every function**, grouped as GET DATA ·
SORT & CURATE · LOOK & SHARE. Each row prints its own key: press it, or move with
**↑/↓** and press **Enter**. The footer keys are **m** (sorters & Docker),
**c** (colour theme), **?** (help) and **q** (quit); **Esc** deliberately does
nothing, so a reflexive back-press never exits. If a recording file is missing the menu says so and shows exactly which
file goes where. It resizes from a wide desktop down to a short editor pane, and
falls back to a plain typed menu when [Textual](https://textual.textualize.io) is
absent or output isn't a terminal.

Power users can run a single action directly (handy for scripting), e.g.
`uv run python SpikeInterface_Menu.py report`,
`uv run python SpikeInterface_Menu.py gui --sorter spykingcircus2`, or
`… gui --gui-mode web` for a browser-based inspector on a headless box. Every
action accepts `--data-dir /path/to/folder`.

The whole workflow, in order:

```bash
uv run python scripts/verify_install.py     # 1. sanity-check the env + that the data loads
uv run python scripts/explore_data.py       # 2. save LFP / raster / firing-rate PNGs to outputs/
uv run python scripts/run_sorting.py        # 3. spike-sort the .ns5 broadband -> outputs/tridesclous2/
uv run jupyter lab notebooks/01_explore_lfp_and_spikes.ipynb   # 4a. explore LFP + units interactively
uv run jupyter lab notebooks/02_spike_sorting.ipynb            # 4b. sort interactively, with plots
```

What each does:

- **`explore_data.py`** writes `lfp_traces.png`, `spike_raster.png` and
  `firing_rates.png` to `outputs/` (git-ignored). Needs no display - safe over SSH.
- **`run_sorting.py`** is the full sorting pipeline; see
  [Spike sorting](#spike-sorting) for the `--sorter` / `--duration` / `--data-dir`
  options and the output layout. It runs on CPU in a couple of minutes; add
  `--duration 30` to sort just the first 30 s as a quick check.
- **Notebooks:** `uv run jupyter lab` uses the project's own `.venv` kernel -
  no `ipykernel install` step needed. Just open a notebook and run.
- **Data elsewhere?** Every script accepts `--data-dir /path/to/folder`
  (default: the repo root).

**Use the loaders in your own code** (`scripts/blackrock_io.py`):

```python
import sys; sys.path.insert(0, "scripts")
import blackrock_io as bio

recording = bio.read_lfp()         # .ns2 LFP @ 1 kHz       -> SpikeInterface Recording
broadband = bio.read_broadband()   # .ns5 @ 30 kHz + probe  -> Recording (ready to sort)
sorting   = bio.read_spikes()      # .nev units             -> SpikeInterface Sorting
events    = bio.read_events()      # digital markers from the .nev
bio.list_streams()                 # what analog streams exist
```

By default they read the repo root; pass `data_dir="..."` to point elsewhere.

## Project layout

```
.
├── pyproject.toml       # uv environment (primary) - `uv sync`
├── uv.lock              # locked, reproducible resolution
├── environment.yml      # conda environment (fallback)
├── run.bat / run.ps1    # Windows launchers (uv run …)
├── SpikeInterface_Menu.py # ⭐ single front door: dashboard + menu, or `… <action>`
├── scripts/
│   ├── blackrock_io.py    # reusable loaders (read_lfp / read_broadband / read_spikes / read_events)
│   ├── verify_install.py  # smoke test
│   ├── explore_data.py    # save exploratory figures to outputs/
│   ├── run_sorting.py     # spike-sort the .ns5 broadband -> outputs/<sorter>/
│   ├── report.py          # build the self-contained interactive HTML report
│   ├── compare.py         # two-sorter agreement matrix -> outputs/comparison.html
│   ├── make_report.py     # thin shim -> the menu's `report` action
│   ├── menu_app.py        # the Textual v2 dashboard (SpikeMenuApp)
│   └── ui.py              # shared rich styling, the Pitt shield + theme palette
├── tests/                 # Textual Pilot tests for the menu (uv run python -m pytest)
├── notebooks/
│   ├── 01_explore_lfp_and_spikes.ipynb
│   └── 02_spike_sorting.ipynb   # interactive sorting of the .ns5 broadband
├── PFCM7_d0ephys_Block2.ns2   # your data (LFP, 1 kHz)
├── PFCM7_d0ephys_Block2.ns5   # your data (raw broadband, 30 kHz - sortable)
└── PFCM7_d0ephys_Block2.nev   # your data (spike events)
```

## Spike sorting

The raw broadband `.ns5` (30 kHz) is what makes sorting possible. `scripts/run_sorting.py`
runs the whole pipeline:

```bash
uv run python scripts/run_sorting.py                          # tridesclous2 (default), full recording
uv run python scripts/run_sorting.py --sorter spykingcircus2  # or lupin / simple (all installed)
uv run python scripts/run_sorting.py --duration 30            # quick test: first 30 s only
uv run python scripts/run_sorting.py --data-dir /path/to/recording
```

It reads the broadband, drops the 6 non-neural aux channels, applies the active
probe geometry, band-passes (300–6000 Hz), excludes bad channels, applies a common
median reference, runs the chosen sorter, and writes a NEW run directory - runs
never overwrite each other (git-ignored; `scripts/runs.py` owns the layout):

```
outputs/tridesclous2/
├── current.json          # which run every surface reads
└── runs/<run_id>/
    ├── run_info.json     # full provenance: params, seed, probe, versions, git sha
    ├── sorting/          # saved SI Sorting   (reload: si.load(".../sorting"))
    ├── analyzer/         # SortingAnalyzer    (open in spikeinterface-gui, or reload)
    └── quality_metrics.csv
```

A `--duration` smoke run never becomes current (`--make-current` overrides);
`uv run python scripts/runs.py list` shows every run.

For an interactive walk-through of the same pipeline (on a short slice, with
plots), use `jupyter lab notebooks/02_spike_sorting.ipynb`.

**About the probe / geometry.** These Blackrock files contain **no electrode map**,
so geometry is a user choice owned by `scripts/probes.py`. The default is this
rig's real **NeuroNexus A1x16-3mm-100-703** (16 contacts, 100 µm pitch); pick
another in the menu (`p`), import a probeinterface `.json`/`.prb` with
`uv run python scripts/probes.py import <file>`, or pass `--probe <name>` /
`--probe-file <file>`. A flagless CLI sort uses the probe the menu has active.

**Sorters.** Four sorters ship inside SpikeInterface itself - `tridesclous2`
(the default), `spykingcircus2`, `lupin`, `simple` - run on CPU, and need no
extra install. Others (mountainsort5, waveclus, ...) run through Docker when it
is on (the menu's `m` manages images). **Kilosort4** and the other GPU sorters
need an NVIDIA GPU and are not offered on this Mac.

## One-glance HTML report

```bash
uv run python SpikeInterface_Menu.py report   # build + open outputs/report.html
# scripts/make_report.py still works - it's now a thin shim that calls the above
```

`outputs/report.html` is a **single self-contained file** (open it in any
browser - Plotly is inlined, so it works offline) that lets you confirm the whole
pipeline at a glance: a PASS/FAIL **status banner**, **LFP** traces + power
spectrum, the **`.nev`** online units, the **sorted units** (raster + waveform
templates), **quality metrics** (sortable table + SNR-vs-rate scatter), and the
**event-marker** timeline.

The report reloads the raw data through the loaders every time (so it re-checks
that loading works) and visualises the **saved** sort. To (re-)run a sort first,
use the launcher's menu (`uv run python SpikeInterface_Menu.py` → *Run / re-run
sorting*) or `uv run python scripts/run_sorting.py`. Each section is isolated, so if one
stage is broken it shows up as a red/SKIP row instead of crashing the report.

## Windows notes

- **Multiprocessing:** when you call SpikeInterface functions with `n_jobs > 1`
  in a script, wrap the entry point in `if __name__ == "__main__":` (Windows
  uses `spawn`). The provided scripts already do this.
- **Any shell works.** cmd and PowerShell are both fine; `run.bat` / `run.ps1`
  set `PYTHONUTF8=1` for you. For the full-screen menu, **Windows Terminal** (or
  Windows 10 1903+) renders the Unicode shield/box-drawing best.
- **Console output is UTF-8-safe.** The scripts force UTF-8 stdout so the `✓`/`→`
  status glyphs don't `UnicodeEncodeError` when you redirect output to a file on a
  legacy console code page (`uv run python scripts\run_sorting.py > log.txt`).
- Keep output paths short if you save in **`.zarr`** - its deeply-nested chunk
  files can hit Windows' 260-character path limit. (The default `run_sorting.py`
  pipeline writes a `binary_folder`, not zarr, and stays well under the limit.)
  On Windows 10 1607+ you can also lift the limit via the `LongPathsEnabled`
  registry key / Group Policy.

## Troubleshooting

- **`No module named 'spikeinterface'`** - run scripts with `uv run python …`
  (uv resolves the env automatically), or run `uv sync` first.
- **Jupyter uses the wrong Python** - launch it with `uv run jupyter lab`; it
  uses the project `.venv` kernel, so no `ipykernel install` is needed.
- **A dependency tries to compile from source on Windows** (e.g. an
  `error: Microsoft Visual C++ 14.0 ... is required`) - uv is pinned to
  **Python 3.12** via `.python-version`, which has prebuilt wheels for every
  dependency, so this should not happen. If you bypassed uv and used a different
  Python, switch back to `uv sync`.

## References

- SpikeInterface docs: <https://spikeinterface.readthedocs.io/en/stable/>
- Installation tips: <https://github.com/SpikeInterface/spikeinterface/tree/main/installation_tips>
- Blackrock extractor API: `spikeinterface.extractors.read_blackrock` /
  `read_blackrock_sorting`
