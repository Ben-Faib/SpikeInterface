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
    probes.import_probe_file("my.json")  # probeinterface .json/.prb -> the library

CLI (import a probe the lab already has a standard description for):

    uv run python scripts/probes.py import my_probe.json [--name NAME] [--label L]
    uv run python scripts/probes.py import my_probe.prb --data-dir /path/to/recording
    uv run python scripts/probes.py list

``import`` reads a probeinterface ``.json`` (or ``.prb``) ONCE and materialises
the geometry — contact positions, min pitch, layout, wiring — into a
self-contained ``imported`` profile in ``probes.json``, so the library never
depends on the source file again. It then checks the contact count against the
recording's neural channel count and reports honestly (a mismatch is a loud
warning at import — the library may serve other recordings — and stays a hard
error at sort time: ``run_sorting.py --probe <name>`` refuses a count mismatch).
Wiring: a full-permutation ``device_channel_indices`` in the file is preserved
and applied; absent wiring means the identity mapping (contact i ↔ channel i);
partial wiring (unconnected ``-1`` contacts) is refused until P3's wiring
surfaces land. Multi-probe files (ProbeGroups) are refused until P2.

Known limits (on record for P2/P3): ``run_sorting.py --probe-file`` (the
one-off ``file`` kind) still applies identity wiring unconditionally — use the
import CLI for a probe that carries wiring. Imported geometry is density-classed
by min contact pitch only, so a tetrode-style import ranks as a dense array
rather than tetrodes (soft re-rank only; it never blocks a sort).
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
    # An 'imported' profile's geometry is materialised at import time and can't be
    # re-derived: a generic upsert that omits it (e.g. a name/label-only edit
    # surface) must not strip it — carry the stored geometry (and provenance note)
    # forward, and refuse outright when there is nothing to carry (a rename that
    # orphans the geometry must fail loud, not save a broken probe).
    if rec["kind"] == "imported" and not rec["params"].get("positions"):
        prev = next((p for p in store["profiles"] if p.get("name") == rec["name"]), None)
        prev_params = (prev or {}).get("params", {})
        if not prev_params.get("positions"):
            raise ValueError(
                f"Refusing to save imported probe '{rec['name']}' without its geometry — "
                "re-import it from the source file instead (probes.py import).")
        rec["params"] = {**prev_params, **rec["params"]}
        if not rec["note"]:
            rec["note"] = (prev or {}).get("note", "")
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
# Import (probeinterface .json / .prb -> a self-contained 'imported' profile)
# --------------------------------------------------------------------------- #
def _sanitize_name(stem) -> str:
    out = "".join(c if c.isalnum() else "-" for c in str(stem).lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def import_probe_file(src, name=None, label=None, path=PROBES_PATH) -> dict:
    """Import a probeinterface description into the user probe library.

    Reads ``src`` (probeinterface ``.json``, or ``.prb``) once and materialises
    the geometry into a self-contained ``imported`` profile: contact positions,
    min pitch, layout class, contact radius, and — when the file carries a full
    permutation — the channel wiring. Saves to ``path`` and returns the stored
    profile. Raises ``ValueError`` naming the exact problem on anything
    unsupported (multi-probe files, 3-D geometry, partial wiring, name
    collisions, unreadable files); nothing is written on failure.
    """
    import numpy as np
    import probeinterface as pi

    src = Path(src)
    if not src.exists():
        raise ValueError(f"No such file: {src}")
    suffix = src.suffix.lower()
    if suffix == ".json":
        fmt = "probeinterface"
        try:
            group = pi.read_probeinterface(src)
        except Exception as e:  # noqa: BLE001 - malformed file -> honest error
            raise ValueError(f"{src.name} is not a readable probeinterface .json: {e}") from e
    elif suffix == ".prb":
        fmt = "prb"
        try:
            group = pi.io.read_prb(src)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"{src.name} is not a readable .prb file: {e}") from e
    else:
        raise ValueError(
            f"Unsupported probe file type '{src.suffix}' — supported: "
            ".json (probeinterface), .prb")

    n_probes = len(group.probes)
    if n_probes == 0:
        raise ValueError(f"{src.name} contains no probes.")
    if n_probes > 1:
        raise ValueError(
            f"{src.name} carries {n_probes} probes (a ProbeGroup) — multi-probe import "
            "lands with multi-shank support (P2); export a single probe for now.")
    probe = group.probes[0]
    if getattr(probe, "ndim", 2) != 2:
        raise ValueError(f"{src.name}: {probe.ndim}-D probe geometry isn't supported (2-D only).")
    pos = np.asarray(probe.contact_positions, dtype=float)
    n = int(pos.shape[0])
    if n == 0:
        raise ValueError(f"{src.name}: the probe has no contacts.")

    # Wiring: honour a full permutation, refuse partial wiring, default identity.
    wiring = None
    dci = probe.device_channel_indices
    if dci is not None:
        dci = np.asarray(dci)
        if len(dci) != n:
            raise ValueError(
                f"{src.name}: device_channel_indices has {len(dci)} entries for {n} contacts.")
        if (dci < 0).any():
            raise ValueError(
                f"{src.name}: some contacts are unconnected (device index -1) — partial "
                "wiring isn't supported yet (wiring surfaces land in P3); connect every "
                "contact or strip the wiring from the file.")
        if sorted(int(i) for i in dci) != list(range(n)):
            raise ValueError(
                f"{src.name}: device_channel_indices isn't a permutation of 0..{n - 1} — "
                "the contacts can't be mapped to channels honestly. Renumber the wiring "
                "to 0-based consecutive channels, or strip it to use the identity mapping.")
        if not np.array_equal(dci, np.arange(n)):
            wiring = [int(i) for i in dci]

    if n == 1:
        min_pitch = None
    else:
        d2 = ((pos[:, None, :] - pos[None, :, :]) ** 2).sum(-1)
        np.fill_diagonal(d2, np.inf)
        min_pitch = float(np.sqrt(d2.min()))
        if min_pitch == 0.0:
            raise ValueError(f"{src.name}: two contacts share the same position.")
    centered = pos - pos.mean(axis=0)
    layout = "linear" if n == 1 or np.linalg.matrix_rank(centered, tol=1e-3) < 2 else "grid2d"

    radius = 5.0
    try:  # uniform circular contacts keep their real radius; anything else -> default
        shapes = list(probe.contact_shapes)
        params = list(probe.contact_shape_params)
        radii = {float(sp["radius"]) for s, sp in zip(shapes, params) if s == "circle"}
        if len(shapes) == n and all(s == "circle" for s in shapes) and len(radii) == 1:
            radius = radii.pop()
    except Exception:  # noqa: BLE001 - shape metadata is optional
        pass

    name = name or _sanitize_name(src.stem)
    if not name:
        raise ValueError(f"Couldn't derive a probe name from '{src.name}' — pass --name.")
    if _is_builtin(name):
        raise ValueError(
            f"'{name}' is a built-in profile name — pass --name to import under a "
            "different name.")
    if any(u["name"] == name for u in user_profiles(path)):
        raise ValueError(
            f"A probe named '{name}' already exists in the library — pass --name, or "
            "delete the existing one first.")

    from datetime import date
    wiring_note = "from file" if wiring else "identity (contact i ↔ channel i)"
    params_out = {"positions": [[float(x), float(y)] for x, y in pos],
                  "min_pitch_um": min_pitch, "layout": layout, "radius_um": radius,
                  "source": src.name, "format": fmt}
    if wiring:
        params_out["device_channel_indices"] = wiring
    profile = {"name": name,
               "label": label or f"{src.stem} · {n} ch (imported)",
               "kind": "imported", "params": params_out, "builtin": False,
               "note": f"Imported from {src.name} ({fmt}), {date.today().isoformat()}. "
                       f"Wiring: {wiring_note}."}
    save_profile(profile, path=path)
    stored = get(name, path=path)
    if stored is None:   # the store swallows write errors — success must mean written
        raise ValueError(f"Couldn't write the probe library at {path} — is it writable?")
    return stored


