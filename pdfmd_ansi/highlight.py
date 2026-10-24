"""Token colours for fenced code in the terminal renderer, with no dependency: a small tokenizer for python, bash/sh, json, yaml and
the C-like languages (c, cpp, java, javascript, rust, go). It finds keywords, strings, comments and numbers, nothing finer, and
says nothing about a language it does not know (`tokens` is None: the block stays plain).

    tokens("python", 'x = "a" # note\\n')  ->  [[("x", ""), (" = ", ""), ('"a"', "str"), (" ", ""), ("# note", "com")], [("", "")]]

A kind is "kw", "str", "com" or "num" (or "" for the rest); `PALETTE` maps it to the style token that `text.emit` turns into a
colour. One pass over the whole block, so a triple-quoted string or a `/* */` comment may run over several lines.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Optional, Tuple

Piece = Tuple[str, str]

# 256-colour codes, chosen to read on a dark and a light background and to differ from the block's own colour (173)
PALETTE: Dict[str, str] = {"kw": "fg:38;5;176", "str": "fg:38;5;108", "com": "fg:38;5;244", "num": "fg:38;5;74"}

IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
NUMBER = re.compile(r"0[xX][0-9a-fA-F_]+[uUlL]*|0[bB][01_]+[uUlL]*|0[oO][0-7_]+|(?:\d[\d_]*)?\.?\d[\d_]*(?:[eE][+-]?\d+)?[uUlLfFjJ]*")


def words(text: str) -> FrozenSet[str]:
    return frozenset(text.split())


class Spec:
    """What a language is made of; the scanner reads it."""

    def __init__(self, keywords: str = "", line_comments: Tuple[str, ...] = (), block_comment: Optional[Tuple[str, str]] = None,
                 strings: Tuple[str, ...] = ("\"", "'"), triple: bool = False, raw_quotes: Tuple[str, ...] = (),
                 string_prefix: Optional[re.Pattern] = None, hash_directives: bool = False, comment_after_space: bool = False,
                 char_literal_only: bool = False, yaml_keys: bool = False, dollar_names: bool = False,
                 numbers: bool = True) -> None:
        self.keywords = words(keywords)
        self.line_comments = line_comments
        self.block_comment = block_comment
        self.strings = strings                       # quote characters that open a string with escapes (\\x)
        self.triple = triple                         # '''..''' and """.."""
        self.raw_quotes = raw_quotes                 # quote characters that open a string without escapes (bash '..', Go `..`)
        self.string_prefix = string_prefix           # python's r"", f"", b"" ...
        self.hash_directives = hash_directives       # C's #include
        self.comment_after_space = comment_after_space   # `#` starts a comment only after a space (bash, yaml)
        self.char_literal_only = char_literal_only   # Rust: 'a is a lifetime, 'a' a character
        self.yaml_keys = yaml_keys
        self.dollar_names = dollar_names             # bash $name, ${name}
        self.numbers = numbers


PYTHON = Spec(
    "False None True and as assert async await break class continue def del elif else except finally for from global if import "
    "in is lambda nonlocal not or pass raise return try while with yield",
    line_comments=("#",), triple=True, string_prefix=re.compile(r"(?i:rb|br|fr|rf|[rbfu])(?=[\"'])"))
BASH = Spec(
    "if then else elif fi for while until do done case esac in function select time return exit break continue export local "
    "readonly unset source alias declare eval exec set shift trap",
    line_comments=("#",), strings=("\"",), raw_quotes=("'",), comment_after_space=True, dollar_names=True)
JSON = Spec("true false null", strings=("\"",))
YAML = Spec("true false null yes no on off", line_comments=("#",), comment_after_space=True, yaml_keys=True)
C = Spec(
    "auto break case char const continue default do double else enum extern float for goto if inline int long register restrict "
    "return short signed sizeof static struct switch typedef union unsigned void volatile while NULL true false bool",
    line_comments=("//",), block_comment=("/*", "*/"), hash_directives=True, char_literal_only=False)
CPP = Spec(
    "alignas alignof and asm auto bool break case catch char class const constexpr const_cast continue decltype default delete do "
    "double dynamic_cast else enum explicit export extern false float for friend goto if inline int long mutable namespace new "
    "noexcept not nullptr operator or private protected public register reinterpret_cast return short signed sizeof static "
    "static_assert static_cast struct switch template this throw true try typedef typeid typename union unsigned using virtual "
    "void volatile while NULL",
    line_comments=("//",), block_comment=("/*", "*/"), hash_directives=True)
JAVA = Spec(
    "abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally "
    "float for goto if implements import instanceof int interface long native new package private protected public return short "
    "static strictfp super switch synchronized this throw throws transient try void volatile while var record true false null",
    line_comments=("//",), block_comment=("/*", "*/"))
JAVASCRIPT = Spec(
    "async await break case catch class const continue debugger default delete do else enum export extends false finally for "
    "function if import in instanceof let new null of return static super switch this throw true try typeof undefined var void "
    "while with yield interface type implements readonly private public protected as from",
    line_comments=("//",), block_comment=("/*", "*/"), strings=("\"", "'", "`"))
RUST = Spec(
    "as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref "
    "return self Self static struct super trait true type unsafe use where while",
    line_comments=("//",), block_comment=("/*", "*/"), char_literal_only=True, strings=("\"", "'"))
GO = Spec(
    "break case chan const continue default defer else fallthrough for func go goto if import interface map package range return "
    "select struct switch type var nil true false iota",
    line_comments=("//",), block_comment=("/*", "*/"), strings=("\"", "'"), raw_quotes=("`",))

LANGUAGES: Dict[str, Spec] = {}
for names, spec in ((("python", "py", "python3", "py3"), PYTHON), (("bash", "sh", "shell", "zsh", "console"), BASH),
                    (("json", "jsonc", "json5"), JSON), (("yaml", "yml"), YAML), (("c", "h"), C),
                    (("cpp", "c++", "cxx", "cc", "hpp", "hxx"), CPP), (("java",), JAVA),
                    (("javascript", "js", "jsx", "mjs", "typescript", "ts", "tsx"), JAVASCRIPT), (("rust", "rs"), RUST),
                    (("go", "golang"), GO)):
    for name in names:
        LANGUAGES[name] = spec


def language_of(classes: List[str]) -> Optional[str]:
    """The language a fenced block names: its first class that is one we know (`python`, `{.python}`, `Python`), else None."""
    for name in classes:
        key = name.strip("{}. ").lower()
        if key in LANGUAGES:
            return key
    return None


def scan(spec: Spec, text: str) -> List[Piece]:
    """The whole block as (text, kind) pieces, line ends included in the plain pieces."""
    out: List[Piece] = []
    plain: List[str] = []

    def put(kind: str, piece: str) -> None:
        nonlocal plain
        if not piece:
            return
        if kind == "":
            plain.append(piece)
            return
        if plain:
            out.append(("".join(plain), ""))
            plain = []
        out.append((piece, kind))

    n, i = len(text), 0
    line_start = True
    while i < n:
        char = text[i]
        before = text[i - 1] if i else "\n"
        # comments
        if spec.block_comment and text.startswith(spec.block_comment[0], i):
            end = text.find(spec.block_comment[1], i + len(spec.block_comment[0]))
            end = n if end < 0 else end + len(spec.block_comment[1])
            put("com", text[i:end])
            i, line_start = end, False
            continue
        marker = next((m for m in spec.line_comments if text.startswith(m, i)), None)
        if marker and (not spec.comment_after_space or before in " \t\n;|&("):
            end = text.find("\n", i)
            end = n if end < 0 else end
            put("com", text[i:end])
            i, line_start = end, False
            continue
        # C preprocessor lines: the directive word
        if spec.hash_directives and char == "#" and (line_start or not text[text.rfind("\n", 0, i) + 1:i].strip()):
            found = re.compile(r"#[ \t]*[A-Za-z_]+").match(text, i)
            if found:
                put("kw", found.group(0))
                i, line_start = found.end(), False
                continue
        # strings
        prefix = spec.string_prefix.match(text, i) if spec.string_prefix else None
        quote_at = i + (len(prefix.group(0)) if prefix else 0)
        if quote_at < n and (prefix is None or before not in IDENT_CHARS):
            quote = text[quote_at]
            if quote in spec.strings or quote in spec.raw_quotes:
                end = string_end(spec, text, quote_at, quote)
                if end is not None:
                    put("str", text[i:end])
                    i, line_start = end, False
                    continue
        if spec.yaml_keys and text[text.rfind("\n", 0, i) + 1:i].strip() in ("", "-"):
            key = re.compile(r"[A-Za-z_][\w.\- ]*?(?=:(?:\s|$))|\"[^\"\n]*\"(?=:(?:\s|$))|'[^'\n]*'(?=:(?:\s|$))").match(text, i)
            if key:
                put("kw", key.group(0))
                i, line_start = key.end(), False
                continue
        # words and numbers
        if char.isalpha() or char in "_$":
            word = IDENT.match(text, i)
            if word:
                if spec.dollar_names and char == "$":
                    put("", word.group(0))
                elif word.group(0) in spec.keywords and before not in "$.@" and not (spec is BASH and before == "-"):
                    put("kw", word.group(0))
                else:
                    put("", word.group(0))
                i, line_start = word.end(), False
                continue
        if spec.dollar_names and char == "$":
            braced = re.compile(r"\$\{[^}\n]*\}|\$[A-Za-z_][A-Za-z_0-9]*|\$[0-9@#?*$!-]").match(text, i)
            if braced:
                put("", braced.group(0))
                i, line_start = braced.end(), False
                continue
        if spec.numbers and (char.isdigit() or (char == "." and i + 1 < n and text[i + 1].isdigit())) \
                and before not in IDENT_CHARS:
            number = NUMBER.match(text, i)
            if number and spec is BASH and text[number.end():number.end() + 1] not in ("", " ", "\t", "\n", ";", ")", "]", "\"", "'"):
                number = None                         # 2>/dev/null, 10.0.0.1/24 are not numbers
            if number and number.group(0):
                put("num", number.group(0))
                i, line_start = number.end(), False
                continue
        put("", char)
        line_start = char == "\n" or (line_start and char in " \t-")
        i += 1
    if plain:
        out.append(("".join(plain), ""))
    return out


IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")


def string_end(spec: Spec, text: str, start: int, quote: str) -> Optional[int]:
    """Where the string that opens at `start` ends (just past its closing quote), or None when what stands there is no string."""
    n = len(text)
    if spec.char_literal_only and quote == "'":        # Rust: 'a' or '\n' is a character, 'a is a lifetime
        found = re.compile(r"'(?:\\.[^']*|[^\\'])'").match(text, start)
        return found.end() if found else None
    triple = quote * 3
    if spec.triple and text.startswith(triple, start):
        end = text.find(triple, start + 3)
        while end > 0 and text[end - 1] == "\\" and text[end - 2:end] != "\\\\":
            end = text.find(triple, end + 1)
        return n if end < 0 else end + 3
    raw = quote in spec.raw_quotes
    multiline = quote == "`"
    i = start + 1
    while i < n:
        char = text[i]
        if char == quote:
            return i + 1
        if char == "\n" and not multiline and not raw:
            return i                                  # an unclosed string ends with its line
        if char == "\\" and not raw and i + 1 < n:
            i += 2
            continue
        i += 1
    return n


def tokens(language: Optional[str], code: str) -> Optional[List[List[Piece]]]:
    """The code as lines of (text, kind) pieces, or None when `language` is not one we colour."""
    spec = LANGUAGES.get((language or "").strip("{}. ").lower())
    if spec is None:
        return None
    lines: List[List[Piece]] = [[]]
    for text, kind in scan(spec, code):
        for index, part in enumerate(text.split("\n")):
            if index:
                lines.append([])
            if part:
                lines[-1].append((part, kind))
    return lines
