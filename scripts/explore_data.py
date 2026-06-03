"""Load the LFP + spike events and save a few exploratory figures.

    conda activate si_env
    python scripts/explore_data.py            # uses the data in the repo root
    python scripts/explore_data.py --data-dir /path/to/another/recording

Figures are written to ./outputs/ (git-ignored):
    * lfp_traces.png   — a short window of several LFP channels
    * spike_raster.png — spike raster across all .nev units
    * firing_rates.png — mean firing rate per unit

This is read-only with respect to your data; it only writes images.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Headless-safe plotting backend (must be set before importing pyplot).
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402

OUTPUT_DIR = bio.REPO_ROOT / "outputs"


def plot_lfp(recording, out_path: Path, window_s: float = 5.0, max_channels: int = 6):
    fs = recording.get_sampling_frequency()
    n_frames = int(min(window_s, recording.get_total_duration()) * fs)
    channel_ids = recording.get_channel_ids()[:max_channels]
    traces = recording.get_traces(start_frame=0, end_frame=n_frames, channel_ids=channel_ids)
    t = np.arange(n_frames) / fs

    # Stack channels vertically with an offset so they don't overlap.
    spacing = 1.2 * np.nanmax(np.abs(traces)) if traces.size else 1.0
    fig, ax = plt.subplots(figsize=(11, 6))
    for i, ch in enumerate(channel_ids):
        ax.plot(t, traces[:, i] + i * spacing, lw=0.6)
    ax.set_yticks([i * spacing for i in range(len(channel_ids))])
    ax.set_yticklabels([str(ch) for ch in channel_ids])
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Channel")
    ax.set_title(f"LFP traces — first {window_s:g}s, {len(channel_ids)} channels @ {fs:g} Hz")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _unit_spike_times(sorting, unit_id):
    fs = sorting.get_sampling_frequency()
    return sorting.get_unit_spike_train(unit_id) / fs


def plot_raster(sorting, out_path: Path):
    unit_ids = list(sorting.get_unit_ids())
    fig, ax = plt.subplots(figsize=(11, max(3, 0.3 * len(unit_ids) + 1)))
    for row, unit in enumerate(unit_ids):
        times = _unit_spike_times(sorting, unit)
        ax.scatter(times, np.full_like(times, row), s=2, marker="|")
    ax.set_yticks(range(len(unit_ids)))
    ax.set_yticklabels([str(u) for u in unit_ids])
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Unit id")
    ax.set_title(f"Spike raster — {len(unit_ids)} units from .nev")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_firing_rates(sorting, out_path: Path):
    unit_ids = list(sorting.get_unit_ids())
    fs = sorting.get_sampling_frequency()
    duration = max(
        (sorting.get_unit_spike_train(u)[-1] / fs if len(sorting.get_unit_spike_train(u)) else 0.0)
        for u in unit_ids
    )
    duration = duration or 1.0
    rates = [len(sorting.get_unit_spike_train(u)) / duration for u in unit_ids]

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar([str(u) for u in unit_ids], rates)
    ax.set_xlabel("Unit id")
    ax.set_ylabel("Mean firing rate (Hz)")
    ax.set_title("Mean firing rate per unit")
    plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> int:
    bio.use_utf8_stdout()  # UTF-8 stdout so the "✓"/em-dash output is Windows-safe
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Folder containing the .nev/.nsX files (default: repo root).",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    print("Reading LFP recording (.ns2) ...")
    recording = bio.read_lfp(args.data_dir)
    print(
        f"  {recording.get_num_channels()} channels, "
        f"{recording.get_total_duration():.2f}s @ {recording.get_sampling_frequency():g} Hz"
    )

    print("Reading spike events (.nev) ...")
    sorting = bio.read_spikes(args.data_dir)
    print(f"  {len(sorting.get_unit_ids())} units")

    print(f"Saving figures to {OUTPUT_DIR} ...")
    plot_lfp(recording, OUTPUT_DIR / "lfp_traces.png")
    plot_raster(sorting, OUTPUT_DIR / "spike_raster.png")
    plot_firing_rates(sorting, OUTPUT_DIR / "firing_rates.png")
    print("Done. ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
