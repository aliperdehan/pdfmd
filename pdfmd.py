#!/usr/bin/env python3
"""Convert Markdown documents to PDF (or other formats) with Pandoc.

Run a document:
    pdfmd report.md
    pdfmd report.md -o report.html
    pdfmd book -r -o book.pdf

Run this checkout:
    python3 scripts/pdfmd report.md
    python3 pdfmd.py report.md

Read the full reference:
    pdfmd --doc reference
    pdfmd --doc reference --print
    pdfmd --doc reference --path

The reference is docs/reference.md in a checkout and ships with installed
copies and the zipapp. Its sections describe input and output formats,
document lookup, metadata, rendering, parts, caches and build records.

Use pdfmd --help for command-line options and --help TOPIC for one subject.
Use pdfmd --doc for the other bundled documents, including worked recipes.
The Python API exports convert_file, convert_text, pdfmd_version and PdfmdError.
"""
from __future__ import annotations

# Versioned from here on -- see CHANGELOG.md next to this file.
#
# BEFORE EDITING THIS FILE: read CLAUDE.md next to this file first. In
# short -- make sure everything is committed in git (`git status` clean)
# before changing anything, and
# add a CHANGELOG.md entry (bump PDFMD_VERSION below) IN THE SAME
# EDIT, not after. This is a shared dependency across multiple, unrelated
# Markdown-to-PDF pipelines (nulabreport is one, but not the only one) --
# CLAUDE.md explains why a fix that looks scoped to one project's document
# can still break another, and why a fix should be verified through the
# full `pdfmd` pipeline, not just by compiling the `.tex` it produced.
#
# This script began as a one-line `pandoc file.md -o file.pdf` wrapper and
# was revised many times since, across ChatGPT, ChatGPT Codex, Claude Chat,
# Cowork, and Claude Code sessions, with no version marker or changelog kept
# at any point -- there is no reliable "v1.x" history left to backfill,
# only inconsistent backups/pdfmd.py.bak-* snapshots from a handful of
# points in that history. Rather than fabricate a precise-looking but
# unreliable 1.x history from those gaps, versioning restarts at 2.0.0 here
# (2026-09-16, the author's call) as an honest baseline: this is where real
# changelog tracking begins, not a claim about how many changes preceded it.

PDFMD_VERSION = "3.33.284"
import importlib.util
import json  # noqa: F401 -- retained for the unchanged start-up module set (phase 2 move 17)
import platform  # noqa: F401 -- preserve startup and the public module attribute
import os  # noqa: F401 -- preserve startup and the public module attribute
import shutil  # noqa: F401 -- preserve startup and the public module attribute
import subprocess
import sys
import time  # noqa: F401 -- read as pdfmd.time by tests/test_install_calibre.py

if sys.version_info < (3, 9):
    raise SystemExit(f"pdfmd needs Python 3.9 or newer (this is {sys.version.split()[0]}). "
                     "Install it with `pipx install pdfmd-cli`, "
                     "which picks a suitable Python, or run pdfmd.py with a newer python3.")
import inspect  # noqa: F401 -- read as core.inspect by lib/pdfmd_bridge/odt.py and as pdfmd.inspect by tests
from pathlib import Path
from shutil import which  # noqa: F401 -- retain the patched core lookup and startup
import tempfile


# A checkout keeps the pdfmd_* packages in lib/ beside this file; an installed copy has them in site-packages and a zipapp at
# its root, where there is no lib/ to add. Resolved, so the symlink ~/dev/python-projects/pdfmd.py finds the real lib/.
try:
    _checkout_lib = Path(__file__).resolve().parent / "lib"
    if _checkout_lib.is_dir() and str(_checkout_lib) not in sys.path:
        sys.path.insert(0, str(_checkout_lib))
except (OSError, RuntimeError):
    pass

# pdfmd.py needs its packages from 3.33 on (the author, 2026-11-09): a copy without lib/ stops here and says why.
if importlib.util.find_spec("pdfmd_comments") is None:
    raise SystemExit("pdfmd: this pdfmd.py has no lib/ folder beside it, and the pdfmd_* packages it needs are not "
                     "installed; keep pdfmd.py together with its lib/ folder, or install pdfmd: pipx install pdfmd-cli")

from pdfmd_base import (BUILD, atomic_write_bytes, atomic_write_pdf, atomic_write_text, natural_key, noted,  # noqa: E402, F401 -- atomic_write_bytes and split_command are read by tests and lib/
                        own_python_folder, read_text_best_effort, read_text_or_none, record_note, sha1_file, sha256_text,
                        split_command, timed, vprint, write_text_lf)

# behind the Python's own packages, before the optional ones below are imported
try:
    if own_python_folder().is_dir() and str(own_python_folder()) not in sys.path:
        sys.path.append(str(own_python_folder()))
except (OSError, RuntimeError):          # a home that cannot be read, or none at all (a sandbox): nothing installed there
    pass

try:
    from pdfmd_yaml_support import yaml
except ImportError:
    yaml = None

def lazy_import(name: str):
    """The module `name`, loaded when it is first used, or None when it is not installed. pypdf alone took about half of
    every start (v3.32.55), and most runs never touch a PDF's insides. A loader that cannot load lazily (zipimport before
    Python 3.10) loads it now."""
    if name in sys.modules:
        return sys.modules[name]
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec is None or spec.loader is None:
        return None
    try:
        loader = importlib.util.LazyLoader(spec.loader)
    except TypeError:
        try:
            return importlib.import_module(name)
        except ImportError:
            return None
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


pypdf = lazy_import("pypdf")


# -- The packages split out of this file (SPLIT.md, entry 3fi) --------------------
# Each one reads pdfmd's own helpers and state as `core.X` when it runs and never imports pdfmd: run as a script this file
# is `__main__`, and a second import would be a second copy with its own state. `core` is lib/pdfmd_base's one object for
# every package, bound to this module below. The names below are re-exported, so `pdfmd.x` keeps working for the code that
# stays here, the tests and lib/.
def load_package(name: str):
    """The module `name` (a package or one module of it), imported now; its `core` is this module (lib/pdfmd_base)."""
    return importlib.import_module(name)


def deferred(module: str, name: str):
    """A stand-in for the function `name` of `module`, a package that pdfmd.py does not load at start (SPLIT.md, step 6):
    the first call loads it, and every call goes to the real function. pdfmd.py's own calls keep their bare names."""
    def stand_in(*args, **kwargs):
        return getattr(load_package(module), name)(*args, **kwargs)
    stand_in.__name__ = stand_in.__qualname__ = name
    stand_in.__doc__ = f"`{module}.{name}`, loaded on its first call."
    return stand_in


# The names table: name -> the module that serves `pdfmd.NAME` (a name that code here calls bare has a stand-in instead).
# Filled below by `names("pdfmd_x.role", "a b c")` lines (pdfmd_base.names_into, 3.33.189) and `DEFERRED_NAMES.update(...)`.
DEFERRED_NAMES: dict[str, str] = {}


def __getattr__(name: str):
    """`pdfmd.X` for a name in DEFERRED_NAMES (PEP 562): the package's own object, its module loaded on the first read.
    It is kept in this module's globals, so a later read is a plain lookup and never comes here again."""
    if name in DEFERRED_NAMES:
        value = globals()[name] = getattr(load_package(DEFERRED_NAMES[name]), name)
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


import pdfmd_base  # noqa: E402
pdfmd_base.bind(sys.modules[__name__])      # every package's `core`, before any of them is imported; the first binding wins
names = pdfmd_base.names_into(DEFERRED_NAMES)   # the names table's lines: names("pdfmd_x.role", "a b c")
from pdfmd_comments import (CommentPolicy, comment_kind_set, parse_comment_policy,  # noqa: E402, F401 -- the strip_*_comments are read by lib/ and tests, comment_kind_set by lib/pdfmd_run
                            strip_markdown_comments, strip_tex_comments, strip_xml_comments)
