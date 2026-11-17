"""Moved out of pdfmd.py in phase 2 of the split (SPLIT.md, `pdfmd_history.record`). pdfmd's own helpers, settings and
state are read as `core.X` when the code runs (`core` is pdfmd: lib/pdfmd_base), never imported."""

from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from pdfmd_base import core


HISTORY_TIME_RE = re.compile(r"^(?P<text>.*?)\s+--\s+(?P<when>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*$")


def history_module():
    """pdfmd_history, or None in a lone pdfmd.py."""
    try:
        import pdfmd_history
        return pdfmd_history
    except ImportError:
        return None


def note_entry(line: str, meta: tuple = ()):
    """The .hst entry of a "Compiled ... -- WHEN" or "Restored ... -- WHEN" line of BUILD NOTES (a bullet's dash is
    allowed), or None."""
    history = history_module()
    found = HISTORY_TIME_RE.match(line.strip().removeprefix("- ").strip())
    if history is None or not found:
        return None
    for word, kind in (("Compiled", "compiled"), ("Restored", "restored")):
        if found.group("text").startswith(word):
            return history.Entry(found.group("when"), kind, found.group("text")[len(word):].strip(), meta)
    return None


compile_entry = note_entry


def history_file(md_path: Path, metadata_files: list[Path] = (), existing: bool = False) -> Path:
    """Where md_path's NAME.hst is: in its backup folder (see backup_directory), or -- reading only -- in the
    NAME.unpacked/ folder --unpack made, when there is none in the backup folder."""
    options = core.resolve_backup_options(md_path, list(metadata_files), None)
    path = core.backup_directory(md_path, options) / f"{md_path.stem}.hst"
    if existing and not path.is_file():
        folder = md_path.with_name(f"{md_path.stem}{core.UNPACKED_SUFFIX}")
        found = [item for item in sorted(folder.glob("*.hst"))] if folder.is_dir() else []
        if (folder / path.name).is_file():
            return folder / path.name
        if len(found) == 1:
            return found[0]
    return path


def record_history(md_path: Path, metadata_files: list[Path], line: str, output: Path, verbose: bool) -> bool:
    """Add a compile to NAME.hst; False when this pdfmd cannot (no pdfmd_history package)."""
    history = history_module()
    entry = compile_entry(line)
    if history is None or entry is None:
        return history is not None
    try:
        digest = core.sha256_text(core.normalized_source(md_path.read_text(encoding="utf-8-sig")))[:12]
    except (OSError, UnicodeDecodeError):
        digest = ""
    where = history.git.state(md_path)
    parts = core.part_digests([Path(item) for item in core.BUILD["sources"][1:]], core.BUILD.get("root"))     # so a later partial entry can say what changed
    entry = history.Entry(entry.when, entry.kind, entry.text, tuple(item for item in (
        ("sha", digest), ("out", output.name), ("git", (where[0] + ("+" if where[1] else "")) if where else ""),
        ("took", f"{core.BUILD['timer'].elapsed():.1f}" if core.BUILD.get("timer") is not None else ""),
        ("shas", ",".join(f"{name}:{part}" for name, part in parts if part)),
        ("reader", core.BUILD.get("history-reader", {}).get("name", ""))) if item[1]))
    path = history_file(md_path, metadata_files)
    pending = core.BUILD.get("history-pending")
    if pending is not None:
        # Output provenance may embed this history before the final --strict result is known.
        # Keep it available there, but restore the previous bytes if the build ultimately fails.
        try:
            before = path.read_bytes() if path.exists() else None
        except OSError as error:
            print(f"WARN  {core.display_path(md_path)}: cannot read {core.display_path(path)} ({error.strerror or error})", file=sys.stderr)
            return True
        if write_history(path, entry, md_path, metadata_files, verbose):
            pending.append((path, entry, md_path, core.BUILD.get("history-reader", {}), before, path.read_bytes()))
        return True
    write_history(path, entry, md_path, metadata_files, verbose)
    return True


def write_history(path, entry, md_path, metadata_files, verbose) -> bool:
    history = history_module()
    try:
        entries, other = history.read_file(path)
        if entry.meta_dict().get("reader"):
            # Prepend to break same-second ties; merging also refreshes a duplicate stamp's baseline.
            history.write_file(path, [entry, *entries], md_path.name, other)
        else:
            history.add_entry(path, entry, md_path.name)
    except OSError as error:
        print(f"WARN  {core.display_path(md_path)}: cannot write {core.display_path(path)} ({error.strerror or error})", file=sys.stderr)
        return False
    backup_notice(path.parent, core.resolve_backup_options(md_path, list(metadata_files), None))
    core.vprint(verbose, f"AUTO HISTORY  {core.display_path(path)}: {entry.when} compiled")
    return True


