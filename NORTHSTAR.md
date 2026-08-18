# NORTHSTAR.md — what this tool is becoming, and the decisions of record

The product spec for the SpikeInterface workbench and the home of dated decisions. When a
session and this file disagree, this file wins; when Ben's live word and this file disagree,
update this file. Method lives in `LOOPS.md`; per-phase detail in `goals/`; the live queue in
`ROADMAP.md`.

## The product

**A spike-sorting workbench a researcher can trust and operate alone** — built for the UPitt
(University of Pittsburgh) researchers in Tracy's lab, whose recordings this repo's
`PFCM7_d0ephys_Block2` block comes from, by **Benjamin Faibussowitsch in collaboration with
Aleece Al-Olimat**. The lab wants the industry-standard **SpikeInterface** underneath; the
workbench is the trustworthy, operable face on it. It takes a raw Blackrock/Ripple recording
to **curated, reproducible, shareable single units**: load → sort → inspect → curate →
report, on the lab's own machine, without the operator needing to know SpikeInterface,
Docker, or quality-metric lore.

**Their probes have different setups** — probe flexibility is a core product requirement,
not a nice-to-have: the workbench must let a researcher describe, import, verify, and switch
electrode geometries (the P track), because a tool locked to one array serves one experiment,
not the lab.

What exists today is the strong half of that: a genuinely good terminal workbench (responsive
dashboard, in-UI sorting with honest progress, real probe geometry, six array/yield metrics on
four surfaces, honest caveats everywhere). What's missing is the science depth that makes the
output publishable: the 2026-06-27 audit's verdict stands — today's output is *candidate*
units, not yet trustworthy (3 of ~20 quality metrics, a hardcoded SNR≥5 headline), not yet
curated (no curation loop, no Phy export), and not yet reproducible (runs clobber each other,
provenance omits the effective params and seed).

## The arc (restructured 2026-08-18 — Ben's UI/UX overhaul directive)

The queue is now a **dependency graph**, not a line — `ROADMAP.md` carries the live graph.
The tracks:

- **D — the UI/UX overhaul** (Ben, 2026-08-18): every surface redesigned for accessibility,
  less clutter, focus on what matters, clean hierarchy with ample room — and a UX that
  provides **timely updates and results** while it works. D0 is the design spec
  (`DESIGN_UX.md`, **Ben veto gate**); D1–D4 implement it (dashboard, timeliness system,
  report, flow modals). Subsumes the old W0 UI quick wins.
- **T — testing procedures** (Ben, 2026-08-18): snapshot/visual regression for the TUI,
  structural golden checks for the report, contract tests for the progress protocol —
  built *before* the redesigns land so they land reviewably.
- **M — the science base**: full quality-metric suite first (old W0 item 5), then
  **W1 Curation** (audit Path 1: curation loop, Phy export, defensible thresholds) and
  **W2 Reproducibility** (audit Path 4: versioned runs, complete provenance).
- **P — probe flexibility** (elevated 2026-08-18): general probe import (probeinterface
  formats), multi-shank, wiring verification — because the lab's probes differ.
- **W3 — one audience/medium bet**, Ben's pick (wizard / web / terminal IDE), after the
  D track gives whichever face a clean base. **W4 — multi-recording** stays last.

**WD — lab deployment** runs alongside everything: the target machine is the lab's **Windows
box with an NVIDIA GPU**, which changes the sorter story (kilosort4 becomes runnable there;
this Mac never offers it). Every phase's work must hold on Windows, not just macOS.

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
  LESSONS, agents, skills), patterned on decantv2's loop-engineering setup.
- **2026-08-18 (Ben, evening)** — **the D0 veto is APPROVED** ("the dashboard needs
  overhaul for sure") with no amendments, the dashboard named the priority, and the build
  authorized to **run autonomously**: sessions execute the ROADMAP graph in dependency
  order without waiting for per-item pastes, sealing per the contract as they go.
- **2026-08-18 (Ben, same day)** — **the UI/UX overhaul mandate**: drastically improve all
  surfaces — more accessible, less clutter, focused on what matters, clean with good
  spacing/hierarchy and ample room; the UX must feel like the program provides timely
  updates and results; complete overhauls are on the table; testing procedures get built
  out properly; the queue becomes a dependency graph. Product facts of record: the users
  are UPitt researchers wanting industry-standard SpikeInterface; **their probes have
  different setups** (probe flexibility elevated to the P track); built by Benjamin
  Faibussowitsch in collaboration with Aleece Al-Olimat. This supersedes the original
  W0-first line ordering — the arc section above carries the new structure.

## Open questions (kept open on purpose — answers land here as dated decisions)

- **What Tracy's lab actually needs first** — users, their fluency, the recordings beyond
  this block, whether curation or batch is the pain. A short requirements pass with the lab
  should precede W3's face pick and could reorder W1/W4.
- **The W3 face**: wizard vs web vs terminal IDE — Ben's call, informed by the lab answer.
- **The adapter map**: the channel→site wiring that would make depth order physical.
- **GPU sorters on the lab box**: which (kilosort4 first?), and how validated against the
  local sorters on the same recording.
