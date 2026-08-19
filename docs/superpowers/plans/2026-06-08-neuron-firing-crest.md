# Animated Firing-Neuron Crest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unrecognizable brain hero crest with a single firing-neuron mark that plays a slow, subtle "receive → fire → rest" animation in the Textual dashboard.

**Architecture:** A phase-driven renderer in `scripts/ui.py` (`neuron_frame(tier, phase)` + `pick_neuron`) builds the crest rows for any animation phase, in width-safe glyphs (box-drawing + the full block `█`, the same no-`●`/no-quadrant discipline as the shield). The Textual `CrestWidget` in `scripts/menu_app.py` gains a `phase` + a `set_interval` timer that walks the phase and re-renders via the existing `_crest_text`, honoring an `animate` config flag and memoizing identical rest frames. Everything else (Welcome, Help "About", the legacy fallback menu) is unchanged - they already draw the Pitt shield, not the brain.

**Tech Stack:** Python 3.12, Textual (already a dep), rich (already a dep), pytest + pytest-asyncio (`uv sync --group dev`). No new dependencies.

---

## Background facts (verified against the current tree on branch `menu-active-explanation-panes`)

- The crest renders through `menu_app._crest_text(rows)` (`scripts/menu_app.py:658`), where each *row* is a list of `(style, segment)` fragments → so **two-tone color is free**.
- `menu_app.CrestWidget` (`scripts/menu_app.py:670`) is the **only** consumer of `ui.pick_brain`. Its `fit(cols, rows, reserve)` calls `picker(cols-4, rows, reserve=reserve)` and renders **once**. `_relayout` calls `self.query_one("#crest", CrestWidget).fit(w, h, reserve)` (`scripts/menu_app.py:842`).
- The legacy fallback `ui.dashboard_menu` draws the **shield** via `ui.pick_logo` (`scripts/ui.py:339,660`) - NOT the brain. Welcome (`#wcrest`) and Help "About" use `ui.SHIELD_FULL`/`ui.SHIELD_COMPACT`. **None of these change.**
- Config persists via `SpikeInterface_Menu._load_config`/`_save_config` and the `MenuController` (`self.use_docker = bool(cfg.get("use_docker", False))` at `SpikeInterface_Menu.py:675`; `set_theme` saves cfg at `:708-714`; `toggle_docker` at `:739-752`; `mark_welcome_seen` at `:798-801`).
- The Controller contract is a `Protocol` in `menu_app.py:91`. The test double is `tests/conftest.py:36 FakeController` (fixture `make_controller` at `:219`). Real-controller tests build via `tests/test_menu_controller.py:35 _controller(monkeypatch, tmp_path, ..., cfg=None)`.

> **Line numbers may have shifted** - the user is editing this branch concurrently. Locate by symbol (the names above), not by line.

## File Structure

- **Modify `scripts/ui.py`** - add the neuron crest (color constants, phase bands, `_NeuronTier`, three baseline tiers, `_encode_neuron_row`, `neuron_frame`, `neuron_rest`, `_NEURONS`, `pick_neuron`) **additively** in Task 1 (the brain stays so imports don't break mid-migration), then remove the brain crest (`_BRAIN_*`, `_build_brain`, `_BRAINS`, `pick_brain`, `BRAIN_PINK`) in Task 5 once nothing references it; add `m animation` to the `HELP_TOPICS` "keys" entry (Task 4). Responsibility: all crest art + the phase renderer.
- **Delete `scripts/_brain_art_gen.py`** - the brain bitmap generator (in Task 5, with the brain removal); the neuron is procedural.
- **Create `scripts/_neuron_art_preview.py`** - dev tool that prints each tier's rest + fire frame for visual QA (replaces the deleted generator's role).
- **Modify `scripts/menu_app.py`** - `CrestWidget` becomes the animated neuron (phase, timer, `_animate`, `set_animate`, `_render`, `fit` via `pick_neuron`); `compose` yields `CrestWidget(id="crest")`; add `Binding("m", "toggle_motion", ...)` + `action_toggle_motion`; `Controller` Protocol gains `animate: bool` + `set_animate`. Responsibility: the animated widget + its toggle.
- **Modify `SpikeInterface_Menu.py`** - `MenuController` gains `self.animate` (from `cfg.get("animate", True)`) + `set_animate`. Responsibility: persist the flag.
- **Modify `tests/conftest.py`** - `FakeController` gains `animate = True` + `set_animate`.
- **Modify `tests/test_menu_app.py`** - retarget the brain tests to the neuron + add animation tests.
- **Modify `tests/test_menu_controller.py`** - add `animate` persistence/default tests.
- **Modify `CLAUDE.md`** - swap the brain-crest description for the neuron (done last, lightly, given concurrent edits).

