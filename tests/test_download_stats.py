"""Unit tests for the pure download-progress module (scripts/download_stats.py).

No Textual / Docker imports — timestamps are injected so the clock is deterministic.
"""
from __future__ import annotations

import download_stats as ds


def test_pct_basic_and_zero_total():
    s = ds.DownloadStats()
    s.update(0, 0, now=0.0)
    assert s.pct == 0           # unknown total -> 0, never a divide error
    s.update(50, 100, now=1.0)
    assert s.pct == 50
    s.update(100, 100, now=2.0)
    assert s.pct == 100


def test_speed_is_a_windowed_average():
    s = ds.DownloadStats()
    s.update(0, 1000, now=0.0)
    assert s.speed is None       # one sample -> no rate yet
    s.update(100, 1000, now=1.0)  # 100 bytes over 1 s window
    assert s.speed is not None and s.speed > 0
    # A steady 100 B/s stream reads ~100 B/s (the window slope).
    s.update(200, 1000, now=2.0)
    s.update(300, 1000, now=3.0)
    assert 90 <= s.speed <= 110


def test_speed_does_not_spike_on_a_completed_layer_burst():
    """A whole layer 'completing' lands as one big byte jump in a single event;
    the windowed average must absorb it, not report a wild instantaneous rate."""
    s = ds.DownloadStats()
    # Steady ~100 B/s for several seconds.
    for t in range(0, 5):
        s.update(t * 100, 100_000, now=float(t))
    steady = s.speed
    assert 90 <= steady <= 110
    # A layer completes: +50 KB lands in one 0.1 s event. Instantaneous = 500 KB/s,
    # but the 5 s window must keep the reported speed sane (well under that spike).
    s.update(400 + 50_000, 100_000, now=5.1)
    assert s.speed is not None and s.speed < 50_000   # nowhere near the 500 KB/s spike


def test_speed_none_until_min_span():
    """Two samples a few milliseconds apart must not report a divide-by-near-zero
    speed — wait until the window spans a meaningful interval."""
    s = ds.DownloadStats()
    s.update(0, 1_000_000, now=0.0)
    s.update(10_000, 1_000_000, now=0.05)   # 10 KB in 50 ms -> 200 KB/s instantaneous
    assert s.speed is None                   # span < min -> withheld, not a garbage value


def test_layer_count_progress_yields_estimated_eta():
    """Extraction reports no bytes, only completed-layer counts. The same window
    machinery must turn the layer-completion rate into an ETA so the extract phase
    isn't a mystery — e.g. 9 layers, 3 done over 3 s -> ~6 s left."""
    s = ds.DownloadStats()
    s.update(0, 9, now=0.0)
    s.update(1, 9, now=1.0)
    s.update(2, 9, now=2.0)
    s.update(3, 9, now=3.0)        # 1 layer/s, 6 layers left
    assert s.pct == 33
    assert s.eta is not None and 4 <= s.eta <= 8


def test_reset_window_clears_rate_on_unit_flip():
    """Flipping from bytes to layer-counts (or vice versa) must reset the window so
    a slope is never computed across mixed units."""
    s = ds.DownloadStats()
    s.update(0, 1_000_000, now=0.0)
    s.update(500_000, 1_000_000, now=2.0)   # byte phase, fast rate
    assert s.speed is not None and s.speed > 100_000
    s.reset_window(now=2.0)
    s.update(1, 9, now=3.0)                  # now layer-counts; only one post-reset sample
    assert s.speed is None                   # window cleared -> no cross-unit slope


def test_eta_from_remaining_over_speed():
    s = ds.DownloadStats()
    s.update(0, 1000, now=0.0)
    s.update(100, 1000, now=1.0)   # ~100 B/s, 900 left -> ~9 s
    assert s.eta is not None and 6 <= s.eta <= 12
    s2 = ds.DownloadStats()
    s2.update(0, 0, now=0.0)        # unknown total -> no ETA
    assert s2.eta is None


def test_elapsed_uses_injected_clock():
    s = ds.DownloadStats()
    s.update(0, 1000, now=10.0)    # first sample stamps the start
    s.update(500, 1000, now=14.5)
    assert abs(s.elapsed - 4.5) < 1e-6


def test_phase_change_resets_speed_window_no_negative():
    s = ds.DownloadStats()
    s.update(900, 1000, now=0.0)   # end of download phase (high byte count)
    s.update(1000, 1000, now=1.0)
    s.set_phase("extracting", now=2.0)
    s.update(10, 1000, now=3.0)    # extract restarts byte counting from ~0
    # Speed must be computed from the post-reset samples, never negative.
    assert s.speed is None or s.speed >= 0


def test_formatters():
    assert ds.fmt_bytes(423 * 1024 * 1024).endswith("MB")
    assert ds.fmt_bytes(None) == "—"
    assert ds.fmt_speed(2.3 * 1024 * 1024).endswith("MB/s")
    assert ds.fmt_speed(None) == "—"
    assert ds.fmt_clock(38) == "0:38"
    assert ds.fmt_clock(72) == "1:12"
    assert ds.fmt_clock(3661) == "1:01:01"
    assert ds.fmt_clock(None) == "—"
