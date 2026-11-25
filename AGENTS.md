# pdfmd: working on the code

For every agent that develops pdfmd. (`docs/agents.md`, shown by `pdfmd --doc agents`, is the other kind of guide: for
programs and assistants that USE pdfmd.)

pdfmd converts Markdown and other Pandoc-readable formats to PDF or another output format. The feature reference is
`docs/reference.md` (`pdfmd --doc reference`); this file is the process. The author decides design, behaviour and
releases. An agent that works under a task brief also follows the last section.

Before working in an area, read TODO.md, the decisions behind it, `docs/reference.md` and the area's tests. Search the
recorded decisions, the code and CHANGELOG.md before calling a feature missing. Undecided items (marked decide, discuss,
later, postponed, the author's call) are not built.

## The repository is public

No secrets, personal names, home paths or local-only details in any committed file, commit message, issue or PR; refer
to "the author". The exception is the author's name in LICENSE* and CITATION.cff. In commands write `~/...` (`$HOME` inside quotes, `Path.home()` in Python), never an absolute home
path, and redact home paths in output you show. In PRs and issues, put role names and placeholders in backticks rather
than a bare `@name`. British spelling, plain prose.

Scratch goes under `$TMPDIR` (or the session's scratch folder), never inside a checkout. Real configuration, caches,
data, Downloads and documents are read, never written: checks and tests get scratch config/cache/data folders through
pdfmd's settings and the `XDG_*` variables (TeX and Matplotlib caches too), and a subprocess environment is
`{**os.environ, ...}`, never built from scratch. Real documents are tried on scratch copies. Never delete with a
wildcard: list the targets, delete by explicit names. No app, browser or pager windows unless asked (`git --no-pager`).
macOS tools are BSD: in-place edits with Python or `sed -i ''`; GNU tools carry a `g` prefix; `shellcheck -x` every
shell script written.

## TODO.md

TODO.md lists postponed open work only: one short line per item with the bracketed id of its decision record; work done
in the session of its decision gets no line. A commit that finishes an item deletes its line; a plan that changes an item
edits it. Design, measurements and long explanations belong in the maintainer's notes, not in TODO.md. A TODO.md change
is shown to the author before it is committed. A TODO-only commit has no changelog entry, and no other entry lists a
TODO line.

## Changing code

`git status` is clean before an edit, so the last commit is the exact pre-edit state; no `.bak` copies. The change, its
CHANGELOG.md entry and the `PDFMD_VERSION` bump go into one commit; the entry starts "Pre-edit state: commit `<parent>`."
(the changelog's numbering starts at 2.0.0; the 1.x entries are a reconstruction and not reliable).

Every code change gets regression coverage in its area's test module, and the docs, `--help` and the guide change with
the behaviour (tests/test_docs_consistency.py checks drift). A feature is not done when its first example works: try the
natural variants (case, spacing, optional outer bars, valid and repaired input, every writer, lists and parts, the
setting off) and say which were tried and what is left uncovered.

A number that changes behaviour (a ratio, a limit, a minimum, a margin, a cap) is a setting: a `pdfmd-options` key, a
`--setup` row, per table where a table can carry it, its default documented. A constant stays only when the author says
so or the situation presses (a file-format fact, a speed limit, no sensible knob); the author is told and the reason is
recorded. Every new flag or `pdfmd-options` key goes into lib/pdfmd_setup/inventory.py in the same commit: a `--setup`
row in lib/pdfmd_setup/registry.py with its `UNSET` words, or an `Omitted` entry with the reason
(tests/test_setup.py `Completeness` fails until it is in one of them).

## Versions and attribution

One minor (`3.N.0`) opens a feature line, however large, and only when the author says so;
every commit after it in that line that changes code, a feature, a setting or behaviour is a patch (+0.0.1) with
its own entry and bump: one commit, one version, one entry, never grouped, never folded into an earlier entry, even
before a release. Kits, tables and smiles get no minor of their own: each commit is the current line's next patch,
its entry tagged `[kits]`, `[tables]` or `[smiles]`. Only a fix to a bug that the unreleased version itself
introduced goes into that version's entry.

A commit that changes no shipped code (tests, a workflow, docs) keeps `PDFMD_VERSION` and gets a lettered heading under
the current version: `## v3.33.285a — date`, then `b`, `c`. The letter lives only in CHANGELOG.md (as a version it would
be a PEP 440 pre-release); the tests that read the changelog skip lettered headings.

Commits use the repository's identity, never `--author` or a `git config` change. The last line names the model that
wrote the change: `Co-authored-by: <Agent> (<Model>) <address>`. From 3.34.0, a commit written by one agent and reviewed
and landed by another carries the writer's trailer and then `Reviewed-by: <Agent> <Model> <address>` for the reviewer;
commits before 3.34.0 stay as they are.

## Layout and the core

The `pdfmd_*` packages live in lib/; pdfmd.py, tests/, scripts/ and the docs stay in the root. A checkout works because
pdfmd.py puts lib/ on `sys.path`; the wheel and the zipapp carry the packages. A new package goes into pyproject.toml
(`packages`, `package-dir`) and `PACKAGES` in scripts/build_zipapp.py (tests/test_packaging.py checks). A test that reads
a shipped file builds its path as `ROOT / "lib" / "pdfmd_x" / ...`.

pdfmd.py is a launchpad (783 lines at 3.33.285): imports, the loading and binding machinery, the state that must stay a
module global, worker-state transfer, `main()` and the Python API. The split that made it so is done; SPLIT.md is its
record and keeps the method (callers first, hubs last, moves separate from fixes; `scripts/split_spec.py`,
`split_move.py`, `split_check.py`). New code goes into the package of its feature, even when the caller still sits in
pdfmd.py; a fix to code in pdfmd.py may stay in place. `wc -l pdfmd.py` before and after is part of every review, and a
commit that makes it longer says why in its entry.

A package that needs pdfmd's state uses `from pdfmd_base import core` and reads, writes or deletes `core.NAME` when it
runs; pdfmd.py binds that proxy to itself (`pdfmd_base.bind()`). A package never imports pdfmd: run as a script it is
`__main__`, and a second import is a second copy with its own state. Names that live in packages are served through the
names table (`names("pdfmd_x.role", "a b c")`, `pdfmd_base.names_into()`): pdfmd.py's `__getattr__` loads the package
on first read. A name is either a module global or a table entry, never both, never registered twice; tests patch the
pdfmd name, so calls to patchable names go through `core` even inside a package. `deferred()` remains for the nine
stand-ins whose pdfmd name differs from the package's (SPLIT.md lists them).

Load only what the run needs: a package is imported at start only when every run uses it; heavy standard-library modules
(`urllib.request`, `ssl`, `http.server`, `tarfile` ...) are imported inside the package that uses them. Check a change
with `python3 -c "import sys; sys.argv=['pdfmd','--version']; sys.path.insert(0,'.'); import pdfmd; print(sorted(sys.modules))"`
(182 modules at 3.33.285) and a timed `python3 scripts/pdfmd --version`. A move or refactor is proved by
`scripts/split_check.py` (SAME, with `--extra` builds that reach the changed code through its real call site).

## Verifying

Run the checkout (`python3 pdfmd.py` or `python3 scripts/pdfmd`); an installed pdfmd is a separate copy, and
`pdfmd --version` says which ran. scripts/pdfmd imports pdfmd.py so Python caches its bytecode (tests/test_launcher.py
covers it, with the `__main__` guard that `-b -j` workers need). External launchers and symlinks that point at the
checkout are not repository work: leave them alone.

When a document's output does not match what its source predicts, reach for `--verbose` first: it prints pdfmd's own
discovery decisions and the exact Pandoc/Quarto command (`log_cmd()`); discovered metadata, preambles and pdfmd's own
filters are often the cause. A fix that touches how pdfmd builds its Pandoc command is verified through pdfmd itself,
not through the Pandoc or LaTeX command it makes: the v2.0.0 table-width bug looked fixed in the generated `.tex` and
was not.

pdfmd is a shared dependency of unrelated pipelines: a fix for one document can break another. Check the case that
motivated it and a deliberately hostile one (the table-width fix: the natural-width table and an overflowing one).

Tests: the touched modules, plus test_setup and test_docs_consistency for a setting or help text and test_packaging for a
new package. The full suite before a push or a release, or when asked, not for every edit:
`python3 scripts/test_parallel.py [-j N] [--failed-only] [PATTERN ...]` runs modules in parallel, each with scratch
config, cache, data and temp folders (`--own-tex-cache` isolates TEXMFVAR); serially
(`python3 -m unittest discover -s tests`) it takes an hour or more. A test that fails only under load is a race in the
test or a bug: find out which before changing either. The end-to-end tests run pdfmd with an empty PATH, which is how
"no Pandoc" is tested. Long jobs run in the background with their output and exit status in a scratch log.

## Generated code and the native tier

lib/pdfmd_inkmd/ is a generated copy of the PyPI package inkmd (the built-in renderer used without Pandoc or a PDF
engine). Never edit it by hand: change scripts/vendor_inkmd.py and regenerate (`--version X.Y.Z`; `--check` reports
drift), then run `PDFMD_GOLDEN=1 python3 -m unittest discover -s tests` and read what changed in the output. The native
tier's rendering (`normalise_gfm()`, math as text, `convert_native()`, `math_lines()`, paper tables) is in
lib/pdfmd_native/; its selection (`native_possible()`, `NATIVE_ENGINES`, `native_run_note()`) and the lost-features
prompt in lib/pdfmd_engines/native.py; `NATIVE_LOST` is state in pdfmd.py. md2pdf (`pymd2pdf`) is optional, not vendored.

lib/pdfmd_yaml/ is a generated pure-Python copy of PyYAML with its MIT licence; it never shadows an installed `yaml`.
Never edit it by hand: change scripts/vendor_pyyaml.py and regenerate against the installed PyYAML (`--version X.Y.Z`;
`--check` reports drift). C extensions are omitted.

## Colophon and the web UI

Read gui/README.md and lib/pdfmd_web/README.md before changing either. gui/ is the Swift app, lib/pdfmd_web/ its web UI,
lib/pdfmd_serve/ the JSON core; pdfmd's logic stays in pdfmd, never in the GUI.

The syntax table (lib/pdfmd_web/syntax/syntaxes.json and cases.json) is shared by Python's reference test, JavaScript's
engine.js (node and the page) and Swift's Highlighter: use their common regex subset (no `\w`, `\d`, `\s`, `\b`, no
flags, named groups or cross-line matches; fixed-width lookbehind only). After an edit: `python3
lib/pdfmd_web/tools/sync_syntax_fixture.py`, test_syntax_table, the page selftest, and `gui/build.sh` with
`pdfmdedit --smoke-syntax`. gui/build.sh builds without launching; the headless `pdfmdedit --smoke-*` checks open no
window. `--install`, launching the app, `--pdf-live` and `--live-studio` only when the author asks. What was not checked
by hand on screen (windows, save panels, visual behaviour) is reported as "not verified by hand".

## Releases

A push to `main` is a release: .github/workflows/publish.yml runs the Windows/macOS/Linux tests and then, only if they
pass and `PDFMD_VERSION` is not on PyPI yet, builds, uploads `pdfmd-cli` and tags `vX.Y.Z`; without a version bump it
publishes nothing. The same run builds the container images (docker.yml: four variants, two architectures,
smoke-tested; a change to docker/ is tried with the push off or with `docker/smoke.sh IMAGE`). Do not rename
publish.yml or the `pypi` environment: PyPI's trusted publisher is registered to them. The release jobs commit
Formula/pdfmd.rb and bucket/pdfmd.json back to `main` as a bot, so GitHub's `main` is then ahead: pull
(`--ff-only`, or `--rebase` with local commits) before the next push. `main` is pushed only on the author's go.

## Reporting

Report what happened, plainly: which tests ran and how many failed (quote the failure), what was skipped and why, what
was not verified. Never call something passing that was not run.

## Working under a task brief

This section is for an agent that was given a task brief (a delegated batch). The brief is the mandate: its items and
nothing else, and where it is stricter than this file, it wins. The orchestrating agent reviews and lands the work.

- Work only in the worktree and the scratch folder the brief names; never in another checkout or worktree.
- Commit only on your branch, one commit per item with the version and trailer the brief gives. No push, tag, merge,
  rebase, amend, reset, stash or branch switch.
- A choice that the brief, the recorded decisions and this file do not settle: stop that item, leave nothing of it in
  the tree, and report the options with a recommendation; go on with the items that do not depend on it.
- Expect a sandbox: what cannot run there (sockets, the real caches, GUI apps, the network) is listed in the report, not
  worked around.
- Keep a log in your scratch folder and end with a short report a reviewer with a small context can read: per item the
  hash, the version, one sentence, the tests (failing before, passing after), and anything skipped, with its options.
