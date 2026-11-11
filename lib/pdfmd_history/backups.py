"""The backups and the history of a document: the snapshots a build keeps beside the source (`backup_directory`, `backup_template`,
`fill_backup_template`, `backup_name_regex`, `backup_snapshots`, `backup_unchanged`, `backup_after_success`, `backup_pdf_after_success`,
`backup_summary`, with `BACKUP_FORMATS`), the compile history in a `.hst` file and in a document's BUILD NOTES (`notes_to_entries`,
`entries_to_notes`, `entry_line`), and the commands `--history`, `--history-diff`, `--history-restore` and `--init-backups`
(`history_command`, `history_view_command`, `history_interactive`, `history_act`, `init_backups_command`, `document_versions`,
`version_text`, `version_differs`, `restore_version`).

Moved out of `pdfmd.py` unchanged (v3.33.28, SPLIT.md), with `BACKUP_FORMATS`, `BACKUP_IGNORED_LINE_RE`, `HISTORY_SHOWN`,
`LEGACY_BACKUP_DIRS`, `_COUNTER` and `_STRFTIME_PATTERNS`. `core` is the `pdfmd` module, bound when the module is first loaded (a
stand-in in `pdfmd.py` loads it on the first call; the first binding wins); the pdfmd names the code uses (`AUTO_METADATA_DISABLED`,
`DEFAULT_BACKUP_DIR`, `EMBED_BLOCK_RE`, `IGNORE_MARK_RE`, `SETUP_HEADER`, `atomic_write_text`, `backup_before_edit`, `backup_notice`,
`backup_sort_key`, `backup_target`, `build_notes_blocks`, `config_path`, `display_path`, `find_markdown`, `find_metadata`,
`history_file`, `history_heading_pattern`, `history_module`, `is_pdfmd_notes`, `load_config`, `normalized_source`, `note_entry`,
`pdfmd_build_notes`, `plan_scaffold`, `resolve_backup_options`, `resolve_stamp_options`, `sha256_text`, `stamp_line_pattern`,
`update_build_notes` and `vprint`) are read as `core.X` when it runs. `backup_after_success` and `backup_pdf_after_success` were
decorated with `pdfmd`'s `@timed`, which is defined far below the place where `pdfmd.py` can load this module: `_timed` is the same
decorator looked up when the function is called. `history_module()` stays in `pdfmd.py` (other code calls it); the functions that
`pdfmd.py`, `lib/pdfmd_report` or the tests call are reached through the stand-ins there.
"""

from __future__ import annotations

import contextlib
import filecmp
import functools
import io
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    from pdfmd_yaml_support import yaml
except ImportError:                                # pragma: no cover -- incomplete installation
    yaml = None

core = None


def _timed(name):
    """`core.timed(name)` for a function defined before `core.timed` exists: each call is wrapped when it is made."""
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            return core.timed(name)(function)(*args, **kwargs)
        return wrapper
    return decorate


def entry_line(entry) -> str:
    return f"{'Restored' if entry.kind == 'restored' else 'Compiled'} {entry.text} -- {entry.when}"


def notes_to_entries(text: str, whole: bool = False) -> tuple[str, list]:
    """(the text without pdfmd's own lines in its BUILD NOTES blocks, those lines as .hst entries). What anybody
    else wrote in the block stays; a block left with nothing but its heading goes. A block marked `pdfmd: ignore`
    is not looked at. With ``whole`` the block pdfmd owns goes entirely -- the free text in it too, as one `note`
    entry (`block=1`) whose text is those lines -- while a block that is not pdfmd's is still left alone."""
    entries: list = []
    for match in reversed(core.build_notes_blocks(text)):
        indent, body = match.group("indent"), match.group("body")
        if core.IGNORE_MARK_RE.search(body) or not core.is_pdfmd_notes(body, indent):
            continue
        kept: list[str] = []
        heading_at: int | None = None
        for raw in body.split("\n"):
            own = (core.stamp_line_pattern(indent).match(raw)
                   or re.match(rf"^{re.escape(indent)}  - (?:Compiled|Restored)\b", raw))
            entry = core.note_entry(raw) if own else None
            if entry is not None:
                entries.append(entry)
                continue
            if core.history_heading_pattern(indent).match(raw + "\n"):
                heading_at = len(kept)
            if raw == "" and kept and kept[-1] == "":
                continue                                   # the blank line a removed line leaves behind
            kept.append(raw)
        if heading_at is not None and not any(re.match(rf"^{re.escape(indent)}  - ", line) for line in kept[heading_at + 1:]):
            del kept[heading_at]
        remainder = "\n".join(kept)
        if whole:
            free = [line[len(indent):] if line.startswith(indent) else line.strip() for line in kept]
            if heading_at is not None and heading_at < len(free) and free[heading_at].strip() == "Compile History:":
                del free[heading_at]
            while free and not free[0].strip():
                free.pop(0)
            while free and not free[-1].strip():
                free.pop()
            if free:
                entries.append(core.history_module().Entry(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "note",
                                                      "\n".join(free), (("block", "1"),)))
            remainder = ""
        if not remainder.strip().strip("\n"):
            end = match.end()
            while text[end:end + 1] == "\n":
                end += 1
            start = match.start()
            text = text[:start].rstrip("\n") + ("\n\n" if text[end:].strip() else "\n") + text[end:]
        else:
            text = text[:match.start("body")] + remainder + text[match.end("body"):]
    return text, entries


