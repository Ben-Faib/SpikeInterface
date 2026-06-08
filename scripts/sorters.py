"""Sorter registry — discovery, availability, parameters, and running.

Single source of truth for which spike sorters this workspace can use. Replaces
the old hardcoded ``SORTERS = ["tridesclous2", "spykingcircus2"]``: it reports
every sorter SpikeInterface knows about, classifies each as runnable locally, via
a Docker container, GPU-only (not runnable here), or unavailable, and runs the
chosen one with optional per-run parameter overrides.

Like ``blackrock_io``, this module imports SpikeInterface lazily (inside the
functions) so importing it stays cheap and the menu stays responsive.

    import sorters
    sorters.installed()              # locally runnable, e.g. ['tridesclous2', ...]
    sorters.runnable(use_docker)     # what the menu offers
    sorters.status("mountainsort5")  # 'local' | 'docker' | 'gpu' | 'unavailable'
    sorters.run(name, recording, folder, params=..., use_docker=...)
"""
from __future__ import annotations

import json
import shutil
import subprocess

# Sorters that need an NVIDIA GPU (and, for the *ks ones, MATLAB). They are shown
# for transparency but never offered as runnable here: this is a Mac with no GPU,
# and Docker-on-Mac has no NVIDIA passthrough.
GPU_SORTERS = frozenset({
    "kilosort", "kilosort2", "kilosort2_5", "kilosort3", "kilosort4",
    "pykilosort", "yass",
})

# CPU-capable sorters with an official SpikeInterface Docker image, so they can be
# run via ``run_sorter(..., docker_image=True)`` without a local install. Curated
# against SpikeInterface's published images (spikeinterface/<name>-base on Docker
# Hub); update this set when SpikeInterface adds/removes images.
CONTAINERIZED = frozenset({
    "combinato", "herdingspikes", "hdsort", "ironclust", "mountainsort4",
    "mountainsort5", "spykingcircus", "spykingcircus2", "tridesclous",
    "tridesclous2", "waveclus",
})

# Preferred default when it is installed; otherwise the first installed sorter.
_PREFERRED_DEFAULT = "tridesclous2"

# The badged ★ default in the menu. Keep consistent with default_sorter().
RECOMMENDED = "tridesclous2"

# One-line, plain-language descriptions shown in the sidebar footer + Help. Covers
# the local sorters, the common container sorters, and the kilosort family; any
# other sorter gets the generic fallback in description().
DESCRIPTIONS = {
    "tridesclous2":   "Fast, reliable, CPU-only. Good default for most recordings.",
    "spykingcircus2": "Template-matching CPU sorter; strong on dense activity.",
    "simple":         "Minimal threshold-based sorter; handy for a quick smoke test.",
    "lupin":          "Lightweight CPU sorter.",
    "mountainsort5":  "Fast density-based clustering; a solid general CPU sorter.",
    "mountainsort4":  "Older MountainSort; superseded by mountainsort5.",
    "herdingspikes":  "Scales to many channels; built for large dense arrays.",
    "spykingcircus":  "Original SpyKING CIRCUS (v1); CPU, template matching.",
    "tridesclous":    "Original Tridesclous (v1); CPU.",
    "waveclus":       "Wavelet + superparamagnetic clustering (MATLAB-based image).",
    "combinato":      "Clustering aimed at human single-unit / long recordings.",
    "hdsort":         "Dense-array sorter (MATLAB-based image).",
    "ironclust":      "Fast density-based sorter (CPU or GPU).",
    "kilosort4":      "State-of-the-art; needs an NVIDIA GPU. Great on Neuropixels.",
    "kilosort3":      "Kilosort 3; needs an NVIDIA GPU.",
    "kilosort2_5":    "Kilosort 2.5; needs an NVIDIA GPU.",
    "kilosort2":      "Kilosort 2; needs an NVIDIA GPU.",
    "kilosort":       "Kilosort 1; needs an NVIDIA GPU + MATLAB.",
    "pykilosort":     "Python Kilosort; needs an NVIDIA GPU.",
    "yass":           "Yet Another Spike Sorter; needs an NVIDIA GPU.",
}


