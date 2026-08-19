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

import re
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

    **A second .nev beside the recording is its own set, not part of it.** This
    repo's folder carries a manually re-exported ``…_manuallySorted.nev``
    alongside the recording; because neo keys on the stem, that export is a
    separate (analog-less) file set. Discovery therefore prefers the stem that
    actually has analog ``.nsX`` data — a stem with only a ``.nev`` is a derived
    export, never the recording — and falls back to a lone ``.nev`` stem when the
    folder holds no analog data at all (spikes/events still load). Two stems that
    both carry analog data are genuinely ambiguous: that raises, naming both,
    rather than picking whichever sorts first.
    """
    data_dir = Path(data_dir) if data_dir is not None else REPO_ROOT
    nev = sorted(data_dir.glob("*.nev"))
    nsx = sorted(data_dir.glob("*.ns[1-6]"))
    if not nev and not nsx:
        raise FileNotFoundError(
            f"No Blackrock .nev/.nsX files found in '{data_dir}'. "
            "Pass data_dir=... pointing at the folder that holds your recording."
        )

    def _one(bases: "list[Path]", what: str) -> Path:
        if len(bases) > 1:
            raise FileNotFoundError(
                f"More than one Blackrock {what} in '{data_dir}': "
                + ", ".join(b.name for b in bases)
                + ". Pass data_dir=... pointing at a folder with a single "
                "recording, or move the others aside."
            )
        return bases[0]

    with_analog = sorted({p.with_suffix("") for p in nsx})
    if with_analog:
        return _one(with_analog, "recording set (.nsX)")
    return _one(sorted({p.with_suffix("") for p in nev}), ".nev file set")


def find_reference_nevs(data_dir: "Path | str | None" = None) -> "list[Path]":
    """The ``.nev`` files beside the recording that are NOT the recording's own.

    The flip side of :func:`find_blackrock_base`: a stem carrying only a ``.nev``
    and no analog ``.nsX`` is a derived export — this repo's folder holds a
    manually re-exported ``…_manuallySorted.nev`` — and those are the files a
    surface can use as a sorted *reference*. Sorted by name; ``[]`` when the
    folder holds none, so a caller drops the comparison instead of guessing.
    Never raises: a folder with no recording at all simply has no references.
    """
    data_dir = Path(data_dir) if data_dir is not None else REPO_ROOT
    nsx_stems = {p.with_suffix("") for p in data_dir.glob("*.ns[1-6]")}
    return sorted(p for p in data_dir.glob("*.nev") if p.with_suffix("") not in nsx_stems)


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

    To swap in real geometry, build a probe with ``probes.build(profile, n)`` (or a
    raw ``probeinterface.Probe``) and call ``recording.set_probe(...)`` instead.
    Returns a new recording with the probe attached (does not mutate in place).
    """
    import numpy as np
    from probeinterface import generate_linear_probe

    n = recording.get_num_channels()
    probe = generate_linear_probe(num_elec=n, ypitch=pitch_um)
    probe.set_device_channel_indices(np.arange(n))
    return recording.set_probe(probe)


# Number of recording sites on the real array used for this dataset.
A1X16_N_CONTACTS = 16
A1X16_PITCH_UM = 100.0


def attach_a1x16_probe(recording, pitch_um: float = A1X16_PITCH_UM):
    """Attach the **real** NeuroNexus A1x16-3mm-100-703 geometry.

    This recording was made with a NeuroNexus **A1x16-3mm-100-703**: a single
    shank with **16 sites in one column, 100 µm apart** (span 1500 µm). Unlike
    :func:`attach_dummy_probe` (a placeholder that spaces channels 250 µm apart so
    none are neighbours), this is the true layout, so cross-channel spatial
    information — neighbours, depth, drift, multi-channel templates — is physical,
    and the ``spikeinterface-gui`` inspector shows each unit across all 16 sites.

    Wiring is **sequential / identity**: recording channel *i* → site *i*
    (tip→top), matching ``attach_dummy_probe``. The geometry and pitch are exact
    for this part; the physical depth *order* depends on the probe→Ripple adapter,
    which is not in the data — flip the mapping here if a real adapter map says so.

    Requires exactly :data:`A1X16_N_CONTACTS` channels (drop the analog aux inputs
    with :func:`neural_channel_ids` first). Returns a new recording (no mutation).
    """
    import numpy as np
    from probeinterface import generate_linear_probe

    n = recording.get_num_channels()
    if n != A1X16_N_CONTACTS:
        raise ValueError(
            f"A1x16 probe has {A1X16_N_CONTACTS} sites but the recording has {n} "
            "channels — drop the non-neural analog aux channels first "
            "(neural_channel_ids), or use attach_dummy_probe for a different array."
        )
    probe = generate_linear_probe(num_elec=A1X16_N_CONTACTS, ypitch=pitch_um)
    probe.set_device_channel_indices(np.arange(A1X16_N_CONTACTS))
    probe.annotate(name="A1x16-3mm-100-703", manufacturer="neuronexus")
    return recording.set_probe(probe)


