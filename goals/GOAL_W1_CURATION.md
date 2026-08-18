# GOAL W1 — The Curation Workbench: candidate units → defensible single units

## Intent

"No curation loop" is the single most-cited gap across the audit's UX, Pipeline, and
Ecosystem sections: the workbench can open an inspector but decisions don't flow back, so the
report always reflects raw sorter output — never publishable as-is. This phase (audit Path 1,
WORKBENCH_DIRECTIONS.md §"Path 1: The Curation Workbench" — read it; it carries the full
design discussion and mockups) turns a sort into a curated, auditable result the lab can
defend. W0's widened metric base is the precondition and must be sealed first.

## Task (slices — one goal run each, in order)

1. **Defensible auto-curation.** Replace the hardcoded `snr>=5 & isi<=0.5` "high-quality"
   headline with a configurable threshold rule grounded in standard practice (e.g.
   amplitude_cutoff, presence_ratio, isi_violations_ratio), owned in one place
   (`sort_summary` is the metrics owner), surfaced with its thresholds stated wherever the
   count appears — never a bare "N look high-quality".
2. **The curation lifecycle.** Persist manual decisions from spikeinterface-gui (merges,
   splits, labels) via SI's curation model: save the curation record, apply it to produce a
   curated Sorting as a first-class output, recompute metrics/analyzer on it, and let the
   report/menu surfaces show curated-vs-raw honestly (which one is displayed is always
   stated).
3. **Phy export.** `export_to_phy` as a menu action + CLI flag, and a documented path for
   round-tripping Phy's labels back into the curation record.
4. **In-TUI unit triage (light).** A unit list in the menu with per-unit metrics and
   accept/reject/noise labeling writing the same curation record — the lightweight loop
   for decisions that don't need a Qt window.

## Definition of done (per slice, plus the phase)

Suite + sort smoke green with the ~4 µV canary; the curation round-trip proven end-to-end on
a real sort of this recording: sort → label/merge in the GUI (or TUI) → curated Sorting saved
→ metrics recomputed → report renders the curated result with honest provenance ("curated
from <run>, N decisions"). Curation records survive relaunch. Phy export opens in Phy or is
verified structurally if Phy isn't installed locally (say which). Fresh-context Fable review
per slice.

## Boundaries and known traps

- The analyzer stays the single source of truth: curated outputs get their own analyzer;
  nothing reads the loose `sorting/` folder or stale CSVs.
- Curation must never mutate or overwrite the raw sort it came from — raw is the audit
  trail. (W2 makes runs versioned; until then, guard the raw outputs by construction.)
- Six-metrics ownership stands: new metrics/thresholds land in `sort_summary`/one owner,
  computed once, surfaced everywhere from that one place.
- The menu view still imports no SpikeInterface — curation state reaches the view through
  the controller Protocol like everything else.
- Windows is a target: no POSIX-only process tricks in any new GUI/export path.
