# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small SpikeInterface workspace for analysing one Blackrock/Ripple recording that lives in the repo root. The file set shares the base name `PFCM7_d0ephys_Block2`:

- `.ns2` — analog **LFP** @ **1 kHz** (neo stream id `2`, channels labelled `lfp N`) → SpikeInterface **Recording** via `read_lfp()`.
- `.ns5` — raw **broadband** @ **30 kHz** (neo stream id `5`, 22 ch, ~132 s) → SpikeInterface **Recording** via `read_broadband()`. This is the spike-sortable stream.
- `.nev` — **spike events** / waveform snippets + digital markers, timestamped at the **30 kHz** system clock → SpikeInterface **Sorting** (already-detected online units) via `read_spikes()`.

There is no package, no test suite, and no build step — it's loader code (`scripts/blackrock_io.py`) plus thin scripts and notebooks that consume it.

## Sorting status & the probe gap (read before touching the sorting pipeline)

Spike sorting **is** possible because the raw broadband `.ns5` is present. Two facts shape how it's done here:

- **No electrode geometry.** The Blackrock files carry no probe/channel map (`get_probe()` raises; there are no channel locations), and the real physical layout is unknown. `read_broadband()` therefore attaches a **placeholder "independent-channel" probe** (`attach_dummy_probe()` — channels laid out in a column 250 µm apart so no two are spatial neighbours). Per-unit results are valid; cross-channel *spatial* info is not physical until a real map is supplied — to swap it in, build a `probeinterface.Probe` and call `recording.set_probe(...)`. Don't tell the user sorting is blocked on geometry; it runs without it.
- **Installed sorters are CPU-only:** `tridesclous2` and `spykingcircus2` (both bundled in `spikeinterface[full]`, no GPU/extra install). `run_sorting.py` exposes both via `--sorter`. Kilosort4 etc. are **not** installed and need an NVIDIA GPU + PyTorch (absent here).

## Commands

```bash
conda activate si_env                  # env is conda, Python 3.12, named si_env
python scripts/verify_install.py       # smoke test — lib versions, LFP + broadband + sorters summary
python scripts/explore_data.py         # writes lfp_traces.png / spike_raster.png / firing_rates.png to outputs/ (git-ignored)
python scripts/explore_data.py --data-dir /path/to/other/recording
python scripts/run_sorting.py          # sort .ns5 broadband with tridesclous2 -> outputs/<sorter>/
python scripts/run_sorting.py --sorter spykingcircus2
python scripts/run_sorting.py --duration 30    # quick smoke test: sort only first 30 s
jupyter lab notebooks/01_explore_lfp_and_spikes.ipynb   # explore LFP + .nev units
jupyter lab notebooks/02_spike_sorting.ipynb            # interactive sort of the .ns5 broadband
```

The raw recordings are **git-ignored** (`*.ns[1-6]`, `*.nev` — the `.ns5` is ~176 MB, over GitHub's 100 MB/file limit), so a fresh clone has no data. The `PFCM7_d0ephys_Block2.{ns2,ns5,nev}` set must sit in the repo root (or be pointed at with `--data-dir`); loaders auto-discover any Blackrock file set by base name, so a missing set surfaces as a clear `FileNotFoundError` from `find_blackrock_base()`.

Env (re)creation: `conda env create -f environment.yml` (Option A) or `uv pip install -r requirements.txt` into a 3.12 venv (Option B). `verify_install.py` is the closest thing to a test — run it to confirm changes to the loaders still read the data.

**Use Python 3.12, not 3.13** (`hdbscan` lacks 3.13 Windows wheels). Pins that matter: `zarr<3` (SpikeInterface doesn't support zarr 3.x), `PySide6<6.8`.

## Architecture

`scripts/blackrock_io.py` is the single source of truth for loading this dataset. Everything else imports it — and because it's not an installed package, consumers prepend `scripts/` to `sys.path` first:

```python
import sys; sys.path.insert(0, "scripts")   # notebook uses Path.cwd().parent / "scripts"
import blackrock_io as bio
recording = bio.read_lfp()        # .ns2 LFP @ 1 kHz       -> Recording
broadband = bio.read_broadband()  # .ns5 @ 30 kHz + probe  -> Recording (sortable)
sorting   = bio.read_spikes()     # .nev online units      -> Sorting
events    = bio.read_events()     # digital markers        -> list of {name, times, labels}
bio.list_streams()                # (stream_name, stream_id) tuples for the nsX file set
```

All loaders default to reading the repo root and accept `data_dir=...` to point elsewhere.

`scripts/run_sorting.py` is the sorting entry point built on these loaders: `read_broadband()` → `bandpass_filter(300–6000)` → `common_reference(median)` → `run_sorter(--sorter)` → save Sorting + `SortingAnalyzer` quality metrics under `outputs/<sorter>/`. Use `--duration N` to sort only the first N seconds as a smoke test.

Non-obvious behaviours baked into the loaders — preserve these when editing:

- **neo file-set semantics:** neo treats the filename *without extension* as a set of files sharing a base name (`foo.nev` + `foo.ns2` + `foo.ns5`). `find_blackrock_base()` returns that extension-less stem; pass it (not a specific extension) to `read_blackrock` / `get_neo_streams`. `read_spikes` is the exception — it appends `.nev` explicitly.
- **Stream selection:** `read_blackrock` rejects receiving *both* `stream_id` and `stream_name`. `read_lfp` resolves to a single `stream_id` (the first stream = `.ns2` LFP) and leaves `stream_name=None` to avoid this. `read_broadband` picks the **highest-sampling-rate** stream via `find_broadband_stream()` and raises if it's below 10 kHz (i.e. only LFP is present).
- **Probe attachment:** `read_broadband(attach_probe=True)` calls `attach_dummy_probe()` (placeholder independent-channel geometry) because the files have none — see the "Sorting status & probe gap" section. `set_probe(...)` returns a *new* recording; it does not mutate in place.
- **NEV timestamp rate:** spike sample indices are converted to seconds with `NEV_TIMESTAMP_RATE = 30_000.0` (from this file's NEURALEV 2.2 header), passed as the Sorting's `sampling_frequency`.
- **Blackrock unit-id convention:** `0` = unsorted threshold crossings, `1..n` = online-sorted units, `255` = noise/invalidated.
- **Events are best-effort:** `read_events` drops to `neo.rawio.BlackrockRawIO` directly and returns `[]` when there are no event channels; callers wrap it in try/except.

## Conventions for new scripts

- Scripts set `matplotlib.use("Agg")` **before** importing `pyplot` (headless-safe) and write figures to `outputs/` (git-ignored).
- Wrap entry points in `if __name__ == "__main__":` and return an int from `main()` (`raise SystemExit(main())`) — also required for `n_jobs > 1` on Windows (`spawn`).
- Use `pathlib` throughout (`REPO_ROOT` is exported from `blackrock_io`) so code runs unchanged on macOS/Windows/Linux.
