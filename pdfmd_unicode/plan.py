"""From a document's text to "these characters need these other fonts".

`plan_text()` finds the characters the main font cannot draw, picks for each the
first installed font in its script's list that can, and `Plan` turns that into
the two things a LaTeX build needs: a preamble that defines one font switch per
chosen font, and a Pandoc Lua filter that wraps each run of such characters in
the right switch (and a direction, for Arabic and Hebrew). Same machinery for
every script, instead of one hand-written `ucharclasses` block per document.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .emoji import can_be_emoji, is_emoji_code_point, VARIATION_EMOJI
from .fonts import Face, FontIndex, coverage
from .scripts import (COMMON, FONTSPEC_SCRIPTS, RTL_SCRIPTS, SCRIPT_NAMES, chain_for, han_language,
                      is_neutral, script_of)


CJK_SCRIPTS = frozenset({"Hani", "Hira", "Kana", "Hang", "Bopo"})


@dataclass
class Choice:
    key: str
    family: str
    face: Face
    scripts: dict[str, int] = field(default_factory=dict)  # script -> characters of it set in this font
    styles: dict[str, Face] = field(default_factory=dict)
    lang: str | None = None  # a language tag for CJK runs (zh, ja, ko): the glyph shapes depend on it

    @property
    def script(self) -> str | None:
        """The script this font was chosen for (the commonest one that is not punctuation)."""
        real = {code: count for code, count in self.scripts.items() if code not in COMMON}
        pool = real or self.scripts
        return max(pool, key=pool.get) if pool else None

    @property
    def rtl(self) -> bool:
        return self.script in RTL_SCRIPTS


@dataclass
class Plan:
    main: str
    choices: dict[str, Choice]                      # key -> font
    candidates: dict[int, list[str]]                # code point -> keys that can draw it, best first
    uncovered: dict[int, int]                       # code point -> occurrences no font can draw
    common: set[int]                                # code points of Common/Inherited script
    emoji: set[int] = field(default_factory=set)    # emoji the main font lacks (drawn in colour, not by these fonts)
    pictures: dict[str, str] = field(default_factory=dict)  # emoji sequence -> PNG file, for LaTeX
    boxes: set[int] = field(default_factory=set)    # characters drawn as a black box (missing: box)
    words: bool = False                             # fallback fonts take whole words (fallback: word)
    cover: dict[str, set[int]] = field(default_factory=dict)  # key -> the document's characters it draws
    code_candidates: dict[int, list[str]] = field(default_factory=dict)  # the same, for code (lacking in the monofont)
    code_common: set[int] = field(default_factory=set)
    code_boxes: set[int] = field(default_factory=set)

    def __bool__(self) -> bool:
        return bool(self.choices) or bool(self.pictures) or bool(self.boxes) or bool(self.code_boxes)

    def add_code(self, code: "Plan") -> None:
        """Take in the plan of the document's code, made against its monofont: the fonts it needs join
        this plan's, and the Lua filter sets them in inline code and code blocks (LaTeX only)."""
        remap: dict[str, str] = {}
        for key, choice in code.choices.items():
            for existing_key, existing in self.choices.items():
                if existing.family == choice.family:
                    remap[key] = existing_key
                    break
            else:
                new_key = _key(len(self.choices))
                remap[key] = new_key
                choice.key = new_key
                self.choices[new_key] = choice
        self.code_candidates = {code_point: [remap[key] for key in keys] for code_point, keys in code.candidates.items()}
        self.code_common = set(code.common)

    def describe(self) -> list[str]:
        """One line per font: what it was chosen for."""
        lines = []
        for choice in self.choices.values():
            names = sorted({SCRIPT_NAMES.get(code, code) for code in choice.scripts if code not in COMMON}
                           or {SCRIPT_NAMES.get(code, code) for code in choice.scripts})
            count = sum(1 for keys in self.candidates.values() if keys and keys[0] == choice.key)
            if not count:
                continue  # a font only the code needs (code in ... lacks ...)
            lines.append(f"{', '.join(names)} -> {choice.family} ({count} character{'s' if count != 1 else ''})")
        return lines

    def describe_uncovered(self, limit: int = 12) -> str:
        shown = []
        for code_point in sorted(self.uncovered)[:limit]:
            try:
                name = unicodedata.name(chr(code_point))
            except ValueError:
                name = "unnamed"
            shown.append(f"U+{code_point:04X} {chr(code_point)} {name}")
        more = len(self.uncovered) - len(shown)
        return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")

    # -- LaTeX ---------------------------------------------------------------------

    def latex_header(self) -> str:
        lines = [
            "% pdfmd: fonts for the characters the main font does not have (pdfmd --help, \"Unicode\")",
            r"\makeatletter",
            r"\providecommand{\texorpdfstring}[2]{#1}",
            r"\ifdefined\directlua",
            r"  \newcommand{\pdfmd@rtl}[1]{{\textdir TRT #1}}",
            r"\else",
            r"  \TeXXeTstate=1",
            r"  \newcommand{\pdfmd@rtl}[1]{\beginR #1\endR}",
            r"\fi",
        ]
        for choice in self.choices.values():
            lines.append(_font_line(choice))
        if self.boxes or self.code_boxes:
            lines.append(r"\providecommand{\pdfmdbox}{\rule[-0.1ex]{0.55em}{0.75em}}")
        if self.code_candidates or self.code_boxes:
            lines.append(r"\usepackage{fancyvrb}")
        if self.pictures:
            lines += [r"\usepackage{graphicx}",
                      r"\providecommand{\pdfmdemoji}[1]{\raisebox{-0.2em}{\includegraphics[height=1.1em]{#1}}}"]
        lines += [
            r"\DeclareRobustCommand{\pdfmdrun}[2]{\texorpdfstring{{\csname pdfmdf#1\endcsname #2}}{#2}}",
            r"\DeclareRobustCommand{\pdfmdrunrtl}[2]{\texorpdfstring"
            r"{\pdfmd@rtl{{\csname pdfmdf#1\endcsname #2}}}{#2}}",
            r"\makeatother",
            "",
        ]
        return "\n".join(lines)

    def lua_filter(self) -> str:
        """The Pandoc filter: wraps each run of characters in its font's switch (LaTeX only)."""
        entries = ", ".join(f'[{code}]={{{", ".join(chr(34) + key + chr(34) for key in keys)}}}'
                            for code, keys in sorted(self.candidates.items()) if keys)
        common = ", ".join(f"[{code}]=true" for code in sorted(self.common) if self.candidates.get(code))
        rtl = ", ".join(f'{choice.key}=true' for choice in self.choices.values() if choice.rtl)
        sequences = ", ".join("[%s]=%s" % (_lua_string(sequence), _lua_string(_tex_option_path(path)))
                              for sequence, path in sorted(self.pictures.items()))
        first = ", ".join(f"[{code}]=true" for code in sorted({ord(sequence[0]) for sequence in self.pictures}))
        longest = max((len(sequence) for sequence in self.pictures), default=1)
        families = ", ".join(f'{choice.key}="{choice.family}"' for choice in self.choices.values())
        langs = ", ".join(f'{choice.key}="{choice.lang}"' for choice in self.choices.values() if choice.lang)
        code_entries = ", ".join(f'[{code}]={{{", ".join(chr(34) + key + chr(34) for key in keys)}}}'
                                 for code, keys in sorted(self.code_candidates.items()) if keys)
        code_common = ", ".join(f"[{code}]=true" for code in sorted(self.code_common) if self.code_candidates.get(code))
        code_boxes = ", ".join(f"[{code}]=true" for code in sorted(self.code_boxes))
        boxes = ", ".join(f"[{code}]=true" for code in sorted(self.boxes))
        covers = ", ".join("%s={%s}" % (key, ", ".join(f"[{code}]=true" for code in sorted(codes)))
                           for key, codes in self.cover.items())
        return (LUA_FILTER.replace("@CODECANDIDATES@", code_entries).replace("@CODECOMMON@", code_common)
                .replace("@CODEBOXES@", code_boxes).replace("@BOXES@", boxes).replace("@WORDS@", "true" if self.words else "false")
                .replace("@COVER@", covers).replace("@CANDIDATES@", entries).replace("@COMMON@", common).replace("@RTL@", rtl)
                .replace("@FAMILIES@", families).replace("@LANGS@", langs).replace("@SEQUENCES@", sequences)
                .replace("@EMOJIFIRST@", first).replace("@LONGEST@", str(longest)))


