# Newcomer-friendly menu + guided Docker UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Textual menu approachable for non-technical users — show *all* sorters grouped by availability with plain-language descriptions, make Docker braindead-easy to enable (detect state, open the download page, start Docker for them, re-check), add a one-time welcome + unified interactive Help — while keeping the typed-fallback at parity and not breaking the v2 responsiveness/index contracts.

**Architecture:** `scripts/menu_app.py` stays a pure **view**; all data/IO lives in `MenuController` (`SpikeInterface_Menu.py`) and the registry (`scripts/sorters.py`). New shared logic (descriptions, grouping, Docker state/start, help text) lives in the registry and `ui.py`. The sorter sidebar becomes a grouped list over the full catalog (all sorters), activation moves to **by-name** (the list now has non-selectable header rows), and three new modal screens (`DockerConfirmScreen`, `WelcomeScreen`, `HelpScreen`) follow the existing `ModalScreen` + `push_screen(modal, callback)` + `dismiss(result)` pattern.

**Tech Stack:** Python 3.12, Textual (Pilot tests), rich, prompt_toolkit (fallback), pytest + pytest-asyncio. Run everything with `uv run`.

**Spec:** `docs/superpowers/specs/2026-06-07-newcomer-friendly-menu-design.md`

---

## File Structure

| File | Change |
|---|---|
| `scripts/sorters.py` | + `RECOMMENDED`, `DESCRIPTIONS`, `description()`, `group_of()`, `docker_state()`, `start_docker()`; `docker_available()` re-expressed via `docker_state()` |
| `SpikeInterface_Menu.py` | + `_saved_summary()`, `_catalog()`; `MenuController.reload`/activation reworked to a catalog; + `set_active_by_name`, `cycle_active`, `docker_status`, `start_docker`, `want_welcome`, `mark_welcome_seen`; `_ACTIONS` data-setup→help; `_menu_fallback` parity |
| `scripts/menu_app.py` | grouped sidebar; by-name activation; footer description; `DockerConfirmScreen`, `WelcomeScreen`, `HelpScreen`; `?` binding, `d` repurposed |
| `scripts/ui.py` | + `HELP_TOPICS`, `print_catalog()`, `docker_confirm_text()` (fallback helpers) |
| `scripts/run_sorting.py` | clearer first-run Docker message; friendly Docker-not-running error |
| `tests/conftest.py` | `ACTIONS` (help at idx 9); `FakeController` reshaped to a catalog + new methods |
| `tests/test_sorters.py` | tests for descriptions/RECOMMENDED/group_of/docker_state/start_docker |
| `tests/test_menu_controller.py` | tests for catalog/by-name/cycle/docker_status/welcome |
| `tests/test_menu_app.py` | rewrite index-sensitive sorter tests; add dialog/welcome/help tests |
| `CLAUDE.md` | document the new UX |

**Conventions (from the spec + CLAUDE.md):**
- Lazy SpikeInterface imports everywhere (inside functions). Importing `sorters`/`menu_app` must not import SpikeInterface.
- Hermetic tests: monkeypatch `installed`/`available`/`docker_available`/`docker_state`/`default_params`; no real Docker, no real sort. Drive the app with `FakeController`.
- `.si_menu.json` load/save stays backward-compatible (missing key → default).
- Before committing, re-check `git status`/`git diff`; if you find unrelated changes you didn't make, keep the user's work in a separate commit (theirs first). End your commits with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

**Orientation command (run once before starting):**
```bash
uv run python -m pytest tests/ -q     # baseline: should be all green
```

---

## Task 1: Registry — descriptions + recommended

**Files:**
- Modify: `scripts/sorters.py` (constants section, after `_PREFERRED_DEFAULT` at line 43)
- Test: `tests/test_sorters.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sorters.py`:

```python
def test_recommended_is_the_preferred_default():
    # The badged ★ sorter must match what default_sorter() prefers.
    assert sorters.RECOMMENDED == "tridesclous2"


def test_description_known_and_fallback():
    assert "GPU" not in sorters.description("tridesclous2")  # local sorter, no GPU mention
    assert sorters.description("tridesclous2")               # non-empty
    # an unknown sorter gets the generic fallback, never a KeyError
    assert sorters.description("totally_made_up_sorter") == "A spike-sorting algorithm."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_sorters.py::test_recommended_is_the_preferred_default tests/test_sorters.py::test_description_known_and_fallback -q`
Expected: FAIL with `AttributeError: module 'sorters' has no attribute 'RECOMMENDED'` / `description`.

- [ ] **Step 3: Add the constants + function**

In `scripts/sorters.py`, immediately after line 43 (`_PREFERRED_DEFAULT = "tridesclous2"`), insert:

```python
# The badged ★ default in the menu. Keep consistent with default_sorter().
RECOMMENDED = "tridesclous2"

# One-line, plain-language descriptions shown in the sidebar footer + Help. Covers
# the local sorters, the common container sorters, and the kilosort family; any
# other sorter gets the generic fallback in description().
DESCRIPTIONS = {
    "tridesclous2":   "Fast, reliable, no GPU. Good default for most recordings.",
    "spykingcircus2": "Template-matching CPU sorter; strong on dense activity.",
    "simple":         "Minimal threshold-based sorter; handy for a quick smoke test.",
    "lupin":          "Lightweight CPU sorter.",
    "mountainsort5":  "Fast density-based clustering; a solid general CPU sorter.",
    "mountainsort4":  "Older MountainSort; superseded by mountainsort5.",
    "herdingspikes":  "Scales to many channels; built for large dense arrays.",
    "spykingcircus":  "Original SpyKING CIRCUS (v1); CPU, template matching.",
    "tridesclous":    "Original Tridesclous (v1); CPU.",
    "waveclus":       "Wavelet + superparamagnetic clustering (MATLAB-based image).",
    "combinato":      "Clustering aimed at human single-unit / long recordings.",
    "hdsort":         "Dense-array sorter (MATLAB-based image).",
    "ironclust":      "Fast density-based sorter (CPU or GPU).",
    "kilosort4":      "State-of-the-art; needs an NVIDIA GPU. Great on Neuropixels.",
    "kilosort3":      "Kilosort 3; needs an NVIDIA GPU.",
    "kilosort2_5":    "Kilosort 2.5; needs an NVIDIA GPU.",
    "kilosort2":      "Kilosort 2; needs an NVIDIA GPU.",
    "kilosort":       "Kilosort 1; needs an NVIDIA GPU + MATLAB.",
    "pykilosort":     "Python Kilosort; needs an NVIDIA GPU.",
    "yass":           "Yet Another Spike Sorter; needs an NVIDIA GPU.",
}


def description(name: str) -> str:
    """One-line plain-language description; generic fallback for unknown sorters."""
    return DESCRIPTIONS.get(name, "A spike-sorting algorithm.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_sorters.py -q`
