# Menu UI Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revert the menu dashboard to a simultaneous three-panel layout (SORTERS + ACTIONS + bottom INSPECTING) with an always-on DATA/SORT banner, run sorting *inside* the TUI with live structured progress, and download/delete Docker images and clear saved sorts in-UI.

**Architecture:** The Textual app (`scripts/menu_app.py`) stays a pure view over `MenuController` (`SpikeInterface_Menu.py`) and imports **no** SpikeInterface. Sorting runs in a subprocess (`scripts/run_sorting.py --progress json`) that streams newline-delimited JSON events parsed by a new pure module (`scripts/sort_progress.py`); a `SortProgressScreen` renders them. Docker image download/delete reuse the existing registry hooks (`scripts/sorters.py`) plus two new helpers.

**Tech Stack:** Python 3.12, Textual (TUI), rich, the Docker SDK (`docker`), pytest + pytest-asyncio (Textual `Pilot`). Run everything with `uv run`.

**Reference docs:** Spec at `docs/superpowers/specs/2026-06-08-menu-ui-overhaul-design.md`. Subsystem map facts are embedded in the tasks below.

**Conventions (follow exactly):**
- The Textual process must never `import spikeinterface` (kept import-light + testable). All SI work stays in the controller or a child process.
- Registry/Docker helpers never raise — they return `False`/`None`/`(False, msg)` on any failure.
- Run tests with `uv run python -m pytest`. Install dev deps once with `uv sync --group dev`.
- Commit after every green step. Branch is `menu-ui-overhaul-three-panel` (already created).
- Keep the user's unrelated `.gitignore` WIP out of every commit — `git add` exact paths only.

---

## File Structure

| File | Responsibility | New/Modify |
|------|----------------|-----------|
| `scripts/sort_progress.py` | Pure JSON progress event schema: `emit()`, `parse_line()`, `reduce()` state machine. No SI/Textual deps. | **New** |
| `scripts/run_sorting.py` | Add `--progress json`: a `Reporter` that mirrors ConsoleUI/tqdm calls into `sort_progress.emit()` on **stdout** while human text goes to **stderr**. | Modify |
| `scripts/sorters.py` | `delete_docker_image()`, `image_size()`. | Modify |
| `SpikeInterface_Menu.py` | Controller: `image_state()`, `download_image()`, `delete_image()`, `clear_saved_sort()`; fold image state into `_catalog()`; `manage` action; sort-modal command builder. Fallback "Manage sorters". | Modify |
| `scripts/menu_app.py` | Layout rewrite (three panels + banner, drop accordion); focus-not-display nav; merged INSPECTING; responsive ladder; new screens `SortProgressScreen`, `DownloadProgressScreen`, `ManageSortersScreen`, `ManageSorterScreen`. | Modify |
| `scripts/ui.py` | Sorter-row download glyph constants, banner styling helpers. | Modify |
| `tests/conftest.py` | Extend `FakeController` (image/saved universe, new methods); add `manage` to ACTIONS. | Modify |
| `tests/test_sort_progress.py` | Event round-trip + reducer tests. | **New** |
| `tests/test_sorters.py` | Tests for delete/size helpers. | Modify |
| `tests/test_menu_controller.py` | Tests for new controller methods + catalog image state. | Modify |
| `tests/test_menu_app.py` | Rewrite layout/nav tests for three-panel; add sort/download/manage screen tests. | Modify |
| `CLAUDE.md` | Architecture section rewrite. | Modify |

---

# STAGE 1 — Pure logic & emitter (TDD, no UI)

### Task 1: `scripts/sort_progress.py` — progress event schema

**Files:**
- Create: `scripts/sort_progress.py`
- Test: `tests/test_sort_progress.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sort_progress.py
"""Tests for the pure sort-progress event protocol (no SI / Textual)."""
import io
import sys

sys.path.insert(0, "scripts")
import sort_progress as sp


def test_emit_parse_roundtrip():
    buf = io.StringIO()
    sp.emit({"t": "phase", "i": 1, "n": 4, "title": "Read broadband"}, stream=buf)
    line = buf.getvalue()
    assert line.endswith("\n")
    ev = sp.parse_line(line)
    assert ev == {"t": "phase", "i": 1, "n": 4, "title": "Read broadband"}


def test_parse_line_ignores_non_events():
    assert sp.parse_line("not json at all") is None
    assert sp.parse_line("") is None
    assert sp.parse_line('{"no":"t key"}') is None
    assert sp.parse_line('{"t": 123}') is None  # t must be a known str


def test_reduce_tracks_phases_and_bar():
    state = sp.new_state()
    for ev in [
        {"t": "phase", "i": 1, "n": 4, "title": "Read broadband", "sub": "22 ch"},
        {"t": "detail", "text": "bandpass 300-6000"},
        {"t": "phase", "i": 2, "n": 4, "title": "Run sorter"},
        {"t": "bar", "desc": "detect", "frac": 0.5, "n": 5, "total": 10},
        {"t": "heartbeat", "label": "running sorter", "secs": 30},
    ]:
        sp.reduce(state, ev)
    assert state["phase_i"] == 2 and state["phase_n"] == 4
    assert state["phase_title"] == "Run sorter"
    assert state["phases"][0]["done"] is True   # phase 1 completed when 2 started
    assert state["bar"]["frac"] == 0.5 and state["bar"]["total"] == 10
    assert state["heartbeat"] == "running sorter" and state["heartbeat_secs"] == 30
    assert state["done"] is None


def test_reduce_done_and_error():
    s1 = sp.new_state()
    sp.reduce(s1, {"t": "done", "ok": True, "units": 13, "good": 9, "out": "outputs/x"})
    assert s1["done"]["ok"] is True and s1["done"]["units"] == 13

    s2 = sp.new_state()
    sp.reduce(s2, {"t": "error", "ok": False, "message": "Docker isn't running"})
    assert s2["done"]["ok"] is False and "Docker" in s2["done"]["message"]


def test_reduce_metrics_rows():
    state = sp.new_state()
    sp.reduce(state, {"t": "metrics", "rows": [{"unit": 1, "snr": 7.2}], "csv": "q.csv"})
    assert state["metrics"]["rows"][0]["unit"] == 1
    assert state["metrics"]["csv"] == "q.csv"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/test_sort_progress.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'sort_progress'`).

- [ ] **Step 3: Write `scripts/sort_progress.py`**

