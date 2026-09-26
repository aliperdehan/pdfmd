# pdfmd

Converts Markdown (and other Pandoc-readable formats) to PDF or another
output format via Pandoc. Started as a one-line `pandoc file.md -o
file.pdf` wrapper; has since grown auto-discovery for metadata files,
LaTeX preambles, Lua filters, and fonts, a multi-engine PDF fallback chain,
a `pdfmd-options:` front-matter block, batch/report/book modes, and its
own generic table-width-balancing Lua filter (`TABLE_WIDTH_LUA_FILTER`) —
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
and why its numbering starts at 2.0.0 rather than reconstructing a 1.x
history.

**Verify before declaring a fix done — a synthetic test is not enough.**
The table-width bug fixed in v2.0.0 is the concrete example: compiling the
generated `.tex` directly with `lualatex` looked correct, and only running
the FULL `pdfmd` pipeline on the same source revealed the bug (`pdfmd`
inserts its own extra `--lua-filter` ahead of anything project-specific).
If a fix touches how `pdfmd` builds its Pandoc command, test through
`pdfmd` itself, not just through the Pandoc/LaTeX commands it constructs
internally.

## Debugging

`pdfmd --version` prints the current version. `--verbose` prints pdfmd's
own auto-discovery decisions AND the exact Pandoc/Quarto command line about
to run, via `log_cmd()` — reach for this FIRST when a document's rendered
output doesn't match what the source and project files alone would
predict; it is very often pdfmd's own auto-applied defaults (a discovered
metadata file, an auto-included preamble, its own table-width filter)
doing something the project-specific files don't show at all.

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
