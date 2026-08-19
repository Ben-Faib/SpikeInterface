# GOAL W2 — The Reproducibility Engine: every result regenerable from its own record

## Intent

A result the lab can't regenerate is a result it can't defend — to a reviewer, a grant's
rigor section, or itself six months later. Today re-sorting clobbers `outputs/<sorter>/` in
place, a quick `--duration` smoke can silently replace a full sort, and `run_info.json` omits
the effective sorter params, seed, and environment. This phase (audit Path 4,
WORKBENCH_DIRECTIONS.md §"Path 4" — the full design lives there) makes runs versioned,
provenance complete, and regeneration checkable. It pairs with W1 — both re-touch the run
store, and doing them adjacently avoids re-architecting it twice.

## Task (slices)

1. **The versioned run store.** Runs land in per-run directories (timestamped/id'd) instead
   of overwriting; the "current" sort per sorter is a pointer, not the only copy; smoke runs
   can never clobber full runs. Downstream consumers (report, compare, menu INSPECTING,
   curation records from W1) resolve through the pointer.
2. **Complete provenance.** The run record carries: the effective sorter parameter dict
   (defaults + overrides actually used), probe id + geometry hash, seed where the sorter
   accepts one, package versions (SI/neo/numpy at least), git commit of this repo, platform,
   and the preprocessing chain. `.si_menu.json` overrides are copied into the record at run
   time, not referenced.
3. **Regenerate-from-record.** A command that re-runs a sort from a run record alone and
   reports what matched (unit count, metrics within stated tolerance — bit-identity is the
   goal where the sorter is deterministic; where it isn't, say so in the record rather than
   pretending).
4. **Config-as-code.** A run is describable as a small committed config file the CLI accepts,
   so "the sort we published" is a file in git, not a memory.

## Definition of done

Suite + smoke green, canary ~4 µV; two runs of the same sorter coexist on disk and the menu/
report show the right one with its provenance visible; the regenerate command, run against a
fresh record, reproduces the sort and prints an honest match report; a smoke run demonstrably
cannot displace a full run. Fresh-context Fable review per slice.

## Boundaries and known traps

- Migration matters: existing saved sorts under `outputs/<sorter>/` must keep working
  (read-only legacy resolution) — don't strand the user's current results.
- Quality-metrics-are-non-fatal stands, including the cleanup contract for half-built
  derived data.
- Don't invent determinism: sorters with stochastic clustering get tolerance-based
  verification with the tolerance stated in the record. **Measured evidence (PRE1,
  2026-08-18): tridesclous2 on this recording gave 14, 16, and 18 units across three
  identical full-pipeline runs (RNG state ruled out — the spread exists between runs
  making zero extra RNG calls), and one run split a unit pair another run merged.**
  Unit counts and ids are not reproduction criteria here; design the match report
  around what is stable (channels, containment against a reference, metric ranges).
- `--progress json` stdout purity holds through any new run-store output.
- Keep `outputs/` gitignored; provenance records are data about runs, and run data stays
  local. The committable artifact is the config file, never the outputs.
