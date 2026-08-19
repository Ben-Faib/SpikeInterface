"""Hermetic unit tests for scripts/sorters.py.

The registry's discovery functions import SpikeInterface lazily, so every test
here monkeypatches them - no SpikeInterface, no Docker, no sorting is invoked.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sorters  # noqa: E402


@pytest.fixture
def fake_env(monkeypatch):
    """Default fake: tridesclous2 + spykingcircus2 installed, Docker on."""
    monkeypatch.setattr(sorters, "installed", lambda: ["spykingcircus2", "tridesclous2"])
    monkeypatch.setattr(sorters, "available", lambda: sorted(
        ["tridesclous2", "spykingcircus2", "mountainsort5", "herdingspikes",
         "kilosort4", "combinato"]))
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    return monkeypatch


def test_status_local(fake_env):
    assert sorters.status("tridesclous2") == "local"


def test_status_docker(fake_env):
    # not installed, CPU container image, Docker up -> docker
    assert sorters.status("mountainsort5") == "docker"
    assert sorters.status("herdingspikes") == "docker"


def test_status_gpu(fake_env):
    # GPU-only sorters are flagged even when Docker is up
    assert sorters.status("kilosort4") == "gpu"


def test_status_unavailable_when_docker_off(fake_env, monkeypatch):
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    assert sorters.status("mountainsort5") == "unavailable"


def test_status_unavailable_unknown(fake_env):
    # not installed, no image, not GPU -> unavailable
    assert sorters.status("nonexistent_sorter") == "unavailable"


def test_runnable_local_only(fake_env):
    assert sorters.runnable(use_docker=False) == ["spykingcircus2", "tridesclous2"]


def test_runnable_with_docker_adds_containers(fake_env):
    r = sorters.runnable(use_docker=True)
    assert r[:2] == ["spykingcircus2", "tridesclous2"]      # installed first
    assert "mountainsort5" in r and "herdingspikes" in r    # container extras
    assert "kilosort4" not in r                              # GPU excluded
    assert len(r) == len(set(r))                             # no duplicates


def test_runnable_docker_off_is_local(fake_env, monkeypatch):
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    assert sorters.runnable(use_docker=True) == ["spykingcircus2", "tridesclous2"]


def test_default_sorter_prefers_tridesclous2(fake_env):
    assert sorters.default_sorter() == "tridesclous2"


def test_default_sorter_falls_back_to_first_installed(fake_env, monkeypatch):
    monkeypatch.setattr(sorters, "installed", lambda: ["spykingcircus2"])
    assert sorters.default_sorter() == "spykingcircus2"


@pytest.fixture
def fake_params(monkeypatch):
    monkeypatch.setattr(sorters, "default_params", lambda name: {
        "detect_threshold": 5.0,   # float
        "n_peaks": 5000,           # int
        "peak_sign": "neg",        # str
        "apply_preprocessing": True,  # bool
        "seed": None,              # None -> JSON
        "job_kwargs": {},          # dict -> JSON
    })


def test_coerce_float():
    assert sorters.coerce_param(5.0, "6.5") == 6.5


def test_coerce_int():
    assert sorters.coerce_param(5000, "1000") == 1000


def test_coerce_bool_truthy():
    assert sorters.coerce_param(True, "false") is False
    assert sorters.coerce_param(False, "yes") is True


def test_coerce_str_passthrough():
    assert sorters.coerce_param("neg", "pos") == "pos"


def test_coerce_none_as_json():
    assert sorters.coerce_param(None, "42") == 42
    assert sorters.coerce_param(None, "null") is None


def test_coerce_dict_as_json():
    assert sorters.coerce_param({}, '{"n_jobs": 4}') == {"n_jobs": 4}


def test_coerce_bad_int_raises():
    with pytest.raises(ValueError):
        sorters.coerce_param(5000, "notanint")


def test_coerce_bad_json_raises():
    with pytest.raises(ValueError):
        sorters.coerce_param({}, "{not json}")


def test_merge_params_applies_overrides(fake_params):
    merged = sorters.merge_params("tridesclous2", {"detect_threshold": 6.0})
    assert merged["detect_threshold"] == 6.0
    assert merged["peak_sign"] == "neg"  # untouched default preserved


def test_merge_params_unknown_key_raises(fake_params):
    with pytest.raises(ValueError) as e:
        sorters.merge_params("tridesclous2", {"not_a_param": 1})
    assert "not_a_param" in str(e.value)


def test_run_passes_docker_and_params(fake_params, monkeypatch):
    calls = {}

    class FakeSorting:
        """Container-path result: SI registers the recording_for_docker binary copy
        on it; sorters.run must swap the native recording back in (Windows keeps
        that copy's .raw open otherwise, blocking the cache cleanup)."""
        registered = None

        def has_recording(self):
            return True

        def register_recording(self, recording, check_spike_frames=True):
            self.registered = recording
            calls["check_spike_frames"] = check_spike_frames

    fake_sorting = FakeSorting()

    class FakeSS:
        def run_sorter(self, name, recording, **kw):
            calls["name"] = name
            calls["kw"] = kw
            return fake_sorting

    import types
    fake_ss = FakeSS()
    # sorters.run does `import spikeinterface.sorters as ss`
    monkeypatch.setitem(sys.modules, "spikeinterface", types.SimpleNamespace(sorters=fake_ss))
    monkeypatch.setitem(sys.modules, "spikeinterface.sorters", fake_ss)
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)
    # Docker is a fallback for NOT-installed sorters, so the container path only
    # triggers when the sorter isn't installed locally.
    monkeypatch.setattr(sorters, "installed", lambda: [])
    # the Docker path dumps the recording to binary first; that needs a real
    # recording, so bypass it here to focus on parameter passing.
    monkeypatch.setattr(sorters, "_as_container_recording", lambda rec, folder: "BINARY")

    out = sorters.run("mountainsort5", "REC", "/tmp/out",
                      params={"detect_threshold": 6.0}, use_docker=True, verbose=False)
    assert out is fake_sorting
    assert calls["name"] == "mountainsort5"
    assert calls["kw"]["docker_image"] is True
    # SpikeInterface takes sorter params as **kwargs, NOT a sorter_params= keyword.
    assert calls["kw"]["detect_threshold"] == 6.0
    assert "sorter_params" not in calls["kw"]
    assert calls["kw"]["remove_existing_folder"] is True
    # The NATIVE recording is re-registered on the returned sorting (not the
    # container binary copy), releasing the copy's file handle for cache cleanup.
    assert fake_sorting.registered == "REC"
    assert calls["check_spike_frames"] is False


