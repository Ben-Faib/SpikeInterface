# Wordmark Crest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's animated ASCII firing-neuron crest with a static, themeable figlet block-letter "SPIKE" wordmark, and remove the now-dead animation machinery.

**Architecture:** Add a wordmark art ladder to `scripts/ui.py` mirroring the existing Pitt-shield infrastructure (`_pick`-based responsive tiers, run-length-encoded `(style, text)` fragment rows so `menu_app._crest_text` renders it unchanged). `CrestWidget` in `scripts/menu_app.py` becomes static: it picks a tier and paints once in the live accent colour. All neuron art, the animation timer, the `m` "motion" toggle, and the `animate` config flag are deleted.

**Tech Stack:** Python 3.12, Textual (TUI), rich (styling), pytest + pytest-asyncio (Textual Pilot tests). Run tests with `uv run python -m pytest tests/`.

## Global Constraints

- **Glyph discipline:** wordmark art uses ONLY the full block `█` (U+2588) and spaces - same rule as the shield, so it aligns in any monospace font. No `●`, quadrant blocks, or ambiguous-width glyphs.
- **Equal-width rows:** every row of a tier must be the same length (the picker and render assume rectangular grids).
- **Themeable:** the wordmark colour is applied at *render* time from the live accent (`self.app._accent`), never baked at module load.
- **No SpikeInterface import** in `menu_app.py` or `ui.py` at import time (unchanged invariant).
- **Python 3.12**, `pathlib` throughout, keep existing code style.

---

### Task 1: Add the wordmark art + picker + render helper to `ui.py`

Add the new wordmark infrastructure alongside (not yet replacing) the neuron art, so the module still imports and the existing app keeps working. Neuron removal happens in Task 3.

**Files:**
- Modify: `scripts/ui.py` (add after the neuron block, before `def _pick`)
- Test: `tests/test_menu_app.py` (add wordmark unit tests near the existing crest tests, ~line 1031)

**Interfaces:**
- Consumes: `ui._pick(ladder, cols, rows, reserve)` (existing).
- Produces:
  - `ui._WORDMARK_FULL: list[str]`, `ui._WORDMARK_COMPACT: list[str]` - equal-width rows of `█`/space.
  - `ui.pick_wordmark(cols, rows=None, reserve=0) -> list[str]` - largest tier that fits, or `[]`.
  - `ui.wordmark_rows(tier: list[str], accent: str) -> list[list[tuple[str, str]]]` - per-row `(style, segment)` fragments; non-space runs styled `accent`, space runs unstyled.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_menu_app.py` (anywhere near the existing crest tests):

```python
# --- wordmark crest ------------------------------------------------------- #
def test_wordmark_tiers_equal_width():
    for tier in (ui._WORDMARK_FULL, ui._WORDMARK_COMPACT):
        widths = {len(row) for row in tier}
        assert len(widths) == 1, f"ragged wordmark tier widths: {widths}"


def test_wordmark_uses_only_block_and_space():
    for tier in (ui._WORDMARK_FULL, ui._WORDMARK_COMPACT):
        chars = {ch for row in tier for ch in row}
        assert chars <= {"█", " "}, f"non-block glyphs in wordmark: {chars}"


def test_pick_wordmark_drops_then_hides():
    assert ui.pick_wordmark(200, 60) == ui._WORDMARK_FULL          # roomy -> full
    assert ui.pick_wordmark(200, 60, reserve=58) == ui._WORDMARK_COMPACT  # short -> compact
    assert ui.pick_wordmark(4, 60) == []                            # too narrow -> hidden


