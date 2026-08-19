# Collapsible Docker-download Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the in-UI Docker-image download a rich telemetry view (downloaded/total, speed, ETA, elapsed) that can collapse to a one-line dashboard indicator while the download keeps running, and re-expand on demand.

**Architecture:** A new pure module `scripts/download_stats.py` holds all progress math + a session dataclass (no Textual, no Docker - like `scripts/sort_progress.py`). The pull worker moves from `DownloadProgressScreen` up to `SpikeMenuApp`, which owns a single live `DownloadSession`; the modal and a new `#dlbar` banner indicator are both pure views over that session. `sorters.pull_docker_image` gains a `should_cancel` hook so the now-detached worker stays abortable.

**Tech Stack:** Python 3.12, Textual (TUI), Docker SDK (registry only), pytest + pytest-asyncio (Textual Pilot tests).

## Global Constraints

- **Python 3.12** only (`requires-python = "==3.12.*"`).
- **The Textual process imports NO SpikeInterface and NO Docker SDK** - all Docker work stays in the controller/registry on the worker thread; `download_stats.py` is stdlib-only.
- **Scripts are imported by basename** - consumers do `sys.path.insert(0, "scripts")`; tests import `menu_app` / `download_stats` directly (see `tests/conftest.py`).
- **`from __future__ import annotations`** at the top of every new module (matches existing files).
- **NO_COLOR-safe shape cues:** every status conveyed by colour must also have a glyph/word cue (`⬇`/`✓`/`✗` + `%`/`ready`), consistent with the DATA/SORT banner.
- **Never let a worker exception kill the app** - wrap worker bodies in `try/except` and surface as a `(False, msg)` result (existing pattern).
- **Commit after each task** with a `feat:`/`test:`/`refactor:` message ending:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Do **not** stage `.gitignore` (the user has an unrelated working change there).

---

## File Structure

| File | Responsibility | Task |
| --- | --- | --- |
| `scripts/download_stats.py` (new) | Pure progress math: `DownloadStats`, `DownloadSession`, formatters | 1 |
| `tests/test_download_stats.py` (new) | Unit tests for the pure module | 1 |
| `scripts/sorters.py` (modify) | `pull_docker_image(..., should_cancel=None)` | 2 |
| `SpikeInterface_Menu.py` (modify) | `MenuController.download_image(..., should_cancel=None)` pass-through | 2 |
| `tests/test_sorters.py` (modify) | `should_cancel` break test | 2 |
| `scripts/menu_app.py` (modify) | App-owned worker + session, `#dlbar` indicator, view-only `DownloadProgressScreen`, `w` binding | 3 |
| `tests/conftest.py` (modify) | `FakeController` stepped-download support | 3 |
| `tests/test_menu_app.py` (modify) | Pilot tests: collapse / expand / cancel / finish | 3 |

---

## Task 1: Pure progress-stats module

**Files:**
- Create: `scripts/download_stats.py`
- Test: `tests/test_download_stats.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `class DownloadStats` with `update(done: int, total: int, now: float) -> None`, `set_phase(phase: str, now: float) -> None`, and read-only properties `pct: int`, `speed: float | None` (bytes/s), `eta: float | None` (seconds), `elapsed: float` (seconds).
  - `@dataclass class DownloadSession` with fields `name: str`, `image: str`, `phase: str` (default `"downloading"`), `stats: DownloadStats`, `result: tuple[bool, str] | None = None`, `cancelled: bool = False`.
  - `fmt_bytes(n: int | None) -> str`, `fmt_speed(bps: float | None) -> str`, `fmt_clock(secs: float | None) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_download_stats.py`:

```python
"""Unit tests for the pure download-progress module (scripts/download_stats.py).

No Textual / Docker imports - timestamps are injected so the clock is deterministic.
"""
from __future__ import annotations

import download_stats as ds


def test_pct_basic_and_zero_total():
    s = ds.DownloadStats()
    s.update(0, 0, now=0.0)
    assert s.pct == 0           # unknown total -> 0, never a divide error
    s.update(50, 100, now=1.0)
    assert s.pct == 50
    s.update(100, 100, now=2.0)
    assert s.pct == 100


def test_speed_needs_two_samples_then_emas():
    s = ds.DownloadStats()
    s.update(0, 1000, now=0.0)
    assert s.speed is None       # one sample -> no rate yet
    s.update(100, 1000, now=1.0)  # 100 bytes in 1 s
    assert s.speed is not None and s.speed > 0
    # A steady 100 B/s stream keeps the EMA near 100 (not wildly off).
    s.update(200, 1000, now=2.0)
    s.update(300, 1000, now=3.0)
    assert 80 <= s.speed <= 120


