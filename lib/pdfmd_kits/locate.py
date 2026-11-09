"""Where a kit's and a package's files are: the folders a local LaTeX package keeps what it ships for pdfmd, what kpsewhich finds, the
`<package>-pdfmd.yaml` helper, the folders of the kits chosen for a document, `--kits`, the kits' header file (its place in the Pandoc
command, what the other header files say settled with the kits' lines, the file in the cache folder), and the files a kit carries.

Moved out of `pdfmd.py` unchanged (v3.33.22, SPLIT.md). `core` is the `pdfmd` module, bound when the module is first loaded (a stand-in in
`pdfmd.py` loads it on the first call; the first binding wins); the pdfmd names the code uses (`BUNDLE_SKIP_DIRS`, `KIT_HEADER_PREFIX`,
`VERBOSE_OUTPUT`, `active_kits`, `auto_disabled`, `cache_root`, `configured_kits`, `display_path`, `find_kit`, `header_argument_positions`,
`kit_cache`, `kit_explicit_sources`, `kit_locations`, `kit_preamble_kits`, `kit_writes_preamble`, `read_text_best_effort`, `run_probe`,
`which` and `yaml`, pdfmd's own optional import) are read as `core.X` when it runs. `VERBOSE_OUTPUT` is rebound by `main`, so it stays in
`pdfmd.py`; `core.cache_root`, `core.run_probe`, `core.which` and `core.VERBOSE_OUTPUT` are patched by tests as `pdfmd.X`.
`kit_package_folders`, which tests patch as `pdfmd.kit_package_folders`, is called only from `package_helper`, which stays in
`pdfmd.py` and reaches it through the stand-in there.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

core = None


def package_places(folder: Path) -> list[Path]:
    """Where a local LaTeX package keeps what it ships for pdfmd: beside its `.sty`, else in an `office/` or a
    `pdfmd/` folder there."""
    return [folder, folder / "office", folder / "pdfmd"]


def kpsewhich_locate(names: list[str], cwd: str | None = None) -> dict[str, Path]:
    """{name: path} of the files TeX finds, one kpsewhich call for all of them (a missing name is left out). TeX looks in the
    current folder first; `cwd` runs the search from another one."""
    kpsewhich = core.which("kpsewhich")
    if not kpsewhich or not names:
        return {}
    done = core.run_probe([kpsewhich, *names], cwd=cwd)
    found: dict[str, Path] = {}
    for line in (done.stdout if done else "").splitlines():
        if line.strip():
            found.setdefault(Path(line.strip()).name, Path(line.strip()))
    return found


def read_package_helper(folder: Path, package: str) -> tuple[dict, Path] | None:
    """`<package>-pdfmd.yaml` (or a plain `pdfmd.yaml`) in this one folder or its `pdfmd/` folder; (mapping, path) or None."""
    if core.yaml is None:
        return None
    for candidate in (folder / f"{package}-pdfmd.yaml", folder / "pdfmd" / f"{package}-pdfmd.yaml", folder / "pdfmd" / "pdfmd.yaml"):
        if candidate.is_file():
            try:
                data = core.yaml.safe_load(candidate.read_text(encoding="utf-8"))
            except (OSError, core.yaml.YAMLError):
                return None
            return (data, candidate) if isinstance(data, dict) else None
    kit = folder / ".kit"
    if kit.is_file():                  # a kit's own file carries the same blocks, for the package it ships
        try:
            data = core.yaml.safe_load(kit.read_text(encoding="utf-8-sig"))
        except (OSError, core.yaml.YAMLError):
            return None
        if isinstance(data, dict) and str(data.get("package") or "").casefold() == package.casefold():
            return {key: data[key] for key in ("latex-keys", "picture-cache", "draft-skip", "office", "lua") if key in data}, kit
    return None


def kit_package_folders(package: str, document: Path | None = None) -> list[Path]:
    """The folders of the kits chosen for ``document`` that ship `<package>.sty` (the kit names its package)."""
    chosen = [item for item in core.active_kits(document) if item.kit.package]
    if not chosen:
        return []
    from pdfmd_kits import normalise
    return [item.kit.folder for item in chosen if normalise(item.kit.package) == normalise(package)]


def kit_install_record(folder: Path) -> dict | None:
    """What `--install kit` recorded about the kit in ``folder`` (where it came from), or None."""
    from pdfmd_kits.install import read_record
    return read_record(folder)


def kits_report(names: list[str], no_auto: list[str] | None = None) -> bool:
    """`--kits [NAME|PATH ...]`: the kits there are (name, version, modes, where), or each named kit in full."""
    from pdfmd_kits import KitError, list_kits, load_kit
    base = Path.cwd().resolve()
    ok = True
    if names:
        for reference in names:
            try:
                found = core.find_kit(reference, base, no_auto)
                kit = load_kit(found.path, found.aliases)
            except KitError as error:
                print(f"ERROR  {error}", file=sys.stderr)
                ok = False
                continue
            print(f"{kit.name} {kit.version}".rstrip() + (f"  {kit.description}" if kit.description else ""))
            print(f"  kit file  {core.display_path(found.path)}  ({found.source}{', cached' if found.cached else ''})")
            record = kit_install_record(found.folder)
            if record:
                print(f"  from      {record.get('source', '?')}" + (f"@{record['ref']}" if record.get("ref") else "")
                      + (f" {record['commit'][:10]}" if record.get("commit") else "") + f"  (installed {record.get('installed', '?')[:10]})")
            if kit.package:
                print(f"  package   {kit.package}")
            for mode in kit.modes.values():
                names_of = f"{mode.name}" + (f" ({', '.join(mode.aliases)})" if mode.aliases else "")
                print(f"  mode      {names_of}" + ("  [default]" if mode.name == kit.default_mode else "")
                      + (f"  options: {', '.join(mode.options)}" if mode.options else ""))
            for label, value in (("lua", kit.lua), ("defaults", kit.defaults)):
                if value:
                    print(f"  {label:<9} {', '.join(item.name for item in value)}")
            if kit.helper:
                print(f"  helper    {', '.join(kit.helper)}")
            if kit.carry:
                print(f"  carries   {', '.join(kit.carry)}")
            if kit.no_auto:
                print(f"  no-auto   {', '.join(kit.no_auto)}")
            for warning in kit.warnings:
                print(f"WARN  {warning}", file=sys.stderr)
        return ok
    locations = core.kit_locations(base, no_auto)
    cache = core.kit_cache() if not (core.auto_disabled(no_auto, "kit") or core.auto_disabled(no_auto, "kpsewhich")) else None
    rows = list_kits(locations, cache)
    for path, _ in core.configured_kits():
        if not path.is_dir():
            print(f"WARN  kits: {core.display_path(path)} (in the config) is not a folder", file=sys.stderr)
    for found in rows:
        try:
            kit = load_kit(found.path, found.aliases)
        except KitError as error:
            print(f"ERROR  {error.problems[0]}", file=sys.stderr)
            ok = False
            continue
        modes = ", ".join(mode.name + (f" ({', '.join(mode.aliases)})" if mode.aliases else "") for mode in kit.modes.values())
        record = kit_install_record(found.folder)
        origin = (f"\n{'':<26}from: {record.get('source', '?')}" + (f"@{record['ref']}" if record.get("ref") else "")) if record else ""
        print(f"{kit.name} {kit.version}".rstrip().ljust(24) + f"  {core.display_path(found.path)}  ({found.source}{', cached' if found.cached else ''})"
              + (f"\n{'':<26}modes: {modes}" if modes else "") + origin)
        for warning in kit.warnings:
            print(f"WARN  {warning}", file=sys.stderr)
    if not rows:
        print("No kit found. A kit is a folder with a `.kit` file: put it in a kits/ folder beside your documents, or list its "
              "folder under `kits:` in the config file (pdfmd --setup). A named kit that only the TeX tree knows is found "
              "when a document selects it.")
    return ok


def kit_header_insert(cmd: list[str], document: Path | None, metadata_files: list[Path]) -> bool:
    """Step 1: a place for the kit's header file, before every other header file but the code-wrapping one."""
    if not core.kit_writes_preamble(document, metadata_files):
        return False
    positions = [index for index, item in enumerate(cmd[:-1]) if item == "--include-in-header"]
    at = next((index for index in positions if not cmd[index + 1].endswith("code_wrap.tex")), len(cmd))
    cmd[at:at] = ["--include-in-header", str(core.cache_root() / "tex" / (core.KIT_HEADER_PREFIX + "pending.tex"))]
    return True