def recording_neural_count(data_dir=None) -> int:
    """Neural (non-aux) channel count of the recording — for import validation.

    Loads broadband headers lazily; propagates the loader's honest
    ``FileNotFoundError`` when there is no recording to check against.
    """
    rec = bio.read_broadband(data_dir, attach_probe=False)
    return len(bio.neural_channel_ids(rec))


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
    if k == "imported":
        return len(p.get("positions", [])) or None
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
    if k == "imported":
        # Geometry was materialised at import time, so this stays analytic (no
        # probeinterface/numpy) and the menu's cheap-import property holds.
        pitch = p.get("min_pitch_um")
        pitch = float(pitch) if pitch else None
        dc = density_class(pitch)
        layout = p.get("layout") if p.get("layout") in ("linear", "grid2d") else "unknown"
        return {"n": contact_count(profile), "layout": layout,
                "min_pitch_um": pitch, "density_class": dc, "klass": dc}
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
    elif k == "imported":
        pos = np.asarray(p.get("positions", []), dtype=float)
        if pos.size == 0 or pos.ndim != 2 or pos.shape[1] != 2:
            raise ValueError(
                f"Probe '{profile['name']}' has no stored geometry — re-import it "
                "from the source file (probes.py import).")
        probe = pi.Probe(ndim=2)
        probe.set_contacts(positions=pos, shapes="circle",
                           shape_params={"radius": float(p.get("radius_um", 5.0))})
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
    # Imported profiles may carry the file's wiring (a validated permutation);
    # everything else keeps the identity mapping (contact i ↔ channel i).
    wiring = profile.get("params", {}).get("device_channel_indices") if k == "imported" else None
    probe.set_device_channel_indices(
        np.asarray(wiring, dtype=int) if wiring else np.arange(n_channels))
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


