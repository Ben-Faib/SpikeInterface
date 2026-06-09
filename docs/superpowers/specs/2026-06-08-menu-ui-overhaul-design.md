# Menu UI Overhaul — three-panel dashboard, in-UI sorting & sorter management

**Date:** 2026-06-08
**Status:** Approved (design), pending implementation plan
**Branch:** `menu-ui-overhaul-three-panel`

## Goal

Bring as much of the workflow as possible *into the same terminal UI space* and make
the dashboard cleaner across the board. Concretely:

1. **Revert the accordion** to a simultaneous **three-panel** layout (SORTERS + ACTIONS
   side-by-side, full-width **INSPECTING** along the bottom) with an always-on two-line
   **DATA / SORT banner** header — the pre-accordion look in the user's screenshot.
2. **Run / re-run sorting inside the TUI** with live structured progress *plus* a
   spinner/heartbeat — never drop to scrolling stdout via `suspend()`.
3. **Download Docker sorter images inside the UI**, in the **sorters area**, as a step
   **separate from** running a sort.
4. **Easier view of what is installed / downloaded** and **a way to delete** downloaded
   Docker images and saved sort outputs — *not* pip-uninstalling sorters.
5. A dedicated **"Manage sorters"** action (a full management hub) in the ACTIONS list,
   in addition to the quick inline paths in the SORTERS pane.

These are user-confirmed decisions (AskUserQuestion, 2026-06-08): image layout with
bottom INSPECTING; structured progress fused with spinner/heartbeat; manage scope =
Docker images + saved outputs (no pip-uninstall); keep the animated neuron crest with
`m` toggle.

## Non-goals / out of scope

- **No pip/conda uninstall** of sorters (mutating the live env is unsafe).
- Qt GUIs (`sigui`, `ephyviewer`) and the HTML report inherently open external
  windows/the browser — those stay external; "same UI space" targets sorting, Docker
  download, and install management.
- No change to the loaders (`blackrock_io.py`), `report.py`, `compare.py`,
  `explore_data.py` internals beyond what the controller already calls.
- No new probe geometry / sorting-science changes.

## Background (current architecture, from the subsystem map)

- `SpikeInterface_Menu.py` (root) — launcher + `MenuController` (the view↔logic bridge).
- `scripts/menu_app.py` — Textual `SpikeMenuApp` (the view). Today: a **focus-driven
  accordion** — exactly one of `#sorters`/`#actions` displayed at a time, a side
  `#explain` pane, a quiet-until-broken `#statusline`, an action-mode `#activebar`, and
  the animated neuron `#crest`. Actions run via `suspend()` (drop alt-screen). The app
  **never imports SpikeInterface** — all heavy work is in the controller / child
  processes. Five modal screens already exist (Choice, DataFolder, ParamEditor,
  DockerConfirm, Welcome, Help).
- `scripts/sorters.py` — registry. Already has the Docker hooks we need:
  `default_docker_image(name)`, `docker_image_present(image)`,
  `pull_docker_image(image, on_progress, on_status)` (streaming callbacks),
  `docker_state(refresh)`, `start_docker()`, plus `group_of`, `runnable`, `status`,
  `run`, param helpers. **Missing:** any image *delete* and any size lookup.
- `scripts/run_sorting.py` — standalone sort entry point. `main()` is a 6-phase pipeline;
  the actual sort is the isolatable `sorters.run(name, rec, folder, params=, use_docker=,
  verbose=)`. Progress is **tqdm→stdout** with no callback hook. A `ConsoleUI` (rich)
  renders phases/details/metrics; `AlignedTqdm` normalizes bars. There is **no machine
  -readable progress channel** today.
- `tests/` — ~46 Textual Pilot tests pin the accordion model; controller + sorter-registry
  tests are mostly pure logic and survive; `conftest.py`'s `FakeController` mirrors the
  controller contract.

## Design

### 1. Layout — three panels + DATA/SORT banner

