# pdfmd

Converts Markdown (and other Pandoc-readable formats) to PDF or another
output format via Pandoc. Started as `batchmd`, a twenty-line `pypandoc`
batch script (see the changelog's v0.1.0); has since grown auto-discovery for metadata files,
LaTeX preambles, Lua filters, and fonts, a multi-engine PDF fallback chain,
a `pdfmd-options:` front-matter block, batch/report/book modes, and its
own generic table-width-balancing Lua filter (`lib/pdfmd_lua/table_width.lua`) —
see the module's own docstring (`pdfmd.py`'s opening lines) for the
current, authoritative feature list; don't rely on this file for feature
details, only for process.

This repository is public. Don't commit personal details (absolute
`/Users/...` home paths, names, anything local-only) into `pdfmd.py`,
`CHANGELOG.md` or this file — use `~/` paths and "the author".

## Before touching pdfmd.py

**Commit first.** Git replaces manual backup copies: before any edit,
`git status` must be clean (commit or stash anything pending), so the
last commit is the exact pre-edit state. Don't create `.bak` copies.
Backups from before v3.9.2 live in `~/dev/python-projects/backups/`; the
changelog's older "Backup reference" lines point there.

**Update the changelog in the same commit**, not after: the code change,
its `CHANGELOG.md` entry and the `PDFMD_VERSION` bump go into one commit,
and new changelog entries cite that commit instead of a backup file. See `CHANGELOG.md` for the format
and why its numbering starts at 2.0.0 (the 1.x entries at the end of the
changelog are an after-the-fact reconstruction and not reliable).

**Verify before declaring a fix done — a synthetic test is not enough.**
The table-width bug fixed in v2.0.0 is the concrete example: compiling the
generated `.tex` directly with `lualatex` looked correct, and only running
the FULL `pdfmd` pipeline on the same source revealed the bug (`pdfmd`
inserts its own extra `--lua-filter` ahead of anything project-specific).
If a fix touches how `pdfmd` builds its Pandoc command, test through
`pdfmd` itself, not just through the Pandoc/LaTeX commands it constructs
internally.

## A new flag or a new pdfmd-options key

Add it to `lib/pdfmd_setup/inventory.py` in the same commit: either the `--setup` row that sets it for
every document (`lib/pdfmd_setup/registry.py`, with its `UNSET` words) or an `Omitted` entry with the
reason. `tests/test_setup.py` (`Completeness`) fails until it is in one of them.

## Layout

The `pdfmd_*` packages live in `lib/` (names unchanged, so `import pdfmd_lua` is as it always was); `pdfmd.py`, `tests/`,
`scripts/` and the docs stay in the root. A checkout works because `pdfmd.py` puts `lib/` on `sys.path` itself; the wheel
and the zipapp get the packages from `[tool.setuptools.package-dir]` in `pyproject.toml` and `PACKAGES` in
`scripts/build_zipapp.py`. A new package goes into all three (`packages`, `package-dir`, `PACKAGES`);
`tests/test_packaging.py` fails until it does. A test that reads a shipped file builds the path as `ROOT / "lib" / "pdfmd_x" / ...`.

## Debugging

`pdfmd --version` prints the current version. `--verbose` prints pdfmd's
own auto-discovery decisions AND the exact Pandoc/Quarto command line about
to run, via `log_cmd()` — reach for this FIRST when a document's rendered
output doesn't match what the source and project files alone would
predict; it is very often pdfmd's own auto-applied defaults (a discovered
metadata file, an auto-included preamble, its own table-width filter)
doing something the project-specific files don't show at all.

## Vendored inkmd and the native tier

`lib/pdfmd_inkmd/` is a generated copy of the PyPI package `inkmd` (the built-in
PDF renderer used when there is no Pandoc or PDF engine). Never edit it by
hand: change `scripts/vendor_inkmd.py` and re-run it
(`python3 scripts/vendor_inkmd.py --version X.Y.Z`; `--check` reports drift),
then `PDFMD_GOLDEN=1 python3 -m unittest discover -s tests` and read what
changed in inkmd's output. The native tier's code is in `pdfmd.py` (the section
after `dependency_report()`: `normalise_gfm()`, the math-as-text converter,
`convert_native()`); md2pdf (`pymd2pdf`) is an optional dependency, not vendored.
`python3 -m unittest discover -s tests` runs everything; the end-to-end tests run
`pdfmd` with an empty PATH, which is how to test "no Pandoc" without removing it.

## This is a shared dependency

`pdfmd` is used across multiple, unrelated Markdown-to-PDF pipelines (the
`nulabreport` chemistry lab-report package at `~/dev/tex/nulabreport/` is
one real, current user, but not the only one). A change made to fix one
project's document can affect every other document `pdfmd` builds — the
v2.0.0 table-width fix had to be checked against BOTH the table that
motivated it (should now render at natural width) AND a deliberately-
overflowing synthetic table (should still get rescued, unchanged) before
being considered safe. Never assume a fix here is scoped to whichever
project you were looking at when you found the bug.

## Location