# --------------------------------------------------------------------------- #
# Sorter fit (geometry -> which sorters suit it). Backs the soft re-rank.
# Classes: independent | tetrode | sparse | dense (see the design's fit table).
# --------------------------------------------------------------------------- #
_RANKS = {"good": 0, "ok": 1, "poor": 2}
_DEFAULT_FIT = {"independent": "ok", "tetrode": "ok", "sparse": "ok", "dense": "ok"}
_FIT = {
    "tridesclous2":   {"independent": "good", "tetrode": "good", "sparse": "good", "dense": "ok"},
    "tridesclous":    {"independent": "good", "tetrode": "good", "sparse": "ok",   "dense": "ok"},
    "mountainsort4":  {"independent": "good", "tetrode": "good", "sparse": "good", "dense": "ok"},
    "mountainsort5":  {"independent": "ok",   "tetrode": "ok",   "sparse": "good", "dense": "good"},
    "spykingcircus2": {"independent": "ok",   "tetrode": "ok",   "sparse": "good", "dense": "good"},
    "spykingcircus":  {"independent": "ok",   "tetrode": "ok",   "sparse": "ok",   "dense": "ok"},
    "waveclus":       {"independent": "good", "tetrode": "good", "sparse": "ok",   "dense": "poor"},
    "combinato":      {"independent": "good", "tetrode": "good", "sparse": "ok",   "dense": "poor"},
    "herdingspikes":  {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "ironclust":      {"independent": "poor", "tetrode": "poor", "sparse": "ok",   "dense": "good"},
    "hdsort":         {"independent": "poor", "tetrode": "poor", "sparse": "ok",   "dense": "good"},
    "kilosort4":      {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "kilosort3":      {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "kilosort2_5":    {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "kilosort2":      {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "kilosort":       {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "pykilosort":     {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
    "yass":           {"independent": "poor", "tetrode": "poor", "sparse": "poor", "dense": "good"},
}
_FIT_NOTE = {
    "tridesclous2": "general-purpose, robust at low channel counts",
    "tridesclous": "tetrode-oriented legacy sorter",
    "mountainsort4": "isolation clustering, best at low channel counts",
    "mountainsort5": "density clustering, scales to many channels",
    "spykingcircus2": "template matching, strong on dense arrays",
    "spykingcircus": "legacy template matching",
    "waveclus": "wavelet clustering for single channels / tetrodes",
    "combinato": "single-unit clustering for sparse / long recordings",
    "herdingspikes": "needs dense neighbours (poor above ~60 µm)",
    "ironclust": "density-based, built for high-density arrays",
    "hdsort": "dense-array sorter",
    "kilosort4": "template matching, built for dense probes (≤~40 µm)",
}
_KLASS_LABEL = {"independent": "independent channels", "tetrode": "tetrodes",
                "sparse": "low-density geometry", "dense": "high-density arrays"}


def fit(name, profile) -> dict:
    """{rank, reason} for sorter ``name`` on geometry ``profile``."""
    klass = geometry_features(profile)["klass"]
    rank = _FIT.get(name, _DEFAULT_FIT)[klass]
    note = _FIT_NOTE.get(name, "")
    label = _KLASS_LABEL[klass]
    if note:
        reason = f"{note}; {rank} fit for {label}."
    else:
        reason = f"{rank} fit for {label}."
    return {"rank": rank, "reason": reason[0].upper() + reason[1:]}


def ranked(names, profile) -> list[dict]:
    """Sorters annotated with fit, stable-sorted good→ok→poor (input order breaks ties)."""
    rows = [dict(name=n, **fit(n, profile)) for n in names]
    return sorted(rows, key=lambda r: _RANKS[r["rank"]])


def recommended_for(profile, runnable_names, prefer=None) -> "str | None":
    """Top good-fit runnable sorter for ``profile``; None if none rank 'good'.

    ``prefer`` (e.g. ``sorters.RECOMMENDED``) wins when it is runnable AND a good
    fit, so the established default is kept whenever geometry doesn't argue against
    it (e.g. the 100 µm 'sparse' A1x16 keeps tridesclous2)."""
    names = list(runnable_names)
    if prefer in names and fit(prefer, profile)["rank"] == "good":
        return prefer
    for r in ranked(names, profile):
        if r["rank"] == "good":
            return r["name"]
    return None


# --------------------------------------------------------------------------- #
# CLI (import / list) — see the module docstring for usage
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    import argparse
    import sys

    bio.use_utf8_stdout()
    ap = argparse.ArgumentParser(
        prog="probes.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="import a probeinterface .json / .prb into the probe library")
    imp.add_argument("file", help="probe description file (.json probeinterface, or .prb)")
    imp.add_argument("--name", default=None, help="library name for the probe (default: from the file name)")
    imp.add_argument("--label", default=None, help="human label shown in the UI")
    imp.add_argument("--data-dir", default=None,
                     help="recording folder for the channel-count check (default: auto-discover)")
    imp.add_argument("--library", default=None, help=argparse.SUPPRESS)  # tests: alternate probes.json
    ls = sub.add_parser("list", help="list the probe library (built-ins + imported/user probes)")
    ls.add_argument("--library", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    store = Path(args.library) if args.library else PROBES_PATH

    if args.cmd == "list":
        for p in library(path=store):
            origin = "built-in" if p["builtin"] else p["kind"]
            print(f"{p['name']:<28} {summary(p):<44} [{origin}]")
        return 0

    try:
        prof = import_probe_file(args.file, name=args.name, label=args.label, path=store)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    wiring = ("from file" if prof["params"].get("device_channel_indices")
              else "identity (contact i ↔ channel i)")
    print(f"✓ imported '{prof['name']}' — {summary(prof)}")
    print(f"  wiring: {wiring}")
    print(f"  sort with it: uv run python scripts/run_sorting.py --probe {prof['name']}")
    # Honest channel-count verdict against the recording. A mismatch is a loud
    # warning here (the library may serve other recordings) and stays a hard
    # error at sort time — the explicit-probe-fails-hard asymmetry.
    try:
        n_rec = recording_neural_count(args.data_dir)
    except FileNotFoundError as e:
        print(f"  channel check skipped — {e}")
        return 0
    except Exception as e:  # noqa: BLE001 - unreadable recording -> honest skip
        print(f"  channel check skipped — couldn't read the recording: {e}")
        return 0
    want = contact_count(prof)
    if want == n_rec:
        print(f"  ✓ matches the recording: {n_rec} neural channels")
    else:
        print(f"  ⚠ MISMATCH: probe has {want} contacts but the recording has {n_rec} "
              f"neural channels — sorting with --probe {prof['name']} will fail "
              "until the counts match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
