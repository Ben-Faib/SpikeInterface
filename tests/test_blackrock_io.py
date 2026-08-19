"""Tests for blackrock_io.py: file-set discovery and the .nev unit classes.

Discovery is the part that bites: this repo's folder permanently holds a SECOND
.nev beside the recording (``…_manuallySorted.nev``, Ben's manual re-export).
neo keys a file set on the extension-less stem, so that export is its own set -
but nothing stopped ``find_blackrock_base`` from returning it and handing every
loader a base with no analog data. The discovery tests below are hermetic (empty
stub files - discovery is pure path logic); one integration test runs against the
real folder, where the extra .nev actually sits, and skips cleanly without data.

The unit-class helpers (``online_unit_labels`` / ``unit_class``) moved here from
compare.py: the Blackrock unit-id convention is a property of this dataset, so it
belongs to the loader, and compare.py / explore_data.py read it from this one home.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import blackrock_io as bio  # noqa: E402

RECORDING = "PFCM7_d0ephys_Block2"
MANUAL_NEV = ROOT / f"{RECORDING}_manuallySorted.nev"


def _touch(folder: Path, *names: str) -> None:
    for n in names:
        (folder / n).write_bytes(b"")


# --------------------------------------------------------------------------- #
# find_blackrock_base - extra .nev files beside the recording set
# --------------------------------------------------------------------------- #
def test_base_is_the_set_with_analog_data_not_a_stray_nev(tmp_path):
    # The manual re-export sorts AFTER the recording here...
    _touch(tmp_path, "rec.ns2", "rec.ns5", "rec.nev", "rec_manuallySorted.nev")
    assert bio.find_blackrock_base(tmp_path) == tmp_path / "rec"


def test_base_ignores_a_stray_nev_that_sorts_first(tmp_path):
    # ...and here it sorts BEFORE it. Discovery must not depend on the name: the
    # stem carrying .nsX data is the recording, a lone .nev is a derived export.
    _touch(tmp_path, "aaa_manual_export.nev", "rec.ns5", "rec.nev")
    assert bio.find_blackrock_base(tmp_path) == tmp_path / "rec"


def test_base_falls_back_to_a_lone_nev_when_there_is_no_analog_data(tmp_path):
    # Spikes and events still load from a .nev-only folder.
    _touch(tmp_path, "spikes_only.nev")
    assert bio.find_blackrock_base(tmp_path) == tmp_path / "spikes_only"


def test_two_recording_sets_error_naming_both(tmp_path):
    _touch(tmp_path, "recA.ns5", "recA.nev", "recB.ns5", "recB.nev")
    with pytest.raises(FileNotFoundError) as e:
        bio.find_blackrock_base(tmp_path)
    msg = str(e.value)
    assert "recA" in msg and "recB" in msg          # the candidates, by name
    assert "data_dir" in msg                         # and the way out


def test_two_nev_only_sets_error_naming_both(tmp_path):
    # No analog data to disambiguate with: guessing which .nev is "the" one would
    # silently compare the wrong spikes, so it refuses and says which two it saw.
    _touch(tmp_path, "manual.nev", "online.nev")
    with pytest.raises(FileNotFoundError) as e:
        bio.find_blackrock_base(tmp_path)
    assert "manual" in str(e.value) and "online" in str(e.value)


def test_empty_folder_still_raises_the_missing_data_error(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        bio.find_blackrock_base(tmp_path)
    assert "No Blackrock" in str(e.value)


def test_ns6_counts_as_analog_data(tmp_path):
    _touch(tmp_path, "rec.ns6", "rec.nev", "other.nev")
    assert bio.find_blackrock_base(tmp_path) == tmp_path / "rec"


# --------------------------------------------------------------------------- #
# The loaders open the file the base names, never a stray .nev
# --------------------------------------------------------------------------- #
def test_read_spikes_defaults_to_the_recordings_own_nev(tmp_path, monkeypatch):
    import spikeinterface.extractors as se

    _touch(tmp_path, "rec.ns5", "rec.nev", "rec_manuallySorted.nev")
    seen = {}
    monkeypatch.setattr(se, "read_blackrock_sorting",
                        lambda path, **kw: seen.setdefault("path", path))
    bio.read_spikes(tmp_path)
    assert Path(seen["path"]).name == "rec.nev"


def test_read_spikes_honours_an_explicit_nev_path(tmp_path, monkeypatch):
    import spikeinterface.extractors as se

    _touch(tmp_path, "rec.ns5", "rec.nev", "rec_manuallySorted.nev")
    seen = {}
    monkeypatch.setattr(se, "read_blackrock_sorting",
                        lambda path, **kw: seen.setdefault("path", path))
    bio.read_spikes(tmp_path, nev_path=tmp_path / "rec_manuallySorted.nev")
    assert Path(seen["path"]).name == "rec_manuallySorted.nev"


def test_read_spikes_explicit_missing_path_fails_hard(tmp_path):
    _touch(tmp_path, "rec.ns5", "rec.nev")
    with pytest.raises(FileNotFoundError):
        bio.read_spikes(tmp_path, nev_path=tmp_path / "nope.nev")


# --------------------------------------------------------------------------- #
# .nev unit classes - the one home for the Blackrock convention
# --------------------------------------------------------------------------- #
def test_unit_class_covers_the_three_blackrock_classes():
    assert bio.unit_class("ch3#0") == "unsorted"
    assert bio.unit_class("ch3#1") == "sorted"
    assert bio.unit_class("ch12#254") == "sorted"
    assert bio.unit_class("ch3#255") == "noise"
    assert bio.unit_class("weird-name") == "other"


def test_online_unit_labels_needs_a_neo_backed_sorting():
    class _Sorting:
        pass

    assert bio.online_unit_labels(_Sorting()) is None


def test_online_unit_labels_reads_the_neo_spike_channel_names():
    class _Reader:
        header = {"spike_channels": {"name": ["ch3#0", "ch5#1"]}}

    class _Sorting:
        neo_reader = _Reader()

    assert bio.online_unit_labels(_Sorting()) == ["ch3#0", "ch5#1"]


# --------------------------------------------------------------------------- #
# Integration - the real folder, where the extra .nev really does sit
# --------------------------------------------------------------------------- #
def test_the_real_folder_resolves_past_its_extra_nev():
    try:
        base = bio.find_blackrock_base()
    except FileNotFoundError:
        pytest.skip("no Blackrock recording on this machine")
    if not MANUAL_NEV.exists():
        pytest.skip("the manually-sorted .nev is not on this machine")

    assert base.name == RECORDING                    # not …_manuallySorted
    assert base.with_suffix(".ns5").exists()

    # The two .nev files are different sorts of the same recording: the default
    # read must give the recording's own units, the explicit read the export's.
    own = bio.read_spikes()
    manual = bio.read_spikes(nev_path=MANUAL_NEV)
    assert len(own.get_unit_ids()) != len(manual.get_unit_ids())
    # ...and the class recovery still names the recording's own detections.
    labels = bio.online_unit_labels(own)
    assert labels and all(bio.unit_class(x) == "unsorted" for x in labels)

    bio.read_events()                                # the base, not a stray .nev