def kit_header_settle(document: Path, kits: list, places: list[tuple[Path, str, bool]]) -> tuple[str, list[str], list]:
    """(the text of the kits' header file, the text of each of ``places`` = (path, name for messages, explicit) once what a kit
    writes is settled in it, the events). Raises SystemExit where a kit and an explicit source contradict."""
    from pdfmd_kits import preamble
    texts = [core.read_text_best_effort(path) for path, _, _ in places]
    blocks: list[str] = []
    events = []
    for item in kits:
        kit, mode = item.kit, item.mode
        own = tuple(mode.options) if mode else ()
        foreign = frozenset(option for other in kit.modes.values() if other is not mode for option in other.options) - frozenset(own)
        lines = [*kit.latex, *(mode.latex if mode else ())]
        label = f"{kit.name}" + (f" {kit.version}" if kit.version else "") + (f" (mode {mode.name})" if mode else "")
        sources = [preamble.Source(name, text, explicit) for text, (_, name, explicit) in zip(texts, places)]
        try:
            result = preamble.resolve(label, kit.package, own, foreign, preamble.kit_inputs(lines), sources)
        except preamble.PreambleClash as error:
            raise SystemExit(f"{document.name}: {error}")
        texts = result.texts
        events += result.events
        blocks.append("\n".join([f"% pdfmd: kit {label}; written by pdfmd, edit the kit, not this file",
                                *([preamble.package_line(kit.package, result.options)] if kit.package else []), *lines]))
    return "\n".join(blocks) + "\n", texts, events


