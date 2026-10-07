#!/usr/bin/env bash
# Make (or refresh) a clickable Desktop launcher that reopens a repo's head conductor in iTerm2.
# Usage: make_launcher.sh <repo-dir> [App Title]
#   writes ~/.claude/conductor/<repo>-start.md (only if missing; the parking conductor fills it in),
#   installs ~/.claude/conductor/open-conductor.sh, and compiles ~/Desktop/<App Title>.app.
set -euo pipefail
repo=$(cd "$1" && pwd); name=$(basename "$repo"); title=${2:-"$name Conductor"}
here=$(cd "$(dirname "$0")" && pwd); dir="$HOME/.claude/conductor"; mkdir -p "$dir"
install -m 755 "$here/open-conductor.sh" "$dir/open-conductor.sh"
prompt="$dir/$name-start.md"
[ -f "$prompt" ] || printf '%s\n' "/conductor You are Ben's head conductor for $name ($repo), reopened from his desktop launcher. Orient from the files (the conductor skill's start steps and ~/.claude/conductor/$name.md), then open with the bottom line, the decisions waiting on Ben (plain words, options, your recommendation, the default in force), and what you would launch next. Then wait for Ben." > "$prompt"
app="$HOME/Desktop/$title.app"; rm -rf "$app"
osacompile -o "$app" -e "do shell script \"\$HOME/.claude/conductor/open-conductor.sh $(printf %q "$repo") $(printf %q "$prompt") $(printf %q "$name-conductor")\"" 2>/dev/null
echo "$app"
