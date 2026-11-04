"""`pdfmd --user-path add|remove|show` (spelled out: --add-to-path, --remove-from-path, --show-user-path): put folders on the
Windows USER PATH, and take off exactly what pdfmd put there.

Opt-in only: nothing in pdfmd calls this by itself. It reads and writes `Path` under HKEY_CURRENT_USER\\Environment (no
administrator rights), keeps the value's registry type (REG_EXPAND_SZ stays REG_EXPAND_SZ; `setx` would cut the value at 1024
characters and turn it into REG_SZ), copies every other entry byte for byte and appends the new ones at the end, so they never
shadow a program the machine PATH has. Every change is listed and asked for first; `--dry-run` writes nothing. What was added is
recorded in `path-added.json` in pdfmd's settings folder (pdfmd's own state, not a setting), and `remove` takes off exactly those
entries.

All the logic works on a backend of four methods (Registry below is the real one), so a test needs no registry.
"""

from __future__ import annotations

import json
import ntpath
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

REG_SZ, REG_EXPAND_SZ = 1, 2
VERBS = ("add", "remove", "show")
RECORD_NAME = "path-added.json"
PROGRAM_SUFFIXES = (".exe", ".cmd", ".bat", ".com")
ENVIRONMENT = "Environment"
MACHINE_ENVIRONMENT = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


class Registry:
    """The user PATH in the Windows registry. ``PDFMD_USER_ENV_KEY`` names another key under HKEY_CURRENT_USER for a test (and
    switches the broadcast off); users never set it."""

    def __init__(self, subkey: str | None = None):
        self.subkey = subkey or os.environ.get("PDFMD_USER_ENV_KEY") or ENVIRONMENT

    def read(self) -> tuple[str, int] | None:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.subkey, 0, winreg.KEY_READ) as key:
                value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return None
        return str(value), kind

    def write(self, value: str, kind: int) -> None:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.subkey, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Path", 0, kind, value)

    def machine(self) -> str:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, MACHINE_ENVIRONMENT, 0, winreg.KEY_READ) as key:
                return str(winreg.QueryValueEx(key, "Path")[0])
        except OSError:
            return ""

    def broadcast(self) -> None:
        """Tell the running programs (Explorer, new terminals) that the environment changed."""
        if self.subkey != ENVIRONMENT:
            return
        try:
            import ctypes
            result = ctypes.c_ulong()
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 2, 5000, ctypes.byref(result))
        except (OSError, AttributeError):
            pass


def same_entry(entry: str) -> str:
    """An entry as it is compared: without quotes, %VARIABLES% expanded, case, slashes and a trailing backslash ignored."""
    text = ntpath.expandvars(entry.strip().strip('"'))
    return ntpath.normcase(ntpath.normpath(text)).rstrip("\\") if text else ""


def entries_of(value: str) -> list[str]:
    return [entry for entry in value.split(";") if entry.strip()]


def check_folder(text: str, exists: Callable[[str], bool] = os.path.isdir) -> tuple[str | None, str]:
    """(the folder as an absolute path, a note) or (None, why it is refused). A folder with no program in it is allowed with a note."""
    text = text.strip().strip('"')
    if not text:
        return None, "no folder given"
    if ";" in text or '"' in text:
        return None, "a folder name with ; or \" in it cannot be put on PATH"
    folder = os.path.abspath(os.path.expandvars(os.path.expanduser(text)))
    if not exists(folder):
        return None, "is not a folder"
    try:
        has_program = any(name.lower().endswith(PROGRAM_SUFFIXES) for name in os.listdir(folder))
    except OSError:
        has_program = True
    return folder, "" if has_program else "it holds no .exe, .cmd, .bat or .com file"


@dataclass
class Change:
    add: list[tuple[str, str, str]] = field(default_factory=list)      # (folder, why, note)
    skip: list[tuple[str, str]] = field(default_factory=list)          # (folder as given, reason)
    before: str = ""
    after: str = ""
    kind: int = REG_EXPAND_SZ


def plan_add(current: tuple[str, int] | None, machine: str, wanted: list[tuple[str, str]],
             exists: Callable[[str], bool] = os.path.isdir) -> Change:
    """What adding ``wanted`` ((folder, why) pairs) to the user PATH ``current`` would do."""
    value, kind = current if current else ("", REG_EXPAND_SZ)
    change = Change(before=value, kind=kind)
    in_user = {same_entry(entry) for entry in entries_of(value)}
    in_machine = {same_entry(entry) for entry in entries_of(machine)}
    for given, why in wanted:
        folder, note = check_folder(given, exists)
        if folder is None:
            change.skip.append((given, note))
            continue
        name = same_entry(folder)
        if name in in_user:
            change.skip.append((folder, "already on your user PATH"))
        elif name in in_machine:
            change.skip.append((folder, "already on the machine PATH"))
        else:
            in_user.add(name)
            change.add.append((folder, why, note))
    if change.add:
        base = value if not value or value.endswith(";") else value + ";"
        change.after = base + ";".join(folder for folder, _, _ in change.add)
    else:
        change.after = value
    return change


