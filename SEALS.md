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
  (D0) is drafted and **waits on Ben's veto**; T1 (testing harness) runs in the peer
  session; prompts M1 (metrics) and P1 (probe import) are ready to paste in parallel.
  Product facts on record: built by Benjamin Faibussowitsch with Aleece Al-Olimat for
  UPitt researchers on industry-standard SpikeInterface.

## OPEN — needs Ben

- **The D0 veto: approve or amend `DESIGN_UX.md`** — every D slice (dashboard, run
  experience, report, flow modals) is gated on it; the peer session's feasibility critique
  folds in first. *(opened 2026-08-18)*
- **Ratify (or amend) the NORTHSTAR arc** — now including the 2026-08-18 restructure into
  the D/T/M/P dependency graph. *(opened 2026-08-18)*
- **Lab requirements pass** — what Tracy's lab needs first (users, fluency, recordings,
  curation-vs-batch pain); shapes the W3 face pick and could reorder W1/W4.
  *(opened 2026-08-18)*
- **Lab-box access for WD** — the deployment track can't start without a session on the
  Windows+GPU machine. *(opened 2026-08-18)*
- **The adapter map** — channel→site wiring to make depth order physical; also gates W4's
  cross-session unit tracking. *(opened 2026-08-18, long-standing)*

---

## The ledger (newest first)

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
