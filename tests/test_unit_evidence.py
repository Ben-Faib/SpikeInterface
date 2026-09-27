"""Tests for unit_evidence: the Judge screen's per-unit evidence as plain data.

Runs on a small synthetic sort with a known gain, so the µV gate is checked the
way it bites on the rig: an analyzer that already returns µV and one that
returns native counts must both come back in µV, neither scaled twice. The
refractory count is pinned against a hand count on a unit given injected
violations, and the missing-extension and unknown-unit paths degrade/raise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import unit_evidence as ue  # noqa: E402

GAIN = 0.25                     # the rig's ~0.25 µV/count: a re-applied gain shows as 4x


@pytest.fixture(scope="module")
def sort(tmp_path_factory):
    """Two analyzers over one synthetic sort: µV with every extension, native bare."""
    si = pytest.importorskip("spikeinterface.full")
    root = tmp_path_factory.mktemp("evidence")
    rec, gt = si.generate_ground_truth_recording(
        durations=[10.0], num_channels=6, num_units=3, seed=0)
    rec.set_channel_gains(GAIN)
    rec.set_channel_offsets(0.0)
    rec = rec.save(folder=root / "recording")
    # Unit 0 gets 25 extra spikes 10 samples after real ones: refractory violations.
    fs = gt.get_sampling_frequency()
    samples, labels = [], []
    for u in gt.unit_ids:
        train = gt.get_unit_spike_train(u)
        if u == gt.unit_ids[0]:
            train = np.sort(np.concatenate([train, train[:25] + 10]))
        samples.append(train)
        labels.append(np.full(train.size, u))
    sorting = si.NumpySorting.from_samples_and_labels(
        [np.concatenate(samples)], [np.concatenate(labels)], fs)

    full = si.create_sorting_analyzer(sorting, rec, folder=root / "uv",
                                      format="binary_folder", sparse=False)
    full.compute(["random_spikes", "templates", "noise_levels", "spike_amplitudes"])
    full.compute("quality_metrics", metric_names=["isi_violation"])
    bare = si.create_sorting_analyzer(sorting, rec, folder=root / "native",
                                      format="binary_folder", sparse=False,
                                      return_in_uV=False)
    bare.compute(["random_spikes", "templates"])
    return {"uv": root / "uv", "native": root / "native", "sorting": sorting,
            "full": full, "unit": str(gt.unit_ids[0])}


def test_waveforms_cover_the_shown_channels_around_the_peak(sort):
    ev = ue.evidence_for_units(sort["uv"], neighbors=1, wave_points=40)
    assert set(ev) == {str(u) for u in sort["sorting"].unit_ids}
    for e in ev.values():
        assert list(e["waveforms"]) == e["channels"]
        assert e["peak_channel"] in e["channels"]
        assert 1 <= len(e["channels"]) <= 3
        assert all(len(w) <= 40 for w in e["waveforms"].values())
        peak = e["waveforms"][e["peak_channel"]]
        assert abs(peak[e["peak_index"]]) == max(abs(v) for v in peak)
    json.dumps(ev)                                   # plain data, all the way down


def test_values_are_microvolts_never_scaled_twice(sort):
    u = sort["unit"]
    e_uv = ue.unit_evidence(sort["uv"], u)
    e_native = ue.unit_evidence(sort["native"], u)
    tmpl = sort["full"].get_extension("templates").get_unit_template(u, operator="average")
    ch = [str(c) for c in sort["full"].channel_ids].index(e_uv["peak_channel"])
    # The µV analyzer's own template trough, unscaled, is what comes back...
    assert min(e_uv["waveforms"][e_uv["peak_channel"]]) == pytest.approx(
        float(tmpl[:, ch].min()), abs=1e-2)
    # ...and a native-count analyzer is converted to the same µV, not 4x off.
    for c in e_uv["channels"]:
        assert e_native["waveforms"][c] == pytest.approx(e_uv["waveforms"][c], abs=1e-2)
    assert e_uv["units_in_uV"] and e_native["units_in_uV"]


def test_isi_counts_and_refractory_match_a_hand_count(sort):
    u = sort["unit"]
    e = ue.unit_evidence(sort["uv"], u, isi_max_ms=25.0, isi_bin_ms=0.5)
    fs = sort["sorting"].get_sampling_frequency()
    isi_ms = np.diff(sort["sorting"].get_unit_spike_train(u) / fs) * 1000.0
    assert sum(e["isi"]["counts"]) == int(np.sum(isi_ms < 25.0))
    assert len(e["isi"]["counts"]) == 50
    assert e["isi"]["refractory_ms"] == 1.5
    assert e["isi"]["n_refractory"] == int(np.sum(isi_ms < 1.5)) >= 25
    qm = sort["full"].get_extension("quality_metrics").get_data()
    assert e["isi"]["n_refractory"] == int(qm.loc[qm.index[0], "isi_violations_count"])
    assert e["isi"]["ratio"] == pytest.approx(float(qm.loc[qm.index[0],
                                                           "isi_violations_ratio"]))


def test_amplitude_block_present_or_honestly_none(sort):
    u = sort["unit"]
    e = ue.unit_evidence(sort["uv"], u, amp_bins=10)
    assert len(e["amplitude"]["t_s"]) == len(e["amplitude"]["n"]) == 10
    assert sum(e["amplitude"]["n"]) == e["n_spikes"]
    bare = ue.unit_evidence(sort["native"], u)
    assert bare["amplitude"] is None
    assert bare["isi"]["ratio"] is None                 # no saved metrics: no ratio


def test_unknown_unit_raises_keyerror(sort):
    with pytest.raises(KeyError, match="not in this sort"):
        ue.unit_evidence(sort["uv"], "no-such-unit")
