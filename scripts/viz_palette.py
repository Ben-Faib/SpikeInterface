"""The one home for chart colors: the periwinkle palette every HTML surface reads.

Ben's decision of record (2026-08-19, the interview): periwinkle anchors the
visuals across ALL surfaces: report.html, the comparison pages, the sweep page,
and the lab-meeting deck. This module is the single source of truth for those
colors; surfaces import it and never hardcode a chart hex. The menu's Textual
theme (ui.py) is a separate system and does not read this file.

    import viz_palette as vp
    vp.CATEGORICAL_LIGHT[0]      # periwinkle, the anchor slot
    vp.sequential(5)             # a 5-step periwinkle ramp, light to dark
    vp.CHROME_LIGHT["surface"]   # the chart surface the palette was validated on

Built with the dataviz skill's method (design-system-agnostic; the skill's
references describe the checks) and VALIDATED, never eyeballed, with its
validate_palette.js. Re-run after ANY change to these values:

    node <dataviz-skill>/scripts/validate_palette.js \\
        "#656dd7,#d67523,#1ea28f,#c69612,#d36a96,#308639,#5e3d9e,#cb4644" \\
        --mode light --surface "#fbfbfe"
    node <dataviz-skill>/scripts/validate_palette.js \\
        "#7d88e6,#c56c21,#0f9b89,#b3880f,#c1628a,#3e8b44,#9675cc,#ca5551" \\
        --mode dark --surface "#17171f"

Measured results on record (2026-08-19):
- light, adjacent pairs: CVD worst 12.5 (protan, gold-teal), normal-vision worst
  19.5, all slots in band; gold sits at 2.62:1 contrast, below the 3:1 line, so
  the RELIEF RULE applies wherever gold carries identity: visible direct labels
  or a table view (both are already house style on these surfaces).
- dark, adjacent pairs: CVD worst 8.6 (deutan), normal-vision worst 18.0, all
  slots >= 3:1 on the dark surface. All hard gates pass in both modes.
- all-pairs charts (scatter, bubble, small multiples): only the FIRST THREE
  slots validate all-pairs (light CVD 13.1 / normal 21.3; dark CVD 13.1 /
  normal 19.1). Past three series on such a chart: fold to "Other" or facet.
- ordinal use of the ramp (discrete ordered marks): on light, start no lighter
  than step 300 (#9da8f0, 2.19:1); on dark, go no darker than step 500
  (#5d64ca, 3.51:1). Both subranges validated with --ordinal.

Rules the surfaces must keep (from the skill, non-negotiable):
- Assign categorical hues in this fixed order, never cycled; a 9th series is
  "Other", never a generated hue.
- Color follows the entity, never its rank; filters must not repaint survivors.
- Sequential = the one periwinkle ramp; diverging = periwinkle vs copper with
  the neutral midpoint; never a rainbow.
- Status colors are reserved for state, ship with an icon or label, and are
  never reused as series colors.
- Text wears ink tokens, never a series color.
"""
from __future__ import annotations

# Categorical: identity. Slot 1 is the periwinkle anchor. Same eight hues in
# both modes, stepped for each surface (dark is not an automatic flip).
CATEGORICAL_HUES = (
    "periwinkle", "orange", "teal", "gold", "rose", "green", "indigo", "red",
)
CATEGORICAL_LIGHT = (
    "#656dd7", "#d67523", "#1ea28f", "#c69612",
    "#d36a96", "#308639", "#5e3d9e", "#cb4644",
)
CATEGORICAL_DARK = (
    "#7d88e6", "#c56c21", "#0f9b89", "#b3880f",
    "#c1628a", "#3e8b44", "#9675cc", "#ca5551",
)
# How many leading slots survive the all-pairs gate (scatter/bubble/maps).
ALL_PAIRS_SAFE_SLOTS = 3