New `compose()` widget tree (replaces the accordion):

```
#crest        CrestWidget        animated neuron, optional; m toggles; auto-hides when short
#titlebar     Static             "══ Spike Sorter ═ University of Pittsburgh · SpikeInterface ══ ? Help ══"
#databar      Static             always-on DATA line (✓/✗ per stream + summary/remedy)
#sortbar      Static             always-on SORT line (active sorter · saved · readiness)
#body         Horizontal
  #sorterpane Vertical (border)  border-title "SORTERS"
    #sorters  NavList(OptionList)  ALWAYS displayed (no accordion)
  #actionpane Vertical (border)  border-title "ACTIONS — on <active>"
    #actions  NavList(OptionList)  ALWAYS displayed
#inspect      VerticalScroll(border)  border-title "INSPECTING ▸ <row> · <subtitle>"
  #inspectbody Static
#footer       Static             context-sensitive key hints (per focused pane)
```

- **Both lists always displayed.** Drop the accordion `_switch_mode`/`display` flip and
  its invariant. `#sorters` and `#actions` co-exist; `←/→` and `Tab/Shift-Tab` move
  **focus** between the two panes (no show/hide). `↑/↓` / `j`/`k` move within the focused
  list. The focused pane's border is accent-highlighted; the blurred pane is dim.
- **INSPECTING** always renders the highlighted row of the **focused** pane — it absorbs
  both `_render_sorter_explain` and `_render_action_explain`. When focus is in SORTERS it
  shows the sorter blurb + state; in ACTIONS it shows the action's what/choose/caveat/needs.
- **DATA bar** (`_render_databar`): healthy → `DATA  ✓ LFP  ✓ Broadband  ✓ .nev units
  ✓ Events    all N streams loaded` (dim/neutral). Broken → emphatic amber/red
  `DATA  ✗ no recording in <folder> — press f to choose · d for help`, or per-file
  `✓/✗` when the set is incomplete, or `✗ Broadband won't load …` when a stream fails
  (reuse the pipeline broadband-FAIL detection). This **replaces** the quiet statusline
  *and* the bordered ⚠ banner; broken state still reads loud via colour + `✗` glyph
  (NO_COLOR-safe: `✗` + the explicit word "no"/"won't load"). `.nev`/Events listed only
  when present (empty Events is not a failure).
- **SORT bar** (`_render_sortbar`): `SORT  ★ <active> · <units> units · <secs> s saved ·
  <readiness>` where readiness ∈ `Ready to run (CPU, no Docker)` / `Ready to run (Docker)` /
  `Docker image not downloaded — Enter to get it` / `Needs an NVIDIA GPU` /
  `Not installed here`. Shows `· N custom params` when overrides exist.
- **Crest** kept (per decision); `m` toggles `animate`. Reserve math accounts for the
  fixed 2-row banner instead of the variable statusline+activebar.

#### Responsive rules (preserve current resilience guarantees)

- **Width:** side-by-side panes down to a `STACK_COLS` breakpoint (≈64); below it, `#body`
  stacks the two list panes vertically (SORTERS over ACTIONS). The banner always spans
  full width. INSPECTING spans full width in both.
- **Height pressure ladder** (drop in this order so the **lists never lose rows / never
  clip**): crest full→compact→mini→hidden first; then INSPECTING caps to `max-height`
  (≈4–6 rows) and, on extreme shortness, hides; the 2-line banner is the last to yield
  (collapse to 1 line — DATA only — only on the very shortest windows). Keep the
  "active/highlighted list always reachable at 20×5" guarantee.
- Constants: replace `SHIELD_RESERVE`/`NARROW_COLS`/`_BANNER_MIN_ROWS`/`_ACTIVEBAR_MIN_ROWS`
  with `STACK_COLS`, `BANNER_ROWS=2`, `INSPECT_MIN_ROWS`, and a crest reserve derived from
  the now-fixed banner height.

