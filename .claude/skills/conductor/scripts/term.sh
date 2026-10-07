#!/usr/bin/env bash
# Terminal-tab helpers for a conductor session: WezTerm (Windows, or macOS when run inside WezTerm),
# otherwise iTerm2 on macOS (hands off to iterm.sh). Usage:
#   term.sh open <dir> <command...>   new tab in the current window, types the command and presses Return; prints the tab's id
#   term.sh list                      every tab (WezTerm: pane id, title, cwd; iTerm2: tty | name)
#   term.sh screen <id> [lines]       the last lines of a tab's screen (default 30)
#   term.sh interrupt <id>            sends Esc (stops a Claude session's current turn; its prompt box is untouched)
#   term.sh send <id> <text...>       pastes the text and presses Return: submits a prompt to a Claude session (WezTerm only)
# The id is a WezTerm pane id, or an iTerm2 tty. Instruct sessions with SendMessage to their --name; `send`
# is for a session SendMessage cannot reach, or a slash command (/park, /exit).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
if [ -z "${WEZTERM_PANE:-}" ] && [ "$(uname -s)" = Darwin ]; then exec "$here/iterm.sh" "$@"; fi

# Git Bash rewrites arguments that look like paths (/exit -> C:/Program Files/Git/exit); never here.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
wez=$(command -v wezterm 2>/dev/null || true)
for c in "/c/Program Files/WezTerm/wezterm.exe" /Applications/WezTerm.app/Contents/MacOS/wezterm; do
  [ -z "$wez" ] && [ -x "$c" ] && wez=$c
done
[ -n "$wez" ] || { echo "term.sh: WezTerm not found (install it, or run inside iTerm2 on macOS)" >&2; exit 1; }
w() { "$wez" cli "$@"; }
winpath() { if command -v cygpath >/dev/null; then cygpath -w "$1"; else printf '%s' "$1"; fi; }

# Outside a WezTerm pane the CLI's own socket discovery fails on Windows; point it at the newest live GUI.
if [ -z "${WEZTERM_UNIX_SOCKET:-}" ]; then
  for s in $(ls -t "$HOME"/.local/share/wezterm/gui-sock-* 2>/dev/null); do
    WEZTERM_UNIX_SOCKET=$(winpath "$s") "$wez" cli list >/dev/null 2>&1 && { export WEZTERM_UNIX_SOCKET=$(winpath "$s"); break; }
  done
  [ -n "${WEZTERM_UNIX_SOCKET:-}" ] || { echo "term.sh: no running WezTerm window to talk to; open WezTerm first" >&2; exit 1; }
fi

cmd=${1:-}; shift || true
case "$cmd" in
  open)
    dir=$(winpath "$1"); shift
    if [ -n "${WEZTERM_PANE:-}" ]; then pane=$(w spawn --pane-id "$WEZTERM_PANE" --cwd "$dir")
    else
      first=$(w list --format json | grep -o '"pane_id": *[0-9]*' | head -1 | grep -o '[0-9]*$' || true)
      if [ -n "$first" ]; then pane=$(w spawn --pane-id "$first" --cwd "$dir"); else pane=$(w spawn --new-window --cwd "$dir"); fi
    fi
    # Wait (up to ~10 s) for the shell's prompt, so the command lands at a ready prompt.
    for _ in $(seq 50); do
      w get-text --pane-id "$pane" 2>/dev/null | grep -Eq '[$#%>] *$' && break
      sleep 0.2
    done
    w send-text --pane-id "$pane" --no-paste "$*"$'\r'
    echo "$pane"
    ;;
  list)
    w list
    ;;
  screen)
    id=$1; n=${2:-30}
    w get-text --pane-id "$id" | { grep -v '^[[:space:]]*$' || true; } | tail -n "$n"
    ;;
  interrupt)
    w send-text --pane-id "$1" --no-paste $'\x1b'
    echo "interrupted $1"
    ;;
  send)
    id=$1; shift
    w send-text --pane-id "$id" "$*"
    sleep 0.5
    w send-text --pane-id "$id" --no-paste $'\r'
    echo "sent to $id"
    ;;
  *) sed -n 2,10p "$0"; exit 1 ;;
esac
