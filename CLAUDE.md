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
- **Sorters are discovered dynamically** via `scripts/sorters.py` (the registry — single source of truth). `installed_sorters()` runnable locally today: `tridesclous2`, `spykingcircus2`, `lupin`, `simple`. Not-installed **CPU** sorters (mountainsort5, herdingspikes, spykingcircus, waveclus, combinato, …) can run via **opt-in Docker** (`run_sorter(..., docker_image=True)`) — Docker is detected at runtime. **GPU sorters** (kilosort*, pykilosort, yass) are shown but never offered: no NVIDIA GPU here, and Docker-on-Mac has no GPU passthrough. `sorters.status(name)` → `local`/`docker`/`gpu`/`unavailable`.

## Commands

```bash
uv sync                                # build .venv from uv.lock (Python 3.12 + all deps); conda fallback: conda env create -f environment.yml
uv run python SpikeInterface_Menu.py   # ⭐ single front door: status dashboard + menu (explore/sort/report/gui/traces/compare/verify)
uv run python SpikeInterface_Menu.py report   # or run one action directly: explore|sort|report|gui|traces|compare|verify
uv run python SpikeInterface_Menu.py gui --sorter tridesclous2   # spikeinterface-gui (sigui) on the saved sort
uv run python scripts/verify_install.py       # smoke test — lib versions, LFP + broadband + sorters summary
uv run python -m pytest tests/                 # Textual Pilot tests for the v2 menu (small-size / focus / missing-data)
uv run python scripts/explore_data.py         # writes lfp_traces.png / spike_raster.png / firing_rates.png to outputs/ (git-ignored)
uv run python scripts/explore_data.py --data-dir /path/to/other/recording
uv run python scripts/run_sorting.py          # sort .ns5 broadband with tridesclous2 -> outputs/<sorter>/
uv run python scripts/run_sorting.py --sorter spykingcircus2
uv run python scripts/run_sorting.py --duration 30    # quick smoke test: sort only first 30 s
uv run python scripts/run_sorting.py --verbosity normal    # step messages + table only, no progress bars
uv run python scripts/run_sorting.py --verbosity quiet     # only the final quality-metrics table
uv run python scripts/run_sorting.py --list-sorters          # availability table for every SI sorter
uv run python scripts/run_sorting.py --sorter mountainsort5 --docker   # run a not-installed CPU sorter via Docker
uv run python scripts/run_sorting.py --param detect_threshold=6.5 --param freq_min=250   # per-run param overrides
uv run python scripts/run_sorting.py --params-file my_params.json       # overrides from a JSON file
uv run python scripts/make_report.py          # thin shim -> SpikeInterface_Menu.py report (builds outputs/report.html)
uv run python scripts/make_report.py --data-dir /path/to/recording
uv run python scripts/compare.py              # agreement matrix between the two sorters -> outputs/comparison.html
uv run jupyter lab notebooks/01_explore_lfp_and_spikes.ipynb   # explore LFP + .nev units
uv run jupyter lab notebooks/02_spike_sorting.ipynb            # interactive sort of the .ns5 broadband
```

