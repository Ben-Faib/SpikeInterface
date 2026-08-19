"""Load the LFP + spike events and save a few exploratory figures.

    uv run python scripts/explore_data.py            # uses the data in the repo root
    uv run python scripts/explore_data.py --data-dir /path/to/another/recording

Figures are written to ./outputs/ (git-ignored):
    * simultaneity.png - LFP (all neural channels) + online detections on ONE
                         shared time axis - the "what happened at the same
                         moment" view
    * lfp_traces.png   - a short window of every neural LFP channel (aux inputs
                         excluded when the neural/aux split is known)
    * spike_raster.png - the .nev online DETECTIONS per channel group (ch#class
                         labels; class 0 = unsorted threshold crossings)
    * firing_rates.png - mean online-detection rate per channel group
    * explore.html     - all of the above on one self-contained page (images
                         embedded, so it can be moved/shared on its own)

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


def _neural_ids(recording):
    """(channel_ids, split_known): NEURAL channels with aux 'analog N' inputs
    excluded when the split is determinable - the figure claims "neural" ONLY
    then; otherwise everything is shown and titled plainly as channels."""
    try:
        ids = bio.neural_channel_ids(recording)
        n_total = recording.get_num_channels()
        if len(ids) and len(ids) < n_total:
            return list(ids), True
        return list(recording.get_channel_ids()), len(ids) == n_total
    except Exception:  # noqa: BLE001 - unusual recordings: show all, claim nothing
        return list(recording.get_channel_ids()), False


def plot_lfp(recording, out_path: Path, window_s: float = 5.0):
    fs = recording.get_sampling_frequency()
    n_frames = int(min(window_s, recording.get_total_duration()) * fs)
    channel_ids, split_known = _neural_ids(recording)
    n_aux = recording.get_num_channels() - len(channel_ids)
    traces = recording.get_traces(start_frame=0, end_frame=n_frames, channel_ids=channel_ids)
    t = np.arange(n_frames) / fs

    # Stack channels vertically with an offset so they don't overlap.
    spacing = 1.2 * np.nanmax(np.abs(traces)) if traces.size else 1.0
    fig, ax = plt.subplots(figsize=(11, max(6, 0.45 * len(channel_ids) + 1)))
    for i, ch in enumerate(channel_ids):
        ax.plot(t, traces[:, i] + i * spacing, lw=0.6)
    ax.set_yticks([i * spacing for i in range(len(channel_ids))])
    ax.set_yticklabels([str(ch) for ch in channel_ids])
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Channel")
    if split_known:
        aux = f" · {n_aux} aux channels excluded" if n_aux else ""
        kind = f"all {len(channel_ids)} neural channels"
    else:
        aux = ""
        kind = f"{len(channel_ids)} channels (neural/aux split unknown)"
    ax.set_title(f"LFP - first {window_s:g}s, {kind} @ {fs:g} Hz{aux}")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _detection_labels(sorting):
    """Honest per-row labels for the .nev rows: 'ch5#1'-style channel#class names
    when the neo header carries them (SpikeInterface renumbers positionally),
    else the bare renumbered ids. The recovery itself belongs to the loader
    (bio.online_unit_labels) - this only decides what to do without it."""
    try:
        labels = bio.online_unit_labels(sorting)
        if labels and len(labels) == len(sorting.get_unit_ids()):
            return labels
    except Exception:  # noqa: BLE001 - labels are best-effort
        pass
    return [str(u) for u in sorting.get_unit_ids()]


def plot_simultaneity(recording, sorting, out_path: Path, window_s: float = 5.0):
    """The shared-clock view: LFP (all neural channels) and the .nev detections on
    ONE time axis, so what happened at the same moment across the array is
    visible - the question the separate figures cannot answer."""
    fs = recording.get_sampling_frequency()
    n_frames = int(min(window_s, recording.get_total_duration()) * fs)
    channel_ids, _split_known = _neural_ids(recording)
    traces = recording.get_traces(start_frame=0, end_frame=n_frames, channel_ids=channel_ids)
    t = np.arange(n_frames) / fs
    labels = _detection_labels(sorting)
    unit_ids = list(sorting.get_unit_ids())

    fig, (ax1, ax2) = plt.subplots(
        2, 1, sharex=True, figsize=(11, max(7, 0.4 * len(channel_ids) + 3)),
        height_ratios=[3, 1], constrained_layout=True)
    spacing = 1.2 * np.nanmax(np.abs(traces)) if traces.size else 1.0
    for i, ch in enumerate(channel_ids):
        ax1.plot(t, traces[:, i] + i * spacing, lw=0.5)
    ax1.set_yticks([i * spacing for i in range(len(channel_ids))])
    ax1.set_yticklabels([str(ch) for ch in channel_ids], fontsize=7)
    ax1.set_ylabel("Channel")
    ax1.set_title(f"Same clock - LFP and online detections, first {window_s:g}s")
    t_end = n_frames / fs
    for row, unit in enumerate(unit_ids):
        times = _unit_spike_times(sorting, unit)
        times = times[times <= t_end]
        ax2.scatter(times, np.full_like(times, row), s=4, marker="|")
    ax2.set_yticks(range(len(unit_ids)))
    ax2.set_yticklabels(labels, fontsize=7)
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Detections")
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _unit_spike_times(sorting, unit_id):
    fs = sorting.get_sampling_frequency()
    return sorting.get_unit_spike_train(unit_id) / fs


def plot_raster(sorting, out_path: Path):
    """The full-recording detections figure, readable at 132 s (Ben's feedback:
    the old squat scatter smeared every group into a dashed stripe).

    Top: a real raster (eventplot - one thin vertical line per event, roomy
    rows, per-row event counts so a near-empty row reads as a fact, not a
    rendering glitch). Bottom, same clock: per-group detection rate in 1 s bins,
    which is what actually shows STRUCTURE at this time scale - bursts, quiet
    stretches, the coordinated episodes."""
    unit_ids = list(sorting.get_unit_ids())
    labels = _detection_labels(sorting)
    trains = [_unit_spike_times(sorting, u) for u in unit_ids]
    t_end = max((t[-1] for t in trains if len(t)), default=1.0)
    colors = [f"C{i % 10}" for i in range(len(unit_ids))]

    fig, (ax, ax2) = plt.subplots(
        2, 1, sharex=True, figsize=(11, max(6, 0.55 * len(unit_ids) + 3.5)),
        height_ratios=[2, 1], constrained_layout=True)
    ax.eventplot(trains, colors=colors, linewidths=0.4, linelengths=0.75,
                 lineoffsets=range(len(unit_ids)))
    ax.set_yticks(range(len(unit_ids)))
    ax.set_yticklabels([f"{lab}  (n={len(tr)})" for lab, tr in zip(labels, trains)],
                       fontsize=9)
    ax.set_ylabel("Detection group (ch#class)")
    ax.margins(y=0.04)
    # Honest naming (C1 finding): these are the rig's ONLINE DETECTIONS -
    # class 0 rows are unsorted threshold crossings, not sorted units.
    ax.set_title(f"Online detections (.nev) - {len(unit_ids)} channel groups, "
                 f"{t_end:.0f} s")
    bins = np.arange(0, t_end + 1.0, 1.0)
    for tr, c, lab in zip(trains, colors, labels):
        if not len(tr):
            continue
        counts, edges = np.histogram(tr, bins=bins)
        ax2.plot(edges[:-1] + 0.5, counts, lw=0.8, color=c, alpha=0.85)
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("events / s")
    ax2.set_title("Detection rate per group (1 s bins)", fontsize=10)
    for a in (ax, ax2):
        a.spines[["top", "right"]].set_visible(False)
        a.grid(axis="x", alpha=0.15)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_firing_rates(sorting, out_path: Path):
    unit_ids = list(sorting.get_unit_ids())
    fs = sorting.get_sampling_frequency()
    duration = max(
        ((sorting.get_unit_spike_train(u)[-1] / fs if len(sorting.get_unit_spike_train(u)) else 0.0)
         for u in unit_ids),
        default=0.0,  # a .nev with no online units must not crash explore
    )
    duration = duration or 1.0
    rates = [len(sorting.get_unit_spike_train(u)) / duration for u in unit_ids]

    labels = _detection_labels(sorting)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(labels, rates)
    ax.set_xlabel("Detection group (ch#class)")
    ax.set_ylabel("Mean event rate (Hz)")
    ax.set_title("Mean online-detection rate per channel group")
    plt.setp(ax.get_xticklabels(), rotation=0, fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def write_gallery(figures: list[tuple[str, Path]], out_path: Path) -> None:
    """One self-contained HTML page showing every saved figure (base64-embedded,
    like report.html - no sibling files needed, safe to move or share alone)."""
    import base64

    sections = []
    for caption, png in figures:
        data = base64.b64encode(png.read_bytes()).decode("ascii")
        sections.append(
            f"<figure><img src='data:image/png;base64,{data}' alt='{caption}'>"
            f"<figcaption>{caption} &middot; <code>{png.name}</code></figcaption></figure>"
        )
    out_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Raw-data exploration</title><style>"
        "body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;"
        "padding:0 1rem;background:#fff;color:#222}"
        "img{max-width:100%;border:1px solid #ddd;border-radius:4px}"
        "figure{margin:2rem 0}figcaption{color:#666;font-size:.9rem;margin-top:.4rem}"
        "</style></head><body><h1>Raw-data exploration</h1>"
        "<p>Static figures from the raw recording (no spike sorting involved). "
        "The PNGs sit next to this file in <code>outputs/</code>.</p>"
        + "".join(sections) + "</body></html>",
        encoding="utf-8",
    )


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

    # Fail clean (one actionable line, not a raw traceback) if the data is absent -
    # matching how the report/menu degrade for the same missing-files case.
    try:
        bio.find_blackrock_base(args.data_dir)
    except FileNotFoundError as err:
        print(f"✗ {err}")
        return 1

    print("Reading LFP recording (.ns2) ...")
    recording = bio.read_lfp(args.data_dir)
    print(
        f"  {recording.get_num_channels()} channels, "
        f"{recording.get_total_duration():.2f}s @ {recording.get_sampling_frequency():g} Hz"
    )

    print("Reading spike events (.nev) ...")
    sorting = bio.read_spikes(args.data_dir)
    print(f"  {len(sorting.get_unit_ids())} detection groups")

    print(f"Saving figures to {OUTPUT_DIR} ...")
    figures = [
        ("Same clock - LFP + online detections (the simultaneity view)",
         OUTPUT_DIR / "simultaneity.png"),
        ("LFP traces (.ns2) - every channel the figure title claims",
         OUTPUT_DIR / "lfp_traces.png"),
        ("Online detections (.nev) - raster + per-group rate, full recording",
         OUTPUT_DIR / "spike_raster.png"),
        ("Mean detection rate per channel group (.nev)",
         OUTPUT_DIR / "firing_rates.png"),
    ]
    plot_simultaneity(recording, sorting, figures[0][1])
    plot_lfp(recording, figures[1][1])
    plot_raster(sorting, figures[2][1])
    plot_firing_rates(sorting, figures[3][1])
    write_gallery(figures, OUTPUT_DIR / "explore.html")
    print(f"Viewable page: {OUTPUT_DIR / 'explore.html'}")
    print("Done. ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
