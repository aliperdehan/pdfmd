"""The terminal view: `--view` and `-o -` build each document with a child pdfmd into a scratch folder and write one stream to
standard output (through a pager when that is a terminal), and the pager itself (`$PDFMD_PAGER`, `$PAGER`, the `pager_command`
setting, `less -FRX`).

Moved out of `pdfmd.py` unchanged (v3.33.16, SPLIT.md), with `ANSI_LINK_TERMINALS`, `BINARY_TARGETS`, `VIEW_DROPPED` and `VIEW_PAGER`
(and the comment that sat above them). `core` is the `pdfmd` module, bound by `pdfmd.py` when it loads (the first binding wins);
the pdfmd names the code uses (`ANSI_COLOR_ENV`, `ANSI_FALLBACK_WIDTH`, `ANSI_LINKS_ENV`, `ANSI_WIDTH_ENV`, `DISPLAY_ALIAS`,
`FORMAT_EXTENSION`, `LookupAmbiguous`, `ansi_columns`, `find_markdown`, `first_pdfmd_option`, `skip_never`, `split_command`) are read as
`core.X` when it runs. So are `core.which`, which tests patch as `pdfmd.which`, and `core.__file__`: the child pdfmd that
`terminal_view` starts is `pdfmd.py` itself.
"""

from __future__ import annotations

import atexit
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

core = None


ANSI_LINK_TERMINALS = frozenset({"iTerm.app", "WezTerm", "ghostty", "vscode", "Hyper"})     # TERM_PROGRAM: they draw OSC 8 links


# `--view` and `-o -` (v3.30.3): each document is built by a child pdfmd into a scratch folder (so every discovery, filter
# and note of a normal build applies, and the notes go to stderr), then the result is written to stdout: one stream, in
# the order given. `--view` is `--to ansi` + `-o -` + a pager when stdout is a terminal. The options the children must not
# get twice are dropped from their command line; the input files are handed over one by one.
VIEW_DROPPED = {"--view": 0, "--pager": 0, "--no-pager": 0, "--color": 1, "--width": 1, "-t": 1, "--to": 1,
                "-o": 1, "--out": 1, "--output": 1, "-b": 0, "--batch": 0, "-r": 0, "--report": 0, "--book": 0,
                "--recursive": 0, "--open": 0, "-w": 0, "--watch": 0}
BINARY_TARGETS = frozenset({"pdf", "docx", "odt", "pptx", "epub", "epub2", "epub3", "rtf"})
VIEW_PAGER = "less -FRX"


def tolerant_streams(streams=None) -> None:
    """Make standard output and standard error unable to raise `UnicodeEncodeError`: a stream whose error handler is
    `strict` (Python's default for standard output) gets `replace`, so a character its encoding lacks prints as `?`, the
    way `--help` has printed it since v3.25.19. A Windows pipe, or a console that is not UTF-8, is cp1252 or another code
    page before Python 3.15, and `NATIVE  <a Cyrillic file name> via inkmd` ended the build with a traceback there. The
    encoding is not changed (the reader of a pipe expects the code page), nor is a handler somebody chose
    (`PYTHONIOENCODING=utf-8:surrogateescape`, standard error's `backslashreplace`). Called at the start of `main()` and
    of every `-j` worker; a stream that cannot be reconfigured (a `StringIO` in a test) is left alone."""
    for stream in (sys.stdout, sys.stderr) if streams is None else streams:
        if getattr(stream, "errors", None) == "strict" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (OSError, ValueError):      # closed or detached: whatever is printed to it fails for another reason
                pass


def view_child_arguments(argv: list[str], paths: list[Path]) -> list[str]:
    """The command line of the run, less what `terminal_view` sets itself and the input paths."""
    wanted = list(paths)
    kept: list[str] = []
    index = 0
    positional = False
    while index < len(argv):
        token = argv[index]
        if token == "--" and not positional:
            positional = True
            index += 1
            continue
        name, equals, _ = token.partition("=") if token.startswith("--") else (token, "", "")
        if not positional and name in VIEW_DROPPED:
            index += 1 if equals else 1 + VIEW_DROPPED[name]
            continue
        if (positional or not token.startswith("-") or token == "-") and Path(token) in wanted:
            wanted.remove(Path(token))
        else:
            kept.append(token)
        index += 1
    return kept


