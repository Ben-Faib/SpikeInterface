# NORTHSTAR.md — what this tool is becoming, and the decisions of record

The product spec for the SpikeInterface workbench and the home of dated decisions. When a
session and this file disagree, this file wins; when Ben's live word and this file disagree,
update this file. Method lives in `LOOPS.md`; per-phase detail in `goals/`; the live queue in
`ROADMAP.md`.

## The product

**A spike-sorting workbench a lab member can trust and operate alone** — built for Tracy's lab
at the University of Pittsburgh (UPitt), whose recordings this repo's `PFCM7_d0ephys_Block2`
block comes from. It takes a raw Blackrock/Ripple recording to **curated, reproducible,
shareable single units**: load → sort → inspect → curate → report, on the lab's own machine,
without the operator needing to know SpikeInterface, Docker, or quality-metric lore.

What exists today is the strong half of that: a genuinely good terminal workbench (responsive
dashboard, in-UI sorting with honest progress, real probe geometry, six array/yield metrics on
four surfaces, honest caveats everywhere). What's missing is the science depth that makes the
output publishable: the 2026-06-27 audit's verdict stands — today's output is *candidate*
units, not yet trustworthy (3 of ~20 quality metrics, a hardcoded SNR≥5 headline), not yet
curated (no curation loop, no Phy export), and not yet reproducible (runs clobber each other,
provenance omits the effective params and seed).

## The arc (ratified from WORKBENCH_DIRECTIONS.md's low-regret sequence)

Deepen and harden one recording first, then choose a face, then broaden:

1. **W0 — quick wins**: the audit's cross-cutting dead-ends, path-neutral.
2. **W1 — Curation Workbench** (audit Path 1): full metric suite, a real curation loop,
   Phy export, defensible auto-curation thresholds. The keystone — every other path's
   signature feature flatters thin evidence until this exists.
3. **W2 — Reproducibility Engine** (audit Path 4): versioned runs, complete provenance,
   regenerate-from-record. Paired tightly with W1 (both re-touch the run store).
4. **W3 — one audience/medium bet**, Ben's pick: Guided Sort wizard (Path 3), Spike Live
   web (Path 5), or the terminal Power IDE (Path 6). Exactly one.
5. **W4 — Multi-Recording Lab Notebook** (Path 2): breadth last — it scales whatever W1/W2
   made trustworthy, and its cross-session unit tracking waits on verified probe wiring.

**WD — lab deployment** runs alongside: the target machine is the lab's **Windows box with an
NVIDIA GPU**, which changes the sorter story (kilosort4 becomes runnable there; this Mac never
offers it). Every phase's work must hold on Windows, not just macOS.

## Product laws

- **Honesty**: wrong-and-loud beats wrong-and-quiet. No mock/sample-data fallback, honest
  empty/error/0-unit states, caveats surfaced where the user decides (not flashed past).
  Already repo culture (truthful geometry, partial-sort caveats) — every phase preserves it.
- **Science invariants are non-negotiable**: the aux-drop-before-CMR ordering, the µV
  double-scaling gate, the ~4 µV noise-floor canary, analyzer-as-single-source-of-truth.
  They live in `CLAUDE.md` ("Invariants that bite"); briefs inherit them without restating.
- **Single source of truth per module** (`CLAUDE.md`'s ownership table). New capability
  extends the owning module; a second implementation of the same fact is a defect.
- **Cross-platform is load-bearing**: macOS is where Ben builds, Windows is where the lab
  runs. A feature that works only on the Mac is not done.
- **Raw data never leaves the machine or enters git** (the `.ns5` is ~176 MB; a fresh clone
  has no data). Cloud/remote agents can do code-only work; nothing that needs the recording.

## Decisions of record

- **2026-06-03** — the `.ns5` broadband arrived; sorting became possible.
- **2026-06-08/09** — the menu overhaul shipped: three-panel dashboard, in-UI sorting via
  `--progress json`, Docker management.
- **2026-06 (PR #1)** — probe geometry is real: `probes.py` owns it, default
  `nnx-a1x16-3mm-100` (NeuroNexus A1x16-3mm-100-703). Channel→site wiring is a
  **user-accepted identity mapping**; true depth order pending the real adapter map.
- **2026-06-27** — WORKBENCH_DIRECTIONS.md written: six paths, and the low-regret sequence
  this NORTHSTAR adopts as the arc.
- **2026-08-18** — orchestrator installed (this file, LOOPS, goals/, ROADMAP, SEALS,
  LESSONS, agents, skills), patterned on decantv2's loop-engineering setup. The arc above
  is **adopted as the working plan pending Ben's ratification** (OPEN in SEALS.md).

## Open questions (kept open on purpose — answers land here as dated decisions)

- **What Tracy's lab actually needs first** — users, their fluency, the recordings beyond
  this block, whether curation or batch is the pain. A short requirements pass with the lab
  should precede W3's face pick and could reorder W1/W4.
- **The W3 face**: wizard vs web vs terminal IDE — Ben's call, informed by the lab answer.
- **The adapter map**: the channel→site wiring that would make depth order physical.
- **GPU sorters on the lab box**: which (kilosort4 first?), and how validated against the
  local sorters on the same recording.
