#!/usr/bin/env bash
# Open a conductor session for a repo. Inside WezTerm, or on Windows: a new tab in the running WezTerm window
# (via the conductor's term.sh). Otherwise iTerm2 on macOS: a new tab in the front window, or a new window if none.
# Usage: open-conductor.sh <repo-dir> <start-prompt-file> [session-name] [--dry-run | --here]
#   --here runs the conductor in this terminal, and leaves a shell behind when it exits
#   (what the Windows Desktop shortcut does inside the new WezTerm window it opens).
set -euo pipefail
repo=$1 prompt=$2 name=${3:-conductor} mode=${4:-}
line="cd $(printf %q "$repo") && claude --name $(printf %q "$name") --model opus --effort xhigh --permission-mode auto \"\$(cat $(printf %q "$prompt"))\""
if [ "$mode" = --dry-run ]; then echo "$line"; exit 0; fi
if [ "$mode" = --here ]; then
  eval "$line" || echo "claude exited with status $?"
  exec bash -li
fi
if [ -n "${WEZTERM_PANE:-}" ] || [ "$(uname -s)" != Darwin ]; then
  exec "$HOME/.claude/skills/conductor/scripts/term.sh" open "$repo" "$line"
fi
osascript - "$line" <<'OSA'
on run argv
  tell application "iTerm2"
    activate
    if (count of windows) = 0 then
      set w to (create window with default profile)
      tell current session of w to write text (item 1 of argv)
    else
      tell current window
        set t to (create tab with default profile)
        tell current session of t to write text (item 1 of argv)
      end tell
    end if
  end tell
end run
OSA
