# ARCHITECTURE.md - how the workbench is put together

The map: where each fact lives, how data flows, how the app is wired. Module docstrings are
the API source of truth (thorough, kept current); this file only says which module to read.
The rules that must not break are in `docs/INVARIANTS.md`.

## The data

One Blackrock/Ripple recording, `PFCM7_d0ephys_Block2`, in the repo root. Raw data is
git-ignored (the `.ns5` is ~176 MB, over GitHub's 100 MB limit), so a fresh clone has no
data. Loaders auto-discover any Blackrock file set by base name; a missing set raises a clear
`FileNotFoundError` from `find_blackrock_base()`.

| File | Stream | Loader |
|---|---|---|
| `.ns2` | LFP @ 1 kHz (`lfp N`) | `read_lfp()` → Recording |
| `.ns5` | broadband @ 30 kHz, the spike-sortable stream | `read_broadband()` → Recording |
| `.nev` | online-detected spikes + digital markers, 30 kHz clock | `read_spikes()` → Sorting; `read_events()` |

Both streams carry 22 channels: 16 neural, 6 non-neural `analog N` aux inputs (sync pulses
etc., ids 10241+). The split is discovered at runtime by `bio.neural_channel_ids()`.

The code is not a package and has no install step. Consumers put `scripts/` on `sys.path`:

```python
import sys; sys.path.insert(0, "scripts")   # notebooks use Path.cwd().parent / "scripts"
import blackrock_io as bio
```

## Module map

Each `scripts/` module is the single source of truth for its job. Extend it; don't
re-implement or hardcode around it.

| Module | Owns | Don't instead |
|---|---|---|
| `blackrock_io.py` | loading this dataset; Blackrock unit-id semantics | open the files with neo/SI directly |
| `sorters.py` | which sorters exist / are runnable, params, Docker | hardcode a sorter list |
| `probes.py` | electrode geometry (profiles, active probe, sorter fit) | build a `Probe` inline |
| `run_sorting.py` | the sort pipeline + its terminal presentation | |
| `sort_progress.py` | the JSON event protocol between `run_sorting` and the app | print status for the UI to scrape |
| `sort_summary.py` | the six array/yield metrics + the unit rollup (strong / thin-evidence / sub-threshold / not-judged, the plain-words phrases every surface quotes) | recompute amplitudes ad hoc, or re-decide "strong" outside the rollup |
| `curation.py` | the curation record (merge/split/label), applying it, curated-vs-raw state; `preferred_analyzer()` is the one home for "curated wins when it exists" | test for `curated/` folders directly |
| `runs.py` | the versioned run store, the current pointer, provenance, regenerate-from-record; `runs.sort_paths()` is the one path resolver | build `outputs/<sorter>/...` paths by hand |
| `settings.py` | every editable setting: schema, validation, defaults, and the `run_sorting` flags they become | add a knob the Settings screen and the sort argv don't both get |
| `journey.py` | the rail's stage marks, the next step, the probe map, output freshness, runs overview + recipes, the palette's action table | decide done/stale/next in the view |
| `report.py` | self-contained `outputs/report.html` (Plotly inlined; `CHART_TEMPLATE` is the shared chart theme) | |
| `compare.py` | two-sorter comparison and offline-vs-online (`.nev`) matching | re-implement matching |
| `unit_evidence.py` | per-unit waveform / ISI / amplitude evidence for 4 Judge (reads the analyzer; µV-gated) | compute evidence in the view |
| `unit_page.py` | `units.html` in each run folder: every unit's real plots (`v` on 4 Judge) | judge units from the terminal drawing |
| `sweep_page.py` | the sorter-shootout page `outputs/sweep.html`, judged via compare.py | build a second shootout surface |
| `viz_palette.py` | chart colors for every HTML surface + the deck (validated periwinkle palette; validator commands in its docstring) | hardcode a chart hex |
| `ui.py` | shared rich styling, themes, fallback widgets, `HELP_TOPICS` | |
| `spike_app.py` + `menu_app.py` | the Spike 2.0 app (rail, panes, Settings, palette, Runs) + the modals it reuses: the view | import SpikeInterface |
| `SpikeInterface_Menu.py` (root) | `MenuController`: data and actions behind the view | |
| `check_workbench.py` | the sandboxed end-to-end check of every function (the Windows acceptance test) | test against the real outputs/ or settings |

The six metrics `sort_summary` owns: **V_pp**, **SNR**, **noise floor**, **yield** (% of
electrodes that are peak channel of ≥1 unit), **units/ch**, **units/active-ch**. They surface
on the `run_sorting` terminal card, `report.html`, the app's sort result, and
`comparison.html`; the computation lives in one place only.

## The sort pipeline

```
read_broadband(attach_probe=False) → drop non-neural aux channels → set_probe(active probe)
    → bandpass_filter(300–6000) → detect + drop bad channels → common_reference(global, median)
    → run_sorter → save Sorting, then build SortingAnalyzer + metrics
    → outputs/<sorter>/runs/<run_id>/
```

Each sort lands in its own run folder; `current.json` is the pointer every surface resolves
through `runs.sort_paths()`. The curation record, `curated/` and `phy/` ride inside the run
they describe.

## The app (Spike 2.0, spec of record `goals/GOAL_V2.md`)

- A rail of six stages (1 Data · 2 Probe · 3 Sort · 4 Judge · 5 Apply · 6 Share) over one
  next step on Home and a pane per stage.
- The view (`spike_app`, `menu_app`) talks to `MenuController` through the `Controller`
  Protocol in `spike_app`; tests inject `tests/conftest.py`'s FakeController.
- Keys: `1`-`6` stages; `Esc` returns Home and never exits; `/` palette, `,` Settings,
  `?` help, `q` quit. Every other letter belongs to one pane and is printed on its key line;
  `ui.HELP_TOPICS` names them all (pinned against the panes' bindings).
- Sorting runs in-app via a `run_sorting.py --progress json` subprocess. Explore, verify,
  apply, Phy export/import, sweep and reproduce run as logged child processes
  (`CommandScreen`, logs in `outputs/logs/`). Only the Qt windows (gui, traces) suspend the
  app, re-invoking the launcher.
- CLI dispatch: `SpikeInterface_Menu.py <action>` with `explore | sort | report | gui |
  traces | compare | verify | phy`. `phy` exports the saved sort (curated when one exists);
  verdicts return via `curation.py import-phy`. `make_report.py` forwards to `report`.

## Local state (git-ignored)

`.si_menu.json` holds `theme`, `use_docker`, `sorter_params`, `active_probe`, `seen_welcome`,
`seen_probe_setup`, `active_sorter`, `last_result`, `quality_rule`, `sort_settings`,
`data_dir` and `built` (`settings.py` owns the schema of `sort_settings`, `quality_rule` and
`data_dir`; `built` stamps which run each output was built from). `probes.json` is the user
probe library.

## Commands

Scripts document their own flags in their module docstrings.

```bash
uv sync                                     # env (Python 3.12); conda fallback: environment.yml
uv sync --group dev                         # + pytest
uv run python SpikeInterface_Menu.py        # the app
uv run python SpikeInterface_Menu.py sort   # ...or dispatch one action directly
uv run python -m pytest tests/              # Textual Pilot tests + unit tests
uv run python scripts/verify_install.py     # loader smoke: versions + all three loaders
uv run python scripts/run_sorting.py --duration 30   # sort smoke (first 30 s)
uv run python scripts/curation.py show --sorter tridesclous2   # curation record + curated state
uv run python scripts/runs.py list          # every saved run + the current pointer
uv run python scripts/check_workbench.py    # every function end to end, sandboxed
uv run python scripts/sweep_page.py         # the sorter shootout page
```
