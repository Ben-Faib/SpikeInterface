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
- **Science depth is the gap**: quality metrics are still 3 of ~20, the "high-quality" count
  is a hardcoded SNR≥5 heuristic, there is no curation loop or Phy export, and runs clobber
  each other with incomplete provenance — the W0→W1→W2 arc exists to close exactly this.
- **Probe geometry is real** (`nnx-a1x16-3mm-100` default) with channel→site wiring a
  user-accepted identity mapping — true depth order still waits on the lab's adapter map.
- **Deployment target is the UPitt lab's Windows+GPU box**; Windows Docker-sort cleanup
  crash fixed 2026-08-18 (`7940f96`); GPU-sorter enablement (kilosort4) not yet started (WD).
- **Current focus (2026-08-18): W0 quick wins** — ROADMAP prompt 1 is ready to paste.

## OPEN — needs Ben

- **Ratify (or amend) the NORTHSTAR arc** — W0→W1→W2→face→breadth was adopted from
  WORKBENCH_DIRECTIONS.md's low-regret sequence pending your word. *(opened 2026-08-18)*
- **Lab requirements pass** — what Tracy's lab needs first (users, fluency, recordings,
  curation-vs-batch pain); shapes the W3 face pick and could reorder W1/W4.
  *(opened 2026-08-18)*
- **Lab-box access for WD** — the deployment track can't start without a session on the
  Windows+GPU machine. *(opened 2026-08-18)*
- **The adapter map** — channel→site wiring to make depth order physical; also gates W4's
  cross-session unit tracking. *(opened 2026-08-18, long-standing)*

---

## The ledger (newest first)

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
