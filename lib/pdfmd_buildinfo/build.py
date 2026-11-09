"""How long a build took and the record it leaves: the build's timer (`begin_timer`, `resolve_build_time`, `attach_time`,
`time_breakdown`), and the record of a build (`BuildRecorder` with what it listens to, `build_log_mode_word`,
`resolve_build_log`, `build_record_folders`, `record_module`), and `--last-build` (`last_build_command`).

Moved out of `pdfmd.py` unchanged (v3.33.23, SPLIT.md), with `BUILD_LOG_KEEP` and `BUILD_LOG_KILOBYTES`. `core` is the `pdfmd` module,
bound when the module is first loaded (a stand-in in `pdfmd.py` loads it on the first call; the first binding wins); the pdfmd names
the code uses (`AutoLog`, `BUILD`, `BUILD_LOG_CLI`, `BUILD_TIME_CLI`, `LOCAL_CACHE_DIRNAME`, `PDFMD_VERSION`, `TIME_FORMAT_CLI`,
`cache_location`, `cache_root`, `config_options`, `display_path`, `engine_label`, `engine_version_line`, `find_markdown`,
`first_pdfmd_option`, `option_flag`, `option_flag_number`, `pandoc_version`, `prepare_cache_root`, `record_note`, `safe_stem`,
`timing_module` and `which`) are read as `core.X` when it runs. `BUILD_LOG_CLI`, `BUILD_TIME_CLI` and `TIME_FORMAT_CLI` are rebound by
`main`, so they stay in `pdfmd.py`; `timed` stays there too, because 15 definitions apply it as a decorator when the file is loaded,
and so does `timing_module`, which `pdfmd.py` calls itself. `core.cache_root`, `core.config_options`, `core.pandoc_version` and
`core.which` are patched by tests as `pdfmd.X`. `pdfmd.py` starts a record as `load_package("pdfmd_buildinfo.build").BuildRecorder.start(...)`:
a class attribute, which a stand-in (a function) does not have.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shlex
import sys
from datetime import datetime
from pathlib import Path

core = None


def begin_timer() -> None:
    """Start the clock of the build that is about to run."""
    timing = core.timing_module()
    core.BUILD["timer"] = timing.Timer() if timing else None


def resolve_build_time(md_path: Path, metadata_files: list[Path]) -> tuple[bool, str]:
    """(whether the closing line shows the time, its style): the command line, else the document's `pdfmd-options`
    (`build-time`, `time-format`), its metadata files', the config file's, else on and `auto`."""
    show = core.BUILD_TIME_CLI
    if show is None and os.environ.get("PDFMD_BUILD_TIME") in ("0", "1"):
        show = os.environ["PDFMD_BUILD_TIME"] == "1"
    style = core.TIME_FORMAT_CLI or os.environ.get("PDFMD_TIME_FORMAT") or ""

    def option(key: str):
        if md_path.suffix.lower() in (".md", ".markdown"):
            return core.first_pdfmd_option(md_path, metadata_files, key)
        return core.config_options().get(key)

    if show is None:
        show = core.option_flag(option("build-time"))
        show = True if show is None else show
    if not style:
        style = str(option("time-format") or "auto").strip()
    timing = core.timing_module()
    problem = timing.check_style(style) if timing else None
    if problem:
        print(f"WARN  {core.display_path(md_path)}: {problem}; using auto", file=sys.stderr)
        style = "auto"
    return show, style


def attach_time(built: "core.Built", md_path: Path, metadata_files: list[Path]) -> "core.Built":
    """Put the build's time, as it is to be written, and its steps on ``built``."""
    timer, timing = core.BUILD.get("timer"), core.timing_module()
    if timer is None or timing is None:
        return built
    show, style = resolve_build_time(md_path, metadata_files)
    built.seconds = timer.elapsed()
    built.time_text = timing.format_duration(built.seconds, style) if show else ""
    built.time_style = style
    built.steps = [(step.name, step.depth, step.seconds) for step in timer.steps]
    return built