```python
"""Pure, dependency-free progress protocol between ``run_sorting.py`` (emitter,
in a subprocess) and the Textual ``SortProgressScreen`` (consumer).

Events are newline-delimited JSON objects, each with a ``t`` (type) field:

    phase     {t,i,n,title,sub?}     a numbered pipeline phase started
    detail    {t,text}               a dim sub-step line
    bar       {t,desc,frac,n,total,elapsed?,remaining?}  determinate progress
    heartbeat {t,label,secs}         "still working" pulse during quiet stretches
    metrics   {t,rows:[...],csv}     quality-metrics table
    done      {t,ok:true,units,good?,out}     finished OK
    error     {t,ok:false,message}   finished with a friendly error

No SpikeInterface / Textual imports here so it is trivially unit-testable and
importable from both sides.
"""
from __future__ import annotations

import json
import sys
from typing import Any

EVENT_TYPES = frozenset(
    {"phase", "detail", "bar", "heartbeat", "metrics", "done", "error"}
)


def emit(event: dict, stream=None) -> None:
    """Write one event as a JSON line. Defaults to stdout (the event channel)."""
    stream = stream if stream is not None else sys.stdout
    stream.write(json.dumps(event, separators=(",", ":")) + "\n")
    stream.flush()


def parse_line(line: str) -> "dict | None":
    """Parse one line into an event dict, or None if it isn't a known event."""
    line = line.strip()
    if not line:
        return None
    try:
        ev = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(ev, dict):
        return None
    if ev.get("t") not in EVENT_TYPES:
        return None
    return ev


def new_state() -> dict:
    """Fresh consumer state the reducer mutates."""
    return {
        "phase_i": 0,
        "phase_n": 0,
        "phase_title": "",
        "phases": [],          # [{i,title,done}]
        "detail": "",
        "bar": None,           # {desc,frac,n,total,elapsed,remaining} or None
        "heartbeat": "",
        "heartbeat_secs": 0,
        "metrics": None,       # {rows,csv} or None
        "done": None,          # {ok,...} or None
    }


def reduce(state: dict, ev: dict) -> dict:
    """Fold one event into ``state`` (mutates and returns it)."""
    t = ev.get("t")
    if t == "phase":
        # mark the previous phase done when a new one starts
        for p in state["phases"]:
            p["done"] = True
        state["phase_i"] = ev.get("i", state["phase_i"])
        state["phase_n"] = ev.get("n", state["phase_n"])
        state["phase_title"] = ev.get("title", "")
        state["phases"].append(
            {"i": ev.get("i"), "title": ev.get("title", ""), "sub": ev.get("sub", ""), "done": False}
        )
        state["bar"] = None            # a new phase clears the old determinate bar
        state["detail"] = ev.get("sub", "")
    elif t == "detail":
        state["detail"] = ev.get("text", "")
    elif t == "bar":
        state["bar"] = {
            "desc": ev.get("desc", ""),
            "frac": ev.get("frac"),
            "n": ev.get("n"),
            "total": ev.get("total"),
            "elapsed": ev.get("elapsed"),
            "remaining": ev.get("remaining"),
        }
    elif t == "heartbeat":
        state["heartbeat"] = ev.get("label", "")
        state["heartbeat_secs"] = ev.get("secs", 0)
    elif t == "metrics":
        state["metrics"] = {"rows": ev.get("rows", []), "csv": ev.get("csv", "")}
    elif t in ("done", "error"):
        for p in state["phases"]:
            p["done"] = True
        state["done"] = {k: v for k, v in ev.items() if k != "t"}
    return state
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m pytest tests/test_sort_progress.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/sort_progress.py tests/test_sort_progress.py
git commit -m "feat(menu): pure JSON progress protocol for in-UI sorting"
```

---

### Task 2: `run_sorting.py --progress json` emitter

Wire the existing `ConsoleUI` + `AlignedTqdm` to also emit `sort_progress` events when `--progress json` is given. In that mode, **events go to stdout** and **all human text goes to stderr**, so the parent reads stdout as a clean event channel.

**Files:**
- Modify: `scripts/run_sorting.py` (ConsoleUI, `_install_aligned_tqdm`, `configure_output`, argparse, `main()` phases)
- Test: `tests/test_run_sorting.py` (add a subprocess-free unit test of the Reporter)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_sorting.py  (append)
import io
import sys

sys.path.insert(0, "scripts")


def test_reporter_emits_events_to_stdout(monkeypatch):
    import run_sorting as rs
    import sort_progress as sp

    buf = io.StringIO()
    rep = rs.Reporter(enabled=True, stream=buf, total_phases=4)
    rep.phase("Read broadband", "22 ch")
    rep.bar("detect", frac=0.5, n=5, total=10)
    rep.done_ok(units=13, good=9, out="outputs/x")

    events = [sp.parse_line(l) for l in buf.getvalue().splitlines()]
    events = [e for e in events if e]
    assert events[0]["t"] == "phase" and events[0]["title"] == "Read broadband"
    assert any(e["t"] == "bar" and e["frac"] == 0.5 for e in events)
    assert events[-1]["t"] == "done" and events[-1]["units"] == 13


def test_reporter_disabled_emits_nothing():
    import run_sorting as rs

    buf = io.StringIO()
    rep = rs.Reporter(enabled=False, stream=buf, total_phases=4)
    rep.phase("X")
    rep.done_ok(units=0, out="o")
    assert buf.getvalue() == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/test_run_sorting.py -q -k reporter`
Expected: FAIL (`AttributeError: module 'run_sorting' has no attribute 'Reporter'`).

- [ ] **Step 3: Implement the `Reporter` and thread it through**

Add near the top of `run_sorting.py` (after the imports, before `ConsoleUI`):

```python
import sort_progress as _sp


class Reporter:
    """Mirrors high-level pipeline events into the JSON progress channel.

    When ``enabled`` (``--progress json``), each call writes a ``sort_progress``
    event to ``stream`` (stdout); when disabled it is a no-op, so the normal CLI
    paths cost nothing. The human ConsoleUI is independent and writes to stderr in
    JSON mode.
    """

    def __init__(self, *, enabled: bool, stream=None, total_phases: int):
        self.enabled = enabled
        self.stream = stream if stream is not None else sys.stdout
        self.total = total_phases
        self.i = 0

    def _emit(self, ev: dict) -> None:
        if self.enabled:
            _sp.emit(ev, stream=self.stream)

    def phase(self, title: str, sub: str = "") -> None:
        self.i += 1
        self._emit({"t": "phase", "i": self.i, "n": self.total, "title": title, "sub": sub})

    def detail(self, text: str) -> None:
        self._emit({"t": "detail", "text": text})

    def bar(self, desc: str, *, frac, n=None, total=None, elapsed=None, remaining=None) -> None:
        self._emit({"t": "bar", "desc": desc, "frac": frac, "n": n, "total": total,
                    "elapsed": elapsed, "remaining": remaining})

    def heartbeat(self, label: str, secs: int) -> None:
        self._emit({"t": "heartbeat", "label": label, "secs": secs})

    def metrics(self, rows: list, csv: str) -> None:
        self._emit({"t": "metrics", "rows": rows, "csv": csv})

    def done_ok(self, *, units: int, out: str, good=None) -> None:
        self._emit({"t": "done", "ok": True, "units": units, "good": good, "out": str(out)})

    def error(self, message: str) -> None:
        self._emit({"t": "error", "ok": False, "message": message})
```

Then:

1. **argparse:** add to the parser in `main()`:
   ```python
   parser.add_argument("--progress", choices=["plain", "json"], default="plain",
                       help="plain CLI output (default) or newline-delimited JSON events on stdout")
   ```
2. **`configure_output(level, json_mode)`:** when `json_mode`, send the rich `ConsoleUI` console to **stderr** (`Console(stderr=True, highlight=False)`), so stdout carries only events. Change the signature to accept `json_mode: bool` and construct the `ConsoleUI` accordingly (pass it down, or set a module flag the `ConsoleUI.__init__` reads). Simplest: add a `stderr: bool = False` kwarg to `ConsoleUI.__init__` and use `Console(stderr=stderr, highlight=False)`; in plain `print` fallback use `file=sys.stderr` when `stderr`.
3. **`main()`:** build `rep = Reporter(enabled=args.progress == "json", total_phases=N)` (N = the existing total-phases count), and after each existing `ui.phase(...)`/`ui.detail(...)`/`ui.metrics(...)` call, add the matching `rep.*` call. Map the final success line to `rep.done_ok(units=n_units, out=out, good=n_good)` and the friendly-error path (`_friendly_sort_error`) to `rep.error(message)`.
4. **tqdm → bar events (`_install_aligned_tqdm`):** when `json_mode`, the `AlignedTqdm.update`/`refresh` override should also call `rep.bar(self.desc, frac=self.n / self.total ...)`. Pass the active `Reporter` to the tqdm installer (module-level `_REPORTER` set in `configure_output`, read by `AlignedTqdm`). Guard: only emit when `self.total` is a positive number; throttle to ~10 Hz by tracking the last emit fraction (emit when `frac - last >= 0.01` or on completion).
5. **heartbeat:** the existing `_Heartbeat` thread should also call `rep.heartbeat(label, secs)` each tick when json_mode.

> Keep all existing plain-CLI behaviour identical when `--progress plain` (the default). The `Reporter` is a no-op then and the ConsoleUI still writes to stdout.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m pytest tests/test_run_sorting.py -q`
Expected: PASS (new reporter tests + existing tests still green).

