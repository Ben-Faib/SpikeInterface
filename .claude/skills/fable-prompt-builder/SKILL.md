---
name: fable-prompt-builder
description: Compose tight, well-scoped, end-to-end prompts for Claude Fable 5 (and Mythos 5) agentic runs, grounded in Anthropic's official Fable 5 prompting guidance. Use this skill whenever the user wants a prompt written, drafted, tightened, or reviewed for Fable, for Claude Code, or for any long-running, autonomous, multi-hour or multi-session agent task. Trigger on requests like "write me a prompt for...", "turn this into a Fable prompt", "prep a prompt for an overnight run", "make this agent-ready", and also when the user hands over a rough task description, spec, or ticket and wants it converted into a runnable end-to-end prompt. Also use it to audit existing prompts, CLAUDE.md files, or skills for patterns that degrade Fable 5.
---

# Fable Prompt Builder

This skill turns a task description into a prompt that Claude Fable 5 can execute as a long, autonomous, end-to-end run with little or no mid-run supervision. The person invoking it wants one strong prompt in one pass, not a back-and-forth refinement session. Deliver accordingly.

Fable 5 differs from earlier models in ways that change how prompts should be written. It sustains multi-hour and multi-day runs, follows brief instructions without needing every behavior enumerated, dispatches parallel subagents readily, and is actively degraded by over-prescriptive prompts carried over from earlier models. The job of a Fable prompt is to supply intent, boundaries, and verification, and then get out of the way.

## Operating principles

**Intent first.** Fable performs better when it understands why the task exists and who the output is for, because that context informs the thousand small decisions a long run requires. Every prompt opens with the reason, not the request.

**Autonomy-preserving.** Say what done looks like and where the hard boundaries are; do not script the route. If you find yourself writing a ten-step procedure, ask whether "here is the goal, here is how to verify it" would serve better. Prescriptive step lists are for cases where order genuinely matters (migrations, protocols), not a default.

**Scale to the run.** A two-hour refactor does not need a memory system, and a task with no subagents available does not need subagent guidance. Include a section only when the run needs it. A tight 40-line prompt beats a 250-line kitchen sink, because padding dilutes the instructions that matter.

**One pass, assumptions stated.** Harvest everything you can from the conversation, the repo, and any files before asking the user anything. If something material is genuinely unknowable (the definition of done, a hard boundary, the execution environment), ask once, in a single batch. Otherwise make the sensible assumption and flag it in a short note under the delivered prompt.

## Workflow

### 1. Establish the run profile

Determine, from context where possible:

- **Task and intent**: what is being built or done, for whom, and what the output enables.
- **Definition of done**: a verifiable end state. If the user gave a vague goal, sharpen it into something checkable (tests pass, file exists and renders, benchmark reaches N, report covers X).
- **Environment**: Claude Code interactive, Claude Code headless or overnight, an API harness, Cowork. This decides which sections apply (subagents, send-to-user tool, checkpoint behavior).
- **Duration class**: single sitting (minutes to an hour), long single session (hours), or multi-session (days, fresh context windows). This decides whether state and memory sections earn their place.
- **Hard boundaries**: what is destructive or irreversible in this domain (prod deploys, force pushes, data deletion, messages to real people), plus anything explicitly out of scope.

### 2. Choose the delivery shape

Default to a single self-contained task prompt (the thing pasted into Claude Code or sent as the user message). If the user is building a harness, they may want a system prompt plus a task prompt. If they want persistent behavior across many runs, a CLAUDE.md addendum or a skill is the right shape. Ask only if the shape is genuinely ambiguous and the choice changes the content.

### 3. Compose

Build the prompt from the skeleton below. For each section you include, consult `references/fable5-patterns.md` for the specific behavioral pattern and ready-to-adapt language. Adapt the language to the task rather than pasting boilerplate: generic boilerplate reads as noise, task-specific phrasing reads as instruction. Write the prompt in the second person, addressed to the model that will run it.