def neural_channel_ids(recording):
    """Return only the genuine electrode channel ids from a broadband recording.

    Blackrock/Ripple stores non-neural **analog auxiliary** inputs (sync pulses,
    foot pedals, etc.) in the same broadband stream as the electrodes, labelled
    ``analog N`` (channel ids 10241+ on this rig). They must **not** be spike
    sorted: feeding them through the common median reference pollutes the median
    that every neural channel is referenced against, and the sorter can emit
    spurious "units" on them. This keeps the channels whose name does *not* start
    with ``analog`` (case-insensitive). If the recording carries no channel names
    it conservatively returns every channel (nothing is dropped blindly).
    """
    names = recording.get_property("channel_name")
    ids = list(recording.get_channel_ids())
    if names is None:
        return ids
    keep = [cid for cid, nm in zip(ids, names)
            if not str(nm).strip().lower().startswith("analog")]
    return keep or ids  # never strip every channel


def select_channels(recording, channel_ids):
    """Restrict a recording to ``channel_ids`` (SpikeInterface-version-agnostic)."""
    if hasattr(recording, "select_channels"):
        return recording.select_channels(channel_ids)
    return recording.channel_slice(channel_ids)  # older SpikeInterface


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
    nev_path: "Path | str | None" = None,
):
    """Read spike events from a ``.nev`` file as a SpikeInterface Sorting.

    By default reads the recording set's own ``.nev``; ``nev_path`` reads an
    EXPLICIT file instead — e.g. a re-exported, manually/online-sorted `.nev`
    for the same recording (``compare.py --nev``). A missing explicit path is a
    hard error (the explicit-fails-hard convention).

    Blackrock unit-id convention: ``0`` = unsorted threshold crossings,
    ``1..n`` = online-sorted units, ``255`` = noise / invalidated. SI renumbers
    the units positionally and drops that id, so the class is recovered from the
    neo names — :func:`online_unit_labels` + :func:`unit_class`, the one home for
    it (compare.py and explore_data.py both read it from here).
    """
    import spikeinterface.extractors as se

    if nev_path is not None:
        target = Path(nev_path).expanduser()
        if not target.exists():
            raise FileNotFoundError(f"no such .nev: {target}")
    else:
        target = Path(str(find_blackrock_base(data_dir)) + ".nev")
    sorting = se.read_blackrock_sorting(
        str(target),
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


# --------------------------------------------------------------------------- #
# .nev unit classes — this dataset's semantics, so they live with the loader
# --------------------------------------------------------------------------- #
# The Blackrock unit id encodes the CLASS of a .nev unit (see read_spikes). Every
# surface that reads the .nev — compare.py's --online reference, explore_data's
# detection labels — asks here rather than re-deriving the convention.
UNSORTED_UNIT_ID = 0
NOISE_UNIT_ID = 255
UNIT_CLASS_LABELS = {
    "sorted": "online-sorted (unit ids 1–254)",
    "unsorted": "unsorted threshold crossings (unit id 0)",
    "noise": "noise / invalidated (unit id 255)",
    "other": "unrecognised label",
}
# neo names a .nev spike channel "ch<channel>#<blackrock unit id>".
_UNIT_LABEL_RE = re.compile(r"^ch(\d+)#(\d+)$")


def online_unit_labels(sorting) -> "list[str] | None":
    """The ``ch<channel>#<unit>`` names of a .nev Sorting's units, in unit order.

    SpikeInterface numbers .nev units positionally (0..n-1), which throws away the
    Blackrock unit id — and with it the class (unsorted / sorted / noise) that
    decides what may be compared. The names neo parsed are still on the extractor
    and in the same order as the unit ids, so the class is recoverable there.
    Returns None when the sorting did not come from neo: the caller says so
    rather than guessing a class it cannot know.
    """
    header = getattr(getattr(sorting, "neo_reader", None), "header", None)
    if header is None:
        return None
    return [str(n) for n in header["spike_channels"]["name"]]


def unit_class(label: str) -> str:
    """One of "sorted" / "unsorted" / "noise" / "other" for a ch<n>#<unit> label."""
    m = _UNIT_LABEL_RE.match(label)
    if m is None:
        return "other"
    unit = int(m.group(2))
    if unit == UNSORTED_UNIT_ID:
        return "unsorted"
    if unit == NOISE_UNIT_ID:
        return "noise"
    return "sorted"


def parse_unit_label(label: str) -> "tuple[int, int] | None":
    """(electrode number, blackrock unit id) from a ``ch<n>#<unit>`` label, else None.

    The split matters because a .nev unit id is a PER-ELECTRODE slot — Trellis
    stores each electrode's unit labels independently, so "unit 1" on ch5 and
    "unit 1" on ch7 are different neurons that happen to share a slot number
    (measured on this recording's manual sort: cross-electrode same-slot spike
    coincidence is chance-level, 0.2–5.6% at ±0.5 ms). Counting distinct sorted
    units means counting electrode × slot combinations; this parse is the one
    home for reading them.
    """
    m = _UNIT_LABEL_RE.match(label)
    return (int(m.group(1)), int(m.group(2))) if m else None
