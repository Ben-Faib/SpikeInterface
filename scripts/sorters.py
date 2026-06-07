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


def docker_available(refresh: bool = False) -> bool:
    """True if the ``docker`` CLI is on PATH and the daemon answers.

    Cached per process (the daemon state rarely flips mid-session); pass
    ``refresh=True`` to re-check.
    """
    if not refresh and "ok" in _docker_cache:
        return _docker_cache["ok"]
    ok = False
    if shutil.which("docker"):
        try:
            ok = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=8
            ).returncode == 0
        except Exception:  # noqa: BLE001 - daemon down / timeout -> not available
            ok = False
    _docker_cache["ok"] = ok
    return ok


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
    if use_docker and not docker_available():
        raise RuntimeError(
            "Docker was requested but the Docker daemon isn't reachable. "
            "Start Docker Desktop, or run without Docker."
        )
    return ss.run_sorter(
        name,
        recording,
        folder=str(folder),
        remove_existing_folder=True,
        docker_image=True if use_docker else False,
        sorter_params=params,
        verbose=verbose,
    )


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