---

## Task 1: Neuron renderer in `ui.py` (additive - brain stays until Task 5)

> **Why additive:** `menu_app.CrestWidget.__init__` currently has `picker=ui.pick_brain` as a *default argument*, evaluated at **import time**. Removing `ui.pick_brain` before the widget is migrated (Task 3) would break `import menu_app` for every test. So Task 1 only *adds* the neuron API; the brain is removed in Task 5 after Task 3 stops referencing it.

**Files:**
- Modify: `scripts/ui.py` (add the neuron block after the `SHIELD_FULL, SHIELD_COMPACT, SHIELD_MINI = ...` line; leave the brain block in place)
- Test: `tests/test_menu_app.py` (the unit-level tests; no app needed)

- [ ] **Step 1: Write the failing tests** - replace the existing `test_brain_art_rows_equal_width` (around `tests/test_menu_app.py:673`) and add neuron-frame tests. (Leave `_has_braille` for now - `test_dashboard_crest_is_the_brain` still uses it until Task 3.)

```python
# tests/test_menu_app.py - replace test_brain_art_rows_equal_width with:

def test_neuron_tiers_equal_width():
    # Every row in each tier's rest pose must be the same width or Textual's
    # centred crest shifts row-to-row.
    for tier in (ui._NEURON_FULL, ui._NEURON_COMPACT, ui._NEURON_MINI):
        widths = {len(row) for row in tier.rest}
        assert len(widths) == 1, f"ragged neuron tier widths: {widths}"


def test_neuron_frame_width_invariant():
    # Animation only recolours / replaces cells in place - it never changes a
    # row's display width, at any phase.
    for tier in (ui._NEURON_FULL, ui._NEURON_COMPACT, ui._NEURON_MINI):
        W = len(tier.rest[0])
        for phase in (0.0, 0.5, 0.80, 0.96):
            for row in ui.neuron_frame(tier, phase):
                assert sum(len(seg) for _, seg in row) == W


def test_neuron_rest_has_no_spark():
    styles = {s for row in ui.neuron_frame(ui._NEURON_FULL, 0.0) for s, _ in row}
    assert ui.NEURON_SPARK not in styles
    assert ui.NEURON_BODY in styles


def test_neuron_fire_has_spark():
    styles = {s for row in ui.neuron_frame(ui._NEURON_FULL, 0.96) for s, _ in row}
    assert ui.NEURON_SPARK in styles
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_app.py -k "neuron" -q`
Expected: FAIL - `AttributeError: module 'ui' has no attribute '_NEURON_FULL'` / `neuron_frame`.

- [ ] **Step 3: Add the `namedtuple` import** to the top-of-file imports in `scripts/ui.py` (next to `import sys`):

```python
from collections import namedtuple
```

- [ ] **Step 4: Add the neuron block** after the `SHIELD_FULL, SHIELD_COMPACT, SHIELD_MINI = ...` line (before `_term_size`/`_pick`). Leave the existing brain block (`BRAIN_PINK`, `_BRAIN_*`, `_build_brain`, `_BRAINS`, `pick_brain`) untouched for now - it's removed in Task 5. Width-safe glyphs only - box-drawing + the full block `█`, no `●`/quadrant blocks (they misalign across fonts; same rule the shield header documents).

