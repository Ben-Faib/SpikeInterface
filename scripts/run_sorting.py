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
import contextlib
import gc
import json
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blackrock_io as bio  # noqa: E402
import sort_progress as _sp  # noqa: E402  (pure JSON progress protocol)
import sorters  # noqa: E402  (sorter registry: discovery / status / params / run)

VERBOSITY_LEVELS = ["quiet", "normal", "verbose"]


class Reporter:
    """Mirrors high-level pipeline events into the JSON progress channel.

    When ``enabled`` (``--progress json``), each call writes a ``sort_progress``
    event to ``stream`` (stdout); when disabled it is a no-op, so the normal CLI
    paths cost nothing. The human ConsoleUI is independent and writes to stderr in
    JSON mode.
    """

    def __init__(self, *, enabled: bool, stream=None, total_phases: int):
        self.enabled = enabled
        self.stream = stream if stream is not None else sys.stdout
        self.total = total_phases
        self.i = 0
        # The pipe-tee reader thread and the main thread both emit, so the write
        # to the event channel must be serialised (one JSON line at a time).
        self._lock = threading.Lock()

    def _emit(self, ev: dict) -> None:
        if self.enabled:
            with self._lock:
                _sp.emit(ev, stream=self.stream)

    def phase(self, title: str, sub: str = "") -> None:
        self.i += 1
        self._emit({"t": "phase", "i": self.i, "n": self.total, "title": title, "sub": sub})

    def detail(self, text: str) -> None:
        self._emit({"t": "detail", "text": text})

    def substep(self, name: str, i: int, n: int) -> None:
        """A named sub-step within the current phase (e.g. one quality metric of N)."""
        self._emit({"t": "substep", "name": name, "i": i, "n": n})

    def bar(self, desc: str, *, frac, n=None, total=None, elapsed=None, remaining=None) -> None:
        self._emit({"t": "bar", "desc": desc, "frac": frac, "n": n, "total": total,
                    "elapsed": elapsed, "remaining": remaining})

    def heartbeat(self, label: str, secs: int) -> None:
        self._emit({"t": "heartbeat", "label": label, "secs": secs})

    def metrics(self, rows: list, csv: str) -> None:
        self._emit({"t": "metrics", "rows": rows, "csv": csv})

    def done_ok(self, *, units: int, out: str, good=None) -> None:
        self._emit({"t": "done", "ok": True, "units": units, "good": good, "out": str(out)})

    def error(self, message: str) -> None:
        self._emit({"t": "error", "ok": False, "message": message})


# Set in configure_output(); read by AlignedTqdm so library/sorter tqdm bars can
# mirror into the JSON event channel without threading the Reporter through every
# SpikeInterface call site.
_REPORTER: "Reporter | None" = None

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
            self._last_emit_frac = -1.0
            super().__init__(*args, **kwargs)

        def _emit_bar(self) -> None:
            """Mirror the bar's current state into the JSON progress channel.

            Only fires when a Reporter is active (``--progress json``); throttled to
            ~1% steps so a fast inner loop doesn't flood the event channel, and
            always fires on completion.
            """
            rep = _REPORTER
            if rep is None or not rep.enabled:
                return
            total = self.total
            if not total or total <= 0:
                return
            frac = self.n / total
            if frac < 1.0 and frac - self._last_emit_frac < 0.01:
                return
            self._last_emit_frac = frac
            fmt = self.format_dict
            desc = _TQDM_DESC_SUFFIX.sub("", (self.desc or "")).strip()
            rep.bar(
                desc, frac=frac, n=self.n, total=total,
                elapsed=fmt.get("elapsed"),
                remaining=(fmt.get("elapsed", 0) / frac - fmt.get("elapsed", 0)) if frac else None,
            )

        def update(self, *args, **kwargs):
            ret = super().update(*args, **kwargs)
            self._emit_bar()
            return ret

        def refresh(self, *args, **kwargs):
            ret = super().refresh(*args, **kwargs)
            self._emit_bar()
            return ret

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

    def __init__(self, *, quiet: bool, total_phases: int, stderr: bool = False):
        self.quiet = quiet
        self.total = total_phases
        self.n = 0
        # In JSON-progress mode stdout is a clean event channel, so the human
        # rich/plain output is redirected to stderr.
        self._stderr = stderr
        try:
            from rich.console import Console

            self._c = Console(stderr=stderr, highlight=False)
        except Exception:  # rich missing — fall back to plain text
            self._c = None

    def _emit(self, markup: str, plain: str) -> None:
        if self._c is not None:
            self._c.print(markup)
        else:
            print(plain, flush=True, file=sys.stderr if self._stderr else None)

    def banner(self, sorter: str) -> None:
        if self.quiet:
            return
        if self._c is not None:
            self._c.rule(f"[bold]spike sorting[/] · [{self.PALETTE['accent']}]{sorter}[/]")
        else:
            print(f"=== spike sorting · {sorter} ===", flush=True,
                  file=sys.stderr if self._stderr else None)

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
            _f = sys.stderr if self._stderr else None
            print("\n" + df.round(3).to_string(), flush=True, file=_f)
            print(f"saved -> {csv_path}", flush=True, file=_f)

    def done(self, out: Path) -> None:
        self._emit(
            f"\n[{self.PALETTE['ok']}]✓ Done[/] · results in [underline]{out}[/]",
            f"\nDone. ✓  Results in {out}",
        )


