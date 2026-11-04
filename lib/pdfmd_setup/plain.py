"""`pdfmd --setup`, as a numbered list: no dependency, works over ssh and in any terminal."""

from __future__ import annotations

from typing import Callable

from .registry import Setting, from_stored, read, to_stored, write
from .registry import shown as shown_value


def run(stores: dict, settings: list[Setting], path: str, read_line: Callable[[str], str] = input,
        say: Callable[[str], None] = print, nudge: str = "", left_out: list[str] | None = None,
        hidden: Callable[[Setting], bool] = lambda setting: False,
        inherited: Callable[[Setting], tuple | None] | None = None,
        actions: dict[str, Callable[[Callable[[str], None], Callable[[str], str]], None]] | None = None) -> bool:
    """Edit `stores` ({"config": {...}, "metadata": {...}}) in place; True when the user chose to save. `left_out` is
    what `o` prints: the flags and keys that are not settable here, and why (pdfmd_setup.inventory). `actions` maps the key of
    an "action" row to what it does (it gets `say` and `read_line`); an action row without one is not shown."""
    actions = actions or {}
    changed = False
    say(f"pdfmd setup  --  {path}")
    if inherited is not None:
        say("A value not set here is shown with the setup it comes from, or as the default.")
    if nudge:
        say(nudge)
    switch = next((setting for setting in settings if setting.key == "disabled"), None)
    while True:
        say("")
        section = None
        usable = [setting for setting in settings if setting.kind != "action" or setting.key in actions]
        shown = [setting for setting in usable if not hidden(setting)]
        for number, setting in enumerate(shown, start=1):
            if setting.section != section:
                section = setting.section
                say(section)
            value = read(stores, setting)
            above = inherited(setting) if value is None and inherited is not None else None
            say(f"  {number:>2}. {setting.title:<44} "
                + ("(choose it to use it)" if setting.kind == "action" else
                   f"{shown_value(setting, above[0])}  ({above[1]})" if above else shown_value(setting, value)))
        if len(shown) < len(usable):
            say(f"  ({len(usable) - len(shown)} rows of switched-off features are hidden: d)")
        say("")
        try:
            answer = read_line("Number to change, d = features switched off, o = what is not here and why, "
                               "s = save and quit, q = quit without saving: ").strip().lower()
        except EOFError:
            return False
        if answer in ("s", "save"):
            return True
        if answer == "d" and switch is not None:
            if edit(stores, switch, read_line, say):
                changed = True
            continue
        if answer == "o":
            say("")
            say("Not settable here, on purpose:")
            for line in left_out or ["  (nothing)"]:
                say(line)
            continue
        if answer in ("q", "quit", ""):
            if answer == "" or not changed:
                return False
            try:
                if read_line("Discard your changes? [y/N] ").strip().lower() not in ("y", "yes"):
                    continue
            except EOFError:
                pass
            return False
        if not answer.isdigit() or not 1 <= int(answer) <= len(shown):
            say("Not a number from the list.")
            continue
        if edit(stores, shown[int(answer) - 1], read_line, say, actions):
            changed = True


def edit(stores: dict, setting: Setting, read_line: Callable[[str], str], say: Callable[[str], None],
         actions: dict | None = None) -> bool:
    say("")
    say(setting.title + (" -- " + setting.help if setting.help else ""))
    if setting.kind == "action":                       # it does its work now and stores nothing
        (actions or {})[setting.key](say, read_line)
        return False
    current = read(stores, setting)
    if setting.kind == "text":
        say(f"  now: {shown_value(setting, current)}")
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
        elif setting.check == "list":
            answer = [item.strip() for item in answer.split(",") if item.strip()]
        elif setting.check == "count":
            if answer.strip().lower() == "all":
                answer = "all"
            elif answer.strip().isdigit() and int(answer) > 0:
                answer = int(answer)
            else:
                say("A whole number, or all, please.")
                return False
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
    what = setting.unset or setting.default
    default = f"the default ({what})" if what else "none"
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
