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


def test_load_quality_metrics_is_pure_and_nan_honest(tmp_path):
    """The per-unit metrics as the sort wrote them — read, never recomputed, and a
    cell the sort could not compute comes back None (a surface renders "–")."""
    (tmp_path / "quality_metrics.csv").write_text(
        ",firing_rate,snr,amplitude_cutoff,l_ratio\n"
        "0,0.2045,5.0409,,\n"
        "1,0.4772,5.2151,0.031,nan\n", encoding="utf-8")
    rows = ss.load_quality_metrics(tmp_path)
    assert list(rows) == ["0", "1"]
    # Column order is the file's, so a surface can lay them out as written.
    assert list(rows["0"]) == ["firing_rate", "snr", "amplitude_cutoff", "l_ratio"]
    assert rows["0"]["snr"] == 5.0409
    assert rows["0"]["amplitude_cutoff"] is None       # blank cell, not 0.0
    assert rows["1"]["l_ratio"] is None                # NaN, not 0.0
    assert rows["1"]["amplitude_cutoff"] == 0.031
    # A non-fatal metrics failure deletes the file — that is {} , never a crash.
    assert ss.load_quality_metrics(tmp_path / "nope") == {}


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


# --------------------------------------------------------------------------- #
# The per-contact rollup (the takeaway) — one home for "which units look real".
# --------------------------------------------------------------------------- #
def _rollup_summary():
    """Four units on three contacts; two share contact 7."""
    return _summary(n_units=4, per_unit=[
        {"unit": 0, "v_pp_uV": 20.0, "snr": 4.5, "best_channel": "5"},
        {"unit": 1, "v_pp_uV": 80.0, "snr": 9.0, "best_channel": "7"},
        {"unit": 2, "v_pp_uV": 30.0, "snr": 6.0, "best_channel": "7"},
        {"unit": 3, "v_pp_uV": 25.0, "snr": 5.0, "best_channel": "11"},
    ])


_CLEAN = {"nn_hit_rate": 0.95, "l_ratio": 0.02, "isolation_distance": 60.0}
_POOR = {"nn_hit_rate": 0.3, "l_ratio": 0.6, "isolation_distance": 5.0}


def test_rollup_ranks_accepted_first_by_snr_then_the_tail():
    metrics = {
        # unit 1 has the best SNR but fails the ISI criterion -> it is TAIL.
        "0": dict(snr=4.5, isi_violations_ratio=0.0, presence_ratio=1.0, **_CLEAN),
        "1": dict(snr=9.0, isi_violations_ratio=2.0, presence_ratio=1.0, **_CLEAN),
        "2": dict(snr=6.0, isi_violations_ratio=0.0, presence_ratio=1.0, **_CLEAN),
        "3": dict(snr=5.0, isi_violations_ratio=9.0, presence_ratio=1.0, **_CLEAN),
    }
    r = ss.unit_rollup(_rollup_summary(), metrics,
                       spike_counts={"0": 900, "1": 5000, "2": 4000, "3": 800})
    assert [u["unit"] for u in r["units"]] == [2, 0, 1, 3]   # accepted 6.0,4.5 then 9.0,5.0
    assert r["n_accepted"] == 2 and r["n_units"] == 4 and r["n_unjudged"] == 0
    assert r["n_strong"] == 2 and r["n_thin"] == 0
    assert r["strong_contacts"] == ["7", "5"]
    assert r["headline"] == "2 strong units (ch 7·5)"
    assert r["site_line"] == "strong at ch 7·5"
    # The rule is stated verbatim wherever the count is.
    assert r["rule_text"] == ss.rule_text(ss.DEFAULT_QUALITY_RULE)


def test_rollup_states_why_a_unit_is_sub_threshold_in_the_rules_words():
    metrics = {"1": {"snr": 9.0, "isi_violations_ratio": 2.0, "presence_ratio": 1.0}}
    r = ss.unit_rollup(_rollup_summary(), metrics)
    why = next(u["why"] for u in r["units"] if u["unit"] == 1)
    assert "ISI ratio ≤ 0.5" in why and "is 2" in why


