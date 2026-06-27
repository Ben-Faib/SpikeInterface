"""Probe-geometry registry — the single source of truth for electrode geometry.

Like ``scripts/sorters.py`` this module returns plain Python data and imports the
heavy libraries (``probeinterface``/``numpy``) lazily, so importing it is cheap and
the Textual menu can stay free of probeinterface/SpikeInterface. The Blackrock
files carry no geometry, so geometry is a *user choice*: a library of profiles
(built-in presets + user-editable ones), one of which is "active" at a time.

    import probes
    probes.library()                 # all profiles (built-in + user), ordered
    probes.geometry_features(p)       # {n, layout, min_pitch_um, density_class, klass}
    probes.build(p, n_channels)       # -> probeinterface.Probe (raises on mismatch)
    probes.fit("herdingspikes", p)    # {rank, reason} for a sorter on geometry p
"""
from __future__ import annotations

import json
from pathlib import Path

import blackrock_io as bio

# Active-probe default + the user-profile store (git-ignored, like .si_menu.json).
# The default is THIS recording's real probe (confirmed: channels raw 1–16 = a
# NeuroNexus A1x16-3mm-100-703; analog 1–6 are aux and dropped before sorting).
DEFAULT_PROBE = "nnx-a1x16-3mm-100"
PROBES_PATH = bio.REPO_ROOT / "probes.json"
# Kept as a constant so the placeholder is still addressable by name everywhere.
PLACEHOLDER_PROBE = "independent"

# Density boundaries (µm). dense: real waveform sharing; independent: none.
DENSE_MAX_UM = 60.0
INDEP_MIN_UM = 150.0


def _profile(name, label, kind, params, note=""):
    return {"name": name, "label": label, "kind": kind, "params": params,
            "builtin": True, "note": note}


# Built-in presets (ordered; the real default first, then the placeholder, then
# standards). All parametric so they build offline (the probeinterface catalog
# needs network — see build()). The A1x16-3mm-100-703 IS this recording's probe
# (channels raw 1–16); a 100 µm pitch is the 'sparse' class, so the geometry-aware
# default sorter stays tridesclous2. The single-shank identity mapping (contact i ↔
# raw i) gives the correct 16-site × 100 µm linear geometry; users who want the
# exact NeuroNexus site permutation can add the catalog (library-kind) probe.
BUILTINS = [
    _profile("nnx-a1x16-3mm-100", "NeuroNexus A1x16-3mm-100-703 · 16 ch @ 100 µm",
             "linear", {"n": 16, "pitch_um": 100.0},
             "This recording's probe: NeuroNexus A1x16-3mm-100-703 "
             "(1 shank, 16 sites, 100 µm pitch, ~30 µm contacts) on channels raw 1–16."),
    _profile("independent", "Independent channels (placeholder)", "independent",
             {"pitch_um": 250.0},
             "No real geometry — channels treated as independent (the old default; "
             "use when a recording's probe is unknown)."),
    _profile("linear-16-50um", "Linear · 16 ch @ 50 µm", "linear",
             {"n": 16, "pitch_um": 50.0}, "Single-shank dense linear array."),
    _profile("linear-32-25um", "Linear · 32 ch @ 25 µm", "linear",
             {"n": 32, "pitch_um": 25.0}, "Dense 32-site shank."),
    _profile("tetrode-4", "Tetrodes · 4 × 4 ch", "tetrode",
             {"n_tetrodes": 4, "within_um": 25.0, "between_um": 300.0},
             "Four tetrodes (16 ch)."),
    _profile("grid-8x4-50um", "Grid · 8 × 4 @ 50 µm", "grid",
             {"rows": 8, "cols": 4, "xpitch_um": 50.0, "ypitch_um": 50.0},
             "Generic dense 2-D grid."),
    _profile("utah-10x10-400um", "Utah array · 10 × 10 @ 400 µm", "grid",
             {"rows": 10, "cols": 10, "xpitch_um": 400.0, "ypitch_um": 400.0},
             "Blackrock Utah array — at 400 µm contacts are electrically independent."),
    _profile("cui-flexible-16-300um", "Cui flexible MEA · 16 ch @ 300 µm", "linear",
             {"n": 16, "pitch_um": 300.0},
             "Cui-lab custom flexible polyimide array (effectively independent)."),
    _profile("cui-transparent-4x4-200um", "Cui transparent MEA · 4 × 4 @ 200 µm",
             "grid", {"rows": 4, "cols": 4, "xpitch_um": 200.0, "ypitch_um": 200.0},
             "Cui-lab transparent MEA for ephys + 2-photon."),
]


def builtins() -> list[dict]:
    """The built-in presets (fresh copies so callers can't mutate the constants)."""
    return [dict(p, params=dict(p["params"])) for p in BUILTINS]


