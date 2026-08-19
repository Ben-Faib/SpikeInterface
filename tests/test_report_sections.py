"""Unit tests for the new report HTML sections (array/yield summary + probe map)
and the show_channels utility's pure helpers. A stub analyzer keeps these
SpikeInterface-free and fast; full rendering is exercised end-to-end elsewhere.
"""
import json
import sys

sys.path.insert(0, "scripts")
import report  # noqa: E402
import sort_summary as ss  # noqa: E402


class StubAnalyzer:
    """Minimal analyzer: just what _render_probe / _render_summary read."""
    def __init__(self, channel_ids, locations=None):
        self.channel_ids = channel_ids
        self._loc = locations

    def get_channel_locations(self):
        if self._loc is None:
            raise RuntimeError("no geometry")
        return self._loc


def _write_summary(tmp_path):
    s = {
        "sorter": "x", "n_units": 3, "n_channels": 4, "n_active_channels": 2,
        "duration_s": 20.0, "units_in_uV": True, "gain_to_uV": 0.25,
        "v_pp_uV": {"median": 84.0, "mean": 80.0, "min": 10.0, "max": 120.0},
        "snr": {"median": 8.0, "mean": 8.0, "min": 3.0, "max": 12.0},
        "noise_floor_uV": {"median": 4.0, "mean": 4.0, "min": 3.5, "max": 4.5,
                           "per_channel": [3.5, 4.0, 4.2, 4.5]},
        "yield_pct": 50.0, "units_per_channel": 0.75, "units_per_active_channel": 1.5,
        "active_channels": ["2", "3"],
        "per_unit": [{"unit": 1, "v_pp_uV": 84.0, "snr": 8.0, "best_channel": "3"}],
    }
    (tmp_path / "summary.json").write_text(json.dumps(s), encoding="utf-8")
    return s


def test_render_summary_from_saved_json(tmp_path):
    _write_summary(tmp_path)
    stub = StubAnalyzer(["1", "2", "3", "4"])
    html = report._render_summary(stub, tmp_path / "analyzer")
    assert "yield (% active electrodes)" in html
    assert "84" in html and "µV" in html          # V_pp headline
    assert "best ch" in html                        # per-unit table header


def test_render_summary_none_analyzer_and_no_summary(tmp_path):
    assert "unavailable" in report._render_summary(None, None)
    # analyzer present but no summary.json and compute would need SI -> skip cleanly
    stub = StubAnalyzer(["1", "2"])
    out = report._render_summary(stub, tmp_path / "analyzer")  # no summary.json here
    assert "unavailable" in out or "skip" in out or "No " in out


def test_render_probe_collection_sites(tmp_path):
    _write_summary(tmp_path)
    loc = [[0.0, 0.0], [0.0, 100.0], [0.0, 200.0], [0.0, 300.0]]
    stub = StubAnalyzer(["1", "2", "3", "4"], loc)
    html = report._render_probe(stub, tmp_path / "analyzer")
    assert "Collection sites" in html
    assert "active electrode" in html               # the ringed-active trace
    assert "noise" in html.lower()


def test_render_probe_no_geometry():
    stub = StubAnalyzer(["1", "2"], locations=None)  # get_channel_locations raises
    assert "no probe geometry" in report._render_probe(stub, None).lower()


def test_render_probe_none_analyzer():
    assert "unavailable" in report._render_probe(None, None)


def test_show_channels_resolves_probe():
    # Pure helper: no SI. Falls back to the default probe with no config/arg.
    import show_channels
    p = show_channels._resolve_probe(None)
    assert p is not None and p.get("name")
    # explicit name resolves too
    import probes
    assert show_channels._resolve_probe(probes.PLACEHOLDER_PROBE)["name"] == probes.PLACEHOLDER_PROBE


# --------------------------------------------------------------------------- #
# Bad-channel exclusion (PRE1) - the report must say WHICH channels left and,
# in the provenance line, WHO decided. On this rig detection flags nothing, so
# the manual-only path is the realistic one and must not credit the detector.
# --------------------------------------------------------------------------- #
def _bad(**over):
    """A run_info `bad_channels` record (the schema run_sorting writes)."""
    base = {"detected": [], "manual": [], "unknown": [], "excluded": [],
            "refused_auto": False, "max_fraction": 0.25, "n_remaining": 16,
            "enabled": True, "method": "mad",
            "params": {"seed": 0, "std_mad_threshold": 5.0}, "labels": {}}
    base.update(over)
    return base