The real file is `~/dev/py/pdfmd/pdfmd.py`. `~/dev/python-projects/pdfmd.py`
is a symlink to it, kept because shell aliases and other projects' docs
invoke that path; don't remove it.

`pyproject.toml` makes it pip-installable (`pipx install
git+https://github.com/aliperdehan/pdfmd`; distribution name `pdfmd-cli`).
A pipx-installed `pdfmd` is a separate copy: edits here don't reach it until
`pipx install --force .` (or install with `pipx install -e .` to link it).
When testing an edit, run `python3 pdfmd.py` from this folder so you know
which copy ran.

## Releasing to PyPI

Automatic. Every push to `main` runs `.github/workflows/publish.yml`: the
Windows/macOS/Linux tests (`test.yml`) and then, only if they pass and
`PDFMD_VERSION` isn't on PyPI yet, a build, an upload to PyPI as
`pdfmd-cli`, and a `vX.Y.Z` tag. So releasing = the usual version bump +
changelog commit, pushed. A push without a version bump publishes nothing.
Don't rename `publish.yml` or the repo's `pypi` environment: PyPI's trusted
publisher is registered to exactly those names.

The same push builds the container images (`.github/workflows/docker.yml`, called from `publish.yml` after the upload): four
variants, two architectures, smoke-tested before they are pushed to `ghcr.io/aliperdehan/pdfmd`. A change to `docker/` is tested by
running `docker.yml` by hand with the push off (or locally with Docker: `docker/smoke.sh IMAGE`).

**After a release, pull before the next push.** The `homebrew` job of `publish.yml` commits the formula bump
(`Formula/pdfmd.rb`) to `main` as `github-actions[bot]`, and so does the `scoop` job, so GitHub's `main` is then one or two commits
ahead of the local one. Run
`git pull --ff-only` (`--rebase` when local commits exist) before every push, or the push is rejected. The bot touches only
that file (and the `scoop` job `bucket/pdfmd.json`), so there is never a conflict. The formula and the Scoop manifest live in this
repository; there is no separate tap or bucket repository.

## Decisions are recorded first

Every decision the author makes in chat (a choice between options, a wish, a design answer, a refusal) is written into the
maintainer's working notes (the master queue) at full context, in the same turn and before any code: the question, the
options, the answer, the reason, what it touches. It also gets a short line in `TODO.md` with the entry id, when the work is put off. Chat is lost at
the next compaction; a decision that exists only there gets re-asked, re-derived or never built. Code follows the record,
never the other way round, and a decision changed later is edited in the notes, not only in the code.

## No hardcoded thresholds

A number that changes behaviour (a ratio, a limit, a minimum length, a margin, a cap) is a setting: a `pdfmd-options` key,
a `--setup` row, per table where a table can carry it, its default written in the docs. A constant stays in the code only
when the author says so or the situation presses (a file-format fact, a speed limit, a case with no sensible knob), and then
the author is told in the same reply and the constant is recorded in the maintainer's notes with the reason.

## TODO.md

`TODO.md` lists the open work that is postponed, one line per item; work done in the same session as its decision gets no line
(the author, 2026-11-03: a line written for work in progress is stale within the hour). When a commit finishes an item, delete its line in
that same commit (the changelog is the record of what shipped); when a plan adds or changes an item,
edit the line. Keep it free of personal paths and names, like every file here.

Keep it lean: one short line per item, never a paragraph. Design, decisions, wishes and measured facts go in the
maintainer's working notes (the master queue), and the line carries only the bracketed entry id that points there. When a
line grows past one sentence or two, move the rest to the notes.

## Version numbers

One minor bump (`3.N.0`) per feature line, however large; every commit after it in that line that changes code, a feature,
a setting or behaviour is a patch (`3.N.x`, +0.0.1) with a changelog entry of its own, in the same commit as the change and
the `PDFMD_VERSION` bump. One commit, one version, one entry: never grouped by feature, never folded into the previous
entry, even while the minor is unreleased.

**The kits, tables and smiles lines are the exception.** They get no minor of their own: every commit of any of them is a 3.31.x patch
(the next free number) with its own changelog entry, tagged `[kits]`, `[tables]` or `[smiles]`, so the rules below apply to each of them
unchanged. (`[smiles]`, chemical structures, was approved by the author on 2026-10-31.)

**No bump for a commit that changes no shipped code.**
- A test, a workflow or a docs file (README, this file) that is the commit's whole change keeps a changelog entry under the
  previous version with a letter: `## v3.30.30b — date`, then `c`, and so on. `PDFMD_VERSION` stays as it is, so
  `publish.yml` releases nothing. The letter lives only in `CHANGELOG.md`: as a version it would be a PEP 440 pre-release
  (`3.30.30a0`), which sorts before 3.30.30. The tests that read the changelog match `## v<digits>.<digits>.<digits>`
  followed by a word boundary, so a lettered heading is skipped by them.
- A commit that changes only `TODO.md` has no changelog entry at all, only its commit message, and a TODO line is never
  listed in another commit's entry.

**Only a fix to a bug that the unreleased version itself introduced** (the version is not on PyPI) goes into that
version's entry with no new heading. A new feature or setting in a later commit does not: it is a patch of its own.
