#!/usr/bin/env bash
# Make (or refresh) a clickable Desktop launcher that reopens a repo's head conductor: on macOS an app that
# opens it in iTerm2, on Windows a shortcut that opens it in a new WezTerm window.
# Usage: make_launcher.sh <repo-dir> [App Title]
#   writes ~/.claude/conductor/<repo>-start.md (only if missing; the parking conductor fills it in),
#   installs ~/.claude/conductor/open-conductor.sh, and makes ~/Desktop/<App Title>.app (.lnk on Windows).
set -euo pipefail
repo=$(cd "$1" && pwd); name=$(basename "$repo"); title=${2:-"$name Conductor"}
here=$(cd "$(dirname "$0")" && pwd); dir="$HOME/.claude/conductor"; mkdir -p "$dir"
install -m 755 "$here/open-conductor.sh" "$dir/open-conductor.sh"
prompt="$dir/$name-start.md"
[ -f "$prompt" ] || printf '%s\n' "/conductor You are Ben's head conductor for $name ($repo), reopened from his desktop launcher. Orient from the files (the conductor skill's start steps and ~/.claude/conductor/$name.md), then open with the bottom line, the decisions waiting on Ben (plain words, options, your recommendation, the default in force), and what you would launch next. Then wait for Ben." > "$prompt"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    # The shortcut starts WezTerm, which runs Git Bash, which runs open-conductor.sh --here. The values reach
    # PowerShell through the environment, so no quoting layer can mangle them.
    gui='C:\Program Files\WezTerm\wezterm-gui.exe'; bash='C:\Program Files\Git\bin\bash.exe'
    [ -f "$(cygpath -u "$gui")" ] || { echo "make_launcher.sh: WezTerm is not installed at $gui" >&2; exit 1; }
    run="$(printf %q "$dir/open-conductor.sh") $(printf %q "$repo") $(printf %q "$prompt") $(printf %q "$name-conductor") --here"
    desktop=$(powershell.exe -NoProfile -Command "[Environment]::GetFolderPath('Desktop')" | tr -d '\r')
    LNK="$desktop\\$title.lnk" TARGET="$gui" WD="$(cygpath -w "$repo")" \
      ARGS="start --cwd \"$(cygpath -w "$repo")\" -- \"$bash\" -li -c \"$run\"" MSYS_NO_PATHCONV=1 \
      powershell.exe -NoProfile -Command '$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath = $env:TARGET; $s.Arguments = $env:ARGS; $s.WorkingDirectory = $env:WD; $s.IconLocation = $env:TARGET + ",0"; $s.Save()'
    echo "$desktop\\$title.lnk"
    ;;
  *)
    app="$HOME/Desktop/$title.app"; rm -rf "$app"
    osacompile -o "$app" -e "do shell script \"\$HOME/.claude/conductor/open-conductor.sh $(printf %q "$repo") $(printf %q "$prompt") $(printf %q "$name-conductor")\"" 2>/dev/null
    echo "$app"
    ;;
esac
