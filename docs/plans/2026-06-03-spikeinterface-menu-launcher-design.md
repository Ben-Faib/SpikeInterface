# Design: `SpikeInterface_Menu.py` — single workspace launcher + usability upgrades

Date: 2026-06-03
Status: approved (brainstorm), ready for implementation plan

## Goal

Make the workspace usable by lab-mates (some CLI-shy) without losing power-user
flexibility. Today there are 5 separate scripts and no single front door; the
HTML report is hardwired to `tridesclous2`; the installed interactive GUIs
(`spikeinterface-gui`, `ephyviewer`) are unused; there is no sorter comparison.

This design adds **one front-door launcher** that fronts every existing
capability plus three new ones (GUI inspector, trace browser, sorter
comparison), and fixes the report's sorter-hardwiring.

## Audience & priorities (from brainstorm)

- Primary user: **lab-mates, some CLI-shy** → optimize for a friendly single
  entry point, but keep arg-dispatch for power use.
- All four improvement areas requested: single launcher, sorter-aware + compare,
  launch interactive GUI, polish (auto-open report, etc.).

## Verified environment facts (research workflow, `si_env`)

SpikeInterface 0.104.3, neo 0.14.4, spikeinterface-gui 0.13.1, ephyviewer 1.8.0,
Python 3.12.13.

- **GUI command is `sigui <analyzer_dir>`** (entry point
  `spikeinterface_gui.main:run_mainwindow_cli`). `spikeinterface-gui` does **not**
  exist. Python API: `spikeinterface_gui.run_mainwindow(analyzer, mode='desktop',
  with_traces=True, curation=False, start_app=True, ...)`.
- **Both GUIs block** on the Qt event loop (`app.exec()`); on macOS Qt must run on
  the main thread → **launch via subprocess**, never in-process from the menu.
- **Active Qt binding is PyQt5 5.15.11** — **PySide6 is NOT installed**. The
  `PySide6<6.8` pin in `requirements.txt`/CLAUDE.md is currently moot.
- The **`ephyviewer` console script is broken** here (`ImportError: cannot import
  name '__version__'`). Use `spikeinterface.widgets.plot_traces({'broadband':
  rec}, backend='ephyviewer')` (blocks on `app.exec()` — run in a subprocess).
- **`compare_two_sorters(s1, s2, sorting1_name=, sorting2_name=)`** →
  `SymmetricSortingComparison`. Heatmap matrix = `get_ordered_agreement_scores()`;
  matched/unmatched from `hungarian_match_12` (value `-1` = unmatched).
- **Commensurability caveat:** the two saved sorts are NOT comparable as-is —
  `tridesclous2` = 132.0 s / 19 units (full), `spykingcircus2` = 10.0 s / 14 units
  (smoke run). Comparing them yields ~0 matches purely from the window mismatch.
  A valid comparison must run both over the same recording window first.
- **Report data path already works for any sorter:** `build_report(analyzer_dir=
  ...)` is parameterized; only the **label strings** are hardwired to
  `tridesclous2`. Sorter name is NOT stored in the analyzer → derive the label
  from `analyzer_dir.parent.name` (contract-respecting; does not peek into
  `sorter_output/`).
- **`verify_install.py` takes no flags** (no argparse) — never pass `--data-dir`.
- A bare loaded `Sorting` has no recording, so `.get_total_duration()` raises;
  read durations from the `SortingAnalyzer` instead.

## Architecture

New file: **`/SpikeInterface_Menu.py` at the repo root** (per user request).
Because it lives in the root, not `scripts/`:

```python
ROOT = Path(__file__).resolve().parent           # repo root
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))                 # import blackrock_io, report
import blackrock_io as bio
import report
```

Run **bare** → status dashboard + interactive numbered menu. Run with a
positional action (`python SpikeInterface_Menu.py report`) → run that action
directly and exit. Shared flags: `--data-dir`, `--sorter {tridesclous2,
spykingcircus2}`, `--duration`.

