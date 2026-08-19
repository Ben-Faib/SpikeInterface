# Newcomer-friendly menu + Docker UX - design

**Date:** 2026-06-07 · **Branch:** `multi-sorter-support` · **Status:** approved, ready for plan

Successor to `2026-06-07-multi-sorter-support-design.md`. That work added the
registry, opt-in Docker, parameter editing, and a compare picker. This work makes
the resulting menu **approachable for non-technical users** and makes Docker
**braindead-easy to turn on**, without disrupting the existing workflow.

## Motivation

The menu shipped multi-sorter support but is unfriendly to newcomers:

- The sorter sidebar lists only the **runnable** sorters (~4 locally), so a new
  user never learns the other ~18 exist or how to reach them.
- The `⊞ Docker sorters` row flips **silently**. A user who has never heard of
  Docker gets no explanation, no setup help, and - if Docker isn't installed or
  isn't running - no feedback beyond container sorters mysteriously not appearing.
- There is **no onboarding** and **two overlapping help affordances** (a
  "Data files & setup help" action + the `d` key) that only cover file placement,
  not "what is a sorter / what is Docker / what do these steps do."

**Deployment reality (important):** this tool will run on **Windows machines with
an NVIDIA GPU**, not the developer's Mac. So the design must treat **GPU sorters
as first-class** (they become runnable once installed on the target) and must be
**portable** - no Mac-specific "GPU is dead" assumptions anywhere.

**Goal:** show *all* sorters grouped by availability with per-sorter descriptions;
make Docker obvious and **guided** (detect state, open the download page, start
Docker for the user, re-check); add light onboarding (a one-time welcome + an
interactive Help that absorbs the data-setup content); keep the typed-fallback
menu at parity; and preserve the two hard contracts from v2 - **responsiveness**
(usable from a wide desktop down to a short VS Code pane) and **test/action-index
stability**.

## Scope - decisions (approved with the user)

1. **Grouped sidebar, every sorter its own row.** Show all ~22 sorters
   (`sorters.available()`) in four labelled groups: `READY TO USE`,
   `DOCKER SORTERS (heavier)`, `NEEDS A GPU`, `NOT AVAILABLE`. Group headers are
   **non-selectable**. The list is taller and scrolls.
2. **Grouping is by set-membership precedence, not the live Docker daemon.** A
   sorter's group is stable regardless of whether Docker Desktop happens to be
   running. **Selectability** (which rows can be made active) is the dynamic part,
   driven only by `sorters.runnable(use_docker)`.
3. **GPU sorters are first-class and portable.** On the Windows+GPU target, an
   installed `kilosort4` lands in `READY TO USE` and is fully runnable -
   automatically, because grouping checks `installed()` first. No code special-
   cases "GPU = unavailable." Selecting a *not-installed* GPU row shows a footer
   hint only.
4. **Unified, interactive Help.** One Help screen (topic list ↔ content pane)
   **replaces** the standalone "Data files & setup help" action; the file
   checklist becomes Help's "Data files" topic. Help is reachable three ways: the
   **Help action**, the **`?`** key (Overview), and **`d`** (jumps to Data files).
5. **Docker UX: maximum hand-holding.** Three-state detection
   (`running` / `installed_not_running` / `not_installed`); a guided confirm
   dialog that opens the Docker download page, offers **"Start Docker for me"**
   (launches Docker Desktop + polls until ready), and a Re-check button; friendly
   (non-traceback) errors; clear first-run download messaging. The **local ★
   recommended sorter is the zero-setup default** - Docker is presented as an
   optional "unlock more sorters" step, never pushed on a newcomer.
6. **Onboarding.** A `WelcomeScreen` shown **once** (persist `seen_welcome`),
   re-openable from Help. A **★ Recommended** badge on the default sorter. The
   footer shows the **highlighted** sorter's one-line plain-language description.
7. **Persistence.** `.si_menu.json` gains `seen_welcome` (bool); load/save stay
   backward-compatible (missing key → behave as first run / defaults).
