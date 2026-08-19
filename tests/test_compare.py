"""Tests for compare.py: saved-sort discovery + the --online (.nev) mode.

The online mode is pinned with synthetic ``NumpySorting``s so none of it needs a
recording: the Blackrock unit-id filtering (0 and 255 dropped, and *counted*),
the crop of the whole-recording reference down to the sort's window, the CLI's
two modes, and every degenerate state that must render a next step instead of a
crash. One integration test runs against this repo's real data and skips cleanly
when there is none.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import blackrock_io as bio  # noqa: E402
import compare  # noqa: E402

FS = 30_000.0


def _sorting(trains: dict):
    """A NumpySorting from {unit id: [frames]} — no recording needed."""
    import numpy as np
    import spikeinterface.full as si

    return si.NumpySorting.from_unit_dict(
        [{u: np.asarray(f, dtype="int64") for u, f in trains.items()}],
        sampling_frequency=FS)


def _text(path) -> str:
    """The page's visible text: markup and the inlined plotly/JS stripped."""
    import html as html_mod

    raw = Path(path).read_text(encoding="utf-8")
    body = re.sub(r"<script.*?</script>", "", raw, flags=re.S)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
    return html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))


def test_saved_sorters_finds_analyzer_dirs(tmp_path, monkeypatch):
    # Two sorters with an analyzer dir, one without.
    for name in ("tridesclous2", "mountainsort5"):
        (tmp_path / name / "analyzer").mkdir(parents=True)
    (tmp_path / "spykingcircus2").mkdir()
    monkeypatch.setattr(compare, "OUTPUT_DIR", tmp_path)
    found = compare.saved_sorters()
    assert found == ["mountainsort5", "tridesclous2"]  # sorted, only those with analyzer


# --------------------------------------------------------------------------- #
# Blackrock unit-id classes (the classifier itself lives in blackrock_io — see
# tests/test_blackrock_io.py; here it is only consumed)
# --------------------------------------------------------------------------- #
def test_split_keeps_only_online_sorted_units_and_counts_what_it_dropped():
    sorting = _sorting({0: [1, 2, 3], 1: [10, 20], 2: [30], 3: [40, 50, 60, 70]})
    labels = ["ch1#0", "ch1#1", "ch2#255", "ch2#2"]

    kept, accounting = compare.split_online_units(sorting, labels)

    assert list(kept.get_unit_ids()) == ["ch1#1", "ch2#2"]      # renamed to ch#unit
    assert len(kept.get_unit_spike_train("ch2#2")) == 4
    by_key = {c["key"]: c for c in accounting}
    assert by_key["sorted"] == {"key": "sorted", "label": bio.UNIT_CLASS_LABELS["sorted"],
                                "n_units": 2, "n_spikes": 6, "kept": True}
    assert (by_key["unsorted"]["n_units"], by_key["unsorted"]["n_spikes"]) == (1, 3)
    assert (by_key["noise"]["n_units"], by_key["noise"]["n_spikes"]) == (1, 1)
    assert not by_key["unsorted"]["kept"] and not by_key["noise"]["kept"]
    assert "other" not in by_key                                # absent classes stay off the page


def test_split_returns_none_when_every_unit_is_unsorted():
    sorting = _sorting({0: [1, 2], 1: [5]})
    kept, accounting = compare.split_online_units(sorting, ["ch1#0", "ch2#0"])

    assert kept is None
    by_key = {c["key"]: c for c in accounting}
    assert by_key["sorted"]["n_units"] == 0                     # stated, not omitted
    assert (by_key["unsorted"]["n_units"], by_key["unsorted"]["n_spikes"]) == (2, 3)


# --------------------------------------------------------------------------- #
# Window crop
# --------------------------------------------------------------------------- #
def test_crop_online_trims_the_reference_to_the_sort_window():
    inside, outside = int(10 * FS), int(100 * FS)
    sorting = _sorting({0: [inside, outside], 1: [outside + 1]})

    cropped, info = compare.crop_online(sorting, window_s=30.0)

    assert info["cropped"] is True
    assert info["n_spikes_before"] == 3 and info["n_spikes_after"] == 1
    assert info["window_s"] == 30.0
    assert 100.0 < info["online_span_s"] < 101.0
    assert info["n_empty"] == 1                                  # unit 1 emptied by the crop
    assert len(cropped.get_unit_spike_train(0)) == 1


