# Skills shipped with this repo

`run-spikeinterface`, `status` and `verify-spike` load as project skills.

`conductor`, `conductor-health`, `giga-park` and `park` are copies of Ben's global skills, kept here so
another machine can install them. Their instructions call scripts at `~/.claude/skills/<name>/scripts/`,
so install them globally after cloning:

    cp -R .claude/skills/{conductor,conductor-health,giga-park,park} ~/.claude/skills/

Tabs are driven by `conductor/scripts/term.sh`: WezTerm on Windows (or on macOS when the conductor runs in
WezTerm), otherwise it hands off to `iterm.sh` for iTerm2 on macOS. On Windows, install WezTerm and give it a
config whose `default_prog` is Git Bash (Ben's is `~/.wezterm.lua`); `giga-park`'s launcher then makes a
Desktop shortcut that opens the conductor in a new WezTerm window, where macOS gets an iTerm2 app. Use
`python`, not `python3`, for `conductor-health` on Windows.
