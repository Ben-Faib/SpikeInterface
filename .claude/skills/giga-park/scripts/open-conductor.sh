#!/usr/bin/env bash
# Open a conductor session for a repo in iTerm2: a new tab in the front window, or a new window if none.
# Usage: open-conductor.sh <repo-dir> <start-prompt-file> [session-name] [--dry-run]
set -euo pipefail
repo=$1 prompt=$2 name=${3:-conductor}
line="cd $(printf %q "$repo") && claude --name $(printf %q "$name") --model opus --effort xhigh --permission-mode auto \"\$(cat $(printf %q "$prompt"))\""
if [ "${4:-}" = --dry-run ]; then echo "$line"; exit 0; fi
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
