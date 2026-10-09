"""`pdfmd --edit FILE`: a small full-screen editor, alpha (v3.25.15).

A nano-like editor for the Markdown file, with the build one key away: Ctrl-B saves and builds, and the last lines of
what pdfmd said stay at the bottom. It is rough on purpose: the point is a base to grow (shortcuts for pdfmd's own
features, a live preview, one place for options) into the interface of a later release. It needs prompt_toolkit
(`pdfmd --install tui`); without it `pdfmd --edit` says so and exits.

Keys (F1 shows them): Ctrl-S save, Ctrl-B build, Ctrl-P open the result, Ctrl-W find, F3 find next, Ctrl-G go to line,
Ctrl-K cut line, Ctrl-U paste, Ctrl-Z undo, Ctrl-Y redo, Ctrl-X exit.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Callable

HELP = """\
  Ctrl-S  save                    Ctrl-W  find        F3      find next
  Ctrl-B  save and build          Ctrl-G  go to line
  Ctrl-P  open the built file     Ctrl-K  cut line    Ctrl-U  paste
  Ctrl-X  exit                    Ctrl-Z  undo        Ctrl-Y  redo
  F1      this help               Esc     leave a prompt or this help
"""

BuildResult = tuple[bool, str, "Path | None"]


def available() -> bool:
    try:
        import prompt_toolkit  # noqa: F401
    except ImportError:
        return False
    return True


def save_text(path: Path, text: str) -> None:
    """Write `text` to `path` through a temporary file in the same folder, so a failure cannot cut the file in half."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False,
                                     prefix=f".{path.name}.", suffix=".tmp") as handle:
        handle.write(text)
        temporary = Path(handle.name)
    try:
        if path.exists():
            temporary.chmod(path.stat().st_mode & 0o777)
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def find_from(text: str, needle: str, start: int) -> int | None:
    """The position of the next `needle` at or after `start`, wrapping round; None when there is none (case is
    ignored unless the needle has a capital)."""
    if not needle:
        return None
    flags = 0 if needle != needle.lower() else re.IGNORECASE
    pattern = re.compile(re.escape(needle), flags)
    found = pattern.search(text, start) or pattern.search(text, 0)
    return found.start() if found else None


