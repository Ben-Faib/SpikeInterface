# SEALS.md — what each run decided, moved, and needs from Ben

*Ben's read-in-30-seconds file, and the source `/status` reads. Every sealing session appends
ONE block here (five lines, one sentence each — the cap is the point), updates the pinned
lines below if its work changed them, and edits the OPEN block if it created or closed a
need. Long prose belongs in ROADMAP, LESSONS, the briefs, and commit messages — never here.
A need left only in a chat summary is a need Ben never sees.*

---

## Where we stand (pinned — any seal that changes one of these rewrites the line)

- **The pipeline works end to end on the one recording**: load → sort (4 local sorters,
  Docker fallback) → analyzer + six array/yield metrics on four surfaces → report/compare;
  noise-floor canary steady at ~4 µV across all saved sorts.
- **The curation loop is live** (W1 s2 `cddd677` + s3 `96a53cb`): merge/split/label
  decisions persist in an anchored record beside the sort, replay onto a curated Sorting
  with re-scored metrics, every surface states curated-vs-raw honestly, and the hard cases
  round-trip through Phy (`phy` menu action / `export-phy` → curate → `import-phy`, verdicts
  landing back in the same record with source="phy"); records and manifests refuse a sort
  they weren't written against (tdc2 non-determinism makes that refusal load-bearing).
  Remaining science gaps: in-TUI triage (s4, in lane) and versioned runs with complete
  provenance (W2, review folded, integration pending) — this run closes them.
- **Probe geometry is real** (`nnx-a1x16-3mm-100` default) with channel→site wiring a
  user-accepted identity mapping — true depth order still waits on the lab's adapter map.
- **Deployment target is the UPitt lab's Windows+GPU box**; Windows Docker-sort cleanup
  crash fixed 2026-08-18 (`7940f96`); GPU-sorter enablement (kilosort4) not yet started (WD).
- **Current focus: CONDUCTOR v2 RUN LIVE (2026-08-19)** — landed: W1 s2 (`cddd677`), W1 s3
  (`96a53cb`), Ben's .nev-structure honesty commit (peer, `ff518fd`). In lanes: W2 (build +
  Fable review done, findings folding; integrates last with the curation sort_paths
  re-point), s4 in-TUI triage (building on `ff518fd`). Then: final suite + launch + close.
  Facts of record binding design: E1's premise FALSE in-band (PRE1), tdc2 non-deterministic
  (14/16/17/18/19 units now observed), and .nev unit ids are PER-ELECTRODE SLOTS — the
  manual reference carries 7 sorted electrode×slot units on 4 electrodes, stated on the
  compare page (`ff518fd`), and cross-electrode same-slot coincidence is chance-level.
  Product facts on record: built by Benjamin Faibussowitsch with Aleece Al-Olimat for
  UPitt researchers on industry-standard SpikeInterface.

## OPEN — needs Ben

- ~~The D0 veto~~ — **CLOSED 2026-08-18: APPROVED by Ben** ("the dashboard needs overhaul
  for sure"), dashboard first, build authorized to run autonomously. The arc-ratification
  item closes with it (continuing the graph was the ratification).
- **Lab requirements pass** — what Tracy's lab needs first (users, fluency, recordings,
  curation-vs-batch pain); shapes the W3 face pick and could reorder W1/W4.
  *(opened 2026-08-18)*
- **Lab-box access for WD** — the deployment track can't start without a session on the
  Windows+GPU machine. *(opened 2026-08-18)*
- **The adapter map** — channel→site wiring to make depth order physical; also gates W4's
  cross-session unit tracking. *(opened 2026-08-18, long-standing)*

---

## The ledger (newest first)

**2026-08-19 — W1 s3: the Phy round trip, recovered, reviewed fix-first, landed (`96a53cb`)**
- Did: recovered the lane's never-committed work from the temp worktree, rebased it onto
  s2's folded schema, ran its Fable review (fix-first), folded all three must-fixes —
  the `--out` rmtree guard (an explicit target could have deleted the raw sort wholesale),
  blank-anchor refusals on BOTH sides of the trip (the reviewer reproduced labels landing
  on the wrong sort through an anchorless manifest), and the stale-curated export refusal —
  and landed it: `phy` menu action, export with identity manifest + id map + seeded labels,
  import keyed by the map with source="phy" provenance and named refusals.
