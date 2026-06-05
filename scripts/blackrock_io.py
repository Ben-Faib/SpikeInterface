"""Reusable loaders for Blackrock / Ripple (.nev / .nsX) recordings.

Thin wrappers around SpikeInterface + neo so the rest of the project (scripts
and notebooks) can load this dataset in one line:

    from blackrock_io import (
        read_lfp, read_broadband, read_spikes, read_events, list_streams,
    )

What the files in this repo can contain
---------------------------------------
* ``*.ns2`` — analog data sampled at **1 kHz** (channels labelled ``lfp N``).
  This is **LFP**, read as a SpikeInterface *Recording* (:func:`read_lfp`).
* ``*.ns5`` — raw **broadband** sampled at **~30 kHz**. This is what you can
  spike-sort, read as a SpikeInterface *Recording* (:func:`read_broadband`).
* ``*.nev`` — spike events / waveform snippets + digital event markers, with
  timestamps at the system clock rate (**30 kHz** for this file). The
  already-detected spikes are read as a SpikeInterface *Sorting*.

Only the highest-rate analog stream (``.ns5``/``.ns6``) can be spike-sorted; the
1 kHz ``.ns2`` LFP cannot. If only an ``.ns2`` is present, :func:`read_broadband`
raises a clear error.

Everything uses :mod:`pathlib`, so it runs unchanged on macOS, Windows and Linux.
"""

from __future__ import annotations

from pathlib import Path

# Blackrock/Ripple stores .nev spike timestamps at the system clock resolution.
# The .nev header for this dataset (NEURALEV spec 2.2, Trellis) reports a
# timestamp resolution of 30000 Hz, so that is the rate used to convert spike
# sample indices to seconds.
NEV_TIMESTAMP_RATE = 30_000.0

# Default place to look for the data: the repo root (this file lives in scripts/).
REPO_ROOT = Path(__file__).resolve().parent.parent


def use_utf8_stdout() -> None:
    """Force UTF-8 stdout/stderr so non-ASCII status output never crashes on Windows.

    The scripts print glyphs like ``✓``/``→``/``…``. On an interactive console
    this is a no-op (Python already uses UTF-8 there), but when output is
    redirected or piped on Windows, stdout falls back to the locale code page
    (e.g. cp1252/cp437) and printing those glyphs raises ``UnicodeEncodeError``.
    Re-encoding to UTF-8 writes valid bytes instead. Idempotent and harmless on
    macOS/Linux. Call once at program start, before any rich/tqdm console is made.
    """
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


# Library/native chatter that is never useful signal — only clutter that breaks
# the clean terminal formatting. Muted everywhere it can leak: the verbose
# progress output, the in-process report/compare paths, and spawned sorter
# workers. Each entry is a regex matched against the START of a warning message
# (warnings uses re.match), so it silences the noise regardless of the Warning
# subclass that raised it:
#   - probe warning: sorters rebuild an internal recording that drops our probe
#   - resource_tracker: known multiprocessing shared-memory cleanup chatter
#   - non-persistent recording: expected — we register an in-memory recording
_MUTED_WARNINGS = (
    "There is no Probe attached",
    "resource_tracker",
    "The registered recording will not be persistent",
)


def mute_native_chatter() -> None:
    """Silence OpenMP/Numba/probe/resource-tracker noise.

    Call *before* importing spikeinterface so ``KMP_WARNINGS`` lands before
    OpenMP initialises and ``PYTHONWARNINGS=ignore`` propagates to any spawned
    sorter worker subprocess (whose warnings the in-process filters never see).
    Idempotent; safe to call from every entry point.
    """
    import os
    import warnings

    os.environ.setdefault("KMP_WARNINGS", "0")
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    for msg in _MUTED_WARNINGS:
        warnings.filterwarnings("ignore", message=msg)
    try:  # numba may be absent; its cast note is muted by category because numba
        from numba.core.errors import NumbaWarning  # prepends ANSI codes -> a message regex misses it

        warnings.filterwarnings("ignore", category=NumbaWarning)
    except Exception:
        pass


def find_blackrock_base(data_dir: "Path | str | None" = None) -> Path:
    """Return the extension-less base path of a Blackrock file set.

    neo treats the filename *without* extension as a set of files that share a
    base name (``foo.nev`` + ``foo.ns2`` + ...). This scans ``data_dir`` for any
    ``.nev`` or ``.ns1``..``.ns6`` file and returns its stem path.
    """
    data_dir = Path(data_dir) if data_dir is not None else REPO_ROOT
    candidates = sorted(data_dir.glob("*.nev")) + sorted(data_dir.glob("*.ns[1-6]"))
    if not candidates:
        raise FileNotFoundError(
            f"No Blackrock .nev/.nsX files found in '{data_dir}'. "
            "Pass data_dir=... pointing at the folder that holds your recording."
        )
    return candidates[0].with_suffix("")


def list_streams(data_dir: "Path | str | None" = None):
    """List the analog (nsX) streams available for the file set.

    Returns a list of ``(stream_name, stream_id)`` tuples.
    """
    from spikeinterface.extractors import get_neo_streams

    base = find_blackrock_base(data_dir)
    names, ids = get_neo_streams("blackrock", str(base))
    return list(zip(names, ids))