def test_run_installed_sorter_runs_native_even_with_docker_on(fake_params, monkeypatch):
    """An installed sorter runs natively even when Docker mode is on (Docker is a
    fallback only - there's no image for the local-only sorters)."""
    calls = {}

    class FakeSS:
        def run_sorter(self, name, recording, **kw):
            calls["recording"] = recording
            calls["kw"] = kw
            return "SORTING"

    import types
    fake_ss = FakeSS()
    monkeypatch.setitem(sys.modules, "spikeinterface", types.SimpleNamespace(sorters=fake_ss))
    monkeypatch.setitem(sys.modules, "spikeinterface.sorters", fake_ss)
    monkeypatch.setattr(sorters, "installed", lambda: ["tridesclous2"])
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: True)

    def _boom(rec, folder):
        raise AssertionError("an installed sorter must not be containerised")
    monkeypatch.setattr(sorters, "_as_container_recording", _boom)

    sorters.run("tridesclous2", "REC", "/tmp/out", use_docker=True)
    assert calls["recording"] == "REC"          # not the binary-dumped recording
    assert calls["kw"]["docker_image"] is False


def test_uses_docker_only_for_not_installed():
    inst = ["tridesclous2", "spykingcircus2"]
    assert sorters.uses_docker("tridesclous2", True, installed_set=inst) is False
    assert sorters.uses_docker("mountainsort5", True, installed_set=inst) is True
    assert sorters.uses_docker("mountainsort5", False, installed_set=inst) is False


def test_default_docker_image_uses_sorter_map():
    # Exact image+tag SpikeInterface would pull (names aren't always <sorter>-base).
    assert sorters.default_docker_image("mountainsort5") == "spikeinterface/mountainsort5-base:latest"
    assert sorters.default_docker_image("spykingcircus") == "spikeinterface/spyking-circus-base:latest"
    assert sorters.default_docker_image("definitely_not_a_sorter") is None