# Serifs tried, after the preferred one, as the main font of a document whose own script the
# preferred font cannot fully draw (STIX Two Text has no Kazakh Cyrillic, for one).
MAIN_CANDIDATES = ("Noto Serif", "PT Serif", "Source Serif 4", "DejaVu Serif")


def dominant_script(text: str) -> str | None:
    """The script most of the letters of ``text`` are in."""
    counts: dict[str, int] = {}
    for character in text:
        if unicodedata.category(character).startswith("L"):
            script = script_of(ord(character))
            counts[script] = counts.get(script, 0) + 1
    return max(counts, key=counts.get) if counts else None


def choose_main_font(text: str, preferred: str, index: FontIndex) -> str:
    """``preferred``, unless another serif draws the document's own script better.

    Mixing fonts inside a word looks wrong, so a document written mostly in one script should
    not have the odd letter of it come from a fallback: when the preferred font misses letters
    of the script most of the text is in, the first installed candidate that has them all
    becomes the main font (the best one if none does)."""
    script = dominant_script(text)
    if script is None or index.regular(preferred) is None:
        return preferred
    letters = {ord(c) for c in set(text) if unicodedata.category(c).startswith(("L", "M"))
               and script_of(ord(c)) in (script, "Zinh") and not is_neutral(ord(c))}
    if not letters:
        return preferred

    def score(family: str) -> int:
        face = index.regular(family)
        return len(letters & coverage(face.path, face.index)) if face is not None else -1

    best, best_score = preferred, score(preferred)
    if best_score == len(letters):
        return preferred
    for family in MAIN_CANDIDATES:
        if index.static(family) and score(family) > best_score:
            best, best_score = family, score(family)
            if best_score == len(letters):
                break
    return best