def configure_output(level: str, *, json_mode: bool = False, reporter: "Reporter | None" = None) -> bool:
    """Mute library/native chatter and align tqdm bars. Returns ``show_bars``.

    Call this *before* importing spikeinterface so the env vars and the tqdm
    patch are in place before OpenMP/Numba/the sorters initialise. ``show_bars``
    is True only for ``verbose``; ``normal``/``quiet`` keep the high-level step
    messages but draw no progress bars. Warnings are muted at every level — they
    are clutter that breaks up the clean formatting, not the verbose signal.

    When ``json_mode`` the aligned-tqdm patch is installed even with bars off, so
    the library/sorter bars can mirror into the JSON event channel via
    ``reporter`` (stored in the module-level ``_REPORTER`` the patch reads).
    """
    global _REPORTER
    _REPORTER = reporter
    # UTF-8 stdout/stderr first, before rich/tqdm/SI build any console — so the
    # ✓ / → / … glyphs below never raise UnicodeEncodeError on a legacy Windows
    # console code page (cp1252/cp437) when output is redirected or piped. Then
    # mute OpenMP/Numba/probe/resource-tracker noise before the heavy imports.
    bio.use_utf8_stdout()
    bio.mute_native_chatter()

    show_bars = level == "verbose"
    # Patch tqdm when drawing bars OR when JSON mode needs to mirror bar events.
    # The patched class is a no-op for the event channel unless _REPORTER.enabled,
    # so installing it in JSON mode never changes plain-CLI behaviour.
    if show_bars or json_mode:
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


def _ext_compute(analyzer, ext: str):
    """Return a 0-arg closure that computes one analyzer extension by name.

    A named function (not an inline lambda) so the captured ``ext`` binds eagerly —
    avoids the classic late-binding-loop bug when building a list of these.
    """
    return lambda: analyzer.compute(ext)


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
        "probe": args.probe,
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


def _friendly_sort_error(exc: Exception, use_docker: bool = False) -> str:
    """Turn a sort failure into a one-line, actionable message (no traceback)."""
    text = str(exc)
    # Decide "Docker is down" by asking the daemon, not by string-matching the
    # message — the old substring check mislabelled unrelated failures (e.g. a
    # missing SDK or a sorter crash that merely mentions "docker") as a dead daemon.
    if use_docker and not sorters.docker_available(refresh=True):
        return "Docker isn't running — open Docker Desktop and try again."
    if use_docker:
        return ("Docker sort failed — the sorter's container image may be "
                f"incompatible, or still downloading. Details:\n{text}")
    return f"Sorting failed: {text}"


def _quality_summary(qm) -> "tuple[int, int | None]":
    """Rule-of-thumb count of 'good-looking' units: SNR ≥ 5 and few ISI violations.

    Returns ``(n_total, n_good)``; ``n_good`` is None if the expected columns are
    missing. This is a sanity signal to orient a newcomer ("did anything good come
    out?"), NOT a substitute for manual curation.
    """
    try:
        good = (qm["snr"] >= 5.0) & (qm["isi_violations_ratio"] <= 0.5)
        return len(qm), int(good.sum())
    except Exception:  # noqa: BLE001 - metric columns can vary; degrade gracefully
        return len(qm), None


