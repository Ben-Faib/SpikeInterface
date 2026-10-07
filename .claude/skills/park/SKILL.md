---
name: park
description: Pause a Claude session and put its work somewhere it can be picked up again, or resume parked work. Works on this session ("/park", "park this", "pause and save where we are") or on another live session by name ("park the X session", "tell X to pause"), including Claude Desktop sessions. Parking stops background work, saves uncommitted code on a park branch without touching the main line, and writes a handoff note to ~/.claude/parked/. Use "/park resume" or "resume the parked X work" to continue.
---

# Park

Parking makes a session safe to leave: nothing is still running, nothing is lost, and a fresh session (or the
same one, days later) can continue from one note without re-reading the conversation. The note is the
product; write it for a reader who saw none of the work.

## The park brief

This is what a session does to park itself. To park another session, send it this brief whole with
`SendMessage` to its name (it may not have this skill), after `~/.claude/skills/conductor/scripts/iterm.sh
interrupt <tty>` if it is mid-turn in an iTerm tab.

> Park now: Ben wants to pause this work and continue it later. Finish only the tool call in flight, then:
> 1. Stop everything you started in the background (workflows, shells, monitors, subagents), so nothing wakes
>    you or keeps changing files. Note each workflow's run id so it can resume from cache.
> 2. Save uncommitted work without changing the main line. In a git repo that no other live session shares:
>    `git switch -c park/<topic>-<YYYY-MM-DD>`, commit the files this work created or changed (code, docs,
>    tests) with a message starting "PARKED (unreviewed):", then `git switch -` back. Never commit data,
>    records, credentials, outputs or anything sensitive (patient, personal or corpus files): leave them where
>    they are and list them in the note. If another session shares the checkout, commit nothing; list the
>    files instead.
> 3. Write `~/.claude/parked/<repo-dir-name>/<topic>-<YYYY-MM-DD>.md`: the goal in Ben's terms; what is done
>    and how it was verified; what is in progress, exactly where you stopped and the next concrete step; what
>    is left; open questions for Ben with your recommendation; the park branch and its commit, uncommitted
>    files left in place and why; workflow run ids; how to resume (the branch to merge or switch to, the
>    commands, the files to read first). Under 80 lines; link files rather than restating them.
> 4. Reply with the note's path and one line on its state, then end your turn and wait. Start nothing else.

## After parking (when you parked another session)

Check the claim on disk: the note exists and reads well cold, the park branch holds the listed files
(`git diff --stat <branch-point>..park/...`), the main line's working tree holds only what the note says was
left, and the session is idle. Tell Ben where it is parked and what was left uncommitted. Desktop and remote
sessions do not report back: wait on the note file with a background `until` loop, and if none appears, the
message may be held for Ben's approval in that window; say so.

## Resume

Read the newest note under `~/.claude/parked/<repo>/` (or the one Ben names), bring the park branch back
(`git merge --squash` or switch to it, as the note says), restart any workflow from its run id, confirm the
tests or checks the note names still pass, and continue from its next step. Move the note to
`~/.claude/parked/<repo>/resumed/` once the work is live again.