### 2. Sorter area — install visibility, download, delete

- **Row state glyphs** (`_sorter_text`): READY group = installed locally (existing active
  `▌`/`★`/`ACTIVE`/units markers kept). DOCKER group rows gain a **download badge**:
  `⬇ get` (image not present), `✓ ready` (image cached), `⬇ NN%` (downloading). GPU /
  NOT-AVAILABLE dim as today. INSPECTING shows full state for the highlighted sorter
  (install/download/saved/overrides + the right call-to-action).
- **Download — Enter, in the sorters area, separate from sorting.** Enter on a Docker
  sorter whose image is **not** present opens **`DownloadProgressScreen`**:
  - Resolve image via `sorters.default_docker_image(name)`. If the Docker daemon is down,
    route first through the existing `DockerConfirmScreen` start/enable flow.
  - Run `sorters.pull_docker_image(image, on_progress, on_status)` in a **Textual worker
    thread**; marshal callbacks to the UI with `app.call_from_thread` to drive a
    `ProgressBar` + layer status line. On success the row flips to `✓ ready` and the
    sorter becomes runnable (optionally auto-activate). Cancel closes the dialog (pulls
    are idempotent/resumable; no hard kill needed).
  - Enter on an installed/ready (or downloaded + Docker-on) sorter = **activate**. Enter on
    the Docker toggle row (index 0) flips Docker. Enter on GPU/unavailable = show block
    reason in INSPECTING.
- **Delete — `x` key → confirm modal (`ManageSorterScreen`, single-sorter):** offers
  whichever applies to the highlighted sorter, each with a confirm + freed-space note:
  *Delete downloaded image (~X GB)* (when `docker_image_present`), *Clear saved sort
  (outputs/<sorter>/, Nu)* (when saved). If neither applies, footer hint "nothing to
  delete for <sorter>". Nothing touches the pip env.

### 3. ACTIONS — new "Manage sorters" hub

Add an action `manage` → **"Manage sorters"** (hint: "download images · delete · clear
saved sorts"). It opens **`ManageSortersScreen`**, a full-screen management hub:

- A list of all sorters (grouped like the sidebar) with columns: group/install state,
  **image present?/size**, **saved units**, runnable.
- Per-row key actions: `Enter`/`g` download image (→ DownloadProgressScreen),
  `x` delete image, `c` clear saved sort, `r` re-check Docker/installed state, `Esc` close.
- This is the comprehensive counterpart to the inline SORTERS-pane shortcuts; both call
  the same controller methods. `manage` needs no recording (always enabled).

ACTIONS list becomes: explore, sort, report, gui, traces, compare, params,
**manage (new)**, verify, theme, help, quit. Number-key `1-9` still jump-run the first
nine; `manage` sits among them (renumber accordingly).

### 4. In-UI sorting — `SortProgressScreen` (structured + spinner/heartbeat)

Sorting runs **inside** the TUI as a modal; no `suspend()`.

- **Emitter:** `run_sorting.py` gains `--progress json`. A small new pure module
  `scripts/sort_progress.py` defines the event schema + an `emit(event)` writer and a
  `parse_line(str) -> dict | None` reader (both unit-testable with no SI/Textual). In
  `--progress json` mode, `ConsoleUI` and `AlignedTqdm` **also** emit newline-delimited
  JSON events to **stdout**, and route human/log text to **stderr** (so stdout is a clean
  event channel). Events:
  - `{"t":"phase","i":1,"n":4,"title":"Read broadband","sub":"22 ch · 30 kHz · 132 s"}`
  - `{"t":"bar","desc":"detect peaks","frac":0.63,"n":48,"total":76,"elapsed":48.1,"remaining":27.0}`
  - `{"t":"detail","text":"bandpass 300–6000 · common median ref"}`
  - `{"t":"heartbeat","label":"running sorter","secs":72}`
  - `{"t":"metrics","rows":[{"unit":1,"snr":7.2,"firing_rate":3.1,"isi":0.01}, …],"csv":"…/quality_metrics.csv"}`
  - `{"t":"done","ok":true,"units":13,"good":9,"out":"outputs/tridesclous2"}`
  - `{"t":"error","ok":false,"message":"Docker isn't running — open Docker Desktop and try again."}`
- **Runner:** `SortProgressScreen` spawns the subprocess with
  `asyncio.create_subprocess_exec(sys.executable, "scripts/run_sorting.py", …,
  "--progress","json", start_new_session=True)` (new process group ⇒ **Cancel** kills the
  whole worker tree). A Textual worker reads stdout lines, `parse_line`s them, and posts
  messages that update: a **phase checklist** (✓ done / ▶ current / dim upcoming), a
  **determinate `ProgressBar`** when a `bar` has a total, and a **spinner + "still working
  (Ns)"** line during indeterminate stretches (driven by `heartbeat` + a local
  `set_interval`). On `metrics` the quality table renders in-panel; on `done`/`error` the
  result line + "Press Enter to close". Closing returns `(ok, message, changed=True)`;
  the app `reload()`s so `13u saved` and the SORT bar update.
