# Fable 5 patterns for end-to-end prompts

Distilled from Anthropic's "Prompting Claude Fable 5" guide and the cross-model "Prompting best practices" page (platform.claude.com/docs, retrieved July 2026). Each pattern lists when it earns a place in the prompt and language to adapt. Adapt means adapt: swap in the task's real nouns, cadences, and boundaries. Task-specific phrasing lands; boilerplate gets skimmed.

## Contents

1. Intent framing
2. Act, don't overplan
3. Autonomy contract (checkpoints + turn-ending)
4. State the boundaries
5. Scope discipline
6. Verification
7. Ground progress claims
8. Parallel subagents
9. State and memory (multi-session runs)
10. Context-budget reassurance
11. Final summary readability
12. Output selection and brevity
13. Send-to-user tool (harness note)
14. Effort levels
15. Harness and timeout notes
16. Cross-model fundamentals worth keeping

---

## 1. Intent framing

**When:** always. This is the single highest-leverage pattern. Fable connects the task to relevant information when it knows why the request exists, instead of inferring intent on its own.

**Shape:** open the prompt with the larger goal, the audience, and what the output enables, then the request.

> I'm building [larger thing] for [who]. They need [what the output enables]. [Constraints of the domain or codebase worth knowing.] With that in mind: [the task].

## 2. Act, don't overplan

**When:** the task has any ambiguity, or prior runs showed option-surveying and re-litigation.

> When you have enough information to act, act. Don't re-derive facts already established here, re-open decisions already made, or narrate options you won't pursue. If you're weighing a choice, give a recommendation rather than a survey. (Your private thinking is exempt; this is about the work and the messages.)

## 3. Autonomy contract (checkpoints + turn-ending)

**When:** any run the user will not be watching (headless, overnight, long unattended stretches). This is the fix for two documented failure modes: pausing to ask permission it doesn't need, and ending a turn on a text-only statement of intent with no tool call behind it.

Checkpoint half, for interactive-but-long runs:

> Pause for me only when the work genuinely requires me: a destructive or irreversible action, a real scope change, or input only I can provide. If you hit one of those, ask and end the turn instead of ending on a promise.

Full contract, for autonomous pipelines:

> You are operating autonomously. I'm not watching in real time and can't answer questions mid-task, so asking "Want me to...?" or "Shall I...?" blocks the work. For reversible actions that follow from this request, proceed without asking. Before ending your turn, check your last paragraph: if it's a plan, a question, a list of next steps, or a promise about work not yet done ("I'll...", "let me know when..."), do that work now with tool calls. End the turn only when the task is complete or you're blocked on input only I can provide.

## 4. State the boundaries

**When:** always, sized to the risk. Fable can occasionally take unrequested actions (drafting artifacts nobody asked for, defensive git-branch backups). Name what is out of scope and what needs confirmation.

For analysis-vs-action ambiguity:

> When I'm describing a problem or thinking out loud, the deliverable is your assessment. Report findings and stop; don't apply a fix until asked. Before any command that changes system state, check that the evidence supports that specific action. A symptom that pattern-matches a known failure can still have a different cause.

For destructive-action confirmation (adapt the examples to the actual domain):

> You're encouraged to take local, reversible actions freely. For actions that are hard to reverse, visible to others, or destructive in this project ([deleting X, pushing to Y, sending Z]), ask first. Don't use destructive shortcuts around obstacles, like bypassing safety checks or discarding unfamiliar files that may be in-progress work.

## 5. Scope discipline

**When:** higher effort settings, or any codebase task where unrequested tidying and refactoring would be unwelcome.

> Don't add features, refactor, or introduce abstractions beyond what the task requires. A bug fix doesn't need surrounding cleanup; a one-shot operation rarely needs a helper. Don't design for hypothetical future requirements: do the simplest thing that works well. Skip error handling and validation for scenarios that can't happen; trust internal code and framework guarantees, and validate only at system boundaries (user input, external APIs). Change the code instead of adding flags or compatibility shims.

Companion, for test-driven tasks:

> Write a general solution, not one shaped to the test cases. Tests verify correctness; they don't define it. If a test itself is wrong or the task is infeasible, say so rather than working around it.

## 6. Verification

**When:** any run longer than a single sitting, and any task where correctness is checkable. Separate fresh-context verifier subagents outperform self-critique.

> Establish a method for checking your own work as you build, and run it every [interval or milestone], verifying against the specification with fresh-context subagents where possible. Before finishing, verify the result against [the definition of done] and include the evidence.

Give the run something concrete to verify against: a spec section, a tests file, a rendering check, a numeric target. Verification instructions with nothing to verify against are decoration.

## 7. Ground progress claims

**When:** every long run. In Anthropic's testing this nearly eliminated fabricated status reports, even on tasks designed to elicit them.

> Before reporting progress, audit each claim against an actual tool result from this session. Report only what you can point to evidence for; if something isn't verified yet, say so explicitly. Report outcomes faithfully: failing tests get reported as failing with their output, skipped steps get named as skipped, and finished-and-verified work gets stated plainly without hedging.

## 8. Parallel subagents

**When:** the environment supports subagents (Claude Code, Cowork, custom harnesses with a dispatch tool). Fable dispatches them readily and manages long-lived ones well; prefer async over blocking, and prefer long-lived subagents that keep context across subtasks (cache savings, no bottleneck on the slowest worker).

> Delegate independent subtasks to subagents and keep working while they run. Intervene if one goes off track or is missing context it needs.

