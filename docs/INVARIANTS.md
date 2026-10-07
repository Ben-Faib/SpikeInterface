# INVARIANTS.md - the rules that bite

Things that are wrong by default. Read this before editing or reviewing code; the reviewer
checks every diff against it. Each module's docstring carries the detail; the map is
`docs/ARCHITECTURE.md`.

## Measured facts of record

Measured on this recording. Designs depend on them; don't "fix" them.

- **Noise floor ~4 µV for every sorter** (3.88-4.09 across all saved sorts and the
  five-sorter sweep). It is a property of the recording after bandpass + CMR. If it varies by
  sorter, or reads ~1 µV, the channel gain was re-applied (see µV scaling).
- **tridesclous2 is non-deterministic here** (14-19 units across identical runs). Never treat
  unit counts or ids as stable, and never use them as a reproduction criterion. Curation
  records and manifests refuse a sort they weren't written against; that refusal is
  load-bearing.
- **No bad channels flagged is correct.** The E1 channel-1 pathology is sub-300 Hz, so the
  bandpass removes it before the median (PRE1).
- **`.nev` unit ids are per-electrode slots**: 7 sorted electrode×slot units on 4 electrodes.
- **The accepted-unit picture is 4 strong cells** (electrodes 5, 7, 9, 11), recovered against
  Ben's manual sort at 96-100%.
- **No swept sorter splits the merged pairs** (five sorters, 18 pair verdicts, zero splits).
  Splitting the merges is Phy work.

## The sort pipeline

- **Aux channels are dropped first** (`bio.neural_channel_ids()` + `bio.select_channels()`;
  `--keep-analog` keeps them). They would poison the common median reference and make the
  sorter emit spurious units. Any new sort-adjacent code drops them too. Never hardcode 16 or 22.
- **Bad channels leave before the CMR too.** `detect_bad_channels` (method `mad`, seed and
  threshold pinned) runs post-bandpass; flagged and `--bad-channels`-named channels are
  excluded from reference and sort, geometry preserved, recorded in `run_info.json`'s
  `bad_channels` block and stated on every surface that shows channels or yield.
  Auto-detection refuses wholesale above 25% of the array; manual names must leave ≥2 channels.
- **The sort passes `attach_probe=False`** and applies geometry from `probes.build()` →
  `set_probe()`, never `attach_dummy_probe()`.
- **Runs never clobber.** A `--duration` smoke run is refused as current and the incumbent
  full run stays pinned (`--make-current` overrides); `current.json` is replaced atomically;
  legacy `outputs/<sorter>/` layouts resolve read-only. Resolve paths only through
  `runs.sort_paths()` and the analyzer only through `curation.preferred_analyzer()`.
- **Quality metrics are non-fatal.** The Sorting is saved before metrics run, so a metrics
  crash is success-with-note (rc 0), and the handler deletes the half-built `analyzer/`,
  `quality_metrics.csv` and `summary.*` so no surface reads stale derived data.
- **`--progress json` keeps stdout pure**: JSON events to stdout; human output and the
  sorters' own fd-1 writes go to stderr.
- **Sorted-unit data comes only from the saved `SortingAnalyzer`.** Loose
  `outputs/<sorter>/sorting/` folders and `quality_metrics.csv` files are leftovers.

## µV scaling: the double-scaling trap

The `SortingAnalyzer` returns µV, so `templates` and `noise_levels` are already scaled.
`compute_summary` gates on `analyzer.return_in_uV` and must not re-apply the channel gain.
This rig's gain is 0.249977 µV/count, so re-applying it multiplies by 0.25: values come out
~4× too *small*. Both `create_sorting_analyzer` call sites (`run_sorting`, `curation`) pin
`return_in_uV=True`; the gate stays as the second line of defence.

## Geometry

- The files carry no probe map, so geometry is a user choice owned by `probes.py`. Default:
  the rig's NeuroNexus A1x16-3mm-100-703 (`nnx-a1x16-3mm-100`, 16 contacts @ 100 µm);
  channel→site identity wiring is the accepted standing assumption.
- **Geometry only re-ranks sorters** (`probes.fit()`); it never blocks sorting. Don't tell the
  user it does. 100 µm is the `sparse` class, which is why `tridesclous2` is the default.
- **Fit failure is asymmetric:** an explicit `--probe`/`--probe-file` that doesn't fit is a
  hard error (rc 1); the default probe not fitting warns and falls back to `independent`.
- The active probe resolves in one place, `probes.active_name()`.

## Loaders (`blackrock_io.py`)

- neo keys a file set on the name without extension: pass `find_blackrock_base()`'s stem
  (`read_spikes` is the exception: it appends `.nev`). Discovery prefers a stem with `.nsX`
  data and refuses, naming the candidates, when several sets are ambiguous.
- Pass exactly one stream selector (`stream_name` silently wins over `stream_id`).
  `read_broadband` picks the highest-rate stream and raises below 10 kHz.
- `set_probe()` returns a new recording; it does not mutate.
- `read_events` raises on a neo parse failure; callers must wrap it.
- Unit ids: `0` unsorted crossings, `1..n` online-sorted units, `255` noise/invalidated.

## Sorters

- The four local sorters (`tridesclous2`, `spykingcircus2`, `lupin`, `simple`) are
  SpikeInterface internals and always installed; everything else needs Docker or a GPU.
- Docker is only a fallback for sorters you don't have (`sorters.uses_docker()`).
- GPU sorters (kilosort*, pykilosort, yass) are listed but never offered on the build Mac (no
  NVIDIA GPU; Docker-on-Mac has no GPU passthrough). The lab box's GPU is the WD track.
- `group_of()` is the stable grouping; `status()` reflects the live Docker daemon.

## The app

- **The view imports no SpikeInterface.** It gets plain data from `MenuController`, and
  `journey.py` decides done / stale / next. (A testability boundary, not an import-cost claim.)
- **A bare run on a non-TTY builds the report** instead of opening the app; a piped, CI or
  agent-shell launch silently runs `report`. Use the `run-spikeinterface` skill to launch.
- Sorting runs in-app as a subprocess, never `suspend()`; only the Qt windows suspend.
- Every panel truncates its own lines to the live width; the key line drops whole items.
  80×24 and 64 columns draw every pane (pinned by the Pilot size test and SVG snapshots).

## Conventions

- `matplotlib.use("Agg")` before importing pyplot; figures go to `outputs/` (git-ignored).
- Entry points: `if __name__ == "__main__": raise SystemExit(main())`, `main()` returning an
  int (Windows `spawn` needs it for `n_jobs > 1`).
- `pathlib` throughout (`REPO_ROOT` from `blackrock_io`); code runs on macOS, Windows and Linux.
- Every text-mode subprocess capture passes `encoding="utf-8", errors="replace"` (Windows
  decodes with cp1252 otherwise); copy `tests/test_sort_progress_contract.py`'s `_run_sorting`.
- Python 3.12, not 3.13 (prebuilt wheels on Windows, no C compiler). Pins that matter:
  `zarr<3`, `plotly<6` (the report inlines `plotly.offline.get_plotlyjs`).
- Qt is PySide6 under uv and PyQt5 under the conda fallback; never both in one env.
- Tests: run the whole suite before claiming a menu change works. For sort-adjacent changes
  a green suite is not enough; run `run_sorting.py --duration 30` (plus one containerized
  sort when touching Docker paths).
