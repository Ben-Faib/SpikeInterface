# LESSONS.md - what failures taught, one entry each

*One lesson per entry, newest first, numbered S<n>: the lesson, then where its fix is
encoded. A lesson retires once it is enforced (a test, a hook, a rule in
`docs/INVARIANTS.md` or `LOOPS.md`) or no longer true. Retired so far: S3 (docs restating
code; CLAUDE.md is now an index), S4 (now an INVARIANTS convention), S9 (enforced by the
em-dash test itself). History: git, tag `pre-cleanup-2026-10-06`.*

---

**S10 - a Textual member name can silently override an internal.** `_render`, `_name` and
`run_action` on Spike 2.0 classes each broke the app without a clear error. Check a new
member name against `dir()` of the Widget/Screen/App base. Encoded:
`tests/test_spike_app.py::test_no_member_shadows_a_textual_internal`.

**S8 - two conductors can run the same slice.** A "dead" session was alive and finishing
the same work. A builder that hits unexpected concurrent edits stops and reports, never
pushes on; the first response to a live peer is a direct message proposing an explicit
split (who finishes and commits, who takes over after a verified baton: tip hash + gates).

**S7 - a concurrent session can hard-reset the tree mid-turn.** Uncommitted board edits and
a fresh commit were lost to a peer's resets. On shared board files, write and commit in the
same breath; after committing contested files, check the commit is still on HEAD. Encoded:
`LOOPS.md` Sealing step 5.

**S6 - a layout change can turn tests into silent skips, and the suite gets greener.** A
fixture that skips when its expected layout is absent disables tests without failing.
Resolve fixtures through the owning module (`runs.saved_sorters()`), and after any re-plumb
compare the skip count before and after, not just failures.

**S5 - agent worktrees can start on a stale base.** A worktree lane's first act is checking
its base is the intended commit; a brief that launches lanes states that commit.

**S2 - a "failed" containerized sort can be version skew, not a sort failure.** Check
host-vs-container SpikeInterface versions before blaming a sorter; slow (mountainsort4) is
not hung. Encoded: `goals/GOAL_WD_DEPLOY.md` boundaries; verify-spike's Docker check.

**S1 - a green suite once enforced a bug that broke all sorting.** For sort-adjacent
changes the suite is necessary, never sufficient; the real gate is
`run_sorting.py --duration 30` plus the ~4 µV canary. Encoded: `LOOPS.md` gate 2, the
verify-spike skill.