def begin_history() -> None:
    core.BUILD.pop("history-reader", None)
    core.BUILD["history-pending"] = []


def set_reader(md_path: Path, reader: str | None, cli_from: str | None,
               metadata_files: list[Path], no_auto, reason: str | None) -> None:
    """Keep the reader actually passed to Pandoc, including an implicit Markdown default."""
    if reader is None and md_path.suffix.lower() not in (".md", ".markdown"):
        return
    chosen = core.FLAVOUR_CLI["name"]
    if chosen is None:
        chosen = core.first_pdfmd_option(md_path, metadata_files, "flavour", "flavor", "reader")
    word = str(chosen or "").strip().lower()
    preset = core.FLAVOUR_PRESETS.get(word)
    fixed = word not in ("", "auto") and (preset is None or preset.reader != "auto")
    explicit = bool(cli_from or fixed
                    or core.auto_disabled(no_auto, "reader"))
    if reason:
        reason = reason.removeprefix(f"{md_path}: ")
    elif core.has_yaml_frontmatter(core.read_text_best_effort(md_path)) and (reader or "markdown").startswith("markdown"):
        reason = "YAML front matter selects Pandoc's Markdown"
    core.BUILD["history-reader"] = {"name": reader or "markdown", "explicit": explicit, "reason": reason}


def reader_warnings() -> list[str]:
    """Compare each queued successful full build with its latest compiled entry, never past a legacy entry."""
    history = history_module()
    warnings = []
    for _, entry, md_path, state, before, _ in core.BUILD.get("history-pending", []):
        if not state or state["explicit"]:
            continue
        try:
            entries, _ = history.parse(before.decode("utf-8-sig")) if before is not None else ([], [])
        except UnicodeDecodeError:
            entries = []
        old = next((old for old in history.merge(entries) if old.kind == "compiled"), None)
        previous = old.meta_dict().get("reader") if old else None
        current = entry.meta_dict().get("reader")
        if previous and current and previous != current:
            reason = f" ({state['reason']})" if state.get("reason") else ""
            warning = f"WARN  {core.display_path(md_path)}: reader changed from {previous} to {current}{reason}"
            warning = " ".join(warning.splitlines())
            print(warning, file=sys.stderr)
            warnings.append(warning)
    return warnings


def finish_history(success: bool) -> None:
    pending = core.BUILD.pop("history-pending", [])
    core.BUILD.pop("history-reader", None)
    if not success:
        for path, _, md_path, _, before, after in reversed(pending):
            try:
                # Do not overwrite a history another build or the author has changed meanwhile.
                if path.read_bytes() != after:
                    continue
                if before is None:
                    path.unlink()
                else:
                    partial = path.with_name(path.name + ".part")
                    partial.write_bytes(before)
                    partial.replace(path)
            except OSError as error:
                print(f"WARN  {core.display_path(md_path)}: cannot restore {core.display_path(path)} ({error.strerror or error})", file=sys.stderr)


DEFAULT_BACKUP_OPTIONS = {
    "enabled": False,
    # Relative to the document's own directory (absolute also accepted). Empty is the default
    # place, see backup_directory(): ".backups", or a folder of the older spellings that is already there.
    "dir": "",
    # Newest N plain-timestamp snapshots of this one file kept; 0 keeps none (no copy is made, nothing already there is
    # deleted); a negative number keeps every one (the default; v3.32.43: 0 used to mean all, now it means what it says).
    # Never counts or deletes tagged ones -- see backup_snapshots().
    "keep": -1,
    "format": "compact",
    # The built PDFs kept beside the sources (v3.32.42): the newest n; 0 keeps none (the default: a build keeps what it always
    # kept, the source); a negative number keeps every one. Same meaning as `keep`.
    "pdfs": 0,
}


DEFAULT_BACKUP_DIR = ".backups"


def notice_once(name: str, text: str) -> None:
    """Say `text` the first time only (a marker file in pdfmd's config folder); never in a pipe or from the API."""
    path = core.config_root() / f"notice-{name}"
    if os.environ.get("PDFMD_NO_PROMPT") or path.exists():
        return
    print(text)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("shown\n", encoding="utf-8")
    except OSError:
        pass


def backup_notice(backup_dir: Path, options: dict) -> None:
    """The first time a backup lands in the default hidden folder, say where it is."""
    if not options.get("dir") and backup_dir.name == DEFAULT_BACKUP_DIR:
        notice_once("backup-folder", f"NOTE  backups go to {DEFAULT_BACKUP_DIR}/ beside the document by default. It is a "
                    "hidden folder (ls -a shows it), so don't worry if you don't see it; "
                    "`pdfmd --setup` or `pdfmd-options: {backup: {dir: ...}}` changes the place.")