8. **Typed-fallback parity.** The non-Textual menu gets text equivalents of all
   of the above.

### Non-goals

- Installing Docker Desktop for the user (the menu can open the download page and
  start an already-installed Docker, but cannot install it).
- Running GPU sorters where unsupported (e.g. on the Mac); GPU passthrough.
- N-way comparison, real Docker image pulls or real sorting inside the test suite,
  probe-geometry inference, collapsing/hiding any sorter group.

## Architecture overview

The v2 boundary is preserved: `scripts/menu_app.py` stays a **pure view**; all
data/IO lives in `MenuController` (`SpikeInterface_Menu.py`) and the registry
(`scripts/sorters.py`). Heavy SpikeInterface imports stay lazy. New shared
constants/logic (descriptions, grouping, Docker state/start, help text) live in
the **registry** and **`ui.py`**, never duplicated in the view.

| Module | Adds |
|---|---|
| `scripts/sorters.py` | `RECOMMENDED`, `DESCRIPTIONS`, `description()`, `group_of()`, `docker_state()`, `start_docker()` |
| `SpikeInterface_Menu.py` (`MenuController`) | full **catalog** over `available()`; `set_active_by_name()`, `cycle_active()`; `docker_status()`, `start_docker()`; `want_welcome` / `mark_welcome_seen()`; `seen_welcome` persistence; `_ACTIONS` data-setup→help |
| `scripts/menu_app.py` | grouped sidebar; `DockerConfirmScreen` (stateful + start/poll); `WelcomeScreen`; interactive `HelpScreen` (absorbs the data checklist); footer descriptions; **by-name** activation; `?` binding, `d` repurposed |
| `scripts/ui.py` | shared `HELP_TOPICS` text; grouped sorter printer; state-aware Docker confirm for the fallback |
| `SpikeInterface_Menu._menu_fallback` | grouped list, Docker confirm, welcome, help, descriptions, ★ |
| `scripts/run_sorting.py` | clearer first-run download message; friendly Docker-not-running error |
| `tests/` | registry/controller/Pilot tests; `conftest` `ACTIONS` + `FakeController` updates |

## Component: `scripts/sorters.py`

Add to the static-constants section (near `_PREFERRED_DEFAULT`), preserving the
lazy-import pattern:

```python
RECOMMENDED = "tridesclous2"   # the badged ★ default; matches default_sorter()

DESCRIPTIONS = {
    "tridesclous2":   "Fast, reliable, no GPU. Good default for most recordings.",
    "spykingcircus2": "Template-matching CPU sorter; strong on dense activity.",
    "mountainsort5":  "Fast density-based clustering; good general CPU sorter.",
    "herdingspikes":  "Scales to many channels; designed for large arrays.",
    "kilosort4":      "State-of-the-art; needs an NVIDIA GPU. Great on Neuropixels.",
    # ... cover local + common container + the kilosort family ...
}

def description(name: str) -> str:
    """One-line plain-language description; generic fallback for unknown sorters."""
    return DESCRIPTIONS.get(name, "A spike-sorting algorithm.")
```

**`group_of(name, installed_set=None) -> str`** - the single source of truth for
sidebar/fallback grouping. Membership precedence (so it is stable and portable):

```python
def group_of(name, installed_set=None) -> str:
    inst = installed_set if installed_set is not None else installed()
    if name in inst:            return "ready"        # installed → runnable locally
    if name in GPU_SORTERS:     return "gpu"          # needs a GPU + install
    if name in CONTAINERIZED:   return "docker"       # runnable via Docker
    return "unavailable"
```

Group label/order: `ready` → "READY TO USE", `docker` → "DOCKER SORTERS
(heavier)", `gpu` → "NEEDS A GPU", `unavailable` → "NOT AVAILABLE".

**`docker_state(refresh=False) -> str`** - three-way, replacing the binary as the
detail source (`docker_available()` is kept, re-expressed as
`docker_state() == "running"`, so existing callers are untouched):

