"""Unit tests for run_sorting's pure helpers (no real sorting)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sorters  # noqa: E402
import run_sorting as rs  # noqa: E402


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(sorters, "installed", lambda: ["spykingcircus2", "tridesclous2"])
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(sorters, "CONTAINERIZED", frozenset({"mountainsort5", "tridesclous2"}))
    monkeypatch.setattr(sorters, "default_params", lambda name: {
        "detect_threshold": 5.0, "n_peaks": 5000, "apply_preprocessing": True})


def test_resolve_sorter_ok_local(fake):
    assert rs.resolve_sorter("tridesclous2", use_docker=False) == "tridesclous2"


def test_resolve_sorter_rejects_unrunnable(fake):
    with pytest.raises(SystemExit):
        rs.resolve_sorter("kilosort4", use_docker=False)


def test_resolve_sorter_docker_enables_container(fake):
    assert rs.resolve_sorter("mountainsort5", use_docker=True) == "mountainsort5"


def test_resolve_overrides_merges_file_then_cli(fake, tmp_path):
    pf = tmp_path / "p.json"
    pf.write_text('{"detect_threshold": 4.0, "n_peaks": 100}')
    out = rs.resolve_overrides("tridesclous2", ["detect_threshold=6.5"], str(pf))
    assert out["detect_threshold"] == 6.5   # CLI wins over file
    assert out["n_peaks"] == 100            # from file
    assert "apply_preprocessing" not in out  # defaults not duplicated


def test_resolve_overrides_unknown_key_exits(fake):
    with pytest.raises(SystemExit):
        rs.resolve_overrides("tridesclous2", ["bogus=1"], None)


def test_resolve_overrides_bad_value_exits(fake):
    with pytest.raises(SystemExit):
        rs.resolve_overrides("tridesclous2", ["n_peaks=notint"], None)


def test_friendly_message_when_docker_not_running(monkeypatch):
    # docker requested AND the daemon actually down -> the start-Docker hint.
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    msg = rs._friendly_sort_error(
        RuntimeError("Docker was requested but the Docker daemon isn't reachable."),
        use_docker=True)
    assert "Docker" in msg and "try again" in msg.lower()


def test_friendly_message_does_not_misblame_docker_when_running(monkeypatch):
    # Regression: an error that merely mentions "docker" must NOT be reported as
    # "Docker isn't running" when the daemon is up — that substring match masked a
    # real failure (a missing SDK / sorter crash) and sent users to a dead end.
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    msg = rs._friendly_sort_error(
        RuntimeError("The python docker package must be installed."), use_docker=True)
    assert "isn't running" not in msg
    assert "docker package" in msg          # the real cause is surfaced, not hidden


def test_friendly_message_local_failure_passthrough():
    msg = rs._friendly_sort_error(RuntimeError("kaboom"), use_docker=False)
    assert "Sorting failed" in msg and "kaboom" in msg


def test_quality_summary_uses_the_shared_rule(tmp_path, monkeypatch):
    # W1 slice 1: the rule's one owner is sort_summary — defaults SNR>=4,
    # ISI ratio<=0.5, amp cutoff<=0.1, presence>=0.9, NaN criteria skipped.
    import pandas as pd
    import blackrock_io as bio
    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)   # no user override present
    qm = pd.DataFrame({
        "snr": [6.0, 3.0, 9.0, 5.0],                  # >=4: rows 0,2,3
        "isi_violations_ratio": [0.1, 0.0, 0.9, 0.2],  # <=0.5: rows 0,1,3
    })
    n_total, n_good, rule_desc, _unk = rs._quality_summary(qm)   # both: rows 0,3
    assert n_total == 4 and n_good == 2
    assert "SNR ≥ 4" in rule_desc and "NaN" in rule_desc


def test_quality_summary_honours_user_rule(tmp_path, monkeypatch):
    import json as _json
    import pandas as pd
    import blackrock_io as bio
    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)
    (tmp_path / ".si_menu.json").write_text(_json.dumps(
        {"quality_rule": {"snr_min": 8.0, "junk": "ignored", "isi_violations_ratio_max": "bad"}}))
    qm = pd.DataFrame({"snr": [6.0, 9.0], "isi_violations_ratio": [0.1, 0.1]})
    n_total, n_good, rule_desc, _unk = rs._quality_summary(qm)
    assert (n_total, n_good) == (2, 1)                 # only snr 9 clears 8
    assert "SNR ≥ 8" in rule_desc                      # the EFFECTIVE rule is stated
    assert "ISI ratio ≤ 0.5" in rule_desc              # junk override fell back


def test_quality_summary_handles_missing_columns(tmp_path, monkeypatch):
    import pandas as pd
    import blackrock_io as bio
    monkeypatch.setattr(bio, "REPO_ROOT", tmp_path)
    # No evaluable criterion on any unit -> honest None, never a fake 0-pass.
    n_total, n_good, _rule, _unk = rs._quality_summary(pd.DataFrame({"firing_rate": [1.0, 2.0]}))
    assert n_total == 2 and n_good is None


def test_prepare_docker_image_uses_cache(monkeypatch):
    monkeypatch.setattr(sorters, "default_docker_image", lambda s: "img:latest")
    monkeypatch.setattr(sorters, "docker_image_present", lambda i: True)

    def _no_pull(*a, **k):
        raise AssertionError("must not pull when the image is already cached")
    monkeypatch.setattr(sorters, "pull_docker_image", _no_pull)
    rs._prepare_docker_image(rs.ConsoleUI(quiet=True, total_phases=4), "mountainsort5")


def test_prepare_docker_image_pulls_when_absent(monkeypatch):
    calls = {}
    monkeypatch.setattr(sorters, "default_docker_image", lambda s: "img:latest")
    monkeypatch.setattr(sorters, "docker_image_present", lambda i: False)
    monkeypatch.setattr(sorters, "pull_docker_image",
                        lambda *a, **k: calls.setdefault("pulled", True) or True)
    rs._prepare_docker_image(rs.ConsoleUI(quiet=True, total_phases=4), "mountainsort5")
    assert calls.get("pulled") is True


def test_prepare_docker_image_noop_without_image(monkeypatch):
    monkeypatch.setattr(sorters, "default_docker_image", lambda s: None)

    def _boom(i):
        raise AssertionError("should not probe presence when there is no image")
    monkeypatch.setattr(sorters, "docker_image_present", _boom)
    rs._prepare_docker_image(rs.ConsoleUI(quiet=True, total_phases=4), "weird")


def test_reporter_emits_events_to_stdout(monkeypatch):
    import io

    import sort_progress as sp

    buf = io.StringIO()
    rep = rs.Reporter(enabled=True, stream=buf, total_phases=4)
    rep.phase("Read broadband", "22 ch")
    rep.bar("detect", frac=0.5, n=5, total=10)
    rep.done_ok(units=13, good=9, out="outputs/x")

    events = [sp.parse_line(l) for l in buf.getvalue().splitlines()]
    events = [e for e in events if e]
    assert events[0]["t"] == "phase" and events[0]["title"] == "Read broadband"
    assert any(e["t"] == "bar" and e["frac"] == 0.5 for e in events)
    assert events[-1]["t"] == "done" and events[-1]["units"] == 13


def test_reporter_disabled_emits_nothing():
    import io

    buf = io.StringIO()
    rep = rs.Reporter(enabled=False, stream=buf, total_phases=4)
    rep.phase("X")
    rep.substep("snr", 1, 8)
    rep.done_ok(units=0, out="o")
    assert buf.getvalue() == ""


def test_reporter_emits_substep_events(monkeypatch):
    import io

    import sort_progress as sp

    buf = io.StringIO()
    rep = rs.Reporter(enabled=True, stream=buf, total_phases=4)
    rep.substep("firing_rate", 1, 8)
    rep.substep("snr", 2, 8)

    events = [e for e in (sp.parse_line(l) for l in buf.getvalue().splitlines()) if e]
    assert events[0] == {"t": "substep", "name": "firing_rate", "i": 1, "n": 8}
    assert events[1] == {"t": "substep", "name": "snr", "i": 2, "n": 8}


def test_reporter_substep_disabled_noop():
    import io

    buf = io.StringIO()
    rep = rs.Reporter(enabled=False, stream=buf, total_phases=4)
    rep.substep("snr", 1, 8)
    assert buf.getvalue() == ""


def test_resolve_probe_defaults_to_active_default():
    import run_sorting, probes
    p = run_sorting.resolve_probe(None, None)
    assert p["name"] == probes.DEFAULT_PROBE == "nnx-a1x16-3mm-100"
    assert p["kind"] == "linear"


def test_resolve_probe_named():
    import run_sorting
    p = run_sorting.resolve_probe("linear-16-50um", None)
    assert p["kind"] == "linear" and p["params"]["n"] == 16


def test_resolve_probe_file():
    import run_sorting
    p = run_sorting.resolve_probe(None, "/tmp/x.json")
    assert p["kind"] == "file" and p["params"]["path"] == "/tmp/x.json"


def test_resolve_probe_unknown_returns_none():
    import run_sorting
    assert run_sorting.resolve_probe("definitely-not-a-real-probe", None) is None


# --------------------------------------------------------------------------- #
# Bad-channel detection (PRE1): a bad electrode must leave BEFORE the common
# median reference, exactly like the analog aux channels.
# --------------------------------------------------------------------------- #
def test_parse_bad_channels_splits_trims_and_dedupes():
    assert rs.parse_bad_channels("3, 7,3 ,,") == ["3", "7"]
    assert rs.parse_bad_channels(None) == []
    assert rs.parse_bad_channels("") == []


def test_plan_excludes_detected_in_recording_order():
    ids = [str(i) for i in range(1, 17)]
    excluded, plan = rs.plan_bad_channels(ids, detected=["3", "1"], manual=[])
    assert excluded == ["1", "3"]          # recording order, not detection order
    assert plan["detected"] == ["3", "1"] and plan["excluded"] == ["1", "3"]
    assert plan["refused_auto"] is False and plan["unknown"] == []


def test_plan_unions_manual_with_detected():
    excluded, plan = rs.plan_bad_channels(list("abcd"), detected=["b"], manual=["d", "b"])
    assert excluded == ["b", "d"]          # union, no duplicate for the overlap
    assert plan["manual"] == ["d", "b"]


def test_plan_refuses_to_auto_exclude_too_much_of_the_array():
    # 5 of 16 is past the 25% ceiling: a detector that flags a third of a small
    # probe is likelier mis-tuned than right, so NOTHING auto-excludes.
    ids = [str(i) for i in range(1, 17)]
    excluded, plan = rs.plan_bad_channels(ids, detected=ids[:5], manual=[])
    assert excluded == [] and plan["refused_auto"] is True
    assert plan["detected"] == ids[:5]     # still recorded — refused, not forgotten


def test_plan_keeps_auto_exclusion_at_the_ceiling():
    ids = [str(i) for i in range(1, 17)]
    excluded, plan = rs.plan_bad_channels(ids, detected=ids[:4], manual=[])
    assert excluded == ids[:4] and plan["refused_auto"] is False


def test_plan_manual_channels_survive_the_guard():
    # The ceiling governs AUTO-detection only; a named channel is the user's call.
    ids = [str(i) for i in range(1, 17)]
    excluded, plan = rs.plan_bad_channels(ids, detected=ids[:9], manual=["2"])
    assert excluded == ["2"] and plan["refused_auto"] is True


def test_plan_reports_unknown_manual_ids():
    excluded, plan = rs.plan_bad_channels(["1", "2"], detected=[], manual=["2", "99"])
    assert plan["unknown"] == ["99"]       # surfaced, never silently ignored
    assert excluded == ["2"]


N_SYNTH = 16          # this rig's electrode count; the probe profile below is its real one


def _synthetic(seed=0):
    """Plain 5 µV noise on N_SYNTH channels, ids "0".."15" — this rig's shape.

    Ids are 0-based only because ``set_probe`` renames a NumpyRecording's channels
    to the probe's device indices; the real Blackrock recording keeps its own
    "1".."16" ids through the same call.
    """
    import numpy as np
    import spikeinterface.full as si

    fs = 30_000.0
    rng = np.random.default_rng(seed)
    traces = rng.normal(0.0, 5.0, size=(int(6 * fs), N_SYNTH)).astype("float32")
    return traces, fs, si, rng


def _wrap(traces, fs, si):
    """The synthetic traces as a Recording carrying the real 100 µm probe geometry."""
    import numpy as np
    import probes

    rec = si.NumpyRecording([traces], sampling_frequency=fs,
                            channel_ids=np.array([str(i) for i in range(N_SYNTH)]))
    rec.set_channel_gains(1.0)
    rec.set_channel_offsets(0.0)
    return rec.set_probe(probes.build(probes.get(probes.DEFAULT_PROBE), N_SYNTH))


def test_detect_flags_nothing_on_a_clean_recording():
    traces, fs, si, _rng = _synthetic()
    rec = _wrap(traces, fs, si)
    bad, labels = rs.detect_bad_channels(rec, "mad")
    assert bad == []
    assert set(labels.values()) == {"good"} and len(labels) == N_SYNTH


def test_detect_finds_a_planted_noisy_channel_and_is_deterministic():
    traces, fs, si, rng = _synthetic()
    traces[:, 6] = rng.normal(0.0, 60.0, size=traces.shape[0])   # channel "6", 12x noisier
    rec = _wrap(traces, fs, si)
    bad, labels = rs.detect_bad_channels(rec, "mad")
    assert bad == ["6"] and labels["6"] == "noise"
    # The seed is pinned, so the same recording flags the same channel every run.
    assert rs.detect_bad_channels(rec, "mad")[0] == ["6"]


def test_excluding_a_bad_channel_keeps_every_other_channel_at_its_own_depth():
    """The exclusion plumbing: the channel leaves, the geometry does not shift."""
    import blackrock_io as bio

    traces, fs, si, rng = _synthetic()
    traces[:, 6] = rng.normal(0.0, 60.0, size=traces.shape[0])
    rec = _wrap(traces, fs, si)
    before = {str(c): tuple(loc) for c, loc in
              zip(rec.get_channel_ids(), rec.get_channel_locations())}

    detected, _labels = rs.detect_bad_channels(rec, "mad")
    excluded, _plan = rs.plan_bad_channels(rec.get_channel_ids(), detected, manual=[])
    kept = bio.select_channels(rec, [c for c in rec.get_channel_ids()
                                     if str(c) not in set(excluded)])

    assert excluded == ["6"]
    assert [str(c) for c in kept.get_channel_ids()] == [str(i) for i in range(16) if i != 6]
    after = {str(c): tuple(loc) for c, loc in
             zip(kept.get_channel_ids(), kept.get_channel_locations())}
    assert all(before[c] == loc for c, loc in after.items())   # the 600 µm slot stays empty
    # And the excluded channel is gone from the reference the sort computes.
    import spikeinterface.preprocessing as spre
    assert spre.common_reference(kept, reference="global",
                                 operator="median").get_num_channels() == 15


def test_cli_rejects_a_bad_channel_id_the_recording_does_not_have():
    """CLI wiring: a typo'd --bad-channels fails fast with the real ids listed."""
    import subprocess

    import blackrock_io as bio
    try:
        bio.find_blackrock_base()
    except FileNotFoundError:
        pytest.skip("no recording present")
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_sorting.py"),
         "--no-bad-channel-detection", "--bad-channels", "99"],
        capture_output=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=300, cwd=ROOT)
    # rich hard-wraps the warning, so compare on whitespace-normalised text.
    out = " ".join((res.stdout + res.stderr).split())
    assert res.returncode == 1                        # not argparse's rc 2 — our check
    assert "doesn't have: 99" in out and "Electrodes here:" in out


