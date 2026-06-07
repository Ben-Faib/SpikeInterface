# Multi-sorter support — design

**Date:** 2026-06-07
**Status:** approved (brainstorm) → ready for implementation plan
**Goal:** make the workspace work with as many spike sorters as possible, instead of
the two hardcoded today (`tridesclous2`, `spykingcircus2`).

## Motivation

`SORTERS = ["tridesclous2", "spykingcircus2"]` in `scripts/run_sorting.py` is the
single hardcoded source of truth, imported by the menu. Reality on this machine:

- SpikeInterface 0.104.3 **knows about 22 sorters**.
- **Four are runnable locally right now**: `tridesclous2`, `spykingcircus2`,
  `lupin`, `simple` — the menu hides `lupin` and `simple`.
- **Docker is installed** (28.4.0), so SpikeInterface's container path
  (`run_sorter(..., docker_image=True)`) can run sorters that aren't installed.
- This is a **Mac with no NVIDIA GPU**, and Docker-on-Mac has no NVIDIA
  passthrough, so GPU-only sorters (Kilosort family, pykilosort, yass) will not
  run here even via Docker. "As many as possible" therefore means **all
  CPU-capable sorters, local + containerized**.

## Scope (decisions from brainstorming)

1. **Ambition:** local auto-detect **+ opt-in Docker**. Surface every locally
   installed sorter automatically; let the user opt into Docker to run
   not-installed CPU sorters on demand. No Docker pulls happen unless asked.
2. **Compare:** the user **chooses which two saved sorts to compare** (instead of
   assuming "the other" sorter). Stays pairwise (SpikeInterface
   `compare_two_sorters`); N-way `MultiSortingComparison` is a non-goal.
3. **Parameters:** **full per-sorter parameter editing** — view/edit a sorter's
   parameters before running, via the menu and the CLI.
4. **Controls (UI):** parameter editing is an **Action** in the right-hand
   Actions list (acts on the active sorter); the **Docker toggle is a row at the
   top of the Sorter sidebar** (reached with ↑/↓, flipped with Enter), because it
   changes which sorters the sidebar lists. **No new global letter hotkeys** (they
   were judged awkward, and `D` clashed with the existing `d` = data-setup).
5. **Persistence:** the Docker on/off state and per-sorter parameter **overrides**
   persist to the existing git-ignored `.si_menu.json`.

## Architecture

A new module **`scripts/sorters.py`** becomes the single source of truth for
sorter *discovery, status, parameters, and running* — mirroring how
`blackrock_io.py` owns dataset loading. Every consumer imports from it:
`run_sorting.py`, `SpikeInterface_Menu.py`, `scripts/compare.py`,
`scripts/verify_install.py`, `scripts/menu_app.py`.

*Alternatives considered and rejected:*
- Grow `run_sorting.py` in place — it already carries tqdm/rich UI plumbing;
  adding discovery/Docker/param logic would mix concerns and bloat one file.
- Put helpers in `blackrock_io.py` — that module is about loading *this Blackrock
  dataset*, not sorter orchestration; wrong home.

## Component: `scripts/sorters.py`

Pure orchestration logic, no UI. Heavy SpikeInterface imports stay lazy (inside
functions) so importing the module is cheap, matching the rest of the codebase.

### Constants
- `GPU_SORTERS: frozenset` = `{"kilosort", "kilosort2", "kilosort2_5",
  "kilosort3", "kilosort4", "pykilosort", "yass"}` — require an NVIDIA GPU; shown
  as informational-only ("GPU — won't run here") on this machine.