from pdfmd_templates import init_command  # noqa: E402, F401 -- read by lib/pdfmd_run
from pdfmd_watch import pinned_watch_argv, run_watch  # noqa: E402, F401 -- read by lib/pdfmd_run, pinned_watch_argv by tests too

from pdfmd_hybrid import attach_hybrid, hybrid_after_success, resolve_hybrid  # noqa: E402, F401 -- attach_hybrid is read by tests/test_embedding.py

from pdfmd_polish import (HF_FIELDS, fill_hf_field, hf_text, locate_headings, markdown_headings,  # noqa: E402, F401 -- read by tests
                          parse_hf_template, polish_pdf)
from pdfmd_pdfimages import (encode_png, extract_pdf_images, file_picture_size, match_images_to_pdf,  # noqa: E402, F401 -- encode_png, file_picture_size and samples_to_png are read by tests
                             rewrite_image_paths, rewrite_tex_image_paths, samples_to_png)
from pdfmd_compat import (batchmd_main, batchmd_translate, inkmd_main, inkmd_translate,  # noqa: E402, F401 -- the *_main are console entry points (pyproject.toml), the *_translate are read by tests
                          md2pdf_main, md2pdf_translate, mdpdf_main, mdpdf_translate, pan_tec_main, pan_tec_translate)
import pdfmd_view  # noqa: E402
from pdfmd_view import (pager_command, run_pager, stdin_build, terminal_view,  # noqa: E402, F401 -- run_pager, view_pager_setting and view_sources are read by tests, stdin_build and terminal_view by lib/pdfmd_run
                        view_pager_setting, view_sources)

from pdfmd_lookup import (LOOKUP_FIELD_WORDS, LOOKUP_TIERS, LookupAmbiguous, cyrillic_candidates,  # noqa: E402, F401 -- LookupAmbiguous, lookup_fields, lookup_key, rank_lookup, document_priority, priority_enabled and source_markdown are read by tests or lib/
                          document_priority, find_wildcard_markdown, latin_candidates, lookup_fields, lookup_key,
                          priority_enabled, rank_lookup, source_markdown, strip_lookup_suffix)

import pdfmd_routing  # noqa: E402, F401 -- no longer read here: lib/pdfmd_run, its one reader, imports it itself
from pdfmd_routing import (BATCHOCR_TAG, EBOOK_INPUT_EXTENSIONS, batchocr_spec, find_batchocr,  # noqa: E402, F401 -- BATCHOCR_TAG, EBOOK_INPUT_EXTENSIONS, batchocr_spec, install_ocr_tools and tessdata_environment are read by tests, the route_*_input by lib/
                           install_ocr_tools, route_ebook_input, route_pdf_input, route_text_input, tessdata_environment)

import pdfmd_bridge  # noqa: E402, F401 -- tests read pdfmd.pdfmd_bridge
from pdfmd_bridge import (CALIBRE_TABLE_CSS, PANDOC_TABLE_STYLE_RE, browser_page_css, calibre_html_command,  # noqa: E402, F401 -- CALIBRE_TABLE_CSS and PANDOC_TABLE_STYLE_RE are read by tests, run_calibre_convert and run_soffice_convert are patched or read by tests and lib/, start_soffice_job by lib/pdfmd_run and tests
                          calibre_page_options, convert_office_direct, convert_via_soffice_bridge, prince_author_options,
                          run_browser_print, run_calibre, run_calibre_convert, run_soffice_convert, start_soffice_job)
from pdfmd_restore import (RESTORE_CHAIN, check_source_command, layout_from_source, restore_attachments,  # noqa: E402, F401 -- RESTORE_CHAIN, layout_from_source, restore_attachments, restore_attachments_in_place and restore_chain are read by tests, restore_target_name by tests and lib/, check_source_command, restore_from_markdown and restore_from_pdf by lib/ (the last by tests too)
                           restore_attachments_in_place, restore_chain, restore_from_markdown, restore_from_pdf,
                           restore_target_name)
from pdfmd_parts import (ATX_HEADING_RE, Heading, NoPartMatches, ScaffoldPlan, SectionPlan, chapter_order,  # noqa: E402, F401 -- ATX_HEADING_RE, Heading, NoPartMatches, collect_parts, find_heading, heading_parts, outermost_headings, parts_directory, plan_sections, scan_headings, scan_items, select_parts, split_into_parts, split_top_level_sections and wrap_runs are read by tests or lib/
                         collect_parts, find_heading, heading_parts, outermost_headings, parts_directory, plan_scaffold,
                         plan_sections, scaffold_inputs, scan_headings, scan_items, section_source, select_parts,
                         split_into_parts, split_top_level_sections, wrap_part, wrap_runs)
from pdfmd_doctor import (DEEP_SAMPLE, PANDOC_FEATURES, completion_options, completion_script, deep_checks,  # noqa: E402, F401 -- DEEP_SAMPLE, PANDOC_FEATURES, completion_options, deep_checks, foreign_commands, pandoc_limits and tool_note are read by tests, completion_script and doctor_report by lib/pdfmd_run and tests
                          doctor_report, foreign_commands, pandoc_limits, tool_note)
import pdfmd_cache  # noqa: E402, F401 -- read as pdfmd.pdfmd_cache by tests
from pdfmd_cache import (TEMPORARY_PLACES, adopt_moved_cache, cache_directory, cache_location, cache_root,  # noqa: E402, F401 -- TEMPORARY_PLACES and cache_location are read by tests or lib/; adopt_moved_cache is named in a docstring only
                         document_cache_root, folder_is_writable, source_fingerprint, temporary_place)
import pdfmd_install  # noqa: E402, F401 -- preserve startup and the public module attribute
from pdfmd_install import (GRAPHVIZ_COMMANDS, GRAPHVIZ_SHA256, GRAPHVIZ_VERSION, INSTALL_SPECS, MATHJAX_FONT_SIZES,  # noqa: E402, F401 -- all but install_extra, install_kind and uninstall_kind are read or patched by tests; install_kind and uninstall_kind are lib/pdfmd_args's type= for --install and --uninstall
                           MATHJAX_SOURCE_SHA256, TECTONIC_REPOSITORY, calibre_asset_pattern, calibre_package_manager,
                           calibre_release_asset, d2_asset_name, detach_disk_image, download_file, extract_executable,
                           github_latest_release, github_release_asset, install_calibre, install_d2, install_extra, install_kind,
                           install_mathjax_files, install_tectonic, install_typst, node_asset_name, release_asset_matching,
                           safe_unpack_tar, tectonic_asset_pattern, typst_asset_name, uninstall_kind, unpack_graphviz, unpack_katex)
from pdfmd_tex import (MAX_TEX_DIRECT_PASSES, PLOT_CTX_PLAIN, PLOT_CTX_TWICE, compile_tex_direct,  # noqa: E402, F401 -- MAX_TEX_DIRECT_PASSES is named in the docstring only; PLOT_CTX_PLAIN, PLOT_CTX_TWICE, latex_engine_command, plot_recorded_inputs and run_tex_engine are read by tests or lib/
                       document_latex_definitions, engine_failure_reason, is_latex_preamble, latex_engine_command,
                       package_latex_keys, pandoc_refused_command, plot_preamble, plot_recorded_inputs, render_plot_requests,
                       run_tex_engine, tex_failure_cause, tex_tree_stamp, wrap_latex_header_includes)
from pdfmd_attach import (ATTACH_FORMAT_PLAIN, add_deflated_attachment, attach_source_after_success,  # noqa: E402, F401 -- all but attach_source_after_success, bundle_files, keep_source_after_success and referenced_images are read by tests or lib/
                          attached_bundle_mode, block_places, bundle_files, drop_blocks, drop_duplicate_blocks, find_in_tex_tree,
                          graphic_names_in, held_comments_note, inline_blocks, inline_candidates, keep_source_after_success,
                          layout_path, read_pdf_attachments, referenced_images, source_attachments, tex_distribution_roots,
                          write_pdf_attachments)