def load_record(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [item for item in data.get("added", []) if isinstance(item, dict) and isinstance(item.get("folder"), str)]
    except (OSError, ValueError, AttributeError):
        return []


def save_record(path: Path, added: list[dict]) -> None:
    if not added:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump({"version": 1, "added": added}, stream, indent=2)
            stream.write("\n")
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def run(verb: str, folders: list[str], *, backend, record: Path, found: Callable[[], list[tuple[str, str]]],
        dry_run: bool = False, yes: bool = False, say: Callable[[str], None] = print,
        ask: Callable[[str], str] = input, interactive: bool = True, version: str = "",
        now: Callable[[], datetime] = datetime.now, exists: Callable[[str], bool] = os.path.isdir) -> int:
    """Do ``verb`` (add, remove or show); the exit code. ``found()`` lists (folder, why) pairs for an `add` without folders."""
    if verb == "show":
        return show(backend, record, say)
    if verb == "remove":
        return remove(backend, record, dry_run, yes, say, ask, interactive)
    if verb != "add":
        say(f"--user-path takes {', '.join(VERBS)}, not {verb!r}.")
        return 2
    wanted = [(folder, "named by you") for folder in folders] or found()
    if not wanted:
        say("No tool that pdfmd found is off your PATH. To add a folder you name: pdfmd --user-path add FOLDER")
        return 0
    change = plan_add(backend.read(), backend.machine(), wanted, exists)
    for folder, why, note in change.add:
        say(f"  add   {folder}   ({why})" + (f"  -- {note}" if note else ""))
    for folder, reason in change.skip:
        say(f"  skip  {folder}   ({reason})")
    if not change.add:
        say("Nothing to add.")
        return 0
    say(f"Your user PATH gets {len(change.add)} more {'entry' if len(change.add) == 1 else 'entries'}, at its end.")
    if dry_run:
        say("--dry-run: nothing was changed.")
        return 0
    if not confirm(f"Add {'it' if len(change.add) == 1 else 'them'} to your user PATH? [y/N] ", yes, say, ask, interactive):
        return 1
    try:
        backend.write(change.after, change.kind)
    except OSError as error:
        say(f"ERROR  the user PATH could not be written: {error}")
        return 1
    added = load_record(record)
    stamp = now().isoformat(timespec="seconds")
    added += [{"folder": folder, "when": stamp, "pdfmd": version, "why": why} for folder, why, _ in change.add]
    try:
        save_record(record, added)
    except OSError as error:
        say(f"WARN  the list of what pdfmd added could not be saved ({error}); --user-path remove will not know these folders")
    backend.broadcast()
    say("Done. New terminals see it; this one does not. To refresh this PowerShell window:")
    say("  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')")
    say("To take these folders off again: pdfmd --user-path remove")
    return 0


def confirm(question: str, yes: bool, say: Callable[[str], None], ask: Callable[[str], str], interactive: bool) -> bool:
    if yes:
        return True
    if not interactive:
        say("Not asked (no terminal, or PDFMD_NO_PROMPT is set): add --yes to go ahead.")
        return False
    try:
        answer = ask(question).strip().lower()
    except EOFError:
        answer = ""
    if answer not in ("y", "yes"):
        say("Nothing changed.")
        return False
    return True


def remove(backend, record: Path, dry_run: bool, yes: bool, say, ask, interactive: bool) -> int:
    added = load_record(record)
    if not added:
        say("pdfmd has added nothing to your user PATH.")
        return 0
    current = backend.read()
    value, kind = current if current else ("", REG_EXPAND_SZ)
    entries = value.split(";")
    gone, taken = [], []
    for item in added:
        folder = item["folder"]
        if folder in entries:
            entries.remove(folder)
            taken.append(folder)
        else:
            gone.append(folder)
    for folder in taken:
        say(f"  remove  {folder}")
    for folder in gone:
        say(f"  gone    {folder}   (no longer on your user PATH; dropped from the list)")
    if dry_run:
        say("--dry-run: nothing was changed.")
        return 0
    if taken and not confirm(f"Take {'it' if len(taken) == 1 else 'them'} off your user PATH? [y/N] ", yes, say, ask, interactive):
        return 1
    if taken:
        try:
            backend.write(";".join(entries), kind)
        except OSError as error:
            say(f"ERROR  the user PATH could not be written: {error}")
            return 1
    try:
        save_record(record, [])
    except OSError as error:
        say(f"WARN  the list of what pdfmd added could not be cleared ({error})")
    if taken:
        backend.broadcast()
        say("Done. New terminals no longer see them.")
    return 0


def show(backend, record: Path, say) -> int:
    added = {item["folder"]: item for item in load_record(record)}
    current = backend.read()
    if current is None:
        say("Your user PATH is not set.")
        return 0
    value, kind = current
    say(f"Your user PATH ({'REG_EXPAND_SZ' if kind == REG_EXPAND_SZ else 'REG_SZ'}):")
    seen = set()
    for number, entry in enumerate(entries_of(value), start=1):
        item = added.get(entry)
        seen.add(entry)
        say(f"  {number:>2}. {entry}" + (f"   <- added by pdfmd, {item.get('when', '')}" if item else ""))
    for folder in added:
        if folder not in seen:
            say(f"      (recorded as added by pdfmd, no longer on your user PATH: {folder})")
    return 0


def menu(say, read_line, **context) -> None:
    """The `--setup` row: the same three commands, chosen by number. ``context`` is what ``run`` takes besides the verb."""
    say("  1. add the folders of the tools pdfmd found off your PATH")
    say("  2. add a folder you name")
    say("  3. show your user PATH")
    say("  4. take off what pdfmd added")
    try:
        answer = read_line("Choose a number, Enter = back: ").strip()
        if answer == "1":
            run("add", [], say=say, ask=read_line, interactive=True, **context)
        elif answer == "2":
            folder = read_line("Folder: ").strip()
            if folder:
                run("add", [folder], say=say, ask=read_line, interactive=True, **context)
        elif answer == "3":
            run("show", [], say=say, ask=read_line, interactive=True, **context)
        elif answer == "4":
            run("remove", [], say=say, ask=read_line, interactive=True, **context)
    except EOFError:
        return