def kit_cache_tex(prefix: str, text: str, digits: int) -> Path:
    """``text`` as a file of the cache folder named ``prefix`` and its content's hash (written once); SystemExit when the folder
    cannot be written."""
    path = core.cache_root() / "tex" / f"{prefix}{hashlib.sha1(text.encode('utf-8')).hexdigest()[:digits]}.tex"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            path.write_text(text, encoding="utf-8")
    except OSError as error:
        raise SystemExit(f"cannot write the kit's preamble to {path} ({error.strerror or error})")
    return path


def kit_header_resolve(cmd: list[str], document: Path, metadata_files: list[Path], pandoc_options: list[str]) -> None:
    """Step 2: read the other header files, settle what they say twice with the kits' lines, write the kits' header file."""
    kits = core.kit_preamble_kits(document, metadata_files)
    pending = next((index for index, item in enumerate(cmd[:-1]) if item == "--include-in-header"
                    and Path(cmd[index + 1]).name == core.KIT_HEADER_PREFIX + "pending.tex"), None)
    if pending is None:
        return
    found = []                                           # (index, is the `=` form, path)
    for index, equals in core.header_argument_positions(cmd):
        raw = cmd[index].split("=", 1)[1] if equals else cmd[index]
        path = Path(raw)
        if not (path.name.startswith(core.KIT_HEADER_PREFIX) or path.name == "code_wrap.tex" or not path.is_file()):
            found.append((index, equals, path))
    explicit = core.kit_explicit_sources(document, [path for _, _, path in found], pandoc_options)
    places = [(path, core.display_path(path), flag) for (_, _, path), flag in zip(found, explicit)]
    body, texts, events = kit_header_settle(document, kits, places)
    for event in events:
        if event.warn:
            print(f"WARN  {event.id}  {event.message}", file=sys.stderr)
        elif core.VERBOSE_OUTPUT:
            print(f"AUTO {event.id}  {event.message}")
    for (index, equals, path), text in zip(found, texts):
        if text != core.read_text_best_effort(path):
            copy = kit_cache_tex(f"kit-{path.stem}-", text, 12)
            cmd[index] = f"--include-in-header={copy}" if equals else str(copy)
    cmd[pending + 1] = str(kit_cache_tex(core.KIT_HEADER_PREFIX, body, 16))


def kit_carried_files(kits: list, base: Path, limit: float) -> tuple[dict[str, Path], list[dict], list[str]]:
    """The files the chosen ``kits`` take along (their `carry:` lists) as {name beside the document: path}, the manifest's record
    of each kit ({name, version, mode, package, carried}) and the notes to print. A named file keeps its path from the kit's
    folder; a named folder is carried by its files, which land beside the document (TeX and Pandoc look there first: a package
    that finds its logo by a bare name finds it again). A name the document's folder already holds is left to the folder."""
    files: dict[str, Path] = {}
    record: list[dict] = []
    notes: list[str] = []
    for item in kits:
        kit = item.kit
        mine: dict[str, Path] = {}
        for entry in kit.carry:
            target = kit.folder / entry.rstrip("/")
            if target.is_dir():
                found = sorted(path for path in target.rglob("*") if path.is_file()
                               and not any(part.startswith(".") or part in core.BUNDLE_SKIP_DIRS
                                           for part in path.relative_to(target).parts))
                pairs = [(path.name, path) for path in found]
            elif target.is_file():
                pairs = [(entry, target)]
            else:
                notes.append(f"NOTE  kit {kit.name}: `carry: {entry}` names nothing in {core.display_path(kit.folder)}; not carried")
                continue
            for name, path in pairs:
                if name in mine:
                    notes.append(f"NOTE  kit {kit.name}: {name} is named twice in `carry:`; the first is carried")
                elif name in files:
                    notes.append(f"NOTE  kit {kit.name}: {name} is also carried by another kit; the first is kept")
                elif not (base / name).exists():
                    mine[name] = path
        size = sum(path.stat().st_size for path in mine.values())
        if size > limit:
            notes.append(f"WARN  kit {kit.name}: its {len(mine)} carried files are {size / 1048576:.0f} MB, over the "
                         f"{limit / 1048576:.0f} MB limit (pdfmd-options.bundle-max-mb); not carried")
            mine = {}
        files.update(mine)
        record.append({"name": kit.name, "version": kit.version or None, "mode": item.mode.name if item.mode else None,
                       "package": kit.package or None, "carried": sorted(mine)})
    return files, record, notes