from pdfmd_assemble import (EmbedPlan, assemble_markdown_text, embedded_resources, filter_bibliography,  # noqa: E402, F401 -- filter_bibliography, remember_trusted, render_embedded_block, render_embedded_file, trust_store_path, unpack_assembled and used_citation_keys are read by tests or lib/
                            parse_embedded_blocks, remember_trusted, render_embedded_block, render_embedded_file,
                            trust_store_path, trusted_hashes, unpack_assembled, used_citation_keys, write_assembled_markdown)
import pdfmd_native  # noqa: E402, F401 -- read as pdfmd.pdfmd_native by tests
from pdfmd_native import (CALIBRE_MARKDOWN_EXTENSIONS, CSV_DIV_LINE_RE, PAGE_BREAK_COMMENT_RE, PAGE_BREAK_RE, PAPER_SIZES,  # noqa: E402, F401 -- all but MathText and convert_native are read by tests
                          MathText, author_names, convert_native, csv_div_table, csv_guess_delimiter, csv_keep,
                          ignored_front_matter_keys, inline_math, native_font_size, native_landscape, native_order, native_page,
                          native_paper, mapped_author, normalise_gfm, author_names_in_place)
from pdfmd_args import build_parser  # noqa: E402, F401 -- read by tests and lib/

# Moves into packages that are not loaded at start (SPLIT.md, step 6): stand-ins that load the module on the first call.
paragraph_spacing_latex_args = deferred("pdfmd_paragraph", "latex_args")
paragraph_spacing_typst_args = deferred("pdfmd_paragraph", "typst_args")
paragraph_spacing_command_line = deferred("pdfmd_paragraph", "apply_cli")
fullcite_pre_args, fullcite_old_spelling = (deferred("pdfmd_fullcite", name) for name in ("fullcite_pre_args", "fullcite_old_spelling"))
chain_plan_build = deferred("pdfmd_chain", "plan_build")
chain_stopped = deferred("pdfmd_chain", "stopped")
chain_engine_failed = deferred("pdfmd_chain", "engine_failed")
ansi_width_argument = deferred("pdfmd_ansi.cli", "ansi_width_argument")      # move 5 (v3.33.6)
ansi_columns = deferred("pdfmd_ansi.cli", "ansi_columns")
ansi_finish = deferred("pdfmd_ansi.cli", "ansi_finish")
ansi_without_pandoc = deferred("pdfmd_ansi.cli", "ansi_without_pandoc")
cache_command = deferred("pdfmd_cache.manage", "cache_command")                 # v3.33.74: --cache-info, --clear-cache WHAT
clear_cache = deferred("pdfmd_cache.manage", "clear_cache")
remove_cache_paths = deferred("pdfmd_cache.manage", "remove_all")
cache_size_note = deferred("pdfmd_cache.manage", "size_note")
serve_live_filters = deferred("pdfmd_serve.commands", "serve_live_filters")     # move 6 (v3.33.7); read by tests/test_serve.py
serve_command = deferred("pdfmd_serve.commands", "serve_command")
api_command = deferred("pdfmd_serve.commands", "api_command")
pandoc_extensions = deferred("pdfmd_flat.build", "pandoc_extensions")           # move 7 (v3.33.8); read by tests
flat_settings = deferred("pdfmd_flat.build", "flat_settings")
flat_writer = deferred("pdfmd_flat.build", "flat_writer")
flat_filter_args = deferred("pdfmd_flat.build", "flat_filter_args")
split_ascii_target = deferred("pdfmd_flat.build", "split_ascii_target")
ascii_missing = deferred("pdfmd_flat.build", "ascii_missing")
ascii_filter_args = deferred("pdfmd_flat.build", "ascii_filter_args")
ascii_finish = deferred("pdfmd_flat.build", "ascii_finish")
DEFERRED_NAMES.update(_PANDOC_EXTENSIONS="pdfmd_flat.build")                      # tests patch it with mock.patch.dict
document_file = deferred("pdfmd_docs.reader", "document_file")                  # move 8 (v3.33.9); read by tests
document_headings = deferred("pdfmd_docs.reader", "document_headings")
document_section = deferred("pdfmd_docs.reader", "document_section")
search_documents = deferred("pdfmd_docs.reader", "search_documents")
render_document = deferred("pdfmd_docs.reader", "render_document")
doc_command = deferred("pdfmd_docs.reader", "doc_command")
DEFERRED_NAMES.update(DOCUMENTS="pdfmd_docs.reader")                              # read by tests/test_doc.py and test_packaging.py
css_scope = deferred("pdfmd_css.latex", "css_scope")                            # move 9 (v3.33.10)
css_additions = deferred("pdfmd_css.latex", "css_additions")                    # read by lib/pdfmd_report too
css_heading_latex = deferred("pdfmd_css.latex", "css_heading_latex")            # read by tests
css_heading_args = deferred("pdfmd_css.latex", "css_heading_args")
picture_target = deferred("pdfmd_crop.targets", "picture_target")                # move 10 (v3.33.11)
multi_target_command = deferred("pdfmd_crop.targets", "multi_target_command")
picture_command = deferred("pdfmd_crop.targets", "picture_command")
vault_root = deferred("pdfmd_obsidian.vault", "vault_root")                    # move 11 (v3.33.12); read by tests
single_newline_mode = deferred("pdfmd_obsidian.vault", "single_newline_mode")
find_embedded_image = deferred("pdfmd_obsidian.vault", "find_embedded_image")
embed_source = deferred("pdfmd_obsidian.vault", "embed_source")
embed_filter_args = deferred("pdfmd_obsidian.vault", "embed_filter_args")
figure_filter_args = deferred("pdfmd_obsidian.vault", "figure_filter_args")
DEFERRED_NAMES.update(_VAULT_ROOTS="pdfmd_obsidian.vault", _EMBED_INDEX="pdfmd_obsidian.vault")   # tests empty them with .clear()
check_command = deferred("pdfmd_check.command", "check_command")                # move 16 (v3.33.17)
ranking_layers = deferred("pdfmd_ranking.choice", "ranking_layers")             # move 17 (v3.33.19); read by lib/pdfmd_serve too
ranking_clashes = deferred("pdfmd_ranking.choice", "ranking_clashes")
bare_ranking = deferred("pdfmd_ranking.choice", "bare_ranking")
priority_candidates = deferred("pdfmd_ranking.choice", "priority_candidates")
which_command = deferred("pdfmd_ranking.choice", "which_command")
user_path_command = deferred("pdfmd_setup.command", "user_path_command")           # move 19 (v3.33.21)
maybe_hint_setup = deferred("pdfmd_setup.command", "maybe_hint_setup")
setup_command = deferred("pdfmd_setup.command", "setup_command")                 # read by tests/test_atomic.py
flag_names = deferred("pdfmd_setup.command", "flag_names")                       # read by tests/test_setup.py
package_places = deferred("pdfmd_kits.locate", "package_places")                         # move 20 (v3.33.22)
kpsewhich_locate = deferred("pdfmd_kits.locate", "kpsewhich_locate")  # read by tests
read_package_helper = deferred("pdfmd_kits.locate", "read_package_helper")  # read by tests
kit_package_folders = deferred("pdfmd_kits.locate", "kit_package_folders")  # tests patch it with mock.patch.object
kits_report = deferred("pdfmd_kits.locate", "kits_report")
kit_header_insert = deferred("pdfmd_kits.locate", "kit_header_insert")
kit_header_settle = deferred("pdfmd_kits.locate", "kit_header_settle")
kit_cache_tex = deferred("pdfmd_kits.locate", "kit_cache_tex")
kit_header_resolve = deferred("pdfmd_kits.locate", "kit_header_resolve")
kit_carried_files = deferred("pdfmd_kits.locate", "kit_carried_files")
markup_header_pieces = deferred("pdfmd_tex.markup", "markup_header_pieces")       # v3.33.67
typst_template_args = deferred("pdfmd_lua.typst", "template_args")
kit_markup_off = deferred("pdfmd_kits.markup", "kit_markup_off")                   # v3.33.68
begin_timer = deferred("pdfmd_buildinfo.build", "begin_timer")                  # move 21 (v3.33.23); read by lib/pdfmd_report too
attach_time = deferred("pdfmd_buildinfo.build", "attach_time")                  # read by lib/pdfmd_report too
time_breakdown = deferred("pdfmd_buildinfo.build", "time_breakdown")            # read by lib/pdfmd_report too
last_build_command = deferred("pdfmd_buildinfo.build", "last_build_command")
csv_defaults = deferred("pdfmd_tables.command", "csv_defaults")                 # move 22 (v3.33.24); read by tests
csv_table_filter_args = deferred("pdfmd_tables.command", "csv_table_filter_args")  # read by tests
table_keep_metadata = deferred("pdfmd_tables.command", "table_keep_metadata")
tables_command = deferred("pdfmd_tables.command", "tables_command")
DEFERRED_NAMES.update(FOLDER_SETTINGS="pdfmd_ranking.choice")                     # named in a docstring only; kept as a re-export
office_package_folders = deferred("pdfmd_office.build", "office_package_folders")  # move 25 (v3.33.27)
office_defaults_sources = deferred("pdfmd_office.build", "office_defaults_sources")
find_office_profile = deferred("pdfmd_office.build", "find_office_profile")
find_reference_doc = deferred("pdfmd_office.build", "find_reference_doc")
OfficeArguments = deferred("pdfmd_office.build", "OfficeArguments")             # a class there; pdfmd.py only calls it
office_finish = deferred("pdfmd_office.build", "office_finish")                 # read by lib/pdfmd_report too
run_office_pandoc = deferred("pdfmd_office.build", "run_office_pandoc")         # read by lib/pdfmd_report too
check_docx_command = deferred("pdfmd_office.build", "check_docx_command")
init_reference = deferred("pdfmd_office.build", "init_reference")
backup_after_success = deferred("pdfmd_history.backups", "backup_after_success")                  # move 26 (v3.33.28)
backup_directory = deferred("pdfmd_history.backups", "backup_directory")
backup_pdf_after_success = deferred("pdfmd_history.backups", "backup_pdf_after_success")
backup_snapshots = deferred("pdfmd_history.backups", "backup_snapshots")
backup_summary = deferred("pdfmd_history.backups", "backup_summary")
backup_template = deferred("pdfmd_history.backups", "backup_template")
document_versions = deferred("pdfmd_history.backups", "document_versions")
entries_to_notes = deferred("pdfmd_history.backups", "entries_to_notes")
fill_backup_template = deferred("pdfmd_history.backups", "fill_backup_template")
history_command = deferred("pdfmd_history.backups", "history_command")
history_interactive = deferred("pdfmd_history.backups", "history_interactive")
history_view_command = deferred("pdfmd_history.backups", "history_view_command")
init_backups_command = deferred("pdfmd_history.backups", "init_backups_command")
notes_to_entries = deferred("pdfmd_history.backups", "notes_to_entries")
version_differs = deferred("pdfmd_history.backups", "version_differs")
version_text = deferred("pdfmd_history.backups", "version_text")
font_missing = deferred("pdfmd_unicode.fonts_choice", "font_missing")                # move 31 (v3.33.34); read by lib/pdfmd_doctor too
system_font_missing = deferred("pdfmd_unicode.fonts_choice", "system_font_missing")  # tests patch it with mock.patch.object
default_monofont = deferred("pdfmd_unicode.fonts_choice", "default_monofont")        # read by lib/pdfmd_report too
fallback_font = deferred("pdfmd_unicode.fonts_choice", "fallback_font")
preferred_font = deferred("pdfmd_unicode.fonts_choice", "preferred_font")            # tests replace it
font_args = deferred("pdfmd_unicode.fonts_choice", "font_args")                      # read by lib/pdfmd_report too
unicode_forced = deferred("pdfmd_unicode.fonts_choice", "unicode_forced")            # read by tests/test_setup.py
managed_fonts_css = deferred("pdfmd_unicode.fonts_choice", "managed_fonts_css")      # read by lib/pdfmd_report too
check_fonts = deferred("pdfmd_unicode.fonts_choice", "check_fonts")
script_fallback = deferred("pdfmd_unicode.fonts_choice", "script_fallback")          # read by lib/pdfmd_report too
# a function, but pdfmd.py never calls it and tests call its .cache_clear(), which a stand-in does not have
DEFERRED_NAMES.update(installed_font_families="pdfmd_unicode.fonts_choice")
names("pdfmd_edit.command", "put_outside_blocks source_carried source_lost")
names("pdfmd_run", "DISABLED_OK_ENV command_line_parser")
names("pdfmd_fullcite", "fullcite_post_args fullcite_command_line")
names("pdfmd_bibliography", "bibliography_indent_args bibliography_indent_command_line")
names("pdfmd_direct.route", "direct_route convert_direct convert_qmd")
names("pdfmd_build", "PREFERRED_FONT DEFAULT_MONOFONT DEFAULT_VARS WEASYPRINT_CSS_NOISE run_engine_command "
                     "_convert_one_core finish_build set_soffice_limit convert_one make_embed_plan")