def test_eta_from_remaining_over_speed():
    s = ds.DownloadStats()
    s.update(0, 1000, now=0.0)
    s.update(100, 1000, now=1.0)   # ~100 B/s, 900 left -> ~9 s
    assert s.eta is not None and 6 <= s.eta <= 12
    s2 = ds.DownloadStats()
    s2.update(0, 0, now=0.0)        # unknown total -> no ETA
    assert s2.eta is None


def test_elapsed_uses_injected_clock():
    s = ds.DownloadStats()
    s.update(0, 1000, now=10.0)    # first sample stamps the start
    s.update(500, 1000, now=14.5)
    assert abs(s.elapsed - 4.5) < 1e-6


def test_phase_change_resets_speed_window_no_negative():
    s = ds.DownloadStats()
    s.update(900, 1000, now=0.0)   # end of download phase (high byte count)
    s.update(1000, 1000, now=1.0)
    s.set_phase("extracting", now=2.0)
    s.update(10, 1000, now=3.0)    # extract restarts byte counting from ~0
    # Speed must be computed from the post-reset samples, never negative.
    assert s.speed is None or s.speed >= 0


def test_formatters():
    assert ds.fmt_bytes(423 * 1024 * 1024).endswith("MB")
    assert ds.fmt_bytes(None) == "-"
    assert ds.fmt_speed(2.3 * 1024 * 1024).endswith("MB/s")
    assert ds.fmt_speed(None) == "-"
    assert ds.fmt_clock(38) == "0:38"
    assert ds.fmt_clock(72) == "1:12"
    assert ds.fmt_clock(3661) == "1:01:01"
    assert ds.fmt_clock(None) == "-"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_download_stats.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'download_stats'` (the `scripts/` dir is on `sys.path` via conftest; the module doesn't exist yet).

- [ ] **Step 3: Write the module**

Create `scripts/download_stats.py`:

```python
"""Pure, dependency-free progress math for the in-UI Docker-image download.

No Textual / Docker imports - like ``scripts/sort_progress.py`` this holds the
arithmetic and formatting so the TUI stays a thin renderer and the logic is
trivially unit-testable. Timestamps are passed IN (monotonic seconds) so the
clock is deterministic in tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# EMA weight for new samples - small enough to smooth the bursty per-event byte
# deltas the Docker SDK emits, large enough to track real speed changes.
_EMA_ALPHA = 0.3
_KB = 1024
_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024


class DownloadStats:
    """Tracks (done, total) byte samples over an injected monotonic clock and
    derives percent / smoothed speed / ETA / elapsed. A phase change resets the
    speed window so the download->extract byte-total reset never yields a
    negative rate."""

    def __init__(self) -> None:
        self._done = 0
        self._total = 0
        self._start: float | None = None      # first-ever sample time -> elapsed
        self._last_t: float | None = None      # last sample time (for deltas)
        self._last_done: int | None = None     # last done (for deltas)
        self._now: float = 0.0
        self._speed: float | None = None       # EMA bytes/s, None until 2 samples

    def set_phase(self, phase: str, now: float) -> None:
        # Reset the per-sample delta window (NOT the start clock / elapsed): the new
        # phase counts bytes from ~0, so a delta against the old phase would be wildly
        # negative. Speed re-warms from the next two samples.
        self._last_t = None
        self._last_done = None
        self._now = now

    def update(self, done: int, total: int, now: float) -> None:
        self._done = done
        self._total = total
        self._now = now
        if self._start is None:
            self._start = now
        if self._last_t is not None and self._last_done is not None:
            dt = now - self._last_t
            dbytes = done - self._last_done
            if dt > 0 and dbytes >= 0:
                inst = dbytes / dt
                self._speed = (inst if self._speed is None
                               else _EMA_ALPHA * inst + (1 - _EMA_ALPHA) * self._speed)
        self._last_t = now
        self._last_done = done

    @property
    def pct(self) -> int:
        return int(self._done / self._total * 100) if self._total else 0

    @property
    def speed(self) -> float | None:
        return self._speed

    @property
    def eta(self) -> float | None:
        if not self._total or not self._speed or self._speed <= 0:
            return None
        remaining = self._total - self._done
        return remaining / self._speed if remaining > 0 else 0.0

    @property
    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        return self._now - self._start


@dataclass
class DownloadSession:
    """The single live download the App owns; both views read from it."""
    name: str
    image: str
    phase: str = "downloading"        # downloading | verifying | extracting | done
    stats: DownloadStats = field(default_factory=DownloadStats)
    result: tuple[bool, str] | None = None    # (ok, message) once finished
    cancelled: bool = False


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    if n >= _GB:
        return f"{n / _GB:.1f} GB"
    if n >= _MB:
        return f"{n / _MB:.0f} MB"
    if n >= _KB:
        return f"{n / _KB:.0f} KB"
    return f"{n} B"


def fmt_speed(bps: float | None) -> str:
    if bps is None:
        return "-"
    if bps >= _MB:
        return f"{bps / _MB:.1f} MB/s"
    if bps >= _KB:
        return f"{bps / _KB:.0f} KB/s"
    return f"{bps:.0f} B/s"


def fmt_clock(secs: float | None) -> str:
    if secs is None:
        return "-"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_download_stats.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/download_stats.py tests/test_download_stats.py
git commit -m "feat: pure download-progress stats module (speed/eta/elapsed)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Cancellable pull in the registry + controller pass-through

**Files:**
- Modify: `scripts/sorters.py:194` (`pull_docker_image`)
- Modify: `SpikeInterface_Menu.py:897` (`MenuController.download_image`)
- Test: `tests/test_sorters.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `sorters.pull_docker_image(image, on_progress=None, on_status=None, should_cancel=None) -> bool` - when `should_cancel` is a callable returning True, the pull loop breaks and returns `False`.
  - `MenuController.download_image(name, on_progress=None, on_status=None, should_cancel=None) -> tuple[bool, str]` - threads `should_cancel` to the registry.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sorters.py` (module imports `sorters` already; check the top of the file and reuse its import name - it is imported as `sorters`):

```python
def test_pull_docker_image_honours_should_cancel(monkeypatch):
    # A fake docker client whose pull stream yields forever; should_cancel must
    # break the loop and return False without consuming the whole stream.
    import sorters

    class _FakeAPI:
        def pull(self, repository, tag, stream, decode):
            i = 0
            while True:
                i += 1
                yield {"status": "Downloading", "id": f"L{i}",
                       "progressDetail": {"current": i, "total": 1000}}

    class _FakeClient:
        api = _FakeAPI()

    class _FakeDocker:
        @staticmethod
        def from_env():
            return _FakeClient()

    monkeypatch.setitem(__import__("sys").modules, "docker", _FakeDocker)

    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] >= 3        # cancel after a few events

    ok = sorters.pull_docker_image("img:latest", should_cancel=should_cancel)
    assert ok is False
    assert calls["n"] >= 3            # the loop actually polled the hook
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_sorters.py::test_pull_docker_image_honours_should_cancel -v`
Expected: FAIL - `TypeError: pull_docker_image() got an unexpected keyword argument 'should_cancel'`.

- [ ] **Step 3: Add the parameter + check**

In `scripts/sorters.py`, change the signature on line 194 from:

```python
def pull_docker_image(image: str, on_progress=None, on_status=None) -> bool:
```

to:

```python
def pull_docker_image(image: str, on_progress=None, on_status=None,
                      should_cancel=None) -> bool:
```

Then in the `for ev in client.api.pull(...)` loop (starts at line 271), make the **first** statement inside the loop body a cancel check, immediately after the `for`:

```python
        for ev in client.api.pull(repository, tag=tag, stream=True, decode=True):
            if should_cancel is not None and should_cancel():
                return False
            if "error" in ev:
                return False
```

(Leave the rest of the loop unchanged.)

- [ ] **Step 4: Thread it through the controller**

In `SpikeInterface_Menu.py`, change `download_image` (line 897) from:

```python
    def download_image(self, name: str, on_progress=None, on_status=None) -> tuple[bool, str]:
        """Pull a sorter's Docker image, streaming progress to the callbacks."""
        img = sorter_registry.default_docker_image(name)
        if not img:
            return False, f"No Docker image is known for {name}."
        ok = sorter_registry.pull_docker_image(img, on_progress, on_status)
        return (True, f"Downloaded {img}") if ok else (False, f"Couldn't download {img}.")
