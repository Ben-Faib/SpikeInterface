"""Every user-editable setting: one schema, one validator, one mapping to the sort.

Single source of truth for **what a researcher can change and what it does**. The
menu's Settings screen lists these rows, the controller validates and persists
edits through here, and every sort started from Spike gets its flags from
``sort_flags`` - so a value shown on screen is exactly the value the next sort
uses, and ``run_info.json`` records what that sort actually ran with.

    import settings
    settings.rows(cfg)                    # every setting, grouped, as plain data
    settings.set_value(cfg, "freq_min", "250")   # -> (ok, message); mutates cfg
    settings.reset(cfg, "freq_min")
    settings.sort_flags(cfg)              # ["--freq-min", "300.0", ...]
    settings.quick_seconds(cfg)

Storage is the menu's local ``.si_menu.json`` dict (``cfg``): the signal and sorter
knobs live under ``sort_settings``, the quality rule under ``quality_rule`` (the
key ``sort_summary.load_quality_rule`` reads), the data folder under ``data_dir``.
Settings whose editor is a whole screen of its own (the active probe, the sorter
and its parameters, Docker, the colour theme) appear as ``link`` rows: the row
shows the current value and names the screen that edits it, so nothing is
editable in two places.

Pure: json-level data only, no SpikeInterface, no Textual.
"""
from __future__ import annotations

import os

import run_sorting  # the pipeline owns its own method list and defaults
import sort_summary

SORT_KEY = "sort_settings"
RULE_KEY = "quality_rule"

# Groups in screen order. Each row: key, group, label, kind, default, help (what it
# affects, in a researcher's words), plus kind-specific bounds/choices.
_SIGNAL = "Signal before sorting"
_SORTER = "Sorting"
_RULE = "Quality rule (what counts as a strong unit)"
GROUPS = ("Recording", "Probe", _SIGNAL, _SORTER, _RULE, "Appearance")

SCHEMA = [
    {"key": "data_dir", "group": "Recording", "label": "Data folder", "kind": "path",
     "default": None, "store": "data_dir",
     "help": "where the .ns5 / .ns2 / .nev set is read from; remembered next launch"},
    {"key": "active_probe", "group": "Probe", "label": "Active probe", "kind": "link",
     "link": "probe", "help": "the electrode geometry every sort uses - edit it on 2 Probe"},

    {"key": "freq_min", "group": _SIGNAL, "label": "Band-pass low (Hz)", "kind": "float",
     "default": 300.0, "min": 1.0, "max": 5000.0, "flag": "--freq-min",
     "help": "slow signal below this is removed before sorting (LFP, drift)"},
    {"key": "freq_max", "group": _SIGNAL, "label": "Band-pass high (Hz)", "kind": "float",
     "default": 6000.0, "min": 500.0, "max": 14000.0, "flag": "--freq-max",
     "help": "fast noise above this is removed before sorting"},
    {"key": "bad_channel_detection", "group": _SIGNAL, "label": "Find bad channels",
     "kind": "bool", "default": True,
     "help": "detected bad channels leave the reference and the sort"},
    {"key": "bad_channel_method", "group": _SIGNAL, "label": "Bad-channel method",
     "kind": "choice", "default": run_sorting.DEFAULT_BAD_CHANNEL_METHOD,
     "choices": list(run_sorting.BAD_CHANNEL_METHODS), "flag": "--bad-channel-method",
     "help": "how bad channels are found (mad suits this probe)"},
    {"key": "bad_channels", "group": _SIGNAL, "label": "Always exclude channels",
     "kind": "channels", "default": "", "flag": "--bad-channels",
     "help": "channel ids you know are bad, e.g. 3,7 - excluded on top of detection"},
    {"key": "keep_analog", "group": _SIGNAL, "label": "Keep aux channels", "kind": "bool",
     "default": False,
     "help": "off: the 'analog N' sync/aux inputs are dropped (they poison the reference)"},

    {"key": "active_sorter", "group": _SORTER, "label": "Sorter", "kind": "link",
     "link": "sorter", "help": "which algorithm finds the units - choose it on 3 Sort"},
    {"key": "sorter_params", "group": _SORTER, "label": "Sorter parameters", "kind": "link",
     "link": "params", "help": "the active sorter's own knobs (thresholds, radii ...)"},
    {"key": "quick_seconds", "group": _SORTER, "label": "Quick-test length (s)",
     "kind": "int", "default": 30, "min": 5, "max": 600,
     "help": "how much of the recording a quick test sorts; it never becomes current"},
    {"key": "n_jobs", "group": _SORTER, "label": "CPU workers", "kind": "int",
     "default": 1, "min": 1, "max": max(1, os.cpu_count() or 1), "flag": "--n-jobs",
     "help": "parallel workers for the sort and metrics; 1 is the safest"},
    {"key": "use_docker", "group": _SORTER, "label": "Docker sorters", "kind": "link",
     "link": "docker", "help": "run sorters this computer lacks inside Docker"},

    *[{"key": k, "group": _RULE, "label": sort_summary.RULE_SETTING_LABELS[k],
       "kind": "float", "default": v, "min": 0.0,
       "max": 1.0 if k in ("presence_ratio_min", "amplitude_cutoff_max") else 1000.0,
       "store": RULE_KEY,
       "help": "re-judges every sort's units on every surface; the sort itself is unchanged"}
      for k, v in sort_summary.DEFAULT_QUALITY_RULE.items()],

    {"key": "theme", "group": "Appearance", "label": "Accent colour", "kind": "link",
     "link": "theme", "help": "the menu's accent colour"},
]
_BY_KEY = {s["key"]: s for s in SCHEMA}