names("pdfmd_cite", "CITATION_ENGINES frontmatter_citation_engine CA_BUNDLES open_url document_csl fetch_csl remote_csl "
                    "csl_args parse_bibliography convert_via_native_bibliography")
names("pdfmd_labels.seed", "PARTS_MARKER_DEFS DRAFT_SKIP_COMMANDS DRAFT_SKIP_SPANS package_draft_skips draft_skip_text "
                           "label_without_page seed_labels_file part_key seed_labels_mode SEED_CALC_MODES seed_calc_mode "
                           "parts_range_text build_calc_seed calc_marked_inputs label_scan_wanted select_wanted "
                           "build_label_scan")
names("pdfmd_cache.settings", "CACHE_DEFAULTS NOTED_PLACES provide_writable_places metadata_cwd pandoc_working_directory "
                              "CACHE_LOCATIONS CACHE_MANIFEST LOCAL_CACHE_DIRNAME prepare_cache_root write_cache_manifest "
                              "cache_settings")
names("pdfmd_tex.failure", "TEX_PROBES probe_tex_cause SHOWN_LOCATIONS source_line_for latex_error_location "
                           "report_engine_failure tex_argument")
names("pdfmd_build.results", "timing_module time_label record_engine Built engine_label built_name _WarningTee "
                             "warning_capture resolve_strict resolve_budget check_asset_budget _NONMATH_DOLLARS "
                             "nonmath_dollars check_nonmath_dollars check_output_budget strict_message")
names("pdfmd_reader", "_MARKDOWN_FEATURES contains_citations contains_crossref crossref_built_for SUFFIX_READERS "
                      "MARKDOWN_LIKE_SUFFIXES resolve_from_format flavour_reader reader_needs promote_bare_title "
                      "prepared_title_source")
names("pdfmd_filters", "has_code_block code_filter_args SVG_WARNED image_filter_args PAGEBREAK_KINDS pagebreak_value "
                       "pagebreak_kinds slide_notes_mode slide_notes_args cover_filter_args cover_header_args "
                       "pagebreak_filter_args LINEBREAK_KINDS LINEBREAK_RE linebreak_value md_macro_in md_macro_on "
                       "INDENT_DIV_RE indent_filter_args title_filter_args raw_filter_args document_filter_args "
                       "DIAGRAM_TIMEOUT diagram_timeout_from diagram_timeout_for DIAGRAM_TOOLS RELATIVE_IMAGE_RE "
                       "select_filter_args chem_filter_args typst_filter_args")