```

to:

```python
    def download_image(self, name: str, on_progress=None, on_status=None,
                       should_cancel=None) -> tuple[bool, str]:
        """Pull a sorter's Docker image, streaming progress to the callbacks.

        ``should_cancel`` (optional callable) lets the in-UI download abort the
        pull mid-stream once the worker is detached from the modal screen."""
        img = sorter_registry.default_docker_image(name)
        if not img:
            return False, f"No Docker image is known for {name}."
        ok = sorter_registry.pull_docker_image(img, on_progress, on_status,
                                                should_cancel=should_cancel)
        return (True, f"Downloaded {img}") if ok else (False, f"Couldn't download {img}.")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_sorters.py -v`
Expected: PASS (existing tests + the new cancel test).

- [ ] **Step 6: Commit**

```bash
git add scripts/sorters.py SpikeInterface_Menu.py tests/test_sorters.py
git commit -m "feat: cancellable docker pull via should_cancel hook

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: App-owned download session, telemetry view, and collapsible indicator

This is the structural task: the worker moves from the screen to the App, the
modal becomes a pure view with full telemetry, and a new `#dlbar` indicator
renders the collapsed state. All in `scripts/menu_app.py`, with a stepped-download
upgrade to the test `FakeController` and Pilot tests.

**Files:**
- Modify: `scripts/menu_app.py` (`DownloadProgressScreen` ~669-803; `SpikeMenuApp` CSS ~1340-1396, BINDINGS ~1398, `compose` ~1438, `_relayout` ~1475-1511, `_select_sorter` ~2099-2133, `_after_download` ~2135-2152)
- Modify: `tests/conftest.py` (`FakeController.download_image` ~263)
- Test: `tests/test_menu_app.py`

