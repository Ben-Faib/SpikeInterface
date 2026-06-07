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
-> drop non-neural 'analog N' aux channels (keep with --keep-analog) -> bandpass
300-6000 Hz -> common median reference -> run sorter -> save + (optionally)
compute quality metrics and the GUI-inspector curation extensions.

Outputs (git-ignored) land in outputs/<sorter>/:
    sorter_output/        raw sorter working folder
    sorting/              saved SI Sorting   (reload: si.load(".../sorting"))
    analyzer/             SortingAnalyzer    (open in spikeinterface-gui, or reload)
    quality_metrics.csv   per-unit firing rate / SNR / ISI-violation table
    run_info.json         provenance: sorter, window (effective vs total), band,
                          channels sorted, unit count, versions, timestamp

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
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import sorters  # noqa: E402  (sorter registry: discovery / status / params / run)

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

    def warn(self, text: str) -> None:
        """A safety/caution line. Shown at *every* level (even quiet) — these flag
        things like overwriting a previous sort, which the user must not miss."""
        self._emit(f"[{self.PALETTE['warn']}]! {text}[/]", f"! {text}")

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


# SortingAnalyzer extensions that the spikeinterface-gui inspector needs for its
# manual-curation views: correlograms (refractory violations), ISI histograms,
# spike amplitudes (drift/amplitude-cutoff), spike locations (depth view),
# template similarity (merge suggestions) and PCA (ND-scatter separability).
# Without these precomputed, those inspector panels open blank. They are cheap on
# this dataset (~5 s on the full 132 s recording) so we compute them at sort time.
_CURATION_EXTENSIONS = [
    "unit_locations",        # probe / unit-position view (placeholder geometry — see caveat)
    "correlograms",
    "isi_histograms",
    "spike_amplitudes",
    "spike_locations",
    "template_similarity",
    "principal_components",
]


def _compute_curation_extensions(analyzer, ui: "ConsoleUI") -> None:
    """Best-effort compute the inspector-facing extensions; never fail the sort.

    Each extension is computed independently so that one that errors on an
    unusual sort (e.g. too few spikes for PCA) just prints a skip note and leaves
    the rest — the core sorting + quality metrics are already saved by now.
    """
    ui.detail("computing GUI-inspector extensions (correlograms, ISI, amplitudes, "
              "locations, similarity, PCA) …")
    for ext in _CURATION_EXTENSIONS:
        try:
            analyzer.compute(ext)
        except Exception as e:  # noqa: BLE001 - optional curation data, keep going
            ui.detail(f"  skipped {ext} ({type(e).__name__})")