def test_run_local_passes_flat_params_and_no_binary_dump(fake_params, monkeypatch):
    """Non-docker run sends params as **kwargs and never touches the binary dump."""
    calls = {}

    class FakeSS:
        def run_sorter(self, name, recording, **kw):
            calls["recording"] = recording
            calls["kw"] = kw
            return "SORTING"

    import types
    fake_ss = FakeSS()
    monkeypatch.setitem(sys.modules, "spikeinterface", types.SimpleNamespace(sorters=fake_ss))
    monkeypatch.setitem(sys.modules, "spikeinterface.sorters", fake_ss)

    def _boom(rec, folder):
        raise AssertionError("binary dump must not run on a local (non-docker) sort")
    monkeypatch.setattr(sorters, "_as_container_recording", _boom)

    sorters.run("tridesclous2", "REC", "/tmp/out",
                params={"detect_threshold": 6.0}, use_docker=False)
    assert calls["recording"] == "REC"
    assert calls["kw"]["docker_image"] is False
    assert calls["kw"]["detect_threshold"] == 6.0
    assert "sorter_params" not in calls["kw"]


def test_run_param_named_like_run_sorter_kwarg_does_not_collide(fake_params, monkeypatch):
    """A sorter param sharing run_sorter's own name (e.g. herdingspikes 'verbose')
    must override our default, not raise 'multiple values for keyword argument'."""
    calls = {}

    class FakeSS:
        def run_sorter(self, name, recording, **kw):
            calls["kw"] = kw
            return "SORTING"

    import types
    fake_ss = FakeSS()
    monkeypatch.setitem(sys.modules, "spikeinterface", types.SimpleNamespace(sorters=fake_ss))
    monkeypatch.setitem(sys.modules, "spikeinterface.sorters", fake_ss)
    monkeypatch.setattr(sorters, "installed", lambda: ["herdingspikes"])
    monkeypatch.setattr(sorters, "default_params",
                        lambda n: {"verbose": True, "detect_threshold": 5.0})

    sorters.run("herdingspikes", "REC", "/tmp/out", params={"verbose": False}, use_docker=False)
    assert calls["kw"]["verbose"] is False          # the user's sorter-verbose wins
    assert calls["kw"]["docker_image"] is False
    assert calls["kw"]["folder"] == "/tmp/out"


def test_coerce_none_default_empty_means_none():
    # Empty field for a None-default param (e.g. tridesclous2 seed) -> None, not error.
    assert sorters.coerce_param(None, "") is None
    assert sorters.coerce_param(None, "   ") is None
    assert sorters.coerce_param(None, "42") == 42   # a real value still parses


def test_run_docker_requested_but_unavailable_raises(fake_params, monkeypatch):
    # Docker only matters for a NOT-installed sorter; with the daemon down that
    # must raise rather than silently fall through.
    monkeypatch.setattr(sorters, "installed", lambda: [])
    monkeypatch.setattr(sorters, "docker_available", lambda *a, **k: False)
    with pytest.raises(RuntimeError):
        sorters.run("mountainsort5", "REC", "/tmp/out", use_docker=True)


def test_status_table_shape(fake_env, fake_params):
    rows = sorters.status_table()
    assert {r["name"] for r in rows} == set(sorters.available())
    by = {r["name"]: r for r in rows}
    assert by["tridesclous2"]["status"] == "local"
    assert by["kilosort4"]["status"] == "gpu"
    assert by["mountainsort5"]["status"] == "docker"
    assert all("n_params" in r for r in rows)


def test_recommended_is_the_preferred_default():
    # The badged ★ sorter must match what default_sorter() prefers.
    assert sorters.RECOMMENDED == "tridesclous2"


def test_description_known_and_fallback():
    assert "GPU" not in sorters.description("tridesclous2")  # local sorter, no GPU mention
    assert sorters.description("tridesclous2")               # non-empty
    # an unknown sorter gets the generic fallback, never a KeyError
    assert sorters.description("totally_made_up_sorter") == "A spike-sorting algorithm."


def test_group_of_membership_precedence(monkeypatch):
    inst = {"tridesclous2", "kilosort4"}   # note: kilosort4 installed -> READY, not GPU
    monkeypatch.setattr(sorters, "installed", lambda: sorted(inst))
    g = lambda n: sorters.group_of(n, installed_set=inst)
    assert g("tridesclous2") == "ready"      # installed
    assert g("kilosort4") == "ready"         # installed beats GPU membership (Windows+GPU target)
    assert g("kilosort3") == "gpu"           # GPU family, not installed
    assert g("mountainsort5") == "docker"    # containerized, not installed
    assert g("totally_made_up_sorter") == "unavailable"


