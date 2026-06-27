"""Pure, dependency-free progress math for the in-UI Docker-image download.

No Textual / Docker imports — like ``scripts/sort_progress.py`` this holds the
arithmetic and formatting so the TUI stays a thin renderer and the logic is
trivially unit-testable. Timestamps are passed IN (monotonic seconds) so the
clock is deterministic in tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# EMA weight for new samples — small enough to smooth the bursty per-event byte
# deltas the Docker SDK emits, large enough to track real speed changes.
_EMA_ALPHA = 0.3
_KB = 1024
_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024


class DownloadStats:
    """Tracks (done, total) byte samples over an injected monotonic clock and
    derives percent / smoothed speed / ETA / elapsed. A phase change resets the
    speed window so the download->extract byte-total reset never yields a
    negative rate."""

    def __init__(self) -> None:
        self._done = 0
        self._total = 0
        self._start: float | None = None      # first-ever sample time -> elapsed
        self._last_t: float | None = None      # last sample time (for deltas)
        self._last_done: int | None = None     # last done (for deltas)
        self._now: float = 0.0
        self._speed: float | None = None       # EMA bytes/s, None until 2 samples

    def set_phase(self, phase: str, now: float) -> None:
        # Reset the per-sample delta window (NOT the start clock / elapsed): the new
        # phase counts bytes from ~0, so a delta against the old phase would be wildly
        # negative. Speed re-warms from the next two samples.
        self._last_t = None
        self._last_done = None
        self._now = now

    def update(self, done: int, total: int, now: float) -> None:
        self._done = done
        self._total = total
        self._now = now
        if self._start is None:
            self._start = now
        if self._last_t is not None and self._last_done is not None:
            dt = now - self._last_t
            dbytes = done - self._last_done
            if dt > 0 and dbytes >= 0:
                inst = dbytes / dt
                self._speed = (inst if self._speed is None
                               else _EMA_ALPHA * inst + (1 - _EMA_ALPHA) * self._speed)
        self._last_t = now
        self._last_done = done

    @property
    def pct(self) -> int:
        return int(self._done / self._total * 100) if self._total else 0

    @property
    def speed(self) -> float | None:
        return self._speed

    @property
    def eta(self) -> float | None:
        if not self._total or not self._speed or self._speed <= 0:
            return None
        remaining = self._total - self._done
        return remaining / self._speed if remaining > 0 else 0.0

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
        return "—"
    if n >= _GB:
        return f"{n / _GB:.1f} GB"
    if n >= _MB:
        return f"{n / _MB:.0f} MB"
    if n >= _KB:
        return f"{n / _KB:.0f} KB"
    return f"{n} B"


def fmt_speed(bps: float | None) -> str:
    if bps is None:
        return "—"
    if bps >= _MB:
        return f"{bps / _MB:.1f} MB/s"
    if bps >= _KB:
        return f"{bps / _KB:.0f} KB/s"
    return f"{bps:.0f} B/s"


def fmt_clock(secs: float | None) -> str:
    if secs is None:
        return "—"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