- [ ] **Step 5: Smoke-check the event channel (no data required to fail cleanly)**

Run: `uv run python scripts/run_sorting.py --duration 1 --progress json 1>/tmp/ev.jsonl 2>/tmp/human.txt; echo "exit=$?"; head -3 /tmp/ev.jsonl`
Expected: if data is present, `/tmp/ev.jsonl` holds JSON event lines and `/tmp/human.txt` holds the rich output; if no data, stderr shows the friendly error and stdout still holds only JSON (an `error` event). Either way stdout is pure JSON.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_sorting.py tests/test_run_sorting.py
git commit -m "feat(sort): --progress json emits structured events (stdout) for in-UI sorting"
```

---

### Task 3: `sorters.delete_docker_image` + `image_size`

**Files:**
- Modify: `scripts/sorters.py` (add after `pull_docker_image`, ~line 234)
- Test: `tests/test_sorters.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sorters.py  (append)
def test_image_size_and_delete(monkeypatch):
    import sorters

    class FakeImg:
        attrs = {"Size": 1_100_000_000}

    class FakeImages:
        def __init__(self): self.removed = []
        def get(self, image): return FakeImg()
        def remove(self, image, force=False): self.removed.append(image)

    class FakeClient:
        images = FakeImages()

    fake_docker = type("D", (), {"from_env": staticmethod(lambda: FakeClient())})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)

    assert sorters.image_size("spikeinterface/x:latest") == 1_100_000_000
    ok, msg = sorters.delete_docker_image("spikeinterface/x:latest")
    assert ok is True and "x" in msg


def test_delete_docker_image_never_raises(monkeypatch):
    import sorters

    class Boom:
        @staticmethod
        def from_env(): raise RuntimeError("daemon down")

    monkeypatch.setitem(__import__("sys").modules, "docker", Boom)
    ok, msg = sorters.delete_docker_image("x:latest")
    assert ok is False and msg
    assert sorters.image_size("x:latest") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/test_sorters.py -q -k "image_size or delete_docker"`
Expected: FAIL (`AttributeError: module 'sorters' has no attribute 'delete_docker_image'`).

- [ ] **Step 3: Implement**

```python
def image_size(image: str) -> "int | None":
    """Size in bytes of a locally cached image, or None. Never raises."""
    try:
        import docker

        return int(docker.from_env().images.get(image).attrs["Size"])
    except Exception:  # noqa: BLE001 - missing image / no SDK / daemon down
        return None


def delete_docker_image(image: str) -> "tuple[bool, str]":
    """Remove a locally cached image. Returns (ok, human_message). Never raises."""
    try:
        import docker

        docker.from_env().images.remove(image, force=False)
        return True, f"Removed Docker image {image}"
    except Exception as e:  # noqa: BLE001 - missing image / in use / no SDK / daemon down
        return False, f"Couldn't remove {image}: {e}"
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m pytest tests/test_sorters.py -q -k "image_size or delete_docker"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/sorters.py tests/test_sorters.py
git commit -m "feat(sorters): delete_docker_image + image_size helpers"
```

---

### Task 4: Controller methods + catalog image state

**Files:**
- Modify: `SpikeInterface_Menu.py` — `_catalog()` (~line 163) to add `img_present`/`img_size` to docker-group rows; add `MenuController` methods `image_state`, `download_image`, `delete_image`, `clear_saved_sort`, and a `sort_command()` builder.
- Test: `tests/test_menu_controller.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_menu_controller.py  (append)
import sys
sys.path.insert(0, "scripts")


def _make_controller(monkeypatch, tmp_path):
    import SpikeInterface_Menu as M
    import sorter_registry  # alias used inside the launcher
    # Point outputs at a temp dir for clear_saved_sort
    return M


def test_clear_saved_sort_removes_outputs(monkeypatch, tmp_path):
    import SpikeInterface_Menu as M
    import blackrock_io as bio

    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)
    saved = tmp_path / "outputs" / "tridesclous2"
    saved.mkdir(parents=True)
    (saved / "run_info.json").write_text("{}")

    c = M.MenuController.__new__(M.MenuController)   # no __init__ I/O
    ok, msg = c.clear_saved_sort("tridesclous2")
    assert ok is True and not saved.exists()


def test_delete_image_resolves_and_calls_registry(monkeypatch):
    import SpikeInterface_Menu as M
    calls = {}
    monkeypatch.setattr(M.sorter_registry, "default_docker_image", lambda n: "img:latest")
    monkeypatch.setattr(M.sorter_registry, "delete_docker_image",
                        lambda img: calls.setdefault("img", img) or (True, "ok"))
    c = M.MenuController.__new__(M.MenuController)
    ok, msg = c.delete_image("mountainsort5")
    assert ok is True and calls["img"] == "img:latest"


def test_sort_command_builds_argv(monkeypatch, tmp_path):
    import SpikeInterface_Menu as M
    c = M.MenuController.__new__(M.MenuController)
    c.active_sorter = "tridesclous2"
    c.use_docker = False
    c.args = type("A", (), {"data_dir": None})()
    c.get_overrides = lambda name: {}
    argv = c.sort_command(span="quick")
    assert "run_sorting.py" in " ".join(argv)
    assert "--progress" in argv and "json" in argv
    assert "--sorter" in argv and "tridesclous2" in argv
    assert "--duration" in argv  # quick → duration set
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python -m pytest tests/test_menu_controller.py -q -k "clear_saved or delete_image or sort_command"`
Expected: FAIL (missing methods).

- [ ] **Step 3: Implement**

In `_catalog()` (each docker-group `info` dict), add image state. Find where docker rows are built and add (cheaply, guarded):

```python
        if group == "docker":
            img = sorter_registry.default_docker_image(name)
            info["image"] = img
            info["img_present"] = bool(img) and sorter_registry.docker_image_present(img)
        else:
            info["image"] = None
            info["img_present"] = None
```

> Keep this guarded and only for docker rows so `_catalog()` stays cheap; `docker_image_present` is a fast local SDK call but skip it entirely when the Docker daemon isn't installed (check `sorter_registry.docker_state() != "not_installed"` once per `_catalog` call).

Add `MenuController` methods (near `run`, ~line 876):

```python
    def image_state(self, name: str) -> dict:
        """{image, present, size} for a sorter's Docker image (best-effort)."""
        img = sorter_registry.default_docker_image(name)
        if not img:
            return {"image": None, "present": False, "size": None}
        present = sorter_registry.docker_image_present(img)
        size = sorter_registry.image_size(img) if present else None
        return {"image": img, "present": present, "size": size}

    def download_image(self, name: str, on_progress=None, on_status=None) -> "tuple[bool, str]":
        """Pull a sorter's Docker image, streaming progress to the callbacks."""
        img = sorter_registry.default_docker_image(name)
        if not img:
            return False, f"No Docker image is known for {name}."
        ok = sorter_registry.pull_docker_image(img, on_progress, on_status)
        return (True, f"Downloaded {img}") if ok else (False, f"Couldn't download {img}.")

    def delete_image(self, name: str) -> "tuple[bool, str]":
        img = sorter_registry.default_docker_image(name)
        if not img:
            return False, f"No Docker image is known for {name}."
        return sorter_registry.delete_docker_image(img)

    def clear_saved_sort(self, name: str) -> "tuple[bool, str]":
        """Delete outputs/<name>/ (the saved sorting + analyzer). Robust to locks."""
        import shutil
        folder = bio.REPO_ROOT / "outputs" / name
        if not folder.exists():
            return False, f"No saved sort for {name}."
        try:
            shutil.rmtree(folder)
            return True, f"Cleared saved {name} sort"
        except Exception as e:  # noqa: BLE001
            return False, f"Couldn't clear {name}: {e}"

    def sort_command(self, span: "str | None") -> list:
        """argv for run_sorting.py in JSON-progress mode, for the in-UI sort modal."""
        import sys as _sys
        argv = [_sys.executable, str(bio.REPO_ROOT / "scripts" / "run_sorting.py"),
                "--sorter", self.active_sorter, "--progress", "json"]
        if span == "quick":
            argv += ["--duration", str(QUICK_SECONDS)]
        if self.use_docker:
            argv += ["--docker"]
        if getattr(self.args, "data_dir", None):
            argv += ["--data-dir", str(self.args.data_dir)]
        overrides = self.get_overrides(self.active_sorter)
        for k, v in overrides.items():
            argv += ["--param", f"{k}={v}"]
        return argv