- **Invariant preserved:** the Textual process still imports **no SpikeInterface** — all SI
  work is in the subprocess. The controller's `run("sort", span)` is rerouted to open the
  modal (instead of `DISPATCH["sort"]` under `suspend()`); the existing params-file
  plumbing (`_write_params_file`) and `--docker`/`--duration` args are passed through.
- If the Docker image is missing at sort time, `run_sorting`'s existing pull-if-missing
  still runs and emits `bar`/`detail` pull events the same screen renders — but the primary
  path is "download first in the sorters area".

### 5. Registry & controller additions

`scripts/sorters.py`:
- `delete_docker_image(image) -> tuple[bool, str]` — `docker.from_env().images.remove(image)`;
  never raises; returns `(ok, human_message)`.
- `image_size(image) -> int | None` — bytes for the "freed ~X GB" note (SDK `attrs["Size"]`),
  None on any failure.

`MenuController` (in `SpikeInterface_Menu.py`):
- `image_state(name) -> dict` — `{image, present, size}` (resolve + `docker_image_present` +
  `image_size`), used to fill catalog rows' download badge. Folded into `_catalog()` so each
  `info` dict gains `img_present`/`img_size` (Docker rows only; cheap, guarded, cached per
  reload).
- `download_image(name, on_progress, on_status) -> tuple[bool, str]` — wraps
  `pull_docker_image`; the screen drives callbacks.
- `delete_image(name) -> tuple[bool, str]` — resolves image + `sorters.delete_docker_image`.
- `clear_saved_sort(name) -> tuple[bool, str]` — robust-rmtree `outputs/<name>/`
  (reuse the `_robust_rmtree` pattern); returns freed/cleared message.
- `start_sort(...)`/run wiring so the app opens `SortProgressScreen` rather than dispatching
  under suspend. Keep `run(key, span)` for the non-sort actions.

### 6. Fallback (typed / prompt_toolkit) menu

Keep `_menu_fallback` functional and intentionally non-parity (no live progress / no
modals). Surface the new capabilities minimally: a typed **"Manage sorters"** option that
lists install/download/saved state and offers download (blocking, with the existing
`pull_docker_image` printing simple progress), delete image, and clear saved sort. Sorting
in the fallback continues to shell out to `run_sorting.py` (human output). Shared metadata
(`_ACTION_DETAIL`, `ui.stream_detail`) keeps the fallback's hints in sync.

### 7. Tests

- **Pure first (TDD):** `sort_progress.py` event round-trip (`emit`→`parse_line`) and the
  event→view-state reducer; `sorters.delete_docker_image`/`image_size`;
  `MenuController.download_image`/`delete_image`/`clear_saved_sort`/`image_state`.