```python
def docker_state(refresh=False) -> str:
    """'running' | 'installed_not_running' | 'not_installed'. Never raises."""
    # cached in _docker_cache["state"]; refresh re-probes
    if not shutil.which("docker"):
        return "not_installed"
    try:
        ok = subprocess.run(["docker", "info"], capture_output=True, timeout=8).returncode == 0
    except Exception:
        ok = False
    return "running" if ok else "installed_not_running"
```

**`start_docker() -> bool`** - best-effort launch of Docker Desktop; never raises;
returns whether a launch command was issued (not whether Docker finished booting -
the caller polls `docker_state(refresh=True)`):

```python
def start_docker() -> bool:
    import sys
    if sys.platform == "darwin":
        cmd = ["open", "-a", "Docker"]
    elif sys.platform.startswith("win"):
        cmd = ["cmd", "/c", "start", "", "Docker Desktop.exe"]   # falls back via PATH/known path
    else:
        cmd = ["systemctl", "--user", "start", "docker-desktop"] # best-effort on Linux
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
```

`status()`, `runnable()`, `run()` are unchanged - `run()` already raises a
readable `RuntimeError` when Docker is requested but unreachable, which the run
path now surfaces verbatim.

## Component: `MenuController` (`SpikeInterface_Menu.py`)

**Catalog.** `reload()` builds `self.infos` over **all** sorters
(`sorters.available()`), computing `installed_set` and Docker state **once** and
passing them down. Each entry:

```python
{ "name", "group",          # group_of(name, installed_set)
  "status",                 # local/docker/gpu/unavailable (dynamic; for glyph/dim)
  "runnable",               # name in runnable(use_docker)  → selectable
  "recommended",            # name == sorters.RECOMMENDED
  "description",            # sorters.description(name)
  "present", "units", "duration",  # best-effort saved-sort probe (dir-exists → guarded read)
  "active" }
```

The saved-sort probe is **lazy and cheap**: it short-circuits when a sorter has no
`outputs/<sorter>/analyzer` directory (the common case), and reads `unit_ids` /
duration guarded only when one exists. Never raises.

**Activation by name** (the list now contains non-selectable rows, so index math
is fragile):

```python
def set_active_by_name(self, name: str) -> bool:
    """Activate a runnable sorter by id. Returns False if not runnable (caller hints)."""
def cycle_active(self) -> None:
    """`t` key: advance to the next *runnable* sorter, skipping non-runnable rows."""
```

`active_idx` is kept as derived state - the index into `self.infos` of the active
(always runnable) entry - so the footer and existing tests keep working.
`set_active(idx)` remains (guards runnable).

**Docker.**

```python
def docker_status(self, refresh=False) -> dict:
    """{state, running: bool, text: str} for the confirm dialog (plain language)."""
def start_docker(self) -> bool:        # passthrough to sorters.start_docker()
```

`toggle_docker()` is unchanged (flip, persist, rebuild runnable list, reload).

**Welcome.** `self.want_welcome = not self.cfg.get("seen_welcome", False)` (fresh
config → first run → show). `mark_welcome_seen()` sets `cfg["seen_welcome"]=True`,
persists, clears `want_welcome`.

**`_ACTIONS`.** Replace the data-setup row **in place at index 9** so indices 0–8
and `quit` (10) are unchanged and every number-key test still passes:

```python
# was: ("data-setup", "Data files & setup help", "what's expected and where it goes", False),
("help", "Help", "what each step does · sorters · Docker · data files", False),
```

## Component: `scripts/menu_app.py`