```python
# --------------------------------------------------------------------------- #
# Firing-neuron hero - the v2 Textual dashboard's animated top crest (replaces
# the brain). A single neuron: dendrites -> soma -> axon -> action-potential
# spike, drawn in width-safe glyphs ONLY (box-drawing U+2500.. + the full block
# █; NO ●/quadrant blocks, which misalign across fonts - same discipline as the
# shield). menu_app.CrestWidget walks `phase` on a slow timer (receive -> fire ->
# rest); Welcome/Help/the legacy fallback keep the shield. Preview the art with
# `uv run python scripts/_neuron_art_preview.py`.
# --------------------------------------------------------------------------- #
NEURON_BODY = "#ff6fb5"     # calm pink - the resting neuron body
NEURON_SPARK = "#ffe066"    # electric yellow - the travelling pulse + firing AP
NEURON_REST_PHASE = 0.0

# Phase bands over one [0,1) cycle. Most of the cycle is REST (identical frames
# the widget memoises away); the travel+fire window is brief and subtle.
_N_TRAVEL = 0.74   # [0,0.74)    rest          (flat, body colour only)
_N_FIRE = 0.92     # [0.74,0.92) pulse travels the conduction path
                   # [0.92,1.0)  the action potential fires

# rest      : list[str]      equal-width rows, the resting pose
# path      : list[(r,c)]    ordered conduction line (dendrite root -> soma ->
#                            axon terminal); the bright pulse walks it on travel
# soma      : list[(r,c)]    cells that flash on fire
# dendrites : list[(r,c)]    tip cells that flash as the signal first arrives
# ap        : list[(r,c,ch)] action-potential glyphs drawn (spark) over the rest
#                            pose during the fire band (replace blank cells)
_NeuronTier = namedtuple("_NeuronTier", "rest path soma dendrites ap")

_NEURON_FULL = _NeuronTier(           # 28 cols x 7 rows
    rest=[
        " ╲                          ",
        "  ╲                         ",
        "   ███                      ",
        "───███━━━━━━━━━━━━━━━━┳─────",
        "   ███                      ",
        "  ╱                         ",
        " ╱                          ",
    ],
    path=[(3, c) for c in range(0, 28)],
    soma=[(2, 3), (2, 4), (2, 5), (3, 3), (3, 4), (3, 5), (4, 3), (4, 4), (4, 5)],
    dendrites=[(0, 1), (1, 2), (5, 2), (6, 1), (3, 0), (3, 1), (3, 2)],
    ap=[(2, 24, "╱"), (1, 25, "╱"), (1, 26, "╲"), (2, 27, "╲")],
)

_NEURON_COMPACT = _NeuronTier(        # 18 cols x 5 rows
    rest=[
        " ╲                ",
        "  ██              ",
        "──██━━━━━━━━━━┳───",
        "  ██              ",
        " ╱                ",
    ],
    path=[(2, c) for c in range(0, 18)],
    soma=[(1, 2), (1, 3), (2, 2), (2, 3), (3, 2), (3, 3)],
    dendrites=[(0, 1), (4, 1), (2, 0), (2, 1)],
    ap=[(1, 15, "╱"), (0, 16, "╱"), (1, 17, "╲")],
)

_NEURON_MINI = _NeuronTier(           # 11 cols x 3 rows
    rest=[
        " ╲         ",
        "─██━━━━━┳──",
        " ╱         ",
    ],
    path=[(1, c) for c in range(0, 11)],
    soma=[(1, 1), (1, 2)],
    dendrites=[(0, 1), (2, 1), (1, 0)],
    ap=[(0, 9, "╱"), (0, 10, "╲")],
)

_NEURONS = [
    (len(_NEURON_FULL.rest[0]), len(_NEURON_FULL.rest), _NEURON_FULL),
    (len(_NEURON_COMPACT.rest[0]), len(_NEURON_COMPACT.rest), _NEURON_COMPACT),
    (len(_NEURON_MINI.rest[0]), len(_NEURON_MINI.rest), _NEURON_MINI),
]


def _encode_neuron_row(chars, styles):
    """Run-length-merge adjacent cells of equal style into (style, segment)
    fragments - the same row shape _build_logo produces, so _crest_text renders
    the neuron unchanged."""
    frags, i, n = [], 0, len(chars)
    while i < n:
        j = i
        while j < n and styles[j] == styles[i]:
            j += 1
        frags.append((styles[i], "".join(chars[i:j])))
        i = j
    return frags


def neuron_frame(tier, phase=NEURON_REST_PHASE):
    """Built crest rows for `tier` at animation `phase` in [0,1). Body cells are
    NEURON_BODY; the travelling pulse and firing AP are NEURON_SPARK; blanks are
    unstyled. Width is invariant across phases (cells are recoloured/replaced in
    place, never added/removed)."""
    H = len(tier.rest)
    grid = [list(row) for row in tier.rest]
    styles = [[NEURON_BODY if ch != " " else "" for ch in row] for row in tier.rest]

    def spark(r, c):
        if 0 <= r < H and 0 <= c < len(grid[r]) and grid[r][c] != " ":
            styles[r][c] = NEURON_SPARK

    if _N_TRAVEL <= phase < _N_FIRE:                      # signal travels in
        t = (phase - _N_TRAVEL) / (_N_FIRE - _N_TRAVEL)
        head = int(t * len(tier.path))
        for k in (head - 1, head):                        # a 2-cell bright pulse
            if 0 <= k < len(tier.path):
                spark(*tier.path[k])
        if t < 0.25:                                      # tips light as it arrives
            for rc in tier.dendrites:
                spark(*rc)
    elif phase >= _N_FIRE:                                # the AP fires
        for rc in tier.soma:
            spark(*rc)
        for (r, c, ch) in tier.ap:
            if 0 <= r < H and 0 <= c < len(grid[r]):
                grid[r][c] = ch
                styles[r][c] = NEURON_SPARK

    return [_encode_neuron_row(grid[r], styles[r]) for r in range(H)]


def neuron_rest(tier):
    """The resting pose - for static contexts and tests."""
    return neuron_frame(tier, NEURON_REST_PHASE)


def pick_neuron(cols, rows=None, reserve=0):
    """Largest neuron tier (full -> compact -> mini -> none) that fits - same fit
    rules as pick_logo. Returns the _NeuronTier (truthy) or [] when even mini
    won't fit."""
    return _pick(_NEURONS, cols, rows, reserve)
```

