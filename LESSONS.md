# LESSONS.md - what failures taught, one entry each

*One lesson per entry, newest first, numbered S<n>. Each entry: what happened, the lesson,
and where the fix was encoded (a skill, a brief, CLAUDE.md) - fixing the instance without
encoding the fix is half a lesson. Repo invariants born from bugs (the µV double-scaling
trap, the aux-drop ordering) live in CLAUDE.md "Invariants that bite"; this file carries
process lessons.*

---

**S8 (2026-08-19) - two conductors can end up running the same slice; message the peer,
don't assume it died.** Ben started the v3 conductor on the stated premise that the face1
session had died mid-build. It hadn't: it was alive and folding its own Fable review of
the same slice - caught only when a builder's first Edit failed with "file modified since
read" on a tree that had been clean minutes earlier (the S7 first-act ListAgents/ps check
had fired, but an idle peer can wake). What worked: the builder STOPPED at the first
mid-run churn and reported instead of re-reading and pushing on; the conductors then
split the work explicitly over SendMessage - the incumbent finishes and commits its lane
and stands down, the fresh session owns everything after a verified baton (tip hash +
gate numbers) - and the two independent reviews turned out complementary, each catching
a finding the other missed. Lesson: a builder that hits unexpected concurrent edits must
stop and report, never continue; and the first response to a live peer on shared state is
a direct message proposing an explicit split, not working around it. Encoded: this entry;
the v3 prompt's first-act check stays as-is.

**S7 (2026-08-19) - a concurrent session can hard-reset the tree mid-turn.** During the
conductor close, a peer session (or terminal) ran hard resets at 01:35 and ~01:40 that
first wiped uncommitted board edits and then dropped a just-made commit - content
survived only because it existed in this session's context and in the reflog. The
existing rule (re-check status before committing) does not protect the window between
writing a file and committing it. Lesson: on shared-tree docs (SEALS/ROADMAP/CLAUDE/
LESSONS), write and commit in the same breath - never leave board edits sitting dirty;
after committing contested files, re-verify the commit is still on HEAD before relying
on it. Encoded: this entry; the repo CLAUDE.md concurrent-edit rule already covers the
rest.

**S6 (2026-08-18) - a layout re-plumb can turn tests into silent skips, and the suite gets
*greener*.** W2's run-store re-plumb moved `outputs/<sorter>/analyzer`; `test_report_golden`'s
fixture and `test_report_resolution`'s guard globbed the old path and, finding nothing,
**skipped** - 14 report tests stopped running on a machine full of saved sorts, and the
only symptom was a higher skip count. Lesson: a fixture/guard that skips when its expected
layout is absent converts any layout change into silent test disablement - resolve fixtures
through the owning module (the tests now ask `runs.saved_sorters()`), and after any
re-plumb compare the suite's **skip count** before/after, not just the failure count.
Encoded: the restored tests in the W2 lane (`ce4ab94`); this entry.

**S5 (2026-08-18) - agent worktrees can be created on a stale base.** Two conductor-run
builder worktrees started 62 files behind main (`84d3bc0`); both builders caught it and
reset onto main before working, but one that didn't would have built on sealed history and
produced an unmergeable diff. Lesson: a worktree lane's first act is verifying its base is
the intended commit (and the brief states that commit); the conductor's re-entry prompt now
carries exact base/branch refs per lane. Encoded: ROADMAP's CONDUCTOR v2 prompt; this entry.

**S4 (2026-08-18) - `subprocess.run(text=True)` without `encoding=` is a Windows landmine.**
Review of the T1 stdout-purity tests caught that text-mode capture decodes with the locale
code page (cp1252 on the lab box) while our children force UTF-8 output full of multibyte
glyphs - one typographic quote in future output turns the test into a UnicodeDecodeError.
Lesson: on this repo, every text-mode subprocess capture passes `encoding="utf-8",
errors="replace"`. Encoded: `tests/test_sort_progress_contract.py`'s `_run_sorting` helper
is the pattern to copy.

**S3 (2026-08-18) - Docs drift silently until audited against source.** The CLAUDE.md
rewrite (`49dd4a3`) exposed stale claims (e.g. an in-code comment citing an SI behavior that
0.104 no longer has). Lesson: module docstrings are the API source of truth and claims about
upstream behavior get verified against the installed version, not repeated. Encoded:
CLAUDE.md points readers at docstrings instead of restating them.

**S2 (2026-06) - A "failed" containerized sort can be version skew, not a sort failure.**
The lab's mountainsort run reported "exited (1)" but the sort itself had succeeded - the
error came from host↔container SpikeInterface version skew when reading results back. Lesson:
check host-vs-container versions before blaming a sorter; and slow (mountainsort4) is not
hung. Encoded: `goals/GOAL_WD_DEPLOY.md` boundaries; verify-spike's Docker check.

**S1 (2026-06) - A green suite once enforced a bug that broke all sorting.** The Pilot/unit
tests asserted the buggy behavior, so "tests pass" actively defended the defect; only an
end-to-end sort caught it. Lesson: for sort-adjacent changes the suite is necessary, never
sufficient - the real gate is `run_sorting.py --duration 30` plus the ~4 µV canary. Encoded:
CLAUDE.md conventions, LOOPS.md gate #2, the verify-spike skill.
