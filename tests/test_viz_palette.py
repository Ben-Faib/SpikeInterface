"""Pins for viz_palette: the one home for chart colors.

The color VALUES are validated by the dataviz skill's validator (the command
and measured results live in the module docstring); these tests pin the
structural rules the surfaces rely on, so a refactor cannot quietly break
them: fixed slot order, the no-cycling cap, ramp monotony, and the
per-mode ordinal bounds.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import viz_palette as vp


def test_categorical_slots_align_across_modes():
    assert len(vp.CATEGORICAL_LIGHT) == len(vp.CATEGORICAL_DARK) == len(vp.CATEGORICAL_HUES) == 8
    assert vp.CATEGORICAL_HUES[0] == "periwinkle"
    for hexes in (vp.CATEGORICAL_LIGHT, vp.CATEGORICAL_DARK):
        assert all(h.startswith("#") and len(h) == 7 for h in hexes)
        assert len(set(hexes)) == len(hexes), "duplicate slot color"


def test_categorical_never_cycles():
    assert vp.categorical(3) == list(vp.CATEGORICAL_LIGHT[:3])
    assert vp.categorical(8, mode="dark") == list(vp.CATEGORICAL_DARK)
    try:
        vp.categorical(9)
    except ValueError as e:
        assert "never cycled" in str(e)
    else:
        raise AssertionError("a 9th series must raise, not invent a hue")


def test_ramp_is_complete_and_keyed_by_its_steps():
    assert set(vp.RAMP) == set(vp.RAMP_STEPS)
    assert len(set(vp.RAMP.values())) == len(vp.RAMP_STEPS)


def test_sequential_honors_the_ordinal_bounds():
    light = vp.sequential(4, mode="light")
    dark = vp.sequential(4, mode="dark")
    assert light[0] == vp.RAMP[vp.ORDINAL_LIGHT_MIN_STEP]
    assert dark[-1] == vp.RAMP[vp.ORDINAL_DARK_MAX_STEP]
    assert len(light) == len(dark) == 4
    assert len(set(light)) == 4 and len(set(dark)) == 4


def test_diverging_arms_are_equal_and_distinct():
    for cool, warm in (
        (vp.DIVERGING_COOL_LIGHT, vp.DIVERGING_WARM_LIGHT),
        (vp.DIVERGING_COOL_DARK, vp.DIVERGING_WARM_DARK),
    ):
        assert len(cool) == len(warm)
        assert not set(cool) & set(warm)


def test_status_is_reserved_and_never_a_series_color():
    series = set(vp.CATEGORICAL_LIGHT) | set(vp.CATEGORICAL_DARK)
    assert not set(vp.STATUS.values()) & series
    assert set(vp.STATUS) == {"good", "warning", "serious", "critical"}
