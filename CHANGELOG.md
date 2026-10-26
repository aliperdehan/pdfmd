# Changelog — pdfmd.py

Newest first. Versions follow semver loosely: a **major** bump changes
behavior in a way that could surprise an existing user (a default flips, a
flag's meaning changes). One **minor** bump (`3.N.0`) opens a feature line,
however large it is; every change after it in that line is a **patch**
(`3.N.x`), whatever it adds, so the version count stays small.

The version string lives in one place, the `PDFMD_VERSION` line of `pdfmd.py`
(a little below its module docstring; `pyproject.toml` and the publish workflow
read it from there):

```python
PDFMD_VERSION = "2.0.0"
```

`pdfmd --version` prints it. Bump it there and add an entry here in the
same commit as the change.

**Why this starts at 2.0.0, not 1.0.0.** `pdfmd.py` began as a one-line
`pandoc file.md -o file.pdf` wrapper and was revised many times since — across
ChatGPT, ChatGPT Codex, Claude Chat, Cowork, and Claude Code sessions — with no
version marker or changelog kept at any point. `backups/pdfmd.py.bak-*` has
snapshots from a handful of points in that history, but not from the
ChatGPT/Codex/Cowork era at all, so reconstructing an honest "v1.x" changelog
from what's actually on disk isn't possible — only a partial,
misleadingly-precise-looking one. Decided 2026-09-16 (the author): start real
changelog tracking now, at 2.0.0, rather than fabricate the gap. If the full
history ever matters, it would need pulling the actual chat transcripts from
each of those tools, not guessing from diffs between inconsistent backup
snapshots.

**Update, 2026-10-05:** an approximate outline of the earlier history has since
been reconstructed, at the very end of this file (see "Before 2.0.0 —
reconstructed history"), from the saved Codex transcripts and the surviving
backup snapshots. It is explicitly NOT reliable: its 1.x numbers are invented,
snapshot-based entries cover windows of days rather than single changes, and
anything done in unsaved sessions (other ChatGPT chats, claude.ai, Cowork) is
missing. Real tracking still begins at 2.0.0.

---

## v3.30.42b — 2026-10-26

Pre-edit state: commit `4efe2c5`. Documentation only (the README and the notes in `pdfmd.py` and `--setup`): `PDFMD_VERSION` stays 3.30.42.

### Fixed
- The notes on pipe-table column widths claimed more than the code does. Unequal separator dashes are kept only under Pandoc's own Markdown reader (a document with front matter or a linked metadata file); under `gfm` they carry no width and every table is balanced. Colons count as dashes. The balancing runs for the LaTeX engines only; the other writers take Pandoc's widths, equal columns for `---|---` with a long line under the Markdown reader. The behaviour itself is unchanged and queued.

## v3.30.42 — 2026-10-26

Pre-edit state: commit `0ae751a` (v3.30.41).

### Fixed
- **`--paper a4,landscape` (and `papersize: a4,landscape`) turned no page but the built-in renderers'.** Pandoc's `papersize` is a
  LaTeX class option: on the LaTeX engines it printed `[a4,landscapepaper]`, LaTeX said "Unused global option" and the page was
  Letter, silently; Calibre and the browsers lost the orientation too (the Word-file reader did not split the list item); WeasyPrint
  ignored the paper altogether (A4 whatever `papersize:` said); Typst stopped on `a4,landscape`, and on a plain `--paper letter`
  (pdfmd's translation to `us-letter` came as a second `-V papersize=`, and Pandoc joined the two into `letterus-letter`). One
  function, `paper_variables`, now settles the paper for each engine: LaTeX gets the size as a class option and the turn as
  `geometry:landscape`; Typst gets its own name (`us-letter`, `iso-b5`) once and `#set page(flipped: true)` through `typst.lua`;
  WeasyPrint gets `@page { size: ... }` through `weasyprint.lua`; Calibre and the browsers read the list item. The same page comes
  from `geometry: landscape` and `classoption: landscape`, and from the `pagesize:` typo, which now also beats a `papersize:` of the
  settings in the Calibre, browser and Word readers (as it did for LaTeX).
- Spellings that printed a Letter page on LaTeX: `a4paper` (became `a4paperpaper`), `A4`, `us-letter`, and `a3` (no class option;
  `geometry:a3paper` now). `--paper landscape` alone keeps the size the settings name.
- `--no-auto papersize` leaves all of this to Pandoc. Measured on Pandoc 3.12 with LuaLaTeX, Typst, WeasyPrint, Calibre and
  the built-in renderer, for `a4,landscape`, `letter,landscape`, `a4`, `letter`, `a4paper`, `a3`, `us-letter,portrait`, `landscape`
  and front matter `papersize`, `pagesize`, `geometry`, `classoption`.

## v3.30.41 — 2026-10-26

Pre-edit state: commit `c2732a2` (v3.30.40).

### Added
- **`mdpdf` answers the npm `mdpdf` too.** `--style FILE` and `MDPDF_STYLES` (a style sheet; `-e html` is added unless an engine is
  named), `--format` (paper), `--orientation landscape` (`-V geometry:landscape`: the LaTeX route; `papersize: a4,landscape` is read
  by the built-in renderers only), `--border` and `--border-top|-left|-bottom|-right` (margins as `geometry:` variables; px count as
  0.75 pt). `--header`/`--footer` are told apart by the value: an `.html`, `.htm` or `.hbs` file, or any file that exists, is the npm
  one's Puppeteer markup and is dropped; a template `"left,middle,right"` stays the PyPI one's. Dropped with a note on standard
  error, never silently: those headers and footers, `--h-height`, `--f-height`, `--no-emoji`, `--gh-style`, `--debug`.
- **`--doctor` names a command of pdfmd's that another program answers.** `pdfmd`, `mdpdf`, `md2pdf`, `inkmd` and the others are
  shared by several tools, and the one installed last owns each name; a "Command names" section says which names on the PATH are not
  pdfmd's and how to take them back (`pip install --force-reinstall --no-deps pdfmd-cli`). It reads the installed package's own list
  of scripts, so it says nothing from a checkout, and nothing when every name is pdfmd's. Checked in a scratch virtualenv with a
  different `md2pdf` ahead on the PATH.

## v3.30.40 — 2026-10-26

Pre-edit state: commit `e606b1b` (v3.30.39).

### Added
- **An `md2pdf` command.** Several tools install that name; pdfmd now answers the keys of all three: jmaupetit's `md2pdf`
  (`-i -o -c -W`), `md-to-pdf` (`--stylesheet`, `--as-html`, `-w`, `--document-title`) and kxxoling's (`--theme file.css`). A style
  sheet adds `-e html` unless an engine is named (only HTML engines read CSS). `-e` is an engine when its value is one and
  jmaupetit's Markdown extension otherwise. What pdfmd has no counterpart for (extensions, `-C`, `--pdf-options`, `--config-file`,
  `--launch-options`, a string given to `--css`, a built-in `--theme`) is named on standard error and left out.

## v3.30.39 — 2026-10-26

Pre-edit state: commit `e069268` (v3.30.38).

### Added
- **`mdpdf in.md out.pdf`: the output as a second positional.** The Go `mdpdf` and `md2static` name the PDF that way; the
  `mdpdf` command now takes a last positional ending in `.pdf` that follows another positional as `-o`, whether or not options
  come after it (`mdpdf notes.md notes.pdf -p A4`). It is left alone when `-o` is given, when it is the value of an option
  (`--cover c.pdf`), when it is the only argument, and when the one before it is a PDF too. The original `mdpdf` never reads a PDF,
  so nothing it accepted changes. `pdfmd` itself does not do this: for pdfmd a PDF argument is an input.
- **`pdfmd x.pdf -o -`: the Markdown on standard output.** M1ck4's `pdfmd` (archived 2026-05-08) pipes that way; for PDF inputs it
  now means batchocr's `--stdout` (it was the terminal view, which refuses a PDF). `pdfmd x.pdf --stdout` worked already. The setting reaches `-j` workers (`tests/test_jobs.py` caught the first version, which did not).

## v3.30.38 — 2026-10-26

Pre-edit state: commit `d4ae514` (v3.30.37).

### Fixed
- **A `.csv` block's caption with several attribute words was printed as text.** `Table: Raw data {#tbl:raw keep=9}` (or the `: Raw data {...}` form) after a `::: {.csv}` block gave the table no id and no attributes and left `{#tbl:raw keep=9}` in the caption: only a block of one word (`{#tbl:raw}`, `{.keep}`) was read. The block may hold several words now, every one an `#id`, a `.class` or a `key=value`, and a `key=value` block (`{keep=9}`) counts. A brace in the caption's prose (`Set {x} and {y}`) is still prose.

### Added
- **`keep` on a `.csv` div reaches the table.** `::: {.csv file="x.csv" keep=4}`, `::: {.csv .keep}` and `.nokeep` put `keep=4`, `keep` or `nokeep` on the table's own attributes, where a filter that keeps a short table on one page (nulabreport.lua) looks for them; the caption's own attributes win. `tests/test_csv_table.py`.

## v3.30.37 — 2026-10-26

Pre-edit state: commit `276f947` (v3.30.36).

### Added
- **`--no-rewrite`: keep the old output.** A build replaces an older `report.pdf`; with `--no-rewrite` it writes `report (1).pdf` (the first free number) and leaves the old file alone. `--rewrite` turns it back on for one run. Also `pdfmd-options: {rewrite: false}` (a document, a folder's `.pdfmd`, the config) and a `--setup` row ("Replace an older output of the same name", in the folder screen too). The name is a template, `rewrite-name` (`--setup`: "The name of the numbered copy"), default `{stem} ({n}){ext}`, with `{n}`, `{stem}`, `{ext}` and `{date}`; one without `{n}` or with a folder in it is refused with a warning. It applies to the final output of every build: the `-o` name, each file of a `-b` batch and of a parts build on its own, `pdfmd -` (`stdin (1).pdf`), `--to` formats; the cache stage's `.tex`, the `--view` scratch files and the builds pdfmd runs on itself (`--edit`'s rebuild, the labels pass, the Python API) are never numbered. A watch (`-w`) always rewrites. The first build of a name has no number. `tests/test_rewrite.py`.

## v3.30.36 — 2026-10-26

Pre-edit state: commit `bdc81b1` (v3.30.35).

### Added
- **The indent div works in Word and OpenDocument.** `::: {indent=false}` (and `noindent`, `indent=2em`, ...) printed a NOTE and changed nothing in a `.docx` or `.odt`, so a Word file did not match the PDF. `pdfmd_lua/indent.lua` now gives the plain paragraphs of the div a paragraph style named for the length, `pdfmd-indent-0pt`, `pdfmd-indent-2em` (Pandoc applies a custom-style div to the paragraphs directly inside it and leaves lists, quotes, code and tables in their own styles); `pdfmd_office` writes the first-line indent into the style afterwards (`w:ind w:firstLine` in a Word file, `fo:text-indent` in an OpenDocument file, where Pandoc only names the style and does not define it). An em is 12 pt there. The paragraphs after the div are the document's own again. A length in `%` or `rem` is still left out with the NOTE. Checked in LibreOffice: the div's first line starts at the margin (72 pt), `2em` at 96 pt, the body text after it at its own indent. `tests/test_indent_office.py`.

## v3.30.35 — 2026-10-26

Pre-edit state: commit `bbb6a47` (v3.30.34).

### Added
- **A LuaTeX that cannot start names why.** An unwritable TeX cache and a corrupt luaotfload database both reached pdfmd only as Pandoc's `lualatex failed (!  ==> Fatal error occurred, no output PDF file produced!)`: the cause is in the engine's own console, and the two looked alike although the fixes differ. When lualatex fails with that line and the text names no known cause, pdfmd runs a one-line page with the same engine in the same environment (once per run, 120 s at most) and classifies what it prints: `cause: the TeX cache folder is not writable; set TEXMFVAR and TEXMFCACHE to a folder you can write to`, or `the LuaTeX font database is corrupt; run luaotfload-tool --update --force, or delete the luatex-cache folders`. `--doctor --deep` shows the same cause after the reason an engine failed. The signature `no writeable cache path` is matched across a wrapped console line (macOS prints `quiting`, Linux `quitting`). Checked with a read-only `TEXMFVAR`/`TEXMFCACHE` on macOS. `tests/test_tex_cause.py`.

## v3.30.34 — 2026-10-26

Pre-edit state: commit `210497a` (v3.30.33).

### Added
- **`pdfmd -` builds the Markdown on standard input.** `echo '# Hi' | pdfmd -` writes `stdin.pdf` (`stdin.html`, `stdin.docx` ... with `--to`) in the current folder, or the file `-o` names. Before, `-` was "Could not find Markdown file for '-'", and only `--view` and `-o -` read a pipe. The text is kept in a hidden file in the current folder for the length of the run (a relative picture or include resolves there; it is removed on success, failure and ^C), and the OK line names it `stdin.md`. Standard input that is empty is refused with a reason. A plain `pdfmd` with a pipe is unchanged (it builds the folder's Markdown): the `-` is what says that the pipe is the document, so no script that runs `pdfmd` with an inherited stdin changes meaning. `tests/test_stdin.py`.

## v3.30.33 — 2026-10-26

Pre-edit state: commit `5fe0411` (v3.30.32b).

### Fixed
- `--doctor --deep` builds a page with a struck-out word. A LaTeX installation without `soul.sty` (xelatex, pdflatex) or `lua-ul` (lualatex) passed the check and then failed on the first document with `~~text~~`.

## v3.30.32b — 2026-10-26

Pre-edit state: commit `3b97509` (v3.30.32). A docs-only commit: `PDFMD_VERSION` stays 3.30.32.

### Added
- `TODO.md`: the open work, one line per item, grouped as next / decide first / agreed features / before 4.0 / investigate first / other repositories. `CLAUDE.md` says to delete an item in the commit that finishes it.

### Fixed
- `tests/test_doc.py` accepts a lettered newest changelog heading (`v3.30.32b`); it compared the heading with `PDFMD_VERSION` exactly, so the first docs-only commit under the 3.30.30 rule would have failed it.

## v3.30.32 — 2026-10-26

Pre-edit state: commit `0f6d680` (v3.30.31). Issue 15.

### Fixed

- A TeX Live or MiKTeX that is installed but not on `PATH` was reported as "no TeX engine installed": on Windows `--doctor` listed only Typst, the default run fell back to Typst without a word (a document with `\ce` or `\SI` built without LaTeX) and `-e tex` stopped with an error. When no TeX engine is on `PATH`, pdfmd now looks in the usual places (TeX Live: `C:\texlive\<year>\bin\*`, `%ProgramFiles%\texlive`, `~/texlive`, `/usr/local/texlive/<year>/bin/*`, `/Library/TeX/texbin`; MiKTeX: `%LOCALAPPDATA%\Programs\MiKTeX`, `%ProgramFiles%\MiKTeX*`), newest year first, and puts the folder it found behind `PATH` for its own runs. `PDFMD_TEX_BIN` names a folder for an install in an unusual place. `--doctor` prints `NOTE  TeX found at ..., which is not on PATH`. Nothing changes when a TeX engine is on `PATH`.
- The message of `-e tex` with nothing found now says the engines are not installed "on PATH".
- `-e lualatex.exe` (and `-e typst.exe,lualatex.EXE`): a trailing `.exe` is dropped from an engine word, so the name Windows shows for the engine works. A word with a path in it is left as written.

### Tests

- `tests/test_tex_bin.py`. `tests.test_calc.PartBuiltAlone` shows Pandoc's own error when its first run fails (it hid it behind `check=True`).
- Windows with MiKTeX (the non-gating `windows-latex` job, found by a short debug run): the job puts poppler's folder in front of Git Bash's, whose `pdftotext` is xpdf's (no `-bbox`, Latin-1 output); the poppler calls in the tests decode UTF-8 with `errors="replace"`; `test_calc` writes Pandoc's discarded output to a file (Pandoc cannot open `nul`); `test_check` compares paths with `/`; `test_embedding` passes `-e lualatex`, not `lualatex.EXE` (which pdfmd now also accepts). Test code and CI only.

## v3.30.31 — 2026-10-26

Pre-edit state: commit `16fad47` (v3.30.30 + the CLAUDE.md rule).

### Added

- A failed TeX run names its cause when the log has a known signature: a second line under the `WARN ... failed` line, `cause: the LaTeX package soul.sty is missing; install it (tlmgr install soul; Debian/Ubuntu: apt install texlive-plain-generic)`. Known: a missing `.sty` (the package that has it for lmodern, soul, selnolig, lua-ul, luacolor; `tlmgr install NAME` for any other), a missing luaotfload, a corrupt luaotfload font database, an unwritable TeX cache. The signatures come from real logs of an outside reviewer's six cases (2026-10-14). Once per document, not once per engine tried.
- Not done: the unwritable cache and the corrupt database reach pdfmd as Pandoc's bare `Fatal error occurred, no output PDF file produced!`, the cause is only in the engine's own console output, so those two are named only when the log text is at hand (not through Pandoc). Naming them needs a probe run (a one-page `lualatex` smoke document after such a failure, as `--doctor --deep` already has); queued.

### Tests

- `tests/test_tex_cause.py`.
- `.gitignore` lists `pdfmd-reviews/` (an outside reviewer's raw logs, kept in the working folder for the classifier; not part of the package: `MANIFEST.in` names the files it ships).
- Windows `native` CI (first run of the combined tree): `test_doc` reads `--help` output with `errors="replace"`, `test_install_calibre.Detach` and `test_sections.PartRanges` compare paths the way the platform spells them (`Path(...)`, `as_posix()`). Test code only.

## v3.30.30 — 2026-10-26

Pre-edit state: commit `69dc4a6` (v3.30.29). Issue 13.

### Fixed

- The PDF made by `-e calibre` lost its bookmarks with Calibre 9.16 (`tests.test_calibre.Builds.test_a_document` failed on every machine with it since 2026-10-14). The bookmarks were there in what `ebook-convert` wrote: pdfmd's own stamp of the finished PDF (`PdfmdVersions`, `Creator`) copied it with pypdf's `append()`, which drops the whole outline of a PDF whose bookmarks are typed `/Type /Outlines`, as Calibre 9.16 writes them. The stamp clones the document instead.
- Every `subprocess` call of pdfmd that reads text names its encoding (`utf-8`, undecodable bytes replaced): `text=True` alone decodes with the ANSI code page on Windows, and Pandoc, TeX, `fc-list` and `kpsewhich` write UTF-8, so a byte the page could not decode made the reader thread die and `.stdout` come back as `None` (issue 13: every build stopped in `installed_font_families()` with TeX Live's `fc-list` on the PATH; that call itself was repaired by `ec8cbfe`, unreleased until now). 46 calls in `pdfmd.py` and five helper modules.

### Tests

- `tests.test_partial_provenance.OutlineSurvives`, `tests.test_probes.SubprocessDecoding` (no `run`/`Popen`/`check_output` call with `text=` and no `encoding=`).
- `tests.test_chem.WhatItCannotConvert` (v3.30.25) runs pdfmd on a Typst route that needs Pandoc, so it is skipped without Pandoc, like its neighbours; the first CI run of the combined tree failed the `native` jobs on it.

## v3.30.29 — 2026-10-26

Pre-edit state: commit `470de88` (v3.30.28). Merged from PR 9 (`cloud/calc-checks`), squashed.

### Added

- `--check` reports the calculator's undefined names (`calc-undefined`, an error): a span, a `::: calc` line or an `{ans}` that uses a name nothing defines, with its line and its part, in document order. A document without a calculator never starts Pandoc for it.
- `--check` notes a name defined more than once (`calc-redefined`, severity `note`, a third severity that is counted and never fails `--check`, not even with `--strict`). A normal build says nothing about it.
- `calc: {export: FILE}`, `--calc-export FILE`, `PDFMD_CALC_EXPORT` (for `-j` workers): after a build, `name,value,digits` with one row per name, sorted, `%.17g`, written atomically, readable back as a `constants` file. Not written without names, with `calc` off, after a failed build, or for a part built alone without the seed. `--attach-source` and `--embed-metadata files` leave it out unless it is also read. A `--setup` row (`options.calc.export`), the inventory entry, the help topic, README and recipes.

## v3.30.28 — 2026-10-26

Pre-edit state: commit `b065576` (v3.30.27). Merged from PR 11 (`cloud/partial-provenance`), squashed; it met 3.30.23's partial history in `pdfmd.py`, resolved by keeping both.

### Fixed

- A partial parts build (`report#intro`, `@60`) keeps the provenance of its PDF (Creator suffix, `PdfmdVersions`, `PdfmdBuildDate`, and a new `PdfmdPartial` naming the parts) and never stamps the `.md`. Word and OpenDocument files never carried these properties. With `stamp: {partial: true}` the "partial" entry of the history (3.30.23) is still written, after the PDF's provenance, by one function (`stamp_build`) that replaces `stamp_unless_partial`; the cache route's intermediate `.tex` stage writes neither.
- The snapshots of one build are one `BACKUP` line (`report.md + 6 parts -> .backups/, parts/.backups/ (...)`); the per-file lines follow only with `--verbose`.

### Tests

- `tests.test_partial_provenance`, `tests.test_backup_summary`.

## v3.30.27 — 2026-10-26

Pre-edit state: commit `b575748` (v3.30.26). Merged from PR 10 (`cloud/csv-notes`), squashed.

### Fixed

- The note under a cut `.csv` table states the fact only, only for the dimension that was cut (it said "2 of 2 columns" when no column was cut), without code spans. The advice moved to a once-per-table `WARN` on stderr.
- `--extract-inline-csv`, `--expand-tables` and `--check` know the bare `::: csv`.
- The stray `unittest.main()` in the middle of `tests/test_csv_table.py` is at the end.

### Added

- `note=short|off|full` (default `short`): a div's `note=`, `csv: {note}`, `--csv-note`, `PDFMD_CSV_NOTE`, a `--setup` row, the inventory entry, the help topic, README and recipes; in the Lua filter and in the built-in renderer. `full` is the only mode that keeps code spans (other writers get them as Pandoc writes them).

## v3.30.26 — 2026-10-26

Pre-edit state: commit `9b054bb` (v3.30.25). Merged from PR 8 (`cloud/portability`), squashed.

### Fixed (Windows)

- `report#section/sub` kept its slash on Windows (`Path()` turned it into a backslash, so the section was never found).
- A pager or editor typed with a Windows path (`C:\Program Files\...`) keeps its backslashes (`shlex` in POSIX mode ate them): `split_command()`.
- The calculator's seed run wrote Pandoc's output to the null device; Pandoc's binary writers cannot open `NUL` on Windows. It writes to a file in the scratch folder.
- A file with a kept source (`--keep-source`) whose line ends had become CRLF (git's `autocrlf`, an editor) "kept no pdfmd source", `--restore` could not give it back, and it was reported as edited. The trailer is read as LF text and the hash ignores the difference.
- The ASCII filter's helper (`--to ascii`) never started on Windows: its command and paths went through Pandoc's metadata with their backslashes. The paths have forward slashes, and the `WARN` says why the helper did not answer.
- TeX engines were started with a temporary folder under its Windows short name (`C:\Users\RUNNER~1\...`); the engine reads its command line as TeX, where `~` is active, and MiKTeX's LuaLaTeX opened no file. The label draft pass, the pictures drawn for Word files and the cache build failed there. `tex_argument()` gives the long name.
- A picture's folder was never taken out of a Word description on Windows.
- `--verbose` says how the label draft pass ended when it left no `.aux`; `provide_writable_places` creates the temporary `texmf-var`/`texmf-config` folders it points at.
- A busy disk image (macOS, `Calibre` install) is detached again before it is forced: four tries a second apart, then `-force`.

### Added

- The built-in parser (no Pandoc) draws an HTML `<table>`'s `colspan` and `rowspan` (`pdfmd_ansi/native.py`). Golden tests.

### Changed (CI, tests)

- The lint job runs `ruff check --select F` on the code and the tests (two unused locals, seven unused imports, a duplicated dictionary key; no behaviour changes). The Windows job (`windows-latex`) installs poppler, the fonts the tests name, and runs with Python's UTF-8 mode.
- The tests: the OS separator in what a run prints, Lua paths in forward slashes, `TEXINPUTS` with `os.pathsep`, a file to discard instead of `NUL`, line ends as Pandoc wrote them, a closed `.docx` before the folder is removed. Two `test_readonly_home.Builds` tests are skipped on Windows (MiKTeX's LuaLaTeX stops in luaotfload when LOCALAPPDATA is redirected).

## v3.30.25 — 2026-10-26

Pre-edit state: commit `abb652a` (v3.30.24). Issue 12.

### Fixed

- siunitx 2 style `\SI{1.8e-5}{}` and `\qty{1.8e-5}{}` (an empty unit) print the number alone, as `\num{1.8e-5}` does; `\si{}` and `\unit{}`
  print nothing; the same for `\SIlist`, `\SIrange` and their `qty` names. The empty unit made the converter refuse the command, so in
  a Typst, HTML or text output the command was left out of the text without a word, and a formula holding one (even beside a `\ce`) stayed raw
  TeX, with a warning that only blamed the missing `pdftocairo`.
- A command or a formula the converter refuses is named in one `WARN` with the reason (`[pdfmd] WARN \SI{3}{\bogus} cannot be converted
  (siunitx unit \bogus is not known); it is left out`), once per command, for the outputs the LaTeX filter does not run for.

### Tests

- `tests.test_chem.Siunitx.test_an_empty_unit_prints_the_number_alone`, `tests.test_chem.WhatItCannotConvert`.

## v3.30.24 — 2026-10-25

Pre-edit state: commit `de9c29a` (v3.30.23).

### Added

- `history:` is accepted in `pdfmd-options` (a document, a metadata file, the config) as another name for `stamp:`: the build history is that
  one setting (`enabled`, `store`, `mode`, `scope`, `packages`, `partial`, ...), not a second one. `history: {store: file, partial: true}` is
  `stamp: {store: file, partial: true}`; a field both set is taken from `stamp`. Older pdfmd versions do not know `history:`, so a shared
  metadata file that must work with them keeps `stamp:`.

### Tests

- `tests.test_partial_history.HistoryAlias`.

## v3.30.23 — 2026-10-25

Pre-edit state: commit `4e38e85` (v3.30.22).

### Added

- **Draft builds in the history.** The `.hst` held full builds only: a build of some parts or sections (`pdfmd @60`, `doc#section`) writes no
  BUILD NOTES line, and nothing took its place. With `pdfmd-options: {stamp: {partial: true}}` (or `--stamp-partial`; `--no-stamp-partial`
  overrides a document that set it; a `--setup` row, `options.stamp.partial`) and the history in a file (`store: file` or `both`), such a build
  leaves a new kind of entry, `partial`:
  `... | partial | parts 50-calculations, 60-discussion; changed: 60-discussion; with nulabreport v1.28.20, pdfmd v3.30.23 | parts=... changed=... new=... shas=... out=...`.
  `changed` compares each part's text with the last entry that saw it; a full build in parts mode now records every part's hash (`shas=`) for
  that, and a part no entry has seen is `first seen` (`new=`). `--history` lists the entries as `partial`. Off by default (a history that
  held full builds only gains lines); older pdfmd versions keep a `partial` line as a comment. A `partial` entry has no `sha`, so it is
  never offered by `--history-restore`.

### Tests

- `tests.test_partial_history` (the entry round trip, the key, parts built and changed against a full build, first seen, off by default,
  the flags, a section of a plain document).

## v3.30.22 — 2026-10-25

Pre-edit state: commit `85a9283` (v3.30.21).

### Added

- **A range of parts:** `pdfmd @45-60` (or `--section 45-60`, `doc#45-60`) builds every top-level part numbered from 45 to 60, ends included,
  whether or not a part has that exact number; a reversed range is the same, and it joins other names (`@10,45-60`). A part literally named
  `45-60` still wins, and a range that covers no part is the usual "matches no part" error. Only digits on both sides count, so
  `10-introduction` is a name as before.

### Tests

- `tests.test_sections.PartRanges`.

## v3.30.21 — 2026-10-25

Pre-edit state: commit `b20d62b` (v3.30.20).

### Fixed

- **A build printed `{ans}` lines and bare names instead of numbers (a regression of 3.30.20).** The new `.calc-table` handler was chained
  to the `::: calc` handler with `calc_div(div) or calc_table_div(div)`, and `or` keeps only the first of the two values the first handler
  returns, so the walk went into the div it had just written and the second pass counted its places twice: every span and `{ans}` line after
  the first calc div failed with "the passes disagree about this place" (LR5: 71 lines in the Calculations, the numbers of the Discussion as
  code). The two results are passed on now.

### Added

- When three or more places of a document could not be evaluated, the calculator ends with one line,
  `WARN  calc: 21 places were not evaluated (each is above); the output shows their code or text where the numbers belong`, so a build
  that failed on a whole section is not mistaken for one that printed a single odd span (`--strict` already fails on any WARN).
- A `.calc-table` caption can be written inside the div: a line `Table: Student's *t*, 95%` (or `: ...` after a blank line); `caption="..."` still works.

### Tests

- `tests.test_calc.Statistics`: a silent span glued to an `{ans}` line (the four-line example of the report), the summary line, the three
  caption spellings.

## v3.30.20 — 2026-10-25

Pre-edit state: commit `4f34b63` (v3.30.19).

### Added

- **Statistics in the calculator:** `sum mean median`, `var sd stdev sem` (sample, n - 1), `rsd` (relative standard deviation in percent),
  `ci(0.95, x1, x2, ...)` (half-width of the confidence interval, t * s / sqrt(n), through the existing `qt`), `gstat(x1, x2, ...)`
  (Grubbs' G) and `gcrit(n, alpha)` (its two-sided critical value; agrees with SciPy to 10 figures). They take names as well as numbers:
  `` ~`R_E4 / mean(R_A, R_B2)`{=0dp} times lower `` works as written. These names stay free for a variable (`mean = 5` and `mean(1, 3)`
  side by side, so no existing document breaks); the older function names are still reserved.
- **`::: calc-table`, a line `t# tinf`, `:::`** (or `::: {.calc-table names="t# tinf"}`): a real table (Pandoc `Table`, so the document's table styling, widths and numbering apply)
  of calculator names with their values, in the digits each was defined with (`digits="3dp"` for all). The names are the text of the div or `names=`: names and patterns
  (`*` any characters, `?` one, `#` a run of digits, so `t#` leaves out `t_welch` and `tinf`), a pattern in natural order (t2 before t10); `labels="t1=$t_{1}$; V=Volume"` by name or one per row in order (Markdown and math
  work); `head="Symbol; Value"` or `none`; `caption="..."` (Markdown); the identifier, other classes and attributes go to the table, so
  `{#tbl:t}` can be cited. A name counts as defined at the place of the div, as for a span there; in a part built alone the names of the
  parts above it are known (3.30.19). A name that is not defined, a pattern with no match, a value that cannot be computed: one `WARN
  calc-table` naming it; a div without names prints its own code. `::: {.calc-table t*}` is not a div for Pandoc (braces take only
  `.class`, `#id`, `key=value`) and gets one WARN with the right spelling instead of printing as text.

### Tests

- `tests.test_calc.Statistics` (13): the summary functions against Python's `statistics`, `ci` and `gcrit` against SciPy, the sentence of a
  Discussion, bad calls (one WARN each, the code kept), the new names still free for a variable and the old ones reserved, the table
  (natural order, labels by name, header, caption and identifier on a real `Table`, the place of the div, digits, everything that goes
  wrong, the malformed spelling), and the detection for a document with only a table.

## v3.30.19 — 2026-10-24

Pre-edit state: commit `65dc1da` (v3.30.18).

### Fixed

- **A part (or a section) built alone knows the calculator's names from what stands above it.** `pdfmd @60` printed nothing where
  `` `mean_A`{=2dp} `` had been (the name is defined in part 50), and the build was silent about it. Before the real pass pdfmd now has
  Pandoc read the scaffold and the parts left out that stand above the last one built, with `calc.lua` only (`-t native -o /dev/null`,
  about a second for 128 names); `calc.lua` writes every name with the value of its last definition (`%.17g`, full precision) and its
  digits (`-M pdfmd-calc-dump=FILE`), and the build reads the file back (`-M pdfmd-calc-seed=FILE`) as definitions above everything in the
  document, after the constants file. A section of an ordinary document (`doc#discussion`) does the same with the sections above it. The
  build says `NOTE  calc: 128 names taken from parts 10-50 (evaluated, not typeset)`. Nothing is stored between builds, so nothing is
  stale. HTML, Word, Typst and the other writers that number the whole document and keep the part already evaluated everything.
- **A span the calculator cannot evaluate no longer vanishes.** `` `name`{=2dp} `` is a raw inline of the format `2dp` for Pandoc; the
  filter put that item back, and the LaTeX and other writers drop a raw inline of a format they do not know, so the sentence had a hole and
  the WARN's "the code is kept" was untrue. The code is kept now (printed as code), with the one WARN, which names the format as written
  (`` `ghost`{=2dp} ``).

### Added

- `pdfmd-options: {seed-calc: auto|scan|off}` and `--seed-calc MODE` (a `--setup` row under Cache): `off` gives the seeding up. `auto` and
  `scan` are the same.

### Tests

- `tests.test_calc.PartBuiltAlone`: the dump and seed through the filter alone (the last value of a redefined name at full precision, its
  digits, a name with no digits); a split report's part 60 built alone against the full build (same text, the NOTE); an unknown name printed
  as code with exactly one WARN in both builds; the setting in the document and on the command line; a part that redefines a name is not
  overridden; a part with no calculator and a document without one are built as before; sections above a section (`doc#Discussion`,
  `doc#Notes`).

## v3.30.18 — 2026-10-24

Pre-edit state: commit `ad8efcd` (v3.30.17).

### Fixed

- **Every file pdfmd rewrites is written atomically**: to a temporary file in the same folder, then renamed over the old one (`os.replace`),
  so a crash, a full disk or ^C leaves the old file whole. The mode of the replaced file is kept and a symlink is written through. Covers the
  BUILD NOTES stamp, outputs, `--history-restore`, the backup options, `--extract-tables`, restored attachments, the config and metadata
  files of `--setup` and `--init-backups --global`, `--init-config`, the places that rewrite a finished PDF, and the built-in renderers. A
  process killed between write and rename leaves a `.NAME....part` file.
- **A read-only home, cache or document folder no longer stops a build.** LuaLaTeX failed with `luaotfload: no writeable cache path`, `--cache`
  crashed on a `PermissionError`, and the import itself died when the home could not be looked into. What cannot be written goes to a
  temporary folder of the run (the cache folder, `TEXMFVAR`, `TEXMFCONFIG`, also for child processes), with one `NOTE`; Pandoc runs in a
  temporary folder when the document's folder is read-only, the document's folder staying on `--resource-path` and `TEXINPUTS`.
- **Probes have a timeout.** A version or capability probe (`pandoc --version`/`--help`/`--list-extensions`, `kpsewhich`, `lualatex`/`typst
  --version`, the checks after `--install typst|node|d2|tectonic`, the Pandoc reference-document probe) is cut after 10 seconds
  (`PROBE_TIMEOUT`); one that does not answer counts as "not available" (an `AUTO PROBE` line under `--verbose`). Build commands never get a
  timeout.
- **A missing `pdfmd_lua` is loud.** A lone copy of `pdfmd.py` gave silence while the Lua filters did nothing; it is one `WARN lua:` per run
  now. A document that needs no filter says nothing.
- **Windows: a font list the console could not decode** came back as `None` and stopped the whole build. `installed_font_families()` and the
  fontconfig and `luaotfload-tool` calls decode the child's output themselves, replacing what cannot be read.

### Changed

- **CI** (`test.yml`, which `publish.yml` calls; `publish.yml` itself is untouched): a `linux-pandoc` job (Pandoc 3.1.3 and latest, LuaLaTeX
  and XeLaTeX, the whole suite) and a `golden` job (`scripts/vendor_inkmd.py --check` and the golden test) now gate a release. A `lint` job
  (`ruff --select F`, 39 findings, none silenced) and a `windows-latex` job (MiKTeX, the whole suite) run but do not gate.

### Tests

- New `tests.test_atomic`, `test_readonly_home`, `test_probes`, `test_lua_missing`; `test_auto_states` no longer
  flakes when a scratch folder name ends in `a`.
- From the cloud session (branch `cloud/robustness-ci`, PR 7). The `windows-latex` job fails on 55 tests and 14 errors of 1652 (Windows paths
  in test Lua files, a `\` in `--section`, MiKTeX refusing to run as an administrator, missing fonts); it was the first whole-suite run on
  Windows and the job does not gate.

## v3.30.17 — 2026-10-24

Pre-edit state: commit `fbe5640` (v3.30.16).

### Added

- **`--to ansi` / `--view` draw spanning table cells.** A cell with a colspan or rowspan is drawn across the merged columns and rows, its text
  wraps to the merged width, the borders inside it are left out and each crossing uses the box character its neighbours ask for. A table
  without spans is drawn exactly as before.
- **Coloured code.** Fenced code in python, bash/sh/shell/zsh, json, yaml, c, cpp, java, javascript/typescript, rust and go (and the usual
  aliases) gets keywords, strings, comments and numbers in four 256-colour codes, with no dependency. With colour off (`NO_COLOR`,
  `--color never`, a pipe) or an unknown language the block is exactly as before.
- **Stacked display math.** A `$$..$$` that is the whole paragraph is drawn on several rows where it has `\frac`/`\dfrac`/`\tfrac`, `\sqrt`
  (with an overbar, and `\sqrt[n]{x}`), big operators with limits (`\sum \prod \coprod \int \iint \iiint \oint`) and `\lim`/`\max`/`\min`/
  `\sup`/`\inf` with the limit below. A formula with anything that cannot be stacked, or wider than the line, prints its linear form whole,
  never half stacked. Inline math stays linear.
- **`options.pager_command`** (`pdfmd-options: {pager_command: "bat --paging=always"}`, also spelled `pager-command`; a word list works too),
  the pager of `--view`. Order: `$PDFMD_PAGER`, `$PAGER`, the setting, `less -FRX`. `--setup` row `options.pager_command`, also offered per folder.

### Tests

- `tests.test_ansi` extended with golden tests (a header spanning two columns, a rowspan of 2, both at once; the code colours; stacked math).
  A fuzz run of about 9000 random span tables had no misaligned line.
- From the cloud session (branch `cloud/ansi-limits`, PR 6). Not verified: a real terminal and pager (checked through a pipe). The no-Pandoc
  tier (`pdfmd_ansi/native.py`) builds tables without spans.

## v3.30.16 — 2026-10-24

Pre-edit state: commit `05c6e73` (v3.30.15).

### Fixed

- The built-in renderers (inkmd, md2pdf) set `b5`, `a6`, `b4`, `b6`, `executive`, `folio`, `a0` to `a2`, `c4` and `c5` as A4 in silence;
  they have real sizes now and honour `landscape` (`papersize: a4,landscape`, `classoption`, `geometry`). A paper they do not know is a
  `NOTE` and A4.
- `pdfmd --doc changelog 1` returned a block hidden in an HTML comment: `--doc` skips HTML comments now, and `--doc search` skips the
  README's contents list.
- `docs/agents.md` counted its commands wrongly and called attaching the source the default (it is off unless asked). The README's
  `pdfmd --doc readme tectonic` example and its sample search output were invented; they are real output now. The README no longer calls
  macOS's Python 3.9 too old.
- The zipapp carries the documents, so `pdfmd --doc` works in a `.pyz`. `pyproject.toml` requires `setuptools>=77` (PEP 639 license fields).

### Changed

- README: a contents list at the top and a shorter "Why".
- `pdfmd_docs.version()` derives the version the docs name from `PDFMD_VERSION`, and `tests.test_docs_consistency` fails on drift.
- `CHANGELOG.md` header: the patch rule and the `PDFMD_VERSION` location are described as CLAUDE.md states them, and the "why this starts
  at 2.0.0" paragraph is visible text instead of a comment.

### Removed

- Four unused functions: `pandoc_missing_message`, `kpsewhich_path_text`, `normalize_stamp_value`, `normalize_backup_value`.

### Tests

- New `tests.test_docs_consistency`; `test_native`, `test_doc` and `test_packaging` extended.
- One reviewer finding was skipped as wrong: the stamp is written before the backup on purpose (a backup per compile would flood the folder).
- From the cloud session (branch `cloud/review-fixes`, PR 5). Not verified: md2pdf with `executive` and `folio`.

## v3.30.15 — 2026-10-24

Pre-edit state: commit `c43923e` (v3.30.14).

### Added

- **An indent div takes its value in the class word.** `::: .indent=3in`, `::: indent=3in`, `::: indent-3in`, `::: {.indent-3in}` and
  `::: {.indent=3in}` (and `::: .indent`, `::: .noindent`) all mean `{indent=3in}`, through the same length parser (false, true, a number,
  units). Pandoc reads the unbraced forms as a single class word, so only the braced `{indent=...}` carried a value before.
- **A near miss warns.** A class that looks like an indent div but is none of the accepted spellings (`.indent3in`, `.noindent=2em`) gets one
  `WARN  indent: '<class>' is not an indent div; write ::: {indent=3in} (or ::: noindent)` per run and is left as written. A project's own
  `.indented`, `.indentation` and `.indent-block` are not looked at.
- **A bare `::: csv` builds a table** like `::: {.csv}`, in the Pandoc route and in the built-in renderer, when it holds inline data.
  `file=` and `align=` still need the braces; `::: csvfile` and `::: csv-x` do not match.
- **`csv: off`** (`pdfmd-options: {csv: off}`, short for `csv: {enabled: false}`), `--csv` / `--no-csv` and `PDFMD_CSV` (for `-j` workers)
  switch the csv-in-a-div feature off: the filter is not added and the div stays a plain div with its text, with no WARN, also in the
  no-Pandoc renderer. A mapping such as `csv: {rows: 30}` still works and leaves tables on. The command line wins over the options.
  `--setup` row `options.csv.enabled`.

### Tests

- New `tests.test_csv_switch` (17 tests); `tests.test_indent` extended (every accepted spelling, a measured x position in a real PDF, near
  misses that warn, `.indented` that does not). One assertion fixed: it now accepts Pandoc 3.1's `\hypertarget` as well as `\label`.
- From the cloud session (branch `cloud/small-patches`, PR 4).

## v3.30.14 — 2026-10-24

Pre-edit state: commit `2c0b9a3` (v3.30.13).

### Added

- **Room around a `::: calc` div, and optional centring.** The block ran straight into the paragraphs above and below it. It has `0.75em`
  of room on each side now (`calc: {space: 0.75em}`, `--calc-space LENGTH|off`, `PDFMD_CALC_SPACE`; pt, mm, cm, in or em; a `--setup` row):
  `\par\addvspace{..}` for LaTeX and Beamer (it merges with the paragraph skip next to it instead of adding to it), `#v(.., weak: true)`
  for Typst, vertical padding on a wrapping `<div>` for HTML and the other HTML writers. `calc: {align: center}` / `--calc-align center`
  (left is the default; a `--setup` row) centres the lines: a `\begingroup\centering` group, `#align(center)[..]`, `text-align: center`.
  Markdown, Word and the plain writers get the block as before. A hidden `::: {.calc .hide}` div has no room, as it prints nothing.
- **Ctrl-C is one line.** An interrupted run printed a page of traceback. It prints `Interrupted (Ctrl-C).` and exits with status 130 now
  (`main()` wraps `run_main()`); Pandoc and the engines get the signal from the terminal, and the temporary folders are removed.

### Tests

- `tests.test_calc.Switches.test_a_calc_div_has_room_around_it_and_can_be_centred`, `test_a_bad_space_or_align_is_an_error_and_the_other_writers_get_nothing`;
  the exact argument lists now carry `pdfmd-calc-space=0.75em`; `tests.test_interrupt`.
- Measured in a LuaLaTeX PDF: the gap between the paragraphs around a calc line grew by the room set (2 cm: +113 pt), and `align: center`
  moved the block's left edge from the margin to the middle of the line.

## v3.30.13 — 2026-10-24

Pre-edit state: commit `67e53d2` (v3.30.12).

### Added

- **A trailing comment in a statement block.** In a ```` ```{=calc} ```` block, a `::: {.calc .hide}` div and the constants file a `#` starts
  a comment to the end of the line, so `M_Mg <- 24.305 # g/mol` defines `M_Mg`; a whole-line `#` was skipped already. Before, the `#` was read
  as arithmetic: the WARN "'#' is not arithmetic" and an undefined name for every later use. `--` is not a comment (it can be a double minus).

### Tests

- `tests.test_calc.Blocks.test_a_hash_starts_a_comment_at_the_end_of_a_line_too`.

## v3.30.12 — 2026-10-24

Pre-edit state: commit `52f3d0f` (v3.30.11).

The calculator's constants file is part of the source that `--attach-source`, `--keep-source` and `--embed-metadata files` carry.

### Fixed

- **A constants file named in `metadata.yaml` was left out.** `calc: {constants: tables/constants.csv}` was found only when the document's own
  text mentioned the path (the scan for referenced files), so a file named in a metadata file, the usual place for a report, was not attached
  and `pdfmd --restore` gave back a source that failed with "no file". It travels now like the `.hst` history file (`add_calc_constants`),
  and comes back under the same relative path. A constants file outside the document's folder gets the usual "outside" warning.

### Tests

- `tests.test_calc.Blocks.test_the_constants_file_named_in_a_metadata_file_travels_with_the_source`.

## v3.30.11 — 2026-10-24

Pre-edit state: commit `2e35666` (v3.30.10).

Definitions in bulk for the calculator: a report that needs 14 constants (t values, a stock concentration, molar masses) kept them as a run of
hidden `` `name = value`{=} `` spans on one line (issue file 2, B).

### Added

- **A block of statements.** ```` ```{=calc} ```` (Pandoc's native raw block, lines intact), one statement per line, each as the text of a
  `{=}` span: `name = value` or `name <- value` stores and prints nothing, a line with `{ans}` prints (one paragraph per line), blank lines and
  `#` lines are skipped, a failing line is kept as code with one WARN and the rest goes on.
- **```` ```{=} ```` works as ```` ```{=calc} ````.** Pandoc does not read an empty raw format as a block: it is a paragraph with one code
  span whose line breaks are gone. `calc.lua` finds those paragraphs and reads the lines again from the input files Pandoc was given
  (`PANDOC_STATE.input_files`), matching them by their text in document order; a fence shown inside a longer fence is not touched. From
  standard input there is no file: one WARN says to write `{=calc}`.
- **`::: {.calc .hide}`** (also `.hidden`): the same statements, nothing printed. Its lines are read as Markdown.
- **`` `code`{=calc} ``** is `` `code`{=} `` (Pandoc's own raw attribute). A ```` ```{.calc} ```` code block stays a code block, never calculated.
- **`calc: {constants: FILE}`**, `--calc-constants FILE`, `PDFMD_CALC_CONSTANTS`, a `--setup` row: a CSV (comma, semicolon or tab; columns
  `name,value[,digits[,note]]`; header row optional; `#` lines skipped) read before the document, found beside the document, beside its
  metadata files, then in the current folder. The `digits` column is the format that name remembers for `{subs}` and a bare `` `t18`{=} ``.
  pdfmd turns the file into statements and passes them as `-M pdfmd-calc-constants`; the document defining a name again gets the usual WARN.
- The filter is also added for a document that has only such a block.

Tests: `tests.test_calc.Blocks` (12: the block, the empty-format fence from a file and from standard input, a fence inside a longer one,
fourteen constants, the hidden div, failing lines, detection, the constants file by option, flag and variable, a semicolon file, the errors).
README "Calculations inside the text" 6, `docs/recipes.md` 1.11.

## v3.30.10 — 2026-10-24

Pre-edit state: commit `735569e` (v3.30.9).

The calculator gets the normal and Student's t distributions, for a lab report that needs a 95 % two-tailed t at 13, 16, 18, 93 or
13.947 degrees of freedom, none of which a printed table lists.

### Added

- **`qt(p, df)`, `pt(t, df)`, `qnorm(p)`, `pnorm(z)`** in `pdfmd_lua/calc.lua`, lower tail as in R, no library. `qnorm` is Wichura's AS 241;
  `qt` inverts the incomplete beta function (continued fraction, bisection on the tail so a small `p` keeps its figures), exact for 1 and 2
  degrees of freedom, and a Cornish-Fisher series above 1000. `df` may be a fraction or `Inf` (`qt(0.975, Inf)` is `qnorm(0.975)`), a name
  works (`qt(0.975, df_w)`). `p` outside (0, 1) or `df <= 0` keeps the text with one WARN. The constant `Inf` is new.
- Accuracy against R 4.6.1 and SciPy: `qnorm` and `pnorm` about 1e-15; `qt` about 1e-12 (3e-11 for `p` near 1e-12); `pt` about 1e-12 up to
  1000 degrees of freedom and 1e-9 above. `qt(0.975, df)` equals R's to the 12 figures it prints for df 1, 2, 3, 6, 8, 9, 10, 13, 16, 18, 93,
  96, 13.947016149 and Inf.
- **Changed:** `qt`, `pt`, `qnorm`, `pnorm` and `Inf` are now built-in names, so a variable called `pt` is refused like `sin` (it was free
  before; the calculator is unreleased).

Tests: `tests.test_calc.Distributions` (R's table, 105 SciPy values, `Inf`, the symmetry, a name as df, the domain errors). README, the
docstring.

## v3.30.9 — 2026-10-24

Pre-edit state: commit `cbcd7a5` (v3.30.8).

A `::: calc` div has no first-line indent. The author wrote `::: noindent` around every calc block of a report whose document indents
its paragraphs; the div now does it itself.

### Added

- **`calc: {noindent: true}`, on by default.** `pdfmd-options: {calc: {noindent: false}}` gives the div the document's own indent again;
  `--calc-noindent` / `--no-calc-noindent` (the command line wins), `PDFMD_CALC_NOINDENT` for `-j` workers, a `pdfmd --setup` row.
  `calc.lua` puts `indent="false"` on the finished div and `indent.lua` (now also added whenever a calc div is in the text and the
  calculator and this option are on) does the rest per writer: LaTeX and Beamer `\begingroup\setlength{\parindent}{0pt}` ... `\endgroup`,
  Typst a `#set par(first-line-indent: 0pt)` block, HTML a `text-indent` style. Markdown, Word and the plain-text writers get no attribute
  and no NOTE (Word follows with the indent item queued for docx/odt). An `indent=` or `.indent` / `.noindent` on the same div wins, and
  an outer `::: noindent` works as before. The default is on because the `::: calc` div was never published (3.30.6 onward).
- A div that carries both classes is written `::: {.calc .noindent}`; `::: calc noindent` is not a Pandoc div (one bare word only) and is
  left as text.

Tests: `tests/test_calc.py` (the default, an `indent=` and `.indent` that win, the option, the flags, the variable, other writers) and a
real LuaLaTeX PDF: body text starts at 86.9 pt, the calc lines at 72.0 pt. README "Calculations inside the text", `docs/recipes.md` 1.11.

## v3.30.8 — 2026-10-24

Pre-edit state: commit `56fe65a` (v3.30.7).

Two fixes and three additions to the calculator, found converting a whole Calculations part of a real lab report (about 130 `{ans}` lines)
to `{=}`, `{ans}` and `::: calc`.

### Fixed

- **A `` `...`{=} `` span inside a `::: calc` div sees the definition above it, not the last one.** The div's lines were registered before
  the spans in them, so in `a = 1 + 1 = {ans:1dp}, so `a * 10`{=}` followed by the same line with `3 + 3`, both spans took the last `a`
  (60 twice, no WARN). Lines and spans are now read together, line by line, in the order of the text, and the div no longer hands its
  paragraphs to the document-wide pass a second time.
- **A `::: calc` line may carry anything after its last `{ans}`.** `y = 2 + 2 = {ans:1dp} ppm \ce{Ca^2+}` (raw TeX), a superscript, bold,
  a link or `$..$` after the value used to leave the whole line as written, `{ans}` and all. Only the text up to the last marker has to be
  plain; the rest is copied as it is. Formatting before the last `{ans}` is still refused with the WARN.

### Added

- **More than one `{ans}` in a span or a line.** After text that does not end in `=` it repeats the value just shown in its own format
  (`= {ans:1dp}, so {ans:0dp}`); after text that ends in `=` it is a new calculation whose expression is the longest tail of that text
  that reads as one (`so round(n) = {ans:0dp}`; `so k = round(n) = {ans:0dp}` also stores `k`).
- **`{subs}`: the expression with the names replaced by their values.** `ppm1 = C_dil * V / 100.0 * 40.078 * 1000 = {subs} = {ans:2dp} ppm`
  prints `... = 0.002039 * 34.41 / 100.0 * 40.078 * 1000 = 28.12 ppm`. Each name shows the digits it was defined with (a hidden span's use
  `calc: digits`); the computation always uses the full values. Literals, operators, functions, `pi` and `deg` stay as typed; a negative value
  gets parentheses (`(-0.5)^2`) unless nothing before it could be read as a sign. `calc: {subs: true}` (also `--calc-subs` /
  `--no-calc-subs`, `PDFMD_CALC_SUBS`, a `pdfmd --setup` row) puts the copy before every `{ans}` that follows an expression with names; a
  lone name, an expression without names and a repeated `{ans}` get none. `{subs}` forces it on a line, `{nosubs}` or `{subs:off}` stops it.
- **`<-` assigns like `=`**: `` `t18 <- 2.10092204`{=} ``, `ppm1 <- C_dil * V = {ans:2dp}`.

The Unicode operators (`×`, `·`, `÷`, `−`) are now read by the tokenizer itself (the parser needs byte positions for `{subs}`). Queued, not
done: `qt(p, df)` and `qnorm(p)`.

## v3.30.7 — 2026-10-24

Pre-edit state: commit `230ff0b` (v3.30.6).

### Fixed

- **A partial build lists its metadata again.** `pdfmd @10,40` (or `report#section`) printed `FOUND nulabreport.lua, 2 parts` and
  `DEFAULTS packages mhchem`, without the metadata file, the preamble, the global metadata or the balanced tables a full build lists.
  The files were used all along (the Pandoc command had them); only the summary was wrong. The hidden pass over the whole document, which
  gives the left-out parts their numbers, printed its own summary to nowhere and emptied the items already recorded. The summary is now saved
  before that pass and put back after it (`AutoLog.snapshot` / `restore`). Test: `tests/test_autolog.py` (`Builds`).

## v3.30.6 — 2026-10-24

Pre-edit state: commit `1725405` (v3.30.5).

### Added

- **`{ans}`: the calculator prints the text it was given.** Inside a `` `...`{=} `` span, `` `V = 20.60 - 0.00 = {ans:2dp} mL`{=} `` becomes
  "V = 20.60 - 0.00 = 20.60 mL" (the text as typed, `{ans}` replaced); the expression is what stands between the last `=` before `{ans}` and that
  `= {ans}`, and what stands before it is a label. `` `2-4={ans}`{=} `` works unspaced and prints as typed. Several `{ans}` may share a span.
- **Names.** A plain identifier on the left (`C_EDTA = ... = {ans}`, or the word after a `:` `;` `,` of a label: `Run 1: V = ...`) is stored with the
  FULL value, not the displayed one, so later calculations cannot drift from what the page shows. `` `A = 4 - 2`{=} `` only stores (prints nothing);
  `` `A`{=} `` and `` `A * 2`{=} `` print values. A name is found anywhere in the document, parts included (Results may cite Calculations): the
  nearest definition above its use, else the first below; a name may be defined again; a cycle, an unknown name or a name that is a function or
  constant (`pi`, `sqrt`) is a WARN and the text is kept. A stored name remembers the digits it was given.
- **Number formats.** `{ans:4sf}` four significant figures (trailing zeros kept: 20.60; the digits before the point are never dropped, 1049 at 3sf is
  1049; scientific only below 1e-6 or from 1e15), `{ans:2dp}` two decimal places, and after a span `` `1/3`{=3sf} `` (Pandoc reads `{=3sf}` as a
  raw attribute: the filter takes `NNsf` / `NNdp` raw inlines and leaves every other raw format alone).
- **`::: calc`** (also `::: {.calc}`, `::: {#id .calc}`; the class alone, as in Pandoc) calculates every line that holds `{ans}`, in paragraphs, list
  items and quotes, without backticks; other lines are plain text; a line with bold, a link or math is left as written with a WARN. The detection
  adds the filter for the div as well. It is the opt-in form of calculating prose: nothing outside it is read.
- `--calc-digits 4sf|2dp` (and `PDFMD_CALC_DIGITS` for `-j` workers) and `pdfmd-options: {calc: {digits: 4sf}}` set the default format of a document
  (unset: as R prints, up to 7 figures); a span's own format wins. `--setup` rows. README "Calculations inside the text" (for anyone writing with it),
  docs/recipes.md 1.11.

### Changed

- **The calculator's options live under `calc:`** (like `csv:` and `backup:`): `pdfmd-options: {calc: {enabled, digits, round}}`, `--setup` rows
  `options.calc.enabled|digits|round`. `calc: off` / `calc: false` stays as the short form of `enabled: false`. The flat `calc-round` key of 3.30.4
  is gone (3.30.4 was not released); `--calc`, `--no-calc`, `--calc-round` are unchanged. A wrong `digits` or `round` is an error naming the key.
- `tests/test_calc.py`: 33 tests (the new ones: 16 statement forms, 20 formats, the div in its spellings, two placeholders in a line, the warnings,
  the options, flags and variables, and a PDF in which Results cites a name that Calculations defines in a `::: calc` div).

### Not done (queued)

- Spacing the operators for you (`C=n/V={ans}` printed as `C = n / V = 0.0203`), calculating plain prose without `{=}` or a div, `$..$` math, statistics
  (mean, stdev, rsd, a t quantile, Grubbs), a check mode for a number already typed, significant-figure tracking, `.qmd` spellings.

---

## v3.30.5 — 2026-10-24

Pre-edit state: commit `2d56ccf` (v3.30.4).

### Fixed

- **A symlink in `parts/` crashed the build** (`ValueError: '...' is not in the subpath of '.../parts'`). `collect_parts()` resolved every part to its real
  path, so a `.md` file linked into the parts folder, or one inside a linked folder, no longer lay under it and `part_key()` / `select_parts()`
  could not name it. A part now keeps the path it has in the parts folder (`os.path.abspath`, not `resolve()`), so a linked file or folder is built
  as a part, in its place in the order and under its link's name. (A folder in `parts/` is always walked: to keep a reference folder beside the parts
  without building it, name it with a leading `_` or `.`.)

### Added

- **`@` for `#` in the section shorthand**: `pdfmd report@methods`, `pdfmd doc@@yield` (a level-2 heading), `pdfmd @yield` (the folder's only Markdown
  file), `doc@a+b`. An interactive bash (and some other shells) takes a `#` for the start of a comment and never passes it on, so `pdfmd #10` ran
  without its argument. A real file whose name has an `@` still wins, as with `#`; `--section` is unchanged. `tests/test_symlinked_parts.py`.

---

## v3.30.4 — 2026-10-24

Pre-edit state: commit `b55a83b` (v3.30.3).

### Added

- **An inline calculator: `` `2026 - 2006`{=} `` becomes `20`.** Inline code followed at once by a bare `{=}` is replaced by its value, in every
  output format a Pandoc build writes. `pdfmd_lua/calc.lua` has its own small parser and runs nothing (no `load`, no R, no Python), so a document from
  anybody is safe and nothing asks for trust. Operators: `+ - * /`, `^` and `**` (right to left; `-2^2` is -4), `%` and `%%` (remainder, floored:
  `-7 % 3` is 2), `//` and `%/%` (floor division: `7 %/% 2` is 3), parentheses, unary minus. `|a - b|` is the absolute value. A `%` that no operand follows is a percent sign, a label and not an operator (`0.5 / 4 * 100%` is 12.5, as a lab report
  writes it); `×`, `·`, `÷` and `−` are `*`, `*`, `/` and `-`. Numbers: `12`, `.5`, `6.022e23`. Constants `pi` and `deg`
  (= pi/180, so `sin(30*deg)` is 0.5). Functions (angles in radians): `sin cos tan cot sec csc`, `asin acos atan acot` (`atan(y, x)` is the two-argument
  arctangent), `sinh cosh tanh asinh acosh atanh`, `sind cosd tand` (degrees in) and `asind acosd atand` (degrees out; `asin(x) / deg` is the same), `exp ln log` (`log(x, base)`), `log10 log2 sqrt cbrt abs sign`,
  `floor ceil trunc`, `round(x)` and `round(x, digits)` (an exact half goes to the even digit, as in R and Python: `round(2.5)` is 2, `round(3.5)` is 4; `calc-round: away` makes it 3), `min max` (any number of
  arguments), `hypot factorial`. A trig result closer to 0 than 1e-15 is 0 (`sin(pi)`). The value prints as R does: up to 7 significant digits, `20`
  and not `20.0`, `0.3` for `0.1 + 0.2`, `1.2044e+24` for a very large one.
- What the parser cannot evaluate (a name it does not know, a division by zero, `asin(2)`, an unfinished expression, an infinite or undefined
  result) is kept as the code it was, without the `{=}`, with one `WARN  calc: ...` naming the span and the reason. Inline code without `{=}`, code
  blocks and a `{=}` anywhere else are never touched.
- `--calc` / `--no-calc` (and `PDFMD_CALC=on|off`, which is how a `-j` worker gets it) and `pdfmd-options: {calc: off}` (the document, a metadata file or the
  config file, in that order of precedence after the flag) turn the calculator on or off, with a `--setup` row;
  `--calc-round even|away`, `pdfmd-options: {calc-round: away}` and a `--setup` row choose how `round()` settles an exact half (default even, like R and Python); the filter is
  attached only to a document that has a `` `...`{=} `` span. Without Pandoc the built-in renderer shows the span as written. docs/recipes.md 1.11.
- `tests/test_calc.py`: 88 expressions with their text, 23 failures with their warning, the neighbouring text, code that must stay, the HTML, LaTeX
  and Typst writers, the detection, the switch (document and metadata file), and real PDFs (a part included) read back with `pdftotext`.

### Not done (queued)

- spellings for `.qmd` (`` `{r} 2 + 2` ``, `{python}`) and an `all` mode that evaluates every
  arithmetic-only code span.

---

## v3.30.3 — 2026-10-24

Pre-edit state: commit `ab380d1` (v3.30.2).

### Added

- **`--to ansi`: a document as styled text for a terminal.** Bold, italic, inline code, strikethrough, links, headings, ordered and bullet lists, block
  quotes, code blocks, rules, footnotes (listed at the end), a title block from the front matter, and every table as a box-drawn grid: a rule between
  rows, a bold header, each column as wide as its widest cell, the alignment the table gives, cells wrapped when the window is narrower than the table,
  wide (East Asian) characters counted as two cells. The text is wrapped to `--width N`, else the terminal's width, else 120. It is a build like the others:
  Pandoc reads the document through the usual steps (metadata files, filters, `pdfmd-options`, citations, `\ce`, the CSV tables) and writes its JSON AST,
  which the new package `pdfmd_ansi/` (a pure function, no other pdfmd module imported) draws; the file is `NAME.ansi`, and `-o x.ansi` selects the format.
  Without Pandoc the built-in parser (`pdfmd_inkmd`) reads the Markdown instead, with a NOTE: no filters, citations, footnotes or metadata files.
- **Math as text, level (a).** `MathText` (the converter the built-in renderer uses) gets an ANSI back-end: Greek letters, operators, Unicode sub- and
  superscripts, `(a+b)/(c+d)`, `√(...)`, variables in italic, a function name after a variable set off by a space (`RT ln K`); a formula alone on its line is
  centred; one the converter cannot read is shown as its TeX.
- **`--view`: read a document in the terminal.** = `--to ansi -o -` + a pager. It takes files (a folder: its Markdown files), `-` or a pipe on standard
  input (written to a hidden temporary `.md` beside the cwd so relative pictures resolve, and removed), else the Markdown files of the current folder, else
  what is typed or pasted into the terminal (ended with Ctrl-D; a hint says so on standard error). Several files are one stream in the order given, with a
  dim rule naming each. Each file is built on its own by a child pdfmd into a scratch folder, so all discovery and notes apply; the notes (`OK`, `DEFAULTS`)
  stay off the screen unless a build fails or `--verbose` is given, every other message goes to standard error. The styling stays when the output is piped
  (`pdfmd --view x.md | less -R`). `--view -o FILE` saves the file and shows nothing; `--view` with another `--to` is an error.
- **The pager** (on by default, `--pager` / `--no-pager`, `pdfmd-options: {pager: false}`, a `--setup` row, also in the folder screen): only when
  standard output is a terminal, through `$PDFMD_PAGER`, else `$PAGER`, else `less -FRX` (`-F` quits at once when the text fits one screen, `-R` keeps the
  colours; a `less` given without `-R` gets it).
- **`-o -` is standard output**, for `--view` and for any format built from a file or a pipe: the build goes to a scratch folder and its bytes are copied to
  stdout; several documents are joined only for text formats (a binary format, `pdf` or `docx`, with several inputs is refused). `--color auto|always|never`:
  a file and `--view` are styled, `-o -` into a pipe is plain, `NO_COLOR` turns `auto` off, `always` wins over it.
- Links are `words (address)`, or OSC 8 hyperlinks in a terminal known to draw them (iTerm2, WezTerm, Ghostty, VS Code) when the text is not paged. Text
  from a document is cleaned before it is shown: control characters (an ESC would start a terminal sequence) and bidi overrides are dropped.
- `--help view` lists `--view --pager --color --width`; `--view` is on the short help page. The flags are in `pdfmd_setup/inventory.py` (`--pager` is the row
  `options.pager`; `--view` a command; `--color` and `--width` per run); `pdfmd_ansi` is in `pyproject.toml` and `scripts/build_zipapp.py`.

### Known limits

- A cell that spans rows or columns is drawn in its first cell only. A formula is linear (stacked fractions, roots and sums with limits, and pictures of
  display math in terminals that show them, are later patches). Raw LaTeX, HTML and Word pieces are left out (`--verbose` counts them). Code is not highlighted.
- The vendored built-in parser reads a `>` quote that follows a list, after a blank line, as a paragraph plus a one-line quote; that is in `pdfmd_inkmd`
  (to be fixed upstream in inkmd, the vendored copy is not edited by hand), so it shows only without Pandoc.

Tests: `tests/test_ansi.py` — widths and wrapping, escape-code cleaning, inline styles with and without colour, links, grid widths at several window
widths (wide characters, shrinking, wrapping), lists/quotes/code, math through the callback; and through the full pipeline: `--to ansi` to a file, `-o x.ansi`,
`--view` into a pipe, `NO_COLOR` / `--color`, `-o -`, several files, a pipe and `-`, `--to docx` refused, `-o` replacing `--view`, no Pandoc.

---

## v3.30.2 — 2026-10-22

Pre-edit state: commit `814acf5` (v3.30.1).

### Added

- **`--table-keep N` and `pdfmd-options: {table-keep: N}`.** pdfmd passes `-M tablekeep=N` to Pandoc, for a Lua filter that keeps a short Markdown
  table on one page (nulabreport.lua, v1.28.16: a table of up to `N` body rows moves to the next page whole instead of splitting; its built-in 10 was
  hard-coded before). `0` lets every table break. Order: the command line (it reaches `-j` workers as `PDFMD_TABLE_KEEP`), then `pdfmd-options.table-keep`
  (document, metadata files, config), then nothing: pdfmd passes no `-M`, and the metadata's own `tablekeep:` or the filter's default stands. Pandoc's `-M`
  wins over a metadata file, so the option also overrides a `tablekeep:` there. A value that is not a whole number stops the run with a message naming the
  file. It is set at all three places the command is built (PDF and the other outputs, the Office route). A row in `pdfmd --setup` (Tables), in the
  folder screen too. A filter that does not read `tablekeep` ignores it. Tested through the full pipeline: the flag, the option, the metadata key and
  their order, and a bad value.

---

## v3.30.1 — 2026-10-21

Pre-edit state: commit `5617970` (v3.30.0).

### Fixed

- **The closing line names the PDF, not the `.tex` the cache made on the way.** A build through the cache folder (a part alone, `report#second`, with `cache:` on,
  as the lab reports have it) printed `OK    report.md > ~/.cache/pdfmd/b888f4388b-report/report.tex  (lualatex)` although the PDF was written beside the source:
  the nested Markdown-to-`.tex` stage of `convert_via_cache()` recorded its own file as the build's output, and nothing put the PDF back. It is restored after the
  stage, so the line is `OK    report.md > report.second.pdf  (lualatex)`; `--to latex` still names the `.tex`, and `--verbose` still shows the cache folder (the
  `CMD` and `TEXDIRECT` lines). Tested with the cache route on, which fails without the fix (`tests/test_build_record.py`).

---

## v3.30.0 — 2026-10-21

Pre-edit state: commit `a030424` (v3.29.36).

### Added

- **A paragraph indent for a stretch of text: `::: {indent=false}`.** A fenced div with `indent=` (`false`, `no`, `off`, `0`; `true`, which is 1.5em; or a
  length: `2em`, `12pt`, `5mm`, a bare number is em), or the classes `.noindent` / `.indent`, sets the first-line indent of the paragraphs inside it and puts the
  document's own back at the closing `:::`, so there is no "turn it back on" line to forget. Divs nest (the inner one wins, the outer comes back after it), and
  the div's `#id` and other classes stay. The new `pdfmd_lua/indent.lua` does it per writer: LaTeX and Beamer set `\parindent` in a `\begingroup` ...
  `\endgroup`, Typst a `first-line-indent` rule in a content block (not in a `#block`, where it did not reach a paragraph that followed another), HTML and
  EPUB a `text-indent` style on the div. Pandoc Markdown, GFM and CommonMark keep the div as written; Word, OpenDocument and the rest have no per-block indent,
  so the text stays and a NOTE says the setting was left out. A value that is not an indent is a WARN and changes nothing. The filter is added only for a
  document (or one of its parts) that has such a div (`indent_filter_args()`, `INDENT_DIV_RE`); there is no switch, since the div is the opt-in. Found with the
  calculations of a lab report, where the lines of arithmetic should not be indented but the prose between them should. New `tests/test_indent.py`: the
  detection, every writer, and real PDFs measured with `pdftotext -bbox` (a plain document and a report in parts). `docs/recipes.md` 1.9.

---

## v3.29.36 — 2026-10-14

Pre-edit state: commit `bf7c82c` (v3.29.35).

### Fixed

- **The examples job of the CI gets a token for `pdfmd --install`'s release listing.** Its Tectonic step (v3.29.7) listed GitHub's releases without one, and the
  runners' shared addresses hit the unauthenticated rate limit ("GitHub lists no Tectonic download for this machine"): it failed the macOS job of v3.29.35 twice,
  and with it the publish (which waits for every test job), after passing before. The other install job already passed one. pdfmd itself is unchanged.

## v3.29.35 — 2026-10-14

Pre-edit state: commit `0fce452` (v3.29.34).

### Fixed

- **The Calibre workflow looks harder at its one failing test.** The first diagnostic (v3.29.27) found that Calibre's own `ebook-convert` gives a
  small document its PDF bookmarks on Linux and on macOS (`pages 1 outline ['Introduction', 'Second section']`), while `tests.test_calibre.Builds.test_a_document`
  (the same headings plus a formula, a table and `papersize: a4`, built through pdfmd) finds none on both runners (it passes on the author's Mac). A new step
  builds that document through pdfmd in five variants (plain, with the formula, with the table, with the paper, all) and prints the bookmarks of
  each, with pdfmd's `--verbose` output of the first and the last. It never fails the run. Nothing in pdfmd changed.

## v3.29.34 — 2026-10-14

Pre-edit state: commit `7930027` (v3.29.33).

### Fixed

- The CI of v3.29.33 (the native jobs: no Pandoc, no `prompt_toolkit`, an older setuptools, Windows pipes) stopped three things that a machine with all of
  them had not shown; nothing was published from it:
  - **`pdfmd --doc` to a pipe on Windows** wrote the documents in the ANSI code page, so `--doc search` (whose lines of the README and the recipes
    are not ASCII) could not be read back as UTF-8, and a character outside that code page would have stopped it. A `--doc` that is not on a terminal
    writes UTF-8 now.
  - **The folder screen of `pdfmd --setup FOLDER` told, without the full-screen interface installed, to set the row "This setup screen"** to fancy: a row
    that screen does not have. No nudge in a folder's setup.
  - **`tests/test_doc.py` ran `setup.py build_py` with the setuptools of the machine**, and one older than 77 does not read the license string of
    `pyproject.toml` (PEP 639): the test is skipped there (the publish job builds with a current one, in an isolated environment).

## v3.29.33 — 2026-10-14

Pre-edit state: commit `fe17777` (v3.29.32).

### Fixed

- **A folder cannot loosen what finds code** (found in review before anything was published). With 3.29.30 a hidden `.pdfmd/config.yaml` with
  `auto: {lua: on}` switched Lua discovery back on where the config said `no-auto: [lua]`, against the rule that a folder's options cannot name code,
  and `explicit-only` in a folder would have let the document's named filter through. Now, for `lua` and `preamble` (and the aliases `files`,
  `tex`) a folder's `on` is ignored with a `WARN`, and the state is the strictest of the layers that are not a folder's and of every folder's;
  only the command line and the document's own `pdfmd-options` can loosen. Folders can still switch back on every other kind.
- **A folder cannot name a Word profile:** `office: {profile: FILE}` (a Lua file the Word route runs) is dropped from a folder's options with a `WARN`;
  `config_options(document)` brought it in with 3.29.29. (`pdf-engine` is checked against the engines pdfmd knows, so a folder's `./x.sh` is refused.)
- **`explicit-only` for metadata no longer drops the user's own defaults.** It looked for nothing and, with nothing named, also dropped the folders'
  `.pdfmd/metadata.yaml` and the global `metadata.yaml` of `--setup` (the author and paper size you set there vanished): only the search beside the
  document is skipped now (`find_metadata(discover=False)`); `off` is what it always was.
- `docs/agents.md` says a `.pdfmd/` folder above the document applies even with `PDFMD_CONFIG=` empty.

## v3.29.32 — 2026-10-14

Pre-edit state: commit `b2f15dc` (v3.29.31).

### Fixed

- A test of the folder settings ran a whole build to see a warning of `folder_layer_files`; without Pandoc (a CI job with none) the build stops before
  it. It asks `folder_layer_files` in the process now. Nothing else changed.

## v3.29.31 — 2026-10-14

Pre-edit state: commit `386eab3` (v3.29.30).

### Added

- **`pdfmd --setup FOLDER` shows where a value comes from.** A row the folder has no value for reads `9  (global)` or `3  (folder ~/proj)`
  (the nearest setup above that sets it, as a build layers them, and none for `inherit: false` on the folder's own row, which cuts the
  folders above but not the global setup) instead of "(default)" when something above sets it. The numbered screen only; the full-screen one
  shows the default as before. Not done: `--show-config FILE` printing the resolved values with their layer, and the same in the global screen
  (there is nothing above it).

## v3.29.30 — 2026-10-14

Pre-edit state: commit `d99eeed` (v3.29.29).

### Added

- **The automatic kinds are three-state** (queue item 4): `on`, `off` and `explicit-only` (it looks for nothing, but uses what the document
  names: a Lua filter, a preamble, a metadata file; for `lua`, `preamble`, `metadata` and their aliases `files`, `tex`, `yaml`). A layer
  says it with `no-auto:` (a list: off; `true`: everything off, as ever) and/or the new `auto: {lua: explicit-only, margin: on}` of
  `pdfmd-options` (an `auto` entry wins over `no-auto` in the same layer; `explicit-only` for any other kind is an error that says so). The
  old spellings (`--no-auto`, `--no-auto KIND`, `no-auto:`) mean exactly what they did, and the command lines pdfmd builds with them are the same
  byte for byte (checked on a folder with a discovered filter, preamble and metadata file, under every spelling, old code against new).
- **What changes: the layers decide kind by kind instead of adding up.** The command line (`--no-auto`, which only switches off), the document,
  the folders' `.pdfmd/config.yaml` (the nearest first), the global config: the first one that names a kind decides it, so a folder can
  switch back on what the config switched off (`auto: {lua: on}`), where before a kind off anywhere stayed off. For files that only use the old
  spellings nothing differs. `no-auto` in a metadata file is still not read: it would have to be read before pdfmd knows whether metadata files
  are read at all (use the document, a folder's `config.yaml`, or the config).
- **`pdfmd --setup`:** the rows *Look for nothing, use only what the document names* (`auto: {lua: explicit-only}`) and, in a folder's setup, *Switch
  back on* (`auto: {margin: on}`) next to the old *Automatic behaviour to switch off*; the old row is in a folder's setup too now.
- The internal form: a list of the kinds that are off, with `explicit:KIND` entries for the explicit-only ones (it travels through `--no-auto` of
  the child runs and the `no-auto:` marker of an assembled file, whose pattern accepts them). `discovery_disabled()` is asked where pdfmd looks for
  files, `auto_disabled()` where it uses a named one; `document_preambles()` is the one place that joins the two for preambles.

Not done: `explicit-only` for the Word reference document and profile (`officeref`, `officeprofile`: the search and the named file are one step
there), a `--auto` flag on the command line (it only switches off).

## v3.29.29 — 2026-10-14

Pre-edit state: commit `1132c88` (v3.29.28).

### Added

- **`pdfmd --setup FOLDER`** (queue item 4, the folder part): the numbered screen for a folder, writing `FOLDER/.pdfmd/config.yaml` (the
  `options:` and `inherit:`) and `FOLDER/.pdfmd/metadata.yaml` (author, language, paper, fonts ... the rows the global setup keeps in
  its `metadata.yaml`), both for that folder and everything under it. **The folder's `metadata.yaml` is read now:** a build's metadata
  files are the document's own, then the folders' (nearest first), then the global one (`find_metadata`, `pandoc_metadata_order`: a
  later file wins, the global lowest, and `inherit: false` ends the walk for the metadata as for the options). The screen offers only
  what a build reads from a folder (`registry.FOLDER_OPTIONS`, the keys read through `first_pdfmd_option` / `option_sources` or
  `config_options(document)`) and the metadata rows, never a row of the machine (`setup-ui`, `translit`, `disabled`), and says what
  it left out (`o`): the page header and footer, bookmarks, the HTML / Markdown / text output tables, the editor, `table-widths`,
  `no-auto`, `metadata-precedence` ... are read from the global setup alone. A path row (`bibliography`, `csl`, `css`, `office.reference-doc`,
  `backup.dir`) is left out too: relative to the document for `css`, and from the `.pdfmd` folder for a metadata file (Pandoc's own rule),
  which is for the author to decide. A name that is no folder is refused; `--preset` is the global setup's.
- **`config_options(document)`:** the `options:` of the global config with the folders' laid over it field by field, nearest first. The
  readers that skipped the folder layers (`pdf-engine`, `citation-engine`, the cache and `seed-labels`, `parts`, the code filter's wrapping
  and numbering, the Word route's `office:`) take it.

### Fixed

- `pdfmd --setup` wrote a `.bak` of the file and said "your comments are not kept" on every second save: the second line of its own header counted
  as a hand-written comment (the global `config.yaml` and `metadata.yaml`, and now a folder's).

Not done: carrying a folder's files in an attached source or a bundle (a restored PDF builds with the folder it is restored into); showing
the layer a value comes from in `--setup`.

## v3.29.28 — 2026-10-14

Pre-edit state: commit `7e4777b` (v3.29.27).

### Added

- **Universal markup in Word: centred text, highlighted text, landscape pages** (`markup: [center, highlight, landscape]`; before, a
  `.docx` kept the text and said so). Pandoc gives a style it does not find in the reference document no formatting at all and writes a raw
  section break as it was written, so the filter (`pdfmd_lua/markup.lua`) marks the text (a Div with the style `PdfmdCenter`, a Span with
  `PdfmdHighlight`, two marker paragraphs around a landscape block) and `pdfmd_office.finish_markup` finishes the file (every Word build,
  the soffice route's too): `jc center` into `PdfmdCenter` and a yellow character shading into `PdfmdHighlight` (a style of that name that
  the user's own reference document already formats is left alone; a shading, not `w:highlight`, because LibreOffice takes only that in
  a style), and the markers into section breaks that carry the document's own last section: its paper size and margins, headers and
  footers, the block's turned. A block at the very start or the very end of the document, and two blocks in a row, make no empty page; the
  title page's own first page stays the first page's. OpenDocument and PowerPoint still keep the text, with the note once. Tests
  (`tests/test_markup_word.py`): the section arithmetic on synthetic XML, and a real build drawn by LibreOffice whose pages are
  portrait, landscape, portrait, all A4, with Pandoc 3.12 and 3.1.3. Not done: `keep` in Word (no keep-together for a run of blocks
  without a style per block), centring, highlight and landscape in OpenDocument.

## v3.29.27 — 2026-10-14

Pre-edit state: commit `a2c1509` (v3.29.26).

### Fixed

- **The Calibre workflow, a look at its one failure.** The first run with valid YAML (the CI of v3.29.24) passed everything on macOS and
  on Linux but one test: `test_a_document` finds no PDF bookmarks in what Calibre wrote on Linux (it finds both headings on macOS, with
  Pandoc 3.12 and with 3.1.3, so it is not the Pandoc the Linux runner installs). Nothing in pdfmd changed: the workflow gets a step
  that builds a small page with the installed Calibre and prints Calibre's own `-vv` output, the page count and the bookmarks, so
  the next run says where they go. It never fails the run.

## v3.29.26 — 2026-10-14

Pre-edit state: commit `ce218e3` (v3.29.25).

### Added

- **`pdfmd --doc`** (queue item 6, a first version): the documents of the pdfmd in hand, offline. `README.md`, `CHANGELOG.md`,
  `docs/recipes.md` and a new short **agent guide** (`docs/agents.md`: the ten commands that matter, how to read the output lines and
  the exit codes, running without a person, what to do when a build fails) are copied into a `pdfmd_docs` package by the build
  (`setup.py`, `MANIFEST.in` for the sdist: nothing is duplicated in git; a checkout reads the originals). `--doc` lists them with their
  size; `--doc NAME` shows one (a web page made by Pandoc once per version and opened, or the Markdown when the output is not a
  terminal, with `--print`, or with `PDFMD_NO_PROMPT`); `--doc NAME SECTION` a part (a number counts the `##` headings, else a word of the
  title; the part runs to the next heading of its level); `--doc search WORD ...` the lines that have every word, with their heading path;
  `--path`. Tests: every `--flag` of the agent guide exists in `--help all` and every `pdfmd ...` command in it parses (`tests/test_doc.py`);
  the build copy is tested with `setup.py build_py`. Not done: `--online`, a PDF of a document (use `pdfmd --doc readme --print | pdfmd`
  by hand), render-safe copies (the README page links its remote badges as they are),
  the `--help` footer pointing here, a check that every flag of `--help all` is in the README.

## v3.29.25 — 2026-10-14

Pre-edit state: commit `e4a8d53` (v3.29.24).

### Added

- **Universal markup, the ninth kind: `space`** (the last candidate of the plan's list that has a plain spelling). `\vspace{1cm}`,
  `\vspace*{..}`, `\smallskip` / `\medskip` / `\bigskip` (3, 6, 12 pt), one or more `<br>` alone on a line (a paragraph of raw inlines:
  an em each) and a raw `#v(1cm)` on a line of their own become LaTeX `\vspace{..}`, Typst `#v(..)`, an HTML/EPUB empty div of that
  height, about one empty paragraph per 12 pt in Word and OpenDocument; the Markdown family keeps them. Opt-in with the rest of
  `markup`. `tests/test_markup_space.py` (Pandoc 3.12 and 3.1.3).

## v3.29.24 — 2026-10-14

Pre-edit state: commit `231dc98` (v3.29.23).

### Fixed

- **CI of the 3.29.15 push failed on Windows (3.10)** in `test_images.Remote.test_an_old_copy_is_fetched_again_and_kept_if_that_fails`
  (no release came of it: 3.29.8 is the last on PyPI): a remote picture fetched with `max_age_days=0` was "less than 0 days old" when
  the file's modification time was a few milliseconds ahead of `time.time()`, which Windows' clocks allow, so the second fetch used the
  copy. An age of 0 (or less) now means "always fetch again" (`pdfmd_images/remote.py`), whatever the clocks say; the default 7 days is
  untouched. The same push's Calibre workflow did not run (the YAML of 3.29.22).

## v3.29.23 — 2026-10-14

Pre-edit state: commit `6719049` (v3.29.22).

### Added

- **Spreadsheets in the `.csv` block** (queue item 5c): `::: {.csv file="results.xlsx" sheet="Run 2"}` for `.xlsx`, `.xlsm`, `.xls`, `.ods`.
  `pdfmd_tables/sheets.py` reads the sheet (a name, or a number from 1; the first by default) with the first of openpyxl (xlsx, xlsm;
  stored values, not display formats; dates as ISO, whole floats as integers), pandas (also xls and ods) and LibreOffice (the sheet by
  number), and says what to install when none can. pdfmd writes each sheet once as a CSV in the cache (named by the file's content and the
  sheet) and gives the filter the map (`pdfmd-sheet-map`, a `--metadata-file`, as for converted images: `spreadsheet_args` inside
  `csv_table_filter_args`); `csv_table.lua` reads the converted file; `pdfmd --expand-tables` reads a sheet through the same function.
  Pandoc's own xlsx reader (3.12 has one, 3.1.3 not) is not used: it gives a table, not the CSV the block's options (delimiter, cut,
  align) are about. All three were run here (LibreOffice through its app bundle: sheet 1 and sheet 2 of a two-sheet file). `tests/test_spreadsheets.py`.

## v3.29.22 — 2026-10-14

Pre-edit state: commit `171af5d` (v3.29.21).

### Fixed

- `.github/workflows/calibre.yml` was not valid YAML since 3.29.12: the name of the new Pandoc step had a colon followed by a space
  ("... copy: the no-Pandoc tests ..."), so GitHub ran nothing ("a workflow file issue") on the 3.29.15 push. The name has none now,
  and every workflow file was read with a YAML parser before this commit (they should be, before each one).

## v3.29.21 — 2026-10-14

Pre-edit state: commit `5b521b0` (v3.29.20).

### Added

- **`show-comments`** (queue item 5d; the author, 2026-10-10: "`--show-comments`, a `--setup` row and `pdfmd-options: show-comments`; OFF by
  default"). An HTML comment, invisible until now, is shown (`pdfmd_lua/markup.lua`, kind `comments`, which no `markup:` list names and
  `markup: true` does not turn on): LaTeX, Typst, HTML and EPUB a box labelled Comment (the callout machinery, in a grey: the
  header file defines the box once for both kinds), docx a **real Word comment** (`comment-start` / `comment-end` spans, anchored on
  the paragraph after the comment; Pandoc 3.12 and 3.1.3 both write `word/comments.xml`), an inline comment `[comment: ...]` in
  italics; the Markdown family keeps the comment; OpenDocument and PowerPoint drop it with a note once. Left invisible: `<!-- pdfmd:
  ... -->`, `<!-- pdfmd-... -->`, the page-break words, `toc`, `appendix`, an empty comment. `--show-comments` / `--no-show-comments`,
  `pdfmd-options.show-comments`, a `--setup` row under *Universal markup*, inventory and help entries. The author's open
  questions were decided as the defaults above (a box, real Word comments): say if the look should differ. Not done: ODT annotations
  (Pandoc writes none), the built-in renderer. `tests/test_show_comments.py` (Pandoc 3.12 and 3.1.3).

## v3.29.20 — 2026-10-14

Pre-edit state: commit `4aa8c25` (v3.29.19).

### Added

- **Universal markup, the eighth kind: `appendix`**. A raw `\appendix`, `<!-- appendix -->` or a heading with the class `.appendix`
  (the start itself) makes the sections after it lettered: LaTeX `\appendix` once, Typst `#set heading(numbering: "A.1")` and a counter
  reset (only when the build numbers its sections: `PANDOC_WRITER_OPTIONS.number_sections`); other writers keep their numbering with a
  note once when numbered. Opt-in with the rest of `markup`. `tests/test_markup_appendix.py` (Pandoc 3.12 and 3.1.3). That is
  eight of the nine kinds of the plan's list (toc, callouts, appendix, centring, highlight, keep-together, landscape; and
  vertical space): not done, vertical space (`\vspace`, `\bigskip`, `<br>`), and the native renderers' own reading of any kind.

## v3.29.19 — 2026-10-14

Pre-edit state: commit `bcf99ef` (v3.29.18).

### Added

- **Universal markup, the seventh kind: `landscape`**. `::: landscape`, `<div style="page: landscape">` and, for writers other than
  LaTeX, a raw `\begin{landscape}` ... `\end{landscape}` become LaTeX's `landscape` environment (the header file loads `pdflscape`,
  else `lscape`, else an empty environment; checked: the PDF's page has `Rotate 90`), Typst's `#page(flipped: true)[...]`, and for HTML
  engines a named page: `@page landscape { size: landscape }` and the rest of the document `@page pdfmd-normal {}` with
  `body { page: pdfmd-normal }`, because WeasyPrint stays on the landscape page after it unless the portrait pages have a name too
  (found on a hand-made page: 2 pages instead of 3). The browser route adds the document's own paper turned (`@page landscape { size:
  H W !important }` in `browser_page_css`): without it Edge printed Letter landscape on an A4 document. Calibre's PDF cannot name
  page types (its whole document turned landscape): `-M pdfmd-no-named-pages=1` on its HTML makes the filter keep the text with a note.
  Word and OpenDocument keep the text with a note. Opt-in with the rest of `markup`. `tests/test_markup_landscape.py` (Pandoc
  3.12 and 3.1.3; a WeasyPrint build checks portrait, landscape, portrait).

## v3.29.18 — 2026-10-14

Pre-edit state: commit `06b727d` (v3.29.17).

### Added

- **Universal markup, the sixth kind: `keep`**. `::: keep` (also `nobreak`, `keep-together`), a `<div style="break-inside: avoid">` and a
  raw `\begin{samepage}` ... `\end{samepage}` become LaTeX's `samepage`, Typst's `#block(breakable: false)[...]`, an HTML/EPUB
  `break-inside: avoid` div; Word and OpenDocument keep the text with one note. The raw TeX environments the reader keeps as one block
  (for `center` too) are now read by one function (`tex_environments`), for the kinds that are on. Opt-in with the rest of `markup`.
  `tests/test_markup_keep.py` (Pandoc 3.12 and 3.1.3).

## v3.29.17 — 2026-10-14

Pre-edit state: commit `5f4f3e4` (v3.29.16).

### Added

- **Universal markup, the fifth kind: `highlight`**. `==text==` (Pandoc splits `==a b==` into `==a`, a space, `b==`: the run is put
  together across words, emphasis, links and soft breaks; a closing `==` may be followed by punctuation; a lone `==` and code are
  untouched) and, with Pandoc 3.12's `+mark`, a `Span.mark` become LaTeX `\pdfmdhl{...}` (soul's `\hl` with a pale yellow, in the one
  header file of pdfmd's own that now holds every kind's LaTeX definitions: `MARKUP_HEADERS`), Typst `#highlight[...]`, `<mark>` for
  HTML, EPUB, gfm and commonmark; Pandoc's Markdown keeps `==...==`; Word and OpenDocument keep the text and say once that it is not
  highlighted. Opt-in with the rest of `markup`. Not done: a Word highlight (a run property: needs the office route), a colour.
  `tests/test_markup_highlight.py` (Pandoc 3.12 and 3.1.3).

## v3.29.16 — 2026-10-14

Pre-edit state: commit `6569136` (v3.29.15).

### Added

- **Universal markup, the fourth kind: `center`**. `<center>` ... `</center>` (a raw HTML pair around blocks), `<div align="center">`,
  `<div style="text-align: center">`, a fenced `::: center` (also `centered`, `centering`) and, for writers other than LaTeX, a raw
  `\begin{center}` ... `\end{center}` (which the reader keeps as one raw block: its text is read as Markdown) become LaTeX's `center`
  environment, Typst's `#align(center)[...]`, an HTML/EPUB `text-align: center` div; Word and OpenDocument keep the text and say once
  that centring is not applied. Opt-in with the rest of `markup`. Not done: an inline `<center>x</center>` in a paragraph, a Word
  centring style. `tests/test_markup_center.py` (Pandoc 3.12 and 3.1.3).

## v3.29.15 — 2026-10-14

Pre-edit state: commit `e2594ab` (v3.29.14).

### Fixed

- `tests/test_install_calibre.py` counted every mounted `pdfmd-calibre-dmg` image to prove the test's own had been detached; two test
  runs at once (the two Pandoc suites and the Pandoc-off run share the machine) counted each other's. It now looks for its own
  image's path in `hdiutil info`. (Found by the 3.29.11 verification run: one failure in 1375.)

## v3.29.14 — 2026-10-14

Pre-edit state: commit `0e51139` (v3.29.13).

### Added

- **Universal markup, the third kind: `toc`**. A paragraph that is `[TOC]`, `[toc]`, `[[TOC]]` or `[[_TOC_]]` (which Pandoc reads as
  `[[`, an emphasis, `]]`: matched on its text), `<!-- toc -->`, or a raw `\tableofcontents` for a writer that is not LaTeX, becomes the
  table of contents in that place (`pdfmd_lua/markup.lua`): LaTeX `\tableofcontents` (a raw one is left as it is: Pandoc reruns LaTeX
  and the contents are filled on the cache route and on `--no-cache`, tested), Typst `#outline()`, Word a TOC field (`w:dirty`: Word offers
  to update it), every other writer a nested list of links to the headings to level 3 under a bold "Contents". Opt-in with the rest of
  `markup` (`markup: [callouts, toc]`, `true`, `--markup toc`). Not done: a depth or title of its own, OpenDocument's own field.
  `tests/test_markup_toc.py` (Pandoc 3.12 and 3.1.3).

## v3.29.13 — 2026-10-14

Pre-edit state: commit `fec4094` (v3.29.12).

### Added

- **Universal markup, the second kind: callouts** (queue item 5b; page breaks, `pagebreak.lua`, were the first). GitHub's and Obsidian's
  `> [!NOTE]` / `> [!warning] Title` / `> [!tip]-`, a fenced `::: note` (or `{.warning title="..."}`), and Quarto's `::: callout-tip`
  with its first heading as the title become each writer's own box (`pdfmd_lua/markup.lua`, one filter for every kind to come):
  LaTeX the `pdfmdcallout` environment (a `tcolorbox` with the kind's colour, else an indented quote; **defined in a header file of
  pdfmd's own** (`markup_header_args`), because a filter's `header-includes` are dropped by pdfmd's other header files: the cover
  bug of 3.29.9), Typst a tinted block, HTML/EPUB `div.callout.callout-KIND` with a `<style>` in `include-before`, every other writer
  a block quote with a bold title. Five kinds as GitHub has them; Obsidian's other names map to them; an unknown name is a note titled
  with it. Opt-in like page breaks: `pdfmd-options.markup` (true, `all`, or a list of kinds), `--markup [KIND ...]`, `--no-markup`, a
  `--setup` row under *Universal markup*, the inventory and help entries. Spellings were taken from `pandoc -t native` on 3.12 and
  3.1.3 (identical; the `alerts` and `mark` extensions of 3.12 are off by default and 3.1.3 has neither, so the marker is read from the
  block quote, and a Div with the class works as it is). Not done: the built-in renderer (no Pandoc), a Word shaded box. Next kinds
  (each its own commit): a table of contents where `[TOC]` / `[[_TOC_]]` / `<!-- toc -->` / `\tableofcontents` stands, centring,
  `==highlight==`, keep-together, appendix, landscape. `tests/test_markup_callouts.py`.

## v3.29.12 — 2026-10-14

Pre-edit state: commit `80d5388` (v3.29.11).

### Fixed

- **The Calibre workflow's first run on GitHub** (`.github/workflows/calibre.yml`, run on 3.29.8): `pdfmd --install calibre` worked on
  both runners (Linux: the archive unpacked and `ebook-convert` found in pdfmd's data folder; macOS: the disk image), and the Calibre
  test modules ran against the real thing, which found two things in the tests, not the product. `test_calibre.Finding.test_not_installed`
  assumed no Calibre in pdfmd's own folder (it now points `XDG_DATA_HOME` at an empty one). And the no-Pandoc tests (empty `PATH`) met
  a Pandoc anyway: `pdfmd --install pandoc` puts one in pdfmd's own tools folder, which pdfmd adds to `PATH` itself, so the workflow
  now installs Pandoc with apt / Homebrew, where an empty `PATH` hides it.

## v3.29.11 — 2026-10-14

Pre-edit state: commit `7c0a5c9` (v3.29.10).

### Fixed

- **A picture cover vanished from a LaTeX document with code** (3.29.9): the filter put it in the metadata's `header-includes`, which
  every `--include-in-header` file of pdfmd's own (the code header, the packages, a house preamble) replaces; only a document's
  own survive that. The picture now goes in a header file of pdfmd's own (`cover_header_args`, beside `css_heading_args`), and the
  HTML page break of `cover: true` is a `<style>` in `include-before`, which a `-H` of your own does not replace. Tests build both
  with a code block and with `-H` (they would have passed on the broken code with a plain document: the advisor's catch).
- **Folder settings** (3.29.10): a `.pdfmd/config.yaml` owned by another user is not read (the walk reaches a shared `/tmp`, whose
  folder another user may have written); a WARN says so. The comment on what a folder's options may name was wrong in its claim of
  a trust path: no key read from a folder names a Lua filter or a preamble (those are read from the document's own front matter
  only), so there is none to route; the comment and the README say that, and that a path in a folder's options is relative to the
  document, not to the folder file. A search of the author's home and `~/dev` (four levels) found no `.pdfmd` folder.

## v3.29.10 — 2026-10-14

Pre-edit state: commit `34808ef` (v3.29.9).

### Added

- **Folder settings** (queue item 4, the first part): `.pdfmd/config.yaml` in the document's folder or any folder above it holds
  the same `options:` as the global config, for everything under it (`folder_layer_files`, `option_sources`). The layer order, the
  author's of 2026-10-10: command line, document `pdfmd-options`, metadata files, **folder settings (nearest first)**, global config,
  built-in. `inherit: false` ends the walk upward; `translit`, `setup-ui` and `disabled` are the machine's and a folder that sets
  them gets a WARN (once per file) and is ignored for them; a `stamp:` or `backup:` mapping without `enabled` stays off, as in the
  global file (`is_setup_layer`). A build reports the files on its `FOUND` line (`AUTO SETTINGS`). Not done yet: `pdfmd --setup DIR`
  writing the file, the source of each value shown in `--setup` / `--show-config`, carrying the layers in an attached source,
  a bundle or `--embed-metadata` (a PDF rebuilt from its attached source does not see the folder file), and the per-install
  layer. `tests/test_folder_settings.py`.

## v3.29.9 — 2026-10-14

Pre-edit state: commit `f04a106` (v3.29.8).

### Added

- **`pdfmd-options: cover`** (the `cover` key of the Calibre line's plan, in a smaller form than planned). `cover: true` makes the
  title block a page of its own: LaTeX gets `classoption: titlepage` (only for article, report, book and KOMA's classes), an
  HTML-family PDF (WeasyPrint, a browser, Calibre) or an HTML page a page break after `#title-block-header`. `cover: picture.png`
  (relative to the document) is the first page of a LaTeX or HTML-family PDF (LaTeX: at the start of the document, before
  `\maketitle`, which Pandoc's `include-before` comes after) and the cover of an EPUB, so of a Kindle book made from it. One
  filter for all of them, `pdfmd_lua/cover.lua`, called beside the title filter at every build site (`cover_filter_args`); Word,
  OpenDocument, Typst and the rest get one `NOTE` that it was not applied (not done: a Word title page, a Typst one). A
  picture that is not there is a WARN and no cover. Off by default; the `pdfmd_setup` inventory lists it as per-document.
  `tests/test_cover.py`.

## v3.29.8 — 2026-10-14

Pre-edit state: commit `9503d07` (v3.29.7).

### Added

- **CSS, the second round** (queue: "headings in LaTeX, guarded" and "`@media print` with css too", the author, 2026-10-13).
  *Media queries* (`pdfmd_css.applies`): read as a browser prints: `print` and `all` apply, `screen` and the other media types do not,
  a comma is "or", `only X` is X, `not X` its opposite, `(orientation: landscape|portrait)` is read against the sheet's own `@page`
  size, `(color)` is true, and a feature of the screen or of a width (`(min-width: 600px)`, `prefers-color-scheme`) is not for a
  printed page: the rule is dropped and the `CSS` note says which condition. *Headings*: `h1`-`h5` (and comma lists of them)
  with `color` (a hex or one of 40 CSS names, as an HTML colour: CSS's `green` is not xcolor's), `font-size` (`em`/`%` of the body's
  size, or a length), `font-family` (fontspec engines), `font-weight`, `font-style` are set for LaTeX with `css-scope: all`
  as titlesec's starred formats (`\titleformat*{\section}{...}`: numbering and spacing stay the class's), in a header file
  that comes last (`css_heading_args`, beside `tex_package_args` at the three build sites). Guarded: only the plain article class
  (`documentclass:` anything else is a `CSS` note), and never over a document that formats its headings itself (titlesec, sectsty,
  KOMA, memoir, `\titleformat`, `\section` redefined ... in a preamble, `header-includes` or metadata file: named, nothing added);
  without titlesec installed one LaTeX warning says so. `h6` and the other properties are named as not used. Word and Typst
  headings are still not translated. `tests/test_css_v2.py` (and `test_css.py`: headings are collected, no longer "ignored").

## v3.29.7 — 2026-10-14

Pre-edit state: commit `3a1d68f` (v3.29.6).

### Added

- **`pdfmd --install core:tex`** (also `cortex`): the other core, **Pandoc and Tectonic** (the author's request, 2026-10-14: "it is
  currently pandoc+typst, but pandoc+tectonic is a good alternative"). Pandoc is the real binary from PyPI as for `--install
  pandoc`; Tectonic is the release file for the machine (`tectonic_asset_pattern`: macOS, Linux musl x86-64/ARM, Windows x86-64),
  checked against the SHA-256 GitHub lists (nothing is downloaded without one), its `tectonic` placed in pdfmd's tools folder
  (`install_tectonic`) and run once to check; it fetches the TeX files a document needs from the network the first time. `core:typst`
  and `core` alone are `--install full` (Pandoc and Typst), so the two cores have one spelling. The versioned-file lookup is
  `release_asset_matching` (Calibre's is built on it). Tested for real on macOS (the 22 MB download, the check, the run);
  Linux and Windows files are chosen by name only. `tests/test_install_core_tex.py`; the `install-tools` CI job also installs
  Tectonic on the three systems.

## v3.29.6 — 2026-10-14

Pre-edit state: commit `7927841` (v3.29.5).

### Added

- **`pan-tec` command** (the author's request, 2026-10-14): the first version of pdfmd, v0.1.0's shell function `pandoc "$@"
  --pdf-engine=tectonic --pdf-engine-opt=--chatter=minimal`, as a command name beside `mdpdf`, `inkmd` and `batchmd`.
  `pan-tec test.md -o ex.pdf` runs pdfmd with `-e tectonic` and `--pdf-engine-opt=--chatter=minimal` added (`pan_tec_translate`,
  `pan_tec_main`, a script in `pyproject.toml`); an engine or a chatter level on the command line is used instead; a Tectonic that is
  not installed gets pdfmd's own "engine not found" message. Not done: the other half of the request, a Pandoc + Tectonic
  core install (`pdfmd --install core:tex`), which is queued. `tests/test_pan_tec.py`.

## v3.29.5 — 2026-10-14

Pre-edit state: commit `e2df84f` (v3.29.4).

### Added

- **`pdfmd --doctor --deep` tries the last resorts** (queue item G): each installed browser and Calibre build the small page
  (`edge: built a PDF in 6.1 s`), and with Calibre an ebook is written and checked (`calibre:azw3: built an AZW3 ebook in
  18.0 s`; `deep_checks` takes `engine:format` entries). A missing Qt library or a broken install shows there.
  `tests/test_doctor.py`.
- **A CI workflow with a real Calibre** (`.github/workflows/calibre.yml`, apart from the gating `test.yml` so that a Calibre
  release or a runner library cannot stop a PyPI release): on Linux and macOS it runs `pdfmd --install calibre` (the archive
  unpacked, the disk image mounted: the paths the unit tests only imitate), then the Calibre test modules against the real
  `ebook-convert`, then builds a PDF and an AZW3 and reads the AZW3 back. On pushes that touch the Calibre code or tests, weekly
  (Monday 04:17 UTC) and on request. Not run yet: its first run is on GitHub.

## v3.29.4 — 2026-10-14

Pre-edit state: commit `12c3aab` (v3.29.3).

### Added

- **`pdfmd --install calibre`** (queue item F). In a terminal on macOS with Homebrew or on Windows with winget it offers `brew
  install --cask calibre` / `winget install --id calibre.calibre -e` first (`[Y/n/d]`: `d` downloads it instead; the package
  manager is never run unasked, and not at all with `PDFMD_NO_PROMPT` or without a terminal). Otherwise it downloads Calibre's
  release file for the machine (`calibre_asset_pattern`: `calibre-X.Y.Z.dmg` on macOS, `-x86_64.txz` / `-arm64.txz` on Linux;
  the names carry the version, so they are matched by pattern) and checks it against the SHA-256 GitHub's API lists for it; with
  no digest listed (offline, a rate limit) nothing is downloaded unchecked. macOS: `hdiutil attach -nobrowse -readonly` on a
  scratch mount point, `ditto` of `calibre.app` into `~/Applications` (never `/Applications`; `resolve_calibre` already
  looks there), detached again in a `finally`. Linux: the archive (checked member by member to stay inside the folder, links
  included: `safe_unpack_tar`) goes to `data_root()/calibre/<version>`, which `resolve_calibre` now searches (`calibre_own_folders`,
  newest first); no `calibre_postinstall` (it writes desktop files and may want root). Either way `ebook-convert --version` runs
  to check. Windows is not unpacked (the installer wants admin rights; the MSI route was not tried): winget or calibre-ebook.com.
  An installed Calibre is left alone (`OK    Calibre is already installed`). Calibre is GPLv3 and is run, never bundled. The
  messages that say Calibre was not found, and `--doctor`, name the command. Not tested on this machine: the Linux archive
  (its listing was read: `ebook-convert` is at the top of it; the unpack is tested with a small stand-in) and Windows.
  `tests/test_install_calibre.py` (a fake release listing; a stand-in `.txz`; on macOS a real disk image made with `hdiutil
  create` holding a stand-in `calibre.app`).

## v3.29.3 — 2026-10-14

Pre-edit state: commit `c34dc91` (v3.29.2).

### Fixed

- **A Calibre ebook with Pandoc 3.1 keeps its math as MathML** (the 3.1.3 suite of v3.29.0 failed three tests). Pandoc 3.1
  writes an EPUB's formulas as plain text unless `--mathml` is given (newer Pandoc defaults to MathML); a Calibre job whose
  target keeps MathML (`epub` through `-e calibre`, `htmlz`) now asks for it unless a math option of yours is on the command
  line (`start_calibre_job`). `pdfmd_lua/ebook_input.lua` recognises Pandoc 3.1's `#ch002.xhtml#id` link form when it keeps the
  anchors a link points at. The tests accept the `.svgz` pictures Pandoc 3.1 writes and its missing-title note.

## v3.29.2 — 2026-10-14

Pre-edit state: commit `934899f` (v3.29.1).

### Fixed

- **An ebook read as Markdown loses Calibre's scaffolding and keeps its pictures** (the advisor's check of 3.29.1). Calibre's
  EPUB carries an empty anchor for every file it split the book into (`[]{#index_split_001.html}`), page-break divs and a class
  on every span (`.calibre1`); `pdfmd_lua/ebook_input.lua` drops what is empty and not the target of a link, and the converter's
  classes (`calibre*`, `mbp_*`, `pagebreak*`); words, headings, lists, tables, pictures and links are not touched. And
  `pdfmd book.mobi -o book.md` wrote `![](media/images/00001.jpg)` with the pictures deleted along with the scratch folder: the
  `media/` folder is now copied beside a kept Markdown (`.md`, `.markdown`), never over a file already there. (Before 3.29.1 an
  ebook given to pdfmd stopped with a UnicodeDecodeError: nothing regressed.) `tests/test_ebook_input.py` (a book with a
  picture, an anchor nothing links to and one a link points at).

## v3.29.1 — 2026-10-14

Pre-edit state: commit `8f5d4a1` (v3.29.0).

### Changed

- **The browsers and Calibre are last resorts of the automatic chain** (the author, 2026-10-13: wire them in once they work;
  v3.29.0 made them work when named). With no `-e`, `select_engines` returns the installed numbered engines in their order
  and, ahead of LibreOffice (whose page is the least like the document's), the installed browsers (Chrome, Chromium, Edge,
  Brave) and then Calibre: a document that LaTeX, Typst and every HTML engine fail on still ends as a PDF, and the closing
  line names the engine (`OK    d.md > d.pdf  (edge; lualatex, typst failed)`). Nothing changes where none is installed
  or an engine is named; slides never use them; `-e pandoc` is still every engine Pandoc drives and never these; a comma list
  names exactly what it names. `--doctor` prints `last resorts, after those: edge, calibre`. `tests/test_engine_chain.py`
  (`Automatic`), `tests/test_calibre.py`.
- **With no Pandoc and Calibre installed, Calibre reads the Markdown itself** (its Python-Markdown reader: tables, footnotes,
  fenced code, lists, `extra, toc, sane_lists`), ahead of the rough built-in renderers, which stay its fallback (`NATIVE
  d.md via calibre`; `OK    d.md > d.pdf  (calibre)`). It is the native tier's engine `calibre`: the text is normalised as for
  inkmd (the front matter gone, the title and author as a heading and `--title`/`--authors`, math as plain text, footnotes as
  endnotes, Pandoc's syntax removed), the page is the document's (`papersize`, `geometry`, `margin`, `lang`: else Letter
  and 1in), and what it cannot honour is reported once each as for the others (`math expression(s) set as plain text`, `front-matter
  keys not used`). With Pandoc, `-e calibre` is the HTML route of v3.28.0, unchanged (`is_native_engine`); `-e calibre` or
  `-e native` without Pandoc picks it. `PDFMD_CALIBRE` names the `ebook-convert` file, or an empty value says there is
  none (the tests of the no-Pandoc tier set it, so a Calibre on the machine does not leak in). `tests/test_calibre_markdown.py`.
- **An ebook as input**: `pdfmd book.epub`, `book.mobi`, `.azw`, `.azw3`, `.azw4`, `.kepub`, `.lit`, `.lrf`, `.pdb`, `.prc`,
  `.chm`, `.snb`, `.tcr`, `.rb`, `.pmlz`, `.htmlz`, `.txtz` (`EBOOK_INPUT_EXTENSIONS`). An EPUB goes straight to Pandoc; the
  others through Calibre's `ebook-convert` to an EPUB first (`--no-default-epub-cover --no-svg-cover`: a book with no cover
  is not given a generated one; a book's own cover stays, it is content). Pandoc turns the EPUB into Markdown with its pictures (`--extract-media=media`) in a scratch folder
  (`route_ebook_input`, after `route_text_input` in `main`), and that Markdown is built as any file is: the output is named after the
  book beside it (`book.pdf`; `-o` and `--to` as usual), the closing line names the book (`OK    book.mobi > book.pdf  (lualatex)`:
  `DISPLAY_ALIAS` in `display_path`), and `pdfmd book.mobi -o book.md` keeps the Markdown for editing. One book at a time (not
  with other files, `-b` or `-r`); a book with no Calibre says how to install it; DRM-protected books and ebooks that are only
  pictures are not handled. A MOBI that holds its math as pictures keeps them as pictures. `tests/test_ebook_input.py`.
- Not done: the math-aware order of the 3i spec (a document with math and no MathJax or KaTeX trying a browser or Calibre
  before WeasyPrint); the chain is per run, not per document, and WeasyPrint, which prints most documents well, stays first.

## v3.29.0 — 2026-10-13

Pre-edit state: commit `561044b` (v3.28.49). The converters write what Pandoc cannot (Calibre ebooks, LibreOffice `.doc`) and a browser is a PDF engine for Markdown.

### Added

- **A browser prints a Markdown document**: `-e edge`, `-e chrome`, `-e chromium`, `-e brave`, or the family word `-e browser` (the
  installed ones in that order; aliases `msedge`, `microsoft-edge`, `google-chrome`, `brave-browser`). Pandoc writes the same
  one self-contained HTML page the Calibre route does (MathML, which a browser draws itself, the same filters, citations,
  fonts, and the LaTeX filter of the Word route for LaTeX the page would drop) and `pdfmd_direct`'s headless browser prints it
  with the paper and margins the document asks for as `@page` (`papersize`, `geometry`, `margin`, `classoption`, read as for a
  Word file; else Letter and 1in) and Pandoc's screen style undone (the column, the padding, the grey page, narrow tables).
  Named, a browser is tried first (v3.29.1 makes it and Calibre last resorts of the automatic chain); usable in a chain (`-e typst,edge`) and as
  `pdf-engine: edge`. Before, `-e edge` on a `.md` was refused (only a `.html` file went to a browser). On a Mac Edge's printing
  looked right on the math test page (accents, limits, matrices) with no correction of its own.
- **LibreOffice writes `.doc`** (and, with `-e soffice` first on the command line, `rtf`, `odt`, `txt` and `epub`). `pdfmd letter.md -o
  letter.doc` has Pandoc write the Word file (the one `-o letter.docx` writes: reference document, native equations and tables,
  pictures for what LaTeX alone can draw) into a scratch folder and headless LibreOffice convert it (Word 97 is a format
  Pandoc does not write). A format Pandoc writes itself goes through LibreOffice only when asked, with a NOTE; a
  `pdf-engine: soffice` in front matter or the config is a PDF setting. `-e soffice` with a target it does not write (`.tex`)
  stops and lists what it does. One document at a time (`-b`, `-r`, `-p` stop with that said); no LibreOffice: the error says
  where it was looked for and how to install it. `run_soffice_convert` takes the target; the job, its checks and its closing
  line are the Calibre ones' (`finish_convert_job`).
- **Calibre writes ebooks** (the author: start the Calibre line, one `+0.0.1` per item after this). `pdfmd book.md -o book.azw3`
  or `--to azw3` has Pandoc write an EPUB 3 into a scratch folder (chapters, contents, the metadata, the math as MathML; the
  same filters, citations and fonts as any EPUB) and `ebook-convert` turn it into the target, `book.azw3` beside the document
  (`-o` names it, or a folder; no suffix gets the format's). Twelve targets only Calibre writes: `azw3`, `mobi`, `kepub`,
  `lit`, `lrf`, `pdb`, `rb`, `snb`, `tcr`, `pmlz`, `htmlz`, `txtz`. Each was converted back to text with ebook-convert 9.14 and
  the heading, the words, the list and the table were there. `-o file.EXT` knows them all by their suffix.
- **`-e calibre` for a target Pandoc writes too**: `epub`, `docx`, `rtf`, `txt`, `fb2` are Calibre's only when `-e calibre` (or
  `-e ebook-convert,...`: Calibre first) is on the **command line**, with a NOTE that Pandoc's own route has more of the
  format's features; a `pdf-engine: calibre` in front matter or the config is a PDF setting and does not move a docx to Calibre.
  `-e calibre` with a target it cannot write (`.tex`, `.html`, `.md`) stops and lists what Calibre writes. A target only
  Calibre writes with another engine named prints `WARN  --engine is ignored for --to azw3: Calibre writes it`.
- **Math in an ebook.** The EPUB has the formulas as MathML, which a Kindle or a Kobo does not draw and a MOBI, a Palm book
  or an RTF file has no place for (a MOBI made from it simply lost them: "Inline  and water ."). So the targets that can
  show pictures (`azw3`, `mobi`, `kepub`, `lit`, `lrf`, and `docx` through Calibre) get each formula drawn by LaTeX as a
  picture, in the document's own preamble, by the route of a Word file (`latex: images`, cached; `\ce` and siunitx converted);
  the picture keeps `LaTeX: x^2` as its description and the tooltip that named a folder of this machine's cache is dropped
  (`pdfmd_lua/ebook.lua`). The plain formats (`pdb`, `rb`, `snb`, `tcr`, `pmlz`, `txtz`, and `rtf`, `txt`, `fb2` through
  Calibre) get the formulas as text, the simple ones with their superscripts and the rest as TeX, with one WARN that counts
  them; so does a picture target when there is no LaTeX engine or no `pdftocairo` (the WARN says why). `epub` and `htmlz`
  keep the MathML. A math option of your own (`--mathml`, `--math-method=...`) is kept as it is.
- One document at a time: `-b`, `-r` and `-p` with such a target stop with that said. No Calibre: the error names the target,
  where `ebook-convert` is looked for and how to install Calibre. `--doctor` says which formats need it.

### Fixed

- **`-o book.azw3` (any suffix pdfmd did not know) wrote a PDF under that name**; the same for `.mobi`, `.kepub` and the
  rest. A suffix that is none of pdfmd's formats still does what it did (a PDF), except these twelve.

### Not done (the next items of the Calibre line)

- Calibre and the browsers in the automatic chain, direct `.md` through Calibre,
  ebooks as input, `pdfmd --install calibre`.
- A batch or a report to ebooks.

Tests: `tests/test_browser_engine.py` (selection, the page as CSS, a build with a stand-in browser that writes a PDF and logs the page it
was given); `tests/test_calibre_targets.py` (the decisions, the job, a build with a stand-in for `ebook-convert` that copies the EPUB
it is given, `ebook.lua` through Pandoc, and a real Calibre where there is one: `BOOKMOBI` at byte 60 of an AZW3 and a MOBI).

## v3.28.49 — 2026-10-13

Pre-edit state: commit `1f5c789` (v3.28.48).

### Fixed

- **CI's native job failed on 20 tests that run a Pandoc build** (the job has no Pandoc by design): `test_autolog.Builds`,
  `test_bopen.Batch`, `test_rawcode.Builds` and six of `test_presets.Presets` were written without the skip that every
  other module with a Pandoc build has. They are skipped now when `pandoc` is not on PATH; nothing else changed. The first push of
  3.28.48 therefore published nothing (the tests gate the release).

## v3.28.48 — 2026-10-13

Pre-edit state: commit `cd2c629` (v3.28.47).

### Changed

- **MathJax: only the STIX Two math font is offered.** v3.28.46 also let `math:mathjax:newcm,termes,pagella,dejavu` add the
  math fonts of other body fonts. Checked before anything was published, with the five fonts side by side against Chromium on
  the 36 shapes: the margin that undoes WeasyPrint's misplacing is each font's ascent-over-descent excess plus 0.03em (STIX
  Two 0.262 -> 0.29em; New Computer Modern 0.306, Termes 0.282, Pagella 0.226, DejaVu 0.292), and with it every shape but one is
  within 0.5 pt in all five. The one is a tall delimiter built from pieces (`\left[` over a three-row matrix): its bracket
  breaks in WeasyPrint in the other four fonts (a gap in the middle; up to 7 pt off) while STIX Two Math draws it from a
  single glyph. So `pdfmd --install math:mathjax` fetches MathJax and STIX Two Math only (12 MB), a body font that is not STIX
  Two Text gets it sized to its x-height, and a font is one row of three tables when its brackets are fixed.
- The `overflow: hidden` on `mjx-stretchy-v` is gone (it did nothing in STIX Two and was one cause of the gap); the one on
  `mjx-stretchy-h` stays (an `\overline` or an arrow ran past its width without it).

### Checked

- Accents against LaTeX (STIX Two Math, 11 pt) after the fix: `\hat` +0.4, `\bar` 0.0, `\tilde` +0.2, `\vec` -0.2,
  `\dot` -0.1 pt (before: +3.0 to +3.6 pt).

## v3.28.47 — 2026-10-13

Pre-edit state: commit `9f624a5` (v3.28.46).

### Changed

- **README brought up to date with the unpushed 3.27 and 3.28 commits** (the author: every change keeps the README current;
  PyPI shows it as the project's page). An audit of each changelog entry since v3.26.20 against the README found it already
  describing the settings menu, `--merge`, the CSV caps, the page-break kinds, the presets and the global metadata, `-e
  calibre` and the engine chain, the style sheet and `css-scope`, `--edit` of a PDF, `--bopen` with `eN` and `sN`,
  `--check-source`, the picture cache, `--install diagram`, KaTeX and MathJax. What it had wrong or lacked, now in the
  attached-source section: sibling-folder text files are blocks of the source too (it said they stayed attachments), a CRLF
  file is a block with `eol: crlf` and comes back byte for byte, `--edit` writes those files where the document reads them,
  and the manifest's format number is 2, so an older pdfmd refuses a newer source instead of restoring half of it.

## v3.28.46 — 2026-10-13

Pre-edit state: commit `21cf89d` (v3.28.45).

### Added

- **MathJax 4 typesets the math of a WeasyPrint PDF** (`pdfmd --install math:mathjax[:FONT[,FONT]]`), ahead of KaTeX. The
  install fetches MathJax's npm package (7.5 MB) and the math font package that goes with pdfmd's default body font (STIX Two
  Math, 4.8 MB), each checked against its SHA-256 pinned in pdfmd (the registry's own sha512 agrees), keeps what pdfmd runs
  (about 3 MB on disk, in `data_root()/mathjax/4.1.3/node_modules/@mathjax`) and fetches node as it does for KaTeX.
  `math:mathjax:newcm,termes,pagella,dejavu` adds the fonts of the other bodies in the table of v3.28.24 (New Computer Modern,
  TeX Gyre Termes, TeX Gyre Pagella, DejaVu Serif; Libertinus has none). `pdfmd_lua/mathjax.cjs` renders every formula in one
  node call; a formula it cannot read goes to KaTeX in a second call (a NOTE says how many), and what neither reads stays
  text with one WARN. The math font is the one that goes with the body font; another body gets STIX Two Math sized to its
  x-height (`pdfmd-body-xheight`, within 0.85 and 1.4). `--no-auto mathjax` leaves the math to KaTeX or text; `--doctor` and
  `--check-dependencies` list MathJax and KaTeX. Installing into a scratch `XDG_DATA_HOME` is how the tests run it.
  `tests/test_mathjax.py` (installer, font table, variables, the filter with a stand-in for node, and a real build where
  MathJax is installed); `tests/test_engine_filters.py`'s KaTeX builds say `--no-auto mathjax`.

### Fixed

- **WeasyPrint put MathJax's stacked math too far apart.** Measured against Chromium and LaTeX (STIX Two Math, 11 pt): an
  accent (`\hat`, `\bar`, `\tilde`, `\vec`, `\dot`) floated 3.0 to 3.6 pt over its letter (0.65 to 0.75 of an x-height; the
  gap to the letter was 4 pt where LaTeX leaves 0.5 to 1.1), limits and `\overset` 1.6 pt, `\underset` and `\underbrace`
  2 to 5 pt too low, a fraction's denominator 2.2 pt too low, a root's bar 3 pt too high, and an `\overline` ran past its
  letter. Cause: MathJax sets every glyph in an inline box of no width and no content height whose font stack starts with
  a font of zero ascent and descent (so that the baseline is the box's bottom); WeasyPrint takes the line's metrics from the
  font that draws the glyph (STIX's ascent exceeds its descent by 0.262 em), so every box stood that much too tall above its
  baseline. `weasyprint.lua` adds `mjx-c { margin-top: -0.29em }` (0.28 to 0.30 matches Chromium to 0.3 pt on 36 shapes), an
  `overflow: hidden` on the stretchy bars and braces (WeasyPrint draws no `clip-path`, which cut them to their width), and 0.2em for
  `\underline`'s bar. Left: a fraction's bar is 0.7 pt low and a little thick. `tests/test_mathjax.py` fails without the rule
  (the accent is 3.9 pt off) and passes with it (0.4 pt).

## v3.28.45 — 2026-10-13

Pre-edit state: commit `b61d1ba` (v3.28.44).

### Changed

- The attached source's manifest is **format 2** (it was 1 since v3.22). v3.28.38 to v3.28.44 changed what a PDF carries (the
  chain of folders, text files as blocks of the source with line markers, `eol: crlf`, files above the document's folder) while
  the number stayed 1, so an older pdfmd restored such a PDF with warnings and half of its files. A pdfmd that reads up to 1 now
  stops with `was made by a newer pdfmd (pdfmd X, attachment format 2; this pdfmd Y reads up to 1); upgrade pdfmd to restore it`,
  and this one restores both 1 and 2 (checked both ways with a PDF made by v3.28.44 and one made now).
  `tests/test_attach_format.py`.

## v3.28.44 — 2026-10-13

Pre-edit state: commit `4fd2bf7` (v3.28.43).

### Changed

- The text files of the folders **above** the document's (`../schemes/fig.tex`, `../ir/plain/x.csv`) are blocks of the attached
  source's own text too, with the other text files after the text and with their `<!-- pdfmd-at: ... -->` line markers
  (v3.28.39 left them as attachments named `files/__up__/...`). A Pre-lab 7 PDF: 10 attachments -> 6 (the logos, the package,
  its helper, the manifest and the source), and the schemes and spectra are editable text. `--restore` puts them back
  beside the document's folder as before.
- A file with Windows line ends (CRLF all through) is held as text with an `eol: crlf` line in its block and comes back byte
  for byte; the spectra of the Pre-lab were CRLF. A file with mixed line ends is still an attachment.
- `--edit FILE.pdf` writes those files where the document reads them (in its own temporary folder) from what the file says
  before every build, so an edit of a `../schemes/fig.tex` block is the edit of the file. A TeX search does not look
  above the working folder, which is why this is written there.
- A build of a Markdown source that holds such a block, in a folder that has no such file, says so (`pdfmd --restore` or
  `--edit` puts the folders back) and writes nothing outside the document's folder; a file that is there is never replaced
  by the block.
- `--unpack` writes a `..` path as `__up__/...` under its output folder, so a sibling's file and the document's own file of
  one name no longer collide (before, any path with `..` was written by its file name alone).

### Fixed

- `--edit` of a single file wrote every `type: file` block and the citation style **twice** into the rebuilt PDF's source (the
  blocks the file held, then the ones the build made again: Pre-lab 7 grew from 6700 to 13000 lines). A file the build finds
  replaces its block, one it does not find (no copy beside the document) stays the block it is, and a style or bibliography
  embedded again keeps the first.
- The "NEEDS graphics ...: not stored" note named files the PDF did carry (a logo or package found in the document's own
  folder, as in a restored or edited source): what the attachments hold is no longer reported as missing.

## v3.28.43 — 2026-10-13

Pre-edit state: commit `118c0e7` (v3.28.42).

### Fixed

- A Word file (or any input that is not text) went through the new style-sheet search and stopped on `UnicodeDecodeError`
  (v3.28.41 read the document's front matter for `css:`); it is read only when it is text. The zipapp build script lists the
  `pdfmd_css` package too (the wheel and the zipapp ship the same packages: a test says so).

## v3.28.42 — 2026-10-13

Pre-edit state: commit `af5ef7a` (v3.28.41).

### Added

- **An ordered chain of engines** (the author approved the router's first stage). `-e typst,calibre,lualatex` tries the
  engines in the order written and nothing else; a word is an engine or its alias, a family (`tex`, `html`, `typst`: its
  installed members in their usual order, in place) or `pandoc` (every engine Pandoc drives, never Calibre). `pdf-engine:`
  and `engine:` in `pdfmd-options`, the front matter, a metadata file and the config take the same list, as a comma string
  or a YAML list. A word whose engine is not installed is passed over with a NOTE when another one of the list can run;
  the build stops only when none can ("none of it can run", with each reason). A single engine, a family and no `-e` at all
  are what they were (the default chain is unchanged: tests prove it); slides keep only the engines Beamer can use.

## v3.28.41 — 2026-10-13

Pre-edit state: commit `1d745f8` (v3.28.40).

### Added

- **A style sheet for the page** (the author approved the CSS design and asked that `css:` in the metadata or front matter
  be picked up too). `pdfmd.css` or `<name>.css` beside a document (`--no-auto css` turns it off), `css:` of the front matter
  or a metadata file (Pandoc's own key, which its HTML template already links), `pdfmd-options: {css: FILE | [..]}` (also in
  the config, `pdfmd --setup` has a row), and `--css FILE` (now an option of pdfmd's own, repeatable) are the HTML writers'
  sheets: HTML, EPUB, the HTML engines' PDF and Calibre link them, in that order.
- **`css-scope: html | all`** (`--css-scope`, `pdfmd-options.css-scope`, a `--setup` row): with `all` the part of the sheet that
  means something to LaTeX, Typst and Word is read as well (new package `pdfmd_css`, no new dependency): `@page` size
  (A4/letter ..., landscape) and margin, the body's `font-family`, `font-size` (10, 11 or 12 pt), `line-height` and
  `text-indent`, the colour of `a` (named or `#rrggbb`), the font of `code`/`pre`, as Pandoc variables **below** what the
  document, its metadata and the command line set. `@media print` counts, `@media screen` and other conditions do not; the
  last rule wins; `--verbose` says what each setting came from and names what was not used (headings, tables, the rest).
  Headings are not translated for LaTeX, whose class or package already formats them: this v1 names them.
- Checked: letter and 11 pt from a sheet in a LaTeX build, a sheet beside the document in a WeasyPrint PDF (its `@page` makes
  the paper), and a document that sets its own paper, size and margin keeps them.

## v3.28.40 — 2026-10-13

Pre-edit state: commit `fe59bbb` (v3.28.39).

### Changed

- **`--edit FILE.pdf` opens a document as one file** (the author: "edit a standalone single file by default, and use
  `--unpack`/`--restore` for delocalised editing"). The attached source, which holds the metadata, preamble, filters,
  bibliography, style and (v3.28.39) the `.tex` and CSV files as blocks of its text, is written as that one file, with fresh
  line markers, into the temporary folder; the pieces that are not text (the package, pictures, files in sibling folders) are
  beside it, as for any restore. Your editor (or the built-in one) gets the one file, each save rebuilds from it, and the
  temporary folder is removed when you leave. A book built with `-r` is still edited as its chapter files.
- **The rebuilt PDF is checked before it replaces yours.** It must carry its source (a PDF that does not is refused, yours is
  untouched) and everything the old one carried (files, text files, bibliography, style, filters, history); what is missing is
  named in a WARN. A Lua filter embedded in the source that this machine's pdfmd has not written is noted: a build skips it
  unless `--trust-embedded` is among the options you give (read it first).
- Checked on Pre-lab 7: a title edited in the one file shows in the rebuilt PDF, which carries the same ten attachments.

## v3.28.39 — 2026-10-13

Pre-edit state: commit `7e1b094` (v3.28.38).

### Changed

- **The attached source holds its text files, editable** (the author: "csvs and tex inputs: they should be editable there as
  well, close to the end ... first all embedded texs, after them csvs, and after that those things already at the end"). The
  `.tex` files a document reads (`\input`) and its CSV and other data (`.csv .tsv .dat .txt`, up to 1 MB each, UTF-8) are no
  longer separate attachments: each is a `type: file` block of the source's own text, after the text and before the
  filters, history, bibliography and style that were always at the end: `.tex` first, then the data, each group by name.
  Files with one content are one block (`also:` lists the other paths: LR6's `chemicals.tex` is linked from two folders and
  was stored twice, 76 KB each). Pictures, the package (`.sty`, logos, its helper) and files in sibling folders stay
  separate files. A restore writes the blocks back at their paths, byte for byte; a build of the source itself finds them
  (they are written to a scratch folder the engines search). LR6's attachments went from 34 to 11 files, its source from 3,900
  to 22,000 lines (the data).
- **Line markers.** Each embedded file is announced in two places by `<!-- pdfmd-at: ... -->` comments: an index after the
  front matter (front matter, preamble, each file, bibliography, style, with its line) and one line before each block of the
  text that names a file (`file="tables/x.csv"`, `\input{tex/fig}`: "tex/fig.tex @ line 241"). They are written whenever
  the source is written, so the numbers are right in every attached source, and taken out wherever one is read: a restore
  gives the original text byte for byte, a rebuild or re-attach of an edited source writes fresh ones. (An editor that has
  the file open sees the numbers of the moment it was written until the next write.)
- LR1-2, LR3, LR4-5, LR6 and Pre-lab 7 restored into an empty home folder rebuild to the same pages, and the second
  generation differs from the first only by the line numbers and the build-history line.

## v3.28.38 — 2026-10-13

Pre-edit state: commit `5dc15d5` (v3.28.37 and its test fixes).

### Fixed

- **A report rebuilds on its own from its PDF** (the author: "make the reports build on their own after embedding"). The
  acceptance test is a restore into an EMPTY home folder (no `~/Library/texmf`, no Pandoc data folder, no pdfmd config) and a
  rebuild there: Pre-lab 7 comes out identical to the pixel, and attached again keeps every file. What it took:
  - `--bundle-packages` stores the package's `<package>-pdfmd.yaml` as well (a rebuild lost the title-page keys without it).
    Its Lua filter is not stored by this: one the build applied is embedded already, and one it did not (a pre-lab) must not
    start to be applied by a rebuild.
  - The graphics a package draws are the file names that reach an `\includegraphics` through a macro
    (`\newcommand{\LogoFile}{nu-logo}`), not every braced word that was also a graphic's name: `titlepage`, `equation` and
    `sidefigure` (the manual's figures, 55 KB) had been stored with every report.
  - A package, class or `\input` that already sits in the document's own folder is kept when the source is attached again (a
    restored source lost its package the second time).
  - The package scan finds a package beside the document first, as TeX does; `office_packages` read the TeX tree only.
  - `<package>-pdfmd.yaml` and `<package>-office.yaml` beside a document are no longer taken for metadata files ("Multiple
    YAML files found").
  - A bibliography named by a symlinked metadata file is looked up in that file's real folder, as the build's
    `--resource-path` does: a pre-lab's `nulab.bib` was "not found in the document's folders", so its source carried no
    bibliography and a restored pre-lab did not build. It is pruned to the cited entries like any other (5 of 141).
  - Files in sibling folders (`\input{../schemes/x.tex}`, `../ir/x.csv`) are stored, up to two folders above the document's
    folder and never the home folder or above, as `files/__up__/schemes/x.tex` (an attachment's name must not climb);
    the manifest's `chain` says which folders the document sat in, and `--restore` / `--edit` put it back under the same
    layout (`<out>/<folder>/doc.md`, `<out>/schemes/x.tex`). Before, these were listed as "not stored, outside the
    document's folder" and the restored source could not build.
- **`--restore` gives a 1-bit picture back as it was.** A PNG that LuaTeX included sits in the PDF as its own IDAT data
  (Flate with a PNG predictor); decoding it with pypdf unfiltered a 1-bit image with a pixel of 0 bytes and wrote the picture
  back mostly black (LR1-2's four Palleros spectra, found by the empty-home rebuild: three pages differed). The same bytes
  now make the PNG again, byte for byte the data the engine had, and nothing is recompressed.
- nulabreport v1.28.7 sets `bundle-packages: true` and `attach-csl: true` (and, for pre-labs and General Chemistry reports,
  `attach-source`) in its shared metadata files: about 90 KB more a PDF (the package packs 3:1, the citation style 6:1).

## v3.28.37 — 2026-10-13

Pre-edit state: commit `0f75282` (v3.28.36).

### Changed

- **pdfmd no longer names any LaTeX package** (the author: "generally, nulabreport specific things should live in
  nulabreport's own pdfmd metadata file, so it is portable to anything"). What a package brings is found by reading the
  packages the document loads (its preamble files, its `header-includes:` and its metadata's) and the `<package>-pdfmd.yaml`
  beside each style file. Four things were written in pdfmd and are now data:
  - the title-page key table (`experiment`, `group`, `performed` ... -> `\LabExperiment` ...) was a table here; it is the
    package's `latex-keys:` only (it already could be);
  - the Lua filter: `<package>.lua` for each local package the document loads, beside the document or its metadata, and
    whatever the helper lists under `lua:`; `nulabreport.lua` was a literal name. The Word profile is
    `<package>-office.lua` of a loaded package, not `nulabreport-office.lua`;
  - what a draft pass need not draw: `chemfig` and `\schemestart...\schemestop` are two small tables
    (`DRAFT_SKIP_COMMANDS`, `DRAFT_SKIP_SPANS`) that a helper extends under `draft-skip:` (`commands:`, `spans:`), so a
    circuit package would add its own;
  - the picture cache's first names (`LabPlotCacheDir`, `.plotreq`, `Lab@pc@wd` ...) are the helper's `picture-cache:`
    (`dir`, `render`, `requests`, `wd`, `ht`, `dp`), defined and read as aliases; a helper with that block takes part in the
    cache like a style file that mentions `pdfmdCacheDir`. **A package that used its own names needs that block**: without
    it the cache is inert (nulabreport v1.28.6 has it).
- **A package loaded from `header-includes` is found.** The package scan read preamble files only, so a pre-lab (which loads
  its package from the metadata's `header-includes`) got none of the package's Word profile, Lua filter or title-page keys.
  Now it does: Pre-lab 7's Word file has the house header, title table and styles the full reports have. The `.tex` and the
  Word file of LR1-2, LR3, LR4-5 and LR6 are identical to the old code's (checked), the pre-lab's `.tex` too; a package's
  Lua filter is applied only when pdfmd can see the package is loaded (`--no-auto preamble` now drops it as well).

## v3.28.36 — 2026-10-13

Pre-edit state: commit `b4ab613` (v3.28.35).

### Changed

- **The citation style is no longer embedded in a source unless asked** (the author: "why is csl embedded at all? make it
  adjustable and off by default"). Looking at a restored PDF, the merged source was 2065 lines, 2000 of them `apa.csl`
  (86 KB), which the author's global metadata sets for every document, cited or not; the "does the document cite anything"
  test only silenced the warning for a missing style, not the embedding. `csl` is now an embed kind of its own and an
  optional one, as `files` is: `--attach-csl` / `--no-attach-csl`, `pdfmd-options: {attach-csl: true}` and a `--setup` row
  ("The citation style attached with the source", off) for an attached source, `--embed-metadata csl` or
  `embed: {csl: true}` for an assembled file, `all` includes it. Even when asked for, a style no one cites with stays out.
  What is left out is recorded (`csl_left` in the manifest) and `--restore` says so: "the citation style X is not in the
  source: a build needs a style of that name". A house style that exists only on one machine (nu-labreport.csl) should be
  carried: `attach-csl: true` in its metadata. Sizes measured: apa 86 KB, apa6 59 KB, nu-labreport 72 KB, ieee 18 KB, acs 11 KB.
  The merged text of a document with a bibliography but no style asked for is 2000 lines shorter.

## v3.28.35 — 2026-10-13

Pre-edit state: commit `4b99efb` (v3.28.34).

### Added

- **Two more markers in a request's context, found by checking the scheme cache against the author's real reports** (LR1-2 to
  LR6 and Pre-lab 7, in scratch copies; the new PDF has to be the old one). Building LR1-2 with schemes cached showed two faults
  that no synthetic test had: the whole page below the scheme sat a fraction of a point lower, and a raised label (the H of
  `\chemabove{N}{H}`) was cut off at the top of its picture. The causes are general:
  - **ink outside the box.** A picture's box is not always its ink. `@@margin=56pt@@` makes the standalone page the box plus
    that on every side, writes `\pdfmdCacheMargin` to the `.dim`, and the package includes the page shifted back by the margin,
    so what overflowed the box overflows it again; a request without the marker is the exact page as before.
  - **state a picture changes and a later one reads.** After the box, the job writes the package's `\pdfmdCachePost` (if it is
    defined) to the `.dim` as `\pdfmdCachePostStored`, for the package to run when it finds the picture stored instead of
    typesetting it. (chemfig keeps the greatest depth of the molecule names so far in a global; a scheme read it from an earlier one.)
- The README's section for a package author describes both.
- **What the checks said** (scratch copies of LR1-2, LR3, LR4-5, LR6 and Pre-lab 7, each built five ways: no cache,
  rebuild cache only, plots cached with the scheme part switched off, everything cached): with schemes cached the PDF is the
  one without them -- LR3, LR4-5, LR6 and Pre-lab 7 are identical to the pixel on every page (0 differing pixels in 14, 28, 29
  and 7 pages), LR1-2 has the same text and 5 pixels on one page. The attached source (`--attach-source --bundle`) and
  the `--merge` file are the same with and without the cache: the TeX of every scheme is in them, never a cached picture, and
  the only line that differs is the build-history entry of the later build. What the checks showed that is NOT this work:
  the rebuild cache alone (`--cache`) makes some pages differ from a `--no-cache` build (LR1-2: a paragraph on page 2 breaks
  its lines elsewhere; LR3, LR6, Pre-lab 7: plot tick labels move by a rounding step), and the plot cache moves a few tick
  labels of LR1-2 and Pre-lab 7 by the same step; both were there before.

## v3.28.34 — 2026-10-13

Pre-edit state: commit `8e57bf0` (v3.28.33).

### Changed

- **The picture cache's protocol names no package** (the author: "keep things neutral so it can scale to any package imaginable
  ... nulabreport specific things should live in nulabreport's own files"). Until now pdfmd looked for `nulabreport.sty`
  by name, tested it for `LabPlotCacheDir`, and wrote `\LabPlotCacheDir`, `\LabPlotRender`, `Lab@pc@wd` and `<job>.plotreq`.
  Now `picture_cache_styles` reads the packages the preamble loads (`\usepackage`, `\RequirePackage`, `\documentclass`) and
  takes in the style files that mention `pdfmdCacheDir`; their text keys the cache folder as nulabreport.sty's did. pdfmd
  defines `\pdfmdCacheDir` and `\pdfmdCacheVersion` (3 from v3.28.35: the margin and the replay of a picture's side effects are version 3), the render jobs define `\pdfmdCacheRender`, write the size as
  `\pdfmdCacheWd`/`Ht`/`Dp`, and the requests may come in `<job>.pdfmdreq`. The old names are one table
  (`LEGACY_CACHE_NAMES`, a style that mentions `LabPlotCacheDir` still takes part) and are defined and read as well, so
  nulabreport 1.26-1.28 caches as before. The render job's `\ClearShipoutPicture...` calls are guarded now (they came
  with one package's preamble). The README has a section for a package author.

### Added

- **Two markers in a request's context**, for a package whose pictures depend on more than expl3 can carry:
  `@@plain@@` splits the context into the part read under expl3's catcodes (as before) and a part read with the ordinary
  ones (chemfig's settings have spaces in their names, which expl3 drops), and `@@runs=2@@` runs the job twice (a picture
  whose arrows point at its own nodes uses TikZ's `remember picture`, which needs the second run). A request without
  them runs as before. The tests drive `render_plot_requests` with a stand-in engine, and `picture_cache_styles`
  with a package in a TEXMFHOME of the test's own.
- Where this came from: a scheme cache for nulabreport (v1.28.5, its own repository) uses both: on its Pre-lab 7 a warm
  rebuild takes 17 s of CPU instead of 24 s, with the same pages and five of seven pages pixel-identical (the other two
  differ by under 0.04% of their pixels: anti-aliasing at the edges of cached pictures).

## v3.28.33 — 2026-10-13

Pre-edit state: commit `ad111f0` (v3.28.32).

### Added

- **`pdfmd --install diagram`, `diagram:d2`, `diagram:dot`** (queue item s4; the author would not install them on the
  machine, so everything was tried against a scratch data folder with a PATH that had neither tool). `diagram:d2` downloads D2's release
  binary for this machine (macOS, Linux, Windows; amd64 and arm64) into pdfmd's tools folder, checked against the SHA-256 GitHub lists
  for the asset, as `--install typst` does. Graphviz has no download of its own for macOS or Linux, so `diagram:dot` fetches
  `@hpcc-js/wasm-graphviz` 1.29.2 (Graphviz 16.1 built to WebAssembly: one 2 MB script, pinned SHA-256 in pdfmd) and writes
  `dot`, `neato`, `fdp`, `sfdp`, `circo`, `twopi`, `osage` and `patchwork` launchers that run `pdfmd_lua/graphviz.cjs` with node
  (node comes the way it does for KaTeX; the launchers prefer pdfmd's own node, then the one on PATH). The tools folder is last on
  PATH, so a Graphviz or D2 of yours always wins. The WebAssembly build writes SVG only (no Cairo): when `dot -Tpdf` or
  `-Tpng` fails, `diagram.lua` now takes `-Tsvg` and converts it with `rsvg-convert` or `inkscape`, as it always did for D2.
  Compared with the real `dot` 16.1 on one graph: the same layout, the drawing 2% wider (446 against 437 pt; the WebAssembly
  build estimates the font's widths instead of measuring Times). The Windows launchers (`.cmd`) are written but untested.
- **Checked against the real tools** (no stand-ins): `dot` 16.1 and `d2` 0.9.0 draw the same document (a dot graph with a
  caption, a D2 diagram) into a LaTeX PDF, a Typst PDF, HTML (inline SVG) and Word (PNG), with rsvg-convert for the PDF and Word;
  also with the scratch-installed D2 and the WebAssembly `dot` only on PATH.

### Fixed

- **D2's "success: successfully compiled ..." line came out in every build that drew a D2 diagram.** `diagram.lua` runs the
  tool through `/bin/sh` with its stderr in a file (not on Windows), and shows that text only when the diagram could not be
  drawn: the warning now says what the tool said (`err: failed to compile in.d2: ...`) where it used to say "run d2 on it to see".

## v3.28.32 — 2026-10-13

Pre-edit state: commit `7864ff3` (v3.28.31).

### Fixed

- **Every Word, OpenDocument and PowerPoint build failed on Python 3.9 to 3.11** with `SyntaxError: f-string expression part
  cannot include a backslash` in `pdfmd_office/properties.py`. The privacy fix of v3.28.5 (the cache path in a picture's
  description becomes its file name) wrote `f'{...re.split(r"[/\\]", value)...}'`, which Python 3.12 accepts and older ones do
  not; the suite runs on 3.14 here, so it went unseen until a build under macOS's own Python 3.9 failed. The line is a plain
  concatenation now. Every other file was parsed on 3.9 and is clean. `tests/test_old_python_syntax.py` parses every source file
  with each Python older than 3.12 it finds (this one when CI's matrix runs it on 3.9, macOS's own `/usr/bin/python3`, a
  `python3.9`-`3.11` on PATH) and skips where there is none.

## v3.28.31 — 2026-10-13

Pre-edit state: commit `1268739` (v3.28.30).

### Fixed

- **`pdfmd --edit BOOK.pdf` on a report in parts (`-r`) replaced the whole book with one chapter.** The edit restored the
  chapters but opened and rebuilt only the first chunk, as a document of its own; the old book went to `.backups/`, so
  nothing was lost, but the new PDF was one chapter long (found by trying it on a three-chapter report: the PDF kept only
  chapter 2). A report is now edited as a report: `--editor CMD` is given every chapter file, and each save rebuilds
  `pdfmd -r CHAPTERS --attach-source` in the order the book was built, so the PDF stays a book that carries its chapters.
  The built-in editor, which opens one file, opens the first chapter and names the others. The new test edits the last
  chapter of a three-chapter report and checks the three chapters, the edit, the order and the manifest.

## v3.28.30 — 2026-10-13

Pre-edit state: commit `9051a96` (v3.28.29).

### Added

- **`--bopen sN`** (the author asked for it beside `eN`): the first file, then every Nth, as Python's `files[::N]` does
  (`s3` opens the 1st, 4th, 7th ...). `eN` stays the Nth, 2Nth ... (`e3`: the 3rd, 6th, 9th ...). Both mix with the
  other selectors (`f2,s5`). No new flag, so no setup row.

## v3.28.29 — 2026-10-13

Pre-edit state: commit `41badfc` (v3.28.28).

### Fixed

- **v3.28.25 broke the report route (`-r`) for a PDF build.** Its KaTeX size read `report_tex_font` at a place where the
  variable is not set yet (`UnboundLocalError`), which stopped every report build with a Traceback (three tests of
  `test_header_includes` and `test_budget`, found by the full suite of v3.28.27, not by the modules run with 3.28.25). The
  report's body font for the size is `-f`, else the `mainfont:` the document or its metadata names. v3.28.25 to v3.28.28
  carry the bug. A test builds a WeasyPrint report with a named font.

---

## v3.28.28 — 2026-10-13

Pre-edit state: commit `94d9dd9` (v3.28.27).

### Fixed

- **`pdfmd --edit FILE.pdf --editor CMD` no longer rebuilds in a loop when the build writes beside the source.** The watch
  compared the restored folder with its state before the build, so a file the build itself wrote (a backup in `.backups/`, a
  stamp history, a document-local cache) counted as a new edit and started another build, until the editor closed. A hidden
  file or folder is now never an edit, and the folder is read again after each build so that what the build wrote is not
  one either. (v3.28.23's test used an editor that ended at once, which left the loop no time to show; the new test keeps the
  editor open while the build runs, and fails without the fix.)

---

## v3.28.27 — 2026-10-13

Pre-edit state: commit `180f3f1` (v3.28.26).

### Fixed

- Choosing the global metadata for a document that cannot be read (not there yet, not UTF-8) no longer stops the build with an
  error: the config's `preset` / `global-metadata` alone decide (v3.28.19 read the document's own `pdfmd-options` first).

---

## v3.28.26 — 2026-10-13

Pre-edit state: commit `1c9c169` (v3.28.25).

### Fixed

- **`pdfmd --install tui|math|emoji|translit|batchocr` works on a Python the system manages (PEP 668).** On Homebrew's and
  Debian's Python pip refuses ("externally-managed-environment") and the install failed with "pip failed". pdfmd now sees
  that message and installs the same packages with `pip install --upgrade --target` into its own folder,
  `data_root()/python/X.Y` (`~/.local/share/pdfmd/python/3.14`), says so (`NOTE  this Python is managed by the system`), and
  adds that folder to the end of `sys.path` at start-up, before the optional modules are imported (so the system's own
  packages win). Any other pip failure is reported as before and not retried.
- **The doctor no longer tells you to install the romanization packs when they are installed.** It said
  `pdfmd --install translit for Chinese and the rest` whatever was there; now, when the packs are installed and only off, it says
  `ready, off until you turn them on: --translit all` and lists them.
- **`pdfmd.pyz` (the zipapp) lacked `pdfmd_edit`, `pdfmd_help` and `pdfmd_raw`**: `--edit`, `--help` topics and raw-block
  conversion were missing from it. `scripts/build_zipapp.py` lists the same packages as `pyproject.toml`, and a test
  (`test_packaging`) fails when the two lists, or the package folders, differ.
- Tests: `tests/test_install_python.py` (the folder, the start-up path, the fallback and not retrying other failures, the doctor).

---

## v3.28.25 — 2026-10-13

Pre-edit state: commit `04d057d` (v3.28.24).

### Changed

- **KaTeX's formulas in a WeasyPrint PDF are sized to the body font.** KaTeX sets math at 1.21em, tuned for a text face with
  a large x-height; in a document in STIX Two Text (x-height 0.473 em) or Libertinus (0.429) the formulas stood out. pdfmd
  now reads the body font's x-height (the OS/2 `sxHeight` of the font file fontconfig finds) and gives the formulas the
  `font-size` of x-height / 0.442 em: STIX Two Text 1.07, Noto Serif 1.21 (as before), Times New Roman 1.01, Georgia 1.09,
  Libertinus Serif 0.97, kept between 0.85 and 1.4. The body font is the one pdfmd chose, or `mainfont:` of the document or its
  metadata files, or `-f`/`-V mainfont=`; a font that is not installed or has no recorded x-height leaves KaTeX's own size.
  It is `-V pdfmd-katex-scale=` for `pdfmd_lua/weasyprint.lua`, which writes `html .katex { font-size: ...em }` into the page's
  header, kept even when a `--css` file or `document-css: false` replaces the page style.
- Tests: `tests/test_katex_scale.py` (a font built in the test, the size and its bounds, a font fontconfig does not have, a
  real WeasyPrint build).

---

## v3.28.24 — 2026-10-13

Pre-edit state: commit `a1c3982` (v3.28.23).

### Added

- **Formulas are set in the math font that goes with the body font.** unicode-math (LuaLaTeX, XeLaTeX) and Typst set
  math in Latin Modern Math / New Computer Modern Math unless a `mathfont` is given, so a document in pdfmd's default STIX
  Two Text had formulas in another typeface. When pdfmd chose the main font itself, it now passes `-V mathfont=` with the
  companion: STIX Two Text → STIX Two Math, DejaVu Serif → DejaVu Math TeX Gyre, Libertinus Serif → Libertinus Math, New
  Computer Modern → New Computer Modern Math (as fontconfig or Typst spells it), TeX Gyre Termes/Pagella → their Math fonts,
  each only when installed. Not added: when `-f`, `mainfont:` (front matter, metadata files, `-V`) names the text font or
  `mathfont:` names the math font; for pdfLaTeX, latexmk and WeasyPrint; for Typst when Pandoc's template has no `mathfont`
  (Pandoc 3.1.3). `--no-auto mathfont` (or `--no-auto font`) stops it; `DEFAULTS` says `math in STIX Two Math`
  (`AUTO MATHFONT` with `--verbose`). It applies to single documents, `--to latex` and reports.
- Tests: `tests/test_mathfont.py` (the table, the engines, what the user named, the switches, the DEFAULTS words, and the
  LaTeX file of a real build).

---

## v3.28.23 — 2026-10-13

Pre-edit state: commit `6a9ce06` (v3.28.22).

### Added

- **`pdfmd --edit FILE.pdf` edits a PDF that carries its source and rebuilds it in place.** The source is restored
  (as `--restore` does) into a temporary folder; the built-in editor of `--edit` works on it (Ctrl-B builds there, the
  original PDF is not touched), or the editor of `--editor CMD` (`"code --wait"`, `vim`; also `options.editor` in `--setup`),
  in which case the folder is watched and every save rebuilds it, as `-w` does. On leaving: no change, or a last version that
  does not build, leaves the PDF as it was; otherwise the old PDF is copied to `.backups/NAME.TIMESTAMP.pdf` and the rebuilt
  one (made with `--attach-source`, so it carries the edited source) is renamed over it, after a `[Y/n]` question in a terminal
  (`n` writes `NAME.edited.pdf` instead). The options of the first build are the ones the document and its metadata
  files record; the command-line ones are the ones given with `--edit`. The global metadata stays the machine's (3.28.13).
- **`--editor CMD` on a Markdown file** (`pdfmd --edit report.md --editor vim`): the editor, and `pdfmd -w` beside it until
  the editor closes. The built-in editor is still the default and still needs prompt_toolkit.
- Tests: `tests/test_edit_pdf.py` (a fake editor that appends a paragraph: the PDF is replaced, carries the new text and the
  new source, the old one is in `.backups/`; no change; a PDF without a source is refused).

---

## v3.28.22 — 2026-10-13

Pre-edit state: commit `7627683` (v3.28.21).

### Added

- **`pdfmd --check-source [PDF or FOLDER ...]` (alias `--sources`) says which PDFs carry their source.** It reads only the
  attachment list of each PDF, builds nothing, and takes no argument (the working folder), a folder (`--recursive`
  goes below it) or PDF files. One line each: `SOURCE  a.pdf  a.md, 52 lines, pdfmd 3.28.22` (with a note when the attached
  text no longer matches its recorded hash, or when a Markdown file of the same name beside the PDF is newer than it),
  `HYBRID` for a LibreOffice hybrid PDF, `NONE  b.pdf  b.md is beside it: pdfmd b.md --attach-source` or `no b.md beside it`,
  `ERROR` for a file that is not a PDF; then `CHECK  5 PDFs: 2 with the source, 3 without`. Exit status 1 when one has none.
  (`--check` was taken by the document checker, `--edit` by the editor.)
- Tests: `tests/test_check_source.py`.

---

## v3.28.21 — 2026-10-13

Pre-edit state: commit `96cd623` (v3.28.20).

### Fixed

- **v3.28.17 broke raw LaTeX in headers and pdfmd-options.** Its code-font test defined `RAW_FENCE_RE` a second time,
  further down in `pdfmd.py`, and so replaced the pattern that `raw_latex_only()` and `pandoc_header_includes()` use to read
  raw blocks: a fenced ```` ```{=latex} ```` header was no longer seen (`tests/test_header_includes.py`, three tests, caught by
  the full suite of v3.28.18, not by the modules run before it). The code-font test's patterns are `CODE_RAW_FENCE_RE` and
  `CODE_RAW_SPAN_RE` now; nothing else changes. v3.28.17 to v3.28.20 carry the bug.

---

## v3.28.20 — 2026-10-13

Pre-edit state: commit `2e7e0a3` (v3.28.19).

### Added

- **`--bopen [SPEC]` opens some of a batch's finished files when the batch is done.** `--open` is still ignored in a batch
  (it would open every file) and its warning now points here. A SPEC is a comma list of selectors, each with any whole
  number N from 1 (nothing is fixed at 15 or 10): `fN` the first N, `lN` the last N, `flN` the first half and the last half
  (the first gets the odd one: `fl15` is 8 + 7), `eN` every Nth file (the Nth, the 2Nth ...), `all`; no SPEC means all.
  The union opens, each file once, in the order the batch lists them (not the order parallel workers finish), only files
  that were built; `OPENED  3 of 6 (f2,l1): d1.html, d2.html, d6.html` says which. A SPEC that is not one stops before
  anything is built and prints the grammar. In a single-file or report build `--bopen` is `--open`. A folder written right
  after a bare `--bopen` (`pdfmd --bopen notes -b`) is taken as the folder, not as a SPEC.
- Tests: `tests/test_bopen.py` (the selectors, bad specs, a batch with a fake opener on PATH, with and without `-j`).

---

## v3.28.19 — 2026-10-13

Pre-edit state: commit `ad3f1f0` (v3.28.18).

### Added

- **The global metadata can be switched off, and swapped for a preset.** Until now the global `metadata.yaml` of
  `pdfmd --setup` went into every build and only an empty `PDFMD_CONFIG` removed it.
  - `--no-global-metadata` / `--global-metadata`, `pdfmd-options: {global-metadata: false}` (a document, or a folder's
    metadata) and `options: {global-metadata: false}` (the config; the *Use the global metadata above* row of `--setup`).
    The command line beats the document, which beats the folder's metadata, which beats the config. (`--global` was
    taken: `--init-backups --global`.)
  - **Presets:** a file `presets/NAME.yaml` (or `.yml`) beside the config file is global metadata like `metadata.yaml`
    (the preset `default`). `--preset NAME` (the name with or without `.yaml`, or a path), `pdfmd-options: {preset: NAME}`,
    `options: {preset: NAME}` (the *Which set of global metadata* row) choose it; `--preset none` takes none. A name that
    is no preset stops the build and lists the ones there are. `pdfmd --setup --preset NAME` edits that file's rows (made if
    absent); `pdfmd --presets [DOCUMENT]` lists the presets, marking the one a build there would use.
  - A preset shows as `preset NAME` on the `DEFAULTS` line and `(the preset NAME of pdfmd --setup)` with `--verbose`.
    `--restore` / `--unpack` leave a preset to the machine as they do the global metadata (every global file is recognised
    by where it is, not by its name).
- Tests: `tests/test_presets.py` (every layer and spelling, the switch, the unknown name, `--presets`, `--setup --preset`).

### Fixed

- **Esc works in the full-screen `pdfmd --setup`.** On the main screen it did nothing (only `q` left); it now steps back out
  of a list and then out of the screen (asking first when something is unsaved), and in the prompt of a text row it
  cancels. The metadata rows say they are saved in `metadata.yaml` for every document, which the screen did not.

---

## v3.28.18 — 2026-10-13

Pre-edit state: commit `b4691e5` (v3.28.17).

### Changed

- **The closing line names the file the build made: `OK    report.md > report.pdf  (lualatex)`.** The file is given by
  its name when it sits beside the source, by its path when it does not (`-o`, `--out-dir`); a build that wrote no one
  file keeps the old line. What stands between the two is `options.ok-delimiter` (`--setup`; default `>`).
- **`FOUND` lists the files of one folder under it once:** `FOUND     metadata: metadata.yaml + preamble.tex, nulabreport.lua, 9 parts`.
  A folder with one file keeps its path. `options.found-style: path` (`--setup`) gives every file with its path as before.
- **`DEFAULTS`:** the global metadata is `global metadata` (the key list is gone; `--verbose` still names the file and
  says it is the global one), and two more decisions moved in from the `AUTO:` line: `title from heading` (a leading
  `# ` heading taken as the title) and `balanced 2 wide tables` (below).
- **The line follows the terminal.** When stdout is a terminal the `FOUND`/`DEFAULTS` lines are cut at its width
  (`+3 more (--verbose)`), 110 characters when the output is piped or a batch runs in parallel.

### Added

- **The table-width filter says so when it fires.** It was passed to every LaTeX-family build and said nothing when it
  resized a table. `pdfmd_lua/table_width.lua` now appends the table's place in the document to the file named by
  `PDFMD_TABLEWIDTH_LOG` (set by pdfmd for its own runs), only for a table that had no column widths and would have run
  past the margin; pdfmd counts them once however many engines were tried: `DEFAULTS  ... balanced 1 wide table`,
  `AUTO TABLEWIDTH` with `--verbose`. A table that fits, or has widths of its own, is still left alone and unannounced.

### Fixed

- A raw fence of any length is raw: ```` `````{=latex} ```` holding shorter fences, a closing fence longer than the
  opening one, and an inline span in two or three backticks around a single one (`` `` `x` ``{=typst} ``) all stay out of the
  code-font test of v3.28.17.
- Tests: `Layout` and four build tests in `tests/test_autolog.py` (grouping, title and table in DEFAULTS, the terminal width,
  the resized-table line, the delimiter and the path style), six more fence cases in `tests/test_rawcode.py`.

---

## v3.28.17 — 2026-10-13

Pre-edit state: commit `cd7cd52` (v3.28.16).

### Fixed

- **A document with only raw blocks no longer gets the code font.** `has_code_spans()` took any backtick for code, so a
  ```` ```{=latex} ```` block, a `` `x`{=latex} `` span, or a ```` ```{=pdfmd} ```` block made the build say `has code but no
  monofont set` and apply the default code font. Raw content in any format (`{=latex}`, `{=html}`, `{=typst}`, `{=pdfmd}`...) is
  now left out of the test; a fence with the class `pdfmd` and no `=` (```` ```{pdfmd} ````) is ordinary code. Unchanged: real
  inline code, fenced code and `~~~` fences still count, and so does a raw block that is never closed.
- **`csl: apa` finds `apa.csl`.** The embedder (`--attach-source`, `--embed-metadata`) looked for the style under the name as
  written only, so the global metadata's `csl: apa` printed `WARN not embedded: apa (not found ... Pandoc's csl/ folder)` on
  every build although `apa.csl` is in Pandoc's `csl/` folder (Pandoc itself adds the suffix). It now tries the name, then the
  name with `.csl`, in each folder it looks in. And a style it cannot find is no longer a warning when the document cites
  nothing (no `bibliography`, no `@key`): the global metadata sets a style for every document.
- Tests: `tests/test_rawcode.py` (eleven spellings, the verbose `AUTO MONOFONT` line with and without code, the style lookup
  and the citing condition).

---

## v3.28.16 — 2026-10-12

Pre-edit state: commit `1209178` (v3.28.15).

### Changed

- **A build says what it decided in three lines: `FOUND`, `DEFAULTS`, `AUTO:`.** Before, a metadata file, the
  global metadata of `pdfmd --setup` and a preamble were a line each (`AUTO YAML`, `AUTO TEX`), the Lua filter,
  the parts, the margin and the code font were folded into one `AUTO: KINDS` line, and the default main font was
  not said at all (until 3.28.14). The global metadata looked like a file pdfmd had found in the folder.
  ```
  FOUND     metadata/metadata.yaml, metadata/preamble.tex, nulabreport.lua, 9 parts
  DEFAULTS  global metadata (colorlinks, csl +1), margin 1in, font STIX Two Text, code in JetBrains Mono
  OK    report.md  (lualatex)
  ```
  - `FOUND`: what pdfmd picked up from the folder (metadata files, preamble, Lua filter, parts).
    `DEFAULTS`: what it applied because nothing said otherwise (the global metadata with its first two keys, the
    margin, the main font, the code font, the packages it adds). `AUTO: KINDS`: the decisions with no short form
    (reader, title, standalone, Unicode ...), as before.
  - **The screen is not for the catalogue:** a line is cut at 110 characters (`+3 more (--verbose)`), a default
    that did not take effect is not listed, and a build prints at most these three lines before its `OK`.
    LR4-5: 4 lines (`AUTO YAML` x2, `AUTO:`) became 3; with a preamble and code: 4 became 3.
  - **`--verbose` is unchanged in words** (`AUTO YAML`, `AUTO TEX`, `AUTO LUA`, `AUTO MARGIN` ... each with its
    reason): nulabreport's manual quotes them. The global metadata's line says `(the global metadata of pdfmd
    --setup)`.
  - **A batch** (`-b`, several files) prints a `FOUND` or `DEFAULTS` line again only when it differs from the
    last; with `-j N` the parent prints `FOUND` and the global metadata and the workers print none.
    A report (`-r`) uses the same lines before its `OK  REPORT`.
  - `AUTO: PARTS` is gone from the default output: the parts are in `FOUND` (`9 parts`). nulabreport's manual
    says to look for `AUTO: PARTS`; that sentence needs `FOUND ... 9 parts` (or `--verbose` and `AUTO PARTS`).
- An explicit `-y FILE` still prints as `YAML  FILE` (you named it, so it is not a decision).

### Tests

- `test_autolog`: the cut with a count, the sorting into the lines, one item per decision, a batch not repeating
  a line, verbose as before; end to end: three lines and `OK`, verbose words, a batch, `-j 2`.
  `test_header_includes` reads `FOUND ... preamble.tex`.

## v3.28.15 — 2026-10-12

Pre-edit state: commit `ae5bc6d` (v3.28.14).

### Changed

- **A PDF with its source attached now carries what the text reads, without the images (`bundle: sources`).**
  Before, `--restore` of a report built with `attach-source` alone stopped at `\input{schemes/...}`: the
  `.tex` files and the data a macro reads came only with `bundle: referenced`, which stores the pictures too.
  - New third state of the `bundle` setting (`--bundle sources`, `pdfmd-options.bundle: sources`) and the new
    default when the source is attached and `bundle` is not set. `bundle: false` / `--no-bundle` keeps the
    source alone as before; `bundle: true` / `--bundle` (referenced) adds the image files; `all` is unchanged.
  - Images are not stored: the PDF holds every picture it drew and `--restore` takes them out of it. A
    picture only an `\input`ed `.tex` draws is now recorded in the manifest like the text's own, so it comes
    back too; a picture that comes back under another name (`fig.svg` becomes `fig.pdf`) is renamed in the
    stored `.tex` as well, not only in the Markdown.
  - A Markdown output (`--keep-source`) has no PDF to take pictures from and does not get the default.
  - **Behaviour change for every `attach-source` user:** the attachment grows by the data the document reads
    (LR4-5: 1.00 MB, with `referenced`: 1.65 MB, now 1.2 MB, 25 files; LR6: 0.5 MB, 28 files). A PDF built
    before this version has none of it and restores as before.
- **`--restore` and `--unpack` stay short.** They count what they write by folder (`RESTORED  44 files into
  rest6b  (report.md, parts/ 9, metadata/ 6, ir/ 5 ...)`) instead of printing a line per file; an edited file,
  a filter this machine does not know and the global metadata still get their own line. `--verbose` gives
  the old listing; `--restore --list` always does. LR6 restore: 89 lines before, 12 now. Pictures the PDF does
  not hold are one line, not one each; the packages and graphics a rebuild needs from the author's TeX tree
  are one `NEEDS`/`NOTE` line a kind (six lines became two on every attach).

### Checked

- LR4-5 and LR6, each built from a copy, restored, and the restored folder built with lualatex: same page
  count and no difference in the text (29 pages, 12,069 words; 14 pages, 5,717 words); the three TLC pictures
  came out of the PDF.

### Tests

- `test_attach`: the default stores the inputs and data and not the images; `bundle: false` and `off`; the
  referenced mode; a Markdown output gets no default; a renamed picture inside a stored `.tex`; the compact
  and verbose restore and `--list`. `test_polish` expects the linked file stored with the source.

## v3.28.14 — 2026-10-12

Pre-edit state: commit `4ea4176` (v3.28.13).

### Fixed

- **A font named in a metadata file was replaced by pdfmd's default.** `has_mainfont()` and `has_monofont()`
  read only `-V` and the document's own front matter.
  - So a `metadata.yaml` that said `mainfont: Georgia` and `monofont: Menlo` still built in STIX Two Text and
    JetBrains Mono: pdfmd's `-V mainfont=` and `-V monofont=` beat metadata in Pandoc.
  - The global metadata of `pdfmd --setup`, whose menu offers the main and the code font, was overridden the same
    way.
  - Both now also read the metadata files the document gets (`has_font_setting()`), at every site: a single build,
    the `.tex` route, `-r` reports, `--check-fonts`.
  - A font the metadata names now counts as the document's own: pdfmd no longer swaps it for another script's
    font, as it never swapped one named in the front matter.
  - nulabreport's `metadata.yaml` names pdfmd's own defaults, which is why the bug did not show there. Its builds
    no longer report `MONOFONT` ("has code but no monofont set") for a monofont the file sets.

### Changed

- **pdfmd's own main font is named like its other defaults.** `AUTO MAINFONT  doc.md: no mainfont set; using STIX
  Two Text` (in the one-line summary: `MAINFONT`). Before, it was said only when the font was swapped for the
  document's script, while the margin and the code font were always named.
- **A decision is reported once per build.** A build that tries a second engine repeated each `AUTO` line.

Checked:
- LR4-5: the generated `.tex` and `.typ` are identical to v3.28.13's.
- A `metadata.yaml` with `mainfont: Georgia` and `monofont: Menlo`, built with lualatex and with Typst on Pandoc
  3.12 and 3.1.3: the PDF now has Georgia (and Menlo with lualatex). It had STIX Two Text and JetBrains Mono.
- Kazakh text with `mainfont: STIX Two Text` in `metadata.yaml`, as nulabreport has it:
  - before, the whole document was set in Noto Serif;
  - now STIX Two Text stays, and the words with letters it lacks are set in Noto Serif;
  - every letter is drawn, with lualatex and with Typst.

### Tests

- `tests/test_setup.py`: a folder `metadata.yaml`'s `mainfont` and the global file's `monofont` reach the
  `.tex`, with no MAINFONT or MONOFONT note. Without either, both notes are given. Fails on v3.28.13.

---

## v3.28.13 — 2026-10-12

Pre-edit state: commit `08c8076` (v3.28.12).

A report in parts restored from its PDF built its title page only. This happened when the report's folder had a
`metadata.yaml` and the machine that built it had a global metadata file (`pdfmd --setup`). Three faults behind it,
each fixed:

### Fixed

- **The global metadata outranked the folder's own in the attached source.** Since v3.27.17 a build gives Pandoc
  the global file first, as the lowest layer. The attached source (and `--to assembled`) still merged the files in
  list order, where it comes last. So a key both files set took the global value in the source: the author's LR6
  carried `csl: apa` though its PDF was typeset with the folder's `nu-labreport.csl`. The merge now follows
  Pandoc's order, `--metadata-precedence first` included, for metadata keys and `pdfmd-options` alike.
- **The restore wrote the global file into `NAME.unpacked/`.** A build reads only that folder's YAML when it is
  there, so the restored `metadata/metadata.yaml` was never read. The global file belongs to the machine, not the
  document:
  - the attached source marks it: `origin.global` in the front matter, `"global": true` in the manifest's layout
    entry;
  - the manifest no longer stores the global file's text, and names the file `../pdfmd/metadata.yaml`. Its real
    path relative to the document told how deep the folder sat, and from a folder outside the home folder it
    held the user's name;
  - `--restore` and `--unpack` leave it out and print one line naming its keys ("not restored: a build here uses
    this machine's own");
  - a PDF made before this release is recognised by its layout path, a `pdfmd/metadata.yaml` outside the
    document's folder.
- **The restore wrote a rebuilt `metadata.yaml`, without `parts`.** It compared the stored text with the
  rebuilt one, which differed by the misattributed `csl`, so it refused the stored text and wrote the rebuilt
  one. It had already left `parts: auto` out of the document, because the stored text said it. Now:
  - when the attached source's hash matches, the stored text is the file the build read, and it comes back as
    written;
  - the comparison remains for an edited source;
  - whether `parts` goes into the document is decided from the metadata files actually written.
- **Matching the metadata pieces.** `--restore` now matches them to the layout by their label, in the order the
  build listed them, so a label made unique as `folder-metadata.yaml` finds its file too.
- **A metadata file from outside the document's folder** (`-y ../shared.yaml`) no longer goes to `NAME.unpacked/`
  when the folder has its own metadata files. There it would hide them. It goes to `outside/`, with one WARN giving
  the `-y` list that layers it as before.
- **A bibliography or CSL file** goes beside the first metadata file inside the folder, not beside the global
  file.

The author's `report.pdf` of LR6, restored again:
- `metadata/metadata.yaml` comes back byte for byte, comments and `parts: auto` included;
- there is no `report.unpacked/`;
- one NOTE: `csl, colorlinks: from pdfmd's global metadata`;
- `--to latex` has all nine parts and the numeric citations of the original (`[1, sec. 22.2]`, "1. Palleros").

The full build then stops at `\input{schemes/esterification.tex}`: the PDF carries the text and the `tables/` CSVs
but not the files the report `\input`s or plots. That is by design, and `bundle: referenced` carries them.

A document built with no global metadata file gets a byte-identical attachment (source and manifest).

LR4-5 (nulabreport, lualatex) built with v3.28.12 and with this release:
- same PDF text, same 29 pages;
- the attached source now says `csl: nu-labreport.csl` and embeds that style (1,927 lines), in place of `csl: apa`;
- every such build printed `WARN  not embedded: apa (not found ...)`, and that WARN is gone;
- the front matter's keys keep their order, and only the winning value changed.

### Tests

- `tests/test_attach.py` `GlobalMetadataRestore`, with a global file in a folder called `pdfmd`:
  - the folder's key wins in the source, the layout marks the global file and the manifest keeps only the folder's
    text;
  - the restore gives the folder's `metadata.yaml` back as written, adds no `parts` to the document and no
    `report.unpacked/`;
  - a PDF made as v3.28.11 made them (unmarked global, its value credited with the folder's key) restores to a
    folder whose HTML build has the part's text and the folder's subtitle;
  - `--unpack` leaves the global file out with its GLOBAL line;
  - a `-y` file from outside goes to `outside/` with the `-y` list.
  - All four fail on v3.28.12.

---

## v3.28.12 — 2026-10-12

Pre-edit state: commit `9b6f91f` (the changelog's batchmd and pan-tec history, docs only).

A persona for batch mode: the `batchmd` command, the first script's name, is `pdfmd -b`.

### Added

- **`batchmd` command: `pdfmd -b` under the name of the first script.** Like `mdpdf` and `inkmd`, it is a second
  console script (`pyproject.toml`, `batchmd = "pdfmd:batchmd_main"`) that does what pdfmd does with batch mode.
  - Every `.md` in the folder becomes its own PDF beside it, with pdfmd's options as usual (`-e`, `--header`, ...).
  - With no folder named it takes the current one. `pdfmd -b` alone still refuses ("Batch mode requires one directory
    path"); `pdfmd` itself is unchanged, since it is a shared dependency.
  - `batchmd_translate()` is the whole translation: it adds `-b`, and `.` when the parse finds no folder. The parse
    uses pdfmd's own parser, so a value such as the `lualatex` of `-e lualatex` is not taken for a folder.
  - `--help` and `--version` pass through unchanged.

### Tests

- `tests/test_polish.py` `BatchmdKeys`: the translation (`-b` added, `.` as the default folder, values and named
  folders kept, `--help` and `--version` untouched), the entry point, and an end-to-end run of
  `pdfmd.batchmd_main()` with `argv[0]` set to `batchmd` and an empty PATH that writes two PDFs.
- Checked by hand: `batchmd` and `pdfmd -b notes` on the same two-file folder give the same PDFs and the same
  build lines (only the path shown differs: `alpha.md` against `notes/alpha.md`).

---

## v3.28.11 — 2026-10-12

Pre-edit state: commit `fed3b3d` (v3.28.10).

Stage 6 A2, first step: math in WeasyPrint's PDFs.

### Added

- **`pdfmd --install math:katex`: WeasyPrint's PDFs typeset their math.** WeasyPrint does not draw MathML, so since
  v3.27.12 a formula was Pandoc's plain text (`αᵢ ≤ β`, or its TeX).
  - With KaTeX in place, `pdfmd_lua/weasyprint.lua` sends every formula to KaTeX in one node call
    (`pdfmd_lua/katex.cjs`) and puts KaTeX's HTML in its place. The page links KaTeX's stylesheet and fonts, and
    WeasyPrint prints them as a browser does: fractions, roots, matrices, `cases`, stretchy and labelled arrows,
    `\tag` numbers.
  - Chemistry is converted first: the filter now runs last, after the LaTeX filter, so `$\ce{...}$` reaches KaTeX
    as pdfmd_chem's plain math. A labelled arrow, which was text, is an equation again.
  - Pandoc's math stays plain, so a formula the filter does not reach prints as text, never as MathML.
  - A formula KaTeX cannot read (a macro from the LaTeX preamble, a `\tag` inline) stays text, with one WARN for all
    of them that names the first and why. `\textmu` is defined for it.
  - What WeasyPrint gets wrong in KaTeX's own stylesheet is set right: `\neq` lost its "=" (a flexbox column) and
    `\vec` its arrow (an absolutely placed picture in a box of no width).
  - A formula in the title or an author's name is typeset on the page, and the PDF's Title and Author keep its TeX,
    as without KaTeX: typeset, it was raw HTML, which the page's `<title>` leaves out ("Energy  here").
  - `--math-method=...` on the command line keeps Pandoc's math, as before.
- **The install** puts KaTeX 0.18.9 in `data_root()/katex/0.18.9`: the npm package, checked against a SHA-256 pinned
  in pdfmd, of which only the script, the stylesheet, the fonts, mhchem and the licence are kept (1.5 MB). Without
  node on PATH it also fetches node's newest long-term-support release for this machine from nodejs.org, checked
  against the SHA-256 listed there, into pdfmd's tools folder, as for Typst (about 30 MB to download, 120 MB on disk;
  the author's choice over a pip package of V8 or only pointing to a package manager). It ends by typesetting one
  formula. A KaTeX left by an older pdfmd is used until the new one is installed.
- **`--doctor`** and **`--check-dependencies`** say whether WeasyPrint's math is typeset (KaTeX's version, node)
  or text, with the command that changes it. The WARN for math printed as text names it too.

### Fixed

- **A WeasyPrint build that worked printed WeasyPrint's complaints about CSS** (`WARNING: Ignored
  text-rendering...`, `Invalid media type...`): four lines for Pandoc's own page style, and twenty more for KaTeX's.
  They are left out unless `--verbose`. Every other WeasyPrint warning stays.
- **The WARN for math as text counted the formulas before the LaTeX filter**, so an `equation` block it turns into a
  formula was not counted (LR4-5: 45 said, 52 printed as text). It now counts what is printed.

Checked:
- **No KaTeX, no change:** LR4-5 with `-e weasyprint` gives the same text as v3.28.10 (31 pages), with the CSS
  complaints gone and the count above.
- **LR4-5 with KaTeX:** all 52 formulas typeset, none left as TeX (v3.28.10 had TeX on 3 pages), in KaTeX's fonts;
  equations (5) and (6) numbered at the margin.
- **15,214 distinct formulas** from the author's course and lab-report documents through KaTeX 0.18.9: 169 errors,
  123 of them siunitx's `\si` (pdfmd_chem converts it first in a real build) and 23 `\textmu` (now defined); the
  rest are macros from preambles and broken TeX. 101 of them, chosen to cover 140 different commands, printed by
  WeasyPrint and read through: each as its source says. A page of accents found the two stylesheet faults above.
- **A labelled arrow in text** (`\ce{A ->[\Delta] B}`) is an equation with Δ over the arrow with KaTeX, and
  "A ⟶ (Δ) B" without it, as before.
- **The install**, run for real: KaTeX's package checked and unpacked (64 files); with no node on PATH, node v24.21.0
  for macOS arm64 fetched, checked and run. A test page through `-e weasyprint` on Pandoc 3.12 and 3.1.3, alone and
  with `-r`; `--math-method=plain` still gives text.
- **Packaging:** the wheel and `pdfmd.pyz` hold `pdfmd_lua/katex.cjs`.

### Tests

- `tests/test_engine_filters.py`:
  - `KatexInstall`: what the package keeps (and nothing from outside it), a package without fonts refused, the
    pinned release else the newest installed, node's release names, node taken from its `bin` folder, the
    `math:katex` kind, WeasyPrint's CSS complaints dropped and the rest kept;
  - `WeasyPrintArguments`: KaTeX and node named to the filter, with plain math, and not when the command line chooses
    the math;
  - `WeasyPrintKatex` (with node and KaTeX installed): typeset in KaTeX's fonts with nothing said, a formula KaTeX
    cannot read is text with one WARN, `\ce` in math converted first (the command line has the LaTeX filter before
    this one: KaTeX's own mhchem would hide the order), a formula in the title kept in the PDF's Title;
  - `WeasyPrintMath` builds with no KaTeX, and its WARN names `pdfmd --install math:katex`.
- `tests/test_table_widths.py`: the package data now includes `*.cjs`, and `katex.cjs` is there.
- Full suite, with KaTeX in place: Pandoc 3.12, 1051 tests; Pandoc 3.1.3, 1051. Each had one failure, the packaging
  test above (it still expected the old package-data line), which now passes. The modules that build with WeasyPrint
  (154 tests) pass again with no KaTeX.

## v3.28.10 — 2026-10-12

Pre-edit state: commit `b2a5eb9` (v3.28.9).

Stage 6 A, last step: every output gets the chemistry and units.

### Fixed

- **An HTML, EPUB, Markdown, text or `.typ` file, or a PowerPoint deck, dropped `\ce` and siunitx.** Their writers
  drop raw LaTeX, and the LaTeX filter does not run for them: `Water \ce{H2O} and \qty{25}{\mL}` was "Water and", and
  `$\ce{CO2}$` stayed TeX.
  - The new `pdfmd_lua/chem.lua` makes each such command in text text with sub- and superscripts.
  - A formula with them in it gets them converted.
  - In text and Markdown, a formula that is one command becomes its text too: CO₂, `A ⟶ (Δ) B`. Pandoc's plain
    writer cannot write words over an arrow.
  - pdfmd adds it only when a source has such a command, after the document's own filters, for every output but
    LaTeX, Word and OpenDocument (the LaTeX filter's own), and not with `office: {latex: off}`.
  - Its metadata (`pdfmd-chem-python`, `pdfmd-chem-preamble`) is removed once read, so that a standalone Markdown
    file does not write out a folder of this machine.
  - `raw.lua` leaves such a command to it: with the flat outputs' raw setting it dropped the `\ce` first.
- **A paragraph that is one command** (`\ce{2H2 + O2 -> 2H2O}` on a line of its own) was a picture in Word and was
  dropped in HTML. It is now text in both.
- **A reaction scheme in display math** (`\schemestart ... \arrow{->[\ce{NaBH4}]} ...`) is left whole: only LaTeX
  draws it, and its arguments are LaTeX's.
- **A letter amount** (the `x` of `x Na(NH4)HPO4`) is italic in an equation, as mhchem sets it.

### Changed

- The Lua side of the converter is `pdfmd_lua/chem_client.lua`, shared by the LaTeX filter and `chem.lua`. The
  filter loads it guarded: if it is missing, one WARN, and LaTeX draws the formulas.
- One list of the commands, `CHEM_COMMANDS` in `pdfmd.py`. It is the same as the Lua one and pdfmd_chem's (a test
  says so). The check for LaTeX that Typst and WeasyPrint would drop now also knows `\cee`, `\cf` and siunitx's
  lists.

Checked:
- **No regression:** LR4-5 to `.docx` on Pandoc 3.12 and 3.1.3 has the same text as with v3.28.9. A document
  without chemistry gives byte-identical HTML, GFM and Typst, and the same Word text.
- **LR4-5 to HTML, GFM and Typst:** the changes, read through, are the chemistry and units that used to be missing
  (NaBH₄, R₂CH−O−Cl, C−H, CDCl₃, the formula display lines), Typst's table cells with their text back, and lines
  wrapped anew around them.
- **A test page** to HTML, GFM, txt, ascii (`H_2O`, `-->`, `^(15)N`), Typst and `.pptx`: each shows the chemistry.
- **Packaging:** the wheel, installed in a fresh virtual environment, builds `.docx` and `.html` with `\ce`. The
  wheel and `pdfmd.pyz` both hold `pdfmd_lua/chem_client.lua` and `chem.lua`.
- **nulabreport smoke test** on v3.28.9: 94 checks pass.

### Tests

- `tests/test_chem.py`:
  - `CommandLists`: the three lists agree;
  - `Routes`: HTML, GFM, txt, ascii and Typst through pdfmd, with no `pdfmd-chem` key in a standalone Markdown file;
  - every fixture formula through Pandoc's Typst and plain writers, with no TeX left over (the ones text shows as
    text aside);
  - a reaction scheme is left whole.
- Full suite: Pandoc 3.12, 1039 tests OK; Pandoc 3.1.3, 1039 OK.

## v3.28.9 — 2026-10-12

Pre-edit state: commit `2846890` (v3.28.8).

Stage 6 A, third step: the LaTeX filter uses the converter.

### Changed

- **`\ce`, `\pu` and siunitx in Word, OpenDocument, Typst, WeasyPrint and Calibre output come from `pdfmd_chem`.**
  The filter's own Lua translators are gone.
  - **How it runs:**
    - A first pass collects every such command of the document: in text, in `$...$`, in `\[...\]` and in equation
      environments.
    - One `python3 pdfmd_chem` call converts them all.
    - The collect run's answers are kept in a file for the render run, which therefore makes no call and gets the
      same answers.
    - A command met later (a profile's table, an `\input` file) is asked for on its own.
  - **Settings:** pdfmd passes its own Python and the document's preamble, which the filter used to get only with a
    house-style profile. The converter reads the preamble's `\sisetup`, `\DeclareSIUnit` and unit shortcuts, and
    those of the user's own packages it loads: nulabreport's `group-separator={,}`, `\molar`, `\gml`. These are
    found with one kpsewhich call, read one level deep, and never TeX Live's own.
  - **If Python cannot be run:** one WARN, and LaTeX draws the formulas as before.
  - **Where an equation cannot be shown** (WeasyPrint's plain math), a formula with words over its arrow stays text:
    `A ⟶ (Δ) B`.

What changes in a document:
- the siunitx abbreviations (`\mL`, `\mol`, `\uL`) inside math are converted; before, they were pictures;
- a bond is a minus sign (`C−H`, `R₂CH−O−Cl`, as mhchem sets it), not a hyphen, and a bond at the end is a bond
  (`-COO-`), not a charge;
- isotopes are `¹⁵N` and labelled arrows are equations Word edits (`\overset`), not pictures;
- in text, a number and its unit, and digit groups, are separated by a narrow no-break space (U+202F, as siunitx's
  `\,`; Times New Roman and STIX Two have it), not a full one;
- in an equation, Word's own operator spacing replaces the translator's explicit spaces.

Typst no longer prints `$\ce{CO2}$` as "C O2": it is CO₂.

Checked through pdfmd, LR4-5 to `.docx` on Pandoc 3.12 and 3.1.3, against v3.28.8:
- **Pictures:** the same (23, and 24 with Pandoc 3.1.3).
- **Native pieces:** the same, 24 formulas and 191 LaTeX pieces made native.
- **WARN lines:** none, before and after.
- **Text:** every paragraph's text, scripts marked, compared. Only two kinds of change, both above: 51 bonds
  hyphen → minus, and 22 equations without the explicit spaces.
- **Time:** a warm build is 4.0 s, against 3.4 s before.
- **Other outputs:** `.odt`, `report#discussion` and the LibreOffice PDF were built and looked at (page 2 beside
  the LaTeX PDF). So were Typst, WeasyPrint and Calibre PDFs of a test page; Calibre's was looked at: CO₂, H₂O,
  25 mL, Δ over the arrow.

### Tests

- `tests/test_office_latex.py`, `Translators`, now through the converter:
  - mhchem and siunitx in math, with the old cases plus a bond at the end, chemfig left to LaTeX and an
    abbreviation;
  - `\ce` in text as runs;
  - one call for a whole document;
  - an arrow with words as text where math is plain, as an equation where it is MathML;
  - without Python: one WARN, the build goes on, and the `\ce` is left to LaTeX.
- Full suite: Pandoc 3.12, 1034 tests OK; Pandoc 3.1.3, 1034 OK. One test first failed on 3.1.3: it asked for
  `--math-method`, which 3.1.3 does not have. It now asks for the option each Pandoc has, as pdfmd does.

## v3.28.8 — 2026-10-11

Pre-edit state: commit `26b37f8` (v3.28.7).

Stage 6 A, second step: the converter itself. It is added and tested on its own; the LaTeX filter switches to it in
the next version.

### Added

- **`pdfmd_chem/`, LaTeX's chemistry and units for the outputs LaTeX does not make.** It gives text runs (text,
  subscripts, superscripts) for running text and math TeX for an equation.
  - **`siunitx.py`** follows siunitx 3 for `\num`, `\qty`/`\SI`, `\unit`/`\si`, `\ang`, `\numrange`/`\qtyrange`/
    `\SIrange` and `\numlist`/`\qtylist`/`\SIlist`:
    - digit groups from five digits on, the decimal part included (`0.000 123 45`);
    - the decimal marker as set, `1,5` read as `1.5`;
    - `× 10` exponents, the compact uncertainty (`1.23 +- 0.04` is `1.23(4)`), comparators (`\sim 5`, `<5`) and
      signs;
    - `per-mode` power or symbol, and no space before `\degree`;
    - the abbreviations (`\mL`, `\mol`, `\uL`: the LaTeX filter's translator knew none of them);
    - the document's `\sisetup`, `\DeclareSIUnit` and unit shortcuts (nulabreport's `\gml`, `\molar`).

    What siunitx itself refuses (`\num{2 x 3}`), or a unit it does not know, is left to LaTeX.
  - **`render.py`** writes what `pdfmd_mhchem` parses as runs and math. It works from mhchem's parse, not its TeX,
    which is full of phantoms that Word does not take.
    - A mass or atomic number before a symbol is in Unicode script digits (¹⁴N): in Word and LibreOffice a script
      with nothing before it is an empty box.
    - An arrow with words over or under it is an equation (`needs_math`), since text cannot set words over an
      arrow. It is written with `\overset`/`\underset`, because Pandoc's math converter has no `\xrightarrow`. So
      the old translator's labelled arrows were pictures in Word.
    - A `\ce` inside `$...$` inside a `\ce` is converted too.
    - Two subscripts in a row (`CO3^2-_{(aq)}`) are joined into one, which TeX requires.
    - chemfig's drawings (`\chemfig`, `\schemestart`...) are left to LaTeX.
  - **`batch.py`** is one process per document: `python3 pdfmd_chem` reads a JSON request (the preamble, then every
    command) and writes the answers, in 0.09 s.

Checked:
- **siunitx:** 268 commands give what siunitx 3.4.14 prints (LuaLaTeX, then pdftotext, spaces left out), with
  siunitx's defaults and with nulabreport's `\sisetup`. That is 536 of 536; the 269th, `\num{2 x 3}`, is refused, as
  LaTeX refuses it. The commands are 228 from the author's reports and 41 more.
- **mhchem:** 482 of 504 formulas (the 388 real ones and mhchem's tests) have mhchem's structure (text, scripts,
  arrows, labels). 18 differ on purpose, as the isotopes, the joined subscripts and the converted inner `\ce` above.
  4 are left to LaTeX: a `\chemfig` inside a `\ce`, a `\frac` in a subscript, and two of mhchem's rarer bond
  styles.
- **Equations:** the math of every formula not left to LaTeX (763) becomes MathML through Pandoc's converter on
  Pandoc 3.12 and 3.1.3, so it is an equation in Word.

### Tests

- `tests/test_chem.py`:
  - siunitx against `tests/fixtures/chem/siunitx-latex.json` (LaTeX's own output);
  - spacing and scripts, the preamble's settings, math, refusals;
  - chemistry: the translator's old mistakes, arrows that need math, nested `\ce`, units;
  - every fixture formula through Pandoc's converter;
  - the batch process.
- Full suite: Pandoc 3.12, 1030 tests OK; Pandoc 3.1.3, 1030 OK.

## v3.28.7 — 2026-10-11

Pre-edit state: commit `0749bd4` (v3.28.6).

Stage 6 A begins: one converter for mhchem's `\ce` and `\pu` that every output will use. In this version it is
added and tested on its own; no build uses it yet.

### Added

- **`pdfmd_mhchem/`, a Python port of mhchemParser 4.2.1.** This is Martin Hensel's parser of mhchem's `\ce` and
  `\pu`, the one MathJax and KaTeX use. `to_tex("H2O")` gives the TeX LaTeX's mhchem makes of `\ce{H2O}`.
  - It is a translation of the TypeScript, statement by statement, so it parses as mhchem does. That covers the
    bond-or-charge rules, arrows with labels, isotopes, states, oxidation numbers and `\pu`'s digit groups.
  - It keeps mhchemParser's Apache License 2.0 (`pdfmd_mhchem/LICENSE`, the notice in `parser.py`). pdfmd's licence
    line becomes `MIT AND Apache-2.0`.
  - The wheel ships it, and so does `scripts/build_zipapp.py`'s `pdfmd.pyz`.
  - No new dependency: node is used only to check the port in development.
  - Decided with the author: a port inside pdfmd under its own licence, rather than an optional package of its own.
    No Python port existed anywhere, and an optional one would have meant keeping a second parser as the fallback.

Why: the audit of the LaTeX filter's own Lua translator compared 388 distinct `\ce` from real lab reports with
mhchem:
- 372 come out alike;
- 9 come out wrong (a bond at the end read as a charge, `-COO-` → COO⁻; an arrow's label left as text,
  `->[NaBH4]`; `...` as `···`);
- 7 cannot be read at all (`^15N`, `PP_i`, `(CH2O)_n`, `H_nA`).

Checked:

| Inputs | Same TeX as the JavaScript original |
|---|---|
| mhchemParser's own test suite | 117 of 117 |
| `\ce` of real lab reports | 388 of 388 |
| random strings of chemistry tokens, errors included (5000 `\ce`, 2000 `\pu`) | 7000 of 7000 |

### Tests

- `tests/test_mhchem.py` checks the port against fixtures holding the original's answers:
  - `tests/fixtures/mhchem/upstream.json`: mhchem's own tests;
  - `documents.json`: the real formulas, chemistry only;
  - `odd.json`: 800 of the random inputs with the 7 mhchem rejects.

  It also has examples, the licence notice, and `AgainstTheOriginal`, which compares 3000 fresh random inputs with
  the JavaScript itself. That last test is development only: it runs with `PDFMD_MHCHEM_NODE` set to a
  `node_modules` folder that has `mhchemparser@4.2.1`, and is skipped otherwise.
- Full suite: Pandoc 3.12, 1016 tests OK; Pandoc 3.1.3, 1016 OK (the node check skipped).

## v3.28.6 — 2026-10-11

Pre-edit state: commit `d111afc` (v3.28.5).

### Fixed

- **A PDF's Title lost the LaTeX in a title.** For LR4-5's `Reduction of \emph{trans}-Cinnamaldehyde`, the Title read
  "Reduction of -Cinnamaldehyde". Pandoc makes `title-meta`, which hyperref writes as the LaTeX PDF's Title, from the
  title as plain text, and leaves raw LaTeX out. A part built alone (`report#discussion`) had the same gap in every
  output: nulabreport's filter takes the title out and keeps a `title-meta` it flattens the same way, and 3.28.5's
  properties used it. `pdfmd_lua/title_meta.lua` now reads the LaTeX first ("trans"), for the authors too
  (`author-meta`, "A; B").
  - It runs only when the title or the authors have a backslash, and before the document's own filters. A filter that
    keeps `title-meta` when it is set (nulabreport's) therefore finds it right, and nulabreport needs no change.
  - A `title-meta` or `author-meta` of the document's own stays.
  - It is added at every build site where pdfmd adds its page-break filter: one document, the native-bibliography
    route, LibreOffice, Typst/WeasyPrint/Calibre, and `-r` (both).
- In a Word or OpenDocument file, `title-meta`, `author-meta` and `pagetitle` are no longer custom properties of their
  own. They are Pandoc's variables for a PDF's or a page's properties and only repeated the Title and Author.

Checked through pdfmd, LR4-5's Title:

| Output | Before | After |
|---|---|---|
| LaTeX PDF (LuaLaTeX), whole and `report#discussion` | "... Reduction of -Cinnamaldehyde ..." | "... Reduction of trans-Cinnamaldehyde ..." |
| `report#discussion` with Calibre, WeasyPrint or Typst, and to `.docx` | "-Cinnamaldehyde" (3.28.5) | "trans-Cinnamaldehyde" |

- The whole LaTeX PDF is 29 pages, with no `??`.
- The `.docx`'s 42 links all reach a bookmark, and no path is left in it.

### Tests

- `tests/test_office_latex.py`, `Properties.test_a_latex_pdfs_title_keeps_its_latex`, through `pdfmd --to latex`:
  - `pdftitle` and `pdfauthor` keep the LaTeX's words;
  - so does a document filter that takes the title out and keeps `title-meta`;
  - a title without LaTeX gets no filter.
  It fails on `d111afc`.
- `test_word_and_opendocument` also checks for no `title-meta` property.
- Full suite: Pandoc 3.12, 1007 tests OK; Pandoc 3.1.3, 1007 OK.

## v3.28.5 — 2026-10-11

Pre-edit state: commit `9f7fd88` (v3.28.4).

### Fixed

- **A Word, OpenDocument or PowerPoint file held folders of the machine that built it.**
  - **Custom properties:** Pandoc writes every metadata key it does not know into the file's custom properties
    (File › Properties). pdfmd hands its Lua filters their settings that way:
    - the LaTeX filter's `pdfmd-office-path`, `-profile`, `-fragments`, `-labels`, `-report` and `-preamble`;
    - the diagram and raw filters' `pdfmd-raw-cache` (the cache folder, with or without the LaTeX filter, `.pptx`
      included).

    So a file passed on carried the home folder, with the user's name in it, and temporary paths. These keys, and
    every other `pdfmd-` key (`pdfmd-options` included: settings for pdfmd, not properties of the document), are now
    taken out of the finished file. The document's own keys stay, numbered from 2 again as Word numbers them.
  - **Picture descriptions:** Pandoc also writes a picture's source into its description in Word and PowerPoint. For
    a picture the LaTeX filter drew, that is a file in pdfmd's cache (19 pictures in LR4-5). A description naming a
    file under pdfmd's cache, the temporary folder or the home folder now keeps the file's name alone. A relative path
    of the document's own (`tlc/contour/plate-3_contour.png`) is left as it is.
  - **Where:** one step after every office build (`office_finish`), the LaTeX filter's or not, `-r` included; an
    `.odt`'s `mimetype` stays first and uncompressed.
  - **Files already sent:** a `.docx` or `.odt` made with the LaTeX filter before this version has these paths in its
    properties; one with a mermaid/dot/d2 block, a `.pptx` too.
- **A house style's cover took the title and author out of a PDF's properties.** nulabreport's office profile draws
  its own cover and takes `title` and `author` out of the metadata, so that the writer does not print them a second
  time. The LaTeX filter now keeps what the document had (or `title-meta`/`author-meta`, which a partial build's
  filter leaves), as plain text with LaTeX read (`\emph{trans}` is "trans"), and hands it on per output:
  - **HTML** (Calibre, WeasyPrint): `pagetitle` and `author-meta`, as raw HTML. Pandoc writes its own literally, but
    wraps a metadata value at 72 columns, and WeasyPrint kept those line breaks in the PDF's Title.
  - **Typst:** `#set document(title: ..., author: ...)` at the start of the body. In `header-includes` it would be
    undone: Pandoc 3.12's template sets `document(title: none)` after them. Typst takes it after content from 0.12
    on (before, the build would stop), so pdfmd passes it only when `typst --version` says 0.12 or later. It is also
    left out in columns, where Pandoc 3.1.3's template puts the body in a container that Typst refuses it in.
  - **Word and OpenDocument:** the filter's report, from which pdfmd fills an empty Title and Author (several authors
    `A; B`). LibreOffice's PDF takes them from there.

Checked through pdfmd, LR4-5 (`title:` with `\emph{trans}`, one author):

| Output | Title, before | Title, after (all with the author) |
|---|---|---|
| `-e calibre` | `report`, by `Unknown` | the full title, "trans-" kept |
| `-e weasyprint` | `report` | the same |
| `-e typst` | none | the same |
| `-e soffice` | none | the same |
| `.docx`, `.odt` (Pandoc 3.12, and 3.1.3) | empty | the same |
| `report#discussion`, Calibre | `.report.pdfmd-section-h79hcvt9` (a temporary file's name), by `Unknown` | `... Reduction of -Cinnamaldehyde ...` (see below) |

- A scan of every part of each `.docx`/`.odt` finds no folder and no `pdfmd-` key. The only `pdfmd-` strings left
  are the names `media/pdfmd-N.svg` of the drawn pictures' SVGs.
- The `.docx`'s links still all reach a bookmark (42 of 42, Pandoc 3.12 and 3.1.3).
- `-r` to `.docx`, `.odt` and `.pptx`: the same.
- The LibreOffice PDF's Info has no other key.

Not fixed here:
- A partial build's title loses "trans": nulabreport's filter leaves `title-meta` flattened by
  `pandoc.utils.stringify`, which drops raw LaTeX. That is nulabreport's fix to make.
- The LaTeX PDF's own Title has the same gap ("Reduction of -Cinnamaldehyde"), from before this version.
- `-e typst` with Pandoc 3.1.3 stops on `#cite("key")`, which Typst 0.15 no longer takes. This is also the case
  with v3.28.4.

### Tests

- `tests/test_office_latex.py`, new class `Properties`, through a cover profile that takes the title and authors out:
  - a `.docx` and an `.odt` keep the title and authors in their properties and hold no folder or `pdfmd-` key;
  - HTML's `<title>` and author meta, a long title on one line;
  - Typst's `#set document`, only when pdfmd says the Typst takes it and not in columns;
  - a document that keeps its own title is left alone;
  - a partial build's `title-meta`;
  - no `pdfmd-` key in a `.docx` or `.pptx` with the LaTeX filter off (a mermaid block);
  - `finish_properties` fills only what is empty;
  - a picture's folder out of its description;
  - a Calibre PDF's Title and Author.
- On `9f7fd88`'s code seven of the eight fail. The one that passes checks what must not change: a document keeping
  its own title.
- Full suite: Pandoc 3.12, 1006 tests OK; Pandoc 3.1.3, 1006 OK.

## v3.28.4 — 2026-10-11

Pre-edit state: commit `fd9f00d` (v3.28.3).

### Fixed

- **A reference to what LaTeX labelled led nowhere** in Word, OpenDocument and HTML output, and in Typst it became
  plain text. The LaTeX filter makes `\cref{x}` a link to `#x`. Before 3.28.2 this went unseen. Once 3.28.2 gave a
  named `-e weasyprint` the filter, WeasyPrint printed `ERROR: No anchor #fig:… for internal URI reference` for each
  such link (19 lines for LR4-5).
  - **The cause:** the label was dropped on the way:
    - a raw `\label{}` in a Markdown caption (LR4-5's tables: `` : caption `\label{tbl:rf}`{=latex} ``);
    - a block drawn as a picture (nulabreport's `\irspectrumpage`, a `sidefigure` in an `\input` file);
    - every line of an equation but the first;
    - in OpenDocument, any equation, since its label sat on a Div and that writer writes no Div's identifier.
  - **The fix:** each such `\label` is now an anchor where it stands, an empty span with the label as its identifier.
    That is a bookmark in Word and OpenDocument, an id in HTML and a label in Typst. A figure environment drawn
    whole keeps its first label as the figure's and the others (subfigures) as anchors. An equation's labels are
    anchors in its cell, and the Div around it is gone. A caption's own label gives the caption LaTeX's number.
  - In HTML and Typst an anchor whose label the document already carries is dropped, and so is a second anchor of a
    label. This includes Pandoc's LaTeX reader's own empty span beside a figure's identifier: Typst no longer warns
    "1 label on more than one element (fig:tlc)" for LR4-5, and HTML has no id twice. Word and OpenDocument keep
    that span, since their writers do not always write a figure's identifier (OpenDocument never, Word not with
    Pandoc 3.1.3).
  - OpenDocument writes no bookmark for a table's, a figure's or a div's identifier. Such an element gets an anchor
    in its caption, or else in its first line or first cell. This covers a `{#tbl:x}` table, a nulabreport
    `\chemicals` table and the references' entries, so a citation's link now leads to its entry.
- **A picture sized by one side stopped the Word or OpenDocument build with Pandoc 3.1.3.** An `\includegraphics[height=...]`
  read through Pandoc's LaTeX reader (LR4-5's TLC plates) failed with "attempt to index a nil value (field 'image')":
  Pandoc 3.1.3 has no `pandoc.image`. Without it the size is now left to the writer, which keeps the aspect ratio.

Not done: the one-line warning for WeasyPrint's links to missing anchors, planned in 3.28.3's notes. The anchors
left LR4-5 with none in any output, and such a check would have to run after the LaTeX filter (the order 3.28.2 had
to fix for Typst).

Checked through pdfmd, LR4-5:

| Output | Links without a target, before | After |
|---|---|---|
| `.docx`, Pandoc 3.12 | 12 of 42 | 0 |
| `.docx`, Pandoc 3.1.3 | (the build stopped) | 0 |
| `.odt`, Pandoc 3.12 and 3.1.3 | 28 | 0 |
| `-e weasyprint` | 19 `No anchor` lines | none |

- `-e typst` builds with no warning.
- `-e calibre` builds (28 pages).
- Caption numbers agree with the LaTeX PDF (Table 1 to 14).

### Tests

- `tests/test_office_latex.py`, new class `Anchors`, on Pandoc 3.12 and 3.1.3:
  - a caption's `\label` in Word and OpenDocument, with LaTeX's number;
  - both labels of an `align`;
  - OpenDocument reaching a div, a figure, a table and a citation;
  - no label twice in HTML or Typst;
  - a height-sized picture.
- `Pictures`: a drawn block keeps both its labels.
- On `fd9f00d`'s filter the six fail on Pandoc 3.1.3, and the five but the picture on 3.12.
- Full suite: Pandoc 3.12, 998 tests OK (14 skipped); Pandoc 3.1.3, 998 OK (24 skipped).

## v3.28.3 — 2026-10-11

Pre-edit state: commit `cb7adde` (v3.28.2).

### Fixed

- **"Table 1. Table 1: A table" with a Pandoc before 3.8.2.** Up to 3.8.2 a table caption's `{#tbl:x}` is caption text,
  not the table's identifier. pandoc-crossref (0.3.16 with Pandoc 3.1.3) numbers the caption and puts the label on a
  Div around the table, so v3.28.1's check, which reads the table's own identifier, did not see it. The LaTeX filter
  now takes its number back when such a Div holds the table and crossref has numbered the caption. The table still
  counts, and a Div's label alone takes no number away. This was found by the full suite on Pandoc 3.1.3, where
  v3.28.1's simulated test could not work (the test now needs 3.8.2). It was checked with the real pandoc-crossref
  0.3.16 built for Pandoc 3.1.3.
- **Captions in a Calibre or WeasyPrint PDF.** Pandoc's own page style is for a screen. It makes a table a full-width
  block that scrolls sideways (`display: block; overflow-x: auto`) and lets a word break anywhere.
  - Calibre (3.28.0) cut a caption off at the width of a narrow table: "Table 1: Label", "Table 2: Secon".
  - WeasyPrint (since it became an engine) set the caption a syllable a line.
  - While that style is in (no `--css` of your own), a table is now a table again. It sits at its natural width,
    centred, as LaTeX's longtable sets it.
  - Calibre's caption is up to 4in wide (longtable's `\LTcapwidth`); a narrower table widens to it.
  - WeasyPrint has no `max-content` width, so its caption is as wide as the table. The table is at least 4in wide,
    and the caption is centred and breaks between words.
  - A numbered equation (the LaTeX filter's three-cell table) spans the line with its number at the margin, without
    a table's rules. Before, it shrank to its content.
  - Calibre gets these rules in its `--extra-css`, only when the page's `<head>` has Pandoc's table style.
    WeasyPrint gets them from `pdfmd_lua/weasyprint.lua`, in `header-includes`, so the document's own
    header-includes stay. An `--include-in-header` replaces them, as it replaces the document's own.
  - Decided here: natural width rather than Pandoc's `width: 100%`, as the LaTeX PDF has it. Column widths a document
    gives (a long pipe-table divider) were already lost under Pandoc's style in both engines (the inner table is
    `auto` wide) and still are; honouring them is left to the CSS stage.

Checked through pdfmd:
- Pandoc 3.1.3 with pandoc-crossref 0.3.16, a `{#tbl:t}` table to `.docx`: "Table 1: Labelled", "Table 2: Second".
  The same document with `-e calibre`.
- A narrow table with a long caption, a wide table and a numbered `equation`, with `-e calibre` and `-e weasyprint`
  on Pandoc 3.12 and 3.1.3. Looked at the rendered pages; `pdftotext` reads every caption whole.
- The filter adds its style with Pandoc's own, keeps a document's `header-includes` (one or a list), and adds
  nothing with `--css` or `document-css: false`, on both Pandocs.

### Tests

- `tests/test_office_latex.py`: the label on a Div around the table, as crossref puts it before Pandoc 3.8.2 (every
  Pandoc). The simulated `{#tbl:t}` caption test needs 3.8.2. The new test spells its no-break spaces as ` `; the
  older ones in the file carry them as invisible characters.
- `tests/test_calibre.py`: the table style only while Pandoc's own is in; a narrow table's caption is whole in the PDF.
- `tests/test_engine_filters.py`: weasyprint.lua's style (not with `--css`, not for Typst, the document's
  header-includes kept); a narrow table's caption is whole in a WeasyPrint PDF.
- The five new tests fail on 3.28.2's code (four failures, one error).
- Full suite: Pandoc 3.12, 992 tests OK (14 skipped); Pandoc 3.1.3, 992 OK (24 skipped).

Also checked: LR4-5 with `-e calibre` is 28 pages instead of 35, with the same text (about 10,800 words). Under
Pandoc's style each table and equation was one unbreakable block (a scrolling element is printed whole), so it
jumped to the next page and left half-empty pages. Tables now break across pages, the header row repeated.

## v3.28.2 — 2026-10-11

Pre-edit state: commit `13529ad` (v3.28.1). The author's choice: Typst and WeasyPrint named with `-e` run the LaTeX
filter, like Calibre, rather than only warning about what they drop.

### Changed

- **A Typst or WeasyPrint PDF no longer drops the document's LaTeX.** The LaTeX filter now runs whenever the document
  has LaTeX these engines would drop, whether they were named (`-e typst`, `-e weasyprint`, `pdf-engine:`) or reached
  in the chain. The filter makes `\ce`, `\SI` and `\cref` native and draws the rest with LaTeX, or lists what it could
  not. Before this, `-e weasyprint` on "Water is \ce{H2O} and" printed "Water is and", and every tikzpicture was left
  out, without a word (Pandoc only noted the `\ce` it found inside math).
  - **What counts** (`latex_dropped`): a raw ```` ```{=latex} ```` block, a LaTeX command in the text, or chemistry and
    units inside math (`\ce`, `\SI`, `\si`, `\qty`, `\num`..., which texmath does not know). Front matter and code are
    not looked at. A document with only ordinary math is built as before: the filter rewrites math for Word (a long
    display is broken at its equals signs, `$5$` becomes text), and that is not wanted where nothing would be lost.
  - **References** take LaTeX's numbers, as in a Word file (`office: {labels}`, `auto` by default: one cached LaTeX
    build of the document when it refers to labels), unless LaTeX is what failed. In `-r` report mode, labels stay
    off, as for Calibre.
  - **How to keep Pandoc's own behaviour:** `raw: {typst: [typst]}` (or `html:`) says what that family takes and
    decides first; `office: {latex: off}` and `--no-auto officelatex` turn the filter off. HTML and Typst *files*
    (`-o x.html`, `--to typst`) still use it only on request (`office: {latex: auto}`).
- **`typst.lua` runs last, after the LaTeX filter**, so the references the filter makes are checked as well. LR4-5
  stopped Typst on 18 references to figures and tables it had no label for, and on a label carried twice
  (`fig:tlc`, a drawn figure environment and its own label). `typst.lua` now also keeps a label on its first
  element only, with one WARN, as it already made links to missing labels text.
- **Report mode (`-r`)** gets the filter on the same terms, `typst.lua` (it had neither) and WeasyPrint's plain
  math (since v3.27.12 for one document; a report printed each formula twice as flat text).
- The filter's warning names the output: "LaTeX the Typst output could not express" (it said "Word" for every
  output).

### Fixed

- **A Typst or WeasyPrint run after LaTeX failed never got the filter** (since v3.24.x). The engine loop records a
  failed engine by its TeX family (`luatex`, `xetex`, `pdftex`), and the check looked for engine names (`lualatex`...),
  so it never matched. A document whose LaTeX build failed came out of Typst with its `\ce{H2O}` gone ("Water is here.",
  checked on 3.28.1). Now "Water is H2O here.".

Checked through pdfmd: `-e typst` and `-e weasyprint` on a document with `\ce` in text and in math and two
tikzpictures with no `\usepackage{tikz}`. Both print H2O and CO2 and warn that the two pictures could not be drawn
(before: "Water is and", no warning). A document whose LaTeX fails goes on to Typst with its chemistry kept. LR4-5 with
`-e typst` (copy) builds in 19 s with the numbers and pictures cached: 31 pages and 10714 words, against 24
pages, 9917 words and no scheme or figure on 3.28.1 (LaTeX: 29 pages, 12069 words). Typst sets `$\ce{CO2}$` as "C O2" (spaced letters in math); that is for the `\ce` converter
(stage 6 A), next.

### Tests

- `tests/test_office_latex.py`:
  - a named `-e typst` draws the tikzpicture and prints H2O, unless `raw: {typst: [typst]}` says Typst takes no LaTeX;
  - Typst after a failed LaTeX gets the filter (fails on 3.28.1);
  - `latex_dropped` on what counts (`\ce` in text, `\ce`/`\si` in math, a raw block, an environment) and what does not
    (ordinary math, header-includes in the front matter, code);
  - `office_fallback_wanted` lets the `raw` option decide first, and `latex_failed` knows the TeX families.
- `tests/test_engine_filters.py`: a label on a div and on a heading is kept by the div, with one WARN (Pandoc
  3.12 and 3.1.3).
- Full suite: Pandoc 3.12, 987 tests OK (14 skipped). Pandoc 3.1.3, 986 OK (23 skipped) and 1 failure:
  v3.28.1's caption test, whose `{#tbl:t}` Pandoc before 3.8.2 does not read as the table's label (v3.28.3).

## v3.28.1 — 2026-10-11

Pre-edit state: commit `a2566ad` (v3.28.0).

### Fixed

- **A table caption pandoc-crossref had numbered was numbered again**: "Table 1: Table 1: A table". pdfmd's LaTeX
  filter (`pdfmd_office/office.lua`) puts "Table N. " in front of every table and figure caption, as the PDF prints
  it, and pandoc-crossref runs before it. This affected every `.docx` and `.odt` with a `{#tbl:...}` table, the
  LibreOffice route, Calibre (3.28.0, where it was found), and Typst, WeasyPrint and HTML output with
  `office: {latex: auto}`. In Word files figures were not affected; in HTML (Calibre) a `{#fig:...}` figure is now
  numbered once too.
  - The filter now leaves alone a caption with one of crossref's labels (`tbl:`, `fig:`) whose text starts with
    crossref's title and a number (its `tableTitle`/`figureTitle`, "Table"/"Figure" by default). Such a table is still
    counted, so an unlabelled table after it is "Table 2" as in LaTeX.
  - The same label without pandoc-crossref (not installed, or `--no-auto crossref`) is numbered by the filter as
    before.

Checked through pdfmd: a document with a labelled and an unlabelled table and figure, to `.docx` and with
`-e calibre`, with pandoc-crossref and with `--no-auto crossref`. Each caption carries one number, in the same order
as before.

### Tests

- `tests/test_office_latex.py`: a caption crossref numbered (simulated, and with a custom `tableTitle`) keeps one
  number and the next table counts it; a `tbl:` label without crossref is numbered; and the same with
  pandoc-crossref itself (skipped without a pandoc-crossref built for this Pandoc). The first and the last fail on
  3.28.0.
- `test_office_latex`, `test_office`, `test_docx_tables`, `test_soffice_parts`, `test_engine_filters` and
  `test_calibre` pass. The full suite runs at 3.28.2.

## v3.28.0 — 2026-10-11

Pre-edit state: commit `a8a73a2` (v3.27.28). The first commit of the Calibre line (stage 6 of the plan; the author
approved 3.28 for it, and everything after it stays 3.28.x). Calibre comes before the planned `\ce`/siunitx converter
and the math work, which follow.

### Added

- **`-e calibre`**: Calibre's `ebook-convert` as a PDF engine. It can also be asked for as `-e ebook-convert`,
  `pdf-engine: calibre` or the `--setup` choice. It is used only when named: it is not in the automatic chain (the
  author: try it explicitly first, add it to the chain once it works) and has no number of its own.
  - Pandoc writes one standalone HTML page into a scratch folder (math as MathML, pictures inlined, the same filters,
    citations and fonts WeasyPrint gets) and `ebook-convert` prints it. Calibre draws MathML with its own MathJax.
  - Not an EPUB, as the plan had it: Pandoc splits an EPUB at every top-level heading (`--split-level` takes 1 to 6,
    there is no "never") and Calibre starts each of those files on a new page, so a report got a page per section.
    The EPUB stays the in-between file for e-book outputs (the format router, later).
  - The page is the document's. `papersize`, `geometry`, `margin`, `classoption: landscape` and `lang` are read as
    for a Word file; without them it is Letter with 1in margins, as with LaTeX. Text is 12pt unless `fontsize:` says
    otherwise (a browser's default, as with WeasyPrint). Page numbers go at the foot, and the PDF bookmarks are the
    headings (h1 to h3, the title left out).
  - Calibre's e-book defaults are turned off:
    - font sizes rescaled to its output profile (11pt text came out about twice as large; with no `fontsize`, 15pt);
    - 5pt of margin of its own inside the page's;
    - a page break before every h1/h2, and before headings with "Chapter" or "Section" in them;
    - bookmarks made from the document's links ("1", "the other file", "↩︎");
    - following links into other local files.

    Pandoc's screen styling is reset for paper: a 36em column with 50px of padding, and an off-white page that
    printed as a grey tint (Calibre does not apply `@media print`).
  - LaTeX in the document always goes through the Word route's filter, as for LibreOffice. It is made native (`\ce`,
    `\SI`, `\cref`...) or drawn by LaTeX as a picture, and references take the numbers of a LaTeX build of the document
    (`office: {labels}`, cached). `office: {latex: off}` turns this off. Report mode (`-r`) works the same way, without
    LaTeX's label numbers: they would be the first chapter's only.
  - Qt runs offscreen (`QT_QPA_PLATFORM=offscreen`, unless already set) on macOS and Linux: no window, and no display
    needed on a server.
  - `ebook-convert` is found on PATH, in `calibre.app` (`/Applications` or `~/Applications`), or in `Calibre2` under
    Program Files. If it is missing, the error says how to install Calibre. `--check-dependencies` and `--doctor` list
    it, and `-e`'s help mentions it.
  - A `.html` input with `-e calibre` goes through Pandoc's HTML reader (the direct HTML route keeps its own engines).

Checked through pdfmd:

- **A small document** (math, a table, code, a footnote, a picture, a link): one A4 page at its 11pt, bookmarks
  "Introduction" and "Second section", title and author in the PDF's properties, about 5 s.
- **Page breaks:** `\newpage` breaks, and so does `<!-- pagebreak -->` with `--pagebreak`. A5 landscape with 1cm
  margins lands within 0.5pt.
- **A copy of LR4-5** (nulabreport):
  - 35 pages (LaTeX: 29); every section and subsection is in the bookmarks;
  - the reaction schemes are drawn, `\ce` is text, and reactions, equations and figures are numbered in the text;
  - no `??` anywhere;
  - 188 s with an empty cache (one LaTeX build for the numbers, 19 pieces drawn), 25 s once they are cached.
- **Pandoc 3.1.3** (the oldest supported): the same command and bookmarks.
- **A two-chapter `-r` report.**

Not done, or known:

- The PDF's title is the HTML page's `<title>`. A document whose title nulabreport builds itself (no `title:`) gets
  the file name, "report", where LaTeX's PDF has the real title.
- macOS's STIX Two Text (pdfmd's default main font) is a variable font, and Calibre embeds it as Type 3. The text
  stays searchable and sharp, but some print shops object. A static font in `mainfont:` avoids it.
- Whether Calibre's icon still bounces in the macOS dock is open (an item of the plan).
- **Found here, fixed in 3.28.1:** pdfmd's LaTeX filter numbers a caption that pandoc-crossref has already numbered
  ("Table 1: Table 1: A table"). This affects `.docx`, `.odt`, the LibreOffice route and now Calibre.

### Tests

- `tests/test_calibre.py` (new) covers:
  - finding `ebook-convert` (PATH first, Program Files);
  - using Calibre only when named, the install hint when it is missing, no slides, the `--check-dependencies` line;
  - the Pandoc command it rewrites (html5, standalone, inlined resources, MathML unless the command line chose the
    math);
  - the page options (A5 landscape, 1cm, de-DE; Letter and 72pt by default);
  - a real build, skipped without Pandoc and Calibre: A4, the headings as bookmarks, one page.
- Full suite: 978 passed (14 skipped).

## v3.27.28 — 2026-10-11

Pre-edit state: commit `5a8abaf` (v3.27.27).

### Fixed

The author asked for nulabreport's plot cache to be switched on, on condition that a stored plot is used only while it
still matches what the build would draw. Checked first on copies of LR4-5 and LR3, which turned up four gaps:

- **A report's plots were thrown away by building other documents.** The plot folders were shared by every document
  and the three newest were kept. Every report has its own preamble (its title, its `\LabExperiment`), so building
  three other documents with the plot cache on, even ones without plots, deleted a report's plots. Each document now
  keeps its plot folders in its own cache folder, the newest eight. `pdfmd DOC --clear-cache` now clears that
  document's plots too.
- **A part built alone drew its plots again, in a new folder at every build.** The folder is keyed by the
  preamble, and `report#discussion` adds two things to it:
  - pdfmd's label replay, which names a temporary file;
  - nulabreport's filter drops a part's title.

  So every build of a part had a new folder: LR4-5's Discussion drew its 4 plots again each time, and pushed the full
  build's folder towards the prune. What pdfmd adds to one build only (the replay, the counter markers) is now left
  out of the preamble the plots are keyed by and drawn with (`plot_preamble`). The key also leaves out the title
  (`\title`, `pdftitle`) and ignores line wrapping (`plot_key_text`). LR4-5's Discussion now uses the full build's
  plots.

  A part whose preamble really differs keeps a folder of its own, drawn once and reused from its next build: Pandoc
  writes the citation commands only for a part that cites (LR4-5's Calculations), and table packages only for one
  with tables.
- **A `tlmgr update` kept the old plots.** The engine's version line names only the TeX Live year. The folder's key
  now also takes the size and time of TeX Live's package database (`tlpkg/texlive.tlpdb`, rewritten by every
  install, update and removal; `tex_tree_stamp`). Nothing changes on MiKTeX or without `kpsewhich`.
- **Files of the package's own were not inputs.** A plot job reads 5 files from `~/Library/texmf` besides
  `nulabreport.sty`, which is in the folder's key: nulabreport's vendored chemfig and its `chemicals.tex`. Inputs
  were recorded only under the report's folders. Files under TEXMFHOME and TEXMFLOCAL (`user_tex_trees`) are now
  recorded too, with their SHA-1, like a CSV. Each file is hashed once per build, not once per plot.
- **With `cache: {location: document}` no plot was ever reused.** The plot folder is then under the report's
  folder, so the plot job's own `.tex` (deleted once it has run) was recorded as an input, and every entry was
  dropped at the next build. Files in the plot folder itself are no longer inputs.

`PLOT_CACHE_FORMAT` is 2, so the first build draws every plot once.

Checked on copies of LR4-5 and LR3 (in a cache folder of their own):
- LR4-5 cached against uncached: 0 of 12315 words moved by more than 0.05 bp. As pictures, the largest blurred
  difference is 47/255, which is anti-aliasing.
- LR4-5's Discussion with the full build's plots, against the Discussion uncached: 0 of 4628 words moved; 45/255.
- Two full builds in a fresh cache used one folder, and the Discussion used the same one.
- LR3 built after LR4-5 left LR4-5's folders alone.
- With `--cache-location document`, LR3's second build stored nothing. 3.27.27 drew all 11 plots again.
- LR4-5's timings (a busy machine, so roughly): 98 s with no cache, 55 s with the `.aux` cache, 30-45 s with both.
  The build that stores the plots took about 140 s, about 35-55 s of it spent storing 12 plots, four at a time.

### Tests

- `tests/test_plot_cache.py`:
  - a part's own headers leave the folder unchanged;
  - each document keeps its folders;
  - the TeX Live stamp;
  - the user's trees are inputs and TeX Live's are not;
  - a cache beside the document keeps its entries;
  - TEXMFHOME/TEXMFLOCAL as kpsewhich gives them.
- `tests/test_compat.py`: the zipapp test expects PyYAML and pypdf inside the file only when the Python running it
  has them, as the build script does. Homebrew's Python 3.14.8 has no pypdf, so the test failed there.

## v3.27.27 — 2026-10-11

Pre-edit state: commit `8e7053b` (v3.27.26).

### Added

- **A citation style named by its URL is fetched by pdfmd** (`remotecsl`), at the author's request. `csl:
  https://.../ieee.csl` needs the network and Pandoc's HTTP support, which a Homebrew Pandoc lacks: the author's
  `prelab1` stopped with "pandoc was compiled without HTTP support". pdfmd now fetches the style once into its cache
  (`csl/` there, fetched again after 30 days) and hands Pandoc the file (`--csl`, beside `--citeproc` on every route).
  When the fetch fails, it tries in this order:
  1. the copy it fetched before, however old (a NOTE);
  2. a style of the same file name in Pandoc's own `csl/` folder, with a WARN;
  3. `pdfmd-options: {csl-fallback: default}` (the default): Pandoc's default style, with a WARN;
     `csl-fallback: error` stops instead. Under `--strict` the WARNs fail the build as usual.

  A style the command line names (`--csl`, `-M csl=...`) is left alone, and so is everything with
  `--no-auto remotecsl`. `csl-fallback` is a `pdfmd --setup` row (Citations).
- **https fetches retry with the system's certificates** (`open_url`; `_open` in `pdfmd_images/remote.py`). A
  python.org Python on macOS has no CA certificates until its "Install Certificates" step runs, so every https fetch
  failed with CERTIFICATE_VERIFY_FAILED. That covers the style, remote images and `--install` downloads. pdfmd now
  tries once more with `/etc/ssl/cert.pem` (or the Linux bundles, or certifi). Found on `prelab1` once the author's
  `python3` became the python.org one after a Homebrew upgrade.

Checked on a copy of `prelab1`: it fetched the IEEE style from GitHub and built with lualatex. Without the
certificate retry, it built with the author's own `ieee.csl` from Pandoc's folder, with a WARN.

### Tests

- `tests/test_remote_csl.py`:
  - which `csl:` counts, and what is left alone;
  - fetched once and kept; offline, the old copy, then Pandoc's own style of the same name, then the default style or
    an error;
  - the certificate retry, and no retry for other errors;
  - a build with an unreachable style, which works with `remotecsl` and fails with `--no-auto remotecsl`.

## v3.27.26 — 2026-10-11

Pre-edit state: commit `3d303ed` (v3.27.25).

### Fixed

- **A `-r` report's PDF printed "N/A" for front-matter values such as `experiment:`.** For nulabreport, the first
  chapter's `experiment:`, `group:`, `course:` (and a package's own `latex-keys`) become
  `\renewcommand{\LabExperiment}{...}` lines (`document_latex_definitions`, in `document_header_file`). A single
  document gets them, and so does a report built `--to latex`. The report's PDF route never made that header file, so
  the macros kept their defaults: "Experiment N/A done" for `experiment: 7`. Noted as a known gap in 3.27.18; the PDF
  route now adds the header file under the same condition, last, and `keep_header_includes` knows it carries the
  chapter's own header-includes.

### Tests

- `test_header_includes.Building.test_a_report_takes_the_first_chapters_macro_values`: a `preamble.tex` default of
  `N/A` and `experiment: 7`. A `-r` PDF printed "Experiment N/A done" on 3.27.23 and now prints "Experiment 7 done".

## v3.27.25 — 2026-10-11

Pre-edit state: commit `3f715f3` (v3.27.24).

### Fixed

- **A `preamble.tex` that defines an environment around a tikzpicture was left out.** Preamble discovery refuses a
  file that is a TikZ picture rather than a preamble, but it tested for any `\begin{tikzpicture}`. So
  `\newenvironment{plot}{\begin{tikzpicture}}{\end{tikzpicture}}` (or a `\newcommand` that draws) made the whole
  preamble "a picture": it was left out with no `AUTO TEX` line, and the build stopped at the environment's first use.
  Found while writing 3.27.23's tests. Now only a tikzpicture at the top level, outside every brace group (comments
  aside), makes a file a picture (`top_level_tikzpicture`).

### Tests

- `test_header_includes.PreambleWithAPicture`:
  - definitions and a commented mention are preambles, while a bare picture and a full document are not;
  - a build with such a `preamble.tex` succeeds and announces it.

## v3.27.24 — 2026-10-11

Pre-edit state: commit `927c794` (v3.27.23).

### Added

- `--config` is another name for `--setup` (the settings menu), at the author's request. `--setup fancy` and
  `--config fancy` are the same; `--show-config` and `--init-config` are unchanged.

### Tests

- `test_setup`: `test_config_is_another_name_for_setup`.

## v3.27.23 — 2026-10-11

Pre-edit state: commit `6288eeb` (v3.27.22).

### Changed

- **The draft pass of `seed-labels: draft` does not draw pictures.** A part built alone (`report#discussion`) with
  `seed-labels: draft` gets the other parts' numbers from one LaTeX pass over the whole document, and most of that
  pass was drawing: nulabreport's pgfplots IR spectra, chemfig structures and reaction schemes. None of them steps a
  counter, because a figure's `\caption` is outside its picture. `DRAFT_SKIP_PICTURES`, put before
  `\begin{document}` for that pass only, skips:
  - a `tikzpicture` (pgfplots inside it too), up to its literal `\end{tikzpicture}`;
  - `\chemfig` and a chemfig `\schemestart ... \schemestop`;
  - images (graphicx's `draft`).

  On LR4-5 (copies): 44.8 s for the pass, now 12.9 s, with all 170 labels at the same numbers. Built part by part, LR3
  (8 parts), LR4-5 (8 sections) and the split-report demo (8 parts) gave text identical to the full pass's.

  Pages move when pictures are not drawn, so the seed leaves the labels' page numbers out: `\pageref` and `\cpageref`
  into what was left out print `??` (`label_without_page`; cleveref's page group keeps its form).
- **A pass that went wrong runs again with the pictures** (`draft_skip_problem`), in any of these cases:
  - a picture whose `\end{tikzpicture}` is hidden in a macro (a house style's environment around a tikzpicture): the
    skip meets the end of the surrounding environment or of the document first, and writes `PDFMD-DRAFT-SKIP-FAILED`
    to the log;
  - a LaTeX error that names the skip or a `tikzpicture`;
  - a `\label` of the document's body missing from the pass's `.aux`.

  The document's own errors do not count, since the pass with pictures would have them too. `--verbose` says which
  pass ran. `--no-auto draftpictures` always draws them. It needs LaTeX 2020-10 (`\AddToHook`); older kernels draw as
  before.

### Found (not changed here)

- `is_latex_preamble` refuses a `preamble.tex` that contains `\begin{tikzpicture}`, so it never mistakes a TikZ
  picture file for a preamble. That also refuses one that defines an environment around a tikzpicture: it is silently
  left out, and the build fails at the first use. Queued.

### Tests

- `test_labels.QuickDraft` (needs TikZ):
  - a literal tikzpicture: the numbers stay, the pages print `??`, and `--verbose` says the pictures were not drawn;
  - a package's `mypic` environment around a tikzpicture: the full pass runs, with exact pages;
  - `--no-auto draftpictures`.
- `test_labels.PagesLeftOut`: plain and cleveref label values lose their page.

## v3.27.22 — 2026-10-10

Pre-edit state: commit `5112eb8` (v3.27.21).

### Changed

- **When two metadata files set the same key, the later one wins for pdfmd's own keys too.** Pandoc takes a later
  `--metadata-file` over an earlier one, but pdfmd read its own keys (`pdfmd-options:`, `margin:`, the engine) from the
  first file that set them. A folder with `metadata.yaml` and `report.yaml` (or `<name>.yaml`, which pdfmd's own code
  calls the override of the shared base) got `report.yaml`'s margins and title, but `metadata.yaml`'s
  `pdfmd-options`. The same split happened with `-y base.yaml -y extra.yaml`. Decided by the author.

  One helper, `metadata_files_by_priority`, now gives the order for every reader of pdfmd's own keys:
  `option_sources` (and through it `first_pdfmd_option`, the stamp), `seed_labels_mode`, `parts_setting`,
  `resolve_embed`, `cache_location`, `cache_settings`, `frontmatter_engine`, `frontmatter_citation_engine` and the
  `margin:` reader. The document's own front matter still comes first, and the global `metadata.yaml` (pdfmd --setup)
  and the config come last.

  None of the author's folders stacks two metadata files that both set `pdfmd-options` (checked: Fall26 has none;
  nulabreport's `metadata.yaml`, `genchem-metadata.yaml` and `prelab-metadata.yaml` are each used alone), so no
  build of theirs changes.

### Added

- `--metadata-precedence later|first`, and `metadata-precedence` in `pdfmd --setup` (Input), at the author's request,
  for anyone the new order would surprise. `first` makes the first file win everywhere: pdfmd reads it first, and
  Pandoc gets the files in reverse (`pandoc_metadata_order`), so it wins Pandoc's keys as well. Either way there is
  one rule for every key. The global metadata file stays the lowest. It is read from the command line and the config
  only, not from a document or a metadata file, since it decides how those are layered.
  `pdfmd --help output` lists it beside `-y`.

### Tests

- `test_setup.Plain`:
  - `test_pdfmd_options_follow_the_same_rule`: `metadata.yaml` + `a.yaml` both setting `seed-labels` and `margin:`;
    `a.yaml` wins both, and a key only the first file sets still comes from it.
  - `test_the_rule_can_be_turned_round`: with `first`, `metadata.yaml` wins Pandoc's `subtitle` and pdfmd's keys;
    the config's `options.metadata-precedence` is read, and a wrong value names the valid ones.
  - `test_the_flag_reaches_pandoc`: a build with `-y metadata.yaml a.yaml` shows `a.yaml`'s subtitle, and
    `metadata.yaml`'s with `--metadata-precedence first`.

## v3.27.21 — 2026-10-10

Pre-edit state: commit `0b4b3a9` (v3.27.20).

### Fixed

- **Documents with no code got the code header (`code_wrap.tex`, fvextra) and the code filter.** The test was one
  regex that took any line starting with a fence, or indented four spaces, for code. So it also counted:
  - the fences of raw blocks (```` ```{=latex} ```` around a `tikzpicture` or `chemfig`, and their closing ```` ``` ````);
  - the front matter's indented YAML (a `references:` list: `    type: article-journal`);
  - a list item's continuation indented four spaces.

  In the A/B check of the author's documents for 3.27.18, 13 of the 16 that got the header had no code block. Five
  proposals and a pre-lab had only a `references:` list; the rest had only raw LaTeX blocks. Until 3.27.18 that header
  threw away their `header-includes`. Since then it is only wasted, but it was still wrong.

  `has_code_block` now skips the front matter, raw `{=format}` blocks (fences and contents) and inline code written
  ```` ```x``` ````. An indented block counts only after a blank line that does not continue a list item. A fenced
  block in a list item (indented) still counts. On the same 16 documents: the three SOC203 references (```` ```r ````)
  and the two CHEM341 midterm guides (bare ```` ``` ```` blocks) keep it; the other 11 do not.

### Tests

- `test_code_blocks.Arguments.test_what_is_not_code`: front-matter YAML, raw blocks, list continuations and inline
  triple backticks are not code; plain, `r`, `{.python}`, `~~~~`, a block after a raw one, a block in a list item and an
  indented block are.

## v3.27.20 — 2026-10-10

Pre-edit state: commit `952195b` (v3.27.19).

### Fixed

- **A part built alone printed a wrong number, not `??`, for a table in an environment of the document's own.**
  nulabreport writes a table as its own `labtabularbt` environment with a `\caption` inside. pdfmd's label scan
  (`pdfmd_labels/scan.py`, the source of a partial build's numbers since 3.26.0) knows `table`, `longtable` and the
  other standard floats, so it did not count that caption, but it still replayed the `\label` in it. Replayed, the
  label took the number of the last thing counted, the section around the table. The split-report demo's Discussion,
  built alone, said "(Section 4, Results)" where the full report says "(Table 1, Results)". The scanner's docstring
  promised `??` for what it cannot see.

  Now a `\label` after a caption the scan could not count is left out until the next step it does count, so the
  reference prints `??`. This covers every package's wrappers, not only nulabreport's. `--seed-labels draft` (a LaTeX
  pass over the whole document) still counts such labels exactly. The build's closing NOTE says how many labels were
  left out, and `--verbose` says so after the scan.

### Not changed (for the author)

- Teaching the scan a document's own wrappers is the next step: a declaration in `pdfmd-options` (nulabreport's
  metadata files would declare theirs). pdfmd itself names no package's environments.

### Tests

- `test_labels.Scanner.test_a_label_after_a_caption_it_could_not_count_is_left_out`: Pandoc's LaTeX for a
  `labtabularbt` table; a counted equation afterwards is replayed again.
- `test_labels.UnknownWrapper`: a three-part report whose middle part has a table in a `preamble.tex` environment.
  Built alone, the last part printed "See Table 3 in Section 3" on 3.27.19; now "See Table ?? in Section 3", and
  "See Table 1" with `--seed-labels draft`.

## v3.27.19 — 2026-10-10

Pre-edit state: commit `4bd2230` (v3.27.18).

### Fixed

- **3.27.18 stopped a document whose `header-includes` item uses Pandoc's raw attribute**, the manual's own way of
  writing one:

  ```yaml
  header-includes:
    - |
      ```{=latex}
      \setlength{\parskip}{1em}
      ```
  ```

  With one code block, the header file 3.27.18 builds from the item handed LaTeX the backticks ("Missing
  \begin{document}"); 3.27.17 had dropped the item silently and built. `raw_latex_only` now gives LaTeX what Pandoc's
  LaTeX writer would:
  - a ```` ```{=latex} ```` (or `{=tex}`) block or a `` `...`{=latex} `` span without its fence;
  - nothing of a block or span for another format (`{=html}`, `{=typst}` ...).

  It runs inside `document_header_includes`, so `document_header_file` (the same text whenever a `preamble.tex` is
  there, for every version) and the package scans that read it get it too, and in `header_includes_latex` for a
  metadata file's.
- `has_header_include_option` knows Pandoc's attached form `-Hmine.tex`. With it, your own header file still let
  pdfmd add the header-includes next to it, and preamble discovery still ran (it stops for `-H mine.tex`).

### Tests

- `tests/test_header_includes.py`: `raw_latex_only` (latex/tex fences with backticks or tildes, an html block, inline
  spans, plain text untouched), `document_header_includes` with a latex item, an html item and a plain one, `-Hmine.tex`
  left alone, and a real build with a fenced latex item, a fenced html item and code.

## v3.27.18 — 2026-10-10

Pre-edit state: commit `5aed974` (v3.27.17).

### Fixed

- **A header file of pdfmd's own threw away `header-includes:`.** Pandoc puts `--include-in-header` files and
  `header-includes` in one template variable, and the command line wins (checked on 3.12 and 3.1.3). So, for a
  document that loads a package in its front matter (`header-includes: \usepackage{lipsum}`), one code block was
  enough to stop LaTeX at the first `\lipsum` (the code-wrapping header, since 3.25.3). The same happened with:
  - a raw `\includegraphics` (graphicx),
  - text in another script (the fonts header),
  - `\ce`/`\SI` (3.27.16's packages header: its filter route was undone by any later header file),
  - a `preamble.tex` beside a metadata file that has `header-includes`.

  Without the document's own, a metadata file's went the same way. A real case was a nulabreport pre-lab, which loads
  `\usepackage[prelab]{nulabreport}` only through `prelab-metadata.yaml`: with one code block it stopped at `\ce`.
  - Now `keep_header_includes` runs on the finished command at every LaTeX site (the PDF and `--to latex` builds,
    the native-bibliography route, both report sites). When pdfmd added a header file and the caller did not, it puts
    back what Pandoc would have kept, as a header file of its own:
    - the document's own (the last input's, when there are several), placed last but for the packages header, which
      must see them;
    - else the last metadata file's in Pandoc's order, placed where a shared preamble goes: after the code-wrapping
      header (which must come first, see `hoist_code_header`) and before `preamble.tex` and the rest.
  - `document_header_file` still re-adds the document's own when a preamble is there. The text is the raw LaTeX of the
    YAML value, as `document_header_file` does, with a `{=latex}` fence taken off.
  - An `--include-in-header` or `-M header-includes` you pass yourself replaces them, as in Pandoc.
  - This also closes the report PDF route's "known gap" for the chapters' own header-includes. The front-matter macro
    definitions are still not made there.
- `\ce`/`\SI` packages: always a header file, last (keep_header_includes keeps everything before it);
  `pdfmd_lua/header.lua` is gone, and `tex_package_args` lost its `cmd`/`pandoc_options` parameters.

### Checked

- Read-only scan of nulabreport and the author's course folders for `header-includes` that would now come back:
  - 29 files: 27 documents' own and 2 copies of `prelab-metadata.yaml`;
  - none has a `preamble.tex` beside it (the copy in nulabreport's root is never built there);
  - none loads what pdfmd's own headers load (fvextra/fancyvrb, graphicx; the packages header is guarded).
- A pre-lab with one code block, in a frozen export of nulabreport: fails on 3.27.16 ("Undefined control sequence",
  `\ce`) and builds with the house style on 3.27.18.

### Tests

- New `tests/test_header_includes.py`:
  - what Pandoc keeps: the document beats metadata files, the later metadata file and the later input win, a
    fenced metadata file, a `{=latex}` fence;
  - the placement around the code-wrapping, graphicx, preamble, fonts and packages headers;
  - left alone with no header file, with your own `-H` or `-M header-includes`, or when `document_header_file` has
    them;
  - real lualatex builds that load lipsum: the document's own with code, the document's own with a raw
    `\includegraphics`, a metadata file's with code, a metadata file's beside a `preamble.tex`, a `-r` report whose
    first chapter has its own and code, and your own `-H` replacing them.

  The five builds that should succeed all fail on 3.27.17.
- `tests/test_texpackages.py`: the arguments test follows the single route. The document's own `\ce` is now defined
  with `\csname` in a block scalar: Pandoc expands a `\newcommand`, `\def`, `\DeclareRobustCommand` or
  `\NewDocumentCommand` itself, so LaTeX never saw it and the test passed whatever the preamble did.

## v3.27.17 — 2026-10-10

Pre-edit state: commit `b4005b4` (v3.27.16).

### Fixed

- **The global metadata file (`metadata.yaml` beside the config, written by `pdfmd --setup`) beat the folder's own
  metadata files**, the opposite of what it is for: pdfmd passed it last, and Pandoc prefers a later
  `--metadata-file` (checked on Pandoc 3.12 and 3.1.3). A folder's `subtitle:` lost to a global `subtitle:`. Pandoc
  now gets it first (`pandoc_metadata_order`), at every site that hands Pandoc the metadata files. Only that order
  changed: the list keeps the global file last, so Pandoc still runs in the folder of the first local metadata file
  and pdfmd's own `pdfmd-options` lookups still see it last.
- `effective_metadata` (the Word/OpenDocument reference styles, the bibliography check) and the built-in renderer read
  the metadata files the same way Pandoc does: a later file wins. `effective_metadata` had the first file winning, so
  `metadata.yaml` beat a document-named `a.yaml` there while Pandoc took `a.yaml`.

### Not changed (for the author)

- pdfmd's own `pdfmd-options` lookups (`option_sources`) still take the FIRST metadata file that sets a key, so for a
  pdfmd option a folder's `metadata.yaml` beats a document-named `a.yaml` or `report.yaml`, while for a Pandoc key the
  document-named file wins (`find_local_metadata` calls it the override). Turning that around changes which file
  wins for existing setups, so it waits for the author.

### Tests

- `tests/test_setup.py`: a build with a global and a folder `metadata.yaml` (the folder's `subtitle` wins, the global
  `author` still arrives), `pandoc_metadata_order`, and `effective_metadata` with a later file winning. Both new
  tests fail on 3.27.16.

## v3.27.16 — 2026-10-10

Pre-edit state: commit `607540c` (v3.27.15).

### Fixed

- **`\ce{H2O}` (or `\SI{25}{\celsius}`) stopped every LaTeX engine** when the document did not load mhchem (siunitx)
  itself: "Undefined control sequence" with lualatex and xelatex alike (queue item 2(e) asked whether xelatex got
  mhchem; no engine did). New auto kind `texpackages`: when a source uses `\ce`/`\cee`/`\cf` or
  `\SI`/`\si`/`\num`/`\qty`/`\unit`/`\ang`/the range commands, the preamble gets a guarded load, after everything
  else: nothing when the package is loaded already (a house package's own options win, no option clash), when the
  command is defined some other way (a document's own `\newcommand{\ce}`), or when the package is not installed (the
  old error, not a new one). An `AUTO TEXPACKAGES` line says so; `--no-auto texpackages` turns it off.
- How it reaches the preamble matters: one `--include-in-header` replaces every metadata file's `header-includes`
  (Pandoc's command line wins over metadata; nulabreport loads its package that way). With a header file already on
  the command line (those are gone then anyway) it is one more, last; without one, a new filter
  `pdfmd_lua/header.lua` appends it to the header-includes Pandoc merged.

### Tests

- `tests/test_texpackages.py`: the arguments in both modes, nothing without the commands, `--no-auto`; real lualatex
  builds: chemistry and units with no preamble, a metadata file that loads mhchem with its own options and defines a
  macro (both survive), a `preamble.tex` that loads it, a document's own `\ce`.

## v3.27.15 — 2026-10-10

Pre-edit state: commit `b89ee55` (v3.27.14).

### Changed

- **Page breaks in every format are off unless asked, and you choose what takes part** (the author: 3.27.13 had them
  on for everyone, as an auto kind). `pdfmd-options.pagebreak: true` (every family) or a list of families:
  `comment` (`<!-- pagebreak -->` and the other spellings), `tex` (`\newpage`, `\clearpage` ...), `html` (a CSS-break or
  `class="pagebreak"` div or hr), `div` (an empty `::: pagebreak`), `typst` (a raw `#pagebreak()`), `word` (a raw Word
  break). From the document, a metadata file or the config (`pdfmd --setup`: a new section, **Universal markup**, which
  also takes the raw-pieces row); `--pagebreak [KIND ...]` (bare: all) and `--no-pagebreak` for a run. pdfmd passes the
  families to `pagebreak.lua` as `-M pdfmd-pagebreak=...`, which the filter takes out of the metadata. The auto kind
  `pagebreak` and its `--no-auto` are gone (never released). Without the option every writer keeps only its own
  spelling, as before 3.27.13; the built-in renderer reads the comment and TeX spellings as it always did.

### Fixed

- **Python warned `invalid escape sequence '\p'` on every run of 3.27.13**, and its docstring lost the `\n` of
  `\newpage` to a line break: the new paragraph had single backslashes. `tests/test_compat.py` now compiles every
  source with warnings as errors.

### Tests

- `tests/test_pagebreak.py`: the option's values, off unless asked, the command line over the document, only the
  chosen families converted (in Pandoc and in a Word file).

## v3.27.14 — 2026-10-10

Pre-edit state: commit `f824538` (v3.27.13).

### Changed

- **`pdfmd --setup` has a section per subject** (the author: the CSV rows had "leaked into Output"). "Output" held 18
  rows and "The source file" 19; they are now Output (the engine, the default format, defaults for `.typ`/`.html`),
  HTML, Tables (the `.csv` rows, columns, cut and delimiter, pipe-table widths), Code, Word and OpenDocument, Build
  history (the stamp), Backups, and Source inside the PDF (attaching, bundling, comment stripping). The hybrid-PDF
  row moved to PDF finishing and the raw-pieces row to Input. The settings and what they write are unchanged.

## v3.27.13 — 2026-10-10

Pre-edit state: commit `bc1c81b` (v3.27.12).

### Fixed

- **A page break worked in some outputs only.** Through Pandoc each writer understood one spelling and dropped the
  others (checked with five breaks: LaTeX made 4 pages of 6, Typst 1, WeasyPrint 2, Word 3 breaks); `<!-- pagebreak -->`
  worked only in the built-in renderer. A new filter, `pdfmd_lua/pagebreak.lua`, runs on every Pandoc route (before
  `raw.lua`) and makes a block that is only a page break, in any spelling, the output's own:

  - written as: `<!-- pagebreak -->`, `page-break`, `newpage`, `new-page` or `<!-- pdfmd: pagebreak -->` (any case);
    `\newpage`, `\newpage{}`, `\pagebreak`, `\pagebreak[n]`, `\clearpage`, `\cleardoublepage` (to an odd page);
    `<div style="page-break-after: always">` (before or after, also `break-*: page`), `<div class="pagebreak">`,
    `<hr class="pagebreak">`; an empty `::: pagebreak` (or `newpage`); a raw Typst `#pagebreak()` or a raw Word
    `<w:br w:type="page"/>` paragraph;
  - becomes: LaTeX `\newpage{}`, Typst `#pagebreak(weak: true)`, a `break-after: page` div for HTML, EPUB and
    WeasyPrint, a Word page-break run, an OpenDocument paragraph in the `Pagebreak` style, ConTeXt `\page`, ms `.bp`,
    a form feed in `--to txt` and `<!-- pagebreak -->` in `--to gfm`.

  A spelling already in the output's language stays as written (`\pagebreak[3]` for LaTeX). A GitHub-Markdown file
  (no front matter) reads `\newpage` as words, and it still breaks. Slides drop a break with a NOTE (a beamer
  document's own `\newpage` stays); Pandoc Markdown, rst, org and the others keep what was written. New auto kind
  `pagebreak` (`--no-auto pagebreak`: the old behaviour), with its row in `pdfmd --setup`.
- The `.odt` reference document pdfmd builds gets a `Pagebreak` paragraph style (break before: page) when it has none.
- The built-in renderer also reads `<!-- pdfmd: pagebreak -->`, `\pagebreak[n]` and `\cleardoublepage`.

### Tests

- `tests/test_pagebreak.py`: one list of 20 spellings checked against the filter for seven writers and against the
  built-in renderer's patterns, what is not a break, the comment stripper keeping them, slides and Markdown, and real
  output through pdfmd: five breaks make six pages with lualatex, Typst and WeasyPrint, and five breaks in a Word file
  (fewer with `--no-auto pagebreak`).

## v3.27.12 — 2026-10-10

Pre-edit state: commit `c34c6b5` (v3.27.11).

### Fixed

- **Math in a PDF made by WeasyPrint was garbage**: WeasyPrint does not draw MathML, Pandoc's default HTML math (since
  Pandoc 3.x), so each formula printed as its flat text followed by its TeX (`x2+abx^2 + \frac{a}{b}`). For
  `-e weasyprint` (or a fallback to it) pdfmd now gives Pandoc `--math-method=plain`: simple formulas in Unicode
  (`αi ≤ β`), the others as their TeX, once. A new filter, `pdfmd_lua/weasyprint.lua`, says it once
  (`WARN  weasyprint: WeasyPrint does not typeset math; 5 formulas are printed as text ... -e typst`). A math option
  on the command line (`--mathml`, `--math-method=...`) is kept. Real math for WeasyPrint (KaTeX) is stage 6 A2.
- **A direct `.html` page with MathML went to WeasyPrint first**; it now goes to a browser first, as a page with
  scripts does (the author's decision: WeasyPrint first again once pdfmd gives it math). With no browser, a `WARN`
  says the formulas print as flat text.

### Tests

- `tests/test_typst.py` is now `tests/test_engine_filters.py` (both engine filters): the WeasyPrint math arguments,
  a WeasyPrint build with math (one WARN, no MathML flat text) and one without. `tests/test_direct.py`: a MathML page's
  engine order.

## v3.27.11 — 2026-10-10

Pre-edit state: commit `08a3a32` (v3.27.10).

### Fixed

- **A link to an anchor the document does not have stopped a Typst build** ("label <135-your-own-defaults> does not
  exist in the document"; a pasted transcript quoting another document's `(see 13.5)` links was enough). LaTeX and
  HTML only warn. A new last filter for Typst, `pdfmd_lua/typst.lua` (PDF and `.typ`), makes each such link its text,
  with one `WARN` naming the anchors. Pandoc's Typst writer labels headings, divs, spans, figures and tables (3.1.3 and
  3.12 alike, checked); a link to the id of a code block, an image, inline code or a link is made text too.
- **A Typst PDF lost its relative pictures with Pandoc 3.1.3 when Pandoc runs in a metadata file's folder** (a
  discovered `~/.config/pdfmd/metadata.yaml`, or `-y shared/meta.yaml`): that Pandoc runs Typst in its own working
  folder without fetching the pictures first. `typst.lua` makes each picture's path the absolute path found on the
  resource path, for a PDF only (a `.typ` file keeps its relative paths); 3.27.10's `--root=/` lets Typst read it.

### Tests

- `tests/test_typst.py`: the filter through Pandoc (labels kept, the rest text, one WARN, other writers untouched), a
  Typst PDF with a missing anchor, and a picture found when Pandoc runs in the metadata file's folder (fails on 3.1.3
  without the filter).

## v3.27.10 — 2026-10-10

Pre-edit state: commit `1c2c70c` (v3.27.9).

### Fixed (Pandoc 3.1.3, the oldest pdfmd is tested with: the 3.26.x features had never run on it)

- **`--to gfm`, `--to txt`, `--to ascii` and `--keep-source` failed outright** on a Pandoc before 3.2: `flat.lua` called
  `pandoc.Caption`, which those versions lack. It gets the same stand-in as `csv_table.lua`.
- **`{#tbl:x}` was left in a table's caption** in flat Markdown and text when pandoc-crossref did not run (not installed,
  or built for another Pandoc) and the Pandoc is too old to read a table caption's attributes. The words go.
- **A hard line break in flat Markdown was two trailing spaces** with Pandoc 3.1.3's gfm writer (an editor strips them
  without a trace); it is now the backslash a newer Pandoc writes.
- **A Typst PDF with a picture pdfmd drew (a diagram, a raw TeX piece) failed** with "file not found": an older Pandoc
  runs Typst with its root at the document, where the picture's absolute path in the cache was looked for. Typst is now
  given `--root=/`, as a newer Pandoc does (not when the command line sets its own `--root`). The limit is gone from
  `--doctor`'s list for older Pandoc.

### Tests

- `tests/pandoc_support.py`: `CROSSREF_USABLE` / `needs_crossref`, true only when pdfmd would run pandoc-crossref
  (installed and built for this Pandoc). The whole-document numbering tests skip without it; the text-output test checks
  the unnumbered captions instead.

## v3.27.9 — 2026-10-10

Pre-edit state: commit `3297564` (v3.27.8).

### Fixed (found by a review of 3.27.8 before it was called done)

- **With `source` or `cache` switched off, every plain build was refused** ("--keep-comments: the source features are
  switched off"): two flags share a dest with different defaults (`--strip-comments` None, `--keep-comments` True;
  `--cache` / `--no-cache`; `--attach-source` / `--no-attach-source`), and the check compared against the second
  one's. It now compares against what the parser gives with no options at all, and never refuses a dest a visible
  option shares. A test builds a plain document with each feature off in turn.
- **pdfmd's own child processes were refused** when a feature they use is off: the Word/ODT route, `--hybrid`, Word
  reference numbers, `--doctor --deep` and `--watch` start pdfmd again with `--no-stamp`, `--no-backup` and the like
  (history). A run that passed the check sets `PDFMD_ALLOW_DISABLED` for its children.

### Changed

- **A house style's Word defaults are above the config file.** `office.reference-doc`, `office.latex` ... from
  `pdfmd --setup` (the config) are now below what a package ships (`<package>-office.yaml`, nulabreport's department
  template), so a global template no longer replaces the department one in every report's Word file; the document and
  its metadata files stay above both. (Since 3.27.1 the config's `office:` was merged into the document's and then put
  over the package's defaults.)

### Tests

- `SwitchedOff`: a plain build with each feature off, a child process; `NewRows`: a house style's reference doc over the
  config's, the config's `latex` below it. The completeness test notes the calls its key scan cannot see.

## v3.27.8 — 2026-10-10

Pre-edit state: commit `c47bfc9` (v3.27.7).

### Added

- **Whole features can be switched off** (the author's idea from the 3.25 line): `disabled: [history, tables]` in
  `config.yaml`, or `d` in `pdfmd --setup` (a new row, "Features switched off", in the Setup section). The features are
  the topics of `--help` (`pdfmd_help.TOPICS`); `output`, `setup` and `debug` stay on (`pdfmd_help.CORE`; naming one is a
  WARN). A switched-off feature's options leave `--help` (`--help history` says it is off), shell completion and the
  setup screen (its rows are hidden, and the list says how many), and the command line refuses them with a message
  that names the way back; `--disabled` lets one run use them and shows them in `--help`. An option that also belongs
  to a feature still on stays (`--dry-run` is tables' and history's). A setup row belongs to the features of the flags
  that set it, else to its family (`inventory.ROW_TOPICS`: `options.stamp.` -> history ...). What a document's own
  `pdfmd-options` asks for still applies, so a document from someone else builds the same. A completion script made
  before the change keeps the old options until `--completion` writes it again.

### Changed

- In the full-screen setup, `r` resets a row to its default; `d` now opens the features list, as the author asked.

### Tests

- `tests/test_setup.py` `SwitchedOff` (6): help, refusal and `--disabled`, a shared option, the core topics,
  completion, the setup screen and `d`; `Fancy`: `d` and `r`.

## v3.27.7 — 2026-10-10

Pre-edit state: commit `b010b69` (v3.27.6).

### Changed

- **A cut `.csv` table keeps the last ⌊√cap⌋ rows (and columns)**, not about 30% of the cap: 7 + 3 of 10, 5 + 2 of 7
  (as before), 16 + 4 of 20, 25 + 5 of 30, 90 + 10 of 100. The author's numbers for 10, 7 and 20 all follow this rule:
  the tail is a short look at the end and grows slowly; the head keeps most of a large cap. A cap of 3 now keeps
  2 + 1 (was 3 + 0); under 3 the head only, as before. `csv_keep` (built-in renderer) and `keep_indices` (Lua) agree.

### Tests

- `csv_keep` for caps 7, 10, 20, 30, 100; the cap-3 cases.

## v3.27.6 — 2026-10-10

Pre-edit state: commit `0c39591` (v3.27.5).

### Added

- **`--merge`**: one standalone Markdown file that builds alone, anywhere (`NAME.assembled.md`, or `-o`): the parts
  joined and everything pdfmd finds beside the document embedded, data files and pictures included. A shorthand for
  `--assemble-only --embed-metadata all` (the author asked where "merge everything into one Markdown" is; it existed
  under those two flags). `--unpack` gives the files back. Before this, argparse took `--merge` as an abbreviation of
  `--merge-history`. Not `--standalone`: pdfmd hands options it does not know to Pandoc, and that one is Pandoc's own.

### Tests

- `tests/test_embedding.py`: `--merge` writes the same file as `--assemble-only --embed-metadata all`, and refuses
  `--no-embed-metadata`.

## v3.27.5 — 2026-10-10

Pre-edit state: commit `868f670` (v3.27.4).

### Changed

- **The delimiter guess parses records, not lines** (the author's point: what makes a delimiter is that every record has
  the same number of fields with it). For each of `,` `;` tab `|`, the first 20 records are read with the real CSV
  parser, so a quoted delimiter or a line break inside a quoted field counts as it should; the candidate that gives
  them all the same number of fields, more than one, wins (the most fields first, the file name's own delimiter on a
  tie). 3.27.4 counted per physical line, and a quoted line break made the right delimiter look uneven. A long file is
  sampled in its first 64 KB. The first-line count stays as the last fallback. Same in `pdfmd_lua/csv_table.lua` and the
  built-in renderer (`csv_guess_delimiter`).

### Tests

- A `;` file whose quoted field holds commas and a line break; a 9000-line file.

## v3.27.4 — 2026-10-10

Pre-edit state: commit `cc6c86d` (v3.27.3).

### Changed

- **A cut `.csv` table keeps both ends.** Over the cap (10 x 7 by default) it shows the first 7 rows, a row of `…`, the
  last 3, and the first 5 columns, a `…` column, the last 2: about 70% and 30% of any cap (a cap under 3 keeps the head
  only). The note under the table says "the first 7 and the last 3 of 15 rows, ...". `cut="head"` on the div,
  `pdfmd-options: {csv: {cut: head}}` or the `--setup` row "Where a long .csv table is cut" gives the old cut back. A
  separator row's or `align=`'s alignments and widths follow their columns; the `…` column is centred. The built-in
  renderer cuts the same way (`csv_keep`, the Lua filter's `keep_indices`). The `…` is U+2026, which every text font
  has (U+22EE ⋮ is only in the math fonts of STIX and Libertinus).

### Added

- **The delimiter guess reads the first eight lines**: the one of `,` `;` tab `|` that splits them into the same number
  of fields (more than one) wins, the most fields first and the file name's own delimiter (tab for `.tsv`/`.tab`, else
  comma) on a tie; failing that, the old rule (what the first line holds most of). A `.tsv` used to be read with tabs
  whatever it held. When the guess is not the name's delimiter, the build **warns** (`d.csv: read with semicolons as
  the delimiter (its lines split evenly on them); say delimiter="semicolon" on the div, or `csv: {delimiter:
  semicolon}` in pdfmd-options, to make it explicit`). `pdfmd-options: {csv: {delimiter: auto|comma|semicolon|tab|pipe
  |space|colon|<one character>}}` names it for every table (no warning), and so does the `--setup` row "The delimiter of
  .csv data"; a div's own `delimiter=` still wins.

### Tests

- `tests/test_csv_table.py`: the cut in both modes and through every layer, the delimiter guess with and without the
  warning (a decimal comma in a `;` file stays in its cell, a `.tsv`, a div's own word), the built-in renderer's guess
  and cut. `tests/test_native.py` expects the new cut. Passes on Pandoc 3.12 and 3.1.3.

## v3.27.3 — 2026-10-10

Pre-edit state: commit `75529e1` (v3.27.2).

### Fixed

- **`-j N` built some documents without the command line's settings.** Worker processes start fresh (macOS and Windows
  spawn them), so everything main() keeps in module globals was missing there: `--line-numbers`, `--no-code-wrap`,
  `--fallback`, `--missing`, `--raw`, `--keep-source`, `--attach-source`, `--bundle`, `--paper`, `--header`/`--footer`,
  `--no-citeproc`, the comment policy ... (only what travels as an environment variable, `--strict`, the budgets and
  the CSV cap, arrived). The pool now starts each worker with a copy of them (`worker_state()`: every `*_CLI` global
  and `WORKER_GLOBALS`).

### Tests

- `tests/test_jobs.py`: `-b -j 2 --to latex --line-numbers` writes the same files as `-j 1` (failed before the fix);
  every `global` main() sets is one a worker gets; the state survives pickling.

## v3.27.2 — 2026-10-10

Pre-edit state: commit `34bcec4` (v3.27.1).

### Added

- **The cap of `::: {.csv}` tables for every table of a document**, not only per div: `--csv-rows N|all` and
  `--csv-cols N|all`, `pdfmd-options: {csv: {rows, cols, header, reader}}` (the document, its metadata files, the config;
  field by field), and two `--setup` rows ("Rows a .csv table shows", "Columns ..."). Default unchanged, 10 x 7. A div's
  own `rows=`/`cols=`/`header=`/`reader=` still win for that table. pdfmd hands what differs from the defaults to
  `pdfmd_lua/csv_table.lua` as `-M pdfmd-csv-*`, which the filter reads first and removes from the metadata (so a
  `--to markdown`/`native` output carries no trace); the built-in renderer's own CSV tables (`csv_div_table`) take the
  same values. The command line reaches `-j` workers as `PDFMD_CSV_ROWS` / `PDFMD_CSV_COLS`. The note under a cut table
  now also names `--csv-rows`/`--csv-cols`. `csv.header` and `csv.reader` are per document (listed as such in setup's
  `o` list); a bad value is an error naming the key.

### Not changed, found on the way

- With `-j N`, worker processes start fresh (macOS spawns them), so settings main() keeps in module globals do not
  reach them: `--line-numbers`/`--no-code-wrap` (CODE_CLI), `--fallback`/`--missing`, `--raw`... Only the ones handed over
  as environment variables (`--strict`, the budgets, now the CSV cap) do. Fixed in 3.27.3.

### Tests

- `tests/test_csv_table.py` `Limits` (5): the default cap and its note, the command line / document / config and their
  order, a div's own attributes, header and reader for every table, a bad value, the built-in renderer. Passes on
  Pandoc 3.12 and 3.1.3.

## v3.27.1 — 2026-10-10

Pre-edit state: commit `641e917` (v3.27.0).

### Fixed

- **A detail row of `pdfmd --setup` switched stamping or backups on for every document.** "Where the compile history
  goes" (`stamp: {store: file}` in the config), "Backup folder" (`backup: {dir: ...}`) and the 3.27.0 detail rows were
  read with the rule meant for documents, "a `stamp:`/`backup:` mapping without `enabled` means on". In the config file
  a mapping now says only what it says; `enabled` comes from its own row. (A document or a metadata file keeps the old
  rule: `stamp: {mode: history}` there still switches stamping on. A list or a name, `stamp: [nulabreport]`, means on
  everywhere.)
- **A mapping-valued option is merged field by field** down the document, its metadata files (in order) and the config,
  the first place to set a field winning, until a place sets the key to a plain value. It used to be taken whole from
  the first place that had it, so a document's `stamp: true` dropped the shared metadata.yaml's `store: file` (the
  report's BUILD NOTES were written after all), and a document's `html: {math: katex}` dropped the config's `css:`. This
  covers `stamp`, `backup`, `cache` and every key read through `first_pdfmd_option` / `cascaded_option` (`html`,
  `office`, `gfm`, `txt`, `ascii`, `raw`, `strip-comments`...). New `option_sources()` is the one list of places.

### Tests

- `tests/test_setup.py` `FieldByField` (7): the config's detail rows, a document switching on over them, a shared
  metadata file's details under a document's own, an explicit off, the list shorthand, html/cache/raw.

## v3.27.0 — 2026-10-10

Pre-edit state: commit `ee1977f` (v3.26.21). The 3.27 line holds the rest of the plan: the settings foundations, the
Calibre/math/CSS/format-router work, the per-folder setup, the parts markers, `--doc`, and the fixes found on the way.

### Added

- **Every flag and every `pdfmd-options` key is accounted for in `pdfmd --setup`.** `pdfmd_setup/inventory.py` lists all
  145 argparse destinations and every key pdfmd reads (dotted for a mapping's field: `stamp.mode`), each pointing at the
  `--setup` row that sets it for every document or carrying the reason it has none: a command (`--doctor`), about one
  run (`-o`, `--section`), about one document or project (`alias`, `lua-filter`, the Word-only `office.*` overrides),
  trust (`--trust-lua`), written by pdfmd itself (an assembled file's `origin`), or accepted but inert (`txt.math`). `o`
  in the numbered list and in the full-screen one shows that list with the reasons. `tests/test_setup.py` checks it both
  ways (the parser's flags, the keys read through `first_pdfmd_option`, `cascaded_option`, `config_options()` and the
  front-matter reader, the fields of the stamp/backup/cache/gfm/txt/office mappings, and the registry), so a new flag
  or key that is in neither fails the suite; CLAUDE.md says so.
- **31 new rows**, each read by the same function a document's own key goes through (a test per group):
  checks and limits (`strict`, `max-asset-mb`, `max-output-mb`, `check-ignore`); the Markdown reader (`reader`); HTML
  as a full page and its style sheet (`html.standalone`, `html.css`); the Word/ODT template (`office.reference-doc`);
  plain Markdown and text (`gfm.scripts`, `gfm.math`, `gfm.title`, `txt.scripts`, `txt.title`, `ascii.missing`,
  `keep-source`); the stamp's details (`stamp.mode`, `stamp.scope`, `stamp.packages`, `stamp.include-output`,
  `stamp.pdf-metadata`); backup names and how many are kept (`backup.format`, `backup.keep`); the LaTeX packages in the
  bundle (`bundle-packages`); the plot cache and the labels of a part built alone (`cache.plots`, `seed-labels`).
  Each says what pdfmd does when it is not set (`registry.UNSET`).
- A text row can hold a list (`check-ignore`, `stamp.packages`): typed comma-separated, stored as a YAML list.
- Each row has a scope: `setup-ui` and `translit` are this computer's (`registry.MACHINE`), the rest may later come
  from a folder's own setup (`pdfmd --setup DIR`, planned).

### Fixed

- The comment above `FILE_ONLY_OPTION_KEYS` said `parts` and `no-auto` are read from a document's front matter only;
  they are left out of what an assembled file folds in, but a normal build reads `parts` from the document, its
  metadata files and the config, and `no-auto` from the command line, the document and the config.

### Not changed, found while building the table (planned in this line)

- A mapping-valued option is taken whole from the first place that has it: a document's `stamp: {enabled: true}`
  hides the config's `stamp: {mode: history}`, and the same for `backup`, `html`, `office`, `cache`, `gfm`, `txt`.
- `no-auto` in a metadata file is not read (the document and the config are).

### Tests

- `tests/test_setup.py`: `Completeness` (7 tests), `NewRows` (5), the `o` list in both screens, a list row.

## v3.26.21 — 2026-10-10

Pre-edit state: commit `17a3afc` (v3.26.20).

### Fixed

- `pdfmd --setup` printed "not set" for every setting whose default is not a choice of its own: paper size, font size, page
  geometry, main font, code font and about thirty more, as if pdfmd did nothing when they were empty. Each now says what
  pdfmd does (`STIX Two Text (or a serif with the letters) (default)`, `margin=1in (default)`, `US Letter (A4 in WeasyPrint)
  (default)`, `10 pt LaTeX, 11 pt Typst (default)`), or `none` where nothing is added. The words are `registry.UNSET` in
  `pdfmd_setup`; the numbered list's "0. back to the default (...)" line and the full-screen list use them too, and a test
  fails for a setting with neither a default nor an entry there.

## v3.26.20 — 2026-10-10

Pre-edit state: commit `28944c3` (v3.26.19).

### Fixed

- On Windows, a path in a message (`OK    doc.md`, `doc.md:3: warning ...`, `--check`'s lines) was printed in full instead of
  relative to the working folder whenever that folder was in its 8.3 short form (`C:\Users\RUNNER~1\...`, as on a GitHub
  runner) while the file's folder resolved to the long one: `display_path` compared the two spellings. It resolves the working
  folder too. The first push of 3.26.0-3.26.19 failed six tests (`test_check` four, `test_build_record` two) on Windows with
  this one cause, and was not published.

## v3.26.19 — 2026-10-09

Pre-edit state: commit `da231ff` (v3.26.18).

### Fixed

- The size budget said an image's size twice in a build of one section (the label scan builds the document again and
  printed the same warning), and the scan overwrote the record of the output file. The scan is now silent about budgets and
  restores what it recorded. A `-r` report and a section of a document in parts are tested (one warning each).
- `--strict` of a `-r` report counts a filter's `WARN` lines too (as a single document's build has since 3.26.16).
- `pdfmd --init` wrote its files with `Path.write_text(newline=...)`, which Python 3.9 does not have.
- `diagram.lua` gives `Figure` the caption as a plain table, which every Pandoc 3 takes (it had `pandoc.Caption`).
- A diagram built through a real LaTeX engine and through Typst was looked at and tested: the figure and its caption are
  on the page (the tests use a stand-in `dot` whose PDF comes from `rsvg-convert`, and skip without it). The diagram tests
  are skipped on Windows (they write shell scripts as stand-in tools). The tests were also run on Python 3.9.
- The 3.26.15 note no longer says whose notes it was run on.

## v3.26.18 — 2026-10-09

Pre-edit state: commit `7b2dd70` (v3.26.17).

### Added

- Size budgets. `--max-asset-mb N` / `pdfmd-options: {max-asset-mb: N}` for one image or data file, `--max-output-mb N` /
  `max-output-mb` for the file that is made. With a budget set a build prints a `WARN` for each image over it before it
  starts, and for an output over its budget names it with the three largest images behind it; `--check` reports the
  images as `asset-large`. Warnings, so `--strict` fails them. Off unless set; 0 on the command line turns a document's
  budget off. Single documents, parts and `-r` reports; the command line reaches `-j` workers through
  `PDFMD_MAX_ASSET_MB` / `PDFMD_MAX_OUTPUT_MB`.

## v3.26.17 — 2026-10-09

Pre-edit state: commit `383e064` (v3.26.16).

### Added

- `pdfmd --init [TEMPLATE] [NAME]`: a new document from a template. Alone it lists them. Built in (new package
  `pdfmd_templates`): `article` (abstract, equation, table, a citation and its `.bib`), `report` (contents, numbered
  sections, a table from a CSV file), `notes`, `slides` (for `-p`) and `book` (a scaffold and `parts/`). Yours: a folder or
  a `.md` file in `templates/` of the config folder, or any folder or `.md` file named by path. `{{name}}`, `{{title}}`,
  `{{author}}` (`-V author=`, else `git config user.name`), `{{date}}`, `{{year}}` and `__name__` in file names are filled
  in; unknown `{{...}}` stay. Nothing that exists is overwritten (the clashing files are named and nothing is written).
  The plan said `--init --from TEMPLATE`, but `--from` is already the Pandoc reader, so the template is the argument of
  `--init`. Every built-in template passes `--check --strict` and builds, in the tests.

## v3.26.16 — 2026-10-09

Pre-edit state: commit `bf8870e` (v3.26.15).

### Added

- Diagrams written as code. A fenced block of class `mermaid`, `d2`, `dot` or `graphviz` is drawn by `mmdc`, `d2` or `dot`
  when it is installed, and the picture replaces the block, in the format of the output (`pdfmd_lua/diagram.lua`, reached
  through `raw_filter_args`, so every route gets it): PDF for LaTeX (D2 through `rsvg-convert`/`inkscape`), SVG for HTML
  (inside the file as a data URI) and for Typst (PNG for Mermaid), PNG for Word and OpenDocument, an SVG in `<name>_files/`
  for `--to gfm` (a Mermaid block stays, GitHub draws it), the source kept for `--to txt`. Kept in the cache by content.
  `caption=`, `{#fig:id}`, `width=`, `engine=` (Graphviz layouts), `theme=` (Mermaid), `layout=` (D2). A tool that is not
  installed or a diagram that does not parse leaves the block as code with one warning that says how to install it.
  `--no-auto diagrams`; `pdfmd --doctor` lists the tools. The tests use stand-in tools (no Graphviz, D2 or Mermaid is
  needed to run them); one runs a real `dot` when there is one. **Not yet run against a real `d2` or `mmdc`** (neither was
  installed where this was written; `dot` neither).

### Fixed

- `--strict` now also counts the `WARN` lines that Lua filters write (a filter's stderr was only read for Pandoc's own
  `[WARNING]`), so a picture a filter could not draw fails a strict build.

## v3.26.15 — 2026-10-09

Pre-edit state: commit `af34059` (v3.26.14).

### Added

- `pdfmd FILE --check`: a linter that reads a Markdown document (a scaffold and its parts as one) and builds nothing. It
  prints compiler-style lines (`doc.md:12: error: image not found: a.png  [image-missing]`) and a `CHECK` summary, and exits 1
  on an error (on a warning too with `--strict`). Checks: missing images, `file=` of csv divs and local links;
  `#anchor` links to no heading or `{#id}` (Pandoc's and GitHub's heading ids both count, a duplicate heading's `-1`
  too); duplicate `{#id}`; `@fig:`/`@tbl:`/`@eq:`/`@sec:`/`@lst:` references and `\ref{}` that nothing defines; citations the
  bibliography (`.bib`, CSL JSON, YAML, or `references:`, from the document or a metadata file) lacks, with a "did you
  mean", citations with no bibliography, a bibliography file that is missing; footnotes without text or unused; a skipped
  heading level, `#Heading` without a space, an empty heading; a code fence, `<!--`, `:::` div or `$$` never closed; YAML
  front matter that does not parse or never closes, a key set twice. Code, comments, math and URLs are masked first.
  `--check-ignore CODE[,CODE]`, `pdfmd-options: {check-ignore: [...]}` and `<!-- pdfmd-check: ignore CODE -->` turn checks off.
- `pdfmd --init-vscode` adds a "pdfmd: check" task whose problem matcher puts the findings in VS Code's Problems panel.
- New package `pdfmd_check` (plain text analysis; `pdfmd.py` finds the files and the bibliography keys).
- Run over real lecture notes and the docs of this repository it found a real typo (an image with a misspelt extension) and
  no false alarm in the docs.

## v3.26.14 — 2026-10-09

Pre-edit state: commit `cc01974` (v3.26.13).

### Added

- A LaTeX error is placed in the Markdown. Pandoc prints the line of the LaTeX it wrote (`l.67 Second has \badmacro`), which
  nobody has; pdfmd now looks for those words in the `.md` (whitespace collapsed, since LaTeX re-wraps the paragraph; then
  the last 30 characters; then the last command) and adds `near line 9 of doc.md: ...paragraph runs over two lines and
  has \badmacro` under the failed-engine warning, once per place even when several LaTeX engines fail in it. Only for a
  Markdown file built directly (not a book, a part or the cache route, which have no single source). Typst errors are not
  mapped.

## v3.26.13 — 2026-10-09

Pre-edit state: commit `b665ade` (v3.26.12).

### Added

- `pdfmd-options: {reader: markdown|gfm|commonmark_x|...}` (a document, a metadata file or the config's `options:`; `auto`
  keeps the default choice): the Pandoc reader of a Markdown file, as `--from` per document or per folder.
- A file with no front matter is read as gfm, which leaves Pandoc-only syntax as text. When the file uses any of
  `H~2~O`, `x^2^`, `^[inline footnotes]`, `{#id .class}` attributes, raw LaTeX (`\begin`, `\newcommand`, `\ce`) or
  fenced divs (outside code), a `NOTE` now says so outright (it used to be an `AUTO READER` line, hidden unless `-v`),
  with the three ways to read it as Pandoc's Markdown. A plain file prints nothing new.

## v3.26.12 — 2026-10-09

Pre-edit state: commit `7542c5c` (v3.26.11).

### Added

- `pdfmd --doctor --deep`: after the usual report, builds a small page (maths, an accent, code, a table) with each
  installed engine (the built-in renderers when there is no Pandoc or engine) by running `pdfmd.py` itself in a scratch
  folder, and prints `OK engine: built a PDF in N s` or `MISS engine: could not build it (reason)`; a failing engine is
  added to the list of things to fix, and one that hangs is stopped after 180 s. `--deep` without `--doctor` is refused.

## v3.26.11 — 2026-10-09

Pre-edit state: commit `5d4533e` (v3.26.10).

### Added

- A Lua filter pdfmd finds by itself (`<name>.lua`, `nulabreport.lua`, the files in `NAME.unpacked/` and the ones
  `pdfmd-options.lua-filter` names) is noted: the first build with one this machine has not run, and the first build
  after its content changed, print a `NOTE`; the filter runs, nothing prompts, and the next build is quiet (path and
  SHA-256 are kept in `known-lua.txt` beside the config). `pdfmd --trust-lua FOLDER|FILE` marks a folder (for good) or a
  file (as it is now) so nothing there is noted; with `--strict`, a new or edited filter outside a trusted folder is
  skipped with a `WARN` (and so the build fails). Not a defence for the first build of a downloaded folder; the
  README says so.

## v3.26.10 — 2026-10-09

Pre-edit state: commit `7e050f8` (v3.26.9).

### Added

- The closing line of a build names the engine that made the PDF: `OK    report.md  (lualatex)`; when an engine was
  tried and failed first, it says which: `OK    report.md  (typst; lualatex, xelatex failed)`. Built-in renderers
  (`inkmd`, `md2pdf`), direct `.tex`/`.typ`/`.html` builds, `soffice` and Quarto are named too; a build that needs no
  engine (Word, HTML...) prints the line as before. `convert_one` now returns a `Built` (a tuple of the same three
  items with `.engine` and `.failed`), so the name also arrives from `-j` workers.
- `--strict` / `--no-strict` and `pdfmd-options: {strict: true}`: a file whose build printed any `WARN` line (an engine
  that failed and was replaced, the fonts retry, lost ASCII characters, a skipped embedded filter...) or whose Pandoc run
  printed a `[WARNING]` (a missing image or citation, a LaTeX undefined reference) is reported `FAIL` with the first
  warnings listed; the output is kept and the exit code is 1. In a batch only that file fails; `-r` reports the book.

## v3.26.9 — 2026-10-09

Pre-edit state: commit `dc15f10` (v3.26.8).

### Changed

- `.ascii` in an output name asks for the ASCII build of whatever ending follows it, as `.gfm.md` asks for `--to gfm`:
  `-o notes.ascii.txt`, `.ascii.gfm.md`, `.ascii.md`, and now `.ascii.rst`, `.ascii.org`, `.ascii.adoc` (were: only the
  first three; the others wrote the Unicode text under an ASCII-looking name). `notes.ascii.html` or `.ascii.pdf` is
  refused with the list of text formats. `-o x.adoc` alone now means `--to asciidoc`.

## v3.26.8 — 2026-10-09

Pre-edit state: commit `acce055` (v3.26.7).

### Added

- `--to ascii` and `--to ascii:FORMAT` (txt by default; gfm, gfm+raw, markdown, commonmark, commonmark_x, markdown_strict,
  plain, rst, org, asciidoc): the format's build with no character above 127. `pdfmd_lua/ascii.lua` runs last and sends
  the document's words, code, math, and link/image titles in one batch to `pdfmd.py --ascii-stdio`, which runs
  `pdfmd_flat/asciify.py` (new) and returns them mapped; so the writer escapes what the ASCII spelling needs (`-`, `>=`,
  `*` at a line's start) and measures table columns on the ASCII text. Pandoc's plain writer sets math in Unicode, and
  a writer with smart typography writes its quotes and dashes itself, so pdfmd maps the written file once more
  (`ascii_finish`). The mapping, in this order: spaces and invisible characters, quotes, dashes (`--`), `...`, symbols
  (`<=`, `+/-`, `->`, `deg`, `1/2`, `(c)`), Greek by name (`mu` before a Latin letter is `u`, a Greek word is spelt),
  Cyrillic with its case, Latin letters Unicode cannot take apart (`ss`, `ae`, `o`, `l`), accents and compatibility forms
  by NFKD, sub/superscripts as `_2`, `^(2-)`, then `pdfmd_unicode.translit`'s packs (Hebrew, Arabic, Armenian, Georgian,
  Korean, kana; Chinese and the rest with `pypinyin` or `anyascii`). TeX math keeps TeX (`\alpha`, `\geq`); a link's
  address is percent-encoded. `--gfm-scripts` is `ascii` for these builds unless `drop`.
- `--ascii-missing question|escape|drop|fail` (and `pdfmd-options: {ascii: {missing: ...}}`): a character with no ASCII form
  is counted in a `WARN` that names the first ones, and written as `?` (default), `\uXXXX`, nothing, or the output is
  removed (`fail`).
- Default names are `<name>.ascii.txt` / `.ascii.gfm.md` / `.ascii.md`, which `-o` recognises as the target again; a
  Unicode output of the same document is never overwritten.
- `--keep-source readable` on an ASCII file writes the trailer packed (a NOTE says so), with the source's name spelt in ASCII.
- `--ascii-missing fail` fails only the file (a batch goes on with the next); `pdfmd-options.default-output: ascii` is refused
  with a pointer to `--to ascii`.

### Changed

- Since 3.26.7 the Python API's `to="txt"` (and an `outputfile` named `.txt`) gives flat text; `to="plain"` is still
  Pandoc's own plain writer.

## v3.26.7 — 2026-10-09

Pre-edit state: commit `8f8a3bf` (v3.26.6).

### Changed

- `--to txt` (and `-o x.txt`, `default-output: txt`) is flat text: the flat build of `--to gfm` (includes, parts, `.csv`
  tables, pandoc-crossref, citations, raw HTML and LaTeX, the document's filters, then `pdfmd_lua/flat.lua`) written by
  Pandoc's plain writer. Title, subtitle, author line and abstract are written; headings are underlined (`=`, `-`) and
  numbered with `number-sections`; a table caption is `Table 1. text` above the table, a figure is `[Figure 1. text]`;
  a link is `words <address>` (the words alone when they are the address or point into the document); no emphasis marks;
  Unicode scripts. Wrapping is Pandoc's (72 columns, `--columns`). The raw filter has its `md` family for text too but
  draws no picture (a Typst piece is left out with a `WARN`). Settings: `--gfm-scripts` (`html` means `unicode`),
  `pdfmd-options: {txt: {scripts, title}}`.
- Until now `--to txt` was Pandoc's plain writer, which drops links, the title and captions' numbers and leaves
  `{#tbl:x}` in captions. Pandoc's own writer is `--to plain`, as `--to gfm+raw` is for gfm.

## v3.26.6 — 2026-10-09

Pre-edit state: commit `a9cf06d` (v3.26.5).

### Added

- `-o notes.gfm.md` is `--to gfm`: the name a flat file gets by default from `notes.md` now also asks for it. `-o notes.md`
  alone is still Pandoc's Markdown.

## v3.26.5 — 2026-10-09

Pre-edit state: commit `36cfdb2` (v3.26.4).

### Added

- A raw LaTeX picture that Pandoc's reader cannot read (`tikzpicture`, `circuitikz`, `pgfpicture`, `forest`, `pspicture`,
  `axis`, `\chemfig`, `\schemestart`) is drawn by `pdfmd_lua/raw.lua` for the HTML, Typst and flat-Markdown families: it is
  typeset alone (lualatex, else xelatex, pdflatex) with the `standalone` class, after the document's preamble files and
  its `header-includes` (given back as the TeX the LaTeX writer would write, so `$..$` in a macro survives), with its own
  package loaded if the preamble has not; the cropped PDF becomes an SVG for HTML and flat Markdown. A piece that does not
  compile is left out with a `WARN` that quotes LaTeX's first error. The engine runs in a scratch folder and in the
  document's TeX search path (`TEXINPUTS`), so house packages resolve.
- For a flat build only the SVGs are written beside the output (`<output stem>_files/`); the drawn PDFs stay in pdfmd's
  cache (`pdfmd-raw-work`).

- Flat Markdown: a display equation loses its numbering wrapper (`\begin{equation}`, `\label`, `\nonumber`, which GitHub's
  math does not read) and `align`/`gather` become `aligned`/`gathered`.
- A flat build written outside the document's folder says (a `NOTE`) that its image links stay relative to the document.
- A flat build passes the document's TeX search path to Pandoc, so a house package's files resolve in a LaTeX picture.

### Changed

- The README and recipes no longer list "tikz and chemfig as pictures in HTML" as not yet done.

## v3.26.4 — 2026-10-09

Pre-edit state: commit `dc41c97` (v3.26.3).

### Added

- `--keep-source [packed|readable]` (`pdfmd-options: {keep-source: true|packed|readable}`, `--no-keep-source`): a Markdown
  output (`--to gfm`, `gfm+raw`, `markdown`, `commonmark` ...) ends with its whole source in one HTML comment: the files
  `--attach-source` puts into a PDF (the assembled Markdown, comments stripped unless `strip-comments` says otherwise, a
  manifest of the layout, the `.csv` data and any `--bundle` files). `packed` (default) is the entries as JSON, zlib, base64;
  `readable` is the text with `\`, `>`, CR and a line-initial `<` or `=` escaped by a backslash. Neither can close the
  comment early: base64 has no `-`, `<` or `>`, and the readable form has no bare `>` (so no `-->` or `--!>`) and no line
  that could pass for the marker. A comment inside the source, `-->` in a code block, CRLF, binary data, a huge source
  (tested at 1.4 MB) and a source that contains the marker come back byte for byte. The comment stores a hash of the
  Markdown above it. A whole build only (a part or a section alone keeps nothing, like `--attach-source`); over 1 MB a
  warning says GitHub stops showing such a file. The new module is `pdfmd_flat/keep.py`.
- `pdfmd --restore FILE.md` writes the kept source back into `FILE.restored/` (or `-o DIR`), never over anything, with
  `--list` to look first, and a `NOTE` when the Markdown was edited since (its hash differs). `--restore` of a PDF is as
  before; both share one core (`restore_attachments`).

### Changed

- `attach_source_after_success` was split: `source_attachments` collects the entries (for a PDF or a Markdown file) and
  `attachment_requirements` takes no PDF. Nothing changes for `--attach-source`.

## v3.26.3 — 2026-10-09

Pre-edit state: commit `8472936` (v3.26.2).

### Added

- `--to gfm` is now FLAT Markdown: plain GitHub-flavoured Markdown that any viewer shows as it is, made after everything
  pdfmd runs for any other target (includes, parts, `::: {.csv}` tables, pandoc-crossref, citeproc, the raw pieces and
  the document's filters). The new `pdfmd_lua/flat.lua` runs last and writes the title block (`# Title`, an author and
  date line, the abstract); bakes section numbers into the headings when the document numbers them; turns captions
  into `**Table 1.** text` above a table and under a figure (split at pandoc-crossref's number, any language) with no
  `{#tbl:x}` left; unwraps divisions, spans, figures and the bibliography's wrappers; points links to headings at
  GitHub's anchors and turns links to vanished ids into text; writes sub/superscripts as Unicode where every character
  has one and `_(..)`/`^(..)` where not (`--gfm-scripts unicode|html|drop|ascii`); keeps math as `$..$` (`--gfm-math
  dollars|fenced`); turns definition lists, line blocks, small capitals and underline into plain Markdown; and writes
  a table Markdown cannot hold (spans, several header rows, block cells) as an HTML table, counted in a `NOTE`. What no
  Markdown can carry (Word XML, a LaTeX macro nothing read) is left out with a `WARN` that counts it and shows the first.
  Settings also come from `pdfmd-options: {gfm: {scripts, math, title}}`. The new package `pdfmd_flat` holds them.
- `--to gfm+raw` is Pandoc's own gfm writer, as `--to gfm` was until now.
- The raw option has a fifth family, `md` (flat Markdown): it takes every syntax unless `raw: {md: [...]}` says otherwise,
  so raw HTML and LaTeX are READ into Markdown (`<b>x</b>` -> `**x**`, `\textbf{x}` -> `**x**`), a raw Typst piece and a
  PDF image (`![](plot.pdf)`, `<img src="plot.pdf">`) become SVG files in `<output stem>_files/` beside the output, linked
  by a relative path. `raw.lua` and `pdf_images.lua` learned the new family; they are inactive for a plain gfm writer.
- A flat output made from `doc.md` is named `doc.gfm.md` (a part build `report#two.gfm.md`...), beside its source.

### Fixed

- A Markdown writer could replace its own source: `pdfmd doc.md --to markdown` wrote `doc.md` over `doc.md` (with a
  leading `# Title` promoted to metadata and gone from the text). pdfmd now stops with "is the source itself" when the
  output would be the source (or one of its parts), whatever the format.
- A front-matter-less document is read as gfm (as before); a flat build of one therefore leaves `H~2~O` literal. Give the
  document a front matter (or `--from markdown`) to read it as Pandoc Markdown. (Documented, not changed.)

## v3.26.2 — 2026-10-09

Pre-edit state: commit `5479ffa` (v3.26.1).

### Added

- A part (`report#methods`) or a section (`doc#results`) built for HTML, EPUB, Word, OpenDocument, Typst, or PDF through
  an engine that is not LaTeX, now shows the numbers of the WHOLE document, and its references to the rest resolve. The
  inputs are all the parts (the whole text of a plain document), each wrapped in a fenced div
  `{.pdfmd-part pdfmd-keep="yes|no"}`, so pandoc-crossref numbers and resolves everything; the new
  `pdfmd_lua/select.lua`, placed right after pandoc-crossref and before citeproc (the bibliography lists only what the
  kept part cites), drops the parts marked no and unwraps the others. A reference to a dropped item has its number
  already, as a link that leads nowhere. Headings are numbered by the filter over the whole document and keep the number
  as the `number` attribute the HTML, Word and OpenDocument writers print (`--number-sections`); for Typst it sets
  `#counter(heading)` before each kept heading. A part's sections inside a cut (`report#sampling`) are marked the same
  way line by line. Not for `--to latex` (a `.tex` stays plain), the built-in renderers, `--seed-labels aux|off`.
- The soffice route (Pandoc to .docx, LibreOffice to PDF) looks for pandoc-crossref syntax in the parts too, not only in the scaffold, so `[@sec:x]` in a part resolves there (it ran no crossref when only a part used it).
- The closing NOTE says which way the numbers of the rest were found. A raw LaTeX `\ref` is not resolved outside LaTeX
  (Pandoc passes it on to nobody): write `[@sec:x]` with pandoc-crossref.

## v3.26.1 — 2026-10-09

Pre-edit state: commit `f7f1882` (v3.26.0).

### Added

- `--seed-labels draft` (`pdfmd-options: {seed-labels: draft}`): the labels of the rest of the document come from a
  LaTeX pass over the WHOLE document without output (`-draftmode` for LuaLaTeX and pdfLaTeX, `-no-pdf` for XeLaTeX), run
  on the LaTeX Pandoc wrote for the scan, with the parts' markers in it. Its `.aux` is read exactly as a cached full
  build's is, so the numbers, the house number style and the parts' counters are exact, not counted; the scan still fills
  in what that pass does not know. It costs about half a compile of the whole document, on every part build (the cache's
  `.aux` is free but has to exist), which is why it is not the default.

## v3.26.0 — 2026-10-09

Pre-edit state: commit `8257ff7` (v3.25.20).

### Added

- A part of a split document (`report#methods`), or a section of an ordinary document (`doc#results`), built on its own
  now shows the numbers of the rest instead of `??`, without the cache and without an earlier full build. Pandoc writes
  the LaTeX of the whole document once more (no images, no engine; about a second), the new `pdfmd_labels` package reads
  it for what steps a counter or defines a label (numbered headings, captions in figures and tables, equations and align
  rows, labels, `\appendix`, footnotes, the parts' markers), and the TeX it renders replays those events at
  `\AtBeginDocument` in a box that is thrown away, with the `.aux` write redirected: LaTeX does the counting, so Roman
  `\thesection`, `\counterwithin`, package counters and cleveref's `\cref` entries come out as in the full build, and
  every counter and `\the...` macro is put back afterwards. A part's own sections, figures and equations continue from
  the parts before it. A label is defined only if nothing defined it before: the part's own, then the last full build's
  `.aux` (cache on; exact), then the scan. Approximate where the document defines its own macros (that label stays `??`);
  `\pageref` stays `??`. The build says "N labels counted from the sources".
- `pdfmd-options: {seed-labels: auto|aux|scan|draft|off}` and `--seed-labels MODE`. `auto` is the default (`.aux`, then
  the scan), `aux` the old behaviour, `scan` the scan alone, `off` the old `??`. (`draft`: see v3.26.1.)
- `test_sections.py`: the no-full-build test builds with `--seed-labels off` (the default now counts the labels).
- `tests/test_labels.py`: the scanner and the rendered TeX on fixed LaTeX (no Pandoc), a mode/trigger table, and builds
  of a part and of a section compared with the full build (Pandoc, LuaLaTeX, pdftotext).

## v3.25.20 — 2026-10-09

Pre-edit state: commit `4c468e6` (v3.25.19).

### Tests

- The old-Pandoc notice tests point the config folder at a temporary one on Windows too (`APPDATA`, which is where
  `config_root()` looks there); on a Windows runner the "said once" notice could already exist and the test failed.

## v3.25.19 — 2026-10-09

Pre-edit state: commit `840ef6f` (v3.25.18).

### Fixed

- **`pdfmd --help` no longer crashes on a console that cannot show every character**: the `--translit` help carries a
  CJK sample, and a Windows pipe or console in cp1252 raised `UnicodeEncodeError` (empty output, exit 1) for
  `--help all` and for the `fonts` topic. Characters the console cannot show now print as `?`.

### Tests

- The first push of the 3.24.20-3.25.18 line failed the CI matrix (Windows, macOS and Linux, no Pandoc installed there)
  because several tests assumed the author's machine. Tests that build a document through Pandoc are skipped without it;
  the tests whose stand-in programs are `sh` scripts (the direct HTML route, the SVG converters, `pandoc-crossref`) are
  skipped on Windows; the browser-choosing tests no longer see a Chrome that is really installed (macOS runners have
  one); the backup-folder test builds its absolute path from the temporary folder instead of writing `/abs`.

## v3.25.18 — 2026-10-09

Pre-edit state: commit `137aea7` (v3.25.17).

### Changed

- **`docs/recipes.md` is a manual now**, not eight short answers: fifteen chapters (the basics, a project with a house style,
  long documents, tables, code and images and raw pieces, other inputs, other outputs, the PDF that carries its source,
  history and backups, fonts and scripts, finishing a PDF, speed, the editor / VS Code / completion / setup, what to do
  when something looks wrong) with the commands of every feature and a task-to-option table at the end.
- The raw option (`pdfmd-options.raw`) hands LaTeX to pdfmd's LaTeX route for the families that take it: a Typst or HTML
  build whose family lists `tex` now turns that route on (`\ce`, units and equations native, tikz and chemfig drawn as vector
  pictures in the document's own preamble), instead of reading the LaTeX with Pandoc's plain reader; where the route is
  off or missing the plain reader is still the fallback.

## v3.25.17 — 2026-10-09

Pre-edit state: commit `86d71a7` (v3.25.16).

### Added

- **Raw passthrough: `pdfmd-options: {raw: ...}`, `--raw`, `--no-raw`, `--raw-for FAMILY=SYNTAXES`.** Pandoc keeps raw pieces
  written in the format it writes and silently drops the others. `raw` is a table per output family (`tex`, `typst`,
  `html`, `office`) of the syntaxes (`tex`, `html`, `typst`, `office`) that take part: the family's own stay, the foreign
  ones are carried over by the new `pdfmd_lua/raw.lua` -- HTML read by Pandoc's HTML reader into the target's own
  elements (`<img>`, tables, `<b>...</b>`, and a `<div>` around Markdown, with an opening and a closing tag in separate
  pieces matched), LaTeX read by the LaTeX reader, Typst drawn by `typst compile` as a cropped vector picture (PDF; SVG
  for HTML), kept in the cache by content -- and a syntax not listed is dropped, the family's own included. A family not
  mentioned is left to Pandoc as before; `raw: all`, a list, or a mapping (with `default:`) are accepted; a bad value is a
  warning. The new `pdfmd_raw` package parses it. `--setup` has an on/off entry. Tested through Pandoc 3.12 and 3.1.3 and
  through the command line (`tests/test_raw.py`).
- **PDF images in HTML builds, on by default** (`pdfmd_lua/pdf_images.lua`): a Markdown image or an `<img>` whose file is a
  PDF becomes an SVG (first page; poppler's `pdftocairo`, `mutool`, `pdf2svg` or `inkscape`) for an HTML writer -- a web
  page, an EPUB, a PDF through WeasyPrint -- kept in the cache by content; other writers are untouched. `--no-auto
  pdfimages` turns it off.

## v3.25.16 — 2026-10-09

Pre-edit state: commit `0516860` (v3.25.15).

### Added

- **VS Code.** `pdfmd --init-vscode` writes a `.vscode/tasks.json` (build, build and open, watch, extract tables; never
  overwrites one). The new `vscode/` folder is an extension over the command line, no build step and no dependencies:
  build / build and open / build as docx, odt, html, typst, tex, epub or slides, rebuild on change (terminal), extract
  tables (all, chosen numbers, or a preview), expand, `<!-- pdfmd: ignore -->` above the cursor, history / compare /
  restore, restore the source of a PDF (Explorer context menu), doctor; settings `pdfmd.command`, `pdfmd.extraArguments`,
  `pdfmd.buildOnSave`, `pdfmd.openAfterBuild`. `npm test` runs it against a stand-in for the VS Code API and the real pdfmd;
  `vsce package` produces the .vsix. It is not in the PyPI package.

### Fixed

- `--extract-tables` on a document with no front matter (read as gfm): the check read the new document as plain gfm, in
  which a `.csv` block is not a table, so it always refused; it reads it as `gfm+fenced_divs`, which is what the build
  uses. A table with a `: text` line under it is left alone there (gfm reads the line as a paragraph; a CSV block
  would take it as its caption), with the reason.

## v3.25.15 — 2026-10-09

Pre-edit state: commit `4d9339c` (v3.25.14).

### Added

- **`pdfmd --edit [FILE]`: a small full-screen editor (alpha).** Nano-like, in the new `pdfmd_edit` package on the
  optional `tui` extra (prompt_toolkit; `pdfmd --install tui`): Ctrl-S save, Ctrl-B save and build (the last lines of
  pdfmd's output stay at the bottom), Ctrl-P open the result, Ctrl-W / F3 find, Ctrl-G go to a line, Ctrl-K / Ctrl-U cut
  and paste a line, Ctrl-Z / Ctrl-Y undo and redo, Ctrl-X exit (asks once about unsaved changes), F1 help. Saves go
  through a temporary file, options given beside `--edit` are used for the build, and a new name starts a new file. Rough
  on purpose: a base for the interface of a later release. Tested with scripted keys through prompt_toolkit's pipe input
  and by hand in a pseudo-terminal.

## v3.25.14 — 2026-10-09

Pre-edit state: commit `b014262` (v3.25.13).

### Changed

- **`pdfmd --help` is one short page** (about 30 lines, down from 651): the usual jobs, a dozen options and the list of
  topics. `pdfmd --help all` is the complete list as before; `pdfmd --help TOPIC` is that list for one subject (`output`,
  `modes`, `source`, `tables`, `history`, `code`, `fonts`, `builtin`, `office`, `cache`, `setup`, `debug`; `other` shows
  options no topic claims, and a test keeps that empty). `-h` is the same. The topics live in the new `pdfmd_help`
  package; a lone `pdfmd.py` keeps argparse's single page. The README says that `pdfmd` alone builds the one Markdown
  file of a folder.

## v3.25.13 — 2026-10-09

Pre-edit state: commit `2dbf316` (v3.25.12).

### Added

- **A PDF can carry its source with nothing lost (source parity).** The `metadata` comment kind (new in
  `strip-comments`, `--strip-comments-in`, `--keep-comments-in`): where it is kept (`strip-comments: false`, or
  `{metadata: false}`), the attachment stores each metadata YAML file and the document's front matter as written, and
  `--restore` writes them back byte for byte when they still read as the same data (else the rewritten file, as
  before). Until now a YAML file lost its `#` comments and its quoting in the merge. Tested on a real split-file report:
  every file of the restored folder, `report.md` included, is identical to the original.
- **The data of `.csv` blocks travels with every attached source** (`tables/*.csv`, up to 5 MB each), bundle or not: the
  merged text names those files and cannot build without them. `--restore` puts them back.
- `--table-numbers 1,3-4` with `--extract-tables`: only those tables, by their position in the document; `--table-names`
  then names just the chosen ones.

### Fixed

- `--extract-tables` on a document in parts: the files went to `parts/tables/` and the check read the part as a document of
  its own (`gfm`, no front matter), so a part's `file="tables/x.csv"` was checked against a folder the build never uses.
  The report's folder and the report's reader are used now, and a table without a caption is named after its part
  (`discussion-table1.csv`), so the parts no longer fight over `table1.csv`. `--table-names` works on one part.
- `--extract-tables` refused a pipe table whose separator had equal dashes and whose rows were too wide for the page
  ("widths differs"): Pandoc gives such a table equal column shares, which the table-width filter reads as "not
  chosen", the same as none. The check treats them alike, and no `widths=` is written (it would have turned a balanced
  table into a fixed 20%-per-column one).

## v3.25.12 — 2026-10-09

Pre-edit state: commit `382f589` (v3.25.11).

### Fixed

- **A document using nulabreport (or anything that rewrites `\[`) no longer fails in LaTeX when it has code.** Found
  building a real report (`LR1-2`): from 3.25.3 the code-wrapping header loaded `fvextra`, which loads `lineno`, which
  rewrites `\[`, `\]` and the `equation` environments to number the lines of displays; nulabreport copies and replaces
  `\[` afterwards, and the copy broke (`\begin{linenomath} on input line 484 ended by \end{equation*}`). All three LaTeX
  engines failed and the PDF came from the Typst fallback, without a word of the LaTeX the report needs. 3.24.19 built it
  in 24 pages; so does this version. `code_wrap.tex` now defines `\mathindent` while `fvextra` loads (lineno then leaves
  those environments alone), takes lineno's amsmath hook out, and pdfmd puts the file before the document's own preamble.
  A regression test mimics the `\[` override. (The nulabreport smoke build was due at the end of the line and had been
  postponed; it passes on this version.)
- The note after `--assemble-only` that CSV data and raw-LaTeX images are "never embedded" is not printed when the `files`
  kind was used, and names the kind when it was not.

### Changed

- **`--history-to-file` moves the whole BUILD NOTES block pdfmd owns**, not only its "Compiled" lines: anything written by
  hand inside it travels as one `note` entry (`block=1`) and `--history-to-notes` builds the block again. A block that is
  not pdfmd's is still left alone, and a second move does not copy the text again.

### Added

- **`<!-- pdfmd: ignore -->`** on the line above a table or a `.csv` block, or under a table's caption, keeps
  `--extract-tables` and `--expand-tables` away from it (reported as `SKIP ... marked`). Like every comment that starts
  with `pdfmd`, it survives comment stripping; the BUILD NOTES block does not (it is stripped from assembled and attached
  copies, and Between a table and its caption is not supported: Pandoc
  would no longer read the caption as one.
- **`--extract-inline-csv`** (implies `--extract-tables`): also moves the data of `.csv` blocks that hold it inside the
  document to `tables/<caption or identifier or csvN>.csv`, keeping the block's other attributes.

### Tests

- The `\[` override with code; the whole block out and back (no duplicate text, another author's block untouched);
  marks above/below/after the last thing, the comment under a caption going to the next table; extract, inline extract and
  expand honouring them; stripping keeps the mark and drops the BUILD NOTES.

---

## v3.25.11 — 2026-10-09

Pre-edit state: commit `e3e1125` (v3.25.10).

### Compatibility with Pandoc 3.1.3

The claude.ai sandbox has Pandoc 3.1.3; the whole suite was run against it (a downloaded release binary) and what broke
was fixed or, where Pandoc lacks the feature, recorded and skipped.

- **Lua filters on a Pandoc without `pandoc.Caption`, `pandoc.TableBody`, `pandoc.log`** (all 3.2 or later): the CSV and
  office filters define stand-ins (a caption is `{long, short}`, a body a plain table), so they, and a house style's
  `office.lua` written for a newer Pandoc, run on 3.1.3. Before, every CSV block with a caption and every Word build with a
  numbered equation stopped with "attempt to call a nil value".
- **pandoc-crossref built for another Pandoc is not run.** It prints "not supported" and leaves `??` where the numbers go;
  pdfmd now reads its `--version`, and when it was built for another Pandoc than the one running, says so once with the
  release to get and does not run it.
- **Cross-reference detection** (`@tbl:x`, `{#tbl:x}`) also finds a label that an older Pandoc leaves in a table caption as
  words (it only reads it as the table's identifier from 3.8.2).
- **`--extract-tables`** leaves a table whose caption has attributes when Pandoc is older than 3.8.2, with the reason,
  instead of failing the check for the whole document.
- **Known degradations** (`PANDOC_FEATURES`, listed by `--doctor`): Typst PDFs with a picture pdfmd drew (before 3.2), the
  borderless style of a numbered equation in a Word file (before 3.4), caption attributes (before 3.8.2).
- **`PANDOC_MIN` = 3.1.3.** The first compile with an older Pandoc warns once per version; `--doctor` says so too.

### Added

- **`scripts/build_zipapp.py` makes `dist/pdfmd.pyz`**, pdfmd and its packages with PyYAML and pypdf in one file (1.4 MB),
  for a machine with no network. It unpacks itself once into `~/.cache/pdfmd/pyz/<hash>/` because Pandoc must open the Lua
  filters and headers as real files. Run with `python3 -S` (no site-packages) in the tests: the bundled PyYAML and pypdf
  are the ones used. README: the same with `pip download` and `--no-index --find-links`. (Not added to the release workflow:
  that could not be tried here.)
- README "Why": entries for CSV tables, code and images, finished files and the hybrid PDF, and history.

### Tests

- The suite passes on Pandoc 3.12 and on 3.1.3 (597 tests, 9 skipped for the three known differences). New:
  `tests/pandoc_support.py` (`needs_pandoc(3, 4)`), version logic, the one-time warning, the crossref mismatch, the zipapp
  built and run with `-S` and building a document with its filters.

---

## v3.25.10 — 2026-10-09

Pre-edit state: commit `4755334` (v3.25.9).

### Added

- **`--hybrid`: the PDF opens in LibreOffice as an editable document.** LibreOffice's "hybrid PDF" is a PDF with the
  document it was made from attached as `Original.odt` (`.odp`, `.ods`), described "Embedded original document of this PDF
  file", with the ODF mime type as the attachment's subtype. Checked by experiment: LibreOffice goes by that attachment, not
  by the pages (a LaTeX-built PDF with an unrelated `.odt` attached opened as the `.odt`), so any engine's PDF can carry
  one. An Office file is converted by LibreOffice (`.docx` to `.odt`, `.pptx` to `.odp`, `.xlsx` to `.ods`); anything else
  is built to `.odt` by pdfmd itself with the same metadata. A PDF that already has one is left alone, other attachments
  are kept. `--no-hybrid`, `pdfmd-options.hybrid`, and an entry in `--setup`. `--restore` writes the ODF file back, for a PDF
  made by LibreOffice's own export as well as pdfmd's.
- **`--embed-metadata files` / `all`: an assembled file carries the files the text points at.** The images (Markdown and
  raw LaTeX), CSV data (`.csv` blocks, pgfplots), and `\input`ed files become `type: file` blocks (text as it is, anything
  else base64 with a hash), are written to a scratch folder for the build and found like the document's own folder, and
  `--unpack` writes them back byte for byte (`--slim` leaves a clean document). The result builds alone in an empty folder
  with its table and both kinds of image. Not in the default kinds (size; `bundle-max-mb` caps it); `embed: all` now means
  every kind, `embed: true` the default ones.

### Fixed

- **`TEXINPUTS`** for a build with embedded files had no separator after `.` (the embedded folder was glued to it);
  raw LaTeX images are found now.

### Tests

- The attachment's structure against what LibreOffice writes, no second one, other attachments kept, restore; a Markdown
  PDF and a `.docx` built with `--hybrid` (LibreOffice opens the first as its source); the block round trip for text, binary,
  empty; unpack byte for byte; and the single file built alone.

---

## v3.25.9 — 2026-10-09

Pre-edit state: commit `dc02d9d` (v3.25.8).

### Added

- **`pdfmd --history FILE`** lists a file's versions newest first in one numbered list: its backups -- the configured
  folder and every folder of the spellings in use beside the document (`.backups`, `backup`, `backups`, `.backup`,
  `_backups`), whichever of the five naming forms each file has -- the git commits that changed it (the repository may be
  above the document's folder), and the compiles and restores recorded in its `.hst` or BUILD NOTES that no backup
  holds. A backup shows what was compiled when it was taken. The newest 15 are shown, `--history-all` lists the rest; in a
  terminal the list is navigable (a number: what differs, `d N`, `r N`, `a`, `q`). A document in parts lists its parts too.
- **`--history-diff REF` and `--history-restore REF`** (`--dry-run` shows without writing). REF: a number of the list, a
  backup's timestamp (any prefix), a file name, a commit hash, `latest`, or `previous` (the newest version that is not
  the file as it is). A restore backs the file up first, keeps the BUILD NOTES and history of the file as it is, and adds a
  `Restored version ID (NAME)` entry -- to the `.hst` when the document keeps one, else to its BUILD NOTES -- unless
  `pdfmd-options: {stamp: {restored-note: false}}` (in `--setup`) or `--no-restored-note` says not to or the document
  was never stamped. BUILD NOTES and `.hst` now hold `Restored` entries as well as compiles; a compile in the `.hst` also
  records `git=<hash>` (a `+` when the file differed from it).
- **`pdfmd --init-backups FILE`** sets `backup` and `stamp: {store: file}` in the file's front matter (or its
  metadata.yaml) under an `# AUTO GENERATED` comment, leaving whatever is there alone, makes the folder
  (`--backup-folder DIR`, default `.backups`), backs the file up once and starts its `.hst`. A document with no front
  matter and no metadata file is not given one (it would change how pdfmd reads it: Pandoc's markdown, not GitHub's);
  `--init-backups --global` sets the same in the config for every document.

### Deviation from the plan

- `--init-backups [FOLDER]` became `--init-backups` with `--backup-folder FOLDER`, for the reason `--table-names` exists:
  argparse would take the file name as the folder.

### Tests

- Backups of three naming forms in two folders and git commits from a repository above the document, truncation and
  `--history-all`, the ways to name a version, `previous`, diff, restore (the file backed up first, the notes of the newest
  file kept, the entry in the `.hst` or in BUILD NOTES, none for an untracked document, `--no-restored-note`), a commit
  restored, the interactive loop, and `--init-backups` (front matter, an existing `pdfmd-options` extended, no front
  matter refused, `--global`).

---

## v3.25.8 — 2026-10-09

Pre-edit state: commit `738426a` (v3.25.7).

### Added

- **The build history can live in a file, `NAME.hst`, instead of in the document** (new package `pdfmd_history`). The
  format is one entry per line, newest first: `WHEN | KIND | TEXT | key=value ...` (compiled, restored or note; the
  hash of the source and the output name as extra words), so two files join with `cat`, diff cleanly and merge line by
  line; anything in the file that is not an entry is kept as a comment. It lives in the document's backup folder.
  `--stamp-store notes|file|both` (`pdfmd-options.stamp.store`, in `--setup`) says where a compile is written;
  `file` leaves the document untouched by a build. `--merge-history A B [-o OUT]` joins files, each entry once.
- **`--history-to-file` / `--history-to-notes`** move pdfmd's own lines (the "Compiled ..." line and the "Compile
  History:" list) between a document's BUILD NOTES and its `.hst`; the document is backed up first, `--dry-run` shows
  what would move, the file is written before the document is changed, and what else is in the block stays.
- **BUILD NOTES blocks that are not pdfmd's are left alone.** A document can carry several (the author's, an AI agent's):
  pdfmd now writes into the block that already holds its lines, else into the only block there is (the convention it has
  always automated), else -- several, none its own -- into a block of its own. A line `pdfmd: ignore` in a block keeps
  pdfmd out of it. Before, it wrote into whichever came first.
- **`hst` is an embed kind**: `--embed-metadata` folds the `.hst` into the assembled file (a `type: hst` block), `--unpack`
  writes it out (`--slim` takes the block away), `--attach-source` stores it in the PDF and `--restore` writes it back
  into the backup folder.

### Tests

- The format (escapes, merge, comments), which block is chosen, moving lines out and back with other people's text
  untouched, the commands with a real document, a compile written to the file only and to both, merge from the command
  line, and the history through an assembled file, `--unpack --slim`.

---

## v3.25.7 — 2026-10-09

Pre-edit state: commit `8044f2c` (v3.25.6).

### Added

- **SVG images in LaTeX builds** (new package `pdfmd_images`, filter `pdfmd_lua/images.lua`). LaTeX cannot read SVG; a
  raw `\includegraphics{a.svg}` failed outright, and a Markdown SVG needed `rsvg-convert` (in a sandbox without it:
  "Package svg Error"). Each SVG a document names is now converted once, with the first converter found (rsvg-convert,
  Inkscape, cairosvg, svglib, LibreOffice: Draw sizes the page to the drawing), kept in `~/.cache/pdfmd/images` by the
  file's content, and put where the document wrote the SVG (Markdown image, raw `\includegraphics`, raw `\includesvg`).
  A Markdown SVG is left to Pandoc when rsvg-convert is there. Without any converter there is one `WARN` naming the file
  and what to install; `--doctor` shows the converter. `--no-auto svg` turns it off.
- **Remote images are fetched once and kept** (seven days; an older copy is kept if a refetch fails; PNG, JPEG, SVG,
  PDF; 20 MB; 10 s). Pandoc from Homebrew is "compiled without HTTP support" and dropped every badge of the README
  (replacing it with its description); they now arrive, an SVG badge is converted, and the second build needs no
  network. With no network there is one `WARN` (not one per image) and Pandoc leaves the descriptions.
  `--no-auto remoteimages` turns it off. For LaTeX builds only, like the SVG conversion.

### Fixed

- **A raw `\includegraphics` in a document with no Markdown image** stopped the build ("Undefined control sequence"),
  whatever the file: Pandoc loads graphicx only when it sees an image. pdfmd now adds `\usepackage{graphicx}` then.

### Not done

- `<img>` tags in Markdown (the README's screenshots) are raw HTML and are still dropped from a LaTeX build.

### Tests

- The scan (code, comments, front matter skipped; titles and `<...>` paths), conversion kept by content, the next
  converter tried, no converter, the Lua map on Markdown and raw LaTeX, a local server for fetch/cache/expiry/errors/dead
  network, an SVG badge through to the map file, and raw SVG end to end.

---

## v3.25.6 — 2026-10-09

Pre-edit state: commit `500ed2a` (v3.25.5).

### Added

- **A `.typ` file is compiled by Typst itself, and an `.html` file is printed by its own engine; Pandoc is not
  involved** (new package `pdfmd_direct`). Pandoc read these into its own model and wrote them out again, losing the
  page setup, the styles and the scripts: the same PDF now keeps the document's own page size (an A5 `@page`, a
  `#set page(width: 12cm)`), where the Pandoc route gave US Letter. For a page, WeasyPrint is tried first; a page with
  a `<script>` that is not data goes to a browser first (Chrome, Chromium, Edge, Brave, found on PATH or where the
  installer puts them; `PDFMD_BROWSER` names one), then wkhtmltopdf, Prince, pagedjs-cli and LibreOffice; a failing
  engine falls through to the next one with the usual `WARN`. `-e weasyprint|chrome|chromium|edge|brave|browser|html`
  picks; `-e` naming another kind of engine, `--from`, a target other than PDF, `--no-auto typstdirect|htmldirect`
  (listed in `--setup`), or the engine not being installed keeps the Pandoc route, with a `WARN` for the missing tool.
  No Pandoc is needed. Some browser builds write the PDF and then keep running; pdfmd waits for the file to be complete
  and stops the browser. `--doctor` lists what HTML and `.typ` files go to.
- **`--apply-defaults` / `--no-apply-defaults`** (and `options: {apply-defaults: true}` in the config, or `--setup`):
  a direct document gets none of the defaults a Markdown one does; this gives it the title, author, date, language, main
  font, font size, paper size and margin of its metadata files (those found beside it, the global one, or `-y`), without
  Pandoc. They are written ahead of the document's own settings so those win (`#set document/text/page` lines for Typst;
  a `<title>`, `<meta name=author>`, `lang` and a `<style>` at the start of `<head>` for HTML), in a copy beside the
  original that is removed afterwards; a Typst error names the original file and its own line numbers.
- **A `.tex` file that no LaTeX engine can compile is tried through Pandoc** (the old route), with a `WARN` that says
  the LaTeX is rewritten on the way and may look different. With no Pandoc the failure is returned as before.

### Tests

- Engine order and requests, a failing engine falling through, a browser that stays running (fake executables on a
  scratch PATH, so they run anywhere), the route decisions, Typst and WeasyPrint end to end (page size kept, no Pandoc on
  PATH, a Typst error leaves no PDF), the defaults for both formats and the config switch, and the `.tex` fallback.

---

## v3.25.5 — 2026-10-09

Pre-edit state: commit `a84a912` (v3.25.4).

### Fixed

- **`--extract-tables` read every document as Pandoc's own `markdown`, whatever reader the build used.** A document
  with no YAML front matter is built as `gfm`, where grid, simple and multiline tables are plain text; extracting them
  would have turned text into tables. Both the extraction and the check now use the reader the build would use, and
  under `gfm`/`commonmark` only pipe tables are touched, with a `NOTE` saying how many others were left (front matter
  or `--from markdown` makes them tables).
- **A simple table without a header** (a rule of dashes, rows, a closing rule) was not seen at all; it is now found
  and reported as skipped, with the reason (a CSV block always has a header row).

### Tests

- A document mixing `.csv` blocks (inline and from a file) with pipe, grid, headerless and block-celled tables: the
  blocks are left alone, the unconvertible tables are skipped with a reason, `--expand-tables` gives back the CSV
  file untouched; a failed check exits 1 and writes nothing (no CSV, no backup); a `gfm` document gets pipe tables
  only. The built PDF text of the mixed document is the same before and after extraction.

---

## v3.25.4 — 2026-10-09

Pre-edit state: commit `1a7b146` (v3.25.3).

### Fixed

- **Code did not wrap in a document where pdfmd had added a header of its own.** 3.25.3 put the line that loads fvextra
  into the document's `header-includes` from the Lua filter, but Pandoc lets `--include-in-header` win over
  `header-includes`, so the line vanished from every build that also had pdfmd's font header (a document with other
  scripts in it, the README among them). The line is now a file, `pdfmd_lua/code_wrap.tex`, passed with
  `--include-in-header` and only for a document that has code (fenced or indented); the filter turns a language-less
  block into a `Verbatim` only when told the header is there. Inline code is still not wrapped.

---

## v3.25.3 — 2026-10-09

Pre-edit state: commit `8a68435` (v3.25.2).

### Added

- **Long code lines wrap in LaTeX builds.** Pandoc's `Highlighting` and `verbatim` environments cannot break a line, so
  a long command or path ran past the margin (the README's own `CMD` line did). The new filter `pdfmd_lua/code.lua`
  loads fvextra with `breaklines` (breaking anywhere when a line has no space to break at), and turns a block with no
  language into a fancyvrb `Verbatim`. A TeX without fvextra still builds, unwrapped. `--no-code-wrap`, `pdfmd-options:
  {code-wrap: false}`, `--no-auto codewrap`, and `{wrap=false}` on a block switch it off; Typst, WeasyPrint and HTML
  already wrapped.
- **Optional line numbers**, off by default: `--line-numbers [STEP]`, `pdfmd-options: {line-numbers: true,
  line-number-step: 5}` and the `--setup` entries number every code block; per block `{.numberLines startFrom=10
  step=5 numbersep=8pt}` and `{.noNumberLines}`.

---

## v3.25.2 — 2026-10-09

Pre-edit state: commit `64044d7` (v3.25.1).

### Added

- **`pdfmd --extract-tables FILE`** turns every table of a document (pipe, simple, multiline or grid; code blocks are
  skipped) into a `.csv` block reading `tables/<name>.csv`, or holding its data (`--tables-inline`); `--tables-dir`,
  `--table-names a,b,c` (the count must match the tables, or it is an error), `--dry-run`. Captions become `caption=`,
  alignments `align=`, chosen widths `widths=`; a table over the 10 x 7 cap gets `rows=all`/`cols=all`. Pandoc reads the old
  and the new document and the tables must be identical before anything is written; the old file is backed up first;
  tables Pandoc cannot write as CSV are left with the reason. A document in parts is done part by part.
- **`pdfmd --expand-tables FILE`**, the reverse: every `.csv` block becomes a pipe table, all rows, `caption=` as the
  `: caption` line. The package behind both is `pdfmd_tables/`.
- **`widths="30%,60%"`** on a `.csv` block: with a % on every number the shares of the text width itself (what a grid
  table's columns ask for), not just relative.

### Changed

- **Backups go to `.backups/` by default** (was `backup/`): a hidden folder, and the first time pdfmd writes there it says
  so. A `backup/`, `backups/`, `.backup/` or `_backups/` folder that is already beside the document is kept using, and
  `pdfmd-options: {backup: {dir: ...}}` or `pdfmd --setup` ("Backup folder") still names any place.
- A `.csv` block whose attributes hold braces in quotes (`caption="Masses {#tbl:m}"`) is recognised by the native tier too.

---

## v3.25.1 — 2026-10-09

Pre-edit state: commit `70baa48` (v3.25.0).

### Added

- **`.csv` blocks can hold their data.** A `::: {.csv}` div with no `file=` reads the data written inside it, from a
  fenced code block (verbatim: nothing in it is Markdown) or from plain lines; a file named by `file=` wins when both
  are there. Quoted fields may contain line breaks (the file reader read line by line before).
- **Any delimiter.** `delimiter=` takes a character or a name (`comma`, `semicolon`, `tab`, `pipe`, `space`, `colon`);
  without one the extension decides (`.tsv`), else the first line (whichever of `,` `;` tab `|` it holds most of).
- **Alignment and widths for CSV tables.** `align="lcr"` / `align="left,center,right"`, or a second data row of `---`,
  `:--`, `:-:`, `--:` read as a pipe table's separator row (`separator="none"` keeps such a row as data; `align=` wins
  over the row); `widths="5,1,1"` gives relative widths, kept as written even when equal, and unequal dashes in the
  separator row are widths too. The native tier (no Pandoc) reads all of it except `widths=`.

---

## v3.25.0 — 2026-10-09

Pre-edit state: commit `0ff734c` (v3.24.26). First commit of the 3.25 line (tables, code blocks, direct routes,
history and restore, images); nothing of it is pushed until the whole line is done.

### Changed

- **A `---|---` pipe table is laid out by its content.** Pandoc gives a pipe table whose lines run long the widths of
  its separator dashes, and the usual `---|---` is the same count in every column, so such a table came out in equal
  columns whatever it held (the README's own tables: a one-word key column as wide as the prose beside it). The
  filter now reads equal dashes as "no opinion" and picks the widths that make the rows take the fewest lines within
  the text width, a column never narrower than its longest word nor wider than its longest cell; a table that
  fits is given back its natural width. Unequal dashes (`--|-----`) are a choice and are kept. `pdfmd-options:
  {table-widths: keep}`, the same key in the config or `--setup` ("Pipe-table column widths"), switches it off;
  `--no-auto tablewidth` still removes the filter altogether.
- **pdfmd's Lua filters are files now.** The table-width and CSV-table filters were Python strings inside
  `pdfmd.py`; they live in the package `pdfmd_lua/` (`table_width.lua`, `csv_table.lua`), as `pdfmd_office/office.lua`
  already did. A lone copy of `pdfmd.py` without the package still builds, only without the two filters.

---

## v3.24.26 — 2026-10-09

Pre-edit state: commit `7b111ba` (v3.24.25).

### Fixed

- **Several equations in one raw LaTeX block were drawn as one broken picture in Word files.** A
  ```` ```{=latex} ```` block holding `\begin{equation}..\end{equation}` three or six times in a row was matched from the
  first `\begin` to the last `\end`, which LaTeX rejected ("You can't use \eqno in math mode") and the whole group was
  lost. The filter now splits such a block into its environments, and each is a native Word equation with its own number.
- **References to labels in a split document stayed `??` in Word files.** The numbers LaTeX gave the labels are read from
  one PDF build of the document, but that build was only started when the main file itself mentioned a label, and a
  document whose equations and references live in its parts never did. The parts are read (and watched for changes) too.

---

## v3.24.25 — 2026-10-09

Pre-edit state: commit `527e61c` (v3.24.24).

### Changed

- **README (docs only).** "Why" and the opening now say that pdfmd writes Word and OpenDocument files that follow the
  document's page setup and fonts, carry its LaTeX over as native Word text or vector pictures, and are switched by
  `office: {latex: auto|images|off}`, `--no-auto officelatex` and `--setup`. "Not just Markdown" says a Typst source is
  read as Typst and that the automatic Markdown decisions apply to Markdown files only; the `AUTO` table says the same
  and how citations and crossref are detected; the install note no longer calls `pdfmd.py` a single file (four package
  folders sit beside it); the `--doctor` sample shows batchocr 1.2.5.

---

## v3.24.24 — 2026-10-09

Pre-edit state: commit `8f4a027` (v3.24.23).

### Fixed

- **Syntax a document writes *about* was taken for syntax it uses.** Whether a Markdown file has citations, or uses
  pandoc-crossref, was decided by a pattern over the raw text, so `@fig:setup` in backticks or a code block (as in
  pdfmd's own README), an e-mail address or an escaped `\@` switched on `--citeproc`, the `pandoc-crossref` filter and the
  full `markdown` reader (which sizes every pipe-table column equally) for a document that used none of it. pdfmd now asks
  Pandoc's own Markdown reader once per file state (one `-t json` parse, remembered while the file is unchanged) and looks
  for citations, crossref references and crossref labels (`{#fig:..}`, `{#tbl:..}`, `{#eq:..}`, `{#sec:..}`, `{#lst:..}`)
  in what it read. With no Pandoc the old pattern is the fallback, as before. The README now builds as `gfm`
  without a crossref warning.

---

## v3.24.23 — 2026-10-09

Pre-edit state: commit `c54ad1c` (v3.24.22).

### Fixed

- **A preamble in the front matter was drawn as a picture in Word files.** `header-includes: | \usepackage{tikz}` is
  LaTeX for the preamble, but Pandoc's filters walk the metadata too, so the Word filter treated the block as content,
  tried to draw it ("can be used only in preamble"), warned, and listed it in `--check-docx`. The filter now takes
  LaTeX out of `header-includes`, `include-before` and `include-after` before it looks at the document (the Word, ODF,
  HTML and Typst writers do not use it).
- **`office: {latex: images}` did the same as `auto`.** It is now what `--setup` says: formulas, `\ce`, `\si`/`\SI`/`\num`
  and equation environments are drawn by LaTeX as pictures (vector with a PNG fallback) instead of being made native;
  `auto` (the default) still makes them native where it can, `off` is Pandoc's own behaviour.

---

## v3.24.22 — 2026-10-09

Pre-edit state: commit `7cd78d5` (v3.24.21).

### Fixed

- **A `.typst` file was read as Markdown.** Pandoc knows `.typ` but not `.typst`, and an extension it does not know
  means Markdown, so the PDF held the Typst source as text. `.typ` and `.typst` now always give `-f typst` (with an
  `AUTO READER` line for `.typst`, and a Pandoc without the Typst reader fails by name instead of printing the source).
- **The Markdown-only helpers ran on any file.** The scan for `@key` citations (which added `--citeproc`, so a Typst
  `@label` became a citation and printed as `[label]`), the one for pandoc-crossref's syntax and the promotion of a
  leading `# Title` now look at Markdown (`.md`, `.markdown`, `.mdown`, `.mkd`, `.txt`) only.
- **`--to md` failed** ("Unknown output format 'md'"). `--to` takes the names of the files as `default-output:` does:
  `md`, `tex`, `typ`, `txt`, `htm`.

---

## v3.24.21 — 2026-10-09

Pre-edit state: commit `73818f4` (v3.24.20).

### Fixed

- **Parts mode and `doc#section` work with every engine.** The soffice route (`-e soffice`, and the last resort when
  every other engine fails) refused a split document or a section ("the soffice last-resort fallback doesn't support
  parts mode or sections"); the built-in renderers (no Pandoc) refused them too. The soffice route now takes what every
  other engine takes (the document cut down to its sections, the parts joined after it, the partial-build mark), and
  is also given the same corrected inputs as `--to docx` (an embedded preamble is dropped). The built-in renderers
  read the same text as one Markdown file: the parts joined after the document, a heading inside a part cut out of it.
- The built-in renderers no longer list pdfmd's own `pdfmd-assembled`/`pdfmd-partial` marks as "front-matter keys not used".

---

## v3.24.20 — 2026-10-09

Pre-edit state: commit `5900c3b` (v3.24.19).

### Fixed

- **Tables narrower than the page sat at the left margin in the LibreOffice route.** pdfmd's table styles say
  `centre`, but LibreOffice ignores a table style's alignment (Word honours it), so `pdfmd -e soffice` and anything
  else drawn by LibreOffice showed Table 4, 5, 6 and the like flush left while LaTeX centres them. The alignment is now
  written into each table of pdfmd's own styles in the `.docx` itself, after every Word build (the soffice route's
  intermediate file included). A table that already says where it sits, a template's own table style and a house
  style's form table are left alone.

---

## v3.24.19 — 2026-10-08

Pre-edit state: commit `faabca0` (v3.24.18).

### Fixed

- **`AUTO YAML` printed the long path for a symlinked metadata file.** The short (relative) form of a path was worked out
  from the file after following its symlink, so `metadata/metadata.yaml` linking to a shared house-style file outside the
  folder fell back to the absolute path. The folder is resolved, the link itself is not: it is shown where it sits
  (`metadata/metadata.yaml`). The same goes for every other AUTO/CMD line (`--full-paths` still prints absolute paths).

---

## v3.24.18 — 2026-10-08

Pre-edit state: commit `19d7d03` (v3.24.17).

### Fixed

- **`::: {.csv ...}` cells were read as GFM only**, so `H~2~O`, `$x^2$`, `\ce{...}` and `[@key]` in a CSV stayed literal. They are
  read as Pandoc Markdown now (`reader="gfm"` for the old behaviour).
- **A `: Caption` after the block printed as a paragraph**: the caption syntax belongs to a table the reader has already
  seen, and the table was made later by the filter. The filter takes the `: Caption {#tbl:id}` (or `Table: Caption`) paragraph
  after the block as the table's caption and identifier. Moved ahead of pandoc-crossref, the csv filter's tables are numbered and
  referenced like any other (`@tbl:id`); the house convention (`\label{...}` in the caption, `\cref`) works as for a pipe table.
- **A relative `file=` was looked for in the folder of the metadata file** (where Pandoc runs), so a report with `metadata/`
  lost its tables; it is tried beside the document and along the resource path too.

### Added

- **`caption="..."` and `#tbl:id` among the attributes of the block**, instead of a line after it (Markdown allowed in the text).

---

## v3.24.17 — 2026-10-08

Pre-edit state: commit `8233fac` (v3.24.16), which failed its CI run and was never published.

### Fixed

- A `--setup` test that builds an HTML page ran on the CI jobs that have no Pandoc: it is skipped without one.

---

## v3.24.16 — 2026-10-08

Pre-edit state: commit `8c646c7` (v3.24.15).

### Fixed

- `H$_2$O`, `CCl$_4$`, `Fe$^{3+}$` (math that is only a script, its base being the text outside the dollars) came out as an empty box
  before the subscript: it is a real subscript or superscript now.

---

## v3.24.15 — 2026-10-08

Pre-edit state: commit `539f38d` (v3.24.14).

### Added

- **`pdfmd FILE --check-docx`**: what a Word build would make native (formulas, other LaTeX pieces) and what it would draw as
  pictures, each named by the environment or macro behind it, without drawing or writing anything (the first pass of the build
  only).

### Fixed

- A table that was still a picture: `\setcounter{table}{1}\chemicals{...}` (a house filter puts the counter in front) and
  `\chemicals{...}%` newline `{caption}` (a `%` ending a line, which TeX joins) were not recognised as the profile's
  `\chemicals`. A leading `\setcounter` now sets the filter's own counter before the command, and a `%` at a line end joins
  the lines in every raw block.
- A package's shared `chemicals.tex` (found only through TeX's own search path) is found by the filter too (`kpsewhich`, as
  a last resort).
- `PdfmdGrid` tables (the chemicals table, a `tablestyle: grid` table) are centred like the booktabs ones.
- `\ce{C=O}`, `\ce{CH=CH}` (double bond) and `\ce{HC#CH}` (triple) are native text, not pictures.

---

## v3.24.14 — 2026-10-08

Pre-edit state: commit `bd4ba95` (v3.24.13).

### Changed

- **The soffice route goes through the Word file.** `pdfmd -e soffice` (and the last-resort fallback) went Pandoc -> `.odt` ->
  LibreOffice, which lost the cover and tables of a house style and, on a nulabreport report, most of the text. It now writes
  the same `.docx` as `-o x.docx` (template, native equations and tables, pictures for what only LaTeX draws) and has
  LibreOffice turn that into the PDF; with `-e soffice` named explicitly the reference numbers come from LaTeX's own
  `.aux` like a `.docx` build, in the fallback chain they are counted (LaTeX is what failed).
- **`pick:` in a package's office yaml.** A package whose own macros choose its colour scheme says where to read the choice
  (`pick: {default, default-by-option, from-preamble: REGEX, variants}`): the last match in the preamble or the document's
  header-includes names the variant, whose `replace`/`media`/... are merged in, so the Word file follows the PDF
  (nulabreport's `\LabScheme{word|black|gold}` instead of "every course but genchem is black").
- **`--setup` covers what the config can say.** The config file's `options:` is now honoured for the `stamp`, `backup`, `unicode`,
  `header`, `footer`, `bookmarks` and `attach-links` too (it was only read for part of them), and a `metadata.yaml` beside
  `config.yaml` is global metadata, found last, so lowest in priority, whenever metadata is found automatically. The menu lists
  all of these (metadata, citations, output, PDF finishing, the source file, cache, input) and takes text and numbers as
  well as choices.

---

## v3.24.13 — 2026-10-08

Pre-edit state: commit `106b74f` (v3.24.12).

### Added

- **`--text-to-markdown [auto|force|paragraphs]`**: a `.txt` input is read as Markdown through batchocr 1.2.5 (headings,
  lists, tables and paragraphs guessed from how the text is typed; the letters and digits never change; a garbled text gets
  paragraphs only). `-o x.md` is the conversion alone; otherwise `notes.md` is written beside the text (never over an existing
  file) and the build goes on from it. Off unless asked; also `options: {text-to-markdown: ...}` in the config and a
  setting in `pdfmd --setup`.

---

## v3.24.12 — 2026-10-08

Pre-edit state: commit `bce6ad3` (v3.24.10); v3.24.11 above landed in the same commit.

### Added

- **`pdfmd --setup [plain|fancy]`**: change the global defaults from a menu instead of editing `config.yaml`. The default
  screen is a numbered list (no dependency); `pdfmd --install tui` adds prompt_toolkit for a full-screen one
  (`--setup fancy`, or `setup-ui: fancy` in the config; "This setup screen" is itself a setting, and a missing
  prompt_toolkit falls back to the list with a note). Settings: what to do about characters a font lacks or none draws, fonts
  for other scripts, romanization packs, the PDF engine, the default output format, LaTeX and reference numbers in Word
  files, the cache, and which automatic behaviours are off. The file is rewritten without comments (the old one is kept as
  `.bak`). New package `pdfmd_setup`; `--install tui` / `pip install "pdfmd-cli[tui]"`.
- **`no-auto` in the config file** (`options: {no-auto: [margin, monofont]}`) switches those automatic behaviours off for every
  document, merged with the command line's and the document's; `--setup` writes it.
- A one-time `TIP` about `--setup` after the first successful build in an interactive terminal with no config file; never in
  a pipe, in CI or from the Python API (`PDFMD_NO_PROMPT=1` silences it). `--doctor` reports which setup screens exist.

---

## v3.24.11 — 2026-10-08

Pre-edit state: commit `bce6ad3` (v3.24.10).

### Added

- **A Python API**: `pdfmd.convert_file(source, to, outputfile, ...)` and `pdfmd.convert_text(text, to, format, ...)`,
  `pdfmd.PdfmdError`, `pdfmd.pdfmd_version()`. Each call runs the command-line tool as a subprocess (the way `pypandoc` runs
  Pandoc), so a document builds as `pdfmd` builds it and the caller's process is untouched; the source is neither stamped nor
  backed up unless asked. Text outputs come back as `str`, binary ones as `bytes`; any format Pandoc reads can be the input.

---

## v3.24.10 — 2026-10-08

Pre-edit state: commit `7718a2b` (v3.24.9). A package's own table recipe: the chemicals table is native.

### Added

- **A profile can build tables and read the document's files.** The helpers of an office profile now include
  `read_file(name)` (a file of the document's folders: its own, the metadata and preamble folders, as `\input` finds
  them), `number_caption(table, "table")` (the "Table 3." number LaTeX gave), `warn(text)`, and `inlines`/`blocks` now
  carry the filter's own math, `\ce`/`\si` and profile commands through (a LaTeX string of a package's data becomes
  finished Word inlines). nulabreport's profile uses them for `\chemicals{...}{caption}`: its library
  (`\DeclareChemical` of `chemicals.tex`), the house column widths, per-call `key[form]` lines and the caption below.
- A `PdfmdGrid` (ruled all round, tight padding) and a `PdfmdSmall` (80% of the text, a `\footnotesize` table) style in
  every reference document, beside the `PdfmdBooktabs` of 3.24.8. A table cell's custom style must sit on a `Para`
  (Pandoc ignores it on a `Plain`).

### Fixed

- A signed number in math (`$-4$`, `$\sim 825$`, `$>500$`) is text with a real minus sign, not a small equation of its own
  (in a table cell it was a larger, different-looking figure).
- `\allowbreak` in text is not a picture; a `%` at the end of a line in an `\input` file joins it to the next, as TeX does
  (`\chemicals{...}%` over `{caption}`).

---

## v3.24.9 — 2026-10-08

Pre-edit state: commit `c84ece9` (v3.24.8). A package says in its own file what pdfmd cannot know.

### Added

- **`<package>-pdfmd.yaml`**, beside a LaTeX package's `.sty` (or in a `pdfmd/` folder there; found from the preamble's
  `\usepackage` like the Word files). `latex-keys:` maps front-matter keys to the macros they fill
  (`\renewcommand{\Macro}{value}` after the preamble) and an optional `office:` section holds the package's Word/ODT defaults,
  under `<package>-office.yaml` (which may now also sit in `pdfmd/`, as `-office.lua` and `-reference.docx` may). nulabreport
  ships its own (`experiment`, `group`, `course`, `section`, `instructor`, `performed`, `unknown(s)`).
- The package lookup is one `kpsewhich` call for all `\usepackage`d names instead of one each.

### Changed

- `DOCUMENT_LATEX_KEYS` (those nulabreport keys, hard-coded in pdfmd) stays as the fallback for a nulabreport without the
  file, now with a note: the keys of a package's own file are added to it and win. Documents of a package without
  the file build exactly as before; the LaTeX of a nulabreport report is byte-identical with and without it.

---

## v3.24.8 — 2026-10-08

Pre-edit state: commit `5559552` (v3.24.7). The second reading of the Word builds.

### Fixed

- **A block picture sat at the left of its box.** A block fragment (an `\includegraphics` with `width=0.7\linewidth`, a
  spectrum) was typeset in a text-wide box and cropped to that box, so a narrower picture carried empty space on its
  right and, centred as a whole, looked shifted left. Block fragments are now cropped to what they draw on both sides
  (vertically still to the box); the pictures of earlier builds are drawn again (the cache key carries a version).
- **Tables were pictures.** A house filter that rewrites Pandoc tables into raw LaTeX leaves nothing for Word, so the
  table was drawn as a picture; with the filter guarded to LaTeX output (nulabreport v1.27.2) they are Pandoc tables and
  come out native and editable. A table that gives no column widths (a pipe table of short lines) is sized to its text,
  as a LaTeX `tabular` would be, instead of equal columns that broke words in two ("Paracetam-ol"); a `PdfmdBooktabs`
  table style (rules above, below and under the header row) is part of every reference document.
- **A `replace` key with markup in it** (`<w:color .../>`) is now XML for XML, not escaped text, so a header or footer
  colour can be changed (the page number on a black box turned black on black).

---

## v3.24.7 — 2026-10-08

Pre-edit state: commit `095f2e5` (v3.24.6). What reading the six Word builds page by page showed.

### Fixed

- **Pictures were indented like body text** (a picture's paragraph inherited the first-line indent): the `Figure` and
  `Captioned Figure` styles are centred with no indent in every reference document, and pdfmd's own picture
  paragraphs use a centred, unindented `PdfmdCentered` style.
- **`105\,^\circ\text{C}` showed an empty box** before the degree sign (a superscript with nothing before it, here the thin
  space, is a placeholder in Word and LibreOffice): such a degree sign is text.
- **A long display ran off the page.** LaTeX (or the house style) sets it on several lines; Word's equation cannot wrap. A
  display wider than the line (estimated in characters, fractions counted as their wider part) is cut at its top-level
  equals signs into the rows of an aligned block, each row after the first starting with "="; an equation of its own
  `\\`/`&` or `\begin` is left as the author wrote it.
- **`\input{tex/table-x}` was always a picture.** What the file holds now decides (a booktabs `tabular` is a native
  table; whole-line comments are dropped with their line break, as a blank line would end a paragraph inside a tikz
  option list); a file that cannot be read is drawn as before.

### Added

- `office: {media: {word/media/image1.png: logo.png}}` replaces a picture of the template (paths relative to the
  package folder for a package's yaml). nulabreport uses it with `replace` to give every course but genchem the
  black logo and page-number box its PDF has.

---

## v3.24.6 — 2026-10-08

Pre-edit state: commit `574f398` (v3.24.5).

### Changed

- The "Compiled with ..." line pdfmd writes into BUILD NOTES says the format when it is not a PDF:
  "Compiled to docx with nulabreport v1.27.0, pdfmd v3.24.6 -- TIMESTAMP" (a PDF's, and `--to latex`'s, stay as they were;
  `stamp: {include-output: true}` still names the file).

---

## v3.24.5 — 2026-10-08

Pre-edit state: commit `e957078` (v3.24.4).

### Fixed

- The PDF build for a document's reference numbers and the `--to latex` run for its fragments' preamble are pdfmd runs of
  their own: each added a "Compiled with pdfmd" line to the source's BUILD NOTES and might take a snapshot. They run with
  `--no-stamp --no-backup` now; only the build the user asked for writes its note.

---

## v3.24.4 — 2026-10-08

Pre-edit state: commit `8a83d39` (v3.24.3). The other outputs, and what building every CHEM212L/CHEM220L report
to `.docx` showed.

### Added

- **The soffice fallback** (Pandoc -> .odt -> LibreOffice -> PDF) goes through the same reference document and filter:
  papersize, geometry and fonts are kept (it printed Letter in LibreOffice's defaults), equations are numbered, what is
  LaTeX is made native or drawn. No PDF build for numbers there (LaTeX is what failed).
- **Typst and WeasyPrint runs** go through the filter when a LaTeX engine failed before them, or the document says
  `office: {latex: auto}`; the first run lists the fragments as Typst/HTML source instead of building a PDF. HTML,
  Typst and EPUB-like outputs use it only on request.

### Fixed

- Pandoc's LaTeX reader forgets an unknown command and keeps its arguments as text (`\chemicals{a}{b}` became the
  text "b"): a raw block is read only when every command in it is one the reader knows (`\ce`, `\si`, `\cref`... count
  as known: they are translated afterwards), otherwise it is drawn. The two runs of the filter decide this alike.
- A lone `height=` or `width=` on a picture the reader put in a table cell was ignored by the docx writer (three
  TLC plates came out a page wide each); both are now given, the missing one from the picture's proportions.
- A macro that makes a float (a spectrum comparison) failed inside the fragment box ("Not in outer par mode"):
  `figure` and `table` do not float there. A fragment error shows the real LaTeX message (`-file-line-error` form).
- A picture's border: fragments are drawn with 10 bp of room and trimmed back (see 3.24.3); a house style's
  furniture is switched off in them.

### Verified

- All six lab reports of CHEM212L (LR1-2 draft, LR3, LR4-5) and CHEM220L (LR1, LR2, LR2 plain) built to `.docx`
  with the department's template: 3 to 41 LaTeX pictures each, no fragment lost, text 91-98 % the PDF's, page counts
  within a few pages (the PDFs' full-page spectra and wide tables set differently in Word); read page by page
  through LibreOffice.

---

## v3.24.3 — 2026-10-08

Pre-edit state: commit `3fae4a4` (v3.24.2). A house style's own Word template and macros, and what building
real lab reports showed.

### Added

- **Style aliases** (`office: {styles: {Heading1: LRH1, BodyText: LRNormal, Table: TableGrid}}`): Pandoc's styles take the look of
  the template's own differently named ones (a source based on its target only adds its settings, any other
  replaces the look; a Pandoc style the template lacks is made, under the name Pandoc looks it up by).
  **`office: {replace: {FROM: TO}}`** rewrites text in the template's headers and footers;
  **`office: {title-page: true}`** adds `titlePg` (the first page has no header or footer).
- **Packages ship Word support**: beside a local LaTeX package's `.sty` (or in an `office/` folder there):
  `<package>-reference.docx|dotx`, `<package>-office.lua`, `<package>-office.yaml` (defaults for `office:`, with
  `by-option:` for what `\usepackage[opt]{package}` adds); found through `kpsewhich` from the preamble's
  `\usepackage` lines. The document's own `office:` still wins key by key.
- The profile can read the preamble (`helpers.preamble()`), the metadata (`helpers.meta()`), draw a fragment
  (`helpers.fragment`) and rewrite the whole document (`pandoc = function(doc, helpers)`); `PdfmdCentered` style.
- **Fragments**: drawn with a 10 bp border that is trimmed again (an inline one to exactly its box, a block to its box
  and all it draws, through Ghostscript's bbox and pypdf: a picture can reach past its own bounding box); a house style's
  header, footer and furniture are switched off so they cannot land in the crop (the university logo came out
  with a ghost of the running header).
- `\[ ... \]` displays (a house filter wraps `$$...$$` so) are converted like any math; math and macros inside what
  Pandoc's LaTeX reader returned are translated too (they were seen by no filter again).

### Verified

- A real lab report (title page, headers, equations, a chemicals table, figures) built to `.docx` with the
  department's template: cover, logo header, page-number footer with the course's wording, Roman headings,
  numbered equations and cross-references all as in the PDF; checked page by page through LibreOffice.

---

## v3.24.2 — 2026-10-08

Pre-edit state: commit `11431ae` (v3.24.1). What cannot be native is drawn by LaTeX and embedded; a house
style's macros can be declared.

### Added

- **Fragments drawn by LaTeX** (`pdfmd_office/fragments.py`, `docx_post.py`): the filter runs twice. The first run
  lists what it could not make native (unknown raw blocks and inline commands, math Pandoc's converter rejects,
  display environments it cannot convert, the body of a `figure`/`table` it cannot read) and pdfmd compiles
  them in the document's own preamble (taken from a `--to latex` run of the same document, so fonts,
  packages, house macros and the script fallback are the PDF's), one fragment to a `preview` page, all at once
  and, on an error, halved until the fragment that breaks is alone (one engine, no retries; `\newlabel`s of the
  real build are loaded, `\setcounter` restores a captioned float's number). Each page becomes an SVG
  (pdftocairo, glyphs as outlines) and a 300 dpi transparent PNG, with the box's depth. Cached under
  `~/.cache/pdfmd/office/<hash of preamble, engine and labels>/` by content.
- The second run puts them in: a `.docx` gets the PNG as the picture, then **docx_post** adds the SVG as
  Word's `svgBlip` extension beside it (Word 2016+ draws the vector, LibreOffice and older readers the PNG),
  lowers an inline picture by its depth (`w:position`) so it sits on the baseline, scales a picture wider than
  the text to the text width, and clears the marker. `.odt` gets the SVG directly.
- **PDF and EPS pictures** (`\includegraphics{x.pdf}`, `![](x.pdf)`) are converted to SVG and PNG
  (pdftocairo; EPS through epstopdf or Ghostscript), again when the file is newer than its cache entry.
- A `figure`/`table` whose body Pandoc's LaTeX reader would silently drop (tikz, pgfplots, `\input`, any environment
  it does not know) keeps its **caption as text** with its number ("Figure 3. ...") and its body drawn as a
  picture; the reader is only trusted with environments it knows.
- **Profiles**: `office.lua`, `<name>-office.lua`, `nulabreport-office.lua` (beside the document, in `metadata/`, beside
  its metadata files or in `~/.config/pdfmd/`) or `office: {profile: FILE}` tell pdfmd what a house style's own
  macros mean in a Word file: `ignore = {...}`, `commands = {name = function(args, raw, helpers, as_block)}`
  (text, blocks such as a native table, or `{}`), `pandoc = function(doc, helpers)` for the whole document.
  `--no-auto officeprofile`.
- Captions, figures and tables get a Word look of the LaTeX one (centred, italic, 0.9x) in pdfmd's styles.
- `tests/test_office_latex.py`: profile, vector picture with baseline, caching, a failing fragment, PDF picture,
  captioned tikz figure.

### Fixed

- Pandoc's LaTeX reader returns a `figure` with an empty body (no raw block left to notice) when it meets tikz;
  such figures were rendered as a bare caption.
- Reference-number lookups, fragments and the preamble run use `pdfmd` as a subprocess with the same
  `-V`, metadata files and `--no-auto` kinds (`office_pdfmd_command`).

---

## v3.24.1 — 2026-10-08

Pre-edit state: commit `0f9d82e` (v3.24.0). LaTeX the document uses becomes native in Word/ODT output
(tiers 1-3 and numbers; images for what is left follow).

Found by building a lab report to `.docx`: every `\begin{equation}` with `\ce` was dropped, `\ce` and `\si`
stayed literal, references and figures vanished. nulabreport's own filter (unguarded `FixDisplaySpacing`)
also turns display math into LaTeX raw blocks a Word writer drops.

### Added

- **`pdfmd_office/office.lua`**, a Pandoc Lua filter run last for `.docx`/`.odt` (`office: {latex: auto|off}`,
  `--no-auto officelatex`): math Pandoc can convert is kept (checked through the MathML writer, silently);
  **mhchem** `\ce{...}` (species, coefficients, charges, subscripts, states, bonds, hydrates, arrows with
  labels) and **siunitx** `\si \SI \qty \unit \num` (prefixes, powers, `\per`) are translated, in math
  (`\text{...}` runs, so Word and LibreOffice both set them upright) and in text (real subscripts and
  superscripts); `\xoverline`; **display environments** (`equation`, `align`, `gather`, `reaction`...,
  also behind a house filter's `\par\nointerlineskip` wrapper) become a Word equation in a borderless
  three-cell table with the number at the right; raw `figure`/`tabular`/lists/`\emph`... go through Pandoc's
  LaTeX reader; `\newpage` is a page break; `\vspace` and friends are dropped.
- **Numbers from LaTeX**: `\ref \eqref \cref \Cref \autoref \pageref` and the "Figure N. " / "Table N. "
  before captions use `\newlabel`s read from the `.aux` of one PDF build made in the cache (reused while the
  sources are older; `office: {labels: off}` counts instead), cleveref names and the "Equation (1)" form,
  list and pair wording ("Equations (1) and (2)"), the caption separator from `labelsep=`, `\crefname`s and
  `capitalize` read from the preamble and the local packages it loads. A reference with no label is `??`.
  A reference to a single label is a link to it.
- What cannot be made native is counted and named once per run (`-v` lists up to 20): `WARN ... LaTeX the Word
  output could not express: 1 block, 2 inline`.
- `pdfmd_office/labels.py`, `tests/test_office_latex.py`; the reference document gets a `PdfmdEquation` table style.

### Fixed

- nulabreport.lua's `FixDisplaySpacing` was not guarded by the output format (fixed in nulabreport; pdfmd
  runs its filter after the others and reads the wrapped block too, so older copies work).

---

## v3.24.0 — 2026-10-08

Pre-edit state: commit `8beeb9e` (v3.23.23). Word and OpenDocument output follows the document: the
first part of the office-export line (the rest, LaTeX the document cannot express natively, comes in
the 3.24.x patches).

Found by building a lab report (`papersize: a4`, `geometry:`, STIX Two Text) to `.docx`: Pandoc
writes a Letter page in its default fonts and ignores every one of those keys.

### Added

- **`pdfmd_office/`**: `papersize`, `pagesize`, `classoption` (a4paper, landscape...), `geometry:` (every
  spelling: list, comma string, mapping, `margin=`, `top=`/`hmargin=`/`paperwidth=`...), `margin:`,
  `fontsize`, `mainfont`, `sansfont`, `monofont`, `CJKmainfont`, `linestretch`, `lang` and `indent` are
  written into a copy of the reference document before Pandoc runs (page size, margins and orientation
  into the last section, fonts and sizes into `styles.xml`, theme fonts replaced, every other size
  scaled with `fontsize`, `lang` into the defaults, first-line indent into Body Text). `.docx` by
  text edits that keep a Word template's namespaces intact and elements in schema order; `.odt`
  likewise on `styles.xml`.
- **Fonts Word has**: a `.docx` carries font names, so STIX Two Text and its kind map to Times New
  Roman, Helvetica Neue and kind to Arial, JetBrains Mono and kind to Consolas, with an `AUTO OFFICE`
  note; `office: {fonts: exact}` keeps the names. An unknown font is kept, with a note.
- **pdfmd's own Word look** when nothing else says otherwise: black bold headings sized like a LaTeX
  article (1.2x, 1x), a centred title block, booktabs-style table rules, Times New Roman and Consolas
  (`office: {style: plain}` or `--no-auto officestyle` leaves Pandoc's styles).
- **Reference documents are found**, only for `.docx`/`.odt`/`.pptx` output: `office: {reference-doc: F}`,
  `<name>-reference.<ext>`, `reference.<ext>` (`.dotx`/`.ott`/`.potx` too) beside the document, in its
  `metadata/` folder or beside its metadata files, then `~/.config/pdfmd/`. A template keeps its own page
  and fonts; the `office:` block changes just the keys it names. A document's own output is never taken
  as its template. Pandoc's `--reference-doc` is left alone. `--no-auto officeref`.
- **`pdfmd --init-reference [docx|odt|pptx]`** writes `reference.<ext>` (Pandoc's styles with pdfmd's
  look) into the folder, never over an existing one.
- Single files, `-r` reports and `-b` batches all go through it. README section "Word and OpenDocument
  output"; `tests/test_office.py` (units, XML well-formedness and order, discovery, and a LibreOffice
  render that checks the page size).

### Verified

- A 27-document matrix through Pandoc and LibreOffice (A4, Letter, Legal, A5, B5, landscape, every
  geometry/margin spelling, `-V` variables, font sizes, fonts, ODT): page size and margins come out as
  asked, fonts as mapped.

---

## v3.23.23 — 2026-10-08

Pre-edit state: commit `80e8a0a` (v3.23.22). Documentation only.

### Added

- `docs/recipes.md`: "how do I..." answers (scripts and fonts, finding documents by a name in another
  script, scanned PDFs to Markdown, a PDF that carries its source, a folder's house style, books and
  reports, other formats, fast rebuilds, debugging, completion), linked from the README's Reference.

---

## v3.23.22 — 2026-10-08

Pre-edit state: commit `d0afddc` (v3.23.21). Found while making the README's script screenshot: with
Apple Color Emoji a skin tone, a joined emoji and a flag came out as a plain emoji or as boxes, though
3.23.15 said they resolve.

### Fixed

- **Apple Color Emoji sequences**: the font keeps its sequences in AAT tables, but names each glyph
  (`u1F469_u1F52C.3`, `u1F1F0_u1F1FF`, `u0031_u20E3`, `u1F9CE.0.W`); pdfmd reads the `post` table and
  looks a sequence up by that name (the code points without joiners and selectors, a skin tone as
  `.N`, two people `.NN`, a gender sign as `.W`/`.M`). Skin tones, flags, keycaps, tag flags and most
  joined emoji now come out right; a joined emoji the font has no named glyph for (a family of four)
  is reported as undrawn instead of drawn as its first emoji (the Noto path is unchanged).
- `--check-fonts` knew a colour emoji font only if it was Noto; it now counts Apple's, as the build does.

### Added

- `examples/scripts.md` and `docs/scripts.png`, shown in the README's "Other scripts".
- `tests/test_apple_emoji.py`.

---

## v3.23.21 — 2026-10-08

Pre-edit state: commit `202f29b` (v3.23.20).

### Added

- **`pdfmd --completion bash|zsh|fish`** prints a tab-completion script generated from the argument
  parser (flags, their one-line help, the choices of `--stop-at` and the like, the kinds of
  `--install`; fish also completes `fonts:NAME` and `ocr:LANG`; flags that take a file complete
  files). Also registered for `pdfmd-cli`.
- `tests/test_completion.py` (the scripts are syntax-checked in the shells that are there).

---

## v3.23.20 — 2026-10-08

Pre-edit state: commit `25dcb7b` (v3.23.19).

### Added

- **`pdfmd --doctor`**: one report on what pdfmd uses: Pandoc and the PDF engines (and which runs
  first), the Python packages, the default fonts, the fonts pdfmd installed, a colour emoji font, a CJK
  font, the name-lookup packs, batchocr, Tesseract and Poppler, the OCR languages pdfmd holds, the
  config file and the cache; it ends with the command that fixes each missing piece (the same fix is
  listed once). Exit status 0 while a PDF can still be made (the built-in renderer counts).
  `--check-dependencies` and `--check-fonts` are unchanged.
- `tests/test_doctor.py`.

---

## v3.23.19 — 2026-10-08

Pre-edit state: commit `3d169e9` (v3.23.18). OCR languages without a package manager.

### Added

- **`pdfmd --install ocr[:LANG,...]`** lists / fetches Tesseract language files (the `tessdata_fast`
  models, Apache-2.0, 125 languages; `pdfmd_unicode/tessdata.py`, catalog generated by
  `scripts/gen_tessdata_catalog.py` at a pinned commit, every file checked against its git blob
  SHA-1) into `~/.local/share/pdfmd/tessdata` (`%LOCALAPPDATA%\pdfmd\tessdata`), with English and the
  orientation model added so the folder stands on its own. Codes, ISO 639-1 codes and names
  (`ru`, `kazakh`, `zh`, `chi_sim`). `--uninstall ocr:LANG` removes.
- **PDF reading uses it**: `pdfmd scan.pdf --lang rus` runs batchocr with `TESSDATA_PREFIX` at that
  folder when it has every language asked for (English when no `--lang`) and the user has set no
  `TESSDATA_PREFIX`; otherwise Tesseract's own languages are used as before.
- `tests/test_tessdata.py`.

---

## v3.23.18 — 2026-10-08

Pre-edit state: commit `33aae99` (v3.23.17). `--install batchocr` reaches the system programs on
every platform; the README catches up with the 3.23 line.

### Added

- **`pdfmd --install batchocr` offers Tesseract and Poppler** through the system's package manager
  (Homebrew, apt, dnf, pacman, zypper, apk on macOS/Linux; scoop, Chocolatey, winget on Windows): it
  shows the exact command (with `sudo` where the manager needs it and the user is not root) and runs
  it only after a yes on an interactive terminal (`PDFMD_NO_PROMPT=1` or a pipe: printed only). They
  are not bundled: separate programs with their own licences and per-platform builds. OCR languages
  are named per manager, never installed. `--check-dependencies` reports `pdftoppm` too, and the
  hints in it and in the "batchocr not found" message use the manager found instead of a fixed
  macOS/apt/choco line.
- `tests/test_install_ocr.py`.

### Documentation

- README: the Why list now names scripts and emoji, name lookup in any script and PDF reading; the
  Install section has Fedora and Arch lines and says `--install full` needs no root on Linux; the
  PDF-to-Markdown section explains the Tesseract/Poppler step and OCR languages.

---

## v3.23.17 — 2026-10-08

Pre-edit state: commit `a126fa7` (v3.23.16).

### Fixed

- Without fontconfig and without TeX (a typical Windows machine) pdfmd could not tell that a font is
  absent from the system, so a font that exists only in its own fonts folder was named by family and
  failed to load; its own scan of the system font folders answers now (after `fc-list` and
  `luaotfload-tool`).
- The test that compared the generated Unicode script table with fontTools' own copy failed whenever
  fontTools shipped another Unicode version; the table is checked for being well-formed instead
  (`scripts/gen_unicode_scripts.py --check` stays as a development check).

---

## v3.23.16 — 2026-10-08

Pre-edit state: commit `f1110f3` (v3.23.15). Tests only: what the first CI run on Windows and on a
machine without Pandoc showed (nothing of pdfmd itself changed).

### Fixed

- Tests that assumed POSIX paths, `\n` line ends or the XDG folders (Windows uses `%APPDATA%`/
  `%LOCALAPPDATA%`), and two `--assemble-only` tests that need Pandoc now skip without it.

---

## v3.23.15 — 2026-10-08

Pre-edit state: commit `5b25832` (v3.23.14). Emoji pictures: Apple's font, and inside code.

### Added

- **Apple Color Emoji as a picture source** for LaTeX (its `sbix` PNG strikes, largest first, `dupe`
  glyphs followed), used when no Noto Color Emoji is installed. Single emoji, skin tones and most ZWJ
  sequences resolve; flags and keycaps are not found in Apple's font by this reader, so they are
  reported as undrawn (install `pdfmd --install emoji` for those).
- **Emoji in inline code and code blocks** become pictures too. They are referenced by number
  (`\pdfmdemojin{N}`, the path defined in the preamble), because a path cannot be read inside a
  `Verbatim` block. A code block is only rewritten as `Verbatim` when something in it needs work (a digit
  that could begin a keycap does not count).

---

## v3.23.14 — 2026-10-08

Pre-edit state: commit `9e79464` (v3.23.13). The fallback on the natbib/biblatex route.

### Added

- `citation-engine: natbib | biblatex` builds now get the script fallback, the main-font choice and
  managed fonts like every other LaTeX build (the body text only: the bibliography itself is typeset by
  bibtex/biber with the main font). The soffice last-resort fallback is left to LibreOffice's own font
  replacement.

---

## v3.23.13 — 2026-10-08

Pre-edit state: commit `44091c8` (v3.23.12). Code on Typst and WeasyPrint.

### Added

- **Fallback fonts for code on Typst and WeasyPrint**: the characters the code's font lacks (DejaVu
  Sans Mono, Typst's default, or the document's `monofont`; Menlo and friends on WeasyPrint) are set in
  the fallback fonts through Typst's `codefont` list (`-V codefont=...`, which Typst reads glyph by
  glyph) and a CSS `font-family` rule for `code`/`pre`. The main-font choice by script and
  `fallback: document` already applied to every engine (pdfmd's default font, with the `AUTO MAINFONT` note).

---

## v3.23.12 — 2026-10-08

Pre-edit state: commit `4a835b4` (v3.23.11). The cache can live beside the document, and a moved
document finds its cache.

### Added

- **`cache: {location: global | document}`** (`pdfmd-options`, `--cache-location`, the config
  file): `global` (default, unchanged) is `~/.cache/pdfmd`; `document` is `.cache/pdfmd` beside the
  document (self-contained, with `CACHEDIR.TAG` and a `.gitignore`), holding its LaTeX cross-reference
  folder, the plot cache and the emoji pictures. `--clear-cache` clears both places.
- **A moved document finds its cache.** Each cache folder records its document
  (`.pdfmd-source.json`: path, stem, folder name, SHA-256 of the source). A document with no cache
  under its path adopts that of a document whose recorded original no longer exists: same stem and
  same content, or, after an edit, same stem and same folder name when only one such cache is left
  (an `AUTO CACHE` note says so). A copy never takes its original's cache.
- **Plot-cache entries survive a move**: they record the folders they were made in and, when the
  report has moved, their input files are looked for under the new ones (and the entry is re-pointed);
  a changed data file still drops the entry.
- `tests/test_cache_location.py`.

---

## v3.23.11 — 2026-10-08

Pre-edit state: commit `b4bbc31` (v3.23.10). More fonts in the catalog.

### Added

- Catalog (regenerated; every file still pinned): `nastaliq` (Noto Nastaliq Urdu, chosen for text
  in `lang: ur` and the like, the other Arabic-script languages stay in Naskh), `oriya`,
  `mongolian`, `coptic`, `gothic`, `runic`, `canadian`, `tifinagh`, `nko`, `indic-sans` (the
  sans-serif faces of the nine Indic scripts), and `cjk-sans-sc/tc/jp/kr` (Noto Sans CJK subsets,
  regular and bold) with a group `cjk-sans`. `fonts:urdu` installs Naskh and Nastaliq. The group sizes
  in `pdfmd --install fonts` are computed.

---

## v3.23.10 — 2026-10-08

Pre-edit state: commit `2dbf10b` (v3.23.9).

### Added

- **`pdfmd --check-fonts DOC`**: the fonts report without a build: the mode, the main font and why
  it was changed, which scripts (and which code) get which fallback font, emoji, the characters no
  installed font draws and the `--install fonts:...` that would fix it. Exit status 1 when
  something cannot be drawn.

---

## v3.23.9 — 2026-10-08

Pre-edit state: commit `84deaa5` (v3.23.8). Characters in code.

### Added

- **Fallback in code (LaTeX)**: the document's inline code and code blocks are checked against the
  monofont (its own, or JetBrains Mono), and the characters it lacks are set in a fallback font
  (right-to-left runs get their direction), drawn as black boxes (`missing: box`), or counted by
  `missing: error`. A code block that needs one is written as a `fancyvrb` `Verbatim` with
  `commandchars`, so it loses syntax highlighting (blocks with nothing missing are untouched).
  Typst and HTML code are left to their own fallback; math is left to unicode-math.

---

## v3.23.8 — 2026-10-08

Pre-edit state: commit `5ba014b` (v3.23.7).

### Changed

- **`fallback: word` is the default** (no word set half in one font and half in another).
  `fallback: true`/`on`/`yes` mean the default; `false`/`no`/`none` mean `off`.
- **pdfmd's own default main font is chosen by script again**, with an `AUTO MAINFONT` note (shown
  in full with `-v`, as the `AUTO:` summary line otherwise): when no font is named and STIX Two Text
  lacks letters of the script the document is mostly in (Kazakh Cyrillic), a serif that has them
  all is used. A font the document or the command line names is never replaced, except by
  `fallback: document`; `off`, `box` and `error` never choose.

---

## v3.23.7 — 2026-10-08

Pre-edit state: commit `a61741e` (v3.23.6). The fallback is a choice, and by default it
touches only the missing characters.

### Added

- **`fallback: char | word | document | off | box | error`** (`pdfmd-options`, `--fallback`, the
  config file's `options:`; YAML's bare `off`/`no` read as false are understood): `char` is the
  default and sets just the missing characters in another font; `word` sets a whole word in one
  fallback font that draws all of it (a word with nothing missing stays in the main font);
  `document` makes the installed font that draws most of the document the main font, replacing even
  one the document names (`AUTO MAINFONT` says so); `off` is Pandoc's own behaviour (no fonts, no
  emoji pictures, no main-font choice); `box` draws every missing character as a black box (LaTeX
  `\rule`, Typst `#box`, an HTML span); `error` stops the build and lists them.
- **`missing: warn | box | error`** (`--missing`): the same choice for characters no installed font
  draws after the fallback. `box` and `error` as a fallback mode imply it.

### Changed

- **The main font is no longer chosen by script.** 3.23.0 replaced the automatic main font (STIX
  Two Text) by a serif that has all the letters of the document's own script, whatever the mode; a
  document that names its font was never touched, but the default one changed behind the user's back.
  Now only `fallback: document` changes the main font; `char` (default) leaves it and sets the
  missing letters (the Kazakh ә ғ қ ң ө ұ ү һ і in STIX Two Text) in another font.
  `choose_main_font` stays in the package for callers that want it.

---

## v3.23.6 — 2026-10-08

Pre-edit state: commit `0573687` (v3.23.5). A global config file, and the state pdfmd keeps
about the user moved out of the cache.

### Added

- **`~/.config/pdfmd/config.yaml`** (`$XDG_CONFIG_HOME`, `%APPDATA%\pdfmd`; `PDFMD_CONFIG` names
  another file or, empty, none). `options:` = defaults for every document's `pdfmd-options`,
  the lowest source (document, then its metadata files, then the config; the command line
  above all) for the options read through the shared cascade (`default-output`, `parts`,
  `strip-comments`, `embed`, `cache`, `pdf-engine`/`engine`, `citation-engine`, ...);
  `translit:` the lookup's romanization packs (below `--translit` and `PDFMD_TRANSLIT`).
  `--init-config` writes a commented template, `--show-config` reports. A broken file or an
  unknown setting is a WARN, never a failure.

### Changed

- **Persistent decisions left the cache.** The trusted embedded-filter hashes (a security
  allow-list) and the dismissed native-renderer offer were in `~/.cache/pdfmd`, which
  `--clear-cache` (or any cache cleaner) empties; they are now
  `~/.config/pdfmd/trusted-filters.txt` and `native-prompt-dismissed`, moved from the old place
  the first time they are read.
- The test suite points the config and state folders at a temporary one.

---

## v3.23.5 — 2026-10-08

Pre-edit state: commit `2468b07` (v3.23.4).

### Fixed

- Finding a family's regular face without fontconfig (the scan of the font folders used on
  machines without `fc-list`): "Regular" now ranks before "Medium" (a family whose Medium file
  sorted first used to stand for the whole family), and a static font before a variable one.
  Checked on Python 3.9 as well as 3.14.

---

## v3.23.4 — 2026-10-08

Pre-edit state: commit `5a38677` (v3.23.3). Fonts in more places.

### Added

- **A font the document itself names** (`mainfont:`, `sansfont:`, `monofont:`) that exists only
  in pdfmd's fonts folder is loaded by file under LaTeX (`document_font_args`), unless the
  document gives its own `...options:`.
- **Report mode** (`-r`) gets the script fallback, the managed fonts and the main font by script,
  in both its `--to latex` and PDF-engine branches.

---

## v3.23.3 — 2026-10-08

Pre-edit state: commit `bc30b40` (v3.23.2). Finding documents by names in other scripts.

### Added

- **Romanization packs** (`pdfmd_unicode/translit.py`): `--translit PACKS` /
  `PDFMD_TRANSLIT` turns on, per script, the spelling of a name in Latin letters that the
  lookup compares (`pdfmd tyche` finds `Τύχη.md`, `pdfmd unmyeong` `운명.md`,
  `pdfmd mingyun` `命運.md`; headings in `doc#section` too). Own tables, no dependency:
  `greek` (scholarly Latinization: η = e, φ = ph, γκ = nk, ου = ou), `armenian`,
  `georgian`, `hebrew` and `arabic` (consonant skeletons, Persian and Urdu letters),
  `hangul` (Revised Romanization with the usual liaison), `kana` (Hepburn: yoon, small
  vowels, doubled consonants). `han` is pinyin without tones through `pypinyin` (MIT) or
  `anyascii` (ISC), `other` every remaining script through `anyascii`; both are optional
  (`pdfmd --install translit`, `pdfmd-cli[translit]`). `all`, `none`, and `--translit list`.
  Off by default except Cyrillic (Russian, Ukrainian, Belarusian, Kazakh), which stays
  built into `pdfmd.py` exactly as it was; `--translit none` turns that off as well,
  including the exact-name Cyrillic/Latin spellings. Homophones (命運, 銘運) stay ambiguous:
  the existing "fits two documents" error lists them.
- A loose lookup key treats `ph` as `f` (Greek φ is written either way).
- `tests/test_translit.py`.

---

## v3.23.2 — 2026-10-08

Pre-edit state: commit `1505ed8` (v3.23.1). Emoji in lualatex and xelatex.

### Added

- **Emoji as pictures under LaTeX**: the PNG of each emoji is read straight out of a
  colour bitmap font (Noto Color Emoji: the CBDT/CBLC tables, no dependency; the glyph of
  a sequence, a flag, a skin tone, a ZWJ family, a keycap, a tag flag, through the
  font's own GSUB ligatures), kept in `~/.cache/pdfmd/emoji/`, and set by the Lua filter
  as `\pdfmdemoji{...}` (`\includegraphics`, 1.1 em high, raised 0.2 em). Needs the font:
  `pdfmd --install emoji`, or a system Noto Color Emoji; without it the WARN says so.
  A `--to latex` file points at the cached pictures.
- Tests with a synthetic CBDT font written by the test itself.

### Changed

- Cyrillic letters the main font lacks are tried in Noto Serif before PT Serif.
- The ASCII range counts too when a main font lacks it (an explicit `-f` Hebrew-only
  font no longer prints the Latin text as missing glyphs).

---

## v3.23.1 — 2026-10-08

Pre-edit state: commit `28646b0` (v3.23.0). `pdfmd --install fonts`, and the fonts it
fetches used by every engine; emoji and the other scripts on Typst and WeasyPrint.

### Added

- **`pdfmd --install fonts`** lists the fonts pdfmd can fetch (size, state, what for);
  **`--install fonts:NAME[,NAME...]`** fetches them into pdfmd's own folder
  (`~/.local/share/pdfmd/fonts`, `$XDG_DATA_HOME`, `%LOCALAPPDATA%\pdfmd\fonts`), one
  folder per package with its licence beside it, no admin rights, nothing system-wide;
  **`--uninstall fonts:NAME`** removes. Groups `core`, `scripts`, `cjk`, `all`, and
  aliases (`ja`, `zh-tw`, `kazakh`, `persian`...). The catalog
  (`pdfmd_unicode/_catalog.py`, generated by `scripts/gen_font_catalog.py`): STIX Two
  Text and Math, JetBrains Mono, Noto Serif (Latin, Cyrillic with Kazakh, Greek), Amiri
  and Noto Naskh Arabic, Hebrew, Armenian, Georgian, Devanagari, Bengali, Tamil, Telugu,
  Kannada, Malayalam, Gujarati, Gurmukhi, Sinhala, Thai, Lao, Khmer, Myanmar, Tibetan,
  Ethiopic, Syriac, Thaana, Cherokee, symbols, Noto Serif CJK for SC/TC/JP/KR (subset,
  one weight), DejaVu, and Noto Color Emoji. Every file is pinned: by the commit it is
  fetched from and its git blob SHA-1, or by the SHA-256 of the archive it comes out of,
  and refused if it differs. All SIL OFL except DejaVu's own free licence.
- **The fonts are used**: LaTeX loads a font that is only in pdfmd's folder by file name
  and `Path` (`mainfont`/`monofont` options included, so STIX Two Text and JetBrains Mono
  from `--install fonts` become the defaults wherever the machine has none), Typst gets
  `--font-path`, WeasyPrint `@font-face` rules; `font_missing()` knows the folder.
- **The same script runs on Typst and WeasyPrint**: the Lua filter emits `#text(font: ..,
  lang: ..)[..]` for Typst (whose own fallback does not find CJK or Hangul even when the
  fonts are installed) and a `font-family` span for HTML, with the language tag for CJK.
- **Emoji**: told apart from the script fonts (pictographs, regional-indicator flags, and
  symbols such as the heart only with U+FE0F). Typst draws them; WeasyPrint is left to the
  system's emoji font (its handling of Noto Color Emoji's bitmaps is broken: tiny and
  misplaced); LaTeX cannot yet and says so. `--install emoji` now installs the font into
  pdfmd's own folder, where the built-in renderer finds it first (no pip, no `inkmd`
  package needed) and every other engine too.
- When no installed font draws a character the WARN names the package to install
  (`pdfmd --install fonts:cjk-sc`).

### Changed

- A missing-glyph warning that is only about characters no font has (already warned about)
  no longer triggers the retry with DejaVu Serif, which could not help and doubled the time.
- Variation selectors no longer count as letters the main font must have.

---

## v3.23.0 — 2026-10-07

Pre-edit state: commit `b329fc0` (v3.22.9). Script-aware font fallback: the
one-off `header-includes` of a multilingual paper (polyglossia, `ucharclasses`,
a `\newfontfamily` per script, `newunicodechar` rules that swap characters for
look-alikes) done once, properly, for every document.

### Added

- **`pdfmd_unicode/`**, a package beside `pdfmd.py` with no dependencies: the Unicode
  Script property as a generated range table (`scripts/gen_unicode_scripts.py`, from
  fontTools at development time only; `--check` reports drift), a reader of fonts'
  own `name` and `cmap` tables (TrueType/OpenType and collections), the installed
  fonts from fontconfig or a scan of the system font folders plus pdfmd's own folder
  (`~/.local/share/pdfmd/fonts`), and a per-script list of families to try.
- **Fonts for other scripts** (lualatex, xelatex; `AUTO UNICODE`): the characters of
  the document's Markdown, metadata and bibliography files (code excluded) that the
  main font cannot draw are set, run by run, in the first installed font of their
  script's list, by a generated preamble and a Pandoc Lua filter that runs before the
  table-width filter (which renders table cells to LaTeX). Arabic and Hebrew runs get
  a direction, Han characters the Chinese/Japanese/Korean flavour the text or `lang:`
  points to, punctuation and combining marks the font of the text beside them,
  variable fonts (set at their thinnest weight by TeX) are used only when nothing
  else has the glyph. Characters no installed font has are listed in a WARN. The
  fonts that cannot be loaded are dropped and the build retried without them.
  A document with its own script setup (`ucharclasses`, `\newfontfamily`, `xeCJK`,
  `\babelfont`, `CJKmainfont`, `mainfontfallback`) is left alone;
  `pdfmd-options: {unicode: true}` forces it, `--no-auto unicode` disables it.
- **Main font by script** (`AUTO MAINFONT`): when the document is mostly in one
  script and STIX Two Text lacks letters of it (the Kazakh Cyrillic ә ғ қ ң ө ұ ү
  һ і), the first installed serif that has them all (Noto Serif, PT Serif,
  Source Serif 4, DejaVu Serif) becomes the main font, so no word is half one font
  and half another. This replaces most uses of the compile-then-retry with DejaVu Serif,
  which stays as the last resort.
- `tests/test_unicode.py`: synthetic fonts written by the tests themselves, so nothing
  depends on what is installed.

### Verified

- The author's Kazakh/Arabic/Chinese/Greek paper, with its `header-includes` removed:
  47 pages, no missing glyph (it had hundreds), one pass instead of a retry;
  Arabic right-to-left in Amiri, Han in Songti SC, the rest in Noto Serif; with
  its own header-includes it is built as before.

---

## v3.22.9 — 2026-10-07

Pre-edit state: commit `3de8508` (v3.22.8). What mdpdf does, without PyMuPDF; and
`mdpdf` and `inkmd` as command names.

### Added

- **Finishing touches on the built PDF**, with pypdf, so they work with every
  engine, and all off unless asked for: `--bookmarks` (PDF bookmarks from the
  Markdown headings when the engine made none; the headings are found again in the
  PDF's own text, in order, and a contents page is not taken for the chapters),
  `--header` / `--footer "LEFT,MIDDLE,RIGHT"` (a running header and footer; fields
  `{page} {pages} {header} {date} {title}`), `--attach-links` (the local files the
  document links to are attached as `linked/PATH`, with a paperclip in the margin
  beside the link), `--pdf-title/-subject/-author/-keywords` (PDF properties only)
  and `--paper SIZE` (`-V papersize=SIZE`, and the built-in renderers' page too).
  The header/footer text is Helvetica: letters outside Latin-1 are reduced to their
  base letter or `?` (the unicode work can improve that).
- **`mdpdf` command**: mdpdf's own keys (`-o -h -f -t -s -a -k -p` and long names)
  mapped onto the above, with bookmarks and attached links on, wildcards expanded,
  and several inputs combined into one PDF, like mdpdf. mdpdf (MIT) is a small tool
  built on PyMuPDF (AGPL); its ideas are done here and none of its code or
  dependencies is used. If the real `mdpdf` is installed too, the last installed owns
  the command name.
- **`inkmd` command**: `pdfmd -e inkmd` with inkmd's keys (`-o`, `--page-size`,
  `--family`, `--no-autolinks`, `--no-html`, `--allow-unsafe-urls`,
  `--allow-remote-images`, `--emoji-fallback`; the last five are now ordinary pdfmd
  flags for the built-in renderer), any named engine winning. Like inkmd it reads
  standard input when no file is given and writes the PDF to standard output for
  `-o -`, or when there is no `-o` and standard output is not a terminal.

### Changed

- **Attaching keeps the whole document**: `write_pdf_attachments` now clones the
  PDF instead of copying its pages, so the properties, bookmarks and files already
  in it survive an attach (they were dropped).
- The default page size of `mdpdf` and `inkmd` is pdfmd's, not Letter.

---

## v3.22.8 — 2026-10-07

Pre-edit state: commit `a4e2780` (v3.22.7). Python 3.9, and pictures included by
raw LaTeX.

### Added

- **Python 3.9 is supported again** (it was 3.10+): `from __future__ import
  annotations`, and `write_text_lf()` for the one place that used `Path.write_text(newline=)`
  (3.10+). macOS's own `/usr/bin/python3` is 3.9, so `python3 pdfmd.py` works
  there without a newer Python. The whole suite passes on 3.9.6; CI now runs 3.9,
  3.10 and 3.13. (The built-in math renderer, md2pdf, still needs 3.11.)
- **Pictures included by raw LaTeX are recorded and restored from the PDF like
  Markdown ones**: `\includegraphics{...}` in a raw block or the preamble
  (extension optional). One inside a stored `.tex` file is stored by `--bundle`.

### Fixed

- On the PDF route, `-c` (batchocr's `--concat`) was still taken as an
  abbreviation of pdfmd's `-cwd` by Python versions before 3.12 even with
  abbreviations off; the single-dash long options are now removed from that parser.
- `PDFMD_BATCHOCR` is split the Windows way on Windows (a path with backslashes),
  and a report whose chapters sit on different drives falls back to the first
  chapter's folder.

---

## v3.22.7 — 2026-10-07

Pre-edit state: commit `d584d35` (v3.22.6). A PDF given to pdfmd is read, not
built: PDF to Markdown, with all of the reading in batchocr.

### Added

- **PDF input**: `pdfmd paper.pdf` writes `paper.md`; the direction follows the
  files (a `.pdf` input, `-o x.md`, `-o x.txt`, `--to md|txt`). A PDF that carries
  a pdfmd source is restored (`--restore`) instead; `--extract`, `-o FILE` or `--to`
  read its pages. `-o x.pdf`, a target such as `--to html`, contradictory
  `-o`/`--to`, and PDF mixed with Markdown inputs are refused before anything runs.
- **Everything pdfmd does not know goes to batchocr unchanged** (M1ck4's flag
  names: `--ocr`, `--lang`, `--export-images`, `--page-breaks`, `--preview-only`,
  `--stats`, `--no-progress`, `-q`, `--no-color`; and batchocr's own). The flags
  that exist in both are mapped: `-o/--output` (`--output` is new, an alias of
  `--out`), `-t/--to`, `-j`, `-v` (pdfmd's is a switch, batchocr's a counter, so
  `-vv` is passed as two), `--engine` (batchocr's takes `FORMAT=ENGINE`; only such
  a value goes on). Abbreviations are switched off on this route: `-c`
  (batchocr's `--concat`) used to be taken as an abbreviation of pdfmd's `-cwd`.
  Checked for every one of batchocr's 47 options and M1ck4's.
- **`pdfmd --install batchocr`**: `pip install "batchocr[md] @ git+https://github.com/aliperdehan/batchocr.git@v1.2.4"`
  into the Python pdfmd runs from (`PDFMD_BATCHOCR_SPEC` overrides the spec, for a
  checkout), with a note that PyMuPDF is AGPL-3.0 and installed as its own
  package, and the brew/apt command for Tesseract and Poppler if they are missing.
  `PDFMD_BATCHOCR` names a command for a checkout that is not on PATH.
  `--check-dependencies` reports batchocr, Tesseract and Poppler.
- The manifest of an attached source also records when and on what it was made
  (timestamp, platform, TeX Live) beside the pdfmd, pandoc and engine versions.
- README: "PDF to Markdown", with the credit to M1ck4 and the licence note.

### Notes

- batchocr 1.2.4's tags exist only locally until it is pushed; `--install batchocr`
  needs `v1.2.4` on GitHub.

---

## v3.22.6 — 2026-10-07

Pre-edit state: commit `1311d83` (v3.22.5). A PDF that was attached without
`--bundle` still gets its images back: the PDF holds every picture it drew.

### Added

- **`--restore` takes the Markdown's images out of the PDF itself** when they
  were not bundled. The manifest records, for each image, which picture of the
  PDF it is (found by its size and its order among the pictures; a JPEG by its
  bytes, since every engine copies the file's own stream) and restore writes it
  back: a JPEG **byte for byte**; a PNG, GIF or other raster as a PNG of the
  PDF's pixels (grey, palette, RGB at 1-16 bits, and an alpha channel from the
  soft mask), not the original file but the same picture; an **SVG or PDF
  figure as a one-page vector PDF** (`fig.svg` comes back as `fig.pdf`, and the
  restored Markdown now points at `fig.pdf`: restore says so). A picture the PDF
  does not hold is only recorded, as before. Checked by restoring a document
  with RGB, RGBA, grey, palette, JPEG, SVG and PDF figures and building it
  again: every page renders pixel-identical, and the restored PNGs equal the
  originals pixel for pixel. No new dependency (zlib and pypdf).
- **`--bundle` is not needed for images any more**; it stays for data and
  anything the PDF does not draw. A bundle stores the original files and
  extracts nothing.

---

## v3.22.5 — 2026-10-07

Pre-edit state: commit `fb3fd74` (v3.22.4). A bundle that rebuilds on a machine
that has only the PDF, found by restoring a real lab report and building it
with its house style hidden from LaTeX.

### Added

- **A bundle follows what it stores**: a stored `.tex`, `.md`, CSV and the like
  is read for the files it points at, to any depth (a figure's `tex/fig.tex`
  that `\input`s `tex/fig-raw`, which the first version missed: the restored
  report did not compile).
- **Files only the TeX tree finds are stored**: an `\input{chemicals}` that
  resolves through `kpsewhich` to the user's own tree (not the TeX
  distribution's, not the document's folder) is stored and restored beside the
  document (`FILE chemicals.tex (... from a TeX tree)`).
- **`--bundle-packages`, `pdfmd-options.bundle-packages`**: also store the
  packages and classes the preamble loads from that tree, what they `\input`
  and the graphics they name (found by looking every braced word up with a
  graphic's extension: a logo file named in a macro, and a few harmless
  look-alikes). Checked on a real report: restored from the PDF alone and built
  with `TEXMFHOME` pointing at an empty tree, it produced the same PDF text.
- **The manifest records requirements** (`requirements`): the user's own TeX
  files with their `\Provides...` version and hash and whether they were stored,
  the fonts the metadata names, and pdfmd/pandoc/engine versions. `--restore`
  and `--restore --list` print what is missing (`NEEDS package ...: not stored`)
  and attaching says so in a note.
- **`-r/--report` builds carry their source** (`--attach-source`, `--bundle`):
  every chapter keeps its own front matter and its place relative to the
  chapters' common folder; restore says `pdfmd -r DIR` builds it again.
  (A `name#section` build still attaches nothing: it is a throwaway.)

### Notes

- Found while testing, not changed here, cause not found: on the real lab report
  the first build of a source that has no BUILD NOTES block (a restored folder is
  one, since comments go) prints REFERENCES without its "VIII." number, and the
  same source after pdfmd has stamped it has it. The generated `.tex` is identical
  in both (`--stop-at tex`), so it is the compile, not the restore.

---

## v3.22.4 — 2026-10-07

Pre-edit state: commit `b244bf7` (v3.22.3). What the attached source keeps and
cuts: comments per kind of file, only the bibliography entries that are cited,
deflated attachments.

### Added

- **`pdfmd-options.strip-comments` names kinds** (and `--strip-comments-in KINDS`,
  `--keep-comments-in KINDS`): `true`, `false`, a list of kinds, or a per-kind
  mapping. Kinds: `markdown`, `preamble` (LaTeX `%`), `bibliography` (the text
  between a .bib's entries), `csl` (XML comments). A PDF's attached source now
  loses the comments of all of them by default. The LaTeX stripper is careful: a
  `%` that closes a line stays as a bare `%` (it swallows the line break, which
  is meaning), `\%`, `\verb`, `\url`, verbatim/listings/minted environments are
  text, `% !TEX` magic comments stay. YAML metadata loses its `#` comments
  whenever it is embedded (merged and written again) and Lua filters are never
  touched; both are said in the help.
- **The attached bibliography holds only the entries the text cites**, with
  what they `crossref`/`xref`/`xdata`/`related`, `@string` and `@preamble`; the
  keys come from the Markdown (`@key`, `[@a; @b]`), raw `\cite`-family commands,
  the metadata and the preamble, and `nocite: '@*'` / `\nocite{*}` keeps every
  entry. `pdfmd-options.attach-bibliography: all` / `--attach-bibliography all`
  keeps the file whole. `--list` and `--restore` say "2 of 120 entries".
- Restore names every Lua filter it writes (it is code, and pdfmd runs one beside
  a document) and the docs now say so; the earlier sentence that a restored
  filter "runs only if trusted" was true of an embedded filter, not of a file.

### Changed

- Attachments are deflated (a real report's PDF went from 413 KB to 215 KB with
  the same content, mostly the pruned bibliography).
- The manifest's `comments_stripped` is the list of kinds (older PDFs hold a
  plain true/false, which `--restore` still reads), and it records
  `bibliography` and `mode`.

---

## v3.22.3 — 2026-10-07

Pre-edit state: commit `28408c7` (v3.22.2). Packaging and documentation for the
attached source.

### Added

- **The command is also installed as `pdfmd-cli`** (`[project.scripts]`), the
  package's own name: `pdfmd` is also the command of an unrelated, popular
  PDF-to-Markdown tool, and when both are installed the second install silently
  replaces the first one's `pdfmd`. `pdfmd-cli` is never ambiguous. (`mdpdf` was
  considered and left out: it is itself the name of an existing PyPI project and
  would recreate the clash.) A packaging test pins both names.
- README: "The PDF carries its own source" (`--attach-source`, `--bundle`,
  `--restore`, `--strip-comments`).

---

## v3.22.2 — 2026-10-07

Pre-edit state: commit `abab176` (v3.22.1). `--bundle`: the PDF carries the
files its source cannot.

### Added

- **`--bundle [all]`, `--no-bundle`, `pdfmd-options.bundle` (`true` | `all`),
  `pdfmd-options.bundle-max-mb` (default 100)**: besides the source, store the
  images and data the document needs, each as its own PDF attachment named
  `files/PATH` (no archive: any tool lists or extracts a file, and nothing is
  compressed twice). `--bundle` stores what the text and preamble point at; it
  finds them from Markdown images and `<img>`, `file="..."` CSV tables,
  `\includegraphics`, `\input`/`\include`, pgfplots `table` and
  `\pgfplotstableread`, listings, verbatim and included-PDF macros, and, as a
  catch-all, any word that is a relative file name naming a file that exists
  (how data reached through a project's own macro, `\irpanel{ir/x.csv}`, is
  found; a name only in a comment does not count). `--bundle all` stores every
  file in the folder except the output, hidden files and folders, `.aux`/`.log`
  and the like, and backups. It implies `--attach-source`; the Markdown files it
  stores lose their comments like the source does; a file outside the folder is
  named in a note and not stored; the manifest lists every stored file with its
  hash and size.
- **`--restore` puts the files back**, never over an existing one, checking each
  hash (exit 1 on a mismatch), and refusing a path that climbs out of the
  folder. `--list` shows them (`FILE path (size)`).
- Tests (28 in all): referenced and `all` bundles, a comment-only mention not
  counting, off and the size limit, an edited stored file.

### Checked on real documents (copies)

- The parts report of 3.22.1 with `--bundle`: 12 more files (0.4 MB: the IR
  spectra's CSVs, the figures, the TeX the preamble `\input`s) found, none of
  them by a pattern written for this project; the restored folder (27 files) built
  with the PDF's text identical to the original's (0 differing lines of 1231, 15
  pages), where without the bundle it stopped at the first missing CSV. The
  PDF grew from about 0.6 MB to 1.0 MB.
- A single-file report in a 39 MB folder: `--bundle` 14 files, 0.7 MB;
  `--bundle all` 83 files, 38.6 MB (under the limit).

### Not changed / not covered

- Images are stored as the original files, in addition to the copy the PDF
  engine embedded; sharing the two is not attempted. (`--bundle` stores them
  only when asked for.)
- Files the text reaches only through a computed name (a macro building a path
  from pieces) are not found; use `--bundle all`.
- Still not covered: `-r/--report`.

---

## v3.22.1 — 2026-10-07

Pre-edit state: commit `3abf9c1` (v3.22.0). The PDF carries its own source:
`--attach-source` and `--restore`. (Per-file bundles of the whole folder, images
included, come as the next patch release.)

### Added

- **`--attach-source` (alias `--embed-source`), `--no-attach-source`,
  `pdfmd-options.attach-source` (alias `embed-source`)**: after a successful PDF
  build the document's source is attached to the PDF (PDF attachments, listed by
  any viewer): `pdfmd-source.md`, the assembled Markdown with every kind
  embedded (metadata, preamble, Lua filters, bibliography and CSL), comments
  stripped (`strip-comments` defaults to on here; `strip-comments: false` keeps
  them), and `pdfmd-manifest.json`: the document's name, a hash of the source,
  where each embedded file sat relative to the document, each file of a parts
  document (its path, its dropped front matter, where it began), the document's
  own `no-auto`, the `parts` setting, and the images the text points at with
  their hashes (recorded, not stored). Added with `pypdf` after the build, so
  every engine, and the native tier, gets it; a failure leaves the PDF as built
  and says so. Off by default. Not for `name#section` builds, `-r/--report`
  or a non-PDF target (a note says reports are not covered yet).
- **`pdfmd --restore FILE.pdf [-o DIR]`** writes the layout back into
  `FILE.restored/`: `name.md`, `metadata/...`, the preamble, filters,
  bibliography and CSL where they sat, and `parts/...` split by the recorded
  boundaries. It reuses `--unpack --slim` for the embedded kinds. It never
  overwrites (stops, writing nothing, if a file is there), never writes outside
  its folder (a manifest path with `..`, absolute, or a drive letter is
  refused and the file goes to `NAME.unpacked/` or the document's own name),
  exits 1 if the attached text no longer matches its hash, and a restored Lua
  filter is as untrusted as any other (it runs only if this machine's pdfmd
  wrote it, or with `--trust-embedded`). `--list` shows what a PDF carries.
- `make_embed_plan()` (the assembled branch's embed-plan construction, now
  shared), `first_pdfmd_option()`, `option_flag()`.
- Tests: `AttachAndRestore` (single file with metadata and preamble, comments
  kept on request, parts with boundaries and front matter, images recorded, no
  overwrite, a PDF with no source, an edited source, hostile paths, the CLI) on
  blank PDFs, so they need no engine.

### Checked on real documents (copies of two lab reports)

- A parts report (a scaffold, 9 parts, an external metadata/Lua/bibliography set
  behind symlinks): attached, restored to `report.md`, `parts/*.md` (all nine
  byte-identical to the originals less their comments), `metadata/` with the
  metadata, CSL, bibliography and preamble; with the images put back and
  built, the PDF's text is identical to the original build's (0 differing
  lines, 15 pages). A single-file report with a local metadata/preamble/Lua
  set: restored layout builds the same `.tex`.
- The comment stripper took out the long private dictation comments of every
  part, and nothing else.

### Not changed / not covered

- Images and other data the text points at are recorded, not stored. Storing
  them (`--bundle`) is the next release.
- The Lua filter a project shares from outside its folder (not reachable
  through a name in the folder) is restored into `NAME.unpacked/`, which pdfmd
  searches; a symlink to it in `metadata/` is restored as the file itself.
- Restored YAML is re-written (comments lost), like `--unpack`.

---

## v3.22.0 — 2026-10-07

Pre-edit state: commit `58d1202` (v3.21.5 plus a README credit for inkmd). The
first step of attaching a document's source to its PDF (the rest follows as
patch releases of 3.22): the comment stripper that source needs.

### Added

- **`--strip-comments` / `--keep-comments` and `pdfmd-options.strip-comments`**:
  drop every `<!-- -->` comment from the assembled file (`--stop-at markdown`,
  also for a report). Meant for notes to oneself that must not travel (reviewer
  remarks, drafts, the BUILD NOTES block). It reads the Markdown, it does not
  pattern-match it: a comment inside a fenced (backtick or tilde) or indented
  code block or inside an inline code span is text and stays, YAML front matter
  is left alone, a fence-looking line inside a comment does not open a fence, and
  pdfmd's own markers (`<!-- pdfmd-... -->`, `<!-- pagebreak -->`) stay. A
  comment alone on its line takes the line with it, and a blank line that
  leaves doubled goes too; one inside a sentence takes one of the spaces around
  it; a multi-line one is removed whole; an unterminated one is kept as written.
  Off by default for the assembled file. The command line wins over the
  document, then its metadata files (`first_pdfmd_option`).
- `tests/test_attach.py`: the stripper's cases, and the option through the CLI.

### Not changed

- The comment handling the native renderers already have (`strip_html_comments`
  for their own text) is a separate function and untouched.

---

## v3.21.5 — 2026-10-07

Pre-edit state: commit `6fd97b8` (v3.21.4). The labels half of the cache for
sections, as decided after testing 3.21.3 with pandoc-crossref.

### Added

- **A section or element of an ordinary document takes the labels it lacks from
  the last full build, when the cache is on.** `pdfmd doc#results --cache` after
  a cached `pdfmd doc --cache` prints the numbers of the other sections where
  it printed `??`; the build says how many labels it took and from when. It
  reuses parts mode's seed file (a label the section defines itself stays its
  own) and the cache folder the full build already writes its `.aux` to; the
  full build's output is unchanged. pandoc-crossref leaves `\ref{...}` in LaTeX
  output, so its references are seeded the same way.
- The note after a section build says which of the two happened: references
  come from the last full build, or print as `??` (and that a full build with
  the cache on first would fill them in).
- `SectionLabelSeeding` tests (they need Pandoc and LuaLaTeX): after a full
  build no reference in the section's LaTeX log is undefined; without one they
  still are; a section's own label is numbered from its own start.

### Not changed

- Heading, figure, table and equation numbers of a section still restart at
  its first. Carrying them over needs a marker at every heading and element in
  the full build, which changes that build's output; it is left out.
- A section written to the full document's own output name (`-o doc.pdf`) is
  not seeded, since it would overwrite the `.aux` it reads (it already did).

---

## v3.21.4 — 2026-10-07

Pre-edit state: commit `5da17cb` (v3.21.3). Found by running 3.21.3 on a machine
with pandoc-crossref (Pandoc 3.11, crossref 0.3.25).

### Fixed

- **A labelled element directly under a heading no longer swallows the heading.**
  With no blank line between `# Results {#sec:results}` and
  `![Second](b.png){#fig:b}`, the figure's paragraph started on the heading's own
  line, and heading lookup (keyed by line number) let the figure replace the
  heading: `doc#results` built only the heading and the figure, losing its
  subsections, and wrote `doc.fig-b.pdf`. A heading line (and a setext
  underline) now ends a paragraph and never begins one, and lookup is keyed by
  position, so two items that begin on one line stay two items.
- **The note after a partial parts build told the truth about whole parts only.**
  A section or element cut out of a part is not given the full build's numbers
  by the cache (it has no counter marker; only a whole part has one), yet the
  note said it was. A second note now says such a cut is numbered from its own
  start, cache or not.
- `test_exact_stem_and_extension` compared a path with the file name as typed,
  which a case-insensitive filesystem (macOS, Windows) returns unchanged; it
  now compares the files themselves.

### Checked with pandoc-crossref (nothing changed)

- Every section and element build exits 0; crossref never leaves a literal
  `@fig:a` in LaTeX output. Only LaTeX reports `Reference 'fig:a' undefined`
  (printed `??`). In HTML and DOCX crossref itself reports `Undefined
  cross-reference` and prints `¿fig:a?`.
- In LaTeX output crossref writes references as `\ref{fig:a}`, so the last full
  build's `.aux` can fill them in (verified by hand with one LaTeX run); heading,
  figure, table and equation numbers of a cut still restart.
- pdfmd's own note, "references to other sections print as ??", is accurate for
  LaTeX and PDF output.

---

## v3.21.3 — 2026-10-07

Pre-edit state: commit `b52e436` (v3.21.2).

### Fixed

- **`--split` cuts at setext headings too.** A level-1 heading written as a line
  underlined with `===` (and, with `--split-depth 2`, a level-2 one underlined
  with `---`) starts a part like `# Title` does, instead of staying inside the
  part before it. The cut uses the heading scanner of 3.21.1, so a `---` that
  ends a paragraph, a table rule and `#` lines in code or comments are still not
  headings. On documents written with `#` headings only, the cut is identical
  to before (checked against the previous splitter at levels 1 to 3), and
  `--split` still verifies that the parts read back as the identical document
  (Pandoc AST compared).

---

## v3.21.2 — 2026-10-07

Pre-edit state: commit `2e04eee` (v3.21.1). The third step: anything with a
`{#label}`, not only a heading.

### Added

- **`pdfmd doc#fig:setup` builds one labelled element.** Named by its id, with
  the same spelling tolerance as headings: a figure (`![..](..){#fig:x}`), an
  equation (`$$..$$ {#eq:x}`), a table (its `: caption {#tbl:x}` line and the
  table it belongs to, the caption written below or above), a fenced
  `::: {#id}` div (to its closing fence, with whatever is inside), a fenced code
  block with `{#lst:x}`, a `[span]{#id}`, or the paragraph or list holding any
  other id. `doc#section/fig:x` finds one inside a section; a short name
  (`doc#setup`) finds `fig:setup` by its word, with a WARN.
- Built like a section, but a lone element does not bring the text before the
  first heading (a section does, as before), and comes out as
  `doc.fig-setup.pdf`. The document's title page stays: a title may come from a
  shared metadata file, so it cannot be dropped reliably.
- `--list-parts` lists the labelled elements as well, under the heading they
  sit in, with their kind (figure, equation, table, div, code block, paragraph).
- In parts mode the same names work for elements inside the parts.
- Tests build each kind of element to LaTeX and check every block against the
  full document's LaTeX.

### Not changed

- An element's number restarts at 1 and its references to other elements print
  as `??` (as for a section). External links and bare citations have nothing to
  cut out and are not addressable; an internal link names an id, which is.

---

## v3.21.1 — 2026-10-07

Pre-edit state: commit `c3df55a` (v3.21.0 and a changelog tidy). The second of
the three steps; it uses the lookup engine of 3.21.0 for headings.

### Added

- **`pdfmd doc#NAME` builds one section of an ordinary document.** The section
  runs from the heading to the next heading of the same or a higher level
  (subsections included). The build is a partial one, like parts mode's: the
  document's own front matter, settings and the text before its first heading
  are kept, the output is `doc.NAME.pdf` (a Cyrillic or Turkish heading gets a
  Latin file name), nothing is stamped, `pdfmd-partial: true` is set. Checked on
  real builds: every block of a section's LaTeX appears verbatim in the full
  document's LaTeX, also with a bare `# Title` promoted to the title.
- **Headings are named like files are found**: case, spaces, `_`, accents and
  script ignored, then looser spelling, then the start of the text or of a word
  (a WARN says which), and an explicit `{#id}` counts too (`doc#sec:methods`).
  `doc##name` means a level-2 heading (the number of `#` is the level),
  `doc#parent/name` one under another, `doc#a+b` several, and `#name` with no
  document the folder's only Markdown file. Two headings fitting equally well
  is an error that lists both and says how to tell them apart.
- **Setext headings** (a line underlined with `===` or `---`) count as headings
  of level 1 and 2. A `---` under a paragraph's last line, a table rule, `#`
  lines in code blocks or HTML comments and indented code are not headings.
- **`--list-parts` works for any document**: every heading and `{#id}` with its
  lines. In parts mode it also lists the headings inside each part.
- **Parts mode finds headings inside parts**: a name that is no part's builds
  the matching section of whichever part has it (`report#sampling`); a name
  starting with `#` is a heading from the start (`report##sampling`). A part
  named whole beats a section of it. A section of a part is numbered from the
  part's start, not its own (no counter marker is written for it).
- `--no-auto lookup` leaves headings only their exact name (case and spaces
  aside).
- `tests/test_sections.py`: the scanner, the resolver, and the CLI to LaTeX
  checking each section against the full build, ordinary and parts mode.

### Fixed

- With only the soffice fallback available, a parts or section build crashed
  with an `AssertionError`; it now fails with a message that names the cause.

### Not changed

- `--split` still cuts only at `# ` headings. Heading, figure and table numbers
  of a section restart, and references to other sections print as `??`
  (parts mode's own limitation without the cache); the cache does not carry
  numbers over for a non-parts document yet.

---

## v3.21.0 — 2026-10-07

Pre-edit state: commit `9af6dfd` (v3.20.5). First of three steps (3.21.0 to
3.21.2) that let `pdfmd NAME#section` render one section of an ordinary
document and find documents by what they are called inside. This one is the
lookup engine every later step reuses.

### Added

- **A document can be found by its alias, its title, the start of either, or a
  looser spelling**, after every rule that already worked has failed (so
  nothing that resolved before resolves differently; checked against the
  previous release on a folder of awkward names). In order, the first tier
  with a hit decides: `pdfmd-options: {alias: ...}` (a name or a list; a bare
  `pdfmd-title:` also counts), the file name, the title (`title:` or a
  `% title` line), all ignoring case, spaces, `_ - . :` and accents
  (`pdfmd animportantdocument`); then the same with merged letters
  (c/k/q, i/y/j, v/w, sh/ş/ш, ё/е, Kazakh қ=q=k, ү/ұ/у=u, ы/і=i; a `y`/`w` in
  what you type may be either vowel); then the start of an alias, file name or
  title (`pdfmd animp`, at least 3 characters), then the start of a word in
  one. A file name or alias beats a title at each step.
- **Every guess is announced.** An exact match that only differs in case,
  separators or script prints an `AUTO MD` line; everything after it is a
  `WARN` saying what matched. Two documents fitting equally well is an error
  naming both (`LookupAmbiguous`, a `FileNotFoundError`).
- **`--no-auto lookup`** restores the previous lookup exactly. CLI only: a
  document's own `pdfmd-options: no-auto` cannot apply to the lookup that is
  still finding it.
- `tests/test_lookup.py`: the old forms (exact, wildcard, Latin for Cyrillic,
  `Пробный`, dots in names) as a regression guard, plus the new tiers.

### Fixed

- `latin_candidates` had `("oi", "oй")` with a Latin `o` inside the Cyrillic
  replacement, a spelling that could never match a real name.

### Not changed

- `-b/--batch` and `-r/--report` still take names and folders exactly as
  before; nothing there is guessed.
- `pdfmd sub/name` still looks for `name.md` in the current folder first (an
  old quirk, kept); only the new tiers look inside `sub/`.

---

## v3.20.5 — 2026-10-07

Pre-edit state: commit `21ca3fa` (v3.20.4). Three small things from the local
verification of v3.20.3.

### Changed

- **`pdfmd --install typst` now says whether the download was checked.** On
  success it prints `SHA-256 verified (...)`, or a NOTE that no checksum was
  available when GitHub's API could not be reached; before, only the absence was
  ever mentioned, so a verified install looked the same as an unverifiable one.
- **"Pandoc was not found" names `pdfmd --install pandoc`** (and `full`, which adds
  Typst), so `-o file.html`, `-p`, `-e xelatex` and the rest of what still needs
  Pandoc point at the one command that fixes it, as the other hints already did.

### Not changed

- The "pdf_metadata is on but pypdf is not installed" warning on built-in builds
  was the missing `pypdf` dependency of v3.20.0 to v3.20.2, restored in v3.20.3;
  with `pip install pdfmd-cli` it no longer appears.
- Display math printed by the built-in inkmd renderer is centred with
  zero-width spaces between no-break spaces (inkmd has no text alignment), so
  text copied out of such a PDF carries runs of invisible characters.

---

## v3.20.4 — 2026-10-07

Pre-edit state: commit `a8bfbbf` (v3.20.3). Patch bump: a test, no behaviour change.

### Added

- **`tests/test_packaging.py`**: reads `pyproject.toml` itself and fails if
  `pyyaml`/`pypdf` stop being declared (v3.20.0 lost them, and every test still
  passed on a machine that had both installed -- only CI, which installs what is
  declared, noticed); if a `pdfmd --install KIND` has no `pdfmd-cli[KIND]` extra
  naming the same packages; if the vendored `pdfmd_inkmd` package, its fonts or its
  licences would not be shipped; or if the changelog's newest entry is not
  `PDFMD_VERSION`. On Python 3.10, which has no `tomllib`, a small fallback reader
  does the job, and a test checks that it agrees with `tomllib` wherever both exist.
  Shown to fail when the dependency line is deleted.

---

## v3.20.3 — 2026-10-07

Pre-edit state: commit `b152b40` (v3.20.2). Found by the branch's first CI run.

### Fixed

- **`pyproject.toml` had lost `dependencies = ["pyyaml", "pypdf"]`** while the
  built-in renderer was added, so a plain `pip install pdfmd-cli` installed
  neither. Both are optional inside `pdfmd.py`, but without PyYAML the
  `pdfmd-options:` front matter (`parts: auto`, `no-auto`, ...) is ignored and the
  built-in renderer drops a document's `title:`/`author:`; without pypdf the PDF
  Info stamp is skipped. Restored. This is what failed eight tests in the `native`
  job and the `report#methods` step of the `examples` job.
- `test_missing_md2pdf_is_an_error_not_a_silent_downgrade` expected the
  `--install math` hint on Python 3.10, where md2pdf correctly says it needs 3.11.

---

## v3.20.2 — 2026-10-07

Pre-edit state: commit `9a03bfa` (v3.20.1). Found while checking that the
Pandoc route is unchanged by the native tier.

### Fixed

- **The native tier's `CSV_DIV_RE` shadowed the Pandoc route's of the same name**
  (both module-level, the later one wins). `contains_csv_table()` then used a
  line-anchored regex without `MULTILINE`, so a `::: {.csv file=...}` div anywhere
  but the very start of the file was not detected, the CSV filter was not added,
  and the div printed as literal text. The native one is now `CSV_DIV_LINE_RE`;
  a regression test covers the Pandoc-side detection.
- `tests/test_native.py` `EngineSelectionTests` no longer sees a real LibreOffice
  (`resolve_soffice()` finds the macOS app bundle off PATH), which made two tests
  fail on a Mac with LibreOffice installed.

---

## v3.20.1 — 2026-10-07

Pre-edit state: commit `e15ed13` (v3.20.0). Patch bump by the one-time
numbering override above, though it adds a flag value.

### Added

- **`pdfmd --install pandoc | typst | full`**: the missing programs, without admin
  rights and without a package manager.
  - `pandoc` is `pip install pypandoc_binary` into pdfmd's own environment (the
    wheel bundles the real Pandoc executable; about 35 MB, wheels for macOS,
    Linux and Windows). Also `pdfmd-cli[pandoc]`.
  - `typst` downloads Typst's release archive for this machine (Linux and macOS
    `.tar.xz`, Windows `.zip`; x86-64 and ARM) from its GitHub release into
    pdfmd's tools folder (`$XDG_DATA_HOME` or `~/.local/share/pdfmd/bin`;
    `%LOCALAPPDATA%\pdfmd\bin` on Windows), checks the SHA-256 GitHub lists for
    the asset (and refuses a file that does not match; without the API it falls
    back to the `latest/download` link and says no checksum was available),
    extracts only the one executable, and runs `typst --version`. Typst is not on
    PyPI as a program (the `typst` package is Python bindings only), hence the
    download.
  - `full` is both. `math` and `emoji` are unchanged.
- pdfmd appends those folders to `PATH` at start-up, **behind** the user's own:
  a Pandoc or Typst already installed always wins. `--check-dependencies` lists
  the folders in use.
- The offer after a lossy native build now says "install Pandoc and Typst now"
  and does it, instead of printing commands.

### Changed

- The "install Pandoc and Typst" hints name `pdfmd --install full` first, then the
  system package manager.

### Verified here, and not

`--install pandoc` was run against the real PyPI in a clean virtualenv: the
installed Pandoc was found by `--check-dependencies`, built HTML, and left the
PDF to the built-in renderer (no engine). The Typst path is tested with a faked
release (archive types, executable bit, checksum mismatch refused, no-checksum
fallback, `.part` file removed), because the sandbox could not reach GitHub:
**the real download is not verified here**. A new CI job runs
`pdfmd --install full` and a Typst build on Windows, macOS and Linux.

---

## v3.20.0 — 2026-10-07

Pre-edit state: commit `91b6a39` (v3.19.8). Minor bump: a new capability, and
nothing changes for a machine that has Pandoc and a PDF engine.

### Added

- **A built-in fallback, so `pip install pdfmd-cli` works on a bare machine.**
  With no Pandoc, or Pandoc but no PDF engine, pdfmd used to stop with an install
  message. It now builds a plain PDF from a Markdown file with a pure-Python
  renderer, says so (`NOTE  Pandoc was not found: building with the built-in
  renderer ...`), and prints one `WARN  native (...)` line per kind of thing it
  could not honour. Two renderers:
  - **inkmd 0.5.0**, vendored in `pdfmd_inkmd/` (MIT; about 1.8 MB, standard
    library only, offline, byte-deterministic). It is a generated copy: the
    package is renamed so it cannot clash with a separately installed `inkmd`, its
    CLI files are dropped, and its 10 MB colour-emoji font is left out (emoji
    print as `[rocket]`-style labels). `scripts/vendor_inkmd.py` regenerates it
    from the PyPI wheel (checked against PyPI's SHA-256), and `--check` reports
    any drift; `pdfmd_inkmd/VENDORED.md` records the version and hash.
  - **md2pdf** (PyPI `pymd2pdf` 0.6, ReportLab; Python 3.11+), when installed.
    Footnotes, bookmarks, highlighted code, and (with matplotlib) offline math.
  Neither is Pandoc: no LaTeX, preambles, filters, citations, slides, parts or
  report mode, and Markdown input only; `.tex`, `.rst`, `--to html` and the rest
  still say Pandoc is needed.
- **Every input is read as GitHub-flavoured Markdown** (`normalise_gfm()`). Fenced
  code is never touched. `\newpage`/`\pagebreak`/`\clearpage` and
  `<!-- pagebreak -->` become a page break; every other `<!-- comment -->`
  (one line or several) is dropped, since neither renderer is trusted to; footnotes stay
  footnotes for md2pdf and become numbered endnotes for inkmd; heading and image
  attributes (`{#id .class}`, `{width=50%}`), `:::` fenced-div markers (content
  kept) and raw LaTeX (`{=latex}` blocks, command-only lines, non-math
  environments) are removed; citations stay as written; a `::: {.csv file="..."}`
  div becomes the same table the Pandoc filter builds (delimiter, `header=`,
  `rows=`/`cols=`, the 10 x 7 cap and its note). The front matter's
  title/author/date become a title block and the PDF's own Title/Author
  (`papersize` and `fontsize` are honoured too); other keys are listed as not
  used.
- **Math without a typesetter.** inkmd cannot typeset math, and md2pdf only what
  matplotlib's mathtext reads, so formulas are set as text: Greek letters and
  operators as Unicode, `x^2`/`x_i` as super/subscripts (Unicode ones for md2pdf,
  which ignores `<sup>`), variables in italics, `\frac{a}{b}` as `a/b`,
  `\sqrt`, accents, `\mathbb`, `\mathbf`, cases and matrices in a rough linear
  form. `$...$` is inline in the sentence; `$$...$$` (single or multi-line) and
  `\begin{equation|align|gather|multline}` are display math, set as their own
  centred lines (an `aligned`/`align` block stacks its rows). Centring is
  approximate: inkmd has no text alignment, so the line is padded using Helvetica
  metrics, with zero-width spaces between the no-break spaces because inkmd
  collapses a run of whitespace. md2pdf with matplotlib keeps the formulas
  mathtext reads (typeset, centred, rewriting `\tfrac`, `\frac13`, `\displaystyle`,
  `\tag`, `\le`/`\ge`, ... first) and sets only the rest as text; without
  matplotlib it is left alone (it would need the network). Dollar signs that are
  not math (`$5 and $6`) are written as `&#36;` for md2pdf, which read them as a
  formula (and printed a `\$` escape as it was).
- **md2pdf printed a local path.** It prepends a hidden `<!-- SOURCE_FILE: /full/path
  -->` marker and, when a paragraph follows it directly (a document that does not
  start with a heading), printed that marker, path included, into the PDF. Such a
  document now starts with an empty paragraph (`&nbsp;`) so the marker stays a
  block of its own.
- **`-e inkmd`, `-e md2pdf`, `-e native`** (and `pdf-engine:` in `pdfmd-options`)
  ask for it explicitly. It is chosen automatically only when no Pandoc route
  exists: an explicit request for a Pandoc engine or family without Pandoc is an
  error, never a silent downgrade, and a failing Pandoc build never falls back to
  it. With both renderers, md2pdf takes documents with footnotes, math (when
  matplotlib is there) or a title; inkmd takes the rest, and either is the
  other's fallback if it raises.
- **`pdfmd --install math|emoji`** and the extras **`pdfmd-cli[math]`** (md2pdf and
  matplotlib, about 150 MB) and **`pdfmd-cli[emoji]`** (the stock `inkmd` wheel,
  whose emoji font the vendored copy is pointed at, about 11 MB).
- **An offer after a lossy native build**, on an interactive terminal only (not in
  CI or a pipe, not with `PDFMD_NO_PROMPT` set): install md2pdf with math, the
  emoji font, show how to install Pandoc and Typst, or "continue and don't ask
  again" (remembered in pdfmd's cache folder).
- `--check-dependencies` lists the native renderers and prints which mode applies;
  it now exits 0 when only the native route exists.
- `tests/` (`python3 -m unittest discover -s tests`): the vendored copy, the
  normaliser, engine selection with and without Pandoc, and real `pdfmd` runs
  with nothing on PATH. `PDFMD_GOLDEN=1` compares inkmd's output with
  `tests/golden/` after a re-vendor. CI runs them on Windows, macOS and Linux,
  once without Pandoc installed; a weekly workflow checks for new inkmd and
  pymd2pdf releases and tests the newest pymd2pdf.

### Changed

- `select_engines()` falls back to the native tier instead of exiting when there
  is no Pandoc route (and never for slides), and `main()`'s Pandoc check is now
  skipped for a plain Markdown-to-PDF run. Every other mode (`--to`, `-p`, `-r`,
  `--split`, `--unpack`, `--stop-at`, `-w`, ...) still needs Pandoc and says so
  as before.
- `pyproject.toml` packages `pdfmd_inkmd` beside `pdfmd.py` (and its two licence
  files). A bare copy of `pdfmd.py` without that folder behaves as before.

### Verified here, and not

Checked in a clean virtualenv built from this tree, with only Python on PATH: a
`pip install .`, a build with inkmd (with and without the `[emoji]` font, the
page images looked at), a build with md2pdf after `pdfmd --install math`
(footnote, title, author, typeset and text-fallback formulas, prices, comments),
the interactive offer through a pseudo-terminal (each choice, and "don't ask
again" holding), the unit tests on Python 3.11, 3.12 and 3.13 (with and without
md2pdf and matplotlib), and inkmd's byte-identical output across those three.
Not checked: Windows and macOS, the `pip install` choices of the offer, md2pdf's
emoji and Kroki fetches (the sandbox had no route to them), and anything with
real Pandoc reports.

---

## v3.19.8 — 2026-10-07

Pre-edit state: commit `fb357d6` (v3.19.7). Patch bump by the one-time
numbering override above. From the author's re-test of v3.19.7 on real reports
with Pandoc 3.11.

### Fixed

- **The math-method flag, third time right.** v3.19.7's check for
  `--html-math-method` was wrong for Pandoc 3.11, which renamed the option to
  `--math-method` (and warns `Deprecated: --mathml. Use --math-method=mathml
  instead.`): the check failed and pdfmd fell back to the short flag, so the
  warning stayed. pdfmd now tries `--math-method`, then `--html-math-method`,
  then the short flags, taking the first the installed Pandoc lists in `--help`,
  matched as a whole option name (`--math-method` is a substring of
  `--html-math-method`, which a plain substring test would have taken for it).
  Checked against stand-in help texts for each of the four cases (3.11, the
  middle range, both listed, short flags only) and the real Pandoc 3.1.3; the
  3.11 spelling itself is from the author's report, not seen here.
- **A CSL style kept in Pandoc's user data folder was not embedded** (and, for
  any file not found, nothing said why). A `csl:` is now also looked up in
  Pandoc's `csl/` data folder (from the `User data directory:` line of
  `pandoc --version`), and a bibliography or CSL file found nowhere prints a
  `WARN  not embedded: ... (not found ...)` instead of only appearing in the
  NOTE. Checked with a style that existed only in that folder: embedded, then
  deleted from the machine, and the embedded file still built with a `.tex`
  identical to the original build's.

### Changed

- Assembling with anything embedded now also prints, once, that data a macro in
  the text reads (the CSV tables a report's plots take, images in raw LaTeX) is
  never embedded and cannot be detected; it stays beside the document. (The
  author's report: the real report's plots read CSV files from four folders,
  without which its PDF would not build.)

---

## v3.19.7 — 2026-10-07

Pre-edit state: commit `477e2bc` (v3.19.6). Patch bump by the one-time
numbering override above. From the author's test of v3.19.6 on real reports.

### Added

- **`--embed-metadata bibliography`: bibliography and CSL files embedded**, the
  way Lua filters are. The `bibliography:` and `csl:` files the merged metadata
  names go into `{=pdfmd}` blocks (`type: bibliography` / `type: csl`, with the
  `path:` the metadata gives them and a hash). A name that is absolute or climbs
  out with `..` cannot be written back as it is, so the embedded file's
  metadata then names it by its own safe path. At build time the blocks are
  written to a temporary folder at that path, for the length of the build, and
  the folder is searched after everything else -- by Pandoc's citeproc
  (`--resource-path`) and by BibTeX/Biber (`BIBINPUTS`; the cache route's
  compile step included) -- so a file beside the document still wins, and
  nothing embedded changes a lookup that already worked. They are data, so no
  trust is asked, unlike filters. It is a fourth kind: on in a bare
  `--embed-metadata`, switchable as `--embed-metadata metadata preamble` or
  `pdfmd-options: {embed: {bibliography: false}}`. With it off (or a file
  missing, or not UTF-8 text) the `NOTE  not embedded:` line still names them.
  An embedded file with its bibliography now builds alone in an empty folder
  (checked: byte-identical `.tex`, with citations resolved).
- `--unpack` writes the bibliography/CSL files back (at their paths, hash
  checked) and `--unpack --slim` removes the blocks; the slimmed file finds them
  in its `NAME.unpacked/` folder, which is now also searched for them.

### Fixed

- **`--self-contained` warned on Pandoc 3.11** (`[WARNING] Deprecated: ...`):
  pdfmd passed `--mathml`, which Pandoc 3.11 deprecates in favour of
  `--html-math-method=mathml`. pdfmd now uses the long form where the installed
  Pandoc lists it in `--help`, and the short flag (`--mathml`, `--mathjax`,
  `--katex`, `--webtex`, `--gladtex`) otherwise -- Pandoc 3.1 does not know
  `--html-math-method` at all, which a first version of this fix got wrong and
  a test on Pandoc 3.1.3 caught. (The `html: {math: ...}` option uses the same.)

### Checked

- Fixture with a metadata-owned `bibliography: refs/test.bib` and `csl:` in a
  subfolder and citations: embedded copy alone in an empty folder, `.tex`
  identical to the original build's (citations resolved); the same through
  `--unpack --slim` and the unpacked folder; absolute and `../` names rewritten
  and identical; `embed: {bibliography: false}` and `--embed-metadata metadata`
  leave them out, say so, and fail to build alone as expected; the math method
  against Pandoc 3.1.3 (short flag) and, by stubbing the capability, the long
  form; BIBINPUTS and the
  resource path carry the extracted folder. All earlier comparisons pass, also
  under Python 3.11 (the project's minimum), which now runs the stand-in-engine
  cache test as well.
- Not checked: BibTeX/Biber itself finding an embedded `.bib` for
  `citation-engine: natbib|biblatex` (no LaTeX here); only the search path is.

---

## v3.19.6 — 2026-10-07

Pre-edit state: commit `38008e1` (v3.19.5). Patch bump by the one-time
numbering override above. Everything here comes from a test of the branch on the
author's machine with real nulabreport reports and LaTeX engines (every
normal-build `.tex` and PDF text identical to main's; embedding round trips
identical).

### Fixed

- **The cache route dropped an embedded Lua filter** (`pdfmd-options: {cache:
  {aux: true}}` or `plots`, on an assembled file). `_convert_one` handed the
  cache route the document's already-merged `no-auto`, which for an assembled file
  lists `lua`; the Markdown-to-`.tex` pass inside re-reads the document's own
  `no-auto` itself and then hid the embedded filter, silently (a real 29-page
  report came out 28 pages). It now passes the command line's `--no-auto` only,
  as that inner pass expects. Found on the real report; reproduced here with a
  stand-in LaTeX engine: the `.tex` handed to the engine had no filter output
  before the fix, and has it after. A normal document with the same cache option
  is unaffected.
- **`--unpack` then `--unpack --slim` on the same file** stopped on "already
  holds". Files already there with exactly the content that would be written
  are now left as they are (and counted); a file that differs still stops the
  run, writing nothing.

### Changed

- **Corrected a too broad claim.** An embedded file does not "build the same
  alone, in any folder": metadata, preamble and filters travel, but what the
  text points at -- `bibliography:`/`csl:` files, images, files a preamble
  `\input`s or `\includegraphics`, data -- does not. The docs now say so, and
  assembling with `--embed-metadata` prints a `NOTE  not embedded: ...` naming
  those it can see (a bibliography or CSL key, `\input`/`\includegraphics` in
  the preamble, images in the text). `--lua-mode ref` paths are relative to the
  output file's folder, so the layout must be kept.

### Reported by the test, left as is

- `pdfmd src.md -o src.md --to markdown` overwrites its own source; true on main
  as well (not a regression). Only `--assemble-only` guards against it.
- `--cache` / `--cache-plots` on the command line do not travel to an assembled
  file (the `cache:` settings in `pdfmd-options` do); noted in v3.19.5.

---

## v3.19.5 — 2026-10-07

Pre-edit state: commit `952d6d8` (v3.19.4). Patch bump by the one-time
numbering override above.

### Fixed

- **An assembled partial build carries `pdfmd-partial`.** A partial parts-mode
  build (`report#methods`, `--section`) tells Pandoc `-M pdfmd-partial=true` on
  the command line, which a Lua filter such as nulabreport's reads to degrade
  gracefully when the Appendix is not there. The assembled file of such a build
  (`--assemble-only`, with or without `--embed-metadata`) did not carry it, so
  building the file later ran the filter as if for the whole report. It is now
  written into the front matter (`pdfmd-partial: true`, next to the assembled
  marker); a partial scaffold with no front matter at all cannot hold it, and
  says so. Found by tracing what a normal build passes to Pandoc outside the
  text.

### Checked

- A probe filter that reports whether it sees `pdfmd-partial`: normal partial
  build "partial", normal full build "full", the embedded copy of the partial
  build built alone "partial", with a `.tex` byte-identical to the normal
  partial build's. Earlier comparisons unchanged.

### Known limits, for the record (what an assembled file does not carry)

- Command-line options of the original run: `-V`, `--from`, passthrough Pandoc
  options, `--cache`/`--cache-plots` (the cache settings in `pdfmd-options` do
  travel), `-e`. Re-give them when building the assembled file.
- The label seeding and part counters of a partial build with the cache on
  (they come from the last full build of the scaffold, which the assembled file
  is no longer).

---

## v3.19.4 — 2026-10-06

Pre-edit state: commit `437596c` (v3.19.3). Patch bump by the one-time
numbering override above; this closes the assemble/embed series.

### Added

- **`pdfmd-options: {default-output: FORMAT}`**: the format a document builds
  to when the command line names none (no `--to`, no `-o` extension, no
  `--stop-at`, no `-p`). Any Pandoc writer name or `pdf` (`tex`, `md`, `txt`,
  `typ`, `htm` as shortcuts). Document first, then its metadata files (so a
  shared `metadata.yaml` can set it for every document that finds it); per
  document in `-b`, the first file in `-r`. A missing PDF engine is now an
  error only for a document that actually builds a PDF (a machine with no
  engine can build `default-output: html` documents); an explicit `-e` that is
  not installed still fails as before.
- **HTML options, `pdfmd-options: {html: {...}}`**, Quarto-style:
  `self-contained: true` (`--standalone --embed-resources`; `--self-contained`
  before Pandoc 2.19; MathML for math by default since it needs no network; a
  page with no title gets the file name as `<title>`), `standalone: true` (a
  full page, resources linked), `math:` (mathml, mathjax, katex, webtex,
  plain), `css:` (a name or a list, relative to the document).
  `--self-contained` / `--no-self-contained` on the command line win over the
  document (a Pandoc `--self-contained` passed through before now means this,
  which is what Pandoc meant by it). Nothing changes for HTML output unless one
  of these is set: it is still the fragment it was.
- An assembled file's **embedded LaTeX preamble stays out of every non-LaTeX
  build** (HTML, docx, typst, ...), where Pandoc would have printed it into the
  output; the HTML of an embedded copy equals the original's.

### Checked

- Self-contained from the document's option and from the flag: one file, image
  inlined as a data URI, CSS inlined, `<math>` for the maths, `<title>` set; a
  plain `-o x.html` and the fragment are unchanged. `default-output` from a
  document, from a shared metadata file (report mode), mixed in `-b -j 2`
  (html, typst and pdf side by side); beaten by `-o x.pdf`, `--to latex`;
  needs no PDF engine for an HTML document. The PDF path was exercised only
  through the Pandoc -> ODT -> LibreOffice fallback in the session that wrote
  this (LibreOffice was installed, no LaTeX engine); CI builds with Typst. All
  earlier comparisons and the normal-build baselines are unchanged.

### Known limits

- No PDF metadata stamping or engine chain for HTML (they are LaTeX/PDF only),
  and a BUILD NOTES comment stays in the HTML source as a comment, as it did.
- `math: mathjax|katex|webtex` fetch their scripts when the file is built, so
  they need network access with `self-contained`.

---

## v3.19.3 — 2026-10-06

Pre-edit state: commit `11f1c97` (v3.19.2). Patch bump by the one-time
numbering override above.

### Added

- **`NAME.unpacked/` is discovered.** The folder `--unpack` writes is an
  accessory folder for the document NAME.md, searched like `metadata/`: all of
  its metadata YAML files (in name order, as the only metadata for that
  document), every `.tex` in it as a preamble, every `.lua` in it as a filter
  (the folder is made by pdfmd for that document alone, so the usual "only
  fixed names" rule is not needed). `--watch` follows it.
- **Origin of the merged keys, recorded.** An embedded file writes
  `pdfmd-options.origin`: which keys came from the document and from each
  metadata file, and the line count and hash of each preamble file. `--unpack`
  uses it to write the metadata back as the files it came from
  (`01-metadata.yaml`, `02-report.yaml`, ...) and the preamble as its original
  files; a file without the record, or a preamble edited since, still unpacks
  as one merged `metadata.yaml` / one `preamble.tex`, as before.
- **`--unpack --slim`**: after writing the files, rewrites the assembled file
  without them (embedded filters, preamble, and the metadata files' keys where
  the origin is recorded), leaving the document's own front matter and its
  `NAME.unpacked/` -- the original layout, which the discovery then builds
  exactly like the embedded file (checked: byte-identical `.tex`).
- **`pdfmd-options` file names**: `yaml:` (or `metadata:` with a name/list)
  names metadata files, like `-y` but written in the document; the existing
  `preamble:` and `lua-filter:` still work, and all three can be grouped under
  `metadata:` (`metadata: {yaml: .., preamble: .., lua-filter: ..}`; `lua:` is
  accepted for `lua-filter:` there). Flat and grouped add up. Paths are
  relative to the document. `--no-auto metadata`/`preamble`/`lua` suppress them
  as they do the other document-written options; an explicit `-y` wins.
- **`pdfmd-options.embed`**: what `--assemble-only` embeds without the flag --
  `true` (all three), `false`, a list of kinds, or a mapping (`metadata`,
  `preamble` true/false, each on unless said otherwise; `lua`: embed|ref|apply
  |off, true = embed, false = off). The document's own value wins over its
  metadata files' (so a shared `metadata.yaml` can turn it on for every
  report), the command line over both: `--embed-metadata KIND ..`,
  `--lua-mode` (its default is now "the option, else embed"), and the new
  `--no-embed-metadata`. Resolved per document in batch mode.
- An embedded file drops the names it embedded (and `embed:`) from its own
  `pdfmd-options`, which would point into the original folder.

### Fixed

- A metadata file given with a path relative to the current folder in a
  subfolder (`-y cfg/x.yaml`, or the new `yaml:` key) made Pandoc, which runs
  inside that file's own folder, look for `cfg/cfg/x.yaml`. `resolve_yaml` now
  returns an absolute path (symlinks not resolved).

### Checked

- Slim + unpacked folder, embedded copy alone, and the original build give the
  same `.tex` for the fixture with two metadata files, a preamble, a filter and
  the document's own `header-includes`; editing an unpacked preamble changes the
  next build. Flat and grouped file names build the same; a document naming its
  files in a subfolder builds, and its embedded copy alone is identical.
  `embed:` as `true`, a mapping, a list, `false`, from a shared metadata file,
  and the CLI overrides behave as described. All earlier comparisons and the
  normal-build baselines are unchanged.
- Not checked: PDF compilation (no LaTeX engine in this session).

---

## v3.19.2 — 2026-10-06

Pre-edit state: commit `0434c8c` (v3.19.1). Patch bump by the one-time
numbering override above.

### Added

- **`--lua-mode apply`**: the filters run during assembly, Markdown to Markdown
  through Pandoc (`--wrap=preserve`, the reader pdfmd would pick), so the text
  already has their effect; they are listed under `pdfmd-options.applied-lua`
  and discovery of them stays off. Approximate by nature: Pandoc re-writes the
  text (explicit heading ids, table and footnote layout), a filter's change to
  the metadata and a filter that needs citeproc first are not reproduced. A
  filter that mentions `FORMAT` (it would see `markdown` here) is embedded
  instead, with a note; so is any filter when Pandoc fails on them.
- **`--unpack FILE [-o DIR]`**: writes an assembled file's embedded Lua filters,
  `preamble.tex` (the part of `header-includes` before the preamble marker) and
  `metadata.yaml` (the merged front matter) back out, into `FILE.unpacked/` by
  default. Checks each filter against the SHA-256 recorded when it was written
  and says whether this machine's pdfmd knows it; exit status 1 on a mismatch.
  Never overwrites (stops without writing anything) and never edits the file.

### Fixed

- An embedded `{=pdfmd}` block's backtick fence counted as "this document has
  code" (and its text could trip the citation, cross-reference, CSV-table and
  definition-list checks), so an embedded copy could gain a monofont line the
  original did not have. These checks now ignore embedded blocks. (Found by the
  round-trip comparison on a document with no code.)

### Checked

- `apply`, `embed` and `ref` copies of a fixture with a Header filter give a
  `.tex` byte-identical to the original build's (`off` differs by design); a
  filter that checks `FORMAT` is embedded instead and its copy is identical;
  a filter with a Lua syntax error falls back to embedding with a warning.
  `--unpack` round trip (filter byte-identical to the original, preamble and
  metadata written, a second run refused, an edited filter flagged). The v3.19.0
  and v3.19.1 comparisons and the normal-build baselines are unchanged.
- Not checked: PDF compilation (no LaTeX engine in this session).

---

## v3.19.1 — 2026-10-06

Pre-edit state: commit `1086cfe` (v3.19.0). Patch bump by the one-time
numbering override above.

### Added

- **`--embed-metadata [KIND ...]`** (with `--stop-at markdown`): the assembled
  file also carries what pdfmd discovers beside the document, so it builds the
  same alone, in any folder. Kinds: `metadata` (the YAML files merged as Pandoc
  merges them -- later file over earlier, document over both, per top-level key,
  checked against Pandoc 3.1.3 -- with the document's front matter, into ONE
  block; `pdfmd-options` merged by pdfmd's own cascade; a file's `no-auto` and
  `parts` are not carried), `preamble` (the preamble file(s) at the head of
  `header-includes`, a literal block), `lua` (the Lua filters). None named =
  all three. The kinds embedded are written into the file's own
  `pdfmd-options: no-auto` (and `embedded`), or into the comment form of the
  marker (`<!-- pdfmd-assembled: true; no-auto: lua -->`) where there is no
  front matter, so the discovery that would find them again stays off.
- **`--lua-mode embed|ref|off`** (default `embed`). `embed`: each filter whole,
  in a fenced `{=pdfmd}` raw block at the very bottom (the fence is longer than
  any backtick run inside; Pandoc ignores raw blocks of unknown formats); `ref`:
  the filter's path in `pdfmd-options.lua-filter`, relative to the output, a
  missing one a warning rather than an error; `off`: none. (`apply` comes in a
  later step.)
- **Embedded filters run only if trusted.** A Lua filter can run any command.
  pdfmd records the SHA-256 of each filter it embeds in
  `<cache>/pdfmd/embedded-trust.txt`; at build time an embedded filter runs only
  if its own text hashes to one of those, else it is skipped with a warning (the
  build completes) unless `--trust-embedded`. A hash stored in the file itself
  cannot prove where it came from, so it is not what is trusted. A CLI
  `--no-auto lua` skips embedded filters too.
- The assembled file is always read with Pandoc's own markdown (never `gfm`,
  which would print a `{=pdfmd}` block as code).

### Changed

- The BUILD NOTES stamp ignores embedded blocks when it looks for its comment
  (a filter's text can contain the words) and, when it has to create the
  comment, writes it above them, so they stay the last thing in the file.
- Front-matter macros (`experiment:` and the like) are emitted after an embedded
  preamble, as after a discovered one (a marker line in `header-includes`
  records where the preamble ends; it never reaches the `.tex`).

### Checked

- Embedded file -> `--to latex` is byte-identical to the original build's
  `.tex`, also when the file is copied alone into an empty folder (so the
  filter can only come from its block), for: a parts report with a metadata
  file, a preamble, a Lua filter and its own `header-includes`; a report/book
  with metadata and preamble; unicode/quoted/nested YAML; a document without
  front matter (with metadata, and with only a filter). Untrusted, edited and
  `--trust-embedded` filters, `--lua-mode ref` (and a missing file), `off`,
  selected kinds, the stamp, and `-b -j 2` behave as described. Normal builds and
  v3.19.0's plain assembly are unchanged against the earlier baselines.
- Not checked: PDF compilation (no LaTeX engine in this session).

### Known limits

- YAML goes through PyYAML (YAML 1.1 rules, comments lost): an ambiguous scalar
  such as `007` is written back as `7`.
- A document with no front matter and a bare leading `# Title` keeps its
  preamble out of the file (a new front-matter block would stop the title being
  promoted); a warning says so.
- A report/book build applies no discovered Lua filter, so none is embedded.
- The embedded preamble sits in `header-includes`, which a non-LaTeX target
  (HTML) would also see; that is for the HTML step.

---

## v3.19.0 — 2026-10-06

Pre-edit state: commit `26eb3ed` (after v3.18.0).

**Version numbering, a one-time override (the author, 2026-10-06):** the
"assemble / embed" feature series bumps the minor version once (this
release) and then only the patch number per step (v3.19.1, v3.19.2, ...),
instead of a minor bump each, to keep the version count down. The usual
rule above resumes afterwards.

### Added

- **`--stop-at markdown|tex|pdf`, and `--assemble-only`** (= `--stop-at
  markdown`). The build runs as normal and ends after the named stage.
  `markdown` writes the assembled Markdown, `NAME.assembled.md`: the scaffold
  and its parts joined into one text (a part's leading front matter dropped,
  as the real build does), or the chapters of a `-r` report/book; `-o` may
  name it, and an `-o` ending `.assembled.md` implies the stage. It carries
  no discovered metadata, preamble or filter yet, runs no engine, writes no
  stamp and makes no backup, and refuses to overwrite one of its own sources.
  `tex` is `--to latex` (`beamer` with `-p`). Combinations that contradict
  each other (`--to`, `-p`/`-w` with `markdown`, `--assemble-only --stop-at
  tex`, a non-Markdown input) are an error.
- **The `pdfmd-assembled: true` marker.** Written into the file's front
  matter, or, for a document with none, as a trailing `<!-- pdfmd-assembled:
  true -->` (a new front-matter block would stop a leading `# Title` being
  promoted to the title, so it is never created). Parts mode ignores a marked
  file (it would join the parts a second time, and `parts: auto` would
  otherwise take it for another scaffold beside `parts/`), and `-b`/`-r` with
  `--stop-at markdown` skip such files.

### Checked

- Assembled file fed back to pdfmd, `--to latex`: byte-identical `.tex` to
  the original build for a parts report, a report/book (`-r`), a single
  document with a bare `# Title`, and a `% title` block document. Normal
  `--to latex` output of the examples is unchanged.
- Not checked here: PDF compilation (no LaTeX engine in the cloud session
  that wrote this); nothing in this release touches that path.

---

## v3.18.0 — 2026-10-04

Pre-edit state: commit `50d46d4` (v3.17.0).

### Added

- **The plot cache: `pdfmd-options: {cache: {plots: true}}` / `--cache-plots`**
  (needs nulabreport >= 1.26.0 and LuaLaTeX; skipped with a note otherwise).
  Defines `\LabPlotCacheDir` in the generated `.tex`; the package then
  includes a stored PDF for each whole plot picture it has seen and logs the
  ones it hasn't to `<jobname>.plotreq`. After a successful build pdfmd
  renders those in parallel, each in a standalone job that loads the same
  preamble (cut from the generated `.tex`) and ships the picture out as a
  page of exactly its size, for the next build. A failure to render costs
  nothing but the speed-up. Staleness: the folder is keyed by a hash of
  `nulabreport.sty`, the preamble and the engine version; every entry records
  the user files its job read (`-recorder`, not a guess at argument names)
  and is dropped before the next build if one changed; an entry is committed
  by renaming its `.dim` last, so an interrupted render leaves nothing that
  could be half-used. Measured on a real 29-page report: 80 s plain, 28 s
  with `cache.aux`, 15 s with both; the cached build's words match the plain
  build's to 0.05 bp (0 of 12,312), and CSV edits, a patched package and a
  `trace color`/`overlay colors` that only the call's own keys set were each
  checked to give the right picture.
- **`--clear-cache`**: removes a document's cache folder (or all of it with
  no document). Always safe.

### Fixed

- The cache's `NOTE` text and `--help` now say what is cached and what is not
  (only LaTeX's cross-reference files; every build still typesets from the
  current package, filter and text).

---

## v3.17.0 — 2026-10-04

Pre-edit state: commit `f6498b3` (v3.16.0).

### Added

- **The cache: `pdfmd-options: {cache: {aux: true}}` / `--cache` /
  `--no-cache`.** Pandoc writes the standalone `.tex` (the path `--to latex`
  already takes), and pdfmd compiles it itself in a per-document folder under
  `~/.cache/pdfmd` (`$XDG_CACHE_HOME`, `%LOCALAPPDATA%`), using the existing
  direct-`.tex` runner (`compile_tex_direct`, now with `aux_dir`, `cwd`, `env`):
  rerun only while the log asks, bibtex/biber between passes. LaTeX's `.aux`
  persists, so an unchanged document settles in one pass. Measured on a real
  29-page report: 80 s cold, 28 s warm; the PDF text is identical to the
  Pandoc-run build's. A failed engine run wipes that document's LaTeX files
  and retries once clean. Off by default.
- **Parts mode + cache: a part built alone no longer prints `??`.** Labels
  from the last full build's `.aux` are defined (only where the part does not
  define them itself), and each selected part starts with a `\pdfmdpart{key}`
  raw line that restores LaTeX's counters to their values at that point of
  the full build (`pdfmd@st@key`), so `report#discussion+appendix` is
  numbered "V." and "VIII." as in the full report, not "I." and "II.".
  Verified on a real report and a demo; the NOTE says the numbers are the last
  full build's.
- **`citation-engine: natbib`/`biblatex` with parts**, via the same route
  (it was an error): bibtex/biber run between passes.

---

## v3.16.0 — 2026-10-04

Pre-edit state: commit `63cc7a7` (v3.15.1).

### Added

- **Parts mode: one long document as a scaffold plus a folder of parts.**
  With `pdfmd-options: {parts: auto}` (in a shared `metadata.yaml`, so the
  content files stay free of typesetting; or in the document's own front
  matter), a document with a `parts/` or `sections/` folder beside it is
  built from the scaffold and every `.md` under that folder, in natural
  filename order, in one Pandoc run. Off unless asked for, and with `auto`
  only for a document that actually has the folder, so nothing existing
  changes. Verified on a real 1,800-line lab report cut into nine parts:
  the Pandoc AST, the generated LaTeX and the PDF text are identical to the
  single file's. See the module docstring ("A long document in parts").
  - `--section NAME` / `--only`, `pdfmd report#NAME`, or a part's own path
    build just those parts (`report.NAME.pdf`, no stamp, `pdfmd-partial:
    true` in the metadata for filters). Typos are an error listing the
    choices, never a silent wrong build. `-s` is Pandoc's `--standalone`,
    so there is no short flag.
  - `--list-parts` prints the build order.
  - `+` joins sections (`report#discussion+appendix`), as does `,`. Parts
    always build in report order, once each, and the file is named in that
    order. A name matching parts in two top-level folders is an error, not a
    quiet union (`discussion/yield` names one exactly).
  - `--split-depth N` also cuts at `## `/`### ` headings, each cut section
    becoming a folder (its first file holds the heading), so a subsection
    can be built alone; slugs are cut at a word boundary.
  - `--split DIR` cuts a single-file document at its `# ` headings into a
    scaffold plus `parts/` in a NEW folder (the source is never touched; the
    other files it uses are symlinked in so the result builds as it
    stands), fence- and comment-aware (a `# ---` line in a code block is
    not a heading), then compares the Pandoc AST of the parts against the
    original and reports whether they read back identically. Verified on
    two real lab reports.
  - A leading YAML or `% title` block in a part is stripped before Pandoc:
    Pandoc merges later files' YAML and the **later value wins** (checked),
    so a stray `title:` in a part would have replaced the document's.
  - `--no-auto parts`, `parts: false`, `parts: <folder>`.
  - `-w/--watch` follows the parts folder.
  - `--backup` snapshots each part as well as the scaffold.
  - Built through `convert_one` (new `extra_inputs`, `partial` arguments),
    not the `-r/--report` branch, which is a separate, older code path that
    skips much of what single-file builds do (Lua filter discovery, among
    other things); that is why the output matches a single file exactly.

---

## v3.15.1 — 2026-09-30

Pre-edit state: commit `10c09f8` (v3.15.0).

### Fixed

- **PDFs now name pdfmd in their `/Creator` field** instead of only the
  underlying tool (`LaTeX via pandoc`, `Typst 0.x`, ...), which made a
  pdfmd-built PDF indistinguishable from a bare `pandoc` run. The existing
  post-compile PDF Info stamp (`stamp_pdf_metadata_posthoc()`, so every
  engine, gated by the same `pdf_metadata` switch) now appends it in
  pandoc's own order: `LaTeX via pandoc via pdfmd-cli`. Uses the PyPI
  distribution name so it is searchable; the version is already in the
  `PdfmdVersions` key. Idempotent; an absent Creator becomes `pdfmd-cli`.

---

## v3.15.0 — 2026-09-29

Pre-edit state: commit `dd52035` (v3.14.0). v3.14.0's `margin:`/`geometry:`
translation was front-matter-only, same scope `papersize:` translation
already accepted — but for a *translation* (as opposed to a same-document
default), that scope limit means a document with its margin set ONLY in a
shared `--metadata-file` loses it silently on the engine that can't read
that key natively, same failure this feature exists to fix, just moved
one level out. Found immediately after v3.14.0, checking that exact case.

### Fixed

- **`frontmatter_margin_geometry_options()` and `fix_typst_margin()` now
  also translate a `margin:`/`geometry:` set only in a linked
  `--metadata-file`**, not just the document's own front matter. Same
  precedence `pdf-engine`/`no-auto` resolution already uses (see
  `frontmatter_pdfmd_options()`'s callers): the document's own front
  matter is checked first, and only if it sets no `margin:` at all are
  the linked metadata files checked next, in order — so a shared
  `metadata.yaml` can set `margin:` once for every document that finds
  it, exactly the kind of file `nulabreport`-style pipelines already use
  for shared defaults. A real `geometry:` anywhere — front matter, any
  metadata file, or `-V` — still always wins, untouched, checked before
  any `margin:` in any source (same as `has_geometry()`).

  On the Typst side, `prepared_latex_inputs()` now takes `doc_count`
  (defaulting to 1, the existing behavior everywhere except report/book
  mode, which passes `len(files)`) to correctly tell every path after the
  main document(s) apart from the main document(s) themselves — a
  linked `--metadata-file`, which Pandoc accepts EITHER fenced
  (`---`/`...`-delimited, same as front matter) OR completely bare (no
  delimiters at all). `fix_typst_margin()` takes a new `is_metadata` flag
  for this: a bare *metadata file* is now read as pure YAML directly; a
  bare *main document* (no front matter at all) is always left alone —
  that's markdown body text, never YAML, and must never be parsed as
  such regardless of `is_metadata`. Confirmed directly: a *fenced*
  metadata file's mapping `margin:` was still silently missed even with
  this fix half-applied, because `yaml.safe_load()` chokes on a second
  `---` as "expected a single document in the stream" — front matter is
  now unwrapped from a metadata file's own text the same way it already
  is from the document's, before parsing either.

---

## v3.14.0 — 2026-09-29

Pre-edit state: commit `9466c31` (v3.13.0). v3.13.0 only translated a bare
scalar `margin:` — found immediately after, while checking whether a
document written for one engine family and later rendered through the
other would round-trip cleanly in the two directions v3.13.0 didn't cover:
a `margin:` that's already a per-side mapping (silently ignored on
LaTeX-family engines, same as the scalar case before v3.13.0), and a
`geometry:`-only document (silently ignored on Typst — no error, just the
wrong margin, since Typst's template never reads `geometry:` at all).

### Changed

- **`frontmatter_margin_scalar()` → `frontmatter_margin_geometry_options()`**,
  and **`fix_typst_margin_scalar()` → `fix_typst_margin()`**: both now
  handle a `margin:`/`geometry:` value of any shape Pandoc itself accepts,
  not just a bare scalar, via two new shared normalizers,
  `parse_margin_sides()` and `parse_geometry_sides()`, each returning a
  canonical `{top, bottom, left, right}` dict (or None when nothing safe to
  translate). Both now use `yaml.safe_load()` on the front-matter block
  (PyYAML — already an optional soft dependency here, see
  `frontmatter_pdfmd_options()`) instead of `frontmatter_margin_scalar()`'s
  old scalar-only regex, which is kept as the fallback when PyYAML isn't
  installed.

### Fixed

- **A `margin:` per-side mapping (`top:`/`bottom:`/`left:`/`right:`, or
  Typst's `x:`/`y:` shorthand) was silently ignored on every LaTeX-family
  engine**, same failure v3.13.0 fixed for a bare scalar but explicitly
  left this case out of scope for. `frontmatter_margin_geometry_options()`
  now expands `x:`/`y:` into paired sides and emits one `geometry:<side>=
  <value>` option per side actually given (or a single `margin=<value>`
  when all four are equal) — one `-V geometry:...` per option, at the same
  four call sites as before. A mapping using Typst's `inside:`/`outside:`/
  `rest:` (binding-aware, no LaTeX equivalent at all) is left untouched,
  same as v3.13.0 already left a non-scalar `margin:` untouched.

- **A document with ONLY `geometry:` set (no `margin:` at all) — written
  for and tested against a LaTeX-family engine — silently fell back to
  Typst's own default margin (1.25in) the moment `--engine typst` ran it**,
  no error, just the wrong margin: Typst's template never reads
  `geometry:` at all. `fix_typst_margin()` now parses `geometry:` the same
  way (a bare `"key=val"` scalar, a comma-joined `"key=val,key=val"`
  scalar, or a YAML list of either) via `parse_geometry_sides()`, and adds
  a new `margin:` mapping translated from it — `geometry:` itself is left
  in the front matter untouched (inert for Typst, not harmful). A
  `geometry:` option this can't safely interpret as a margin (anything
  with no `key=`, or a key that isn't a recognized margin/side name, e.g.
  `showframe`) leaves the document untouched rather than guessing.

---

## v3.13.0 — 2026-09-28

Pre-edit state: commit `c31a35b` (v3.12.0). Found and fixed while rendering
a bibliography document with `margin: 2.54cm` in its front matter and
`pdfmd-options: {engine: typst}`.

### Fixed

- **A document's own `margin:` value was silently ignored on every
  LaTeX-family engine, and crashed outright on the Typst engine.**
  `margin:` is a real Pandoc variable for the Typst template only —
  Pandoc's LaTeX template never reads it, only `geometry:` does (a list of
  "key=value" strings that becomes `\usepackage[...]{geometry}`).
  `has_geometry()` already treated a bare `margin:` as "a margin setting
  exists" (correctly, so `DEFAULT_MARGIN` wasn't injected on top of it),
  but nothing translated that value into the variable LaTeX's own template
  actually consumes — so `margin: 2.54cm` with no `geometry:` compiled
  fine on every LaTeX-family engine while silently keeping LaTeX's own
  much wider article-class default margins, the requested value never
  taking effect. New `frontmatter_margin_scalar()` detects this case
  (front matter/`-V` only, same scope as `pagesize_typo_value()`) and
  translates it into `-V geometry:margin=<value>` at all four call sites
  that already handle `DEFAULT_MARGIN` injection (`_convert_one`'s
  non-PDF-target and PDF-engine-loop branches, and both of report mode's
  matching branches). An explicit `geometry:` anywhere, or a `margin:`
  that's already a YAML mapping/per-side block, is left untouched.

- **`--engine typst` (or `pdfmd-options: {engine: typst}`) failed with
  `error: unexpected comma` on any document whose `margin:` was a plain
  scalar** (`margin: 2.54cm`, `margin: 1in`, ...) — exactly the value every
  other writer, including the LaTeX translation above, accepts. Pandoc's
  own default Typst template renders margin unconditionally as `margin:
  ($for(margin/pairs)$$margin.key$: $margin.value$,$endfor$)`: it always
  iterates key/value pairs, so a scalar has nothing to iterate and comes
  out as the literal, invalid `margin: (: ,)`. New
  `fix_typst_margin_scalar()` rewrites a bare scalar `margin:` in the
  document's own front matter into the `x:`/`y:` YAML mapping the template
  actually needs, applied through a generalized `prepared_latex_inputs()`
  (now also takes `typst_engine=`, mutually exclusive with `latex_engine=`)
  the same way LaTeX header-includes get corrected — a temporary, sibling
  copy of the input, cleaned up after the render. A `margin:` that's
  already a mapping (a `top:`/`bottom:`/`left:`/`right:` or `x:`/`y:`
  breakdown) needs no fix and is left alone.

  Report mode gets both fixes at its two matching call sites too. Only the
  document's own front matter is handled in either fix, not a shared
  `--metadata-file` setting `margin:` as a scalar — same scope limit
  `typst_papersize_translation()`'s callers already accept for `papersize:`
  — and only the plain-scalar case, not translating an existing per-side
  `margin:` breakdown into `geometry:` options for LaTeX, which is a
  reasonable follow-up left out of scope here.

---

## v3.12.0 — 2026-09-28

Pre-edit state: commit `17025b7` (v3.11.2). Found and fixed while wiring a
citeproc-dependent Lua filter (one that pulls a single formatted reference
out of citeproc's resolved bibliography div) into a real document.

### Added

- **`pdfmd-options: lua-filter: ...`** front-matter key
  (`frontmatter_extra_lua_filters()`), for a filter that isn't named after
  the document's own stem and so `find_lua_filters()`'s fixed
  auto-discovery (`<stem>.lua` / `nulabreport.lua`) never picks it up.
  Accepts a bare string or a YAML list, resolved relative to the document's
  own directory, merged with (not replacing) whatever auto-discovery
  already found, and deduped by resolved path. Same conventions as
  `pdfmd-options: preamble:` (`frontmatter_extra_preambles()`): a hard
  `SystemExit` if a named file doesn't exist, and suppressed the same as
  auto-discovery by `--no-auto lua` / a bare `--no-auto`.

### Fixed

- **Extra CLI args (`pandoc_options`, from `parse_known_args()`) landed on
  the Pandoc command line *before* `--citeproc`**, in every PDF-rendering
  code path (the direct `run()` closure, the standalone-tex-target branch,
  the soffice-bridge fallback, and both report-mode branches). Harmless for
  most passthrough flags, but silently broke any `--lua-filter`/`--filter`
  passed this way that depends on citeproc's resolved output — e.g. one
  reading citeproc's `id="refs"` / `id="ref-<citekey>"` bibliography div,
  which never existed yet when the filter ran. `pdfmd`'s own
  auto-discovered Lua filters were never affected (already correctly
  ordered after `--citeproc`) — only filters supplied via extra CLI args or
  (before this version existed) with no auto-discovery route at all.
  `cmd += pandoc_options` now happens after the `--citeproc` append in each
  of those five spots (left `convert_via_native_bibliography` — the
  `citation-engine: natbib`/`biblatex` path — untouched: it never produces
  citeproc's bibliography div, so this ordering doesn't apply there).
  Verified with `--verbose` that the built command now reads `--citeproc
  --lua-filter=...` instead of the reverse, and that a real citeproc-
  dependent filter resolves correctly through the full `pdfmd` pipeline
  (not just a synthetic Pandoc-only repro) — plus a regression check that
  an ordinary citation-free document, and `--no-auto lua` suppression of
  the new front-matter key, both still behave unchanged.

---

## v3.11.2 — 2026-09-26

Pre-edit state: commit `452e83d` (v3.11.1). Windows fixes found by reading
the code. Not yet run on Windows; the macOS/Linux behavior is unchanged.

### Fixed

- **`BIBINPUTS` joined paths with a hard-coded `:`** for a direct `.tex`
  compile with a bibliography. That's wrong on Windows, where the separator
  is `;` and the `:` in a drive letter (`C:\`) splits the path. It now uses
  `os.pathsep`, like `TEXINPUTS` and `--resource-path` already did.
  Re-verified on macOS: a direct `.tex` with `\bibliography{refs}` still
  resolves its citation.
- **`--open` did nothing on Windows** (it only knew `open`/`xdg-open`). It
  now uses `os.startfile`, Windows' "open with the default app".
- **LibreOffice wasn't found on Windows** unless it was on PATH, which the
  Windows installer doesn't do. `resolve_soffice()` now also checks
  `%ProgramFiles%` and `%ProgramFiles(x86)%\LibreOffice\program\soffice.exe`.

The two Windows-only branches were checked by running `open_file()` and
`resolve_soffice()` with `sys.platform` patched to `win32` (`os.startfile`
called; a fake `%ProgramFiles%` install found).

---

## v3.11.1 — 2026-09-26

Pre-edit state: commit `2d64619` (v3.11.0). First version published to PyPI.

### Added

- **Published to PyPI as `pdfmd-cli`**, so the install is `pipx install
  pdfmd-cli`. `.github/workflows/publish.yml` builds and uploads on every
  pushed `v*` tag, through PyPI trusted publishing (no stored token) and
  the repo's `pypi` environment. It refuses a tag that doesn't match
  `PDFMD_VERSION`.

### Changed

- The Python-too-old error and the README now show `pipx install
  pdfmd-cli`. README links and images are now absolute URLs, so they also
  work on the PyPI project page.

---

## v3.11.0 — 2026-09-26

Pre-edit state: commit `bcafe7f` (v3.10.0).

### Added

- **A symlinked metadata file finds files beside its real copy.** When a
  discovered or `-y` metadata file is a symlink, its target's real
  directory is appended to `--resource-path` (`resource_path_option()`),
  so a relative `bibliography:` in one shared metadata file resolves from
  every folder the file is symlinked into. That used to need an absolute
  path, because Pandoc runs in the symlink's folder. The directory is
  appended LAST, so it only decides a lookup that would otherwise fail.
  Without symlinked metadata the command line is byte-for-byte unchanged
  (no `--resource-path` is added).

  Motivated by nulabreport's `prelab-metadata.yaml`, which is symlinked
  into each prelab folder and hard-coded
  `bibliography: /Users/<name>/.../nulab.bib`. Verified on real
  prelabs (`prelab4`, `prelab5`, `prelab5.5`, all of which cite): old
  pdfmd with the absolute path and new pdfmd with `bibliography: nulab.bib`
  give pixel-identical PDFs (6/6, 4/4 and 2/2 pages), and the reference
  list renders. Also verified for typst and lualatex in single-file mode
  and for `-r` report mode, and that a non-symlinked metadata folder
  still gets no `--resource-path` at all.

---

## v3.10.0 — 2026-09-26

First change made under "commit before editing": the pre-edit state is
commit `a4724b5` (v3.9.2).

### Added

- **Installable with `pipx install git+https://github.com/aliperdehan/pdfmd`**
  (or `uv tool install`), which puts a `pdfmd` command on PATH. The new
  `pyproject.toml` names the distribution `pdfmd-cli`, because `pdfmd` on
  PyPI is an unrelated PDF-to-Markdown tool. The version is read from
  `PDFMD_VERSION`. `pyyaml` and `pypdf` are regular dependencies of the
  installed package, so `pdfmd-options:` and PDF metadata stamping work
  out of the box. Running `pdfmd.py` directly is unchanged, and both
  libraries stay optional there.
- **A clear error on Python older than 3.10**, instead of a `TypeError`
  from the first `list[str] | None` annotation. macOS's own
  `/usr/bin/python3` is 3.9.
- **Install instructions in the "Pandoc was not found" error.**

### Fixed

- **`--no-citeproc` broke the build instead of turning citeproc off.** It
  was only ever looked for among the options passed through to Pandoc,
  and then passed on to Pandoc, which has no such flag ("Unknown option
  --no-citeproc"). It's now a real pdfmd flag (listed in `--help`) that
  sets `CITEPROC_DISABLED`, and all five call sites that add `--citeproc`
  automatically check it. Verified in single-file, batch and report mode.
- **Missing default fonts made every LaTeX engine fail.** JetBrains Mono
  (code), and DejaVu Serif (the missing-glyph retry) on macOS, usually
  aren't installed on a fresh machine. `fontspec` then errored under
  lualatex and xelatex, pdflatex failed on Unicode, and the document
  silently fell through to typst or an HTML engine. pdfmd now checks
  whether a default font is installed (`fc-list`, else `luaotfload-tool`;
  with neither, it assumes the font is present, as before) and substitutes
  an installed one with a one-line `WARN`:
  - code: Menlo, DejaVu Sans Mono, Liberation Mono or Courier New;
  - the glyph retry: Times New Roman, Liberation Serif or Georgia. All
    three cover the ≥/Δ/· that STIX Two Text lacks.

  Each lookup runs at most once per run, and only when a document
  actually needs that default. Verified on a simulated fresh Mac (fonts
  renamed to nonexistent ones), with and without `fc-list`: that used to
  end on typst, and now builds with lualatex, Menlo and Times New Roman,
  with every glyph present. With the fonts installed, nothing changes:
  nulabreport's `LR_sample.md` built through v3.9.2 and v3.10.0 gives
  pixel-identical pages (4/4) with identical fonts.

### Changed

- README: install section rewritten around pipx; documents automatic
  `--citeproc` (and `--no-citeproc`) and the passing of unknown options
  through to Pandoc.

---

## v3.9.2 — 2026-09-25

Backup references: `backups/pdfmd.py.bak-20260925a` and `-20260926a` (in
the old `~/dev/python-projects/backups/`, like every backup reference
below). This is the last version with a backup file; from here on each
change is a git commit instead, and entries cite the commit.

### Changed

- **Moved to its own folder, `~/dev/py/pdfmd/`, to be published as a git
  repository.** `~/dev/python-projects/pdfmd.py` is now a symlink to the
  new location, so every existing alias and documented command keeps
  working unchanged. This file was renamed from `CHANGELOG-pdfmd.md` to
  `CHANGELOG.md` (an old-name symlink remains in `python-projects`).
  Backups made before this version stay in `~/dev/python-projects/backups/`.
- **Process: "commit before editing" replaces manual backups.** The
  header comment in `pdfmd.py` and `CLAUDE.md` now say so.
- **Licensed under MIT** (`LICENSE`).
- **Comments and changelog only, no behavior change:** the author's
  first name and absolute home-directory paths were replaced with "the
  author" and `~/` paths ahead of publishing, verbatim chat quotes were
  paraphrased, the docstring's example file names were made generic
  (`pdfmd report`, `pdfmd slides -p`), and the header comment now
  points at `CHANGELOG.md` / `CLAUDE.md` next to the script.

### Added

- **`README.md`**, with usage examples and real output, plus runnable
  sources in `examples/` (lecture notes, a CSV table, Beamer slides, a
  two-chapter book) and cropped page previews in `docs/`, rendered from
  those examples.

---

## v3.9.1 — 2026-09-24

Backup reference: `backups/pdfmd.py.bak-20260924c`.

### Fixed

- **A bare name containing a dot built the wrong file.** `pdfmd prelab5.5`
  compiled `prelab5.md` → `prelab5.pdf` and reported `OK prelab5.md`, never
  touching `prelab5.5.md`. `find_markdown()` and `name_candidates()` both ran
  `Path(...).stem` unconditionally, so the `.5` was taken for an extension
  and stripped. When a sibling with the shorter name existed, the wrong
  document was built (and its PDF overwritten) with no error. Both now go
  through a new `strip_lookup_suffix()`, which only drops `.md`,
  `.markdown` or `.pdf` (case-insensitive). `pdfmd prelab5.5` now resolves
  to `prelab5.5.md`; `prelab5` still resolves to `prelab5.md`. A name that
  is already an existing file, and wildcard patterns, return before this
  lookup and are unchanged.

---

## v3.9.0 — 2026-09-24

Backup reference: `backups/pdfmd.py.bak-20260924b`.

### Added

- **`pdfmd-options.backup.format` / `--backup-format`: choose how snapshots
  are named.** Presets cover every convention found in a survey of the
  real backup folders (LR2/backup, LR3/backups, LR4-5/backup and prelab/
  backups, ir/webbook/backups, nulabreport/backups and _superseded):
  `compact` (`report.md.bak.20260924091500`, still the default, so
  v3.8.0 behavior is unchanged), `dashed` (`report.md.bak.20260924-091500`),
  `stem` (`report_20260924-091500.md`), `suffix`
  (`report.md.20260924-091500.bak`), `short`
  (`report.md.09-24_09-15-00.bak`). A custom template also works: `{name}`
  `{stem}` `{ext}` plus strftime codes. It is validated, so a template
  without `{name}`/`{stem}` or without any strftime code is refused, since
  every snapshot or every file would then collide. A same-second clash gets
  `-2`, `-3`, ... before the extension (or before `.bak`).
- **Every existing naming form is recognized as a snapshot of its file**,
  whatever `format:` is currently set to. That covers the dedupe check,
  ordering (date parsed from the name, else mtime) and `keep:` pruning.
  Changing format therefore never makes old snapshots invisible.
  Recognition was dry-run against those real folders: every hand-made
  backup was attributed to the right source, and unrelated files (`test.tex`,
  `chat.md`, `.dotx` templates) were ignored.

### Changed

- `keep:` now prunes only **plain-timestamp** snapshots. A tagged name
  (`nulabreport.sty.pre-irstack.20260923-211848.bak`,
  `chemicals.tex.before-LR1-2`, `prelab5.md.09-21_18-27-50.pre-migration.bak`)
  is a deliberate milestone, never deleted and not counted toward `keep`.
  v3.8.0 only ever matched its own compact names, so it could not have
  pruned these either. This makes that guarantee explicit now that other
  forms are recognized.

---

## v3.8.0 — 2026-09-24

Backup reference: `backups/pdfmd.py.bak-20260924a`.

### Added

- **Automatic source backups on compile: `--backup` / `--no-backup` and
  `pdfmd-options: backup:`.** After a successful compile, the source is
  copied to `backup/<name>.bak.YYYYMMDDHHMMSS` beside it. That is the
  naming already used by hand in report folders (`LR2/backup/
  report.md.bak.20260923212449`, ...), so manual and automatic snapshots
  sort together. Front matter / metadata-file cascade is the same as
  `stamp:` (document wins, then each metadata file in order, then the CLI).
  Accepts `true`/`false`, a directory name, or `{enabled, dir, keep}`.
  `keep: N` prunes to the newest N snapshots of that one file, and only
  ever touches files matching `<name>.bak.<14 digits>[-n]`.
- The snapshot is taken **after** the BUILD NOTES stamp and skipped when
  the newest existing snapshot matches, ignoring the stamp's own lines (the
  live `Compiled ... pdfmd vX` line, its `- Compiled ...` history bullets,
  and the `Compile History:` heading). Recompiling unedited source (or a
  `--watch` recompile triggered by something else in the folder) therefore
  doesn't pile up copies. The line filter is needed because `stamp: {mode:
  history}` rewrites a timestamp on every compile, so a plain byte
  comparison never matched. That was caught on the first real run against
  `LR2/report.md`. Binary (office) sources fall back to a byte comparison. A backup failure (OSError) only warns and
  never fails a compile that already succeeded.
- Implemented as a thin `convert_one` wrapper around the old body (now
  `_convert_one`), so every success path gets it (Pandoc, natbib/biblatex
  direct compile, direct `.tex`, office). This avoids adding a call at
  each return. Report mode backs up each chapter after its stamp. `.qmd`
  reads only its own front matter (no metadata.yaml, same as the rest of
  the Quarto path).
- `--watch` is unaffected: `watch_signature()` is non-recursive and never
  sees `backup/`.

---

## v3.7.1 — 2026-09-23

Backup reference: `backups/pdfmd.py.bak-20260923a`. Found and fixed live
while building `LR4-5/report.md`, which has a `metadata/` subfolder (see
`accessory_directories()`).

### Fixed

- **A `metadata/` subfolder broke every raw-LaTeX relative-path reference
  in a document, not just Pandoc-resolved images.** When pdfmd
  auto-discovers a metadata file inside `metadata/`, it runs Pandoc with
  `cwd=metadata/` instead of the document's own directory
  (`resource_path_option()`'s own `pandoc_cwd` parameter), and compensates
  with `--resource-path`. But `--resource-path` only helps Pandoc's own
  image resolution — a real `Image` AST node from Markdown `![]()` syntax.
  Per pandoc's own manual, it "will not cause image paths to be rewritten
  in other cases (e.g., when pandoc is generating LaTeX)." A raw
  `\includegraphics{...}` in the document's own hand-written LaTeX, or a
  package macro that reads a relative-path data file (confirmed directly:
  nulabreport's `\irspectrum`/`\irspectrumcompare`, which hand a relative
  CSV path to pgfplots' own table-reading code), is resolved entirely by
  the TeX engine's own kpathsea search relative to `pandoc_cwd` — broken
  the moment that differs from the document's own directory, which is
  exactly what a `metadata/` subfolder does. Reproduced directly on
  `LR4-5/report.md`: lualatex failed first on
  `tlc/contour/plate-1_contour.png` (a raw `\includegraphics`), and again
  — after a report-local `\graphicspath` workaround fixed that one — on
  `ir/own-15.09/plain/aldehyde_plain.csv` (an `\irspectrumcompare` pgfplots
  table read), the same underlying cause surfacing through two unrelated
  macros. Fixed generally, not per-macro: new `tex_search_env()` sets
  `TEXINPUTS` (the one mechanism kpathsea honors for every one of these
  lookups at once) to include the document's own directory, passed via
  `env=` to both `--pdf-engine=`-invoking `subprocess.run()` calls
  (single-file/batch mode's `run()`, and report mode's engine loop). A
  no-op — `env=None`, subprocess inherits the parent environment exactly
  as before — whenever `pandoc_cwd == document_directory`, the common case
  with no `metadata/` subfolder or out-of-tree `-y` in play, mirroring
  `resource_path_option()`'s own condition exactly.

## v3.7.0 — 2026-09-21

Backup reference: `backups/pdfmd.py.bak-20260921a`. Found and fixed live
while migrating a `nulabreport` pre-lab document onto a shared
`--metadata-file` (`nulabreport/prelab-metadata.yaml`) in place of a
per-document `preamble.tex` — see that project's own `docs/CHANGELOG.md`
v1.15.0 entry and `LR4-5/prelab/backups/findings.md` for the document side.

### Changed

- **PDF-metadata stamping (`PdfmdVersions`/`PdfmdBuildDate`, on by default —
  see `--stamp-pdf-metadata`) is now a post-hoc edit of the finished PDF via
  the optional `pypdf` dependency, not LaTeX baked in before the engine
  runs.** Two real reasons, not a refactor for its own sake:
  1. **It silently broke a document's own package loads.** The old approach
     added a small `\hypersetup{pdfinfo=...}` snippet via a second
     `--include-in-header` file. Confirmed directly: pandoc's default LaTeX
     template gives `--include-in-header` and a metadata file's own
     `header-includes:` key THE SAME template slot, and `--include-in-header`
     wins outright rather than merging — so any `--metadata-file` that set
     `header-includes:` (not the `.md` document's own front matter, which
     `document_header_file()`/`wrap_latex_header_includes()` already
     protects) had its entire header-includes silently discarded the moment
     PDF-metadata stamping was also on, with no error at that point —
     surfacing only later as a confusing "Undefined control sequence" the
     first time the document used a macro from whatever it just lost.
  2. **It only ever worked on `LATEX_ENGINES`.** A non-LaTeX PDF engine
     (weasyprint, typst, soffice, ...) had no equivalent injection point
     this reached at all, so `pdf_metadata: true` silently did nothing
     there. A post-hoc edit of the produced PDF works identically regardless
     of which engine made it.
  - `pdf_metadata_snippet()` is left in place (now always returns `None`)
    rather than removed, since several call sites across the engine-
    fallback/native-bibliography/report/batch paths already thread its
    return value through as a plain parameter and already treat `None` as
    "no extra `--include-in-header` entry" — this retires the mechanism
    without touching any of that surrounding control flow. The real
    implementation is the new `stamp_pdf_metadata_posthoc()`, called from
    inside `stamp_after_success()` (now independent of `options["enabled"]`,
    which only ever gated the separate `.md`-source BUILD NOTES stamp).
  - Silently skipped, with a `WARN` under `--verbose`, if `pypdf` isn't
    installed — same soft-dependency convention this file already uses for
    `PyYAML`.

### Fixed

- **`citation-engine: natbib`/`biblatex` never called `stamp_after_success`
  at all** (`convert_via_native_bibliography`'s own call site in
  `convert_one`) — neither the `.md` BUILD NOTES stamp nor a PDF-metadata
  one ever fired for a document using this option, unlike every other
  success path in the same function. Found while verifying the change
  above through the full `pdfmd` pipeline (not just a synthetic `pandoc`/
  engine invocation, per this file's own process note); fixed by calling
  `stamp_after_success()` there too, on success, matching the other paths.

### Known gap, not fixed here

- Report/book mode's PDF-target branch (`main()`, the block whose own
  2026-09-20 comment already flags this) still never calls
  `document_header_file()`, so `files[0]`'s own front-matter
  `header-includes:` can still collide with `--include-in-header` from a
  report preamble the same way PDF-metadata used to — this change removes
  PDF-metadata as one trigger of that collision, but a report preamble
  itself can still cause it. Left as previously flagged: no report/book-mode
  document was available this session to verify a fix against.

## v3.6.0 — 2026-09-20

Backup reference: `backups/pdfmd.py.bak-20260920b`. Same CHEM 341 session as
v3.5.1 just below, requests raised directly while watching that build's own
output.

### Added

- **`--full-paths`** (default off): AUTO YAML/TEX/MD, the OK/FAIL/SKIP/
  `[WARNING] unnumbered Markdown` status lines, and (with `-v`) the CMD line
  now print a path relative to the current directory by default, falling
  back to the absolute path only when it isn't under cwd at all (a system
  temp file, e.g.). `-v`/`--verbose` (and `--debug`, which already implies
  it) turns full paths back on too -- more detail is the point of asking for
  verbose -- so `--full-paths` on its own is really for getting full paths
  WITHOUT the rest of `--verbose`'s output. Raised directly: the previous
  always-full-path default is fine from a shallow directory (Downloads) but
  genuinely hard to read from a deep one -- the concrete example was a path
  under `.../Library/CloudStorage/OneDrive-.../Documents/Fall26/CHEM341/
  guides/M1`. New `display_path()` helper; applied at every AUTO YAML/TEX/MD
  and status-line call site plus `log_cmd()`, but NOT the `MARGIN`/
  `MONOFONT`/`PAPERSIZE`/etc. `note()` detail strings (those still embed
  `{md_path}` in full) -- narrower scope than a complete sweep, chosen to
  match what was actually asked for ("auto md, auto yaml, auto tex") rather
  than guess at a larger one under time pressure; a `note()`-detail pass is
  a reasonable follow-up if the same complaint comes up there too.
- **`pagesize:` -> `papersize:` auto-correction** (`pagesize_typo_value()`,
  new `papersize` `--no-auto`/`pdfmd-options.no-auto` KIND): a document that
  sets `pagesize:` (not a real Pandoc variable -- `papersize:` is) and no
  `papersize:` of its own now gets `-V papersize=<value>` added
  automatically on LaTeX-family targets, with a `PAPERSIZE` AUTO note
  explaining the substitution. Raised directly: the CHEM 341 document this
  session was built around already had `pagesize: a4` in its own front
  matter and a task brief that KNEW it silently produced a Letter PDF
  instead -- documented as an accepted caveat rather than fixed, because
  nothing was catching it (that document has since been fixed by hand --
  `papersize: a4` directly -- once this made the gap obvious). Wired into
  `convert_one`'s two PDF-and-`-t`-latex-target branches, the same two
  places `geometry_needed`/`DEFAULT_MARGIN` already live -- NOT into
  `convert_via_native_bibliography` or either report-mode branch (same
  scoping call as the v3.5.1 fixes below: unverified paths left alone
  rather than patched blind).
- **`papersize:` translation for the typst engine** (`typst_papersize_translation()`,
  `TYPST_PAPERSIZE_ALIASES`, reuses the `papersize` KIND above): Pandoc's
  `papersize:` variable is LaTeX-shaped by convention ("letter", "legal",
  "a4", ...) and Pandoc's typst template passes that string straight through
  to typst's own `page(paper: ...)` rule, which does not accept "letter" or
  "legal" at all (typst's own names are "us-letter"/"us-legal"; most other
  names, "a4" included, already match and need no translation). Raised
  directly: letter and legal paper sizes worked with TeX engines but not
  with typst.
  Confirmed as a hard failure, not just a wrong default: `papersize: letter`
  through `--pdf-engine=typst` errored outright before this fix (typst
  rejects the unrecognized paper name), and produced a correct 612x792pt
  Letter PDF after it. Only the two confirmed-different names are aliased;
  extend `TYPST_PAPERSIZE_ALIASES` if another is found to differ the same
  way. Applies whether the size came from the document's own `papersize:`,
  a `-V papersize=`, or this session's own `pagesize:` auto-correction above
  -- wired into the same two `convert_one` branches, gated on `--to typst`/
  `engine == "typst"` respectively.
- **`pdfmd-options: preamble: ...`** (`frontmatter_extra_preambles()`): a
  document can now name its own LaTeX preamble file(s) explicitly -- a bare
  string or a YAML list, resolved relative to the document's own directory
  -- instead of relying on the fixed `preamble.tex`/`latex-preamble.tex`
  auto-discovered names. Merged with (appended after, so it can override)
  whatever `PREAMBLE_FILENAMES` auto-discovery already finds, and gated by
  the same `--no-auto preamble` as auto-discovery (an explicit CLI `-H`
  remains the one thing that survives even that). A path that doesn't exist
  is a hard `SystemExit`, not a silent skip. Wired into all four
  `find_preambles()` call sites (single-file, batch, report x2). Directly
  requested (`is it worth it?`) alongside a real use case that, on
  inspection, turned out NOT to need it after all -- see
  `frontmatter_extra_preambles()`'s own docstring for why (a preamble whose
  own `\setchemfig`/`\usetikzlibrary` calls need chemfig/tikz loaded first
  can only get that from `\input` inside a document's own header-includes,
  not from any `--include-in-header` ordering, named or auto-discovered
  alike) -- but the capability is still useful in general, and is what that
  document would reach for if it didn't have this specific ordering need.
  `metadata`/`filter` equivalents were asked about in the same breath but
  NOT implemented this round -- metadata-file discovery is more deeply
  woven into per-directory caching and `-y`/CLI-arg interplay than preamble
  discovery is, and deserves its own careful pass rather than a rushed
  version bolted on under the same time budget as everything else here.

### Verified

`--full-paths`: confirmed default (relative) and `--full-paths`/`-v`
(absolute) output on a real `pdfmd Midterm_guide.md ...` run against the
same CHEM 341 document. `pagesize`/`papersize` auto-correction: confirmed
against a synthetic `pagesize: a4` document (`pdfinfo` reporting `595.276 x
841.89 pts (A4)` by default, `612 x 792 pts (letter)` under `--no-auto
papersize`) -- not re-tested against the CHEM 341 document itself, which no
longer needs it (fixed by hand at the source instead once this made the gap
visible). typst translation: confirmed against a synthetic `papersize:
letter` document targeting `--pdf-engine=typst` (hard failure before the
fix, correct 612x792pt PDF after it). `pdfmd-options.preamble`: confirmed
end-to-end against a synthetic document (a `\newcommand` in a separately-
named preamble file, invoked in the body, rendering correctly in the output
PDF) -- the normal case, `--no-auto preamble` correctly suppressing it
(`\mygreeting` came back undefined, as expected), and a nonexistent named
file raising the intended `SystemExit` with a clear message. Only
single-file mode was run against a real `pdfmd` invocation; batch and
report mode use the identical `find_preambles(...) +
frontmatter_extra_preambles(...)` pattern at their own call sites but were
not separately exercised.

## v3.5.1 — 2026-09-20

Backup reference: `backups/pdfmd.py.bak-20260920a`. Found while building a
real document (a CHEM 341 study guide with its own `mainfont:`/
`header-includes:` front matter) end-to-end through `pdfmd`, not a synthetic
test -- both bugs below needed a document that both sets its own font AND
has its own YAML `header-includes` to surface, and only on the actual
direct-to-PDF path (`--stamp-pdf-metadata` is on by default there).

### Fixed

- **A document's own YAML `header-includes:` block silently vanished from
  ANY PDF build**, whenever `--stamp-pdf-metadata` was on (the default) --
  even with no preamble.tex/latex-preamble.tex auto-discovery involved at
  all. Root cause: Pandoc feeds every `--include-in-header` file into the
  same `header-includes` template slot as the document's own metadata, and
  a command-line-set variable silently replaces the metadata one rather than
  merging with it. `document_header_file()`/`document_header_includes()`
  already existed specifically to work around this -- by re-materializing
  the document's own header-includes into a trailing `--include-in-header`
  of pdfmd's own -- but all three call sites only turned it on when
  `preamble_files` was non-empty, not when the (unconditional-by-default)
  PDF-metadata stamp header was the thing about to trigger the bug. Fixed by
  turning the safeguard on whenever EITHER source will add an
  `--include-in-header` (`convert_via_native_bibliography`,
  `convert_one`'s `-t`/`-o` non-PDF-target branch, and its direct-PDF `run()`
  closure -- all three had the same gap). `document_header_includes()`'s own
  docstring updated to say so plainly, since it undersold the trigger before.
- **`-V mainfontfallback=<font>` crashed lualatex outright on the very
  first PDF attempt** for any document that sets its own `mainfont:` --
  before a single glyph was even confirmed missing. Cause: `run(first_font,
  fallback=document_font)` in `convert_one`'s direct-PDF path added Pandoc's
  own `mainfontfallback` mechanism whenever `document_font` was true, which
  is exactly backwards from the rest of the file's own stated design:
  `PREFERRED_FONT`'s docstring, and a comment on the `-t latex` non-PDF
  path right above this one, both already explain that Pandoc's
  `mainfontfallback` is known to crash lualatex in this environment, which
  is supposedly why pdfmd uses its own detect-then-retry-with-a-different-
  mainfont approach instead of ever touching it -- except this one call site
  still did, for exactly the one case (document already has its own
  mainfont) where the safe swap-retry can't apply either, so nothing ever
  covered it. Fixed to `fallback=False` unconditionally: a document that
  wants a fallback font can still set `mainfontfallback:` itself in its own
  front matter (or a linked metadata file), which reaches Pandoc through the
  normal metadata merge, not this `-V` injection, so it doesn't hit the
  crash.

### Verified

Both confirmed via the FULL `pdfmd` pipeline (not just the Pandoc/LaTeX
commands it constructs), per this file's own process note above: a real
document (`mainfont: "STIX Two Text"`, its own `header-includes:` with
`\usepackage{mhchem}` etc.) built clean end-to-end with `--stamp-pdf-metadata`
left at its default (on) -- header-includes survived in the rendered PDF's
own LaTeX, and no lualatex crash on the first pass. Not re-tested against a
document using `mainfont_auto`'s own STIX Two Text -> DejaVu Serif swap-retry
path (that path's `fallback` was already `False` before this fix and is
untouched by it), or against `-r`/`--report` mode's own separate font-
selection code (unaffected -- report mode doesn't call this `run()` closure).

## v3.5.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one used for the
whole of this session's work).

Two more items from later in the same conversation, requested together:
watch mode (a convenience feature, expected to see light use) and CSV/TSV table inclusion (one of the ideas raised
alongside the rejected `\input`-style raw-text inclusion syntax).

### Added

- **`-w`/`--watch`**: recompiles once immediately, then again on each
  later change to the source file's own directory or its `metadata/`
  subfolder (`watch_signature()` -- polls file mtimes, non-recursive,
  same two locations `accessory_directories()` already searches; no new
  dependency). Deliberately a thin wrapper (`run_watch()`) that re-execs
  the whole CLI as a fresh subprocess on each recompile (the original
  argv, minus `-w`/`--watch`) rather than threading a rebuild loop
  through `main()`'s own batch/report/single-file branching --
  disproportionate engineering for a feature expected to see light use.
  Single-file mode only; combining it with `-b`/`-r` is a clear error.
  Signature is re-snapshotted AFTER each recompile, not just before, so
  the compile's own output file (or a `--stamp` write back into the
  source) never falsely re-triggers another immediate recompile.
- **CSV/TSV table inclusion**: a fenced Div with class `csv` (`::: {.csv
  file="data.csv"} :::`) is replaced with an actual table read from that
  file (`CSV_TABLE_LUA_FILTER`, `contains_csv_table()`,
  `csv_table_filter_args()`). Capped at 10 rows/7 columns by default
  (`rows`/`cols` attributes override either, including `all`), per the
  request's own suggested numbers, with a truncated table getting both a
  `WARN` and a note printed directly under the table in the rendered
  output itself. Delimiter auto-detected from the extension
  (`.tsv`/comma otherwise) or set via `delimiter=`; `header="false"` for
  a header-less CSV. A Div, deliberately, not a new raw-text sigil/key
  scanned over the Markdown source before Pandoc sees it -- the same
  `\input`-style inclusion idea raised in the same conversation was
  passed over for exactly the risk this avoids (firing inside a fenced
  code block containing a literal syntax example): Pandoc has already
  told code blocks apart from real content by the time a Lua filter's
  `Div()` callback fires, so this can't happen at the AST level the way
  it could with a raw-text approach. Works for any output format (not
  LaTeX-specific, unlike the table-width filter) -- single-file, batch,
  report mode, and the v3.2.0 soffice PDF-engine bridge all support it.
  `csvtable` added to the `--no-auto`/`pdfmd-options.no-auto` KIND set.
  Builds the table via `pandoc.read()` on a hand-assembled GFM pipe-table
  string rather than constructing `pandoc.Table`'s AST nodes directly --
  reuses Pandoc's own already-correct pipe-table parser instead of this
  filter needing to get every field of `TableHead`/`TableBody`/`Cell`/
  `ColSpec` right by hand, and guarantees the result is indistinguishable
  from a hand-written table, including to `TABLE_WIDTH_LUA_FILTER`
  re-balancing it afterward (ordered to run first, for exactly that
  reason).

### Fixed (found building the CSV feature's own tests, before release)

- **A `.csv` div in a front-matter-less document rendered as literal,
  smart-quoted source text** (`::: {.csv file="small.csv"} :::`) instead
  of being recognized as a Div at all: `resolve_from_format()` bumps a
  front-matter-less document to the `gfm` reader (see its own docstring),
  which -- unlike Pandoc's default `markdown` reader, where it's on by
  default -- does not enable `fenced_divs` at all. Fixed by adding
  `+fenced_divs` onto `gfm` specifically when `contains_csv_table()`
  detects the document needs it, mirroring the existing
  `+definition_lists` pattern right above it.
- **A real Lua runtime error**, once the Div was actually being
  recognized: `"bad argument #2 to 'insert' (number expected, got
  string)"`. Cause: `string.gsub` returns TWO values (the result string,
  and a count of substitutions), and `escape_cell()`'s bare `return
  text:gsub("|", "\\|")` leaked both -- as the LAST argument to a later
  `table.insert(escaped, escape_cell(...))` call, ALL of a Lua function's
  return values get spliced in as separate arguments, so this silently
  became the 3-argument `table.insert(list, pos, value)` form, with the
  escaped string misread as `pos`. Fixed by wrapping the return in
  parens (`return (text:gsub(...))`), which truncates to one value.
- **The table's own last data row rendered as a stray, unparsed
  paragraph** ("| Bob | 25 | Boston |" as literal text) instead of the
  table's actual last row, even after both bugs above were fixed.
  Isolated with a minimal standalone repro: `pandoc.read(text, "gfm")`,
  called from inside a Lua filter, needs an explicit trailing blank line
  to correctly close out a pipe table's final row -- the IDENTICAL text
  read by Pandoc's own CLI (`pandoc -f gfm`) from a file does not need
  this, so it's specifically a `pandoc.read()`-from-a-filter quirk, not a
  general GFM pipe-table requirement. Fixed by appending `"\n\n"` before
  calling `pandoc.read()`.

### Verified

Through the actual `pdfmd` CLI: `-w`/`--watch` compiled a real document
immediately, then correctly recompiled after the source was edited a
second time (confirmed by reading the regenerated PDF's text each time);
`-b`/`-r` combined with `-w` confirmed to raise the documented clear
error. CSV inclusion: a real 2-row CSV with a quoted, comma-containing
field ("New York, NY") rendered correctly as a proper table (confirmed by
reading the PDF's text, not just a successful exit code -- this is
exactly the test that caught both Lua bugs above); a 20-row/9-column CSV
correctly truncated to 10/7 with the WARN and in-document note, then
correctly included in full with `rows=all cols=all`, then correctly
limited to exactly 1 row/2 columns with `rows=1 cols=2`; a `.tsv` file
auto-detected via extension; `--no-auto csvtable` confirmed to drop the
filter and leave the div inert; a `.csv` div naming a nonexistent file
confirmed to `WARN` and leave it empty rather than failing the compile;
report mode confirmed to support CSV inclusion too. Regression: a plain
`.md`, a direct `.tex`, and a direct `.docx` were all re-run after every
change in this round and confirmed unaffected.

---

## v3.4.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one used for the
whole of this session's work -- v3.1.0 through this release were all
developed back-to-back in one sitting, no real-world use of any
intermediate version in between).

The last of the items from the original round started in v3.1.0: citation
engine routing (`citeproc` vs. native `biblatex`/`natbib`), decided
("opt-in via pdfmd-options") in the very first planning round for this
whole session but never assigned to a numbered phase alongside the other
three -- built now as a follow-up once flagged.

### Added

- **`pdfmd-options.citation-engine: natbib`/`biblatex`** routes a LaTeX-
  family PDF target's (or `--to latex`/`beamer`/`context`'s) bibliography
  through Pandoc's own `--natbib`/`--biblatex` flags instead of
  `--citeproc` -- native biber/bibtex processing via the engine's own
  bibliography tooling, using the document's existing `bibliography:`
  field, rather than citations rendered directly into the generated LaTeX
  via a CSL style. Default stays `citeproc` -- a document only needs this
  key at all to opt into something else, per the original decision.
  `frontmatter_citation_engine()` reads it with the same document-then-
  metadata-file precedence as `frontmatter_engine()`; an unknown value
  raises a clear `SystemExit` naming the three valid ones.
- **`convert_via_native_bibliography()`** does the actual work for a PDF
  target, and it is NOT as simple as adding `--natbib`/`--biblatex` next
  to the usual `--pdf-engine=<engine>` invocation. Confirmed empirically,
  before writing any of this: a real document compiled with `pandoc ...
  --pdf-engine=lualatex --natbib` came out with citations completely
  undefined ("Citing ? here.") -- Pandoc's own PDF-making pipeline never
  runs bibtex/biber at all when it calls a LaTeX engine directly this way,
  *regardless* of engine, except `--pdf-engine=latexmk` (latexmk manages
  that itself). Rather than restrict this feature to latexmk only, it
  generates a complete standalone `.tex` via Pandoc first (mirroring
  `convert_one`'s own `TEX_STANDALONE_FORMATS` branch), then hands it to
  v3.1.0's `compile_tex_direct()` -- which already runs exactly the
  rerun-until-stable + automatic bibtex/biber loop this needs, for ANY of
  lualatex/xelatex/pdflatex/latexmk/tectonic, reusing that work directly
  rather than duplicating it.
- For the non-PDF `--to latex`/`beamer`/`context` branch, the equivalent
  substitution (`--natbib`/`--biblatex` instead of `--citeproc`) needed no
  bridge at all -- that branch never runs an engine itself, it just hands
  the caller a `.tex` to compile (and resolve its own bibliography in)
  themselves.
- **`citationengine`** added to the `--no-auto`/`pdfmd-options.no-auto`
  KIND set. Meaningless (silently ignored) for any non-LaTeX target --
  HTML, typst, docx, an office document, or the v3.2.0 soffice PDF-engine
  fallback -- same as e.g. LaTeX-only geometry/monofont defaults already
  are; a document that sets it but resolves to a fallback chain with no
  LaTeX-family engine available at all gets one clear `WARN` and falls
  back to `--citeproc` rather than silently ignoring the setting or
  hard-failing.

### Fixed (found building this feature's own tests, before release)

- **A first version of `convert_via_native_bibliography()` generated its
  intermediate `.tex` into a throwaway `mkdtemp()` scratch directory --
  compiled without any reported error, but left the citation completely
  unresolved** ("Citing ? here.") because bibtex/biber run with
  `cwd=tex_path.parent` (same as `compile_tex_direct()` always has), and a
  `/tmp` scratch directory has no relationship to the document's own
  `refs.bib`. Same underlying class of bug as v3.1.0's `openout_any`
  fix, just from the opposite direction (wrong directory entirely, not a
  security policy blocking the right one). Fixed by generating the
  intermediate `.tex` directly beside `md_path` instead (`mkstemp(dir=
  md_path.parent, ...)`, cleaned up in a `finally` unless `--keep-aux`),
  so a relative `\bibliography{}`/`\addbibresource{}` resolves the same
  way it would for a real, hand-written `.tex` in that directory.
- **The fix above then hit a second, unrelated bug of its own**: the
  first attempt named that temp file with a leading dot
  (`.natbib.pdfmd-nativebib-xxxx.tex`), matching the convention
  `prepared_latex_inputs()` already uses for ITS OWN temp files -- except
  those are only ever Pandoc *input* (a `--metadata-file`/title source),
  never something a LaTeX engine compiles directly as its own jobname.
  Confirmed with a standalone repro (`lualatex .hidden.tex`): a LaTeX
  engine derives its jobname from the input filename up to the FIRST
  period, which is empty for a dotfile, so it silently ignores
  `-output-directory` and tries to write its own `.log` next to the
  source instead -- tripping the exact same `openout_any=p` wall a
  second, unrelated way. Fixed by dropping the leading dot from this
  specific temp filename (`{stem}-pdfmd-nativebib-xxxx.tex`, not
  `.{stem}.pdfmd-nativebib-xxxx.tex`).

### Verified

Through the actual `pdfmd` CLI: a real document with `pdfmd-options:
{citation-engine: natbib}` and one with `citation-engine: biblatex` both
compiled correctly, confirmed by reading the rendered PDF's text -- natbib
produced "Einstein [1905]" (natbib's own bracket-year style), biblatex
produced "Einstein [1]" with a numbered reference list entry, both
visibly different from citeproc's "Einstein (1905)" default, confirming
each engine's own real bibliography backend actually ran (not just that
compilation succeeded). A plain document with no `citation-engine` key set
confirmed unaffected (`--citeproc`, unchanged). `--keep-aux` combined with
`citation-engine: natbib` confirmed to leave the intermediate `.tex` AND
its own `.aux`/`.log` behind for inspection, correctly named and readable.
An unknown `citation-engine` value confirmed to raise a clear error. A
document requesting `natbib` while restricted to `--engine html`
confirmed to print the clear `WARN` and fall back to `--citeproc`
successfully rather than failing outright. Regression: a plain `.md`, a
direct `.tex`, a direct `.docx`, and a crossref-using `--to latex` output
were all re-run after every change in this round and confirmed unaffected.
No leftover files in any test directory after any of the above.

---

## v3.3.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one used for the
whole of this session's work -- v3.1.0 through this release were all
developed back-to-back in one sitting, no real-world use of any
intermediate version in between).

Phase 3 of the round started in v3.1.0 (see that entry for the full list
and the phasing rationale): pandoc-crossref auto-detection, and a math-
aware fix for the table-width Lua filter. Both were among the specific
items suggested (by another AI, per the author) at the start of this round.

### Added

- **pandoc-crossref auto-detection**: a document using `@fig:`/`@eq:`/
  `@tbl:`/`@sec:`/`@lst:` reference syntax, or a `{#fig:...}`-style
  numbered-element attribute, now automatically gets `--filter pandoc-
  crossref` (`contains_crossref()`, `crossref_filter_args()`) -- added
  BEFORE `--citeproc` in the command array in every one of the five
  places pandoc-crossref could apply (both single-file/batch `convert_one`
  PDF paths, the non-PDF `TEX_STANDALONE_FORMATS` branch, the v3.2.0
  soffice bridge, and both of report/book mode's own inline command-
  builders), since pandoc-crossref has to resolve/number references
  before citeproc runs or citeproc treats the leftovers as unresolvable
  bibliography keys. That ordering bug was real and already live before
  this fix: `contains_citations()`'s generic `@key` regex already matches
  `@fig:setup` too (a colon is a valid citation-key character), so a
  crossref-only document was already getting `--citeproc` added --
  confirmed directly (see "Verified" below) that citeproc alone reports
  `citation fig:setup not found`/`citation tbl:results not found` for
  exactly this reason. A document that needs crossref but doesn't have
  the `pandoc-crossref` binary installed gets one clear `WARN` instead of
  silently shipping unresolved references into the rendered output.
  `crossref` added to the `--no-auto`/`pdfmd-options.no-auto` KIND set.
- **Math-aware table-width Lua filter**: `TABLE_WIDTH_LUA_FILTER`'s
  `cell_length()` used to measure a `Math` inline via
  `pandoc.utils.stringify()`, which returns its raw LaTeX SOURCE (e.g.
  `\frac{1.0 \times 10^{-14}}{[OH^-]}`, 34 characters) rather than
  anything close to its typeset width -- exactly the chemistry-table
  scenario (Ksp calculations, uncertainty propagation) flagged in the
  original suggestion. Fixed with `math_overcount()`, which walks each
  cell's content for `Math` nodes and discounts each one's raw source
  length by a flat `MATH_LENGTH_DIVISOR = 3` before it factors into the
  column's natural-width estimate -- a rough heuristic, like every other
  measurement this filter already makes (see its own long Python-side
  comment), not a real LaTeX-width calculation, which nothing at Lua-
  filter time has the means to do.

### Verified

Through the actual `pdfmd` CLI and real Pandoc invocations, not synthetic
assertions: a document mixing `@fig:`/`@tbl:` crossref syntax, an
attribute-defined figure/table, AND a genuine `@einstein` bibliography
citation all resolved correctly in one compile (`pdftotext` showed
"Figure 1"/"Table 1"/"fig. 1"/"tbl. 1" numbering from pandoc-crossref
alongside a properly formatted "Einstein (1905)" citation and reference-
list entry from citeproc -- both filters firing correctly in the same
run, in the right order); `--no-auto crossref` confirmed to drop the
filter from the command line; a plain citation-only document (no crossref
syntax) confirmed to never get the filter added at all; pandoc-crossref
temporarily moved aside (`mv` its real binary, restored immediately after)
to confirm the missing-binary WARN fires, and that citeproc alone then
visibly mishandles the crossref keys exactly as described above -- direct
evidence the bug this fixes was real, not hypothetical. For the table
filter: extracted both the OLD (pre-fix, from `backups/
pdfmd.py.bak-20260919c`) and NEW filter to real `.lua` files and ran both
through actual `pandoc --lua-filter` on the same synthetic math-heavy
table, comparing the emitted LaTeX `\real{...}` column-width fractions
directly -- old gave the math column 19.15% (inflated by its 34-character
raw source) and the genuinely long prose column only 73.23%; new gives
them 7.80%/84.55%, correctly reflecting where the real width need is.
Then compiled the same table through the full `pdfmd` pipeline to a real
PDF (not just Pandoc's intermediate LaTeX) to confirm it still renders
correctly end to end. Regression, per CLAUDE.md's own explicit "test both
directions" instruction from the original 2026-09-16 table-width fix: a
plain short table (old and new both correctly return nil/natural-width,
no `\real{...}` at all) and a deliberately-overflowing table with NO math
in it (old and new produce byte-identical fractions, 7.59%/92.41%,
confirming zero behavior change for any table that never touches a Math
node) were both re-run against both filter versions side by side.

---

## v3.2.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one v3.1.0/v3.1.1
used -- v3.1.0, v3.1.1, and this release were all developed back-to-back
in one sitting, no real-world use of the intermediate versions in between).

Phase 2 of the round started in v3.1.0 (see that entry for the full list
and the phasing rationale). This phase: a soffice/LibreOffice fallback in
the PDF-engine chain, and direct office-document-to-PDF conversion.

### Added

- **soffice as a last-resort PDF-engine fallback** for Markdown/Pandoc
  input: `-e/--engine soffice` (alias `office`/`libreoffice`, numeric
  `14`), or left to the unrestricted chain, where it is tried only after
  every tex/typst/html engine has failed or is missing
  (`convert_via_soffice_bridge()`). Not a real Pandoc `--pdf-engine` --
  Pandoc has no native "write ODT, then shell out to LibreOffice" engine
  -- so this is special-cased directly in `convert_one`'s own fallback
  loop: Pandoc renders an intermediate `.odt`, then headless soffice
  converts that to PDF. Citeproc and a document's own auto-discovered Lua
  filters still apply; LaTeX-only concerns (geometry/mainfont/monofont/
  preamble/table-width filter) don't, since none of them mean anything
  for an ODT target. New `ENGINE_GROUPS["office"]` family keyword for
  `-e office`/a document's `pdf-engine: office` front-matter restriction.
- **Direct office-document-to-PDF conversion**: a `.docx`/`.doc`/`.odt`/
  `.ott`/`.rtf`/`.pptx`/`.ppt`/`.odp`/`.xlsx`/`.xls`/`.ods` input targeting
  PDF converts straight through headless soffice (`convert_office_direct()`
  / `run_soffice_convert()`), no Pandoc involved -- requested directly,
  to stop having to type out `soffice --headless --convert-to pdf <path>`
  by hand. Every soffice invocation (both
  this and the fallback above) gets its own scratch
  `-env:UserInstallation` profile, since concurrent/rapid-fire calls
  (batch mode's `-j`) otherwise collide on the shared default profile's
  lock and fail with "another instance is already running."
- **`resolve_soffice()`/`engine_executable()`**: `soffice` is reachable on
  this machine (and plausibly others) only through an interactive shell
  alias pointing straight at the macOS `.app` bundle's own binary --
  invisible to `which()`/`subprocess`, neither of which consults shell
  aliases. Caught immediately (`--check-dependencies` reported soffice as
  MISS despite it working fine at a real terminal prompt) before this
  round's own feature could even be tested. `engine_executable()` (used
  everywhere `PDF_ENGINES` membership is checked: `installed_engines`,
  `select_engines`, `dependency_report`) checks `soffice`/`libreoffice` on
  PATH, then the standard macOS app-bundle path directly, before
  reporting an engine missing.
- **`officedirect`** added to the `--no-auto`/`pdfmd-options.no-auto` KIND
  set -- see "Known limitation" below for what disabling it actually does
  (not what the equivalent `texdirect` kind does for `.tex`).

### Changed

- **A `.docx`/`.odt` input targeting PDF now converts via soffice by
  default instead of the old Pandoc-mediated route** -- a default
  behavior change for anyone already running `pdfmd report.docx` today
  (flagged per CLAUDE.md's semver rule, same as v3.1.0's `.tex` change).
  Pandoc's own docx/odt reader can produce a PDF too, but loses the
  original document's layout going through Pandoc's AST and LaTeX writer;
  soffice preserves it directly. `.pptx`/`.ppt`/`.xlsx`/`.xls`/`.odp`/etc.
  have no Pandoc reader at all and could never reach a PDF through pdfmd
  before this version -- pure addition for those, not a flip.

### Fixed (found wiring up this phase's own new feature, before release)

- **`pdfmd source.docx` and `pdfmd source.pptx` both crashed outright**
  the first time this phase's own new feature was tested against a real
  office file, well before reaching any of the new soffice code: `main()`
  unconditionally calls `frontmatter_value()`/`metadata_for()` on every
  single-file input looking for a `documentclass`/`class` front-matter
  key, and both read the file as UTF-8 text -- fatal on a zip-based
  binary format. This bug predates this phase entirely (feeding pdfmd a
  `.docx` would have hit the exact same crash before any of this round's
  changes existed, just apparently never actually tried); fixed here
  since it sits directly in the path of the feature this phase adds, not
  filed as a separate known-issue the way v3.1.0 did for the unrelated
  `resolve_from_format` bug. Fixed with a new early dispatch branch in
  `main()` (mirroring the existing `.qmd` special case) that routes an
  `OFFICE_INPUT_EXTENSIONS` file straight to `convert_one` without any of
  that Markdown-oriented front-matter/preamble discovery.
- **The same crash recurred one level deeper**: `effective_no_auto()` and
  `resolve_engines()` both call `frontmatter_pdfmd_options()`
  unconditionally too (looking for a document's own `no-auto`/`pdf-engine`
  front-matter settings), which has the identical text-read-on-binary-
  file problem -- reached even after the `main()` fix above, and also
  reachable for a `.tex` file (though rarely hit in practice there, since
  most `.tex` input now goes through v3.1.0's own direct-compile branch
  first). Fixed at the source instead of patching each caller:
  `frontmatter_pdfmd_options()` now returns `{}` immediately for anything
  in `OFFICE_INPUT_EXTENSIONS`, without attempting to read it.
- **`--no-auto officedirect` (and a non-PDF `--to`, or an explicit
  `--from`) on an office document crashed too**, one call further into
  `convert_one`'s generic Pandoc-oriented machinery (`has_mainfont`,
  `contains_citations`, `find_lua_filters`, `promote_bare_title`, ... --
  all assume text input). Unlike `.tex`'s `texdirect`, there is no
  supported way to make this route actually work without auditing every
  one of those helpers for binary-safety, judged out of scope for this
  phase (see "Known limitation" below) -- so instead of leaving a
  flag that reliably crashes a few calls later, these combinations now
  raise one clear `SystemExit` explaining that only direct PDF conversion
  is supported for an office document in this version.

### Verified

Through the actual `pdfmd` CLI: a real `.docx` and a real `.pptx`
(generated via `pandoc source.md -o source.docx`/`-t pptx`, then fed back
into `pdfmd`) both converted correctly, confirmed by extracting and
reading the rendered PDF's text, not just checking for a successful exit
code -- `.pptx` specifically confirms a format Pandoc cannot read at all
now reaches a PDF; `--engine soffice` forced directly on a `.md` source
(the fallback-bridge path, not the direct-input path) also verified by
reading its rendered text; `--no-auto officedirect`, a non-PDF `--to` on
an office file, and an explicit `--from` all confirmed to fail with the
new clear error instead of a traceback; `--check-dependencies` confirmed
`soffice` now reports OK via `engine_executable()` instead of MISS; and,
for regression, a plain `.md` document (still routes through Pandoc with
`--pdf-engine=lualatex`, unchanged) and a `.tex` document (still uses
v3.1.0's direct-compile path, unchanged) -- both re-run after every
change in this round, confirming the new per-engine-loop `soffice`
branch and the two office-input branches don't touch either existing
path. No leftover scratch directories after any of the above.

### Known limitation

Unlike `.tex`'s `texdirect`, disabling `officedirect` does **not** route
a `.docx`/`.odt` back through the old Pandoc-mediated path -- it raises a
clear error instead (see "Fixed" above for why: that route crashes deeper
in, in code this phase didn't audit for binary-safety, and arguably isn't
worth making work at all, since it would only produce a worse-formatted
PDF than direct soffice conversion already does). If a genuine need for
Pandoc-mediated `.docx`/`.odt` conversion ever comes up, that would be its
own follow-up, auditing `has_mainfont`/`contains_citations`/
`find_lua_filters`/`promote_bare_title`/etc. for binary input rather than
just the two front-matter functions this phase fixed.

---

## v3.1.1 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919c` (same one v3.1.0 used --
developed back-to-back in the same sitting, no real-world use of v3.1.0 in
between).

### Fixed

- **The "known issue" flagged in v3.1.0's own changelog entry, fixed the
  same day it was found**: `resolve_from_format()` decided the Pandoc
  reader purely from front-matter/metadata-file presence, never from the
  file's own extension, so any non-Markdown Pandoc input (`.tex`, `.html`,
  `.rst`, ...) with no YAML front matter of its own was silently read as
  `gfm` instead of Pandoc inferring the right reader from its extension --
  live for a `.tex` file specifically via `--to` a non-PDF target or
  `--no-auto texdirect` (the direct-.tex-compile path added in v3.1.0
  doesn't go through this function at all, so most `.tex` input no longer
  hits it in practice, but both escape hatches still do). Fixed by
  returning early (no override) for anything other than a real
  `.md`/`.markdown` suffix -- the gfm heuristic is specifically about
  ordinary GitHub-Flavored-Markdown authoring conventions and was never
  meant to apply to another format's own file. Pre-existing bug, unrelated
  to v3.1.0's own changes; not a default flip for any document this was
  ever working correctly for (a `.md`/`.markdown` file's behavior is
  unchanged), hence a patch bump rather than another major one.

---

## v3.1.0 — 2026-09-19

Backup taken before this round: `backups/pdfmd.py.bak-20260919c`.

**Versioning note (the author's call, this session only):** this entry and the
two after it (v3.1.1, v3.2.0) were originally released as v4.0.0, v4.0.1,
and v5.0.0 -- each bump to the leading digit exactly per the semver rule
above (a default behavior change), since a real `.tex`/`.docx` input
changing how it's processed by default is precisely what that rule calls
major. The author's own judgment, after the fact: none of the three actually
break the script's core functionality (the Markdown/Pandoc pipeline this
script exists for is untouched by all three), so the leading digit stays
capped at 3 for this round and these three are renumbered as minor/patch
bumps instead. The semver rule itself is unchanged for future entries --
this is a one-time relabeling of this round only, not a standing
exception. Any "flagged here per CLAUDE.md's own semver rule"-type
language below describing these as major bumps is accordingly stale;
left as-is/see this note rather than rewritten line-by-line.

Phase 1 of a larger round of changes the author asked for (direct .tex compilation
with rerun detection and tectonic-style cleanup; a soffice/LibreOffice
fallback and direct office-to-PDF conversion; pandoc-crossref auto-
detection and a math-aware table-width filter; watch mode) -- scoped and
phased per the author's own call, one backup+changelog+verify cycle per phase
rather than one large patch, specifically so a regression in one phase
doesn't get tangled up with an unrelated one. This is phase 1 only; the
rest follow in later versions.

### Changed

- **A real `.tex` input targeting PDF is now compiled directly with a
  LaTeX engine, instead of being handed to Pandoc first** -- a default
  behavior change for every existing `pdfmd notes.tex` invocation, flagged
  here per CLAUDE.md's own semver rule even though raw `.tex` input is a
  much rarer case than the Markdown pipeline this script exists for.
  Previously, `.tex` input was read by Pandoc's own LaTeX reader and
  regenerated through Pandoc's LaTeX writer before an engine ever saw it --
  a lossy round-trip for exactly the kind of hand-written raw LaTeX (chemfig,
  tikz, custom macros) a `.tex` file is likely to contain on purpose. The
  new path (`compile_tex_direct()`, `run_tex_engine()`) skips Pandoc
  entirely: the `-e/--engine` fallback chain still applies, restricted to
  its LaTeX-family members (lualatex, xelatex, pdflatex, latexmk, tectonic
  -- not context, whose CLI/markup are unrelated to the other five).
  `--no-auto texdirect`, or an explicit `--from` other than `latex`/`tex`,
  opts back into the old Pandoc-mediated route for a document that
  specifically needs pdfmd's own font/margin/metadata/stamp injection
  applied to raw LaTeX; a non-PDF `--to` target was never affected (Pandoc
  is still the only way to get `.tex` into another format).

### Added

- **Automatic multi-pass compilation**: lualatex/xelatex/pdflatex are
  rerun (up to `MAX_TEX_DIRECT_PASSES` = 5 times) whenever the engine's own
  `.log` asks for another pass -- the same "Rerun to get..."/"Label(s) may
  have changed" signal latexmk itself watches for (`tex_wants_rerun()`),
  covering both a forward cross-reference (verified against a real
  `\ref` used before its `\label`: correctly took 2 passes, 1 on a
  second run where the label was already resolved) and, more generally,
  anything else that only settles after a previous pass's output feeds
  back in (this is also what would make a chemfig diagram's arrow
  angles/positions converge, per the author's own question when asking for this
  feature -- not separately tested here, no such diagram on hand, but the
  mechanism is the same generic log-driven rerun loop, not anything
  specific to bibliographies).
- **Automatic bibtex/biber**: `tex_bibliography_tool()` detects
  `\addbibresource{`/`\usepackage{biblatex}` (biber) vs. bare
  `\bibliography{` (bibtex/natbib) in the source and runs the matching
  tool once between engine passes, no flag needed. latexmk/tectonic
  already manage this (and their own reruns) internally and are each
  given a single wrapped call instead of pdfmd's own loop.
- **Scratch-directory cleanup, on by default, mimicking tectonic**: every
  engine pass writes into a fresh `-output-directory`/`-o` scratch
  directory; only the finished PDF is copied back out, and the scratch
  directory is deleted (even on failure -- verified no leftover
  `pdfmd-tex-*` directories after a synthetic 3-engine failure chain).
  The source directory is never touched, so a pre-existing `.aux`/`.log`
  from a previous manual/`--keep-aux` compile is left alone rather than
  swept up -- verified directly (a stale `.aux`/`.log`/`.out` set from an
  earlier `--keep-aux` run survived an unrelated later default-mode
  compile in the same directory untouched).
- **`--keep-aux`** turns the above off: compiles in place (no
  `-output-directory` at all) and leaves every `.aux`/`.log`/`.out`/etc.
  beside the source, for inspecting a failing or suspicious compile's own
  `.log` by hand -- restores the exact pre-v3.1.0-for-.tex behavior.
- **`texdirect`** added to the `--no-auto`/`pdfmd-options.no-auto` KIND set.

### Fixed (caught during this round's own verification, before release)

- **bibtex silently failed to resolve citations** (`Citing [?]` instead of
  `Citing [Einstein, 1905]`) the first time this was tested against a real
  `natbib`/`\bibliography{}` document -- exactly the kind of thing CLAUDE.md
  warns a synthetic/isolated check won't catch; this was only caught by
  reading the actual rendered PDF's text, not just checking bibtex's exit
  code or trusting a clean compile log. Cause: bibtex was run from the
  source directory but pointed at a target path inside the scratch
  `-output-directory`, which MacTeX's default `openout_any=p` (paranoid)
  security policy silently refuses to write outside of -- bibtex printed
  its own "Not writing to ... (openout_any = p; no extended check)"
  warning and returned nonzero, but the compile still "succeeded" with an
  unresolved citation. Fixed by running bibtex with `cwd` set to the
  scratch directory itself (satisfying the policy trivially) and
  `BIBINPUTS` pointing back at the source directory so it can still find
  the `.bib` file (bibtex has no `--input-directory` flag the way biber
  does). Re-verified against the same document: citation now resolves
  correctly. biber was unaffected (its own `--input-directory` sidesteps
  this) and needed no fix.
- **A failed direct-.tex compile's one-line reason was silently truncated
  mid-word** (e.g. "ed, no output PDF file produced!" instead of "...Fatal
  error occurred, no output PDF file produced!") -- caught the same way,
  by reading an actual failure's printed reason rather than trusting that
  a WARN line was produced at all. Two compounding causes: (1) `-file-
  line-error` (added for its own sake, to name the offending source line)
  changes LaTeX's error format from a leading `! ...` to `path:line:
  ...`, which the existing `engine_failure_reason()` helper (built only
  ever seeing Pandoc's own unwrapped stderr) doesn't recognize; (2)
  LaTeX's `.log` hard-wraps every physical line at `max_print_line`
  (confirmed 79 on this machine via `kpsewhich -var-value=max_print_line`,
  observed wrapping in practice at 80) with no word-boundary awareness,
  splitting exactly the tail-end summary line mid-word. Fixed with two new,
  direct-.tex-specific helpers instead of changing the shared
  `engine_failure_reason()` (which still works correctly for its original
  Pandoc-stderr callers and had no reason to change): `tex_log_dewrap()`
  rejoins physical log lines wrapped at/past that width before anything
  else inspects the text, and `tex_log_failure_reason()` prefers a `!
  ...` line, then a `path:line: ...` line (skipping the generic "Fatal
  error occurred..." trailer every halted run ends with, which names no
  actual cause), then falls back to the last non-blank line. Re-verified
  against the same synthetic `\thisisnotarealcommand` failure: reason now
  reads exactly "Undefined control sequence."
- **`shutil.copy2` crashed with `SameFileError`** under `--keep-aux` when
  no `-o`/`--out` redirected the output elsewhere: the engine already
  writes its PDF straight to the same path pdfmd would otherwise "copy"
  it to, since `--keep-aux` uses no `-output-directory` at all. Fixed by
  skipping the copy when the produced file and the target output already
  resolve to the same path.

### Verified

Per CLAUDE.md's "verify through the full pipeline, not a synthetic test"
rule -- all through the actual `pdfmd` CLI, not by hand-invoking Pandoc/
LaTeX/bibtex directly: a real forward-cross-reference document (2-pass
rerun, then 1-pass on a stable second compile); a `natbib`/bibtex
document and a `biblatex`/biber document (both citations confirmed
resolved by reading the rendered PDF's text, not just the exit code); a
deliberately broken document exhausting all five direct-compile engines
in order with correct family-skip behavior (lualatex/xelatex/pdflatex
fail together as expected, latexmk correctly skipped as sharing pdflatex's
pdftex family, tectonic correctly skipped as sharing xelatex's xetex
family) and no leftover scratch directories afterward; `latexmk` and
`tectonic` each run directly as the sole engine; `--keep-aux` (aux files
left in place, correct PDF) immediately followed by a default-mode compile
in the same directory (stale aux files from the `--keep-aux` run left
untouched, confirming cleanup only ever touches pdfmd's own scratch
directory); a `.tex` input targeting `--to html` and a `.tex` input with
`--no-auto texdirect` (both correctly still routed through Pandoc, per
this version's own documented escape hatches); and, for regression, a
plain `.md` document with a table and a bare title (identical Pandoc
command line and AUTO decisions as before this round, confirming the new
`.tex`-only branch -- gated strictly on file extension -- doesn't touch
the Markdown/Pandoc path at all).

### Known issue, found during this verification, not fixed here

`resolve_from_format()` (pre-existing, untouched by this round) decides
the Pandoc reader purely from front-matter/metadata-file presence, never
from the file's own extension -- so a `.tex` file routed through the old
Pandoc-mediated path (via `--to html`, or `--no-auto texdirect`) with no
YAML front matter of its own is read as `gfm`, not `latex`, unless
`--from` is given explicitly. Surfaced by this round's own edge-case
testing (`--to html`/`--no-auto texdirect` on a `.tex` file are both rare
paths that this version newly exercises more than before), not something
this round introduced or is in scope to fix -- noted here so it isn't
lost, in case a `.tex`-to-non-PDF or `--no-auto texdirect` user hits it.

---

## v3.0.0 — 2026-09-19

Backup reference: `backups/pdfmd.py.bak-20260919b` (taken before v2.6.0 AND
this release both -- they were developed back-to-back in one sitting with
no real-world use of v2.6.0 in between, so there is no clean pre-v3.0.0-
only snapshot; rolling back to this one undoes both releases together).

### Added

- **`--stamp-pdf-metadata` embeds the same package/pdfmd version info
  directly into the rendered PDF's own Info dictionary**, as two custom
  keys (`PdfmdVersions`, `PdfmdBuildDate`) -- prompted by the author asking
  whether pdfmd's PDFs carry any metadata at all (checked with
  `pdfinfo`/`exiftool` against a real report: yes -- Title/Author from
  document metadata, Creator "LaTeX via pandoc", Producer the engine's own
  signature, Subject/Keywords empty by default) and whether pdfmd could
  insert its own version there as well. Implemented as a second, additive
  `\hypersetup{pdfinfo={...}}` call -- merges with Pandoc's own rather
  than overwriting pdftitle/pdfauthor/etc., so a document's real metadata
  is never touched. Invisible on the rendered page and in a normal
  "Document Properties" panel; readable with `exiftool`/`pdfinfo -meta`.
  LaTeX-family engines only -- a non-LaTeX PDF engine (weasyprint, typst,
  ...) has no equivalent mechanism this reaches, so it's silently skipped
  there. Verified against a real compile with `exiftool`: both custom
  keys present, Author/Title/Creator/Producer all unchanged.
- **Independent of `enabled`/the .md BUILD NOTES stamp**, per the author's direct
  follow-up asking for the .md and PDF stamps to be controllable
  separately (e.g. PDF on, .md off): `options['pdf_metadata']` is its own switch, checked on
  its own at each call site, not gated behind `options['enabled']` the
  way it was in the first cut of this feature (a real bug caught before
  release -- `--stamp-pdf-metadata` alone did nothing without `--stamp`
  too, verified and fixed). `--stamp` with PDF metadata off,
  `--stamp-pdf-metadata`/`pdf_metadata: true` with the .md stamp off, or
  both together, are all valid combinations now, confirmed with a 4-way
  test matrix.

### Changed

- **`pdf_metadata` now defaults to ON, unlike `enabled`** -- a deliberate
  default flip, the author's own call (the PDF stamp is harmless compared
  with the .md one): embedding two invisible,
  additive Info-dictionary keys has no visible effect on the rendered
  page or a normal "Document Properties" panel, unlike `enabled` (which
  edits the visible .md source and rightly stays off until asked). This
  means **every LaTeX-engine PDF pdfmd produces, across every pipeline
  that uses this script**, now carries a `PdfmdVersions`/`PdfmdBuildDate`
  Info entry unless `--no-stamp-pdf-metadata`/`pdfmd-options.stamp.
  pdf_metadata: false` turns it off -- flagged here explicitly because a
  default flip is exactly the kind of change CLAUDE.md's own semver
  section calls out as major, even though `pdf_metadata` itself only
  existed for a few hours before this flip and nothing has depended on
  the old default yet.

### Fixed

- **`pdf_metadata_snippet`'s `\ifdefined\hypersetup` guard never actually
  fired for a document with no LaTeX-loaded package of its own** (i.e.
  the exact bare-document case the new default-on behavior now hits
  constantly): generating the real `.tex` Pandoc produces showed
  `--include-in-header` content lands in the preamble BEFORE
  `\usepackage{bookmark}` (which is what actually loads hyperref
  indirectly -- there is no literal `\usepackage{hyperref}` line to be
  after), so `\hypersetup` was undefined at the point the guard checked
  it, and the whole block silently no-opped. It happened to work in
  every nulabreport-based test only because nulabreport.sty's own
  `--include-in-header`'d preamble loads hyperref itself, earlier in the
  same `-H` file list. Fixed by wrapping the whole call in
  `\AtBeginDocument{...}`, which defers it until every package is loaded
  regardless of `--include-in-header` ordering; the `\ifdefined` guard
  stays as cheap extra insurance, no longer load-bearing. Re-verified
  against the original failing bare-document case, all four
  enabled/pdf_metadata combinations, and a real nulabreport report/book
  build.
- **`--stamp-mode history`'s v2.6.0 redesign (see below) also gained a
  helper refactor here**: `gather_stamp_texts()`/`stamp_scope_matches()`
  extracted out of `stamp_after_success()` so the new pre-compile
  PDF-metadata path and the existing post-compile .md-stamp path share
  one implementation instead of two copies that could drift.

## v2.6.0 — 2026-09-19

Backup taken before this round: `backups/pdfmd.py.bak-20260919b`.

### Changed

- **`--stamp-mode history` restructured into a "Compile History:" trailer,
  same day it shipped.** The original v2.5.0 shape kept every past stamp
  line stacked at the TOP of the block, so each successive compile pushed
  a report's own hand-written BUILD NOTES (compound-library additions,
  values to recheck, etc.) one more line further from "BUILD NOTES" --
  clutter the author flagged immediately on trying it for real. `history` mode
  now keeps exactly ONE live stamp line at the top (so the latest compile
  is still always the first thing read) and demotes whatever was
  previously there into a `Compile History:` list of `  - ` bullets at the
  END of the comment, just before its closing `===...-->`,
  newest-demoted-first -- hand-written notes in between stay exactly where
  they are, at a fixed position, regardless of how many compiles happen.
  `update_build_notes()` now returns `(text, warning)`; `replace` mode
  never touches an existing history list (by design -- that log is meant
  to survive a mode switch), but now prints a WARN via `apply_stamp()`
  when one exists and has entries, since silently freezing a history a
  document was actively building was flagged as a real footgun by the author:
  switching to `replace` should only replace the last entry and leave
  every earlier entry below it untouched.
  Verified against a synthetic multi-step history-then-replace sequence
  and a real copy of LR1's report.md.
- **`~/dev/tex/nulabreport/metadata.yaml`** (the shared
  file symlinked into every course folder) now sets
  `pdfmd-options: stamp: {packages: [nulabreport], mode: history}`, so
  every report that finds it gets stamped automatically -- no per-report
  `--stamp` needed. `pdf-engine: tex` (already there) is untouched; `stamp:`
  was added as a sibling key under the same `pdfmd-options:` mapping.

## v2.5.0 — 2026-09-19

Backup taken before this round: `backups/pdfmd.py.bak-20260919a`.

### Added

- **New `--stamp` (and `pdfmd-options: stamp:`) feature automates a
  build-provenance note the author was already keeping by hand.** Real reports
  (LR1, LR3) already end in a `<!-- ===... BUILD NOTES ...=== -->` HTML
  comment -- invisible in the rendered PDF, visible in the .md source --
  whose one load-bearing line reads "Compiled with nulabreport vX.Y.Z,
  pdfmd vA.B.C", updated by hand after each real compile, sometimes with
  other freeform notes (compound-library additions, TODOs, values to
  recheck) written around it. `--stamp` automates just that one line --
  now with a timestamp appended -- and never touches anything else already
  in the block:
  - `resolve_stamp_options()`/`frontmatter_stamp()` cascade a document's
    own `pdfmd-options.stamp`, then each linked metadata file's, same
    precedence as `pdf-engine` (see `frontmatter_engine`) -- a shared
    `metadata.yaml` can turn stamping on for every report that finds it.
    CLI flags (`--stamp`/`--no-stamp`, `--stamp-mode`, `--stamp-packages`,
    `--stamp-scope`, `--stamp-output`/`--no-stamp-output`) win field by
    field on top of that.
  - `--stamp-mode replace` (default) overwrites the previous stamp line in
    place; `history` never overwrites -- each run inserts a new line above
    the previous ones, directly under "BUILD NOTES", so the newest entry
    always reads first (the author's spec: newest entry directly below
    BUILD NOTES).
  - `--stamp-packages nulabreport` includes a package's version via
    `kpsewhich <name>.sty` + that file's own `\ProvidesPackage` line --
    matching `nulabreport.sty`'s real `\ProvidesPackage{nulabreport}
    [2026/09/18 v1.14.7 ...]` line exactly. A named package is silently
    left out of the line if this document doesn't actually `\usepackage`
    it, or no version could be determined -- never a hard failure.
  - `--stamp-scope` (`always`/`report`/`standalone`) answers the author's own
    follow-up question: a document can ask to be stamped only when
    compiled as a whole report/book, not on its own, or the reverse.
    `--stamp-output` names the rendered file even outside report mode; a
    report/book chapter's stamp always names the shared output ("Compiled
    as part of `book.pdf` with ..."), regardless of this flag, and gets
    written into every chapter file that's part of that report, not just
    the first.
  - `BUILD_NOTES_RE`/`update_build_notes()` locate the comment anywhere in
    the file (not assumed to be the last line -- a report chapter's own
    comment can end up mid-file once concatenated with others, per the author's
    own concern), and only ever touch the single recognized stamp line
    inside it, identified by pattern (a line starting "Compiled" that
    mentions "pdfmd vX") rather than by any new, differently-styled marker
    -- so it reads as a natural extension of what the author already writes by
    hand, not a second, redundant-looking line next to it. Verified
    against real copies of LR1's and LR3's `report.md` (the latter's
    multi-paragraph hand-written notes below the stamp line came back
    byte-for-byte unchanged, confirmed by diff) and a from-scratch
    document with no BUILD NOTES block at all.

## v2.4.0 — 2026-09-18

Backup taken before this round: `backups/pdfmd.py.bak-20260918a`.

### Added

- **Auto-discovered metadata YAML, preambles, and Lua filters can now live in
  a `metadata/` subfolder instead of directly beside the document.** Raised
  by the author: a report's own top-level folder currently holds nothing but a
  symlinked `metadata.yaml`/`nulab.bib`/`nulabreport.lua`, a copied-and-edited
  `preamble.tex`, and sometimes a symlinked `chemicals.tex` -- entirely
  because pdfmd only ever looked beside the document, which leaves a folder
  that's supposed to hold just a report's `.md` source and rendered PDF
  cluttered with files an outsider has no reason to recognize. Every
  filename-based auto-discovery function (`find_metadata`'s YAML glob,
  `preamble_candidates`'s `.tex` glob, `find_lua_filters`, and `-y`'s bare-name
  `resolve_yaml` lookup) now also searches a `metadata/` subdirectory beside
  the document, via a new shared `accessory_directories()` helper -- nothing
  needs to opt in, and a pipeline with no `metadata/` folder sees no change
  at all. Pandoc's own working directory for a render already follows
  wherever the first discovered metadata file lives (`pandoc_cwd =
  metadata_files[0].parent`, pre-existing, originally there for an explicit
  `-y` pointing at a shared directory elsewhere) -- so once `metadata.yaml`
  moves into `metadata/`, a preamble's raw LaTeX `\input{chemicals}` and a
  `metadata.yaml`'s own relative `bibliography:`/`csl:` keys keep resolving
  for free, as long as `chemicals.tex`/`nulab.bib`/`nu-labreport.csl` move
  into that same `metadata/` folder alongside it.
- **New `resource_path_option()` guards a document's own relative paths
  (e.g. an image) against that same `pandoc_cwd` shift.** Before this
  change, `pandoc_cwd` always happened to equal the document's own
  directory in every pipeline that kept its metadata beside the document --
  so nothing exercised the gap. The moment metadata moves into
  `metadata/`, `pandoc_cwd` moves with it, and a document's own relative
  image path would otherwise silently resolve against `metadata/` instead
  of the document's actual directory. pdfmd now adds `--resource-path
  <document dir>:.` to the Pandoc command whenever `pandoc_cwd` differs
  from the document's own directory -- a no-op, with zero command-line
  change, for every pipeline where the two already coincide.

## v2.3.0 — 2026-09-17

Backup taken before this round: `backups/pdfmd.py.bak-20260917a`.

### Added

- **Every failed PDF-engine attempt now prints a one-line reason, with no
  flag needed** — found debugging a `testref` (SOC203) reference sheet
  whose `\begin{multicols}{2}...\end{multicols}` two-column function index
  failed on every engine (missing `\usepackage{multicol}`, then a second,
  subtler bug: Pandoc's Markdown reader treats a bare `\begin{ENV}...
  \end{ENV}` paragraph as one opaque raw-LaTeX block and stops parsing
  Markdown inside it, so the index's backtick code spans and underscores
  were passed to LaTeX literally instead of becoming `\texttt{}`). Bare
  `pdfmd file.md` gave only `WARN ... {engine} failed; trying {next}...`
  with no hint why — finding the actual cause meant already guessing which
  engine to force via `--engine {name} --verbose` to see the raw LaTeX log.
  New `engine_failure_reason()` pulls the single most useful line out of a
  failed attempt's stderr (a LaTeX fatal error's own `!`-prefixed line if
  there is one, else a `Error`/`pandoc:`-prefixed line, else the last
  non-empty line) and a new shared `report_engine_failure()` prints it on
  EVERY `WARN`, including — new — the final engine's failure, which
  previously printed nothing at all beyond the eventual bare `FAIL <path>`.
  Both the single-file/batch engine loop (`convert_one`) and report/book
  mode's separate inline loop now go through this one function instead of
  each having their own bare `WARN` print.
- **New `--debug` flag** for when the one-line reason above still isn't
  enough (several stacked LaTeX errors, or a Pandoc-level error with no
  leading `!`/`Error` line at all): dumps the failed engine's FULL captured
  stderr inline, at the point of failure, for every engine that fails —
  even one a later engine in the fallback chain goes on to recover from —
  instead of only the final one. Implies `--verbose`. Threaded through
  every `convert_one` call site, including the positional
  `ProcessPoolExecutor.submit` call in parallel batch mode (`-j`), and
  through report/book mode's own inline engine loop via `args.debug`
  directly (that loop was never refactored into `convert_one`).
- **A pointer comment for future editors** (human or AI) was added right
  above `PDFMD_VERSION` in `pdfmd.py` itself, naming this project's
  `CLAUDE.md` and its backup-before-editing / changelog-in-the-same-edit
  requirement explicitly — found worth adding after noticing an editor can
  reach `pdfmd.py` directly (e.g. asked to fix a specific compile failure)
  without ever having opened this directory's `CLAUDE.md` first.

### Verified

- Reran the `testref` reference sheet that surfaced this through the real
  fallback chain (no `--engine` override): `lualatex` still fails for the
  pre-existing, unrelated `mainfontfallback`/lualatex crash documented at
  `PREFERRED_FONT`'s own comment, and the new `WARN` line surfaced ITS
  reason too (previously silent), before `xelatex` picked it up and
  produced a correct PDF.
- A synthetic deliberately-broken `\begin{multicols}` document confirmed:
  (1) no flags — the undefined-environment reason shows on the very first
  `WARN`, and a NEW final-failure `WARN` (with the same reason plus a
  `--verbose`/`--debug` hint) appears right before `FAIL`, where past
  versions printed nothing between the last engine's silent failure and
  `FAIL`; (2) `--debug` with an unrestricted chain — every attempted
  engine's full stderr prints inline as each one fails in turn, not only
  the last.
- A normal, successful compile (a working document, default flags) was
  confirmed unchanged: no new output at all, since `report_engine_failure`
  is only ever reached on a non-zero return code.

## v2.2.0 — 2026-09-17

Backup taken before this round: `~/dev/tex/nulabreport/_superseded/
pdfmd.py.pre-standalonetex.20260917-131249.bak`.

### Fixed

- **`--to latex`/`beamer`/`context` (or `-o file.tex`) produced a bare
  Pandoc-LaTeX fragment, not a document that compiles on its own** — the author hit
  this running `pdfmd -o test.tex` on a lab report: the `.tex` had no
  `\documentclass`/`\begin{document}`/`\end{document}`, no `--standalone`,
  and (since preamble/header-includes discovery was gated on `target_format
  == "pdf"`) none of the project's own `preamble.tex` (its `nulabreport`
  package load, course/instructor front-matter, `\input{chemicals}`) or the
  margin/mainfont/monofont defaults a PDF render of the same source would
  have gotten — none of it compiled. Fixed by giving `latex`/`beamer`/
  `context` targets (new `TEX_STANDALONE_FORMATS`) the same preamble/
  header-includes/margin/monofont/mainfont treatment as the PDF-via-
  LaTeX-engine path, plus `--standalone`, in `convert_one` (single-file and
  batch modes) and the report/book mode's non-PDF branch alike; a new
  `--no-auto standalone` (also settable via `pdfmd-options: no-auto:
  [standalone]`) turns just the `--standalone` addition back off, for a
  `.tex` that's deliberately meant to be `\input`/`\include`d into another
  document rather than compiled on its own. One thing this deliberately
  does NOT reproduce: the PDF path's missing-glyph detect-and-retry between
  `STIX Two Text` and `DejaVu Serif` needs an actual compile to check
  against, which nothing here performs, so the emitted document keeps
  whichever font it tried first; a first attempt at closing that gap with
  Pandoc's own `mainfontfallback` variable was reverted after it reproduced
  PREFERRED_FONT's already-documented crash under lualatex in this
  environment (confirmed with a real `lualatex` compile of the generated
  `.tex` — `luaotfload | resolve : sequence of 3 lookups yielded nothing
  appropriate` immediately followed by a fatal `attempt to index a nil
  value` in `luaotfload-fallback.lua`), so it isn't attempted at all here,
  same as the PDF path's own reasoning for avoiding it. Verified end to end
  on the report that surfaced this: the generated `.tex` now compiles
  cleanly with `lualatex` (two passes, for cross-references) to a PDF whose
  `pdftotext` output is byte-identical to, and whose page count (39) matches,
  a PDF made by running `pdfmd` directly on the same Markdown source.

## v2.1.1 — 2026-09-17

Backup taken before this round: `~/dev/tex/nulabreport/_superseded/
pdfmd.py.pre-enginequiet.20260917-001806.bak`.

### Fixed

- **v2.1.0's `AUTO ENGINE  <path>: chain` line printed unconditionally,
  every run, regardless of `-v`/`--verbose`** — the one auto-discovery
  message in the whole script that bypassed the established
  note()/flush_summary() convention (every other "AUTO ..." line is either
  shown in full under `--verbose` or folded into one `AUTO: KINDS. Use
  --verbose to see in full` summary otherwise). Caught immediately on real
  use (the author, building a report normally with no `-v`). Fixed two ways at
  once: `resolve_engines()` takes a new `verbose: bool = False` parameter
  and only prints when it's true (all four call sites in `main()` now pass
  `args.verbose` through); and the label itself changed from `AUTO ENGINE`
  to plain `ENGINE`, since as of v2.1.0 this restriction can come from
  either a document's own front matter (an explicit per-document request,
  not really "auto") or its linked metadata file (genuinely a default,
  closer to "auto") -- one shared "AUTO" prefix no longer described both
  sources accurately. No silent summary line was added for the
  non-verbose case (unlike the note()-based messages) -- this one is
  either fully shown or fully hidden, since the caller already knows
  whether it asked for a restriction at all.

---

## v2.1.0 — 2026-09-17

Backup taken before this round: `~/dev/tex/nulabreport/_superseded/
pdfmd.py.pre-unknownskey.20260916-235642.bak` (before the DOCUMENT_LATEX_KEYS
change) and `pdfmd.py.pre-metadataengine.20260917-000621.bak` (before the
engine-resolution change) — kept in the `nulabreport` package's own
`_superseded/` since that's the session that prompted both, not this
project's own `backups/`.

### Added

- **`pdf-engine`/`engine` (and `pdfmd-options` generally, for that one key)
  now also falls through to a document's linked `--metadata-file` YAML, not
  only the document's own front matter.** Found while verifying a
  `nulabreport` course's shared `metadata.yaml` (symlinked into every course
  folder) after the author added `pdfmd-options:\n  pdf-engine: tex` to it, expecting
  every report in that course to restrict fallback to the LaTeX family by
  default: `resolve_engines()`/`frontmatter_engine()` only ever inspected the
  source `.md`'s own front matter, so the setting was silently inert — no
  `AUTO ENGINE` line, and the ordinary unrestricted fallback ran regardless.
  Confirmed with `-v`: the same `pdf-engine: tex` line in the report's own
  front matter DID restrict the chain (`lualatex -> xelatex -> pdflatex ->
  latexmk -> tectonic`, no html/typst); the identical line in `metadata.yaml`
  alone did nothing. Fixed by teaching `frontmatter_engine()` a second,
  lower-priority source: after checking the document's own `pdfmd-options`
  and bare top-level `pdf-engine`/`engine`, it now checks each of the
  document's already-resolved `metadata_files` in turn (new
  `metadata_file_yaml()` — a metadata file has no `---`/`...` fence to find
  first, unlike a document's front matter; the whole file already IS the
  mapping). `resolve_engines()` takes a new optional `metadata_files`
  parameter to carry this through; all four call sites in `main()`
  (single-file, batch serial, batch parallel via `ProcessPoolExecutor`, and
  report/book mode) now compute or reorder-to-reuse each file's metadata
  before resolving its engines, instead of after. A document's own front
  matter still wins when both are set — this is a course-wide *default*, not
  an override. Deliberately does **not** extend to `no-auto`: `no-auto`
  decides whether metadata auto-discovery runs at all, so it can't also
  depend on the metadata file that same discovery would find, without a
  circular dependency. Verified end-to-end (not just by reading the code)
  across all three of single-file, `-b` batch, and `-r` report mode, each
  with `-v`, each showing the `AUTO ENGINE` restriction now firing from
  `metadata.yaml` alone with no per-report front matter needed — and a
  sanity check that an explicit CLI `-e` still overrides it, unchanged.
- **`DOCUMENT_LATEX_KEYS` gained `unknown` and `unknowns`** (both map to the
  same `\LabUnknown`) for `nulabreport`'s `titlepage` layout's new optional
  unknown-sample field — see that package's own `docs/CHANGELOG.md` v1.14.0
  (the field itself) and v1.14.2 (the `Unknown:`/`Unknowns:` singular/plural
  label switch, and the `unknowns` alias added here). Verified end-to-end
  through `pdfmd` itself, not a hand-rolled `\renewcommand`: `unknown: 3` and
  `unknowns: "1, 2"` both build and render correctly.

---

## v2.0.0 — 2026-09-16

Baseline entry: versioning and changelog tracking begin here (see above).
Both fixes below were found and fixed in the same session that established
this file, discovered while debugging an unrelated `nulabreport` LaTeX
package issue (see that project's own `docs/CHANGELOG.md` v1.13.3 for the
report-side half of the story) — a short, all-numeric table was rendering
stretched across the full page width for no visible reason, and it took
real effort to figure out the actual cause was in `pdfmd.py`, not the LaTeX
package being built.

### Fixed

- **`TABLE_WIDTH_LUA_FILTER` (the auto-applied Lua filter that assigns
  column widths to a plain pipe table pandoc parsed with no explicit
  widths) fired on EVERY such table, not only ones that risked actually
  overflowing the page.** Intent was always "rescue a table whose unwrapped
  content would run past the margin" (see the filter's own long comment) —
  a short, all-numeric table with no wrapping risk at all got exactly the
  same treatment, forcibly rebalanced and stretched to the full page width,
  fighting any downstream Lua filter (e.g. a house-style package's own
  table macro) that deliberately sizes such a table to its natural content
  width instead. Root-caused by testing the SAME generated `.tex` two ways:
  compiling it directly with `lualatex` gave the correct, natural-width
  table; running the full `pdfmd` pipeline on the same source gave a
  stretched one — isolating the discrepancy to `pdfmd`'s own pandoc
  invocation (specifically, the extra `--lua-filter` it inserts before any
  user-supplied one) rather than the LaTeX side. Fixed by adding a real,
  if approximate, overflow check: estimate the table's total natural width
  from the same per-column longest-cell character count the filter already
  computes for its proportions, and skip rewriting the table entirely
  (leaving its `nil` widths untouched) when that estimate already fits a
  reasonable one-line budget (`CHAR_BUDGET`, ~95 characters, sized for this
  script's typical 12pt/1in-margin default document shape — an estimate,
  not a real width measurement, since a Lua filter runs before Pandoc or
  LaTeX ever measures a real font). Verified three ways: the previously
  -broken short table now renders at its natural width; a deliberately
  wide, genuinely-overflowing table still gets rescued (wraps within the
  page, doesn't overflow) exactly as before; a small generic 2-column table
  with no house-style package involved also now renders compact and
  centred instead of stretched.
- **`--verbose` never showed the actual Pandoc command being run** — only
  pdfmd's own "AUTO ..." decisions (which font/metadata/preamble/lua-filter
  it auto-discovered), never the resulting command line, which `--lua-filter`
  order, or what a discovered file actually resolved to. This is exactly
  the information that would have made the table-width bug above far
  faster to find. Added `log_cmd()`, called under `--verbose` right before
  every `subprocess.run` that invokes Pandoc (or Quarto's CLI is not yet
  covered — see below), printing the full command line via `shlex.quote` so
  a copy-pasted line is directly re-runnable.

### Known gaps, not fixed here

- `log_cmd()` is wired into every Pandoc-invoking `subprocess.run` call
  (single-file, batch, and report/book modes) but NOT into
  `convert_qmd`'s Quarto invocation, which doesn't currently take a
  `verbose` parameter at all. Low priority (`.qmd` is a narrow, separately
  -documented path) but worth doing in the same pass if `convert_qmd` is
  next touched for something else.
- `CHAR_BUDGET`'s ~95-character estimate is a single constant, not aware of
  a document's own `fontsize`/`geometry` front matter. Fine for this
  script's own typical use so far; revisit if a document with an unusual
  page shape trips the same "wrongly rebalanced" or "wrongly left alone"
  symptom in the other direction.

---

# Before 2.0.0 — reconstructed history (NOT reliable)

> **Read this first.** Nothing below was recorded at the time. It was
> rebuilt on 2026-10-05, after the fact, from two incomplete sources, and
> it should be read as an approximate outline, not a record:
>
> - **[chat]** — the author's saved transcripts of a few ChatGPT Codex
>   sessions (28 Jul – 1 Sep). They give real dates and real intent, but
>   cover only some of the edits: other sessions (other ChatGPT chats,
>   claude.ai, Cowork) were never saved, and the author does not remember
>   or could not find whether the script was also edited by other AIs
>   before then. The transcripts carry day and month but no year; 2026 is
>   assumed (it is the only reading consistent with the snapshots).
> - **[snapshot]** — differences between the surviving
>   `~/dev/python-projects/backups/pdfmd.py.bak-*` files (1 Sep, 7 Sep and
>   two on 16 Sep). Their dates are file modification times, and anything
>   that was added and removed (or changed twice) between two snapshots is
>   invisible. Every snapshot entry therefore covers a *window* of days,
>   and the order of its items inside that window is unknown.
> - **[recollection]** — the first script, `pan-tec` (v0.1.0), which the author
>   found again afterwards; its code and its chat (12 July 2026) are known.
>
> The version numbers 1.0.0–1.9.0 are invented here to give the outline a
> shape; they never existed in the script, and `PDFMD_VERSION` has only
> ever been 2.0.0 or later. Where an entry says "undated" or "by the
> snapshot of ...", the feature is known to exist by then but when and how
> it was introduced is not known. The script was also not born as
> `pdfmd.py`: it grew out of an earlier `pan-tec` shell function (v0.1.0)
> and `batchmd.py` (v0.2.0, a Markdown batch converter), both at the end of
> this file, written on 12 July 2026.
>
> Further, the transcripts mention edits made to individual Markdown
> documents rather than to the script (fixing a `header-includes:`
> preamble, replacing unsupported IPA macros, wiring up a bibliography);
> those are not script changes and are left out.

---

## v1.9.0 — 2026-09-16 (snapshot window: 11:18 → 21:12)

[snapshot] Between `pdfmd.py.bak-20260916-113000` and
`pdfmd.py.bak-20260916-tablewidth-preedit` — the latter is the exact
pre-edit state of v2.0.0.

### Added

- **`-v` / `--verbose`, and a quiet default.** Each "AUTO ..." decision
  (reader, title, margin, mainfont, monofont, lua) used to print its own
  line on every run; now one condensed `AUTO: KIND KIND ...` line per
  document is printed, and `--verbose` restores the full explanations.
  (`AUTO YAML`/`TEX`/`ENGINE`/`MD` still print in full.)
- **`--open`**: open the finished file with `open` (macOS) or `xdg-open`
  (Linux) after a successful single-file or report build; ignored in batch.
- **`--no-auto` grew four kinds** beyond the document-default ones:
  `metadata`/`yaml`, `preamble`/`tex`, `lua` and `files` (all three), so
  pdfmd's file auto-discovery can be switched off too. An explicit
  `-y`/`-H` still wins. The decision is made once, in a new
  `effective_no_auto()`, because discovery runs before `convert_one()`.
- **`pdfmd-options:` becomes the home for pdfmd-only front-matter keys.**
  `pdf-engine:`/`engine:` can now be nested under it; the bare top-level
  spelling keeps working.

### Fixed

- A document whose first line is a Pandoc `% title` block was switched to
  the `gfm` reader, which does not parse it, leaving the `%` lines as
  literal text; it is now treated like a document with YAML front matter.

---

## v1.8.0 — 2026-09-07 → 2026-09-16 (snapshot window)

[snapshot] Between `pdfmd.py.bak-20260907a` (7 Sep, 22:18) and
`pdfmd.py.bak-20260916-113000` (16 Sep, 11:18). The script roughly
doubled in size here (877 → 1,834 lines), and the module docstring grew
from a few usage examples into the long feature description. This is the most
under-resolved stretch of the whole history: it is certainly several
sessions' work squeezed into one entry.

### Added

- **Other output formats and input formats.** `--to FORMAT` (any Pandoc
  writer), `--from FORMAT`, and a recognised extension on `-o`
  (`-o notes.html`) pick a non-PDF target; the PDF engine is then neither
  needed nor checked. Any Pandoc-readable input works when given with its
  real extension. `.qmd` is handed to the `quarto` CLI instead of Pandoc
  (`--check-dependencies` lists it). (Note: in 2026-08 the author had
  decided *against* claiming `-t` for "typst" so as not to collide with
  Pandoc's own `-t`; `-t` was claimed later, here, as Pandoc's `--to`.)
- **Engine families and per-document engines.** `ENGINE_FAMILY` makes the
  fallback chain skip engines that share a TeX implementation with one
  that just failed; `ENGINE_GROUPS` (`tex`, `html`, `typst`) lets `-e` or
  a `pdf-engine:` front-matter key restrict the chain to one paradigm. A
  bare `-e` means the full unrestricted chain and overrides the document.
- **A reader choice for Markdown.** A document with no YAML front matter
  and no linked metadata file is read as `gfm` (content-sized pipe-table
  columns, tolerant of GitHub-style spacing), with `+definition_lists`
  re-enabled when needed and the plain `markdown` reader kept for `@cite`
  documents. A leading bare `# Title` is promoted to real title metadata
  and the headings shifted up a level.
- **`TABLE_WIDTH_LUA_FILTER`**, the auto-applied filter that assigns
  proportional widths to width-less pipe tables so a long cell wraps
  instead of running past the margin. (Its over-eager firing is what
  v2.0.0 fixes.)
- **Typographic defaults on LaTeX engines:** `geometry:margin=1in` when
  the document, a metadata file or a preamble sets no margin (with a check
  against loading `geometry` twice); `JetBrains Mono` as the monofont when
  the document has code and no `monofont:`.
- **`--no-auto [KIND ...]`** and the `pdfmd-options: {no-auto: ...}`
  front-matter block (needs PyYAML) to switch those defaults off.

### Changed

- **Font strategy.** The 1 Sep script already passed `mainfontfallback`
  (and retried with DejaVu Serif on a missing-glyph warning). This stretch
  tried Pandoc's per-glyph fallback and dropped it (it silently does
  nothing under XeLaTeX and crashes LuaLaTeX here); the default is now
  `STIX Two Text` first, retried once with `DejaVu Serif` if glyphs are
  reported missing. `-f`/`mainfont:` still win outright.

### Fixed

- A document given by a relative path with a subdirectory (`sub/a.md`) was
  looked up twice-nested once Pandoc's working directory was changed to
  the document's folder; paths are now resolved to absolute ones.

---

## v1.7.0 — 2026-09-02 → 2026-09-07 (snapshot window)

[snapshot] Between `pdfmd.py.bak-20260902` (identical to `-20260901`) and
`pdfmd.py.bak-20260907a`.

### Added

- **More engines and short names.** `latexmk`, `tectonic`, `pagedjs-cli`
  and `groff` joined the list (13 in all); `-e` accepts the number shown
  by `--check-dependencies` or a short alias (`lua`, `xe`, `pdf`, `mk`,
  `tect`, `weasy`, `wkhtml`, `pagedjs`, `roff`).
- **A document's own `header-includes:` survives an auto-included
  preamble.** Pandoc feeds `-H` files into the same variable, so a
  preamble beside the document used to silently discard the document's own
  block; pdfmd now re-appends it as a last `--include-in-header`, so a
  per-document override works.
- **Front-matter keys passed on to the preamble.** `experiment`, `group`,
  `course`, `section`, `instructor` and `performed` become
  `\renewcommand{\Lab...}{...}` lines after the preambles (for the
  `nulabreport` title page).
- **Auto-applied Lua filters** — only `<stem>.lua` and `nulabreport.lua`
  beside the document or its metadata file, announced as `AUTO LUA`;
  applied last, after `--citeproc`.
- **Bare `pdfmd`** with no argument converts the single `.md` file in the
  current directory (`AUTO MD`), and refuses with a list if there are
  several.

---

## v1.6.0 — 2026-09-01

[chat] Codex session, 17:08. (Present in the 1 Sep snapshot.)

### Added

- **Preamble discovery by the document's name.** For `review.md`:
  `review.yaml`/`review.yml` (layered over `metadata.yaml`) and the TeX
  preambles `preamble.tex`, `latex-preamble.tex`, `preamble-*.tex`,
  `review.tex`, `review_preamble.tex` and `review-preamble.tex`. Several
  safe preambles are all included, generic first and document-specific
  last, and a warning notes that later ones may override earlier ones.
  Complete documents and standalone TikZ files stay rejected.

---

## v1.5.0 — 2026-09-01

[chat] Codex session, 16:38–16:43.

### Added

- **Auto-discovery of a LaTeX preamble** (`preamble.tex`,
  `latex-preamble.tex`) beside the document, passed as
  `--include-in-header`. A file containing `\documentclass`,
  `\begin{document}`, `\end{document}` or `\begin{tikzpicture}` is never
  taken; an explicit `-H` is never duplicated; non-LaTeX engines never
  receive it.
- **Transparent discovery.** Auto-found files are printed as
  `AUTO YAML <path>` and `AUTO TEX <path>`; explicit `-y`/`-H` files are
  not labelled as automatic.

---

## v1.4.0 — 2026-08-30

[chat] Codex session, 15:00.

### Added

- **Wildcard names:** `pdfmd '*scrutiny'` matches Markdown stems with
  `fnmatch` (the `.md` is still implied). More than one match lists the
  candidates and stops instead of guessing. (Quote the pattern, or the
  shell expands it first.)

---

## v1.3.0 — 2026-08-29

[chat] Codex session, 22:10–22:18.

### Added

- **`--check-dependencies`** reports Pandoc and each supported PDF engine.
  Pip packaging was advised to be a separate `pyproject.toml`, with the
  engines checked but never installed by the script (done, much later, in
  3.10.0).
- **An engine fallback chain.** With no `-e`, installed engines are tried
  in order — LuaLaTeX, XeLaTeX, pdfLaTeX, Typst, WeasyPrint, wkhtmltopdf,
  Prince, ConTeXt, pdfroff — and the next one is tried when one fails,
  announced as `WARN  <file>: lualatex failed; trying xelatex...`. An
  explicit `-e` is respected; Beamer (`-p`) is limited to TeX-family
  engines.
- **Automatic `{=latex}` wrapping of `header-includes: |`** for LaTeX
  engines, in Markdown and metadata YAML, in single-file and report mode.
  A `%` comment or preamble command inside a YAML literal block was parsed
  as Markdown (`%` → `\%`), so the preamble broke with "Missing
  \begin{document}"; the source file itself is never modified (a
  temporary copy is compiled).

### Fixed

- A bug in the exclusion options of report mode (unspecified in the
  transcript).

---

## v1.2.1 — 2026-08-26

[chat] Codex session, 18:06–18:09.

### Fixed

- **`--citeproc` was not enabled automatically for bare citations.** The
  detector only looked for `[@key]`; it now also recognises `@key` and
  `-@key`, while skipping e-mail addresses. (The first attempt to apply
  the fix failed on a write-permission restriction in that session and
  was redone on request.)

---

## v1.2.0 — undated, between 2026-07-28 and 2026-08-29

[snapshot, inferred] Not described by any saved transcript; present in the
1 Sep snapshot, and implied by chat remarks (an "existing `--report`
exclusion-option bug" on 29 Aug; "the script already automatically
searches for yaml files" on 1 Sep).

### Added

- **Report/book mode** (`-r`/`--report`/`--book`, `--recursive`): all
  Markdown files in a folder combined into one PDF, ordered by a
  `chapter:` front-matter field; `-i`/`--exclude` and
  `--exclude-unnumbered` to leave files out.
- **Metadata YAML:** `-y`/`--metadata-file` (a stack, `all`, or a bare `-y`
  to disable discovery), automatic discovery of `metadata.yaml` and a
  document-named YAML, `yamlorder:` and `autoinclude: false` inside the
  YAML files, and `defaults.yaml` always skipped.
- **Mainfont handling:** fall back to DejaVu Serif when a build reports a
  missing glyph, unless the user or the document chose a font.

---

## v1.1.1 — 2026-08-08

[chat] Codex session, 18:10.

### Fixed

- A regression from the previous change: adding a `-cwd` spelling of the
  destination flag left `args.destination_cwd` undefined, so
  `pdfmd name -p` crashed with an `AttributeError`. `-d`, `-cwd`, `--cwd`
  and `--destination-cwd` now all set the same destination.

---

## v1.1.0 — 2026-07-31

[chat] Codex session, 21:11.

### Added

- **`-d` / `--destination-cwd`**: keep the document's filename but write
  the PDF into the current working directory instead of beside the source
  (for previewing a file given by full path before saving it for good).

---

## v1.0.1 — 2026-07-28

[chat] Codex session, 16:18–16:19 (outcome not confirmed in the
transcript, but the 1 Sep snapshot normalises names to NFC).

### Fixed

- A Cyrillic name was not found because the file name used a decomposed
  character (e.g. `и` + combining breve) while the generated candidate
  used the composed `й`; matching now normalises both sides.

---

## v1.0.0 — 2026-07-28

[chat] Codex session, 16:01–16:06. The first version called `pdfmd`:
`batchmd.py` extended and renamed.

### Added

- **Name resolution** from a bare, Latin-spelled name: the exact name
  first, then transliterated Cyrillic variants, then each with the
  `Пробный ` prefix used for slide decks (`pdfmd Name` finds `Name.md`,
  its Cyrillic spellings, or `Пробный <Name>.md`), and the PDF takes the
  name of the file that was found. Zero or several matches is an error.
- **Presentation mode** `-p` (Beamer via XeLaTeX, `--slide-level`),
  **batch mode** `-b` over a directory with `-j` parallel jobs and `-o`
  output directory, and passthrough of `-e` (engine; LuaLaTeX by default),
  `-f` (font), `-V` (Pandoc variables, e.g. geometry) and any other
  Pandoc option.

---

## v0.2.0 — 2026-07-12

[recollection] The second code of the day, called `batchmd`, written later on
12 July than `pan-tec` (v0.1.0 below), which it followed. Generated by Gemini,
like `pan-tec`. The version numbers of the 0.x entries are labels given in this
file; the scripts did not carry them.

### Added

- A script of about twenty lines: `pypandoc` converts every `*.md` in one fixed
  folder (`~/Downloads/files`) to a PDF beside it, with the Tectonic engine,
  `geometry:margin=1.5cm` and `mainfont=DejaVu Serif`. It prints
  `Converting NAME.md to NAME.pdf...` for each file, reports a failed file and
  goes on, and ends with `Batch conversion completed!`. Margin and font were
  already two of the defaults pdfmd still has.

---

## v0.1.1 — 2026-10-08 (`pan-tec`)

[chat] The author's own edit of the function, in `~/dev/sh/functions/pan-tec.zsh` (outside this repository), dated by that
file's last change. Diffed against the v0.1.0 function from the Gemini chat: the same command line, plus the changes below.

### Added

- A header comment: `# pan-tec <pandoc args...> — pandoc with the tectonic PDF engine, quiet output`.
- A check that `tectonic` is on the PATH before pandoc runs. Without it the function prints `pan-tec: tectonic not found`
  to standard error and returns 1, instead of pandoc failing on the engine later.

### Unchanged

- The pandoc line itself: `pandoc "$@" --pdf-engine=tectonic --pdf-engine-opt=--chatter=minimal`. The `--chatter=minimal`
  is the value the Gemini chat only suggested (see v0.1.0); this file is the author's working copy of it.

---

## v0.1.0 — 2026-07-12 (`pan-tec`)

[chat] Gemini conversation, 12 July 2026, pasted by the author (the year is
taken from the surrounding entries; the transcript shows only the day). The first
version of what became pdfmd, and it came before `batchmd` (v0.2.0 above) the same
day. It was not a Python script but a shell function in `~/.zshrc`: a thin wrapper
around pandoc, as the author remembered. The transcript ends with Gemini's last
suggested flag; whether it ran cleanly is not shown.

### Added

- **`pan-tec`**, a shell function in `~/.zshrc`:
  `pandoc "$@" --pdf-engine=tectonic --pdf-engine-opt=--chatter=minimal`.
  `pan-tec test.md -o ex.pdf` compiles a Markdown file to PDF with the Tectonic
  engine and without Tectonic's font-path warnings (the `NewCM` fonts were
  loaded from an absolute path under the user's `Library/Fonts`, which Tectonic
  flags as not reproducible; the transcript shows those warnings and no error).

### Notes

- The first version passed `--pdf-engine-opt=--chatter-level=critical`.
  Tectonic rejected it: `unexpected argument '--chatter-level' found`.
- The next version used `--chatter=critical`, which Tectonic also rejected:
  `invalid value 'critical' for '--chatter <CHATTER_LEVEL>': unsupported or unknown chatter level`.
- Tectonic's `--help` gives `-c, --chatter <CHATTER_LEVEL>` with the default
  `default` but does not list the other levels. Gemini's last suggestion,
  `--chatter=minimal`, is not confirmed by a run in the transcript.