def spec(key: str) -> dict:
    return _BY_KEY[key]


def _store(cfg: dict, s: dict) -> dict:
    """The dict a setting's value lives in (created on write, never on read)."""
    where = s.get("store", SORT_KEY)
    if where == "data_dir":
        return cfg
    box = cfg.get(where)
    return box if isinstance(box, dict) else {}


def get(cfg: dict, key: str):
    """The effective value: the saved one when valid, else the default."""
    s = _BY_KEY[key]
    if s["kind"] == "link":
        return None
    box = _store(cfg, s)
    name = "data_dir" if s.get("store") == "data_dir" else key
    if name not in box:
        return s["default"]
    ok, value, _msg = _parse(s, box[name])
    return value if ok else s["default"]


def is_default(cfg: dict, key: str) -> bool:
    return get(cfg, key) == _BY_KEY[key]["default"]


def _parse(s: dict, raw):
    """(ok, value, message) - the one validator every edit goes through."""
    kind = s["kind"]
    if kind == "bool":
        if isinstance(raw, bool):
            return True, raw, ""
        text = str(raw).strip().lower()
        if text in ("on", "true", "yes", "1"):
            return True, True, ""
        if text in ("off", "false", "no", "0"):
            return True, False, ""
        return False, None, "type on or off"
    if kind in ("int", "float"):
        try:
            value = float(str(raw).strip())
        except ValueError:
            return False, None, f"{s['label']} must be a number"
        if kind == "int":
            if value != int(value):
                return False, None, f"{s['label']} must be a whole number"
            value = int(value)
        lo, hi = s.get("min"), s.get("max")
        if lo is not None and value < lo or hi is not None and value > hi:
            return False, None, f"{s['label']} must be between {lo:g} and {hi:g}"
        return True, value, ""
    if kind == "choice":
        text = str(raw).strip()
        if text not in s["choices"]:
            return False, None, "choose one of " + ", ".join(s["choices"])
        return True, text, ""
    if kind == "channels":
        text = str(raw or "").replace(" ", "")
        parts = [p for p in text.split(",") if p]
        if any(not p.replace("_", "").isalnum() for p in parts):
            return False, None, "list channel ids separated by commas, e.g. 3,7"
        return True, ",".join(parts), ""
    if kind == "path":
        text = str(raw or "").strip()
        return True, (os.path.expanduser(text) if text else None), ""
    return False, None, f"{s['label']} is edited on its own screen"


