"""`pdfmd --setup`, as a numbered list: no dependency, works over ssh and in any terminal."""

from __future__ import annotations

from typing import Callable

from .registry import Setting, from_stored, get, put, shown, to_stored


def run(config: dict, settings: list[Setting], path: str, read: Callable[[str], str] = input,
        write: Callable[[str], None] = print, nudge: str = "") -> bool:
    """Edit `config` in place; True when the user chose to save."""
    changed = False
    write(f"pdfmd setup  --  {path}")
    if nudge:
        write(nudge)
    while True:
        write("")
        section = None
        for number, setting in enumerate(settings, start=1):
            if setting.section != section:
                section = setting.section
                write(section)
            write(f"  {number:>2}. {setting.title:<44} {shown(setting, get(config, setting.key))}")
        write("")
        try:
            answer = read("Number to change, s = save and quit, q = quit without saving: ").strip().lower()
        except EOFError:
            return False
        if answer in ("s", "save"):
            return True
        if answer in ("q", "quit", ""):
            if answer == "" or not changed:
                return False
            try:
                if read("Discard your changes? [y/N] ").strip().lower() not in ("y", "yes"):
                    continue
            except EOFError:
                pass
            return False
        if not answer.isdigit() or not 1 <= int(answer) <= len(settings):
            write("Not a number from the list.")
            continue
        setting = settings[int(answer) - 1]
        if edit(config, setting, read, write):
            changed = True


def edit(config: dict, setting: Setting, read: Callable[[str], str], write: Callable[[str], None]) -> bool:
    current = get(config, setting.key)
    write("")
    write(setting.title + (" -- " + setting.help if setting.help else ""))
    if setting.kind == "multi":
        chosen = set(str(item) for item in current) if isinstance(current, list) else set()
        for number, (value, meaning) in enumerate(setting.choices, start=1):
            write(f"  {number:>2}. [{'x' if value in chosen else ' '}] {value:<14} {meaning}")
        try:
            answer = read("Numbers to toggle (1 3 5), a = all, n = none, Enter = leave as it is: ").strip().lower()
        except EOFError:
            return False
        if not answer:
            return False
        if answer == "a":
            chosen = {value for value, _ in setting.choices}
        elif answer == "n":
            chosen = set()
        else:
            for part in answer.replace(",", " ").split():
                if part.isdigit() and 1 <= int(part) <= len(setting.choices):
                    chosen ^= {setting.choices[int(part) - 1][0]}
        new = [value for value, _ in setting.choices if value in chosen] or None
        put(config, setting.key, new)
        return new != current
    now = from_stored(setting, current)
    for number, (value, meaning) in enumerate(setting.choices, start=1):
        mark = "*" if value == now else " "
        write(f"  {number:>2}. {mark} {value:<14} {meaning}")
    default = f"the default ({setting.default})" if setting.default else "not set"
    write(f"   0.   back to {default}")
    try:
        answer = read("Choose a number, Enter = leave as it is: ").strip()
    except EOFError:
        return False
    if not answer.isdigit():
        return False
    number = int(answer)
    if number == 0:
        put(config, setting.key, None)
        return current is not None
    if 1 <= number <= len(setting.choices):
        new = to_stored(setting, setting.choices[number - 1][0])
        put(config, setting.key, new)
        return new != current
    return False