Expected: PASS (all sorter tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/sorters.py tests/test_sorters.py
git commit -m "feat(sorters): add RECOMMENDED + per-sorter DESCRIPTIONS/description()

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Registry — group_of()

**Files:**
- Modify: `scripts/sorters.py` (after `status()`, ~line 98)
- Test: `tests/test_sorters.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sorters.py`:

```python
def test_group_of_membership_precedence(monkeypatch):
    inst = {"tridesclous2", "kilosort4"}   # note: kilosort4 installed -> READY, not GPU
    monkeypatch.setattr(sorters, "installed", lambda: sorted(inst))
    g = lambda n: sorters.group_of(n, installed_set=inst)
    assert g("tridesclous2") == "ready"      # installed
    assert g("kilosort4") == "ready"         # installed beats GPU membership (Windows+GPU target)
    assert g("kilosort3") == "gpu"           # GPU family, not installed
    assert g("mountainsort5") == "docker"    # containerized, not installed
    assert g("totally_made_up_sorter") == "unavailable"


def test_group_of_uses_live_installed_when_omitted(monkeypatch):
    monkeypatch.setattr(sorters, "installed", lambda: ["tridesclous2"])
    assert sorters.group_of("tridesclous2") == "ready"
    assert sorters.group_of("mountainsort5") == "docker"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_sorters.py::test_group_of_membership_precedence -q`
Expected: FAIL with `AttributeError: module 'sorters' has no attribute 'group_of'`.

- [ ] **Step 3: Add `group_of()`**

In `scripts/sorters.py`, immediately after the `status()` function (after line 97), insert:

```python
def group_of(name: str, installed_set=None) -> str:
    """Stable sidebar group for ``name`` by set-membership precedence.

    'ready' (installed → runnable locally) | 'gpu' (NVIDIA GPU family, not
    installed) | 'docker' (has a CPU container image) | 'unavailable'. Unlike
    status(), this does NOT depend on the live Docker daemon, so a sorter never
    jumps groups when Docker Desktop starts/stops — only its *selectability*
    (runnable()) does. Installed wins first, so an installed kilosort on a GPU box
    lands in 'ready'.
    """
    inst = installed_set if installed_set is not None else installed()
    if name in inst:
        return "ready"
    if name in GPU_SORTERS:
        return "gpu"
    if name in CONTAINERIZED:
        return "docker"
    return "unavailable"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_sorters.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/sorters.py tests/test_sorters.py
git commit -m "feat(sorters): add group_of() membership-precedence grouping

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Registry — docker_state() + start_docker()

**Files:**
- Modify: `scripts/sorters.py` (`docker_available()` at lines 62-79)
- Test: `tests/test_sorters.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sorters.py`:

```python
import subprocess as _subprocess


class _Ret:
    def __init__(self, rc):
        self.returncode = rc


def test_docker_state_not_installed(monkeypatch):
    sorters._docker_cache.clear()
    monkeypatch.setattr(sorters.shutil, "which", lambda _n: None)
    assert sorters.docker_state(refresh=True) == "not_installed"
    assert sorters.docker_available(refresh=True) is False


def test_docker_state_installed_not_running(monkeypatch):
    sorters._docker_cache.clear()
    monkeypatch.setattr(sorters.shutil, "which", lambda _n: "/usr/bin/docker")
    monkeypatch.setattr(sorters.subprocess, "run", lambda *a, **k: _Ret(1))
    assert sorters.docker_state(refresh=True) == "installed_not_running"
    assert sorters.docker_available(refresh=True) is False


def test_docker_state_running(monkeypatch):
    sorters._docker_cache.clear()
    monkeypatch.setattr(sorters.shutil, "which", lambda _n: "/usr/bin/docker")
    monkeypatch.setattr(sorters.subprocess, "run", lambda *a, **k: _Ret(0))
    assert sorters.docker_state(refresh=True) == "running"
    assert sorters.docker_available(refresh=True) is True


def test_start_docker_never_raises(monkeypatch):
    called = {}

    def _popen(cmd, *a, **k):
        called["cmd"] = cmd
        class _P:  # noqa: D401 - dummy Popen
            pass
        return _P()

    monkeypatch.setattr(sorters.subprocess, "Popen", _popen)
    assert sorters.start_docker() is True
    assert called["cmd"]  # a launch command was issued

    def _boom(*a, **k):
        raise OSError("no such app")

    monkeypatch.setattr(sorters.subprocess, "Popen", _boom)
    assert sorters.start_docker() is False   # swallowed, returns False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_sorters.py::test_docker_state_running tests/test_sorters.py::test_start_docker_never_raises -q`
Expected: FAIL with `AttributeError: module 'sorters' has no attribute 'docker_state'` / `start_docker`.

- [ ] **Step 3: Replace `docker_available()` with state-aware versions**

In `scripts/sorters.py`, replace the whole `docker_available()` function (lines 62-79) with:

```python
def docker_state(refresh: bool = False) -> str:
    """'running' | 'installed_not_running' | 'not_installed'. Never raises.

    Cached per process (the daemon state rarely flips mid-session); pass
    ``refresh=True`` to re-probe (the Docker confirm dialog does this).
    """
    if not refresh and "state" in _docker_cache:
        return _docker_cache["state"]
    if not shutil.which("docker"):
        state = "not_installed"
    else:
        try:
            ok = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=8
            ).returncode == 0
        except Exception:  # noqa: BLE001 - daemon down / timeout
            ok = False
        state = "running" if ok else "installed_not_running"
    _docker_cache["state"] = state
    return state


def docker_available(refresh: bool = False) -> bool:
    """True iff the Docker daemon is reachable (i.e. docker_state() == 'running')."""
    return docker_state(refresh=refresh) == "running"


def start_docker() -> bool:
    """Best-effort launch of Docker Desktop. Never raises.

    Returns whether a launch command was issued — NOT whether Docker finished
    booting (the caller polls docker_state(refresh=True) until 'running').
    """
    import os
    import sys

    if sys.platform == "darwin":
        cmd = ["open", "-a", "Docker"]
    elif sys.platform.startswith("win"):
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe"),
            os.path.expandvars(r"%LocalAppData%\Docker\Docker Desktop.exe"),
        ]
        exe = next((c for c in candidates if os.path.exists(c)), None)
        cmd = [exe] if exe else ["cmd", "/c", "start", "", "Docker Desktop"]
    else:  # Linux: best effort (Docker Desktop or the daemon)
        cmd = ["systemctl", "--user", "start", "docker-desktop"]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:  # noqa: BLE001 - no known launcher / permission denied
        return False
```

Note: this keeps `_docker_cache` (line 45) and the `import shutil` / `import subprocess` already at the top. The cache key changed from `"ok"` to `"state"`; nothing else reads `"ok"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_sorters.py -q`
Expected: PASS. (Existing `runnable()`/`status()` tests still pass — they call `docker_available()`, now delegating to `docker_state()`.)

- [ ] **Step 5: Commit**

```bash
git add scripts/sorters.py tests/test_sorters.py
git commit -m "feat(sorters): three-state docker_state() + start_docker(); docker_available delegates

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Controller — catalog + by-name activation + docker/welcome state

**Files:**
- Modify: `SpikeInterface_Menu.py` (`_sorter_info`/`_load_dashboard` area lines 113-142; `MenuController` lines 513-632; config defaults)
- Test: `tests/test_menu_controller.py`

This task changes only `MenuController` and its unit tests — the Textual app still uses `FakeController`, so Pilot tests are unaffected until Task 5.

- [ ] **Step 1: Write the failing tests**

Read the current `tests/test_menu_controller.py` to match its fixture style (it builds a `MenuController` with a fake args + cfg and monkeypatches the registry). Append these tests (adapt the existing helper that constructs a controller — call it `_controller(...)` below; if the file already has such a helper, reuse it):

```python
def test_catalog_covers_all_sorters_with_groups(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "mountainsort5", "kilosort4"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)
    by = {i["name"]: i for i in c.infos}
    assert set(by) == {"tridesclous2", "spykingcircus2", "mountainsort5", "kilosort4"}
    assert by["tridesclous2"]["group"] == "ready" and by["tridesclous2"]["runnable"] is True
    assert by["tridesclous2"]["recommended"] is True
    assert by["tridesclous2"]["description"]
    assert by["mountainsort5"]["group"] == "docker" and by["mountainsort5"]["runnable"] is False
    assert by["kilosort4"]["group"] == "gpu" and by["kilosort4"]["runnable"] is False


def test_set_active_by_name_guards_non_runnable(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "kilosort4"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)
    assert c.set_active_by_name("spykingcircus2") is True
    assert c.active_sorter == "spykingcircus2"
    assert c.set_active_by_name("kilosort4") is False   # not runnable -> no change
    assert c.active_sorter == "spykingcircus2"


def test_cycle_active_skips_non_runnable(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2", "spykingcircus2"])
    monkeypatch.setattr(reg, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "kilosort4"]))
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)
    start = c.active_sorter
    c.cycle_active()
    assert c.active_sorter != start and c.active_sorter in ("tridesclous2", "spykingcircus2")


def test_docker_status_text_per_state(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2"])
    monkeypatch.setattr(reg, "available", lambda: ["tridesclous2"])
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)
    monkeypatch.setattr(reg, "docker_state", lambda *a, **k: "running")
    s = c.docker_status(refresh=True)
    assert s["state"] == "running" and s["running"] is True and s["text"]
    monkeypatch.setattr(reg, "docker_state", lambda *a, **k: "not_installed")
    assert c.docker_status(refresh=True)["running"] is False


def test_welcome_shown_once_and_persisted(monkeypatch, tmp_path):
    import sorters as reg
    monkeypatch.setattr(reg, "installed", lambda: ["tridesclous2"])
    monkeypatch.setattr(reg, "available", lambda: ["tridesclous2"])
    monkeypatch.setattr(reg, "docker_available", lambda *a, **k: False)
    c = _controller(monkeypatch, tmp_path, use_docker=False)   # fresh cfg -> first run
    assert c.want_welcome is True
    c.mark_welcome_seen()
    assert c.want_welcome is False
    assert c.cfg.get("seen_welcome") is True
```

If `tests/test_menu_controller.py` has no `_controller(...)` helper, add one that mirrors how the file already builds a controller (it must set `args.data_dir = str(tmp_path)`, `args.sorter = None`, pass `cfg={...}`/`use_docker`, and stub `report._gather` to return empty pipeline rows so `reload()` doesn't load SpikeInterface). Example helper:

```python
def _controller(monkeypatch, tmp_path, use_docker=False, cfg=None):
    import SpikeInterface_Menu as M
    import report
    monkeypatch.setattr(report, "_gather", lambda *a, **k: ({}, []))
    import argparse
    args = argparse.Namespace(data_dir=str(tmp_path), sorter=None, duration=None,
                              docker=False, params_file=None, gui_mode="auto")
    monkeypatch.setattr(M, "_save_config", lambda cfg: None)  # don't write real files
    return M.MenuController(args, dict(cfg or {}, use_docker=use_docker))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_controller.py -q`
Expected: FAIL (`AttributeError` on `group`/`set_active_by_name`/`cycle_active`/`docker_status`/`want_welcome`).

- [ ] **Step 3: Add the catalog builder helpers**

In `SpikeInterface_Menu.py`, replace `_load_dashboard` (lines 130-142) by ADDING two new functions next to it (keep `_sorter_info` and `_load_dashboard` — the fallback still uses `_load_dashboard`):

```python
def _saved_summary(sorter: str):
    """(present, units, duration) for a sorter's saved analyzer; best-effort.

    Short-circuits cheaply when there is no analyzer dir (the common case), so
    probing all ~22 sorters stays fast. Never raises.
    """
    d = _analyzer_dir(sorter)
    if not d.exists():
        return False, 0, 0.0
    try:
        import spikeinterface.full as si

        a = si.load_sorting_analyzer(d)
        return True, len(a.unit_ids), float(a.get_total_duration())
    except Exception:  # noqa: BLE001 - unreadable analyzer -> treat as absent
        return False, 0, 0.0


