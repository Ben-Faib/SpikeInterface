"""Show the recording's channels and its collection sites (probe geometry).

    uv run python scripts/show_channels.py                     # all channels + probe map
    uv run python scripts/show_channels.py --channels 1,3,7    # only those channels
    uv run python scripts/show_channels.py --sorter mountainsort5  # highlight that sort's
                                                                  # active electrodes + noise
    uv run python scripts/show_channels.py --window 3 --probe independent

Writes two headless figures to ./outputs/ (git-ignored) and prints a site→channel
table:
    * probe_map.png  - the COLLECTION SITES: each electrode contact drawn at its
                       physical (x, y) position in µm, labelled by channel id.
                       Active electrodes (the peak channel of >=1 sorted unit, from
                       the sort's summary.json) are filled; sites are colour-graded
                       by per-channel noise floor when a sort is available.
    * channels.png   - the CHANNELS: a short band-passed window of each selected
                       channel, stacked in physical depth order so the trace stack
                       mirrors the probe.

This is read-only w.r.t. your data. For an INTERACTIVE view of different channels
use the menu's "Scroll raw traces" (ephyviewer) action; for the probe + per-unit
templates use the "Open inspector GUI" (spikeinterface-gui) action.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe, before pyplot
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import probes  # noqa: E402
import runs  # noqa: E402  (the run store: which saved run is current)
import sort_summary  # noqa: E402

OUTPUT_DIR = bio.REPO_ROOT / "outputs"
ACTIVE_COLOR = "#3fb950"
IDLE_COLOR = "#8b949e"


def _resolve_probe(name: "str | None"):
    """The requested probe profile, else the menu's active probe, else the default."""
    if name:
        return probes.get(name)
    try:  # the menu persists the active probe in .si_menu.json
        import json
        cfg = json.loads((bio.REPO_ROOT / ".si_menu.json").read_text(encoding="utf-8"))
        return probes.get(cfg.get("active_probe") or probes.DEFAULT_PROBE) or probes.get(probes.DEFAULT_PROBE)
    except Exception:  # noqa: BLE001 - no config -> default
        return probes.get(probes.DEFAULT_PROBE)


def _sorted_recording(data_dir, probe_profile):
    """Broadband, neural channels only, with the chosen probe geometry attached."""
    rec = bio.read_broadband(data_dir, attach_probe=False)
    neural = bio.neural_channel_ids(rec)
    if 0 < len(neural) < rec.get_num_channels():
        rec = bio.select_channels(rec, neural)
    try:
        rec = rec.set_probe(probes.build(probe_profile, rec.get_num_channels()))
    except Exception:  # noqa: BLE001 - geometry mismatch -> placeholder so we still render
        rec = bio.attach_dummy_probe(rec)
    return rec