```

> Note the launcher imports the registry as `sorter_registry` (alias). Use that name. `bio` is `blackrock_io` (already imported). `QUICK_SECONDS = 30` is module-level.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m pytest tests/test_menu_controller.py -q`
Expected: PASS (new + existing controller tests).

- [ ] **Step 5: Commit**

```bash
git add SpikeInterface_Menu.py tests/test_menu_controller.py
git commit -m "feat(menu): controller image-state/download/delete/clear + sort_command"
```

---

# STAGE 2 — Three-panel layout & banner

> From here the work is in `scripts/menu_app.py`. The accordion (`_switch_mode`, `_mode`, `action_focus_*`, `#activebar`, `#statusline`, `#panelabel`, `#explain`) is replaced. Read the current file before editing; reuse the existing render helpers (`_sorter_text`, `_action_text`, `_render_*_explain`, `_relayout`, `CrestWidget`) where possible — they change, but their logic is the starting point.

### Task 5: New CSS + `compose()` (both panels + banner + INSPECTING)

**Files:**
- Modify: `scripts/menu_app.py` — `CSS` (~737), `compose()` (~829), `on_mount` (~845)

- [ ] **Step 1: Replace the `CSS` block** with the three-panel stylesheet:

```python
    CSS = """
    Screen { background: $background; }

    #crest { height: auto; content-align: center top; padding: 1 0 0 0; }
    #titlebar { height: 1; content-align: left middle; }

    /* Always-on two-line banner (replaces statusline + activebar). */
    #databar { height: 1; margin: 1 2 0 2; }
    #sortbar { height: 1; margin: 0 2 0 2; }

    #body { height: 1fr; padding: 1 1 0 1; }
    #body.stacked { layout: vertical; }

    /* SORTERS and ACTIONS are co-equal and BOTH always shown. */
    #sorterpane, #actionpane { width: 1fr; height: 1fr; min-height: 5;
        border: round #3a3f47; padding: 0 1; }
    #actionpane { margin: 0 0 0 1; }
    #body.stacked #actionpane { margin: 1 0 0 0; }
    /* Focused pane: accent + heavy border (shape cue survives NO_COLOR). */
    #sorterpane:focus-within { border: heavy $accentcolor; }
    #actionpane:focus-within { border: heavy $accentcolor; }

    #sorters, #actions { height: 1fr; }

    /* Cursor vs ACTIVE distinction (unchanged intent). */
    OptionList:focus > .option-list--option-highlighted {
        background: $accentcolor 25%; color: $foreground; text-style: none; }
    OptionList > .option-list--option-highlighted {
        background: transparent; text-style: underline; }

    /* Bottom INSPECTING panel — full width, capped height, scrolls. */
    #inspect { height: auto; max-height: 7; border: round #3a3f47;
        padding: 0 1; margin: 1 1 0 1; }
    #inspect.hidden { display: none; }

    #footer { dock: bottom; height: 2; padding: 0 2; }
    """
```

- [ ] **Step 2: Replace `compose()`**:

```python
    def compose(self) -> ComposeResult:
        yield CrestWidget(id="crest")
        yield Static(id="titlebar")
        yield Static(id="databar")
        yield Static(id="sortbar")
        with Horizontal(id="body"):
            with Vertical(id="sorterpane"):
                yield NavList(id="sorters")
            with Vertical(id="actionpane"):
                yield NavList(id="actions")
        with VerticalScroll(id="inspect"):
            yield Static(id="inspectbody")
        yield Static(id="footer")
```

> Panel titles use Textual `border-title`. In `on_mount`, set:
> ```python
> self.query_one("#sorterpane").border_title = "SORTERS"
> self.query_one("#inspect").can_focus = False
> ```
> and update the ACTIONS title from the active sorter in `_refresh_action_title()` (Task 7).

- [ ] **Step 3:** Update `on_mount` to build both lists, set both panel titles, focus `#sorters`, and remove all `_mode`/accordion setup. Keep the welcome-screen push and the initial `_relayout()`.