def set_value(cfg: dict, key: str, raw) -> "tuple[bool, str]":
    """Validate ``raw`` and store it in ``cfg`` (the caller persists cfg)."""
    s = _BY_KEY.get(key)
    if s is None:
        return False, f"unknown setting {key}"
    ok, value, msg = _parse(s, raw)
    if not ok:
        return False, msg
    if key == "freq_min" and value >= get(cfg, "freq_max"):
        return False, f"band-pass low must be below the high edge ({get(cfg, 'freq_max'):g} Hz)"
    if key == "freq_max" and value <= get(cfg, "freq_min"):
        return False, f"band-pass high must be above the low edge ({get(cfg, 'freq_min'):g} Hz)"
    if s.get("store") == "data_dir":
        cfg["data_dir"] = value
    else:
        where = s.get("store", SORT_KEY)
        if not isinstance(cfg.get(where), dict):
            cfg[where] = {}
        cfg[where][key] = value
    return True, f"{s['label']} → {display(cfg, key)}"


def reset(cfg: dict, key: str) -> "tuple[bool, str]":
    s = _BY_KEY.get(key)
    if s is None or s["kind"] == "link":
        return False, "nothing to reset here"
    if s.get("store") == "data_dir":
        cfg.pop("data_dir", None)
    else:
        box = cfg.get(s.get("store", SORT_KEY))
        if isinstance(box, dict):
            box.pop(key, None)
    return True, f"{s['label']} back to its default ({display(cfg, key)})"


def display(cfg: dict, key: str, value=None) -> str:
    s = _BY_KEY[key]
    value = get(cfg, key) if value is None and s["kind"] != "link" else value
    kind = s["kind"]
    if kind == "bool":
        return "on" if value else "off"
    if kind == "float":
        return f"{value:g}"
    if kind == "channels":
        return value or "none"
    if kind == "path":
        return value or "this project folder"
    return "" if value is None else str(value)


def rows(cfg: dict) -> list:
    """Every setting as plain data, in screen order."""
    out = []
    for s in SCHEMA:
        row = {k: s[k] for k in ("key", "group", "label", "kind", "help")}
        if s["kind"] == "link":
            row.update(link=s["link"], value="", default="", is_default=True)
        else:
            row.update(value=display(cfg, s["key"]),
                       default=display(cfg, s["key"], s["default"]),
                       is_default=is_default(cfg, s["key"]))
            for extra in ("choices", "min", "max"):
                if extra in s:
                    row[extra] = s[extra]
        out.append(row)
    return out


def sort_flags(cfg: dict) -> list:
    """run_sorting.py flags for the saved signal/sorter settings - ALWAYS explicit,
    so a sort's argv (recorded in run_info.json) states every value it used and a
    future change of a run_sorting default cannot silently change a menu sort."""
    flags = ["--freq-min", f"{get(cfg, 'freq_min'):g}",
             "--freq-max", f"{get(cfg, 'freq_max'):g}",
             "--bad-channel-method", get(cfg, "bad_channel_method"),
             "--n-jobs", str(get(cfg, "n_jobs"))]
    if not get(cfg, "bad_channel_detection"):
        flags.append("--no-bad-channel-detection")
    if get(cfg, "bad_channels"):
        flags += ["--bad-channels", get(cfg, "bad_channels")]
    if get(cfg, "keep_analog"):
        flags.append("--keep-analog")
    return flags


def quick_seconds(cfg: dict) -> int:
    return int(get(cfg, "quick_seconds"))


def changed_count(cfg: dict) -> int:
    """How many non-link settings differ from their defaults (a Home/Sort hint)."""
    return sum(1 for s in SCHEMA if s["kind"] != "link" and not is_default(cfg, s["key"]))
