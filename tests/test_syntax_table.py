"""The syntax table (lib/pdfmd_web/syntax/syntaxes.json, v3.32.44, entry 3do): written once, read by the page's editor (engine.js) and the Mac
app's (Highlighter.swift). This file keeps the table honest: every pattern uses the subset of regular expressions the three engines agree on,
every role it names exists, and the colours the engines give to cases.json are the expected ones -- through a Python copy of the engine
here and through the page's own engine.js under node (skipped without node). The Mac app runs the same file with `pdfmdedit --smoke-syntax`."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

SYNTAX = Path(__file__).resolve().parent.parent / "lib" / "pdfmd_web" / "syntax"
TABLE = json.loads((SYNTAX / "syntaxes.json").read_text(encoding="utf-8"))
CASES = json.loads((SYNTAX / "cases.json").read_text(encoding="utf-8"))["cases"]
NODE = shutil.which("node")

# what the engines read differently: shorthand classes are Unicode in ICU and Python and ASCII in JavaScript; named groups, flags and
# \p{..} are not shared; a lookbehind needs a fixed width
FORBIDDEN = [(re.compile(r"(?<!\\)(?:\\\\)*\\[wWdDsSbBpPhHRXzZAG]"), "a shorthand class (use an explicit [..])"),
             (re.compile(r"\(\?(?:P?<[A-Za-z]|[a-zA-Z]+[:)]|#|>|\|)"), "a named group, an inline flag or a group kind the engines do not share")]


def rules_of(syntax: dict):
    return [(re.compile(rule["match"], re.MULTILINE), rule["role"]) for rule in syntax["rules"]]


def utf16(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le")) // 2


def reference_runs(name: str, text: str) -> list[list]:
    """The Python copy of the engine: the rules of syntaxes.json's header, applied to `text`; runs [from, to, role] in UTF-16 units."""
    syntax = TABLE["syntaxes"][name]
    owner: list[str | None] = [None] * len(text)

    def paint(syntax_name: str, start: int, end: int) -> None:
        segment = text[start:end]
        for pattern, role in rules_of(TABLE["syntaxes"][syntax_name]):
            for match in pattern.finditer(segment):
                if match.end() > match.start():
                    owner[start + match.start():start + match.end()] = [role] * (match.end() - match.start())

    front = 0
    fm = syntax.get("frontMatter")
    if fm and text.startswith(fm["open"]) and text[len(fm["open"]):len(fm["open"]) + 1] in ("\n", "\r"):
        limit = min(len(text), len(fm["open"]) + fm["scan"])
        hits = [i for closer in fm["close"] if (i := text[:limit].find("\n" + closer, len(fm["open"]))) >= 0]
        if hits:
            newline = text.find("\n", min(hits) + 1)
            front = len(text) if newline < 0 else newline + 1
            paint(fm["syntax"], 0, front)
    cursor, in_code = front, False
    fences = syntax.get("fences")

    def fill(start: int, end: int) -> None:
        owner[start:end] = [fences["role"]] * (end - start)

    def body(start: int, end: int) -> None:
        if end > start:
            paint(name, start, end)

    if fences:
        fence = re.compile("^ {0,3}(?:" + "|".join(re.escape(m) for m in fences["markers"]) + ")")
        position = front
        starts = []
        while position < len(text):
            newline = text.find("\n", position)
            end = len(text) if newline < 0 else newline
            if fence.match(text[position:end]):
                starts.append(position)
            position = end + 1
        for start in starts:
            (fill if in_code else body)(cursor, start)
            newline = text.find("\n", start)
            end = len(text) if newline < 0 else newline + 1
            fill(start, end)
            in_code, cursor = not in_code, end
    (fill if in_code else body)(cursor, len(text))
    runs: list[list] = []
    at = 0
    while at < len(text):
        role, end = owner[at], at + 1
        while end < len(text) and owner[end] == role:
            end += 1
        if role is not None:
            runs.append([utf16(text, at), utf16(text, end), role])
        at = end
    return runs


class Table(unittest.TestCase):
    def test_every_rule_names_a_role_of_the_table_and_every_role_is_complete(self):
        roles = {role["key"] for role in TABLE["roles"]}
        for role in TABLE["roles"]:
            self.assertTrue(re.fullmatch(r"#[0-9A-Fa-f]{6}", role["light"]) and re.fullmatch(r"#[0-9A-Fa-f]{6}", role["dark"]), role["key"])
            self.assertTrue(role["category"] and role["help"], role["key"])
        for name, syntax in TABLE["syntaxes"].items():
            used = {rule["role"] for rule in syntax["rules"]} | ({syntax["fences"]["role"]} if syntax.get("fences") else set())
            self.assertLessEqual(used, roles, f"{name}: a role the table does not define")
            if syntax.get("frontMatter"):
                self.assertIn(syntax["frontMatter"]["syntax"], TABLE["syntaxes"], name)

    def test_every_pattern_uses_the_subset_the_engines_share(self):
        for name, syntax in TABLE["syntaxes"].items():
            for rule in syntax["rules"]:
                with self.subTest(syntax=name, pattern=rule["match"]):
                    re.compile(rule["match"])
                    for forbidden, why in FORBIDDEN:
                        self.assertIsNone(forbidden.search(rule["match"]), why)
                    for sample in ("a\nb\n", "\n\n", "x  \n  y"):
                        for match in re.finditer(rule["match"], sample, re.MULTILINE):
                            self.assertNotIn("\n", match.group(0), "a rule must not match a line break")

    def test_the_header_names_what_the_clients_must_do(self):
        text = " ".join(TABLE["about"])
        for needle in ("LATER rule wins", "UTF-16", "frontMatter.scan", "ANY fence line"):
            self.assertIn(needle, text)


class Cases(unittest.TestCase):
    def test_the_python_copy_of_the_engine_gives_the_expected_colours(self):
        for case in CASES:
            with self.subTest(case["name"]):
                self.assertEqual(reference_runs(case["syntax"], case["text"]), case["runs"])

    @unittest.skipUnless(NODE, "needs node")
    def test_the_pages_engine_gives_the_same_colours(self):
        script = (
            "const E=require(process.argv[1]+'/engine.js');const t=require(process.argv[1]+'/syntaxes.json');"
            "const cases=require(process.argv[1]+'/cases.json').cases;const c=E.compile(t);"
            "console.log(JSON.stringify(cases.map(k=>E.runs(c,k.syntax,k.text))));")
        done = subprocess.run([NODE, "-e", script, str(SYNTAX)], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        for case, got in zip(CASES, json.loads(done.stdout)):
            with self.subTest(case["name"]):
                self.assertEqual(got, case["runs"])


if __name__ == "__main__":
    unittest.main()