def choose_document_font(text: str, base: str, index: FontIndex) -> str:
    """The installed font that draws the most of ``text``: ``base`` unless another does better
    (fallback: document -- one font for everything, the old retry-with-DejaVu behaviour)."""
    wanted = {ord(c) for c in set(text) if ord(c) > 0x20 and not is_neutral(ord(c))}

    def score(family: str) -> int:
        face = index.regular(family)
        return len(wanted & coverage(face.path, face.index)) if face is not None else -1

    best, best_score = base, score(base)
    for family in dict.fromkeys((*MAIN_CANDIDATES, "DejaVu Serif", "DejaVu Sans", "Noto Sans", "Arial Unicode MS")):
        if family != base and index.static(family) and score(family) > best_score:
            best, best_score = family, score(family)
    return best


def _lua_string(text: str) -> str:
    """A Lua string literal for ``text``, every non-ASCII character as a \\u{...} escape."""
    out = []
    for character in text:
        if character in '"\\':
            out.append("\\" + character)
        elif 0x20 <= ord(character) < 0x7F:
            out.append(character)
        else:
            out.append("\\u{%X}" % ord(character))
    return '"' + "".join(out) + '"'


def _tex_option_path(path: str) -> str:
    return path.replace("\\", "/")


def _font_line(choice: Choice) -> str:
    options: list[str] = []
    script = FONTSPEC_SCRIPTS.get(choice.script or "")
    if script:
        options.append(f"Script={script}")
    options.append("Scale=MatchLowercase")  # the fallback's x-height follows the main font's
    face = choice.face
    if face.managed:
        directory = _tex_option_path(str(Path(face.path).parent)) + "/"
        options.append(f"Path={{{directory}}}")
        for kind, option in (("bold", "BoldFont"), ("italic", "ItalicFont"), ("bolditalic", "BoldItalicFont")):
            other = choice.styles.get(kind)
            if other is not None:
                options.append(f"{option}={{{Path(other.path).name}}}")
        name = Path(face.path).name
    else:
        name = choice.family
    return rf"\newfontfamily\pdfmdf{choice.key}[{','.join(options)}]{{{name}}}"


