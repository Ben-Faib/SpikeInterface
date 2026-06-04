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
python SpikeInterface_Menu.py          # ⭐ single front door: status dashboard + menu (explore/sort/report/gui/traces/compare/verify)
python SpikeInterface_Menu.py report   # or run one action directly: explore|sort|report|gui|traces|compare|verify
python SpikeInterface_Menu.py gui --sorter tridesclous2   # spikeinterface-gui (sigui) on the saved sort
python scripts/verify_install.py       # smoke test — lib versions, LFP + broadband + sorters summary
python scripts/explore_data.py         # writes lfp_traces.png / spike_raster.png / firing_rates.png to outputs/ (git-ignored)
python scripts/explore_data.py --data-dir /path/to/other/recording
python scripts/run_sorting.py          # sort .ns5 broadband with tridesclous2 -> outputs/<sorter>/
python scripts/run_sorting.py --sorter spykingcircus2
python scripts/run_sorting.py --duration 30    # quick smoke test: sort only first 30 s
python scripts/run_sorting.py --verbosity normal    # step messages + table only, no progress bars
python scripts/run_sorting.py --verbosity quiet     # only the final quality-metrics table
python scripts/make_report.py          # thin shim -> SpikeInterface_Menu.py report (builds outputs/report.html)
python scripts/make_report.py --data-dir /path/to/recording
python scripts/compare.py              # agreement matrix between the two sorters -> outputs/comparison.html
jupyter lab notebooks/01_explore_lfp_and_spikes.ipynb   # explore LFP + .nev units
jupyter lab notebooks/02_spike_sorting.ipynb            # interactive sort of the .ns5 broadband
```

The raw recordings are **git-ignored** (`*.ns[1-6]`, `*.nev` — the `.ns5` is ~176 MB, over GitHub's 100 MB/file limit), so a fresh clone has no data. The `PFCM7_d0ephys_Block2.{ns2,ns5,nev}` set must sit in the repo root (or be pointed at with `--data-dir`); loaders auto-discover any Blackrock file set by base name, so a missing set surfaces as a clear `FileNotFoundError` from `find_blackrock_base()`.

Env (re)creation: `conda env create -f environment.yml` (Option A) or `uv pip install -r requirements.txt` into a 3.12 venv (Option B). `verify_install.py` is the closest thing to a test — run it to confirm changes to the loaders still read the data.

**Use Python 3.12, not 3.13** — broadest prebuilt-wheel coverage across the whole dependency set on Windows, so the install never needs a C/C++ compiler (current `hdbscan` 0.8.44 *does* now ship 3.13 Windows wheels, but other deps may still lag, so 3.12 stays the tested choice). Pins that matter: `zarr<3` (SpikeInterface doesn't support zarr 3.x), `PySide6<6.8`.

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

**Terminal presentation** (`run_sorting.py` only) is layered: `--verbosity {quiet,normal,verbose}` (default `verbose`) picks how much shows — `verbose` = numbered phase headers + per-step sorter prints + progress bars, `normal` = headers + final table (no bars), `quiet` = final table only.
- `configure_output()` runs **before** importing SpikeInterface (so env vars/the tqdm patch land before OpenMP/Numba/the sorters init). It mutes chatter at *every* level: sets `KMP_WARNINGS`/`PYTHONWARNINGS` (kills the OpenMP banner + covers worker subprocesses), filters the probe/resource_tracker/non-persistent `UserWarning`s, and mutes `NumbaWarning` by **category** (a message regex misses it — numba prepends ANSI codes to the message).
- `_install_aligned_tqdm()` (verbose only) monkeypatches `tqdm` so every bar is uniform: strips the `(no parallelization)`/`(workers: …)` suffix, pads each description to a **fixed width** (`_TQDM_DESC_WIDTH`), and draws a **fixed-width coloured** bar (`_TQDM_BAR_WIDTH`/`_TQDM_BAR_COLOUR`, not stretched to the terminal edge) via one `bar_format`. Must patch before the SpikeInterface import so the libraries' `from tqdm.auto import tqdm` picks up the subclass.
- `ConsoleUI` renders the structured output with **rich** (now an explicit dep; degrades to plain `print` if rich is absent): a banner rule, numbered `[i/N]` phase headers (cyan/bold), dim detail lines, a boxed per-unit quality-metrics `Table`, and a green `✓ Done` line. Colours auto-disable when stdout isn't a TTY.

`scripts/report.py` builds a single self-contained `outputs/report.html` (Plotly JS **inlined**, so it opens offline) via `build_report(data_dir, analyzer_dir, out_path)`. Each loader stage runs in its own try/except (a failure becomes a red/SKIP row in the status banner, never a crashed report), and sorted-unit data — sorting, waveform templates, quality metrics — is read **only** from the saved `SortingAnalyzer` (its single source of truth; the loose `outputs/<sorter>/sorting/` folder and `quality_metrics.csv` are from other runs and ignored). Sections: status banner, LFP traces + Welch spectrum, `.nev` online units, sorted units (raster/rates/templates), quality metrics (sortable table + SNR scatter), event-marker timeline, footer. The interactive front door is now `SpikeInterface_Menu.py` (see below); `scripts/make_report.py` is a thin shim that forwards to it.

`SpikeInterface_Menu.py` (repo **root**, not `scripts/`) is the single front-door
launcher: run bare it opens an interactive dashboard; run with an action
(`report`, `sort`, `gui`, `traces`, `compare`, `verify`, `explore`) it dispatches
directly. The interactive view is a **single full-screen TUI** (`scripts/ui.py`'s
`dashboard_menu()`, built on `prompt_toolkit`) that updates **in place** — never
stacking duplicate dashboards. It pins a header (`University of Pittsburgh ·
SpikeInterface`), a **sorter tab bar** (one tab per sorter, switched with
**←/→** or **Tab/Shift-Tab**), the sorter-independent **pipeline status**, a
**last-action** line that updates as you do things, and the **action list**
(moved with **↑/↓** or j/k; Enter runs the highlighted action on the **active
tab's sorter** — there is no separate "which sorter" prompt; numbers jump;
`q`/Ctrl-C quits). Off-TTY / without prompt_toolkit it falls back to a scrolling
status panel + a typed numbered menu (with a *Switch sorter* entry). The palette
is the **cyan** accent shared with `run_sorting.py`. `scripts/ui.py` also holds
the shared rich styling (rules, boxed tables, ✓ lines) and the inline `select()`
(full/quick, compare prompts). It shells out to the `scripts/*.py`
for explore/sort/verify (live stdout), calls `report.build_report(...)`
in-process, and launches the **blocking** Qt GUIs in fresh child processes
(`_self`): the inspector is `spikeinterface-gui` (console command **`sigui
<analyzer_dir>`**, not `spikeinterface-gui`) and the trace browser is
`plot_traces(..., backend="ephyviewer")`. `make_report.py` is now a thin shim
over the launcher's `report` action. `scripts/compare.py` builds a standalone
`outputs/comparison.html` from `compare_two_sorters`; it refuses to draw a
misleading matrix when the two sorts cover different windows (the launcher's
`compare` action offers to re-sort both over a common window first). The Qt
binding in `si_env` is **PyQt5** (the `PySide6<6.8` pin is satisfied by a pip
install but the conda env resolves to PyQt5; either works).

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
