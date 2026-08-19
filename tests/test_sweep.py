"""Tests for the sorter sweep: the pair test (compare.py) and its page.

The pair test is pinned over synthetic ``NumpySorting``s, so none of it needs a
recording or a sorter: each case builds a reference with two units on one
electrode and a sort that splits, merges, half-finds or misses them, and asserts
the verdict. Nothing here asserts unit counts of a real sort: tridesclous2 is
measured non-deterministic on this recording, so counts are never a criterion.

The page is pinned over an injected run store, including the rows that exist to
be honest: a sorter with no run, a run whose sort never saved, and a run that
found nothing must each render as a row that says so.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import compare  # noqa: E402
import sweep_page  # noqa: E402

FS = 30_000.0
# Two reference units on ONE electrode: the pair the test exists for. Spikes sit
# 1000 frames (33 ms) apart, far outside the 2 ms coincidence window.
REF_A = [1000 * i for i in range(1, 21)]                  # ch5#1, 20 spikes
REF_B = [500_000 + 1000 * i for i in range(1, 21)]        # ch5#2, 20 spikes
FAR = [2_000_000 + 1000 * i for i in range(1, 21)]        # coincides with neither


def _sorting(trains: dict):
    """A NumpySorting from {unit id: [frames]}, no recording needed."""
    import numpy as np
    import spikeinterface.full as si

    return si.NumpySorting.from_unit_dict(
        [{u: np.asarray(f, dtype="int64") for u, f in trains.items()}],
        sampling_frequency=FS)


@pytest.fixture
def pair_test(monkeypatch):
    """Run compare.manual_pair_test over injected sortings; returns its dict."""
    def _run(offline, reference=None, labels=("ch5#1", "ch5#2"), window_s=132.0,
             nev_path="manual.nev", refs=None, exc=None):
        monkeypatch.setattr(compare, "_load",
                            lambda s, curated=False, run=None: (offline, window_s))

        def _read_spikes(data_dir=None, **kw):
            if exc is not None:
                raise exc
            return reference

        monkeypatch.setattr(compare.bio, "read_spikes", _read_spikes)
        monkeypatch.setattr(compare.bio, "online_unit_labels",
                            lambda s: list(labels) if labels is not None else None)
        monkeypatch.setattr(compare.bio, "find_reference_nevs",
                            lambda d=None: list(refs if refs is not None else []))
        return compare.manual_pair_test("tridesclous2", nev_path=nev_path)

    return _run


def _pair(got, electrode=5):
    return next(p for p in got["pairs"] if p["electrode"] == electrode)


# --------------------------------------------------------------------------- #
# The four verdicts
# --------------------------------------------------------------------------- #
def test_two_distinct_units_one_per_neuron_is_a_split(pair_test):
    reference = _sorting({0: REF_A, 1: REF_B})
    offline = _sorting({7: REF_A, 8: REF_B})
    pair = _pair(pair_test(offline, reference))

    assert pair["verdict"] == compare.PAIR_SPLIT
    assert sorted(pair["sorter_units"]) == ["7", "8"]
    assert pair["distinct_min"] == 1.0


def test_one_unit_carrying_both_neurons_is_merged(pair_test):
    """The tridesclous2 shape: one unit holds the whole electrode."""
    reference = _sorting({0: REF_A, 1: REF_B})
    offline = _sorting({4: REF_A + REF_B, 5: FAR})
    pair = _pair(pair_test(offline, reference))

    assert pair["verdict"] == compare.PAIR_MERGED
    assert pair["sorter_units"] == ["4"] and pair["carrier"] == "4"
    assert pair["carrier_min"] == 1.0
    # The best distinct pairing is reported whatever the verdict, so a merged
    # pair shows how far the runner-up was from carrying the other neuron.
    assert pair["distinct_min"] == 0.0
    assert len(pair["assignment"]) == 2


def test_finding_only_one_of_the_two_says_so(pair_test):
    reference = _sorting({0: REF_A, 1: REF_B})
    offline = _sorting({4: REF_A, 5: FAR})
    pair = _pair(pair_test(offline, reference))

    assert pair["verdict"] == compare.PAIR_ONE
    assert pair["sorter_units"] == ["4"]


def test_finding_neither_is_its_own_verdict(pair_test):
    reference = _sorting({0: REF_A, 1: REF_B})
    offline = _sorting({4: REF_A[:5] + REF_B[:5]})       # a quarter of each
    pair = _pair(pair_test(offline, reference))

    assert pair["verdict"] == compare.PAIR_NEITHER
    assert pair["sorter_units"] == []


def test_the_split_bar_is_where_it_says_it_is(pair_test):
    """Just under SPLIT_RECOVERY is not a split, and not a merge either."""
    reference = _sorting({0: REF_A, 1: REF_B})
    offline = _sorting({4: REF_A[:15], 5: REF_B[:15]})    # 15 of 20 = 0.75
    pair = _pair(pair_test(offline, reference))
    assert pair["verdict"] == compare.PAIR_NEITHER
    assert pair["distinct_min"] == pytest.approx(0.75)

    offline = _sorting({4: REF_A[:16], 5: REF_B[:16]})    # 16 of 20 = 0.80
    pair = _pair(pair_test(offline, reference))
    assert pair["verdict"] == compare.PAIR_SPLIT
    assert pair["distinct_min"] == pytest.approx(compare.SPLIT_RECOVERY)


# --------------------------------------------------------------------------- #
# Recovery, and what is and is not a pair
# --------------------------------------------------------------------------- #
def test_recovery_is_the_reference_direction_so_density_cannot_hide_it(pair_test):
    """Our unit carrying ten times the events still recovered the human's unit.

    Symmetric agreement collapses under that asymmetry; recovery is the fraction
    of the REFERENCE unit we carry, and it must stay at 1.0.
    """
    reference = _sorting({0: REF_A, 1: REF_B})
    offline = _sorting({4: REF_A + [3_000_000 + 137 * i for i in range(200)], 5: REF_B})
    got = pair_test(offline, reference)

    rows = {r["unit"]: r for r in got["by_reference"]}
    assert rows["ch5#1"]["recovered"] == 1.0 and rows["ch5#1"]["best_unit"] == "4"
    assert rows["ch5#1"]["recovered_fully"] is True
    assert _pair(got)["verdict"] == compare.PAIR_SPLIT


def test_an_electrode_with_one_unit_is_not_a_pair(pair_test):
    reference = _sorting({0: REF_A, 1: REF_B})
    got = pair_test(_sorting({4: REF_A, 5: REF_B}), reference,
                    labels=("ch5#1", "ch7#1"))
    assert got["pairs"] == []
    assert [r["unit"] for r in got["by_reference"]] == ["ch5#1", "ch7#1"]


def test_unsorted_and_noise_slots_never_become_a_pair(pair_test):
    """Slot 0 is threshold crossings and 255 is noise: neither is a sorted unit,
    so an electrode carrying one real unit beside them is not a pair."""
    reference = _sorting({0: REF_A, 1: REF_B, 2: FAR})
    got = pair_test(_sorting({4: REF_A}), reference,
                    labels=("ch5#0", "ch5#1", "ch5#255"))
    assert [r["unit"] for r in got["by_reference"]] == ["ch5#1"]
    assert got["pairs"] == []


def test_the_pair_test_refuses_rather_than_guessing(pair_test):
    offline = _sorting({4: REF_A})
    reference = _sorting({0: REF_A})
    assert pair_test(offline, reference, nev_path=None) is None      # no reference
    assert pair_test(None, reference) is None                        # no saved sort
    assert pair_test(offline, exc=FileNotFoundError("nope")) is None  # loader refused
    assert pair_test(offline, reference, labels=None) is None        # classes unreadable
    assert pair_test(offline, reference, labels=("ch5#0",)) is None   # nothing sorted


# --------------------------------------------------------------------------- #
# The page: honest rows, and the verdict it states
# --------------------------------------------------------------------------- #
def _run_dir(out, sorter, run_id, *, units=3, seconds=132.0, analyzer=True,
             noise=4.02, wall=30.0, docker=False):
    d = out / sorter / "runs" / run_id
    d.mkdir(parents=True)
    if analyzer:
        (d / "analyzer").mkdir()
    (d / "run_info.json").write_text(json.dumps({
        "sorter": sorter, "run_id": run_id, "smoke": False, "n_units": units,
        "created": "2026-08-19T05:00:00", "effective_seconds": seconds,
        "wall_seconds": wall, "docker": docker, "si_version": "0.104.3",
        "freq_min": 300.0, "freq_max": 6000.0, "n_dropped_analog": 6,
        "channel_ids": [str(i) for i in range(16)], "probe_id": "nnx-a1x16-3mm-100",
        "preprocessing": {"reference": "global median"}, "bad_channels": {"excluded": []},
        "params": {"effective": {"detect_threshold": 5.0}, "overrides": {}},
    }), encoding="utf-8")
    (d / "summary.json").write_text(json.dumps(
        {"sorter": sorter, "n_units": units, "noise_floor_uV": {"median": noise}}),
        encoding="utf-8")
    return d


CANNED = {
    "reference": "manual.nev", "delta_ms": 2.0, "split_recovery": 0.8,
    "window_s": 132.0, "cropped": False, "n_reference_units": 2, "n_sorter_units": 3,
    "by_reference": [
        {"unit": "ch5#1", "electrode": 5, "slot": 1, "n_reference_spikes": 475,
         "best_unit": "4", "recovered": 0.99, "recovered_fully": True},
        {"unit": "ch5#2", "electrode": 5, "slot": 2, "n_reference_spikes": 753,
         "best_unit": "4", "recovered": 1.0, "recovered_fully": True}],
    "pairs": [{"electrode": 5, "units": ["ch5#1", "ch5#2"], "verdict": compare.PAIR_MERGED,
               "sorter_units": ["4"], "distinct_min": 0.3, "carrier": "4",
               "carrier_min": 0.99,
               "assignment": [{"unit": "ch5#1", "sorter_unit": "4", "recovered": 0.99},
                              {"unit": "ch5#2", "sorter_unit": "9", "recovered": 0.3}]}],
}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """An injected run store; returns its outputs/ directory."""
    monkeypatch.setattr(sweep_page.bio, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sweep_page.compare, "manual_pair_test",
                        lambda sorter, **kw: dict(CANNED))
    return tmp_path / "outputs"


def test_every_roster_sorter_gets_a_row_even_with_nothing_saved(store):
    _run_dir(store, "tridesclous2", "20260819-050000-aaaaaa", units=16)
    _run_dir(store, "spykingcircus2", "20260819-050100-bbbbbb", units=0)
    _run_dir(store, "lupin", "20260819-050200-cccccc", analyzer=False)
    data = sweep_page.sweep(["tridesclous2", "spykingcircus2", "lupin", "waveclus"])

    status = {r["sorter"]: r["status"] for r in data["rows"]}
    assert status == {"tridesclous2": sweep_page.S_JUDGED,
                      "spykingcircus2": sweep_page.S_NO_UNITS,
                      "lupin": sweep_page.S_NO_SORT,
                      "waveclus": sweep_page.S_NO_RUN}
    # Every non-judged row names what the store actually holds (never a blank).
    assert all(r["note"] for r in data["rows"] if r["status"] != sweep_page.S_JUDGED)


def test_a_run_that_died_before_saving_its_record_is_named(store):
    (store / "mountainsort5" / "runs" / "20260819-050300-dddddd" / "sorter_output").mkdir(
        parents=True)
    row = sweep_page.sorter_row("mountainsort5")
    assert row["status"] == sweep_page.S_NO_SORT
    assert "20260819-050300-dddddd" in row["note"]


def test_the_page_states_the_honest_rows_and_stays_self_contained(store, tmp_path):
    _run_dir(store, "tridesclous2", "20260819-050000-aaaaaa", units=16, wall=35.4)
    _run_dir(store, "waveclus", "20260819-050400-eeeeee", units=3, docker=True, wall=250.0)
    out = sweep_page.build_page(tmp_path / "sweep.html",
                                ["tridesclous2", "waveclus", "simple"])
    raw = out.read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))

    # Self-contained: no scripts, and no URL that is not the SVG namespace (which
    # is never fetched), so the page opens with no network at all.
    assert "<script" not in raw and "src=" not in raw
    assert [u for u in re.findall(r"https?://[^\"' >]+", raw) if "w3.org" not in u] == []
    # Ben's boundary: no em dashes on any surface. Written as an escape so this
    # file itself stays clean for the repo-wide grep.
    assert "\u2014" not in raw
    assert "raw sorter output, before any curation" in text
    assert "20260819-050000-aaaaaa" in text        # every number names its run
    assert sweep_page.S_NO_RUN in text             # the un-swept sorter is a row
    assert "Docker image" in text and "installed locally" in text
    assert "detect_threshold" in text              # the effective parameters, stated
    assert "4.02 µV" in text and "250 s" in text   # noise floor + runtime


def test_the_verdict_is_computed_from_the_rows(store):
    _run_dir(store, "tridesclous2", "20260819-050000-aaaaaa", units=16)
    data = sweep_page.sweep(["tridesclous2"])
    assert sweep_page.verdict(data)["headline"] == "No sorter splits the pairs."
    assert sweep_page.verdict(data)["splitters"] == []

    split = dict(CANNED)
    split["pairs"] = [{**CANNED["pairs"][0], "verdict": compare.PAIR_SPLIT,
                       "sorter_units": ["4", "9"]}]
    data["rows"][0]["pair_test"] = split
    data["judged"][0]["pair_test"] = split
    got = sweep_page.verdict(data)
    assert got["splitters"] == ["tridesclous2"] and "splits the pairs" in got["headline"]


def test_a_docker_row_says_where_its_parameter_values_came_from(store):
    _run_dir(store, "waveclus", "20260819-050400-eeeeee", units=3, docker=True)
    data = sweep_page.sweep(["waveclus"])
    html = sweep_page._params_section(data)
    assert "ran in a Docker image" in html
    assert "0.104.3" in html            # what the record can honestly state


def test_a_partial_sweep_does_not_overclaim(store):
    """Review F4: with unjudged rows in the roster the headline names how many
    sorters were actually judged instead of claiming "no sorter"."""
    _run_dir(store, "tridesclous2", "20260819-050000-aaaaaa", units=16)
    data = sweep_page.sweep(["tridesclous2", "kilosort4"])
    v = sweep_page.verdict(data)
    assert v["headline"] == "The one judged sorter does not split the pairs."
    assert "1 of 2 sorters could be judged" in v["lede"]
    assert "exactly what tridesclous2 does" in v["lede"]

    data_no_tdc2 = sweep_page.sweep(["kilosort4"])
    v2 = sweep_page.verdict(data_no_tdc2)
    assert v2["headline"] == "Nothing to judge yet."