def test_group_of_uses_live_installed_when_omitted(monkeypatch):
    monkeypatch.setattr(sorters, "installed", lambda: ["tridesclous2"])
    assert sorters.group_of("tridesclous2") == "ready"
    assert sorters.group_of("mountainsort5") == "docker"


import subprocess as _subprocess


class _Ret:
    def __init__(self, rc):
        self.returncode = rc


def test_docker_state_not_installed(monkeypatch):
    sorters._docker_cache.clear()
    monkeypatch.setattr(sorters.shutil, "which", lambda _n: None)
    assert sorters.docker_state(refresh=True) == "not_installed"
    assert sorters.docker_available(refresh=True) is False


def test_docker_state_installed_not_running(monkeypatch):
    sorters._docker_cache.clear()
    monkeypatch.setattr(sorters.shutil, "which", lambda _n: "/usr/bin/docker")
    monkeypatch.setattr(sorters.subprocess, "run", lambda *a, **k: _Ret(1))
    assert sorters.docker_state(refresh=True) == "installed_not_running"
    assert sorters.docker_available(refresh=True) is False


def test_docker_state_running(monkeypatch):
    sorters._docker_cache.clear()
    monkeypatch.setattr(sorters.shutil, "which", lambda _n: "/usr/bin/docker")
    monkeypatch.setattr(sorters.subprocess, "run", lambda *a, **k: _Ret(0))
    assert sorters.docker_state(refresh=True) == "running"
    assert sorters.docker_available(refresh=True) is True


def test_start_docker_never_raises(monkeypatch):
    called = {}

    def _popen(cmd, *a, **k):
        called["cmd"] = cmd
        class _P:  # noqa: D401 - dummy Popen
            pass
        return _P()

    monkeypatch.setattr(sorters.subprocess, "Popen", _popen)
    assert sorters.start_docker() is True
    assert called["cmd"]  # a launch command was issued

    def _boom(*a, **k):
        raise OSError("no such app")

    monkeypatch.setattr(sorters.subprocess, "Popen", _boom)
    assert sorters.start_docker() is False   # swallowed, returns False


def test_image_size_and_delete(monkeypatch):
    import sorters

    class FakeImg:
        attrs = {"Size": 1_100_000_000}

    class FakeImages:
        def __init__(self): self.removed = []
        def get(self, image): return FakeImg()
        def remove(self, image, force=False): self.removed.append(image)

    class FakeClient:
        images = FakeImages()

    fake_docker = type("D", (), {"from_env": staticmethod(lambda: FakeClient())})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)

    assert sorters.image_size("spikeinterface/x:latest") == 1_100_000_000
    ok, msg = sorters.delete_docker_image("spikeinterface/x:latest")
    assert ok is True and "x" in msg


def test_delete_docker_image_never_raises(monkeypatch):
    import sorters

    class Boom:
        @staticmethod
        def from_env(): raise RuntimeError("daemon down")

    monkeypatch.setitem(__import__("sys").modules, "docker", Boom)
    ok, msg = sorters.delete_docker_image("x:latest")
    assert ok is False and msg
    assert sorters.image_size("x:latest") is None


# --- pull_docker_image: aggregate progress over ALL layers -------------------

def _install_fake_pull(monkeypatch, events):
    """Monkeypatch the docker SDK so client.api.pull(...) yields ``events``.

    Mirrors the test_image_size_and_delete fake-docker pattern, but for the
    streaming pull API used by pull_docker_image.
    """
    class FakeApi:
        def __init__(self, evs): self._evs = evs
        def pull(self, repository, tag=None, stream=True, decode=True):
            for ev in self._evs:
                yield ev

    class FakeClient:
        def __init__(self, evs): self.api = FakeApi(evs)

    fake_docker = type("D", (), {
        "from_env": staticmethod(lambda evs=events: FakeClient(evs))})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)