def view_stdin_file(text: bytes, scratch: Path, made: list[Path]) -> Path:
    """Standard input as a Markdown file: in the current folder (a relative picture or include resolves there), else in the
    scratch folder. The caller removes it."""
    for folder in (Path.cwd(), scratch):
        target = folder / f".pdfmd-stdin-{os.getpid()}.md"
        try:
            target.write_bytes(text)
        except OSError:
            continue
        made.append(target)
        return target
    raise SystemExit("could not keep standard input in a file to build it from")


def view_sources(args, scratch: Path, made: list[Path]) -> list[Path]:
    """The documents to show, in order. A path that exists is read as a file (a folder: its Markdown files); `-` or no path
    with a pipe on standard input reads that; no path and no pipe: the Markdown files of the current folder; and with
    none there, what is typed or pasted into the terminal, ended with Ctrl-D."""
    files: list[Path] = []
    for path in args.path or []:
        if str(path) == "-":
            files.append(view_stdin_file(sys.stdin.buffer.read(), scratch, made))
        elif path.is_dir():
            found = core.skip_never(sorted(path.rglob("*.md") if args.recursive else path.glob("*.md"),
                                      key=lambda item: str(item).casefold()), args.include_never)
            if not found:
                raise SystemExit(f"{path}: no Markdown files in this folder")
            files += found
        else:
            try:
                files.append(core.find_markdown(path))
            except (FileNotFoundError, core.LookupAmbiguous) as error:
                raise SystemExit(str(error))
    if files:
        return files
    if not sys.stdin.isatty():
        text = sys.stdin.buffer.read()
        if text.strip():
            return [view_stdin_file(text, scratch, made)]
    found = core.skip_never(sorted(Path.cwd().glob("*.md"), key=lambda item: item.name.casefold()), args.include_never)
    if found:
        return found
    if sys.stdin.isatty():
        print("reading Markdown from the terminal, Ctrl-D to finish", file=sys.stderr)
        text = sys.stdin.read().encode("utf-8")
        if text.strip():
            return [view_stdin_file(text, scratch, made)]
    raise SystemExit("Nothing to show: no file named, nothing on standard input and no Markdown files in this folder.")


def stdin_build(args) -> None:
    """`pdfmd -`: Markdown read from standard input is built like a file. It sits in the current folder for the length of the
    run (a relative picture or include resolves there) and is shown as `stdin.md`; the result is `stdin.pdf` (or `stdin.<ext>`
    for `--to`) unless `-o` names it. `-o -` and `--view` read standard input in terminal_view()."""
    if sys.stdin.isatty():
        print("reading Markdown from the terminal, Ctrl-D to finish", file=sys.stderr)
    text = sys.stdin.buffer.read()
    if not text.strip():
        raise SystemExit("Nothing to build: standard input was empty.")
    made: list[Path] = []
    scratch = Path(tempfile.mkdtemp(prefix="pdfmd-stdin-"))
    atexit.register(shutil.rmtree, scratch, ignore_errors=True)
    source = view_stdin_file(text, scratch, made)
    atexit.register(lambda: [item.unlink(missing_ok=True) for item in made])
    core.DISPLAY_ALIAS[source] = core.DISPLAY_ALIAS[source.resolve()] = source.with_name("stdin.md")
    args.path = [source]
    if args.out is None:
        target = args.to or "pdf"
        args.out = Path.cwd() / ("stdin" + core.FORMAT_EXTENSION.get(target, "." + target))


def view_wants_pager(args, first: Path) -> bool:
    """--pager/--no-pager, else `pdfmd-options: {pager: ...}` (the document, its folder, the config), else on."""
    if args.pager is not None:
        return args.pager
    try:
        value = core.first_pdfmd_option(first, [], "pager")
    except Exception:
        value = None
    return str(value).strip().casefold() not in ("false", "no", "off", "0") if value is not None else True


def view_pager_setting(first: Path) -> str:
    """`pdfmd-options: {pager_command: "bat --paging=always"}` (also `pager-command`; a word list works too): the document's,
    its folder's or the config's pager, "" when none says."""
    try:
        value = core.first_pdfmd_option(first, [], "pager_command", "pager-command")
    except Exception:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(shlex.quote(str(word)) for word in value)
    return "" if value in (None, False, True) else str(value).strip()


def pager_command(setting: str = "") -> list[str]:
    """The pager as words: `$PDFMD_PAGER`, else `$PAGER`, else the `pager_command` setting, else `less -FRX`. The environment
    wins over the setting, so one shell can override a project's choice."""
    return core.split_command(os.environ.get("PDFMD_PAGER") or os.environ.get("PAGER") or setting or VIEW_PAGER)


