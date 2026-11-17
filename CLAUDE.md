@AGENTS.md

# The orchestrating agent

AGENTS.md is the process every agent follows; this part is for the agent that works with the author directly and runs
the work. (Its last section, "Working under a task brief", is for delegated agents, not for you.)

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

The review stays with you, every batch, never scripted away or handed to another agent: the report and the commits (one
per item, its trailer, `git status` clean), the touched test modules re-run outside the agent's sandbox with the real
cache and config folders listed before and after, `wc -l pdfmd.py`, each entry's "Pre-edit state" equal to the commit's
parent, ruff, `split_check` for a move or refactor, and the diff wherever the report shows a design choice, a kept
constant or a skipped item. A stop for a choice no decision covers is yours to settle only when it is mechanical
(recorded, the author told); otherwise it goes to the author.

Landing: a branch that starts at `main` lands by fast-forward; one that does not is cherry-picked with its versions and
"Pre-edit state" lines renumbered. The checkout may be someone's live pdfmd: land when no build from it is running.
From 3.34.0 the landed commits carry your `Reviewed-by` line (AGENTS.md, "Versions and attribution").

CI runs on a branch pushed for that purpose (never `main`; pushing it is a standing permission), at the end of a batch or
wave, not per commit; a job that fails before any test (a runner or package-feed outage) is re-run, not fixed in code.
A release (a push to `main`) waits for the author's go at push time, after the full suite and a green CI.