def test_rollup_nan_never_masquerades_as_failure():
    # Every criterion NaN/absent -> "not judged", NOT a failure and NOT a pass.
    r = ss.unit_rollup(_rollup_summary(), {"0": {"snr": float("nan")}})
    u0 = next(u for u in r["units"] if u["unit"] == 0)
    assert u0["verdict"] is None and u0["verdict_word"] == "not judged"
    assert r["n_accepted"] == 0 and r["n_unjudged"] == 4
    assert "no criterion could be evaluated" in u0["why"]


def test_rollup_per_contact_counts_and_line():
    metrics = {
        "0": dict(snr=4.5, isi_violations_ratio=0.0, presence_ratio=1.0),
        "1": dict(snr=9.0, isi_violations_ratio=0.0, presence_ratio=1.0),
        "2": dict(snr=6.0, isi_violations_ratio=9.0, presence_ratio=1.0),
        "3": dict(snr=5.0, isi_violations_ratio=9.0, presence_ratio=1.0),
    }
    r = ss.unit_rollup(_rollup_summary(), metrics)
    by = {c["contact"]: c for c in r["contacts"]}
    assert by["7"]["n_accepted"] == 1 and by["7"]["n_other"] == 1
    assert by["5"]["n_accepted"] == 1 and by["5"]["n_other"] == 0
    assert by["11"]["n_accepted"] == 0 and by["11"]["n_other"] == 1
    assert "contact 7: 1 accepted + 1 sub-threshold candidate" in r["contact_line"]
    assert "contact 5: 1 accepted" in r["contact_line"]
    # A contact with no accepted unit is summarised, never dropped.
    assert "1 further contact" in r["contact_line"] and "no accepted unit" in r["contact_line"]


def test_isolation_phrase_thresholds_and_honesty_gates():
    # Too few spikes: the PCA metrics cannot mean anything, and it says so.
    assert ss.isolation_phrase(_CLEAN, n_spikes=10) == "too few spikes to judge"
    # SpikeInterface's degenerate isolation_distance is discarded, not believed.
    assert ss.isolation_phrase({"isolation_distance": 1e15},
                               n_spikes=5000) == "no isolation metrics — cannot judge"
    assert ss.isolation_phrase(_CLEAN, n_spikes=5000) == "clean"
    assert ss.isolation_phrase({"nn_hit_rate": 0.7}, n_spikes=5000) == "mostly separate"
    # Poor + a co-located unit names the neighbour it overlaps.
    assert ss.isolation_phrase(_POOR, n_spikes=5000, contact="7",
                               shares_contact_with=1) == "overlaps another unit on ch 7"
    assert ss.isolation_phrase(_POOR, n_spikes=5000, contact="7",
                               shares_contact_with=2) == "overlaps 2 other units on ch 7"
    # Poor but alone on its contact: no neighbour is named, because none is known.
    assert ss.isolation_phrase(_POOR, n_spikes=5000, contact="7") == \
        "not clearly separate from the other units"
    # An UNCOUNTED unit gets its own phrase: without the count the too-few gate
    # cannot fire, and scoring the metrics anyway would let the same unit read
    # "clean" here and "too few spikes to judge" on a surface that counted (F4).
    assert ss.isolation_phrase(_CLEAN) == ss.UNKNOWN_SPIKES_PHRASE


def test_rollup_match_column_is_absent_not_guessed():
    r = ss.unit_rollup(_rollup_summary(), {})
    assert r["has_matches"] is False
    assert all(u["match"] is None for u in r["units"])
    r2 = ss.unit_rollup(_rollup_summary(), {},
                        matches={"1": {"unit": "ch7#1", "containment": 0.97}})
    assert r2["has_matches"] is True
    assert next(u["match"] for u in r2["units"] if u["unit"] == 1)["unit"] == "ch7#1"
    assert next(u["match"] for u in r2["units"] if u["unit"] == 0) is None


def test_rollup_on_a_sort_with_no_units():
    r = ss.unit_rollup(_summary(n_units=0, per_unit=[]), {})
    assert r["units"] == [] and r["n_accepted"] == 0 and r["n_strong"] == 0
    assert r["headline"] == "0 strong units"
    assert r["site_line"].startswith("no unit passes SNR")
    assert r["contact_line"] == "no units on any contact"


