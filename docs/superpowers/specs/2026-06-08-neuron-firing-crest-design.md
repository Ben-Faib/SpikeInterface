# Animated firing-neuron crest

**Date:** 2026-06-08
**Status:** Design approved, ready for implementation plan
**Supersedes the hero choice in:** `2026-06-08-brain-hero-crest-design.md` (the brain blob this replaces)

## Problem

The v2 dashboard's top crest is a brain (`ui._BRAIN_FULL/_COMPACT/_MINI`) — a
solid, photo-derived Braille blob (`scripts/_brain_art_gen.py`'s `S_NEURON`)
area-averaged down to 30/18/12 columns. It does not read as a brain: a brain is
recognised from its *silhouette* (bumpy cerebrum, cerebellum bulge, brainstem
stub) and its *cortical folds*, and a downscaled filled photo preserves neither —
the folds are texture noise and averaging erases them, worst at the small tiers.
The result is a featureless pink potato.

## Goal

Replace the brain hero with a **single firing neuron** drawn as deliberate
line-art, and — in the Textual dashboard only — play a slow, subtle
"receive → fire → rest" animation on a ~5–7 s loop. The neuron is more
distinctive *and* more on-theme than a brain: spike sorting isolates individual
units (cells), and the mark depicts exactly that — a cell receiving a signal and
firing a spike (the data this tool actually produces).

## Non-goals

- No change to the **Pitt shield** (it stays on the Welcome screen and the Help
  "About" topic, unchanged).
- No change to the sorter sidebar, actions pane, pipeline panel, or any data /
  loader / sorting logic.
- **No new dependencies** — Textual and rich are already present.
- Animation is **Textual-only**. The legacy prompt_toolkit / typed fallback menu,
  off-TTY output, Welcome, and Help all render the neuron **at rest** (static).

## The mark

A horizontal neuron, reading left → right like the signal path:

```
   ╲   │   ╱
  ──●━━━━━━━━━━━━━━━━━━━╤────────        ← flat trace at rest
   ╱   │   ╲
   dendrites · soma · ───── axon ───── · spike (action potential)
```

- **Dendrites** — a few branching strokes on the left, converging on the soma.
- **Soma** — a small filled body where the dendrites meet.
- **Axon** — a horizontal line running rightward from the soma.
- **Spike** — at the axon terminal, an **action-potential waveform** (sharp
  upstroke → fall → afterhyperpolarization dip). Flat at rest.

The exact glyphs (Braille `U+28xx`, block, and box-drawing) are settled during the
build's candidate phase (below). Constraints that the art **must** satisfy:

- Three responsive tiers — **full / compact / mini** — reusing the existing
  fit-and-collapse ladder (largest tier that fits the live window; hidden when
  even mini won't fit).
- **Every row in a tier is the same display width** (code points), so Textual's
  centred layout doesn't shift row-to-row. This is the existing
  `test_brain_art_rows_equal_width` invariant, retargeted to the neuron.
- Legible as "a firing neuron" even at the **mini** tier.

## The motion (6 states, looped)

Mostly at rest; the active portion is brief (~1–1.5 s) and gentle.

1. **Rest** — neuron at the calm base colour, trace flat.
2. **Input** — a bright pulse appears at the dendrite tips.
3. **Integrate** — the pulse converges; the soma briefly brightens.
4. **Propagate** — the pulse travels rightward along the axon.
5. **Fire** — the AP waveform rises to a peak at the axon terminal.
6. **Decay** — the AP settles back to flat; brightness fades to rest. Hold, then
   repeat.

**Colour (two-tone).** Neuron body in the existing calm pink (`#ff6fb5`, the
current `ui.BRAIN_PINK`, renamed to a neuron-appropriate constant). The travelling
pulse and firing AP use a **fixed electric white-yellow** spark colour so the
energy always pops regardless of the active theme. (Implementation keeps the spark
hex in one constant; switching it to follow the theme `$accentcolor` later is a
one-line change.) Two-tone is free: `_crest_text(rows)` already renders multiple
`(style, segment)` fragments per row.

**Cadence / performance.**
- ~6 fps timer (interval ≈ 0.15 s), ~6 s full cycle.
- The active states (2–6) occupy ~1–1.5 s; the rest of the cycle holds the flat
  rest frame.
- The widget **skips re-rendering identical rest frames** (memoise the last
  rendered rows), so idle cost is near zero.
- The timer **pauses** while an action / modal is running (the app `suspend()`s
  anyway) and when the crest is collapsed off a short window (widget hidden).

## Architecture

### `scripts/ui.py` — the neuron crest renderer

Replace the static brain (`_BRAIN_FULL/_COMPACT/_MINI`, `_build_brain`, `_BRAINS`,
`pick_brain`) and delete the dev tool `scripts/_brain_art_gen.py`. Add a
**phase-driven** neuron crest:

- Per tier (full / compact / mini), an authored **skeleton**: the rest-pose rows,
  an ordered **conduction path** (dendrite tip → soma → axon terminal, as a list of
  cell positions so the pulse can be placed at `path[int(phase·len)]`), and the
  **spike anchor** (where the AP waveform draws).
- `neuron_frame(tier, phase) -> rows` — returns built rows (each a list of
  `(style, segment)` fragments, exactly what `_crest_text` consumes). It starts
  from the rest pose, overlays the bright pulse at the phase position, and grows
  the AP waveform by phase. `phase` at/within the rest band returns the rest pose.
- `pick_neuron(cols, rows, reserve) -> tier_id | None` — same fit math as the
  current `_pick`, but returns **which tier** fits (since the rows now depend on
  phase) rather than baked rows. `None` ⇒ hide the crest.
- A convenience for static contexts (fallback menu, Welcome, tests):
  `neuron_rest(tier)` = `neuron_frame(tier, REST_PHASE)`.

Procedural (phase-driven) rather than dozens of hand-authored frames: smoother
travel, no combinatorial art across 3 tiers × N frames, and a single source of
truth for the rest pose.

### `scripts/menu_app.py` — `CrestWidget` gains a phase + timer

- `CrestWidget` keeps the **chosen tier** (set by `fit()` on resize via
  `pick_neuron`) and a `phase` float.
- On mount (when `animate` is on and a tier fits), start a `set_interval` (the
  same pattern `DockerConfirmScreen` already uses) that advances `phase`,
  re-renders via the existing `_crest_text(neuron_frame(tier, phase))`, and skips
  the `update()` when the frame is unchanged.
- `animate` **off** ⇒ no timer; render the rest pose once.
- Pause/stop the timer when the widget is hidden (collapsed) or during
  `suspend()`; resume on return.
- This is the **only** crest swap — the shield (`ui.pick_logo`, `#wcrest`, Help
  "About") is untouched.

### Config — an `animate` flag

- Add `animate: bool` (default `True`) to `.si_menu.json`, plumbed through the
  controller alongside `theme` / `seen_welcome` / `use_docker`
  (`SpikeInterface_Menu.py` `_load_config` / `_save_config` / `Controller`).
- Expose a **toggle** in the menu (a settings/Actions affordance, mirroring the
  Docker on/off row) and document it in the Help "keyboard" topic.
- Honour a reduce-motion path: if `animate` is off, the dashboard is fully static.

### Legacy fallback

`ui.dashboard_menu()` (prompt_toolkit / typed) renders `neuron_rest(tier)` for the
top crest — same rest pose as the Textual path, no animation.

## Build approach

The art is the hard part, so the build **starts with a candidate-generation
workflow** before any wiring:

1. **Generate** — several agents each draft a neuron rest-pose + AP-waveform style
   across the 3 tiers (Braille / block / box-drawing line-art), honouring the
   equal-row-width and mini-legibility constraints.
2. **Render** — each candidate is rendered at true terminal scale (and a fired
   frame), captured as text.
3. **Judge** — a panel scores each on: reads instantly as a *firing neuron*,
   legible at mini, clean two-tone, equal row widths. Pick the winner (graft the
   best dendrite/soma/axon/AP ideas from runners-up).

Then wire the renderer + `CrestWidget` timer + config flag + fallback, and update
tests. (Implementation phase — after this spec is approved and a plan is written.)

## Testing (`tests/test_menu_app.py`, Textual Pilot)

Update the existing crest tests and add animation coverage:

- **Retarget** `test_brain_art_rows_equal_width` → neuron tiers: every row in
  full / compact / mini is equal width; each tier renders non-empty.
- **Retarget** `test_dashboard_crest_is_the_brain` → the dashboard crest is the
  neuron (rest pose) at a tall size.
- **Keep** `test_welcome_screen_shows_pitt_shield` and
  `test_help_about_topic_shows_pitt_shield` (shield unchanged) — these guard that
  the swap did not disturb the shield.
- **Add**: `neuron_frame(tier, phase)` returns equal-width rows with both the body
  and spark styles present at the fire phase; rest phase contains no spark style.
- **Add**: with `animate=True` the `CrestWidget` starts an interval and `phase`
  advances across `pilot.pause()`s; with `animate=False` no timer runs and the
  crest holds the rest pose.
- **Keep** the existing short-window guard (`#crest` `display is False` when even
  mini won't fit).

## Open decisions (resolved)

- **Motif:** single firing neuron (replaces the brain). ✓
- **Layout:** horizontal signal-flow (dendrites → soma → axon → spike). ✓
- **Spike:** action-potential waveform (animates as a time-course). ✓
- **Animation:** subtle, ~6 fps, gentle loop every ~5–7 s; Textual-only, static
  elsewhere; `animate` flag persisted, default on. ✓
- **Spark colour:** fixed electric white-yellow (theme-independent), one constant,
  switchable to theme-following later. ✓