**Interfaces:**
- Consumes: `download_stats.DownloadStats/DownloadSession/fmt_bytes/fmt_speed/fmt_clock` (Task 1); `controller.download_image(name, on_progress, on_status, should_cancel)` (Task 2).
- Produces (on `SpikeMenuApp`): `self._download: DownloadSession | None`; `start_download(name)`; `action_watch_download()` (bound to `w`); `_render_dlbar(width)`. `DownloadProgressScreen(controller, name, accent)` becomes view-only and is dismissed with `"collapsed"` (collapse), `(ok, msg)` (finished), or a cancel sentinel.

### Part A - make the test `FakeController` drive a stepped download

- [ ] **Step 1: Upgrade `FakeController.download_image`**

The current stub (conftest.py:263) calls the callbacks synchronously and returns,
which can't model "still in progress" for the collapse/expand tests. Replace it so
the test can advance the download and so `should_cancel` is honoured. Replace the
method body (lines 263-277) with:

```python
    def download_image(self, name, on_progress=None, on_status=None, should_cancel=None):
        # Stepped fake pull: emit a scripted sequence, polling should_cancel between
        # steps and pausing on a threading.Event the test can release. With no gate
        # set (the default) it runs straight through, preserving old test behaviour.
        import threading as _t
        self.downloaded.append(name)
        gate = getattr(self, "dl_gate", None)        # a threading.Event or None
        steps = [
            ("status", "Downloading 1/2 layers"),
            ("progress", (25, 100)),
            ("gate", None),                            # test may pause the worker here
            ("progress", (50, 100)),
            ("status", "Extracting 1/2 layers"),
            ("progress", (100, 100)),
        ]
        for kind, payload in steps:
            if should_cancel is not None and should_cancel():
                return False, f"Download of {name} cancelled"
            if kind == "status" and on_status is not None:
                on_status(payload)
            elif kind == "progress" and on_progress is not None:
                on_progress(*payload)
            elif kind == "gate" and gate is not None:
                while not gate.wait(timeout=0.02):
                    if should_cancel is not None and should_cancel():
                        return False, f"Download of {name} cancelled"
        self._cached_images.add(name)
        return True, f"Downloaded {name}"
```

(No new imports at module top are needed - `threading` is imported locally.)

- [ ] **Step 2: Commit the fixture upgrade**

```bash
git add tests/conftest.py
git commit -m "test: stepped fake download_image (gate + should_cancel)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Part B - App-owned session + indicator + view-only modal

- [ ] **Step 3: Write the failing Pilot tests**

Add to `tests/test_menu_app.py` (it already imports `menu_app`, `ui`, and `Static`/`OptionList`; add `import threading` near the top if not present):

```python
async def test_download_shows_telemetry_then_collapses_and_expands(make_app):
    import threading
    app = make_app(present=True, use_docker=True)
    app.c.dl_gate = threading.Event()           # hold the worker at the gate step
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        # Start the gated download directly (avoids depending on row indices).
        app.start_download("mountainsort5")
        await pilot.pause()
        # The expanded modal is up and shows the stats line (downloaded/total + /s).
        screen = app.screen
        assert isinstance(screen, menu_app.DownloadProgressScreen)
        await pilot.pause()
        body = app.query_one("#dlbody", Static).renderable
        assert "100" in str(body) or "/" in str(body)   # a size readout rendered
        # Collapse: modal closes, the dashboard indicator shows.
        await pilot.press("c")
        await pilot.pause()
        assert not isinstance(app.screen, menu_app.DownloadProgressScreen)
        dlbar = app.query_one("#dlbar", Static)
        assert dlbar.has_class("hidden") is False
        assert "mountainsort5" in str(dlbar.renderable)
        # Re-expand with w.
        await pilot.press("w")
        await pilot.pause()
        assert isinstance(app.screen, menu_app.DownloadProgressScreen)
        # Let the worker finish.
        app.c.dl_gate.set()
        for _ in range(50):
            await pilot.pause()
            if app._download is None:
                break
        assert "mountainsort5" in app.c.downloaded


