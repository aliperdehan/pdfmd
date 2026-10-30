"""`pdfmd --user-path` (v3.31.16): the Windows user PATH, changed only when asked, and put back exactly. The logic runs on a fake
backend on every system; one Windows-only test uses the real registry on a throwaway key."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfmd  # noqa: E402
from pdfmd_setup import fancy, plain, registry, settings_for, userpath  # noqa: E402

REG_SZ, REG_EXPAND_SZ = userpath.REG_SZ, userpath.REG_EXPAND_SZ


class Fake:
    """An in-memory user PATH: what the registry would hold, and how often it was written and broadcast."""

    def __init__(self, value: str | None = "C:\\Windows;%USERPROFILE%\\bin", kind: int = REG_EXPAND_SZ, machine: str = ""):
        self.state = None if value is None else (value, kind)
        self.machine_value = machine
        self.writes = 0
        self.broadcasts = 0

    def read(self):
        return self.state

    def write(self, value, kind):
        self.state = (value, kind)
        self.writes += 1

    def machine(self):
        return self.machine_value

    def broadcast(self):
        self.broadcasts += 1


class Case(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.record = self.root / "state" / "path-added.json"
        self.said: list[str] = []
        self.answers: list[str] = []

    def make(self, name: str, program: bool = True) -> str:
        folder = self.root / name
        folder.mkdir()
        if program:
            (folder / "tool.exe").write_bytes(b"")
        return str(folder)

    def go(self, verb, folders=(), backend=None, found=lambda: [], **keywords):
        backend = backend if backend is not None else self.backend
        keywords.setdefault("interactive", True)
        return userpath.run(verb, list(folders), backend=backend, record=self.record, found=found, say=self.said.append,
                            ask=lambda question: self.answers.pop(0) if self.answers else "", version="3.31.16",
                            now=lambda: datetime(2026, 11, 1, 12, 0, 0), **keywords)

    def text(self) -> str:
        return "\n".join(self.said)


class Adding(Case):
    def setUp(self):
        super().setUp()
        self.backend = Fake()

    def test_a_folder_is_appended_at_the_end_with_the_type_kept(self):
        mine = self.make("mine")
        self.answers = ["y"]
        self.assertEqual(self.go("add", [mine]), 0)
        self.assertEqual(self.backend.state, ("C:\\Windows;%USERPROFILE%\\bin;" + mine, REG_EXPAND_SZ))
        self.assertEqual(self.backend.broadcasts, 1)
        recorded = json.loads(self.record.read_text(encoding="utf-8"))["added"]
        self.assertEqual([item["folder"] for item in recorded], [mine])
        self.assertEqual(recorded[0]["why"], "named by you")

    def test_a_plain_string_value_stays_a_plain_string_and_a_trailing_semicolon_is_kept(self):
        mine = self.make("mine")
        self.backend = Fake("C:\\a;", REG_SZ)
        self.go("add", [mine], yes=True)
        self.assertEqual(self.backend.state, ("C:\\a;" + mine, REG_SZ))

    def test_a_missing_value_is_created_as_an_expandable_string(self):
        mine = self.make("mine")
        self.backend = Fake(None)
        self.go("add", [mine], yes=True)
        self.assertEqual(self.backend.state, (mine, REG_EXPAND_SZ))

    def test_a_folder_that_is_already_there_is_skipped_however_it_is_spelled(self):
        mine = self.make("mine")
        other = self.make("other")
        self.backend = Fake(mine.upper() + "\\;" + "%ZZZ%", REG_EXPAND_SZ, machine=other)
        self.go("add", [mine, other], yes=True)
        self.assertEqual(self.backend.writes, 0)
        self.assertIn("already on your user PATH", self.text())
        self.assertIn("already on the machine PATH", self.text())
        self.assertFalse(self.record.exists())

    def test_the_same_folder_twice_is_added_once(self):
        mine = self.make("mine")
        self.go("add", [mine, mine], yes=True)
        self.assertEqual(self.backend.state[0].count(mine), 1)

    def test_any_folder_is_accepted_but_not_a_missing_one_or_one_with_a_semicolon(self):
        bare = self.make("bare", program=False)
        missing = str(self.root / "nowhere")
        odd = self.make("a;b")
        self.go("add", [bare, missing, odd], yes=True)
        self.assertEqual(self.backend.state[0], "C:\\Windows;%USERPROFILE%\\bin;" + bare)
        self.assertIn("holds no .exe", self.text())
        self.assertIn("is not a folder", self.text())
        self.assertIn("cannot be put on PATH", self.text())

    def test_no_folder_means_the_folders_a_tool_was_found_in(self):
        mine = self.make("mine")
        self.go("add", [], found=lambda: [(mine, "tesseract found there")], yes=True)
        self.assertIn(mine, self.backend.state[0])
        self.assertIn("tesseract found there", self.text())
        self.said.clear()
        self.go("add", [], found=lambda: [])
        self.assertIn("No tool that pdfmd found is off your PATH", self.text())

    def test_a_dry_run_writes_nothing_at_all(self):
        mine = self.make("mine")
        self.assertEqual(self.go("add", [mine], dry_run=True, yes=True), 0)
        self.assertEqual((self.backend.writes, self.backend.broadcasts), (0, 0))
        self.assertFalse(self.record.exists())
        self.assertIn("--dry-run: nothing was changed", self.text())

    def test_without_a_yes_it_asks_and_a_no_changes_nothing(self):
        mine = self.make("mine")
        self.answers = ["n"]
        self.assertEqual(self.go("add", [mine]), 1)
        self.assertEqual(self.backend.writes, 0)
        self.answers = [""]
        self.assertEqual(self.go("add", [mine]), 1)
        self.assertEqual(self.backend.writes, 0)

    def test_with_no_terminal_it_refuses_unless_yes_is_given(self):
        mine = self.make("mine")
        self.assertEqual(self.go("add", [mine], interactive=False), 1)
        self.assertIn("add --yes", self.text())
        self.assertEqual(self.backend.writes, 0)

    def test_a_registry_that_cannot_be_written_is_said_and_leaves_no_record(self):
        mine = self.make("mine")

        def refuse(value, kind):
            raise PermissionError("denied")
        self.backend.write = refuse
        self.assertEqual(self.go("add", [mine], yes=True), 1)
        self.assertIn("could not be written", self.text())
        self.assertFalse(self.record.exists())


class Undoing(Case):
    def setUp(self):
        super().setUp()
        self.backend = Fake()

    def test_remove_takes_off_exactly_what_was_added_and_the_rest_stays_byte_for_byte(self):
        one, two = self.make("one"), self.make("two")
        before = self.backend.state
        self.go("add", [one, two], yes=True)
        self.backend.state = (self.backend.state[0] + ";D:\\later", REG_EXPAND_SZ)       # the user adds an entry meanwhile
        self.said.clear()
        self.assertEqual(self.go("remove", yes=True), 0)
        self.assertEqual(self.backend.state, (before[0] + ";D:\\later", REG_EXPAND_SZ))
        self.assertFalse(self.record.exists())

    def test_an_entry_the_user_already_removed_is_only_dropped_from_the_record(self):
        one = self.make("one")
        self.go("add", [one], yes=True)
        self.backend.state = ("C:\\Windows", REG_EXPAND_SZ)
        self.said.clear()
        self.go("remove", yes=True)
        self.assertIn("gone", self.text())
        self.assertEqual(self.backend.state, ("C:\\Windows", REG_EXPAND_SZ))
        self.assertFalse(self.record.exists())

    def test_remove_with_nothing_recorded_says_so_and_a_dry_run_changes_nothing(self):
        self.assertEqual(self.go("remove", yes=True), 0)
        self.assertIn("added nothing", self.text())
        one = self.make("one")
        self.go("add", [one], yes=True)
        before = (self.backend.state, self.backend.writes)
        self.go("remove", dry_run=True)
        self.assertEqual((self.backend.state, self.backend.writes), before)
        self.assertTrue(self.record.exists())

    def test_remove_asks_first(self):
        one = self.make("one")
        self.go("add", [one], yes=True)
        self.answers = ["n"]
        self.assertEqual(self.go("remove"), 1)
        self.assertIn(one, self.backend.state[0])

    def test_show_marks_what_pdfmd_added(self):
        one = self.make("one")
        self.go("add", [one], yes=True)
        self.said.clear()
        self.assertEqual(self.go("show"), 0)
        self.assertIn("REG_EXPAND_SZ", self.text())
        self.assertIn("added by pdfmd, 2026-11-01T12:00:00", self.text())
        self.assertIn("C:\\Windows", self.text())

    def test_an_unknown_verb_is_refused(self):
        self.assertEqual(self.go("sideways"), 2)
        self.assertIn("takes add, remove, show", self.text())


class SetupRow(unittest.TestCase):
    def test_the_row_is_a_machine_action_that_stores_nothing(self):
        [row] = [setting for setting in settings_for(pdfmd.NO_AUTO_KINDS) if setting.key == "user-path"]
        self.assertEqual((row.kind, row.scope), ("action", "machine"))
        self.assertEqual(registry.read({}, row), None)

    def run_screen(self, answers: list[str], actions):
        said: list[str] = []
        lines = iter(answers)
        settings = settings_for(pdfmd.NO_AUTO_KINDS)
        saved = plain.run({}, settings, "config.yaml", lambda prompt: next(lines), said.append, actions=actions)
        return saved, "\n".join(said)

    def test_the_numbered_screen_runs_the_action_and_saves_nothing(self):
        settings = settings_for(pdfmd.NO_AUTO_KINDS)
        number = [setting.key for setting in settings].index("user-path") + 1
        ran = []
        saved, text = self.run_screen([str(number), "s"], {"user-path": lambda say, read_line: ran.append(read_line)})
        self.assertEqual(len(ran), 1)
        self.assertIn("Windows user PATH", text)
        self.assertTrue(saved)

    def test_without_an_action_the_row_is_not_shown(self):
        saved, text = self.run_screen(["q"], None)
        self.assertNotIn("Windows user PATH", text)

    def test_the_menu_runs_the_same_commands(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, folder, True)
        record = Path(folder) / "added.json"
        backend = Fake("C:\\a")
        said: list[str] = []
        answers = iter(["2", folder, "y", "3", "4", "y"])
        context = dict(backend=backend, record=record, found=lambda: [], version="3.31.16")
        for _ in range(3):
            userpath.menu(said.append, lambda prompt: next(answers), **context)
        self.assertEqual(backend.state, ("C:\\a", REG_EXPAND_SZ))          # added, shown, taken off
        self.assertTrue(any("C:\\a" in line for line in said))


@unittest.skipUnless(fancy.available(), "needs prompt_toolkit")
class FancyRow(unittest.TestCase):
    def drive(self, keys: str, actions):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        settings = settings_for(pdfmd.NO_AUTO_KINDS)
        down = "j" * [setting.key for setting in settings].index("user-path")
        with create_pipe_input() as pipe:
            pipe.send_text(down + keys)
            return fancy.run({}, settings, "config.yaml", input=pipe, output=DummyOutput(), actions=actions)

    def test_enter_on_the_row_runs_the_action_and_nothing_is_stored(self):
        ran = []
        self.assertTrue(self.drive("\rs", {"user-path": lambda say, read_line: ran.append(1)}))
        self.assertEqual(ran, [1])

    def test_without_an_action_the_row_is_not_on_the_screen(self):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        settings = settings_for(pdfmd.NO_AUTO_KINDS)
        before = [setting.key for setting in settings].index("user-path")
        with create_pipe_input() as pipe:
            pipe.send_text("j" * before + "\rq")        # on this position enter now lands on the next row, not on an action
            self.assertFalse(fancy.run({}, settings, "config.yaml", input=pipe, output=DummyOutput()))


class Command(unittest.TestCase):
    def test_off_windows_it_prints_the_shell_line_and_exits_one(self):
        if sys.platform == "win32":
            self.skipTest("this checks the other systems")
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--user-path", "show"], capture_output=True, text=True,
                              encoding="utf-8")
        self.assertEqual(done.returncode, 1)
        self.assertIn("export PATH", done.stderr)

    def test_the_spelled_out_forms_and_a_wrong_verb(self):
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--user-path", "sideways"], capture_output=True, text=True,
                              encoding="utf-8")
        self.assertEqual(done.returncode, 2)
        self.assertIn("takes add, remove, show", done.stderr)
        done = subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), "--user-path", "show", "x"], capture_output=True, text=True,
                              encoding="utf-8")
        self.assertEqual(done.returncode, 2)


@unittest.skipUnless(sys.platform == "win32", "needs the Windows registry")
class RealRegistry(unittest.TestCase):
    """The real winreg, on a throwaway key under HKEY_CURRENT_USER (never the real Environment)."""

    def setUp(self):
        import uuid
        import winreg
        self.subkey = f"Software\\pdfmd-test-{uuid.uuid4().hex}\\Environment"
        self.addCleanup(self.drop, winreg)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.root / "config"), "APPDATA": str(self.root / "config"), "PDFMD_USER_ENV_KEY": self.subkey, "PDFMD_CONFIG": ""}

    def drop(self, winreg):
        base = self.subkey.rsplit("\\", 1)[0]
        for name in (self.subkey, base):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, name)
            except OSError:
                pass

    def pdfmd(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / "pdfmd.py"), *arguments], capture_output=True, text=True, encoding="utf-8",
                              env=self.env, stdin=subprocess.DEVNULL)

    def value(self):
        return userpath.Registry(self.subkey).read()

    def test_add_show_and_remove_through_the_command_line(self):
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.subkey, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Path", 0, REG_EXPAND_SZ, "%USERPROFILE%\\bin;C:\\Tools")
        mine = self.root / "mine"
        mine.mkdir()
        (mine / "tool.cmd").write_text("@echo off\n", encoding="utf-8")
        dry = self.pdfmd("--user-path", "add", str(mine), "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertEqual(self.value(), ("%USERPROFILE%\\bin;C:\\Tools", REG_EXPAND_SZ))
        refused = self.pdfmd("--add-to-path", str(mine))                       # no terminal and no --yes
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(self.value()[0], "%USERPROFILE%\\bin;C:\\Tools")
        added = self.pdfmd("--user-path", "add", str(mine), "--yes")
        self.assertEqual(added.returncode, 0, added.stdout + added.stderr)
        self.assertEqual(self.value(), (f"%USERPROFILE%\\bin;C:\\Tools;{mine}", REG_EXPAND_SZ))
        self.assertIn(str(mine), self.pdfmd("--show-user-path").stdout)
        gone = self.pdfmd("--remove-from-path", "--yes")
        self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
        self.assertEqual(self.value(), ("%USERPROFILE%\\bin;C:\\Tools", REG_EXPAND_SZ))


if __name__ == "__main__":
    unittest.main()