def time_breakdown(result) -> list[str]:
    """The TIME lines of --verbose: the whole build, then every step, a step inside another indented, and what no step
    covers (finding the files and settings, the pre-passes, Pandoc's own work for formats with no engine)."""
    timing = core.timing_module()
    seconds = getattr(result, "seconds", None)
    if timing is None or seconds is None:
        return []
    style = getattr(result, "time_style", "auto")
    steps = getattr(result, "steps", [])
    lines = [f"TIME  {core.display_path(result[0])}  {timing.format_duration(seconds, style)}"]
    lines += [f"TIME  {'  ' * (depth + 1)}{name}  {timing.format_duration(took, style)}" for name, depth, took in steps]
    covered = sum(took for _, depth, took in steps if depth == 0)
    if steps and seconds - covered > 0:
        lines.append(f"TIME    the rest (files, settings, pre-passes)  {timing.format_duration(seconds - covered, style)}")
    return lines


BUILD_LOG_KEEP = 5            # defaults of the two numbers; both are settings
BUILD_LOG_KILOBYTES = 512


def record_module():
    """pdfmd_buildinfo.record, or None in a lone pdfmd.py."""
    try:
        from pdfmd_buildinfo import record
        return record
    except ImportError:
        return None


class _RecordTee:
    """A text stream that passes everything on and keeps each line, in order, in the record."""

    def __init__(self, stream, lines: list[str]):
        self._stream, self._lines, self._partial = stream, lines, ""

    def write(self, text):
        self._partial += text
        *complete, self._partial = self._partial.split("\n")
        self._lines.extend(complete)
        return self._stream.write(text)

    def finish(self) -> None:
        if self._partial:
            self._lines.append(self._partial)
            self._partial = ""

    def __getattr__(self, name):
        return getattr(self._stream, name)


def build_log_mode_word(value) -> str | None:
    if isinstance(value, bool):
        return "on" if value else "off"
    text = str(value).strip().casefold() if value is not None else ""
    return {"on": "on", "true": "on", "yes": "on", "off": "off", "false": "off", "no": "off", "failed": "failed"}.get(text)


def resolve_build_log(md_path: Path, metadata_files: list[Path]) -> tuple[str, int, int]:
    """(on | failed | off, how many records to keep, the size cap in KB): the command line, else the document's
    `pdfmd-options` (`build-log`, `build-log-keep`, `build-log-max-size`), its metadata files', the config's, else on, 5, 512."""
    def option(key: str):
        if md_path.suffix.lower() in (".md", ".markdown"):
            return core.first_pdfmd_option(md_path, metadata_files, key)
        return core.config_options().get(key)

    mode = build_log_mode_word(core.BUILD_LOG_CLI or os.environ.get("PDFMD_BUILD_LOG")) or build_log_mode_word(option("build-log")) or "on"
    keep = core.option_flag_number(option("build-log-keep"))
    kilobytes = core.option_flag_number(option("build-log-max-size"))
    return (mode, int(keep) if keep and keep >= 1 else BUILD_LOG_KEEP,
            int(kilobytes) if kilobytes and kilobytes > 0 else BUILD_LOG_KILOBYTES)


def build_record_folders(md_path: Path, metadata_files: list[Path] | None = None) -> list[Path]:
    """Where ``md_path``'s records are kept: [the folder its cache location names]; for a look-up, both places."""
    stem = core.safe_stem(md_path.stem)
    document = md_path.resolve().parent / core.LOCAL_CACHE_DIRNAME / "builds" / stem
    machine = core.cache_root() / "builds" / f"{stem}-{hashlib.sha1(str(md_path.resolve()).encode('utf-8')).hexdigest()[:8]}"
    if metadata_files is None:
        return [machine, document]
    try:
        where = core.cache_location(md_path, metadata_files) if md_path.suffix.lower() in (".md", ".markdown") else "global"
    except (SystemExit, OSError):
        where = "global"
    return [document if where == "document" else machine]