def entries_to_notes(text: str, entries: list) -> str:
    """BUILD NOTES with `entries` in it, together with what was already there: the newest compile as the live line,
    then the free text of a block moved out whole (`note` entries with `block=`), then the rest newest first as the
    "Compile History:" list."""
    history = core.history_module()
    text, existing = notes_to_entries(text)
    free = [entry.text for entry in entries if entry.meta_dict().get("block")]
    merged = history.merge(existing, [entry for entry in entries if not entry.meta_dict().get("block")])
    if not merged and not free:
        return text
    live = next((entry for entry in merged if entry.kind == "compiled"), None)
    bullets = [entry for entry in merged if entry is not live]
    indent = "     "
    if live is not None:
        text, _ = core.update_build_notes(text, entry_line(live), "replace")
    match = core.pdfmd_build_notes(text) if live is not None else None
    if match is None:
        lines = [f"<!-- {'=' * 60}", f"{indent}BUILD NOTES", ""]
        for chunk in free:
            lines += [(indent + line) if line else "" for line in chunk.split("\n")] + [""]
        if bullets:
            lines += [f"{indent}Compile History:", *(f"{indent}  - {entry_line(entry)}" for entry in bullets)]
        lines += [f"{indent}{'=' * 60} -->"]
        block = "\n".join(lines) + "\n"
        embedded = core.EMBED_BLOCK_RE.search(text)
        if embedded:
            return text[:embedded.start()].rstrip("\n") + "\n\n" + block + "\n" + text[embedded.start():]
        return text.rstrip("\n") + "\n\n" + block
    indent, body = match.group("indent"), match.group("body")
    if free:
        live_at = core.stamp_line_pattern(indent).search(body)
        chunk = "".join(("\n".join((indent + line) if line else "" for line in text_.split("\n"))) + "\n\n" for text_ in free)
        if live_at is not None:
            position = live_at.end() + (2 if body[live_at.end():live_at.end() + 2] == "\n\n" else 1)
            body = body[:position] + chunk + body[position:]
    if bullets:
        trimmed = body.rstrip(" \t").rstrip("\n")
        body = (trimmed + "\n\n" + f"{indent}Compile History:\n"
                + "".join(f"{indent}  - {entry_line(entry)}\n" for entry in bullets) + indent)
    return text[:match.start("body")] + body + text[match.end("body"):]


# --- --history, --history-diff, --history-restore, --init-backups --------------------------------------------

HISTORY_SHOWN = 15                       # versions listed without --history-all


def backup_folders(document: Path, options: dict) -> list[Path]:
    """Every folder where a snapshot of `document` may be: the configured one, then each folder of the spellings pdfmd
    and its author have used (`.backups`, `backup`, `backups`, `.backup`, `_backups`) beside the document."""
    folders: list[Path] = []
    for folder in (backup_directory(document, options),
                   *(document.parent / name for name in (core.DEFAULT_BACKUP_DIR, *LEGACY_BACKUP_DIRS))):
        if folder.is_dir() and folder not in folders:
            folders.append(folder)
    return folders


