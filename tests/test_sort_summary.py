"""Tests for the pure (SpikeInterface-free) side of the array/yield summary:
persistence round-trip + the formatting helpers the menu/report/compare render.

``compute_summary`` itself is SpikeInterface-backed and exercised against a real
saved analyzer elsewhere; here we pin the schema-consuming helpers so the menu
(which imports no SpikeInterface) and the HTML surfaces stay correct.
"""
import sys

sys.path.insert(0, "scripts")
import sort_summary as ss


def _summary(**over):
    """A representative summary dict (the schema compute_summary emits)."""
    base = {
        "sorter": "tridesclous2", "n_units": 14, "n_channels": 16,
        "n_active_channels": 10, "duration_s": 20.0, "units_in_uV": True,
        "gain_to_uV": 0.25,
        "v_pp_uV": {"median": 10.061, "mean": 11.0, "min": 4.0, "max": 30.0},
        "snr": {"median": 5.247, "mean": 5.5, "min": 3.0, "max": 12.0},
        "noise_floor_uV": {"median": 1.001, "mean": 1.0, "min": 0.9, "max": 1.7,
                           "per_channel": [1.0] * 16},
        "yield_pct": 62.5, "units_per_channel": 0.875, "units_per_active_channel": 1.4,
        "active_channels": [str(i) for i in range(10)],
        "per_unit": [{"unit": 1, "v_pp_uV": 10.0, "snr": 5.2, "best_channel": "3"}],
    }
    base.update(over)
    return base


def test_headline_row_has_six_metrics_in_uV():
    row = ss.headline_row(_summary())
    assert list(row) == ["V_pp", "SNR", "noise floor", "yield (% active electrodes)",
                         "units / ch", "units / active ch"]
    assert row["V_pp"] == "10.061 µV"
    assert row["noise floor"] == "1.001 µV"
    assert row["yield (% active electrodes)"] == "62.5% (10/16)"
    assert row["units / ch"] == "0.875"
    assert row["units / active ch"] == "1.4"


def test_yield_cell_states_the_shrunken_denominator_when_channels_were_excluded():
    # PRE1: excluding a bad channel shrinks the yield denominator. The cell must say
    # so — a smaller denominator quietly inflating the percentage is the failure mode.
    row = ss.headline_row(_summary(n_channels=15, n_active_channels=10, yield_pct=66.7,
                                   excluded_channels=["3"]))
    assert row["yield (% active electrodes)"] == "66.7% (10/15 sorted; 1 excluded as bad)"


def test_yield_cell_is_unchanged_when_nothing_was_excluded():
    assert ss.headline_row(_summary(excluded_channels=[]))[
        "yield (% active electrodes)"] == "62.5% (10/16)"
    # and for a summary written before the field existed at all
    assert ss.headline_row(_summary())["yield (% active electrodes)"] == "62.5% (10/16)"


def test_csv_row_counts_excluded_channels():
    assert ss.csv_row(_summary(excluded_channels=["3", "9"]))["n_excluded_channels"] == 2
    assert ss.csv_row(_summary())["n_excluded_channels"] == 0


def test_empty_summary_carries_the_exclusion():
    empty = ss._empty_summary("simple", n_channels=15, units_in_uV=True,
                              excluded_channels=["3"])
    assert empty["excluded_channels"] == ["3"] and empty["n_channels"] == 15


def test_headline_row_falls_back_to_au_without_gain():
    row = ss.headline_row(_summary(units_in_uV=False))
    assert row["V_pp"].endswith("a.u.")
    assert row["noise floor"].endswith("a.u.")


def test_format_card_lines():
    card = ss.format_card(_summary())
    assert any(line.startswith("V_pp: ") for line in card)
    assert len(card) == 6


def test_csv_row_columns_match():
    r = ss.csv_row(_summary())
    assert set(r) == set(ss.CSV_COLUMNS)
    assert r["v_pp_uV_median"] == 10.061
    assert r["yield_pct"] == 62.5
    assert r["sorter"] == "tridesclous2"


def test_none_medians_render_as_dash():
    empty = ss._empty_summary("simple", n_channels=16, units_in_uV=True, duration_s=5.0)
    row = ss.headline_row(empty)
    assert row["V_pp"] == "—" and row["SNR"] == "—" and row["noise floor"] == "—"
    # yield/units are real zeros (no units), not dashes
    assert row["yield (% active electrodes)"] == "0% (0/16)"


def test_write_then_load_roundtrip(tmp_path):
    s = _summary()
    path = ss.write_summary(s, tmp_path)
    assert path.exists() and (tmp_path / "summary.csv").exists()
    loaded = ss.load_summary(tmp_path)
    assert loaded["n_units"] == 14
    assert ss.headline_row(loaded)["V_pp"] == "10.061 µV"


def test_load_summary_missing_returns_none(tmp_path):
    assert ss.load_summary(tmp_path) is None
    assert ss.load_summary(tmp_path / "nope") is None


# --- W1 slice 1: the quality rule's one owner ------------------------------- #
def test_quality_pass_tristate_flags():
    import sort_summary as ss
    nan = float("nan")
    rows = [
        {"snr": 6, "isi_violations_ratio": 0.1},          # passes evaluable subset
        {"snr": 6, "isi_violations_ratio": 2.0},          # fails ISI
        {"snr": nan, "isi_violations_ratio": nan},        # nothing judgeable -> None
        {"snr": 3.0},                                     # fails SNR (>=4)
    ]
    n, flags = ss.quality_pass(rows)
    assert n == 1 and flags == [True, False, None, False]


def test_load_quality_rule_overrides_and_drops_junk(tmp_path):
    import json
    import sort_summary as ss
    cfg = tmp_path / ".si_menu.json"
    cfg.write_text(json.dumps({"quality_rule": {
        "snr_min": 7, "presence_ratio_min": True, "unknown_key": 1}}))
    rule = ss.load_quality_rule(cfg)
    assert rule["snr_min"] == 7.0
    assert rule["presence_ratio_min"] == 0.9      # bool is junk -> default kept
    assert "unknown_key" not in rule
    assert "SNR ≥ 7" in ss.rule_text(rule)
    # No config at all -> pure defaults.
    assert ss.load_quality_rule(tmp_path / "missing.json") == ss.DEFAULT_QUALITY_RULE


def test_load_quality_rule_survives_non_dict_config(tmp_path):
    # W1 review F2: "quality_rule": "strict" must not take out the report verdict.
    import json
    import sort_summary as ss
    for bad in ('"strict"', "5", "[1, 2]", "null"):
        (tmp_path / "cfg.json").write_text('{"quality_rule": %s}' % bad)
        assert ss.load_quality_rule(tmp_path / "cfg.json") == ss.DEFAULT_QUALITY_RULE