class BuildRecorder:
    """The record of one build: it listens to the console from the start, and writes the file when the build ends."""

    def __init__(self, md_path: Path, metadata_files: list[Path], mode: str, keep: int, kilobytes: int):
        self.md_path, self.metadata_files, self.mode, self.keep, self.kilobytes = md_path, metadata_files, mode, keep, kilobytes
        self.lines: list[str] = []
        self.started = datetime.now()
        self.out, self.err = sys.stdout, sys.stderr
        self.tees = (_RecordTee(self.out, self.lines), _RecordTee(self.err, self.lines))
        sys.stdout, sys.stderr = self.tees
        core.BUILD["record"] = self.lines
        for path in metadata_files:             # main announces these after the build, when the record is closed
            core.record_note(core.AutoLog.file_line("YAML", path))

    @classmethod
    def start(cls, md_path: Path, metadata_files: list[Path]) -> "BuildRecorder | None":
        """The recorder, or None when the record is off or cannot be made: a record never fails a build."""
        try:
            if record_module() is None:
                return None
            mode, keep, kilobytes = resolve_build_log(md_path, metadata_files)
            return None if mode == "off" else cls(md_path, metadata_files, mode, keep, kilobytes)
        except Exception:
            return None

    def stop(self) -> None:
        for tee in self.tees:
            tee.finish()
        if sys.stdout is self.tees[0]:
            sys.stdout = self.out
        if sys.stderr is self.tees[1]:
            sys.stderr = self.err
        core.BUILD["record"] = None

    def header(self, built, failure: str) -> list[str]:
        ok = built is not None and bool(built[1])
        command = os.environ.get("PDFMD_COMMAND_LINE") or shlex.join(sys.argv[1:])
        pandoc = ".".join(str(part) for part in core.pandoc_version()) if core.which("pandoc") else "not found"
        engines = [name for name in [*core.BUILD["tried"], *(built.failed if built is not None else []),
                                     (built.engine if built is not None else "") or ""] if name]
        rows = [("pdfmd", f"{core.PDFMD_VERSION}   python {platform.python_version()}   {platform.platform()}"),
                ("when", f"{self.started:%Y-%m-%d %H:%M:%S}"),
                ("document", str(self.md_path.resolve())),
                ("folder", str(Path.cwd())),
                ("command", f"pdfmd {command}"),
                ("pandoc", pandoc),
                ("engines", ", ".join(f"{name}: {core.engine_version_line(name) or 'no version'}" for name in dict.fromkeys(engines)) or "none")]
        took = getattr(built, "seconds", None) if built is not None else None
        timing = core.timing_module()
        spent = f"  in {timing.format_duration(took)}" if took is not None and timing else ""
        by = core.engine_label(built).strip() if built is not None else ""
        rows.append(("result", ("ok" if ok else "FAILED") + spent + (f"  {by}" if by else "")))
        if built is not None and getattr(built, "output", None):
            rows.append(("output", str(built.output)))
        if failure:
            rows.append(("reason", failure))
        return ["pdfmd build record", *(f"{name + ':':<10} {value}" for name, value in rows)]

    def finish(self, built=None, failure: str = "") -> Path | None:
        """Stop listening and write the record (a failed build always; a good one unless build-log is `failed`). The path."""
        self.stop()
        ok = built is not None and bool(built[1])
        if ok and self.mode == "failed":
            return None
        try:
            steps = time_breakdown(built) if built is not None else []
            answer = built[2].strip() if built is not None and len(built) > 2 and isinstance(built[2], str) else ""
            text = "\n".join([*self.header(built, failure), "", *steps, "",
                              "----- what pdfmd printed, and what it ran -----", *self.lines, "",
                              *(["----- what the build answered (the last 3000 characters of Pandoc's messages) -----", answer, ""]
                                if answer else [])])
            folder = self.build_folder()
            core.prepare_cache_root(folder.parent.parent)
            return record_module().write(folder, text, ok, self.keep, self.kilobytes * 1024)
        except Exception:
            return None

    def build_folder(self) -> Path:
        return build_record_folders(self.md_path, self.metadata_files)[0]


def last_build_command(args) -> int:
    """`pdfmd --last-build FILE [--failed]`: the newest record of FILE."""
    record = record_module()
    if record is None:
        print("ERROR  --last-build needs the pdfmd_buildinfo package (a full install of pdfmd-cli).", file=sys.stderr)
        return 1
    status = 0
    targets = args.path or [Path.cwd()]
    for target in targets:
        try:
            document = core.find_markdown(target)
        except FileNotFoundError as error:
            raise SystemExit(f"ERROR  {error}")
        found = record.newest_of(build_record_folders(document), failed=args.failed)
        if found is None:
            print(f"{core.display_path(document)}: no record of a {'failed ' if args.failed else ''}build "
                  "(build-log is off, or it was never built here)", file=sys.stderr)
            status = 1
            continue
        if len(targets) > 1:
            print(f"==> {core.display_path(found)} <==")
        sys.stdout.write(found.read_text(encoding="utf-8", errors="replace"))
    return status