- [ ] **Step 4: Commit** (UI won't fully run until Task 6–9; commit the structural change once `compose` imports cleanly):

```bash
uv run python -c "import sys; sys.path.insert(0,'scripts'); import menu_app"   # must import clean
git add scripts/menu_app.py && git commit -m "refactor(menu): three-panel compose + CSS (no accordion)"
```

---

### Task 6: Focus-driven nav (move focus, don't hide lists)

**Files:** Modify `scripts/menu_app.py` — `BINDINGS` (~789) and the focus actions.

- [ ] **Step 1: Write the failing Pilot test** (replaces the old accordion test):

```python
# tests/test_menu_app.py  (replace test_left_right_switch_focus)
async def test_both_lists_visible_and_focus_moves(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        sorters = app.query_one("#sorters")
        actions = app.query_one("#actions")
        # both always visible now
        assert sorters.display is True and actions.display is True
        assert app.focused is sorters
        await pilot.press("right")
        assert app.focused is actions
        await pilot.press("left")
        assert app.focused is sorters
        await pilot.press("tab")
        assert app.focused is actions
```

(`make_app` is the existing fixture building `SpikeMenuApp(FakeController())`; reuse it.)

- [ ] **Step 2: Run to verify it fails** (old behavior hid a list).

Run: `uv run python -m pytest tests/test_menu_app.py -q -k both_lists_visible`
Expected: FAIL.

- [ ] **Step 3: Implement** — replace the mode actions with plain focus moves:

```python
    BINDINGS = [
        Binding("left", "focus_sorters", show=False),
        Binding("right", "focus_actions", show=False),
        Binding("tab", "focus_actions", show=False, priority=True),
        Binding("shift+tab", "focus_sorters", show=False, priority=True),
        Binding("t", "cycle_sorter", show=False),
        Binding("m", "toggle_motion", show=False),
        Binding("x", "manage_highlighted", show=False),   # delete/clear for highlighted sorter
        Binding("d", "data_help", show=False),
        Binding("f", "choose_folder", show=False),
        Binding("question_mark", "help", show=False),
        Binding("q", "quit", show=False),
        Binding("ctrl+c", "quit", show=False),
        *[Binding(str(n), f"run_index({n - 1})", show=False) for n in range(1, 10)],
    ]

    def action_focus_sorters(self) -> None:
        self.query_one("#sorters", OptionList).focus()
        self._render_inspect()

    def action_focus_actions(self) -> None:
        self.query_one("#actions", OptionList).focus()
        self._render_inspect()
```

Delete `_switch_mode`, `action_focus_sorter`/`action_focus_actions` (old), `_mode`, `_render_explain_for_mode`, and the `#activebar`/`#panelabel` logic. `action_run_index(i)` now just focuses `#actions`, moves its highlight to `i`, and runs it (no mode reveal needed since both are visible).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run python -m pytest tests/test_menu_app.py -q -k both_lists_visible`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): focus-driven nav between always-visible panes"
```

---

### Task 7: DATA / SORT banner + ACTIONS title

**Files:** Modify `scripts/menu_app.py` — add `_render_databar`, `_render_sortbar`, `_refresh_action_title`; call them from `_relayout`/after reloads. Remove `_render_statusline`/`_render_activebar`.

- [ ] **Step 1: Write the failing tests** (replace the statusline tests):

```python
# tests/test_menu_app.py
async def test_databar_healthy_lists_streams(make_app):
    app = make_app()                       # FakeController(present=True)
    async with app.run_test() as pilot:
        data = app.query_one("#databar").render().plain
        assert "✓" in data and ("LFP" in data or "stream" in data.lower())


async def test_databar_broken_is_loud(make_app):
    app = make_app(present=False)
    async with app.run_test() as pilot:
        data = app.query_one("#databar").render().plain
        assert "✗" in data and ("no recording" in data.lower() or "press f" in data.lower())


async def test_sortbar_shows_active_and_readiness(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        sort = app.query_one("#sortbar").render().plain
        assert "tridesclous2" in sort and "Ready" in sort
```

> The `make_app` fixture needs a `present` arg → `SpikeMenuApp(FakeController(present=present))`. Update the fixture if it doesn't take one.

- [ ] **Step 2: Run to verify it fails.**

Run: `uv run python -m pytest tests/test_menu_app.py -q -k "databar or sortbar"`
Expected: FAIL.

- [ ] **Step 3: Implement** the renderers (mirror the data the old `_render_statusline`/`_render_activebar` used — `self.c.data_report`, `self.c.pipeline`, `self.c.infos[self.c.active_idx]`):

```python
    def _render_databar(self, width: int) -> None:
        dr = self.c.data_report
        files = dr.get("files", [])
        complete = bool(files) and all(f.get("present") for f in files)
        bb = next((r for r in self.c.pipeline if "Broadband" in r.get("stage", "")), None)
        unreadable = complete and bb is not None and bb.get("status") == "FAIL"
        t = Text()
        t.append("DATA  ", style=ui.SECONDARY)
        if dr.get("present") and complete and not unreadable:
            for f in files:
                if f["ext"] == ".nev" and not f.get("present"):
                    continue
                t.append("✓ ", style="#3fb950")
                t.append(f"{f['label']}   ", style=ui.PRIMARY)
            t.append(f"   all {len([f for f in files if f.get('present')])} streams loaded",
                     style="dim")
        elif not dr.get("present"):
            t.append("✗ no recording in ", style="bold #f0883e")
            t.append(f"{dr.get('data_dir','.')} ", style="#f0883e")
            t.append("— press f to choose · d for help", style="dim")
        elif unreadable:
            t.append("✗ Broadband (.ns5) won't load ", style="bold #f0883e")
            t.append("— press d for help", style="dim")
        else:
            missing = ", ".join(f["ext"] for f in files if not f.get("present"))
            t.append(f"✗ incomplete set — missing {missing} ", style="bold #f0883e")
            t.append("· press f / d", style="dim")
        t.truncate(max(1, width - 2), overflow="ellipsis")
        self.query_one("#databar", Static).update(t)

    def _render_sortbar(self, width: int) -> None:
        info = self.c.infos[self.c.active_idx]
        t = Text()
        t.append("SORT  ", style=ui.SECONDARY)
        if info.get("recommended"):
            t.append("★ ", style=f"bold {self._accent}")
        t.append(info["name"], style=f"bold {self._accent}")
        if info.get("present"):
            t.append(f" · {info['units']} units · {info['duration']:.0f} s saved", style=ui.PRIMARY)
        else:
            t.append(" · not sorted yet", style="dim")
        # readiness
        if info.get("runnable"):
            ready = "Ready to run (Docker)" if self.c.use_docker and info.get("group") == "docker" \
                    else "Ready to run (CPU, no Docker)"
        elif info.get("group") == "docker":
            ready = ("Docker image not downloaded — Enter to get it"
                     if not info.get("img_present") else "Turn on Docker sorters to run")
        elif info.get("group") == "gpu":
            ready = "Needs an NVIDIA GPU"
        else:
            ready = "Not installed here"
        t.append(f" · {ready}", style="#f0883e" if not info.get("runnable") else "#3fb950")
        n = info.get("overrides", 0)
        if n:
            t.append(f" · {n} custom params", style="dim")
        t.truncate(max(1, width - 2), overflow="ellipsis")
        self.query_one("#sortbar", Static).update(t)

    def _refresh_action_title(self) -> None:
        self.query_one("#actionpane").border_title = f"ACTIONS — on {self.c.active_sorter}"
```

Call all three from `_relayout` and after every `reload`/activation.

- [ ] **Step 4: Run to verify it passes.**

Run: `uv run python -m pytest tests/test_menu_app.py -q -k "databar or sortbar"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): always-on DATA/SORT banner + ACTIONS title"
```

---

### Task 8: Merged INSPECTING (focused pane's highlight)

**Files:** Modify `scripts/menu_app.py` — add `_render_inspect()` dispatching to the existing `_render_sorter_explain`/`_render_action_explain` bodies (rename their target to `#inspectbody`, panel title to `#inspect`'s `border_title`). Wire `on_option_list_option_highlighted` for **both** lists to call `_render_inspect()`.

- [ ] **Step 1: Write the failing test:**

```python
async def test_inspect_follows_focused_pane(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        body = app.query_one("#inspectbody").render().plain
        assert "tridesclous2" in body          # sorter highlighted at boot
        await pilot.press("right")             # focus ACTIONS (row 0 = explore)
        body = app.query_one("#inspectbody").render().plain
        assert "figures" in body.lower() or "explore" in body.lower()
```

- [ ] **Step 2: Run to verify it fails.** Expected: FAIL (`#inspectbody` not updated / old `#explainbody`).

- [ ] **Step 3: Implement:**

```python
    def _render_inspect(self) -> None:
        focused = self.focused
        if focused is self.query_one("#actions", OptionList):
            self.query_one("#inspect").border_title = "INSPECTING ▸ action"
            idx = focused.highlighted or 0
            key = self.c.actions[idx]["key"]
            self._render_action_explain(self.c.action_explain(key))
        else:
            sid = self._highlighted_sorter_id()       # existing helper or compute from #sorters
            info = next((i for i in self.c.infos if i["name"] == sid), None)
            label = info["name"] if info else self.c.active_sorter
            self.query_one("#inspect").border_title = f"INSPECTING ▸ {label}"
            self._render_sorter_explain(info)
```

Change `_render_sorter_explain`/`_render_action_explain` to write `#inspectbody` (was `#explainbody`). Add highlight handlers:

```python
    def on_option_list_option_highlighted(self, event) -> None:
        self._render_inspect()
```

- [ ] **Step 4: Run to verify it passes.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): bottom INSPECTING panel follows the focused pane"
```

---

### Task 9: Responsive ladder (stack, crest reserve, never-clip)

**Files:** Modify `scripts/menu_app.py` — rework `_relayout` for the fixed 2-row banner; constants near line 72.

- [ ] **Step 1: Write the failing tests** (port the survivors + the new shape):

```python
async def test_narrow_stacks_and_keeps_both_lists(make_app):
    app = make_app()
    async with app.run_test(size=(60, 24)) as pilot:
        assert app.query_one("#body").has_class("stacked")
        for wid in ("#sorters", "#actions"):
            r = app.query_one(wid).region
            assert r.intersection(app.screen.region).height > 0


async def test_tiny_never_clips_lists(make_app):
    app = make_app()
    for size in [(40, 12), (30, 8), (24, 6), (20, 5)]:
        async with app.run_test(size=size) as pilot:
            for wid in ("#sorters", "#actions"):
                vis = app.query_one(wid).region.intersection(app.screen.region)
                assert vis.height > 0, f"{wid} clipped at {size}"
            assert app.is_running


async def test_crest_drops_before_lists(make_app):
    app = make_app()
    async with app.run_test(size=(100, 14)) as pilot:
        assert app.query_one("#crest").display is False
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** the new `_relayout`:

```python
    STACK_COLS = 64
    BANNER_ROWS = 2

    def _relayout(self, size=None) -> None:
        size = size if size is not None else self.size
        w, h = size.width, size.height
        self.query_one("#body").set_class(w < self.STACK_COLS, "stacked")
        self._render_databar(w)
        self._render_sortbar(w)
        self._refresh_action_title()
        # crest reserve = title(1) + banner(2) + footer(2) + min body(8) + inspect(up to 4)
        reserve = 1 + self.BANNER_ROWS + 2 + 8
        self.query_one("#crest", CrestWidget).fit(w, h, reserve)
        # hide INSPECTING on extreme shortness so the lists keep their rows
        self.query_one("#inspect").set_class(h < 16, "hidden")
        self._refresh_footer(w)
```

Delete the `SHIELD_RESERVE`/`NARROW_COLS`/`_BANNER_MIN_ROWS`/`_ACTIVEBAR_MIN_ROWS` usage; the crest `fit()` ladder (full→compact→mini→hidden) is unchanged.

- [ ] **Step 4: Run to verify it passes.** Then run the **whole** app test file and fix any remaining accordion-era references:

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: PASS for all ported/rewritten tests. Delete obsolete accordion-only tests (the old `#activebar`/`#explain`/`#statusline`/mode tests — A.2, A.4 auto-advance, A.18, A.38, A.39, etc.) and keep the re-pinned equivalents above.

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): responsive three-panel ladder (stack/crest/inspect, never clip)"
```

---

# STAGE 3 — In-UI sorting

### Task 10: `SortProgressScreen`

**Files:** Modify `scripts/menu_app.py` — new `ModalScreen` that spawns the sort subprocess and renders `sort_progress` events.

- [ ] **Step 1: Write the failing test** (drive with synthetic events; no real subprocess):

```python
async def test_sort_progress_screen_renders_events(make_app):
    import menu_app, sort_progress as sp
    app = make_app()
    async with app.run_test() as pilot:
        screen = menu_app.SortProgressScreen(["echo"], app._accent)  # argv unused in this test
        await app.push_screen(screen)
        await pilot.pause()
        for ev in [
            {"t": "phase", "i": 1, "n": 4, "title": "Read broadband"},
            {"t": "bar", "desc": "detect", "frac": 0.5, "n": 5, "total": 10},
            {"t": "phase", "i": 2, "n": 4, "title": "Run sorter"},
            {"t": "done", "ok": True, "units": 13, "out": "outputs/tridesclous2"},
        ]:
            screen.handle_event(ev)        # synchronous reducer + render
            await pilot.pause()
        body = screen.query_one("#sortbody").render().plain
        assert "Run sorter" in body and ("13" in body or "Done" in body)
        assert screen._state["done"]["ok"] is True
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement `SortProgressScreen`:**

