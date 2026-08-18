# LESSONS.md — what failures taught, one entry each

*One lesson per entry, newest first, numbered S<n>. Each entry: what happened, the lesson,
and where the fix was encoded (a skill, a brief, CLAUDE.md) — fixing the instance without
encoding the fix is half a lesson. Repo invariants born from bugs (the µV double-scaling
trap, the aux-drop ordering) live in CLAUDE.md "Invariants that bite"; this file carries
process lessons.*

---

**S3 (2026-08-18) — Docs drift silently until audited against source.** The CLAUDE.md
rewrite (`49dd4a3`) exposed stale claims (e.g. an in-code comment citing an SI behavior that
0.104 no longer has). Lesson: module docstrings are the API source of truth and claims about
upstream behavior get verified against the installed version, not repeated. Encoded:
CLAUDE.md points readers at docstrings instead of restating them.

**S2 (2026-06) — A "failed" containerized sort can be version skew, not a sort failure.**
The lab's mountainsort run reported "exited (1)" but the sort itself had succeeded — the
error came from host↔container SpikeInterface version skew when reading results back. Lesson:
check host-vs-container versions before blaming a sorter; and slow (mountainsort4) is not
hung. Encoded: `goals/GOAL_WD_DEPLOY.md` boundaries; verify-spike's Docker check.

**S1 (2026-06) — A green suite once enforced a bug that broke all sorting.** The Pilot/unit
tests asserted the buggy behavior, so "tests pass" actively defended the defect; only an
end-to-end sort caught it. Lesson: for sort-adjacent changes the suite is necessary, never
sufficient — the real gate is `run_sorting.py --duration 30` plus the ~4 µV canary. Encoded:
CLAUDE.md conventions, LOOPS.md gate #2, the verify-spike skill.