def description(name: str) -> str:
    """One-line plain-language description; generic fallback for unknown sorters."""
    return DESCRIPTIONS.get(name, "A spike-sorting algorithm.")


_docker_cache: dict = {}


def available() -> list[str]:
    """Every sorter SpikeInterface knows about, sorted."""
    import spikeinterface.sorters as ss

    return sorted(ss.available_sorters())


def installed() -> list[str]:
    """Sorters runnable on this machine right now (deps importable), sorted."""
    import spikeinterface.sorters as ss

    return sorted(ss.installed_sorters())


def docker_state(refresh: bool = False) -> str:
    """'running' | 'installed_not_running' | 'not_installed'. Never raises.

    Cached per process (the daemon state rarely flips mid-session); pass
    ``refresh=True`` to re-probe (the Docker confirm dialog does this).
    """
    if not refresh and "state" in _docker_cache:
        return _docker_cache["state"]
    if not shutil.which("docker"):
        state = "not_installed"
    else:
        try:
            ok = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=8
            ).returncode == 0
        except Exception:  # noqa: BLE001 - daemon down / timeout
            ok = False
        state = "running" if ok else "installed_not_running"
    _docker_cache["state"] = state
    return state


def docker_available(refresh: bool = False) -> bool:
    """True iff the Docker daemon is reachable (i.e. docker_state() == 'running')."""
    return docker_state(refresh=refresh) == "running"


def start_docker() -> bool:
    """Best-effort launch of Docker Desktop. Never raises.

    Returns whether a launch command was issued — NOT whether Docker finished
    booting (the caller polls docker_state(refresh=True) until 'running').
    """
    import os
    import sys

    if sys.platform == "darwin":
        cmd = ["open", "-a", "Docker"]
    elif sys.platform.startswith("win"):
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe"),
            os.path.expandvars(r"%LocalAppData%\Docker\Docker Desktop.exe"),
        ]
        exe = next((c for c in candidates if os.path.exists(c)), None)
        cmd = [exe] if exe else ["cmd", "/c", "start", "", "Docker Desktop"]
    else:  # Linux: best effort (Docker Desktop or the daemon)
        cmd = ["systemctl", "--user", "start", "docker-desktop"]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:  # noqa: BLE001 - no known launcher / permission denied
        return False


def default_docker_image(name: str) -> "str | None":
    """The exact image (with tag) SpikeInterface pulls for ``name``, or None.

    Mirrors SpikeInterface's ``SORTER_DOCKER_MAP`` so we can pre-pull *precisely*
    the image the sort will use — the names aren't always ``<name>-base`` (e.g.
    spykingcircus -> spyking-circus-base, waveclus -> waveclus-compiled-base), and
    pre-pulling the wrong name would just double the download.
    """
    try:
        from spikeinterface.sorters.runsorter import SORTER_DOCKER_MAP
    except Exception:  # noqa: BLE001 - SI layout changed / import failure
        return None
    repo = SORTER_DOCKER_MAP.get(name)
    if not repo:
        return None
    last = repo.rsplit("/", 1)[-1]
    return repo if ":" in last else f"{repo}:latest"


def docker_image_present(image: str) -> bool:
    """True iff ``image`` is already in the local Docker image cache. Never raises."""
    try:
        import docker

        docker.from_env().images.get(image)
        return True
    except Exception:  # noqa: BLE001 - missing image / no SDK / daemon down
        return False