```python
import asyncio
import sort_progress as _sp


class SortProgressScreen(ModalScreen):
    """Runs a sort subprocess and renders its JSON progress events in-UI."""

    BINDINGS = [Binding("escape", "cancel", show=False),
                Binding("enter", "close_if_done", show=False)]

    def __init__(self, argv: list, accent: str):
        super().__init__()
        self._argv = argv
        self._accent = accent
        self._state = _sp.new_state()
        self._proc = None

    def compose(self) -> ComposeResult:
        with Vertical(id="sortdialog"):
            yield Static("Sorting…", id="sorttitle")
            yield Static(id="sortbody")
            yield Static("Esc to cancel", id="sortfoot")

    def on_mount(self) -> None:
        self.query_one("#sortdialog").border_title = "SORTING"
        self._render()
        self.run_worker(self._run(), exclusive=True)

    async def _run(self) -> None:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
        except Exception as e:  # noqa: BLE001
            self.handle_event({"t": "error", "ok": False, "message": f"couldn't start sort: {e}"})
            return
        assert self._proc.stdout is not None
        async for raw in self._proc.stdout:
            ev = _sp.parse_line(raw.decode("utf-8", "replace"))
            if ev:
                self.handle_event(ev)
        await self._proc.wait()
        if self._state["done"] is None:
            self.handle_event({"t": "error", "ok": False,
                               "message": f"sort exited ({self._proc.returncode}) without finishing"})

    def handle_event(self, ev: dict) -> None:
        _sp.reduce(self._state, ev)
        self._render()
        if self._state["done"] is not None:
            self.query_one("#sortfoot", Static).update("Press Enter to close")

    def _render(self) -> None:
        s = self._state
        t = Text()
        for p in s["phases"]:
            glyph = "✓" if p["done"] else "▶"
            style = "#3fb950" if p["done"] else f"bold {self._accent}"
            t.append(f"{glyph} ", style=style)
            t.append(f"{p['title']}\n", style="" if p["done"] else "bold")
        if s["bar"] and s["bar"].get("total"):
            frac = s["bar"]["frac"] or 0
            fill = int(frac * 24)
            t.append(f"  {s['bar']['desc']} ", style="dim")
            t.append("█" * fill + "░" * (24 - fill), style=self._accent)
            t.append(f"  {frac*100:3.0f}%\n", style="dim")
        elif s["heartbeat"] and s["done"] is None:
            t.append(f"  ⠿ {s['heartbeat']} … still working ({s['heartbeat_secs']}s)\n", style="dim")
        if s["done"]:
            d = s["done"]
            if d.get("ok"):
                t.append(f"\n✓ Done · {d.get('units','?')} units → {d.get('out','')}\n",
                         style="bold #3fb950")
            else:
                t.append(f"\n✗ {d.get('message','failed')}\n", style="bold #f85149")
        self.query_one("#sortbody", Static).update(t)

    def action_cancel(self) -> None:
        if self._proc and self._proc.returncode is None:
            import os, signal
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except Exception:  # noqa: BLE001
                pass
        self.dismiss((False, "Sort cancelled", False))

    def action_close_if_done(self) -> None:
        if self._state["done"] is not None:
            d = self._state["done"]
            self.dismiss((bool(d.get("ok")),
                          f"{'Sorted' if d.get('ok') else 'Sort failed'} {d.get('units', '')}".strip(),
                          True))
```

Add CSS for `#sortdialog` (centered modal, `border: round $accentcolor`, width ~70, height auto) mirroring the existing `DockerConfirmScreen` dialog CSS.

- [ ] **Step 4: Run to verify it passes.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): SortProgressScreen renders in-UI sort progress events"
```

---

### Task 11: Wire the Sort action to the modal

**Files:** Modify `scripts/menu_app.py` — `_activate_action` for `"sort"` now opens the span ChoiceModal (kept) then pushes `SortProgressScreen(self.c.sort_command(span), self._accent)` instead of `_run("sort", span)`. On dismiss `(ok, msg, changed)`, set `_last`, and if `changed` call `reload()` + rebuild + `_relayout`.

- [ ] **Step 1: Write the failing test:**

```python
async def test_sort_opens_progress_screen(make_app):
    import menu_app
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.press("right")          # focus actions
        await pilot.press("2")              # sort
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ChoiceModal)   # span picker first
        await pilot.press("enter")          # choose full
        await pilot.pause()
        assert isinstance(app.screen, menu_app.SortProgressScreen)