The launcher **never imports SpikeInterface at module top** — the menu appears
instantly; all heavy/Qt imports are lazy inside the action that needs them.

### Dispatch rules (mirror the existing `make_report.py` pattern)

- **explore / sort / verify** → `subprocess.run([sys.executable, str(SCRIPTS /
  "<script>.py"), ...flags])`, stdout inherited so live progress bars stream
  through. Coupling only to each script's CLI flags.
- **report** → in-process `report.build_report(...)` (fast, no bars), then
  auto-open.
- **gui / traces / compare-after-resort** → subprocess (Qt blocks; fresh process
  each time avoids Qt-singleton + macOS main-thread issues).

## The menu

```
PFCM7 workspace · active sorter: tridesclous2
  [PASS] LFP (.ns2)             16 ch, 132.0s @ 1 kHz
  [PASS] Broadband (.ns5)       22 ch, 132.0s @ 30 kHz
  [PASS] .nev online units      N units
  [PASS] Saved sort (analyzer)  19 units, 132.0s sorted
  [SKIP] Events                 (all empty)

  1) Explore raw data        quick static figures (LFP + .nev) — no sort needed
  2) Run / re-run sorting    tridesclous2 or spykingcircus2 · full or quick (30s)
  3) Build & open report     interactive HTML → opens in browser
  4) Open GUI inspector      spikeinterface-gui on the saved sort
  5) Scroll raw traces       ephyviewer trace browser
  6) Compare the two sorters agreement matrix (needs both sorted, same window)
  7) Verify install
  t) Switch active sorter    tridesclous2 ⇄ spykingcircus2
  q) Quit
```

- Status rows reuse `report._gather(data_dir, analyzer_dir)` (each stage in its
  own try/except → PASS/SKIP/FAIL, never a crash).
- **Active sorter** in the header drives report/gui/compare targets; `t` toggles
  it; `sort` lets you choose per run. Sorter list single-sourced via
  `from run_sorting import SORTERS`.
- **Non-interactive stdin** (`not sys.stdin.isatty()`) → safe default = build the
  report; never blocks on `input()`.

## Actions (verified argv / calls)

| Action | Implementation |
|---|---|
| explore | `[exe, scripts/explore_data.py] + (['--data-dir', D] if D)` |
| sort | `[exe, scripts/run_sorting.py, '--sorter', active] + (['--duration','30'] if quick) + (['--data-dir',D] if D)` |
| report | `report.build_report(data_dir=D, analyzer_dir=outputs/<active>/analyzer, sorter_label=active)`; then `webbrowser.open(out.resolve().as_uri())` **if** `sys.stdin.isatty()`; always print the `file://` URL |
| gui | guard `analyzer_dir.exists()` else "sort first"; subprocess → `sigui <analyzer_dir>` |
| traces | subprocess → small in-process call `sw.plot_traces({'broadband': bio.read_broadband(D)}, backend='ephyviewer')` (avoids the broken `ephyviewer` CLI) |
| compare | see below |
| verify | `[exe, scripts/verify_install.py]` — no other flags |

For `gui` and `traces`, the menu shells out to **`[sys.executable,
str(SCRIPTS/'SpikeInterface_Menu.py')... ]`**? No — simplest robust form: a
dedicated tiny subprocess target. Decision for the plan: the menu invokes the Qt
actions by re-dispatching the launcher itself in a child process
(`[exe, __file__, 'gui', '--sorter', active]`), so the child runs the action
in-process (blocking is fine there) and the parent menu returns when the window
closes. Direct arg-dispatch of `gui`/`traces` runs in-process.

## Report sorter-awareness fix (`scripts/report.py`)

- `build_report(data_dir=None, analyzer_dir=None, out_path=None, sorter_label=None)`.
- After resolving `analyzer_dir`: `sorter_label = sorter_label or
  analyzer_dir.parent.name`.