def test_wordmark_rows_colours_blocks_with_accent():
    rows = ui.wordmark_rows(ui._WORDMARK_FULL, "#abcdef")
    styles = {s for row in rows for s, seg in row if seg.strip()}
    assert styles == {"#abcdef"}                                    # every block run is accent
    # width is preserved row-for-row
    for src, frags in zip(ui._WORDMARK_FULL, rows):
        assert sum(len(seg) for _, seg in frags) == len(src)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_app.py -k wordmark -q`
Expected: FAIL - `AttributeError: module 'ui' has no attribute '_WORDMARK_FULL'`.

- [ ] **Step 3: Add the wordmark art + helpers to `scripts/ui.py`**

Insert immediately **after** the `pick_neuron` function (currently ends ~line 312) and **before** `def _pick`:

```python
# --------------------------------------------------------------------------- #
# Block-letter "SPIKE" wordmark - the v2 dashboard's static top crest (replaces
# the firing neuron). Block letters in width-safe glyphs ONLY (full block █ +
# spaces, same discipline as the shield). Two responsive tiers; below compact the
# crest hides and the always-present title rule carries the branding. Unlike the
# shield/neuron (fixed colours baked at build time), the wordmark is coloured at
# RENDER time from the live accent (wordmark_rows), so it follows the theme.
# Preview with `uv run python scripts/_wordmark_preview.py`.
# --------------------------------------------------------------------------- #
_WORDMARK_FULL = [                    # 19 cols x 5 rows - block "SPIKE"
    "███ ███ ███ █ █ ███",
    "█   █ █  █  ██  █  ",
    "███ ███  █  █   ███",
    "  █ █    █  ██  █  ",
    "███ █   ███ █ █ ███",
]
_WORDMARK_COMPACT = ["S P I K E"]     # 9 cols x 1 row - letter-spaced caps fallback

_WORDMARKS = [
    (len(_WORDMARK_FULL[0]), len(_WORDMARK_FULL), _WORDMARK_FULL),
    (len(_WORDMARK_COMPACT[0]), len(_WORDMARK_COMPACT), _WORDMARK_COMPACT),
]


def _encode_wordmark_row(line, accent):
    """Run-length-merge a row into (style, segment) fragments: non-space runs get
    ``accent``, space runs are unstyled - the same row shape _build_logo produces,
    so menu_app._crest_text renders the wordmark unchanged."""
    frags, i, n = [], 0, len(line)
    while i < n:
        j, blank = i, line[i] == " "
        while j < n and (line[j] == " ") == blank:
            j += 1
        frags.append(("" if blank else accent, line[i:j]))
        i = j
    return frags


def wordmark_rows(tier, accent):
    """Built crest rows for ``tier`` (list of equal-width strings) coloured with
    the live ``accent``. Width is preserved row-for-row."""
    return [_encode_wordmark_row(row, accent) for row in tier]


def pick_wordmark(cols, rows=None, reserve=0):
    """Largest wordmark tier (full -> compact -> none) that fits - same fit rules
    as pick_logo. Returns the tier (list[str], truthy) or [] when none fits."""
    return _pick(_WORDMARKS, cols, rows, reserve)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_menu_app.py -k wordmark -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/ui.py tests/test_menu_app.py
git commit -m "feat(ui): add static block-letter SPIKE wordmark art + picker

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Switch `CrestWidget` to the static wordmark; remove animation machinery in `menu_app.py`

**Files:**
- Modify: `scripts/menu_app.py`
  - `CrestWidget` class (~lines 1279-1328)
  - constants `_CREST_FPS` / `_CREST_CYCLE_S` (~lines 93-94)
  - `Binding("m", "toggle_motion", ...)` (~line 1407)
  - `action_toggle_motion` (~line 2037-2039)
  - `_after_theme` (~lines 2273-2284) - add a relayout so the crest recolours
  - `ControllerProtocol` (~lines 117, 123) - remove `animate` / `set_animate`
- Test: `tests/test_menu_app.py` - replace the neuron Pilot tests (~lines 1057-1105)

**Interfaces:**
- Consumes: `ui.pick_wordmark`, `ui.wordmark_rows` (Task 1); `self.app._accent` (existing on `SpikeMenuApp`); `menu_app._crest_text` (existing).
- Produces: `CrestWidget` with `fit(cols, rows, reserve=SHIELD_RESERVE)` and `display` reflecting whether a tier fit. No `_animate`/`_phase`/`_tick`/`set_animate` attributes remain.

- [ ] **Step 1: Replace the neuron Pilot tests with wordmark Pilot tests**

In `tests/test_menu_app.py`, delete these tests entirely:
`test_dashboard_crest_is_the_neuron`, `test_crest_advances_phase_when_animated`,
`test_crest_static_when_disabled`, `test_m_key_toggles_animation` (~lines 1057-1105).

Replace them with:

```python
async def test_dashboard_crest_is_the_wordmark(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert crest.display is True
        plain = crest.render().plain
        assert "█" in plain                          # block letters
        assert "━" not in plain                      # not the neuron axon


async def test_crest_has_no_animation(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        assert not hasattr(crest, "_tick")           # animation machinery is gone
        assert not hasattr(crest, "_animate")


async def test_crest_recolours_with_theme(make_app):
    app = make_app(present=True)
    async with app.run_test(size=(110, 45)) as pilot:
        await pilot.pause()
        crest = app.query_one("#crest", menu_app.CrestWidget)
        before = {s for s, _ in crest._tier_fragments()}   # accent style in use
        app.c.theme_name = "amber"                          # fake controller swaps accent
        # drive the theme-applied path directly (no modal in the test)
        app._accent = app.c.themes["amber"]
        app._relayout()
        after = {s for s, _ in crest._tier_fragments()}
        assert before != after
```

Note: `_tier_fragments()` is a tiny test seam added in Step 3.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_menu_app.py -k "crest or wordmark" -q`
Expected: FAIL (the new tests reference behaviour/attrs not yet present; `_tick`/`_animate` still exist).

- [ ] **Step 3: Rewrite `CrestWidget` as a static wordmark**

Replace the whole `CrestWidget` class (~lines 1279-1328) with:

```python
class CrestWidget(Static):
    """The dashboard's static block-letter "SPIKE" wordmark. ``fit(cols, rows)``
    picks the largest tier that fits the live window (and hides the widget when
    none fits). Painted once, in the live accent colour; re-fit on resize/theme."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._tier = None

    def fit(self, cols: int, rows: int, reserve: int = SHIELD_RESERVE) -> None:
        tier = ui.pick_wordmark(cols - 4, rows, reserve=reserve)
        self.display = bool(tier)
        self._tier = tier or None
        self._repaint()

    def _tier_fragments(self):
        """Flat list of the current (style, segment) fragments - a test seam and
        the source for _repaint."""
        if self._tier is None:
            return []
        accent = getattr(self.app, "_accent", "")
        return [frag for row in ui.wordmark_rows(self._tier, accent) for frag in row]

    # NB: deliberately NOT named ``_render`` - that collides with Textual's
    # ``Widget._render`` (the layout engine calls it expecting a Visual).
    def _repaint(self) -> None:
        if self._tier is None:
            return
        accent = getattr(self.app, "_accent", "")
        self.update(_crest_text(ui.wordmark_rows(self._tier, accent)))
```

- [ ] **Step 4: Delete the animation constants**

Remove lines (~93-94):

```python
_CREST_FPS = 6
_CREST_CYCLE_S = 6.0
```

(Keep `SHIELD_RESERVE = 24` at line 87 - `CrestWidget.fit` still uses it as the default.)

- [ ] **Step 5: Remove the `m` motion binding and its action**

Delete the binding line (~1407):

```python
        Binding("m", "toggle_motion", "Motion", show=False),
```

Delete the action method (~2037-2039):

```python
    def action_toggle_motion(self) -> None:
        on = self.c.set_animate(not self.c.animate)
        self.query_one("#crest", CrestWidget).set_animate(on)
```

- [ ] **Step 6: Recolour the crest on theme change**

In `_after_theme` (~2273-2284), add `self._relayout()` before the footer update so the crest repaints in the new accent:

```python
    def _after_theme(self, name: str | None) -> None:
        if not name:
            return
        self._accent = self.c.set_theme(name)
        self.refresh_css()
        self._rebuild_sorters()
        self._rebuild_actions()
        self._render_inspect()
        self._render_databar(self.size.width)
        self._render_sortbar(self.size.width)
        self._relayout()                                  # repaint crest in new accent
        self._last = Text(f"Theme → {name}", style=f"bold {self._accent}")
        self._refresh_footer()
```

- [ ] **Step 7: Drop `animate`/`set_animate` from the controller protocol**

In `ControllerProtocol` (~lines 117 and 123), delete:

```python
    animate: bool                       # crest animation on/off (persisted)
```
and
```python
    def set_animate(self, on: bool) -> bool: ...    # persist + return the new state
```

- [ ] **Step 8: Run the crest/wordmark tests**

Run: `uv run python -m pytest tests/test_menu_app.py -k "crest or wordmark" -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add scripts/menu_app.py tests/test_menu_app.py
git commit -m "feat(menu): static wordmark crest; remove neuron animation + m toggle

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Remove the neuron art + helpers and their unit tests from `ui.py`

Now that nothing references the neuron, delete it.

**Files:**
- Modify: `scripts/ui.py` - remove the neuron block (~lines 176-312: `NEURON_BODY` … `pick_neuron`)
- Test: `tests/test_menu_app.py` - remove the neuron unit tests (~lines 1031-1054)

- [ ] **Step 1: Delete the neuron unit tests**

In `tests/test_menu_app.py`, delete `test_neuron_tiers_equal_width`,
`test_neuron_frame_width_invariant`, `test_neuron_rest_has_no_spark`,
`test_neuron_fire_has_spark` (~lines 1031-1054) and the `# --- firing-neuron crest …`
comment header above them.

- [ ] **Step 2: Delete the neuron art + helpers from `scripts/ui.py`**

Remove the entire neuron section: from the `# Firing-neuron hero …` comment block
(~line 176) through the end of `pick_neuron` (~line 312). This deletes:
`NEURON_BODY`, `NEURON_SPARK`, `NEURON_REST_PHASE`, `_N_TRAVEL`, `_N_FIRE`,
`_NeuronTier`, `_NEURON_FULL`/`_COMPACT`/`_MINI`, `_NEURONS`, `_encode_neuron_row`,
`neuron_frame`, `neuron_rest`, `pick_neuron`.

Keep the `SHIELD_FULL, SHIELD_COMPACT, SHIELD_MINI = _LOGO, _LOGO_COMPACT, _LOGO_MINI`
aliases (line ~174) and everything above them, and keep the wordmark block (Task 1)
and `_pick`/`pick_logo` below.

- [ ] **Step 3: Verify nothing else imports the neuron symbols**

Run: `grep -rn "neuron\|NEURON\|pick_neuron" scripts/ tests/`
Expected: only the new `_wordmark_preview.py` comment (Task 4) or nothing - NO hits in
`ui.py`, `menu_app.py`, or the test files. If any remain, remove them.

- [ ] **Step 4: Run the full ui/menu test module**

Run: `uv run python -m pytest tests/test_menu_app.py -q`
Expected: PASS (no `AttributeError` for missing neuron symbols).

- [ ] **Step 5: Commit**

```bash
git add scripts/ui.py tests/test_menu_app.py
git commit -m "refactor(ui): delete the now-unused firing-neuron art + helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Remove the `animate` flag from the real controller + fake controller + controller tests

**Files:**
- Modify: `SpikeInterface_Menu.py` - `self.animate` (~698), `set_animate` (~739-743)
- Modify: `tests/conftest.py` - `self.animate` (~49), `set_animate` (~156-158)
- Test: `tests/test_menu_controller.py` - remove the 3 animate tests (~244-261)

- [ ] **Step 1: Remove the animate controller tests**

In `tests/test_menu_controller.py`, delete `test_animate_defaults_on`,
`test_animate_reads_saved_off`, `test_set_animate_updates_attr_and_persists`
(~lines 244-261).

- [ ] **Step 2: Remove `animate` from the real controller**

In `SpikeInterface_Menu.py`, delete line ~698:

```python
        self.animate = bool(cfg.get("animate", True))   # crest animation (default on)
```

and the method ~739-743:

```python
    def set_animate(self, on: bool) -> bool:
        self.animate = bool(on)
        self.cfg["animate"] = self.animate
        _save_config(self.cfg)
        return self.animate
```

(Leave `_load_config`/`_save_config` themselves intact - a stale `animate` key in an
existing `.si_menu.json` is simply ignored.)

- [ ] **Step 3: Remove `animate` from the fake controller**

In `tests/conftest.py`, delete line ~49 (`self.animate = True`) and the method
~156-158:

```python
    def set_animate(self, on: bool) -> bool:
        self.animate = bool(on)
        return self.animate
```

- [ ] **Step 4: Run the controller + full suite**

Run: `uv run python -m pytest tests/ -q`
Expected: PASS (entire suite green).

- [ ] **Step 5: Commit**

```bash
git add SpikeInterface_Menu.py tests/conftest.py tests/test_menu_controller.py
git commit -m "refactor(menu): drop the animate config flag (crest no longer animates)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Swap the art-preview script

**Files:**
- Delete: `scripts/_neuron_art_preview.py`
- Create: `scripts/_wordmark_preview.py`

- [ ] **Step 1: Create the wordmark preview**

Create `scripts/_wordmark_preview.py`:

```python
"""Preview the dashboard wordmark tiers in the terminal (dev aid).

    uv run python scripts/_wordmark_preview.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui  # noqa: E402