def pull_docker_image(image: str, on_progress=None, on_status=None) -> bool:
    """Pull ``image`` via the Docker SDK, streaming progress. Never raises.

    ``on_progress(downloaded_bytes, total_bytes)`` fires as layers download;
    ``on_status(text)`` fires when the high-level step changes (Extracting, …).
    Returns True on success, False on any failure — the caller can then fall back
    to letting SpikeInterface pull the image during the run.
    """
    try:
        import docker
    except Exception:  # noqa: BLE001 - no SDK
        return False
    last = image.rsplit("/", 1)[-1]
    if ":" in last:
        repository, tag = image.rsplit(":", 1)
    else:
        repository, tag = image, "latest"
    try:
        client = docker.from_env()
        downloading: dict = {}      # layer id -> (current, total) while downloading
        last_status = None
        for ev in client.api.pull(repository, tag=tag, stream=True, decode=True):
            if "error" in ev:
                return False
            status_text = ev.get("status") or ""
            lid = ev.get("id")
            det = ev.get("progressDetail") or {}
            if status_text == "Downloading" and lid and "total" in det:
                downloading[lid] = (det.get("current", 0), det.get("total", 0))
                if on_progress:
                    done = sum(c for c, _ in downloading.values())
                    total = sum(t for _, t in downloading.values())
                    on_progress(done, total)
            elif status_text and status_text != last_status:
                last_status = status_text
                if on_status:
                    on_status(status_text)
        return True
    except Exception:  # noqa: BLE001 - daemon / network failure mid-pull
        return False


def status(name: str, installed_set=None, docker=None) -> str:
    """Classify one sorter: 'local' | 'docker' | 'gpu' | 'unavailable'.

    ``installed_set`` / ``docker`` may be passed precomputed (so a table doesn't
    re-query SpikeInterface/Docker once per row); both default to a live lookup.
    """
    inst = installed_set if installed_set is not None else installed()
    if name in inst:
        return "local"
    if name in GPU_SORTERS:
        return "gpu"
    if name in CONTAINERIZED:
        dock = docker if docker is not None else docker_available()
        if dock:
            return "docker"
    return "unavailable"


def group_of(name: str, installed_set=None) -> str:
    """Stable sidebar group for ``name`` by set-membership precedence.

    'ready' (installed → runnable locally) | 'gpu' (NVIDIA GPU family, not
    installed) | 'docker' (has a CPU container image) | 'unavailable'. Unlike
    status(), this does NOT depend on the live Docker daemon, so a sorter never
    jumps groups when Docker Desktop starts/stops — only its *selectability*
    (runnable()) does. Installed wins first, so an installed kilosort on a GPU box
    lands in 'ready'.
    """
    inst = installed_set if installed_set is not None else installed()
    if name in inst:
        return "ready"
    if name in GPU_SORTERS:
        return "gpu"
    if name in CONTAINERIZED:
        return "docker"
    return "unavailable"


def runnable(use_docker: bool) -> list[str]:
    """Sorters the menu should offer: installed first, then (optionally) containers.

    With ``use_docker`` and a live Docker daemon, appends the CPU container sorters
    that aren't already installed (GPU sorters excluded). Deduplicated.
    """
    inst = installed()
    out = list(inst)
    if use_docker and docker_available():
        out += sorted(CONTAINERIZED - GPU_SORTERS - set(inst))
    seen, result = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


def uses_docker(name: str, use_docker: bool, installed_set=None) -> bool:
    """Whether a run of ``name`` will *actually* use a container.

    Docker is only a **fallback** for sorters you don't have locally: an installed
    sorter always runs natively. There is no container image for the local-only
    sorters (e.g. ``tridesclous2`` — pulling ``spikeinterface/tridesclous2-base``
    404s), and containerising one you already have just adds a slow, failure-prone
    round trip. So this is True only when Docker is requested AND ``name`` is not
    installed.
    """
    if not use_docker:
        return False
    inst = installed_set if installed_set is not None else installed()
    return name not in inst


def default_sorter() -> str:
    """Preferred default sorter: tridesclous2 if installed, else first installed."""
    inst = installed()
    if _PREFERRED_DEFAULT in inst:
        return _PREFERRED_DEFAULT
    return inst[0] if inst else _PREFERRED_DEFAULT


def default_params(name: str) -> dict:
    """SpikeInterface's default parameter dict for ``name``."""
    import spikeinterface.sorters as ss

    return ss.get_default_sorter_params(name)


def param_descriptions(name: str) -> dict:
    """Per-parameter human descriptions for ``name`` (may omit some keys)."""
    import spikeinterface.sorters as ss

    return ss.get_sorter_params_description(name)


