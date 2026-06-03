# SpikeInterface workspace — PFCM7 LFP + spike events

A ready-to-run [SpikeInterface](https://spikeinterface.readthedocs.io/en/stable/)
setup for analysing the Blackrock/Ripple recording in this repo. Works on
**macOS and Windows** (and Linux).

## The data

| File | Format | Contents |
|------|--------|----------|
| `PFCM7_d0ephys_Block2.ns2` | Blackrock `NEURALCD` v2.2, **1 kHz** | Analog **LFP** (channels labelled `lfp N`) |
| `PFCM7_d0ephys_Block2.ns5` | Blackrock `NEURALCD` v2.2, **30 kHz** | Raw **broadband** (22 channels) — spike-sortable |
| `PFCM7_d0ephys_Block2.nev` | Blackrock `NEURALEV` v2.2, 30 kHz clock | **Spike events** / waveform snippets + digital event markers |

Recorded with Trellis (Ripple), April 2025.

> 📁 **Getting the data.** These recordings are **not committed** to git (they're
> `.gitignore`d — the `.ns5` alone is ~176 MB, over GitHub's 100 MB/file limit).
> A fresh clone has no data: drop the `PFCM7_d0ephys_Block2.{ns2,ns5,nev}` file
> set into the repo root (or point any script at it with `--data-dir /path/...`).
> The scripts auto-discover the Blackrock file set by base name, so any
> `.nev`/`.nsX` set works.

> ℹ️ **Spike sorting is enabled** by the raw broadband `.ns5` (30 kHz). Run it
> with [`scripts/run_sorting.py`](#spike-sorting). The files carry **no electrode
> geometry**, so the pipeline attaches a placeholder *independent-channel* probe
> — sorting runs and per-unit metrics are valid, but cross-channel spatial
> information isn't physical until a real probe map is supplied. You can also
> still explore the LFP, load the already-detected `.nev` units, and do
> peri-event/LFP analysis.

## First-time setup (macOS & Windows)

From a clean machine to a working install. Do steps 1–4 **once**; after that you
only run `conda activate si_env` (step 5) in each new terminal.

### 1. Install Miniconda (one-time)

Miniconda gives you the `conda` package manager. Skip this if you already have
conda or Anaconda. Universal installer: <https://www.anaconda.com/download/success>.

**macOS** (Apple Silicon or Intel):

```bash
brew install --cask miniconda       # or run the installer from the link above
conda init "$(basename "$SHELL")"   # then close and reopen the terminal
```

**Windows:**

```bat
winget install -e --id Anaconda.Miniconda3   REM or run the installer from the link above
```

Then open **"Anaconda Prompt (miniconda3)"** from the Start menu and run every
command below there — it has `conda` pre-initialised, so it's the simplest. (PowerShell
also works after a one-time `conda init powershell` + restarting the shell; if you then
hit a script-blocked error, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.)

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
conda env create -f environment.yml                 # builds si_env from conda-forge + pip
conda activate si_env
python -m ipykernel install --user --name si_env    # register the env as a Jupyter kernel
```

This installs Python 3.12, the scientific stack (numpy/scipy/numba/hdbscan/…),
and `spikeinterface[full,widgets]` — including the `tridesclous2` and
`spykingcircus2` sorters. **Use Python 3.12**, not 3.13 — it has the broadest
prebuilt-wheel coverage across the whole dependency set on Windows, so the install
never needs a compiler.

> **No conda?** Pip/venv works instead — create a Python 3.12 virtual env and
> `pip install -r requirements.txt`:
> - macOS/Linux: `python3.12 -m venv si_env && source si_env/bin/activate`
> - Windows: `py -3.12 -m venv si_env && si_env\Scripts\activate`
>
> `uv` is a faster drop-in: `uv venv si_env --python 3.12 && uv pip install -r requirements.txt`.

### 5. Verify it works

```bash
conda activate si_env          # if not already active
python scripts/verify_install.py
```

Prints library versions and a summary of the LFP recording, the broadband
(spike-sortable) recording, the installed sorters, the spike units, and the
event channels. When it ends with `All good — SpikeInterface can read your data. ✓`,
you're ready.

## Running everything

Activate the environment first — once per terminal (Windows: the **Anaconda
Prompt** is the zero-config option; PowerShell/cmd work too after `conda init`):

```bash
conda activate si_env
```

Then the whole workflow, in order:

```bash
python scripts/verify_install.py     # 1. sanity-check the env + that the data loads
python scripts/explore_data.py       # 2. save LFP / raster / firing-rate PNGs to outputs/
python scripts/run_sorting.py        # 3. spike-sort the .ns5 broadband -> outputs/tridesclous2/
jupyter lab notebooks/01_explore_lfp_and_spikes.ipynb   # 4a. explore LFP + units interactively
jupyter lab notebooks/02_spike_sorting.ipynb            # 4b. sort interactively, with plots
```

What each does:

- **`explore_data.py`** writes `lfp_traces.png`, `spike_raster.png` and
  `firing_rates.png` to `outputs/` (git-ignored). Needs no display — safe over SSH.
- **`run_sorting.py`** is the full sorting pipeline; see
  [Spike sorting](#spike-sorting) for the `--sorter` / `--duration` / `--data-dir`
  options and the output layout. It runs on CPU in a couple of minutes; add
  `--duration 30` to sort just the first 30 s as a quick check.
- **Notebooks:** after `jupyter lab` opens, pick the **`si_env`** kernel
  (Kernel ▸ Change Kernel) — it was registered in setup step 4.
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
├── environment.yml      # conda environment (Option A)
├── requirements.txt     # pip/uv environment (Option B)
├── scripts/
│   ├── blackrock_io.py    # reusable loaders (read_lfp / read_broadband / read_spikes / read_events)
│   ├── verify_install.py  # smoke test
│   ├── explore_data.py    # save exploratory figures to outputs/
│   └── run_sorting.py     # spike-sort the .ns5 broadband -> outputs/<sorter>/
├── notebooks/
│   ├── 01_explore_lfp_and_spikes.ipynb
│   └── 02_spike_sorting.ipynb   # interactive sorting of the .ns5 broadband
├── PFCM7_d0ephys_Block2.ns2   # your data (LFP, 1 kHz)
├── PFCM7_d0ephys_Block2.ns5   # your data (raw broadband, 30 kHz — sortable)
└── PFCM7_d0ephys_Block2.nev   # your data (spike events)
```

## Spike sorting

The raw broadband `.ns5` (30 kHz) is what makes sorting possible. `scripts/run_sorting.py`
runs the whole pipeline:

```bash
python scripts/run_sorting.py                          # tridesclous2 (default), full recording
python scripts/run_sorting.py --sorter spykingcircus2  # the other installed sorter
python scripts/run_sorting.py --duration 30            # quick test: first 30 s only
python scripts/run_sorting.py --data-dir /path/to/recording
```

It reads the broadband, attaches a placeholder probe (see below), band-passes
(300–6000 Hz), applies a common median reference, runs the chosen sorter, and
writes everything to `outputs/<sorter>/` (git-ignored):

```
outputs/tridesclous2/
├── sorter_output/        # raw sorter working folder
├── sorting/              # saved SI Sorting   (reload: si.load(".../sorting"))
├── analyzer/             # SortingAnalyzer    (open in spikeinterface-gui, or reload)
└── quality_metrics.csv   # per-unit firing rate / SNR / ISI-violation table
```

For an interactive walk-through of the same pipeline (on a short slice, with
plots), use `jupyter lab notebooks/02_spike_sorting.ipynb`.

**About the probe / geometry.** These Blackrock files contain **no electrode map**,
and the physical array layout is unknown, so the pipeline attaches a placeholder
*independent-channel* probe (channels spaced far apart so the sorter assumes no
adjacency). Sorting runs and per-unit metrics are valid, but **cross-channel
spatial information is not physical**. If you obtain the real geometry, build a
[`probeinterface`](https://probeinterface.readthedocs.io/) `Probe` and swap it in
— in `scripts/blackrock_io.py`, replace the `attach_dummy_probe` call with
`recording.set_probe(real_probe)`.

**Sorters.** `tridesclous2` and `spykingcircus2` ship with
`spikeinterface[full]`, run on CPU, and need no extra install — those are the two
wired into `run_sorting.py`. **Kilosort4** is faster but needs an NVIDIA GPU
(CUDA + PyTorch, `pip install kilosort`) and so won't run on this Mac. Kilosort
1–3, IronClust, etc. need MATLAB or Docker.

## One-glance HTML report

```bash
conda activate si_env
python scripts/make_report.py     # prints a health check, offers a re-sort menu,
                                  # then writes outputs/report.html
```

`outputs/report.html` is a **single self-contained file** (open it in any
browser — Plotly is inlined, so it works offline) that lets you confirm the whole
pipeline at a glance: a PASS/FAIL **status banner**, **LFP** traces + power
spectrum, the **`.nev`** online units, the **sorted units** (raster + waveform
templates), **quality metrics** (sortable table + SNR-vs-rate scatter), and the
**event-marker** timeline.

`make_report.py` reloads the raw data through the loaders every time (so it
re-checks that loading works) and visualises the **saved** sort. Press **Enter**
to reuse that sort, or pick a **quick** (first 30 s) or **full** re-sort from the
menu first — re-sorting just runs `run_sorting.py` for you. Each section is
isolated, so if one stage is broken it shows up as a red/SKIP row instead of
crashing the report.

## Windows notes

- **Multiprocessing:** when you call SpikeInterface functions with `n_jobs > 1`
  in a script, wrap the entry point in `if __name__ == "__main__":` (Windows
  uses `spawn`). The provided scripts already do this.
- **Any shell works.** The sorters are pure in-process Python, so cmd, PowerShell
  and the Anaconda Prompt are all fine — use whichever has `conda` initialised
  (the Anaconda Prompt needs no setup).
- **Console output is UTF-8-safe.** The scripts force UTF-8 stdout so the `✓`/`→`
  status glyphs don't `UnicodeEncodeError` when you redirect output to a file on a
  legacy console code page (`python scripts\run_sorting.py > log.txt`).
- Keep output paths short if you save in **`.zarr`** — its deeply-nested chunk
  files can hit Windows' 260-character path limit. (The default `run_sorting.py`
  pipeline writes a `binary_folder`, not zarr, and stays well under the limit.)
  On Windows 10 1607+ you can also lift the limit via the `LongPathsEnabled`
  registry key / Group Policy.

## Troubleshooting

- **`No module named 'spikeinterface'`** — activate the env first
  (`conda activate si_env`).
- **Jupyter uses the wrong Python** — install/select the kernel:
  `python -m ipykernel install --user --name si_env`, then pick `si_env` in
  Jupyter.
- **A dependency tries to compile from source on Windows** (e.g. an
  `error: Microsoft Visual C++ 14.0 ... is required`) — you're probably on a
  Python version that lacks a prebuilt wheel for it. Recreate the env with
  **Python 3.12**, which has wheels for every dependency (or use the conda path,
  which installs binaries). On 3.12 no compiler is needed.

## References

- SpikeInterface docs: <https://spikeinterface.readthedocs.io/en/stable/>
- Installation tips: <https://github.com/SpikeInterface/spikeinterface/tree/main/installation_tips>
- Blackrock extractor API: `spikeinterface.extractors.read_blackrock` /
  `read_blackrock_sorting`
