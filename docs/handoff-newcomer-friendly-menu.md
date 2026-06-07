# Handoff — Newcomer-friendly menu + Docker UX

**For:** a fresh Claude Code session that will **design and build** this update.
**Repo:** `/Users/benfaib/Spike/SpikeInterface` · **Branch:** `multi-sorter-support`
**Date written:** 2026-06-07 · **Env:** `uv` (Python 3.12). Run everything with `uv run …`.

---

## 0. How to use this handoff

You are picking up mid-project with no prior conversation. This document is
self-contained: it tells you what the project is, what already shipped, exactly
what to build next (the decisions are already made with the user), and the
conventions/gotchas you must respect.

**Your job:** turn §3 into a written spec + implementation plan, then build it.
The design decisions in §3 were agreed with the user in a prior session — treat
them as approved, but briefly re-confirm before writing code if anything is
ambiguous. Recommended process (the project uses the `superpowers` skills and
"ultracode" workflow orchestration):

1. `superpowers:brainstorming` is effectively **done** (decisions in §3). You may
   skip straight to writing the spec, or do a quick confirm pass.
2. `superpowers:writing-plans` → a task-by-task plan in
   `docs/superpowers/plans/`.
3. Build it with the **Workflow** tool (multi-agent), then run the full test
   suite and commit. (The prior update was built this way; see §2.)

**First commands to orient yourself:**
```bash
uv run python -m pytest tests/ -q            # should be all green (66 passed as of handoff)
uv run python SpikeInterface_Menu.py         # the interactive menu you are improving
uv run python scripts/run_sorting.py --list-sorters
```

---

## 1. Project orientation

A small SpikeInterface workspace for analysing **one** Blackrock/Ripple recording
(`PFCM7_d0ephys_Block2.{ns2,ns5,nev}`, git-ignored, sits in the repo root). No
package, no build step — loader code + thin scripts + a Textual menu. See
`CLAUDE.md` for the authoritative project guide; read it before coding.

**Key files for this work:**

| File | Responsibility |
|---|---|
| `SpikeInterface_Menu.py` (repo root) | Front-door launcher + `MenuController` (the bridge the Textual app calls into). Holds dashboard state, runs actions, persists `.si_menu.json`. Also has a **typed/prompt_toolkit fallback** menu (`_menu_fallback`) for when Textual is absent/off-TTY. |
| `scripts/menu_app.py` | The **Textual app** (`SpikeMenuApp`) — terminal UI v2: responsive two-pane dashboard (Sorter sidebar + Actions list), modal screens, shield art. This is where most of the new UI lives. It is a **pure view**: all data/logic comes from the controller via a `Controller` Protocol. |
| `scripts/sorters.py` | **Sorter registry** — single source of truth for discovery/availability/params/running. `available()`, `installed()`, `docker_available()`, `status(name)`→`local`/`docker`/`gpu`/`unavailable`, `runnable(use_docker)`, `default_sorter()`, `default_params`/`param_descriptions`/`coerce_param`/`merge_params`, `run(...)`, `status_table()`. Constants `GPU_SORTERS`, `CONTAINERIZED`. Lazy SpikeInterface imports. |
| `scripts/ui.py` | Shared rich styling + the Pitt shield art + theme palette + the prompt_toolkit `select()`/`dashboard_menu()` used by the fallback. |
| `scripts/compare.py`, `scripts/run_sorting.py`, `scripts/verify_install.py` | Compare HTML, the sorting CLI, the install smoke test. All consume `sorters.py`. |
| `tests/conftest.py` | `FakeController` test double (mirrors `MenuController`) + an `ACTIONS` table mirroring `SpikeInterface_Menu._ACTIONS`. **Index-sensitive** — see §4. |
| `tests/test_menu_app.py` | Textual **Pilot** tests for the app. |
| `tests/test_sorters.py`, `test_run_sorting.py`, `test_compare.py`, `test_menu_controller.py`, `test_data_report.py` | Unit tests (hermetic — no real SpikeInterface sort, no Docker). |

**Run / test:**
```bash
uv run python SpikeInterface_Menu.py            # interactive menu (or: report|sort|gui|traces|compare|verify)
uv run python -m pytest tests/ -q               # the menu + registry test suite
uv run python -m pytest tests/test_menu_app.py -q
```

---

## 2. What already shipped (context — do NOT rebuild)

