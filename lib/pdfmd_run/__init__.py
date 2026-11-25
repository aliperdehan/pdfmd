"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_run`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported.

The command line, from its options to the builds: `run_main` (moved whole, plan decision D1), which `main()` in pdfmd.py
calls through a stand-in, and what only it uses: the parser of the run with the options of switched-off features hidden
(`command_line_parser`, `disabled_topics`, `DISABLED_OK_ENV`; lib/pdfmd_doctor reads the parser too), the refusal of such an
option without `--disabled` (`refuse_disabled`) and the PDF info keys of `--pdf-title` and the like (`POLISH_INFO_KEYS`).
What the command line sets (the `*_CLI` names, `SHOW_FULL_PATHS`, `PATH_STYLE`, `VERBOSE_OUTPUT` ...) stays pdfmd's state,
written as `core.X = ...`: the rest of pdfmd reads it as before, and `-j` workers get it with pdfmd's `worker_state()`.
`-b` and `-r` hand `core` to lib/pdfmd_batch and lib/pdfmd_report, where pdfmd.py handed them itself."""

from __future__ import annotations

import argparse
import os
import pdfmd_routing
import re
import shlex
import sys
from pathlib import Path

from pdfmd_base import core


POLISH_INFO_KEYS = {"title": "/Title", "subject": "/Subject", "author": "/Author", "keywords": "/Keywords"}


def disabled_topics() -> list[str]:
    value = core.load_config().get("disabled")
    names = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    names = [str(name).strip().casefold() for name in names]
    try:
        from pdfmd_help import CORE, DISABLEABLE
    except ImportError:
        return []
    wrong = [name for name in names if name not in DISABLEABLE]
    if wrong and not core.DISABLED_WARNED:
        core.DISABLED_WARNED = True
        print(f"WARN  config {core.config_path()}: disabled: {', '.join(wrong)} "
              f"{'is not a feature that can be switched off' if len(wrong) == 1 else 'are not features that can be switched off'}"
              f" (can: {', '.join(DISABLEABLE)}; {', '.join(CORE)} stay on)", file=sys.stderr)
    return [name for name in names if name in DISABLEABLE]


DISABLED_OK_ENV = "PDFMD_ALLOW_DISABLED"     # set by a run that passed the check, for pdfmd's own child processes


def command_line_parser(argv: list[str] | None = None) -> tuple[argparse.ArgumentParser, list[argparse.Action]]:
    """The parser for this run, with the options of switched-off features hidden unless --disabled is on it (or this
    is pdfmd's own child process: the Word route, --doctor --deep, --watch ... pass --no-stamp and the like)."""
    parser = core.build_parser()
    argv = sys.argv[1:] if argv is None else argv
    if "--disabled" in argv or os.environ.get(DISABLED_OK_ENV):
        return parser, []
    try:
        from pdfmd_help import hide
    except ImportError:
        return parser, []
    return parser, hide(parser, disabled_topics())


def refuse_disabled(args: argparse.Namespace, hidden: list[argparse.Action],
                    parser: argparse.ArgumentParser | None = None) -> None:
    """Stop when the command line used an option of a switched-off feature without --disabled. "Used" is a value that
    differs from what the parser gives with no options at all (two flags sharing a dest, --strip-comments and
    --keep-comments, have different defaults of their own); a dest a visible option shares is never refused."""
    if not hidden:
        return
    from_help = __import__("pdfmd_help")
    baseline = vars((parser or core.build_parser()).parse_known_args([])[0])
    visible = {action.dest for action in (parser or core.build_parser())._actions if action not in hidden}
    for action in hidden:
        if action.dest not in visible and getattr(args, action.dest, None) != baseline.get(action.dest):
            name = next((item for item in action.option_strings if item.startswith("--")), action.option_strings[0])
            topics = " and ".join(sorted(from_help.topics_of(action)))
            raise SystemExit(f"{name}: the {topics} features are switched off (`pdfmd --setup`, d). Run it once with "
                             f"`pdfmd --disabled {name} ...`, or switch them back on.")


def run_main() -> None:
    parser, hidden = command_line_parser()
    argv, excerpts = sys.argv[1:], None
    if "--excerpts" in argv:
        # `--excerpts` takes the rest of the line as its own command line. argparse's REMAINDER does not hold on to
        # it on Python 3.9 and 3.10 (`--page` was read as an ambiguous pdfmd option): split it off before parsing.
        at = argv.index("--excerpts")
        argv, excerpts = argv[:at + 1], argv[at + 1:]
    args, pandoc_options = parser.parse_known_args(core.load_package("pdfmd_args").normalise_metadata_options(argv))
    refuse_disabled(args, hidden, parser)
    if args.excerpts is not None:
        raise SystemExit(core.load_package("pdfmd_excerpts.cli").command(list(args.excerpts if excerpts is None else excerpts)))
    if args.bopen is not None:
        try:
            core.parse_bopen(args.bopen)
        except SystemExit:
            if not Path(args.bopen).exists():
                raise
            args.path = [Path(args.bopen), *(args.path or [])]       # `--bopen notes`: the folder, not a spec
            args.bopen = "all"
        if not args.batch:
            args.open = True
    if hidden or args.disabled:
        os.environ[DISABLED_OK_ENV] = "1"          # pdfmd's own child processes are not refused again
    if args.ascii_stdio:       # pdfmd_lua/ascii.lua's helper: text in, ASCII text out (see pdfmd_flat/asciify.py)
        from pdfmd_flat import asciify
        raise SystemExit(asciify.serve(*args.ascii_stdio))
    if args.trust_lua:
        raise SystemExit(0 if core.trust_lua(args.trust_lua) else 1)
    if args.path and all(path.suffix.lower() == ".pdf" for path in args.path):
        # Reading a PDF: the unknown flags are batchocr's, and an abbreviation must not
        # swallow one (`-c` is batchocr's --concat and an abbreviation of pdfmd's -cwd).
        reader_parser = core.build_parser()
        reader_parser.allow_abbrev = False
        for flag in [flag for flag in reader_parser._option_string_actions if len(flag) > 2 and flag[1] != "-"]:
            del reader_parser._option_string_actions[flag]     # `-cwd`: older argparse still abbreviates it
        args, pandoc_options = reader_parser.parse_known_args()
    core.use_managed_tools()
    if not (args.path and all(path.suffix.lower() == ".pdf" for path in args.path)):
        from pdfmd_args.paths import invocation_paths
        pandoc_options = invocation_paths(pandoc_options, Path.cwd())
    core.provide_writable_places()
    if args.json:
        if args.show_config == args.doctor or args.init_config:
            raise SystemExit("--json goes with either --show-config or --doctor")
        if args.deep and not args.doctor:
            raise SystemExit("--deep goes with --doctor: pdfmd --doctor --deep")
        if args.show_config:
            if (args.verbose or args.debug) and core.config_path() is None:
                core.load_package("pdfmd_config").note_config_off()
            raise SystemExit(0 if core.config_report(document=args.path[0] if args.path else None, as_json=True) else 1)
    if args.merge:
        # --merge (v3.27.6): one Markdown file that builds alone, = --assemble-only --embed-metadata all
        if args.no_embed_metadata:
            raise SystemExit("--merge embeds everything; it contradicts --no-embed-metadata")
        args.assemble_only = True
        if args.embed_metadata is None:
            args.embed_metadata = ["all"]
    if args.debug:
        args.verbose = True
    if args.verbose and core.config_path() is None:
        core.load_package("pdfmd_config").note_config_off()
    args.to_many = None
    if args.to and "," in args.to:
        # `--to png,pdf`: several picture formats from one build (see picture_command)
        wanted = []
        for name in args.to.split(","):
            name = name.strip().casefold().lstrip(".")
            name = core.DEFAULT_OUTPUT_ALIASES.get(name, name)
            if name and name not in wanted:
                wanted.append(name)
        args.to_many, args.to = wanted, wanted[0]
    if args.to:
        # `--to md`, `--to tex`, `--to typ`: the names of the files, as `default-output:` takes them
        args.to = args.to.strip().casefold().lstrip(".")
        args.to, ascii_asked = core.split_ascii_target(args.to)
        core.ASCII_CLI["on"] = ascii_asked
        args.to = core.DEFAULT_OUTPUT_ALIASES.get(args.to, args.to)
    if args.view:
        if args.to and args.to != "ansi":
            raise SystemExit(f"--view shows the styled terminal text (--to ansi); it cannot be combined with --to {args.to}")
        args.to = "ansi"
        if args.out is not None and str(args.out) != "-":
            args.view = False                         # -o FILE saves it: no pager, nothing shown (one meaning per flag)
    if args.color:
        os.environ[core.ANSI_COLOR_ENV] = args.color
    if args.width:
        os.environ[core.ANSI_WIDTH_ENV] = str(args.width)
    if (args.out is not None and str(args.out) == "-" and not args.view and args.path
            and all(path.suffix.lower() == ".pdf" for path in args.path)):
        args.out, core.PDF_TO_STDOUT_CLI = None, True     # `pdfmd x.pdf -o -`: the Markdown on standard output (M1ck4's pdfmd pipes so)
    if args.view or (args.out is not None and str(args.out) == "-"):
        raise SystemExit(core.terminal_view(args))
    if args.path and [str(path) for path in args.path] == ["-"]:
        core.stdin_build(args)
    core.set_kit_cli(args.kit, args.kit_stack)
    core.REWRITE_CLI = True if args.watch else args.rewrite       # a watch rebuilds the same file on every save
    core.BUNDLE_PACKAGES_CLI = args.bundle_packages
    core.STRIP_COMMENTS_CLI = args.strip_comments
    core.STRIP_KINDS_CLI = core.comment_kind_set(args.strip_comments_in)
    core.KEEP_KINDS_CLI = core.comment_kind_set(args.keep_comments_in)
    core.BIB_ATTACH_CLI = args.attach_bibliography
    core.CSL_ATTACH_CLI = args.attach_csl
    core.CSS_CLI[:] = args.css
    core.CSS_SCOPE_CLI = args.css_scope
    core.ATTACH_CLI = args.attach_source
    core.KEEP_SOURCE_CLI = args.keep_source
    core.HYBRID_CLI = args.hybrid
    core.BUNDLE_CLI = args.bundle
    core.VERBOSE_OUTPUT = bool(args.verbose)
    core.AUTO_LOG.reset(dedupe=bool(args.batch) or len(args.path or []) > 1)
    core.PAPER_CLI = args.paper
    core.INKMD_CLI.clear()
    for flag, key, value in (("family", "family", args.family), ("no_autolinks", "autolinks", False),
                             ("no_html", "html", False), ("allow_unsafe_urls", "safe", False),
                             ("allow_remote_images", "allow_remote_images", True),
                             ("emoji_fallback", "emoji_fallback", args.emoji_fallback)):
        if getattr(args, flag) not in (None, False):
            core.INKMD_CLI[key] = value
    core.IMAGE_DPI_CLI = args.image_dpi
    core.CODE_CLI.clear()
    if args.line_numbers:
        core.CODE_CLI["line-numbers"] = True
        if args.line_numbers.isdigit() and int(args.line_numbers) > 1:
            core.CODE_CLI["line-number-step"] = int(args.line_numbers)
    if args.no_code_wrap:
        core.CODE_CLI["code-wrap"] = False
    core.POLISH_CLI.clear()
    configured = core.config_options()          # the config file's defaults (pdfmd --setup); the command line wins
    core.POLISH_CLI.update(header=args.header or configured.get("header") or None,
                      footer=args.footer or configured.get("footer") or None,
                      bookmarks=args.bookmarks or bool(configured.get("bookmarks")),
                      attach_links=args.attach_links or bool(configured.get("attach-links")),
                      crop=(args.crop, args.crop_pad, args.crop_ignore_bottom, args.crop_page),
                      info={POLISH_INFO_KEYS[name]: getattr(args, f"pdf_{name}")
                            for name in POLISH_INFO_KEYS if getattr(args, f"pdf_{name}")})
    if args.restore is not None:
        restorer = (core.restore_from_markdown if args.restore.suffix.lower() in (".md", ".markdown")
                    else core.restore_from_pdf)
        raise SystemExit(restorer(args.restore, args.out.resolve() if args.out else None, args.list_only))
    # -v/--verbose (or --debug) writes full paths, as it always did; otherwise the style is a setting (entry 3ea): --path-style,
    # then the folder settings above the first document, then the config (the folder settings are read at the first input only:
    # the style is one for the whole run).
    core.SHOW_FULL_PATHS = args.full_paths
    first_input = next(iter(args.path or []), None)
    if first_input is not None and Path(first_input).is_dir():
        first_input = Path(first_input) / "x.md"
    core.PATH_STYLE, core.PATH_UP = core.path_style_settings(args.path_style, args.path_up, first_input, args.verbose)
    core.CITEPROC_DISABLED = args.no_citeproc
    core.PAGE_NUMBERS_CLI = args.page_numbers
    # A CLI switch only: the document's own `pdfmd-options: no-auto` cannot
    # turn off the lookup that is still busy finding that document.
    core.FUZZY_LOOKUP = not core.auto_disabled(args.no_auto, "lookup")
    core.NO_AUTO_CLI = args.no_auto
    core.FALLBACK_CLI, core.MISSING_CLI, core.STRICT_CLI = args.fallback, args.missing, args.strict
    core.ENGINE_CLI, core.ENGINE_FALLBACK_CLI = args.engine, args.engine_fallback
    if args.strict is not None:
        os.environ["PDFMD_STRICT"] = "1" if args.strict else "0"
    if args.shrink is not None:
        os.environ["PDFMD_SHRINK"] = "true" if args.shrink else "false"      # a -j worker is a fresh process: it reads this
    core.BUILD_TIME_CLI, core.TIME_FORMAT_CLI, core.BUILD_LOG_CLI = args.build_time, args.time_format, args.build_log
    if args.build_log:
        os.environ["PDFMD_BUILD_LOG"] = args.build_log
    os.environ.setdefault("PDFMD_COMMAND_LINE", shlex.join(sys.argv[1:]))
    if args.build_time is not None:
        os.environ["PDFMD_BUILD_TIME"] = "1" if args.build_time else "0"
    if args.time_format:
        timing = core.timing_module()
        problem = timing.check_style(args.time_format) if timing else None
        if problem:
            raise SystemExit(f"--time-format: {problem}")
        os.environ["PDFMD_TIME_FORMAT"] = args.time_format
    for value, variable in ((args.csv_rows, core.CSV_ENV["rows"]), (args.csv_cols, core.CSV_ENV["cols"]), (args.csv_note, core.CSV_NOTE_ENV)):
        if value is not None:
            os.environ[variable] = str(value)
    if args.csv is not None:
        os.environ[core.CSV_ENABLED_ENV] = "on" if args.csv else "off"
    if args.calc is not None:
        os.environ[core.CALC_ENV] = "on" if args.calc else "off"
    if args.calc_digits is not None:
        os.environ[core.CALC_DIGITS_ENV] = args.calc_digits
    if args.calc_round is not None:
        os.environ[core.CALC_ROUND_ENV] = args.calc_round
    if args.calc_subs is not None:
        os.environ[core.CALC_SUBS_ENV] = "true" if args.calc_subs else "false"
    if args.calc_typeset is not None:
        os.environ[core.CALC_TYPESET_ENV] = args.calc_typeset
    for style, env in core.CALC_TYPESET_STYLE_ENVS.items():
        if getattr(args, "calc_typeset_" + style) is not None:
            os.environ[env] = getattr(args, "calc_typeset_" + style)
    if args.calc_noindent is not None:
        os.environ[core.CALC_NOINDENT_ENV] = args.calc_noindent
    if args.calc_space is not None:
        os.environ[core.CALC_SPACE_ENV] = args.calc_space
    if args.paragraph_spacing is not None:
        core.paragraph_spacing_command_line(args.paragraph_spacing)
    if args.bibliography_indent is not None:
        core.bibliography_indent_command_line(args.bibliography_indent)
    if args.pagecite is not None:
        core.deferred("pdfmd_excerpts.pagecite", "command_line")(args.pagecite)
    if args.fullcite_list is not None:
        core.fullcite_command_line(args.fullcite_list)
    if args.calc_align is not None:
        os.environ[core.CALC_ALIGN_ENV] = args.calc_align
    if args.calc_constants is not None:
        os.environ[core.CALC_CONSTANTS_ENV] = args.calc_constants
    if args.calc_export is not None:
        os.environ[core.CALC_EXPORT_ENV] = args.calc_export
    if args.table_keep is not None:
        os.environ[core.TABLE_KEEP_ENV] = str(args.table_keep)
    core.TABLE_REPAIR_CLI = args.table_repair
    for value, variable in ((args.max_asset_mb, "PDFMD_MAX_ASSET_MB"), (args.max_output_mb, "PDFMD_MAX_OUTPUT_MB")):
        if value is not None:
            os.environ[variable] = str(value)
    configured = core.load_config().get("translit")
    if isinstance(configured, list):
        configured = ",".join(str(item) for item in configured)
    if args.translit is not None:
        translit = args.translit
    elif os.environ.get("PDFMD_TRANSLIT") is not None:
        translit = os.environ["PDFMD_TRANSLIT"]
    else:
        translit = configured
    if translit and translit.strip().casefold() == "list" and not args.json:
        raise SystemExit(0 if core.translit_report() else 1)
    for problem in core.set_translit(translit):
        print(f"WARN  --translit: {problem}", file=sys.stderr)
    core.CACHE_PLOTS_CLI = args.cache_plots or None
    core.SEED_LABELS_CLI = args.seed_labels
    core.SEED_CALC_CLI = args.seed_calc
    core.METADATA_PRECEDENCE_CLI = args.metadata_precedence
    core.PRESET_CLI, core.GLOBAL_METADATA_CLI = args.preset, args.global_metadata
    core.CACHE_LOCATION_CLI = args.cache_location
    core.RAW_CLI.update({"all": args.raw, "off": args.no_raw, "for": list(args.raw_for or [])})
    core.PAGEBREAK_CLI.update({"kinds": args.pagebreak, "off": args.no_pagebreak})
    core.LINEBREAK_CLI.update({"kinds": args.linebreak, "off": args.no_linebreak})
    core.MARKUP_CLI.update({"kinds": args.markup, "off": args.no_markup})
    core.SHOW_COMMENTS_CLI["on"] = args.show_comments
    core.SHOW_HIDDEN_CLI = args.show_hidden
    core.FLAVOUR_CLI["name"] = args.flavour
    core.UNCLOSED_CLI["mode"] = args.unclosed_comment
    core.GFM_CLI.update({"scripts": args.gfm_scripts, "math": args.gfm_math})
    core.ASCII_CLI["missing"] = args.ascii_missing
    if args.serve is not None:
        raise SystemExit(core.serve_command(args))
    if args.api is not None:
        raise SystemExit(core.api_command(list(args.api)))
    if args.init_reference:
        raise SystemExit(0 if core.init_reference(args.init_reference) else 1)
    if args.completion:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(newline="\n")          # CRLF in a shell script breaks it in Git Bash and WSL
        sys.stdout.write(core.completion_script(args.completion))
        raise SystemExit(0)
    if args.user_path or args.add_to_path is not None or args.remove_from_path or args.show_user_path:
        raise SystemExit(core.user_path_command(args))
    if args.deep and not args.doctor:
        raise SystemExit("--deep goes with --doctor: pdfmd --doctor --deep")
    if args.doctor:
        raise SystemExit(0 if core.doctor_report(deep=args.deep, as_json=args.json) else 1)
    if args.cache_info or isinstance(args.clear_cache, str):
        status = core.cache_command(args)                        # --cache-info, --clear-cache WHAT (pdfmd_cache.manage)
        if status is not None:
            raise SystemExit(status)
    pdf_input = any(path.suffix.casefold() == ".pdf" for path in args.path or [])
    if (args.crop is False or (args.crop is None and pdf_input)) and any(
            value is not None for value in (args.crop_pad, args.crop_ignore_bottom, args.crop_page)):
        from pdfmd_crop.build import CROP_OPTIONS_REQUIRED
        raise SystemExit(CROP_OPTIONS_REQUIRED)
    if args.image_quality is not None and not (args.crop or args.to_many or core.picture_target(args) in core.PICTURE_ONLY):
        raise SystemExit("--image-quality goes with --to png, jpg, tiff, eps, ps or svg")
    if (args.image_dpi is not None and args.path and all(path.suffix.lower() == ".pdf" for path in args.path)
            and not (args.crop or args.to_many or core.picture_target(args) in core.PICTURE_ONLY)):
        raise SystemExit("--image-dpi on a PDF input goes with --to png, jpg, tiff, eps, ps or svg")
    if args.to_many:
        raise SystemExit(core.multi_target_command(args))
    picture = core.picture_target(args)
    if picture in core.PICTURE_ONLY or (args.crop and (pdf_input or picture not in (None, "pdf"))):
        raise SystemExit(core.picture_command(args))
    if args.check_docx:
        raise SystemExit(core.check_docx_command(args, pandoc_options))
    if args.init is not None:
        raise SystemExit(core.init_command(args))
    if args.check_ignore and not args.check:
        raise SystemExit("--check-ignore goes with --check: pdfmd --check --check-ignore heading-jump")
    if args.check:
        raise SystemExit(core.check_command(args, pandoc_options))
    if args.check_dependencies:
        raise SystemExit(0 if core.dependency_report() else 1)
    if args.extract_tables or args.expand_tables or args.extract_inline_csv or args.fix_tables is not None:
        raise SystemExit(core.tables_command(args))
    if args.failed and not args.last_build:
        raise SystemExit("--failed goes with --last-build: pdfmd --last-build --failed FILE")
    if args.last_build:
        raise SystemExit(core.last_build_command(args))
    if args.history or args.history_diff or args.history_restore:
        if args.history_diff and args.history_restore:
            raise SystemExit("--history-diff and --history-restore are different things; pick one.")
        raise SystemExit(core.history_view_command(args))
    if args.init_backups:
        raise SystemExit(core.init_backups_command(args))
    if args.history_to_file or args.history_to_notes or args.merge_history:
        if args.history_to_file and args.history_to_notes:
            raise SystemExit("--history-to-file and --history-to-notes are opposites; pick one.")
        raise SystemExit(core.history_command(args))
    if args.check_fonts:
        ok = True
        for target in (args.path or [Path.cwd()]):
            try:
                document = core.find_markdown(target)
            except FileNotFoundError as error:
                raise SystemExit(str(error))
            ok = core.check_fonts(document, args.no_auto, list(args.variable or [])) and ok
        raise SystemExit(0 if ok else 1)
    if args.edit:
        raise SystemExit(core.edit_command(args))
    if args.init_vscode:
        raise SystemExit(core.init_vscode_command(args))
    if args.show_config or args.init_config:
        raise SystemExit(0 if core.config_report(init=args.init_config, document=args.path[0] if args.path else None,
                                                no_auto=args.no_auto, metadata_request=args.metadata_file) else 1)
    if args.presets:
        raise SystemExit(0 if core.presets_report(args.path[0] if args.path else None) else 1)
    if args.kits is not None:
        raise SystemExit(0 if core.kits_report(list(args.kits), args.no_auto) else 1)
    if args.which is not None:
        raise SystemExit(0 if core.which_command(list(args.which), args) else 1)
    if args.check_source:
        raise SystemExit(0 if core.check_source_command(list(args.path or []), args.recursive) else 1)
    if args.doc is not None:
        raise SystemExit(core.doc_command(args.doc, args.doc_print, args.doc_path))
    if args.doc_print or args.doc_path:
        raise SystemExit("--print and --path go with --doc: pdfmd --doc readme --print")
    if args.setup is not None:
        raise SystemExit(0 if core.setup_command(args.setup) else 1)
    if args.install is not None:
        raise SystemExit(0 if core.install_extra(args.install, bool(getattr(args, "yes", False))) else 1)
    if args.uninstall:
        if args.uninstall.startswith("kit"):
            raise SystemExit(0 if core.uninstall_kit(args.uninstall.partition(":")[2]) else 1)
        if args.uninstall.startswith("ocr"):
            raise SystemExit(0 if core.install_ocr_languages(args.uninstall.partition(":")[2], remove=True) else 1)
        raise SystemExit(0 if core.uninstall_fonts(args.uninstall.partition(":")[2]) else 1)
    if args.batch or (not args.report and len(args.path or []) > 1):
        from pdfmd_batch import prepare_inputs
        prepare_inputs(core, args)
    else:
        routed = core.route_pdf_input(args, pandoc_options)
        if routed is not None:
            raise SystemExit(routed)
        routed = core.route_text_input(args, pandoc_options)
        if routed is not None:
            raise SystemExit(routed)
        core.route_ebook_input(args)
    if not pdfmd_routing.quarto_input(args) and not core.which("pandoc") and not core.native_possible(args):
        raise SystemExit(core.PANDOC_MISSING)
    paths = args.path or [Path.cwd()]
    if args.clear_cache:
        if args.path:
            try:
                document = core.find_markdown(paths[0])
            except FileNotFoundError as error:
                raise SystemExit(str(error))
            plan = core.plan_scaffold(document, [], args.no_auto, args.metadata_file)
            source = plan.scaffold if plan else document
            local = source.resolve().parent / core.LOCAL_CACHE_DIRNAME
            status = core.remove_cache_paths([core.cache_directory(source), core.cache_directory(source, local)], [core.cache_root(), local])
        else:
            status = core.clear_cache("all")                     # the cache folder and ./.cache/pdfmd (v3.33.74: with sizes)
        if status:
            raise SystemExit(status)
        return
    if args.slim and not args.unpack:
        raise SystemExit("--slim goes with --unpack")
    if args.unpack:
        if len(paths) != 1 or not args.path:
            raise SystemExit("--unpack takes one assembled Markdown file")
        try:
            raise SystemExit(core.unpack_assembled(core.find_markdown(paths[0]), args.out.resolve() if args.out else None,
                                              slim=args.slim))
        except FileNotFoundError as error:
            raise SystemExit(str(error))
    if args.split:
        if len(paths) != 1:
            raise SystemExit("--split takes one Markdown file")
        try:
            raise SystemExit(core.split_into_parts(core.find_markdown(paths[0]), args.split.resolve(), max(1, args.split_depth)))
        except FileNotFoundError as error:
            raise SystemExit(str(error))
    variables = core.DEFAULT_VARS + args.variable
    if args.paper and not any(variable.startswith("papersize") for variable in args.variable):
        variables = variables + [f"papersize={args.paper}"]
    stamp_overrides: dict = {}
    if args.stamp:
        stamp_overrides["enabled"] = True
    if args.no_stamp:
        stamp_overrides["enabled"] = False
    if args.stamp_mode:
        stamp_overrides["mode"] = args.stamp_mode
    if args.stamp_packages:
        stamp_overrides["packages"] = args.stamp_packages
    if args.stamp_scope:
        stamp_overrides["scope"] = args.stamp_scope
    if args.stamp_store:
        stamp_overrides["store"] = args.stamp_store
    if args.stamp_output:
        stamp_overrides["include_output"] = True
    if args.no_stamp_output:
        stamp_overrides["include_output"] = False
    if args.stamp_partial:
        stamp_overrides["partial"] = True
    if args.no_stamp_partial:
        stamp_overrides["partial"] = False
    if args.stamp_pdf_metadata:
        stamp_overrides["pdf_metadata"] = True
    if args.no_stamp_pdf_metadata:
        stamp_overrides["pdf_metadata"] = False
    if args.no_auto:
        unknown = sorted(set(args.no_auto) - core.NO_AUTO_KINDS)
        if unknown:
            raise SystemExit(f"Unknown --no-auto kind(s): {', '.join(unknown)}. "
                             f"Valid: {', '.join(sorted(core.NO_AUTO_KINDS))}")
    if args.batch and args.report:
        raise SystemExit("Choose either --batch or --report/--book, not both")
    from pdfmd_run import presentation as slides

    cli_presentation = "-p/--presentation" if args.presentation else None
    if cli_presentation and args.report:
        slides.validate(cli_presentation, "pdf", None, report=True)

    # Stop-at stage (see STOP_STAGES). --assemble-only is --stop-at markdown;
    # so is an -o ending .assembled.md (single-file/report only, like every
    # -o extension below). The stage then fixes the target format: `tex` is
    # --to latex (beamer with -p), `markdown` is the internal assembled one.
    stop_at = args.stop_at
    if args.assemble_only:
        if stop_at not in (None, "markdown"):
            raise SystemExit(f"--assemble-only means --stop-at markdown; it conflicts with --stop-at {stop_at}")
        stop_at = "markdown"
    if (stop_at is None and args.out and not args.batch
            and args.out.name.casefold().endswith(core.ASSEMBLED_SUFFIX)):
        stop_at = "markdown"
    embed_request = None
    if args.no_embed_metadata and args.embed_metadata is not None:
        raise SystemExit("--embed-metadata and --no-embed-metadata contradict each other")
    if args.lua_mode is not None and args.embed_metadata is None and stop_at != "markdown":
        raise SystemExit("--lua-mode applies to --stop-at markdown (--assemble-only) only")
    if args.embed_metadata is not None:
        unknown_kinds = sorted(set(args.embed_metadata) - {*core.EMBED_ALL, "all"})
        if unknown_kinds:
            raise SystemExit(f"Unknown --embed-metadata kind(s): {', '.join(unknown_kinds)}. "
                             f"Valid: {', '.join(core.EMBED_ALL)}, all")
        if stop_at != "markdown":
            raise SystemExit("--embed-metadata applies to --stop-at markdown (--assemble-only) only")
        wanted = (set(core.EMBED_KINDS) if not args.embed_metadata
                  else set(core.EMBED_ALL) if "all" in args.embed_metadata else set(args.embed_metadata))
        embed_request = core.EmbedRequest(frozenset(wanted), args.lua_mode, False)
    elif stop_at == "markdown":
        # No kinds named: each document's own pdfmd-options.embed decides.
        embed_request = core.EmbedRequest(None, args.lua_mode, args.no_embed_metadata)
    if stop_at in ("markdown", "tex"):
        if args.to:
            raise SystemExit(f"--stop-at {stop_at} fixes the output format; drop --to {args.to}")
        out_format = core.format_from_output(args.out) if args.out and not args.batch else None
        if stop_at == "tex" and out_format not in (None, "latex"):
            raise SystemExit(f"--stop-at tex writes a .tex file; -o {args.out} names another format")
        if stop_at == "markdown" and out_format not in (None, "markdown"):
            raise SystemExit(f"--stop-at markdown writes Markdown; -o {args.out} names another format")
        if stop_at == "markdown" and args.engine is not None:
            print("WARN  --engine is ignored for --stop-at markdown: no engine is involved",
                  file=sys.stderr)

    # Target format: explicit --to wins; otherwise a recognized -o/--out
    # extension implies it (single-file/report only -- batch's -o is a
    # directory, so it only responds to --to); default is pdf.
    target_format = (
        (args.to.casefold() if args.to else None)
        or (core.format_from_output(args.out) if args.out and not args.batch else None)
        or "pdf"
    )
    target_format, ascii_named = core.split_ascii_target(target_format)      # `-o notes.ascii.txt`
    core.ASCII_CLI["on"] = core.ASCII_CLI["on"] or ascii_named
    if cli_presentation:
        slides.validate(cli_presentation, target_format, stop_at)
    if stop_at == "markdown":
        target_format = core.ASSEMBLED_FORMAT
    elif stop_at == "tex":
        target_format = "latex"
    metadata_by_dir = {}
    metadata_announced = set()

    def metadata_for(file, document_class=None, announce=True):
        """The metadata files of a document, looked up once. They are announced (FOUND) at the first call that
        has ``announce``: a batch looks every file up before building any (announce=False) and announces each file's
        metadata when it builds it, so each file's FOUND line lists its own files (v3.34.34)."""
        directory = file.parent.resolve()
        cache_key = (directory, file.name.casefold())
        if cache_key not in metadata_by_dir:
            if (document_class is None and not args.batch
                    and file.suffix.lower() not in core.OFFICE_INPUT_EXTENSIONS):
                document_class = (core.frontmatter_value(file, "documentclass")
                                  or core.frontmatter_value(file, "class"))
            # An explicit -y/--metadata-file always wins over --no-auto
            # metadata; only auto-discovery (args.metadata_file is None) is
            # what --no-auto metadata/yaml suppresses -- per file, since
            # each file's own pdfmd-options can differ even in one batch.
            file_no_auto = core.effective_no_auto(file, args.no_auto)
            requested = ([] if args.metadata_file is None
                        and core.auto_disabled(file_no_auto, "metadata")
                        else args.metadata_file)
            if requested is None:
                # pdfmd-options.yaml / .metadata: the document names its own
                # metadata files (like -y, but written in the document).
                requested = core.option_names(core.frontmatter_pdfmd_options(file), "yaml") or None
            metadata_by_dir[cache_key] = core.find_metadata(directory, requested,
                                                        document_class=document_class,
                                                        document_stem=file.stem, document=file,
                                                        discover=not (requested is None and core.discovery_disabled(file_no_auto, "metadata")))
        if announce and cache_key not in metadata_announced:
            metadata_announced.add(cache_key)
            discovered = metadata_by_dir[cache_key]
            if args.metadata_file is None and discovered is not None and discovered is not core.AUTO_METADATA_DISABLED:
                paths = discovered if isinstance(discovered, list) else [discovered]
                for path in paths:
                    core.AUTO_LOG.record_file("YAML", path, args.verbose)
        value = metadata_by_dir[cache_key]
        return None if value is core.AUTO_METADATA_DISABLED else value

    newest_used: list[bool] = []

    def only_markdown_in(directory: Path) -> Path:
        """The one Markdown file of a folder (what `pdfmd` and `pdfmd '#section'` mean)."""
        markdown_files = sorted(directory.glob("*.md"), key=lambda path: path.name.casefold())
        if not markdown_files:
            hint = ""
            try:
                if not sys.stdin.isatty():
                    hint = " To build Markdown piped in, name it: `pdfmd -` reads standard input."
            except (AttributeError, ValueError, OSError):
                pass
            raise SystemExit("No Markdown files found in the current directory." + hint)
        picking = len(markdown_files) > 1 and (args.newest or core.priority_enabled(directory))
        if picking:
            markdown_files = core.source_markdown(markdown_files)
        if len(markdown_files) > 1:
            if picking:
                newest_used.append(True)
                return core.choose_markdown(markdown_files, args.newest, args.include_never)
            names = ", ".join(path.name for path in markdown_files)
            raise SystemExit(
                f"Multiple Markdown files found: {names}\n"
                "Specify one file, use -b to convert all separately, or use -r to combine them."
            )
        print(f"AUTO MD    {core.display_path(markdown_files[0])}")
        return markdown_files[0]

    if not args.path and not args.batch and not args.report:
        paths = [only_markdown_in(Path.cwd())]
    # `pdfmd report#intro` is shorthand for --section: a part in parts mode,
    # any heading (or {#id}) otherwise. A literal path with a '#' in its name
    # wins, so nothing that already worked changes meaning. `doc##name` asks
    # for a level-2 heading (see find_heading); `#name` alone, with no
    # document, means the folder's only Markdown file.
    section_requests = core.split_section_requests(args.section)
    # `@` says the same as `#` (`pdfmd report@intro`, `doc@@yield`): an interactive bash and some other shells take a `#`
    # for the start of a comment and never pass it on.
    if len(paths) == 1 and re.search(r"[#@]", str(paths[0])) and not paths[0].exists():
        # The whole string, not .name: a section path (`doc#results/yield`) has a slash.
        base, separator, suffix = re.split(r"([#@])", str(paths[0]), maxsplit=1)
        if os.sep != "/":
            suffix = suffix.replace(os.sep, "/")        # Path turned `doc#results/yield` into `doc#results\\yield` on Windows
        if base and not base.endswith(("/", os.sep)):
            paths = [Path(base)]
        else:
            paths = [only_markdown_in(Path(base) if base else Path.cwd())]
        # `doc#name` asks for `name`; `doc##name` for `##name`, a level-2 heading.
        section_requests += core.split_section_requests(["#" + suffix.replace("@", "#", 1) if suffix.startswith(("#", "@")) else suffix])
    if args.newest and not newest_used:
        print("WARN  --newest picks among the Markdown files of a folder for a bare `pdfmd` (or `pdfmd '#section'`); "
              "it does nothing with a named file, -b or -r", file=sys.stderr)
    plan_source = None
    single_input = not args.batch and not args.report and len(paths) == 1
    presentation_request = cli_presentation
    if single_input:
        try:
            plan_source = core.find_markdown(paths[0])
            if args.presentation is None:
                metadata = None if plan_source.suffix.lower() == ".qmd" else metadata_for(plan_source)
                presentation_request = slides.source(plan_source, metadata, args.presentation)
        except (FileNotFoundError, ValueError) as error:
            raise SystemExit(str(error))
        if presentation_request:
            slides.validate(presentation_request, target_format, stop_at, document=plan_source)
            if stop_at == "tex":
                target_format = "beamer"
    presentation = bool(presentation_request)
    if stop_at == "markdown" and args.watch:
        raise SystemExit("--stop-at markdown can't be combined with -p/--presentation or -w/--watch")

    def plan_bridge(target_format):
        if stop_at is not None:
            return target_format, None
        goal = core.calibre_goal(args.engine, target_format)
        if goal:
            if args.engine is not None and not core.calibre_asked_first(args.engine):
                print(f"WARN  --engine is ignored for --to {target_format}: Calibre writes it", file=sys.stderr)
            return "epub", core.start_calibre_job(args, goal, target_format, pandoc_options)
        goal = core.soffice_goal(args.engine, target_format)
        if goal:
            if args.engine is not None and not core.soffice_asked_first(args.engine):
                print(f"WARN  --engine is ignored for --to {target_format}: LibreOffice writes it", file=sys.stderr)
            return "docx", core.start_soffice_job(args, goal, target_format)
        return target_format, None

    convert_job = None
    if single_input:
        target_format, convert_job = plan_bridge(target_format)
    if (args.engine is not None and target_format != "pdf" and stop_at != "markdown"
            and not (target_format == "odt" and args.engine.strip().casefold() == "pandoc")):
        print(f"WARN  --engine is ignored for "
              f"{'--stop-at tex' if stop_at == 'tex' else f'--to {target_format}'}: "
              "no PDF engine is involved", file=sys.stderr)
    # Explicit: the command line named a format (or a stage), so a document's
    # pdfmd-options.default-output does not apply.
    target_explicit = (stop_at is not None or bool(args.to) or presentation or args.crop is True
                       or bool(core.format_from_output(args.out) if args.out and not args.batch else None))
    engines: list[str] = []
    engines_error: SystemExit | None = None
    if target_format == "pdf" and not presentation:
        try:
            engines = core.select_engines(args.engine, False)
        except SystemExit as error:
            if target_explicit and single_input:
                raise
            # A document can choose its own output or the Beamer engine chain.
            engines_error = error
    native_auto = (bool(engines) and not args.engine
                   and all(core.is_native_engine(engine) for engine in engines))
    if native_auto:
        core.native_run_note(engines)

    def need_engines(format_name: str) -> None:
        if format_name == "pdf" and engines_error is not None:
            raise engines_error

    def default_target(document: Path, metadata_files: list[Path]) -> str:
        """target_format, or the document's own default-output (never over an explicit one)."""
        if args.report:
            if request := slides.source(document, metadata_files, args.presentation):
                slides.validate(request, target_format, stop_at, report=True)
            plan_bridge(target_format)
        if target_explicit:
            return target_format
        chosen = core.default_output_format(document, metadata_files)
        if chosen and chosen != target_format:
            print(f"AUTO OUTPUT  {core.display_path(document)}: default-output {chosen} (pdfmd-options)")
        return chosen or target_format

    scaffold_plan = None
    section_plan = None
    single_document = single_input and not presentation
    if single_document:
        scaffold_plan = core.plan_scaffold(plan_source, section_requests, args.no_auto, args.metadata_file,
                                          merge=args.merge, include_never=args.include_never)
    if scaffold_plan is None and (section_requests or args.list_parts):
        if not single_document:
            raise SystemExit("--section, --list-parts and 'name#section' take one document, "
                             f"not -b/--batch, -r/--report or {presentation_request or '-p/--presentation'}")
        if plan_source.suffix.lower() != ".md":
            raise SystemExit(f"{plan_source}: sections can only be taken from a Markdown (.md) document")
        if args.list_parts:
            core.print_headings(plan_source, args.no_auto, args.metadata_file)
            return
        section_plan = core.plan_sections(plan_source, section_requests, args.no_auto, args.metadata_file)
    if scaffold_plan is not None and args.list_parts:
        core.print_parts(scaffold_plan)
        return
    if scaffold_plan is not None:
        core.PART_CUTS.update(scaffold_plan.cuts)
    if args.watch:
        if args.batch or args.report:
            raise SystemExit("-w/--watch only supports single-file mode, not -b/--batch or -r/--report")
        if len(paths) != 1:
            raise SystemExit("-w/--watch accepts one Markdown name or path")
        if scaffold_plan is not None:
            watch_source = scaffold_plan.scaffold
        else:
            watch_source = plan_source
        core.run_watch(watch_source, core.pinned_watch_argv(sys.argv[1:], args.path, paths[0]), args, default_target, scaffold_plan, section_plan)
        return
    if args.report:
        from pdfmd_report import run as run_report
        return run_report(core, args=args, default_target=default_target, embed_request=embed_request,
                          engines=engines, need_engines=need_engines, pandoc_options=pandoc_options, paths=paths,
                          stamp_overrides=stamp_overrides, target_format=target_format, variables=variables)
    def embeds_preamble(file) -> bool:
        """Whether the assembled stage folds `file`'s preamble in (so it has to be found)."""
        if target_format != core.ASSEMBLED_FORMAT or embed_request is None:
            return False
        try:
            found = metadata_for(file)
        except (FileNotFoundError, ValueError):
            return False
        chosen = core.resolve_embed(file, found if isinstance(found, list) else ([found] if found else []),
                               embed_request)
        return chosen is not None and "preamble" in chosen[0]

    if args.batch:
        from pdfmd_batch import run as run_batch
        results = run_batch(core, args=args, embed_request=embed_request, embeds_preamble=embeds_preamble,
                            engines=engines, metadata_for=metadata_for, need_engines=need_engines,
                            pandoc_options=pandoc_options, paths=paths, plan_bridge=plan_bridge, stamp_overrides=stamp_overrides,
                            stop_at=stop_at, target_explicit=target_explicit, target_format=target_format,
                            variables=variables)
    else:
        if not single_input:
            raise SystemExit("Single-file mode accepts one Markdown name or path")
        source = plan_source
        if target_format == core.ASSEMBLED_FORMAT:
            if source.suffix.lower() not in (".md", ".markdown"):
                raise SystemExit(f"{source}: --stop-at markdown assembles Markdown files only")
            if core.is_assembled_document(source):
                raise SystemExit(f"{core.display_path(source)} is already an assembled file "
                                 f"({core.ASSEMBLED_KEY}: true); there is nothing left to assemble")
        # A parts-mode build is the scaffold plus its parts: it takes the
        # scaffold's own name and folder, and a partial build carries the
        # section names in its file name so it never replaces the full report.
        output_stem = source.stem
        if scaffold_plan is not None:
            source = scaffold_plan.scaffold
            output_stem = scaffold_plan.output_stem
        elif section_plan is not None:
            output_stem = section_plan.output_stem
        source_metadata = core.scaffold_metadata_files(source, args.metadata_file)
        target_format = default_target(source, source_metadata)
        direct_kind = (core.direct_route(source, target_format, args.from_format, args.no_auto, args.engine)
                       if scaffold_plan is None and section_plan is None and not presentation else None)
        if direct_kind is None and not presentation:
            need_engines(target_format)
        output_extension = core.output_extension_for(target_format, source)
        out_dir = None
        output_file = None
        if args.out and not args.destination_cwd and args.out.is_dir():
            # Check is-a-directory BEFORE adding a default suffix -- a dot-less
            # directory name would otherwise get an extension appended to the
            # directory's own name instead of being used as a directory.
            out_dir = args.out.resolve()
        elif args.out:
            requested_output = Path.cwd() / args.out.name if args.destination_cwd else args.out.resolve()
            output_file = core.default_output_path(requested_output, target_format)
        elif args.destination_cwd:
            output_file = Path.cwd() / f"{output_stem}{output_extension}"
        output = output_file or ((out_dir / f"{output_stem}{output_extension}") if out_dir
                                 else source.with_name(f"{output_stem}{output_extension}"))
        output = output_file = core.load_package("pdfmd_routing.output").single(source, output, convert_job, target_format, metadata_for)
        if source.suffix.lower() == ".qmd":
            core.BUILD["engine"], core.BUILD["failed"] = None, []
            core.begin_timer()
            from pdfmd_crop.build import prepare as prepare_crop
            with core.warning_capture() as seen, prepare_crop(source, output, [], target_format, args.verbose) as crop:
                built = core.convert_qmd(source, output, target_format, variables, pandoc_options)
                if built[1] and crop is not None and (problem := crop()):
                    built = source, False, problem
            results = [core.finish_build(built, seen, source, [])]
            if results[0][1]:
                # Front matter only: Quarto has its own metadata system, so no
                # metadata.yaml is looked up for a .qmd (see convert_qmd).
                core.backup_after_success(source, [], args.backup, args.verbose, args.backup_format)
        elif direct_kind is not None:
            core.BUILD["engine"], core.BUILD["failed"] = None, []
            core.begin_timer()
            from pdfmd_crop.build import prepare as prepare_crop
            with core.warning_capture() as seen, prepare_crop(
                    source, output, source_metadata, target_format, args.verbose) as crop:
                built = core.convert_direct(direct_kind, source, output, args.engine, args.verbose, args.debug,
                                       apply_defaults=(core.config_options().get("apply-defaults", False) if args.apply_defaults is None
                                                       else args.apply_defaults) not in (False, "false", "False", 0, ""),
                                       metadata_request=args.metadata_file)
                if built[1] and crop is not None and (problem := crop()):
                    built = source, False, problem
            results = [core.finish_build(built, seen, source, [])]
            if results[0][1]:
                core.backup_after_success(source, [], args.backup, args.verbose, args.backup_format)
        elif source.suffix.lower() in core.OFFICE_INPUT_EXTENSIONS:
            # A binary office document (.docx/.pptx/.xlsx/.odt/etc.) has no
            # YAML front matter, documentclass, or LaTeX preamble to go
            # looking for -- frontmatter_value()/metadata_for() below both
            # read the file as text, which crashes outright on a zip-based
            # binary format (caught testing this Phase's own new feature: a
            # real .docx/.pptx crashed here immediately, unrelated to
            # convert_one, before this branch existed). convert_one's own
            # OFFICE_INPUT_EXTENSIONS branch handles the actual conversion
            # -- including raising a clear error for --to/--from/--no-auto
            # officedirect combinations that have no working route, rather
            # than reaching this branch's own only-slightly-later crash.
            # No resolve_engines() call: it would read the file as text
            # looking for a pdf-engine front-matter key, which an office
            # document never has and can't be read as (same crash as
            # above) -- engines (from select_engines(args.engine, ...) at
            # the top of main()) is used as-is.
            results = [core.convert_one(source, out_dir, False, args.font, engines, variables, args.slide_level, pandoc_options, None, output_file, [], target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format, output_resolved=True)]
        else:
            if scaffold_plan is not None or section_plan is not None:
                # _convert_one derives the output name from the document's own
                # stem; a partial build's differs, so hand over the final path.
                output_file = output
            try:
                metadata = metadata_for(source)
            except (FileNotFoundError, ValueError) as error:
                raise SystemExit(str(error))
            engine_metadata_files = metadata if isinstance(metadata, list) else ([metadata] if metadata else [])
            preambles = []
            if target_format in {"pdf", *core.TEX_STANDALONE_FORMATS} or embeds_preamble(source):
                preambles = core.document_preambles(source, pandoc_options, core.effective_no_auto(source, args.no_auto), engine_metadata_files)
                core.announce_preambles(preambles)
            file_engines = (slides.engines(source, engine_metadata_files, args.engine, presentation_request, target_format, args.verbose)
                            if presentation else core.resolve_engines(source, args.engine, engines, False,
                                                                     target_format, engine_metadata_files, args.verbose))
            results = [core.convert_one(source, out_dir, presentation, args.font, file_engines, variables, args.slide_level, pandoc_options, metadata, output_file, preambles, target_format=target_format, from_format=args.from_format, no_auto=args.no_auto, verbose=args.verbose, debug=args.debug, stamp_overrides=stamp_overrides, keep_aux=args.keep_aux, backup=args.backup, backup_format=args.backup_format,
                                   extra_inputs=(scaffold_plan.files[1:] if scaffold_plan is not None else None),
                                   all_parts=(scaffold_plan.parts if scaffold_plan is not None else None),
                                   cache_cli=args.cache, embed=embed_request, trust_embedded=args.trust_embedded,
                                   self_contained=args.self_contained,
                                   parts_root=(scaffold_plan.directory if scaffold_plan is not None else None),
                                   partial=((scaffold_plan is not None and scaffold_plan.selected is not None)
                                            or section_plan is not None),
                                   source_override=((section_plan.text, section_plan.shifted)
                                                    if section_plan is not None else None),
                                   full_override=(section_plan.full_text if section_plan is not None else None),
                                   calc_text_override=(section_plan.calc_text if section_plan is not None else None), output_resolved=True)]
            if section_plan is not None and results[0][1] and target_format != core.ASSEMBLED_FORMAT:
                if core.LAST_WHOLE:
                    print("NOTE  section build: the whole document was numbered and this section kept, so its "
                          "numbers and the references to the rest are the full document's (a reference written "
                          "as raw LaTeX \\ref is not resolved outside LaTeX; use @sec:/@fig: with pandoc-crossref)")
                elif core.LAST_SEEDED:
                    print("NOTE  section build: references to other sections come from the last full build "
                          "(cache); they are stale if you have since changed the document. This section's "
                          "own heading, figure, table and equation numbers restart at its first one")
                elif core.LAST_SCANNED and core.LAST_EXACT:
                    print(f"NOTE  section build: references to other sections ({core.LAST_SCANNED} labels) come from a draft "
                          "pass over the whole document, so they are exact. This section's own heading, figure, "
                          "table and equation numbers restart at its first one")
                elif core.LAST_SCANNED:
                    print(f"NOTE  section build: references to other sections ({core.LAST_SCANNED} labels) are counted "
                          "from the document's sources: approximate where it defines its own macros; a full build "
                          "with the cache on (--cache) first makes them exact. This section's own heading, "
                          "figure, table and equation numbers restart at its first one")
                else:
                    print("NOTE  section build: references to other sections print as ??, and heading, "
                          "figure and table numbers restart from this section's own first one (with the "
                          "cache on -- pdfmd-options: {cache: {aux: true}}, or --cache -- a full build "
                          "first lets later section builds fill the references in)")
            if (scaffold_plan is not None and scaffold_plan.selected is not None and results[0][1]
                    and target_format != core.ASSEMBLED_FORMAT):
                if core.LAST_WHOLE:
                    print("NOTE  partial build: the whole document was numbered and these parts kept, so their "
                          "numbers and the references to the rest are the full document's (a reference written "
                          "as raw LaTeX \\ref is not resolved outside LaTeX; use @sec:/@fig: with pandoc-crossref)")
                elif core.LAST_SEEDED:
                    print("NOTE  partial build: numbers of parts left out come from the last full build "
                          "(--cache); they are stale if you have since added or moved a figure or table there"
                          + (f" (and {core.LAST_SCANNED} labels counted from the sources fill in what it lacks)"
                             if core.LAST_SCANNED else ""))
                elif core.LAST_SCANNED and core.LAST_EXACT:
                    print(f"NOTE  partial build: numbers of parts left out ({core.LAST_SCANNED} labels) come from a draft "
                          "pass over the whole document, so they are exact")
                elif core.LAST_SCANNED:
                    print(f"NOTE  partial build: numbers of parts left out are counted from the sources "
                          f"({core.LAST_SCANNED} labels); approximate where the document defines its own macros -- "
                          "a full build with the cache on (--cache) makes them exact")
                else:
                    print("NOTE  partial build: references to parts left out print as ??, and figure/"
                          "table numbers restart from this build's own first one (pdfmd-options: "
                          "{cache: {aux: true}} carries them over from the last full build)")
                if scaffold_plan.cuts:
                    print("NOTE  a section or element cut out of a part is numbered from its own start, "
                          "cache or not: its heading, figure, table and equation numbers restart there "
                          "(only whole parts get their numbers from the last full build)")
            if (core.LAST_SKIPPED and not (core.LAST_EXACT or core.LAST_SEEDED or core.LAST_WHOLE) and results[0][1]
                    and target_format != core.ASSEMBLED_FORMAT
                    and (section_plan is not None or (scaffold_plan is not None and scaffold_plan.selected is not None))):
                print(f"NOTE  {core.LAST_SKIPPED} label{'' if core.LAST_SKIPPED == 1 else 's'} came after a caption in an "
                      "environment pdfmd does not know, so a reference to one outside this build prints ?? rather "
                      "than the number of the heading before it (--seed-labels draft counts them exactly)")
        if args.open and results[0][1]:
            core.open_file(output)
    if convert_job is not None:
        results = core.finish_convert_job(convert_job, results, args.verbose)
    failures = [result for result in results if not result[1]]
    for result in results:
        source, ok, error = result
        print(f"{'OK  ' if ok else 'FAIL'}  {core.display_path(source)}{core.built_name(result)}{core.time_label(result)}{core.engine_label(result)}")
        if args.verbose:
            for line in core.time_breakdown(result):
                print(line)
        if error:
            print(error)
        if getattr(result, "record_path", None) and (args.verbose or not ok):
            print(f"{'      full record: ' if not ok else 'RECORD  '}{core.under_home(result.record_path)}")
    if args.batch and args.bopen is not None:
        built = [Path(result.output) for result in results
                 if result[1] and getattr(result, "output", None) is not None and Path(result.output).is_file()]
        picked = [built[index] for index in core.bopen_indices(args.bopen, len(built))]
        for path in picked:
            core.open_file(path)
        if picked:
            print(f"OPENED  {len(picked)} of {len(built)} ({args.bopen}): " + ", ".join(path.name for path in picked[:6])
                  + (f", +{len(picked) - 6} more" if len(picked) > 6 else ""))
    if native_auto and not failures:
        core.offer_native_upgrade()
    if not failures:
        core.maybe_hint_setup()
    if failures:
        raise SystemExit(1)