def _catalog(active: str, use_docker: bool) -> list[dict]:
    """Full sidebar catalog over EVERY sorter (not just runnable).

    Group is membership-precedence (stable); runnable is the dynamic, Docker-aware
    set. Saved-sort summary is filled where an analyzer exists.
    """
    inst = set(sorter_registry.installed())
    docker = sorter_registry.docker_available()
    runnable = set(sorter_registry.runnable(use_docker))
    out = []
    for name in sorter_registry.available():
        present, units, duration = _saved_summary(name)
        out.append({
            "name": name,
            "group": sorter_registry.group_of(name, installed_set=inst),
            "status": sorter_registry.status(name, installed_set=inst, docker=docker),
            "runnable": name in runnable,
            "recommended": name == sorter_registry.RECOMMENDED,
            "description": sorter_registry.description(name),
            "present": present, "units": units, "duration": duration,
            "active": name == active,
        })
    return out


def _pipeline_rows(data_dir, active: str) -> list[dict]:
    """The sorter-independent pipeline status rows (LFP/Broadband/.nev)."""
    _objects, status = report._gather(data_dir, _analyzer_dir(active))
    return [r for r in status if not r["stage"].startswith("Saved sort")]
```

- [ ] **Step 4: Rework `MenuController` for the catalog + new methods**

In `SpikeInterface_Menu.py`, make these edits inside `MenuController`:

(a) In `__init__` (lines 523-538), after `self.sorter_params = ...` and before `self.sorters = ...`, change the welcome/active wiring. Replace lines 535-538:

```python
        self.sorters = sorter_registry.runnable(self.use_docker) or [sorter_registry.default_sorter()]
        want = args.sorter if args.sorter else sorter_registry.default_sorter()
        self.active_sorter = want if want in self.sorters else self.sorters[0]
        self.args.sorter = self.active_sorter
        self.want_welcome = not bool(cfg.get("seen_welcome", False))
        self.active_idx = 0
        self.reload()
```

(b) Replace the `active_sorter` property (lines 540-542) and `set_active` (lines 544-548) with name-based activation:

```python
    def set_active_by_name(self, name: str) -> bool:
        """Activate a runnable sorter by id. False (no change) if not runnable."""
        if name not in self.sorters:
            return False
        self.active_sorter = name
        self.args.sorter = name
        self._mark_active()
        return True

    def cycle_active(self) -> None:
        """`t` key: advance to the next *runnable* sorter (skips non-runnable rows)."""
        if self.active_sorter in self.sorters:
            i = (self.sorters.index(self.active_sorter) + 1) % len(self.sorters)
        else:
            i = 0
        self.set_active_by_name(self.sorters[i])

    def _mark_active(self) -> None:
        for n, info in enumerate(self.infos):
            info["active"] = (info["name"] == self.active_sorter)
            if info["active"]:
                self.active_idx = n   # index into the full catalog (footer reads this)
```

Note: `active_sorter` is now a plain attribute (set in `__init__` and `set_active_by_name`), not a property.

(c) Replace `reload` (lines 558-563) with the catalog version:

```python
    def reload(self) -> None:
        self.pipeline = _pipeline_rows(self.args.data_dir, self.active_sorter)
        self.infos = _catalog(self.active_sorter, self.use_docker)
        self._mark_active()
        self.data_report = _data_report(self.args.data_dir)
```

(d) In `toggle_docker` (lines 565-575), keep the active sorter by name and re-derive `active_idx` via `reload`/`_mark_active`. Replace lines 570-574 with:

```python
        prev = self.active_sorter
        self.sorters = sorter_registry.runnable(self.use_docker) or [sorter_registry.default_sorter()]
        self.active_sorter = prev if prev in self.sorters else self.sorters[0]
        self.args.sorter = self.active_sorter
        self.reload()
```

(e) Add Docker + welcome helpers (after `set_params`, before `saved_sorters`):

```python
    def docker_status(self, refresh: bool = False) -> dict:
        """{state, running, text} for the Docker confirm dialog (plain language)."""
        state = sorter_registry.docker_state(refresh=refresh)
        text = {
            "running": "✓ Docker is running",
            "installed_not_running": "✗ Docker is installed but not started",
            "not_installed": "You don't have Docker yet",
        }[state]
        return {"state": state, "running": state == "running", "text": text}

    def start_docker(self) -> bool:
        """Best-effort: launch Docker Desktop. The dialog polls docker_status()."""
        return sorter_registry.start_docker()

    def mark_welcome_seen(self) -> None:
        self.want_welcome = False
        self.cfg["seen_welcome"] = True
        _save_config(self.cfg)
```

(f) `saved_sorters()` (lines 599-601) still works (`infos` entries keep `present`). Leave it.

(g) `run()` (line 613-614) uses `self.args.sorter = self.active_sorter` — `active_sorter` is now an attribute, still valid. Leave it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_controller.py -q`
Expected: PASS. Then run the whole suite to confirm nothing else regressed:
Run: `uv run python -m pytest tests/ -q`
Expected: PASS (Pilot tests still use `FakeController`, unaffected).

- [ ] **Step 6: Commit**

```bash
git add SpikeInterface_Menu.py tests/test_menu_controller.py
git commit -m "feat(menu): controller serves full sorter catalog + by-name activation + docker/welcome state

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: View — grouped sidebar + FakeController catalog + sorter-test rewrites

This is the big atomic change: the sidebar renders the full catalog in groups, activation goes by-name, and `FakeController` + the index-sensitive sorter tests are reshaped together so the suite stays green.

**Files:**
- Modify: `scripts/menu_app.py` (`Controller` Protocol; `_rebuild_sorters`; `_sorter_text`; sorter selection; footer; cycle; params)
- Modify: `tests/conftest.py` (`FakeController` → catalog)
- Modify: `tests/test_menu_app.py` (rewrite the sorter-structure tests)

- [ ] **Step 1: Reshape `FakeController` to a catalog (test double first)**

In `tests/conftest.py`, replace the `reload()` body (lines 58-84) and `set_active`/`toggle_docker` (lines 86-104) and add the new methods. Replace lines 58-104 with:

```python
    # A small fake universe spanning all four groups. READY sorters come first so
    # the active sorter sits at infos index 0/1 (mirrors the real catalog order).
    _UNIVERSE = [
        # name, group, units (None = no saved sort)
        ("tridesclous2", "ready", 12),
        ("spykingcircus2", "ready", 7),
        ("mountainsort5", "docker", None),
        ("herdingspikes", "docker", None),
        ("kilosort4", "gpu", None),
    ]

    def reload(self) -> None:
        st = "PASS" if self._present else "FAIL"
        self.pipeline = [
            {"stage": "LFP (.ns2)", "status": st, "detail": "24 ch, 132s @ 1000 Hz"},
            {"stage": "Broadband (.ns5)", "status": st, "detail": "22 ch, 132s @ 30000 Hz"},
            {"stage": ".nev online units", "status": st, "detail": "8 units"},
        ]
        runnable = set(self.sorters)
        self.infos = []
        for name, group, units in self._UNIVERSE:
            present = units is not None
            self.infos.append({
                "name": name, "group": group,
                "status": ("docker" if group == "docker" else
                           "gpu" if group == "gpu" else "local"),
                "runnable": name in runnable,
                "recommended": name == "tridesclous2",
                "description": f"{name} description.",
                "present": present, "units": units or 0,
                "duration": 132.0 if present else 0.0,
                "active": name == self.active_sorter,
            })
        self._mark_active()
        self.data_report = {
            "present": self._present,
            "data_dir": "/data/recordings",
            "base": "PFCM7_d0ephys_Block2" if self._present else None,
            "files": [
                {"ext": ".ns2", "label": "LFP — analog @ 1 kHz", "present": self._present},
                {"ext": ".ns5", "label": "Broadband — raw @ 30 kHz", "present": self._present},
                {"ext": ".nev", "label": "Spike events", "present": self._present},
            ],
            "error": None if self._present else "No Blackrock .nev/.nsX files found in '/data/recordings'.",
        }

    def _mark_active(self) -> None:
        for n, info in enumerate(self.infos):
            info["active"] = (info["name"] == self.active_sorter)
            if info["active"]:
                self.active_idx = n

    def set_active_by_name(self, name: str) -> bool:
        if name not in self.sorters:
            return False
        self.active_sorter = name
        self._mark_active()
        return True

    def cycle_active(self) -> None:
        i = (self.sorters.index(self.active_sorter) + 1) % len(self.sorters)
        self.set_active_by_name(self.sorters[i])

    def toggle_docker(self) -> bool:
        self.use_docker = not self.use_docker
        self.sorters = (["tridesclous2", "spykingcircus2", "mountainsort5", "herdingspikes"]
                        if self.use_docker else ["tridesclous2", "spykingcircus2"])
        if self.active_sorter not in self.sorters:
            self.active_sorter = self.sorters[0]
        self.reload()
        return self.use_docker

    def docker_status(self, refresh: bool = False) -> dict:
        text = {"running": "✓ Docker is running",
                "installed_not_running": "✗ Docker is installed but not started",
                "not_installed": "You don't have Docker yet"}[self.docker_state]
        return {"state": self.docker_state, "running": self.docker_state == "running",
                "text": text}

    def start_docker(self) -> bool:
        self.started_docker = True
        return True

    def mark_welcome_seen(self) -> None:
        self.want_welcome = False
        self.welcome_seen = True
