# PFCM7 self-contained HTML report + interactive re-sort launcher

**Date:** 2026-06-03
**Status:** Approved (design)

## Goal

Give a one-glance way to confirm the whole SpikeInterface pipeline works on the
`PFCM7_d0ephys_Block2` recording, and to actually *see* the results, by producing
a **single self-contained interactive HTML report**. Building the report
re-exercises the loaders every time and visualizes the saved sorting; a re-sort
(quick or full) can be triggered from an **interactive terminal menu** — never a
CLI flag.

This is the "does everything we built actually work?" answer: loaders, the
already-detected `.nev` online units, the `tridesclous2` sort, quality metrics,
and digital events — all in one file you open in a browser and scroll.

## Non-goals

- No hosted/served app, no dashboard, no in-browser controls that re-run Python
  (that was the rejected "local dashboard" option — it needs a running server).
- No change to the sorting pipeline, loaders, or probe handling. The report only
  *reads and visualizes* what those produce. The 16-neural-+-6-analog-aux channel
  mix and the placeholder-probe geometry are surfaced, not altered.
- No new test suite (the project has none); verification is "run it and look".

## Context discovered

- The pipeline already runs end-to-end. `outputs/tridesclous2/` holds a saved
  `Sorting`, a `SortingAnalyzer` (with `templates` + `quality_metrics`
  extensions), and `quality_metrics.csv`.
- **The saved sort is a 20 s smoke test, not the full recording**
  (`analyzer/.../recording_attributes.json` → `num_samples: 600000` @ 30 kHz =
  20 s; 18 units). The launcher must show this provenance so the user always
  knows what they're looking at, and the **full re-sort** menu option is the way
  to upgrade it.
- Broadband stream = 16 real neural channels (`raw 1–16`, ~0.25 µV/bit) + 6
  analog aux channels (`analog 1–6`, mV-scale). Sorting currently runs on all 22.
  The report labels this; it does not change it.
- `run_sorting.py` now takes `--verbosity {quiet,normal,verbose}` and contains
  `configure_verbosity()`; the launcher reuses `run_sorting.py` for re-sorts so
  this behavior is inherited, not duplicated.

## Architecture

Two new files in `scripts/`, everything else reused unchanged. Both follow the
project conventions: `matplotlib.use("Agg")` is irrelevant here (Plotly), use
`pathlib` / `bio.REPO_ROOT`, wrap entry points in `if __name__ == "__main__":`
returning an int from `main()`.

### `scripts/report.py` — the report builder (importable, pure-ish)

Public entry point:

```python
build_report(data_dir=None, analyzer_dir=None, out_path=None) -> Path
```

- Loads via the existing loaders: `bio.read_lfp`, `bio.read_spikes`,
  `bio.read_events`. Opens the saved analyzer with
  `si.load_sorting_analyzer(analyzer_dir)` (default
  `outputs/tridesclous2/analyzer`).
- **Each section is built inside its own try/except.** A failure becomes a red
  ✗ row in the status banner with the error message — it never aborts the
  report. This isolation is what makes the report a real health check.
- Reads sorted units **and** their quality metrics from the *same* saved
  analyzer so they can never disagree (the loose `quality_metrics.csv` is a
  fallback only).
- Assembles one HTML document: small inline CSS, a sticky top nav with anchors,
  the seven sections, footer. Plotly is embedded once with
  `include_plotlyjs="inline"` (truly offline / self-contained); subsequent
  figures use `to_html(full_html=False, include_plotlyjs=False)`.
- Writes to `outputs/report.html` (git-ignored) and returns the path.

Plotting helpers (one per section, each returns an HTML fragment string):
`_status_banner`, `_lfp_section`, `_nev_units_section`, `_sorted_units_section`,
`_quality_metrics_section`, `_events_section`, `_footer`.

Data-volume guards: downsample/limit before handing arrays to Plotly — LFP
shown over a short window (e.g. ~10 s) at 1 kHz; rasters use marker traces;
waveform templates come from the analyzer (already small). Never feed raw 30 kHz
broadband to Plotly.

### `scripts/make_report.py` — the interactive launcher (`__main__`)

1. Print a compact PASS/FAIL summary of the loader stages.
2. Detect the saved sort and print its **provenance**: sorter, units, sorted
   duration (e.g. "20 s of 132 s"), and when it was run.
3. Present an **interactive terminal menu**:
   - `[Enter]` reuse the saved sort and build the report
   - `[q]` quick re-sort (first ~30 s), then build
   - `[f]` full re-sort (~132 s), then build
4. Re-sort is done by invoking the existing `scripts/run_sorting.py` as a
   subprocess (passing the chosen duration and a sensible `--verbosity`), so all
   sorting + verbosity logic is reused, not duplicated. After it finishes, build
   the report against the freshly written analyzer.
5. **Non-interactive safety:** if stdin is not a TTY (CI / piped), skip the menu
   and default to reuse, so the script never blocks. Accept `--data-dir` only
   (no `--resort`-style flag — re-sorting is a menu choice, per the user).

## Report sections

1. **Status & provenance banner** — table: each stage (LFP, broadband-meta,
   `.nev` units, saved sort, analyzer/QC, events) → PASS / FAIL / SKIP plus key
   facts (channels, duration, fs, #units, **sort duration**, run time). The
   at-a-glance health check.
2. **LFP** (`.ns2` @ 1 kHz) — interactive stacked multi-channel traces over a
   short window (legend toggles channels) + a per-channel power spectrum.
3. **`.nev` online units** — interactive raster + firing-rate bar (already
   detected units).
4. **Sorted units** (`tridesclous2`) — raster, firing rates, and **waveform
   templates** per unit (from the analyzer), labelled with sort provenance + the
   placeholder-probe / analog-aux-channel caveats.
5. **Quality metrics** — sortable table (`firing_rate`, `snr`,
   `isi_violations_ratio`) + an SNR-vs-firing-rate scatter to spot good/bad
   units.
6. **Events** — best-effort digital-marker timeline; "no event channels" note if
   `read_events` returns `[]`.
7. **Footer** — library versions (spikeinterface, neo, plotly, numpy) +
   generation timestamp + geometry caveat.

## Error handling

- Per-section try/except → red ✗ row, report still builds.
- Missing analyzer (`outputs/` absent) → sorted-units + QC sections show SKIP,
  not a crash. The launcher still offers to re-sort.
- `read_events` failure / empty → events section shows a benign note (matches the
  loader's best-effort contract).

## Verification (no automated tests exist)

- Run `conda activate si_env && python scripts/make_report.py`, choose reuse,
  confirm `outputs/report.html` is written and the banner is all PASS.
- Temporarily point `analyzer_dir` at a missing path (or rename `outputs/`) →
  confirm the sorted/QC sections degrade to SKIP rather than crashing.
- Open the HTML in a browser; confirm Plotly figures are interactive and the file
  works with no network (inline Plotly).

## Dependencies

- **Plotly** — **not currently installed** in `si_env` (verified 2026-06-03).
  The plan must install it (`pip install plotly` / `conda install -c conda-forge
  plotly`) and add it to `environment.yml` + `requirements.txt`. (A `plotly`
  skill is available to author the figures well.)
- Everything else (spikeinterface, neo, numpy 2.4.6, pandas 2.3.3) is already
  present.

## Documentation touch-ups (after build)

- Add `make_report.py` to the Commands block in `CLAUDE.md` and the README.