- Means: the measured dead-end (tdc2's merges unsplittable by any modest method — residue
  3.6–5.4×) now has its human path: the hard cases go out to Phy and the verdicts come back
  into the same record every surface reads, with wrong-sort/wrong-sorter/stale/anchorless
  folders refused by name rather than quietly mis-imported.
- Moved: suite 514 at the fold (516 on main with the peer's `ff518fd`); raw + curated
  exports exercised live and the shipped artifact regenerated post-fix; six review
  follow-ups (F4–F8, F10) recorded in the W1 brief; CLAUDE.md's actions line + brief
  updated.
- Needs Ben: nothing — F8 (Phy's exact label-snippet syntax) waits on any machine with Phy
  installed.
- Next: s4 (in-TUI triage) builds in its lane; W2's review findings fold in parallel;
  W2 integrates last, re-pointing curation's sort_paths through the run store.

**2026-08-18 — W1 s2: the curation lifecycle, landed and validated fresh (`cddd677`)**
- Did: rebased the review-folded lane onto main (one semantic conflict: PRE1's bad-channel
  note + s2's curation provenance now coexist in the report), ran the whole validation
  chain fresh on the main tree — full 19-unit anchor sort (canary 4.114 µV) → label+split
  record → apply → curated 20 units re-scored (canary 3.993 µV) → both compare pages
  against the manual .nev — and added curation.py's ownership row + commands line to
  CLAUDE.md.
- Means: a lab member can now save merge/split/label decisions against exactly the sort
  they made them on, replay them into a first-class curated result, and trust every
  surface to say which result it is showing — with the anchor refusing a re-sorted tree
  (the non-determinism evidence made that refusal the design's load-bearing wall).
- Moved: the fresh sort extended the tdc2 non-determinism record to 14/16/17/18/19 units;
  s3's unmade handoff commit was recovered from the scratchpad worktree and rebased onto
  the folded schema (LESSONS S5 vindicated); three follow-ups recorded in the W1 brief
  (run_sorting seam promotion, import-gui, seeded GMM split).
- Needs Ben: nothing.
- Next: s3's live export/import validation + Fable review, then the s4 gate.

**2026-08-18 — CONDUCTOR RUN closed mid-flight at Ben's request: 4 sealed, 3 parked**
- Did: sealed P2, PRE1, D6 and DEBT with per-slice Fable reviews folded, and parked
  W1 s2 (`c1af408`, all 9 review findings folded), W1 s3 (`lane-w1s3`) and W2
  (`467ed7e`, honest handoff) on branches with the re-entry queue filed as ROADMAP's
  THE CONDUCTOR v2 prompt.
- Means: main (`c580286`) is 459-green and four slices stronger, and the two facts
  that reshape the science are measured and sealed — no bad channel exists in the
  referenced band (E1's premise false; detection kept as insurance) and tridesclous2
  is non-deterministic here (14/16/18 units), which now binds curation anchoring and
  W2's regeneration criteria.
- Moved: the s2 review's adversarial pass CONFIRMED the merged ch5/ch9 pairs are
  unreachable as defensible units by any modest splitter (3.6-5.4× residue
  contamination; leverage is upstream) — the Phy/human path for hard cases is now
  evidence, not preference; W1 s4 pre-assigned to the peer, gated on s2.
- Needs Ben: nothing new — paste THE CONDUCTOR v2 from ROADMAP into a fresh session.
- Next: v2's queue — land s2 (rebase + fresh validation), s3, open the s4 gate, W2
  (review + first-run regenerate + tests), then final suite + real launch + close.

**2026-08-18 — DEBT: the five recorded debts, closed in one lane (`0127dac`)**
- Did: keyboard-sortable report headers (real buttons, aria-sort state), the D2b
  pending-phase manifest (`plan` event, SHAPES-gated, modal shows pending rows),
  online_unit_labels/unit_class relocated to blackrock_io as the one home, five
  provably-dead controller members deleted, and extra-.nev discovery made robust.
- Means: the extra-.nev item was a REAL latent bug — with the manual export beside the
  recording, discovery returned the first name-sorted `.nev` and was right by luck;
  it now prefers the stem carrying data and refuses honestly, naming candidates, when
  genuinely ambiguous (one sealed test deliberately flipped from pins-the-guess to
  pins-the-refusal).
- Moved: Fable review ship (five low findings, four folded — ambiguity reason now
  reaches the compare page and the Data Setup checklist; probes.py catalog helpers
  deleted as the next dead layer; sort hint surfaced on the report); combined-code
  validation after rebases: 459 green, smoke canary 3.919 µV; CLAUDE.md's two stale
  loader bullets refreshed in the seal commit.
- Needs Ben: nothing.
- Next: recorded cosmetic (report th-padding dead-click zone) rides the debt list;
  W1 s2 integration is the next merge.

**2026-08-18 — D6: the airy dashboard (peer session, `98f2645`)**
- Did: replaced the boxed-panel chrome with Ben's approved whitespace + hairline
  language — crest tall-terminals-only, probe stated once, a pressable t-chip "change"
  control on SORT (click opens the picker), a dim context sentence, inverse-video key
  chips on action rows, the manage/help keys merged into one bottom line, and air wired
  into the yield order to collapse before content — with DESIGN_UX §2 rewritten as the
  spec of record.
- Means: the dashboard reads as sections of air instead of boxes, every affordance looks
  pressable (Ben's "less annoying" intent), and 80×24 stays fully usable with never-clip
  and painted-rows still pinned.
- Moved: the Fable review went fix-first and caught the flagship hairline never actually
  painting (word-wrapped out of its 1-row clip — and my first snapshot re-baseline had
  enshrined the bug) plus a resize-under-modal never-clip violation; all seven findings
  folded, the hairline test now asserts the paint, and the snapshots were re-baselined a
  deliberate second time; suite 441 green, real-controller launch verified.
- Needs Ben: nothing — open the dashboard when convenient; it's his mock synthesis live.
- Next: the debt bundle merges onto this (conductor), and W1s4's triage screen inherits
  the D6 section language.

**2026-08-18 — PRE1: bad channels out of the reference — premise measured false, feature kept (`c823f55`)**
- Did: built data-driven bad-channel detection/exclusion into the sort pipeline
  (mad, pinned seed, 25% wholesale-refusal, manual naming, provenance on every
  surface), archived the baseline, re-ran the full sort + manual comparison to
  measure it, and folded all eight findings of a fix-first Fable review.
- Means: E1's premise is false in the referenced band — ch1's oscillation is
  sub-300 Hz and the bandpass removes it before the median (in-band ch1 is the
  quietest channel and carries a real unit; zero channels flagged by any method),
  so the sort is unchanged and the feature is insurance for the lab's recordings.
- Moved: tridesclous2 measured NON-DETERMINISTIC here (14/16/18 units across
  identical runs) — W1's curation records now hard-anchor to their exact sort and
  W2's regeneration criteria avoid unit counts; baseline + MEASUREMENT.md live in
  outputs/_archive/tridesclous2_pre_badch/.
- Needs Ben: nothing.
- Next: W2 launches off this commit; debt bundle (reviewed: ship) integrates
  behind it; W1 s2 under review, s3 building.

**2026-08-18 — P2: multi-shank / ProbeGroup support (peer session, `8af8111`)**
- Did: a multi-probe ProbeGroup (or a probe with native shank ids) now imports as one
  self-contained profile — shank labels and per-shank pitch/density materialised, group
  wiring validated as one permutation across all contacts and pinned channel→shank→
  position verbatim by test, build reconstructing shanks with an honest outline — with
  the Fable review's five actionable findings folded pre-seal.
- Means: the lab's multi-shank probes drop into the library like any other, density
  classing stays physical (global contact proximity, not shank labels — so sorter fits
  can't be fooled either way), and the report's probe view shows shanks as real columns
  with zero report changes.
- Moved: gates in an isolated worktree (main outputs/ left to PRE1): suite 388 green, 48
  probe unit tests, 30 s multi-shank sort at noise floor 3.993 µV, both shank columns in
  the analyzer and report; save_profile now also shields wiring/shank keys from
  stripping upserts.
- Needs Ben: nothing.
- Next: P3 (wiring surfaces) inherits three recorded items — the --probe-file identity
  trap (P1), coincident-probes error wording, and per-shank display consumption by the
  menu lane when its probe UI pass lands; conductor flips the P2 row.

**2026-08-18 — W1 slice 1: the quality rule, owned and honest (+ Option A adjudicated)**
- Did: replaced the hardcoded SNR≥5 headline with a configurable, NaN-honest,
  provenance-recorded quality rule owned by sort_summary and stated verbatim on every
  surface that shows the count, with its review's seven findings folded (including the
  result card claiming the old rule over new-rule numbers).
- Means: the "N look high-quality" signal is now defensible and tunable
  (.si_menu.json quality_rule), and "couldn't judge" can never masquerade as "failed".
- Moved: Ben chose the curation path; Option A self-resolved — spykingcircus2 smears
  units across channels on this data, so tridesclous2 + curation is confirmed; the
  manual .nev export is the validation reference for slice 2.
- Needs Ben: nothing — slice 2 (the curation loop: save merge/split/label decisions,
  apply, re-score) is next and is a full-session build.
- Next: W1 slice 2 in a fresh session from the board; the run's 17 seals stand.


**2026-08-18 — D5 + C2: the actions-first screen, and the manual sort answered (`63fe05c`, `4ffcfda`)**
- Did: rebuilt the main screen to Ben's late directive (actions primary, sorter list
  behind a filtering t-picker, RESULTS section, MANAGE line) with its review's two
  invisible-to-the-suite bugs fixed and pinned; and wired Ben's manually sorted .nev
  into the comparison machinery (--nev, --delta-ms, a containment column).
- Means: a first-time lab member lands on what they can do; and the sorter question is
  answered with numbers — tridesclous2 finds 97-100% of every manually sorted unit's
  spikes but merges each channel's pair into one unit, which is also exactly why its
  active-channel ISI violations run high (the huge ratios elsewhere are the metric's
  low-rate blowup, not brokenness).
- Moved: a measured ~0.6 ms crossing-vs-peak timestamp offset is now compensated and
  documented in the compare defaults; params were checked (all defaults — not the
  cause); repo memory corrected twice about the .nev.
- Needs Ben: nothing blocking — next-step options are his: a spykingcircus2 full-sort
  comparison, tdc2 clustering tuning, or W1 curation (splitting merges is exactly that
  slice, and the manual export is now its validation reference).
- Next: W1 curation is the highest-value queued science; T-track follow-ups and the
  D5-review's noted controller dead code ride the next pass.


**2026-08-18 — T2/T3: journeys + honesty states (peer session, `fc4652b` + `7e6938d`)**
- Did: retired six layout-detail assertions the redesign obsoleted (each enumerated in the
  commit message), added four journeys that cross the real screens and the real subprocess
  event pipe (explore→sort→report with chain and reopen, cancel-mid-sort with the child
  provably dead cross-platform, the failure card with its log→ next step, 0-unit amber
  reaching the dashboard), and pinned every §1.7 dead-end to NAME its next step.
- Means: the suite now defends what must stay true — flows and honesty — while visual
  change stays a deliberate snapshot re-baseline, so future redesign slices can't be
  fought by chrome assertions or pass while a dead-end goes nameless.
- Moved: the review surfaced the Windows Esc-mid-sort orphan (fixed in D4 `f115015`, now
  asserted universally); the five D4 flow-modal tests ride in `7e6938d` by agreed commit
  order, with D4-review F8a/F8b folded in; suite 382 green.
- Needs Ben: nothing new — the standing report-eyeball ask above covers it.
- Next: the T track is complete; future surfaces inherit the journey/state doctrine now
  written into tests/README.md.

**2026-08-18 — D3 + D4: the report and the flow modals (`d12ff5c`, `f115015`)**
- Did: sealed the overhaul's last two built slices — the verdict-first report (four honest
  stat tiles, truthful TOC glyphs, reader-order sections, one chart language; built by a
  builder agent, hardened by a fix-first review) and the flow modals (informed sort-span
  choice from real wall-time provenance, live param validation with ● marks, compare
  behind an honest BusyScreen with failure causes surfaced, bare gui/sort crashes fixed,
  and Esc-mid-sort now genuinely kills the worker tree on Windows).
- Means: every surface Ben screenshotted this afternoon is rebuilt to the approved spec
  and on main, verified by 382 tests, per-slice Fable reviews, and a real launch.
- Moved: D3b (report/compare progress plumbing) is unblocked and READY; C1 (Ben's
  NEV online-vs-sorted comparison) has its engine building in a lane now.
- Needs Ben: open outputs/report.html — the redesign's only unperformed check is a human
  eyeball in a real browser (no Chrome connection tonight from any session).
- Next: peer seals T2/T3 (in progress); then C1 review + menu wiring and D3b.


**2026-08-18 — B1: bare report crash fixed (peer session, `b43869e`)**
- Did: the documented bare invocations (`make_report.py`, the launcher's report action, and
  the silent non-TTY dispatch CI/piped runs hit) now resolve a sorter — explicit flag >
  persisted active sorter with a saved sort > the most-complete saved sort — instead of
  crashing on a None path join, and error honestly (naming a command that works) when
  nothing is saved.
- Means: the report front door works with zero arguments, and the default it picks is the
  most complete sort rather than a leftover 30 s smoke — the review talked us out of the
  queued recommended-default step on exactly that scenario.
- Moved: 9 regression tests pin the precedence and the exact reported command; isolated
  worktree suite 341 green; review verdict ship (7 findings, 4 folded in).
- Needs Ben: nothing.
- Next: siblings recorded, not fixed — bare `gui` and bare `sort` still crash on a None
  sorter (pre-existing; a good D4-adjacent small fix).

**2026-08-18 — D1: the dashboard overhaul (`18a5279`)**
- Did: rebuilt the dashboard to the approved spec — two-line banner, one home for the
  active sorter, six numbered workflow actions over a dim MANAGE tier, signal-budget
  sorter rows with honest availability glyphs, folded GPU group, compact scrollable
  INSPECTING, a persistent LAST RESULT line with r-reopen, persisted active sorter, and
  truthful help — with the layout driven by real budget arithmetic instead of hand-tuned
  thresholds.
- Means: the first surface of Ben's overhaul is live, and it stays usable at 80×24 — the
  Fable review caught the redesign starving the lists at exactly that size (fix-first, 7
  findings) and every finding is fixed with painted-rows tests pinning it.
- Moved: D4 and B1 unblocked (D1 released the menu files); the D2 view half can start
  (its engine half sealed the same evening as `fc19579` — the protocol now carries
  elapsed, per-phase durations, and a result payload, Fable-reviewed ship).
- Needs Ben: nothing — the run continues autonomously per the standing authorization.
- Next: D2 view half (progress modal + result cards), then D3 report, D4, B1.

**2026-08-18 — P1 probeinterface import (peer session)**
- Did: probes.py now imports probeinterface .json/.prb via CLI, materialising geometry
  (positions, pitch, layout, wiring, provenance) into a self-contained library profile
  with honest channel-count verdicts and named refusals (partial wiring, ProbeGroups,
  name collisions, unwritable store), hardened per the Fable review (`384884e`).
- Means: a probe the lab already has a standard description for drops straight in — real
  density-based sorter fits included — instead of being hand-entered parameter by
  parameter, and declared wiring is honoured rather than silently discarded.
- Moved: gates ran in an isolated worktree against HEAD (main tree churns with D1/D2):
  suite 313 green, 30 s sort with an imported probe at noise floor 3.984 µV, report probe
  section faithful, mismatch asymmetry intact; review verdict ship, 3 medium findings all
  folded in.
- Needs Ben: nothing new.
- Next: D1 should make imported probes view/duplicate/delete-only in the probe editor
  (a geometry-less rename now fails honestly instead of saving a broken probe), and P3
  inherits the on-record `--probe-file` identity-wiring trap plus tetrode-import classing.

**2026-08-18 — T1 testing harness (peer session)**
- Did: built the redesign safety net — 8 deterministic SVG snapshot baselines of today's
  dashboard + modals (pytest-textual-snapshot in the dev group), a fresh-build structural
  golden check for the report, contract tests locking the sort-progress protocol (shapes,
  ordering, emitter, stdout purity), and tests/README.md's re-baselining procedure
  (`6171816`) — plus the 10-finding DESIGN_UX feasibility critique (`a11b259`, folded in).
- Means: D-track sessions can rewrite every visible surface and land it as reviewable
  SVG/structure diffs, with the protocol's extension points pre-agreed (new event types
  gate on the SHAPES table; new optional keys flow free; done/error stay as-is).
- Moved: the suite is 302 tests / ~30 s, green including a fresh report build; the Fable
  review returned 7 findings, none blocking, all six actionable ones folded in pre-seal.
- Needs Ben: nothing new — the D0 veto stays the gate this work serves.
- Next: D1/D2 re-baseline snapshots deliberately per tests/README.md; ROADMAP's T1 node
  needs flipping to done (orchestrating session owns that file this run).

**2026-08-18 — M1: quality metrics widened**
- Did: widened per-unit quality metrics from 3 to 12 columns with dependency-aware,
  best-effort compute ordering, honest NaN rendering everywhere, and a Fable review whose
  four findings (NaN-sort, silent-skip visibility, stale README, degenerate-PCA caveat)
  are all folded in.
- Means: every downstream surface — the report today, D3's verdict tiles, W1's curation
  thresholds — now stands on a real evidence base instead of 3 metrics.
- Moved: D3 lost its M1 gate (only the D0 veto remains); B1 filed (pre-existing bare
  `report` crash, reproduced on unmodified code, prompt READY in ROADMAP).
- Needs Ben: nothing new — the D0 veto remains the big open item.
- Next: paste P1 or B1 from ROADMAP; veto DESIGN_UX.md when ready.

**2026-08-18 — overhaul kickoff (D0 + graph)**
- Did: took Ben's overhaul directive on record (NORTHSTAR: UPitt researchers, varied probes,
  Faibussowitsch × Al-Olimat), drafted the `DESIGN_UX.md` D0 spec from screenshots of every
  surface, wrote the GOAL_D/GOAL_T/GOAL_P briefs, dissolved W0 into the new dependency-graph
  queue, and dispatched T1 (testing harness) to the peer session.
- Means: the overhaul now has a design authority with a veto gate, a testing track that
  makes redesigns reviewable, and two engine prompts (M1 metrics, P1 probe import) that can
  run in parallel while the veto is pending.
- Moved: ROADMAP is a dependency graph; the false-green 0-unit fix, INSPECTING clip,
  active-sorter persistence, and help fixes now live inside D1/D2 with the spec behind them.
- Needs Ben: the D0 veto on DESIGN_UX.md (the big one), plus the standing arc/requirements/
  lab-box items.
- Next: Ben vetoes/amends the spec; meanwhile paste M1 and P1 from ROADMAP; T1 seals from
  the peer session.

**2026-08-18 — orchestrator install**
- Did: installed the decantv2-pattern build system — NORTHSTAR, LOOPS, six goal briefs,
  ROADMAP console, this file, LESSONS, four agents, verify-spike + status skills, CLAUDE.md
  wiring.
- Means: the workbench now has a stated product (Tracy's UPitt lab), a ratifiable arc, and
  sessions that seal against machine-checkable gates instead of drifting.
- Moved: W0's brief is verified-current against source (five of seven audit quick wins
  remain; Explore-figures and stderr-log already landed).
- Needs Ben: the three OPEN items above — arc ratification, the lab requirements pass, and
  lab-box access.
- Next: paste ROADMAP prompt 1 (W0 quick wins) in a fresh session.
