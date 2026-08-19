# GOAL WD - Lab deployment: the workbench proven on the machine that matters

## Intent

The tool is built on a Mac but lives or dies on the UPitt lab's **Windows box with an NVIDIA
GPU**. Deployment is not a phase at the end - it's a standing track that runs whenever
lab-box access exists, so platform breakage is caught per-phase instead of at handoff. The
GPU also changes the product: kilosort-class sorters are never offered on this Mac but become
real there.

## Task (standing, in rough order)

1. **Repeatable install.** `run.bat`/`run.ps1` + `uv sync` proven on the lab box from a
   fresh clone (no data in git - document how the lab's recordings get placed/pointed at via
   the data-dir flow). Any friction found becomes a fix or a documented step, not lore.
2. **The full journey on Windows.** Menu → explore → sort (`--duration 30`, then full) →
   report → compare, with the suite green and the ~4 µV canary holding. Known Windows traps:
   `spawn` requires the `main()`-returns-int entry-point convention; POSIX-only process
   handling (`os.killpg` in the sort modal) needs a Windows-safe path; Docker-on-Windows
   sort cleanup already bit once (fixed 7940f96 - re-verify there).
3. **GPU sorters.** Enable and validate kilosort4 (first) on the lab box: install path,
   a successful sort of this recording, metrics sanity vs the local sorters on the same
   window, and honest surfacing in the sorter catalog (the GPU group stops being
   "never offered" where a GPU exists).
4. **Lab acceptance.** A lab member (Tracy or designee) walks load → sort → report on their
   own machine without Ben driving. Their friction list becomes the next quick-wins set.

## Definition of done (per item - the track never fully closes)

Each item's claim is proven by a run on the lab box (or an equivalent Windows environment,
stated as such), recorded in SEALS.md with what was run and what it showed. Item 3
additionally records the GPU sort's summary metrics next to a local sorter's for the same
window.

## Boundaries and known traps

- Nothing macOS-only lands anywhere in the repo (CLAUDE.md convention: pathlib, cross-
  platform, Python 3.12 for wheel coverage - don't bump).
- Raw data never enters git and never leaves lab/local machines.
- Qt: PySide6 under uv, PyQt5 under conda - never both in one env.
- Version skew is a known false-alarm source (LESSONS S2: a "failed" containerized sort was
  host↔container SI version skew; the sort itself had succeeded). Check versions before
  blaming a sorter.
