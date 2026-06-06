# SpikeInterface Menu — Terminal UI v2

**Date:** 2026-06-05
**Branch:** `terminal-rework`
**Status:** design approved, ready for implementation plan

## Problem

The current front-door launcher (`SpikeInterface_Menu.py` + `scripts/ui.py`'s
prompt_toolkit `dashboard_menu`) is functional but brittle on small terminals,
the active sorter is not prominent enough, and there is no guidance when the
recording files are missing. This tool may run inside a small VS Code integrated
terminal, so it must stay clear and usable at any window size. We want a polished
v2 overhaul that keeps the University of Pittsburgh shield and the existing
feature set.

## Goals

1. **Usable at any terminal size** — wide desktop down to a tiny VS Code pane.
   Nothing essential is ever clipped; the body scrolls when it must.
2. **Active sorter is unmistakable** — a dedicated side panel, always-visible
   ACTIVE marker, echoed in the footer.
3. **Actions always reachable** — scrollable, never hidden by a short window.
4. **Better readability** — generous spacing, clear section headers, consistent
   ✓ / – / ✗ badges.
5. **Missing-data guidance** — a banner plus a details screen that says exactly
   which files are missing and where they belong.
6. **Keep the Pitt shield** and the themeable accent; high polish and fidelity.

Non-goals: changing the loaders (`blackrock_io.py`), the sorters, the HTML
report (`report.py`), or the comparison (`compare.py`). The direct-action CLI
path (`python SpikeInterface_Menu.py report`, etc.) keeps working unchanged.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Framework | **Adopt Textual** (new dependency; pure-Python, pip-installable, fine in `si_env` py3.12 and VS Code terminals) |
| Layout | **Two-pane** (Sorter sidebar + Actions pane), responsive: stacks on narrow, scrolls on short |
| Small-window strategy | **Collapse then scroll** — drop shield / condense pipeline first, then scroll the body; Sorter + Actions never clipped |
| Sorter navigation | Sorter is a **side panel**: ← / → focus it, ↑ / ↓ choose within it |
| Missing data | **Banner + details screen** |
| App lifecycle | **Resident app + `suspend()`** — one persistent app; actions run via `suspend()` then resume keeping state |
| Tests | **Yes** — a small Textual Pilot suite |

## Architecture

### Modules

- **`scripts/menu_app.py`** (new) — the Textual app and everything specific to it:
  - `SpikeMenuApp(App)` — the resident application, owns the session loop.
  - `MainScreen` — top band (shield + title), two-pane body, footer.
  - Widgets: `ShieldWidget` (responsive Pitt shield), `SorterList`, `PipelinePanel`,
    `ActionList`, `MissingDataBanner`.
  - Modal screens: `DataSetupScreen`, `ThemeModal`, `SortSpanModal`,
    `CompareResortModal`, and a generic `ChoiceModal` they can share.
  - The CSS (TCSS) string with an `$accent` variable driven by the theme.
- **`scripts/ui.py`** (kept, lightly trimmed) — shared rich styling used by the
  per-action *scrolling* output and the fallback menu: `say/rule/note/done/link/
  banner/sorters_panel/status_table/select` and the **shield art + theme data**
  (`THEMES`, `set_accent`, `_LOGO_ART*`, `_build_logo`, `pick_logo`). `menu_app.py`
  imports the art and themes from here so there is a single source.
- **`SpikeInterface_Menu.py`** (launcher) — `_menu()` runs the Textual app when
  interactive; otherwise falls back to the existing typed numbered menu. The
  action functions (`action_explore`, `action_sort`, …) and `DISPATCH` are reused
  verbatim; they are invoked from inside the app's `suspend()` block.

### App lifecycle (resident + suspend)

`_menu()` builds dashboard data once (`_load_dashboard`) and constructs
`SpikeMenuApp(...)`, passing in: the header, pipeline rows, sorter infos, the
action table, the active sorter index, a callback to run an action, and a
callback to reload dashboard data. The app runs until the user quits.

Running an action:

1. User presses Enter on an action (or a number key).
2. If the action needs a sub-choice (sort span; re-sort before compare; theme),
   the app pushes the corresponding **modal screen** and waits for the result.
3. The app calls `with self.suspend():` and invokes the action callback, which
   runs the existing code path:
   - shell-outs (`explore`, `sort`, `verify`) via `_shell` (live stdout),
   - in-process `report` / `compare` (their own rich output),
   - blocking Qt (`gui`, `traces`) via `_self` in a child process.
4. On resume, the app refreshes the "last action" line, and for state-changing
   actions (`sort`, `compare`) reloads dashboard data and re-renders.

The action callback is a thin adapter around the launcher's existing
`DISPATCH` / `_self` logic so behaviour (flags, child processes, browser open)
is identical to today.

### Responsive behaviour

Textual handles most of this via TCSS plus a size watcher on the app:

- **Width breakpoint** (`cols < ~72`): the two panes switch from side-by-side
  (`layout: horizontal`) to stacked (`layout: vertical`), Sorter on top.
- **Height pressure:** the `ShieldWidget` chooses full → compact → mini → hidden
  to fit the remaining rows (reusing `pick_logo`); the `PipelinePanel` condenses
  its detail column. Both the Sorter and Actions containers have `overflow: auto`
  so they scroll independently rather than clip.
- Active sorter row and the Actions list are always present and scroll into view.