The raw recordings are **git-ignored** (`*.ns[1-6]`, `*.nev` — the `.ns5` is ~176 MB, over GitHub's 100 MB/file limit), so a fresh clone has no data. The `PFCM7_d0ephys_Block2.{ns2,ns5,nev}` set must sit in the repo root (or be pointed at with `--data-dir`); loaders auto-discover any Blackrock file set by base name, so a missing set surfaces as a clear `FileNotFoundError` from `find_blackrock_base()`.

Env (re)creation: `uv sync` (Option A — primary; reads `pyproject.toml` + `uv.lock`, fetches Python 3.12) or `conda env create -f environment.yml` (Option B — conda fallback). `uv run python scripts/verify_install.py` is the closest thing to a loader smoke test — run it to confirm changes to the loaders still read the data — and `uv run python -m pytest tests/` runs the Textual menu tests (a `dev` dependency-group with `pytest` + `pytest-asyncio`; install with `uv sync --group dev`). The v2 menu needs **`textual`** (a runtime dependency in `pyproject.toml`); without it the launcher falls back to the legacy prompt_toolkit/typed menu.

**Use Python 3.12, not 3.13** — broadest prebuilt-wheel coverage across the whole dependency set on Windows, so the install never needs a C/C++ compiler (current `hdbscan` 0.8.44 *does* now ship 3.13 Windows wheels, but other deps may still lag, so 3.12 stays the tested choice). uv enforces this via `requires-python = "==3.12.*"` in `pyproject.toml` + a `.python-version` file. Pins that matter (carried in `pyproject.toml`): `zarr<3` (SpikeInterface doesn't support zarr 3.x), `plotly<6` (report.py inlines `plotly.offline.get_plotlyjs`), and the PySide6 desktop GUI binding.

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

`scripts/run_sorting.py` is the sorting entry point built on these loaders: `read_broadband()` → `bandpass_filter(300–6000)` → `common_reference(median)` → `run_sorter(--sorter)` → save Sorting + `SortingAnalyzer` quality metrics under `outputs/<sorter>/`. Use `--duration N` to sort only the first N seconds as a smoke test.

**Terminal presentation** (`run_sorting.py` only) is layered: `--verbosity {quiet,normal,verbose}` (default `verbose`) picks how much shows — `verbose` = numbered phase headers + per-step sorter prints + progress bars, `normal` = headers + final table (no bars), `quiet` = final table only.
- `configure_output()` runs **before** importing SpikeInterface (so env vars/the tqdm patch land before OpenMP/Numba/the sorters init). It mutes chatter at *every* level: sets `KMP_WARNINGS`/`PYTHONWARNINGS` (kills the OpenMP banner + covers worker subprocesses), filters the probe/resource_tracker/non-persistent `UserWarning`s, and mutes `NumbaWarning` by **category** (a message regex misses it — numba prepends ANSI codes to the message).
- `_install_aligned_tqdm()` (verbose only) monkeypatches `tqdm` so every bar is uniform: strips the `(no parallelization)`/`(workers: …)` suffix, pads each description to a **fixed width** (`_TQDM_DESC_WIDTH`), and draws a **fixed-width coloured** bar (`_TQDM_BAR_WIDTH`/`_TQDM_BAR_COLOUR`, not stretched to the terminal edge) via one `bar_format`. Must patch before the SpikeInterface import so the libraries' `from tqdm.auto import tqdm` picks up the subclass.
- `ConsoleUI` renders the structured output with **rich** (now an explicit dep; degrades to plain `print` if rich is absent): a banner rule, numbered `[i/N]` phase headers (cyan/bold), dim detail lines, a boxed per-unit quality-metrics `Table`, and a green `✓ Done` line. Colours auto-disable when stdout isn't a TTY.

`scripts/report.py` builds a single self-contained `outputs/report.html` (Plotly JS **inlined**, so it opens offline) via `build_report(data_dir, analyzer_dir, out_path)`. Each loader stage runs in its own try/except (a failure becomes a red/SKIP row in the status banner, never a crashed report), and sorted-unit data — sorting, waveform templates, quality metrics — is read **only** from the saved `SortingAnalyzer` (its single source of truth; the loose `outputs/<sorter>/sorting/` folder and `quality_metrics.csv` are from other runs and ignored). Sections: status banner, LFP traces + Welch spectrum, `.nev` online units, sorted units (raster/rates/templates), quality metrics (sortable table + SNR scatter), event-marker timeline, footer. The interactive front door is now `SpikeInterface_Menu.py` (see below); `scripts/make_report.py` is a thin shim that forwards to it.

`SpikeInterface_Menu.py` (repo **root**, not `scripts/`) is the single front-door
launcher: run bare it opens an interactive dashboard; run with an action
(`report`, `sort`, `gui`, `traces`, `compare`, `verify`, `explore`) it dispatches
directly. The interactive view (terminal UI **v2**) is a **single full-screen Textual app**
(`scripts/menu_app.py`'s `SpikeMenuApp`) — a *resident* dashboard that stays
usable at **any window size**, from a wide desktop down to a short VS Code pane.
The launcher builds a `MenuController` (the bridge to dashboard data + action
running) and runs the app; the app is a pure view that calls back into the
controller. Layout is **two-pane and responsive**: a left **Sorter** sidebar (a
focusable list, one row per sorter with a `● … ACTIVE` marker + `Nu · Ns`
saved-sort summary) above a compact **Pipeline** panel (LFP/Broadband/.nev/Events
with ✓/–/✗), and a right **Actions** list. On narrow terminals (`< NARROW_COLS`,
≈78) the panes **stack**; on short terminals the shield collapses
(full→compact→mini→hidden) and **both lists scroll** — so the active sorter and
the actions are never clipped. **Navigation:** ←/→ (or Tab/Shift-Tab) move focus
**between** the Sorter and Actions panes (the focused pane shows an accent
border); ↑/↓ (or j/k) move within it; Enter on a sorter makes it active, Enter on
an action runs it; **1–9** jump-run an action, **t** cycles the active sorter,
**d** opens data-setup help, `q`/Esc/Ctrl-C quit (j/k and Space also work). The active sorter stays marked
independently of focus and is echoed in the footer. Actions run via Textual's
**`suspend()`** (the app drops out of the alt-screen so the action's own stdout
scrolls normally, then resumes and re-renders) — the sort-span and theme picks
use in-app **modal** screens, while compare's conditional re-sort prompt still
uses `ui.select` during the suspend. **Missing data:** `_data_report()`
classifies the data dir as complete / incomplete / absent; the app shows a red
**banner** when nothing is found (and dims the data-dependent actions) or an amber
*incomplete set* banner when only some files are present, and offers a **Data
Setup** screen (`d`, or the *Data files* action) listing each expected file
(`.ns2` LFP / `.ns5` broadband / `.nev` events) as a present/missing checklist
with the exact folder it belongs in. Off-TTY / without
Textual installed it falls back to the legacy `ui.dashboard_menu()`
(prompt_toolkit full-screen, else a typed numbered menu), which prepends the same
missing-data guidance in plain text.
A detailed
**blue + gold Pitt shield** (the `ui._LOGO_ART` ladder — 21/15/11-col grids of
only the full block `█` and spaces, every row the same width so it aligns in any
monospace terminal/font with no ambiguous-width glyphs) sits atop the view, drawn
by `ShieldWidget` which picks the largest crest that fits the live window (or
hides it). The heraldry sits in negative space (the empty interior = the white
field): crenellated turrets, a centre keystone notch, roundels over a blue/gold
checky band, tapering to the base point. The **accent colour is themeable**
(`ui.THEMES`: periwinkle/sea-green/steel-blue/amber/cyan; default periwinkle),
driven into the Textual **`$accentcolor`** CSS variable (via
`App.get_css_variables` + `refresh_css`); it is changed through the *Change colour
theme* modal and **persisted** to a git-ignored `.si_menu.json` at the repo root
(`_load_config`/`_save_config`), re-applied on launch with `ui.set_accent()`.
`scripts/ui.py` still holds the shared rich styling (rules, boxed tables, ✓
lines), the shield art + theme palette, and the inline `select()` used by the
fallback menu and compare's re-sort prompt. The controller shells out to the
`scripts/*.py`
for explore/sort/verify (live stdout), calls `report.build_report(...)`
in-process, and launches the **blocking** Qt GUIs in fresh child processes
(`_self`): the inspector is `spikeinterface-gui` (console command **`sigui
<analyzer_dir>`**, not `spikeinterface-gui`) and the trace browser is
`plot_traces(..., backend="ephyviewer")`. `make_report.py` is now a thin shim
over the launcher's `report` action. `scripts/compare.py` builds a standalone
`outputs/comparison.html` from `compare_two_sorters`; it refuses to draw a
misleading matrix when the two sorts cover different windows (the launcher's
`compare` action offers to re-sort both over a common window first). The Qt
binding under uv is **PySide6** (pulled by `spikeinterface-gui[desktop]`); the
conda fallback (`environment.yml`) resolves to **PyQt5** instead — either works,
but don't install both into one env.
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