def backup_target(backup_dir: Path, template: str, md_path: Path) -> Path:
    """First free snapshot path for `template` right now."""
    rendered = datetime.now().strftime(core.fill_backup_template(template, md_path))
    target = backup_dir / rendered
    counter = 2
    while target.exists():
        head, tail = rendered, ""
        for candidate in (md_path.suffix, ".bak"):
            if candidate and rendered.endswith(candidate):
                head, tail = rendered[:-len(candidate)], candidate
                break
        target = backup_dir / f"{head}-{counter}{tail}"
        counter += 1
    return target


def backup_sort_key(path: Path) -> tuple:
    """When a snapshot was taken: a full date+time in its name wins
    (20260924-091500 / 20260924091500 / 09-24_09-15-00 with the year from
    mtime), else its mtime. Mixed conventions in one folder still order
    correctly this way. Second element breaks same-second ties."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    # Same-second snapshots (a -2 collision counter) tie on the name; the
    # later one is always a later edit of the source (an unchanged one is
    # never written), so mtime -- copy2 keeps the source's -- breaks it.
    tiebreak = mtime
    full = re.search(r"(?<!\d)(\d{8})-?(\d{6})(?!\d)", path.name)
    if full:
        try:
            return (datetime.strptime(full.group(1) + full.group(2), "%Y%m%d%H%M%S").timestamp(), tiebreak)
        except ValueError:
            pass
    short = re.search(r"(?<!\d)(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})(?!\d)", path.name)
    if short:
        try:
            year = datetime.fromtimestamp(mtime).year
            return (datetime(year, *map(int, short.groups())).timestamp(), tiebreak)
        except ValueError:
            pass
    return (mtime, tiebreak)


def backup_fields(value, implied_on: bool = True) -> dict:
    """The fields a pdfmd-options.backup value sets: a bare bool, a directory name
    (shorthand for enabling it with that directory), or a full dict of
    {enabled, dir, keep, format}. A dict with no explicit ``enabled`` counts
    as on, same as stamp_fields' rule, except in the config file (``implied_on`` False).
    """
    options: dict = {}
    if isinstance(value, bool):
        options["enabled"] = value
    elif isinstance(value, str):
        options["enabled"] = True
        options["dir"] = value
    elif isinstance(value, dict):
        if "enabled" in value or implied_on:
            options["enabled"] = bool(value.get("enabled", True))
        if value.get("dir"):
            options["dir"] = str(value["dir"])
        if value.get("format"):
            options["format"] = str(value["format"])
        for name in ("keep", "pdfs"):
            if value.get(name) is not None:                      # an empty `keep:` is no setting (it was "all" before v3.32.43, too)
                options[name] = backup_count(name, value[name])
    return options


def backup_count(name: str, given) -> int:
    """How many copies `backup: {keep}` (sources) or `{pdfs}` (built PDFs) keeps: a whole number, the newest N; 0 none; negative
    every one (v3.32.43: the two share this meaning). The words all/none/off/true/false are taken too."""
    words = {"all": -1, "none": 0, "off": 0, "true": -1, "false": 0}
    word = str(given).strip().lower()
    try:
        return words[word] if word in words else int(given)
    except (TypeError, ValueError):
        raise SystemExit(f"pdfmd-options.backup.{name} must be a whole number (negative: all, 0: none) or all/none, got {given!r}")


def resolve_backup_options(md_path: Path, metadata_files: list[Path], cli_enabled: bool | None,
                           cli_format: str | None = None) -> dict:
    """Document front matter first, then each metadata file in order (same
    cascade as frontmatter_stamp), then --backup/--no-backup and
    --backup-format on top.
    """
    merged: dict = {}
    for where, own in core.option_sources(md_path, metadata_files):       # field by field since v3.27.1
        for name in ("backup", "backups"):                           # both spellings (v3.32.43); `backup` first where both are set
            if name in own:
                for key, value in backup_fields(own[name], implied_on=not core.is_setup_layer(where)).items():
                    merged.setdefault(key, value)
    options = {**DEFAULT_BACKUP_OPTIONS, **merged}
    if cli_enabled is not None:
        options["enabled"] = cli_enabled
    if cli_format:
        options["format"] = cli_format
    return options


def backup_before_edit(md_path: Path, metadata_files: list[Path] | None = None) -> Path | None:
    """A snapshot of md_path before pdfmd rewrites it (`--extract-tables`...): in the backup folder, named by the
    configured format, whether or not backups are switched on for compiles. The path, or None if it failed."""
    options = core.resolve_backup_options(md_path, metadata_files or [], None)
    backup_dir = core.backup_directory(md_path, options)
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_notice(backup_dir, options)
        target = backup_target(backup_dir, core.backup_template(options["format"]), md_path)
        shutil.copy2(md_path, target)
        return target
    except OSError as error:
        print(f"WARN  {core.display_path(md_path)}: backup failed: {error}", file=sys.stderr)
        return None