names("pdfmd_flavours.markup", "FLAVOUR_PRESETS FLAVOUR_WORDS MARKUP_KINDS markup_value show_comments_on _FLAVOUR_TOLD UNCLOSED_WORDS "
                               "unclosed_comment_mode flavour_setting flavour_of flavour_default obsidian_source "
                               "markup_kinds markup_filter_args MARKUP_HIGHLIGHT_HEADER MARKUP_LANDSCAPE_HEADER "
                               "MARKUP_HEADERS markup_header_args")
names("pdfmd_tex.plots", "CACHE_HANDSHAKE picture_cache_styles cache_aliases user_tex_trees plot_key_text "
                         "plot_cache_directory prune_plot_directories validate_plot_entries read_plot_requests")
names("pdfmd_install.manage", "translit_report kits_install_directory uninstall_kit uninstall_fonts tessdata_directory "
                              "install_ocr_languages reset_font_caches setup_module")
names("pdfmd_page", "has_geometry frontmatter_margin_geometry_options pagesize_typo_value frontmatter_papersize_value "
                    "typst_papersize_translation paper_kind paper_variables has_monofont")
names("pdfmd_office.route", "OFFICE_REFERENCE_EXTENSIONS OFFICE_OPTION_KEYS effective_metadata office_options "
                            "office_pdfmd_command office_label_data office_reference CHEM_COMMANDS MATH_ONLY_LATEX_RE "
                            "latex_failed latex_dropped office_fallback_wanted")
names("pdfmd_bridge.goals", "OFFICE_INPUT_EXTENSIONS CALIBRE_OPTIONS CALIBRE_CSS CALIBRE_SHARED_FORMATS "
                            "CALIBRE_MATH_PICTURES CALIBRE_MATH_TEXT EBOOK_MATH ebook_filter_args math_pictures_possible "
                            "SOFFICE_ONLY_FORMATS SOFFICE_SHARED_FORMATS soffice_asked_first soffice_goal "
                            "calibre_asked_first calibre_goal start_calibre_job finish_convert_job")
names("pdfmd_output", "PICTURE_ONLY PICTURE_FORMATS ASSEMBLED_FORMAT ASSEMBLED_SUFFIX FORMAT_EXTENSION "
                      "CALIBRE_ONLY_FORMATS EXTENSION_FORMAT output_extension_for rewrite_wanted rewrite_template "
                      "numbered_output default_output_path BOPEN_HELP parse_bopen bopen_indices report_common_folder")
names("pdfmd_filters.lua", "package_lua_names find_lua_filters check_lua_filters trust_lua PDFMD_LUA_WARNED")
names("pdfmd_lookup.find", "announce_lookup CYRILLIC_STRICT CYRILLIC_LOOSE LATIN_EXTRA set_translit _LOOKUP_ANNOUNCED choose_markdown "
                           "find_markdown")
names("pdfmd_unicode.document", "unicode_module managed_index managed_face template_has_variable mathfont_args "
                                "document_font_args font_index strip_code_text unicode_source_text own_script_setup "
                                "fallback_settings mainfont_choice name_candidates has_mainfont has_font_setting "
                                "has_code_spans UNICODE_UNCOVERED UNICODE_CODE_FONTS missing_glyph_warning "
                                "missing_glyph_codes retry_font_note")
names("pdfmd_parts", "PARTS_DIR_ALIASES PARTIAL_METADATA parts_setting REPORT_BUILD split_section_requests "
                     "scaffold_metadata_files LEADING_FRONT_MATTER_RE strip_part_front_matter print_parts DIV_FENCE_RE "
                     "print_headings")
names("pdfmd_stamp", "STAMP_MODES STAMP_SCOPES STAMP_STORES DEFAULT_STAMP_OPTIONS stamp_fields frontmatter_stamp "
                     "resolve_stamp_options stamp_summary stamp_line_pattern history_heading_pattern IGNORE_MARK_RE "
                     "is_pdfmd_notes build_notes_blocks pdfmd_build_notes update_build_notes apply_stamp stamp_build "
                     "stamp_after_success partial_parts_label pdf_metadata_snippet stamp_pdf_metadata_posthoc "
                     "pdf_metadata_header_file")
names("pdfmd_history.record", "history_module note_entry compile_entry history_file record_history DEFAULT_BACKUP_OPTIONS "
                              "DEFAULT_BACKUP_DIR backup_notice backup_target backup_sort_key resolve_backup_options "
                              "backup_before_edit")
names("pdfmd_attach.options", "ATTACH_FORMAT ATTACH_MANIFEST ATTACH_SOURCE BUNDLE_MAX_MB EXTRA_PREFIX RESTORED_SUFFIX "
                              "BUNDLE_SKIP_DIRS IMAGE_REF_RE resolve_attach resolve_bundle extra_key relative_posix "
                              "GRAPHIC_RE drop_calc_export add_calc_constants comments_note requirement_lines "
                              "MARKDOWN_TARGETS resolve_keep_source")
names("pdfmd_tables.settings", "width_filter_args csv_table_filter CSV_DIV_RE contains_csv_table CSV_DEFAULTS CSV_ENV "
                               "CSV_NOTE_ENV csv_note_mode csv_count CSV_ENABLED_ENV csv_is_off TABLE_KEEP_ENV "
                               "table_keep_count table_caption_args tabularray_available TABLAY_NOTED cellalign_args "
                               "tblr_header_args CSV_DELIMITER_NAMES CSV_DELIMITER_WORDS table_width_filter "
                               "tablewidth_note ORG_CAPTION_RE")
names("pdfmd_html", "KATEX_VERSION KATEX_PACKAGE katex_folder MATHJAX_VERSION MATHJAX_FONT_SHA256 MATHJAX_DEFAULT_FONT "
                    "MATHJAX_FONT_FOR mathjax_font_package mathjax_folder mathjax_font_for sfnt_x_height body_x_height "
                    "katex_scale weasyprint_math_args ascii_table_transform HTML_TARGETS DEFAULT_OUTPUT_ALIASES "
                    "HTML_MATH_METHODS HTML_MATH_OPTIONS pandoc_has_option html_math_args cascaded_option "
                    "default_output_format html_settings html_pandoc_args")
names("pdfmd_routing", "BATCHOCR_MIN OCR_PACKAGE_MANAGERS system_package_manager ocr_install_command")
names("pdfmd_tex.inputs", "EMBEDDED_RESOURCE_DIRS resource_path_option kit_search_folders TECTONIC_SEARCH_ENV "
                          "tectonic_search_folders tex_search_env hoist_code_header pandoc_header_includes "
                          "keep_header_includes headers_as_metadata tex_package_args has_shift_heading_option "
                          "has_standalone_option document_preambles announce_preambles prepared_latex_inputs "
                          "raw_latex_only document_header_file")
names("pdfmd_kitset", "installed_package_folder configured_kits kit_locations find_kit kit_cache KIT_METADATA ACTIVE_KITS "
                      "set_kit_cli KIT_HEADER_PREFIX kit_preamble_kits kit_writes_preamble header_argument_positions "
                      "kit_explicit_sources kit_embedded_preambles package_helper office_packages")
names("pdfmd_metadata", "AUTO_METADATA_DISABLED METADATA_APPEND_KEY metadata_plus_key metadata_append_keys "
                        "merge_metadata_layers metadata_append_args calc_filter_args global_metadata_file PRESET_OFF "
                        "PRESET_DEFAULT presets_report METADATA_PRECEDENCES metadata_precedence pandoc_metadata_order "
                        "find_metadata find_local_metadata chapter_value has_chapter_field report_sources")