- `CONTAINERIZED: frozenset` — CPU-capable sorters with an official SpikeInterface
  Docker image. Curated, maintainable set:
  `{"combinato", "herdingspikes", "mountainsort4", "mountainsort5",
  "spykingcircus", "tridesclous", "tridesclous2", "spykingcircus2", "waveclus",
  "hdsort", "ironclust"}`. (Locally-installed ones still report `local`; this set
  matters for the ones that aren't installed.) A short comment documents that this
  list is maintained against SpikeInterface's published images.
- `DEFAULT_SORTER: str` — `tridesclous2` if installed, else the first installed
  sorter (so a fresh machine still gets a sensible default).

### Functions
- `available() -> list[str]` — `sorted(ss.available_sorters())`.
- `installed() -> list[str]` — `sorted(ss.installed_sorters())`.
- `docker_available() -> bool` — `shutil.which("docker")` is set **and** `docker
  info` returns 0 within a short timeout. Result cached per process (the daemon
  state rarely changes mid-session); a `refresh=` arg forces a re-check.
- `status(name) -> str` — one of:
  - `"local"`   if `name in installed()`.
  - `"gpu"`     elif `name in GPU_SORTERS` (informational; not runnable here).
  - `"docker"`  elif `name in CONTAINERIZED and docker_available()`.
  - `"unavailable"` otherwise (not installed, no usable image, or Docker off).
- `runnable(use_docker: bool) -> list[str]` — `installed()`, plus
  (`CONTAINERIZED − GPU_SORTERS − installed()`) when `use_docker and
  docker_available()`. Sorted, installed-first. This is the list the menu offers.
- `default_params(name) -> dict` — `ss.get_default_sorter_params(name)`.
- `param_descriptions(name) -> dict` — `ss.get_sorter_params_description(name)`.
- `coerce_param(default_value, raw: str)` — coerce a CLI/string value to the type
  of the sorter default: `bool` accepts true/false/1/0/yes/no; `int`/`float`
  parsed; `None`/`dict`/`list` parsed as JSON; `str` passed through. Raises
  `ValueError` with a clear message on failure.
- `merge_params(name, overrides: dict) -> dict` — start from `default_params`,
  apply only the keys in `overrides`; raise on unknown keys, listing valid ones.
- `run(name, recording, folder, *, params=None, use_docker=False, verbose=False)
  -> Sorting` — wraps `ss.run_sorter(name, recording, folder=folder,
  remove_existing_folder=True, docker_image=use_docker, sorter_params=params or
  {}, verbose=verbose)`. Surfaces a clear message if `use_docker` but Docker is
  down.
- `status_table() -> list[dict]` — `[{name, status, n_params}]` for every
  `available()` sorter; feeds `--list-sorters` and `verify_install.py`.

### Param-override model (persistence-friendly)
The menu and config store **only overrides** (keys that differ from the sorter's
current default), not full param dicts. This keeps `.si_menu.json` small and
robust when SpikeInterface changes its defaults across versions. At run time the
effective params are `default_params(name)` overlaid with the saved overrides
overlaid with any CLI `--param`.

## Component: `scripts/run_sorting.py`

- Drop the hardcoded `SORTERS` constant. The menu imports from `sorters` directly
  (the `from run_sorting import SORTERS` line is removed), so `run_sorting.py` no
  longer needs to export a sorter list at all.
- `--sorter` is **validated after parsing** (not a fixed argparse `choices`)
  against `sorters.runnable(args.docker)`; an invalid name prints the runnable
  list and the GPU/unavailable reason. Default = `sorters.DEFAULT_SORTER`.
- New flags:
  - `--docker` — run the chosen sorter in its SpikeInterface Docker image.
  - `--param NAME=VALUE` (repeatable) — per-run override, type-coerced via
    `sorters.coerce_param`.
  - `--params-file PATH.json` — JSON dict of overrides (used by the menu to pass
    edited params to the subprocess).
  - `--list-sorters` — print `status_table()` and exit 0.
- Merge precedence for params: `defaults` < `--params-file` < `--param`. Unknown
  keys → error listing valid keys, before any sorting starts.
- The "Sort" phase calls `sorters.run(args.sorter, rec, folder, params=...,
  use_docker=args.docker, verbose=show_bars)`. Before a Docker run, print a note
  that the first run pulls an image (can be large/slow).
- Quality-metrics / save / output paths unchanged. Output still lands in
  `outputs/<sorter>/`.

## Component: `SpikeInterface_Menu.py` + `MenuController`

- Import the sorter list from `sorters` (remove `from run_sorting import
  SORTERS`). The controller's sorter set = `sorters.runnable(self.use_docker)`.
- `MenuController` gains:
  - `use_docker: bool` — loaded from / saved to `.si_menu.json`; `toggle_docker()`
    flips it, re-saves, and `reload()`s (the sorter list grows/shrinks).
  - `sorter_params: dict[str, dict]` — per-sorter overrides from config;
    `set_params(sorter, overrides)` saves them.
  - `default_params(sorter)` / `param_descriptions(sorter)` pass-throughs for the
    Param Editor.
- `run("sort", ...)`: writes the effective overrides for the active sorter to a
  temp JSON file and calls `run_sorting.py --sorter <s> --params-file <tmp>
  [--docker] [--duration N]`. Temp file cleaned up afterward.
- `compare` action: a **picker** chooses which two *saved* sorts to compare (only
  sorters with an `outputs/<sorter>/analyzer` are offered). Needs ≥2 saved sorts,
  else a clear warning. The existing duration-mismatch caveat + optional re-sort
  offer is preserved, run on the chosen pair.
- `.si_menu.json` schema additions (backward-compatible; missing → defaults):
  ```json
  { "theme": "...", "use_docker": false,
    "sorter_params": { "tridesclous2": { "detect_threshold": 6.0 } } }
  ```

## Component: Textual app `scripts/menu_app.py`

- **Sorter sidebar** is dynamic over `controller.sorters` and scrollable (already
  supported). Each sorter row shows a status glyph + saved summary:
  `● tridesclous2   3u·30s` (local) · `◇ mountainsort5  —` (docker) ·
  dim `· kilosort4  (GPU)` if any GPU rows are shown. The active marker applies to
  sorter rows only.
- **Docker toggle row** at the **top of the Sorter pane**: a selectable row
  `⊞ Docker sorters: off` / `on`. ↑/↓ reaches it; Enter flips
  `controller.toggle_docker()` and the list re-renders (container sorters appear /
  disappear). It is never the "active sorter".
- **Actions list** gains an **"Edit sorter parameters"** action (acts on the
  active sorter; opens the Param Editor modal). Existing actions unchanged.
- **Param Editor modal** (`ModalScreen`): a scrollable form for the active
  sorter, one row per parameter showing name + description (from
  `param_descriptions`) + an editable value prefilled from saved-or-default:
  - scalar `bool` → a toggle/checkbox; `int`/`float`/`str` → a text `Input`
    validated/coerced on save.
  - `None` default → text field; empty = `None`, else JSON-parsed.
  - `dict`/`list` default → JSON text field; parse errors flagged inline, not
    saved.
  - "Save" stores only changed keys via `controller.set_params`; "Cancel"
    discards. A "Reset to defaults" button clears overrides for that sorter.
- **Compare picker modal**: choose two sorters that have a saved analyzer (list of
  selectable rows; OK enabled when exactly two chosen). Returns the pair to the
  compare flow, which then runs as today (mismatch caveat + optional re-sort
  during `suspend()`).
- Help/footer text updated to mention the Docker row and the param-edit action.
  No new global hotkeys.

## Component: fallback typed menu (`scripts/ui.py`, `_menu_fallback`)

Same capabilities without Textual:
- `t` cycles through the dynamic `sorters.runnable(...)` list.
- A "Docker sorters: off/on" entry toggles `use_docker` (re-saves, reloads).
- An "Edit sorter parameters" entry → `ui.select` a parameter, then prompt a new
  value (coerced); repeat until done. Stores overrides.
- `compare` → `ui.select` the two saved sorts to compare.
The plain-text missing-data guidance is unchanged.

## Component: `scripts/compare.py`

- `build_comparison(data_dir=None, sorters=None, out_path=None)` — when `sorters`
  is `None`, default to the **first two sorters with a saved analyzer** (instead
  of the hardcoded pair). When given, use exactly that pair. All existing logic
  (heatmap, Hungarian match table, duration-mismatch caveat) is unchanged.

## Component: `scripts/verify_install.py`

- Add a **sorter status section**: a table of every `available()` sorter with its
  `status` (local / docker / gpu / unavailable) and parameter count, plus a
  one-line summary ("4 local, N container-capable, M GPU-only"). Documents exactly
  what is runnable on the current machine.

## Testing

- **Registry unit tests** (`tests/`): `status()` / `runnable()` classification
  with `installed()` and `docker_available()` monkeypatched (local-only,
  docker-on, docker-off, GPU name); `coerce_param` per type incl. error cases;
  `merge_params` unknown-key error. Hermetic — no real Docker, no real sorting.
- **Textual Pilot tests**: Param Editor modal opens, edits a scalar, saves → the
  override reaches the controller; Docker toggle row flips and the sorter list
  length changes (with `docker_available` and `runnable` stubbed); compare picker
  requires two selections. Reuse the existing small-size / focus harness.
- Existing menu tests continue to pass.

## Error handling

- `--docker` (or Docker row on) while the daemon is down → clear message; the menu
  stays alive, the toggle still flips but `runnable` won't add container sorters
  until the daemon is up.
- A container sort failing (missing image, needs GPU) → surfaced via the existing
  try/except in `MenuController.run`; the app survives.
- Param coercion / unknown-key / JSON-parse errors → reported before any sorting
  starts; nothing destructive happens.
- A sorter selected via CLI that isn't runnable → exits with the runnable list and
  the reason (gpu / not installed / Docker off).

## Non-goals (YAGNI)

- No GPU sorter **execution** (no NVIDIA GPU; Docker-on-Mac has no passthrough).
  GPU sorters are shown for transparency only.
- No N-way `MultiSortingComparison` — compare stays pairwise (user-chosen pair).
- No real Docker image pulls in tests / CI.
- No automatic probe geometry inference — unrelated to this work.

## Docs

Update `CLAUDE.md`: the new `scripts/sorters.py` registry as source of truth, the
local-vs-Docker status model, opt-in Docker, per-sorter parameter editing
(menu Action + CLI `--param`/`--params-file`), the dynamic sorter sidebar with the
Docker toggle row, the user-chosen compare pair, and the new `.si_menu.json` keys.