def _two_layer_pull_events():
    """A realistic 2-layer ``docker pull`` event sequence (interleaved layers).

    Per layer: Pulling fs layer -> Downloading(progressDetail) ->
    Download complete -> Extracting(progressDetail) -> Pull complete; then once a
    final 'Status:' event. Layer A total = 100, layer B total = 300.
    """
    A, B = "aaaa", "bbbb"
    return [
        {"status": "Pulling fs layer", "id": A},
        {"status": "Pulling fs layer", "id": B},
        # downloading, interleaved
        {"status": "Downloading", "id": A,
         "progressDetail": {"current": 50, "total": 100}},
        {"status": "Downloading", "id": B,
         "progressDetail": {"current": 100, "total": 300}},
        {"status": "Downloading", "id": A,
         "progressDetail": {"current": 100, "total": 100}},
        {"status": "Verifying Checksum", "id": A},
        {"status": "Download complete", "id": A},
        {"status": "Downloading", "id": B,
         "progressDetail": {"current": 300, "total": 300}},
        {"status": "Download complete", "id": B},
        # extracting, interleaved
        {"status": "Extracting", "id": A,
         "progressDetail": {"current": 50, "total": 100}},
        {"status": "Extracting", "id": A,
         "progressDetail": {"current": 100, "total": 100}},
        {"status": "Pull complete", "id": A},
        {"status": "Extracting", "id": B,
         "progressDetail": {"current": 150, "total": 300}},
        {"status": "Extracting", "id": B,
         "progressDetail": {"current": 300, "total": 300}},
        {"status": "Pull complete", "id": B},
        {"status": "Status: Downloaded newer image for spikeinterface/x:latest"},
    ]


def test_pull_status_never_leaks_raw_per_layer_strings(monkeypatch):
    _install_fake_pull(monkeypatch, _two_layer_pull_events())
    statuses = []
    ok = sorters.pull_docker_image("spikeinterface/x:latest",
                                   on_status=statuses.append)
    assert ok is True
    # The raw per-layer terminal strings must NEVER be emitted to the UI.
    assert "Download complete" not in statuses
    assert "Pull complete" not in statuses
    assert "Pulling fs layer" not in statuses
    # And no raw per-layer 'Downloading'/'Extracting' bare strings either.
    assert "Downloading" not in statuses
    assert "Extracting" not in statuses


def test_pull_status_transitions_with_counts(monkeypatch):
    _install_fake_pull(monkeypatch, _two_layer_pull_events())
    statuses = []
    sorters.pull_docker_image("spikeinterface/x:latest", on_status=statuses.append)
    # Only emitted when the string changes -> no consecutive duplicates.
    assert all(a != b for a, b in zip(statuses, statuses[1:]))
    # Download phase counts climb as layers finish downloading.
    assert "Downloading 0/2 layers" in statuses
    assert "Downloading 1/2 layers" in statuses
    assert "Downloading 2/2 layers" in statuses
    # Checksum verification shows up.
    assert "Verifying…" in statuses
    # Extract phase counts climb as layers finish extracting.
    assert "Extracting 0/2 layers" in statuses
    assert "Extracting 1/2 layers" in statuses
    assert "Extracting 2/2 layers" in statuses
    # Final phase.
    assert statuses[-1] == "Done"
    # Order: a Downloading… precedes an Extracting… precedes Done.
    first_dl = next(i for i, s in enumerate(statuses) if s.startswith("Downloading"))
    first_ex = next(i for i, s in enumerate(statuses) if s.startswith("Extracting"))
    done_i = statuses.index("Done")
    assert first_dl < first_ex < done_i


def test_pull_progress_reaches_done_equals_total(monkeypatch):
    _install_fake_pull(monkeypatch, _two_layer_pull_events())
    progress = []
    sorters.pull_docker_image("spikeinterface/x:latest",
                              on_progress=lambda d, t, b=True: progress.append((d, t)))
    assert progress, "on_progress must fire"
    done, total = progress[-1]
    assert total > 0
    assert done == total  # the bar lands exactly full at the end