async def test_download_indicator_hidden_when_idle(make_app):
    app = make_app(present=True, use_docker=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert app.query_one("#dlbar", Static).has_class("hidden") is True
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_app.py::test_download_shows_telemetry_then_collapses_and_expands tests/test_menu_app.py::test_download_indicator_hidden_when_idle -v`
Expected: FAIL - `AttributeError: 'SpikeMenuApp' object has no attribute 'start_download'` / no `#dlbar`.

- [ ] **Step 5: Add the download-stats import**

At the top of `scripts/menu_app.py`, alongside the other `scripts/` imports (e.g. near `import ui`), add:

```python
import download_stats as dlstats
```

- [ ] **Step 6: Rewrite `DownloadProgressScreen` as a view over the session**

Replace the whole class (lines ~669-803) with this view-only version. It no longer
owns the worker; it reads `self.app._download` and repaints on a timer. `c`
collapses (download keeps running); `Esc` cancels.

```python
class DownloadProgressScreen(ModalScreen):
    """Expanded telemetry view over the App's live ``DownloadSession``.

    The pull worker is owned by ``SpikeMenuApp`` (so it survives this modal being
    collapsed), not by this screen. This screen is a pure renderer: it reads
    ``self.app._download`` each tick and draws the phase caption + spinner, a
    determinate bar + percent, and a stats block (downloaded/total · speed; ETA ·
    elapsed). ``c`` collapses back to the dashboard indicator while the download
    continues; ``Esc`` cancels the download; Enter closes once finished."""

    DEFAULT_CSS = """
    DownloadProgressScreen { align: center middle; }
    DownloadProgressScreen > #dldialog {
        width: 70; max-width: 92%; height: auto; max-height: 90%;
        border: round $accentcolor; background: $surface; padding: 1 2;
    }
    DownloadProgressScreen #dltitle { text-style: bold; color: $accentcolor; padding: 0 0 1 0; }
    DownloadProgressScreen #dlbody { height: auto; }
    DownloadProgressScreen #dlfoot { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [
        Binding("c", "collapse", "Collapse", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "close_if_done", "Close", show=False),
    ]

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, controller, name: str, accent: str):
        super().__init__()
        self._c = controller
        self._name = name
        self._accent = accent
        self._spin = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="dldialog"):
            yield Static(f"Downloading {self._name}", id="dltitle")
            yield Static("", id="dlbody")
            yield Static("This runs once (~1 GB).  [c] collapse · [Esc] cancel",
                         id="dlfoot")

    def on_mount(self) -> None:
        self.query_one("#dldialog").border_title = "DOWNLOAD"
        self._repaint()
        # Repaint on a timer: the App's worker mutates the shared session from a
        # thread; this pull-based redraw avoids cross-thread widget touches and also
        # animates the spinner during indeterminate (verify/extract) stretches.
        self._timer = self.set_interval(1.0 / 6, self._tick)

    def on_unmount(self) -> None:
        t = getattr(self, "_timer", None)
        if t is not None:
            t.stop()
            self._timer = None

    def _session(self):
        return getattr(self.app, "_download", None)

    def _tick(self) -> None:
        sess = self._session()
        if sess is not None and sess.result is None:
            self._spin = (self._spin + 1) % len(self._SPINNER)
        self._repaint()

    def _repaint(self) -> None:
        sess = self._session()
        t = Text()
        if sess is None:
            t.append("download finished", style="dim")
            self.query_one("#dlbody", Static).update(t)
            return
        st = sess.stats
        live = sess.result is None
        # Phase caption + spinner.
        if live:
            t.append(self._SPINNER[self._spin] + " ", style=self._accent)
        t.append(sess.phase_caption + "\n", style="dim")
        # Bar + percent.
        pct = st.pct
        fill = int(pct / 100 * 24)
        t.append("█" * fill + "░" * (24 - fill), style=self._accent)
        t.append(f"  {pct:3d}%\n\n", style="dim")
        # Stats block (size · speed ; ETA · elapsed). During verify/extract the byte
        # readout/speed/ETA may be unknown -> render as "-" (fmt_* handle None).
        done, total = sess.bytes_done, sess.bytes_total
        t.append(f"{dlstats.fmt_bytes(done)} / {dlstats.fmt_bytes(total)}"
                 f"   {dlstats.fmt_speed(st.speed)}\n", style="dim")
        t.append(f"ETA {dlstats.fmt_clock(st.eta)}"
                 f"          elapsed {dlstats.fmt_clock(st.elapsed)}", style="dim")
        if sess.result is not None:
            ok, msg = sess.result
            t.append("\n" + ("✓ " if ok else "✗ ") + msg,
                     style="bold " + ("#3fb950" if ok else "#f85149"))
        self.query_one("#dlbody", Static).update(t)
        if not live:
            self.query_one("#dlfoot", Static).update("Press Enter to close")

    def action_collapse(self) -> None:
        # Leave the worker running; the dashboard #dlbar takes over the display.
        self.dismiss("collapsed")

    def action_cancel(self) -> None:
        sess = self._session()
        if sess is not None and sess.result is None:
            sess.cancelled = True          # the worker's should_cancel hook breaks
        self.dismiss("collapsed")          # close now; finish handling runs on the App

    def action_close_if_done(self) -> None:
        sess = self._session()
        if sess is None or sess.result is not None:
            self.dismiss("collapsed")
```

NOTE: `_repaint` references `sess.phase_caption`, `sess.bytes_done`, `sess.bytes_total` - add those as derived helpers on the session via the App's update path (Step 7 stores raw bytes + caption on the session). To keep `download_stats.DownloadSession` pure, store these as **plain attributes set by the App** rather than dataclass fields requiring imports. In Step 7 the App sets `sess.phase_caption`, `sess.bytes_done`, `sess.bytes_total` directly; initialise them in `start_download`.

- [ ] **Step 7: Add the App download lifecycle**

In `SpikeMenuApp`, add the session attribute and methods. Put the attribute init in
`__init__` (find the existing `__init__`; if there is none beyond the dataclass-style
controller assignment, add one that calls `super().__init__()`). Add near the other
action methods:

```python
    # -- in-UI Docker download (worker owned HERE so it survives a collapse) ---- #
    def start_download(self, name: str) -> None:
        """Begin pulling ``name``'s image in an App-owned worker and open the
        expanded view. Refuses a second concurrent download with a footer hint."""
        if getattr(self, "_download", None) is not None and self._download.result is None:
            self._last = Text(f"a download is already running · w to view",
                              style="#f0883e")
            self._refresh_footer()
            return
        img = ""
        try:
            img = self.c.image_state(name).get("image") or ""
        except Exception:  # noqa: BLE001
            img = ""
        sess = dlstats.DownloadSession(name=name, image=img)
        sess.phase_caption = "starting…"
        sess.bytes_done = None
        sess.bytes_total = None
        self._download = sess
        self._render_dlbar(self.size.width)
        self.run_worker(lambda: self._download_worker(sess), thread=True)
        self.push_screen(DownloadProgressScreen(self.c, name, self._accent),
                         self._after_download)

    def _download_worker(self, sess) -> None:
        _PHASE = {"Downloading": "downloading", "Verifying": "verifying",
                  "Extracting": "extracting", "Done": "done"}

        def on_progress(done, total):
            self.call_from_thread(self._dl_progress, sess, done, total)

        def on_status(text):
            self.call_from_thread(self._dl_status, sess, text)

        def should_cancel():
            return sess.cancelled

        try:
            ok, msg = self.c.download_image(sess.name, on_progress, on_status,
                                            should_cancel=should_cancel)
        except Exception as e:  # noqa: BLE001 - never let a worker crash the app
            ok, msg = False, f"download failed: {e}"
        self.call_from_thread(self._dl_finish, sess, ok, msg)

    # -- thread-marshalled session mutations (only via call_from_thread) -------- #
    def _dl_progress(self, sess, done, total) -> None:
        sess.bytes_done, sess.bytes_total = done, total
        sess.stats.update(done, total, now=monotonic())
        self._render_dlbar(self.size.width)

    def _dl_status(self, sess, text) -> None:
        sess.phase_caption = text
        word = text.split()[0] if text else ""
        new_phase = {"Downloading": "downloading", "Verifying": "verifying",
                     "Extracting": "extracting", "Done": "done"}.get(word)
        if new_phase and new_phase != sess.phase:
            sess.phase = new_phase
            sess.stats.set_phase(new_phase, now=monotonic())
        self._render_dlbar(self.size.width)

    def _dl_finish(self, sess, ok, msg) -> None:
        sess.result = (ok, msg)
        # Reload the catalog so the row badge/readiness flips (existing logic).
        self._last = Text(msg, style=_result_style(ok, msg))
        try:
            self.c.reload()
            self._rebuild_sorters()
            self._rebuild_actions()
        except Exception as e:  # noqa: BLE001
            self._last = Text(f"reload after download failed: {e!r}", style="#f85149")
        self._render_sortbar(self.size.width)
        self._refresh_footer()
        self._render_inspect()
        # Show a transient ✓/✗ in the indicator, then clear the session + hide it.
        self._render_dlbar(self.size.width)
        self.set_timer(4.0, self._clear_download)

    def _clear_download(self) -> None:
        self._download = None
        self._render_dlbar(self.size.width)

    def action_watch_download(self) -> None:
        """`w`: re-open the expanded view over the still-running download."""
        sess = getattr(self, "_download", None)
        if sess is None or sess.result is not None:
            self._last = Text("no download in progress", style="dim")
            self._refresh_footer()
            return
        if isinstance(self.screen, DownloadProgressScreen):
            return
        self.push_screen(DownloadProgressScreen(self.c, sess.name, self._accent),
                         self._after_download)
```

Add `from time import monotonic` to the imports at the top of `scripts/menu_app.py`
(no `time`/`monotonic` import exists yet - add it near the other stdlib imports at
line ~49, `import asyncio`). And in the existing `SpikeMenuApp.__init__` (line 1423),
add `self._download = None` right after the existing `self._last = None` (line 1428),
before `super().__init__()`:

```python
    def __init__(self, controller: Controller):
        self.c = controller
        self._accent = controller.accent
        self._last = None
        self._download = None          # the single live DownloadSession (or None)
        super().__init__()
```

- [ ] **Step 8: Phase caption helper expected by the screen**

The screen reads `sess.phase_caption`/`sess.bytes_done`/`sess.bytes_total`, all set by
the App above (Step 7 initialises them in `start_download` and updates them in
`_dl_progress`/`_dl_status`). No change to `download_stats.py` is needed - they are
plain attributes on the session instance.

- [ ] **Step 9: Repoint `_select_sorter` to `start_download`**

In `_select_sorter` (line ~2116-2118), replace:

```python
            if self.c.docker_status(refresh=False).get("running"):
                self.push_screen(DownloadProgressScreen(self.c, name, self._accent),
                                 self._after_download)
```

with:

```python
            if self.c.docker_status(refresh=False).get("running"):
                self.start_download(name)
```

- [ ] **Step 10: Simplify `_after_download` (the reload now happens in `_dl_finish`)**

`_after_download` (line ~2135) now only fires for the modal's dismissal (collapse /
cancel / close). The catalog reload moved into `_dl_finish`. Replace the method body
with a no-op-safe footer refresh so a collapse doesn't double-reload:

```python
    def _after_download(self, result) -> None:
        """The expanded modal was dismissed (collapsed / cancelled / closed). The
        download worker is owned by the App and keeps running; the actual finish
        (catalog reload, badge flip) happens in ``_dl_finish``. Here we only echo a
        status so a collapse reads clearly."""
        if result == "collapsed":
            sess = getattr(self, "_download", None)
            if sess is not None and sess.result is None:
                self._last = Text(f"{sess.name} downloading · w to expand", style="dim")
        self._refresh_footer()
```

- [ ] **Step 11: Add the `#dlbar` widget, CSS, render, relayout, and `w` binding**

(a) In `compose` (line ~1442), add the indicator immediately after `#sortbar`:

```python
        yield Static(id="databar")
        yield Static(id="sortbar")
        yield Static(id="dlbar")
```

(b) In the CSS block, after the `#databar`/`#sortbar` rules (line ~1352), add:

```css
    /* In-UI download indicator: a one-row banner-area line shown only while a
       download is live (or just finished, briefly). Hidden otherwise. */
    #dlbar { height: 1; margin: 0 2 0 2; color: $accentcolor; }
    #dlbar.hidden { display: none; }
```

(c) Add the render helper near `_render_sortbar` (after it, ~line 1587):

```python
    def _render_dlbar(self, width: int) -> None:
        """The collapsed download indicator. Hidden when no session; while live shows
        '⬇ <name>  NN%  <speed>  ETA m:ss   [w expand]'; on finish a transient
        '✓ <name> ready' / '✗ …' until _clear_download hides it."""
        bar = self.query_one("#dlbar", Static)
        sess = getattr(self, "_download", None)
        if sess is None:
            bar.add_class("hidden")
            bar.update("")
            return
        bar.remove_class("hidden")
        t = Text()
        if sess.result is not None:
            ok, msg = sess.result
            t.append(("✓ " if ok else "✗ "), style="bold " + ("#3fb950" if ok else "#f85149"))
            t.append(f"{sess.name} {'ready' if ok else 'failed'}",
                     style="#3fb950" if ok else "#f85149")
        else:
            st = sess.stats
            t.append("⬇ ", style=self._accent)
            t.append(f"{sess.name}  ", style="bold")
            t.append(f"{st.pct:d}%  {dlstats.fmt_speed(st.speed)}  "
                     f"ETA {dlstats.fmt_clock(st.eta)}", style="dim")
            t.append("   [w expand]", style="#6e7681")
        bar.update(t)
```