def test_check_manual_channels_accepts_real_electrodes():
    assert rs.check_manual_channels(["3", "7"], pool=["3", "7", "9"],
                                    all_ids=["3", "7", "9"]) is None
    assert rs.check_manual_channels([], pool=["3"], all_ids=["3"]) is None


def test_check_manual_channels_reports_an_id_the_recording_lacks():
    msg = rs.check_manual_channels(["99"], pool=["1", "2"], all_ids=["1", "2"])
    assert "doesn't have: 99" in msg and "Electrodes here: 1, 2" in msg


def test_check_manual_channels_distinguishes_an_aux_channel_from_a_missing_one():
    # --keep-analog: 10241 IS in the recording, it just isn't an electrode. Saying
    # "this recording doesn't have it" would send the user hunting the wrong problem.
    msg = rs.check_manual_channels(["10241"], pool=["1", "2"],
                                   all_ids=["1", "2", "10241"])
    assert "non-neural aux" in msg and "10241" in msg
    assert "doesn't have" not in msg


def test_plan_reports_what_would_be_left():
    ids = [str(i) for i in range(1, 17)]
    _excluded, plan = rs.plan_bad_channels(ids, detected=[], manual=ids[:15])
    assert plan["n_remaining"] == 1                 # below MIN_SORTABLE_CHANNELS
    _excluded, plan = rs.plan_bad_channels(ids, detected=[], manual=[])
    assert plan["n_remaining"] == 16


def test_cli_refuses_to_leave_the_reference_with_nothing_to_average():
    """Naming almost every channel must fail loudly, not die inside the sorter."""
    import subprocess

    import blackrock_io as bio
    try:
        bio.find_blackrock_base()
    except FileNotFoundError:
        pytest.skip("no recording present")
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_sorting.py"),
         "--no-bad-channel-detection", "--bad-channels", ",".join(str(i) for i in range(1, 16))],
        capture_output=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=300, cwd=ROOT)
    out = " ".join((res.stdout + res.stderr).split())
    assert res.returncode == 1
    assert "would leave 1 electrode(s)" in out and "subtracts that channel from itself" in out
