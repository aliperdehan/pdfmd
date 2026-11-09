# Splitting pdfmd.py into packages under lib/

Entry 3fi. Verified on 2026-11-09 against pdfmd 3.32.54 (`pdfmd.py`: 30,872 lines, 1,047 top-level definitions). This
replaces the first survey (2026-11-08), whose line ranges overlapped, mixed topics and left out about 85 definitions.
The rule behind it is CLAUDE.md's "pdfmd.py holds only the core".

## Numbers

- **Phase 1 (this file):** 37 packages (20 new, 17 existing), 476 definitions, about 12,800 lines of definitions and 380
  lines of constants. `pdfmd.py` goes from about 30,900 to about 17,700 lines, 1,470 of them the module docstring.
- **Phase 2 (not planned yet):** the 571 definitions (about 11,700 lines) that phase 1 leaves. Most of them are helpers that
  several packages call. They are planned from a fresh audit after phase 1, because phase 1 changes who calls whom.

## How the table was made

- The seeds are the names of the first survey. A definition joins a package when every definition that uses it is in that
  package, repeated until nothing changes. A definition used by two packages, or by code that stays, stays.
- Never moved: `main`, `run_main`, `convert_one`, `_convert_one_core`, `convert_file`, `convert_text`, `PdfmdError`.
- A constant moves with a package only when that package alone reads it and nothing rebinds it. State rebound with
  `global` (the `*_CLI` settings, `LAST_*`, `VERBOSE_OUTPUT`, the probe caches) stays in `pdfmd.py`.
- The lists are names, not line numbers, because lines shift with every move. A change to the table during the moves is made
  here, in the commit of the move it concerns.
- SPLIT.md's `pdfmd_cli_parser` is `pdfmd_args` (the `pdfmd_cli` namespace is a 4.0 question). The other names are the
  ones chosen on 2026-11-08: `pdfmd_assemble`, `pdfmd_parts`, `pdfmd_attach`, `pdfmd_tex`, `pdfmd_pdfimages`,
  `pdfmd_compat`, `pdfmd_routing`.

## The pattern for every move

0. **The spec first.** `python3 scripts/split_spec.py pdfmd_x` reads the package's section below and the source as it is
   now, and prints where each name is, the pdfmd names to read as `core.X`, the re-exports, the test patches that matter
   and the names bound twice at the top level of `pdfmd.py`. A name bound twice stays where its binding in force is (the
   later one), whatever the table says; the earlier, dead binding is removed in a commit of its own.