def _key(number: int) -> str:
    letters = ""
    number += 1
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def plan_text(text: str, main_family: str, index: FontIndex, document_language: str | None = None,
              skip: frozenset[int] = frozenset(), fonts: bool = True, words: bool = False) -> Plan | None:
    """The fonts ``text`` needs besides ``main_family``, or None when the main font
    cannot be found (so nothing can be said about what it lacks). With ``fonts`` false nothing is
    looked for: every character the main font lacks is reported as one no font draws."""
    main = index.regular(main_family)
    if main is None:
        return None
    covered = coverage(main.path, main.index)
    wanted = {ord(character) for character in set(text)
              if ord(character) > 0x20 and not is_neutral(ord(character))}
    missing = sorted(code_point for code_point in wanted if code_point not in covered and code_point not in skip)
    # Emoji are drawn in colour by a colour font (or as pictures), not by the per-script fonts.
    asked = {ord(text[number - 1]) for number, character in enumerate(text)
             if ord(character) == VARIATION_EMOJI and number}
    emoji = {code_point for code_point in missing if is_emoji_code_point(code_point)
             or (can_be_emoji(code_point) and code_point in asked)}
    # A text symbol that is only sometimes asked for as a picture (the heart with U+FE0F)
    # still goes through the fonts for the occurrences that are not.
    missing = [code_point for code_point in missing if not is_emoji_code_point(code_point)]
    if not fonts:
        return Plan(main_family, {}, {}, {code_point: text.count(chr(code_point))
                                        for code_point in sorted({*missing, *emoji})}, set())
    if not missing:
        return Plan(main_family, {}, {}, {}, set(), emoji)
    cjk = han_language(text, document_language)

    primary: dict[int, str] = {}
    uncovered: dict[int, int] = {}

    def pick(code_point: int, extra: tuple[str, ...] = ()) -> str | None:
        installed = [family for family in chain_for(code_point, script_of(code_point), cjk, document_language)
                     if index.covers(family, code_point)]
        # A variable font would be set at its thinnest weight; use one only if nothing else will do.
        better = [family for family in installed if index.static(family)]
        found = (better or installed or [family for family in extra if index.covers(family, code_point)])
        return found[0] if found else None

    for code_point in missing:
        if script_of(code_point) not in COMMON:
            family = pick(code_point)
            if family:
                primary[code_point] = family
            else:
                uncovered[code_point] = text.count(chr(code_point))
    # A punctuation mark or a combining mark takes the font of the text beside it when
    # that font has the glyph, so one Arabic phrase is one run, not three.
    used = list(dict.fromkeys(primary.values()))
    common: set[int] = set()
    for code_point in missing:
        if script_of(code_point) in COMMON:
            family = pick(code_point, tuple(used))
            if family:
                primary[code_point] = family
                common.add(code_point)
            else:
                uncovered[code_point] = text.count(chr(code_point))

    families = list(dict.fromkeys([*used, *(primary[code_point] for code_point in sorted(common))]))
    choices: dict[str, Choice] = {}
    keys: dict[str, str] = {}
    for number, family in enumerate(families):
        face = index.regular(family)
        assert face is not None
        key = _key(number)
        keys[family] = key
        choices[key] = Choice(key, family, face, {}, index.styles(face) if face.managed else {})

    candidates: dict[int, list[str]] = {}
    for code_point, family in primary.items():
        found = [keys[family]]
        if code_point in common:
            found += [keys[other] for other in used if other != family and index.covers(other, code_point)]
        candidates[code_point] = found
        script = script_of(code_point)
        counts = choices[keys[family]].scripts
        counts[script] = counts.get(script, 0) + 1
    for choice in choices.values():
        if any(code in CJK_SCRIPTS for code in choice.scripts):
            choice.lang = {"sc": "zh", "tc": "zh", "ja": "ja", "ko": "ko"}[cjk]
    plan = Plan(main_family, choices, candidates, uncovered, common, emoji, words=words)
    if words:
        for key, choice in choices.items():
            plan.cover[key] = {code_point for code_point in wanted
                               if code_point in coverage(choice.face.path, choice.face.index)}
    return plan


