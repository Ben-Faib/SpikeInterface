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


def test_speed_needs_two_samples_then_emas():
    s = ds.DownloadStats()
    s.update(0, 1000, now=0.0)
    assert s.speed is None       # one sample -> no rate yet
    s.update(100, 1000, now=1.0)  # 100 bytes in 1 s
    assert s.speed is not None and s.speed > 0
    # A steady 100 B/s stream keeps the EMA near 100 (not wildly off).
    s.update(200, 1000, now=2.0)
    s.update(300, 1000, now=3.0)
    assert 80 <= s.speed <= 120


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