def test_rule_detail_and_quality_pass_agree():
    rows = [{"snr": 9.0, "isi_violations_ratio": 0.0},
            {"snr": 1.0, "isi_violations_ratio": 0.0},
            {"snr": float("nan")}]
    n, flags = ss.quality_pass(rows)
    assert (n, flags) == (1, [True, False, None])
    assert [ss.rule_detail(r)["flag"] for r in rows] == flags
    assert ss.rule_detail(rows[1])["failed"][0][0] == "SNR ≥ 4"


# --------------------------------------------------------------------------- #
# Review F2/F4 — "strong" must not flatter thin evidence, and an uncounted unit
# must not borrow the too-few phrase.
# --------------------------------------------------------------------------- #
def _thin_case(counts):
    """Unit 1 (SNR 9) dense and failing ISI; the rest pass on `counts` spikes."""
    metrics = {
        "0": dict(snr=4.5, isi_violations_ratio=0.0, presence_ratio=1.0),
        "1": dict(snr=9.0, isi_violations_ratio=0.6, presence_ratio=1.0),
        "2": dict(snr=6.0, isi_violations_ratio=0.0, presence_ratio=1.0),
        "3": dict(snr=5.0, isi_violations_ratio=0.0, presence_ratio=1.0),
    }
    return ss.unit_rollup(_rollup_summary(), metrics, spike_counts=counts)


def test_a_pass_on_too_few_spikes_is_hedged_not_called_strong():
    # 2 and 3 pass on 30 spikes; 0 passes on 5000.
    r = _thin_case({"0": 5000, "1": 6000, "2": 30, "3": 30})
    by = {u["unit"]: u for u in r["units"]}
    # The RULE's verdict is untouched — the pass-quality count must not move.
    assert [by[u]["verdict"] for u in (0, 2, 3)] == [True, True, True]
    assert r["n_accepted"] == 3
    # ...but only the unit whose evidence carries it is called strong.
    assert r["n_strong"] == 1 and r["n_thin"] == 2
    assert by[0]["strong"] is True and by[0]["verdict_word"] == "strong"
    assert by[2]["strong"] is False and by[2]["thin"] == "few"
    assert by[2]["verdict_word"] == "passes the rule · too few spikes to judge"
    # The headline splits, and the dashboard's line comes from the same fields.
    assert r["headline"] == "1 strong unit (ch 5) · 2 more pass the rule on thin evidence"
    assert r["site_line"] == "strong at ch 5 · 2 more pass the rule on thin evidence"
    # A thin pass never outranks a unit whose evidence could carry the claim.
    assert [u["unit"] for u in r["units"]][:1] == [0]
    assert [u["strong"] for u in r["units"]] == [True, False, False, False]


def test_when_every_pass_is_thin_the_headline_says_so_first():
    r = _thin_case({"0": 30, "1": 6000, "2": 30, "3": 30})
    assert r["n_accepted"] == 3 and r["n_strong"] == 0 and r["n_thin"] == 3
    assert r["headline"].startswith("no unit passes the rule on solid evidence · 3 pass it "
                                    "on thin evidence")
    assert r["site_line"].startswith("3 units pass the rule only on thin evidence")


def test_an_uncounted_pass_is_hedged_as_uncounted_not_as_too_few():
    # No spike_counts at all: the surfaces without a Sorting open must say what
    # they do not know, and must not call the unit strong on that basis (F4).
    r = ss.unit_rollup(_rollup_summary(),
                       {"0": dict(snr=4.5, isi_violations_ratio=0.0, presence_ratio=1.0,
                                  **_CLEAN)})
    u0 = next(u for u in r["units"] if u["unit"] == 0)
    assert u0["verdict"] is True and u0["strong"] is False
    assert u0["thin"] == "unknown"
    assert u0["verdict_word"] == "passes the rule · spike count unknown"
    assert u0["isolation"] == ss.UNKNOWN_SPIKES_PHRASE
    assert r["n_strong"] == 0 and r["n_thin"] == 1


def test_thin_reason_is_the_one_home_for_the_hedge():
    assert ss.thin_reason(True, 5000) == ""
    assert ss.thin_reason(True, 30) == "few"
    assert ss.thin_reason(True, None) == "unknown"
    # Only a PASS is ever hedged; a failure and a non-judgement are not "thin".
    assert ss.thin_reason(False, 30) == "" and ss.thin_reason(None, 30) == ""