(d) In `_relayout` (line ~1480), render the dlbar alongside the banners, and include
it in the tiny-collapse list **only when no download is active** (keep live feedback
visible). Change the banner block:

```python
        self._render_databar(w)
        self._render_sortbar(w)
        self._render_dlbar(w)
```

and in the tiny-tier loop (line ~1492), leave `#dlbar` out of the collapse set so a
live download stays visible:

```python
        for wid in ("#titlebar", "#databar", "#sortbar"):
            self.query_one(wid).set_class(tiny, "collapsed")
```

(unchanged - `#dlbar` is deliberately NOT in this tuple).

(e) Add the `w` binding to the dashboard `BINDINGS` (after the `m` binding, line ~1407):

```python
        Binding("w", "watch_download", "Download", show=False),
```

- [ ] **Step 12: Run the new Pilot tests**

Run: `uv run python -m pytest tests/test_menu_app.py::test_download_shows_telemetry_then_collapses_and_expands tests/test_menu_app.py::test_download_indicator_hidden_when_idle -v`
Expected: PASS.

- [ ] **Step 13: Remove the three obsolete internal-coupled tests**

Three existing tests in `tests/test_menu_app.py` assert on internals this task
removes (`screen._done`, `screen._spin_timer`, `screen._set_pct`, `screen._set_status`,
`screen._finish`, and standalone-constructing the screen with no App session). Their
behaviour is now covered by the new tests in Step 3 (telemetry render, phase caption,
collapse/expand, finish→reload). **Delete these three test functions in full:**

