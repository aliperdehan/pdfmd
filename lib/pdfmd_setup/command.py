"""`pdfmd --setup` and `pdfmd --user-path` as pdfmd runs them: the command itself (plain, fancy, a folder's own settings, a preset), the
rows that run something instead of storing a value, the one-time hint that `--setup` exists, the flag names and topics the screens
need from the argument parser, and the headers of the files it writes.

Moved out of `pdfmd.py` unchanged (v3.33.21, SPLIT.md), with `FOLDER_HEADER`, `FOLDER_METADATA_HEADER` and `METADATA_HEADER`. `core` is the
`pdfmd` module, bound when the module is first loaded (a stand-in in `pdfmd.py` loads it on the first call; the first binding wins);
the pdfmd names the code uses (`FOLDER_DIR`, `NO_AUTO_KINDS`, `PDFMD_VERSION`, `PRESET_CLI`, `PRESET_DEFAULT`, `PRESET_OFF`,
`SETUP_HEADER`, `atomic_write_text`, `build_parser`, `config_path`, `config_root`, `display_path`, `folder_walk`,
`global_metadata_file`, `load_config`, `metadata_file_yaml`, `setup_module`, `tool_folders_off_path` and `yaml`, pdfmd's own optional
import) are read as `core.X` when it runs; `PRESET_CLI` is rebound by `main`, so it stays in `pdfmd.py`, and `core.config_root` is
patched by tests as `pdfmd.config_root`.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from pdfmd_base import core


def user_path_command(args) -> int:
    """`--user-path add|remove|show [FOLDER...]`, and its spelled-out forms --add-to-path, --remove-from-path, --show-user-path."""
    from pdfmd_setup import userpath
    if args.user_path:
        verb, folders = args.user_path[0].lower(), list(args.user_path[1:])
    elif args.add_to_path is not None:
        verb, folders = "add", list(args.add_to_path)
    else:
        verb, folders = ("remove" if args.remove_from_path else "show"), []
    if verb not in userpath.VERBS:
        print(f"--user-path takes {', '.join(userpath.VERBS)}, not {verb!r}.", file=sys.stderr)
        return 2
    if verb != "add" and folders:
        print(f"--user-path {verb} takes no folder.", file=sys.stderr)
        return 2
    if sys.platform != "win32":
        print("--user-path changes the Windows user PATH. On macOS and Linux put the folder on PATH in your shell's profile:\n"
              '  export PATH="FOLDER:$PATH"', file=sys.stderr)
        return 1
    return userpath.run(verb, folders, backend=userpath.Registry(), record=core.config_root() / userpath.RECORD_NAME,
                        found=core.tool_folders_off_path, dry_run=args.dry_run, yes=args.yes, version=core.PDFMD_VERSION,
                        interactive=sys.stdin.isatty() and not os.environ.get("PDFMD_NO_PROMPT"))


def setup_actions() -> dict:
    """The `--setup` rows that run something instead of storing a value (the Windows user PATH), by row key."""
    if sys.platform != "win32":
        return {}
    from pdfmd_setup import userpath
    context = dict(backend=userpath.Registry(), record=core.config_root() / userpath.RECORD_NAME, found=core.tool_folders_off_path,
                   version=core.PDFMD_VERSION)
    return {"user-path": lambda say, read_line: userpath.menu(say, read_line, **context)}


def setup_hint_state() -> Path:
    return core.config_root() / "setup-hint-shown"


def maybe_hint_setup() -> None:
    """Once, at the end of a build in an interactive terminal, when there is no config file yet: say that
    `pdfmd --setup` exists. Never in a pipe, in CI, from the Python API, or with PDFMD_NO_PROMPT set."""
    path = core.config_path()
    if (path is None or path.exists() or os.environ.get("PDFMD_NO_PROMPT") or not sys.stdin.isatty()
            or not sys.stdout.isatty() or setup_hint_state().exists()):
        return
    print("TIP   `pdfmd --setup` changes pdfmd's defaults for every document (fonts, engine, what it does by itself)")
    try:
        setup_hint_state().parent.mkdir(parents=True, exist_ok=True)
        setup_hint_state().write_text("shown\n", encoding="utf-8")
    except OSError:
        pass


def flag_topics() -> dict[str, set[str]]:
    """The features (pdfmd_help topics) of each flag, by its argparse dest: for --setup to hide switched-off rows."""
    try:
        from pdfmd_help import topics_of
    except ImportError:
        return {}
    found: dict[str, set[str]] = {}
    for action in core.build_parser()._actions:
        found.setdefault(action.dest, set()).update(topics_of(action))
    return found


def flag_names() -> dict[str, str]:
    """How each command-line flag is written, by its argparse dest (the first long form), for `--setup`'s list of what
    it leaves out (pdfmd_setup.inventory)."""
    names: dict[str, str] = {}
    for action in core.build_parser()._actions:
        if action.option_strings:
            long = [item for item in action.option_strings if item.startswith("--")]
            names.setdefault(action.dest, (long or action.option_strings)[0])
        else:
            names.setdefault(action.dest, action.dest.upper())
    return names


FOLDER_HEADER = ("# pdfmd's settings for this folder and every folder under it, written by `pdfmd --setup FOLDER` (edit it by hand, or\n"
                 "# run that again). Precedence: command line > the document's `pdfmd-options:` > its metadata files > the folders'\n"
                 "# files, the nearest first > the global setup. `inherit: false` stops the folders above from being read.\n")
FOLDER_METADATA_HEADER = ("# pdfmd's metadata for this folder and every folder under it, written by `pdfmd --setup FOLDER`: below anything\n"
                          "# a document's own front matter and its metadata files say, above the global metadata.\n")


METADATA_HEADER = ("# pdfmd's global metadata, written by `pdfmd --setup`: every document gets these, below anything its own\n"
                   "# front matter and its folder's metadata files say.\n")


def setup_sources(module, folder: Path, stores: dict):
    """For `pdfmd --setup FOLDER`: a function that says, for a row the folder has no value for, the value and the setup it comes
    from: the folders above (the nearest first) and then the global config, as a build layers them."""
    registry = module.registry

    def layers() -> list[tuple[str, dict]]:
        found: list[tuple[str, dict]] = []
        config = stores.get("config") or {}
        if str(config.get("inherit", True)).strip().casefold() not in ("false", "no", "off", "0"):
            for directory, data, metadata in core.folder_walk(str(folder.resolve().parent)):
                label = f"folder {core.display_path(directory.parent)}"
                found.append((label, {"config": data or {}, "metadata": core.metadata_file_yaml(metadata) if metadata else {}}))
        glob = {"config": core.load_config(), "metadata": {}}
        metadata = core.global_metadata_file()
        if metadata is not None:
            glob["metadata"] = core.metadata_file_yaml(metadata)
        found.append(("global", glob))
        return found

    def inherited(setting):
        for label, above in layers():
            value = registry.read(above, setting)
            if value is not None:
                return value, label
        return None
    return inherited


def setup_command(screen: str = "") -> bool:
    """`--setup [plain|fancy|FOLDER]`: change the global defaults, or a folder's, without editing the config file by hand."""
    module = core.setup_module()
    if module is None:
        print("pdfmd --setup is missing from this install (pdfmd_setup).", file=sys.stderr)
        return False
    folder = None
    if screen not in ("", "plain", "fancy"):
        folder = Path(screen).expanduser()
        if not folder.is_dir():
            print(f"--setup takes plain, fancy or a folder (for that folder's own settings), not {screen!r}.", file=sys.stderr)
            return False
        if core.PRESET_CLI is not None:
            print("--setup --preset is for the global setup: a folder's setup has no presets.", file=sys.stderr)
            return False
        screen = ""
        path = folder.resolve() / core.FOLDER_DIR / "config.yaml"
    else:
        path = core.config_path()
    if path is None:
        print("The config file is switched off (PDFMD_CONFIG is empty).")
        return False
    if core.yaml is None:
        print("pdfmd --setup needs PyYAML (pip install pyyaml).", file=sys.stderr)
        return False
    import copy
    metadata_path = path.with_name("metadata.yaml")
    if core.PRESET_CLI is not None:
        name = re.sub(r"\.ya?ml$", "", core.PRESET_CLI.strip())
        if not name or name.casefold() in core.PRESET_OFF or re.search(r"[/\\]", name) or name.startswith("~"):
            print(f"--setup --preset takes the name of a preset (lab, or lab.yaml), or default, not {core.PRESET_CLI!r}.",
                  file=sys.stderr)
            return False
        if name.casefold() not in core.PRESET_DEFAULT:
            metadata_path = path.with_name("presets") / f"{name}.yaml"
    files = {"config": path, "metadata": metadata_path}
    stores: dict = {}
    texts: dict = {}
    for name, file in files.items():
        stores[name], texts[name] = {}, ""
        if file.is_file():
            try:
                texts[name] = file.read_text(encoding="utf-8-sig")
                loaded = core.yaml.safe_load(texts[name])
            except (OSError, UnicodeDecodeError, core.yaml.YAMLError) as error:
                print(f"{file} cannot be read ({error}); fix or move it first.", file=sys.stderr)
                return False
            stores[name] = loaded if isinstance(loaded, dict) else {}
    original = copy.deepcopy(stores)
    shown_path = str(path) if metadata_path.name == "metadata.yaml" else f"{path}  (global metadata rows: {metadata_path.parent.name}/{metadata_path.name})"
    if folder is not None:
        shown_path = f"the settings of {core.display_path(folder.resolve())} and every folder under it  ({core.display_path(path)})"
    saved = module.run(stores, core.NO_AUTO_KINDS, shown_path, screen or None, flag_names=flag_names(),
                       flag_topics=flag_topics(), folder=folder is not None,
                       inherited=setup_sources(module, folder, stores) if folder is not None else None,
                       actions=setup_actions())
    if not saved:
        print("Nothing saved.")
        return True
    if stores == original:
        print("Nothing changed.")
        return True
    for name, file in files.items():
        if stores[name] == original[name]:
            continue
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            header = ((FOLDER_HEADER if name == "config" else FOLDER_METADATA_HEADER) if folder is not None
                      else core.SETUP_HEADER if name == "config" else METADATA_HEADER)
            hand_written = [line for line in texts[name].splitlines() if line.lstrip().startswith("#")
                            and line not in header.splitlines()]       # (v3.29.29: the header's second line counted, a .bak every save)
            if hand_written:
                backup = file.with_name(file.name + ".bak")
                core.atomic_write_text(backup, texts[name])
                print(f"NOTE  your comments are not kept in the rewritten file; the old one is {backup.name}")
            if stores[name]:
                core.atomic_write_text(file, header + core.yaml.safe_dump(stores[name], sort_keys=False, allow_unicode=True,
                                                                default_flow_style=False))
            elif file.exists():
                file.unlink()
                if folder is not None:
                    try:
                        file.parent.rmdir()              # the folder's own .pdfmd, when nothing else is in it
                    except OSError:
                        pass
        except OSError as error:
            print(f"Could not write {file}: {error}", file=sys.stderr)
            return False
        print(f"{'Removed' if not stores[name] else 'Saved'} {file}")
    core.load_config.cache_clear()
    core.folder_walk.cache_clear()
    return True