```

Then update `__init__` (lines 44-56) to set the new state. Replace lines 44-56 with:

```python
    def __init__(self, present: bool = True):
        self.theme_name = "periwinkle"
        self.accent = self.themes[self.theme_name]
        self.use_docker = False
        self.sorters = ["tridesclous2", "spykingcircus2"]
        self.active_sorter = "tridesclous2"
        self.active_idx = 0
        self.sorter_params: dict[str, dict] = {}
        self.actions = [dict(key=k, title=t, hint=h, needs_data=nd) for k, t, h, nd in ACTIONS]
        self.ran: list[tuple[str, str | None]] = []
        self.ran_compare = None
        self.params_set = None
        self.docker_state = "running"   # tests flip this to exercise the dialog
        self.started_docker = False
        self.want_welcome = False       # off by default so boot tests see no modal
        self.welcome_seen = False
        self._present = present
        self.reload()
```

Delete the old `set_active` method (was lines 86-89) — it is replaced by `set_active_by_name`. Keep `set_theme`, `default_params`, `param_descriptions`, `get_overrides`, `set_params`, `saved_sorters`, `run_compare`, `run` unchanged.

- [ ] **Step 2: Run the suite to see the expected breakage**

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: FAIL — `menu_app` still calls `c.set_active(...)` / reads `c.active_idx` against the old shape; sorter-structure tests assume old indices. This is expected; the next steps fix the app + the tests.

- [ ] **Step 3: Update the `Controller` Protocol + sidebar rendering in `menu_app.py`**

(a) Protocol (lines 75-93): replace the `infos` comment + method block to reflect the catalog and new methods:

```python
    infos: list[dict]                   # full catalog: {name,group,status,runnable,
                                        # recommended,description,present,units,
                                        # duration,active}
    data_report: dict                   # see SpikeInterface_Menu._data_report
    use_docker: bool
    want_welcome: bool

    def set_active_by_name(self, name: str) -> bool: ...
    def cycle_active(self) -> None: ...
    def set_theme(self, name: str) -> str: ...      # returns the new accent hex
    def reload(self) -> None: ...
    def toggle_docker(self) -> bool: ...
    def docker_status(self, refresh: bool = False) -> dict: ...
    def start_docker(self) -> bool: ...
    def mark_welcome_seen(self) -> None: ...
    def run(self, key: str, span: str | None) -> tuple[bool, str, bool]: ...
```

(b) Add group metadata near `_STATUS_GLYPH` (line 538). Replace `_STATUS_GLYPH` block (lines 537-538) with:

```python
    # Group order + headers for the grouped sidebar. Empty groups are omitted.
    _GROUP_ORDER = ["ready", "docker", "gpu", "unavailable"]
    _GROUP_LABEL = {
        "ready": "READY TO USE",
        "docker": "DOCKER SORTERS (heavier)",
        "gpu": "NEEDS A GPU",
        "unavailable": "NOT AVAILABLE",
    }
    # Per-group row glyph: ◇ = runs via Docker, · = gpu/unavailable, (none) = ready.
    _GROUP_GLYPH = {"docker": "◇", "gpu": "·", "unavailable": "·"}