LUA_FILTER = r'''-- generated by pdfmd (pdfmd_unicode): sets text the main font cannot draw in a font of its own.
local CANDIDATES = { @CANDIDATES@ }
local COMMON = { @COMMON@ }
local RTL = { @RTL@ }
local FAMILIES = { @FAMILIES@ }
local LANGS = { @LANGS@ }
local SEQUENCES = { @SEQUENCES@ }   -- emoji sequence -> picture (LaTeX only)
local EMOJI_FIRST = { @EMOJIFIRST@ }
local LONGEST = @LONGEST@
local BOXES = { @BOXES@ }        -- characters drawn as a black box
local CODE_CANDIDATES = { @CODECANDIDATES@ }   -- the same for code, against the monofont
local CODE_COMMON = { @CODECOMMON@ }
local CODE_BOXES = { @CODEBOXES@ }
local WORDS = @WORDS@            -- fallback fonts take whole words
local COVER = { @COVER@ }        -- key -> the characters of the document its font draws

-- "latex" (a font switch), "typst" (#text) or "html" (a styled span); nil leaves other formats alone
local function mode()
  if FORMAT == "latex" or FORMAT == "beamer" then return "latex" end
  if FORMAT == "typst" then return "typst" end
  if FORMAT:match("^html") or FORMAT == "epub" or FORMAT:match("^epub") then return "html" end
  return nil
end

local function plain_neutral(char)
  return char:match("^[%p%d]$") ~= nil
end

local function has(list, key)
  for _, candidate in ipairs(list) do
    if candidate == key then return true end
  end
  return false
end

local function black_box(kind)
  if kind == "latex" then return pandoc.RawInline("latex", "\\pdfmdbox{}") end
  if kind == "typst" then
    return pandoc.RawInline("typst", "#box(width: 0.55em, height: 0.75em, fill: black)")
  end
  return pandoc.RawInline("html",
    '<span style="display:inline-block;width:.55em;height:.75em;background:#000"></span>')
end

local function wrap(kind, key, items)
  if kind == "latex" then
    local out = { pandoc.RawInline("latex", (RTL[key] and "\\pdfmdrunrtl{" or "\\pdfmdrun{") .. key .. "}{") }
    for _, item in ipairs(items) do out[#out + 1] = item end
    out[#out + 1] = pandoc.RawInline("latex", "}")
    return out
  elseif kind == "typst" then
    local options = 'font: ("' .. FAMILIES[key] .. '",)'
    if LANGS[key] then options = options .. ', lang: "' .. LANGS[key] .. '"' end
    local out = { pandoc.RawInline("typst", "#text(" .. options .. ")[") }
    for _, item in ipairs(items) do out[#out + 1] = item end
    out[#out + 1] = pandoc.RawInline("typst", "]")
    return out
  else
    local attributes = { style = "font-family: '" .. FAMILIES[key] .. "'" }
    if LANGS[key] then attributes.lang = LANGS[key] end
    return { pandoc.Span(items, pandoc.Attr("", {}, attributes)) }
  end
end

-- Code (LaTeX only): split `text` into runs of one font, black boxes and plain text
local function code_segments(text)
  local segments, current, previous = {}, nil, nil
  for _, code in utf8.codes(text) do
    local char, key, box = utf8.char(code), nil, false
    if CODE_BOXES[code] then
      box = true
    elseif CODE_CANDIDATES[code] then
      local candidates = CODE_CANDIDATES[code]
      key = candidates[1]
      if CODE_COMMON[code] and previous and has(candidates, previous) then key = previous end
    end
    if box then
      segments[#segments + 1] = { box = true }
      current = nil
    elseif current and current.key == key then
      current.text = current.text .. char
    else
      current = { key = key, text = char }
      segments[#segments + 1] = current
    end
    previous = key
  end
  return segments
end

local function has_code_trouble(text)
  for _, code in utf8.codes(text) do
    if CODE_CANDIDATES[code] or CODE_BOXES[code] then return true end
  end
  return false
end

local function verbatim_escape(text)
  local out = {}
  for _, code in utf8.codes(text) do
    local char = utf8.char(code)
    if char == "\\" then out[#out + 1] = "\\textbackslash{}"
    elseif char == "{" then out[#out + 1] = "\\{"
    elseif char == "}" then out[#out + 1] = "\\}"
    else out[#out + 1] = char end
  end
  return table.concat(out)
end

function Code(element)
  if mode() ~= "latex" or not has_code_trouble(element.text) then return nil end
  local out = {}
  for _, segment in ipairs(code_segments(element.text)) do
    if segment.box then
      out[#out + 1] = pandoc.RawInline("latex", "\\pdfmdbox{}")
    elseif segment.key then
      out[#out + 1] = pandoc.RawInline("latex", (RTL[segment.key] and "\\pdfmdrunrtl{" or "\\pdfmdrun{")
                                       .. segment.key .. "}{")
      out[#out + 1] = pandoc.Str(segment.text)
      out[#out + 1] = pandoc.RawInline("latex", "}")
    else
      out[#out + 1] = pandoc.Code(segment.text, element.attr)
    end
  end
  return out
end

function CodeBlock(element)
  if mode() ~= "latex" or not has_code_trouble(element.text) then return nil end
  local body = {}
  for _, segment in ipairs(code_segments(element.text)) do
    if segment.box then
      body[#body + 1] = "\\pdfmdbox{}"
    elseif segment.key then
      body[#body + 1] = (RTL[segment.key] and "\\pdfmdrunrtl{" or "\\pdfmdrun{") .. segment.key .. "}{"
                        .. verbatim_escape(segment.text) .. "}"
    else
      body[#body + 1] = verbatim_escape(segment.text)
    end
  end
  return pandoc.RawBlock("latex", "\\begin{Verbatim}[commandchars=\\\\\\{\\}]\n" .. table.concat(body)
                                  .. "\n\\end{Verbatim}")
end

function Inlines(inlines)
  local kind = mode()
  if not kind then return nil end
  local atoms, seen = {}, false
  for _, element in ipairs(inlines) do
    if element.t == "Str" then
      local codes = {}
      for _, code in utf8.codes(element.text) do codes[#codes + 1] = code end
      local position = 1
      while position <= #codes do
        local code = codes[position]
        local matched = false
        if kind == "latex" and EMOJI_FIRST[code] then
          for length = math.min(LONGEST, #codes - position + 1), 1, -1 do
            local file = SEQUENCES[utf8.char(table.unpack(codes, position, position + length - 1))]
            if file then
              atoms[#atoms + 1] = { element = pandoc.RawInline("latex", "\\pdfmdemoji{" .. file .. "}") }
              seen, matched, position = true, true, position + length
              break
            end
          end
        end
        if not matched and BOXES[code] then
          atoms[#atoms + 1] = { element = black_box(kind) }
          seen, matched, position = true, true, position + 1
        end
        if not matched then
          local candidates = CANDIDATES[code]
          if candidates then seen = true end
          atoms[#atoms + 1] = { char = utf8.char(code), code = code, candidates = candidates }
          position = position + 1
        end
      end
    elseif element.t == "Space" or element.t == "SoftBreak" then
      atoms[#atoms + 1] = { element = element, neutral = true }
    else
      atoms[#atoms + 1] = { element = element }
    end
  end
  if not seen then return nil end

  local function passable(atom)
    return atom.neutral or (atom.char and not atom.candidates and plain_neutral(atom.char))
  end

  for _, atom in ipairs(atoms) do
    if atom.candidates and not COMMON[atom.code] then atom.key = atom.candidates[1] end
  end
  for position, atom in ipairs(atoms) do
    if atom.candidates and COMMON[atom.code] then
      local chosen
      for step = position - 1, 1, -1 do
        local other = atoms[step]
        if other.key then
          if has(atom.candidates, other.key) then chosen = other.key end
          break
        end
        if not passable(other) then break end
      end
      if not chosen then
        for step = position + 1, #atoms do
          local other = atoms[step]
          if other.key then
            if has(atom.candidates, other.key) then chosen = other.key end
            break
          end
          if not passable(other) then break end
        end
      end
      atom.key = chosen or atom.candidates[1]
    end
  end

  if WORDS then
    -- a word that has any character in a fallback font goes wholly into one font that draws all of it
    local first = 1
    while first <= #atoms do
      if atoms[first].char then
        local last = first
        while atoms[last + 1] and atoms[last + 1].char do last = last + 1 end
        local keys, present = {}, {}
        for step = first, last do
          local key = atoms[step].key
          if key and not present[key] then present[key] = true; keys[#keys + 1] = key end
        end
        for _, key in ipairs(keys) do
          local whole = true
          for step = first, last do
            if not (COVER[key] and COVER[key][atoms[step].code]) then whole = false; break end
          end
          if whole then
            for step = first, last do atoms[step].key = key end
            break
          end
        end
        first = last + 1
      else
        first = first + 1
      end
    end
  end

  local out, buffer = {}, {}
  local function flush(target)
    if #buffer > 0 then
      target[#target + 1] = pandoc.Str(table.concat(buffer))
      buffer = {}
    end
  end
  local position, total = 1, #atoms
  while position <= total do
    local atom = atoms[position]
    if atom.key then
      local key, last = atom.key, position
      local step = position + 1
      while step <= total do
        local other = atoms[step]
        if other.key == key then
          last = step
        elseif other.key or not passable(other) then
          break
        end
        step = step + 1
      end
      flush(out)
      local items = {}
      for inner = position, last do
        local part = atoms[inner]
        if part.element then
          flush(items)
          items[#items + 1] = part.element
        else
          buffer[#buffer + 1] = part.char
        end
      end
      flush(items)
      for _, item in ipairs(wrap(kind, key, items)) do out[#out + 1] = item end
      position = last + 1
    else
      if atom.element then
        flush(out)
        out[#out + 1] = atom.element
      else
        buffer[#buffer + 1] = atom.char
      end
      position = position + 1
    end
  end
  flush(out)
  return out
end
'''
