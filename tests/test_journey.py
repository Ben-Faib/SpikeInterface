"""journey.py - the rail's marks, the next step, report freshness, the probe map and
recent activity - over hand-built snapshots (the pure half; snapshot() itself reads
the run store and is exercised end to end by scripts/check_workbench.py)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

import journey


def _snap(*, present=True, complete=True, probe=None, run="full", n_units=4, labelled=0,
          flagged=(), curation=None, built=None, reproduced=(), phy=False):
    units = [{"unit": str(u), "contact": str(u + 1), "n_spikes": 1000, "v_pp_uV": 40.0 + u,
              "snr": 5.0, "strong": True, "advised": str(u) in flagged,
              "label": "good" if u < labelled else None} for u in range(n_units)]
    run_d = None
    if run:
        run_d = {"id": "20260101-000000-aaaaaa", "smoke": run == "smoke",
                 "effective_seconds": 30.0 if run == "smoke" else 132.0,
                 "channel_ids": [str(c) for c in range(1, 17)]}
    return {"sorter": "tridesclous2",
            "data": {"present": present, "complete": complete, "unreadable": False,
                     "missing": [] if complete else [".ns5"], "n_streams": 3 if complete else 2},
            "probe": probe or {"name": "nnx", "summary": "16 contacts · linear", "match": "fits"},
            "built": built or {}, "run": run_d, "units": units if run else [],
            "n_units": n_units if run else 0, "n_labelled": labelled if run else 0,
            "flagged": list(flagged), "curation": curation or {}, "reproduced": list(reproduced),
            "phy_exported": phy}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(journey.bio, "REPO_ROOT", tmp_path)
    (tmp_path / "outputs").mkdir()
    return tmp_path


def _marks(snap):
    return {s["key"]: (s["mark"], s["caption"]) for s in journey.stage_status(snap)}


def test_stage_marks_follow_the_state(repo):
    assert _marks(_snap(present=False, run=None))["data"] == ("warn", "no files")
    assert _marks(_snap(complete=False))["data"] == ("warn", "missing .ns5")
    assert _marks(_snap(probe={"name": "x", "match": "mismatch"}))["probe"][0] == "warn"
    assert _marks(_snap(probe={"name": "independent", "match": "auto"}))["probe"] == ("warn", "placeholder")
    assert _marks(_snap(run=None))["sort"] == ("todo", "not sorted")
    assert _marks(_snap(run="smoke"))["sort"] == ("warn", "30 s test only")
    assert _marks(_snap())["sort"] == ("done", "4 units")
    assert _marks(_snap(labelled=2))["judge"] == ("todo", "2/4")
    assert _marks(_snap(labelled=4))["judge"] == ("done", "4/4")
    pending = {"counts": {"total": 3}, "has_curated": False}
    assert _marks(_snap(curation=pending))["apply"] == ("warn", "3 to apply")
    stale = {"counts": {"total": 3}, "has_curated": True, "stale": True}
    assert _marks(_snap(curation=stale))["apply"][0] == "warn"
    assert _marks(_snap(curation={"counts": {"total": 3}, "has_curated": True}))["apply"] == ("done", "curated")
    assert _marks(_snap())["share"] == ("todo", "")          # no report yet


def test_next_steps_lead_with_the_blocker_and_never_invite_judging_a_test_sort(repo):
    assert journey.next_steps(_snap(present=False, run=None))[0]["title"] == "Add the recording"
    assert journey.next_steps(_snap(run=None))[0]["action"] == "sort"
    smoke = [s["title"] for s in journey.next_steps(_snap(run="smoke", flagged=("1",)))]
    assert smoke[0] == "Sort the full recording"
    assert not any(t.startswith(("Judge", "Build the report", "Split", "Check this run"))
                   for t in smoke)
    steps = journey.next_steps(_snap(labelled=1, flagged=("2", "3")))
    assert steps[0]["title"] == "Judge the remaining 3 units"
    assert "2 flagged" in steps[0]["detail"] and steps[0]["action"] == "stage:4"
    titles = [s["title"] for s in steps]
    assert "Split the merged pairs in Phy" in titles and "Check this run reproduces" in titles
    report = repo / "outputs" / "report.html"
    report.write_text("x")
    old = datetime(2026, 1, 1).timestamp()
    os.utime(report, (old, old))
    done = journey.next_steps(_snap(labelled=4, phy=True, reproduced=[{"verdict": "REGENERATED"}],
                                    built={"report": {"when": "2026-01-02T00:00",
                                                      "sorter": "tridesclous2",
                                                      "run": "20260101-000000-aaaaaa"}}))
    assert [s["title"] for s in done] == ["Everything is up to date"]


def test_report_state_never_vouches_for_a_file_it_did_not_build(repo):
    snap = _snap(curation={"updated": "2026-01-01T10:00:00"})
    assert journey.report_state(snap)["status"] == "missing"
    report = repo / "outputs" / "report.html"
    report.write_text("x")
    built_at = datetime(2026, 3, 1, 12, 0)
    os.utime(report, (built_at.timestamp(), built_at.timestamp()))
    assert journey.report_state(snap)["status"] == "unknown"             # no stamp at all
    stamp = {"when": built_at.isoformat(timespec="minutes"), "sorter": "tridesclous2",
             "run": "20260101-000000-aaaaaa", "curation_updated": "2026-01-01T10:00:00"}
    snap["built"] = {"report": dict(stamp)}
    assert journey.report_state(snap)["status"] == "fresh"
    snap["built"] = {"report": dict(stamp, run="20250101-000000-bbbbbb")}
    assert journey.report_state(snap)["status"] == "stale"                # another run
    snap["built"] = {"report": dict(stamp, curation_updated="2025-12-31T00:00:00")}
    assert journey.report_state(snap)["status"] == "stale"                # labels changed since
    later = built_at + timedelta(hours=2)
    os.utime(report, (later.timestamp(), later.timestamp()))
    snap["built"] = {"report": dict(stamp)}
    rs = journey.report_state(snap)
    assert rs["status"] == "unknown" and "outside Spike" in rs["note"]   # a CLI rebuild


def test_probe_map_puts_the_tip_last_and_the_biggest_unit_first():
    snap = _snap(n_units=3)
    snap["units"].append({"unit": "9", "contact": "1", "v_pp_uV": 99.0, "advised": False,
                          "label": None})
    pm = journey.probe_map(snap)
    assert pm["contacts"][0] == "16" and pm["contacts"][-1] == "1"
    assert [u["unit"] for u in pm["units"]["1"]] == ["9", "0"]


def test_recent_keeps_one_line_per_kind_of_event(repo):
    snap = _snap(curation={"has_curated": True, "updated": "2026-01-03T10:00:00",
                           "counts": {"total": 2}},
                 built={"report": {"when": "2026-01-04T09:00"}},
                 reproduced=[{"when": "2026-01-05T08:00:00", "run": "20260101-000000-aaaaaa",
                              "verdict": "REGENERATED"},
                             {"when": "2026-01-01T08:00:00", "run": "20260101-000000-aaaaaa",
                              "verdict": "NOT REGENERATED"}])
    texts = [r["text"] for r in journey.recent(snap)]
    assert texts[0].startswith("reproduced run aaaaaa · REGENERATED")
    assert sum(t.startswith("reproduced") for t in texts) == 1
    assert "report built" in texts and texts[-1].startswith("2 decisions applied")