This branch already added **multi-sorter support** (registry + opt-in Docker +
per-sorter parameter editing + a compare picker). Specs/plans:
- `docs/superpowers/specs/2026-06-07-multi-sorter-support-design.md`
- `docs/superpowers/plans/2026-06-07-multi-sorter-support.md`

It was built with a multi-agent **Workflow** and is committed as:
```
7d3ff9b feat: multi-sorter support — registry, opt-in Docker, parameter editing
ece0085 feat: drop non-neural analog channels, sort provenance + report auto-pick   (pre-existing concurrent work, kept separate)
```
All 66 tests pass. **What exists today in the menu:**
- Sorter sidebar lists only the **runnable** sorters (local; + container sorters
  when Docker mode is on). A `⊞ Docker sorters: off/on` toggle row sits at the top
  of the sidebar (Enter flips it, no confirmation yet).
- An **"Edit sorter parameters"** Action opens a Param Editor modal (scalars
  inline, bool checkbox, dict/None as JSON; Ctrl+S saves only changed keys).
- **Compare** opens a two-step picker to choose which saved sorts to compare.
- `.si_menu.json` persists `theme`, `use_docker`, `sorter_params` (param overrides
  are stored as **diffs** from defaults).

**The problem this update fixes:** the menu is not friendly to non-technical
users. A newcomer sees only ~4 sorters (doesn't know 18 others exist), the Docker
toggle flips silently with no indication it's heavier, and there's no onboarding.

---

## 3. The update to build: newcomer-friendly menu + Docker UX

**Goal:** make the Textual menu approachable for new / non-technical users — show
*all* sorters grouped by availability, make Docker mode obvious and safe to turn
on (it's heavier), and add light onboarding — without disrupting the existing
workflow. Keep full parity in the typed fallback menu.

### Approved decisions (from the prior brainstorming session)

**3.1 Grouped sorter sidebar (show ALL sorters, with more room).**
Replace "list only runnable sorters" with every sorter (`sorters.available()`),
in labelled groups, and give the list more vertical height. Approved layout:

```
SORTER
 ⊞ Docker sorters:   ● ON
 ─────────────────────────────
 READY TO USE
  ★ ● tridesclous2        12u      ← ★ = recommended, ● = active
  ○ spykingcircus2         7u
  ○ lupin                   —
  ○ simple                  —
 DOCKER SORTERS (heavier)
  ◇ mountainsort5           —       ← ◇ = runs via Docker; selectable when Docker ON,
  ◇ herdingspikes           —          dimmed + "turn Docker on above" hint when OFF
  ◇ spykingcircus           —
  ◇ waveclus                —
 NEEDS A GPU (unavailable here)
  · kilosort4                        ← dimmed, not selectable
  · kilosort3
 NOT AVAILABLE
  · <any status == "unavailable">    ← dimmed (no image / unknown), not selectable
```
- Group headers are **non-selectable** rows (use disabled `OptionList` options).
- Only **runnable** sorters can be made active. Selecting a dimmed **Docker**
  sorter (Docker off) **offers to enable Docker** (opens the dialog in 3.2).
  Selecting a GPU/unavailable one shows a plain footer hint ("needs a GPU" / "not
  available on this computer").
- Group sources: `READY TO USE` = `status=="local"`; `DOCKER SORTERS` =
  `status in CONTAINERIZED` (i.e. would be `docker` when on); `NEEDS A GPU` =
  `status=="gpu"`; `NOT AVAILABLE` = `status=="unavailable"` and not a container
  image. Keep the existing per-sorter saved-sort summary (`Nu`) where present.

**3.2 Docker toggle + explain-and-confirm dialog.**
- Toggle row: bold, unmistakable state **`⊞ Docker sorters:  ● ON`** /
  **`○ OFF`**, plus a dim caption line: *"heavier — downloads images, runs slower"*.
- Turning **ON** opens a `DockerConfirmScreen` modal (plain language), with a
  **live Docker status check**, then Enable/Cancel. Turning **OFF** is immediate.
  Approved copy:
```
┌ Enable Docker sorters? ───────────┐
│ These run extra sorters your       │
│ computer doesn't have installed.   │
│                                    │
│ • First run downloads a large      │
│   image (~1 GB) and is slower.     │
│ • Needs Docker Desktop running.    │
│   Status: ✓ Docker is running      │   ← or "✗ Docker not detected — start Docker Desktop"
│                                    │
│   [ Enable ]      [ Cancel ]       │
└────────────────────────────────────┘
```
- If Docker is **not** detected, still allow Enable (mode flips on), but note the
  container sorters will only appear once Docker is running. Persist `use_docker`.

**3.3 Onboarding & guidance.**
- **WelcomeScreen** on first launch only (persist `seen_welcome` in
  `.si_menu.json`; also re-openable from Help). Approved copy:
```
┌ Welcome to the Spike Sorter ────────┐
│ This finds neurons in your          │
│ recording, in 3 steps:              │
│   1. Explore  - see your data       │
│   2. Sort     - detect neurons      │
│   3. Report   - view results        │
│ Put your recording files in this    │
│ folder (press d for help).          │
│        [ Get started ]              │
└─────────────────────────────────────┘
```
- **Highlighted-sorter description** in the footer: when the cursor moves over a
  sorter row, show its one-line plain-language description (e.g. "tridesclous2 —
  fast, reliable, no GPU. Good default for most recordings.").
- **★ Recommended** badge on the default sorter.
- **Help**: a **"Help" Action** *and* the `?` key open a plain-English HelpScreen
  (what each step does; what sorters / Docker are). `?` is the only new global key
  (universal convention; see the key-binding rule in §4).

**3.4 Registry additions (`scripts/sorters.py`).**
- `DESCRIPTIONS: dict[str,str]` — one-line description per sorter; `description(name)`
  returns it or a generic fallback. Cover at least the local + common container +
  kilosort family; generic fallback for the rest.
- `RECOMMENDED = "tridesclous2"` (keep consistent with `default_sorter()`).

**3.5 Typed fallback parity (`SpikeInterface_Menu._menu_fallback` + `ui.py`).**
Text-mode equivalents: grouped sorter list with status labels; Docker ON/OFF +
"heavier" note + a yes/no confirm that prints the same explanation; recommended
marker; descriptions; a first-run welcome blurb; a Help entry. No Textual needed.

**3.6 Controller, tests, docs.**
- `MenuController` serves the grouped **catalog** (ALL sorters: name, status,
  runnable, present, units, duration, active, recommended, description, group),
  a `docker_status()` for the dialog, welcome/`seen_welcome` state, and
  **activate-by-name** (since the list now contains non-selectable rows, index
  math is fragile — select by sorter id).
- Tests: registry (`description` fallback, `RECOMMENDED`); Pilot tests (group
  headers present + disabled; non-runnable rows disabled; Docker confirm dialog on
  enable; welcome shows once / not when `seen_welcome`; footer shows highlighted
  description; ★ badge; Help screen via `?` and Action). Extend `conftest.FakeController`.
- Update `CLAUDE.md`.

### Defaults assumed (confirm with the user if unsure)
- Recommended sorter = **tridesclous2**.
- Welcome shows **once**, then lives under Help.
- Clicking a disabled **Docker** sorter **offers to enable Docker**; clicking a
  GPU/unavailable one shows a footer hint only.

### Acceptance criteria
- The sidebar shows all ~22 sorters in the four groups; group headers and
  non-runnable rows are not activatable; the list scrolls and stays usable at
  small window sizes (the v2 responsiveness contract — see §4).
- Docker toggle state is unmistakable; enabling it always goes through the
  confirm dialog with a live Docker status line; choice persists.
- First launch shows the welcome once; `?`/Help opens help; the footer shows the
  highlighted sorter's description; the recommended sorter is badged.
- Typed fallback has parity. `uv run python -m pytest tests/ -q` is fully green.

---

## 4. Conventions & gotchas (read before coding)

- **Terminal UI v2 architecture.** `menu_app.py` is a pure **view**; never put
  data/IO there — extend the `Controller` Protocol and `MenuController`. The app
  must stay **import-light** (no SpikeInterface at import time) so tests run with
  Textual's `run_test`/Pilot harness and a `FakeController`.
- **Responsiveness is a hard requirement.** The dashboard must stay usable from a
  wide desktop down to a short VS Code pane (`NARROW_COLS≈78` stacks the panes;
  the shield collapses full→compact→mini→hidden; both lists scroll). Existing
  Pilot tests assert "Actions never pushed off-screen" at tiny sizes — your new
  rows/sections must not break that. Test at sizes like (110,40), (77,24),
  (40,12), (30,6).
- **Test/action-index coupling.** `tests/conftest.py` has an `ACTIONS` table that
  must mirror `SpikeInterface_Menu._ACTIONS` (order + `needs_data`), and several
  Pilot tests press number keys (1–9) mapping to action indices. If you add a
  "Help" action, update **both** tables and any index-based test. (`params` action
  is at index 6 today; `verify` at 7, etc.)
- **Key-binding philosophy (learned the hard way).** The user dislikes awkward
  new global letter hotkeys. The established pattern: **new capabilities are
  Actions** in the right list (params, help), **Docker is a row in the Sorter
  sidebar** (not a hotkey). `?` for Help is acceptable (universal). Don't add a
  letter that clashes with existing ones (`t` cycle sorter, `d` data help, `q`
  quit, `j/k` nav, arrows, 1–9 jump).
- **Hermetic tests.** No real Docker pulls, no real sorting in the suite — stub
  `installed()`/`docker_available()`/`default_params()` etc. via monkeypatch (see
  `tests/test_sorters.py`) and drive the app with `FakeController`.
- **`.si_menu.json`** (git-ignored, repo root) is the persisted config. Current
  keys: `theme`, `use_docker`, `sorter_params`. Add `seen_welcome` (bool) for the
  welcome screen. Keep load/save backward-compatible (missing → default).
- **`scripts/sorters.py` is the single source of truth** for anything sorter-
  related. Put `DESCRIPTIONS`/`RECOMMENDED`/`description()` there, not in the UI.
- **Lazy SpikeInterface imports** everywhere (inside functions). Importing
  `sorters`/`menu_app` must not pull in SpikeInterface.
- **Concurrent editing / committing.** The user often edits this repo from another
  session at the same time, so the working tree can change mid-session even if it
  looked clean at start. **Before committing, re-check `git status`/`git diff`**;
  if you find unrelated changes you didn't make, ask — the user's preference is to
  keep their unrelated work in a **separate commit** (theirs first, your feature on
  top), reconstructing per-file content if it's interleaved. End your own commit
  messages with the `Co-Authored-By: Claude …` trailer; do **not** add it to a
  commit that is purely the user's pre-existing work. Branch off `main` if you're
  on it; commit only when the work is verified.
- **Run with `uv run`** (Python 3.12). Textual + rich + prompt_toolkit are
  installed. The Qt GUIs (`sigui`, ephyviewer) are blocking and launched in child
  processes — not relevant to this UI work.

---

## 5. Suggested task breakdown (for your plan)

1. `sorters.py`: add `DESCRIPTIONS`, `RECOMMENDED`, `description()` (+ unit tests).
2. `MenuController` + `_data_report`/dashboard loaders: build the grouped **catalog**
   over `available()` with status/runnable/recommended/description/group;
   activate-by-name; `docker_status()`; `seen_welcome` load/save (+ controller tests).
3. `menu_app.py`: grouped sidebar with headers + dimmed non-runnable rows + ★ +
   `◇`; taller sorter pane; footer highlighted-description; keep responsiveness.
4. `menu_app.py`: `DockerConfirmScreen` (live status) wired to the toggle; bold
   ON/OFF + heavier caption.
5. `menu_app.py`: `WelcomeScreen` (first-run via `seen_welcome`) + `HelpScreen`
   (`?` key + "Help" Action; update `_ACTIONS` + conftest `ACTIONS` + index tests).
6. Typed fallback parity in `SpikeInterface_Menu._menu_fallback` / `ui.py`.
7. Pilot + unit tests for all of the above; full suite green.
8. Update `CLAUDE.md`; update `docs/HANDOFF`/changelog if desired.

Build steps 1–7 with a Workflow (fan out by file, disjoint files, verify phase
runs the full suite), then commit. Keep each agent to disjoint files and have a
final agent run `uv run python -m pytest tests/ -q`.

---

## 6. Pointers

- Authoritative project guide: `CLAUDE.md` (read the "Architecture" and
  "Sorting status & the probe gap" sections).
- Prior update spec/plan: `docs/superpowers/specs/2026-06-07-multi-sorter-support-design.md`,
  `docs/superpowers/plans/2026-06-07-multi-sorter-support.md`.
- The Textual app to extend: `scripts/menu_app.py` (see `SpikeMenuApp`,
  `ChoiceModal`, `DataSetupScreen`, `ParamEditorScreen` for modal patterns;
  `_rebuild_sorters`, `_sorter_text`, `_refresh_footer` for the sidebar/footer).
- The registry: `scripts/sorters.py`.