- [ ] **Step 5: Run the neuron tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_app.py -k "neuron" -q`
Expected: PASS (4 passed). If `test_neuron_tiers_equal_width` fails, a literal row was miscounted - pad the short row(s) with trailing spaces to match the longest in that tier; that is the only allowed fix.

- [ ] **Step 6: Commit**

```bash
git add scripts/ui.py tests/test_menu_app.py
git commit -m "$(printf 'feat(menu): firing-neuron crest renderer in ui.py (additive)\n\nProcedural neuron_frame(tier, phase)/pick_neuron; width-safe box-drawing+block\nart across full/compact/mini tiers. Brain kept for now (removed once the\nwidget migrates).\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: Dev preview tool

**Files:**
- Create: `scripts/_neuron_art_preview.py`

- [ ] **Step 1: Create the preview tool**

```python
"""Dev tool: print each neuron crest tier (rest + a fired frame) to the terminal
so the art can be eyeballed for legibility and alignment. Not imported by the app.

    uv run python scripts/_neuron_art_preview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # find ui.py
import ui  # noqa: E402


def _plain(rows):
    return "\n".join("".join(seg for _, seg in row) for row in rows)


def main() -> int:
    tiers = [("FULL", ui._NEURON_FULL), ("COMPACT", ui._NEURON_COMPACT),
             ("MINI", ui._NEURON_MINI)]
    for name, tier in tiers:
        w, h = len(tier.rest[0]), len(tier.rest)
        print(f"===== {name}: {w} cols x {h} rows - rest =====")
        print(_plain(ui.neuron_frame(tier, 0.0)))
        print(f"----- {name} - fire -----")
        print(_plain(ui.neuron_frame(tier, 0.96)))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it to confirm it renders three tiers**

Run: `uv run python scripts/_neuron_art_preview.py`
Expected: prints FULL/COMPACT/MINI, each a rest pose and a fire frame; rows in a tier are visibly the same width; the fire frame shows the `╱╲` spike at the axon terminal.

- [ ] **Step 3: Commit**

```bash
git add scripts/_neuron_art_preview.py
git commit -m "$(printf 'chore(menu): neuron crest preview tool for visual QA\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: Animated `CrestWidget` + `compose`

