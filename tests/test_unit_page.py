"""unit_page: the units page draws every unit of a run from its saved analyzer,
in µV (never scaled twice), flagged units first, and degrades - never crashes -
when an extension is missing. Runs on a small synthetic sort."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import unit_page  # noqa: E402

GAIN = 0.25


@pytest.fixture(scope="module")
def analyzers(tmp_path_factory):
    si = pytest.importorskip("spikeinterface.full")
    root = tmp_path_factory.mktemp("units")
    rec, sorting = si.generate_ground_truth_recording(
        durations=[8.0], num_channels=6, num_units=3, seed=1)
    rec.set_channel_gains(GAIN)
    rec.set_channel_offsets(0.0)
    rec = rec.save(folder=root / "recording")
    full = si.create_sorting_analyzer(sorting, rec, folder=root / "full",
                                      format="binary_folder", sparse=False)
    full.compute(["random_spikes", "waveforms", "templates", "noise_levels",
                  "spike_amplitudes", "correlograms", "template_similarity",
                  "principal_components"])
    bare = si.create_sorting_analyzer(sorting, rec, folder=root / "bare",
                                      format="binary_folder", sparse=False)
    bare.compute(["random_spikes", "templates"])
    return {"root": root, "full": full}


def _build(monkeypatch, root, name):
    run = root / f"run_{name}"
    run.mkdir(exist_ok=True)
    paths = {"analyzer": root / name, "out": run, "run_info": run / "run_info.json",
             "id": "20260101-000000-aaaaaa"}
    monkeypatch.setattr(unit_page.runs, "sort_paths", lambda sorter, run=None: paths)
    out = unit_page.build("synthetic")
    text = out.read_text(encoding="utf-8")
    figs = json.loads(re.search(r'<script id="figs" type="application/json">(.*?)</script>',
                                text, re.S).group(1))
    return out, text, figs


def test_every_unit_gets_a_card_with_all_six_plots(monkeypatch, analyzers):
    out, text, figs = _build(monkeypatch, analyzers["root"], "full")
    ids = [str(u) for u in analyzers["full"].unit_ids]
    assert out.name == unit_page.PAGE_NAME
    for u in ids:
        assert f'id="unit-{u}"' in text and f'href="#unit-{u}"' in text
        assert len(figs[u]) == 6           # spikes, ACG, ISI, amplitude, features, CCG
    assert "Plotly.newPlot" in text and "IntersectionObserver" in text


def test_waveforms_are_the_analyzer_microvolts_never_scaled_twice(monkeypatch, analyzers):
    _out, _text, figs = _build(monkeypatch, analyzers["root"], "full")
    a = analyzers["full"]
    u = a.unit_ids[0]
    tmpl = a.get_extension("templates").get_unit_template(u, operator="average")
    peak = int(np.argmax(np.ptp(tmpl, axis=0)))
    traces = [t for t in figs[str(u)][0]["data"] if t.get("name") == "template"]
    drawn = max(float(np.ptp(t["y"])) for t in traces)
    assert drawn == pytest.approx(float(np.ptp(tmpl[:, peak])), rel=0.02)


def test_a_bare_analyzer_degrades_to_notes(monkeypatch, analyzers):
    _out, text, figs = _build(monkeypatch, analyzers["root"], "bare")
    assert "no correlograms saved" in text and "no spike amplitudes saved" in text
    assert all(1 <= len(f) <= 2 for f in figs.values())    # waveforms (+ ISI) only


def test_open_at_keeps_the_unit_through_a_redirect(tmp_path):
    page = tmp_path / unit_page.PAGE_NAME
    page.write_text("x")
    redirect = unit_page.open_at(page, 16)
    assert 'url=units.html#unit-16' in redirect.read_text()