If overuse appears (subagents spawned where a direct grep would do):

> Use subagents for parallelizable, isolated, or independent workstreams. For simple sequential work or anything needing shared context across steps, work directly.

## 9. State and memory (multi-session runs)

**When:** the task spans multiple context windows or repeated sessions. Skip entirely for single-session work.

Core moves, from the multi-window guidance:

- First window sets up the framework: tests in a structured file (e.g., `tests.json`), an `init.sh` for servers/linters/test suites, a `progress.txt`. Later windows iterate against them.
- Fable rediscovers state from the filesystem extremely well; a fresh window plus prescriptive re-entry beats compaction in many cases. Re-entry lines: "Review progress.txt, tests.json, and the git log. Run the fundamental integration test before building anything new."
- Git is the state tracker: meaningful commits are both a log and restorable checkpoints.
- Protect the tests: "Removing or editing tests to get green is unacceptable; it hides missing or broken functionality."

Lesson memory, for agents that run repeatedly:

> Keep notes in [directory]: one lesson per file with a one-line summary on top. Record corrections and confirmed approaches alike, with why they mattered. Don't duplicate what the repo or history already records; update existing notes rather than adding near-duplicates, and delete notes that turn out wrong.

Bootstrapping memory from history:

> Reflect on our previous sessions. Use subagents to identify the core themes and lessons, store them in [directory], and reference it in future runs.

Encouraging full use of a window:

> This is a long task, so plan your work and feel free to spend your whole output window on it. Just don't run out of context with significant uncommitted work; commit and note progress before the window turns over.

## 10. Context-budget reassurance

**When:** only if the harness surfaces a remaining-token countdown to the model (avoid surfacing one at all if possible). Counters trigger premature wrap-up, self-summarizing, and new-session suggestions.

> You have ample context remaining. Don't stop, summarize, or suggest a new session on account of context limits. Continue the work.

## 11. Final summary readability

**When:** long or agentic runs where the user returns after being away. Untreated, Fable can hand back arrow-chain shorthand, invented labels, and references to thinking the user never saw.

> Terse shorthand between tool calls is fine; that's you thinking out loud. The final summary is different: it's for a reader who saw none of it. Write it as a re-grounding, not a continuation. Open with the outcome in one plain sentence, then the one or two things you need from me, each explained as if new. Drop the working vocabulary: complete sentences, terms spelled out, no arrow chains or labels invented mid-run. Identifiers (files, commits, flags) each get their own plain-language clause. Between short and clear, choose clear.

## 12. Output selection and brevity

**When:** the user wants tight reports rather than essays. One short instruction replaces enumerating every verbose pattern.

> Lead with the outcome: the first sentence after finishing should answer "what happened" or "what did you find", the thing I'd ask for with "just give me the TLDR". Supporting detail comes after. Keep it short by being selective (drop details that wouldn't change what I do next), not by compressing into fragments, abbreviations, or jargon. Readable beats merely brief.

## 13. Send-to-user tool (harness note)

**When:** the user is building an async harness and the UX depends on the user seeing certain content verbatim mid-run (a deliverable, exact numbers, a direct answer). This is a scaffolding recommendation to relay in the delivery note, not usually prompt text. Tool inputs are never summarized, so content routed through the tool arrives intact. Defining the tool isn't enough; Fable rarely calls it unprompted, so pair it with:

> Between tool calls, when you have content I must read verbatim (a partial deliverable, a direct answer to a question I asked), send it via send_to_user. Use it only for user-facing content, never for narration or reasoning.

## 14. Effort levels

Effort is the primary intelligence/latency/cost control on Fable 5. Recommend in the delivery note:

- `high`: the default for most real tasks.
- `xhigh`: capability-critical work (hardest problems, one-shot correctness matters). Expect excellent verification behavior but also more deliberation than routine work needs.
- `medium` / `low`: routine work and quick interactive loops; these still often beat prior models at `xhigh`.

If a task completes but dawdles, lowering effort is the first lever, before adding prompt constraints.

## 15. Harness and timeout notes

Relay when relevant, in the delivery note rather than the prompt:

- Individual turns can run many minutes at higher effort and autonomous runs can extend for hours. Raise client timeouts, use streaming, and prefer async check-ins (scheduled jobs) over blocking.
- Thinking is always on and adaptive; there are no thinking budgets. Never instruct the model to reproduce its reasoning in the response (reasoning_extraction refusals; see anti-patterns in SKILL.md).
- Fable runs safety classifiers around offensive cybersecurity and biology/life-sciences content; benign work in those areas can occasionally trip them. Harnesses should configure fallback to Opus 4.8 for `stop_reason: "refusal"`.
- Prefills on the last assistant turn are not supported on current models; steer with instructions instead.

## 16. Cross-model fundamentals worth keeping

These predate Fable and still hold; use them quietly rather than ceremonially.

- **Golden rule of clarity:** if a colleague with minimal context would be confused by the prompt, the model will be too.
- **XML tags** to separate instructions, context, inputs, and examples when a prompt mixes them; consistent, descriptive names.
- **Long inputs at the top**, query and instructions after; for very long documents, ask for grounding quotes before the task.
- **Examples (3-5)** are the most reliable format-steering tool: relevant, diverse, wrapped in example tags.
- **Say what to do, not what to avoid** ("write flowing prose paragraphs" over "no markdown").
- **A role line** in the system prompt when the run benefits from a stance ("You are a senior reviewer for...").
- **Self-check line** near the end for checkable outputs: "Before finishing, verify against [criteria]."