# --------------------------------------------------------------------------- #
# User-profile store (probes.json)
# --------------------------------------------------------------------------- #
def _load_store(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("profiles"), list):
            return data
    except Exception:  # noqa: BLE001 - missing/corrupt -> empty
        pass
    return {"profiles": []}


def _save_store(store, path) -> None:
    try:
        Path(path).write_text(json.dumps(store, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - best-effort
        pass


def user_profiles(path=PROBES_PATH) -> list[dict]:
    """User-created/edited profiles from probes.json (each flagged builtin=False)."""
    out = []
    for p in _load_store(path)["profiles"]:
        if isinstance(p, dict) and p.get("name"):
            out.append(dict(p, builtin=False))
    return out


def library(path=PROBES_PATH) -> list[dict]:
    """Built-ins then user profiles, deduped by name (a built-in name wins)."""
    seen = set()
    out = []
    for p in builtins() + user_profiles(path):
        if p["name"] in seen:
            continue
        seen.add(p["name"])
        out.append(p)
    return out


def get(name, path=PROBES_PATH) -> "dict | None":
    return next((p for p in library(path) if p["name"] == name), None)


def _is_builtin(name) -> bool:
    return any(p["name"] == name for p in BUILTINS)


def save_profile(profile, path=PROBES_PATH) -> None:
    """Upsert a user profile into probes.json (built-in names are stored as user
    copies — callers should rename a built-in before saving; see duplicate())."""
    store = _load_store(path)
    rec = {"name": profile["name"], "label": profile.get("label", profile["name"]),
           "kind": profile["kind"], "params": dict(profile.get("params", {})),
           "builtin": False, "note": profile.get("note", "")}
    profiles = [p for p in store["profiles"] if p.get("name") != rec["name"]]
    profiles.append(rec)
    store["profiles"] = profiles
    _save_store(store, path)


def delete_profile(name, path=PROBES_PATH) -> "tuple[bool, str]":
    if _is_builtin(name):
        return False, f"{name} is a built-in profile and can't be deleted (duplicate it to edit)."
    store = _load_store(path)
    before = len(store["profiles"])
    store["profiles"] = [p for p in store["profiles"] if p.get("name") != name]
    if len(store["profiles"]) == before:
        return False, f"No saved probe named {name}."
    _save_store(store, path)
    return True, f"Deleted probe {name}."


def duplicate(name, new_name, new_label=None, path=PROBES_PATH) -> dict:
    """Copy a profile (built-in or user) to a new editable user profile."""
    src = get(name, path) or get(DEFAULT_PROBE)
    dup = {"name": new_name, "label": new_label or f"{src['label']} (copy)",
           "kind": src["kind"], "params": dict(src["params"]),
           "builtin": False, "note": src.get("note", "")}
    save_profile(dup, path)
    return dup


# --------------------------------------------------------------------------- #
# Geometry introspection (analytic for parametric kinds; no probeinterface)
# --------------------------------------------------------------------------- #
def auto_sizes(profile) -> bool:
    """True iff the profile resizes to the recording (only ``independent``)."""
    if not isinstance(profile, dict):
        return False
    return profile.get("kind") == "independent"


def contact_count(profile) -> "int | None":
    """Fixed contact count for parametric kinds; None for auto/unknown kinds."""
    if not isinstance(profile, dict):
        return None
    k, p = profile.get("kind"), profile.get("params", {})
    if k == "linear":
        return int(p.get("n", 0))
    if k == "grid":
        return int(p.get("rows", 0)) * int(p.get("cols", 0))
    if k == "tetrode":
        return int(p.get("n_tetrodes", 0)) * 4
    return None  # independent (auto), library/file (unknown until built)


def density_class(min_pitch_um) -> str:
    if min_pitch_um is None:
        return "sparse"
    if min_pitch_um <= DENSE_MAX_UM:
        return "dense"
    if min_pitch_um >= INDEP_MIN_UM:
        return "independent"
    return "sparse"


def geometry_features(profile) -> dict:
    """{n, layout, min_pitch_um, density_class, klass}. Analytic for parametric
    kinds; library/file return a neutral 'unknown' feature set (no network)."""
    if not isinstance(profile, dict):
        return {"n": None, "layout": "unknown", "min_pitch_um": None,
                "density_class": "sparse", "klass": "sparse"}
    k, p = profile.get("kind"), profile.get("params", {})
    if k == "independent":
        pitch = float(p.get("pitch_um", 250.0))
        return {"n": None, "layout": "independent", "min_pitch_um": pitch,
                "density_class": density_class(pitch), "klass": "independent"}
    if k == "linear":
        pitch = float(p.get("pitch_um", 50.0))
        return {"n": int(p.get("n", 0)), "layout": "linear", "min_pitch_um": pitch,
                "density_class": density_class(pitch), "klass": density_class(pitch)}
    if k == "grid":
        pitch = min(float(p.get("xpitch_um", 50.0)), float(p.get("ypitch_um", 50.0)))
        return {"n": contact_count(profile), "layout": "grid2d", "min_pitch_um": pitch,
                "density_class": density_class(pitch), "klass": density_class(pitch)}
    if k == "tetrode":
        within = float(p.get("within_um", 25.0))
        return {"n": contact_count(profile), "layout": "tetrode", "min_pitch_um": within,
                "density_class": density_class(within), "klass": "tetrode"}
    # library / file: unknown without building -> neutral sparse class.
    return {"n": None, "layout": "unknown", "min_pitch_um": None,
            "density_class": "sparse", "klass": "sparse"}


def summary(profile) -> str:
    """Human one-liner: '16 contacts · linear · 50 µm pitch'. Never raises."""
    if not isinstance(profile, dict):
        return "no probe"
    f = geometry_features(profile)
    n = f["n"]
    layout = {"independent": "independent channels", "linear": "linear",
              "grid2d": "2-D grid", "tetrode": "tetrodes",
              "unknown": profile.get("kind", "probe")}[f["layout"]]
    bits = []
    if profile.get("kind") == "independent":
        bits.append("auto-sizes to the recording")
    elif n:
        bits.append(f"{n} contacts")
    bits.append(layout)
    if f["min_pitch_um"]:
        bits.append(f"{f['min_pitch_um']:g} µm pitch")
    return " · ".join(bits)


# --------------------------------------------------------------------------- #
# Construction (lazy probeinterface / numpy)
# --------------------------------------------------------------------------- #
def _require_count(profile, n_channels) -> None:
    want = contact_count(profile)
    if want is not None and want != n_channels:
        raise ValueError(
            f"Probe '{profile['name']}' has {want} contacts but the recording has "
            f"{n_channels} channels. Pick a matching probe (or 'independent', which "
            "auto-sizes), or edit this probe's contact count.")


def build(profile, n_channels):
    """Build a probeinterface.Probe for ``profile`` sized to ``n_channels``.

    Sets identity device-channel indices (contact i ↔ channel i), matching the old
    attach_dummy_probe. Raises ValueError on a fixed-count mismatch.
    """
    import numpy as np
    import probeinterface as pi

    _require_count(profile, n_channels)
    k, p = profile["kind"], profile.get("params", {})

    if k in ("independent", "linear"):
        pitch = float(p.get("pitch_um", 250.0 if k == "independent" else 50.0))
        n = n_channels if k == "independent" else int(p["n"])
        probe = pi.generate_linear_probe(num_elec=n, ypitch=pitch)
    elif k == "grid":
        probe = pi.generate_multi_columns_probe(
            num_columns=int(p["cols"]), num_contact_per_column=int(p["rows"]),
            xpitch=float(p["xpitch_um"]), ypitch=float(p["ypitch_um"]))
    elif k == "tetrode":
        within, between = float(p["within_um"]), float(p["between_um"])
        offs = np.array([[0, 0], [within, 0], [0, within], [within, within]], dtype=float)
        pos = np.vstack([offs + [t * between, 0.0] for t in range(int(p["n_tetrodes"]))])
        probe = pi.Probe(ndim=2)
        probe.set_contacts(positions=pos, shapes="circle", shape_params={"radius": 5})
        probe.create_auto_shape("tip")
    elif k == "library":
        probe = pi.get_probe(p["manufacturer"], p["model"])
    elif k == "file":
        group = pi.read_probeinterface(p["path"])
        probe = group.probes[0]
    else:
        raise ValueError(f"Unknown probe kind: {k!r}")

    # library/file can carry their own count; validate now that it's known.
    if probe.get_contact_count() != n_channels:
        raise ValueError(
            f"Probe '{profile['name']}' built {probe.get_contact_count()} contacts "
            f"but the recording has {n_channels} channels.")
    probe.set_device_channel_indices(np.arange(n_channels))
    return probe


def catalog_manufacturers() -> list[str]:
    """probeinterface library manufacturers (network); [] on any failure."""
    try:
        from probeinterface.library import probe_dict  # type: ignore
        return sorted(probe_dict().keys())
    except Exception:  # noqa: BLE001 - older/newer layout or offline
        return ["neuronexus", "cambridgeneurotech"]


def catalog_models(manufacturer) -> list[str]:
    try:
        from probeinterface.library import probe_dict  # type: ignore
        return sorted(probe_dict().get(manufacturer, {}).keys())
    except Exception:  # noqa: BLE001
        return []
