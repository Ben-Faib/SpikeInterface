"""Spike-sort the raw broadband recording (.ns5 @ ~30 kHz).

    conda activate si_env
    python scripts/run_sorting.py                          # tridesclous2, full recording
    python scripts/run_sorting.py --sorter spykingcircus2  # the other installed sorter
    python scripts/run_sorting.py --duration 30            # quick test: first 30 s only
    python scripts/run_sorting.py --data-dir /path/to/recording

Pipeline: read broadband (.ns5) -> attach placeholder independent-channel probe
-> bandpass 300-6000 Hz -> common median reference -> run sorter -> save +
(optionally) compute quality metrics.

Outputs (git-ignored) land in outputs/<sorter>/:
    sorter_output/        raw sorter working folder
    sorting/              saved SI Sorting   (reload: si.load(".../sorting"))
    analyzer/             SortingAnalyzer    (open in spikeinterface-gui, or reload)
    quality_metrics.csv   per-unit firing rate / SNR / ISI-violation table

GEOMETRY CAVEAT: the Blackrock files carry no electrode map, so a placeholder
"independent channels" probe is attached (see blackrock_io.attach_dummy_probe).
Per-unit results are valid; cross-channel spatial info is not physical until the
real probe geometry is supplied.

Installed CPU sorters are tridesclous2 and spykingcircus2 (both bundled with
spikeinterface[full]; no GPU needed). Kilosort4 etc. would need an NVIDIA GPU +
PyTorch, which is not installed here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402

SORTERS = ["tridesclous2", "spykingcircus2"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", default=None, help="Folder with the .ns5/.nev (default: repo root).")
    parser.add_argument("--sorter", default="tridesclous2", choices=SORTERS, help="Which sorter to run.")
    parser.add_argument("--output-dir", default=None, help="Where to write results (default: outputs/<sorter>/).")
    parser.add_argument("--duration", type=float, default=None, help="Sort only the first N seconds (quick test).")
    parser.add_argument("--freq-min", type=float, default=300.0, help="Bandpass low cutoff (Hz).")
    parser.add_argument("--freq-max", type=float, default=6000.0, help="Bandpass high cutoff (Hz).")
    parser.add_argument("--no-metrics", action="store_true", help="Skip the SortingAnalyzer / quality-metrics step.")
    args = parser.parse_args()

    import spikeinterface.full as si
    import spikeinterface.preprocessing as spre
    import spikeinterface.sorters as ss

    out = Path(args.output_dir) if args.output_dir else (bio.REPO_ROOT / "outputs" / args.sorter)
    out.mkdir(parents=True, exist_ok=True)

    print("Reading broadband (.ns5) ...")
    rec = bio.read_broadband(args.data_dir)  # placeholder independent-channel probe attached
    print(
        f"  {rec.get_num_channels()} channels @ {rec.get_sampling_frequency():g} Hz, "
        f"{rec.get_total_duration():.1f}s"
    )

    fs = rec.get_sampling_frequency()
    freq_max = min(args.freq_max, 0.49 * fs)  # keep the high cutoff below Nyquist
    if freq_max < args.freq_max:
        print(f"  (clamped bandpass high cutoff to {freq_max:g} Hz for {fs:g} Hz Nyquist)")
    print("Preprocessing (bandpass + common median reference) ...")
    rec = spre.bandpass_filter(rec, freq_min=args.freq_min, freq_max=freq_max)
    rec = spre.common_reference(rec, reference="global", operator="median")
    if args.duration is not None:
        if args.duration <= 0:
            parser.error("--duration must be positive")
        n_samples = rec.get_num_samples()
        end = min(int(args.duration * fs), n_samples)
        rec = rec.frame_slice(0, end)
        print(f"  (limited to first {end / fs:g}s of {n_samples / fs:g}s)")

    print(f"Running {args.sorter} ...")
    sorting = ss.run_sorter(
        args.sorter,
        rec,
        folder=str(out / "sorter_output"),
        remove_existing_folder=True,
        verbose=True,
    )
    print(f"  {len(sorting.get_unit_ids())} units found")

    sorting = sorting.save(folder=str(out / "sorting"), overwrite=True)

    if not args.no_metrics:
        print("Computing quality metrics (SortingAnalyzer) ...")
        analyzer = si.create_sorting_analyzer(
            sorting, rec, folder=str(out / "analyzer"), format="binary_folder", overwrite=True
        )
        analyzer.compute(["random_spikes", "waveforms", "templates", "noise_levels"])
        analyzer.compute("quality_metrics", metric_names=["firing_rate", "snr", "isi_violation"])
        qm = analyzer.get_extension("quality_metrics").get_data()
        qm.to_csv(out / "quality_metrics.csv")
        print(qm.round(3).to_string())

    print(f"\nDone. ✓  Results in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
