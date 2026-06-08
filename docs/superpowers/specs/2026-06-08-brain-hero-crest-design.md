# Brain hero crest + preserved Pitt shield — design

**Date:** 2026-06-08
**Topic:** Replace the dashboard's top Pitt-shield crest with a brain+spike-sorting
hero; keep the Pitt shield on the Welcome and Help screens.

## Goal

The tool sorts neurons from a brain recording, so the main-view hero should be a
**brain**, not the institutional shield. The Pitt crest the user likes is kept —
moved to the one-time **WelcomeScreen** and the **Help/About** screen — and the
titlebar text "University of Pittsburgh · SpikeInterface" is unchanged, so Pitt
branding is never lost.

## Decisions (locked)

- **Placement:** brain becomes the dashboard top crest (today's `ShieldWidget`
  slot). Pitt shield → WelcomeScreen (top of dialog) + Help (an About spot). Titlebar
  text stays.
- **Motif:** brain body + a probe/electrode descending into it + a row of
  spike-raster ticks below — directly evoking spike sorting.
- **Glyphs:** *full glyph freedom* (box-drawing/shading/Unicode allowed) for looks.
  **Hard constraint:** every row in a given size is **equal display width** (so
  Textual layout never shifts). Prefer glyphs that are unambiguous-width in common
  terminals; the brain body should still read if a fancy glyph degrades.
- **Color:** brain body = **fixed neural pink** `BRAIN_PINK` (~`#ff7ab6`, tunable).
  Electrode + spike ticks = the **live accent theme color** (themeable), so spikes
  "pulse" in the picked theme. The Pitt shield keeps its fixed blue+gold.
- **Responsive:** three sizes full / compact / mini feeding the same ladder the
  shield uses (full→compact→mini→hidden as the window shrinks). **Mini** drops the
  electrode + ticks → just the brain blob.

## Crest representation (the format the workflow must produce & integrate)

Each crest *size* is a list of rows; each row carries two parallel, equal-length
strings:

- **ink** — the literal display glyphs (any Unicode); a space = transparent cell.
- **mask** — per-cell color class, same length as ink:
  - `A` → accent (live theme color, emitted as the sentinel `@accent`)
  - `P` or any other non-space → pink brain body (`BRAIN_PINK`)
  - space / `.` over a non-space ink cell → inherit pink

Invariants (builder asserts): within a size every ink row has identical length, and
each row's mask length equals its ink length.

Design-agent output per candidate (JSON): `{full, compact, mini}` where each is
`{ink: [str,...], mask: [str,...], width: int, height: int}`, plus a short
`rationale`. Mini may omit the electrode/ticks.

## Code structure (`scripts/ui.py` + `scripts/menu_app.py`)

- `ui.py`: add `BRAIN_PINK`; add brain art (`_BRAIN_*` ink+mask) for the 3 sizes;
  add a builder that turns (ink, mask) → rows of `(style, text)` fragments where
  `style` is a hex **or** the sentinel `"@accent"`. Generalize the ladder picker so
  both the shield ladder and the brain ladder reuse the same
  largest-that-fits-`cols`/`rows-reserve` logic (keep `pick_logo` working for the
  shield; add a brain equivalent or one generic `pick_crest(ladder, ...)`).
- `menu_app.py`: generalize `ShieldWidget` into a crest widget that takes a ladder +
  resolves `"@accent"` → `self._accent` at render time. Dashboard `#shield` slot
  renders the **brain** ladder; **WelcomeScreen** renders the **shield** ladder at
  the top of its `#dialog`; **HelpScreen** shows the shield in an About spot. Reuse
  the existing `SHIELD_RESERVE` / relayout collapse behavior unchanged.

## Build plan — workflow phases

1. **Design** — N agents each draft a full+compact+mini brain crest in the format
   above (equal row widths enforced; pink body + accent electrode/ticks).
2. **Judge** — panel scores each candidate on: brain recognizability, spike-sorting
   motif clarity, strict equal-row-width correctness, and aesthetic appeal in
   pink+accent. Pick a winner (graft best ideas from runners-up).
3. **Human gate** — show the winning art to the user for a thumbs-up before wiring.
4. **Integrate** — wire winner into `ui.py` + `menu_app.py` (brain → dashboard,
   shield → Welcome/Help) per the structure above.
5. **Verify** — `uv run python -m pytest tests/` stays green; add a test that the
   brain renders on the dashboard and the shield renders on Welcome/Help; render
   smoke-check at several window sizes for equal-width / no crash.

## Testing

- Existing Textual Pilot tests in `tests/` keep passing.
- New: assert the dashboard crest is the brain and Welcome/Help carry the shield;
  assert every brain-art row in each size is equal width (regression guard).

## Out of scope

- Re-coloring or restyling the Pitt shield itself.
- Changing the theme palette or the sorter/actions panes.
