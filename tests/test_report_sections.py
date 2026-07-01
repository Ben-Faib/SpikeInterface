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