ACCENT = next(iter(ui.THEMES.values())) if hasattr(ui, "THEMES") else "#8f8fff"


def main() -> int:
    for label, tier in (("FULL", ui._WORDMARK_FULL), ("COMPACT", ui._WORDMARK_COMPACT)):
        print(f"\n{label}  ({len(tier[0])} cols x {len(tier)} rows)")
        for row in tier:
            print("  " + row)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Delete the neuron preview**

```bash
git rm scripts/_neuron_art_preview.py
```

- [ ] **Step 3: Verify the preview runs**

Run: `uv run python scripts/_wordmark_preview.py`
Expected: prints FULL (5 block-letter rows spelling SPIKE) and COMPACT (`S P I K E`), exit 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/_wordmark_preview.py
git commit -m "chore(scripts): replace neuron art preview with wordmark preview

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Rewrite the crest description**

Find the paragraph beginning "An **animated firing neuron** sits atop the dashboard, drawn by `CrestWidget`" and replace it with a description of the static wordmark. Use this text:

```markdown
A **static block-letter "SPIKE" wordmark** sits atop the dashboard, drawn by
`CrestWidget` (`ui.pick_wordmark`/`ui.wordmark_rows`/`ui._WORDMARK_*`): the letters
in width-safe glyphs only (full block `█` + spaces, the same discipline as the
shield), picking the largest tier (full 5-row → compact `S P I K E` one-liner →
hidden) that fits the live window. It is **not animated** - painted once and
re-painted on resize/theme change - and is coloured at render time from the live
accent, so it follows the colour theme. Preview it with
`scripts/_wordmark_preview.py`.
```

