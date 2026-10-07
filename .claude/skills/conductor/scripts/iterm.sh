#!/usr/bin/env bash
# iTerm2 helpers for a conductor session. Usage:
#   iterm.sh open <dir> <command...>   new tab in the current window, runs the command; prints the tab's tty
#   iterm.sh list                      every session: tty | name
#   iterm.sh screen <tty> [lines]      the last lines of a session's screen (default 30)
#   iterm.sh interrupt <tty>           sends Esc (stops a Claude session's current turn; its prompt box is untouched)
# Typing into a Claude session does NOT submit it (Return cannot be sent without Accessibility rights);
# send instructions with SendMessage to the session's --name instead.
set -euo pipefail
cmd=${1:-}; shift || true
case "$cmd" in
  open)
    dir=$1; shift
    line="cd $(printf %q "$dir") && $*"
    osascript - "$line" <<'OSA'
on run argv
  tell application "iTerm2"
    if (count of windows) = 0 then create window with default profile
    tell current window
      set t to (create tab with default profile)
      tell current session of t
        write text (item 1 of argv)
        return tty
      end tell
    end tell
  end tell
end run
OSA
    ;;
  list)
    osascript -e 'tell application "iTerm2"
  set out to ""
  repeat with w in windows
    repeat with t in tabs of w
      repeat with s in sessions of t
        set out to out & (tty of s) & " | " & (name of s) & linefeed
      end repeat
    end repeat
  end repeat
  return out
end tell'
    ;;
  screen|interrupt)
    tty=$1; n=${2:-30}
    osascript - "$cmd" "$tty" <<'OSA' | { [ "$cmd" = screen ] && grep -v '^[[:space:]]*$' | tail -n "$n" || cat; }
on run argv
  tell application "iTerm2"
    repeat with w in windows
      repeat with t in tabs of w
        repeat with s in sessions of t
          if tty of s is (item 2 of argv) then
            if (item 1 of argv) is "interrupt" then
              tell s to write text (character id 27) newline NO
              return "interrupted " & (item 2 of argv)
            end if
            return text of s
          end if
        end repeat
      end repeat
    end repeat
  end tell
  return "no session on " & (item 2 of argv)
end run
OSA
    ;;
  *) sed -n 2,8p "$0"; exit 1 ;;
esac
