"""`pdfmd --setup`, full screen (needs prompt_toolkit: `pdfmd --install tui`)."""

from __future__ import annotations

from .registry import Setting, from_stored, read, shown, to_stored, write


def available() -> bool:
    try:
        import prompt_toolkit  # noqa: F401
    except ImportError:
        return False
    return True


def run(stores: dict, settings: list[Setting], path: str, input=None, output=None, ask=None,
        left_out: list[str] | None = None, hidden=lambda setting: False) -> bool:
    """Edit `stores` ({"config": ..., "metadata": ...}) in place; True when the user chose to save. `input`/`output`
    let a test drive it; `ask(title, now)` answers a text setting (default: a prompt on the real terminal); `o` shows
    `left_out`, the flags and keys that are not settable here; `hidden(setting)` leaves the rows of switched-off
    features out, and `d` opens the "Features switched off" row (v3.27.8; `r` resets a row, which `d` used to)."""
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.data_structures import Point
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.layout import HSplit, Layout, ScrollOffsets, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    state = {"row": 0, "sub": None, "subrow": 0, "dirty": False, "message": "", "line": 0, "left_out": False}
    switch = next((setting for setting in settings if setting.key == "disabled"), None)

    def rows() -> list[Setting]:
        shown = [setting for setting in settings if not hidden(setting)]
        state["row"] = min(state["row"], len(shown) - 1)
        return shown

    def cycle(setting: Setting, step: int) -> None:
        current = from_stored(setting, read(stores, setting))
        values = [None] + [value for value, _ in setting.choices]
        index = values.index(current) if current in values else 0
        new = values[(index + step) % len(values)]
        write(stores, setting, None if new is None else to_stored(setting, new))
        state["dirty"] = True

    def toggle(setting: Setting, value: str) -> None:
        current = read(stores, setting)
        chosen = [str(item) for item in current] if isinstance(current, list) else []
        chosen = [item for item in chosen if item != value] if value in chosen else chosen + [value]
        ordered = [item for item, _ in setting.choices if item in chosen]
        write(stores, setting, ordered or None)
        state["dirty"] = True

    def render():
        lines = [("class:title", f" pdfmd setup  --  {path}\n\n")]
        if state["left_out"]:
            lines.append(("class:section", " Not settable here, on purpose\n"))
            lines += [("", line + "\n") for line in left_out or ["  (nothing)"]]
            lines.append(("class:help", "\n o, esc or q: back"))
            return lines
        if state["sub"] is not None:
            setting = state["sub"]
            chosen = read(stores, setting)
            chosen = chosen if isinstance(chosen, list) else []
            lines.append(("class:section", f" {setting.title}\n"))
            lines.append(("class:help", f" {setting.help}\n\n"))
            for index, (value, meaning) in enumerate(setting.choices):
                style = "class:cursor" if index == state["subrow"] else ""
                if index == state["subrow"]:
                    state["line"] = sum(text.count("\n") for _, text in lines)
                lines.append((style, f"  [{'x' if value in chosen else ' '}] {value:<16} {meaning}\n"))
            lines.append(("class:help", "\n up/down move   space toggles   enter or esc: back"))
            return lines
        section = None
        for index, setting in enumerate(rows()):
            if setting.section != section:
                section = setting.section
                lines.append(("class:section", f"\n {section}\n"))
                if setting.store == "metadata":
                    lines.append(("class:help", "  (saved as metadata.yaml: every document gets these, below its own metadata)\n"))
            style = "class:cursor" if index == state["row"] else ""
            if index == state["row"]:
                state["line"] = sum(text.count("\n") for _, text in lines)
            lines.append((style, f"  {setting.title:<46}"))
            lines.append((style + " class:value" if style else "class:value", f"{shown(setting, read(stores, setting))}\n"))
        current = rows()[state["row"]]
        lines.append(("class:help", f"\n {current.help}\n"))
        lines.append(("class:help", "\n up/down move   space/right next value   left previous   r default   enter: choose list"
                                     "\n d features switched off   o what is not here and why   s save and quit   q or esc quit"))
        if state["message"]:
            lines.append(("class:warn", f"\n {state['message']}"))
        return lines

    keys = KeyBindings()
    result = {"save": False, "edit": None}

    def leaving() -> bool:
        """Keys close the list of what is not here first (and do nothing else)."""
        if state["left_out"]:
            state["left_out"] = False
            return True
        return False

    @keys.add("o", filter=Condition(lambda: state["sub"] is None))
    def _left_out(event):
        state["left_out"] = not state["left_out"]

    @keys.add("down")
    @keys.add("j")
    def _down(event):
        if leaving():
            return
        if state["sub"] is not None:
            state["subrow"] = (state["subrow"] + 1) % len(state["sub"].choices)
        else:
            state["row"] = (state["row"] + 1) % len(rows())

    @keys.add("up")
    @keys.add("k")
    def _up(event):
        if leaving():
            return
        if state["sub"] is not None:
            state["subrow"] = (state["subrow"] - 1) % len(state["sub"].choices)
        else:
            state["row"] = (state["row"] - 1) % len(rows())

    @keys.add("space")
    @keys.add("right")
    def _next(event):
        if leaving():
            return
        setting = state["sub"] or rows()[state["row"]]
        if setting.kind == "text":
            result["edit"] = setting
            event.app.exit()
        elif setting.kind == "multi":
            if state["sub"] is None:
                state["sub"], state["subrow"] = setting, 0
            else:
                toggle(setting, setting.choices[state["subrow"]][0])
        else:
            cycle(setting, 1)

    @keys.add("left")
    def _previous(event):
        if leaving():
            return
        setting = rows()[state["row"]]
        if state["sub"] is None and setting.kind == "choice":
            cycle(setting, -1)

    @keys.add("enter")
    def _enter(event):
        if leaving():
            return
        if state["sub"] is not None:
            state["sub"] = None
            return
        setting = rows()[state["row"]]
        if setting.kind == "multi":
            state["sub"], state["subrow"] = setting, 0
        elif setting.kind == "text":
            result["edit"] = setting
            event.app.exit()
        else:
            cycle(setting, 1)

    @keys.add("escape", eager=True)
    def _escape(event):
        """Esc steps back: out of a list, then out of the screen (it asks first when something is unsaved)."""
        if leaving():
            return
        if state["sub"] is not None:
            state["sub"] = None
            return
        _quit(event)

    @keys.add("d")
    def _features(event):
        if leaving():
            return
        if switch is not None and state["sub"] is None:
            state["sub"], state["subrow"] = switch, 0

    @keys.add("r")
    def _default(event):
        if leaving():
            return
        if state["sub"] is None:
            write(stores, rows()[state["row"]], None)
            state["dirty"] = True

    @keys.add("s")
    def _save(event):
        if leaving():
            return
        result["save"] = True
        event.app.exit()

    @keys.add("q")
    @keys.add("c-c")
    def _quit(event):
        if leaving():
            return
        if state["dirty"] and not state["message"]:
            state["message"] = "Unsaved changes: q again to quit without saving, s to save."
            return
        event.app.exit()

    def make_application():
        return Application(
            layout=Layout(HSplit([Window(FormattedTextControl(render, get_cursor_position=lambda: Point(0, state["line"])),
                                          wrap_lines=True, scroll_offsets=ScrollOffsets(top=3, bottom=6))])),
            key_bindings=keys, full_screen=True, mouse_support=False, input=input, output=output,
            style=Style.from_dict({"title": "bold", "section": "bold #5fafd7", "cursor": "reverse", "value": "#87d787",
                                   "help": "#888888", "warn": "#ffaf5f"}))
    while True:
        result["edit"] = None
        make_application().run()
        setting = result["edit"]
        if setting is None:
            break
        # a text setting: leave the full screen for a prompt, then come back
        current = read(stores, setting)
        answer = (ask or _prompt)(setting, "" if current is None else str(current))
        if answer is not None:
            if answer.strip() in ("", "-"):
                write(stores, setting, None)
            else:
                value = answer.strip()
                if setting.check == "number":
                    try:
                        number = float(value)
                        value = int(number) if number == int(number) else number
                    except ValueError:
                        state["message"] = "A number, please."
                        continue
                elif setting.check == "list":
                    value = [item.strip() for item in value.split(",") if item.strip()]
                elif setting.check == "count":
                    if value.lower() == "all":
                        value = "all"
                    elif value.isdigit() and int(value) > 0:
                        value = int(value)
                    else:
                        state["message"] = "A whole number, or all, please."
                        continue
                write(stores, setting, value)
            state["dirty"] = True
    return result["save"]


def _prompt(setting: Setting, now: str):
    from prompt_toolkit import prompt
    try:
        from prompt_toolkit.key_binding import KeyBindings
        cancel = KeyBindings()

        @cancel.add("escape", eager=True)
        def _cancel(event):
            event.app.exit(exception=EOFError)
        return prompt(f"{setting.title} ({setting.help or 'empty or - = back to the default'}; esc = cancel): ",
                      default=now, key_bindings=cancel)
    except (EOFError, KeyboardInterrupt):
        return None