def plot_probe_map(rec, out_path: Path, *, active=None, noise=None, label="") -> None:
    """Draw the collection sites at their physical positions, labelled by channel."""
    loc = rec.get_channel_locations()          # (n, 2) µm
    chan_ids = [str(c) for c in rec.get_channel_ids()]
    active = set(active or [])
    x, y = loc[:, 0], loc[:, 1]

    fig, ax = plt.subplots(figsize=(4.5, 9))
    # Colour idle vs active; grade by noise when available (viridis over the sites).
    if noise is not None and len(noise) == len(chan_ids) and np.isfinite(noise).any():
        sc = ax.scatter(x, y, c=noise, cmap="viridis", s=260, edgecolors="black",
                        linewidths=1.2, zorder=3)
        cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label("noise floor (µV)")
    else:
        colors = [ACTIVE_COLOR if c in active else IDLE_COLOR for c in chan_ids]
        ax.scatter(x, y, c=colors, s=260, edgecolors="black", linewidths=1.2, zorder=3)
    # Ring active electrodes so they read even under the noise colourmap.
    for xi, yi, c in zip(x, y, chan_ids):
        if c in active:
            ax.scatter([xi], [yi], s=430, facecolors="none", edgecolors=ACTIVE_COLOR,
                       linewidths=2.4, zorder=4)
        ax.annotate(c, (xi, yi), textcoords="offset points", xytext=(14, 0),
                    va="center", fontsize=8, zorder=5)
    ax.set_xlabel("x (µm)")
    ax.set_ylabel("depth y (µm)")
    n_active = sum(1 for c in chan_ids if c in active)
    title = f"Collection sites - {label or 'probe'}\n{len(chan_ids)} contacts"
    if active:
        title += f" · {n_active} active (filled/ringed)"
    ax.set_title(title, fontsize=10)
    # A little x-margin so labels aren't clipped on a linear (single-column) probe.
    xpad = max((x.max() - x.min()) * 0.5, 40.0)
    ax.set_xlim(x.min() - xpad, x.max() + xpad + 40)
    ax.invert_yaxis()  # depth increases downward, like the physical probe
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_channels(rec, out_path: Path, *, channel_ids=None, window_s: float = 2.0,
                  active=None) -> None:
    """Stacked band-passed traces of the (selected) channels, in physical depth order."""
    import spikeinterface.preprocessing as spre

    filt = spre.bandpass_filter(rec, freq_min=300, freq_max=min(6000, 0.49 * rec.get_sampling_frequency()))
    all_ids = [str(c) for c in filt.get_channel_ids()]
    sel = [c for c in (channel_ids or all_ids) if c in all_ids] or all_ids
    # Order the stack by physical depth (y) so it mirrors the probe layout.
    loc = {str(c): xy for c, xy in zip(rec.get_channel_ids(), rec.get_channel_locations())}
    sel = sorted(sel, key=lambda c: loc.get(c, (0, 0))[1])
    active = set(active or [])

    fs = filt.get_sampling_frequency()
    n = int(min(window_s, filt.get_total_duration()) * fs)
    traces = filt.get_traces(start_frame=0, end_frame=n, channel_ids=sel, return_scaled=True)
    t = np.arange(n) / fs
    spacing = 2.4 * float(np.nanpercentile(np.abs(traces), 99)) if traces.size else 1.0
    spacing = spacing or 1.0

    fig, ax = plt.subplots(figsize=(12, max(4, 0.42 * len(sel) + 1)))
    for i, c in enumerate(sel):
        colour = ACTIVE_COLOR if c in active else "#3b6fb0"
        ax.plot(t, traces[:, i] + i * spacing, lw=0.5, color=colour)
    ax.set_yticks([i * spacing for i in range(len(sel))])
    ax.set_yticklabels([f"ch {c}" + ("  ●" if c in active else "") for c in sel], fontsize=8)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("channel (shallow → deep)")
    ax.set_title(f"Broadband (300–6000 Hz) - first {min(window_s, filt.get_total_duration()):g}s · "
                 f"{len(sel)} channels" + ("  (● = active electrode)" if active else ""))
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> int:
    bio.use_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=None, help="Folder with the .ns5 (default: repo root).")
    ap.add_argument("--probe", default=None, help="Probe profile name (default: active/default probe).")
    ap.add_argument("--channels", default=None,
                    help="Comma-separated channel ids to show in channels.png (default: all).")
    ap.add_argument("--sorter", default=None,
                    help="Highlight this sort's active electrodes + colour sites by its noise floor.")
    ap.add_argument("--window", type=float, default=2.0, help="Seconds of traces to show (default 2).")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        bio.find_blackrock_base(args.data_dir)
    except FileNotFoundError as err:
        print(f"✗ {err}")
        return 1

    profile = _resolve_probe(args.probe)
    if profile is None:
        print(f"✗ Unknown probe {args.probe!r}. See the menu's 'Set probe geometry'.")
        return 1
    print(f"Probe geometry: {probes.summary(profile)}")
    rec = _sorted_recording(args.data_dir, profile)

    # Active electrodes + per-channel noise from a saved sort's summary, if asked.
    active, noise = None, None
    if args.sorter:
        summary = sort_summary.load_summary(
            runs.sort_paths(args.sorter, outputs=OUTPUT_DIR)["out"])
        if summary:
            active = summary.get("active_channels") or []
            per_ch = (summary.get("noise_floor_uV") or {}).get("per_channel")
            if per_ch:
                noise = np.array([np.nan if v is None else v for v in per_ch], dtype=float)
            print(f"Highlighting {len(active)} active electrode(s) from the {args.sorter} sort "
                  f"({summary.get('n_units')} units).")
        else:
            print(f"(no saved summary for {args.sorter} - showing geometry without activity)")

    channel_ids = None
    if args.channels:
        channel_ids = [c.strip() for c in args.channels.split(",") if c.strip()]

    loc = rec.get_channel_locations()
    chan_ids = [str(c) for c in rec.get_channel_ids()]
    print(f"\n{len(chan_ids)} collection sites (channel → x,y µm):")
    for c, (x, y) in zip(chan_ids, loc):
        flag = "  ● active" if active and c in active else ""
        print(f"  ch {c:>3}  →  ({x:6.0f}, {y:6.0f}) µm{flag}")

    print(f"\nSaving figures to {OUTPUT_DIR} …")
    plot_probe_map(rec, OUTPUT_DIR / "probe_map.png", active=active, noise=noise,
                   label=profile.get("label", profile.get("name")))
    plot_channels(rec, OUTPUT_DIR / "channels.png", channel_ids=channel_ids,
                  window_s=args.window, active=active)
    print("  probe_map.png  - collection sites (electrode geometry)")
    print("  channels.png   - per-channel band-passed traces")
    print("Done. ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