def run(path: Path, build: Callable[[Path], BuildResult] | None = None,
        opener: Callable[[Path], None] | None = None, input=None, output=None) -> int:
    """Edit `path` (a new file when it does not exist yet). `build(path)` returns (ok, what pdfmd said, the file it
    made); `opener(file)` opens a file. `input`/`output` let a test drive it. Returns an exit status."""
    from prompt_toolkit.application import Application
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import ConditionalContainer, Dimension, HSplit, Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import TextArea

    try:
        original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    except (OSError, UnicodeDecodeError) as error:
        print(f"ERROR  cannot read {path}: {error}")
        return 1

    lexer = None
    try:
        from prompt_toolkit.lexers import PygmentsLexer
        from pygments.lexers.markup import MarkdownLexer
        lexer = PygmentsLexer(MarkdownLexer)
    except ImportError:
        pass

    state = {"mode": "edit", "saved": original, "message": "", "build": [], "output": None, "building": False,
             "clip": "", "find": "", "quit_asked": False}
    editor = TextArea(text=original, scrollbar=True, line_numbers=True, wrap_lines=True, lexer=lexer,
                      focus_on_click=True)
    prompt_area = TextArea(height=1, multiline=False, prompt="", wrap_lines=False)

    def dirty() -> bool:
        return editor.text != state["saved"]

    def header():
        marks = " [modified]" if dirty() else ""
        position = editor.document.cursor_position_row + 1, editor.document.cursor_position_col + 1
        return [("class:title", f" pdfmd edit  {path.name}{marks}"),
                ("class:title2", f"   line {position[0]}, col {position[1]}")]

    def footer():
        lines = []
        if state["mode"] == "help":
            return [("class:help", HELP)]
        if state["build"]:
            tail = state["build"][-3:]
            lines.append(("class:build", "\n".join(" " + line for line in tail) + "\n"))
        if state["building"]:
            lines.append(("class:warn", " building ...\n"))
        elif state["message"]:
            lines.append(("class:warn", f" {state['message']}\n"))
        lines.append(("class:keys", " ^S save  ^B build  ^P open  ^W find  ^G line  ^K cut  ^U paste  ^X exit  F1 help"))
        return lines

    prompts = {"find": "Find: ", "goto": "Go to line: "}
    asking = Condition(lambda: state["mode"] in prompts)
    helping = Condition(lambda: state["mode"] == "help")
    editing = Condition(lambda: state["mode"] == "edit")
    layout = Layout(HSplit([
        Window(FormattedTextControl(header), height=1, style="class:bar"),
        editor,
        ConditionalContainer(HSplit([Window(FormattedTextControl(lambda: [("class:prompt", prompts.get(state["mode"], ""))]),
                                             height=1, dont_extend_height=True), prompt_area]), filter=asking),
        Window(FormattedTextControl(footer), height=Dimension(min=1, max=7), style="class:foot"),
    ]), focused_element=editor)

    keys = KeyBindings()

    def write_out() -> bool:
        try:
            save_text(path, editor.text)
        except OSError as error:
            state["message"] = f"Cannot save: {error}"
            return False
        state["saved"] = editor.text
        state["message"] = f"Saved {path.name}"
        state["quit_asked"] = False
        return True

    @keys.add("c-s", filter=editing)
    def _save(event):
        write_out()

    @keys.add("c-x", filter=editing, eager=True)
    def _exit(event):
        if dirty() and not state["quit_asked"]:
            state["quit_asked"] = True
            state["message"] = "Unsaved changes: ^S saves, ^X again quits without saving."
            return
        event.app.exit(result=0)

    @keys.add("c-k", filter=editing)
    def _cut(event):
        buffer = editor.buffer
        row = buffer.document.cursor_position_row
        lines = buffer.text.split("\n")
        state["clip"] = lines[row] + "\n"
        del lines[row]
        buffer.text = "\n".join(lines)
        buffer.cursor_position = len("\n".join(lines[:row])) + (1 if row else 0) if lines else 0

    @keys.add("c-u", filter=editing)
    def _paste(event):
        if state["clip"]:
            buffer = editor.buffer
            row = buffer.document.cursor_position_row
            lines = buffer.text.split("\n")
            lines[row:row] = state["clip"].rstrip("\n").split("\n")
            buffer.text = "\n".join(lines)
            buffer.cursor_position = len("\n".join(lines[:row])) + (1 if row else 0)

    @keys.add("c-z", filter=editing)
    def _undo(event):
        editor.buffer.undo()

    @keys.add("c-y", filter=editing)
    def _redo(event):
        editor.buffer.redo()

    def ask(kind: str, event) -> None:
        state["mode"] = kind
        prompt_area.text = state["find"] if kind == "find" else ""
        event.app.layout.focus(prompt_area)

    @keys.add("c-w", filter=editing)
    def _find(event):
        ask("find", event)

    @keys.add("c-g", filter=editing)
    def _goto(event):
        ask("goto", event)

    @keys.add("f3", filter=editing)
    def _again(event):
        jump(state["find"], event)

    def jump(needle: str, event) -> None:
        buffer = editor.buffer
        position = find_from(buffer.text, needle, buffer.cursor_position + 1)
        if position is None:
            state["message"] = f"Not found: {needle}" if needle else "Nothing to find yet (^W)"
        else:
            buffer.cursor_position = position
            state["message"] = ""

    @keys.add("enter", filter=asking)
    def _accept(event):
        kind, answer = state["mode"], prompt_area.text.strip()
        state["mode"] = "edit"
        event.app.layout.focus(editor)
        if kind == "find":
            state["find"] = answer
            jump(answer, event)
        elif kind == "goto":
            if answer.isdigit() and int(answer) >= 1:
                buffer = editor.buffer
                lines = buffer.text.split("\n")
                row = min(int(answer), len(lines)) - 1
                buffer.cursor_position = len("\n".join(lines[:row])) + (1 if row else 0)
                state["message"] = ""
            else:
                state["message"] = "A line number, please."

    @keys.add("escape", filter=asking | helping)
    def _leave(event):
        state["mode"] = "edit"
        event.app.layout.focus(editor)

    @keys.add("f1", filter=editing)
    def _help(event):
        state["mode"] = "help"

    @keys.add("<any>", filter=helping, eager=True)
    def _any(event):
        state["mode"] = "edit"

    @keys.add("c-b", filter=editing)
    @keys.add("f5", filter=editing)
    def _build(event):
        if state["building"]:
            return
        if build is None:
            state["message"] = "Nothing to build with."
            return
        if dirty() and not write_out():
            return
        state["building"], state["build"], state["message"] = True, [], ""
        app = event.app

        def work():
            try:
                ok, said, made = build(path)
            except Exception as error:  # noqa: BLE001 -- the editor must survive a failed build
                ok, said, made = False, f"The build failed: {error}", None
            lines = [line for line in said.splitlines() if line.strip()] or ["(no output)"]
            state["build"] = lines
            state["output"] = made if ok else None
            state["building"] = False
            state["message"] = "Built " + (made.name if made else path.name) if ok else "The build failed (see above)"
            app.invalidate()

        threading.Thread(target=work, daemon=True).start()

    @keys.add("c-p", filter=editing)
    def _open(event):
        target = state["output"]
        if target is None:
            state["message"] = "Nothing built yet (^B)"
        elif opener is not None:
            opener(target)
            state["message"] = f"Opened {target.name}"

    app = Application(layout=layout, key_bindings=keys, full_screen=True, mouse_support=True, input=input, output=output,
                      style=Style.from_dict({"bar": "reverse", "title": "bold reverse", "title2": "reverse",
                                             "foot": "", "keys": "reverse", "help": "", "build": "#888888",
                                             "warn": "#ffaf5f", "prompt": "bold"}))
    return int(app.run() or 0)
