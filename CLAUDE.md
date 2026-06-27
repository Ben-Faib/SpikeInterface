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
- **Sorters are discovered dynamically** via `scripts/sorters.py` (the registry — single source of truth). `installed_sorters()` runnable locally today: `tridesclous2`, `spykingcircus2`, `lupin`, `simple`. Not-installed **CPU** sorters (mountainsort5, herdingspikes, spykingcircus, waveclus, combinato, …) can run via **opt-in Docker** (`run_sorter(..., docker_image=True)`) — Docker is detected at runtime. **GPU sorters** (kilosort*, pykilosort, yass) are shown but never offered here: no NVIDIA GPU, and Docker-on-Mac has no GPU passthrough. `sorters.status(name)` → `local`/`docker`/`gpu`/`unavailable`. For the newcomer-friendly menu the registry also exposes `RECOMMENDED` (the badged `★` default = `tridesclous2`), `DESCRIPTIONS`/`description(name)` (one-line plain-language blurb per sorter, generic fallback for unknowns), and `group_of(name)` → `ready`/`docker`/`gpu`/`unavailable` (a **membership-precedence** group that, unlike `status()`, does *not* depend on the live Docker daemon, so a sorter never jumps groups when Docker starts/stops — installed wins first, so an installed GPU sorter on a GPU box lands in `ready`).

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
`available()`/`installed()` wrap SpikeInterface; `status(name)` classifies each
sorter `local`/`docker`/`gpu`/`unavailable`; `group_of(name)` is the **stable**
sidebar grouping (`ready`/`docker`/`gpu`/`unavailable`, daemon-independent);
`runnable(use_docker)` is what the menu offers as *selectable* (installed always,
container CPU sorters when Docker is on); `default_params`/`param_descriptions`/
`coerce_param`/`merge_params` back the parameter editor; and `run(...)` wraps
`run_sorter` with `docker_image=` + `sorter_params=`. **Docker is three-state:**
`docker_state(refresh=)` → `running`/`installed_not_running`/`not_installed`
(cached per process, never raises; `refresh=True` re-probes — the confirm dialog
does this); `docker_available()` is just `docker_state() == "running"`; and
`start_docker()` best-effort launches Docker Desktop (`open -a Docker` on macOS,
the install path / `start` on Windows, `systemctl --user start docker-desktop` on
Linux), returning whether a launch command was *issued* (the caller polls
`docker_state(refresh=True)` until `running`). `RECOMMENDED` + `DESCRIPTIONS`/
`description(name)` give the badged default and per-sorter blurbs. **Docker images
are managed in-UI:** `default_docker_image(name)` resolves the exact image,
`docker_image_present(image)` checks the local cache, `pull_docker_image(image,
on_progress, on_status)` pulls it with streaming callbacks (driven by the menu's
`DownloadProgressScreen`), and `image_size(image)` / `delete_docker_image(image)`
back the size note + in-UI delete — all never raise (degrade to `False`/`None` with
no SDK / daemon down). Heavy SpikeInterface imports stay lazy, so importing the
registry is cheap. `GPU_SORTERS` and `CONTAINERIZED` are curated constants.

`scripts/run_sorting.py` is the sorting entry point built on these loaders: `read_broadband()` → `bandpass_filter(300–6000)` → `common_reference(median)` → `run_sorter(--sorter)` → save Sorting + `SortingAnalyzer` quality metrics under `outputs/<sorter>/`. Use `--duration N` to sort only the first N seconds as a smoke test. With `--docker` it prints a clear first-run note ("first Docker run downloads the sorter image (~1 GB, one time only)"), and a Docker daemon failure is caught and re-phrased as a friendly hint ("Docker isn't running — open Docker Desktop and try again.") instead of a raw traceback.