Then remove any remaining mentions of: the `m` motion toggle, the `animate` flag in
`.si_menu.json`, `_neuron_art_preview.py`, and `pick_neuron`/`neuron_frame`/`_NEURON_*`.
Update the keyboard-shortcut list (the line describing `t`/`m`/`?`/`d`/`f`) to drop
`m`, and drop `animate` from the persisted-keys list (`use_docker`, `sorter_params`,
`theme`, `seen_welcome`).

- [ ] **Step 2: Sanity-check for stale references**

Run: `grep -n "neuron\|firing\| m toggle\|animate\|_NEURON\|pick_neuron\|_neuron_art" CLAUDE.md`
Expected: no hits (or only unrelated prose). Fix any that remain.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md describes the static wordmark crest

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final Verification

- [ ] Run the whole suite: `uv run python -m pytest tests/ -q` → all green.
- [ ] Launch the app and eyeball the crest: `uv run python SpikeInterface_Menu.py` → static block "SPIKE" in the accent colour, title rule beneath, DATA/SORT banner below; pressing `m` does nothing; changing the theme recolours the wordmark.
- [ ] `grep -rn "neuron\|NEURON\|pick_neuron\|action_toggle_motion\|_CREST_FPS" scripts/ tests/ SpikeInterface_Menu.py` → no hits.

## Self-Review Notes

- **Spec coverage:** art+picker (Task 1) ✓; static widget + theme recolour (Task 2) ✓; remove neuron art (Task 3) ✓; remove `m` toggle + `animate` flag (Tasks 2-4) ✓; preview swap (Task 5) ✓; tests + CLAUDE.md (all tasks + Task 6) ✓. Shield/Welcome/Help untouched (out of scope) ✓.
- **Commit greenness:** Task 1 adds without removing (neuron still live); Task 2 switches the widget before Task 3 deletes the neuron; each commit keeps the suite green.
- **Type consistency:** `pick_wordmark` returns `list[str]` (a tier) or `[]`; `wordmark_rows(tier, accent)` consumes that tier; `CrestWidget._tier` holds it; `_crest_text` consumes `wordmark_rows(...)` output (same `(style, text)` shape as the shield/neuron it replaces).