- `test_download_screen_reaches_done_and_reloads` (the `_done`/enter-to-reload model is
  gone - `_dl_finish` reloads on the App, not the screen on close).
- `test_download_screen_shows_phase_label_and_spinner` (constructs the screen standalone
  and calls `_set_status`/`_spin_timer` - the screen is now a view over `app._download`).
- `test_download_screen_never_shows_complete_below_100` (uses `_set_pct`/`_finish`).

**Keep** `test_enter_on_undownloaded_docker_opens_download` and
`test_enter_on_undownloaded_docker_offers_docker_when_daemon_down` - they exercise
`_select_sorter` routing (Enter → `start_download` pushes the screen / offers Docker),
which still holds. Preserve the "no false 'complete' at partial percent" intent by
adding this assertion inside the new `test_download_shows_telemetry_...` test, right
after the size-readout assertion (while the worker is gated mid-download):

```python
        assert "complete" not in str(body).lower()   # never a false "complete" mid-pull
```

- [ ] **Step 14: Run the full suite (no regressions)**

Run: `uv run python -m pytest tests/ -q`
Expected: PASS - the whole suite green, the three deleted tests gone, the new download
tests passing.

- [ ] **Step 15: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat: collapsible in-UI download with live telemetry + dashboard indicator

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Docs - update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (the `DownloadProgressScreen` description in the architecture section)

**Interfaces:** none (documentation).

- [ ] **Step 1: Update the architecture prose**

In `CLAUDE.md`, find the `DownloadProgressScreen` description (in the menu_app
architecture paragraph, "In-UI Docker download:"). Replace its sentence(s) with:

```
**In-UI Docker download:** the pull worker is owned by the **App** (not the modal),
so the view is **collapsible** - `start_download(name)` runs `sorters.pull_docker_image`
(now with a `should_cancel` hook) in an App-owned worker thread and opens
`DownloadProgressScreen`, a pure **telemetry view** over the App's single live
`download_stats.DownloadSession` (downloaded/total · speed · ETA · elapsed, via the
stdlib-only `scripts/download_stats.py`: `DownloadStats` EMA speed/eta + `fmt_bytes`/
`fmt_speed`/`fmt_clock`). `c` collapses the modal back to the dashboard while the
download continues, leaving the one-row `#dlbar` indicator (`⬇ <name> NN% <speed>
ETA m:ss`); `w` (`action_watch_download`) re-expands it; `Esc` cancels (sets the
session's `cancelled` flag → the pull's `should_cancel` breaks). On finish `_dl_finish`
reloads the catalog (badge/readiness flip) and the indicator shows a transient
`✓ <name> ready` before clearing. Docker rows still show a `⬇ get`/`✓ ready`/`⬇ NN%`
badge from the catalog's `img_present`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md describes collapsible download telemetry

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notes

**Spec coverage:**
- Rich telemetry (size/speed/ETA/elapsed) → Task 1 (math) + Task 3 Step 6 (render).
- Collapsible to banner indicator → Task 3 Steps 6 (`action_collapse`), 11 (`#dlbar`).
- Re-expandable → Task 3 Step 7 (`action_watch_download`), 11e (`w` binding).
- Worker survives collapse → Task 3 Step 7 (App-owned worker).
- Single download at a time → Task 3 Step 7 (`start_download` guard).
- EMA speed smoothing → Task 1 (`_EMA_ALPHA`).
- Cancellable pull → Task 2.
- Phase-reset (download→extract) no negative speed → Task 1 `set_phase` + test.
- Responsive (indicator stays under height pressure) → Task 3 Step 11d.
- Tests (pure + Pilot) → Tasks 1 and 3.
- Docs → Task 4.

**Type consistency:** `DownloadSession` (Task 1) is consumed in Task 3 with extra
plain attributes (`phase_caption`, `bytes_done`, `bytes_total`) set by the App - not
dataclass fields, by design, to keep the module pure. `should_cancel` signature
matches across `pull_docker_image` / `download_image` / the worker. `_render_dlbar`,
`start_download`, `action_watch_download` names are used consistently.

**Placeholder scan:** none - every code step shows full code.