```

> The `FakeController` must provide `sort_command(span)` returning a harmless argv like `["true"]` so the worker spawns and exits cleanly. Add it in Task 17 (or inline now).

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** the sort branch in `_activate_action` (reuse the existing span-modal + overwrite-warning flow, then push the progress screen):

```python
    def _start_sort(self, span: str) -> None:
        argv = self.c.sort_command(span)
        self.push_screen(SortProgressScreen(argv, self._accent), self._after_sort)

    def _after_sort(self, result) -> None:
        ok, message, changed = result or (False, "Sort cancelled", False)
        self._last = Text(message, style=_result_style(ok, message))
        if changed:
            self.c.reload(); self._rebuild_sorters(); self._rebuild_actions()
        self._refresh_footer(); self._relayout(); self._render_inspect()
```

The span ChoiceModal's callback calls `self._start_sort(span)` instead of `self._run("sort", span)`.

- [ ] **Step 4: Run to verify it passes.**

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py tests/conftest.py
git commit -m "feat(menu): Sort action runs in-UI via SortProgressScreen"
```

---

# STAGE 4 — Docker download + sorter-row state

### Task 12: Docker-row download badges

**Files:** Modify `scripts/menu_app.py` — `_sorter_text` adds the download badge for docker rows; `scripts/ui.py` adds glyph constants.

- [ ] **Step 1: Write the failing test:**

```python
async def test_docker_row_shows_download_badge(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        sorters = app.query_one("#sorters")
        labels = [sorters.get_option_at_index(i).prompt.plain
                  for i in range(sorters.option_count)]
        ms = next(l for l in labels if "mountainsort5" in l)
        assert "get" in ms.lower() or "⬇" in ms      # not-downloaded badge
```

(The FakeController docker universe must expose `img_present=False` for mountainsort5 — Task 17.)

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** in `_sorter_text` (append after the units/active markers, for docker group only):

```python
        if info.get("group") == "docker":
            if info.get("img_present"):
                t.append("  ✓ ready", style="dim #3fb950")
            elif info.get("downloading") is not None:
                t.append(f"  ⬇ {info['downloading']}%", style=self._accent)
            else:
                t.append("  ⬇ get", style="#d29922")
```

- [ ] **Step 4: Run to verify it passes.**

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py scripts/ui.py tests/test_menu_app.py tests/conftest.py
git commit -m "feat(menu): Docker sorter rows show downloaded/get badge"
```

---

### Task 13: `DownloadProgressScreen` + Enter→download

**Files:** Modify `scripts/menu_app.py` — new modal + the Enter decision table in `_select_sorter`.

- [ ] **Step 1: Write the failing test:**

```python
async def test_enter_on_undownloaded_docker_opens_download(make_app):
    import menu_app
    app = make_app(use_docker=True)         # docker on so the row is selectable
    async with app.run_test() as pilot:
        # move highlight to mountainsort5 then Enter
        app._highlight_sorter_by_name("mountainsort5")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DownloadProgressScreen)
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** `DownloadProgressScreen` (worker **thread**, callbacks marshalled with `app.call_from_thread`):

```python
class DownloadProgressScreen(ModalScreen):
    BINDINGS = [Binding("escape", "close", show=False), Binding("enter", "close", show=False)]

    def __init__(self, controller, name: str, accent: str):
        super().__init__()
        self._c = controller
        self._name = name
        self._accent = accent
        self._pct = 0
        self._status = "starting…"
        self._done = None

    def compose(self) -> ComposeResult:
        with Vertical(id="dldialog"):
            yield Static(f"Downloading {self._name}", id="dltitle")
            yield Static(id="dlbody")
            yield Static("This runs once (~1 GB). Esc to close.", id="dlfoot")

    def on_mount(self) -> None:
        self.query_one("#dldialog").border_title = "DOWNLOAD"
        self._render()
        self.run_worker(self._pull, thread=True, exclusive=True)

    def _pull(self) -> None:
        def on_progress(done, total):
            pct = int(done / total * 100) if total else 0
            self.app.call_from_thread(self._set_pct, pct)
        def on_status(text):
            self.app.call_from_thread(self._set_status, text)
        ok, msg = self._c.download_image(self._name, on_progress, on_status)
        self.app.call_from_thread(self._finish, ok, msg)

    def _set_pct(self, pct): self._pct = pct; self._render()
    def _set_status(self, text): self._status = text; self._render()
    def _finish(self, ok, msg):
        self._done = (ok, msg); self._render()
        self.query_one("#dlfoot", Static).update("Press Enter to close")

    def _render(self):
        t = Text()
        fill = int(self._pct / 100 * 24)
        t.append("█" * fill + "░" * (24 - fill), style=self._accent)
        t.append(f"  {self._pct:3d}%\n", style="dim")
        t.append(self._status + "\n", style="dim")
        if self._done:
            ok, msg = self._done
            t.append(("✓ " if ok else "✗ ") + msg, style="bold " + ("#3fb950" if ok else "#f85149"))
        self.query_one("#dlbody", Static).update(t)

    def action_close(self):
        self.dismiss(self._done or (False, "download still running", False))
```

`_select_sorter` decision table (Enter on a sorter):

```python
    def _select_sorter(self, name: str) -> None:
        info = next((i for i in self.c.infos if i["name"] == name), None)
        if info is None:
            return
        if info.get("group") == "docker" and not info.get("img_present"):
            # download path — ensure docker is up first
            if self.c.docker_status(refresh=False)["running"]:
                self.push_screen(DownloadProgressScreen(self.c, name, self._accent),
                                 self._after_download)
            else:
                self._toggle_docker(offer_from=name)
        elif info.get("runnable"):
            self._set_active_by_name(name)
        elif info.get("group") == "docker":
            self._toggle_docker(offer_from=name)
        else:
            hint = ("needs a GPU build — see Help" if info.get("group") == "gpu"
                    else "not available on this computer")
            self._last = Text(f"{name}: {hint}", style="#f0883e"); self._refresh_footer()

    def _after_download(self, result) -> None:
        ok, message, *_ = (result if isinstance(result, tuple) else (False, str(result)))
        self._last = Text(message, style=_result_style(ok, message))
        self.c.reload(); self._rebuild_sorters(); self._refresh_footer(); self._render_inspect()
```

- [ ] **Step 4: Run to verify it passes.**

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py tests/conftest.py
git commit -m "feat(menu): in-UI Docker image download (DownloadProgressScreen)"
```

---

# STAGE 5 — Manage hub, delete, fallback, docs

### Task 14: `ManageSorterScreen` (single-sorter `x` confirm) + clears

**Files:** Modify `scripts/menu_app.py` — `action_manage_highlighted` opens a confirm modal offering the applicable deletes for the highlighted sorter.

- [ ] **Step 1: Write the failing test:**

```python
async def test_x_opens_manage_for_saved_sorter(make_app):
    import menu_app
    app = make_app()
    async with app.run_test() as pilot:
        app._highlight_sorter_by_name("tridesclous2")   # has saved units
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ManageSorterScreen)
        body = app.screen.query_one("#mgbody").render().plain
        assert "saved" in body.lower()
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** `ManageSorterScreen` (a `ChoiceModal`-style list with only the applicable options) and:

```python
    def action_manage_highlighted(self) -> None:
        if self.focused is not self.query_one("#sorters", OptionList):
            return
        name = self._highlighted_sorter_name()
        info = next((i for i in self.c.infos if i["name"] == name), None)
        if info is None:
            return
        opts = []
        if info.get("img_present"):
            size = (info.get("img_size") or 0) / 1e9
            opts.append(("del_image", f"Delete downloaded image (~{size:.1f} GB)"))
        if info.get("present"):
            opts.append(("clear_sort", f"Clear saved sort ({info['units']}u)"))
        if not opts:
            self._last = Text(f"nothing to delete for {name}", style="dim"); self._refresh_footer(); return
        self.push_screen(ManageSorterScreen(name, opts, self._accent),
                         lambda choice: self._do_manage(name, choice))

    def _do_manage(self, name: str, choice) -> None:
        if choice == "del_image":
            ok, msg = self.c.delete_image(name)
        elif choice == "clear_sort":
            ok, msg = self.c.clear_saved_sort(name)
        else:
            return
        self._last = Text(msg, style=_result_style(ok, msg))
        self.c.reload(); self._rebuild_sorters(); self._refresh_footer()
        self._render_sortbar(self.size.width); self._render_inspect()
```

- [ ] **Step 4: Run to verify it passes.**

- [ ] **Step 5: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py tests/conftest.py
git commit -m "feat(menu): x opens per-sorter manage (delete image / clear saved)"
```

---

### Task 15: `manage` action + `ManageSortersScreen` hub

**Files:** Modify `SpikeInterface_Menu.py` (`_ACTIONS`, `_ACTION_DETAIL`), `tests/conftest.py` (ACTIONS), `scripts/menu_app.py` (`ManageSortersScreen`, `_activate_action` `manage` branch).

- [ ] **Step 1: Write the failing test:**

```python
async def test_manage_action_opens_hub(make_app):
    import menu_app
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.press("right")
        # 'manage' is action index 7 → key "8"
        await pilot.press("8")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.ManageSortersScreen)
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement.** Add to `_ACTIONS` (after `params`):

```python
    ("manage", "Manage sorters", "download images · delete · clear saved sorts", False),
```

and to `_ACTION_DETAIL`:

```python
    "manage": {"what": "Download Docker sorter images, delete downloaded images, "
                       "and clear saved sort outputs — all in one place."},
```

Mirror both in `tests/conftest.py`'s `ACTIONS` (insert `("manage", "Manage sorters", "download · delete", False)` after `params`). `ManageSortersScreen` is a scrollable list of `self.c.infos` rows with per-row keys: `enter`/`g` → push `DownloadProgressScreen` (docker, not present), `x` → `delete_image`, `c` → `clear_saved_sort`, `r` → `self.c.reload()` + rebuild, `escape` → close. On any change call the controller method, then `reload` + re-render the hub list. `_activate_action("manage")` pushes it.

- [ ] **Step 4: Run to verify it passes.** Also update the number-key tests: `params` is now index 6 (`7`), `manage` index 7 (`8`), `verify` index 8 (`9`).

- [ ] **Step 5: Commit**

```bash
git add SpikeInterface_Menu.py scripts/menu_app.py tests/conftest.py tests/test_menu_app.py
git commit -m "feat(menu): Manage sorters action + full management hub"
```

---

### Task 16: Fallback typed menu — Manage sorters

**Files:** Modify `SpikeInterface_Menu.py` — `_menu_fallback` gains a "Manage sorters" option (typed) that lists install/download/saved state and offers download (blocking, prints simple progress), delete image, clear saved sort. Reuse `_pick_compare_pair`-style `ui.select`.

- [ ] **Step 1:** Add a `_manage_sorters_typed(cfg)` helper and wire it into the fallback action loop. (No new test required beyond import-clean + an existing fallback smoke test; add a `test_fallback.py` assertion that the option appears in the menu list.)

- [ ] **Step 2:** Run `uv run python -m pytest tests/test_fallback.py -q` → PASS.

- [ ] **Step 3: Commit**

```bash
git add SpikeInterface_Menu.py tests/test_fallback.py
git commit -m "feat(menu): typed fallback gains a Manage-sorters option"
```

---

### Task 17: Consolidate `FakeController` extensions

**Files:** Modify `tests/conftest.py` — ensure the fake exposes everything the new screens/tests use: `image_state`, `download_image`, `delete_image`, `clear_saved_sort`, `sort_command`, `docker_status`, per-info `img_present`/`img_size`/`image`/`overrides`, and a `use_docker`/`present` constructor knob. Add `make_app(present=True, use_docker=False)` support if the fixture lacks it.

- [ ] **Step 1:** Implement the fake methods to return deterministic values (e.g. `download_image` calls `on_progress(50,100)` then returns `(True, "Downloaded")`; `sort_command` returns `["true"]`). Set `mountainsort5.img_present=False`, give a `spykingcircus` docker row `img_present=True` so badge tests cover both.

- [ ] **Step 2:** Run the **whole** suite:

Run: `uv run python -m pytest tests/ -q`
Expected: PASS (all stages green together).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(menu): extend FakeController for download/delete/sort-modal"
```

---

### Task 18: Docs + final verification

**Files:** Modify `CLAUDE.md` (the menu architecture section), run the full suite + a manual smoke.

- [ ] **Step 1:** Rewrite the `SpikeInterface_Menu.py` / `menu_app.py` architecture paragraphs in `CLAUDE.md` to describe: the three-panel layout (SORTERS + ACTIONS + bottom INSPECTING), the always-on DATA/SORT banner, focus-driven nav (no accordion), in-UI sorting via `SortProgressScreen` + `run_sorting.py --progress json` + `scripts/sort_progress.py`, in-UI Docker download/delete + the `Manage sorters` hub, and the new `x` key. Remove the accordion/`#activebar`/quiet-statusline descriptions.

- [ ] **Step 2:** Full verification:

```bash
uv run python -m pytest tests/ -q                       # all green
uv run python -c "import sys; sys.path.insert(0,'scripts'); import menu_app, sort_progress, run_sorting, sorters"  # imports clean
uv run python SpikeInterface_Menu.py                     # manual: panels, banner, navigate, Sort modal, Manage hub
```

Expected: suite PASS; the dashboard shows both panels + banner; Sort opens the in-UI progress modal; Manage opens the hub.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md describes the three-panel in-UI menu overhaul"
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Three-panel layout + DATA/SORT banner → Tasks 5–9. ✓
- In-UI sorting (structured + spinner/heartbeat) → Tasks 1, 2, 10, 11. ✓
- Docker download in sorters area, separate from sort → Tasks 12, 13. ✓
- Easier install visibility → Tasks 4 (catalog state), 12 (badges), 7 (SORT bar readiness). ✓
- Delete downloaded images + clear saved sorts → Tasks 3, 4, 14, 15. ✓
- "Manage sorters" ACTIONS hub → Task 15. ✓
- Keep crest + `m` toggle → preserved (CSS/relayout keep `#crest`, `m` binding retained). ✓
- Fallback parity-lite → Task 16. ✓
- Tests + docs → Tasks 17, 18 + per-task TDD. ✓

**Placeholder scan:** No "TBD/TODO"; UI tasks that can't show every line (large rewrite) give the exact new methods/CSS/compose and exact tests; the remaining adaptation (porting render-helper targets from `#explainbody`→`#inspectbody`) is spelled out. The `~X GB` is a runtime value, not a placeholder.

**Type consistency:** `sort_progress.emit/parse_line/new_state/reduce`, `Reporter.{phase,detail,bar,heartbeat,metrics,done_ok,error}`, controller `{image_state,download_image,delete_image,clear_saved_sort,sort_command}`, registry `{delete_docker_image,image_size}`, screens `{SortProgressScreen,DownloadProgressScreen,ManageSortersScreen,ManageSorterScreen}` — names used consistently across tasks. Catalog keys `img_present`/`img_size`/`image` consistent between Task 4 (producer) and Tasks 7/12/14 (consumers).