def run_pager(text: str, setting: str = "") -> None:
    """The text through `$PDFMD_PAGER`, else `$PAGER`, else the `pager_command` setting (``setting``), else `less -FRX` (-F: no
    pager at all when it fits the screen; -R: keep the colours); printed directly when there is none."""
    command = pager_command(setting)
    if not command or not core.which(command[0]):
        sys.stdout.write(text)
        return
    if Path(command[0]).name == "less":
        flags = [word for word in command[1:] if word.startswith("-")]
        if not flags:
            command += ["-FRX"]
        elif not any("R" in word or "r" in word for word in flags) and "R" not in os.environ.get("LESS", ""):
            command += ["-R"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        process.stdin.write(text.encode("utf-8"))
        process.stdin.close()
    except BrokenPipeError:                                  # the reader quit before the end
        pass
    try:
        process.wait()
    except KeyboardInterrupt:
        process.wait()


def terminal_view(args) -> int:
    """`--view`, and `-o -` for any target: build into a scratch folder, write one stream to stdout (see the comment above)."""
    target = args.to or "pdf"
    tty = sys.stdout.isatty()
    if not tty and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")     # the text is UTF-8; a Windows pipe is the ANSI code page otherwise
        except (OSError, ValueError):
            pass
    if args.color in ("always", "never"):
        colour = args.color
    elif os.environ.get("NO_COLOR"):
        colour = "never"
    else:
        colour = "always" if (args.view or tty) else "never"
    os.environ[core.ANSI_COLOR_ENV] = colour
    if args.width:
        os.environ[core.ANSI_WIDTH_ENV] = str(args.width)
    elif tty:
        os.environ[core.ANSI_WIDTH_ENV] = str(max(20, shutil.get_terminal_size((core.ANSI_FALLBACK_WIDTH, 24)).columns))
    suffix = core.FORMAT_EXTENSION.get(target, "." + target)
    failed = 0
    results: list[tuple[Path, bytes]] = []
    made: list[Path] = []
    pager = False
    with tempfile.TemporaryDirectory(prefix="pdfmd-view-") as scratch_name:
        scratch = Path(scratch_name)
        try:
            files = view_sources(args, scratch, made)
            pager = bool(args.view) and tty and view_wants_pager(args, files[0])
            if len(files) > 1 and target in BINARY_TARGETS:
                raise SystemExit(f"-o - is one stream: {len(files)} documents cannot be joined as {target}. Build them "
                                 "into a folder instead (-b, -o DIR), or name one.")
            os.environ[core.ANSI_LINKS_ENV] = ("1" if tty and not pager and os.environ.get("TERM_PROGRAM") in ANSI_LINK_TERMINALS
                                          else "0")
            environment = {**os.environ, "PDFMD_NO_PROMPT": "1"}
            for number, source in enumerate(files):
                built = scratch / f"{number:03d}{suffix}"
                command = [sys.executable, str(Path(core.__file__).resolve()), *view_child_arguments(sys.argv[1:], args.path or []),
                           "--to", target, "-o", str(built), "--no-stamp", "--no-backup", "--rewrite", "--", str(source)]
                done = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, env=environment)
                # the child's OK / DEFAULTS lines would sit above the document: shown for a failure or with --verbose
                sys.stderr.write((done.stdout if done.returncode != 0 or args.verbose else "") + done.stderr)
                if done.returncode != 0 or not built.is_file():
                    failed += 1
                    continue
                results.append((source, built.read_bytes()))
        finally:
            for item in made:
                item.unlink(missing_ok=True)
    if args.view:
        pieces = []
        for source, data in results:
            header = ""
            if len(files) > 1:                          # a dim rule with the file's name above each one
                title = f"── {'stdin' if source.name.startswith('.pdfmd-stdin-') else source.name} "
                rule = title + "─" * max(0, min(core.ansi_columns(), 100) - len(title))
                header = (f"\x1b[2m{rule}\x1b[0m" if colour == "always" else rule) + "\n\n"
            pieces.append(header + data.decode("utf-8", "replace"))
        text = "\n".join(pieces)
        if pager:
            run_pager(text, view_pager_setting(files[0]))
        else:
            sys.stdout.write(text)
            sys.stdout.flush()
    else:
        for _, data in results:
            sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    return 1 if failed else 0
