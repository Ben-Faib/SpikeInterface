---
name: conductor-health
description: Set a repo up for the conductor pattern, or check a conductor repo's health and clean it up with Ben, iteratively. Health measures how heavy the always-loaded files (CLAUDE.md chain, the memory index) and the state files (ROADMAP, STATUS, DECISIONS, LESSONS, …) have become, how much of them is finished work, stale dates, dead paths and repeats, then walks Ben through cuts one file at a time with the numbers before and after. Use on "/conductor-health", "health check", "our files are bloated", "reset to a better place", "clean up the roadmap", "set up a conductor here", or when a conductor session notices its state files have grown hard to read.
---

# Conductor setup and health

The conductor pattern (the `conductor` skill) only works while its files stay short enough to read at the
start of every session: a plan someone can take in at a glance, a decisions file whose open list is short,
lessons that are still true, and an always-loaded layer that costs little per turn. Files drift the other way
by default: every session appends, nothing is retired. This skill measures that drift and reverses it with
Ben, without losing a ruling or a fact that is still in force.

## Measure first

Run `python3 ~/.claude/skills/conductor-health/scripts/health.py <repo>` (`python` on Windows, which has no `python3`) (add `--json` for the raw numbers).
It is read-only. It reports, per file: estimated tokens and a grade (always-loaded files are held to 2.5k
tokens before "heavy", state files to 8k), the share of the file that is finished work, lines dated over 30
days ago, lines over 600 characters, cited paths that no longer exist, sentences repeated across files, and
branches untouched for three weeks. The numbers point at where to look; they are not a verdict. A long
DECISIONS file of rulings still in force is healthy; a ROADMAP that is 40% finished work is not.

## Health check, with Ben

1. Show the table and, in plain words, the three or four places where weight buys the least: finished work
   still in the plan, closed questions still under "open", lessons that are now encoded in code or rules,
   status paragraphs that restate the plan, dead paths, the same rule said in two files.
2. Agree the order with Ben, then work one file at a time. For each: propose the specific cuts and moves as a
   short list (what goes, where it goes, what stays and why), get his yes or edits, apply, re-run the script
   and show before and after. Then the next file. Ben can stop at any file.
3. Nothing is lost: before the first edit, tag the repo (`git tag pre-cleanup-<date>`), and move retired text
   to an archive file or rely on the tag, saying which in the commit. Rulings in force, open questions, and any
   number the current plan depends on stay. A lesson is retired only when it is encoded somewhere that is
   enforced (a test, a hook, a rule) or no longer true.
4. Commit each file's cleanup on its own, with the before and after token counts in the message. Never edit a
   file a live session is working in; pause it or wait (see `conductor`).

For the always-loaded layer, apply the global rule that each line has a recurring cost: a CLAUDE.md line must
change what the model does in most sessions in that repo; reference material moves to a file it points to.
A "reset to a better place" is the same loop applied to every state file at once, starting from the plan:
rewrite it as where-we-stand (one line per job) plus the queue, with history left to git.

## Setup

For a repo without the pattern: adopt the files it already has (Sylph keeps STATUS.md; do not rename) and add
only what is missing, agreed with Ben: a plan file (where we stand, one line per job; the queue; each job's
definition of done), a decisions file (open: what needs Ben with a recommendation and the default taken;
ruled: dated, his words), a short read order in CLAUDE.md naming them, and the conductor's notes at
`~/.claude/conductor/<repo-dir-name>.md`. If the repo launches unattended runs, give it a launcher like
decantv2's `scripts/run_job.sh` (the run prompt kept in the plan file, so it stays current). Finish by running
the health script, so the repo starts with a baseline.
