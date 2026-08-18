# tests/

Run everything with `uv run python -m pytest tests/` (needs `uv sync --group dev`).

| File | Pins |
|---|---|
| `test_menu_app.py` + `conftest.py` | menu **journeys/behaviour** over `FakeController` (Textual Pilot) |
| `test_snapshots.py` | menu **appearance** — SVG snapshots of the dashboard + modals |
| `test_sort_progress.py` | reducer behaviour of the progress protocol |
| `test_sort_progress_contract.py` | the protocol **contract**: event vocabulary/shapes, ordering, emitter lock, stdout purity |
| `test_report_golden.py` | report **structure** — builds a fresh report into tmp, checks sections/nav/figures |
| others | unit tests per module (sorters, probes, controller, …) |

## Snapshot tests (visual regression)

`test_snapshots.py` renders the app over `FakeController` and compares against
SVG baselines in `tests/__snapshots__/test_snapshots/`. A failure means the UI
*looks* different — pytest prints a link to `snapshot_report.html` with a
side-by-side visual diff. That is either a regression (fix the code) or an
intended redesign (re-baseline).

**Re-baselining is deliberate, never a reflex:**

1. Open the snapshot report and review every changed SVG — confirm each change
   is one you meant to make (and nothing else drifted along).
2. `uv run python -m pytest tests/test_snapshots.py --snapshot-update`
3. Re-run without the flag to confirm green, then **commit the updated `.svg`
   baselines in the same commit as the UI change** — the diff of the SVGs is
   the reviewable record of what the redesign changed.

Never run `--snapshot-update` to silence a failure you don't understand, and
never update baselines in a commit that isn't supposed to change the UI.

Snapshots must stay deterministic: drive them over `FakeController`, and for
the sort-progress screen use the `FrozenSortScreen` pattern (no subprocess, no
spinner animation). If a new snapshot flickers between runs, find and freeze
the nondeterminism — don't re-baseline around it.

## Report golden check

`test_report_golden.py` builds a fresh `report.html` into a pytest tmp dir
(your `outputs/report.html` is never touched) and checks structure only:
required sections present and ordered, nav complete, no crashed/empty
sections, figures present, self-contained. It **skips cleanly when no saved
sort exists** (`outputs/<sorter>/analyzer`) — run any sort first, e.g.
`uv run python scripts/run_sorting.py --duration 30`.

If a redesign legitimately renames/reorders/adds sections, update
`REQUIRED_SECTION_ORDER` in the same commit — that list is the baseline.

## Progress-protocol contract

`test_sort_progress_contract.py` locks `scripts/sort_progress.py` (the JSON
wire protocol between `run_sorting.py` and the TUI) ahead of its planned
extension. To add a new event type: extend `EVENT_TYPES` + the docstring in
`sort_progress.py`, then add the type with its required keys to `SHAPES` in
the contract test — `test_shapes_table_covers_event_types` fails until you do.
Adding *optional* keys to existing events needs no test changes (extension
safety is itself under test). The stdout-purity tests run `run_sorting.py`
in a real subprocess on failure paths; they need no recording and never touch
saved sorts.