def read_lfp(
    data_dir: "Path | str | None" = None,
    stream_id: "str | None" = None,
    stream_name: "str | None" = None,
):
    """Read an analog/LFP recording (e.g. ``.ns2`` @ 1 kHz) as a SI Recording.

    If neither ``stream_id`` nor ``stream_name`` is given and several streams
    exist, the first one is used.
    """
    import spikeinterface.extractors as se

    base = find_blackrock_base(data_dir)
    if stream_id is None and stream_name is None:
        # Resolve to a single stream id; leave stream_name None so we never
        # pass both selectors to read_blackrock (which rejects receiving both).
        _name, stream_id = list_streams(data_dir)[0]
    recording = se.read_blackrock(
        str(base),
        stream_id=stream_id,
        stream_name=stream_name,
        all_annotations=True,
    )
    return recording


def find_broadband_stream(data_dir: "Path | str | None" = None):
    """Return ``(stream_name, stream_id)`` of the highest-sample-rate analog stream.

    Blackrock numbers analog streams by bandwidth (``.ns1`` 500 Hz … ``.ns5``
    30 kHz), so the spike-sortable *broadband* stream is simply the one with the
    greatest sampling frequency. Each stream's header is read (cheap, memmapped)
    to compare rates rather than trusting the file extension.
    """
    import spikeinterface.extractors as se

    base = find_blackrock_base(data_dir)
    best = None  # (fs, name, id)
    for name, sid in list_streams(data_dir):
        fs = se.read_blackrock(str(base), stream_id=sid).get_sampling_frequency()
        if best is None or fs > best[0]:
            best = (fs, name, sid)
    return best[1], best[2]


def attach_dummy_probe(recording, pitch_um: float = 250.0):
    """Attach a placeholder linear probe so a probe-less recording can be sorted.

    The Blackrock files carry **no electrode geometry**, and the real physical
    layout of this array is unknown. This lays the channels out in a single
    column ``pitch_um`` apart — far enough that sorters treat every channel as
    **independent** (no shared spatial neighbourhood / no cross-channel merging).
    Per-channel results are valid; cross-channel *spatial* information is not
    physical until a real map is supplied.

    To swap in the real geometry later, build a ``probeinterface.Probe`` with the
    true contact positions and call ``recording.set_probe(real_probe)`` instead.
    Returns a new recording with the probe attached (does not mutate in place).
    """
    import numpy as np
    from probeinterface import generate_linear_probe

    n = recording.get_num_channels()
    probe = generate_linear_probe(num_elec=n, ypitch=pitch_um)
    probe.set_device_channel_indices(np.arange(n))
    return recording.set_probe(probe)


def read_broadband(
    data_dir: "Path | str | None" = None,
    stream_id: "str | None" = None,
    attach_probe: bool = True,
    probe_pitch_um: float = 250.0,
    min_sampling_hz: float = 10_000.0,
):
    """Read the raw broadband recording (e.g. ``.ns5`` @ ~30 kHz) for spike sorting.

    Selects the highest-sample-rate analog stream unless ``stream_id`` is given,
    and (by default) attaches a placeholder independent-channel probe via
    :func:`attach_dummy_probe` so the result is immediately sortable. Raises if
    the chosen stream is slow enough to be LFP rather than broadband — sorting
    1 kHz LFP is not meaningful.
    """
    import spikeinterface.extractors as se

    base = find_blackrock_base(data_dir)
    if stream_id is None:
        _name, stream_id = find_broadband_stream(data_dir)
    recording = se.read_blackrock(
        str(base), stream_id=stream_id, all_annotations=True
    )
    fs = recording.get_sampling_frequency()
    if fs < min_sampling_hz:
        raise ValueError(
            f"Selected stream is {fs:g} Hz — that is LFP, not raw broadband. "
            "Spike sorting needs the ~30 kHz broadband stream (a .ns5/.ns6 file). "
            "Add it to the data folder, or pass stream_id=... for the right stream."
        )
    if attach_probe:
        recording = attach_dummy_probe(recording, pitch_um=probe_pitch_um)
    return recording


def read_spikes(
    data_dir: "Path | str | None" = None,
    sampling_frequency: float = NEV_TIMESTAMP_RATE,
):
    """Read spike events from the ``.nev`` file as a SpikeInterface Sorting.

    Blackrock unit-id convention: ``0`` = unsorted threshold crossings,
    ``1..n`` = online-sorted units, ``255`` = noise / invalidated.
    """
    import spikeinterface.extractors as se

    base = find_blackrock_base(data_dir)
    sorting = se.read_blackrock_sorting(
        str(base) + ".nev",
        sampling_frequency=sampling_frequency,
    )
    return sorting


def read_events(data_dir: "Path | str | None" = None):
    """Best-effort read of digital/serial event markers stored in the ``.nev``.

    Returns a list of dicts ``{"name", "times", "labels"}`` (one per event
    channel), where ``times`` is in seconds. Returns an empty list if the file
    has no event channels.
    """
    from neo.rawio import BlackrockRawIO

    base = find_blackrock_base(data_dir)
    reader = BlackrockRawIO(filename=str(base))
    reader.parse_header()

    events = []
    event_channels = reader.header["event_channels"]
    for ev_idx in range(len(event_channels)):
        channel = event_channels[ev_idx]
        timestamps, _durations, labels = reader.get_event_timestamps(
            block_index=0, seg_index=0, event_channel_index=ev_idx
        )
        times = reader.rescale_event_timestamp(
            timestamps, dtype="float64", event_channel_index=ev_idx
        )
        events.append({"name": channel["name"], "times": times, "labels": labels})
    return events