names("pdfmd_calc", "CALC_DIV_RE CALC_SPAN_RE CALC_ENV CALC_DIGITS_ENV CALC_ROUND_ENV CALC_SUBS_ENV CALC_TYPESET_ENV "
                    "CALC_TYPESET_STYLE_ENVS CALC_NOINDENT_ENV CALC_SPACE_ENV CALC_ALIGN_ENV CALC_ALIGNS "
                    "CALC_CONSTANTS_ENV CALC_EXPORT_ENV CALC_ROUNDS calc_is_off calc_round_mode calc_subs_on "
                    "calc_typeset_mode calc_typeset_styles calc_noindent_mode calc_space calc_align calc_constants_file "
                    "calc_export_file write_calc_export calc_constants_statements calc_digits_value calc_digits_mode")
names("pdfmd_config.auto", "ACCESSORY_DIRNAME UNPACKED_SUFFIX NO_AUTO_KINDS NO_AUTO_ALIASES auto_disabled "
                           "accessory_directories discovery_disabled folder_auto_safe resolve_auto effective_no_auto "
                           "kit_no_auto_kinds")
names("pdfmd_assemble.embed", "_EmbedDumper")
names("pdfmd_assemble.embed", "strip_embedded_preamble ASSEMBLED_KEY ASSEMBLED_COMMENT_RE is_assembled_text "
                              "is_assembled_document EMBED_KINDS EMBED_ALL PREAMBLE_END_MARK LUA_MODES EMBED_BLOCK_RE "
                              "EmbedRequest parse_embed_option resolve_embed normalized_source is_crlf_text "
                              "strip_location_markers first_block_start outside_folder block_relative_path embedded_lines "
                              "with_location_markers embedded_lua_filters header_includes_text")
names("pdfmd_engines", "PDF_ENGINES ENGINE_ALIASES BROWSER_ENGINES LATEX_ENGINES PREAMBLE_FILENAMES "
                       "TEX_STANDALONE_FORMATS ENGINE_FAMILY ENGINE_GROUPS automatic_engines select_engines "
                       "resolve_engines dependency_report frontmatter_engine")
names("pdfmd_engines.native", "INSTALL_KINDS INSTALL_SIZES PANDOC_MIN warn_old_pandoc PANDOC_MISSING inkmd_vendored "
                              "md2pdf_available matplotlib_available inkmd_emoji_font is_native_engine native_available "
                              "available_native_engines native_request native_possible native_run_note "
                              "system_install_hint pandoc_install_hint offer_native_upgrade")
names("pdfmd_engines.tools", "FOUND_TOOLS TOOLS_FOUND TOOL_WARNED app_path_file locate_tool use_found_tools "
                             "SOFFICE_TIMEOUT soffice_timeout_from soffice_limit run_soffice tool_folders_off_path "
                             "resolve_soffice calibre_own_folders resolve_calibre engine_executable tools_directory "
                             "bundled_pandoc_directory managed_tool_directories use_managed_tools tex_install_patterns "
                             "find_tex_directory use_tex_install pandoc_user_data_dir pandoc_version PROBE_TIMEOUT "
                             "run_probe kpsewhich_path engine_version_line typst_version")
names("pdfmd_log", "PATH_STYLES DISPLAY_ALIAS path_style_settings AutoLog AUTO_LOG under_home failure_text open_file "
                   "log_cmd")
names("pdfmd_config", "frontmatter_no_auto no_auto_from_value has_embedded_preamble scalar_text split_front_matter "
                      "data_root config_root config_path load_config merge_options folder_options_safe config_options "
                      "config_report migrate_state SETUP_HEADER has_yaml_frontmatter frontmatter_value metadata_file_yaml "
                      "option_names frontmatter_extra_preambles frontmatter_extra_lua_filters option_flag FOLDER_WARNED "
                      "FOLDER_DIR folder_file_data folder_walk folder_layer_files folder_metadata_files "
                      "is_folder_metadata is_setup_layer folder_layers option_sources first_pdfmd_option "
                      "resolve_strip_comments merge_option_dicts option_flag_number front_matter_dict")
names("pdfmd_native", "Chunk MATH_LINE_BREAK math_lines NATIVE_PAPER_POINTS PAPER_NAME_ALIASES")
names("pdfmd_comments", "fence_after FENCE_RE COMMENT_KINDS")
names("pdfmd_ansi.cli", "ANSI_LINKS_ENV ANSI_COLOR_ENV ANSI_WIDTH_ENV ANSI_FALLBACK_WIDTH")
names("pdfmd_flat.build", "ASCII_FORMATS")
names("pdfmd_hybrid", "HYBRID_MIME")
names("pdfmd_css.latex", "CSS_SCOPES")
names("pdfmd_watch", "WATCH_INTERVAL")
display_path = deferred("pdfmd_log", "display_path")
installed_engines = deferred("pdfmd_engines", "installed_engines")
mask_embedded_blocks = deferred("pdfmd_assemble.embed", "mask_embedded_blocks")
is_global_metadata = deferred("pdfmd_metadata", "is_global_metadata")
metadata_files_by_priority = deferred("pdfmd_metadata", "metadata_files_by_priority")
preset_name = deferred("pdfmd_metadata", "preset_name")
active_kits = deferred("pdfmd_kitset", "active_kits")
kit_metadata_files = deferred("pdfmd_kitset", "kit_metadata_files")
document_header_includes = deferred("pdfmd_tex.inputs", "document_header_includes")
find_preambles = deferred("pdfmd_tex.inputs", "find_preambles")
frontmatter_pdfmd_options = deferred("pdfmd_tex.inputs", "frontmatter_pdfmd_options")
has_header_include_option = deferred("pdfmd_tex.inputs", "has_header_include_option")
batchocr_version = deferred("pdfmd_routing", "batchocr_version")
tesseract_install_hint = deferred("pdfmd_routing", "tesseract_install_hint")
katex_runtime = deferred("pdfmd_html", "katex_runtime")
mathjax_fonts = deferred("pdfmd_html", "mathjax_fonts")
mathjax_runtime = deferred("pdfmd_html", "mathjax_runtime")
cell_tags_text = deferred("pdfmd_tables.settings", "cell_tags_text")
repair_ascii_text = deferred("pdfmd_tables.settings", "repair_ascii_text")
table_ascii_mode = deferred("pdfmd_tables.settings", "table_ascii_mode")
is_package_helper_yaml = deferred("pdfmd_stamp", "is_package_helper_yaml")
yaml_autoinclude = deferred("pdfmd_stamp", "yaml_autoinclude")
document_font_setting = deferred("pdfmd_unicode.document", "document_font_setting")
fonts_directory = deferred("pdfmd_unicode.document", "fonts_directory")
skip_never = deferred("pdfmd_lookup.find", "skip_never")
lua_filter_file = deferred("pdfmd_filters.lua", "lua_filter_file")
pdfmd_lua_missing = deferred("pdfmd_filters.lua", "pdfmd_lua_missing")
format_from_output = deferred("pdfmd_output", "format_from_output")
office_module = deferred("pdfmd_office.route", "office_module")
fix_typst_margin = deferred("pdfmd_page", "fix_typst_margin")
paper_words = deferred("pdfmd_page", "paper_words")
resolve_raw = deferred("pdfmd_filters", "resolve_raw")
crossref_filter_args = deferred("pdfmd_reader", "crossref_filter_args")
safe_stem = deferred("pdfmd_labels.seed", "safe_stem")
_convert_one = deferred("pdfmd_build", "_convert_one")
run_main = deferred("pdfmd_run", "run_main")
edit_command = deferred("pdfmd_edit.command", "edit_command")
gather_stamp_texts = deferred("pdfmd_edit.command", "gather_stamp_texts")
init_vscode_command = deferred("pdfmd_edit.command", "init_vscode_command")
part_digests = deferred("pdfmd_edit.command", "part_digests")
stamp_scope_matches = deferred("pdfmd_edit.command", "stamp_scope_matches")

