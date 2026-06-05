"""Spike-sort the raw broadband recording (.ns5 @ ~30 kHz).

    uv run python scripts/run_sorting.py                          # tridesclous2, full recording
    uv run python scripts/run_sorting.py --sorter spykingcircus2  # the other installed sorter
    uv run python scripts/run_sorting.py --duration 30            # quick test: first 30 s only
    uv run python scripts/run_sorting.py --data-dir /path/to/recording
    uv run python scripts/run_sorting.py --verbosity normal       # step messages + table, no bars
    uv run python scripts/run_sorting.py --verbosity quiet        # only the final result + table

Output is clean at every level: progress bars are aligned (uniform width/layout)
and library/native warnings (probe, OpenMP, numba, resource_tracker) are muted.
The default 'verbose' shows the aligned progress bars + per-step sorter prints.

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
import gc
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402

SORTERS = ["tridesclous2", "spykingcircus2"]
VERBOSITY_LEVELS = ["quiet", "normal", "verbose"]

# Width the tqdm description is padded/truncated to, so every progress bar's
# fill lines up in the same column. 34 fits all but the longest SI/sorter job
# names; longer ones are truncated with an ellipsis.
_TQDM_DESC_WIDTH = 34
# Fixed bar width (chars). A fixed width — rather than stretching to the terminal
# edge — keeps the bars compact and visually uniform.
_TQDM_BAR_WIDTH = 28
# Colour of the bar fill (any tqdm-accepted name or hex). Matches the cyan used
# for the phase headers in ConsoleUI for a consistent palette.
_TQDM_BAR_COLOUR = "cyan"
# Drop SpikeInterface's parallelisation suffix from the description — it is the
# same on (almost) every bar and only pushes the bar start to the right.
_TQDM_DESC_SUFFIX = re.compile(r"\s*\((?:no parallelization|workers:[^)]*)\)\s*$")
# Uniform bar layout: padded desc · 3-wide percentage · fixed-width bar · a
# consistent counts/timing tail. No brackets around the bar — the colour fill
# already delimits it cleanly.
_TQDM_BAR_FORMAT = (
    "{desc} {percentage:3.0f}%  {bar:" + str(_TQDM_BAR_WIDTH) + "}  "
    "{n_fmt}/{total_fmt}  [{elapsed}<{remaining}, {rate_fmt}]"
)


def _install_aligned_tqdm() -> None:
    """Patch tqdm so every SpikeInterface/sorter progress bar is aligned & uniform.

    Must run *before* ``import spikeinterface`` so that the libraries' own
    ``from tqdm.auto import tqdm`` picks up the patched class. The subclass strips
    the noisy parallelisation suffix, pads the description to a fixed width and
    draws a fixed-width coloured bar via a single ``bar_format`` — so every bar
    has an identical, compact layout instead of stretching to the terminal edge.
    """
    import tqdm as _tqdm
    import tqdm.auto as _tqdm_auto
    import tqdm.std as _tqdm_std

    base = _tqdm_std.tqdm

    def _format_desc(desc: str) -> str:
        desc = _TQDM_DESC_SUFFIX.sub("", desc)
        if len(desc) > _TQDM_DESC_WIDTH:
            desc = desc[: _TQDM_DESC_WIDTH - 1] + "…"
        return desc.ljust(_TQDM_DESC_WIDTH)

    class AlignedTqdm(base):
        def __init__(self, *args, **kwargs):
            if kwargs.get("desc"):
                kwargs["desc"] = _format_desc(kwargs["desc"])
            elif len(args) >= 2 and isinstance(args[1], str):  # desc passed positionally
                args = (args[0], _format_desc(args[1])) + args[2:]
            kwargs.setdefault("bar_format", _TQDM_BAR_FORMAT)
            kwargs.setdefault("colour", _TQDM_BAR_COLOUR)
            super().__init__(*args, **kwargs)

    # Rebind on every module the libraries might import tqdm from.
    _tqdm.tqdm = _tqdm_std.tqdm = _tqdm_auto.tqdm = AlignedTqdm


class ConsoleUI:
    """Structured, coloured terminal output for the pipeline.

    Renders numbered phase headers, dimmed detail lines, a boxed quality-metrics
    table and a final status line via :mod:`rich` (already a SpikeInterface
    dependency). Degrades gracefully to plain ``print`` if rich is unavailable.
    ``quiet`` suppresses everything except the final metrics table + status line;
    progress bars themselves are drawn by tqdm, not here.
    """

    PALETTE = {"accent": "cyan", "muted": "dim", "ok": "bold green", "warn": "yellow"}

    def __init__(self, *, quiet: bool, total_phases: int):
        self.quiet = quiet
        self.total = total_phases
        self.n = 0
        try:
            from rich.console import Console

            self._c = Console(highlight=False)
        except Exception:  # rich missing — fall back to plain text
            self._c = None

    def _emit(self, markup: str, plain: str) -> None:
        if self._c is not None:
            self._c.print(markup)
        else:
            print(plain, flush=True)

    def banner(self, sorter: str) -> None:
        if self.quiet:
            return
        if self._c is not None:
            self._c.rule(f"[bold]spike sorting[/] · [{self.PALETTE['accent']}]{sorter}[/]")
        else:
            print(f"=== spike sorting · {sorter} ===", flush=True)

    def phase(self, title: str, subtitle: str = "") -> None:
        """Start a numbered phase, e.g. ``[2/4] Preprocess``."""
        if self.quiet:
            return
        self.n += 1
        sub_m = f" [{self.PALETTE['muted']}]{subtitle}[/]" if subtitle else ""
        sub_p = f" {subtitle}" if subtitle else ""
        self._emit(
            f"\n[{self.PALETTE['accent']}][{self.n}/{self.total}][/] [bold]{title}[/]{sub_m}",
            f"\n[{self.n}/{self.total}] {title}{sub_p}",
        )

    def detail(self, text: str) -> None:
        if self.quiet:
            return
        self._emit(f"    [{self.PALETTE['muted']}]{text}[/]", f"    {text}")

    def result(self, text: str) -> None:
        """A highlighted per-phase outcome (e.g. '18 units found'), always indented."""
        if self.quiet:
            return
        self._emit(f"    [bold]{text}[/]", f"    {text}")

    def metrics(self, df, csv_path: Path) -> None:
        """Render the quality-metrics dataframe as a boxed table (always shown)."""
        if self._c is not None:
            from rich import box
            from rich.table import Table

            table = Table(
                box=box.SIMPLE_HEAVY,
                header_style=f"bold {self.PALETTE['accent']}",
                title="[bold]Quality metrics[/]  [dim](per unit)[/]",
                title_justify="left",
                pad_edge=False,
            )
            table.add_column("unit", justify="right", style="bold")
            for col in df.columns:
                table.add_column(col, justify="right")
            for idx, row in df.iterrows():
                cells = [str(idx)]
                for col in df.columns:
                    v = row[col]
                    cells.append(str(int(v)) if "count" in col else f"{v:.3f}")
                table.add_row(*cells)
            self._c.print()
            self._c.print(table)
            self._c.print(f"[{self.PALETTE['muted']}]saved → {csv_path}[/]")
        else:
            print("\n" + df.round(3).to_string(), flush=True)
            print(f"saved -> {csv_path}", flush=True)

    def done(self, out: Path) -> None:
        self._emit(
            f"\n[{self.PALETTE['ok']}]✓ Done[/] · results in [underline]{out}[/]",
            f"\nDone. ✓  Results in {out}",
        )


def configure_output(level: str) -> bool:
    """Mute library/native chatter and align tqdm bars. Returns ``show_bars``.

    Call this *before* importing spikeinterface so the env vars and the tqdm
    patch are in place before OpenMP/Numba/the sorters initialise. ``show_bars``
    is True only for ``verbose``; ``normal``/``quiet`` keep the high-level step
    messages but draw no progress bars. Warnings are muted at every level — they
    are clutter that breaks up the clean formatting, not the verbose signal.
    """
    # UTF-8 stdout/stderr first, before rich/tqdm/SI build any console — so the
    # ✓ / → / … glyphs below never raise UnicodeEncodeError on a legacy Windows
    # console code page (cp1252/cp437) when output is redirected or piped. Then
    # mute OpenMP/Numba/probe/resource-tracker noise before the heavy imports.
    bio.use_utf8_stdout()
    bio.mute_native_chatter()

    show_bars = level == "verbose"
    if show_bars:
        _install_aligned_tqdm()
    return show_bars


def _robust_rmtree(path: Path, attempts: int = 5, delay: float = 0.5) -> None:
    """Remove a directory tree, retrying past transient Windows file locks.

    SpikeInterface writes ``sorting``/``analyzer`` as memory-mapped binary
    folders. On Windows a just-closed ``spikeinterface-gui``/ephyviewer can leave
    a lagging handle, so deleting the folder to overwrite it raises
    ``PermissionError`` (WinError 32) — POSIX unlinks an open file silently, so
    this only bites on Windows. Retry with a gc sweep + short backoff; re-raise
    if the lock never clears.
    """
    for attempt in range(attempts):
        try:
            if path.exists():
                shutil.rmtree(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            gc.collect()
            time.sleep(delay)


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
    parser.add_argument(
        "--verbosity",
        choices=VERBOSITY_LEVELS,
        default="verbose",
        help="Terminal output: 'verbose' = aligned progress bars + per-step sorter "
        "prints (default), 'normal' = step messages + final table only, "
        "'quiet' = final table only. Warnings are muted at every level.",
    )
    args = parser.parse_args()

    # Configure output BEFORE importing spikeinterface so env vars / the tqdm
    # patch land before OpenMP/Numba/the sorters initialise.
    show_bars = configure_output(args.verbosity)
    quiet = args.verbosity == "quiet"
    ui = ConsoleUI(quiet=quiet, total_phases=3 if args.no_metrics else 4)

    import spikeinterface.full as si
    import spikeinterface.preprocessing as spre
    import spikeinterface.sorters as ss

    si.set_global_job_kwargs(progress_bar=show_bars)

    out = Path(args.output_dir) if args.output_dir else (bio.REPO_ROOT / "outputs" / args.sorter)
    out.mkdir(parents=True, exist_ok=True)

    ui.banner(args.sorter)

    ui.phase("Read broadband", "(.ns5)")
    rec = bio.read_broadband(args.data_dir)  # placeholder independent-channel probe attached
    ui.detail(
        f"{rec.get_num_channels()} channels · {rec.get_sampling_frequency():g} Hz · "
        f"{rec.get_total_duration():.1f}s"
    )

    fs = rec.get_sampling_frequency()
    freq_max = min(args.freq_max, 0.49 * fs)  # keep the high cutoff below Nyquist
    ui.phase("Preprocess", "bandpass + common median reference")
    if freq_max < args.freq_max:
        ui.detail(f"clamped bandpass high cutoff to {freq_max:g} Hz for {fs:g} Hz Nyquist")
    ui.detail(f"bandpass {args.freq_min:g}–{freq_max:g} Hz · common median reference")
    rec = spre.bandpass_filter(rec, freq_min=args.freq_min, freq_max=freq_max)
    rec = spre.common_reference(rec, reference="global", operator="median")
    if args.duration is not None:
        if args.duration <= 0:
            parser.error("--duration must be positive")
        n_samples = rec.get_num_samples()
        end = min(int(args.duration * fs), n_samples)
        rec = rec.frame_slice(0, end)
        ui.detail(f"limited to first {end / fs:g}s of {n_samples / fs:g}s")

    ui.phase("Sort", args.sorter)
    sorting = ss.run_sorter(
        args.sorter,
        rec,
        folder=str(out / "sorter_output"),
        remove_existing_folder=True,
        verbose=show_bars,
    )
    ui.result(f"{len(sorting.get_unit_ids())} units found")

    _robust_rmtree(out / "sorting")  # retry past Windows GUI file-locks before overwrite
    sorting = sorting.save(folder=str(out / "sorting"), overwrite=True)

    if not args.no_metrics:
        ui.phase("Quality metrics", "(SortingAnalyzer)")
        _robust_rmtree(out / "analyzer")  # retry past Windows GUI file-locks before overwrite
        analyzer = si.create_sorting_analyzer(
            sorting, rec, folder=str(out / "analyzer"), format="binary_folder", overwrite=True
        )
        analyzer.compute(["random_spikes", "waveforms", "templates", "noise_levels"])
        analyzer.compute("quality_metrics", metric_names=["firing_rate", "snr", "isi_violation"])
        qm = analyzer.get_extension("quality_metrics").get_data()
        qm.to_csv(out / "quality_metrics.csv")
        ui.metrics(qm, out / "quality_metrics.csv")

    ui.done(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