def test_crop_online_is_a_no_op_when_the_reference_already_fits():
    sorting = _sorting({0: [int(5 * FS)]})
    cropped, info = compare.crop_online(sorting, window_s=30.0)

    assert info["cropped"] is False
    assert info["n_spikes_before"] == info["n_spikes_after"] == 1
    assert len(cropped.get_unit_spike_train(0)) == 1


def test_crop_note_says_the_crop_out_loud():
    note = compare._crop_note({"cropped": True, "window_s": 30.0, "online_span_s": 132.0,
                               "n_spikes_before": 7219, "n_spikes_after": 1339, "n_empty": 1})
    assert "cropped to the first 30 s" in note
    assert "132 s" in note and "7219" in note and "1339" in note


# --------------------------------------------------------------------------- #
# The page: happy path + every degenerate state
# --------------------------------------------------------------------------- #
@pytest.fixture
def online_page(tmp_path, monkeypatch):
    """Build the --online page over injected sortings; returns the visible text."""
    def _build(offline=None, window_s=30.0, online=None, labels=None, exc=None):
        monkeypatch.setattr(compare, "OUTPUT_DIR", tmp_path)
        # _load takes a `curated` flag (W1 slice 2); the fake ignores it.
        monkeypatch.setattr(compare, "_load",
                            lambda s, curated=False: (offline, window_s))

        def _read_spikes(data_dir=None, **kw):
            if exc is not None:
                raise exc
            return online

        monkeypatch.setattr(compare.bio, "read_spikes", _read_spikes)
        monkeypatch.setattr(compare.bio, "online_unit_labels", lambda s: labels)
        out = compare.build_online_comparison("tridesclous2",
                                              out_path=tmp_path / "comparison.html")
        return out, _text(out)

    return _build


def test_online_page_renders_matrix_and_per_unit_best_match(online_page):
    # Two online units; ch1#1 lines up with offline unit 0, ch2#1 matches nothing.
    online = _sorting({0: [1000, 2000, 3000], 1: [500_000, 500_100]})
    offline = _sorting({0: [1001, 1999, 3000], 1: [900_000]})
    out, text = online_page(offline=offline, online=online, labels=["ch1#1", "ch2#1"])

    assert "Traceback" not in out.read_text(encoding="utf-8")
    assert 'class="plotly-graph-div"' in out.read_text(encoding="utf-8")
    assert "reference, not ground truth" in text
    assert "typically undercounts" in text
    assert "nothing on this page is accuracy or precision" in text
    assert "n = 2 online-sorted unit(s) against 2 tridesclous2 unit(s)" in text
    assert "ch1#1" in text and "ch2#1" in text
    assert "1 with a best match at agreement ≥ 0.5" in text


def test_online_page_flags_zero_agreement_with_a_next_step(online_page):
    online = _sorting({0: [1000, 2000]})
    offline = _sorting({0: [800_000, 900_000]})
    _out, text = online_page(offline=offline, online=online, labels=["ch1#1"])

    assert "Zero agreement" in text
    assert "window mismatch" in text and "channel mismatch" in text


def test_online_page_states_the_crop(online_page):
    online = _sorting({0: [1000, int(90 * FS)]})
    offline = _sorting({0: [1001]})
    _out, text = online_page(offline=offline, window_s=30.0, online=online, labels=["ch1#1"])

    assert "cropped to the first 30 s to match the sort" in text


def test_online_page_without_online_sorted_units_names_the_next_step(online_page):
    online = _sorting({0: [1, 2, 3], 1: [4, 5]})
    offline = _sorting({0: [1]})
    _out, text = online_page(offline=offline, online=online, labels=["ch1#0", "ch2#0"])

    assert "no online-sorted units" in text
    assert "5 spikes across 2" in text                       # the accounting is stated
    assert "unsorted threshold crossings (unit id 0)" in text
    assert "scripts/compare.py" in text                      # the named alternative


