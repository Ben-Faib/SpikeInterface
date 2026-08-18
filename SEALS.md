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
- **Science depth is the remaining gap, one notch smaller**: quality metrics are now 12
  columns (M1, 2026-08-18 — presence, amplitude, PCA isolation added), but the
  "high-quality" count is still a hardcoded SNR≥5 heuristic, there is no curation loop or
  Phy export, and runs clobber each other with incomplete provenance — W1→W2 close this.
- **Probe geometry is real** (`nnx-a1x16-3mm-100` default) with channel→site wiring a
  user-accepted identity mapping — true depth order still waits on the lab's adapter map.
- **Deployment target is the UPitt lab's Windows+GPU box**; Windows Docker-sort cleanup
  crash fixed 2026-08-18 (`7940f96`); GPU-sorter enablement (kilosort4) not yet started (WD).
- **Current focus (2026-08-18, updated same day): THE OVERHAUL.** Ben's directive — all
  surfaces redesigned for accessibility/focus/hierarchy + a timely-updates UX + real
  testing procedures + probe flexibility for a lab whose setups differ. `DESIGN_UX.md`
  (D0) was **approved by Ben the same evening** and the autonomous run delivered the
  whole D track in one day: D1 dashboard (`18a5279`), D2 both halves (`fc19579` +
  `29e96f8`), D3 report (`d12ff5c`), D4 flow modals (`f115015`) — plus T1 harness, M1
  metrics, P1 probe import, B1 (peer). Remaining from the overhaul: D3b progress
  plumbing (READY); in flight: C1, Ben's NEV online-vs-sorted comparison.
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