### 4. Self-review

Reread the draft against the anti-pattern list below and cut anything not pulling its weight. Then confirm the prompt answers the three questions a fresh Fable instance would have: What am I making and why? How do I know it is correct? When do I stop or ask?

### 5. Deliver

Present the prompt in a single fenced code block, followed by a short note (a few sentences, not a report) covering the recommended effort level, any assumptions made, and anything the user should set up in the harness (client timeouts, a send-to-user tool, a notes directory). If the run is headless or the prompt is long, also save it as a `.md` file so it can be piped or referenced.

## The skeleton

Sections in composition order. The first four are almost always present; the rest earn their place per the run profile.

1. **Context and intent.** Two to five sentences: the larger goal, who it is for, what the output enables, relevant constraints of the codebase or domain.
2. **The task.** The actual request, concrete and scoped.
3. **Definition of done.** Verifiable end conditions. Prefer conditions the model can check itself (tests, builds, rendered output) over conditions only a human can judge.
4. **Boundaries.** What not to do: out-of-scope items, destructive actions that require confirmation, over-engineering guardrails. See "State the boundaries" and "Scope discipline" in the reference.
5. Autonomy and checkpoints. When to proceed without asking, and the short list of situations that genuinely warrant pausing. Essential for headless and overnight runs. See "Autonomy contract".
6. Verification. The self-checking cadence and method, with fresh-context verifier subagents where available. See "Verification".
7. Progress reporting. Evidence-grounded claims only. Cheap to include and it nearly eliminates fabricated status reports on long runs. See "Ground progress claims".
8. Subagents. Only when the environment has them. See "Parallel subagents".
9. State and memory. Only for multi-session runs: progress files, structured test tracking, setup scripts, git discipline. See "State and memory".
10. Communication. How the final summary should read, since it is the user's first look at hours of unattended work. See "Final summary readability".

## Anti-patterns that degrade Fable 5

These come straight from the documented behavioral differences. Auditing for them is also the core of any "review my existing prompt" request.

- **Enumerated micro-behaviors and ALL-CAPS MUSTs.** Fable follows a brief instruction with a reason better than a list of ten prohibitions. If a draft has a bulleted list of forbidden behaviors, collapse it into one or two sentences that convey the principle.
- **Over-prescription.** Step-by-step scripts, mandated tool sequences, and rigid templates written for older models. Fable's defaults often beat the old workaround; remove the instruction and let the model work.
- **Show-your-reasoning instructions.** Anything telling the model to echo, transcribe, or explain its internal reasoning in the response text can trigger the reasoning_extraction refusal category and cause fallbacks to Opus. Reasoning visibility belongs to the harness (thinking blocks, a send-to-user tool), never to the prompt.
- **Context-budget countdowns.** Surfacing remaining-token counts makes Fable wrap up early, trim its work, or suggest a new session. Avoid mentioning budgets; if the harness must show them, include the ample-context reassurance from the reference.
- **Anti-laziness prompting.** "If in doubt, use the tool", "ALWAYS search first", "be extremely thorough". These were crutches for models that undertriggered. On Fable they cause overtriggering, overplanning, and unrequested extra work.
- **Ending on a promise.** Prompts for unattended runs that never define turn-ending behavior can get a text-only "I'll now run X" with no tool call behind it. The autonomy contract in the reference addresses this; include it for any run the user will not be watching.

## Audit mode

When the user brings an existing prompt, skill, or CLAUDE.md to modernize: read it, mark every line against the anti-pattern list, identify which skeleton sections are missing or bloated, and return a rewritten version plus a three-or-four-line changelog of what was cut and why. Cutting is usually the bigger win than adding.

## Reference

`references/fable5-patterns.md` holds the distilled Fable 5 behavioral patterns with adaptable instruction language, organized to match the skeleton, plus effort guidance and harness notes. Read it when composing; it is the source this skill is built on. The live document is at https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5 and is worth fetching when something seems version-sensitive and web access is available.
