"""Pure, dependency-free progress math for the in-UI Docker-image download.

No Textual / Docker imports - like ``scripts/sort_progress.py`` this holds the
arithmetic and formatting so the TUI stays a thin renderer and the logic is
trivially unit-testable. Timestamps are passed IN (monotonic seconds) so the
clock is deterministic in tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_KB = 1024
_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024

# Speed is a moving average over the last few seconds of transfer, NOT a per-event
# instantaneous rate. Docker reveals bytes in bursts (a whole layer "completes" in
# one event), so an instantaneous rate spikes wildly; averaging over a window gives
# a steady, honest "downloaded N bytes over the last W seconds" figure.
_SPEED_WINDOW_S = 5.0
# Don't quote a speed until at least this much wall-clock has accrued in the window
# - early on, one or two sub-second samples divide by a near-zero span and produce a
# meaningless huge number.
_SPEED_MIN_SPAN_S = 1.0


class DownloadStats:
    """Tracks (done, total) byte samples over an injected monotonic clock and
    derives percent / a windowed average speed / ETA / elapsed. A phase change
    clears the speed window so the download->extract byte-total reset never yields a
    spurious rate."""

    def __init__(self) -> None:
        self._done = 0
        self._total = 0
        self._start: float | None = None      # first-ever sample time -> elapsed
        self._now: float = 0.0
        # Recent (time, done_bytes) samples within the speed window - the average
        # rate is the slope across this window, which smooths Docker's bursty deltas.
        self._samples: list[tuple[float, int]] = []

    def reset_window(self, now: float) -> None:
        """Drop accumulated samples (NOT the start clock / elapsed) so the rate
        re-warms cleanly. Used on a phase change AND when the progress unit flips
        between bytes and layer-counts - a slope across mixed units is meaningless."""
        self._samples.clear()
        self._now = now

    def set_phase(self, phase: str, now: float) -> None:
        self.reset_window(now)

    def update(self, done: int, total: int, now: float) -> None:
        self._done = done
        self._total = total
        self._now = now
        if self._start is None:
            self._start = now
        self._samples.append((now, done))
        # Drop samples older than the window, but always keep at least one before the
        # window edge so the slope spans the full window once it's warm.
        cutoff = now - _SPEED_WINDOW_S
        while len(self._samples) > 2 and self._samples[1][0] < cutoff:
            self._samples.pop(0)

    @property
    def pct(self) -> int:
        return int(self._done / self._total * 100) if self._total else 0

    @property
    def speed(self) -> float | None:
        # Average bytes/s across the sample window. None until the window spans at
        # least _SPEED_MIN_SPAN_S (so the first reading isn't a divide-by-near-zero).
        if len(self._samples) < 2:
            return None
        t0, d0 = self._samples[0]
        t1, d1 = self._samples[-1]
        span = t1 - t0
        if span < _SPEED_MIN_SPAN_S or d1 < d0:
            return None
        return (d1 - d0) / span

    @property
    def eta(self) -> float | None:
        speed = self.speed
        if not self._total or not speed or speed <= 0:
            return None
        remaining = self._total - self._done
        return remaining / speed if remaining > 0 else 0.0

    @property
    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        return self._now - self._start


@dataclass
class DownloadSession:
    """The single live download the App owns; both views read from it."""
    name: str
    image: str
    phase: str = "downloading"        # downloading | verifying | extracting | done
    stats: DownloadStats = field(default_factory=DownloadStats)
    result: tuple[bool, str] | None = None    # (ok, message) once finished
    cancelled: bool = False


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    if n >= _GB:
        return f"{n / _GB:.1f} GB"
    if n >= _MB:
        return f"{n / _MB:.0f} MB"
    if n >= _KB:
        return f"{n / _KB:.0f} KB"
    return f"{n} B"


def fmt_speed(bps: float | None) -> str:
    if bps is None:
        return "-"
    if bps >= _MB:
        return f"{bps / _MB:.1f} MB/s"
    if bps >= _KB:
        return f"{bps / _KB:.0f} KB/s"
    return f"{bps:.0f} B/s"


def fmt_clock(secs: float | None) -> str:
    if secs is None:
        return "-"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