def test_provenance_credits_the_detector_when_it_found_them():
    line = report._bad_channel_provenance(_bad(detected=["3"], excluded=["3"]))
    assert line == "bad channels excluded: 3 (mad)"


def test_provenance_says_manual_when_the_user_named_them():
    # The regression this pins: attributing a hand-named channel to "(mad)" credits
    # the detector with a call it never made - and here it never makes any.
    line = report._bad_channel_provenance(_bad(manual=["3"], excluded=["3"]))
    assert "named manually" in line and "(mad)" not in line


def test_provenance_names_both_sources_when_both_contributed():
    line = report._bad_channel_provenance(
        _bad(detected=["3"], manual=["9"], excluded=["3", "9"]))
    assert "3, 9" in line and "mad + manual" in line


def test_provenance_covers_the_three_no_exclusion_states():
    assert "none flagged" in report._bad_channel_provenance(_bad())
    assert "disabled" in report._bad_channel_provenance(_bad(enabled=False))
    refused = report._bad_channel_provenance(
        _bad(detected=[str(i) for i in range(5)], refused_auto=True))
    assert "too many to trust" in refused and "5 channels" in refused


def test_bad_channel_note_states_the_exclusion_and_is_silent_otherwise():
    note = report._bad_channel_note(_bad(manual=["3"], excluded=["3"]))
    assert "excluded as bad" in note and "common median reference" in note
    assert report._bad_channel_note(_bad()) == ""      # nothing left -> nothing said
    assert report._bad_channel_note(None) == ""        # a sort predating the feature


def test_probe_caveat_carries_the_exclusion():
    html = report._probe_caveat("independent", 6, _bad(manual=["3"], excluded=["3"]))
    assert "analog aux channel(s) were excluded" in html   # the aux drop still stated
    assert "excluded as bad" in html                        # and the bad channel too


def test_render_summary_states_the_shrunken_yield_denominator(tmp_path):
    s = _write_summary(tmp_path)
    s.update(n_channels=3, excluded_channels=["1"], yield_pct=66.7,
             noise_floor_uV={**s["noise_floor_uV"], "per_channel": [4.0, 4.2, 4.5]})
    (tmp_path / "summary.json").write_text(json.dumps(s), encoding="utf-8")
    html = report._render_summary(StubAnalyzer(["2", "3", "4"]), tmp_path / "analyzer")
    assert "excluded as bad" in html                        # the yield cell itself
    assert "neither the denominator nor the chart" in html  # the explaining note


def test_render_summary_says_nothing_extra_when_nothing_was_excluded(tmp_path):
    _write_summary(tmp_path)
    html = report._render_summary(StubAnalyzer(["1", "2", "3", "4"]), tmp_path / "analyzer")
    assert "excluded as bad" not in html


def test_run_stamp_on_a_curated_result_names_the_raw_run_not_the_anchor_dict():
    # A curated run_info has no run_id; it has curated_from (the raw run's PATH)
    # and curated_from_run (the anchor DICT). The first curated pass through the
    # strong-units block printed the dict repr in the stamp (clean-pass find).
    info = {
        "curated": True,
        "curated_from": "outputs/tridesclous2/runs/20260819-035117-c7184d",
        "curated_from_run": {"created": "2026-08-19T03:51:51", "n_units": 16},
        "created": "2026-08-19T03:54:03",
        "effective_seconds": 132.0, "total_seconds": 132.0,
    }
    stamp = report._run_stamp(info, "outputs/tridesclous2/runs/x/curated/analyzer",
                              "tridesclous2 · curated")
    assert "20260819-035117-c7184d" in stamp
    assert "{" not in stamp and "created" not in stamp


def test_run_stamp_on_a_legacy_curated_result_never_prints_the_sorter_as_a_run():
    # Legacy curated results live at outputs/<sorter>/curated - the path's name
    # is the sorter, which must not masquerade as a run id.
    info = {"curated": True, "curated_from": "outputs/tridesclous2",
            "created": "2026-08-18T20:00:00"}
    stamp = report._run_stamp(info, "outputs/tridesclous2/curated/analyzer",
                              "tridesclous2 · curated")
    assert "run <code>tridesclous2</code>" not in stamp