def coerce_param(default_value, raw: str):
    """Coerce a string value to the type of the sorter default.

    bool accepts true/false/1/0/yes/no/on/off; int/float are parsed; str is passed
    through; None/dict/list/other are parsed as JSON. Raises ``ValueError`` with a
    readable message on failure.
    """
    if isinstance(default_value, bool):
        low = raw.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"expected true/false, got {raw!r}")
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"expected an integer, got {raw!r}")
    if isinstance(default_value, float):
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"expected a number, got {raw!r}")
    if isinstance(default_value, str):
        return raw
    if default_value is None and raw.strip() == "":
        return None        # empty field for a None-default param means "leave unset"
    try:  # None / dict / list / anything else -> JSON
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"expected JSON for this parameter, got {raw!r}: {e}")


def merge_params(name: str, overrides: dict) -> dict:
    """Defaults overlaid with ``overrides``; raise on any unknown key.

    Used both to validate keys before a run and to compute the effective dict.
    """
    defaults = default_params(name)
    unknown = set(overrides) - set(defaults)
    if unknown:
        raise ValueError(
            f"unknown parameter(s) for {name}: {sorted(unknown)}. "
            f"valid keys: {sorted(defaults)}"
        )
    merged = dict(defaults)
    merged.update(overrides)
    return merged


def _as_container_recording(recording, folder):
    """Dump ``recording`` to a binary folder so a container can reconstruct it.

    The official SpikeInterface sorter images often lag the host SI version. A
    native extractor (e.g. the Blackrock recording, whose serialised dict carries
    host-only kwargs like ``gap_tolerance_ms``) then fails to deserialise inside
    the older container. Saving to a plain binary recording first sidesteps the
    skew: the container reloads a version-agnostic ``BinaryFolderRecording``.
    Returns the reloaded recording.
    """
    from pathlib import Path

    bin_folder = Path(folder).parent / "recording_for_docker"
    if bin_folder.exists():
        shutil.rmtree(bin_folder, ignore_errors=True)
    return recording.save(folder=str(bin_folder), format="binary",
                          progress_bar=False, verbose=False)


def run(name, recording, folder, *, params=None, use_docker=False, verbose=False):
    """Run sorter ``name`` on ``recording``, writing to ``folder``.

    ``params`` is an *overrides* dict (validated against the sorter's defaults);
    SpikeInterface fills the rest. ``use_docker`` runs the sorter in its official
    SpikeInterface image and raises if the Docker daemon isn't reachable.
    """
    import spikeinterface.sorters as ss

    params = params or {}
    if params:
        merge_params(name, params)  # validate keys; raises ValueError on unknown
    # Docker is a fallback for sorters you don't have — an installed sorter runs
    # natively even with Docker mode on (else it would chase a nonexistent image).
    use_container = uses_docker(name, use_docker)
    if use_container and not docker_available():
        raise RuntimeError(
            "Docker was requested but the Docker daemon isn't reachable. "
            "Start Docker Desktop, or run without Docker."
        )
    if use_container:
        recording = _as_container_recording(recording, folder)
    # SpikeInterface's run_sorter takes sorter parameters as **kwargs — there is no
    # ``sorter_params=`` keyword (passing one makes it a bogus param named
    # "sorter_params"). Build the call explicitly: the control kwargs
    # (folder/remove/docker) are always ours, while a sorter param that happens to
    # share run_sorter's own name — e.g. herdingspikes' ``verbose`` — overrides our
    # default instead of raising "multiple values for keyword argument". ``params``
    # is already validated against the defaults above.
    call_kwargs = dict(params)
    call_kwargs.setdefault("verbose", verbose)
    call_kwargs["folder"] = str(folder)
    call_kwargs["remove_existing_folder"] = True
    call_kwargs["docker_image"] = use_container
    return ss.run_sorter(name, recording, **call_kwargs)


def _n_params(name: str) -> int:
    try:
        return len(default_params(name))
    except Exception:  # noqa: BLE001 - introspection failure -> 0, never crash a table
        return 0


def status_table() -> list[dict]:
    """One ``{name, status, n_params}`` row per available sorter (for verify/list)."""
    inst = set(installed())
    dock = docker_available()
    return [
        {"name": name, "status": status(name, installed_set=inst, docker=dock),
         "n_params": _n_params(name)}
        for name in available()
    ]