- **Pilot tests rewritten** for the three-panel model: boot shows **both** lists; `←/→` &
  `Tab` move focus (not show/hide); INSPECTING reflects the focused list's highlight;
  DATA/SORT banner healthy vs broken; download badge on Docker rows; Enter→download opens
  `DownloadProgressScreen`; `x`→`ManageSorterScreen`; the `manage` action opens
  `ManageSortersScreen`; `SortProgressScreen` driven by synthetic JSON lines (no real
  subprocess) renders phases/bar/metrics/done; responsive stack + never-clip + crest drop.
- **conftest `FakeController`** extends with `image_state`, `download_image`,
  `delete_image`, `clear_saved_sort`, and a fake saved/image universe; the ACTIONS table
  gains `manage`.
- Surviving largely as-is: registry param/status/group/run tests; controller param/
  welcome/animate/action_explain tests (update the action list/count).

## Files touched

| File | Change |
|------|--------|
| `scripts/menu_app.py` | Layout rewrite (three panels + banner, drop accordion); 3 new screens: `SortProgressScreen`, `DownloadProgressScreen`, `ManageSortersScreen` (+ single-sorter `ManageSorterScreen` confirm); focus-not-display nav; INSPECTING merge; responsive ladder rework |
| `scripts/sort_progress.py` (new) | Pure event schema + `emit`/`parse_line` (no SI/Textual deps) |
| `scripts/run_sorting.py` | `--progress json` mode wiring `ConsoleUI`/`AlignedTqdm` to `sort_progress.emit`; stdout=events, stderr=human |
| `scripts/sorters.py` | `delete_docker_image`, `image_size` |
| `SpikeInterface_Menu.py` | Controller: `image_state`, `download_image`, `delete_image`, `clear_saved_sort`, sort-modal wiring; `manage` action in `_ACTIONS`/`_ACTION_DETAIL`; fallback "Manage sorters" |
| `scripts/ui.py` | Banner/border styling helpers, sorter-row download glyphs, theme touch-ups |
| `tests/*` | Rewrite Pilot layout/nav tests; add pure-logic tests; extend `FakeController` |
| `CLAUDE.md` | Architecture section rewrite for the three-panel dashboard + in-UI sort/download/manage |

## Build stages (each verified before the next)

1. **Logic & emitter:** `sort_progress.py`, `run_sorting.py --progress json`,
   `sorters.delete_docker_image`/`image_size`, controller methods — with unit tests.
2. **Layout & banner:** three-panel `compose`, DATA/SORT bars, focus nav, INSPECTING merge,
   responsive ladder; rewrite the Pilot layout/nav tests.
3. **In-UI sort:** `SortProgressScreen` + controller wiring; Pilot test with synthetic events.
4. **Download + row state:** `DownloadProgressScreen`, Docker-row badges, Enter→download.
5. **Manage/delete:** `ManageSortersScreen` action + `x` single-sorter confirm + clears;
   fallback "Manage sorters"; `CLAUDE.md` update; full `pytest` green.

## Risks / mitigations

- **Subprocess lifecycle / Cancel:** use `start_new_session=True` and kill the process
  group; on app exit, ensure the child is terminated. Test the parser, not the spawn, in CI.
- **stdout/stderr split in `run_sorting`:** the tqdm patch + ConsoleUI must write events to
  stdout and everything else to stderr only in `--progress json` mode; default CLI behavior
  unchanged. Cover with a subprocess smoke test (`--duration` tiny) gated to not require data.
- **Docker SDK presence:** all image helpers already degrade (no SDK / daemon down → False/
  None); delete/size follow the same never-raise discipline.
- **Test churn:** the accordion Pilot tests are intentionally replaced; the both-panes
  invariants are re-pinned. Keep registry/controller pure tests stable to limit blast radius.
- **Reserve/relayout regressions:** keep the "lists never clip at 20×5" and "broken state is
  loud" guarantees as explicit Pilot tests.
