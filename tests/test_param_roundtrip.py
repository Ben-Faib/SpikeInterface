"""End-to-end pins for the sorter-parameter round trip.

The chain Ben asked to be sure of, and where each link lives:

    param editor (menu_app)
      -> MenuController.set_params            (SpikeInterface_Menu.py)
      -> .si_menu.json "sorter_params"        (diffs from the defaults)
      -> MenuController.sort_command          (in-UI sort: --param NAME=VALUE)
         / _write_params_file                 (dispatch path: --params-file)
      -> run_sorting.resolve_overrides        (scripts/run_sorting.py)
      -> run_info.json "params"               (provenance)

These tests use the real seams: the real controller, the real
``sorters.default_params`` introspection that BOTH the editor and run_sorting
read, and run_sorting's own ``resolve_overrides``. Nothing is sorted here; the
provenance tests read the runs already saved under ``outputs/`` and check the
record against the parameter dict SpikeInterface itself wrote for that run.

Regression pinned: ``sort_command`` used to build ``--param k=str(value)``, which
is Python repr for dict / list / None-default parameters. The child then exited
with "expected JSON for this parameter" before sorting started, so any edit to a
parameter like tridesclous2's ``job_kwargs`` or spykingcircus2's ``detection``
made the dashboard's sort button fail. See ``_param_arg``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import SpikeInterface_Menu as M  # noqa: E402
import run_sorting as rs  # noqa: E402
import runs  # noqa: E402
import sorters  # noqa: E402

# The internal sorters: no external binary, so always installed (CLAUDE.md).
LOCAL_SORTERS = ["tridesclous2", "spykingcircus2", "lupin", "simple"]


def _sample_edit(default):
    """A plausible edited value for a parameter whose default is ``default``.

    Derived from the default's TYPE rather than named per parameter, so the test
    keeps covering every parameter the editor can show even when SpikeInterface
    renames or adds one.
    """
    if isinstance(default, bool):
        return not default
    if isinstance(default, int):
        return default + 1
    if isinstance(default, float):
        return default + 1.5
    if isinstance(default, str):
        return default + "x"       # a str default is taken raw: any string works
    if isinstance(default, dict):
        return {"n_jobs": 2}
    if isinstance(default, list):
        return [1, 2]
    return 42                      # None default: JSON-decoded, so a scalar is fine


def _params(**over):
    ns = dict(data_dir=None, sorter="tridesclous2", duration=None, docker=False,
              params_file=None, gui_mode="auto")
    ns.update(over)
    return argparse.Namespace(**ns)


def _controller(monkeypatch, tmp_path, cfg=None, save=False):
    """A real MenuController over an empty data dir. ``save=True`` lets it write
    .si_menu.json, redirected into ``tmp_path``."""
    import report

    monkeypatch.setattr(report, "_gather", lambda *a, **k: ({}, []))
    monkeypatch.setattr(M, "CONFIG_PATH", tmp_path / ".si_menu.json")
    if not save:
        monkeypatch.setattr(M, "_save_config", lambda cfg: None)
    return M.MenuController(_params(data_dir=str(tmp_path)), dict(cfg or {}))


def _cli_params(argv: list) -> list:
    """The NAME=VALUE payloads of every --param in an argv list."""
    return [argv[i + 1] for i, a in enumerate(argv) if a == "--param"]


# --------------------------------------------------------------------------- #
# The defaults a user is shown are the defaults that run
# --------------------------------------------------------------------------- #
def test_defaults_have_a_single_home():
    """Editor, controller and run_sorting must read the same introspection call."""
    assert M.sorter_registry is sorters       # what the editor is served
    assert rs.sorters is sorters              # what the sort resolves against


@pytest.mark.parametrize("sorter", LOCAL_SORTERS)
def test_shown_defaults_are_the_defaults_run_sorting_validates(monkeypatch, tmp_path, sorter):
    c = _controller(monkeypatch, tmp_path)
    shown = c.default_params(sorter)          # exactly what the param editor lists
    assert shown == sorters.default_params(sorter)
    assert shown, f"{sorter} exposes no parameters"
    # run_sorting validates against that same dict: no key it shows is rejected.
    assert rs.resolve_overrides(sorter, [], None) == {}
    with pytest.raises(SystemExit):
        rs.resolve_overrides(sorter, ["not_a_real_param=1"], None)


# --------------------------------------------------------------------------- #
# Editor value -> CLI -> resolved override
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sorter", LOCAL_SORTERS)
def test_every_parameter_survives_the_cli_encoding(sorter):
    """Encode with the menu's encoder, decode with run_sorting's decoder, for
    EVERY parameter the sorter exposes. The two must be exact inverses."""
    defaults = sorters.default_params(sorter)
    for key, default in defaults.items():
        edited = _sample_edit(default)
        raw = M._param_arg(defaults, key, edited)
        got = rs.resolve_overrides(sorter, [f"{key}={raw}"], None)
        assert got == {key: edited}, f"{sorter}.{key} ({type(default).__name__})"


def test_python_repr_of_a_container_is_rejected_by_the_child():
    """Why the encoder exists: str() of a dict is not JSON, and the child says so
    rather than sorting with a wrong value."""
    repr_form = "job_kwargs=" + str({"n_jobs": 2})     # the old sort_command output
    with pytest.raises(SystemExit):
        rs.resolve_overrides("tridesclous2", [repr_form], None)


def test_sort_command_roundtrips_overrides_of_every_type(monkeypatch, tmp_path):
    """The in-UI sort path, end to end: saved overrides -> argv -> what the child
    resolves. This is the regression that broke dict / None-default edits."""
    saved = {"detect_threshold": 6.5,        # float
             "n_peaks_per_channel": 4000,    # int
             "peak_sign": "pos",             # str
             "apply_preprocessing": False,   # bool
             "seed": 42,                     # None default -> JSON
             "job_kwargs": {"n_jobs": 2}}    # dict default -> JSON
    c = _controller(monkeypatch, tmp_path,
                    cfg={"sorter_params": {"tridesclous2": dict(saved)}})
    assert c.active_sorter == "tridesclous2"
    argv = c.sort_command(None)
    assert rs.resolve_overrides("tridesclous2", _cli_params(argv), None) == saved


def test_sort_command_passes_nothing_when_there_are_no_overrides(monkeypatch, tmp_path):
    c = _controller(monkeypatch, tmp_path)
    assert _cli_params(c.sort_command(None)) == []


def test_params_file_path_roundtrips_overrides(monkeypatch, tmp_path):
    """The dispatch path (MenuController.run -> --params-file) carries the same
    dict, types intact."""
    saved = {"detect_threshold": 6.5, "seed": 7, "job_kwargs": {"n_jobs": 2}}
    c = _controller(monkeypatch, tmp_path,
                    cfg={"sorter_params": {"tridesclous2": dict(saved)}})
    path = M._write_params_file(c.get_overrides("tridesclous2"))
    try:
        assert rs.resolve_overrides("tridesclous2", [], path) == saved
    finally:
        Path(path).unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Editor -> .si_menu.json
# --------------------------------------------------------------------------- #
def test_set_params_persists_diffs_and_reloads(monkeypatch, tmp_path):
    defaults = sorters.default_params("tridesclous2")
    c = _controller(monkeypatch, tmp_path, save=True)
    # What the editor dismisses with: every widget's value, defaults included.
    edited = dict(defaults)
    edited["detect_threshold"] = 6.5
    edited["job_kwargs"] = {"n_jobs": 2}
    c.set_params("tridesclous2", edited)

    on_disk = json.loads((tmp_path / ".si_menu.json").read_text(encoding="utf-8"))
    assert on_disk["sorter_params"]["tridesclous2"] == {"detect_threshold": 6.5,
                                                        "job_kwargs": {"n_jobs": 2}}
    # A fresh session reads the same overrides back, and they still resolve.
    c2 = _controller(monkeypatch, tmp_path, cfg=on_disk)
    assert c2.get_overrides("tridesclous2") == {"detect_threshold": 6.5,
                                                "job_kwargs": {"n_jobs": 2}}
    assert rs.resolve_overrides("tridesclous2", _cli_params(c2.sort_command(None)),
                                None) == {"detect_threshold": 6.5,
                                          "job_kwargs": {"n_jobs": 2}}


def test_reset_to_defaults_clears_the_saved_overrides(monkeypatch, tmp_path):
    """Ctrl+R dismisses with an empty dict; the sort must then carry no --param."""
    c = _controller(monkeypatch, tmp_path, save=True,
                    cfg={"sorter_params": {"tridesclous2": {"detect_threshold": 6.5}}})
    c.set_params("tridesclous2", {})
    assert c.get_overrides("tridesclous2") == {}
    assert _cli_params(c.sort_command(None)) == []
    on_disk = json.loads((tmp_path / ".si_menu.json").read_text(encoding="utf-8"))
    assert "tridesclous2" not in on_disk["sorter_params"]


# --------------------------------------------------------------------------- #
# run_info.json provenance
# --------------------------------------------------------------------------- #
def _saved_records() -> list:
    """(run_info dict, sorter_output dir) for every finished run in the store."""
    out = []
    for sorter in LOCAL_SORTERS + ["mountainsort5", "waveclus", "mountainsort4"]:
        base = runs.sorter_dir(sorter) / "runs"
        if not base.is_dir():
            continue
        for run_dir in sorted(base.iterdir()):
            info_path = run_dir / runs.RUN_INFO_NAME
            if not info_path.is_file():
                continue            # unfinished run, or one being written right now
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(info.get("params"), dict):
                out.append((info, run_dir / "sorter_output"))
    return out


def test_run_info_params_block_is_self_consistent():
    """effective == defaults + overrides, as recorded. Version independent: it
    compares the record against itself, so an SI upgrade cannot fake a pass."""
    records = _saved_records()
    if not records:
        pytest.skip("no saved run with a params block in outputs/")
    for info, _ in records:
        p = info["params"]
        assert set(p) >= {"effective", "defaults", "overrides"}, info.get("run_id")
        assert p["effective"] == {**p["defaults"], **p["overrides"]}, info.get("run_id")
        assert set(p["overrides"]) <= set(p["defaults"]), info.get("run_id")


def test_run_info_records_the_parameters_spikeinterface_actually_used():
    """The provenance claim, checked against SpikeInterface's own record of the
    run: run_sorter writes sorter_output/spikeinterface_params.json."""
    checked = 0
    for info, sorter_output in _saved_records():
        si_params = sorter_output / "spikeinterface_params.json"
        if not si_params.is_file():
            continue
        try:
            actual = json.loads(si_params.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        assert actual["sorter_params"] == info["params"]["effective"], info.get("run_id")
        checked += 1
    if not checked:
        pytest.skip("no saved run carries SpikeInterface's own parameter record")