def test_pull_progress_denominator_never_shrinks_in_download_phase(monkeypatch):
    """Completed layers must NOT drop out of the denominator (the old bug).

    Records (status, done, total) interleaved so we can isolate the download
    phase: while the caption is 'Downloading n/N', the denominator must only
    grow as new layers reveal their size (a finished layer keeps its bytes in
    both done and total - the inflated-early-% bug was the denominator shrinking).
    """
    _install_fake_pull(monkeypatch, _two_layer_pull_events())
    events = []  # ('status', text) | ('progress', done, total)
    sorters.pull_docker_image(
        "spikeinterface/x:latest",
        on_progress=lambda d, t, b=True: events.append(("progress", d, t)),
        on_status=lambda s: events.append(("status", s)),
    )
    phase = None
    dl_totals = []
    for e in events:
        if e[0] == "status":
            phase = ("dl" if e[1].startswith("Downloading")
                     else "ex" if e[1].startswith("Extracting") else phase)
        else:
            _, d, t = e
            assert d <= t                       # never inflated past 100%
            if phase == "dl":
                dl_totals.append(t)
    assert dl_totals
    assert dl_totals == sorted(dl_totals)       # download denominator never shrinks
    assert dl_totals[-1] == 400                 # full known size (100 + 300)


def test_pull_extracting_drives_progress_in_extract_phase(monkeypatch):
    """An 'Extracting' event with progressDetail moves the bar mid-extract."""
    _install_fake_pull(monkeypatch, _two_layer_pull_events())
    progress = []
    statuses = []
    sorters.pull_docker_image(
        "spikeinterface/x:latest",
        on_progress=lambda d, t, b=True: progress.append((d, t)),
        on_status=statuses.append,
    )
    # Find where the extract phase begins (first Extracting status).
    ex_start = next(i for i, s in enumerate(statuses) if s.startswith("Extracting"))
    assert ex_start >= 0
    # There must be progress values strictly between 0 and total during extract
    # (i.e. a partial Extracting event moved the bar, not just the boundaries).
    _, total = progress[-1]
    assert any(0 < d < total for d, t in progress)


def test_pull_status_image_up_to_date_finishes_done(monkeypatch):
    """A cached image ('Image is up to date') still reaches Done with no layers,
    and snaps the bar to 100% (not a blank bar) - the real fully-cached re-download
    shape, where Docker streams only 'Pulling from'/'Digest'/'Status:' lines."""
    events = [
        {"status": "Pulling from library/x", "id": "latest"},
        {"status": "Digest: sha256:deadbeef"},
        {"status": "Status: Image is up to date for spikeinterface/x:latest"},
    ]
    _install_fake_pull(monkeypatch, events)
    statuses = []
    progress = []
    ok = sorters.pull_docker_image("spikeinterface/x:latest",
                                   on_progress=lambda d, t, b=True: progress.append((d, t)),
                                   on_status=statuses.append)
    assert ok is True
    assert statuses[-1] == "Done"
    assert progress and progress[-1] == (1, 1)   # bar lands full, never blank at 0


def _all_cached_pull_events():
    """A re-download where every layer is already in Docker's blob cache.

    Deleting a sorter image leaves the underlying layer blobs (SpikeInterface
    images share base layers across sorters), so re-pulling reports each layer as
    'Already exists' with NO byte sizes, then a final up-to-date Status line.
    """
    return [
        {"status": "Already exists", "id": "aaaa"},
        {"status": "Already exists", "id": "bbbb"},
        {"status": "Already exists", "id": "cccc"},
        {"status": "Status: Image is up to date for spikeinterface/x:latest"},
    ]


def test_pull_progress_moves_when_all_layers_cached(monkeypatch):
    """Re-download-after-delete: cached 'Already exists' layers carry no byte
    sizes, so the byte total is 0. The bar must still advance to 100% by completed
    -layer count (not sit blank), and the caption must reflect the layers - the
    'redownload looks broken' bug."""
    _install_fake_pull(monkeypatch, _all_cached_pull_events())
    progress = []
    statuses = []
    ok = sorters.pull_docker_image(
        "spikeinterface/x:latest",
        on_progress=lambda d, t, b=True: progress.append((d, t)),
        on_status=statuses.append,
    )
    assert ok is True
    assert progress, "on_progress must fire even when every layer is cached"
    done, total = progress[-1]
    assert total > 0 and done == total          # bar lands full, never blank at 0
    assert any("3/3 layers" in s for s in statuses)   # caption reflects the layers
    assert statuses[-1] == "Done"


