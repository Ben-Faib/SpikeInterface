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

## Recorded follow-ups (from the slice-2 seal, 2026-08-18)

- **run_sorting seam promotion**: `curation.apply_record` rebuilds the curated
  analyzer+metrics by mirroring run_sorting's steps; promote ONE public
  analyzer-build+metrics function in run_sorting and call it from both, so the
  two can't drift.
- **`curation.py import-gui`** (sigui ingestion): decisions made inside
  spikeinterface-gui are not yet captured into the record — an explicit scope
  shift off slice 2; the record schema (source= provenance) is ready for it.
- **Seeded 3-way GMM split method**: the slice-2 review measured it as an
  incremental gain over the shipped k-means on the merged pairs (residue still
  swamps within-unit splits — leverage is upstream); optional, not implemented.

## Recorded follow-ups (from the slice-3 review, 2026-08-18)

- **Seeded-quality echo (F4)**: the export seeds current labels into
  cluster_quality.tsv; if Ben relabels a unit by hand after export, an untouched
  cluster's stale seeded value imports back as a fake "phy" verdict (loud, but
  misattributed). Fix shape: record seeded labels in the manifest; import treats
  a quality value identical to its seed as "no verdict" (a group edit always wins).
- **Seeding skips the identity check (F5)**: a stale record beside a fresh sort
  seeds old labels onto same-numbered new units (import is refused later, but the
  curation session was already poisoned). Skip seeding + say why when the record's
  anchor doesn't match disk.
- **`--out` re-import hint (F6)**: after `export-phy --out <dir>`, the printed
  next step omits `--from <dir>` and would read the default folder.
- **rc 0 on all-rejected import (F7)**: "imported 0, rejected N" exits 0;
  scripted callers see success.
- **Verify Phy's label snippet (F8)**: the docstring's `:quality unsure` is
  likely `:l quality unsure` — verify once on a machine with Phy installed.
- **Anchor `probe` field null on bare CLI sorts (F10, pre-existing)**:
  run_sorting records `probe` from the flag only, so one of the anchor's seven
  fields never binds for bare CLI runs; created+n_units carry it.

## Recorded follow-ups (from the slice-4 review, 2026-08-19 — verdict ship, all hardening)

- **TOCTOU on the no-record first label**: triage open → concurrent CLI re-sort →
  first keypress anchors a fresh record to the NEW run_info while the screen shows
  the old sort's units. Fix shape: triage_state returns the run identity it
  rendered; label_unit verifies it before writing. (Revisit after W2's store —
  run dirs change the shape.)
- **Corrupt record silently replaced** (pre-existing): load_record returns None
  for malformed JSON, indistinguishable from absent → first write overwrites the
  corrupt audit trail. Distinguish unparseable from absent; refuse via anchor_error.
- **Empty-state wording after a metrics crash**: triage says "no saved sort —
  press 2 to sort" when sorting/ exists and only derived data was cleaned;
  rebuilding metrics is the honest next step.
- **_TRIAGE_KEYS vocabulary unpinned**: duplicates QUALITY_OPTIONS with only a
  comment; one test asserting the sets match would pin it.
- **Scope note**: the controller's spike counts read the loose sorting/ folder
  (best SI-free-adjacent source; run_sorting rewrites it every run). CLAUDE.md's
  "leftovers — ignore" line is scoped to report.py and stays true.