# --- Finishing the built PDF: bookmarks, running header/footer, linked files ----------------
# Ideas from mdpdf (MIT, github.com/normanlorrain/mdpdf): a small Markdown-to-PDF tool whose own
# renderer needs PyMuPDF (AGPL), which pdfmd does not use. The ideas are done here on the finished
# PDF with pypdf, so they work with every engine: headings become PDF bookmarks (when the engine
# made none), a "left,middle,right" template prints a running header and footer, and local files
# the document links to are attached to the PDF with a paperclip in the margin beside the link. All of it is
# off unless asked for (`--bookmarks`, `--header`, `--footer`, `--attach-links`, `--pdf-title` ...),
# except under the `mdpdf` command, which asks for bookmarks and attachments like mdpdf does.

# -- MathJax for WeasyPrint (v3.28.46) ---------------------------------------------------------------------------------
# MathJax 4 typesets the math of a WeasyPrint PDF first, KaTeX takes the formulas it cannot read, and what neither reads
# stays text. `pdfmd --install math:mathjax` puts this release's files in data_root()/mathjax/<version>/node_modules/@mathjax
# (the npm packages below, each checked against its SHA-256 pinned here: the bundle's TeX input and CHTML output, and the
# STIX Two math font, which goes with pdfmd's default body font), and node as for KaTeX. pdfmd_lua/mathjax.cjs renders;
# Apache-2.0. Only STIX Two is offered: MathJax's New Computer Modern, TeX Gyre Termes, TeX Gyre Pagella and DejaVu fonts
# were measured too (the margin that undoes WeasyPrint's misplacing is the font's ascent-descent excess plus 0.03em in
# each, as in STIX Two), but a tall delimiter built from pieces (`\left[` over three rows) came out broken in WeasyPrint,
# so they wait for a fix of that. A font is one entry in each of the three tables below.
# MATHJAX_REGISTRY, MATHJAX_SOURCE_SHA256, MATHJAX_FONT_SIZES, MATHJAX_BUNDLE_KEPT, MATHJAX_BUNDLE_FOLDERS, MATHJAX_BUNDLE_INPUT and
# mathjax_package_url: lib/pdfmd_install/__init__.py (v3.33.35)

# Default page margin when no document setting is given.
DEFAULT_MARGIN = "1in"

# Whether printed paths use their full absolute form.
SHOW_FULL_PATHS = False

# Requested display style for printed paths.
PATH_STYLE = "auto"

# Parent levels included in printed paths.
PATH_UP = 2

# Whether --no-citeproc disables citation processing.
CITEPROC_DISABLED = False

# Command-line comment stripping override; None defers to the document.
STRIP_COMMENTS_CLI: bool | None = None

# --line-numbers and friends, filled in by main()
CODE_CLI: dict = {}

# Command-line raw block selection and off override.
RAW_CLI: dict = {"all": False, "off": False, "for": []}

# Command-line page-break kinds and off override.
PAGEBREAK_CLI: dict = {"kinds": None, "off": False}

# Command-line markup kinds and off override.
MARKUP_CLI: dict = {"kinds": None, "off": False}

# Command-line visible-comments override.
SHOW_COMMENTS_CLI: dict = {"on": None}

try:
    import pdfmd_flavours  # noqa: F401 -- preserve the pre-move start-up module set
except ImportError:
    pass

# Command-line Markdown flavour override.
FLAVOUR_CLI: dict = {"name": None}

# Command-line unclosed-comment handling override.
UNCLOSED_CLI: dict = {"mode": None}

# Command-line line-break kinds and off override.
LINEBREAK_CLI: dict = {"kinds": None, "off": False}

# where this build's calc.lua writes its names, when the document exports them (set around one build)
CALC_DUMP: Path | None = None

# the names of the parts before a part built alone (build_calc_seed; set around one build)
CALC_SEED: Path | None = None

# the first definitions in the parts after it (3.31.44; the same)
CALC_BELOW: Path | None = None

# Command-line GFM script, math and title settings.
GFM_CLI: dict = {"scripts": None, "math": None, "title": None}

# Command-line ASCII rendering and missing-picture settings.
ASCII_CLI: dict = {"on": False, "missing": None}

# what the document being built says (set by convert_one); None: the config's
SOFFICE_TIMEOUT_NOW: float | None = None

# Counts of features lost by the native renderer in this run.
NATIVE_LOST: dict[str, int] = {}

# --kit, parsed (None: not given; [OFF]: bare --kit / none)
KIT_CLI: list | None = None

# --kit-stack, as given
KIT_STACK_CLI = None

# the TeX folder use_tex_install() put on PATH, for --doctor and --verbose
TEX_FOUND_AT: Path | None = None

# Cached system font index for this run.
_FONT_INDEX = None

# Cached managed font index for this run.
_MANAGED_INDEX = None

# Command-line fallback-font override.
FALLBACK_CLI: str | None = None

# Command-line missing-glyph handling override.
MISSING_CLI: str | None = None

# main() clears it for --no-auto lookup
FUZZY_LOOKUP = True

# Enabled transliteration packs for document lookup.
TRANSLIT_PACKS: frozenset[str] = frozenset()

# Whether lookup transliterates Cyrillic names.
TRANSLIT_CYRILLIC = True

# --no-auto as given (set in main): the command line's layer of priority_enabled()
NO_AUTO_CLI: list[str] | None = None

# Command-line build-time display override.
BUILD_TIME_CLI: bool | None = None

# Command-line build-time formatting override.
TIME_FORMAT_CLI: str | None = None

# Command-line build-record mode override.
BUILD_LOG_CLI: str | None = None

# --preset (set in main)
PRESET_CLI: str | None = None

# --global-metadata / --no-global-metadata (set in main)
GLOBAL_METADATA_CLI: bool | None = None

# --metadata-precedence (set in main)
METADATA_PRECEDENCE_CLI: str | None = None

# Selected heading cuts for each parts source.
PART_CUTS: dict[Path, list[Heading]] = {}

# Cached Pandoc help text for capability checks.
_PANDOC_HELP: str | None = None

# Cached Pandoc data directory; False means not checked.
_PANDOC_DATA_DIR: Path | None | bool = False

# Cached Pandoc version tuple.
_PANDOC_VERSION: tuple[int, ...] | None = None

# --css FILE (repeatable)
CSS_CLI: list[str] = []

# --css-scope
CSS_SCOPE_CLI: str | None = None

# Comment kinds explicitly stripped by the command line.
STRIP_KINDS_CLI: frozenset[str] = frozenset()

# Comment kinds explicitly retained by the command line.
KEEP_KINDS_CLI: frozenset[str] = frozenset()

# Document that owns the currently unpacked embedded resources.
_RESOURCE_OWNER: Path | None = None

# Command-line output replacement override.
REWRITE_CLI: bool | None = None

# labels a partial cache build took from the last full build
LAST_SEEDED = 0

# --cache-location (set in main)
CACHE_LOCATION_CLI: str | None = None

# --strict / --no-strict (set in main)
STRICT_CLI: bool | None = None

# -e as given ("" a bare -e), for lib/pdfmd_chain's pinned engine (set in main)
ENGINE_CLI: str | None = None

# --engine-fallback MODE (lib/pdfmd_chain; set in main)
ENGINE_FALLBACK_CLI: str | None = None

# --seed-labels (set in main)
SEED_LABELS_CLI: str | None = None

# labels the last build took from the scan (for the closing NOTE)
LAST_SCANNED = 0

# ... and whether they came from a draft pass
LAST_EXACT = False

# ... and how many it left out (after a caption it could not count)
LAST_SKIPPED = 0