def test_pull_on_summary_reports_pulled_vs_cached(monkeypatch):
    """on_summary tells the caller how many layers actually downloaded vs were
    reused from Docker's cache - so the UI can honestly explain an instant pull."""
    events = [
        {"status": "Pulling fs layer", "id": "a"},
        {"status": "Downloading", "id": "a",
         "progressDetail": {"current": 100, "total": 100}},
        {"status": "Download complete", "id": "a"},
        {"status": "Already exists", "id": "b"},
        {"status": "Already exists", "id": "c"},
        {"status": "Status: Downloaded newer image for spikeinterface/x:latest"},
    ]
    _install_fake_pull(monkeypatch, events)
    summary = {}
    ok = sorters.pull_docker_image(
        "spikeinterface/x:latest",
        on_summary=lambda pulled, cached: summary.update(pulled=pulled, cached=cached))
    assert ok is True
    assert summary == {"pulled": 1, "cached": 2}


def test_pull_on_summary_all_cached(monkeypatch):
    """A fully cached re-pull reports 0 downloaded, N reused."""
    _install_fake_pull(monkeypatch, _all_cached_pull_events())   # 3 'Already exists'
    summary = {}
    sorters.pull_docker_image(
        "spikeinterface/x:latest",
        on_summary=lambda pulled, cached: summary.update(pulled=pulled, cached=cached))
    assert summary == {"pulled": 0, "cached": 3}


def test_delete_docker_image_deep_prunes_and_reports_reclaim(monkeypatch):
    """Deep delete: after removing the image, prune now-dangling layers and report
    the space reclaimed (image size + pruned bytes)."""
    import sorters

    class FakeImg:
        attrs = {"Size": 500_000_000}

    class FakeImages:
        def __init__(self):
            self.removed = []
            self.pruned_filters = None
        def get(self, image): return FakeImg()
        def remove(self, image, force=False): self.removed.append(image)
        def prune(self, filters=None):
            self.pruned_filters = filters
            return {"SpaceReclaimed": 100_000_000}

    imgs = FakeImages()

    class FakeClient:
        images = imgs

    fake_docker = type("D", (), {"from_env": staticmethod(lambda: FakeClient())})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)

    ok, msg = sorters.delete_docker_image("spikeinterface/x:latest")
    assert ok is True
    assert imgs.removed == ["spikeinterface/x:latest"]
    assert imgs.pruned_filters == {"dangling": True}    # safe prune only
    assert "reclaim" in msg.lower()                      # reports space freed


def test_pull_error_event_returns_false(monkeypatch):
    events = [
        {"status": "Pulling fs layer", "id": "aaaa"},
        {"error": "manifest unknown"},
    ]
    _install_fake_pull(monkeypatch, events)
    ok = sorters.pull_docker_image("spikeinterface/x:latest")
    assert ok is False


def test_pull_no_sdk_returns_false(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def _no_docker(name, *a, **k):
        if name == "docker":
            raise ImportError("no docker SDK")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_docker)
    assert sorters.pull_docker_image("spikeinterface/x:latest") is False


def test_pull_mid_stream_exception_returns_false(monkeypatch):
    """A daemon/network failure mid-pull is swallowed -> False, never raised."""
    class FakeApi:
        def pull(self, repository, tag=None, stream=True, decode=True):
            yield {"status": "Pulling fs layer", "id": "aaaa"}
            raise RuntimeError("connection reset")

    class FakeClient:
        api = FakeApi()

    fake_docker = type("D", (), {"from_env": staticmethod(lambda: FakeClient())})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)
    assert sorters.pull_docker_image("spikeinterface/x:latest") is False


def test_pull_docker_image_honours_should_cancel(monkeypatch):
    # A fake docker client whose pull stream yields forever; should_cancel must
    # break the loop and return False without consuming the whole stream.
    import sorters

    class _FakeAPI:
        def pull(self, repository, tag, stream, decode):
            i = 0
            while True:
                i += 1
                yield {"status": "Downloading", "id": f"L{i}",
                       "progressDetail": {"current": i, "total": 1000}}

    class _FakeClient:
        api = _FakeAPI()

    class _FakeDocker:
        @staticmethod
        def from_env():
            return _FakeClient()

    monkeypatch.setitem(__import__("sys").modules, "docker", _FakeDocker)

    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] >= 3        # cancel after a few events

    ok = sorters.pull_docker_image("img:latest", should_cancel=should_cancel)
    assert ok is False
    assert calls["n"] >= 3            # the loop actually polled the hook