```

(c) Replace `_rebuild_sorters` (lines 518-528) with the grouped builder:

```python
    def _rebuild_sorters(self) -> None:
        ol = self.query_one("#sorters", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        ol.add_option(Option(self._docker_row_text(), id="__docker__"))
        active_row = 0
        by_group: dict[str, list[dict]] = {}
        for info in self.c.infos:
            by_group.setdefault(info.get("group", "unavailable"), []).append(info)
        for group in self._GROUP_ORDER:
            members = by_group.get(group)
            if not members:                      # omit empty groups
                continue
            ol.add_option(Option(Text(self._GROUP_LABEL[group], style="dim bold"),
                                  id=f"__grp_{group}__", disabled=True))
            for info in members:
                ol.add_option(Option(self._sorter_text(info), id=info["name"]))
                if info.get("active"):
                    active_row = ol.option_count - 1
        ol.highlighted = (keep if (keep is not None and keep < ol.option_count)
                          else active_row)
```

(d) Replace `_sorter_text` (lines 540-553) — drop the `active` arg, read it from `info`, add ★/dim:

```python
    def _sorter_text(self, info: dict) -> Text:
        # Compact for the 36-col sidebar. ★ recommended, ●/○ active, group glyph,
        # name, saved-unit count; dim when not runnable. Footer carries the
        # description + full units · duration.
        active = info.get("active", False)
        runnable = info.get("runnable", False)
        t = Text()
        t.append("★ " if info.get("recommended") else "  ",
                 style=f"bold {self._accent}" if info.get("recommended") else "")
        t.append("● " if active else "○ ", style=self._accent if active else "dim")
        glyph = self._GROUP_GLYPH.get(info.get("group"))
        if glyph:
            t.append(glyph + " ", style="dim")
        name_style = f"bold {self._accent}" if active else ("" if runnable else "dim")
        t.append(info["name"], style=name_style)
        t.append(f"  {info['units']}u" if info.get("present") else "  —", style="dim")
        if active:
            t.append("  ACTIVE", style=f"bold {self._accent}")
        return t
```

(e) Replace sorter selection in `on_option_list_option_selected` (lines 649-657) and the `_set_active` helper (lines 643-646):

```python
    def _set_active_by_name(self, name: str) -> None:
        if self.c.set_active_by_name(name):
            self._rebuild_sorters()
            self._refresh_footer()

    # -- list selection ------------------------------------------------------- #
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list is self.query_one("#sorters", OptionList):
            oid = event.option.id
            if oid == "__docker__":
                self._toggle_docker()
            elif oid and oid.startswith("__grp_"):
                return
            else:
                self._select_sorter(oid)
        elif event.option_list is self.query_one("#actions", OptionList):
            self._activate_action(event.option.id)

    def _select_sorter(self, name: str) -> None:
        info = next((i for i in self.c.infos if i["name"] == name), None)
        if info is None:
            return
        if info.get("runnable"):
            self._set_active_by_name(name)
        elif info.get("group") == "docker":
            self._toggle_docker(offer_from=name)     # offer to enable Docker
        else:
            hint = ("needs a GPU build installed — see Help" if info.get("group") == "gpu"
                    else "not available on this computer")
            self._last = Text(f"{name}: {hint}", style="#f0883e")
            self._refresh_footer()
```

(f) Replace `action_cycle_sorter` (lines 633-634):

```python
    def action_cycle_sorter(self) -> None:
        self.c.cycle_active()
        self._rebuild_sorters()
        self._refresh_footer()
```

(g) Fix `_open_params` (line 721) to use the active sorter name:

```python
        sorter = self.c.active_sorter
```

(In Step (e) note `_toggle_docker` gains an `offer_from` kwarg — for now, in this task, make `_toggle_docker` accept and ignore it; Task 6 wires the dialog. Update the signature: `def _toggle_docker(self, offer_from: str | None = None) -> None:` and leave the body as the existing immediate toggle.)

(h) Footer description on highlight. Add a highlight handler and a description slot. After `_refresh_footer` (line 624), add:

```python
    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list is not self.query_one("#sorters", OptionList):
            return
        oid = event.option.id
        info = next((i for i in self.c.infos if i["name"] == oid), None)
        self._sorter_hint = Text(info["description"], style="dim") if info else None
        self._refresh_footer()
```

And in `_refresh_footer`, show the hint on line 1 when set. Replace the `if self._last:` block (lines 610-612) with:

```python
        hint = getattr(self, "_sorter_hint", None)
        if hint is not None:
            line1.append("    ")
            line1.append(hint)
        elif self._last:
            line1.append("    ")
            line1.append(self._last if isinstance(self._last, Text) else Text(str(self._last)))
```

Initialise `self._sorter_hint = None` in `__init__` (after `self._last = None`, line 411).

- [ ] **Step 4: Rewrite the index-sensitive sorter Pilot tests**

In `tests/test_menu_app.py`, add a helper near the top (after `_app`):

```python
def _sorter_row(app, name):
    ol = app.query_one("#sorters", OptionList)
    for i in range(ol.option_count):
        if ol.get_option_at_index(i).id == name:
            return i
    raise AssertionError(f"sorter row {name!r} not found")
```

Replace these tests with catalog-robust versions:

`test_boots_with_lists_and_focus` (lines 17-30):

```python
async def test_boots_with_lists_and_focus(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        actions = app.query_one("#actions", OptionList)
        assert sorters.get_option_at_index(0).id == "__docker__"
        assert actions.option_count == 11
        assert actions.highlighted == 0
        # the cursor sits on the active sorter row
        assert sorters.highlighted == _sorter_row(app, "tridesclous2")
        assert app.focused is actions
```

`test_enter_on_sorter_sets_active` (lines 62-74):

```python
async def test_enter_on_sorter_sets_active(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = _sorter_row(app, "spykingcircus2")
        await pilot.press("enter")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"
        assert "spykingcircus2" in app.query_one("#footer", Static).render().plain
```

`test_t_cycles_sorter` (lines 77-87):

```python
async def test_t_cycles_sorter(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert c.active_sorter == "tridesclous2"
        await pilot.press("t")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"
        await pilot.press("t")
        await pilot.pause()
        assert c.active_sorter == "tridesclous2"
```

`test_space_selects_sorter` (lines 241-250):

```python
async def test_space_selects_sorter(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = _sorter_row(app, "spykingcircus2")
        await pilot.press("space")
        await pilot.pause()
        assert c.active_sorter == "spykingcircus2"
```

`test_active_marker_and_incomplete_banner` (lines 253-260):

```python
async def test_active_marker_and_incomplete_banner(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        row = _sorter_row(app, "tridesclous2")
        assert "ACTIVE" in sorters.get_option_at_index(row).prompt.plain
        assert "★" in sorters.get_option_at_index(row).prompt.plain   # recommended badge
```

`test_docker_toggle_row_is_first_and_toggles` (lines 302-315) — toggling no longer changes the row count (all sorters always listed); it flips runnability:

```python
async def test_docker_toggle_row_is_first_and_toggles(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        assert sorters.get_option_at_index(0).id == "__docker__"
        assert next(i for i in c.infos if i["name"] == "mountainsort5")["runnable"] is False
        sorters.highlighted = 0           # the Docker toggle row
        await pilot.press("enter")
        await pilot.pause()
        assert c.use_docker is True
        assert next(i for i in c.infos if i["name"] == "mountainsort5")["runnable"] is True
```

`test_toggle_does_not_change_active_sorter_index` (lines 318-327):

```python
async def test_toggle_does_not_change_active_sorter_index(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        await pilot.press("enter")        # toggle docker
        await pilot.pause()
        assert c.active_sorter == "tridesclous2"   # active sorter unchanged
```

`test_param_editor_*` tests call `app._open_params()` which now reads `c.active_sorter` (= "tridesclous2") — they keep asserting `sorter == "tridesclous2"`, unchanged.

- [ ] **Step 5: Run the menu_app tests**

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: PASS for all except the two still-on-old-behaviour tests `test_missing_data_shows_banner` (checks `by_id["data-setup"]`) and `test_data_setup_screen_lists_files` (presses `d`) — those stay GREEN here because Task 5 does **not** touch data-setup/`d` yet (Task 8 does). If they fail, you changed the actions table prematurely — revert that.

Run the full suite:
Run: `uv run python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/menu_app.py tests/conftest.py tests/test_menu_app.py
git commit -m "feat(menu): grouped sorter sidebar over full catalog + by-name activation + footer descriptions

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: View — guided DockerConfirmScreen (start-Docker + poll)

**Files:**
- Modify: `scripts/menu_app.py` (new `DockerConfirmScreen`; wire `_toggle_docker`)
- Modify: `tests/test_menu_app.py` (dialog tests; update the toggle test to go through the dialog)

- [ ] **Step 1: Write the failing tests**

In `tests/test_menu_app.py`, add:

```python
async def test_docker_enable_opens_confirm_when_running(make_controller):
    c = make_controller(present=True)
    c.docker_state = "running"
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        sorters = app.query_one("#sorters", OptionList)
        sorters.highlighted = 0
        await pilot.press("enter")        # turning ON -> confirm dialog
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DockerConfirmScreen)
        assert "running" in app.screen.query_one("#dstatus", Static).render().plain.lower()
        assert c.use_docker is False      # not enabled until confirmed


async def test_docker_confirm_enable_turns_on(make_controller):
    c = make_controller(present=True)
    c.docker_state = "running"
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one("#sorters", OptionList).highlighted = 0
        await pilot.press("enter")
        await pilot.pause()
        app.screen.action_enable()        # the [Enable] button/action
        await pilot.pause()
        assert c.use_docker is True


async def test_docker_confirm_not_installed_shows_download(make_controller):
    c = make_controller(present=True)
    c.docker_state = "not_installed"
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one("#sorters", OptionList).highlighted = 0
        await pilot.press("enter")
        await pilot.pause()
        body = app.screen.query_one("#dstatus", Static).render().plain.lower()
        assert "don't have docker" in body or "download" in body


async def test_docker_confirm_start_calls_controller(make_controller):
    c = make_controller(present=True)
    c.docker_state = "installed_not_running"
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one("#sorters", OptionList).highlighted = 0
        await pilot.press("enter")
        await pilot.pause()
        app.screen.action_start_docker()  # [Start Docker for me]
        await pilot.pause()
        assert c.started_docker is True


async def test_docker_off_is_immediate(make_controller):
    c = make_controller(present=True)
    c.toggle_docker()                     # turn ON first (no dialog needed off->on in fake)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert c.use_docker is True
        app.query_one("#sorters", OptionList).highlighted = 0
        await pilot.press("enter")        # turning OFF -> immediate, no dialog
        await pilot.pause()
        assert c.use_docker is False
        assert not isinstance(app.screen, menu_app.DockerConfirmScreen)
```

Also update `test_docker_toggle_row_is_first_and_toggles` from Task 5 to go through the dialog (it currently expects an immediate toggle). Replace its tail (after pressing enter on row 0) with:

```python
        sorters.highlighted = 0
        await pilot.press("enter")        # opens the confirm dialog (state defaults to running)
        await pilot.pause()
        app.screen.action_enable()
        await pilot.pause()
        assert c.use_docker is True
        assert next(i for i in c.infos if i["name"] == "mountainsort5")["runnable"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_app.py -k docker -q`
Expected: FAIL (`AttributeError: module 'menu_app' has no attribute 'DockerConfirmScreen'`).

- [ ] **Step 3: Add `DockerConfirmScreen`**

In `scripts/menu_app.py`, after `ParamEditorScreen` (before `_setup_body`, line 279), add:

```python
class DockerConfirmScreen(ModalScreen):
    """Guided 'enable Docker?' dialog. Reads the live three-state status from the
    controller and adapts: running → just Enable; installed-not-running → Start
    Docker for me + Re-check; not-installed → Open download page + Re-check. Enable
    is always allowed (container sorters appear once Docker is up). Dismisses
    'enable' or None."""

    DOWNLOAD_URL = "https://www.docker.com/products/docker-desktop/"

    DEFAULT_CSS = """
    DockerConfirmScreen { align: center middle; }
    DockerConfirmScreen > #dialog {
        width: 64; max-width: 92%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    DockerConfirmScreen #dtitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    DockerConfirmScreen #dstatus { height: auto; }
    DockerConfirmScreen #dfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("e", "enable", "Enable"),
        Binding("s", "start_docker", "Start Docker"),
        Binding("o", "open_download", "Open download"),
        Binding("r", "recheck", "Re-check"),
        Binding("enter", "enable", "Enable", show=False),
    ]

    def __init__(self, controller, accent: str):
        super().__init__()
        self._c = controller
        self._accent = accent
        self._polls = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Enable Docker sorters?", id="dtitle")
            yield Static(id="dstatus")
            yield Static(id="dfoot")

    def on_mount(self) -> None:
        self._render()

    def _render(self) -> None:
        st = self._c.docker_status(refresh=False)
        t = Text()
        t.append("These run extra sorters your computer doesn't have installed.\n", style="")
        t.append("• First run downloads a large image (~1 GB) and is slower.\n", style="dim")
        t.append("• Needs Docker Desktop running.\n\n", style="dim")
        colour = "#3fb950" if st["running"] else "#f0883e"
        t.append(st["text"] + "\n", style=f"bold {colour}")
        if st["state"] == "not_installed":
            t.append("It's a free app that unlocks extra sorters.\n", style="dim")
        self.query_one("#dstatus", Static).update(t)
        self.query_one("#dfoot", Static).update(self._foot_text(st["state"]))

    def _foot_text(self, state: str) -> Text:
        f = Text()
        if state == "not_installed":
            f.append("[o] open download page   ", style="dim")
        elif state == "installed_not_running":
            f.append("[s] start Docker for me   ", style="dim")
        f.append("[r] re-check   [e] enable   [Esc] cancel", style="dim")
        return f

    def action_enable(self) -> None:
        self.dismiss("enable")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_open_download(self) -> None:
        import webbrowser
        try:
            webbrowser.open(self.DOWNLOAD_URL)
        except Exception:  # noqa: BLE001
            pass

    def action_recheck(self) -> None:
        self._c.docker_status(refresh=True)
        self._render()

    def action_start_docker(self) -> None:
        self._c.start_docker()
        self.query_one("#dstatus", Static).update(
            Text("Starting Docker…  (~30–60s — press [r] to re-check)", style="dim"))
        self._polls = 0
        self.set_interval(2.0, self._poll)

    def _poll(self) -> None:
        self._polls += 1
        st = self._c.docker_status(refresh=True)
        if st["running"]:
            self._render()                       # advances to the 'running' view
            return
        if self._polls >= 45:                    # ~90s timeout -> manual fallback
            self.query_one("#dstatus", Static).update(
                Text("Still not ready — open Docker Desktop, then press [r].", style="#f0883e"))
            return
```

Note: the poll uses `set_interval`, which Textual stops automatically when the screen is dismissed. The `_poll` early-returns leave the interval running until `running` or timeout; that is fine for a modal (it is removed on dismiss). If you want to stop it explicitly, capture the return of `set_interval` and call `.stop()` on success/timeout.

- [ ] **Step 4: Wire `_toggle_docker` to the dialog (ON only)**

Replace `_toggle_docker` (lines 659-666) with:

```python
    def _toggle_docker(self, offer_from: str | None = None) -> None:
        if self.c.use_docker and offer_from is None:
            self._apply_docker_toggle()          # turning OFF is immediate
            return
        self.push_screen(DockerConfirmScreen(self.c, self._accent), self._after_docker_confirm)

    def _after_docker_confirm(self, result) -> None:
        if result != "enable":
            self._last = Text("Docker sorters unchanged", style="dim")
            self._refresh_footer()
            return
        if not self.c.use_docker:
            self._apply_docker_toggle()

    def _apply_docker_toggle(self) -> None:
        on = self.c.toggle_docker()
        self._rebuild_sorters()
        self._rebuild_actions()
        self._last = Text(f"Docker sorters {'on' if on else 'off'}",
                          style=f"bold {self._accent}")
        self._refresh_footer()
        self._relayout()
```

(The `offer_from=name` path from a dimmed Docker row also opens the dialog — same `_after_docker_confirm`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: PASS. Then `uv run python -m pytest tests/ -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): guided DockerConfirmScreen — 3-state, start-Docker + poll, open download

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: View — one-time WelcomeScreen

**Files:**
- Modify: `scripts/menu_app.py` (new `WelcomeScreen`; show on mount when `want_welcome`)
- Modify: `tests/test_menu_app.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_welcome_shows_when_wanted(make_controller):
    c = make_controller(present=True)
    c.want_welcome = True
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, menu_app.WelcomeScreen)
        await pilot.press("enter")        # [Get started] dismisses + marks seen
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.WelcomeScreen)
        assert c.welcome_seen is True


async def test_welcome_hidden_when_seen(make_controller):
    c = make_controller(present=True)   # want_welcome defaults False
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.WelcomeScreen)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_app.py -k welcome -q`
Expected: FAIL (`AttributeError: ... WelcomeScreen`).

- [ ] **Step 3: Add `WelcomeScreen` + show it on mount**

In `scripts/menu_app.py`, after `DockerConfirmScreen`, add:

```python
class WelcomeScreen(ModalScreen):
    """First-launch onboarding (shown once; re-openable from Help)."""

    DEFAULT_CSS = """
    WelcomeScreen { align: center middle; }
    WelcomeScreen > #dialog {
        width: 60; max-width: 92%; height: auto;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    WelcomeScreen #wtitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    WelcomeScreen #wfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("enter", "start", "Get started"),
        Binding("escape", "start", "Get started", show=False),
    ]

    def compose(self) -> ComposeResult:
        body = Text()
        body.append("This finds neurons in your recording, in 3 steps:\n\n")
        body.append("  1. Explore", style="bold"); body.append("  – see your data\n", style="dim")
        body.append("  2. Sort", style="bold");    body.append("     – detect neurons\n", style="dim")
        body.append("  3. Report", style="bold");  body.append("   – view results\n\n", style="dim")
        body.append("Put your recording files in this folder ", style="")
        body.append("(press d for help).", style="dim")
        with Vertical(id="dialog"):
            yield Static("Welcome to the Spike Sorter", id="wtitle")
            yield Static(body)
            yield Static("[ Get started ]  ·  Enter", id="wfoot")

    def action_start(self) -> None:
        self.dismiss(None)
```

In `on_mount` (lines 436-441), after the existing setup and `self.query_one("#actions", OptionList).focus()`, add:

```python
        if getattr(self.c, "want_welcome", False):
            self.push_screen(WelcomeScreen(), self._after_welcome)

    def _after_welcome(self, _result) -> None:
        self.c.mark_welcome_seen()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: PASS. Then `uv run python -m pytest tests/ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): one-time WelcomeScreen (seen_welcome-gated)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: View — unified interactive HelpScreen (replaces data-setup)

**Files:**
- Modify: `scripts/ui.py` (add `HELP_TOPICS`)
- Modify: `scripts/menu_app.py` (`HelpScreen`; `_ACTIONS` mirror via controller is in `SpikeInterface_Menu.py`; `?`/`d` bindings; route help)
- Modify: `SpikeInterface_Menu.py` (`_ACTIONS`: data-setup → help)
- Modify: `tests/conftest.py` (`ACTIONS`: data-setup → help)
- Modify: `tests/test_menu_app.py` (migrate the two data-setup tests; add help tests)

- [ ] **Step 1: Add shared help text in `ui.py`**

In `scripts/ui.py`, after the `THEMES`/`DEFAULT_THEME` block (after line 29), add:

```python
# Shared, plain-language Help content (single source for the Textual HelpScreen
# AND the typed-fallback help). Each entry is (topic_key, title, body_lines).
HELP_TOPICS = [
    ("overview", "Overview",
     ["This tool finds neurons (spike sorting) in a Blackrock/Ripple recording.",
      "Put your recording files in the data folder, then: Explore → Sort → Report."]),
    ("steps", "The 3 steps",
     ["Explore  – quick static figures of your raw data (no sorting needed).",
      "Sort     – detect neurons in the broadband signal with a chosen sorter.",
      "Report   – build an interactive HTML report of the sorted results."]),
    ("sorters", "Sorters",
     ["A 'sorter' is the algorithm that detects neurons. tridesclous2 is the ★",
      "recommended default: fast, reliable, needs no GPU. Others appear in the",
      "sidebar grouped by what your computer can run right now."]),
    ("docker", "Docker (optional)",
     ["Docker lets you run extra sorters your computer doesn't have installed,",
      "without installing them yourself. It's optional — the ★ recommended sorter",
      "needs no Docker. Turning it on downloads a large image the first time and",
      "runs a bit slower; the menu can start Docker Desktop for you."]),
    ("data", "Data files",
     []),   # filled at render time from the live data report (present/missing checklist)
    ("keys", "Keyboard",
     ["↑/↓ or j/k move · ←/→ or Tab switch panes · Enter run/activate · 1-9 jump",
      "t switch sorter · ? help · d data files · q quit"]),
]
```

- [ ] **Step 2: Write the failing tests**

In `tests/conftest.py`, change the `ACTIONS` row `("data-setup", ...)` (line 31) to:

```python
    ("help", "Help", "what each step does · sorters · Docker · data files", False),
```

In `tests/test_menu_app.py`, replace `test_missing_data_shows_banner`'s last three asserts (lines 132-135) to reference `help` instead of `data-setup`:

```python
        by_id = {o.id: o for o in actions._options}
        assert by_id["explore"].disabled is True
        assert by_id["verify"].disabled is False
        assert by_id["help"].disabled is False
```

Replace `test_data_setup_screen_lists_files` (lines 138-150) with a Help-screen version:

```python
async def test_help_screen_opens_via_d_at_data_topic(make_controller):
    app = _app(make_controller(present=False))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")            # d -> Help, jumped to the Data files topic
        await pilot.pause()
        assert isinstance(app.screen, menu_app.HelpScreen)
        body = app.screen.query_one("#helpbody", Static).render().plain
        assert ".ns5" in body and ".ns2" in body and ".nev" in body
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.HelpScreen)


async def test_help_screen_opens_via_question_mark(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")   # the ? key
        await pilot.pause()
        assert isinstance(app.screen, menu_app.HelpScreen)
        # overview topic by default
        assert "spike sorting" in app.screen.query_one("#helpbody", Static).render().plain.lower()


async def test_help_action_runs(make_controller):
    c = make_controller(present=True)
    app = _app(c)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        # 'help' is the action at index 9 (number keys only reach 1-9, so open via the list)
        actions = app.query_one("#actions", OptionList)
        idx = next(i for i in range(actions.option_count)
                   if actions.get_option_at_index(i).id == "help")
        actions.highlighted = idx
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.HelpScreen)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_app.py -k help -q`
Expected: FAIL (`AttributeError: ... HelpScreen`; the `?`/`d` bindings not wired).

- [ ] **Step 4: Change `_ACTIONS` (data-setup → help) in `SpikeInterface_Menu.py`**

Replace the `("data-setup", ...)` row (line 506) with:

```python
    ("help",       "Help",                    "what each step does · sorters · Docker · data files", False),
```

Update the comment above `_ACTIONS` (lines 493-495) to say `help` (not `data-setup`) is handled in-app.

- [ ] **Step 5: Add `HelpScreen` and wire bindings/routing in `menu_app.py`**

(a) Add `?` to `BINDINGS` and keep `d` (repurposed). Replace the `d` binding (line 398) region — change `BINDINGS` so `d` maps to data-help-via-help and add `?`:

```python
        Binding("d", "data_help", "Data files", show=False),
        Binding("question_mark", "help", "Help", show=False),
```

(b) Replace `action_data_help` (lines 636-637) with Help routing, and add `action_help`:

```python
    def action_data_help(self) -> None:
        self.push_screen(HelpScreen(self.c, self._accent, topic="data"))

    def action_help(self) -> None:
        self.push_screen(HelpScreen(self.c, self._accent, topic="overview"))
```

(c) In `_activate_action`, replace the `elif key == "data-setup":` branch (lines 673-674) with:

```python
        elif key == "help":
            self.action_help()
```

(d) Add the `HelpScreen` class after `WelcomeScreen`:

```python
class HelpScreen(ModalScreen):
    """Interactive Help: a topic list (left) ↔ scrollable content (right). Absorbs
    the old data-setup checklist as the 'Data files' topic."""

    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    HelpScreen > #dialog {
        width: 90; max-width: 96%; height: 90%; max-height: 34;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    HelpScreen #htitle { text-style: bold; color: $accentcolor; height: 1; }
    HelpScreen #hrow { height: 1fr; }
    HelpScreen #htopics { width: 24; height: 1fr; border: round #3a3f47; }
    HelpScreen #hscroll { width: 1fr; height: 1fr; padding: 0 1; }
    HelpScreen #helpbody { height: auto; }
    HelpScreen #hfoot { color: $text-muted; height: 1; padding: 1 0 0 0; }
    HelpScreen.stacked #hrow { layout: vertical; }
    HelpScreen.stacked #htopics { width: 1fr; height: auto; max-height: 30%; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close", show=False),
    ]

    def __init__(self, controller, accent: str, topic: str = "overview"):
        super().__init__()
        self._c = controller
        self._accent = accent
        self._topic = topic

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Help", id="htitle")
            with Horizontal(id="hrow"):
                topics = NavList(
                    *[Option(title, id=key) for key, title, _body in ui.HELP_TOPICS],
                    id="htopics")
                yield topics
                with VerticalScroll(id="hscroll"):
                    yield Static(id="helpbody")
            yield Static("↑/↓ choose topic · Esc to close", id="hfoot")

    def on_mount(self) -> None:
        topics = self.query_one("#htopics", OptionList)
        start = next((n for n, (k, _t, _b) in enumerate(ui.HELP_TOPICS) if k == self._topic), 0)
        topics.highlighted = start
        topics.focus()
        self._show(self._topic)
        self._relayout()

    def on_resize(self, event) -> None:
        self._relayout(event.size)

    def _relayout(self, size=None) -> None:
        size = size if size is not None else self.size
        self.set_class(size.width < NARROW_COLS, "stacked")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id:
            self._show(event.option.id)

    def _show(self, key: str) -> None:
        title, lines = next(((t, b) for k, t, b in ui.HELP_TOPICS if k == key),
                            ("Help", []))
        if key == "data":
            body = _setup_body(self._c.data_report, self._accent)
        else:
            body = Text()
            body.append(title + "\n\n", style=f"bold {self._accent}")
            for ln in lines:
                body.append(ln + "\n")
        self.query_one("#helpbody", Static).update(body)

    def action_close(self) -> None:
        self.dismiss(None)
```

Note: `HelpScreen` reuses `_setup_body(...)` (already in this file) for the Data files topic, so `.ns2/.ns5/.nev` + "Where to put them" still render. `DataSetupScreen` is now unused but may stay in the file; remove it only if nothing references it (the `test_data_setup_screen_lists_files` test was replaced in Step 2). Removing it is optional cleanup — if you remove it, also drop its name from any import in tests.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: PASS. Then `uv run python -m pytest tests/ -q` → PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/ui.py scripts/menu_app.py SpikeInterface_Menu.py tests/conftest.py tests/test_menu_app.py
git commit -m "feat(menu): unified interactive HelpScreen (replaces data-setup); ? key + d alias

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: run_sorting.py — clearer Docker message + friendly error

**Files:**
- Modify: `scripts/run_sorting.py` (the Docker message at line 524-525; wrap the `sorters.run` call ~526-531)
- Test: `tests/test_run_sorting.py`

- [ ] **Step 1: Read the current sort call site**

Read `scripts/run_sorting.py` lines 515-540 to see the exact `ui.phase(...)`, the `if args.docker:` message, and the `sorting = sorters.run(...)` call.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_run_sorting.py` (match its existing import/monkeypatch style). The goal: when `sorters.run` raises the Docker-unreachable `RuntimeError`, the script surfaces a friendly message and returns non-zero rather than a traceback. If the file already has a helper that runs `main()` with stubbed sorters, reuse it; otherwise test the smaller helper you extract:

```python
def test_friendly_message_when_docker_not_running(monkeypatch, capsys):
    import run_sorting
    msg = run_sorting._friendly_sort_error(
        RuntimeError("Docker was requested but the Docker daemon isn't reachable."))
    assert "Docker" in msg and "try again" in msg.lower()
```

- [ ] **Step 3: Add the helper + use it**

In `scripts/run_sorting.py`, add near the other helpers:

```python
def _friendly_sort_error(exc: Exception) -> str:
    """Turn a sort failure into a one-line, actionable message (no traceback)."""
    text = str(exc)
    if "daemon" in text.lower() or "docker" in text.lower():
        return "Docker isn't running — open Docker Desktop and try again."
    return f"Sorting failed: {text}"
```

Update the Docker pre-message (line 525) to:

```python
        ui.detail("first Docker run downloads the sorter image (~1 GB, one time only)")
```

Wrap the `sorters.run(...)` call (lines 526-531) in try/except so a Docker failure prints the friendly line and exits non-zero:

```python
    try:
        sorting = sorters.run(
            args.sorter, rec, sort_dir,
            params=params, use_docker=args.docker, verbose=(args.verbosity == "verbose"),
        )
    except RuntimeError as e:
        ui.warn(_friendly_sort_error(e))
        return 1
```

(Keep the existing variable names — read the real lines in Step 1 and adapt; the `params=`/`verbose=` kwargs above mirror the current call.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_run_sorting.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_sorting.py tests/test_run_sorting.py
git commit -m "feat(run_sorting): friendly Docker-not-running error + clearer first-run download note

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Typed-fallback parity

**Files:**
- Modify: `scripts/ui.py` (`print_catalog`, `docker_confirm_text`)
- Modify: `SpikeInterface_Menu.py` (`_menu_fallback`: grouped catalog print, docker confirm, welcome blurb, help entry, `_MENU` help row)
- Test: `tests/test_menu_controller.py` or a small `tests/test_fallback.py`

The fallback's `dashboard_menu` tab bar keeps activating over the *runnable* set (small). We ADD: a grouped read-only catalog print, a state-aware Docker confirm, a one-time welcome blurb, and a Help entry that prints `HELP_TOPICS`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fallback.py`:

```python
import sorters
import ui


def test_print_catalog_groups_and_recommends(monkeypatch, capsys):
    catalog = [
        {"name": "tridesclous2", "group": "ready", "runnable": True,
         "recommended": True, "description": "fast", "present": True, "units": 12},
        {"name": "mountainsort5", "group": "docker", "runnable": False,
         "recommended": False, "description": "container", "present": False, "units": 0},
        {"name": "kilosort4", "group": "gpu", "runnable": False,
         "recommended": False, "description": "gpu", "present": False, "units": 0},
    ]
    ui.print_catalog(catalog)
    out = capsys.readouterr().out
    assert "READY TO USE" in out and "DOCKER SORTERS" in out and "NEEDS A GPU" in out
    assert "tridesclous2" in out and "★" in out


def test_docker_confirm_text_per_state():
    assert "download" in ui.docker_confirm_text("not_installed").lower()
    assert "start" in ui.docker_confirm_text("installed_not_running").lower()
    assert "running" in ui.docker_confirm_text("running").lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_fallback.py -q`
Expected: FAIL (`AttributeError: module 'ui' has no attribute 'print_catalog'`).

- [ ] **Step 3: Add the fallback helpers in `ui.py`**

```python
_CATALOG_LABEL = {"ready": "READY TO USE", "docker": "DOCKER SORTERS (heavier)",
                  "gpu": "NEEDS A GPU", "unavailable": "NOT AVAILABLE"}
_CATALOG_ORDER = ["ready", "docker", "gpu", "unavailable"]


def print_catalog(catalog) -> None:
    """Plain grouped sorter listing for the typed fallback (read-only overview)."""
    by = {}
    for info in catalog:
        by.setdefault(info.get("group", "unavailable"), []).append(info)
    for group in _CATALOG_ORDER:
        members = by.get(group)
        if not members:
            continue
        say(f"\n[bold {ACCENT}]{_CATALOG_LABEL[group]}[/]")
        for info in members:
            star = "★ " if info.get("recommended") else "  "
            units = f"{info['units']}u" if info.get("present") else "—"
            dim = "" if info.get("runnable") else f"[{MUTED}]"
            dimend = "" if info.get("runnable") else "[/]"
            say(f"  {dim}{star}{info['name']:18} {units:>5}   "
                f"{info.get('description', '')}{dimend}")


def docker_confirm_text(state: str) -> str:
    """One-line plain-language Docker guidance for the typed fallback, per state."""
    return {
        "running": "Docker is running. Enable extra sorters?",
        "installed_not_running":
            "Docker is installed but not started — start Docker Desktop, then retry.",
        "not_installed":
            "You don't have Docker — download Docker Desktop (docker.com), then retry.",
    }.get(state, "Enable Docker sorters?")
```

- [ ] **Step 4: Wire the fallback (`_menu_fallback`) in `SpikeInterface_Menu.py`**

Make these changes in `_menu_fallback` (lines 733-822) and `_MENU` (lines 480-491):

(a) `_MENU`: change the row `("8", "docker", ...)` set and append a help row. Replace the `("10", "theme", ...)` row and add help so the typed menu offers Help. Concretely, add after the theme row:

```python
    ("11", "help",   "Help",                    "what each step does · sorters · Docker · data"),
```

(b) In `_menu_fallback`, after `_print_setup_plain(report)` block (line 737), add a one-time welcome blurb + the grouped catalog:

```python
    if not cfg.get("seen_welcome", False):
        ui.note("Welcome! This finds neurons in your recording in 3 steps: "
                "Explore → Sort → Report.  Put your files in the data folder.")
        cfg["seen_welcome"] = True
        _save_config(cfg)
    catalog = _catalog(args.sorter or sorter_registry.default_sorter(), use_docker)
    ui.print_catalog(catalog)
```

Note: compute `use_docker` (already at line 739) before this block; move the `use_docker = ...` line above the catalog print.

(c) Replace the `if action == "docker":` block (lines 777-787) with a state-aware confirm before flipping ON:

```python
        if action == "docker":
            turning_on = not bool(cfg.get("use_docker", False))
            if turning_on:
                state = sorter_registry.docker_state(refresh=True)
                ui.note(ui.docker_confirm_text(state))
                if state == "not_installed":
                    if ui.prompt("Open the Docker download page? [y/N] ").strip().lower().startswith("y"):
                        webbrowser.open("https://www.docker.com/products/docker-desktop/")
                elif state == "installed_not_running":
                    if ui.prompt("Start Docker Desktop now? [y/N] ").strip().lower().startswith("y"):
                        sorter_registry.start_docker()
                        ui.note("Starting Docker… give it ~30–60s, then toggle again.")
                if ui.prompt("Enable Docker sorters? [y/N] ").strip().lower() != "y":
                    last = "Docker sorters unchanged"
                    continue
            use_docker = not use_docker
            cfg["use_docker"] = use_docker
            _save_config(cfg)
            sorter_list = sorter_registry.runnable(use_docker) or [sorter_registry.default_sorter()]
            if args.sorter not in sorter_list:
                args.sorter = sorter_list[0]
            pipeline, infos = _load_dashboard(args.data_dir, args.sorter, sorter_list, use_docker)
            active_idx = sorter_list.index(args.sorter)
            last = f"Docker sorters {'on' if use_docker else 'off'}"
            continue
```

(d) Add a `help` action handler before the final dispatch (after the `params` block, line 791):

```python
        if action == "help":
            topics = [(k, t, "") for k, t, _b in ui.HELP_TOPICS]
            while True:
                topic = ui.select("Help — choose a topic", topics + [("__done__", "Back", "")],
                                  default=0)
                if topic in (None, "__done__"):
                    break
                if topic == "data":
                    _print_setup_plain(_data_report(args.data_dir))
                    continue
                title, lines = next((t, b) for k, t, b in ui.HELP_TOPICS if k == topic)
                ui.say(f"\n[bold {ui.ACCENT}]{title}[/]")
                for ln in lines:
                    ui.say(f"  {ln}")
            last = "Closed help"
            continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_fallback.py -q`
Expected: PASS. Then `uv run python -m pytest tests/ -q` → PASS.

Smoke-check the fallback renders (pipe stdin so it takes the non-Textual path):
Run: `echo q | uv run python SpikeInterface_Menu.py 2>/dev/null | head -40 || true`
Expected: shows the grouped catalog (READY/DOCKER/GPU headers) without crashing.

- [ ] **Step 6: Commit**

```bash
git add scripts/ui.py SpikeInterface_Menu.py tests/test_fallback.py
git commit -m "feat(menu): typed-fallback parity — grouped catalog, docker confirm, welcome, help

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Docs — CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the relevant CLAUDE.md sections**

Edit `CLAUDE.md` to document (find the existing menu/sorter paragraphs and update them — do not duplicate):
- The **grouped sidebar**: all sorters via `sorters.available()`, four membership-precedence groups (READY/DOCKER/GPU/NOT AVAILABLE), GPU first-class (installed GPU sorter → READY on a GPU box), activation by name, footer shows the highlighted sorter's `description`, `★` recommended badge.
- **Guided Docker UX**: `sorters.docker_state()` three-way + `start_docker()`; the `DockerConfirmScreen` (open download page / start Docker + poll / re-check); friendly Docker-not-running error in `run_sorting.py`.
- **Onboarding**: one-time `WelcomeScreen` (`seen_welcome` in `.si_menu.json`); the unified interactive `HelpScreen` (replaces the data-setup screen/action) reachable via the **Help** action, **`?`**, and **`d`** (Data files topic).
- The new registry surface: `RECOMMENDED`, `DESCRIPTIONS`/`description()`, `group_of()`, `docker_state()`, `start_docker()`.
- `.si_menu.json` now also stores `seen_welcome`.

- [ ] **Step 2: Verify the docs build mentally + commit**

Run: `uv run python -m pytest tests/ -q`  (sanity: nothing referenced in docs is broken)
Expected: PASS.

```bash
git add CLAUDE.md
git commit -m "docs: document grouped sidebar, guided Docker UX, Welcome + Help (CLAUDE.md)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `uv run python -m pytest tests/ -q`
Expected: PASS — all green (66 prior + the new tests).

- [ ] **Step 2: Import-light sanity (no SpikeInterface at import)**

Run: `uv run python -c "import sys; sys.path.insert(0,'scripts'); import sorters, menu_app; assert 'spikeinterface' not in sys.modules; print('import-light OK')"`
Expected: prints `import-light OK`.

- [ ] **Step 3: Responsiveness sweep still holds**

Run: `uv run python -m pytest tests/test_menu_app.py -k "stay_on_screen or never_clips or tiny or short or resize" -q`
Expected: PASS at all the small sizes.

- [ ] **Step 4: Launch the menu once by hand (visual smoke)**

Run: `uv run python SpikeInterface_Menu.py` (then `q` to quit)
Expected: grouped sidebar with READY/DOCKER/GPU groups, `★` on tridesclous2, footer shows a description as you move the cursor, `?` opens Help, the Docker toggle opens the confirm dialog.

- [ ] **Step 5: Final state**

Confirm `git status` is clean and the branch holds the task commits. Mark the handoff `docs/handoff-newcomer-friendly-menu.md` done if desired (separate doc commit).

---

## Self-Review (completed by plan author)

**Spec coverage:** §3.1 grouped sidebar → Tasks 2,4,5. §3.2 Docker toggle + dialog → Tasks 3,6 (+ maximum hand-holding: start-Docker poll). §3.3 onboarding (welcome, descriptions, ★, help) → Tasks 1,5,7,8. §3.4 registry additions → Tasks 1,2,3. §3.5 fallback parity → Task 10. §3.6 controller/tests/docs → Tasks 4,8,11. Friendly Docker errors (spec "Error handling") → Task 9. All covered.

**Placeholder scan:** No TBD/TODO; every code step shows real code. The HELP_TOPICS "data" entry has an intentionally empty body filled at render time from the live data report (documented inline).

**Type consistency:** Catalog dict keys (`name/group/status/runnable/recommended/description/present/units/duration/active`) are identical across `_catalog()` (Task 4), `FakeController` (Task 5), the sidebar renderer (Task 5), and `print_catalog()` (Task 10). `set_active_by_name`/`cycle_active`/`docker_status`/`start_docker`/`mark_welcome_seen`/`want_welcome`/`active_sorter` match between `MenuController` (Task 4), the `Controller` Protocol (Task 5), and `FakeController` (Task 5). `_setup_body` is reused by `HelpScreen` (Task 8). `docker_state` return values (`running`/`installed_not_running`/`not_installed`) match across registry, controller, dialog, and fallback.

**Index contract:** `_ACTIONS`/`conftest.ACTIONS` keep indices 0–8 unchanged (help replaces data-setup at index 9); number-key tests (`1` explore, `2` sort, `6` compare, `7` params, `8` verify) are untouched and remain valid.