def document_versions(document: Path, metadata_files: list[Path], include_git: bool = True) -> list:
    """The versions of one file: its backups in every folder and naming form, the commits that changed it, and the
    compiles recorded in its .hst and BUILD NOTES that no backup accounts for."""
    history = core.history_module()
    versions = history.versions
    options = core.resolve_backup_options(document, metadata_files, None)
    template = backup_template(options["format"])
    recorded, _ = history.read_file(core.history_file(document, metadata_files, existing=True))
    try:
        _, in_notes = notes_to_entries(document.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        in_notes = []
    compiles = history.merge(recorded, in_notes)
    result = []
    seen: set[Path] = set()
    for folder in backup_folders(document, options):
        try:
            found, _ = backup_snapshots(folder, document, template)
        except OSError:
            continue
        for path in found:
            if path in seen or path.resolve() in seen:
                continue
            seen.add(path)
            seen.add(path.resolve())
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
            _, inside = notes_to_entries(text)
            digest = core.sha256_text(core.normalized_source(text))[:12]
            absorbed = [entry for entry in compiles if entry.kind == "compiled" and entry.meta_dict().get("sha") == digest]
            summary = ""
            newest = next((entry for entry in sorted(inside, key=lambda item: item.when, reverse=True)
                           if entry.kind == "compiled"), None) or next(iter(absorbed), None)
            if newest is not None:
                summary = f"compiled {newest.text}"
            result.append(versions.Version(core.backup_sort_key(path)[0], "backup", versions.timestamp_id(path.name),
                                           path.name, summary, path=path, document=document,
                                           lines=len(text.splitlines())))
    backup_times = [version.when for version in result]
    backup_digests = {core.sha256_text(core.normalized_source(version.path.read_text(encoding="utf-8-sig", errors="replace")))[:12]
                      for version in result if version.path is not None}
    for entry in compiles:
        stamp = datetime.strptime(entry.when, "%Y-%m-%d %H:%M:%S").timestamp()
        if entry.kind == "compiled" and (entry.meta_dict().get("sha") in backup_digests
                                         or any(abs(stamp - when) <= 5 for when in backup_times)):
            continue                                       # a backup holds that compile and says so itself
        result.append(versions.Version(stamp, {"restored": "restore", "note": "note", "partial": "partial"}.get(entry.kind, "compile"),
                                       f"{entry.kind}-{entry.when}", entry.text, "", document=document))
    if include_git:
        for commit in history.git.log(document):
            result.append(versions.Version(commit.when, "git", commit.short, commit.subject, commit.author,
                                           commit=commit.full, document=document))
    return versions.sort_newest_first(result)


def version_text(version) -> str | None:
    history = core.history_module()
    if version.kind == "backup" and version.path is not None:
        try:
            return version.path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return None
    if version.kind == "git" and version.document is not None:
        return history.git.show(version.document, version.commit)
    return None


def version_differs(version) -> bool:
    """Whether `version`'s text, apart from pdfmd's own lines of BUILD NOTES, is not the document as it is."""
    text = version_text(version)
    if text is None or version.document is None:
        return False
    try:
        current = version.document.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return False
    return core.normalized_source(notes_to_entries(text)[0]) != core.normalized_source(notes_to_entries(current)[0])


def restore_version(document: Path, version, metadata_files: list[Path], note: bool, dry_run: bool) -> int:
    """Put `version` back as `document`. The file as it is now is backed up first; the BUILD NOTES and the history
    stay those of the NEWEST file (an old version has the notes of its own day); and a "Restored" entry says what
    happened and when, unless the document or the command line says not to."""
    history = core.history_module()
    text = version_text(version)
    if text is None:
        print(f"ERROR  {core.display_path(document)}: cannot read {version.label}", file=sys.stderr)
        return 1
    current = document.read_text(encoding="utf-8-sig")
    options = core.resolve_stamp_options(document, metadata_files, {})
    old_stripped, _ = notes_to_entries(text)
    _, kept = notes_to_entries(current)
    result = entries_to_notes(old_stripped, kept) if kept else old_stripped
    if core.normalized_source(result) == core.normalized_source(current):
        print(f"{core.display_path(document)}: already the same as {version.label}; nothing to restore")
        return 0
    store = options["store"]
    hst_exists = core.history_file(document, metadata_files, existing=True).is_file()
    wanted = note and options.get("restored_note", True) and (options["enabled"] or hst_exists or bool(kept))
    to_file = wanted and (store in ("file", "both") or (store == "notes" and not kept and hst_exists))
    to_notes = wanted and store in ("notes", "both") and not (to_file and store == "notes")
    source = version.label if version.kind == "backup" else f"commit {version.ref}"
    entry = history.Entry(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "restored", f"version {version.ref} ({source})",
                          tuple(item for item in (("sha", core.sha256_text(core.normalized_source(text))[:12]),
                                                  ("from", version.kind)) if item[1]))
    if to_notes:
        result = entries_to_notes(old_stripped, [*kept, entry])
    print(f"{'WOULD RESTORE' if dry_run else 'RESTORING'}  {core.display_path(document)} <- {source}  ({version.when_text})")
    if dry_run:
        print(history.versions.unified(current, result, version.label, "current", sys.stdout.isatty()) or "  (no difference)")
        return 0
    saved = core.backup_before_edit(document, metadata_files)
    if saved is None:
        print(f"ERROR  {core.display_path(document)}: not restored, since the file as it is could not be backed up.",
              file=sys.stderr)
        return 1
    core.atomic_write_text(document, result)
    if to_file:
        history.add_entry(core.history_file(document, metadata_files), entry, document.name)
    print(f"  BACKUP    {core.display_path(saved)}  (the file as it was a moment ago)")
    print(f"  RESTORED  {core.display_path(document)}" + ("  (a \"Restored\" entry is in its history)" if to_file or to_notes else ""))
    return 0


def history_documents(args) -> list[Path]:
    documents: list[Path] = []
    for target in (args.path or [Path.cwd()]):
        try:
            document = core.find_markdown(target)
        except FileNotFoundError as error:
            raise SystemExit(f"ERROR  {error}")
        with contextlib.redirect_stderr(io.StringIO()):
            plan = core.plan_scaffold(document, [], args.no_auto, args.metadata_file)
        for item in (plan.files if plan else [document]):
            if item not in documents:
                documents.append(item)
    return documents


def linked_metadata(document: Path, requested) -> list[Path]:
    found = core.find_metadata(document.parent.resolve(), requested, document_stem=document.stem, document=document)
    return [] if found is core.AUTO_METADATA_DISABLED or found is None else (found if isinstance(found, list) else [found])


def history_view_command(args) -> int:
    """--history / --history-diff REF / --history-restore REF."""
    history = core.history_module()
    if history is None:
        print("ERROR  --history needs the pdfmd_history package (a full install of pdfmd-cli).", file=sys.stderr)
        return 1
    documents = history_documents(args)
    reference = args.history_diff or args.history_restore
    all_versions: list = []
    for document in documents:
        all_versions += document_versions(document, linked_metadata(document, args.metadata_file))
    all_versions = history.versions.sort_newest_first(all_versions)
    many = len(documents) > 1
    if not reference:
        shown = all_versions if args.history_all else all_versions[:HISTORY_SHOWN]
        label = ", ".join(core.display_path(item) for item in documents)
        if not all_versions:
            print(f"{label}: no versions found (no backups in {core.display_path(backup_directory(documents[0], core.resolve_backup_options(documents[0], [], None)))}"
                  " or beside it, no commits, no recorded compiles). `pdfmd --init-backups` starts keeping them.")
            return 0
        print(f"{label}: {len(all_versions)} version{'s' if len(all_versions) != 1 else ''}")
        print(history.versions.table(shown, many))
        if len(shown) < len(all_versions):
            print(f"  ... {len(all_versions) - len(shown)} older; --history-all lists them")
        if sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get("PDFMD_NO_PROMPT"):
            return history_interactive(documents, all_versions, shown, args)
        print("  pdfmd --history-diff N|ID FILE shows what differs; --history-restore N|ID FILE puts a version back "
              "(N is the number above; ID a timestamp, a file name or a commit)")
        return 0
    try:
        version = history.versions.resolve(reference, all_versions, version_differs)
    except history.versions.Ambiguous as error:
        print(f"ERROR  {reference!r} matches several versions: {error}", file=sys.stderr)
        return 1
    if version is None or version.kind not in ("backup", "git") or version.document is None:
        print(f"ERROR  no version of {', '.join(core.display_path(item) for item in documents)} matches {reference!r}"
              + (" (a recorded entry has no copy of the file to go back to)" if version is not None else "")
              + ". `pdfmd --history FILE` lists them.", file=sys.stderr)
        return 1
    return history_act(version, "restore" if args.history_restore else "diff", args)


def history_act(version, action: str, args) -> int:
    history = core.history_module()
    document = version.document
    if action == "diff":
        text = version_text(version)
        if text is None:
            print(f"ERROR  cannot read {version.label}", file=sys.stderr)
            return 1
        current = document.read_text(encoding="utf-8-sig")
        diff = history.versions.unified(current, text, version.label, document.name, sys.stdout.isatty())
        print(diff or f"{core.display_path(document)} is the same as {version.label}")
        return 0
    return restore_version(document, version, linked_metadata(document, args.metadata_file),
                           not args.no_restored_note, args.dry_run)


def history_interactive(documents: list[Path], versions: list, shown: list, args) -> int:
    """The list, navigable: a number shows what a version changed, `d N` the full difference, `r N` restores it."""
    history = core.history_module()
    print("  [N] what differs   d N  diff   r N  restore   a  list all   q  quit")
    while True:
        try:
            answer = input("history> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not answer or answer.casefold() in ("q", "quit", "exit"):
            return 0
        if answer.casefold() in ("a", "all"):
            print(history.versions.table(versions, len(documents) > 1))
            continue
        word, _, rest = answer.partition(" ")
        action, target = ("diff", answer) if word.isdigit() else (
            {"d": "diff", "diff": "diff", "r": "restore", "restore": "restore"}.get(word.casefold(), ""), rest.strip())
        if not action:
            print("  a number, `d N`, `r N`, `a` or `q`")
            continue
        try:
            version = history.versions.resolve(target, versions, version_differs)
        except history.versions.Ambiguous as error:
            print(f"  {target!r} matches several: {error}")
            continue
        if version is None or version.kind not in ("backup", "git"):
            print("  no such version" if version is None else "  that is a recorded entry; there is no copy of the file to use")
            continue
        if action == "restore":
            if input(f"  put {version.label} back as {version.document.name}? the file as it is now is backed up first [y/N] "
                     ).strip().casefold() not in ("y", "yes"):
                continue
        history_act(version, action, args)


def init_backups_command(args) -> int:
    """`--init-backups [FOLDER]`: switch on backups and a history file for a document (or, with --global, for all)."""
    folder = args.backup_folder or core.DEFAULT_BACKUP_DIR
    note_text = f"AUTO GENERATED by pdfmd --init-backups on {datetime.now().strftime('%Y-%m-%d')}; edit freely"
    wanted = {"backup": {"enabled": True, **({"dir": folder} if folder != core.DEFAULT_BACKUP_DIR else {})},
              "stamp": {"enabled": True, "store": "file"}}
    if args.global_:
        if yaml is None or core.config_path() is None:
            print("ERROR  the config file is switched off or PyYAML is missing.", file=sys.stderr)
            return 1
        data = core.load_config()
        options = data.setdefault("options", {}) if isinstance(data.get("options"), dict) or "options" not in data else {}
        added = [key for key in wanted if key not in options]
        for key in added:
            options[key] = wanted[key]
        if added:
            core.config_path().parent.mkdir(parents=True, exist_ok=True)
            core.atomic_write_text(core.config_path(), f"# {note_text}\n" + core.SETUP_HEADER
                              + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        print(f"CONFIG  {core.config_path()}: " + (f"set {', '.join(added)}" if added else "backup and stamp were already set; left alone"))
        return 0
    status = 0
    for document in history_documents(args):
        text = document.read_text(encoding="utf-8-sig")
        front = re.match(r"^---[ \t]*\n(?P<yaml>.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)", text, re.DOTALL)
        metadata = [item for item in linked_metadata(document, args.metadata_file) if item.parent == document.parent]
        target = document if front else (metadata[0] if metadata else None)
        if target is None:
            print(f"{core.display_path(document)}: has no front matter and no metadata.yaml beside it. Adding either one changes how "
                  "pdfmd reads the document (Pandoc's markdown instead of GitHub's), so it is not done for you. "
                  "Add a front matter block yourself, or run `pdfmd --init-backups --global` to set it for every document.")
            status = 1
            continue
        body = front.group("yaml") if target == document else target.read_text(encoding="utf-8-sig")
        try:
            existing = yaml.safe_load(body) if yaml is not None else None
        except yaml.YAMLError:
            existing = None
        existing = existing if isinstance(existing, dict) else {}
        options = existing.get("pdfmd-options") if isinstance(existing.get("pdfmd-options"), dict) else {}
        missing = {key: value for key, value in wanted.items() if key not in options}
        if existing.get("pdfmd-options") not in (None, {}) and not isinstance(existing.get("pdfmd-options"), dict):
            print(f"{core.display_path(target)}: its pdfmd-options is not a mapping; add backup/stamp by hand.", file=sys.stderr)
            status = 1
            continue
        saved = None
        if missing:
            lines = body.split("\n")
            at = next((index for index, line in enumerate(lines) if re.match(r"^pdfmd-options\s*:\s*(#.*)?$", line)), None)
            if at is None and "pdfmd-options" in existing:
                print(f"{core.display_path(target)}: its pdfmd-options is written in one line; add backup/stamp by hand: "
                      + json.dumps(missing), file=sys.stderr)
                status = 1
                continue
            def flow(value) -> str:
                if isinstance(value, dict):
                    return "{" + ", ".join(f"{key}: {flow(item)}" for key, item in value.items()) + "}"
                return str(value).lower() if isinstance(value, bool) else str(value)

            block = [f"  {key}: {flow(value)}" for key, value in missing.items()]
            if at is None:
                lines = [*lines, f"# {note_text}", "pdfmd-options:", *block]
            else:
                lines[at + 1:at + 1] = [f"  # {note_text}", *block]
            saved = core.backup_before_edit(target) if target.is_file() else None
            if saved is None:
                print(f"ERROR  {core.display_path(target)}: not changed, since its backup could not be made.", file=sys.stderr)
                status = 1
                continue
            new_body = "\n".join(lines)
            core.atomic_write_text(target, text[:front.start("yaml")] + new_body + text[front.end("yaml"):] if target == document
                              else new_body)
        options_now = core.resolve_backup_options(document, linked_metadata(document, args.metadata_file), None)
        backup_dir = backup_directory(document, {**options_now, **({"dir": folder} if folder != core.DEFAULT_BACKUP_DIR else {})})
        backup_dir.mkdir(parents=True, exist_ok=True)
        first = saved if saved is not None and target == document else core.backup_before_edit(
            document, linked_metadata(document, args.metadata_file))
        history = core.history_module()
        if history is not None:
            history.add_entry(core.history_file(document, linked_metadata(document, args.metadata_file)),
                              history.Entry(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "note",
                                            "history kept from here (pdfmd --init-backups)"), document.name)
        print(f"{core.display_path(document)}:")
        print(f"  {'SET' if missing else 'ALREADY SET'}  backup + stamp (store: file) in {core.display_path(target)}"
              + (f"  ({', '.join(missing)} added; the old file is {core.display_path(saved)})" if saved else ""))
        print(f"  FOLDER  {core.display_path(backup_dir)}" + ("" if first is None else f"  (first copy: {first.name})"))
        print("  from now on every build keeps a copy of the source when it changed, and records the compile in "
              f"{document.stem}.hst, without editing the document. `pdfmd --history {document.name}` lists them.")
    return status


def history_command(args) -> int:
    """--history-to-file / --history-to-notes / --merge-history. Returns the exit status."""
    history = core.history_module()
    if history is None:
        print("ERROR  the history commands need the pdfmd_history package (a full install of pdfmd-cli).", file=sys.stderr)
        return 1
    if args.merge_history:
        sources = [Path(item) for item in args.merge_history]
        missing = [str(item) for item in sources if not item.is_file()]
        if missing:
            print(f"ERROR  not a file: {', '.join(missing)}", file=sys.stderr)
            return 1
        lists, other = [], []
        for source in sources:
            entries, comments = history.read_file(source)
            lists.append(entries)
            other += [line for line in comments if line not in other]
        name = sources[0].stem + ".md"
        merged = history.render(history.merge(*lists), name, other)
        if args.out:
            history.write_file(args.out, history.merge(*lists), name, other)
            print(f"WROTE  {core.display_path(args.out)}  ({sum(len(item) for item in lists)} entries in, "
                  f"{len(history.merge(*lists))} out)")
        else:
            sys.stdout.write(merged)
        return 0
    status = 0
    for target in (args.path or [Path.cwd()]):
        try:
            document = core.find_markdown(target)
        except FileNotFoundError as error:
            print(f"ERROR  {error}", file=sys.stderr)
            return 1
        text = document.read_text(encoding="utf-8-sig")
        metadata = core.find_metadata(document.parent.resolve(), args.metadata_file, document_stem=document.stem,
                                 document=document)
        linked = [] if metadata is core.AUTO_METADATA_DISABLED or metadata is None else (metadata if isinstance(metadata, list) else [metadata])
        path = core.history_file(document, linked, existing=args.history_to_notes)
        if args.history_to_file:
            stripped, entries = notes_to_entries(text, whole=True)
            if not entries:
                print(f"{core.display_path(document)}: no pdfmd BUILD NOTES block to move")
                continue
            old, other = history.read_file(path)
            known = {entry.text for entry in old if entry.meta_dict().get("block")}
            entries = [entry for entry in entries if not (entry.meta_dict().get("block") and entry.text in known)]
            merged = history.merge(old, entries)
            print(f"{core.display_path(document)}: {len(entries)} compile{'s' if len(entries) != 1 else ''} -> "
                  f"{core.display_path(path)} ({len(merged)} entries there now)")
            if args.dry_run:
                continue
            if core.backup_before_edit(document) is None:
                print(f"ERROR  {core.display_path(document)}: not changed, since its backup could not be made.", file=sys.stderr)
                status = 1
                continue
            history.write_file(path, merged, document.name, other)       # the file first: nothing is lost if this stops
            core.atomic_write_text(document, stripped)
            core.backup_notice(path.parent, core.resolve_backup_options(document, linked, None))
        else:
            entries, other = history.read_file(path)
            other = [line for line in other if not line.startswith("# pdfmd history of")]
            compiled = [entry for entry in entries if entry.kind == "compiled" or entry.meta_dict().get("block")]
            if not compiled:
                print(f"{core.display_path(document)}: no compiles in {core.display_path(path)} to move")
                continue
            print(f"{core.display_path(document)}: {len(compiled)} entr{'ies' if len(compiled) != 1 else 'y'} -> BUILD NOTES"
                  + (f"; {len(entries) - len(compiled)} other entr{'y stays' if len(entries) - len(compiled) == 1 else 'ies stay'} in the file"
                     if len(entries) != len(compiled) else ""))
            if args.dry_run:
                continue
            if core.backup_before_edit(document) is None:
                print(f"ERROR  {core.display_path(document)}: not changed, since its backup could not be made.", file=sys.stderr)
                status = 1
                continue
            core.atomic_write_text(document, entries_to_notes(text, compiled))
            left = [entry for entry in entries if entry not in compiled]
            if left or other:
                history.write_file(path, left, document.name, other)
            else:
                path.unlink(missing_ok=True)
    return status


# Snapshot names come from `format:` -- a preset name from BACKUP_FORMATS
# or a custom template: {name} (report.md), {stem} (report), {ext} (.md),
# plus any strftime code (%Y%m%d-%H%M%S, ...). Every preset is a naming
# convention already in real use in the author's folders (2026-09-24 survey), so
# any folder can keep the style it already has.
BACKUP_FORMATS = {
    # report.md.bak.20260924091500 -- LR2/backup, nulabreport/_superseded
    "compact": "{name}.bak.%Y%m%d%H%M%S",
    # report.md.bak.20260924-091500 -- compact with a date/time separator
    "dashed": "{name}.bak.%Y%m%d-%H%M%S",
    # report_20260924-091500.md -- LR3/backups, LR4-5/backup, ir/webbook;
    # keeps the real extension, so a snapshot opens straight in its app
    "stem": "{stem}_%Y%m%d-%H%M%S{ext}",
    # report.md.20260924-091500.bak -- nulabreport/backups
    "suffix": "{name}.%Y%m%d-%H%M%S.bak",
    # report.md.09-24_09-15-00.bak -- LR4-5/prelab/backups (no year)
    "short": "{name}.%m-%d_%H-%M-%S.bak",
}


# strftime codes -> what they render as, for recognizing a format's own
# output again (dedupe/pruning). Anything unlisted matches loosely.
_STRFTIME_PATTERNS = {
    "Y": r"\d{4}", "y": r"\d{2}", "m": r"\d{2}", "d": r"\d{2}", "H": r"\d{2}",
    "I": r"\d{2}", "M": r"\d{2}", "S": r"\d{2}", "f": r"\d{6}", "j": r"\d{3}",
    "p": r"[AP]M", "%": "%",
}
# Collision counter a snapshot name gets when its second (or minute, for a
# coarse format) is already taken -- "-2", "-3", ...
_COUNTER = r"(?:-\d+)?"


LEGACY_BACKUP_DIRS = ("backup", "backups", ".backup", "_backups")


def backup_directory(md_path: Path, options: dict) -> Path:
    """Where md_path's snapshots live: `dir:` when it is set, else the folder of the older spellings that is already
    beside the document (`backup/`, `backups/`...), else the hidden `.backups/`."""
    name = options.get("dir") or ""
    if name:
        folder = Path(os.path.expanduser(name))
        return folder if folder.is_absolute() else md_path.parent / folder
    for candidate in (core.DEFAULT_BACKUP_DIR, *LEGACY_BACKUP_DIRS):
        if (md_path.parent / candidate).is_dir():
            return md_path.parent / candidate
    return md_path.parent / core.DEFAULT_BACKUP_DIR


def backup_template(value: str) -> str:
    """Resolve a `format:` value to a template, validating a custom one."""
    template = BACKUP_FORMATS.get(value, value)
    if "{name}" not in template and "{stem}" not in template:
        raise SystemExit(f"pdfmd-options.backup.format {value!r}: needs {{name}} or {{stem}} "
                         f"(or a preset: {', '.join(BACKUP_FORMATS)}), or every file in the "
                         "folder would share one set of snapshot names")
    if "%" not in template:
        raise SystemExit(f"pdfmd-options.backup.format {value!r}: needs at least one strftime "
                         "code (e.g. %Y%m%d-%H%M%S), or every snapshot gets the same name")
    try:
        template.format(name="x", stem="x", ext="x")
    except (KeyError, IndexError, ValueError) as error:
        raise SystemExit(f"pdfmd-options.backup.format {value!r}: only {{name}}, {{stem}} and "
                         f"{{ext}} are recognized placeholders ({error})")
    return template


def fill_backup_template(template: str, md_path: Path) -> str:
    """Substitute {name}/{stem}/{ext}, leaving strftime codes in place --
    plain replace() rather than str.format so a file name with a literal
    brace can't break it, and any % in the name doubled so strftime keeps
    it literal."""
    for key, value in (("{name}", md_path.name), ("{stem}", md_path.stem), ("{ext}", md_path.suffix)):
        template = template.replace(key, value.replace("%", "%%"))
    return template


def backup_name_regex(template: str, md_path: Path) -> re.Pattern:
    """A regex matching every name `template` can produce for md_path,
    including a collision counter before the extension-like tail."""
    literal = fill_backup_template(template, md_path)
    parts = re.split(r"(%.)", literal)
    body = "".join(_STRFTIME_PATTERNS.get(part[1], r".+?") if part.startswith("%") and len(part) == 2
                   else re.escape(part) for part in parts)
    # Counter goes where backup_target() puts it: before the source's own
    # extension, before a trailing .bak, or at the very end.
    for tail in (re.escape(md_path.suffix), re.escape(".bak")):
        if tail and body.endswith(tail):
            return re.compile(f"^{body[:-len(tail)]}{_COUNTER}{tail}$")
    return re.compile(f"^{body}{_COUNTER}$")


# Plain-timestamp names any earlier convention (or any preset) produces for
# one file -- the ones `keep:` may prune. Anything else that still clearly
# belongs to the file (report.md.pre-irstack.20260923-211848.bak,
# chemicals.tex.before-LR1-2, report.md.pre-v1.17.0.bak, ...) is a
# deliberately named milestone: compared against for dedupe, never pruned.
def _plain_backup_patterns(md_path: Path) -> list[re.Pattern]:
    name, stem, ext = map(re.escape, (md_path.name, md_path.stem, md_path.suffix))
    return [re.compile(pattern) for pattern in (
        rf"^{name}\.bak\.\d{{8}}-?\d{{6}}{_COUNTER}$",                  # compact / dashed
        rf"^{stem}_\d{{8}}-\d{{6}}{_COUNTER}{ext}$",                     # stem
        rf"^{name}\.\d{{8}}-\d{{6}}{_COUNTER}\.bak$",                    # suffix
        rf"^{name}\.\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}-\d{{2}}{_COUNTER}\.bak$",  # short
        rf"^{name}\.bak-\d{{8}}[a-z]?$",                                 # pdfmd's own bak-YYYYMMDD[letter]
        rf"^{name}\.\d{{2}}-\d{{2}}\.bak$",                              # prelab5.pdf.18-53.bak
    )]


def backup_snapshots(backup_dir: Path, md_path: Path, template: str) -> tuple[list[Path], list[Path]]:
    """Every existing snapshot of md_path in backup_dir, in any recognized
    naming form, oldest first -- and the subset `keep:` may prune (plain
    timestamps only; see _plain_backup_patterns)."""
    own = backup_name_regex(template, md_path)
    plain = _plain_backup_patterns(md_path)
    stem_form = re.compile(rf"^{re.escape(md_path.stem)}_\d{{8}}-\d{{6}}.*{re.escape(md_path.suffix)}$")
    every, prunable = [], []
    for path in backup_dir.iterdir():
        if not path.is_file():
            continue
        name = path.name
        is_plain = bool(own.match(name)) or any(pattern.match(name) for pattern in plain)
        if is_plain or name.startswith(md_path.name + ".") or stem_form.match(name):
            every.append(path)
            if is_plain:
                prunable.append(path)
    every.sort(key=core.backup_sort_key)
    prunable.sort(key=core.backup_sort_key)
    return every, prunable


# Lines a --stamp writes (the live "Compiled ... pdfmd vX" line, its demoted
# "- Compiled ..." history bullets, and the "Compile History:" heading),
# ignored when deciding whether a source changed since its last snapshot --
# otherwise stamp mode: history, which rewrites a timestamp on every
# compile, would make every compile look like an edit. Found testing
# v3.8.0 against a real LR2 report.
BACKUP_IGNORED_LINE_RE = re.compile(
    r"^[ \t]*(?:(?:- )?Compiled\b.*?\bpdfmd\s+v[0-9][^\r\n]*|Compile History:[ \t]*)\r?\n?",
    re.MULTILINE,
)


def backup_unchanged(previous: Path, current: Path) -> bool:
    """Whether current matches the snapshot previous, apart from --stamp's
    own lines (BACKUP_IGNORED_LINE_RE). Byte comparison for anything that
    isn't UTF-8 text (an office document).
    """
    try:
        old_text = previous.read_text(encoding="utf-8")
        new_text = current.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return filecmp.cmp(previous, current, shallow=False)
    return BACKUP_IGNORED_LINE_RE.sub("", old_text) == BACKUP_IGNORED_LINE_RE.sub("", new_text)


@_timed("backup (source)")
def backup_after_success(md_path: Path, metadata_files: list[Path], cli_enabled: bool | None,
                         verbose: bool, cli_format: str | None = None, collect: "list[Path] | None" = None) -> None:
    """Snapshot md_path into its backup directory if --backup/
    pdfmd-options.backup says to -- skipped when the newest existing
    snapshot, in any recognized naming form (backup_snapshots), is already
    identical ignoring --stamp's own lines; then pruned to ``keep`` (a negative ``keep`` prunes nothing, 0 makes no copy).
    Best-effort: an OSError warns rather than failing a compile that
    already succeeded. ``collect``: the snapshot is added to this list instead of announced (a parts build announces its
    files in one line, see backup_summary()).
    """
    options = core.resolve_backup_options(md_path, metadata_files, cli_enabled, cli_format)
    if not options["enabled"]:
        return
    if options["keep"] == 0:
        core.vprint(verbose, f"AUTO BACKUP  {core.display_path(md_path)}: keep is 0; no copy made")
        return
    template = backup_template(options["format"])
    backup_dir = backup_directory(md_path, options)
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        core.backup_notice(backup_dir, options)
        every, prunable = backup_snapshots(backup_dir, md_path, template)
        if every and backup_unchanged(every[-1], md_path):
            core.vprint(verbose, f"AUTO BACKUP  {core.display_path(md_path)}: unchanged since "
                  f"{core.display_path(every[-1])}; skipped")
            return
        target = core.backup_target(backup_dir, template, md_path)
        shutil.copy2(md_path, target)
        if collect is None:
            print(f"BACKUP  {core.display_path(target)}")
        else:
            collect.append(target)
        prunable.append(target)
        if options["keep"] > 0 and len(prunable) > options["keep"]:
            for old in prunable[:-options["keep"]]:
                old.unlink()
                core.vprint(verbose, f"AUTO BACKUP  pruned {core.display_path(old)} (keep: {options['keep']})")
    except OSError as error:
        print(f"WARN  {core.display_path(md_path)}: backup failed: {error}", file=sys.stderr)


def backup_pdf_pattern(pdf: Path) -> re.Pattern:
    """The names the PDF copies of ``pdf`` have in the backup folder: `report_20261105-101500.pdf` (a collision counter after the stamp).
    A copy named otherwise (`report_submitted_...pdf`) is a milestone: never counted, never pruned."""
    return re.compile(rf"^{re.escape(pdf.stem)}_\d{{8}}-\d{{6}}{_COUNTER}\.pdf$")


@_timed("backup (PDF)")
def backup_pdf_after_success(md_path: Path, pdf: Path, metadata_files: list[Path], cli_enabled: bool | None,
                             verbose: bool, when: datetime | None = None) -> Path | None:
    """Copy the PDF a build made into the backup folder of ``md_path`` (v3.32.42), when `backup` is on and `backup: {pdfs: N}` is not 0:
    a rebuilt document cannot give an old PDF back (pdfmd, a package or a kit may have changed since), so the PDF is the one thing a
    source copy cannot replace. Named `STEM_YYYYMMDD-HHMMSS.pdf`, the stamp of the source copy of the same run (``when``) so the two pair
    up. Skipped when the newest copy is byte for byte this PDF; then the oldest copies beyond N are removed (N negative: none is).
    Best-effort like the source copy: an OSError warns and the build stands."""
    options = core.resolve_backup_options(md_path, metadata_files, cli_enabled)
    keep = options["pdfs"]
    if not options["enabled"] or keep == 0 or not pdf.is_file():
        return None
    backup_dir = backup_directory(md_path, options)
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        core.backup_notice(backup_dir, options)
        pattern = backup_pdf_pattern(pdf)
        kept = sorted((path for path in backup_dir.iterdir() if path.is_file() and pattern.match(path.name)), key=core.backup_sort_key)
        if kept and filecmp.cmp(kept[-1], pdf, shallow=False):
            core.vprint(verbose, f"AUTO BACKUP  {core.display_path(pdf)}: the same PDF as {core.display_path(kept[-1])}; skipped")
            return None
        stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
        target, counter = backup_dir / f"{pdf.stem}_{stamp}.pdf", 2
        while target.exists():
            target = backup_dir / f"{pdf.stem}_{stamp}-{counter}.pdf"
            counter += 1
        shutil.copy2(pdf, target)
        print(f"BACKUP  {core.display_path(target)}")
        kept.append(target)
        if keep > 0 and len(kept) > keep:
            for old in kept[:-keep]:
                old.unlink()
                core.vprint(verbose, f"AUTO BACKUP  pruned {core.display_path(old)} (pdfs: {keep})")
        return target
    except OSError as error:
        print(f"WARN  {core.display_path(pdf)}: PDF backup failed: {error}", file=sys.stderr)
        return None


def backup_summary(md_path: Path, saved: list[Path], when: datetime | None = None) -> str:
    """One line for the snapshots of one build: `BACKUP  report.md + 6 parts -> .backups/, parts/.backups/ (20261024-173319)`.
    A single snapshot is named as it always was. ``saved`` are the snapshot files; the first one is md_path's when it was saved."""
    if len(saved) == 1:
        return f"BACKUP  {core.display_path(saved[0])}"
    folders: list[str] = []
    for target in saved:
        folder = core.display_path(target.parent).rstrip("/\\") + os.sep
        if folder not in folders:
            folders.append(folder)
    own = bool(saved) and saved[0].name.startswith(md_path.name)
    parts = len(saved) - (1 if own else 0)
    what = f"{md_path.name} + {parts} part{'s' if parts != 1 else ''}" if own else f"{parts} parts"
    return f"BACKUP  {what} -> {', '.join(folders)} ({(when or datetime.now()).strftime('%Y%m%d-%H%M%S')})"
