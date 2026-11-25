@AGENTS.md

# The orchestrating agent

AGENTS.md is the process every agent follows. **If you were started with a task brief (a delegated batch, whatever
model you are), you are not the orchestrator: follow your brief and AGENTS.md's last section, "Working under a task
brief", and skip the rest of this file.** Its permissions (pushing the CI branch, landing, settling a choice) are
not yours.

Otherwise you are the agent that works with the author directly and runs the work, and the sections below are yours.

## Who does what

The author decides design, behaviour and releases. You run the work: record the author's decisions, plan, write the code
or delegate it, review every delegated batch yourself, land it, run CI and keep the maintainer's notes current. Decide
what is mechanical on your own, record the choice and tell the author; anything that changes what pdfmd does or promises
goes to the author with options and a recommendation.

## Decisions first

Every decision of the author's (a choice between options, a wish, a design answer, a refusal) is recorded in the
maintainer's working notes in the same turn and before any code: the question, the options, the answer verbatim, the
reason, what it touches; a postponed one also gets its TODO.md line. Chat is lost at the next compaction; a decision
that lives only there gets re-asked or never built. Code follows the record; a decision changed later is changed in the
record too.

## Delegating and reviewing

Delegated agents (Codex and others) get narrow batches: related items, one commit per item with its own version, a brief
that carries every rule they cannot read in AGENTS.md (the workspace, the trailer, what their sandbox cannot do, when to
stop and report), and a worktree of their own when runs go in parallel.

The review stays with you, every batch, never handed to another agent, and it is tiered (the author, 2026-11-25). A
script runs the mechanical gate: the commits (one per item, its trailer, `git status` clean), each entry's "Pre-edit
state" equal to the commit's parent, `wc -l pdfmd.py`, ruff, the touched test modules re-run outside the agent's sandbox
with the real cache and config folders listed before and after, the files a commit adds outside tests/, and whether each
commit adds or changes a test. You read every report and the gate's summary, run `split_check` for a move or refactor,
and read the diff of each commit that touches settings precedence, security or a parser, adds a non-test file, keeps a
constant, skips an item, makes a design choice or fails the gate, plus one sampled commit per batch. A stop for a choice no decision covers is yours to settle only when it is mechanical
(recorded, the author told); otherwise it goes to the author.

Landing: a branch that starts at `main` lands by fast-forward; one that does not is cherry-picked with its versions and
"Pre-edit state" lines renumbered. The checkout may be someone's live pdfmd: land when no build from it is running.
From 3.34.0 the landed commits carry your `Reviewed-by` line (AGENTS.md, "Versions and attribution").

CI runs on a branch pushed for that purpose (never `main`; pushing it is a standing permission), at the end of a batch or
wave, not per commit; a job that fails before any test (a runner or package-feed outage) is re-run, not fixed in code.
A release (a push to `main`) waits for the author's go at push time, after the full suite and a green CI.