def _merge_rollup():
    """One merged unit (dense, impossible ISI) and one thin junk unit beside it."""
    summary = {"per_unit": [
        {"unit": 4, "v_pp_uV": 87.4, "snr": 7.64, "best_channel": "5"},
        {"unit": 11, "v_pp_uV": 26.6, "snr": 5.33, "best_channel": "12"},
    ]}
    metrics = {
        "4": dict(snr=7.64, isi_violations_ratio=1.358, presence_ratio=1.0),
        "11": dict(snr=5.33, isi_violations_ratio=107.77, presence_ratio=1.0),
    }
    return ss.unit_rollup(summary, metrics, spike_counts={"4": 7557, "11": 35})


def test_the_split_advisory_is_quoted_where_units_are_shown():
    html = report._render_strong_units(_merge_rollup(), "", None)
    # The block answers "do I need Phy?" up front, in the rollup's own words...
    assert "Do I need Phy?" in html
    assert ss.split_line(1, ["5"]) in html
    # ...and against the unit itself, beside the verdict it explains.
    assert 'class="advice"' in html
    assert html.count(ss.SPLIT_PHRASE) == 1        # the merged unit only
    # The criteria are stated wherever the advisory fires, never left implicit
    # (escaped: the rule text carries an apostrophe).
    import html as stdlib_html
    assert stdlib_html.escape(ss.split_rule_text()) in html


def test_a_sort_with_nothing_to_split_says_nothing_about_phy():
    summary = {"per_unit": [{"unit": 1, "v_pp_uV": 80.0, "snr": 9.0, "best_channel": "7"}]}
    rollup = ss.unit_rollup(summary, {"1": dict(snr=9.0, isi_violations_ratio=0.0,
                                                presence_ratio=1.0)},
                            spike_counts={"1": 5000})
    html = report._render_strong_units(rollup, "", None)
    assert "Do I need Phy?" not in html and 'class="advice"' not in html


def test_the_advisory_points_at_its_own_evidence():
    # The audit's coherence tie: the block that makes the claim links to the
    # section that draws it (and only when there is a claim to back up).
    assert 'href="#evidence"' in report._render_strong_units(_merge_rollup(), "", None)


# --------------------------------------------------------------------------- #
# Split evidence (GOAL_PRESENT item 6): the advisory's own proof.
# --------------------------------------------------------------------------- #
def test_evidence_degrades_honestly_without_a_sort():
    assert "No saved sort" in report._render_evidence(None, None)


def test_evidence_says_so_when_the_rollup_could_not_be_built():
    out = report._render_evidence(object(), {"rollup": None, "error": "RuntimeError('x')"})
    assert 'class="skip"' in out and "RuntimeError" in out


def test_isi_intervals_are_milliseconds_and_never_crash_on_a_lone_spike():
    import numpy as np
    isi = report._isi_ms([0.0, 0.001, 0.010])
    assert np.allclose(isi, [1.0, 9.0])
    assert report._isi_ms([0.5]).size == 0        # one spike -> no interval at all
    assert report._isi_ms([]).size == 0


def test_evidence_panels_lead_with_the_advised_units_and_stay_inside_the_budget():
    rollup = _merge_rollup()
    picked = report._panel_units(rollup)
    assert [u["unit"] for u in picked] == [4]     # the merged unit, not the thin junk
    # The budget is a cap, not a suggestion: a 40-unit merge storm must not turn
    # into 80 charts.
    many = {"units": [{"unit": i, "contact": "1", "strong": False,
                       "split_advice": "x"} for i in range(40)],
            "n_split_candidates": 40, "n_strong": 0}
    assert len(report._panel_units(many)) == report.EVIDENCE_MAX_PANELS


def test_report_chart_colour_comes_from_the_one_home():
    # Palette application (item 7): no chart hex may be reborn in report.py.
    import viz_palette as vp
    assert report.UNIT_PALETTE is vp.CATEGORICAL_LIGHT
    assert report.MARK == vp.CATEGORICAL_LIGHT[0]
    assert report.ACCENT == vp.RAMP[600]
    assert report.DIM_MARK == vp.CHROME_LIGHT["ink_muted"]
    assert report.RAMP_SCALE[0][1] == vp.RAMP[vp.RAMP_STEPS[0]]
    assert report._rgba("#656dd7", 0.5) == "rgba(101,109,215,0.5)"