def _write_run_info(out: Path, args, **fields) -> None:
    """Write outputs/<sorter>/run_info.json so a sort is self-identifying.

    Records the sorter, the effective vs total recording window, the band, the
    channels actually sorted and the unit count — so downstream tools (and the
    report) can tell a short ``--duration`` smoke test apart from a full run
    instead of silently presenting one as the other.
    """
    info = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "command": "run_sorting.py",
        "duration_arg": args.duration,
        "keep_analog": args.keep_analog,
        "n_jobs": args.n_jobs,
        **fields,
    }
    try:
        (out / "run_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - provenance is best-effort
        pass


def _warn_existing_sort(out: Path, ui: "ConsoleUI") -> None:
    """Warn (don't block) before overwriting an existing sort in ``out``.

    The sort overwrites outputs/<sorter>/ in place, so a previous full run can be
    silently replaced by a quick ``--duration`` smoke test. Surface what is about
    to be lost; the run still proceeds (this is a CLI, not an interactive prompt).
    """
    info_path = out / "run_info.json"
    if info_path.exists():
        try:
            prev = json.loads(info_path.read_text(encoding="utf-8"))
            eff = prev.get("effective_seconds")
            span = f"{eff:.0f}s" if isinstance(eff, (int, float)) else "?s"
            ui.warn(f"overwriting previous {prev.get('sorter', '?')} sort "
                    f"({prev.get('n_units', '?')} units over {span}, "
                    f"created {prev.get('created', '?')})")
            return
        except Exception:  # noqa: BLE001 - fall through to the generic warning
            pass
    if (out / "analyzer").exists() or (out / "sorting").exists():
        ui.warn(f"overwriting an existing sort in {out}")


def _friendly_sort_error(exc: Exception) -> str:
    """Turn a sort failure into a one-line, actionable message (no traceback)."""
    text = str(exc)
    if "daemon" in text.lower() or "docker" in text.lower():
        return "Docker isn't running — open Docker Desktop and try again."
    return f"Sorting failed: {text}"


def resolve_sorter(name: str, use_docker: bool) -> str:
    """Validate a requested sorter against what's runnable; exit clearly if not.

    ``--sorter`` is not a fixed argparse ``choices`` because the runnable set
    depends on ``--docker`` and what's installed; this resolves it after parsing.
    """
    runnable = sorters.runnable(use_docker)
    if name in runnable:
        return name
    st = sorters.status(name)
    reason = {
        "gpu": "needs an NVIDIA GPU (not available here)",
        "docker": "is a container sorter — re-run with --docker (and start Docker)",
        "unavailable": "is not installed and has no usable container image",
        "local": "is installed",  # unreachable (would be in runnable)
    }.get(st, "is not available")
    raise SystemExit(
        f"Sorter {name!r} {reason}.\nRunnable now: {', '.join(runnable) or '(none)'}."
        "\nSee all sorters with: python scripts/run_sorting.py --list-sorters"
    )


def resolve_overrides(sorter: str, param_kv: list[str], params_file: "str | None") -> dict:
    """Build the override dict: defaults < --params-file < repeated --param.

    Values are coerced to each default's type; unknown keys / bad values exit with
    a clear message (before any sorting starts).
    """
    defaults = sorters.default_params(sorter)
    overrides: dict = {}
    if params_file:
        try:
            file_over = json.loads(Path(params_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise SystemExit(f"--params-file {params_file!r}: {e}")
        if not isinstance(file_over, dict):
            raise SystemExit(f"--params-file {params_file!r} must contain a JSON object.")
        overrides.update(file_over)
    for item in param_kv:
        if "=" not in item:
            raise SystemExit(f"--param expects NAME=VALUE, got {item!r}")
        key, raw = item.split("=", 1)
        key = key.strip()
        if key not in defaults:
            raise SystemExit(
                f"unknown parameter {key!r} for {sorter}. valid keys: {sorted(defaults)}")
        try:
            overrides[key] = sorters.coerce_param(defaults[key], raw)
        except ValueError as e:
            raise SystemExit(f"--param {key}: {e}")
    # validate any keys that came from the file too
    unknown = set(overrides) - set(defaults)
    if unknown:
        raise SystemExit(
            f"unknown parameter(s) for {sorter}: {sorted(unknown)}. "
            f"valid keys: {sorted(defaults)}")
    return overrides


def print_sorter_table() -> None:
    """Print the availability of every SpikeInterface sorter, then return."""
    rows = sorters.status_table()
    label = {"local": "local", "docker": "docker", "gpu": "GPU-only", "unavailable": "—"}
    print("Sorters known to SpikeInterface (status on this machine):\n")
    for r in rows:
        print(f"  {r['name']:18} {label.get(r['status'], r['status']):9} "
              f"{r['n_params']:>3} params")
    n_local = sum(r["status"] == "local" for r in rows)
    n_dock = sum(r["status"] == "docker" for r in rows)
    n_gpu = sum(r["status"] == "gpu" for r in rows)
    print(f"\n{n_local} local · {n_dock} container-capable · {n_gpu} GPU-only.")
    if not sorters.docker_available():
        print("(Docker not detected — container sorters need Docker running.)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", default=None, help="Folder with the .ns5/.nev (default: repo root).")
    parser.add_argument("--sorter", default=None,
                        help="Which sorter to run (default: tridesclous2 if installed). "
                             "See all with --list-sorters.")
    parser.add_argument("--docker", action="store_true",
                        help="Run the sorter in its SpikeInterface Docker image "
                             "(lets you run not-installed CPU sorters).")
    parser.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                        help="Override one sorter parameter (repeatable).")
    parser.add_argument("--params-file", default=None,
                        help="JSON file of sorter parameter overrides.")
    parser.add_argument("--list-sorters", action="store_true",
                        help="Print every sorter and its availability, then exit.")
    parser.add_argument("--output-dir", default=None, help="Where to write results (default: outputs/<sorter>/).")
    parser.add_argument("--duration", type=float, default=None, help="Sort only the first N seconds (quick test).")
    parser.add_argument("--freq-min", type=float, default=300.0, help="Bandpass low cutoff (Hz).")
    parser.add_argument("--freq-max", type=float, default=6000.0, help="Bandpass high cutoff (Hz).")
    parser.add_argument("--n-jobs", type=int, default=1, help="Parallel workers for waveforms/metrics/sorting (default 1).")
    parser.add_argument(
        "--keep-analog",
        action="store_true",
        help="Keep non-neural 'analog N' aux channels in the sort (default: drop them — "
        "they pollute the common reference and can produce spurious units).",
    )
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

    # Validate args up front — before the heavy SpikeInterface import and the
    # 174 MB broadband read — so a typo fails in milliseconds, not minutes.
    if args.freq_min >= args.freq_max:
        parser.error(f"--freq-min ({args.freq_min:g}) must be below --freq-max ({args.freq_max:g})")
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be positive")
    if args.n_jobs < 1:
        parser.error("--n-jobs must be >= 1")

    if args.list_sorters:
        configure_output("quiet")  # mute import chatter; we only want the table
        print_sorter_table()
        return 0

    if args.sorter is None:
        args.sorter = sorters.default_sorter()
    args.sorter = resolve_sorter(args.sorter, args.docker)
    overrides = resolve_overrides(args.sorter, args.param, args.params_file)

    # Configure output BEFORE importing spikeinterface so env vars / the tqdm
    # patch land before OpenMP/Numba/the sorters initialise.
    show_bars = configure_output(args.verbosity)
    quiet = args.verbosity == "quiet"
    ui = ConsoleUI(quiet=quiet, total_phases=3 if args.no_metrics else 4)

    import spikeinterface.full as si
    import spikeinterface.preprocessing as spre
    import spikeinterface.sorters as ss

    si.set_global_job_kwargs(n_jobs=args.n_jobs, progress_bar=show_bars)

    out = Path(args.output_dir) if args.output_dir else (bio.REPO_ROOT / "outputs" / args.sorter)
    out.mkdir(parents=True, exist_ok=True)

    ui.banner(args.sorter)
    _warn_existing_sort(out, ui)  # flag (don't block) before we overwrite it

    ui.phase("Read broadband", "(.ns5)")
    rec = bio.read_broadband(args.data_dir)  # placeholder independent-channel probe attached
    total_seconds = rec.get_total_duration()
    ui.detail(
        f"{rec.get_num_channels()} channels · {rec.get_sampling_frequency():g} Hz · "
        f"{total_seconds:.1f}s"
    )

    # Drop non-neural analog aux channels (ids 10241+, 'analog N') before sorting:
    # left in, they corrupt the common median reference and can spawn fake units.
    n_dropped = 0
    if not args.keep_analog:
        neural = bio.neural_channel_ids(rec)
        n_dropped = rec.get_num_channels() - len(neural)
        if 0 < len(neural) < rec.get_num_channels():
            rec = bio.select_channels(rec, neural)
            rec = bio.attach_dummy_probe(rec)  # re-size the placeholder probe to the kept channels
            ui.detail(f"excluded {n_dropped} non-neural analog aux channel(s) → "
                      f"sorting {len(neural)} electrode(s)")

    fs = rec.get_sampling_frequency()
    freq_max = min(args.freq_max, 0.49 * fs)  # keep the high cutoff below Nyquist
    ui.phase("Preprocess", "bandpass + common median reference")
    if freq_max < args.freq_max:
        ui.detail(f"clamped bandpass high cutoff to {freq_max:g} Hz for {fs:g} Hz Nyquist")
    ui.detail(f"bandpass {args.freq_min:g}–{freq_max:g} Hz · common median reference")
    rec = spre.bandpass_filter(rec, freq_min=args.freq_min, freq_max=freq_max)
    rec = spre.common_reference(rec, reference="global", operator="median")
    if args.duration is not None:
        n_samples = rec.get_num_samples()
        end = min(int(args.duration * fs), n_samples)
        rec = rec.frame_slice(0, end)
        ui.detail(f"limited to first {end / fs:g}s of {n_samples / fs:g}s")
    effective_seconds = rec.get_total_duration()

    ui.phase("Sort", args.sorter + ("  (docker)" if args.docker else ""))
    if overrides:
        ui.detail("overrides: " + ", ".join(f"{k}={v}" for k, v in overrides.items()))
    if args.docker:
        ui.detail("first Docker run downloads the sorter image (~1 GB, one time only)")
    try:
        sorting = sorters.run(
            args.sorter,
            rec,
            out / "sorter_output",
            params=overrides,
            use_docker=args.docker,
            verbose=show_bars,
        )
    except RuntimeError as e:
        ui.warn(_friendly_sort_error(e))
        return 1
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
        _compute_curation_extensions(analyzer, ui)

    _write_run_info(
        out, args, si_version=si.__version__, sorter=args.sorter,
        n_units=len(sorting.get_unit_ids()), channel_ids=list(rec.get_channel_ids()),
        n_dropped_analog=n_dropped, total_seconds=total_seconds,
        effective_seconds=effective_seconds, freq_min=args.freq_min, freq_max=freq_max,
    )

    ui.done(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