1. **One package per commit, a pure move.** The tree is clean first. The first move is 3.33.0, each later one 3.33.x,
   with its own changelog entry and `PDFMD_VERSION` bump. A move changes no behaviour; a bug found on the way is fixed in
   a commit of its own (the author's leave, 2026-11-09).
2. **Where the code goes.** A new package: `lib/pdfmd_x/__init__.py`. An existing package: a module of its own beside
   what is there (`lib/pdfmd_x/<role>.py`), unless the moved code is small. The text is moved as it is; only names change.
3. **How it reaches pdfmd.** The package has a module global `core = None`; `pdfmd.py` sets it right after the import,
   and the first binding wins, so a second copy of pdfmd (a script run imports nothing as `pdfmd`, but a stray
   `import pdfmd` would make one) never re-points it. The binding is one line in the block after
   `pypdf = lazy_import("pypdf")`: `import pdfmd_x`, the re-exports, `bind_core(pdfmd_x)`. `pdfmd.py` needs its packages
   (the author, 2026-11-09): the block starts with a check that stops a copy without `lib/` with one line, so a new package
   needs no fallback for a missing import. The new `__init__.py` starts
   with `from __future__ import annotations` (Python 3.9 reads the moved signatures' `str | None` only with it). Every pdfmd name the moved code uses (a helper, a constant, state)
   is read as `core.NAME` when it runs: never `import pdfmd`, never a copy taken at import time. Calls between moved
   functions are direct, except calls to a name that a test patches (`mock.patch.object(pdfmd, ...)`): those go through
   `core.`, so the patch still reaches them. Each package's section lists them.
4. **pdfmd.py.** The moved code is deleted. A re-export (`from pdfmd_x import a, b`, beside the binding) brings back every
   moved name that `pdfmd.py` itself, a test or a `lib/` module reads, so `pdfmd.a` keeps working. A lazy loader
   (`x_module()`) that only served the moved code goes. For a package that `pdfmd.py` does not load at start, the
   re-export is deferred (step 6).
5. **Packaging.** A new package goes into `pyproject.toml` (`packages` and `[tool.setuptools.package-dir]`) and into
   `PACKAGES` in `scripts/build_zipapp.py`; `test_packaging` fails until it does.
6. **Start-up time.** A plain re-export makes the package load at every start. Heavy imports stay inside functions;
   `python3 scripts/pdfmd --version` must not get slower (interleaved runs of HEAD and the move, best and median).
   - **New packages** hold only the moved code, cost a fraction of a millisecond, and are re-exported plainly.
   - **An existing package that `pdfmd.py` does not load at start today** is deferred, whatever it costs: the moved
     code goes into `lib/pdfmd_x/<role>.py`, and importing that runs the package's `__init__`, which loads the rest of
     the package (measured 2026-11-09 on top of pdfmd's own start: `pdfmd_serve` 17 ms, as it brings `http.server` and
     `ssl`; `pdfmd_office` 21 ms; the other fourteen 0.2 to 3.5 ms each, about 25 ms together). In the binding
     block, each moved function that `pdfmd.py` calls or a test reads gets a stand-in,
     `serve_command = deferred("pdfmd_serve.commands", "serve_command")`, which loads the module on its first call,
     hands it `core` (`bind_core`) and calls the real function; `pdfmd.py`'s own calls keep their bare names. A moved
     constant or class that a test or `lib/` reads as `pdfmd.X` goes into `DEFERRED_NAMES` instead
     (`DEFERRED_NAMES.update(_PANDOC_EXTENSIONS="pdfmd_flat.probe")`): the module's `__getattr__` (PEP 562) loads the
     module on the first read and returns the package's own object, so `mock.patch.dict(pdfmd.X)` still reaches it.
     `split_check`'s default builds may never reach a deferred call, so each deferred move adds an `--extra` build (or a
     timed hand run) that goes through the real call site.
7. **Proof.**
   - `ruff check --select F --force-exclude --exclude pdfmd_inkmd pdfmd.py lib/ scripts/ tests/` (the CI line).
   - The package's tests (below) and the always-run set: `test_packaging`, `test_setup`, `test_docs_consistency`,
     `test_compat`, `test_probes`, `test_serve`, `test_launcher`, `test_jobs`.
   - `python3 scripts/split_check.py` does the next two checks in one run: "before" is HEAD in a temporary worktree,
     "after" the working tree with the move uncommitted (`--extra 'NAME:ARGS'` adds a build of the package's feature).
     Nothing in `pdfmd.py` or `lib/` is edited while it runs.
   - `--help` and every `--help TOPIC` byte-identical before and after.
   - `--verbose` output identical before and after (temporary names, times and the build-record folder aside) on a fixed
     set: one document to PDF, `--to html`, `--to docx`, `-r` on `examples/book`, `-b -j 2`, and the documents that use
     the package's feature. The baseline is taken before the first edit, with the tree clean.
   - The full suite once, after the last move (the author, 2026-11-09), not per move.
8. **Docs** that say where code lives (CLAUDE.md, README, docstrings) change in the same commit.
9. **Progress.** When a package is done, its heading here gets "done in 3.33.x (commit)". When all are done, phase 2 is
   planned and this file is rewritten for it.

## Phase 2 clusters (for later; read from where the remaining definitions sit)

Configuration, paths and document discovery; the filter-argument glue for `lib/pdfmd_lua`; markup and metadata layers;
engine and tool resolution; preamble and Lua-filter discovery; stamps and PDF metadata; labels and calc seeding; output
naming; the direct and cached routes; `run_main` itself (about 1,000 lines of dispatch).

## Phase 1: the packages, in order

The order goes from the smallest risk to the largest. Wave 1 sets the pattern for a new and for an existing package; the
hard packages come last, when the pattern is proven. "Tests" are the test modules that name the package's definitions or
its feature, run in addition to the always-run set.

### Wave 1: the pattern (Opus)

#### 1. `pdfmd_comments` (new package): 8 definitions, ~244 lines; done in 3.33.0

Definitions: `scan_comment_line`, `strip_markdown_comments`, `CommentPolicy`, `comment_kind_set`, `parse_comment_policy`, `tex_comment_start`, `strip_tex_comments`, `strip_xml_comments`.

Constants that move with it (only this package reads them): `COMMENT_KIND_NAMES`, `KEEP_COMMENT_RE`, `LIST_ITEM_RE`, `TEX_KEEP_COMMENT_RE`, `TEX_VERBATIM_BEGIN_RE`.

Facts: 8 callers stay in pdfmd.py (re-exported); 3 pdfmd names read through `core`.

Note: Leaf: nothing it calls is in another group. Sets the pattern for a NEW package (binding, re-exports, packaging in three places).
`FENCE_RE` was bound twice (v3.20.0 and, in this block, v3.22.0); the second binding, with named groups, is the one in
force for every user, so it stays in `pdfmd.py` and the package reads `core.FENCE_RE`. The two explanatory comment
blocks moved with the code.

Tests: `test_attach`, `test_pagebreak`, `test_show_comments`, `test_tables`, and for the binding itself
`test_ranking_generated` (a second copy of `pdfmd.py` in one process) and `test_lua_missing` (a script run in-process).

#### 2. `pdfmd_templates` (existing package): 3 definitions, ~63 lines; done in 3.33.2

Definitions: `templates_module`, `git_user_name`, `init_command`.

Facts: 1 callers stay in pdfmd.py (re-exported); 2 pdfmd names read through `core`.

Note: Sets the pattern for an EXISTING package: the lazy loader `templates_module()` goes, the package calls itself directly.
Its "the package is missing" branch went with it: a copy without `lib/` stops at start. `config_root` is patched by
`test_lua_trust`, so the package reads `core.config_root`. The eager import costs about 0.5 ms.

Tests: `test_templates`.

### Wave 2: small and self-contained (Sonnet, reviewed)

#### 3. `pdfmd_watch` (new package): 3 definitions, ~70 lines; done in 3.33.3

Definitions: `watch_signature`, `pinned_watch_argv`, `run_watch`.

Facts: 1 callers stay in pdfmd.py (re-exported); 3 pdfmd names read through `core`.

Note: `run_watch` re-runs the script it was started from, found with `__file__`; inside the package that would be
`lib/pdfmd_watch/__init__.py`, so it reads `core.__file__` (`pdfmd.py`). `WATCH_INTERVAL` stays in `pdfmd.py` (two other polling loops read it).

Tests: `test_ranking_generated`.

#### 4. `pdfmd_hybrid` (new package): 4 definitions, ~84 lines; done in 3.33.4

Definitions: `resolve_hybrid`, `odf_source_for`, `attach_hybrid`, `hybrid_after_success`.

Constants that move with it (only this package reads them): `HYBRID_DESCRIPTION`, `HYBRID_FAMILY`.

Facts: 1 callers stay in pdfmd.py (re-exported); 14 pdfmd names read through `core`.

Note: `HYBRID_CLI` (rebound by `main()`) and `HYBRID_MIME` (also read by the attachment readers) stay in `pdfmd.py`. `pypdf` there is a
lazy loader, so the package reads `core.pypdf` and never imports pypdf at its top.

Tests: `test_embedding`.

#### 5. `pdfmd_ansi` (existing package): 7 definitions, ~77 lines; done in 3.33.6

Definitions: `ansi_width_argument`, `ansi_columns`, `ansi_colour_on`, `ansi_math`, `ansi_document_text`, `ansi_finish`, `ansi_without_pandoc`.

Facts: 3 callers stay in pdfmd.py (re-exported); 11 pdfmd names read through `core`.

Note: `ANSI_*_ENV`, `ANSI_FALLBACK_WIDTH` and `ANSI_LINK_TERMINALS` stay in `pdfmd.py`; the module reads them as `core.X`. `inkmd_vendored` is patched by `test_calibre_markdown`, so it is called as `core.inkmd_vendored`.

Tests: `test_ansi`.

#### 6. `pdfmd_serve` (existing package): 6 definitions, ~89 lines; done in 3.33.7

Definitions: `serve_main_document`, `serve_discovered`, `serve_live_filters`, `serve_core`, `serve_command`, `api_command`.

Facts: 1 callers stay in pdfmd.py (re-exported); 12 pdfmd names read through `core`.

Note: `serve_live_filters` is read by `test_serve` (one filter list); that test already finds it in `lib/`.

Note: the module's global `core` is pdfmd; `lib/pdfmd_serve/core.py` (the JSON core) is a different thing. `serve_live_filters` is a context manager: its stand-in returns the real one, which is what `Core(filters=...)` calls. The successful `--api` answers carry an mtime or seconds, so `split_check` proves the error paths and a by-hand run proves the rest (see the changelog entry).

Tests: `test_serve`.

#### 7. `pdfmd_flat` (existing package): 8 definitions, ~112 lines; done in 3.33.8

Definitions: `pandoc_extensions`, `flat_settings`, `flat_writer`, `flat_filter_args`, `split_ascii_target`, `ascii_missing`, `ascii_filter_args`, `ascii_finish`.

Constants that move with it (only this package reads them): `_PANDOC_EXTENSIONS`.

Facts: 2 callers stay in pdfmd.py (re-exported); 9 pdfmd names read through `core`.

Note: `GFM_CLI` and `ASCII_CLI` (settings main() fills) stay in `pdfmd.py` and are read as `core.X`. `_PANDOC_EXTENSIONS` is a `DEFERRED_NAMES` entry (`test_probes` patches it with `mock.patch.dict`). `ascii_filter_args` reads `core.__file__`. split_check's extras need `--no-auto raw`: the raw map's file name hashes the cache path, which differs between its two copies.

Tests: `test_ascii`, `test_flat`, `test_keep_source`, `test_probes`, `test_setup`.

#### 8. `pdfmd_docs` (existing package): 6 definitions, ~164 lines; done in 3.33.9

Definitions: `document_file`, `document_headings`, `document_section`, `search_documents`, `render_document`, `doc_command`.

Constants that move with it (only this package reads them): `DOCUMENTS`, `DOC_URL`.

Facts: 1 callers stay in pdfmd.py (re-exported); 3 pdfmd names read through `core`.

Note: `document_file` reads `core.__file__` for the checkout's copy and leaves `pdfmd_docs.__file__` (the bundled copy) as it was. `fence_after` stays (other code reads it); `cache_root` and `which` are patched by tests, so they are `core.` calls. `DOCUMENTS` is a `DEFERRED_NAMES` entry.

Tests: `test_compat`, `test_doc`, `test_docs_consistency`, `test_doctor`, `test_docx_tables`, `test_packaging`, `test_sections`.

#### 9. `pdfmd_css` (existing package): 6 definitions, ~191 lines; done in 3.33.10

Definitions: `css_scope`, `css_names`, `css_sources`, `css_additions`, `css_heading_latex`, `css_heading_args`.

Constants that move with it (only this package reads them): `CSS_COLOURS`, `CSS_HEADING_COMMANDS`, `CSS_HEADING_DEFAULTS`, `CSS_HEADING_OWN_RE`.

Facts: 1 callers stay in pdfmd.py (re-exported); 16 pdfmd names read through `core`.

Tests: `test_css`, `test_css_v2`.

#### 10. `pdfmd_crop` (existing package): 8 definitions, ~192 lines; done in 3.33.11 (`PICTURE_FORMATS` stayed in `pdfmd.py`: it is built from `PICTURE_ONLY`)

Definitions: `picture_target`, `picture_build`, `picture_sources`, `picture_page_folder`, `picture_targets`, `picture_one`, `multi_target_command`, `picture_command`.

Constants that move with it (only this package reads them): `PICTURE_FORMATS`, `PICTURE_OPTIONS`, `TARGET_ONLY_OPTIONS`.

Facts: 1 callers stay in pdfmd.py (re-exported); 7 pdfmd names read through `core`.

Tests: `test_crop`.

#### 11. `pdfmd_obsidian` (existing package): 8 definitions, ~157 lines; done in 3.33.12 (the two caches are in `DEFERRED_NAMES`; `FLAVOUR_PRESETS` is read as `core.FLAVOUR_PRESETS`)

Definitions: `vault_app_setting`, `single_newline_mode`, `vault_root`, `embed_settings`, `_embed_folder_index`, `find_embedded_image`, `embed_source`, `embed_filter_args`.

Constants that move with it (only this package reads them): `EMBED_FIT_WORDS`, `EMBED_SEARCH_WORDS`, `NEWLINE_WORDS`, `_EMBED_INDEX`, `_EMBED_SKIP_FOLDERS`, `_VAULT_ROOTS`.

Facts: 4 callers stay in pdfmd.py (re-exported); 5 pdfmd names read through `core`.

Tests: `test_embeds`, `test_newline`, `test_obsidian`, `test_wikilinks`.

#### 12. `pdfmd_polish` (new package): 11 definitions, ~270 lines; done in 3.33.13 (`polish_pdf`'s `@timed` is a `_timed` that looks `core.timed` up at call time)

Definitions: `parse_hf_template`, `fill_hf_field`, `markdown_headings`, `search_form`, `locate_headings`, `outline_entries`, `hf_text`, `hf_overlay`, `local_file_of_link`, `polish_wanted`, `polish_pdf`.

Constants that move with it (only this package reads them): `HF_FIELDS`, `HF_FONT`, `HF_MARGIN`, `HF_SIZE`, `LINKED_FILE_LIMIT`.

Facts: 1 callers stay in pdfmd.py (re-exported); 7 pdfmd names read through `core`.

Tests: `test_polish`, `test_sections`.

#### 13. `pdfmd_pdfimages` (new package): 10 definitions, ~268 lines; done in 3.33.14 (`restored_image_paths` stays: it is not on the list)

Definitions: `png_chunk`, `encode_png`, `file_picture_size`, `pdf_pictures`, `match_images_to_pdf`, `samples_to_png`, `form_to_pdf`, `extract_pdf_images`, `rewrite_tex_image_paths`, `rewrite_image_paths`.

Constants that move with it (only this package reads them): `DECODE_LIMIT`, `SVG_UNITS`.

Facts: 3 callers stay in pdfmd.py (re-exported); 3 pdfmd names read through `core`.

Tests: `test_attach`, `test_standalone_source`.

#### 14. `pdfmd_compat` (new package): 12 definitions, ~250 lines; done in 3.33.15 (the comments above the constants moved with them; `expand_glob` is imported by the package, so `pdfmd.py` lost its own import)

Definitions: `mdpdf_npm_file`, `mdpdf_npm_length`, `mdpdf_translate`, `mdpdf_main`, `md2pdf_translate`, `md2pdf_main`, `inkmd_translate`, `inkmd_main`, `batchmd_translate`, `batchmd_main`, `pan_tec_translate`, `pan_tec_main`.

Constants that move with it (only this package reads them): `INKMD_KEYS`, `MD2PDF_ENGINE_WORDS`, `MD2PDF_IGNORED_VALUE_KEYS`, `MD2PDF_VALUE_KEYS`, `MDPDF_KEYS`, `MDPDF_NPM_FLAGS`, `MDPDF_NPM_VALUE_KEYS`.

Facts: 0 callers stay in pdfmd.py (re-exported); 2 pdfmd names read through `core`.

Note: `mdpdf_main`, `md2pdf_main` are console entry points in `pyproject.toml` (`pdfmd:mdpdf_main`): the re-export keeps them; check `pip install` metadata is unchanged.

Tests: `test_compat`, `test_pan_tec`, `test_polish`.

#### 15. `pdfmd_view` (new package): 9 definitions, ~197 lines; done in 3.33.16 (`__file__` is `core.__file__`: the child it starts is pdfmd.py; `which` is `core.which`; `split_command` stays)

Definitions: `view_child_arguments`, `view_stdin_file`, `view_sources`, `stdin_build`, `view_wants_pager`, `view_pager_setting`, `pager_command`, `run_pager`, `terminal_view`.

Constants that move with it (only this package reads them): `ANSI_LINK_TERMINALS`, `BINARY_TARGETS`, `VIEW_DROPPED`, `VIEW_PAGER`.

Facts: 1 callers stay in pdfmd.py (re-exported); 12 pdfmd names read through `core`.

Tests: `test_ansi`, `test_command_words`, `test_ranking_lists`.

#### 16. `pdfmd_check` (existing package): 7 definitions, ~177 lines; done in 3.33.17 (in `command.py`; only `check_command` has a stand-in; `check_module()` and the `check is None` branch are gone)

Definitions: `check_module`, `bibliography_names`, `bibliography_file_keys`, `check_bibliography`, `calc_check_records`, `check_documents`, `check_command`.

Facts: 1 callers stay in pdfmd.py (re-exported); 22 pdfmd names read through `core`.

Note: The lazy loader `check_module()` goes.

Tests: `test_check`, `test_check_source`.

#### 17. `pdfmd_ranking` (existing package): 9 definitions, ~173 lines; done in 3.33.19 (in `choice.py`; the test that loads a second pdfmd copy needed no change; `FOLDER_SETTINGS` has a `DEFERRED_NAMES` entry only)

Definitions: `ranking_inherit_off`, `read_ranking_file`, `ranking_of_options`, `ranking_for_document`, `ranking_layers`, `ranking_clashes`, `bare_ranking`, `priority_candidates`, `which_command`.

Constants that move with it (only this package reads them): `FOLDER_SETTINGS`, `RANKING_DOCUMENT_KEYS`, `RANKING_FILE`.

Facts: 4 callers stay in pdfmd.py (re-exported); 14 pdfmd names read through `core`.

Tests: `test_ranking_bare`, `test_ranking_generated`, `test_ranking_layers`, `test_ranking_lists`, `test_ranking_rules`, `test_ranking_which`.

Hazard: `test_ranking_generated` loads `pdfmd.py` a second time as `pdfmd_under_test`. The package's `core` is the copy
loaded first, so a patch on the second copy does not reach the moved code; the test imports `pdfmd` instead, or patches
through `pdfmd_ranking.core`.

#### 18. `pdfmd_lookup` (new package): 13 definitions, ~228 lines; done in 3.33.20 (`LOOKUP_TIERS` and `LOOKUP_FIELD_WORDS` moved too, as default arguments of `rank_lookup`; `CYRILLIC_LOOSE` stayed, built from `CYRILLIC_STRICT`)

Definitions: `latin_candidates`, `cyrillic_candidates`, `strip_lookup_suffix`, `find_wildcard_markdown`, `lookup_key`, `lookup_query_keys`, `LookupAmbiguous`, `lookup_field_matches`, `rank_lookup`, `lookup_fields`, `priority_enabled`, `source_markdown`, `document_priority`.

Constants that move with it (only this package reads them): `CYRILLIC_LOOSE`, `GENERATED_MARKDOWN_ENDINGS`, `LOOKUP_HEAD_BYTES`, `LOOKUP_MIN_PREFIX`.

Facts: 11 callers stay in pdfmd.py (re-exported); 16 pdfmd names read through `core`.

Tests: `test_lookup`, `test_translit`.

#### 19. `pdfmd_setup` (existing package): 8 definitions, ~184 lines; done in 3.33.21 (in `command.py`; stand-ins for `user_path_command`, `maybe_hint_setup`, `setup_command` and `flag_names`)

Definitions: `user_path_command`, `setup_actions`, `setup_hint_state`, `maybe_hint_setup`, `flag_topics`, `flag_names`, `setup_sources`, `setup_command`.

Constants that move with it (only this package reads them): `FOLDER_HEADER`, `FOLDER_METADATA_HEADER`, `METADATA_HEADER`.

Facts: 1 callers stay in pdfmd.py (re-exported); 19 pdfmd names read through `core`.

Tests: `test_ansi`, `test_atomic`, `test_auto_states`, `test_presets`, `test_setup`, `test_setup_folder`, `test_user_path`.

#### 20. `pdfmd_kits` (existing package): 11 definitions, ~217 lines; done in 3.33.22 (in `locate.py`; ten stand-ins; `kit_package_folders` is called only from `package_helper`, which stays)

Definitions: `package_places`, `kpsewhich_locate`, `read_package_helper`, `kit_package_folders`, `kit_install_record`, `kits_report`, `kit_header_insert`, `kit_header_settle`, `kit_cache_tex`, `kit_header_resolve`, `kit_carried_files`.

Facts: 12 callers stay in pdfmd.py (re-exported); 18 pdfmd names read through `core`.

Tests: `test_kit_carry`, `test_kit_install`, `test_kit_no_auto`, `test_kit_preamble`, `test_kit_selection`, `test_kit_texinputs`, `test_kits`, `test_package_helper`, `test_probes`.

#### 21. `pdfmd_buildinfo` (existing package): 12 definitions, ~224 lines; done in 3.33.23 (in `build.py`; `timed` and `timing_module` stayed: 15 definitions apply `timed` as a decorator when the file is loaded, so a stand-in would load the package at every start, and `pdfmd.py` calls `timing_module` itself, while `lib/pdfmd_polish` keeps its own `_timed`; `BuildRecorder` is started through `load_package("pdfmd_buildinfo.build").BuildRecorder.start(...)`, as a stand-in is a function and has no class attribute; stand-ins for `begin_timer`, `attach_time`, `time_breakdown` and `last_build_command`)

Definitions: `begin_timer`, `timed`, `resolve_build_time`, `attach_time`, `time_breakdown`, `record_module`, `_RecordTee`, `build_log_mode_word`, `resolve_build_log`, `build_record_folders`, `BuildRecorder`, `last_build_command`.

Constants that move with it (only this package reads them): `BUILD_LOG_KEEP`, `BUILD_LOG_KILOBYTES`.

Facts: 18 callers stay in pdfmd.py (re-exported); 22 pdfmd names read through `core`.

Note: 18 callers outside: re-exports carry them. The lazy loaders `timing_module()`/`record_module()` go where nothing else needs them.

Tests: `test_build_log`, `test_build_time`.

#### 22. `pdfmd_tables` (existing package): 5 definitions, ~245 lines; done in 3.33.24 (in `command.py`; stand-ins for `csv_defaults`, `csv_table_filter_args`, `table_keep_metadata` and `tables_command`; `spreadsheet_args` is called only from `csv_table_filter_args`)

Definitions: `csv_defaults`, `table_keep_metadata`, `spreadsheet_args`, `csv_table_filter_args`, `tables_command`.

Constants that move with it (only this package reads them): `CSV_CUTS`.

Facts: 5 callers stay in pdfmd.py (re-exported); 27 pdfmd names read through `core`.

Tests: `test_cellalign`, `test_celltags`, `test_csv_switch`, `test_csv_table`, `test_docx_tables`, `test_serve`, `test_spreadsheets`, `test_syntax_table`, `test_table_ascii`, `test_table_captions`, `test_table_keep`, `test_table_widths`, `test_tables`.

### Wave 3: medium (Sonnet, reviewed)

#### 23. `pdfmd_routing` (new package): 10 definitions, ~287 lines; done in 3.33.25 (`tessdata_environment` moved too, from far above the rest; `PDF_TO_STDOUT_CLI` stayed, rebound with `global`; `BATCHOCR_MIN` stayed, read as `core.BATCHOCR_MIN`)

Definitions: `tessdata_environment`, `batchocr_spec`, `find_batchocr`, `install_ocr_tools`, `batchocr_missing_message`, `pdf_read_target`, `route_ebook_input`, `route_pdf_input`, `text_to_markdown_mode`, `route_text_input`.

Constants that move with it (only this package reads them): `BATCHOCR_REPOSITORY`, `BATCHOCR_TAG`, `BATCHOCR_TEXT_MIN`, `EBOOK_INPUT_EXTENSIONS`, `PDF_READ_FORMATS`.

Facts: 4 callers stay in pdfmd.py (re-exported); 23 pdfmd names read through `core`.

Tests: `test_ebook_input`, `test_install_ocr`, `test_pdf_input`, `test_tessdata`.

#### 24. `pdfmd_bridge` (new package): 10 definitions, ~248 lines; done in 3.33.26 (`CITEPROC_DISABLED` stayed, rebound with `global`; the three `@timed` functions use `_timed`)

Definitions: `run_soffice_convert`, `convert_office_direct`, `convert_via_soffice_bridge`, `calibre_html_command`, `calibre_page_options`, `run_calibre`, `start_soffice_job`, `run_calibre_convert`, `browser_page_css`, `run_browser_print`.

Constants that move with it (only this package reads them): `CALIBRE_TABLE_CSS`, `PANDOC_TABLE_STYLE_RE`.

Facts: 6 callers stay in pdfmd.py (re-exported); 32 pdfmd names read through `core`.

Tests: `test_browser_engine`, `test_calibre`, `test_calibre_targets`, `test_soffice_timeout`.

#### 25. `pdfmd_office` (existing package): 15 definitions, ~414 lines; done in 3.33.27 (`lib/pdfmd_office/build.py`; `OfficeArguments` has a stand-in, `office_module()` stayed)

Definitions: `office_package_folders`, `office_defaults_sources`, `find_office_profile`, `find_reference_doc`, `OfficeArguments`, `office_properties`, `office_finish`, `run_office_pandoc`, `build_office_pandoc`, `describe_fragment`, `print_office_check`, `check_docx_command`, `office_render_fragments`, `office_convert_asset`, `init_reference`.

Facts: 6 callers stay in pdfmd.py (re-exported); 18 pdfmd names read through `core`.

Note: `pdfmd_office` costs about 10 ms to import: keep heavy imports inside functions, so the re-export does not slow every start.

Tests: `test_docx_tables`, `test_indent_office`, `test_markup_word`, `test_office`, `test_office_latex`, `test_old_python_syntax`, `test_paper`, `test_raw`.

#### 26. `pdfmd_history` (existing package): 26 definitions, ~680 lines; done in 3.33.28 (`lib/pdfmd_history/backups.py`; the two `@timed` functions use `_timed`; `history_module()` stayed)

Definitions: `entry_line`, `notes_to_entries`, `entries_to_notes`, `backup_folders`, `document_versions`, `version_text`, `version_differs`, `restore_version`, `history_documents`, `linked_metadata`, `history_view_command`, `history_act`, `history_interactive`, `init_backups_command`, `history_command`, `backup_directory`, `backup_template`, `fill_backup_template`, `backup_name_regex`, `_plain_backup_patterns`, `backup_snapshots`, `backup_unchanged`, `backup_after_success`, `backup_pdf_pattern`, `backup_pdf_after_success`, `backup_summary`.

Constants that move with it (only this package reads them): `BACKUP_FORMATS`, `BACKUP_IGNORED_LINE_RE`, `HISTORY_SHOWN`, `LEGACY_BACKUP_DIRS`, `_COUNTER`, `_STRFTIME_PATTERNS`.

Facts: 5 callers stay in pdfmd.py (re-exported); 32 pdfmd names read through `core`.

Note: The lazy loader `history_module()` goes where nothing else needs it.

Tests: `test_atomic`, `test_backup_keep`, `test_backup_pdfs`, `test_backup_summary`, `test_history`, `test_partial_history`, `test_tables`, `test_versions`.

#### 27. `pdfmd_restore` (new package): 16 definitions, ~518 lines; done in 3.33.29 (`VERBOSE_OUTPUT` stayed, rebound with `global`; `pypdf` is `core.pypdf`; `yaml` is imported by the package)

Definitions: `folder_counts`, `restored_image_paths`, `restore_chain`, `restore_target_name`, `check_source_command`, `restore_from_pdf`, `restore_attachments`, `restore_attachments_in_place`, `restore_from_markdown`, `restore_front_matter`, `original_metadata_text`, `without_parts`, `text_holds_parts`, `is_global_layout_entry`, `assembled_origin`, `layout_from_source`.

Constants that move with it (only this package reads them): `RESTORE_CHAIN`.

Facts: 4 callers stay in pdfmd.py (re-exported); 30 pdfmd names read through `core`.

Tests: `test_attach`, `test_attach_format`, `test_attach_layers`, `test_kit_carry`, `test_standalone_source`.

#### 28. `pdfmd_parts` (new package): 32 definitions, ~699 lines; done in 3.33.30 (`FUZZY_LOOKUP` and both `DIV_FENCE_RE` bindings stayed; `Heading` moved; the banner above the section code moved with it)

Definitions: `chapter_order`, `parts_directory`, `collect_parts`, `part_slug`, `part_keys`, `NoPartMatches`, `NoHeadingMatches`, `select_parts`, `select_parts_and_sections`, `ScaffoldPlan`, `warn_shared_parts_folder`, `plan_scaffold`, `wrap_part`, `wrap_runs`, `scaffold_inputs`, `split_top_level_sections`, `slug_of`, `heading_parts`, `scan_headings`, `block_ids`, `scan_labelled_blocks`, `scan_items`, `parse_section_request`, `describe_heading`, `item_label`, `find_heading`, `outermost_headings`, `section_label`, `SectionPlan`, `section_source`, `plan_sections`, `split_into_parts`.

Constants that move with it (only this package reads them): `ATTRIBUTE_ID_RE`, `ATX_HEADING_RE`, `HEADING_ATTRIBUTES_RE`, `HEADING_FIELD_WORDS`, `Heading`, `PARTS_SKIP_DIRS`, `PART_FENCE`, `SETEXT_UNDERLINE_RE`, `TABLE_LINE_RE`.

Facts: 9 callers stay in pdfmd.py (re-exported); 22 pdfmd names read through `core`.

Tests: `test_ansi`, `test_calc`, `test_css_v2`, `test_direct`, `test_labels`, `test_native`, `test_office`, `test_partial_history`, `test_partial_provenance`, `test_sections`, `test_soffice_parts`, `test_symlinked_parts`, `test_typst_input`, `test_wikilinks`.

#### 29. `pdfmd_doctor` (new package): 9 definitions, ~377 lines; done in 3.33.31 (`TEX_FOUND_AT` and `TRANSLIT_PACKS` stayed, rebound with `global`; `__file__` is `core.__file__`)

Definitions: `tool_note`, `user_path_hint`, `pandoc_limits`, `folder_size`, `deep_checks`, `foreign_commands`, `doctor_report`, `completion_options`, `completion_script`.

Constants that move with it (only this package reads them): `DEEP_SAMPLE`, `PANDOC_FEATURES`.

Facts: 1 callers stay in pdfmd.py (re-exported); 41 pdfmd names read through `core`.

Tests: `test_compat`, `test_completion`, `test_doctor`, `test_install_python`, `test_setup`, `test_tool_locations`.

### Wave 4: the hard ones (Opus)

#### 30. `pdfmd_cache` (new package): 8 definitions, ~104 lines; done in 3.33.33 (`CACHE_LOCATIONS` (the parser's choices), `CACHE_MANIFEST`, `LOCAL_CACHE_DIRNAME` and `NOTED_PLACES` stayed, read by code that stays; `CACHE_LOCATION_CLI` stayed, rebound with `global`; `cache_root` is called as `core.cache_root()` inside the package)

Definitions: `cache_root`, `folder_is_writable`, `temporary_place`, `cache_location`, `document_cache_root`, `source_fingerprint`, `adopt_moved_cache`, `cache_directory`.

Constants that move with it (only this package reads them): `CACHE_LOCATION_NAMES`, `TEMPORARY_PLACES`.

Facts: 33 callers stay in pdfmd.py (re-exported); 9 pdfmd names read through `core`; calls to test-patched names inside the package: `cache_directory->cache_root`, `document_cache_root->cache_root`.

Note: 33 callers outside. Tests patch `pdfmd.cache_root` (5 files): inside the package, `document_cache_root` and `cache_directory` call it as `core.cache_root`.

Tests: `test_cache_location`, `test_config`, `test_css_v2`, `test_doc`, `test_header_includes`, `test_markup_callouts`, `test_markup_highlight`, `test_picture_cache_protocol`, `test_plot_cache`, `test_readonly_home`, `test_sections`, `test_show_comments`.

#### 31. `pdfmd_unicode` (existing package): 13 definitions, ~332 lines; done in 3.33.34 (in `fonts_choice.py`, deferred; `installed_font_families` is in `DEFERRED_NAMES`, as tests call its `.cache_clear()`; `reset_font_caches` stayed, rebinding `global`s, and clears the moved caches by name; `unicode_module()` stayed: `managed_index`, `install_fonts`, `uninstall_fonts` and others in `pdfmd.py`, `lib/pdfmd_lookup`, `lib/pdfmd_doctor` and `lib/pdfmd_routing` call it)

Definitions: `installed_font_families`, `font_missing`, `system_font_missing`, `default_monofont`, `fallback_font`, `preferred_font`, `font_args`, `unicode_code_text`, `unicode_forced`, `managed_fonts_css`, `check_fonts`, `describe_code_points`, `script_fallback`.

Constants that move with it (only this package reads them): `CODE_FONTS_HTML`, `CODE_FONTS_TYPST`, `DEFAULT_FONT`, `EMOJI_FAMILIES`, `MONOFONT_STAND_INS`, `SERIF_STAND_INS`, `UNICODE_ENGINES`.

Facts: 8 callers stay in pdfmd.py (re-exported); 21 pdfmd names read through `core`; calls to test-patched names inside the package: `check_fonts->preferred_font`, `font_args->system_font_missing`, `font_missing->system_font_missing`.

Note: Tests patch `system_font_missing` and `preferred_font`: inside the package, calls to them go through `core.`. The lazy loader `unicode_module()` goes.

Tests: `test_apple_emoji`, `test_ascii`, `test_font_retry_note`, `test_install_python`, `test_katex_scale`, `test_mathfont`, `test_probes`, `test_setup`, `test_tessdata`, `test_translit`, `test_unicode`.

#### 32. `pdfmd_install` (new package): 43 definitions, ~904 lines; done in 3.33.35 (`KATEX_PACKAGE` stayed: it is built from `KATEX_VERSION`, which stays, when `pdfmd.py` is loaded; `download_file` and `github_latest_release` are re-exported too, as tests patch them; `tarfile` and `zipfile` are imported at the package's top, as they were in `pdfmd.py`, which drops its own `import tarfile`; `urllib.request` stays inside the functions)

Definitions: `typst_asset_name`, `github_release_asset`, `download_file`, `extract_executable`, `install_typst`, `node_install_hint`, `node_asset_name`, `install_node`, `unpack_katex`, `katex_works`, `install_katex`, `mathjax_package_url`, `unpack_npm`, `mathjax_keeps_source`, `mathjax_keeps_font`, `install_mathjax_files`, `mathjax_works`, `ensure_node`, `install_mathjax`, `d2_asset_name`, `github_latest_release`, `install_d2`, `unpack_graphviz`, `write_graphviz_launchers`, `install_graphviz`, `install_diagram`, `calibre_asset_pattern`, `calibre_release_asset`, `release_asset_matching`, `calibre_package_manager`, `calibre_install_hint`, `safe_unpack_tar`, `detach_disk_image`, `install_calibre_dmg`, `install_calibre`, `tectonic_asset_pattern`, `install_tectonic`, `install_kind`, `uninstall_kind`, `kit_install_settings`, `install_kits`, `install_fonts`, `install_extra`.

Constants that move with it (only this package reads them): `CALIBRE_REPOSITORY`, `D2_REPOSITORY`, `D2_TARGETS`, `DIAGRAM_INSTALLS`, `GRAPHVIZ_COMMANDS`, `GRAPHVIZ_PACKAGE`, `GRAPHVIZ_SHA256`, `GRAPHVIZ_VERSION`, `INSTALL_SPECS`, `KATEX_KEPT`, `KATEX_SHA256`, `KIT_SOURCES_DEFAULT`, `MATHJAX_BUNDLE_FOLDERS`, `MATHJAX_BUNDLE_INPUT`, `MATHJAX_BUNDLE_KEPT`, `MATHJAX_FONT_SIZES`, `MATHJAX_REGISTRY`, `MATHJAX_SOURCE_SHA256`, `NODE_DIST`, `NODE_TARGETS`, `TECTONIC_REPOSITORY`, `TECTONIC_TARGETS`, `TYPST_REPOSITORY`, `TYPST_TARGETS`.

Facts: 3 callers stay in pdfmd.py (re-exported); 27 pdfmd names read through `core`; calls to test-patched names inside the package: `install_calibre->download_file`, `install_d2->d2_asset_name`, `install_d2->download_file`, `install_d2->github_latest_release`, `install_extra->install_extra`, `install_extra->install_tectonic`, `install_extra->install_typst`, `install_graphviz->download_file`, `install_katex->download_file`, `install_kits->download_file`, `install_mathjax_files->download_file`, `install_node->download_file`, `install_tectonic->download_file`, `install_typst->download_file`, `install_typst->github_release_asset`, `install_typst->typst_asset_name`.

Note: Tests patch eight of its functions (`download_file`, `github_release_asset`, `github_latest_release`, `install_typst`, `install_tectonic`, `install_extra`, `typst_asset_name`, `d2_asset_name`): the 16 caller-callee pairs above are 19 uses inside the package (15 calls, 4 `download_file` passed or taken as a default), all through `core.` (corrected in 3.33.35; this said six functions and 16 calls).

Tests: `test_engine_filters`, `test_formula`, `test_install_calibre`, `test_install_core_tex`, `test_install_diagram`, `test_install_ocr`, `test_install_python`, `test_kit_install`, `test_mathjax`, `test_native`, `test_packaging`, `test_tessdata`.

#### 33. `pdfmd_tex` (new package): 18 definitions, ~494 lines; done in 3.33.36 (the comments above `package_latex_keys`, `TEX_CAUSES` and `TEX_LOG_WRAP_WIDTH` and the banner of the direct `.tex` compile moved with them; the picture cache's protocol comment stayed above `CACHE_HANDSHAKE`; `render_plot_requests` and `compile_tex_direct` use `_timed`; `run_probe` and `which` are `core.X`)

Definitions: `is_latex_preamble`, `top_level_tikzpicture`, `wrap_latex_header_includes`, `package_latex_keys`, `document_latex_definitions`, `engine_failure_reason`, `tex_failure_cause`, `tex_wants_rerun`, `tex_log_dewrap`, `tex_log_failure_reason`, `tex_bibliography_tool`, `latex_engine_command`, `run_tex_engine`, `tex_tree_stamp`, `plot_preamble`, `plot_recorded_inputs`, `render_plot_requests`, `compile_tex_direct`.

Constants that move with it (only this package reads them): `AUX_CLEAN_SUFFIXES`, `MAX_TEX_DIRECT_PASSES`, `PLOT_CTX_MARGIN`, `PLOT_CTX_PLAIN`, `PLOT_CTX_TWICE`, `TEX_CAUSES`, `TEX_LOG_WRAP_WIDTH`, `TEX_PACKAGES`, `TEX_RERUN_TRIGGERS`.

Facts: 10 callers stay in pdfmd.py (re-exported); 14 pdfmd names read through `core`.

Tests: `test_header_includes`, `test_install_core_tex`, `test_kit_texinputs`, `test_package_helper`, `test_picture_cache_protocol`, `test_plot_cache`, `test_probes`, `test_tex_bin`, `test_tex_cause`, `test_texpackages`, `test_text_input`.

#### 34. `pdfmd_attach` (new package): 32 definitions, ~773 lines; done in 3.33.37 (`BIB_ATTACH_CLI`, `BUNDLE_CLI`, `BUNDLE_PACKAGES_CLI` and `CSL_ATTACH_CLI` stayed, rebound with `global`; `pypdf` is `core.pypdf`; `attach_source_after_success` uses `_timed`; the three `@lru_cache` functions are re-exported plainly; `pdfmd.py` lost its own `import zlib`)

Definitions: `folder_options_in_force`, `block_places`, `drop_blocks`, `drop_duplicate_blocks`, `inline_candidates`, `inline_blocks`, `attached_bundle_mode`, `layout_path`, `referenced_images`, `tex_distribution_roots`, `graphic_names_in`, `graphics_named_in`, `tex_tree_graphics`, `find_in_tex_tree`, `tex_names`, `tex_tree_dependencies`, `package_companions`, `bundle_reach`, `bundle_files`, `attachment_manifest`, `attached_source`, `resolve_bibliography_pruning`, `resolve_csl_attach`, `add_deflated_attachment`, `write_pdf_attachments`, `read_pdf_attachments`, `resolve_bundle_packages`, `attachment_requirements`, `csv_block_files`, `source_attachments`, `attach_source_after_success`, `keep_source_after_success`.

Constants that move with it (only this package reads them): `ATTACH_FORMAT_PLAIN`, `BUNDLE_IMAGE_SUFFIXES`, `BUNDLE_SKIP_SUFFIXES`, `CLASS_RE`, `FONT_KEYS`, `GLOBAL_LAYOUT_PATH`, `GRAPHIC_ARGUMENT_RE`, `GRAPHIC_SUFFIXES`, `INLINE_LIMIT`, `INLINE_ORDER`, `INLINE_SUFFIXES`, `MACRO_VALUE_RE`, `PACKAGE_RE`, `PATH_TOKEN_RE`, `PROVIDES_RE`, `RAW_REFERENCE_RES`, `REFERENCE_EXTENSIONS`, `SCANNED_SUFFIXES`, `TEX_INPUT_RE`, `TEX_SOURCE_SUFFIXES`, `TEX_TREE_SCAN_LIMIT`.

Facts: 10 callers stay in pdfmd.py (re-exported); 62 pdfmd names read through `core`.

Tests: `test_atomic`, `test_attach`, `test_attach_format`, `test_attach_layers`, `test_check_source`, `test_edit_pdf`, `test_embedding`, `test_kit_carry`, `test_pdf_input`, `test_polish`, `test_standalone_source`.

#### 35. `pdfmd_assemble` (new package): 23 definitions, ~995 lines; done in 3.33.38 (`_RESOURCE_OWNER` stayed as state, read and written as `core._RESOURCE_OWNER`; `write_assembled_markdown` uses `_timed`; the `base64` and `binascii` imports left `pdfmd.py`)

Definitions: `mark_assembled`, `used_citation_keys`, `filter_bibliography`, `assemble_markdown_text`, `write_assembled_markdown`, `EmbedPlan`, `render_embedded_block`, `render_embedded_file`, `safe_relative_path`, `parse_embedded_blocks`, `trust_store_path`, `trusted_hashes`, `remember_trusted`, `split_preamble_parts`, `unpack_assembled`, `slim_assembled`, `embedded_resources`, `literal_block`, `strip_embedded_option_names`, `relative_filter_path`, `lua_checks_format`, `apply_lua_filters`, `embed_into_text`.

Constants that move with it (only this package reads them): `ASSEMBLED_COMMENT`, `BIB_LINK_RE`, `BIB_SUFFIXES`, `FILE_ONLY_OPTION_KEYS`, `LATEX_CITE_RE`, `PANDOC_CITE_RE`, `PARTIAL_KEY`.

Facts: 13 callers stay in pdfmd.py (re-exported); 53 pdfmd names read through `core`; rebinds globals: `embedded_resources` -> _RESOURCE_OWNER.

Note: `embedded_resources` rebinds the global `_RESOURCE_OWNER`: it becomes `core._RESOURCE_OWNER = ...` (the state stays in pdfmd.py).

Tests: `test_attach`, `test_config`, `test_embedding`, `test_standalone_source`.

#### 36. `pdfmd_native` (new package): 40 definitions, ~1166 lines

Definitions: `csv_cut_advice`, `native_note`, `native_lose`, `escape_markup`, `MathText`, `chunks_markup`, `chunks_width`, `centred_math`, `inline_math`, `stacked_math`, `mathtext_form`, `NativeSource`, `author_names`, `csv_extension_delimiter`, `csv_guess_delimiter`, `csv_keep`, `csv_alignments`, `csv_separator_alignments`, `csv_div_table`, `strip_html_comments`, `convert_math_items`, `protect_dollars`, `normalise_gfm`, `title_block`, `ignored_front_matter_keys`, `native_page`, `native_paper`, `native_landscape`, `native_paper_note`, `native_font_size`, `native_order`, `load_inkmd`, `set_pdf_info`, `captured_logs`, `report_messages`, `render_native`, `calibre_page_options_for`, `render_calibre_markdown`, `convert_native`, `describe_native_changes`.

Constants that move with it (only this package reads them): `CALIBRE_MARKDOWN_EXTENSIONS`, `CITATION_RE`, `CODE_SPAN_RE`, `CSV_ALIGNMENTS`, `CSV_DIV_LINE_RE`, `CSV_SEPARATOR_CELL_RE`, `DISPLAY_IN_TEXT_RE`, `DIV_ATTRIBUTE_RE`, `DIV_CLOSE_RE`, `EMOJI_RE`, `FOOTNOTE_DEF_RE`, `FOOTNOTE_REF_RE`, `HEADING_ATTR_RE`, `HTML_COMMENT_RE`, `IMAGE_ATTR_RE`, `INLINE_MATH_CAPTURE_RE`, `INLINE_MATH_RE`, `MARKDOWN_ESCAPE_RE`, `MATHTEXT_REWRITES`, `MATH_ACCENTS`, `MATH_BINARY`, `MATH_BLACKBOARD`, `MATH_BOLD_COMMANDS`, `MATH_DROP`, `MATH_DROP_ARGUMENT`, `MATH_ESCAPES`, `MATH_FUNCTIONS`, `MATH_GREEK`, `MATH_MATRICES`, `MATH_RELATIONS`, `MATH_SYMBOLS`, `MATH_TEXT_COMMANDS`, `NATIVE_META_KEYS`, `NATIVE_PAPER_NOTED`, `NATIVE_READERS`, `NATIVE_SOURCE_SUFFIXES`, `NO_BREAK_SPACE`, `PAGE_BREAK_COMMENT_RE`, `PAGE_BREAK_MARKUP`, `PAGE_BREAK_RE`, `PAPER_SIZES`, `SUBSCRIPTS`, `SUPERSCRIPTS`, `TEX_BEGIN_RE`, `TEX_COMMAND_LINE_RE`, `TEX_MATH_ENVIRONMENTS`.

Facts: 2 callers stay in pdfmd.py (re-exported); 37 pdfmd names read through `core`.

Note: CLAUDE.md's "Vendored inkmd and the native tier" names pdfmd.py's section after `dependency_report()`: reword it in the same commit.

Tests: `test_calibre_markdown`, `test_csv_switch`, `test_csv_table`, `test_native`, `test_pagebreak`.

#### 37. `pdfmd_args` (new package): 7 definitions, ~957 lines

Definitions: `csv_note_argument`, `csv_count_argument`, `table_keep_argument`, `calc_round_argument`, `calc_digits_argument`, `pdfmd_labels_modes`, `build_parser`.

Constants that move with it (only this package reads them): `BUILD_LOG_MODES`, `STOP_STAGES`.

Facts: 7 callers stay in pdfmd.py (re-exported); 23 pdfmd names read through `core`.

Note: `build_parser` (the whole argparse tree). `--help` of every topic must be byte-identical; `test_docs_consistency` and `test_help*` read it.

Tests: `test_doc`, `test_help`, `test_ranking_generated`, `test_setup`.