### Navigation & focus

- Two focus targets: the **Sorter** sidebar and the **Actions** pane. The
  focused one shows a bright accent border.
- `left` / `right` (and `tab` / `shift+tab`): move focus between the two.
- `up` / `down` (and `j` / `k`): move the highlight within the focused list.
- `enter` / `space`: Sorter → set active sorter (updates pipeline "Saved sort"
  row, summaries, and which sorter report/gui/compare act on); Actions → run.
- `1`–`9`: jump to and run an action.
- `t`: quick-cycle the active sorter without changing focus.
- `d`: open the Data Setup screen. `q` / `escape` / `ctrl+c`: quit.
- The **active sorter is marked independently of focus** (accent-filled row +
  ACTIVE pill) and echoed in the footer, so it is obvious even when focus is on
  Actions.

### Missing-data handling

A helper (in `menu_app.py` or `SpikeInterface_Menu.py`) computes a data report:
call `bio.find_blackrock_base(data_dir)`; on `FileNotFoundError`, mark data
missing. Independently, glob the data dir for `*.ns2`, `*.ns5`, `*.nev` (by base
name when a base is found) to build a per-file present/missing checklist.

- **Banner:** when data is missing, `MissingDataBanner` shows a red line — e.g.
  `⚠ No recording found in <data_dir> — press d for setup help` — and the
  data-dependent actions (`explore/sort/report/gui/traces/compare`) render dimmed
  / disabled. `verify`, `theme`, `data-setup`, `quit` stay enabled.
- **Data Setup screen** (modal, also reachable any time via `d` or the action):
  - The expected base name (discovered stem, or the generic
    `<name>.{ns2,ns5,nev}` pattern).
  - A checklist: `.ns2` LFP @1 kHz · `.ns5` broadband @30 kHz · `.nev` events,
    each ✓ present / ✗ missing.
  - The exact folder they belong in (repo root, or the `--data-dir` path).
  - The note that the raw files are git-ignored, so a fresh clone has none.
  - The underlying `find_blackrock_base` error text for reference.

### Theming

Keep `ui.THEMES` (periwinkle / sea-green / steel-blue / amber / cyan) and
`set_accent`. The chosen accent is injected as the TCSS `$accent` variable;
`ThemeModal` changes it live (re-applying the stylesheet) and persists the choice
to `.si_menu.json` via the existing `_load_config` / `_save_config`, re-applied on
launch.

### Fallback path

Textual needs a real terminal. When stdin is not a TTY, or `import textual`
fails, `_menu()` uses the **existing** typed numbered menu (`ui.select` /
`_select_typed` + `ui.banner` / `sorters_panel` / `status_table`), including the
"Switch sorter" entry and the report-on-non-interactive-stdin shortcut. This
preserves piping/CI behaviour. The fallback also prints the missing-data guidance
as plain text.

## Error handling

- `import textual` failure or non-TTY → fallback menu (no crash).
- Each action is wrapped so a raised exception becomes a red "last action" line
  and the app keeps running (today `_shell`/`_self` return a bool; in-process
  `report`/`compare` can raise — wrap them).
- `gui` / `compare` already guard a missing analyzer with a warning; preserved.
- Off-screen / zero-size terminals: never `divide`/index past the shield ladder;
  `pick_logo` already returns `[]` (hidden) when nothing fits.

## Dependencies

- Add `textual` to `environment.yml` and install it into `si_env`
  (`pip install textual`). Pin a recent, working version after verifying import.
- Add `pytest` as a dev/test dependency for the Pilot tests.
- prompt_toolkit stays (still used by `ui.select` in the fallback path); rich
  stays (shared styling + Textual depends on it).

## Testing

New `tests/` using Textual's `run_test()` / `Pilot`:

1. **Boots** — app starts, main screen mounts, all actions present.
2. **Focus switch** — `right`/`left` move focus between Sorter and Actions;
   focus border follows.
3. **Sorter select** — Enter on a sorter sets it active; footer + ACTIVE marker
   update; the value the launcher would act on changes.
4. **Navigation** — `down`/`up` move the Actions highlight; a number key targets
   the right action.
5. **Tiny window** — resize to a small size (e.g. 40×10); app does not crash,
   Actions list is still reachable (scrolls), shield hides.
6. **Missing data** — with an empty data dir, the banner shows and the Data Setup
   screen lists the three files as missing with the expected location.

`scripts/verify_install.py` remains the environment smoke test.

## Documentation

Update `CLAUDE.md`'s Architecture section to describe the Textual v2: the
two-pane layout, focus/nav model, responsive collapse+scroll, the missing-data
banner + setup screen, `menu_app.py` vs `ui.py` split, the resident-app +
`suspend()` lifecycle, and the new `textual` dependency.

## Rollout

Single branch `terminal-rework`. Implementation order:

1. Add `textual` to env + install; confirm import + a trivial app runs in `si_env`.
2. `menu_app.py`: app shell, two-pane layout, shield widget, CSS, themes.
3. Wire data: sorter list, pipeline panel, footer, active-sorter model.
4. Navigation + focus model.
5. Action runner via `suspend()` + the modal sub-prompts.
6. Missing-data banner + Data Setup screen.
7. Launcher `_menu()` integration + fallback preservation.
8. Tests.
9. `CLAUDE.md` update.
10. Manual pass at several sizes (wide, narrow, short, tiny) + verify_install.
