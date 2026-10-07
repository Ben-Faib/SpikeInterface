---
name: giga-park
description: Park the head conductor itself, so Ben can close everything and reopen the whole setup later with one click. Parks every run session under it, writes the conductor's notes and a start prompt that opens with the decisions waiting on Ben, and puts a clickable "<Repo> Conductor" app on the Desktop that reopens the conductor in iTerm2 (a new tab, or a new window if none) at xhigh effort. Use on "/giga-park", "park the conductor", "park everything", "I'm stopping for the day", or before restarting iTerm or the machine. Only for a head conductor session; to park one worker session use `park`.
---

# Giga-park

The conductor holds the picture in its head; giga-park puts all of it on disk, so that a fresh conductor
opened from the Desktop is as useful in its first message as this one is now. Done well, Ben clicks the icon
tomorrow and reads: what is live, what is waiting on him with a recommendation for each, and what will run on
his word. Nothing is still running, nothing that matters is uncommitted, nothing has to be remembered.

1. **Park the workers.** For each live run session under this conductor (`ListAgents`, and the notes file),
   park it by the `park` skill's brief, or confirm it is idle with its work committed. Verify on disk: its
   commits and branches, its Paused note or checklist resume lines, a clean main-line working tree. A
   session whose terminal is gone is fine if its work is committed; say so.
2. **Write the conductor's notes**, `~/.claude/conductor/<repo>.md`: live sessions (none, after step 1, or
   which and why), parked branches and resume commands, Ben's standing rulings in force (spend, push, deploy),
   the queue, and every decision waiting on him with the plain-words issue, options, recommendation and
   default. Record in the repo's own files (decisions, plan) anything only the conversation held, and commit
   it if no live session shares the checkout.
3. **Write the start prompt**, `~/.claude/conductor/<repo>-start.md`: begins with `/conductor`, then tells the
   reopened conductor to open with the bottom line, the decisions waiting on Ben (the few that are his first,
   then the rest grouped; a table where it helps), and what it would launch next, then wait. Specific to the
   repo's present state; regenerate it on every giga-park.
4. **Make the launcher**: `~/.claude/skills/giga-park/scripts/make_launcher.sh <repo> "<Repo> Conductor"`.
   It installs `~/.claude/conductor/open-conductor.sh` and compiles `~/Desktop/<Repo> Conductor.app`, which
   opens iTerm2 and runs `claude --name <repo>-conductor --model opus --effort xhigh --permission-mode auto`
   with the start prompt. Check it with `open-conductor.sh <repo> <prompt> <name> --dry-run`. The first click
   asks macOS to let the app control iTerm2; Ben allows it once.
5. **Tell Ben** in a few lines: what was parked and where, what is waiting on him, and that the Desktop icon
   reopens it all. Then end; do not start new work.
