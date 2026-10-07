# NORTHSTAR.md - what this tool is becoming, and the decisions of record

The product spec for the SpikeInterface workbench and the home of dated decisions. When a
session and this file disagree, this file wins; when Ben's live word and this file disagree,
update this file. Method lives in `LOOPS.md`; per-brief detail in `goals/`; the live queue in
`ROADMAP.md`.

## The product

**A spike-sorting workbench a researcher can trust and operate alone** - built for the UPitt
(University of Pittsburgh) researchers in Tracy's lab, whose recordings this repo's
`PFCM7_d0ephys_Block2` block comes from, by **Benjamin Faibussowitsch in collaboration with
Aleece Al-Olimat**. The lab wants the industry-standard **SpikeInterface** underneath; the
workbench is the trustworthy, operable face on it. It takes a raw Blackrock/Ripple recording
to **curated, reproducible, shareable single units**: load → sort → inspect → curate →
report, on the lab's own machine, without the operator needing to know SpikeInterface,
Docker, or quality-metric lore.

**Their probes have different setups**, so probe flexibility is a core requirement: the
workbench must let a researcher describe, import, verify, and switch electrode geometries.

**Where it stands: Spike 2.0 is the baseline** (`goals/GOAL_V2.md`). The full loop works on
the one recording: sort with four local sorters (Docker fallback for others), judge units on
their real evidence, curate (merge / split / label, Phy round trip), re-score, and share
reports, with every run versioned and re-runnable from its recipe and every setting
editable in the app. Not yet proven: the lab's Windows+GPU box (the Windows audit, then GPU
sorters), recordings beyond this block, and what the lab needs first.

## Direction

From the Spike 2.0 baseline, improve the UI/UX and the functionality. Ben sets the queue in
`ROADMAP.md`. The deployment target is the lab's **Windows box with an NVIDIA GPU**, so every
change must hold on Windows, not just macOS.

## Product laws

- **Honesty**: wrong-and-loud beats wrong-and-quiet. No mock/sample-data fallback, honest
  empty/error/0-unit states, caveats surfaced where the user decides (not flashed past).
- **Science invariants are non-negotiable**: the aux-drop-before-CMR ordering, the µV
  double-scaling gate, the ~4 µV noise-floor canary, the analyzer as the single source of
  truth. They live in `docs/INVARIANTS.md`; briefs inherit them without restating.
- **Single source of truth per module** (`docs/ARCHITECTURE.md`'s module map). New capability
  extends the owning module; a second implementation of the same fact is a defect.
- **Cross-platform is load-bearing**: macOS is where Ben builds, Windows is where the lab
  runs. A feature that works only on the Mac is not done.
- **Raw data never leaves the machine or enters git** (the `.ns5` is ~176 MB; a fresh clone
  has no data). Cloud/remote agents can do code-only work; nothing that needs the recording.

## Decisions of record (in force)

Superseded decisions are retired to git history (tag `pre-cleanup-2026-10-06`).

- **2026-06 (PR #1)** - probe geometry is real: `probes.py` owns it, default
  `nnx-a1x16-3mm-100` (NeuroNexus A1x16-3mm-100-703).
- **2026-08-18 (Ben)** - the UI/UX mandate: every surface accessible, uncluttered, focused on
  what matters, with clean hierarchy and ample room, and a UX that gives timely updates and
  results while it works. `DESIGN_UX.md` §1 binds all surface work.
- **2026-08-18 (Ben)** - the build runs autonomously: sessions execute the ROADMAP queue in
  dependency order without waiting for per-item pastes, sealing per `LOOPS.md` as they go.
- **2026-08-19 (Ben, the interview)** - the merges: quality-rule defaults stay unchanged;
  the path is split-the-merges (the merge advisory and Phy prep in the tool, Ben splits in
  Phy), since no swept sorter splits them. **No adapter map is coming**: channel→site
  identity wiring is the standing assumption (reopen only if a map ever arrives). No em
  dashes anywhere in the repo. Periwinkle is the palette anchor across all surfaces.
- **2026-09-27 (Ben, "build it and then test")** - Spike 2.0 from the v2.0 mockups
  (`goals/GOAL_V2.md` is the spec of record): the journey rail (1 Data · 2 Probe · 3 Sort ·
  4 Judge · 5 Apply · 6 Share) with one next step on Home; `1`-`6` are stage keys; every
  setting editable in place and reproducible. The terminal is the face; a web or wizard face
  reopens only if the lab asks for one.
- **2026-10-06 (Ben)** - **Opus 5.5 for every run and every review** (`LOOPS.md` doctrine 5).
  Spike 2.0 is the baseline: the old ROADMAP, SEALS ledger and version-specific lessons are
  retired to git, and the next queue starts from Ben's direction.

## Open questions (kept open on purpose - answers land here as dated decisions)

- **What Tracy's lab actually needs first** - users, their fluency, the recordings beyond
  this block, whether curation or batch is the pain.
- **GPU sorters on the lab box**: which (kilosort4 first?), and how validated against the
  local sorters on the same recording.