- Thread `sorter_label` into `_render_sorted(analyzer, sorter_label)` and the
  three hardwired strings: section title (`f"Sorted units ({sorter_label})"`),
  raster/rate `title_prefix` (`f"Sorted ({sorter_label}) units"`), and the note
  (`f"Sorted with {sorter_label} over ..."`). Keep `id="sorted"` (anchor)
  unchanged. Footer geometry caveat needs no change.
- `run_sorting.py`: **no changes** (already sorter-aware).
- Default no-arg behavior unchanged (`DEFAULT_ANALYZER_DIR.parent.name` ==
  `"tridesclous2"`).

## Sorter comparison → `outputs/comparison.html` (standalone, chosen option)

New module `scripts/compare.py`, reusing `report`'s HTML scaffolding helpers
(`report._fig_html`, `report._html_document`, `report._CSS`, `report._SORT_JS`)
for visual consistency.

`build_comparison(data_dir=None, sorters=SORTERS, out_path=outputs/comparison.html)`:
1. Load both analyzers; if either missing → friendly message, abort gracefully.
2. Read both durations from the analyzers. If they **differ** (beyond a small
   tolerance) → emit a clear caveat and do NOT present a misleading matrix; the
   **launcher's compare action** offers to re-sort both over a common window
   (shell out `run_sorting.py --sorter X --duration N` for each) before
   comparing.
3. When commensurate: `cmp = compare_two_sorters(s1, s2,
   sorting1_name=..., sorting2_name=...)`. Section content:
   - Plotly `Heatmap(z=cmp.get_ordered_agreement_scores().to_numpy(), ...,
     colorscale='Blues', zmin=0, zmax=1)` (sorter1 units on y, sorter2 on x).
   - Sortable matched/unmatched table from `hungarian_match_12` (agreement
     fraction per matched pair; counts of matched vs unmatched per side).
   - Run parameters (`delta_time`, `match_score`).
4. Write `outputs/comparison.html` (Plotly JS inlined, opens offline) and
   auto-open on a TTY.

## `make_report.py` → thin shim (chosen option)

Reduce `scripts/make_report.py` to a small wrapper that invokes the launcher's
report flow, so the documented `python scripts/make_report.py` command still
works. Its reuse/quick/full re-sort menu is subsumed by the launcher's `sort` +
`report` actions.

## Error handling

Every action guards preconditions and degrades to a clear message, never a
traceback — consistent with `_gather`'s PASS/SKIP/FAIL and `_safe_section`. GUI
import failure → explain (suggest `verify_install.py`). Auto-open gated on
`sys.stdin.isatty()`; `webbrowser.open` returning `False` → fall back to printing
the path. Use `Path.resolve().as_uri()` (space-safe), not `f"file://{path}"`.

## Conventions (CLAUDE.md)

`bio.use_utf8_stdout()` first in `main()`; `if __name__ == "__main__": raise
SystemExit(main())`; `pathlib` throughout; figures/artifacts to `outputs/`
(git-ignored). New `scripts/compare.py` follows the same import-shim pattern.

## Incidental doc fixes (separate, low-risk)

- Correct CLAUDE.md/README: the env uses **PyQt5**, not PySide6; the `PySide6<6.8`
  pin is currently inert. Document the `sigui` command and the new launcher.
- Note the broken `ephyviewer` console script and the `plot_traces` workaround.

## Testing / verification

No formal suite. Verify by: launcher renders bare (menu + correct status);
arg-dispatch each action; report builds with both `sorter_label`s; GUI/traces
subprocess commands smoke-tested headless with `QT_QPA_PLATFORM=offscreen`;
`verify_install.py` remains the integration check. `comparison.html` built after
re-sorting both at a common `--duration`.

## Out of scope (YAGNI)

Real probe geometry import; timestamped/run-history output dirs; sorter-specific
parameter knobs beyond what `run_sorting.py` already exposes; the `web`/Panel GUI
mode.