def _prepare_docker_image(ui: "ConsoleUI", sorter: str) -> None:
    """Pre-download the sorter's Docker image with a live progress bar.

    Otherwise the first containerised run fetches ~1-2 GB behind a single terse
    'pulling image' line and a long silent gap — so it looks hung. Pulling it
    ourselves first turns that into a real progress bar (bytes + % + elapsed).
    Best-effort: on any hiccup we fall back to letting SpikeInterface pull it.
    """
    image = sorters.default_docker_image(sorter)
    if not image:
        return
    if sorters.docker_image_present(image):
        ui.detail(f"Docker image already downloaded ({image}) — using the cached copy.")
        return
    ui.detail(f"Downloading the {sorter} Docker image: {image}")
    ui.detail("One-time ~1–2 GB download — this can take a few minutes.")
    console = getattr(ui, "_c", None)
    if console is None or ui.quiet:
        ok = sorters.pull_docker_image(image)        # no bar (rich missing / quiet)
    else:
        from rich.progress import (BarColumn, DownloadColumn, Progress,
                                    SpinnerColumn, TextColumn, TimeElapsedColumn)
        with Progress(
            SpinnerColumn(),
            TextColumn("[cyan]{task.description}[/]"),
            BarColumn(),
            DownloadColumn(),
            TimeElapsedColumn(),
            console=console, transient=True,
        ) as prog:
            task = prog.add_task("downloading", total=None)

            def on_progress(done, total):
                prog.update(task, completed=done, total=total or None)

            def on_status(status):
                prog.update(task, description=status.lower())

            ok = sorters.pull_docker_image(image, on_progress=on_progress, on_status=on_status)
    if ok:
        ui.result("✓ image downloaded")
    else:
        ui.detail("Couldn't pre-download with a progress bar — "
                  "SpikeInterface will fetch the image during the run.")


# A line that is just a tqdm bar (or carriage-return progress spam) — not an
# informative sorter print worth mirroring as a 'detail' event. tqdm bars carry a
# "%|" gauge or an "it/s]" rate tail; lone carriage returns are redraw spam.
_TQDM_LINE = re.compile(r"%\||it/s\]|\d+\.\d+s/it\]")


def _is_informative_line(text: str) -> bool:
    """True when ``text`` is a real sorter step print (not a tqdm bar / CR spam)."""
    s = text.strip()
    if not s:
        return False
    return _TQDM_LINE.search(s) is None


class _StdoutTee:
    """Capture sorter ``print()`` output on **fd 1** and forward it two ways.

    In ``--progress json`` mode the event channel is the *real* stdout (duped aside
    before this runs), so fd 1 is free to repurpose. Sorters write informative step
    lines (``detect_peaks(): 562 peaks found`` …) straight to fd 1 with ``print()``;
    the old code sent fd 1 → stderr and lost them to the event consumer.

    Instead we point fd 1 at an ``os.pipe()`` and run a daemon reader thread that,
    for every line, (a) echoes it to the **real stderr** (so the human terminal is
    unchanged) and (b) emits an informative, non-tqdm line as a ``detail`` event via
    ``reporter`` — so the UI sees the sorter's progress prints live. tqdm bars still
    go to fd 2 (the real stderr) untouched; the event channel stays pure JSON.

    A no-op (``enabled=False``) outside JSON mode, so plain-CLI behaviour is
    byte-identical.
    """

    def __init__(self, reporter: "Reporter | None", *, enabled: bool):
        self.reporter = reporter
        self.enabled = enabled
        self._os = __import__("os")
        self._saved_fd1 = None          # original fd 1, restored on exit
        self._real_stderr_fd = None     # a dup of fd 2 the reader echoes to
        self._write_fd = None           # pipe write end (fd 1 points here)
        self._read_fd = None            # pipe read end (the reader thread reads)
        self._thread: "threading.Thread | None" = None

    def __enter__(self):
        if not self.enabled:
            return self
        os = self._os
        sys.stdout.flush()
        # Keep a private copy of the original fd 1 and of the real stderr so we can
        # restore fd 1 and echo human-visible lines after the pipe is torn down.
        self._saved_fd1 = os.dup(1)
        self._real_stderr_fd = os.dup(2)
        self._read_fd, self._write_fd = os.pipe()
        os.dup2(self._write_fd, 1)                    # fd 1 -> pipe write end
        # Rebuild sys.stdout on the new fd 1 so Python-level prints flow through too.
        sys.stdout = os.fdopen(os.dup(1), "w", buffering=1)
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        return self

    def _reader(self) -> None:
        os = self._os
        with os.fdopen(self._read_fd, "r", buffering=1, errors="replace") as pipe:
            for line in pipe:
                # Echo to the real terminal stderr so the human sees it unchanged.
                try:
                    os.write(self._real_stderr_fd, line.encode("utf-8", "replace"))
                except OSError:
                    pass
                if self.reporter is not None and _is_informative_line(line):
                    self.reporter.detail(line.strip())

    def __exit__(self, *exc) -> None:
        if not self.enabled:
            return
        os = self._os
        # Flush any buffered Python writes, then restore fd 1 and close the pipe
        # write end so the reader hits EOF and the loop ends.
        try:
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass
        os.dup2(self._saved_fd1, 1)                   # restore real fd 1
        sys.stdout = os.fdopen(os.dup(1), "w", buffering=1)
        os.close(self._write_fd)                      # EOF for the reader
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        for fd in (self._saved_fd1, self._real_stderr_fd):
            try:
                os.close(fd)
            except OSError:
                pass