**Sidebar.** `_rebuild_sorters()` emits: the Docker toggle row (id `__docker__`,
bold `● ON` / `○ OFF` + a dim "heavier - downloads images, runs slower" caption),
then for each **non-empty** group **in order**: a **disabled** header `Option`
(`disabled=True`, id `__grp_<group>__`) followed by its sorter rows. Empty groups
are **omitted** (no header) to protect vertical space on short terminals - a
deliberate departure from the literal "NOT AVAILABLE (none on this machine)"
placeholder in the approved mockup. Row text
(compact for the 36-col sidebar): `★` if recommended, `●/○` active, group glyph
(`◇` docker, `·` gpu/unavailable, none for ready), name, `Nu` / `-`, `ACTIVE`
tag; **dim** when not runnable. The active (runnable) sorter is highlighted by
default so useful rows are in view. (If Textual's `OptionList` does not skip
disabled options during cursor movement, the highlight handler advances past
them.)

**Activation.** `on_option_list_option_selected` reads `event.option.id`:
`__docker__` → Docker toggle flow; `__grp_*` → ignored; otherwise a sorter name →
if `runnable`, `controller.set_active_by_name(name)`; else a footer hint -
**docker-group + Docker off → offer the enable dialog**; gpu → "needs a GPU build
installed (see Help)"; unavailable → "not available on this computer."

**Footer.** `on_option_list_option_highlighted` for `#sorters` shows that
sorter's `description`, alongside the active-sorter summary line.

**`DockerConfirmScreen` (stateful).** On mount reads `controller.docker_status()`
and renders per state:

- **running** → "✓ Docker is running" · `[ Enable ] [ Cancel ]`
- **installed_not_running** → "✗ Docker is installed but not started" ·
  `[ Start Docker for me ] [ Re-check ] [ Cancel ]`
- **not_installed** → "You don't have Docker yet - it's a free app that unlocks
  extra sorters" · `[ Open download page ] [ Re-check ] [ Cancel ]`

Buttons: **Open download page** → `webbrowser.open(<docker desktop url>)`;
**Start Docker for me** → `controller.start_docker()`, then show
"Starting Docker… (~30–60s)" and **poll** `docker_status(refresh=True)` on a timer
until `running` (auto-advance to the running view) or a ~90s timeout (fall back to
"open Docker Desktop manually, then Re-check"); **Re-check** → re-probe + re-render.
**Enable** is always allowed even if not running (mode flips on; container sorters
appear once Docker is up). `dismiss("enable"|None)`; the app calls
`toggle_docker()` on `"enable"`. Turning Docker **off** is immediate (no dialog).
The dialog has a max width and scrolls so it fits small windows.

**`WelcomeScreen`.** Pushed on app mount when `controller.want_welcome`; the
3-steps copy from the handoff; dismiss → `controller.mark_welcome_seen()`.

**Interactive `HelpScreen`.** Two-pane (topic list ↔ scrollable content), stacking
on narrow terminals. Topics: **Overview** (the welcome text), **The 3 steps**
(Explore / Sort / Report), **Sorters explained**, **Docker**, **Data files** (the
present/missing checklist, rendered from `data_report` - this absorbs the old
`DataSetupScreen`), **Keyboard**. Highlighting a topic updates the content;
`Esc`/`q` closes. Topic text comes from a shared `ui.HELP_TOPICS` so the fallback
reuses it. Opens at **Overview** by default, **Data files** when launched via `d`.

**Bindings.** Add `?` → open Help (Overview). Repurpose existing `d` → open Help
(Data files). All other keys unchanged (`t`, `q`, `esc`, `ctrl+c`, arrows, `j/k`,
`space`, `1`–`9`). `?` is the only genuinely new global key (universal).

## Component: typed fallback (`_menu_fallback` + `ui.py`)

- `ui.HELP_TOPICS`: the single source of help text (shared with the Textual Help).
- `ui` gains a grouped sorter printer (group labels + status + `★` + one-line
  description) and a **state-aware Docker confirm** for text mode: prints the
  three-state status and offers, per state, "open download page? [y/N]"
  (`webbrowser.open`), "start Docker for me? [y/N]" (`start_docker()` + a short
  poll), and a Re-check loop - mirroring the dialog.
- `_menu_fallback`: replace the data-setup action with **help** (prints
  `HELP_TOPICS`, selectable topics via `ui.select`); group the sorter listing;
  route the Docker toggle through the text confirm; show a **first-run welcome
  blurb**; badge the recommended sorter; show descriptions. Uses the same
  `sorters.group_of`.

