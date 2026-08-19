---
name: verify-spike
description: Verify any workbench change end-to-end before declaring it done - the suite for menu/view work, the 30 s sort smoke with the ~4 µV canary for sort-adjacent work, loader/report/Docker checks where touched. Invoke before reporting any substantive change complete, and as the done-check inside goal runs.
---

# Verifying workbench changes

Never report a change complete on a successful edit alone. Verify it the way Ben would check
it the next morning, and claim only what a tool result in this session shows.

**Run each check once.** An edit that compiles is not a change that works - but more passes
are not better. Do not stack additional self-verification on top of these checks, re-run a
gate you have already run green, or spawn an agent to re-check a conclusion you have already
checked; the independent Fable review below is the second set of eyes.

## Map change-type → gates

Run every row your change touches:

| You touched | Run | Pass means |
|---|---|---|
| anything | `uv run python -m pytest tests/` | green - but see the S1 rule below |
| sort pipeline / metrics / preprocessing / params | `uv run python scripts/run_sorting.py --duration 30 --probe nnx-a1x16-3mm-100` | completes; **noise floor ~4 µV** |
| `blackrock_io.py` | `uv run python scripts/verify_install.py` | all three loaders load |
| Docker paths (`sorters.py` Docker logic, image mgmt) | one containerized sort (short `--duration`) | completes; check host↔container SI versions before blaming a failure (LESSONS S2) |
| report / compare | build it and open the HTML | renders; caveats present; no stale derived data read |
| menu view / controller | the Pilot suite, plus a real launch for anything Pilot can't see (colors, suspend, subprocess UX) | journeys pass; nothing clips |

**The S1 rule:** for sort-adjacent changes a green suite is necessary, never sufficient -
the tests once enforced a bug that broke all sorting. The smoke row is the real gate.

**The canary is a verdict, not a stat.** Noise floor is a property of the recording
(post-bandpass + CMR), so it lands at ~4 µV (observed 3.88–4.02) for every sorter. A ~1 µV
reading means the channel gain got re-applied (the 4×-too-small double-scaling bug) - a
stop-the-line correctness failure even if everything else is green. Sorter-to-sorter
variation in the canary is the same verdict.

**Honest states count as behavior.** If the change touches a surface with an empty/error/
0-unit state, drive that state once and confirm it reads honestly (amber with a next step,
never a green nothing).

## For substantive slices

One fresh-context review pass, by Fable - not an extra round of self-checking. Spawn the
`reviewer` agent with the brief's definition-of-done and the diff, no access to your
reasoning. Ask for everything it finds, ranked and severity-labeled - a prompt that asks
only for high-severity issues gets a shorter list, not a cleaner diff. Resolve or record the
findings before sealing. Mechanical/trivial changes skip the review.

If a gate fails: fix it, then re-run only the checks that fix could have affected - not the
whole table from the top. Partially verified work is reported as exactly that.