**Files:**
- Modify: `scripts/menu_app.py` (`CrestWidget` class; `compose`'s `CrestWidget(...)`; module constants near `SHIELD_RESERVE`)
- Test: `tests/test_menu_app.py`

- [ ] **Step 1: Write the failing tests** - retarget the brain dashboard test and add animation tests. Also delete the now-unused `_has_braille` helper from the top of `tests/test_menu_app.py` (its last user, `test_dashboard_crest_is_the_brain`, is replaced here).

```python
# tests/test_menu_app.py - replace test_dashboard_crest_is_the_brain with:

async def test_dashboard_crest_is_the_neuron(make_controller):
    app = _app(make_controller(present=True))
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest.display is True
        plain = crest.render().plain
        assert "━" in plain and "█" in plain        # axon + soma, not the shield


async def test_crest_advances_phase_when_animated(make_controller):
    c = make_controller(present=True)
    c.animate = True
    app = _app(c)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest._animate is True
        p0 = crest._phase
        crest._tick(); crest._tick()
        assert crest._phase != p0                    # the timer callback walks phase


async def test_crest_static_when_disabled(make_controller):
    c = make_controller(present=True)
    c.animate = False
    app = _app(c)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest._animate is False
        before = crest.render().plain
        crest._tick()                                # no-op while disabled
        assert crest._phase == 0.0
        assert crest.render().plain == before
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_menu_app.py -k "crest" -q`
Expected: FAIL - `AttributeError` on `crest._animate` / `_tick` / `_phase`, and the neuron-render assertion errors against the old brain widget.

- [ ] **Step 3: Add animation constants** near `SHIELD_RESERVE` (top of `scripts/menu_app.py`, after `_BORDER_DIM`):

```python
# Crest animation: a slow, subtle receive->fire->rest loop. ~6 fps over a ~6 s
# cycle; most of the cycle is the (memoised) rest frame, so idle cost is ~nil.
_CREST_FPS = 6
_CREST_CYCLE_S = 6.0
```

- [ ] **Step 4: Replace the `CrestWidget` class** (`scripts/menu_app.py`, currently the `class CrestWidget(Static)` with `__init__(picker=...)` + `fit`):

```python
class CrestWidget(Static):
    """The dashboard's animated firing-neuron crest. ``fit(cols, rows)`` picks the
    largest tier that fits the live window (and hides the widget when even mini
    won't). A slow timer walks ``phase`` (receive -> fire -> rest); identical rest
    frames are memoised away. Honours the controller's ``animate`` flag."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._tier = None
        self._phase = 0.0
        self._animate = True
        self._last = None
        self._timer = None

    def on_mount(self) -> None:
        self._animate = bool(getattr(self.app.c, "animate", True))
        self._timer = self.set_interval(
            1.0 / _CREST_FPS, self._tick, pause=not self._animate
        )

    def fit(self, cols: int, rows: int, reserve: int = SHIELD_RESERVE) -> None:
        tier = ui.pick_neuron(cols - 4, rows, reserve=reserve)
        self.display = bool(tier)
        self._tier = tier or None
        self._render()

    def set_animate(self, on: bool) -> None:
        self._animate = bool(on)
        if self._timer is not None:
            self._timer.resume() if on else self._timer.pause()
        if not on:
            self._phase = 0.0
        self._render()

    def _tick(self) -> None:
        if not self._animate or not self.display or self._tier is None:
            return
        self._phase = (self._phase + 1.0 / (_CREST_FPS * _CREST_CYCLE_S)) % 1.0
        self._render()

    def _render(self) -> None:
        if self._tier is None:
            return
        phase = self._phase if self._animate else ui.NEURON_REST_PHASE
        rows = ui.neuron_frame(self._tier, phase)
        if rows != self._last:
            self._last = rows
            self.update(_crest_text(rows))
```

- [ ] **Step 5: Update `compose`** - change the crest line from `yield CrestWidget(ui.pick_brain, id="crest")` to:

```python
        yield CrestWidget(id="crest")
```

- [ ] **Step 6: Run the crest tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_app.py -k "crest" -q`
Expected: PASS (3 passed).

- [ ] **Step 7: Run the full menu suite (no regressions)**

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: PASS - including the unchanged shield tests `test_welcome_screen_shows_pitt_shield` and `test_help_about_topic_shows_pitt_shield`.

- [ ] **Step 8: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "$(printf 'feat(menu): animate the neuron crest (slow receive->fire->rest loop)\n\nCrestWidget gains a phase + a ~6fps set_interval timer that re-renders via\nneuron_frame; memoises rest frames; honours an animate flag.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: `animate` flag - config, controller, toggle

**Files:**
- Modify: `SpikeInterface_Menu.py` (`MenuController.__init__`, new `set_animate`)
- Modify: `scripts/menu_app.py` (`Controller` Protocol; `BINDINGS`; `action_toggle_motion`)
- Modify: `scripts/ui.py` (`HELP_TOPICS` "keys" body)
- Modify: `tests/conftest.py` (`FakeController`)
- Test: `tests/test_menu_controller.py`, `tests/test_menu_app.py`

- [ ] **Step 1: Write the failing controller tests** - add to `tests/test_menu_controller.py` (uses the file's existing `_controller` helper):

```python
def test_animate_defaults_on(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path)
    assert c.animate is True


def test_animate_reads_saved_off(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path, cfg={"animate": False})
    assert c.animate is False


def test_set_animate_updates_attr_and_persists(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path)
    saved = {}
    monkeypatch.setattr(M, "_save_config", lambda cfg: saved.update(cfg))
    assert c.set_animate(False) is False
    assert c.animate is False
    assert c.cfg["animate"] is False
    assert saved.get("animate") is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_menu_controller.py -k "animate" -q`
Expected: FAIL - `AttributeError: 'MenuController' object has no attribute 'animate'` / `set_animate`.

- [ ] **Step 3: Add `animate` to `MenuController`** in `SpikeInterface_Menu.py`. After the line `self.use_docker = bool(cfg.get("use_docker", False))`, add:

```python
        self.animate = bool(cfg.get("animate", True))   # crest animation (default on)
```

Then add a method next to `set_theme`:

```python
    def set_animate(self, on: bool) -> bool:
        self.animate = bool(on)
        self.cfg["animate"] = self.animate
        _save_config(self.cfg)
        return self.animate
```

- [ ] **Step 4: Run the controller tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_controller.py -k "animate" -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Extend the Controller Protocol** in `scripts/menu_app.py` (`class Controller(Protocol)`). Add a field beside `use_docker`:

```python
    animate: bool
```

and a method beside `set_theme`:

```python
    def set_animate(self, on: bool) -> bool: ...
```

- [ ] **Step 6: Add the toggle binding + action** in `SpikeMenuApp`. Add to `BINDINGS` (next to the `t`/`d` bindings):

```python
        Binding("m", "toggle_motion", "Motion", show=False),
```

and the action method on the app:

```python
    def action_toggle_motion(self) -> None:
        on = self.c.set_animate(not self.c.animate)
        self.query_one("#crest", CrestWidget).set_animate(on)
        self.notify(f"Crest animation {'on' if on else 'off'}")
```

- [ ] **Step 7: Add `m` to the Help keyboard topic** in `scripts/ui.py` `HELP_TOPICS`, the `("keys", "Keyboard", [...])` entry. Change the middle line to include motion:

```python
      "1-9 jump to an action · t switch sorter · m animation · ? help · d data files",
```

- [ ] **Step 8: Update the test double** in `tests/conftest.py` `FakeController`. After `self.use_docker = False` in `__init__`, add:

```python
        self.animate = True
```

and a method (next to `set_theme`):

```python
    def set_animate(self, on: bool) -> bool:
        self.animate = bool(on)
        return self.animate
```

- [ ] **Step 9: Write + run the toggle Pilot test** - add to `tests/test_menu_app.py`:

```python
async def test_m_key_toggles_animation(make_controller):
    c = make_controller(present=True)
    c.animate = True
    app = _app(c)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest._animate is True
        await pilot.press("m")
        await pilot.pause()
        assert c.animate is False and crest._animate is False
        await pilot.press("m")
        await pilot.pause()
        assert c.animate is True and crest._animate is True
```

Run: `uv run python -m pytest tests/test_menu_app.py -k "toggle or crest or neuron" -q`
Expected: PASS.

- [ ] **Step 10: Full suite (no regressions)**

Run: `uv run python -m pytest tests/ -q`
Expected: PASS (all green).

- [ ] **Step 11: Commit**

```bash
git add SpikeInterface_Menu.py scripts/menu_app.py scripts/ui.py tests/conftest.py tests/test_menu_app.py tests/test_menu_controller.py
git commit -m "$(printf 'feat(menu): persist an animate flag + m-key toggle for the crest\n\nMenuController.animate (default on, saved to .si_menu.json) + set_animate;\nm toggles it live; Help keyboard topic + Controller Protocol updated.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: Remove the brain crest

Now that `CrestWidget` no longer references `ui.pick_brain` (Task 3) and the tests use the neuron (Tasks 1, 3), the brain is dead code and safe to delete.

**Files:**
- Modify: `scripts/ui.py` (delete `BRAIN_PINK`, `_BRAIN_FULL/_COMPACT/_MINI`, `_build_brain`, `_BRAINS`, `pick_brain`)
- Delete: `scripts/_brain_art_gen.py`

- [ ] **Step 1: Confirm nothing in code still references the brain API**

Run: `grep -rn "pick_brain\|_BRAIN\|BRAIN_PINK\|_build_brain\|_brain_art_gen" scripts/ tests/ SpikeInterface_Menu.py`
Expected: **no hits** in `.py` files. (Doc hits in `CLAUDE.md`/specs are handled in Task 7.) If any `.py` reference remains, stop and migrate it first.

- [ ] **Step 2: Delete the brain block from `scripts/ui.py`** - the comment header above `BRAIN_PINK`, the `BRAIN_PINK = "#ff6fb5"` line, `_BRAIN_FULL`, `_BRAIN_COMPACT`, `_BRAIN_MINI`, `def _build_brain(...)`, the `_BRAINS = [...]` ladder, and `def pick_brain(...)`. Leave `_pick`, `pick_logo`, `_LOGO_INDENT`, `SHIELD_*`, and the entire neuron block intact.

- [ ] **Step 3: Delete the generator**

Run: `git rm scripts/_brain_art_gen.py`
Expected: `rm 'scripts/_brain_art_gen.py'`

- [ ] **Step 4: Full suite (import-clean, no regressions)**

Run: `uv run python -m pytest tests/ -q`
Expected: PASS - `import menu_app` no longer evaluates `ui.pick_brain` anywhere, so the removal is safe.

- [ ] **Step 5: Commit**

```bash
git add scripts/ui.py
git rm scripts/_brain_art_gen.py
git commit -m "$(printf 'refactor(menu): drop the dead brain crest + its generator\n\nThe neuron fully replaced the brain hero; remove _BRAIN_*/pick_brain/\nBRAIN_PINK and scripts/_brain_art_gen.py.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: Visual QA + art polish (recommended)

The baseline art in Task 1 is correct-by-construction but plain. This task makes it genuinely read as a firing neuron. The renderer/format/tests do **not** change - only the three `_NeuronTier` literals in `scripts/ui.py`.

- [ ] **Step 1: Eyeball the baseline**

Run: `uv run python scripts/_neuron_art_preview.py` and `uv run python SpikeInterface_Menu.py` (watch the crest loop for a few seconds; press `m` to confirm it stops/starts).
Expected: a recognizable neuron firing left→right. Note what's weak (soma too blocky, dendrites sparse, spike unclear at mini, etc.).

- [ ] **Step 2: Generate candidates with a Workflow** (ultracode). Author/run a workflow that, per tier (full/compact/mini), spawns several agents each drafting a `_NeuronTier` (rest grid + `path`/`soma`/`dendrites`/`ap`) under the hard constraints: width-safe glyphs only (box-drawing + `█`, no `●`/quadrant blocks); all `rest` rows equal width; legible as a firing neuron at that tier's size. Render each candidate's rest+fire frame to text, then a judge panel scores legibility/cleanliness/equal-width and picks a winner per tier (grafting the best dendrite/soma/axon/AP ideas from runners-up).

A judging note for the workflow: the `ap` cells must land on cells that are blank in the rest grid (so the spike appears on fire), and `path` must be an ordered left→right line from a dendrite root through the soma to the axon terminal.

- [ ] **Step 3: Swap the winning literals** into `scripts/ui.py` (`_NEURON_FULL/_COMPACT/_MINI` only).

- [ ] **Step 4: Re-run the structural tests** (these guard the swap):

Run: `uv run python -m pytest tests/test_menu_app.py -k "neuron or crest" -q`
Expected: PASS - equal-width + width-invariant + spark-on-fire still hold. Fix any ragged row by padding with trailing spaces.

- [ ] **Step 5: Re-preview + commit**

Run: `uv run python scripts/_neuron_art_preview.py` (confirm the improved art).

```bash
git add scripts/ui.py
git commit -m "$(printf 'feat(menu): polish the firing-neuron crest art (workflow-selected tiers)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-06-08-brain-hero-crest-design.md` (one-line superseded note)

- [ ] **Step 1: Update `CLAUDE.md`** - the menu/architecture section describes "the brain - not the shield - is the dashboard's top crest" and "a detailed, solid Braille brain in neural pink." Replace those with the neuron: the dashboard's top crest is now an **animated firing neuron** (dendrites → soma → axon → action-potential spike) drawn in width-safe box-drawing+block glyphs, on a slow `receive → fire → rest` loop (~6 fps, ~6 s) gated by an `animate` flag in `.si_menu.json` (toggle with `m`); the Pitt shield stays on Welcome + Help "About"; the legacy fallback keeps the shield. Note `pick_brain`/`_BRAIN_*` are gone, replaced by `neuron_frame`/`pick_neuron`/`_NEURON_*`, and `_brain_art_gen.py` by `_neuron_art_preview.py`.

> Edit by locating the phrases, not line numbers - the user is editing `CLAUDE.md` concurrently. Touch only the crest sentences; leave unrelated edits alone.

- [ ] **Step 2: Mark the old spec superseded** - add one line at the top of `docs/superpowers/specs/2026-06-08-brain-hero-crest-design.md`:

```markdown
> **Superseded by `2026-06-08-neuron-firing-crest-design.md`** - the brain hero was replaced by an animated firing neuron.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-06-08-brain-hero-crest-design.md
git commit -m "$(printf 'docs: neuron crest replaces the brain hero (CLAUDE.md + spec note)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-review notes (spec coverage)

- **Motif / layout / spike** (horizontal neuron → AP spike): Task 1 art + renderer. ✓
- **Animation, ~6 fps, gentle ~5–7 s loop, 6 states, two-tone, memoised rest**: Task 1 phase bands + Task 3 timer (`_CREST_CYCLE_S = 6.0`; rest band = 74% of the cycle ⇒ a fire roughly every ~6 s; `_render` memoises). ✓
- **Textual-only animation; static rest elsewhere**: only `CrestWidget` animates; Welcome/Help/fallback are untouched (they draw the shield). ✓ - note this *deviates from the spec*, which said the fallback shows the neuron at rest; in the current code the fallback already shows the shield, so leaving it is less churn and still "no animation outside Textual." Flag for the user.
- **`animate` flag persisted + toggle**: Task 4. ✓
- **Pitt shield unchanged on Welcome/About**: guarded by the kept shield tests. ✓
- **Tests retargeted + animation tests added**: Tasks 1, 3, 4. ✓
- **Candidate-generation workflow for the art**: Task 6. ✓
- **No `●`/quadrant blocks (width-safe)**: enforced in Task 1 art + the equal-width / width-invariant tests; called out in Task 6's constraints. ✓
- **No new dependencies**: Textual/rich/pytest only. ✓

## Risks / watch-items

- **`set_interval(..., pause=...)`** and `Timer.pause()/.resume()` are the Textual API used elsewhere in this file (the Docker poll timer). If a Textual version mismatch surfaces, fall back to starting the timer unpaused and early-returning in `_tick` when `not self._animate` (the guard is already there).
- **Glyph width across fonts** - the art is restricted to box-drawing + `█`, the same set the shield uses. The equal-width test guards *code-point* width; the `_neuron_art_preview.py` eyeball (Task 6 Step 1) guards *display* width.
- **Concurrent edits** - the user is actively editing `menu_app.py`/`CLAUDE.md` on this branch. Each `git add` lists explicit paths; never `git add -A`. Locate code by symbol, re-read before editing.