class _Heartbeat:
    """Periodic 'still working' line so a long, silent container step (image setup,
    in-container install, the sort itself) never looks frozen. No-op when quiet."""

    def __init__(self, ui: "ConsoleUI", label: str, every: float = 25.0,
                 reporter: "Reporter | None" = None):
        self.ui, self.label, self.every = ui, label, every
        self.reporter = reporter
        self._stop = threading.Event()
        self._t: "threading.Thread | None" = None
        self._t0 = 0.0

    def __enter__(self):
        # Start the thread when the human cares (not quiet) OR when JSON-progress
        # is on (so the consumer still gets a "still working" pulse while quiet).
        if not self.ui.quiet or (self.reporter is not None and self.reporter.enabled):
            self._t0 = time.monotonic()
            self._t = threading.Thread(target=self._run, daemon=True)
            self._t.start()
        return self

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            el = int(time.monotonic() - self._t0)
            self.ui.detail(f"… {self.label} — still working ({el // 60}m{el % 60:02d}s elapsed)")
            if self.reporter is not None:
                self.reporter.heartbeat(self.label, el)

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._t is not None:
            self._t.join(timeout=0.2)


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
    parser.add_argument(
        "--probe",
        choices=["a1x16", "independent"],
        default="a1x16",
        help="Electrode geometry. 'a1x16' (default) = the real NeuroNexus "
        "A1x16-3mm-100-703 (16 sites, one column, 100 µm) so the sorter sees real "
        "spatial neighbours; 'independent' = the placeholder layout (250 µm, no "
        "neighbours) for arrays without a known geometry.",
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
    parser.add_argument(
        "--progress", choices=["plain", "json"], default="plain",
        help="plain CLI output (default) or newline-delimited JSON events on stdout "
        "(human/rich output then goes to stderr) — used by the in-UI sort screen.",
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

    json_mode = args.progress == "json"
    total_phases = 3 if args.no_metrics else 4
    # In JSON mode stdout must be a *pure* event channel, but sorters/libraries
    # write status lines straight to stdout (fd 1, bypassing sys.stdout). So we
    # dup the real stdout aside for the Reporter to emit events on, then point
    # fd 1 (and sys.stdout) at stderr for the rest of the run — any other write
    # to stdout then lands on stderr, off the event channel.
    event_stream = sys.stdout
    if json_mode:
        os = __import__("os")
        saved_fd = os.dup(1)                       # the real stdout, for events
        event_stream = os.fdopen(saved_fd, "w", buffering=1)
        sys.stdout.flush()
        os.dup2(2, 1)                              # fd 1 -> stderr
        sys.stdout = os.fdopen(os.dup(1), "w", buffering=1)
    rep = Reporter(enabled=json_mode, stream=event_stream, total_phases=total_phases)

    # Configure output BEFORE importing spikeinterface so env vars / the tqdm
    # patch land before OpenMP/Numba/the sorters initialise. In JSON mode the
    # tqdm patch is installed too (it mirrors bar events into the event channel).
    show_bars = configure_output(args.verbosity, json_mode=json_mode, reporter=rep)
    quiet = args.verbosity == "quiet"
    # In JSON mode stdout is the clean event channel, so the human ConsoleUI
    # output goes to stderr.
    ui = ConsoleUI(quiet=quiet, total_phases=total_phases, stderr=json_mode)

    import spikeinterface.full as si
    import spikeinterface.preprocessing as spre
    import spikeinterface.sorters as ss

    # Drive SI's own tqdm bars when drawing them OR in JSON mode (so the patched
    # tqdm fires bar events); in JSON mode they render on stderr, off the channel.
    si.set_global_job_kwargs(n_jobs=args.n_jobs, progress_bar=show_bars or json_mode)

    out = Path(args.output_dir) if args.output_dir else (bio.REPO_ROOT / "outputs" / args.sorter)
    out.mkdir(parents=True, exist_ok=True)

    ui.banner(args.sorter)
    _warn_existing_sort(out, ui)  # flag (don't block) before we overwrite it

    ui.phase("Read broadband", "(.ns5)")
    rep.phase("Read broadband", "(.ns5)")
    rec = bio.read_broadband(args.data_dir)  # placeholder independent-channel probe attached
    total_seconds = rec.get_total_duration()
    _ch_detail = (f"{rec.get_num_channels()} channels · "
                  f"{rec.get_sampling_frequency():g} Hz · {total_seconds:.1f}s")
    ui.detail(_ch_detail)
    rep.detail(_ch_detail)

    # Drop non-neural analog aux channels (ids 10241+, 'analog N') before sorting:
    # left in, they corrupt the common median reference and can spawn fake units.
    n_dropped = 0
    _drop_msg = ""
    if not args.keep_analog:
        neural = bio.neural_channel_ids(rec)
        n_dropped = rec.get_num_channels() - len(neural)
        if 0 < len(neural) < rec.get_num_channels():
            rec = bio.select_channels(rec, neural)
            _drop_msg = (f"excluded {n_dropped} non-neural analog aux channel(s) → "
                         f"sorting {len(neural)} electrode(s)")
            ui.detail(_drop_msg)

    # Attach electrode geometry AFTER the channel drop, so the contact count matches
    # the kept electrodes. Default = the real NeuroNexus A1x16-3mm-100-703 (16 sites,
    # 100 µm) so the sorter uses true spatial neighbours and the GUI shows real depth;
    # falls back to the independent-channel placeholder (250 µm) for --probe independent
    # or any array that isn't the expected 16 channels.
    if args.probe == "a1x16" and rec.get_num_channels() == bio.A1X16_N_CONTACTS:
        rec = bio.attach_a1x16_probe(rec)
        _probe_msg = (f"geometry: NeuroNexus A1x16-3mm-100-703 "
                      f"({bio.A1X16_N_CONTACTS} ch · {bio.A1X16_PITCH_UM:g} µm linear)")
    else:
        rec = bio.attach_dummy_probe(rec)
        _probe_msg = f"geometry: independent-channel placeholder ({rec.get_num_channels()} ch · 250 µm)"
        if args.probe == "a1x16":
            _probe_msg += f" — A1x16 needs {bio.A1X16_N_CONTACTS} channels, got {rec.get_num_channels()}"
    ui.detail(_probe_msg)
    rep.detail(_probe_msg)

    fs = rec.get_sampling_frequency()
    freq_max = min(args.freq_max, 0.49 * fs)  # keep the high cutoff below Nyquist
    ui.phase("Preprocess", "bandpass + common median reference")
    rep.phase("Preprocess", "bandpass + common median reference")
    # Mirror the real preprocess sub-steps onto the event channel so the consumer
    # sees each one (channel drop, bandpass, common median reference, frame slice).
    if _drop_msg:
        rep.detail(_drop_msg)
    if freq_max < args.freq_max:
        _clamp_msg = f"clamped bandpass high cutoff to {freq_max:g} Hz for {fs:g} Hz Nyquist"
        ui.detail(_clamp_msg)
        rep.detail(_clamp_msg)
    _band_msg = f"bandpass {args.freq_min:g}–{freq_max:g} Hz"
    ui.detail(f"{_band_msg} · common median reference")
    rep.detail(_band_msg)
    rec = spre.bandpass_filter(rec, freq_min=args.freq_min, freq_max=freq_max)
    rep.detail("common median reference")
    rec = spre.common_reference(rec, reference="global", operator="median")
    if args.duration is not None:
        n_samples = rec.get_num_samples()
        end = min(int(args.duration * fs), n_samples)
        rec = rec.frame_slice(0, end)
        _slice_msg = f"limited to first {end / fs:g}s of {n_samples / fs:g}s"
        ui.detail(_slice_msg)
        rep.detail(_slice_msg)
    effective_seconds = rec.get_total_duration()

    use_container = sorters.uses_docker(args.sorter, args.docker)
    _sort_sub = args.sorter + ("  (docker)" if use_container else "")
    ui.phase("Sort", _sort_sub)
    rep.phase("Sort", _sort_sub)
    if args.docker and not use_container:
        ui.detail(f"{args.sorter} is installed — running it natively (no Docker needed)")
    if overrides:
        ui.detail("overrides: " + ", ".join(f"{k}={v}" for k, v in overrides.items()))
    if use_container:
        try:
            _prepare_docker_image(ui, args.sorter)
        except Exception:  # noqa: BLE001 - pre-pull is best-effort; SI will pull if needed
            ui.detail("(couldn't pre-download with a progress bar — SpikeInterface "
                      "will fetch the image during the run.)")
        ui.detail("Starting the container and running the sorter. On the first run "
                  "SpikeInterface also installs itself inside the container "
                  "(1–3 min, little output) — the lines below come from it.")
    # A heartbeat reassures during long silent stretches: always for Docker (the
    # sort runs out-of-process in the container), for a native sort whenever
    # progress bars are off (normal/quiet), and always in JSON mode (the consumer
    # gets no tqdm bars for the silent sorter steps, so it needs the pulse) — so a
    # multi-minute sort never looks hung.
    if use_container:
        hb = _Heartbeat(ui, f"{args.sorter} in Docker", reporter=rep)
    elif not show_bars or rep.enabled:
        hb = _Heartbeat(ui, args.sorter, reporter=rep)
    else:
        hb = contextlib.nullcontext()
    # In JSON mode, tee the sorter's fd-1 prints into 'detail' events so the two
    # longest phases stop being black boxes (the human terminal is unchanged: the
    # tee echoes every line to the real stderr). A no-op outside JSON mode.
    tee = _StdoutTee(rep, enabled=rep.enabled)
    try:
        with tee, hb:
            sorting = sorters.run(
                args.sorter,
                rec,
                out / "sorter_output",
                params=overrides,
                use_docker=args.docker,
                verbose=show_bars,
            )
    except Exception as e:  # noqa: BLE001 - show a friendly message, not a traceback
        # Use whether a container was ACTUALLY used (not the raw --docker flag): a
        # native sort that failed while Docker happens to be down isn't a Docker problem.
        message = _friendly_sort_error(e, use_docker=use_container)
        ui.warn(message)
        rep.error(message)
        return 1
    n_units = len(sorting.get_unit_ids())
    if n_units == 0:
        ui.warn("No units detected. Try lowering 'detect_threshold' (Edit sorter "
                "parameters), sorting more data (drop --duration), or another sorter.")
    else:
        ui.result(f"{n_units} units found")

    _robust_rmtree(out / "sorting")  # retry past Windows GUI file-locks before overwrite
    sorting = sorting.save(folder=str(out / "sorting"), overwrite=True)

    n_high_quality = None
    if not args.no_metrics and n_units > 0:
        ui.phase("Quality metrics", "(SortingAnalyzer)")
        rep.phase("Quality metrics", "(SortingAnalyzer)")
        # In JSON mode tee the analyzer's fd-1 prints into 'detail' events too — the
        # ~8 compute sub-steps otherwise run silently on the event channel.
        metrics_tee = _StdoutTee(rep, enabled=rep.enabled)
        # JSON mode only: the consumer gets no tqdm bars for the silent compute
        # sub-steps, so pulse it. Plain CLI output is left byte-identical (no hb here).
        metrics_hb = (_Heartbeat(ui, "computing quality metrics", reporter=rep)
                      if rep.enabled else contextlib.nullcontext())
        with metrics_tee, metrics_hb:
            _robust_rmtree(out / "analyzer")  # retry past Windows GUI file-locks before overwrite
            # sparse=False (dense): SpikeInterface defaults to sparse=True, which keeps
            # only the channels within ~100 µm of each unit's peak. The placeholder probe
            # (attach_dummy_probe) spaces channels 250 µm apart so NO channel is within that
            # radius — sparsity would collapse every unit to its single peak channel and the
            # spikeinterface-gui inspector could then only ever show one channel per unit.
            # With this small array (16 ch) dense is cheap and always shows the full layout;
            # it is the honest choice while geometry is a placeholder, and harmless once a
            # real probe (e.g. NeuroNexus A1x16, 100 µm) is attached.
            analyzer = si.create_sorting_analyzer(
                sorting, rec, folder=str(out / "analyzer"), format="binary_folder",
                overwrite=True, sparse=False,
            )
            # One compute per extension so each shows a named 'substep' the moment it
            # starts; i/n span the whole metrics phase (base + metrics + curation).
            # Base + quality_metrics are core (must succeed); the curation/inspector
            # extensions stay best-effort (one bad one is skipped, not fatal).
            base_steps = [
                ("random_spikes", lambda: analyzer.compute("random_spikes")),
                ("waveforms", lambda: analyzer.compute("waveforms")),
                ("templates", lambda: analyzer.compute("templates")),
                ("noise_levels", lambda: analyzer.compute("noise_levels")),
                ("quality_metrics", lambda: analyzer.compute(
                    "quality_metrics", metric_names=["firing_rate", "snr", "isi_violation"])),
            ]
            curation_steps = [(ext, _ext_compute(analyzer, ext)) for ext in _CURATION_EXTENSIONS]
            n_steps = len(base_steps) + len(curation_steps)
            for i, (name, fn) in enumerate(base_steps, start=1):
                rep.substep(name, i, n_steps)
                fn()  # core extension — let a real failure surface as before
            qm = analyzer.get_extension("quality_metrics").get_data()
            qm.to_csv(out / "quality_metrics.csv")
            ui.detail("computing GUI-inspector extensions (correlograms, ISI, amplitudes, "
                      "locations, similarity, PCA) …")
            for j, (name, fn) in enumerate(curation_steps, start=len(base_steps) + 1):
                rep.substep(name, j, n_steps)
                try:
                    fn()
                except Exception as e:  # noqa: BLE001 - optional curation data, keep going
                    ui.detail(f"  skipped {name} ({type(e).__name__})")
        ui.metrics(qm, out / "quality_metrics.csv")
        if rep.enabled:
            rows = [{"unit": idx, **{c: (int(r[c]) if "count" in c else float(r[c]))
                                    for c in qm.columns}}
                    for idx, r in qm.iterrows()]
            rep.metrics(rows, str(out / "quality_metrics.csv"))
        n_total, n_high_quality = _quality_summary(qm)
        if n_high_quality is not None:
            ui.result(f"{n_high_quality} of {n_total} units look high-quality "
                      "(SNR ≥ 5 and few ISI violations — a rough signal, not a substitute "
                      "for manual curation)")

    _write_run_info(
        out, args, si_version=si.__version__, sorter=args.sorter,
        n_units=n_units, n_high_quality=n_high_quality,
        channel_ids=list(rec.get_channel_ids()),
        n_dropped_analog=n_dropped, total_seconds=total_seconds,
        effective_seconds=effective_seconds, freq_min=args.freq_min, freq_max=freq_max,
    )

    # The container-only binary copy of the recording is no longer needed.
    _robust_rmtree(out / "recording_for_docker")
    if n_units == 0:
        # Don't leave a previous run's analyzer/metrics behind — they'd report a
        # stale unit count while the saved sorting says 0 (sidebar/report read them).
        _robust_rmtree(out / "analyzer")
        (out / "quality_metrics.csv").unlink(missing_ok=True)
        ui.warn(f"Saved to {out}, but no units were found — adjust parameters and re-run.")
        rep.done_ok(units=0, out=out, good=0)
        return 0
    ui.done(out)
    rep.done_ok(units=n_units, out=out, good=n_high_quality)
    ui.detail("saved: sorting/ · analyzer/ · quality_metrics.csv")
    ui.detail("next: build a report, open the inspector GUI, or compare sorters "
              "(from the menu, or scripts/make_report.py).")
    if args.duration is not None:
        ui.detail(f"note: this sorted only the first {args.duration:g}s — "
                  "re-run without --duration for the full recording.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