## Component: `scripts/run_sorting.py` (messaging + friendly errors)

- First-run Docker message → "Downloading the `<sorter>` image (~1 GB, one time
  only - later sorts skip this)," with pull progress streaming (verbose).
- Wrap `sorters.run(...)`: on the Docker-unreachable `RuntimeError`, print the
  plain "Docker isn't running - open Docker Desktop and try again" and exit
  non-zero, so `MenuController.run()` returns it as a friendly footer message
  rather than a traceback.

## Testing

Hermetic throughout - monkeypatch `installed`/`available`/`docker_available`/
`docker_state`/`default_params`; no real Docker pulls, no real sorting; drive the
app with `FakeController`.

**Registry** (`test_sorters.py`): `description()` fallback; `RECOMMENDED ==
default_sorter()` when installed; `group_of()` precedence - installed→ready,
installed-GPU→ready, not-installed-GPU→gpu, container→docker, else unavailable;
`docker_state()` three states (mock `shutil.which` + `subprocess.run`);
`start_docker()` issues the platform command and never raises.

**Controller** (`test_menu_controller.py`): catalog built over `available()` with
correct group/runnable/recommended/description per entry; `set_active_by_name`
returns False and does not change the active sorter for a non-runnable name;
`cycle_active` skips non-runnable; `docker_status` text per state; `want_welcome`
derives from `seen_welcome`; `mark_welcome_seen` persists.

**Pilot** (`test_menu_app.py`): group headers present, disabled, and not
activatable; a non-runnable row does not change `active_idx` (shows a footer hint);
`★` badge on the recommended row; footer shows the **highlighted** sorter's
description; Docker toggle-on pushes `DockerConfirmScreen`; the dialog renders each
state from `FakeController.docker_status`, the **Start Docker** button calls
`controller.start_docker()` and the poll advances to "running" when the fake flips
state; `WelcomeScreen` shows when `want_welcome` and not when `seen_welcome`; Help
opens via `?`, the Help action, and `d` (Data files topic) and lists topics + the
file checklist. **Update** the former `test_data_setup_screen_lists_files` to
assert the Help Data-files topic.

**Index/size contracts:** number-key tests (`1`=explore, `2`=sort, `6`=compare,
`7`=params, `8`=verify) keep passing unchanged (help replaced data-setup at index
9, shifting nothing in 0–8). Re-assert the size-critical tests - `(110,40)`,
`(77,24)`, `(40,12)`, `(30,6)`, and the stacked/short sweep - that actions and
sorters are never fully clipped with the new header rows + toggle caption.

**`conftest.py`:** update `ACTIONS` (help at index 9). Extend `FakeController`
with a catalog-shaped `infos` over a small fake universe spanning all four groups,
plus `set_active_by_name`, `cycle_active`, `docker_status` (settable state),
`start_docker`, `want_welcome` (**default False** so existing boot tests see no
modal), and `mark_welcome_seen`.

## Error handling

- `docker_state`, `docker_available`, `start_docker` never raise (subprocess
  guarded); the Start-Docker poll has a timeout and degrades to manual
  instructions.
- A Docker sort that fails because Docker isn't reachable surfaces as a friendly
  message, never a traceback.
- `WelcomeScreen`/`HelpScreen` guard a missing/partial `data_report`.
- Config load/save is backward-compatible: a missing `seen_welcome` behaves as
  first run; a corrupt file falls back to defaults (existing behaviour).

## Docs

- Update `CLAUDE.md`: grouped sidebar (all sorters, four groups, membership
  precedence), the guided Docker UX (three states + Start-Docker + open-download),
  the unified interactive Help + one-time Welcome, per-sorter descriptions, the new
  `?` key and repurposed `d`, and the `seen_welcome` config key.
- The handoff `docs/handoff-newcomer-friendly-menu.md` can be marked done.
