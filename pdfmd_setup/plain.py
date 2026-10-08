"""`pdfmd --setup`, as a numbered list: no dependency, works over ssh and in any terminal."""

from __future__ import annotations

from typing import Callable

from .registry import Setting, from_stored, read, shown, to_stored, write


def run(stores: dict, settings: list[Setting], path: str, read_line: Callable[[str], str] = input,
        say: Callable[[str], None] = print, nudge: str = "") -> bool:
    """Edit `stores` ({"config": {...}, "metadata": {...}}) in place; True when the user chose to save."""
    changed = False
    say(f"pdfmd setup  --  {path}")
    if nudge:
        say(nudge)
    while True:
        say("")
        section = None
        for number, setting in enumerate(settings, start=1):
            if setting.section != section:
                section = setting.section
                say(section)
            say(f"  {number:>2}. {setting.title:<44} {shown(setting, read(stores, setting))}")
        say("")
        try:
            answer = read_line("Number to change, s = save and quit, q = quit without saving: ").strip().lower()
        except EOFError:
            return False
        if answer in ("s", "save"):
            return True
        if answer in ("q", "quit", ""):
            if answer == "" or not changed:
                return False
            try:
                if read_line("Discard your changes? [y/N] ").strip().lower() not in ("y", "yes"):
                    continue
            except EOFError:
                pass
            return False
        if not answer.isdigit() or not 1 <= int(answer) <= len(settings):
            say("Not a number from the list.")
            continue
        if edit(stores, settings[int(answer) - 1], read_line, say):
            changed = True


def edit(stores: dict, setting: Setting, read_line: Callable[[str], str], say: Callable[[str], None]) -> bool:
    current = read(stores, setting)
    say("")
    say(setting.title + (" -- " + setting.help if setting.help else ""))
    if setting.kind == "text":
        say(f"  now: {shown(setting, current)}")
        try:
            answer = read_line("New value (Enter = leave as it is, - = back to the default): ").strip()
        except EOFError:
            return False
        if not answer:
            return False
        if answer == "-":
            write(stores, setting, None)
            return current is not None
        if setting.check == "number":
            try:
                value = float(answer)
            except ValueError:
                say("A number, please.")
                return False
            answer = int(value) if value == int(value) else value
        write(stores, setting, answer)
        return answer != current
    if setting.kind == "multi":
        chosen = set(str(item) for item in current) if isinstance(current, list) else set()
        for number, (value, meaning) in enumerate(setting.choices, start=1):
            say(f"  {number:>2}. [{'x' if value in chosen else ' '}] {value:<14} {meaning}")
        try:
            answer = read_line("Numbers to toggle (1 3 5), a = all, n = none, Enter = leave as it is: ").strip().lower()
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
        write(stores, setting, new)
        return new != current
    now = from_stored(setting, current)
    for number, (value, meaning) in enumerate(setting.choices, start=1):
        mark = "*" if value == now else " "
        say(f"  {number:>2}. {mark} {value:<14} {meaning}")
    default = f"the default ({setting.default})" if setting.default else "not set"
    say(f"   0.   back to {default}")
    try:
        answer = read_line("Choose a number, Enter = leave as it is: ").strip()
    except EOFError:
        return False
    if not answer.isdigit():
        return False
    number = int(answer)
    if number == 0:
        write(stores, setting, None)
        return current is not None
    if 1 <= number <= len(setting.choices):
        new = to_stored(setting, setting.choices[number - 1][0])
        write(stores, setting, new)
        return new != current
    return False
