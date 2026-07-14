# Audit and repair the SpikeInterface workspace (Windows run)

## Context

This is a maintenance pass on a small research-software repository. The code belongs to
the Tracy X. Cui lab in the Department of Bioengineering at the University of Pittsburgh,
an academic neural-engineering group; the repo is an ordinary open-source
[SpikeInterface](https://spikeinterface.readthedocs.io) workspace that reads one Blackrock
recording off disk, runs published spike-sorting algorithms on it, and presents the results
in a terminal dashboard. Everything you will touch is plain Python engineering: file
loaders, a Textual UI, a sorting pipeline, and a pytest suite. Terms like *spike*, *probe*,
*sorter*, and *channel* are the standard vocabulary of academic electrophysiology software
and refer to numerical signal processing, not to anything else.

The lab is about to hand this workspace to students who will run it on **Windows**, which is
where it is currently breaking. It has only ever been exercised on macOS. That makes
cross-platform correctness the point of this run, and it means you are running on the machine
where the bug actually reproduces — use that.

Read `CLAUDE.md` first. It is a freshly corrected map of the repo's real invariants
(the aux-channel drop, the µV double-scaling trap, the probes layer, the sort pipeline order)
and it is trustworthy as of this commit. `AUDIT_FINDINGS.md` is a list of twelve suspected
defects produced by a prior audit pass; it has **not** been verified against running code,
and its line numbers are as of commit `4807ce0`.

## The task

Three strands, in whatever order the evidence supports:

**1. Resolve the Windows failure.** Reproduce it first, then fix it.

A lab member ran a `mountainsort5` sort (a Docker sorter) from the menu on Windows and got
this in the sort progress screen:

<windows_error>
Sorting…
  ✓ Read broadband
  ✓ Preprocess
  ✓ Sort
  ✓ Quality metrics

Array / yield summary
  V_pp: 90.235 µV
  SNR: 7.143
  noise floor: 4.077 µV
  yield (% active electrodes): 56.2% (9/16)
  units / ch: 0.562
  units / active ch: 1

✗ PermissionError: [WinError 32] The process cannot access the file because it is being
  used by another process:
  'C:\Users\Aleece\Documents\SpikeInterface\outputs\mountainsort5\recording_for_docker\traces_cached_seg0.raw'
</windows_error>

Read the phase list before you touch anything, because it is the whole story: the sort
**worked**. Every phase completed, the units were saved, the metrics computed, and the noise
floor landed at 4.077 µV — right on the canary. The run then died in teardown and reported
itself to the user as a failure. Two defects are tangled together here and both want fixing.

The Windows one: `WinError 32` is Windows refusing to delete a file that still has an open
handle. `recording_for_docker` is the temporary binary copy of the recording that
SpikeInterface writes out for a containerised sorter and removes afterwards, and
`traces_cached_seg0.raw` is plausibly still memory-mapped by a live extractor object when the
delete runs. On macOS, unlinking an open file is legal, which is why this has never surfaced
here. Find who holds the handle and who does the deleting, and make the temporary folder be
released before it is removed. That is how the evidence reads to me; confirm it against a real
reproduction rather than taking my word for it, and follow the evidence if it points elsewhere.

The reporting one: a crash in cleanup destroyed a run that had already finished and saved its
real work. `CLAUDE.md` states this principle for quality metrics — the Sorting is saved before
metrics run, so a metrics crash degrades to success-with-a-note rather than discarding units.
Teardown deserves the same treatment. A sort whose outputs are on disk should not be presented
to a student as a red ✗.

Then sweep for the class of mistake, not just the call site. This repository has only ever run
on macOS, so expect Unix assumptions throughout: POSIX-only calls (cancelling a sort uses
`os.killpg(os.getpgid(...))` at `scripts/menu_app.py:717`, and neither function exists on
Windows), file handles held open across a delete or rename, path and encoding assumptions,
`spawn`-versus-`fork` multiprocessing when `n_jobs > 1`, console assumptions in the Textual UI,
and anything expecting a Unix shell.

**2. Verify every finding in `AUDIT_FINDINGS.md` against the code as it is now**, then fix the
ones that survive. Each finding gets a verdict — confirmed, refuted, or true-but-different-than-
described — backed by the actual code you read, not by re-reading the audit's own reasoning.
Findings 1 through 5 are the substantive ones; 11 and 12 are cosmetic and worth doing only if
they are as trivial as they look. A refuted finding is a real result: record why and move on.

**3. Audit the repo yourself, beyond that list.** The prior pass was a documentation-drift
review and was not looking for bugs. You are. Weight your attention toward correctness of the
signal-processing path, the places where the tests do not reach, and cross-platform behaviour.

## Definition of done

On this Windows machine, from a clean checkout of your branch:

- `uv run python -m pytest tests/` is fully green, with no test deleted, skipped, or loosened
  to get there.
- `uv run python scripts/verify_install.py` passes — all three loaders.
- `uv run python scripts/run_sorting.py --duration 30` completes and writes its outputs.
- The menu launches, and the failing flow works end to end: with Docker Desktop running, a
  `mountainsort5` sort started from the menu finishes, reports success, and leaves no
  temporary `recording_for_docker` folder behind. If Docker is unavailable on this machine,
  say so plainly rather than declaring the bug fixed on the strength of a unit test.
- The noise-floor canary holds: post-bandpass, post-CMR noise lands near 4 µV for every
  sorter. A reading near 1 µV means the channel gain got re-applied and the µV invariant
  described in `CLAUDE.md` is broken.
- `AUDIT_FINDINGS.md` is rewritten as a resolved document: a verdict and a resolution for each
  of the twelve, plus a new section for what you found yourself.
- Each fix is its own commit with a message that says what broke and why the fix is right.

Where a fix changes behaviour that `CLAUDE.md` documents, update `CLAUDE.md` in the same commit.
Do not otherwise rewrite it.

## Boundaries

The working tree may hold uncommitted work that is not yours — the human who set this up edits
this repo concurrently. Commit their changes separately, or leave them alone; never discard,
stash away, or `git checkout --` over a file you did not write, and never force-push or reset.
Work on a branch. Do not push.

Fix what is broken and stop there. No refactors around the fixes, no new abstractions, no
compatibility shims, no features nobody asked for. If a bug's honest fix is a rewrite of a
module, say so and make the case rather than doing it quietly. The raw Blackrock recording in
the repo root is irreplaceable and git-ignored: read it, never write to it.

Regenerating `outputs/` is free and expected. Deleting a saved sort someone may want is not —
leave existing `outputs/<sorter>/` directories in place.

## Autonomy

You are running unattended. Nobody is watching, and nobody can answer a question mid-run, so
asking "shall I proceed?" just stops the work. Take reversible actions freely — edit, run,
test, commit, revert. Pause only for something genuinely mine to decide: a destructive or
irreversible action, a scope change big enough to change what this run is, or a fact you cannot
discover from the repo or the machine.

Before you end a turn, look at your last paragraph. If it is a plan, a promise, or a list of
what you are about to do, do that work now instead of describing it. End the turn when the
task is done or when you are actually blocked on me.

This is a long run. Plan for it and use the whole window, but do not let the window turn over
with significant uncommitted work — commit and write down where you are before that happens.

## Verification

You are on the machine where the bugs live, so verify by running, not by reading. A fix is not
done because the code looks right; it is done when the failing thing passes and the suite is
still green. Run the full suite after each fix, not once at the end — the Textual UI breaks in
ways only the Pilot tests catch.

Fan out with subagents where the work is genuinely independent: the twelve findings verify in
parallel, each in a fresh context that reads the code rather than the audit's conclusions about
it. Use a fresh-context subagent to check your own fixes too — a verifier that did not write the
patch catches what self-review does not. Work directly on anything sequential or needing shared
context; a subagent is not a substitute for a grep.

Before reporting anything as fixed, point to the tool result that shows it. Failing tests get
reported as failing, with their output. Skipped steps get named as skipped. Work that is done
and verified gets stated plainly, without hedging.

## When you finish

The summary is the first thing I will see after being away for hours, and I will not have seen
any of your intermediate work. Write it as a re-grounding for someone who was not there: open
with what happened in one plain sentence, then what broke on Windows and why, then which of the
twelve findings survived contact with the code and which did not. Spell out file names and
terms in full. Anything you need from me goes near the top, explained as if new. Between short
and clear, choose clear.