# the last build numbered the whole document and kept the part (select.lua)
LAST_WHOLE = False

# --seed-calc (set in main)
SEED_CALC_CLI: str | None = None

# --cache-plots (set in main)
CACHE_PLOTS_CLI: bool | None = None

# Command-line source attachment override.
ATTACH_CLI: bool | None = None

# Command-line source bundle mode override.
BUNDLE_CLI: str | None = None

# Whether this run prints verbose discovery and command output.
VERBOSE_OUTPUT = False

# Command-line bibliography attachment mode override.
BIB_ATTACH_CLI: str | None = None

# --attach-csl / --no-attach-csl
CSL_ATTACH_CLI: bool | None = None

# Command-line package bundling override.
BUNDLE_PACKAGES_CLI: bool | None = None

# Command-line source retention mode or path override.
KEEP_SOURCE_CLI: str | bool | None = None

# set by `-o -` on PDF inputs (v3.30.39)
PDF_TO_STDOUT_CLI = False

# filled in by main() from the command line
POLISH_CLI: dict = {}

# --paper, also used by the native renderers
PAPER_CLI: str | None = None

# inkmd's own compile options, from the command line
INKMD_CLI: dict = {}

# Command-line hybrid PDF override.
HYBRID_CLI: bool | None = None

# Non-CLI state copied to spawned batch workers alongside every *_CLI setting.
WORKER_GLOBALS = ("SHOW_FULL_PATHS", "PATH_STYLE", "PATH_UP", "CITEPROC_DISABLED", "FUZZY_LOOKUP", "PART_CUTS", "VERBOSE_OUTPUT")

def worker_state() -> dict:
    return {name: value for name, value in globals().items()
            if (name.endswith("_CLI") or name in WORKER_GLOBALS) and not callable(value)}

def restore_worker_state(state: dict) -> None:
    globals().update(state)
    pdfmd_view.tolerant_streams()
    load_package("pdfmd_log").AUTO_LOG.quiet = True      # the parent prints what a batch found; a worker's summary would repeat per file (v3.28.16)

# Whether this run has reported disabled features.
DISABLED_WARNED = False


def main() -> None:
    """The command: Ctrl-C ends it with one line and the usual exit status 130, not a traceback (v3.30.14). Pandoc and the
    engines are in the same terminal group and get the signal too; the temporary folders are removed on the way out."""
    pdfmd_view.tolerant_streams()      # a character the console's code page lacks prints as `?`, never a traceback
    try:
        run_main()
    except KeyboardInterrupt:
        try:
            sys.stderr.write("\nInterrupted (Ctrl-C).\n")
            sys.stderr.flush()
        except OSError:
            pass
        raise SystemExit(130) from None


# ---------------------------------------------------------------------------
# Python API: `import pdfmd; pdfmd.convert_file("report.md", "docx")`
#
# Every call runs the command-line tool as a subprocess (what pypandoc does with Pandoc): the CLI keeps its
# module-level state to itself, a failure cannot take the caller down, and what you get is what `pdfmd`
# would have made. Nothing is written into the source unless asked (`stamp=True`, `backup=True`).

__all__ = ["PdfmdError", "convert_file", "convert_text", "pdfmd_version"]

API_EXTENSIONS = {"pdf": "pdf", "docx": "docx", "odt": "odt", "pptx": "pptx", "epub": "epub", "html": "html",
                  "html5": "html", "latex": "tex", "tex": "tex", "typst": "typ", "markdown": "md", "md": "md",
                  "plain": "txt", "txt": "txt", "rtf": "rtf", "beamer": "pdf"}
API_TEXT_OUTPUTS = {"html", "html5", "latex", "tex", "typst", "markdown", "md", "plain", "txt", "rtf"}


class PdfmdError(RuntimeError):
    """A conversion that failed: `returncode`, and what pdfmd printed (`stdout`, `stderr`)."""

    def __init__(self, message: str, returncode: int = 1, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def pdfmd_version() -> str:
    return PDFMD_VERSION


def _api_command(source: Path, to: str | None, output: Path, extra_args, metadata, variables, stamp: bool,
                 backup: bool) -> list[str]:
    command = [sys.executable, str(Path(__file__).resolve()), str(source), "-o", str(output.resolve()), "--rewrite"]
    if to and to.lower() not in ("pdf", output.suffix.lstrip(".").lower()):
        command += ["--to", to]
    if not stamp:
        command.append("--no-stamp")
    if not backup:
        command.append("--no-backup")
    if metadata:
        command += ["-y", *map(str, metadata)]
    for key, value in (variables or {}).items():
        command += ["-V", f"{key}={value}"]
    return command + [str(item) for item in extra_args]


def _api_run(command: list[str], cwd: Path | None, timeout: float | None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise PdfmdError(f"pdfmd timed out after {timeout} s", 124) from error


def convert_file(source, to: str | None = None, outputfile=None, *, extra_args=(), metadata=(), variables=None,
                 stamp: bool = False, backup: bool = False, check: bool = True, cwd=None,
                 timeout: float | None = None) -> Path:
    """Convert `source` (Markdown, or any format Pandoc reads) and return the output's path.

    `to` is the target format (`pdf`, `docx`, `odt`, `html`, `latex`, `typst`...; default: from `outputfile`'s
    suffix, else PDF). `outputfile` defaults to the source's name with the format's extension. `metadata` lists
    metadata files, `variables` is a dict of Pandoc variables, `extra_args` anything else the command line takes
    (`["--engine", "typst", "--no-auto", "preamble"]`). Raises `PdfmdError` when the build fails (`check=False`
    returns the path anyway if the file exists)."""
    path = Path(source)
    if not path.exists():
        raise PdfmdError(f"{path} does not exist", 2)
    if outputfile is not None:
        output = Path(outputfile)
    else:
        extension = API_EXTENSIONS.get((to or "pdf").lower(), (to or "pdf").lower())
        output = path.with_suffix("." + extension)
    done = _api_run(_api_command(path, to, output, extra_args, metadata, variables, stamp, backup),
                    Path(cwd) if cwd else None, timeout)
    if check and (done.returncode != 0 or not output.is_file()):
        detail = (done.stderr.strip() or done.stdout.strip()).splitlines()
        raise PdfmdError(f"pdfmd failed ({done.returncode}): {detail[-1] if detail else 'no output'}",
                         done.returncode or 1, done.stdout, done.stderr)
    return output


def convert_text(source: str, to: str = "pdf", format: str = "md", *, extra_args=(), metadata=(), variables=None,
                 outputfile=None, check: bool = True, cwd=None, timeout: float | None = None):
    """Convert text held in memory. Returns the result as `str` for a text format (html, latex, typst, markdown,
    plain) and as `bytes` for the others (pdf, docx, odt, pptx, epub); with `outputfile` the file is kept and
    its path returned. `format` is the input's format by its usual extension (`md`, `rst`, `org`, `tex`...)."""
    with tempfile.TemporaryDirectory(prefix="pdfmd-api-") as directory:
        folder = Path(directory)
        suffix = "." + {"markdown": "md", "latex": "tex", "plain": "txt"}.get(format.lower(), format.lower().lstrip("."))
        path = folder / f"document{suffix}"
        path.write_text(source, encoding="utf-8")
        extension = API_EXTENSIONS.get(to.lower(), to.lower())
        target = Path(outputfile) if outputfile is not None else folder / f"document.{extension}"
        convert_file(path, to, target, extra_args=extra_args, metadata=metadata, variables=variables, check=check,
                     cwd=cwd or folder, timeout=timeout)
        if outputfile is not None:
            return target
        if not target.is_file():
            return "" if to.lower() in API_TEXT_OUTPUTS else b""
        return target.read_text(encoding="utf-8") if to.lower() in API_TEXT_OUTPUTS else target.read_bytes()


if __name__ == "__main__":
    main()