**Terminal presentation** (`run_sorting.py` only) is layered: `--verbosity {quiet,normal,verbose}` (default `verbose`) picks how much shows — `verbose` = numbered phase headers + per-step sorter prints + progress bars, `normal` = headers + final table (no bars), `quiet` = final table only. A separate `--progress {plain,json}` (default `plain`) turns on a **machine-readable event channel** for the in-UI sort modal: in `json` mode a `Reporter` mirrors the `ConsoleUI`/aligned-tqdm calls into newline-delimited `scripts/sort_progress.py` events on **stdout** while the human/rich output (and any sorter fd-1 writes — fd 1 is dup2'd to stderr) goes to **stderr**, so stdout stays a pure event stream the `SortProgressScreen` parses.
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
controller. Layout is a **simultaneous three-panel dashboard** (the pre-accordion
look, restored): a two-line **DATA / SORT banner** (`#databar` + `#sortbar`) on
top, then `#body` holding the **SORTERS** pane (`#sorters` in `#sorterpane`) and the
**ACTIONS** pane (`#actions` in `#actionpane`) **side-by-side — both always
displayed** (no accordion, no `display:none` flip), and a full-width **INSPECTING**
panel (`#inspect` / `#inspectbody`) along the bottom. Panel labels are
`border_title`s (`SORTERS`, `ACTIONS — on <active>`, `INSPECTING ▸ <row>`); the
focused pane gets `:focus-within { border: heavy $accentcolor }`. **Focus, not
mode:** `←/→` (or `Tab/Shift-Tab`) move focus *between* the two always-visible panes
via `action_focus_sorters`/`action_focus_actions` (no show/hide); `↑/↓` (or `j/k`)
move within the focused list. The bottom **INSPECTING panel follows the focused
pane's highlighted row** — `_render_inspect(focus=…)` dispatches to
`_render_sorter_explain`/`_render_action_explain` (both now write `#inspectbody`),
and `on_option_list_option_highlighted` drives it. (The old side `#explain`,
`#statusline`, `#activebar`, `#panelabel`, `_switch_mode`/`_mode` are gone.) The
sorter list **flexes to fill** (most of the ~27-row catalog visible), **auto-scrolls**
the active/highlighted row into view, and marks the **active sorter as a shape, not
just colour**: a left accent **bar `▌`** + bold name + **reverse `ACTIVE` chip**
(plus the `★` recommended badge and saved-unit count) — structurally distinct from
the cursor highlight. `_render_sorter_explain` shows the highlighted sorter's full
(un-truncated) description, header state (`★ · ACTIVE` / `press Enter to make
active` / the block reason for non-runnable rows), saved units · duration, group
reason, any `· N custom params` count, and a `Press → or Tab for actions.`
call-to-action; `_render_action_explain` shows the controller's resolved action
metadata — *what it does*, an optional *you'll choose* line, a `⚠` caveat, and a
`Needs … ✓/✗` + `Output …` footer (omitted for needs-nothing actions). The cursor
highlight is themed to read as *cursor* (focused: a faint accent wash; blurred: an
underline, no filled bar) so it never masquerades as the active selection. **Always-on DATA / SORT banner** (replaces the old quiet statusline + action-mode
activebar). `_render_databar`: healthy → `DATA  ✓ LFP  ✓ Broadband  ✓ .nev …  all N
streams loaded` (`.nev`/Events listed only when present — empty Events is **not** a
failure); broken → a **loud** `DATA  ✗ no recording in <folder> — press f … d …`
(or per-file `✗` when incomplete, or `✗ Broadband won't load …` reusing
`controller.pipeline`'s broadband-`FAIL` detection) — `✗` + the explicit word are
the NO_COLOR-safe shape cues. `_render_sortbar`: `SORT  ★ <active> · <units> units ·
<secs> s saved · <readiness>` where readiness ∈ `Ready to run (CPU, no Docker)` /
`… (Docker)` / `Docker image not downloaded — Enter to get it` / `Needs an NVIDIA
GPU` / `Not installed here`, plus `· N custom params`. **Responsive:** below
`STACK_COLS` (≈64) `#body` **stacks** the two panes (SORTERS over ACTIONS); the
2-row banner spans full width. Under height pressure the **chrome yields in order so
the lists never clip**: the crest drops first (full→compact→mini→hidden), then
`#inspect` caps to `max-height` and hides on extreme shortness, and a `tiny` tier
collapses the title + banner and drops the pane borders — the active/highlighted
list stays reachable down to ~20×5 (re-pinned by the never-clip Pilot tests).
**Navigation:** ←/→ (or Tab/Shift-Tab) move focus **between** the two always-visible
panes; ↑/↓ (or j/k) move within the focused list. **Enter on a runnable sorter
activates it** (and moves focus to ACTIONS); Enter on a **Docker sorter whose image
isn't downloaded** opens the in-UI **`DownloadProgressScreen`** (routing through the
Docker-enable flow first if the daemon is down); Enter on the **Docker toggle row**
(`#sorters` index 0) flips Docker; Enter on a GPU/unavailable sorter shows the block
reason; Enter on an action runs it. **1–9** jump-run an action (explore 1 … params
7, **manage 8**, verify 9; theme/help/quit unnumbered). **x** opens the per-sorter
**`ManageSorterScreen`** (delete downloaded image / clear saved sort — applicable
ops only, each confirmed). **t** cycles the active sorter, **?** opens **Help** and **d** jumps to its *Data files* topic, **f**
re-points the data folder, `q`/Ctrl-C quit (Esc is a deliberate no-op so a reflexive
back-press never exits). A width-adaptive footer echoes the active sorter + last
result. A one-time **WelcomeScreen** greets first-time users (gated by `seen_welcome`
in `.si_menu.json`). **Actions run in three ways:** **Sort** runs *inside* the TUI
via **`SortProgressScreen`** (below) — never `suspend()`; the desktop/browser actions
(explore/report → browser, gui/traces → Qt child via `_self`) still drop out via
`suspend()`; the sort-span, theme, compare-pick, param-edit, Docker, download,
manage, welcome and help flows are in-app **modal** screens (`ChoiceModal`,
`DockerConfirmScreen`, `ParamEditorScreen`, `SortProgressScreen`,
`DownloadProgressScreen`, `ManageSortersScreen`, `ManageSorterScreen`,
`WelcomeScreen`, `HelpScreen`). **In-UI sorting:** the Sort action opens
`SortProgressScreen`, which `asyncio.create_subprocess_exec`s
`run_sorting.py --progress json` in a **new session** (so Esc → `os.killpg` kills the
SI worker tree), reads its stdout, folds each line through the pure
`scripts/sort_progress.py` protocol (`emit`/`parse_line`/`reduce`; events on stdout,
human text on stderr — `run_sorting` dup2's fd 1→stderr in json mode so the channel
stays pure), and renders a **phase checklist + determinate bar + spinner/heartbeat**;
on success it reloads the dashboard. **In-UI Docker download:**
`DownloadProgressScreen` pulls the image in a **worker thread**
(`sorters.pull_docker_image`), marshalling progress to the UI via `call_from_thread`;
Docker rows show a `⬇ get` / `✓ ready` / `⬇ NN%` badge from the catalog's
`img_present`. **Manage sorters:** the `manage` action opens `ManageSortersScreen`, a
grouped hub over every sorter (per-row `enter`/`g` download, `x` delete image, `c`
clear saved sort, `r` reload) — destructive ops (`controller.delete_image` →
`sorters.delete_docker_image`, `controller.clear_saved_sort`) **always confirm**
(reusing `ChoiceModal`), never a single keystroke. The Textual process still imports
**no SpikeInterface** — all SI work stays in the controller / the sort subprocess.
**Missing data:** `_data_report()` classifies the data dir as complete / incomplete /
absent; the DATA bar goes loud (above) and the data-dependent actions are dimmed with
the inline `(needs data)` suffix. The expected-
files checklist (`.ns2` LFP / `.ns5` broadband / `.nev` events, each present/missing
with the folder it belongs in) is now the **Data files** topic of the unified
**HelpScreen** (reached via the *Help* action, **`?`**, or **`d`**), which replaces
the old standalone Data-Setup screen/action — its topics come from `ui.HELP_TOPICS`
(overview / 3 steps / sorters / Docker / data / keyboard), with the `data` body
rendered live from the data report. Because the main view no longer shows the
pipeline panel, the per-stream load detail (channels · rate · duration) it used to
carry is **relocated to the `d` Data-files topic**, merged in from
`controller.pipeline` via the shared `ui.stream_detail(files, pipeline)` helper
(matched by extension; the same helper feeds the fallback's `data` topic). Off-TTY / without
Textual installed it falls back to the legacy `ui.dashboard_menu()`
(prompt_toolkit full-screen, else a typed numbered menu), which prepends the same
missing-data guidance in plain text.
A **static block-letter "SPIKE" wordmark** sits atop the dashboard, drawn by
`CrestWidget` (`ui.pick_wordmark`/`ui.wordmark_rows`/`ui._WORDMARK_*`): the letters
in width-safe glyphs only (full block `█` + spaces, the same discipline as the
shield), picking the largest tier (full 5-row → compact `S P I K E` one-liner →
hidden) that fits the live window. It is **not animated** — painted once and
re-painted on resize/theme change — and is coloured at render time from the live
accent, so it follows the colour theme. Preview it with
`scripts/_wordmark_preview.py`. The detailed **blue +
gold Pitt shield** (the `ui._LOGO_ART` ladder — 21/15/11-col grids of only the
full block `█` and spaces, every row the same width so it aligns in any monospace
terminal/font with no ambiguous-width glyphs; heraldry in negative space —
crenellated turrets, a centre keystone notch, roundels over a blue/gold checky
band, tapering to the base point) now draws only on the **Welcome screen**
(`#wcrest`, `ui.SHIELD_FULL`) and the **Help "About"** topic (`ui.SHIELD_COMPACT`),
not the dashboard top. The **accent colour is themeable**
(`ui.THEMES`: periwinkle/sea-green/steel-blue/amber/cyan; default periwinkle),
driven into the Textual **`$accentcolor`** CSS variable (via
`App.get_css_variables` + `refresh_css`); it is changed through the *Change colour
theme* modal and **persisted** to a git-ignored `.si_menu.json` at the repo root
(`_load_config`/`_save_config`), re-applied on launch with `ui.set_accent()`.
`scripts/ui.py` still holds the shared rich styling (rules, boxed tables, ✓
lines), the shield art + theme palette, the sorter-row download glyphs (`ui.DL_*`),
and the inline `select()` used by the fallback menu and compare's re-sort prompt.
The controller shells out to the `scripts/*.py` for explore/verify (live stdout via
`suspend()`), runs **sort in-UI** (`SortProgressScreen` streams
`run_sorting.py --progress json` — `MenuController.sort_command()` builds the argv),
calls `report.build_report(...)` in-process, and launches the **blocking** Qt GUIs in
fresh child processes (`_self`): the inspector is `spikeinterface-gui` (console
command **`sigui
<analyzer_dir>`**, not `spikeinterface-gui`) and the trace browser is
`plot_traces(..., backend="ephyviewer")`. `make_report.py` is now a thin shim
over the launcher's `report` action. `scripts/compare.py` builds a standalone
`outputs/comparison.html` from `compare_two_sorters`; it refuses to draw a
misleading matrix when the two sorts cover different windows (the launcher's
`compare` action offers to re-sort both over a common window first). The Qt
binding under uv is **PySide6** (pulled by `spikeinterface-gui[desktop]`); the
conda fallback (`environment.yml`) resolves to **PyQt5** instead — either works,
but don't install both into one env.
The **Sorter sidebar** lists the **full catalog** (`sorters.available()`, built by
the controller's `_catalog()`), grouped by `group_of()` into **READY TO USE** /
**DOCKER SORTERS** / **NEEDS A GPU** / **NOT AVAILABLE** (empty groups omitted, with
header rows (brighter than their rows — `bold ui.SECONDARY` — so the grouping reads
as structure), so newcomers see every sorter and *why* it is or isn't usable. Each
catalog entry is a dict with the stable keys
`name/group/status/runnable/recommended/description/present/units/duration/active/overrides`
plus, for **docker-group rows**, `image/img_present/img_size` (the resolved image,
whether it's cached locally, and its size — folded in by `_catalog()` only when
Docker is installed). `overrides` = count of saved per-sorter param diffs;
`★` marks the recommended default, the active row gets the `▌` bar + reverse `ACTIVE`
chip, non-runnable rows use the secondary-grey name, **Docker rows carry a
`⬇ get`/`✓ ready`/`⬇ NN%` download badge**, and the bottom **INSPECTING panel**
(`#inspect`) shows the highlighted sorter's full info. **Activation is by name** (`set_active_by_name`,
`cycle_active` for `t`) — selecting a non-runnable Docker sorter offers to enable
Docker; a GPU/unavailable one shows a hint. A `[ ]/[x] Docker sorters: off/on` **toggle
row at the top** (↑/↓ to reach it, Enter to flip) opens the guided
**`DockerConfirmScreen`** when turning *on* (turning off is immediate): it reads
`docker_status()`'s three-state and adapts — *running* → just **[e] Enable**;
*installed-not-running* → **[s] Start Docker for me** (calls `start_docker()`) +
**[r] Re-check**; *not-installed* → **[o] Open download page** + **[r] Re-check**;
Enable is always allowed (container sorters appear once Docker is up). An **"Edit
sorter parameters"** action opens a Param Editor modal for the active sorter
(scalars inline, bool as a checkbox, dict/None as JSON; Ctrl+S saves only the
changed keys, Ctrl+R resets). **Compare** opens a two-step picker to choose which
saved sorts to compare. Docker on/off, per-sorter parameter **overrides** (diffs
from defaults), the colour theme, and the **`seen_welcome`** one-time-welcome flag
persist to `.si_menu.json` (`use_docker`, `sorter_params`, `theme`, `seen_welcome`).

The typed/prompt_toolkit fallback menu is **intentionally non-parity** (no
accordion, no explanation pane): it has no horizontal pressure, so it keeps its
always-on Sorters + **pipeline** + Actions catalog and the always-visible
`status_table` as a *feature*. It does share the new action metadata, though — the
per-action `what` description (from `MenuController.action_explain`, backed by
`_ACTION_DETAIL`) and the destructive-`sort` `caveat` flow into its action `hint`
text so the typed menu still warns before a re-sort, and its `data` help renders
the same per-stream ch/rate/duration via the shared `ui.stream_detail` helper, and a
typed **Manage sorters** option (`_manage_sorters_typed`) gives blocking
download/delete-image/clear-saved-sort parity. The sorter catalog, Docker confirm,
Welcome, and Help still mirror the Textual app via `ui.select`/prompts +
`ui.print_catalog()`/`ui.docker_confirm_text()`.

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
