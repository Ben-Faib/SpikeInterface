# Skills shipped with this repo

`run-spikeinterface`, `status` and `verify-spike` load as project skills.

`conductor`, `conductor-health`, `giga-park` and `park` are copies of Ben's global skills, kept here so
another machine can install them. Their instructions call scripts at `~/.claude/skills/<name>/scripts/`,
so install them globally after cloning:

    cp -R .claude/skills/{conductor,conductor-health,giga-park,park} ~/.claude/skills/

The iTerm2 and Desktop-launcher scripts (`conductor/scripts/iterm.sh`, `giga-park/scripts/*.sh`) are
macOS-only; on Windows the status, rulings, health and `park` parts work, launching tabs does not.