def test_online_page_without_a_saved_sort_names_the_next_step(online_page):
    _out, text = online_page(offline=None)

    assert "No saved sort for tridesclous2" in text
    assert "run_sorting.py --sorter tridesclous2" in text


def test_online_page_without_a_nev_names_the_next_step(online_page):
    _out, text = online_page(offline=_sorting({0: [1]}), exc=FileNotFoundError("no .nev"))

    assert "No .nev file found" in text
    assert "repo root" in text


def test_online_page_carries_the_loaders_own_reason(online_page):
    # The loader refuses for two different reasons and only IT knows which files it
    # saw. An ambiguous folder (two .nev sets) must reach the page naming the
    # candidates — not be flattened into the generic "put a .nev in the repo root".
    _out, text = online_page(offline=_sorting({0: [1]}), exc=FileNotFoundError(
        "More than one Blackrock .nev file set in '/data': manual, online. "
        "Pass data_dir=... pointing at a folder with a single recording"))

    assert "More than one Blackrock .nev file set" in text
    assert "manual, online" in text


def test_online_page_refuses_to_guess_when_labels_are_unreadable(online_page):
    _out, text = online_page(offline=_sorting({0: [1]}), online=_sorting({0: [1]}),
                             labels=None)

    assert "Could not read the .nev unit-class labels" in text
    assert "nothing is compared here" in text


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_without_flags_still_builds_the_two_sorter_page(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(compare, "build_comparison",
                        lambda **kw: calls.append("pair") or "out.html")
    monkeypatch.setattr(compare, "build_online_comparison",
                        lambda *a, **kw: pytest.fail("online mode ran without --online"))

    assert compare.main([]) == 0
    assert calls == ["pair"]
    assert capsys.readouterr().out.strip() == "out.html"


def test_cli_curated_without_a_curated_result_fails_hard(monkeypatch, capsys):
    """--curated must never quietly fall back to the raw sort (the repo's
    explicit-fails-hard asymmetry)."""
    monkeypatch.setattr(compare, "build_online_comparison",
                        lambda *a, **kw: pytest.fail("built a page anyway"))
    with pytest.raises(SystemExit):
        compare.main(["--online", "nosuchsorter", "--curated"])
    assert "no curated result" in capsys.readouterr().err


def test_cli_online_flag_selects_the_nev_mode(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(compare, "build_comparison",
                        lambda *a, **k: pytest.fail("pair mode ran with --online"))
    monkeypatch.setattr(compare, "build_online_comparison",
                        lambda sorter, **kw: seen.append((sorter, kw.get("nev_path")))
                        or "online.html")

    assert compare.main(["--online", "spykingcircus2"]) == 0
    assert seen == [("spykingcircus2", None)]
    # --nev threads the explicit reference through; bare --nev is refused.
    assert compare.main(["--online", "spykingcircus2", "--nev", "x.nev"]) == 0
    assert seen[-1] == ("spykingcircus2", "x.nev")
    with pytest.raises(SystemExit):
        compare.main(["--nev", "x.nev"])
    out = capsys.readouterr().out.strip().splitlines()
    assert out and all(ln == "online.html" for ln in out)


# --------------------------------------------------------------------------- #
# Integration — real recording + real saved sort, skipped when absent
# --------------------------------------------------------------------------- #
def test_online_comparison_against_this_repo(tmp_path):
    import blackrock_io as bio

    try:
        bio.find_blackrock_base()
    except FileNotFoundError:
        pytest.skip("no Blackrock recording on this machine")
    saved = compare.saved_sorters()
    if not saved:
        pytest.skip("no saved sort (outputs/<sorter>/analyzer) — run a sort first")

    out = compare.build_online_comparison(saved[0], out_path=tmp_path / "comparison.html")
    raw = out.read_text(encoding="utf-8")
    text = _text(out)

    assert "Traceback" not in raw
    assert "The online (.nev) reference" in text
    assert "unsorted threshold crossings (unit id 0)" in text
    # Either a matrix or a named next step — never an empty page.
    assert ("online-sorted unit(s)" in text) or ("nothing to compare against" in text)