# Sequential: magnitude. One hue (periwinkle, OKLCH hue 277), light to dark.
# Keys are ramp steps in the reference-palette convention.
RAMP_STEPS = (100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700)
RAMP = {
    100: "#d6dcfd", 150: "#c8d0fb", 200: "#bac4f8", 250: "#abb6f4",
    300: "#9da8f0", 350: "#8c97e8", 400: "#7b86e0", 450: "#6b74d8",
    500: "#5d64ca", 550: "#5056b6", 600: "#4449a1", 650: "#393c8c",
    700: "#2d2f77",
}
# Ordinal bounds (validated): the step nearest the surface must clear 2:1.
ORDINAL_LIGHT_MIN_STEP = 300   # on the light surface, start no lighter
ORDINAL_DARK_MAX_STEP = 500    # on the dark surface, go no darker


def sequential(n: int, mode: str = "light") -> list[str]:
    """n evenly spaced ramp hexes, light to dark, honoring the ordinal bounds.

    For a continuous fill (heatmap) use RAMP directly; this helper is for
    discrete ordered marks, where every step must stay legible on the surface.
    """
    if mode == "light":
        usable = [s for s in RAMP_STEPS if s >= ORDINAL_LIGHT_MIN_STEP]
    else:
        usable = [s for s in RAMP_STEPS if s <= ORDINAL_DARK_MAX_STEP]
    if n <= 1:
        return [RAMP[usable[len(usable) // 2]]]
    idx = [round(i * (len(usable) - 1) / (n - 1)) for i in range(n)]
    return [RAMP[usable[i]] for i in idx]


# Diverging: polarity. Periwinkle (cool) vs copper (warm), neutral midpoint,
# equal arms, ordered midpoint-outward. Arms are stepped per mode: on light the
# extremes darken, on dark they lighten, so the extreme always carries the most
# contrast against its surface.
DIVERGING_MID_LIGHT = "#efeff4"
DIVERGING_MID_DARK = "#35353b"
DIVERGING_COOL_LIGHT = ("#b5bbde", "#97a0da", "#7a84d4", "#6067cd")
DIVERGING_WARM_LIGHT = ("#ddb499", "#d1966d", "#c3773e", "#ab5d1d")
DIVERGING_COOL_DARK = ("#4449a1", "#5d64ca", "#7b86e0", "#9da8f0")
DIVERGING_WARM_DARK = ("#94582a", "#b46c36", "#d38246", "#e79e6b")

# Status: state, reserved, mode-invariant, never a series color. Always paired
# with an icon or a word; on the light surface warning and serious sit below
# 3:1 by design and the pairing is the mitigation.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Chart chrome and ink, periwinkle-cast neutrals. The surfaces here are the
# ones the categorical palettes were validated against; change one, revalidate.
CHROME_LIGHT = {
    "surface": "#fbfbfe",     # chart surface (validator input)
    "page": "#f7f7fc",        # page plane behind cards
    "ink": "#0e0e14",         # primary text
    "ink_secondary": "#504f5c",
    "ink_muted": "#8a8894",   # axis labels, captions
    "gridline": "#e3e2ee",
    "baseline": "#c4c3d2",
}
CHROME_DARK = {
    "surface": "#17171f",
    "page": "#101016",
    "ink": "#ffffff",
    "ink_secondary": "#c2c1d0",
    "ink_muted": "#8a8894",
    "gridline": "#2b2b35",
    "baseline": "#3a3a46",
}

# The deck reads the same home: a periwinkle-washed background with darker
# periwinkle accents (Ben's decision 6). Charts placed on the wash should use
# the light-mode palette; the wash is close enough to the validated surface
# that the results carry, but keep direct labels on (the relief rule).
DECK = {
    "wash": "#e2e7fc",        # slide background
    "wash_soft": "#eff1fc",   # content panels on the wash
    "accent": "#2d2f77",      # headings, emphasis (ramp 700)
    "accent_soft": "#5056b6", # secondary emphasis (ramp 550)
    "ink": "#0e0e14",
    "ink_secondary": "#504f5c",
}


def categorical(n: int, mode: str = "light") -> list[str]:
    """The first n categorical hexes in fixed slot order (n > 8 raises).

    More than eight series on one chart is a design defect: fold to "Other"
    or facet, never invent a ninth hue.
    """
    base = CATEGORICAL_LIGHT if mode == "light" else CATEGORICAL_DARK
    if n > len(base):
        raise ValueError(
            f"{n} series need folding or faceting: the palette has "
            f"{len(base)} slots and hues are never cycled"
        )
    return list(base[:n])
