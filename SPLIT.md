A comprehensive survey of [`pdfmd.py`](file://~/dev/py/pdfmd/pdfmd.py) (currently **30,868 lines**, ~1.75 MB, 1,047 functions/classes) was conducted to identify all candidate code blocks that can be extracted to [`lib/`](file://~/dev/py/pdfmd/lib), matching the precedent set when modules like `pdfmd_report`, `pdfmd_batch`, `pdfmd_tables`, etc., were extracted.

In total, **~17,700 lines (>57% of `pdfmd.py`)** can be cleanly moved into `lib/`:
1. **~5,550 lines** can be absorbed directly into **existing packages** in `lib/` that currently hold only partial implementations.
2. **~12,150 lines** form cohesive, decoupled subsystems that can become **new packages** in `lib/`.

---

## 1. Code to Move into Existing Packages in `lib/`

Many packages under `lib/` were previously introduced, but their high-level commands, CLI integrations, or data processing pipelines were left inside `pdfmd.py`.

| Target Package | Line Range in `pdfmd.py` | Lines | Key Functions / Classes | What Can Be Moved |
| :--- | :--- | :--- | :--- | :--- |
| [`lib/pdfmd_history/`](file://~/dev/py/pdfmd/lib/pdfmd_history) | [15956–17456](file://~/dev/py/pdfmd/pdfmd.py#L15956-L17456) | **~1,500** | `backup_directory`, `backup_template`, `fill_backup_template`, `backup_snapshots`, `backup_after_success`, `backup_pdf_after_success`, `backup_summary`, `history_view_command`, `history_act`, `history_interactive`, `init_backups_command`, `history_command` | Snapshot creation, template formatting, backup rotation, and interactive CLI history commands (`--history`, `--history-diff`, `--history-restore`, `--init-backups`). |
| [`lib/pdfmd_office/`](file://~/dev/py/pdfmd/lib/pdfmd_office) | [8504–9224](file://~/dev/py/pdfmd/pdfmd.py#L8504-L9224), [9744–9871](file://~/dev/py/pdfmd/pdfmd.py#L9744-L9871) | **~845** | `office_package_folders`, `office_defaults_sources`, `find_office_profile`, `find_reference_doc`, `OfficeArguments`, `office_properties`, `office_finish`, `run_office_pandoc`, `build_office_pandoc`, `check_docx_command`, `office_render_fragments`, `init_reference` | Office Pandoc command runner, Word/ODT reference document resolution, fragment rendering, and `--check-docx` / `--init-reference`. |
| [`lib/pdfmd_kits/`](file://~/dev/py/pdfmd/lib/pdfmd_kits) | [7886–8476](file://~/dev/py/pdfmd/pdfmd.py#L7886-L8476) | **~590** | `package_places`, `kpsewhich_locate`, `read_package_helper`, `kit_package_folders`, `kits_report`, `kit_header_insert`, `kit_header_settle`, `kit_header_resolve`, `kit_carried_files`, `kit_cache_tex` | Kit header resolution, TeX search path setup, package helper integration, and the `--kits` report runner. |
| [`lib/pdfmd_unicode/`](file://~/dev/py/pdfmd/lib/pdfmd_unicode) | [1675–1760](file://~/dev/py/pdfmd/pdfmd.py#L1675-L1760), [12519–13046](file://~/dev/py/pdfmd/pdfmd.py#L12519-L13046) | **~614** | `installed_font_families`, `font_missing`, `system_font_missing`, `default_monofont`, `fallback_font`, `preferred_font`, `font_args`, `script_fallback`, `check_fonts`, `managed_fonts_css` | Fontconfig queries, font stand-in resolution, per-script fallback filter/header generation, and `--check-fonts`. |
| [`lib/pdfmd_tables/`](file://~/dev/py/pdfmd/lib/pdfmd_tables) | [2746–2995](file://~/dev/py/pdfmd/pdfmd.py#L2746-L2995), [17474–17598](file://~/dev/py/pdfmd/pdfmd.py#L17474-L17598) | **~370** | `csv_defaults`, `csv_table_filter_args`, `table_keep_metadata`, `spreadsheet_args`, `tables_command` | CSV block argument generation, table keep metadata, and `--extract-tables` / `--expand-tables` rewriting commands. |
| [`lib/pdfmd_buildinfo/`](file://~/dev/py/pdfmd/lib/pdfmd_buildinfo) | [15628–15931](file://~/dev/py/pdfmd/pdfmd.py#L15628-L15931) | **~304** | `begin_timer`, `timed`, `attach_time`, `time_breakdown`, `_RecordTee`, `BuildRecorder`, `last_build_command` | Build step timing, `--verbose` time breakdown reporting, log tees, build log recording, and `--last-build`. |
| [`lib/pdfmd_obsidian/`](file://~/dev/py/pdfmd/lib/pdfmd_obsidian) | [3116–3385](file://~/dev/py/pdfmd/pdfmd.py#L3116-L3385) | **~270** | `vault_app_setting`, `single_newline_mode`, `vault_root`, `find_embedded_image`, `embed_source`, `embed_filter_args` | Obsidian vault configuration parsing (`app.json`), embed image search indexing, and embed filter arguments. |
| [`lib/pdfmd_ranking/`](file://~/dev/py/pdfmd/lib/pdfmd_ranking) | [13446–13640](file://~/dev/py/pdfmd/pdfmd.py#L13446-L13640) | **~195** | `ranking_layers`, `ranking_clashes`, `bare_ranking`, `priority_candidates`, `which_command` | Multi-layer ranking resolution, clash detection, and `--which` CLI runner. |
| [`lib/pdfmd_check/`](file://~/dev/py/pdfmd/lib/pdfmd_check) | [9480–9668](file://~/dev/py/pdfmd/pdfmd.py#L9480-L9668) | **~189** | `bibliography_file_keys`, `check_bibliography`, `calc_check_records`, `check_documents`, `check_command` | High-level `--check` linter dispatch, bibliography key validation, and calculator syntax verification. |
| [`lib/pdfmd_crop/`](file://~/dev/py/pdfmd/lib/pdfmd_crop) | [9255–9418](file://~/dev/py/pdfmd/pdfmd.py#L9255-L9418) | **~164** | `picture_target`, `picture_build`, `picture_sources`, `picture_one`, `multi_target_command`, `picture_command` | Picture export pipeline and format dispatch (`--crop` and `--to png,svg,tiff,jpg`). |
| [`lib/pdfmd_setup/`](file://~/dev/py/pdfmd/lib/pdfmd_setup) | [5380–5404](file://~/dev/py/pdfmd/pdfmd.py#L5380-L5404), [11541–11700](file://~/dev/py/pdfmd/pdfmd.py#L11541-L11700) | **~185** | `setup_sources`, `setup_command`, `user_path_command`, `maybe_hint_setup` | Interactive `--setup` runner, Windows user path manager (`--user-path`), and setup hint triggers. |
| [`lib/pdfmd_docs/`](file://~/dev/py/pdfmd/lib/pdfmd_docs) | [11349–11477](file://~/dev/py/pdfmd/pdfmd.py#L11349-L11477) | **~129** | `document_file`, `document_headings`, `document_section`, `search_documents`, `render_document`, `doc_command` | Built-in documentation search, heading indexer, HTML documentation cache, and `--doc` CLI runner. |
| [`lib/pdfmd_css/`](file://~/dev/py/pdfmd/lib/pdfmd_css) | [19512–19637](file://~/dev/py/pdfmd/pdfmd.py#L19512-L19637) | **~126** | `css_additions`, `css_heading_latex`, `css_heading_args` | Translating CSS heading rules (`font-family`, `font-weight`, `color`) into LaTeX `titlesec` definitions. |
| [`lib/pdfmd_flat/`](file://~/dev/py/pdfmd/lib/pdfmd_flat) | [4642–4739](file://~/dev/py/pdfmd/pdfmd.py#L4642-L4739) | **~98** | `flat_settings`, `flat_writer`, `flat_filter_args`, `split_ascii_target`, `ascii_missing`, `ascii_filter_args`, `ascii_finish` | CLI argument synthesis for flat Markdown and ASCII builds (`--to ascii`, `-o x.ascii.txt`). |
| [`lib/pdfmd_serve/`](file://~/dev/py/pdfmd/lib/pdfmd_serve) | [13670–13753](file://~/dev/py/pdfmd/pdfmd.py#L13670-L13753) | **~84** | `serve_main_document`, `serve_discovered`, `serve_live_filters`, `serve_command`, `api_command` | Dispatcher glue connecting CLI `--serve` and `--api` to `pdfmd_serve.core.Core`. |
| [`lib/pdfmd_ansi/`](file://~/dev/py/pdfmd/lib/pdfmd_ansi) | [4783–4864](file://~/dev/py/pdfmd/pdfmd.py#L4783-L4864) | **~82** | `ansi_width_argument`, `ansi_columns`, `ansi_colour_on`, `ansi_document_text`, `ansi_finish`, `ansi_without_pandoc` | Pandoc JSON AST to styled terminal text translation and fallback parser when Pandoc is unavailable. |
| [`lib/pdfmd_templates/`](file://~/dev/py/pdfmd/lib/pdfmd_templates) | [9675–9740](file://~/dev/py/pdfmd/pdfmd.py#L9675-L9740) | **~66** | `git_user_name`, `init_command` | Document template listing and scaffolding (`pdfmd --init [TEMPLATE] [NAME]`). |

*Subtotal:* **~5,550 lines**

---

## 2. Code to Move into NEW Packages in `lib/`

These represent substantial, self-contained subsystems that do not fit neatly into existing packages and can be spun off into new `pdfmd_*` modules in `lib/`:

### A. Core External & Secondary Feature Packages

1. **`lib/pdfmd_install/`** ([lines 9900–11200](file://~/dev/py/pdfmd/pdfmd.py#L9900-L11200), **~1,300 lines**)
   - **Functions**: `download_file`, `extract_executable`, `github_release_asset`, `github_latest_release`, `install_typst`, `install_node`, `ensure_node`, `install_katex`, `install_mathjax`, `install_d2`, `install_graphviz`, `install_calibre` (and macOS DMG handling), `install_tectonic`, `install_extra`, `install_kind`, `uninstall_kind`.
   - **Rationale**: Completely independent network/archive tool downloader and verifier (SHA-256 validation). Has zero runtime dependencies on document parsing or PDF compilation.

2. **`lib/pdfmd_native/`** ([lines 5809–7316](file://~/dev/py/pdfmd/pdfmd.py#L5809-L7316), **~1,508 lines**)
   - **Functions / Classes**: `MathText` (252-line class converting LaTeX math to readable Unicode text/matplotlib), `normalise_gfm` (225-line AST normalizer), `NativeSource`, `centred_math`, `inline_math`, `stacked_math`, `mathtext_form`, `csv_div_table`, `strip_html_comments`, `convert_math_items`, `protect_dollars`, `render_native`, `render_calibre_markdown`, `convert_native`.
   - **Rationale**: The entire Pandoc-less fallback rendering tier. `pdfmd_inkmd` is vendored, but all AST transformation and math formatting logic currently sits in `pdfmd.py`.

3. **`lib/pdfmd_assemble/`** or **`lib/pdfmd_embed/`** ([lines 19692–21450](file://~/dev/py/pdfmd/pdfmd.py#L19692-L21450), **~1,759 lines**)
   - **Functions / Classes**: `assemble_markdown_text`, `write_assembled_markdown`, `EmbedPlan`, `render_embedded_block`, `render_embedded_file`, `parse_embedded_blocks`, `trust_store_path`, `trusted_hashes`, `remember_trusted`, `unpack_assembled` (196 lines), `slim_assembled`, `embedded_resources`, `embed_into_text` (349 lines).
   - **Rationale**: The `--stop-at markdown`, `--embed-metadata`, and `--unpack` pipeline. Implements fenced `{=pdfmd}` block rendering, trust stores for embedded Lua filters, and unbundling.

4. **`lib/pdfmd_scaffold/`** or **`lib/pdfmd_parts/`** ([lines 18027–19200](file://~/dev/py/pdfmd/pdfmd.py#L18027-L19200), **~1,174 lines**)
   - **Functions / Classes**: `chapter_order`, `parts_directory`, `collect_parts`, `part_slug`, `select_parts`, `select_parts_and_sections`, `ScaffoldPlan`, `plan_scaffold`, `wrap_part`, `wrap_runs`, `scaffold_inputs`, `split_top_level_sections`, `scan_headings`, `scan_items`, `find_heading`, `section_source`, `plan_sections`, `split_into_parts`.
   - **Rationale**: Multi-part document assembly, scaffold division, and section targeting (`pdfmd doc#section`). Complements `pdfmd_report` and `pdfmd_batch`.

5. **`lib/pdfmd_attach/`** or **`lib/pdfmd_bundle/`** ([lines 25454–26399](file://~/dev/py/pdfmd/pdfmd.py#L25454-L26399), **~946 lines**)
   - **Functions**: `referenced_images`, `tex_distribution_roots`, `graphic_names_in`, `tex_tree_dependencies`, `bundle_files`, `attachment_manifest`, `attached_source`, `add_deflated_attachment`, `write_pdf_attachments`, `read_pdf_attachments`, `source_attachments`, `attach_source_after_success`, `keep_source_after_success`.
   - **Rationale**: Post-build packaging that attaches the source code and dependency tree into the generated PDF (`--attach-source`, `--bundle`).

6. **`lib/pdfmd_tex/`** or **`lib/pdfmd_latex/`** ([lines 11711–12231](file://~/dev/py/pdfmd/pdfmd.py#L11711-L12231), [21951–22251](file://~/dev/py/pdfmd/pdfmd.py#L21951-L22251), [23505–23758](file://~/dev/py/pdfmd/pdfmd.py#L23505-L23758), **~809 lines**)
   - **Functions**: `wrap_latex_header_includes`, `document_latex_definitions`, `is_latex_preamble`, `latex_engine_command`, `run_tex_engine`, `compile_tex_direct`, `engine_failure_reason`, `tex_failure_cause`, `tex_log_dewrap`, `tex_log_failure_reason`, `tex_tree_stamp`, `plot_preamble`, `render_plot_requests`.
   - **Rationale**: Direct TeX engine compilation, TeX `.log` un-wrapping / error diagnostics, and standalone plot cache management.

7. **`lib/pdfmd_restore/`** ([lines 27099–27619](file://~/dev/py/pdfmd/pdfmd.py#L27099-L27619), **~521 lines**)
   - **Functions**: `restore_chain`, `restore_target_name`, `check_source_command`, `restore_from_pdf`, `restore_attachments_in_place`, `restore_from_markdown`, `restore_front_matter`, `layout_from_source`.
   - **Rationale**: Reconstructs Markdown sources, preambles, and sibling files from compiled PDFs (`pdfmd --restore`).

8. **`lib/pdfmd_bridge/`** ([lines 23859–24319](file://~/dev/py/pdfmd/pdfmd.py#L23859-L24319), **~461 lines**)
   - **Functions**: `run_soffice_convert`, `convert_office_direct`, `convert_via_soffice_bridge`, `start_soffice_job`, `calibre_html_command`, `calibre_page_options`, `run_calibre`, `run_calibre_convert`, `browser_page_css`, `run_browser_print`.
   - **Rationale**: Headless converter bridges that invoke LibreOffice, Calibre `ebook-convert`, or headless Chrome/Chromium/Edge for printing.

9. **`lib/pdfmd_lookup/`** ([lines 13049–13443](file://~/dev/py/pdfmd/pdfmd.py#L13049-L13443), **~395 lines**)
   - **Functions / Classes**: `latin_candidates`, `cyrillic_candidates`, `strip_lookup_suffix`, `find_wildcard_markdown`, `lookup_key`, `lookup_query_keys`, `LookupAmbiguous`, `rank_lookup`, `lookup_fields`, `priority_enabled`, `source_markdown`, `document_priority`.
   - **Rationale**: Bare document name fuzzy matching, transliteration cross-matching, and wildcard resolution.

10. **`lib/pdfmd_pdfimages/`** or **`lib/pdfmd_extract/`** ([lines 26416–26715](file://~/dev/py/pdfmd/pdfmd.py#L26416-L26715), **~300 lines**)
    - **Functions**: `png_chunk`, `encode_png`, `file_picture_size`, `pdf_pictures`, `match_images_to_pdf`, `samples_to_png`, `form_to_pdf`, `extract_pdf_images`, `rewrite_tex_image_paths`, `rewrite_image_paths`.
    - **Rationale**: Low-level PDF stream parsing to extract raster and vector figures back into image files.

11. **`lib/pdfmd_polish/`** ([lines 27640–27929](file://~/dev/py/pdfmd/pdfmd.py#L27640-L27929), **~290 lines**)
    - **Functions**: `parse_hf_template`, `fill_hf_field`, `markdown_headings`, `search_form`, `locate_headings`, `outline_entries`, `hf_overlay`, `local_file_of_link`, `polish_pdf`.
    - **Rationale**: Post-processing PDF modifications: running header/footer overlay via `pypdf`, outline/bookmark injection, and hyperlink path normalization.

12. **`lib/pdfmd_foreign/`** or **`lib/pdfmd_compat/`** ([lines 27946–28234](file://~/dev/py/pdfmd/pdfmd.py#L27946-L28234), **~289 lines**)
    - **Functions**: `mdpdf_translate`, `mdpdf_main`, `md2pdf_translate`, `md2pdf_main`, `inkmd_translate`, `inkmd_main`, `batchmd_translate`, `batchmd_main`, `pan_tec_translate`, `pan_tec_main`.
    - **Rationale**: Compatibility CLI entrypoints that simulate external tools (`mdpdf`, `md2pdf`, `pan-tec`).

13. **`lib/pdfmd_comments/`** ([lines 19793–20080](file://~/dev/py/pdfmd/pdfmd.py#L19793-L20080), **~288 lines**)
    - **Functions / Classes**: `scan_comment_line`, `strip_markdown_comments`, `CommentPolicy`, `comment_kind_set`, `parse_comment_policy`, `tex_comment_start`, `strip_tex_comments`, `strip_xml_comments`.
    - **Rationale**: Multi-format comment stripping (Markdown HTML comments, TeX `%` comments, XML/CSL comments).

14. **`lib/pdfmd_routing/`** or **`lib/pdfmd_ocr/`** ([lines 26733–27092](file://~/dev/py/pdfmd/pdfmd.py#L26733-L27092), **~360 lines**)
    - **Functions**: `batchocr_spec`, `find_batchocr`, `install_ocr_tools`, `route_ebook_input`, `route_pdf_input`, `route_text_input`.
    - **Rationale**: OCR pre-processing and input format routing for non-Markdown formats.

15. **`lib/pdfmd_doctor/`** ([lines 7525–7778](file://~/dev/py/pdfmd/pdfmd.py#L7525-L7778), **~254 lines**)
    - **Functions**: `foreign_commands`, `doctor_report`, `deep_checks`, `completion_options`, `completion_script`.
    - **Rationale**: `--doctor` diagnostic report generator and shell completion script generators for bash, zsh, and fish.

16. **`lib/pdfmd_cache/`** ([lines 22347–22599](file://~/dev/py/pdfmd/pdfmd.py#L22347-L22599), **~253 lines**)
    - **Functions**: `cache_root`, `folder_is_writable`, `temporary_place`, `cache_location`, `document_cache_root`, `source_fingerprint`, `adopt_moved_cache`, `cache_directory`.
    - **Rationale**: Global vs. local document cache management, CACHEDIR.TAG handling, and adoption of moved project directories.

17. **`lib/pdfmd_view/`** ([lines 4885–5037](file://~/dev/py/pdfmd/pdfmd.py#L4885-L5037), **~153 lines**)
    - **Functions**: `view_child_arguments`, `view_stdin_file`, `view_sources`, `stdin_build`, `view_wants_pager`, `run_pager`, `terminal_view`.
    - **Rationale**: Terminal viewer (`--view`) and pager integration.

18. **`lib/pdfmd_hybrid/`** ([lines 28432–28521](file://~/dev/py/pdfmd/pdfmd.py#L28432-L28521), **~90 lines**)
    - **Functions**: `resolve_hybrid`, `odf_source_for`, `attach_hybrid`, `hybrid_after_success`.
    - **Rationale**: Embedding editable LibreOffice ODF files into the output PDF (`--hybrid`).

19. **`lib/pdfmd_cli_parser/`** ([lines 28821–29747](file://~/dev/py/pdfmd/pdfmd.py#L28821-L29747), **~927 lines**)
    - **Functions**: `build_parser`.
    - **Rationale**: The huge `argparse` tree configuring all command-line flags and help text.

20. **`lib/pdfmd_watch/`** ([lines 29753–29826](file://~/dev/py/pdfmd/pdfmd.py#L29753-L29826), **~74 lines**)
    - **Functions**: `watch_signature`, `pinned_watch_argv`, `run_watch`.
    - **Rationale**: Continuous re-compilation file watcher.

*Subtotal:* **~12,150 lines**

---

## 3. What Should REMAIN in `pdfmd.py`

To preserve `pdfmd`'s role as the central CLI entry point, executable script, and public Python API, the following components should remain in `pdfmd.py`:

1. **Module Docstring & Version** ([lines 1–1674](file://~/dev/py/pdfmd/pdfmd.py#L1-L1674)): The comprehensive authoritative guide, changelog reference, and `PDFMD_VERSION`.
2. **Path Setup**: Ensuring `lib/` is on `sys.path` when running from checkout.
3. **Core Pipeline Orchestrator**: `convert_one` and the core Pandoc command execution loop `_convert_one_core` ([lines 24491–25340](file://~/dev/py/pdfmd/pdfmd.py#L24491-L25340)), coordinating which filters and engines to invoke.
4. **Main CLI Dispatch**: `main()` and `run_main()` ([lines 29906–30766](file://~/dev/py/pdfmd/pdfmd.py#L29906-L30766)), directing traffic to the respective modules.
5. **Public Python API**: `convert_file`, `convert_text`, `PdfmdError` ([lines 30784–30864](file://~/dev/py/pdfmd/pdfmd.py#L30784-L30864)).
6. **Backward-Compatibility Re-exports**: Over 550 tests directly access `pdfmd.<function_name>`; keeping lightweight aliases in `pdfmd.py` ensures zero breakage across the 182-file test suite.

---

## 4. Migration & Architecture Guidelines

When extracting these modules in future commits, follow the architectural conventions established in `CHANGELOG.md` (commit `e308bde` / entry 3ev):

- **The `core` pattern**: Pass the `pdfmd` module instance to extracted functions (e.g., `run(core, ...)`) rather than having submodules re-import `pdfmd`. This avoids circular imports and prevents duplicate copies of module-level state (`AUTO_LOG`, `CITEPROC_DISABLED`).
- **Packaging registration**: Each new package folder `lib/pdfmd_<name>` must be registered in:
  1. [`pyproject.toml`](file://~/dev/py/pdfmd/pyproject.toml): `packages` list and `[tool.setuptools.package-dir]`.
  2. [`scripts/build_zipapp.py`](file://~/dev/py/pdfmd/scripts/build_zipapp.py): `PACKAGES` tuple.
  3. Checked by [`tests/test_packaging.py`](file://~/dev/py/pdfmd/tests/test_packaging.py) (`test_every_package_is_mapped_to_lib_and_the_root_holds_none`).
- **Zero behavior change**: Retain exact signatures and behavior so `pdfmd` CLI invocations and tests produce byte-identical output.