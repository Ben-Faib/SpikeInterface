# Replace the animated neuron crest with a static figlet wordmark

**Date:** 2026-06-27
**Status:** approved

## Problem

The v2 Textual dashboard opens with an animated ASCII "firing neuron" crest
(`CrestWidget` + `ui._NEURON_*`). Organic ASCII art reads poorly in a terminal and
the user finds it unattractive. Replace it with a clean, intentional typographic
header - a figlet-style block-letter wordmark.

## Decision

- **Wordmark text:** block-letter **"SPIKE"** (5 letters). The full name and
  institution stay in the existing title rule below the crest
  (`── University of Pittsburgh · SpikeInterface ──`), so the wordmark itself never
  needs to spell the 13-letter "SPIKEINTERFACE" (which can't render legibly as
  block letters).
- **Static, not animated.** The animation was the unattractive part; the wordmark
  is drawn once. Remove the animation machinery entirely (no dead toggle left
  behind).
- **Themeable.** Block cells render in the live accent colour, so the wordmark
  follows the colour theme (periwinkle/sea-green/steel-blue/amber/cyan).

## Design

### Art (`scripts/ui.py`)

Mirror the existing Pitt-shield infrastructure (`_build_logo` / `_pick` /
`pick_logo`), which already produces width-safe block-letter art in responsive
tiers using only the full block `█` and spaces (aligns in any monospace font).

- Define a block-letter "SPIKE" grid (fill/space mask) in two tiers:
  - `_WORDMARK_FULL` - 5-row block letters (~19 cols), for tall terminals.
  - `_WORDMARK_COMPACT` - 3-row block letters, for medium terminals.
  - No mini tier: below compact the wordmark **hides** and the always-present
    title rule carries the branding.
- A `_WORDMARKS` ladder `[(w, h, art), …]` widest-first, and
  `pick_wordmark(cols, rows=None, reserve=0)` = `_pick(_WORDMARKS, …)`.
- A render helper `wordmark_rows(tier, accent)` that turns the fill/space grid into
  per-row `(style, text)` fragments (the same shape `_build_logo` and
  `neuron_frame` produce, so `menu_app._crest_text` renders it unchanged), styling
  every fill cell with the passed `accent` colour. Unlike the shield/neuron (fixed
  colours baked at module load), the accent is applied **at render time** so it
  tracks the live theme.

### Widget (`scripts/menu_app.py`)

`CrestWidget` becomes a static wordmark widget:

- `fit(cols, rows, reserve)` calls `ui.pick_wordmark(...)`, sets `display`, stores
  the tier, and repaints once.
- `_repaint()` renders `ui.wordmark_rows(tier, self.app._accent)` via `_crest_text`.
- Re-render on theme change (the existing theme-change path that re-styles accent
  widgets calls `fit`/repaint).
- **Remove** the animation: the `set_interval` timer, `_tick`, `_phase`,
  `_animate`, `set_animate`, and `_CREST_FPS` / `_CREST_CYCLE_S`.

### Cleanup (animation removal)

- `scripts/ui.py`: remove the neuron art + helpers - `_NEURON_FULL/COMPACT/MINI`,
  `_NEURONS`, `_NeuronTier`, `_encode_neuron_row`, `neuron_frame`, `neuron_rest`,
  `pick_neuron`, `NEURON_BODY`/`NEURON_SPARK`/`NEURON_REST_PHASE`, `_N_TRAVEL`/
  `_N_FIRE`.
- `scripts/menu_app.py`: remove `action_toggle_motion`, the **`m`** keybinding, and
  any `animate`-related wiring.
- `SpikeInterface_Menu.py` (controller): remove `self.animate`, `set_animate`, and
  the `animate` key in `_load_config`/`_save_config` config dict. (Existing
  `.si_menu.json` files with a stale `animate` key are harmless - just ignored.)
- Delete `scripts/_neuron_art_preview.py`; add a tiny `scripts/_wordmark_preview.py`
  that prints the tiers (parity with the old preview script).

### Tests & docs

- Update the Pilot/controller tests that reference the neuron, the `m` toggle, or
  the `animate` flag (`tests/conftest.py`, `tests/test_menu_app.py`,
  `tests/test_fallback.py`, `tests/test_menu_controller.py`). The never-clip
  responsive tests must still pass with the new tiers (wordmark hides under height
  pressure exactly as the neuron did).
- Update the CLAUDE.md sections describing the firing-neuron crest, the `m` toggle,
  and `_neuron_art_preview.py` to describe the static wordmark instead. Leave the
  historical `docs/superpowers/specs/*` files as-is.

## Out of scope

- The Pitt shield on the Welcome screen and Help "About" topic is unchanged.
- No change to the title rule, banner, panes, or any action flow.

## Success criteria

- Launching the dashboard shows a static block-letter "SPIKE" in the accent colour,
  the title rule beneath it, then the DATA/SORT banner - no animation, no organic
  ASCII.
- The wordmark follows the colour theme.
- It degrades cleanly: full → compact → hidden as the window shrinks; lists never
  clip (existing never-clip tests stay green).
- No dead animation code, no no-op `m` toggle, no `animate` config key.
- `uv run python -m pytest tests/` is green.
