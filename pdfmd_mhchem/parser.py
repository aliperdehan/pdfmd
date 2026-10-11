"""mhchem's \\ce and \\pu, parsed as LaTeX's mhchem parses them, and written as TeX.

A Python port of mhchemParser.ts 4.2.1 (https://github.com/mhchem/mhchemParser), the parser MathJax and KaTeX use:

    Copyright (c) 2015-2023 Martin Hensel

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

Changes (pdfmd, 2026): translated from TypeScript to Python, statement by statement, so that `to_tex()` gives the
same TeX as `mhchemParser.toTex()` for every input (tests/test_mhchem.py checks it on mhchem's own tests and on
real documents). JavaScript's object order is kept where it decides the order of transitions (integer-like keys
first), and its regular expressions are Python ones with the same meaning (`\\Z` for an end-of-input `$`). The
functions keep the original names, so the two read side by side.
"""

from __future__ import annotations

import re


class MhchemError(Exception):
    """mhchem could not read the input (an unbalanced brace, an unknown bond); the message is mhchem's own."""


#
# _mhchemCreateTransitions: { 'letter': { 'state': { action_: 'output' } } } -> { 'state': [ {pattern, task} ] },
# with 'a|b' expanded to 'a' and 'b' (patterns and states)
#
def _js_keys(mapping: dict) -> list:
    """The keys in JavaScript's order: integer-like keys first, ascending, then the others as inserted."""
    numeric = sorted((key for key in mapping if re.fullmatch(r"0|[1-9][0-9]*", key)), key=int)
    return numeric + [key for key in mapping if key not in numeric]


def _create_transitions(raw: dict) -> dict:
    transitions: dict = {}
    for pattern in _js_keys(raw):
        for state in _js_keys(raw[pattern]):
            for name in state.split("|"):
                transitions[name] = []
    for pattern in _js_keys(raw):
        for state in _js_keys(raw[pattern]):
            task = raw[pattern][state]
            actions = task["action_"] if isinstance(task["action_"], list) else [task["action_"]]
            task = dict(task, action_=[{"type_": item} if isinstance(item, str) else item for item in actions])
            for name in state.split("|"):
                for single in pattern.split("|"):
                    if name == "*":
                        for target in transitions:
                            transitions[target].append({"pattern": single, "task": task})
                    else:
                        transitions[name].append({"pattern": single, "task": task})
    return transitions


#
# patterns
#
GREEK = (r"alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|omicron|pi|rho|sigma|tau|upsilon|"
         r"phi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega")
GREEK_LOWER = (r"alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|omicron|pi|rho|sigma|tau|"
               r"upsilon|phi|chi|psi|omega")


def _find_observe_groups(input_, beg_excl, beg_incl, end_incl, end_excl, beg2_excl=None, beg2_incl=None,
                         end2_incl=None, end2_excl=None, combine=False):
    def _match(text, pattern):
        if isinstance(pattern, str):
            return pattern if text.startswith(pattern) else None
        found = pattern.match(text)
        return found.group(0) if found else None

    def _find(text, i, end_chars):
        braces = 0
        while i < len(text):
            a = text[i]
            found = _match(text[i:], end_chars)
            if found is not None and braces == 0:
                return i, i + len(found)
            elif a == "{":
                braces += 1
            elif a == "}":
                if braces == 0:
                    raise MhchemError("Extra close brace or missing open brace")
                braces -= 1
            i += 1
        return None

    found = _match(input_, beg_excl)
    if found is None:
        return None
    input_ = input_[len(found):]
    found = _match(input_, beg_incl)
    if found is None:
        return None
    ends = _find(input_, len(found), end_incl or end_excl)
    if ends is None:
        return None
    match1 = input_[:(ends[1] if end_incl else ends[0])]
    if not (beg2_excl or beg2_incl):
        return {"match_": match1, "remainder": input_[ends[1]:]}
    group2 = _find_observe_groups(input_[ends[1]:], beg2_excl, beg2_incl, end2_incl, end2_excl)
    if group2 is None:
        return None
    pair = [match1, group2["match_"]]
    return {"match_": "".join(pair) if combine else pair, "remainder": group2["remainder"]}


def _number_e(input_):
    found = re.match(r"(\+\-|\+/\-|\+|\-|\\pm\s?)?([0-9]+(?:[,.][0-9]+)?|[0-9]*(?:\.[0-9]+))?"
                     r"(\((?:[0-9]+(?:[,.][0-9]+)?|[0-9]*(?:\.[0-9]+))\))?"
                     r"(?:(?:([eE])|\s*(\*|x|\\times|\u00D7)\s*10\^)([+\-]?[0-9]+|\{[+\-]?[0-9]+\}))?", input_)
    if found and found.group(0):
        return {"match_": list(found.groups()), "remainder": input_[found.end():]}
    return None


def _state_of_aggregation(input_):
    a = _find_observe_groups(input_, "", re.compile(r"\([a-z]{1,3}(?=[),])"), ")", "")
    if a and re.match(r"(\Z|[\s,;)\]}])", a["remainder"]):
        return a
    found = re.match(r"(?:\((?:\\ca\s?)?\$[amothc]\$\))", input_)
    if found:
        return {"match_": found.group(0), "remainder": input_[found.end():]}
    return None


def _amount(input_):
    found = re.match(r"(?:(?:(?:\([+\-]?[0-9]+/[0-9]+\)|[+\-]?(?:[0-9]+|\$[a-z]\$|[a-z])/[0-9]+|[+\-]?[0-9]+[.,][0-9]+|"
                     r"[+\-]?\.[0-9]+|[+\-]?[0-9]+)(?:[a-z](?=\s*[A-Z]))?)|[+\-]?[a-z](?=\s*[A-Z])|\+(?!\s))", input_)
    if found:
        return {"match_": found.group(0), "remainder": input_[found.end():]}
    a = _find_observe_groups(input_, "", "$", "$", "")
    if a:
        found = re.match(r"\$(?:\(?[+\-]?(?:[0-9]*[a-z]?[+\-])?[0-9]*[a-z](?:[+\-][0-9]*[a-z]?)?\)?|\+|-)\$\Z", a["match_"])
        if found:
            return {"match_": found.group(0), "remainder": input_[found.end():]}
    return None


def _formula(input_):
    if re.match(r"\([a-z]+\)\Z", input_):
        return None
    found = re.match(r"(?:[a-z]|(?:[0-9 +\-,.()]+[a-z])+[0-9 +\-,.()]*|(?:[a-z][0-9 +\-,.()]+)+[a-z]?)\Z", input_)
    if found:
        return {"match_": found.group(0), "remainder": input_[found.end():]}
    return None


def _observe(*arguments, **keywords):
    return lambda input_: _find_observe_groups(input_, *arguments, **keywords)


COMMAND_BRACE = re.compile(r"\\[a-zA-Z]+\{")

PATTERNS = {
    "empty": re.compile(r"\Z"),
    "else": re.compile(r"."),
    "else2": re.compile(r"."),
    "space": re.compile(r"\s"),
    "space A": re.compile(r"\s(?=[A-Z\\$])"),
    "space$": re.compile(r"\s\Z"),
    "a-z": re.compile(r"[a-z]"),
    "x": re.compile(r"x"),
    "x$": re.compile(r"x\Z"),
    "i$": re.compile(r"i\Z"),
    "letters": re.compile(r"(?:[a-zA-Z\u03B1-\u03C9\u0391-\u03A9?@]|(?:\\(?:" + GREEK + r")(?:\s+|\{\}|(?![a-zA-Z]))))+"),
    "\\greek": re.compile(r"\\(?:" + GREEK + r")(?:\s+|\{\}|(?![a-zA-Z]))"),
    "one lowercase latin letter $": re.compile(r"(?:([a-z])(?:\Z|[^a-zA-Z]))\Z"),
    "$one lowercase latin letter$ $": re.compile(r"\$(?:([a-z])(?:\Z|[^a-zA-Z]))\$\Z"),
    "one lowercase greek letter $": re.compile(r"(?:\$?[\u03B1-\u03C9]\$?|\$?\\(?:" + GREEK_LOWER + r")\s*\$?)"
                                               r"(?:\s+|\{\}|(?![a-zA-Z]))\Z"),
    "digits": re.compile(r"[0-9]+"),
    "-9.,9": re.compile(r"[+\-]?(?:[0-9]+(?:[,.][0-9]+)?|[0-9]*(?:\.[0-9]+))"),
    "-9.,9 no missing 0": re.compile(r"[+\-]?[0-9]+(?:[.,][0-9]+)?"),
    "(-)(9.,9)(e)(99)": _number_e,
    "(-)(9)^(-9)": re.compile(r"(\+\-|\+/\-|\+|\-|\\pm\s?)?([0-9]+(?:[,.][0-9]+)?|[0-9]*(?:\.[0-9]+)?)"
                              r"\^([+\-]?[0-9]+|\{[+\-]?[0-9]+\})"),
    "state of aggregation $": _state_of_aggregation,
    "_{(state of aggregation)}$": re.compile(r"_\{(\([a-z]{1,3}\))\}"),
    "{[(": re.compile(r"(?:\\\{|\[|\()"),
    ")]}": re.compile(r"(?:\)|\]|\\\})"),
    ", ": re.compile(r"[,;]\s*"),
    ",": re.compile(r"[,;]"),
    ".": re.compile(r"[.]"),
    ". __* ": re.compile(r"([.\u22C5\u00B7\u2022]|[*])\s*"),
    "...": re.compile(r"\.\.\.(?=\Z|[^.])"),
    "^{(...)}": _observe("^{", "", "", "}"),
    "^($...$)": _observe("^", "$", "$", ""),
    "^a": re.compile(r"\^([0-9]+|[^\\_])"),
    "^\\x{}{}": _observe("^", COMMAND_BRACE, "}", "", "", "{", "}", "", True),
    "^\\x{}": _observe("^", COMMAND_BRACE, "}", ""),
    "^\\x": re.compile(r"\^(\\[a-zA-Z]+)\s*"),
    "^(-1)": re.compile(r"\^(-?\d+)"),
    "'": re.compile(r"'"),
    "_{(...)}": _observe("_{", "", "", "}"),
    "_($...$)": _observe("_", "$", "$", ""),
    "_9": re.compile(r"_([+\-]?[0-9]+|[^\\])"),
    "_\\x{}{}": _observe("_", COMMAND_BRACE, "}", "", "", "{", "}", "", True),
    "_\\x{}": _observe("_", COMMAND_BRACE, "}", ""),
    "_\\x": re.compile(r"_(\\[a-zA-Z]+)\s*"),
    "^_": re.compile(r"(?:\^(?=_)|_(?=\^)|[\^_]\Z)"),
    "{}^": re.compile(r"\{\}(?=\^)"),
    "{}": re.compile(r"\{\}"),
    "{...}": _observe("", "{", "}", ""),
    "{(...)}": _observe("{", "", "", "}"),
    "$...$": _observe("", "$", "$", ""),
    "${(...)}$__$(...)$": lambda input_: (_find_observe_groups(input_, "${", "", "", "}$")
                                          or _find_observe_groups(input_, "$", "", "", "$")),
    "=<>": re.compile(r"[=<>]"),
    "#": re.compile(r"[#\u2261]"),
    "+": re.compile(r"\+"),
    "-$": re.compile(r"-(?=[\s_},;\]/]|\Z|\([a-z]+\))"),
    "-9": re.compile(r"-(?=[0-9])"),
    "- orbital overlap": re.compile(r"-(?=(?:[spd]|sp)(?:\Z|[\s,;)\]}]))"),
    "-": re.compile(r"-"),
    "pm-operator": re.compile(r"(?:\\pm|\$\\pm\$|\+-|\+/-)"),
    "operator": re.compile(r"(?:\+|(?:[\-=<>]|<<|>>|\\approx|\$\\approx\$)(?=\s|\Z|-?[0-9]))"),
    "arrowUpDown": re.compile(r"(?:v|\(v\)|\^|\(\^\))(?=\Z|[\s,;)\]}])"),
    "\\bond{(...)}": _observe("\\bond{", "", "", "}"),
    "->": re.compile(r"(?:<->|<-->|->|<-|<=>>|<<=>|<=>|[\u2192\u27F6\u21CC])"),
    "CMT": re.compile(r"[CMT](?=\[)"),
    "[(...)]": _observe("[", "", "", "]"),
    "1st-level escape": re.compile(r"(&|\\\\|\\hline)\s*"),
    "\\,": re.compile(r"(?:\\[, ;:])"),
    "\\x{}{}": _observe("", COMMAND_BRACE, "}", "", "", "{", "}", "", True),
    "\\x{}": _observe("", COMMAND_BRACE, "}", ""),
    "\\ca": re.compile(r"\\ca(?:\s+|(?![a-zA-Z]))"),
    "\\x": re.compile(r"(?:\\[a-zA-Z]+\s*|\\[_&{}%])"),
    "orbital": re.compile(r"(?:[0-9]{1,2}[spdfgh]|[0-9]{0,2}sp)(?=\Z|[^a-zA-Z])"),
    "others": re.compile(r"[/~|]"),
    "\\frac{(...)}": _observe("\\frac{", "", "", "}", "{", "", "", "}"),
    "\\overset{(...)}": _observe("\\overset{", "", "", "}", "{", "", "", "}"),
    "\\underset{(...)}": _observe("\\underset{", "", "", "}", "{", "", "", "}"),
    "\\underbrace{(...)}": _observe("\\underbrace{", "", "", "}_", "{", "", "", "}"),
    "\\color{(...)}": _observe("\\color{", "", "", "}"),
    "\\color{(...)}{(...)}": lambda input_: (
        _find_observe_groups(input_, "\\color{", "", "", "}", "{", "", "", "}")
        or _find_observe_groups(input_, "\\color", "\\", "", re.compile(r"(?=\{)"), "{", "", "", "}")),
    "\\ce{(...)}": _observe("\\ce{", "", "", "}"),
    "\\pu{(...)}": _observe("\\pu{", "", "", "}"),
    "oxidation$": re.compile(r"(?:[+-][IVX]+|(?:\\pm|\$\\pm\$|\+-|\+/-)\s*0)\Z"),
    "d-oxidation$": re.compile(r"(?:[+-]?[IVX]+|(?:\\pm|\$\\pm\$|\+-|\+/-)\s*0)\Z"),
    "1/2$": re.compile(r"[+\-]?(?:[0-9]+|\$[a-z]\$|[a-z])/[0-9]+(?:\$[a-z]\$|[a-z])?\Z"),
    "amount": _amount,
    "amount2": _amount,
    "(KV letters),": re.compile(r"(?:[A-Z][a-z]{0,2}|i)(?=,)"),
    "formula$": _formula,
    "uprightEntities": re.compile(r"(?:pH|pOH|pC|pK|iPr|iBu)(?=\Z|[^a-zA-Z])"),
    "/": re.compile(r"\s*(/)\s*"),
    "//": re.compile(r"\s*(//)\s*"),
    "*": re.compile(r"\s*[*.]\s*"),
}


def match_(name: str, input_: str):
    """None, or {match_, remainder}: match_ is the first group (or the whole match), or the list of the groups when
    there are two or more"""
    pattern = PATTERNS.get(name)
    if pattern is None:
        raise MhchemError(f"mhchem bug P. Please report. ({name})")
    if callable(pattern):
        return pattern(input_)
    found = pattern.match(input_)
    if found:
        groups = found.groups()
        if len(groups) > 1:
            return {"match_": list(groups), "remainder": input_[found.end():]}
        return {"match_": (groups[0] if groups and groups[0] else found.group(0)), "remainder": input_[found.end():]}
    return None


def _concat(a: list, b) -> None:
    if b:
        if isinstance(b, list):
            a.extend(b)
        else:
            a.append(b)


#
# generic actions
#
def _add(key):
    def action(buffer, m, _option=None):
        buffer[key] = (buffer.get(key) or "") + m
    return action


def _one_half(_buffer, m, _option=None):
    ret = []
    if re.match(r"[+\-]", m):
        ret.append(m[0])
        m = m[1:]
    n = list(re.match(r"([0-9]+|\$[a-z]\$|[a-z])/([0-9]+)(\$[a-z]\$|[a-z])?\Z", m).groups())
    n[0] = n[0].replace("$", "")
    ret.append({"type_": "frac", "p1": n[0], "p2": n[1]})
    if n[2]:
        ret.append({"type_": "tex-math", "p1": n[2].replace("$", "")})
    return ret


ACTIONS = {
    "a=": _add("a"), "b=": _add("b"), "p=": _add("p"), "o=": _add("o"),
    "o=+p1": lambda buffer, _m, a=None: buffer.__setitem__("o", (buffer.get("o") or "") + a),
    "q=": _add("q"), "d=": _add("d"), "rm=": _add("rm"), "text=": _add("text_"),
    "insert": lambda _buffer, _m, a=None: {"type_": a},
    "insert+p1": lambda _buffer, m, a=None: {"type_": a, "p1": m},
    "insert+p1+p2": lambda _buffer, m, a=None: {"type_": a, "p1": m[0], "p2": m[1]},
    "copy": lambda _buffer, m, _option=None: m,
    "write": lambda _buffer, _m, a=None: a,
    "rm": lambda _buffer, m, _option=None: {"type_": "rm", "p1": m},
    "text": lambda _buffer, m, _option=None: go(m, "text"),
    "tex-math": lambda _buffer, m, _option=None: go(m, "tex-math"),
    "tex-math tight": lambda _buffer, m, _option=None: go(m, "tex-math tight"),
    "bond": lambda _buffer, m, k=None: {"type_": "bond", "kind_": k or m},
    "color0-output": lambda _buffer, m, _option=None: {"type_": "color0", "color": m},
    "ce": lambda _buffer, m, _option=None: go(m, "ce"),
    "pu": lambda _buffer, m, _option=None: go(m, "pu"),
    "1/2": _one_half,
    "9,9": lambda _buffer, m, _option=None: go(m, "9,9"),
}


def _clear(buffer: dict, keep=()) -> None:
    for key in list(buffer):
        if key not in keep:
            del buffer[key]


#
# the \ce machine's own actions
#
def _ce_o_after_d(buffer, m, _option=None):
    if re.match(r"[1-9][0-9]*\Z", buffer.get("d") or ""):
        tmp = buffer.get("d")
        buffer["d"] = None
        ret = _ce_output(buffer, None)
        ret.append({"type_": "tinySkip"})
        buffer["b"] = tmp
    else:
        ret = _ce_output(buffer, None)
    ACTIONS["o="](buffer, m)
    return ret


def _ce_d_kv(buffer, m, _option=None):
    buffer["d"] = m
    buffer["dType"] = "kv"


def _ce_charge_or_bond(buffer, m, _option=None):
    if buffer.get("beginsWithBond"):
        ret: list = []
        _concat(ret, _ce_output(buffer, None))
        _concat(ret, ACTIONS["bond"](buffer, m, "-"))
        return ret
    buffer["d"] = m
    return None


def _ce_minus_after_o_d(buffer, m, is_after_d=None):
    c1 = match_("orbital", buffer.get("o") or "")
    c2 = match_("one lowercase greek letter $", buffer.get("o") or "")
    c3 = match_("one lowercase latin letter $", buffer.get("o") or "")
    c4 = match_("$one lowercase latin letter$ $", buffer.get("o") or "")
    hyphen_follows = m == "-" and bool((c1 and c1["remainder"] == "") or c2 or c3 or c4)
    if (hyphen_follows and not buffer.get("a") and not buffer.get("b") and not buffer.get("p") and not buffer.get("d")
            and not buffer.get("q") and not c1 and c3):
        buffer["o"] = "$" + buffer["o"] + "$"
    ret: list = []
    if hyphen_follows:
        _concat(ret, _ce_output(buffer, None))
        ret.append({"type_": "hyphen"})
    else:
        c1 = match_("digits", buffer.get("d") or "")
        if is_after_d and c1 and c1["remainder"] == "":
            _concat(ret, ACTIONS["d="](buffer, m))
            _concat(ret, _ce_output(buffer, None))
        else:
            _concat(ret, _ce_output(buffer, None))
            _concat(ret, ACTIONS["bond"](buffer, m, "-"))
    return ret


def _ce_a_to_o(buffer, _m=None, _option=None):
    buffer["o"] = buffer.get("a")
    buffer["a"] = None


def _set(key, value):
    def action(buffer, _m=None, _option=None):
        buffer[key] = value
    return action


def _store(key):
    def action(buffer, m, _option=None):
        buffer[key] = m
    return action


def _ce_comma(buffer, m, _option=None):
    a = re.sub(r"\s*\Z", "", m, count=1)
    with_space = a != m
    if with_space and buffer["parenthesisLevel"] == 0:
        return {"type_": "comma enumeration L", "p1": a}
    return {"type_": "comma enumeration M", "p1": a}


def _ce_output(buffer, _m=None, entity_follows=None):
    """entity_follows: None = with nothing else to output, the space just read (buffer.sb) is ignored too; 1 = an entity
    follows, the space is never left out (state 1 only); 2 = 1 + the entity can have an amount, so `a\\,` is written
    instead of making it o (states a|as only)"""
    get = buffer.get
    if not get("r"):
        ret: list | dict = []
        if not get("a") and not get("b") and not get("p") and not get("o") and not get("q") and not get("d") \
                and not entity_follows:
            pass
        else:
            if get("sb"):
                ret.append({"type_": "entitySkip"})
            if not get("o") and not get("q") and not get("d") and not get("b") and not get("p") and entity_follows != 2:
                buffer["o"] = get("a")
                buffer["a"] = None
            elif not get("o") and not get("q") and not get("d") and (get("b") or get("p")):
                buffer["o"] = get("a")
                buffer["d"] = get("b")
                buffer["q"] = get("p")
                buffer["a"] = buffer["b"] = buffer["p"] = None
            else:
                if get("o") and get("dType") == "kv" and match_("d-oxidation$", get("d") or ""):
                    buffer["dType"] = "oxidation"
                elif get("o") and get("dType") == "kv" and not get("q"):
                    buffer["dType"] = None
            ret.append({
                "type_": "chemfive",
                "a": go(get("a"), "a"),
                "b": go(get("b"), "bd"),
                "p": go(get("p"), "pq"),
                "o": go(get("o"), "o"),
                "q": go(get("q"), "pq"),
                "d": go(get("d"), "oxidation" if get("dType") == "oxidation" else "bd"),
                "dType": get("dType"),
            })
    else:
        if get("rdt") == "M":
            rd = go(get("rd"), "tex-math")
        elif get("rdt") == "T":
            rd = [{"type_": "text", "p1": get("rd") or ""}]
        else:
            rd = go(get("rd"), "ce")
        if get("rqt") == "M":
            rq = go(get("rq"), "tex-math")
        elif get("rqt") == "T":
            rq = [{"type_": "text", "p1": get("rq") or ""}]
        else:
            rq = go(get("rq"), "ce")
        ret = {"type_": "arrow", "r": get("r"), "rd": rd, "rq": rq}
    _clear(buffer, ("parenthesisLevel", "beginsWithBond"))
    return ret


def _ce_oxidation_output(_buffer, m, _option=None):
    ret = ["{"]
    _concat(ret, go(m, "oxidation"))
    ret.append("}")
    return ret


def _pair(type_, first="p1", second="p2", machine="ce"):
    return lambda _buffer, m, _option=None: {"type_": type_, first: go(m[0], machine), second: go(m[1], machine)}


CE_ACTIONS = {
    "o after d": _ce_o_after_d,
    "d= kv": _ce_d_kv,
    "charge or bond": _ce_charge_or_bond,
    "- after o/d": _ce_minus_after_o_d,
    "a to o": _ce_a_to_o,
    "sb=true": _set("sb", True),
    "sb=false": _set("sb", False),
    "beginsWithBond=true": _set("beginsWithBond", True),
    "beginsWithBond=false": _set("beginsWithBond", False),
    "parenthesisLevel++": lambda buffer, _m=None, _o=None: buffer.__setitem__("parenthesisLevel",
                                                                                buffer["parenthesisLevel"] + 1),
    "parenthesisLevel--": lambda buffer, _m=None, _o=None: buffer.__setitem__("parenthesisLevel",
                                                                                buffer["parenthesisLevel"] - 1),
    "state of aggregation": lambda _buffer, m, _option=None: {"type_": "state of aggregation", "p1": go(m, "o")},
    "comma": _ce_comma,
    "output": _ce_output,
    "oxidation-output": _ce_oxidation_output,
    "frac-output": _pair("frac-ce"),
    "overset-output": _pair("overset"),
    "underset-output": _pair("underset"),
    "underbrace-output": _pair("underbrace"),
    "color-output": lambda _buffer, m, _option=None: {"type_": "color", "color1": m[0], "color2": go(m[1], "ce")},
    "r=": _store("r"),
    "rdt=": _store("rdt"),
    "rd=": _store("rd"),
    "rqt=": _store("rqt"),
    "rq=": _store("rq"),
    "operator": lambda _buffer, m, p1=None: {"type_": "operator", "kind_": p1 or m},
}


def _text_output(buffer, _m=None, _option=None):
    if buffer.get("text_"):
        ret = {"type_": "text", "p1": buffer["text_"]}
        _clear(buffer)
        return ret
    return None


def _tex_math_output(buffer, _m=None, _option=None):
    if buffer.get("o"):
        ret = {"type_": "tex-math", "p1": buffer["o"]}
        _clear(buffer)
        return ret
    return None


def _tight_operator(buffer, m, _option=None):
    buffer["o"] = (buffer.get("o") or "") + "{" + m + "}"


#
# the \pu machines' actions
#
def _pu_enumber(_buffer, m, _option=None):
    ret: list = []
    if m[0] in ("+-", "+/-"):
        ret.append("\\pm ")
    elif m[0]:
        ret.append(m[0])
    if m[1]:
        _concat(ret, go(m[1], "pu-9,9"))
        if m[2]:
            if re.search(r"[,.]", m[2]):
                _concat(ret, go(m[2], "pu-9,9"))
            else:
                ret.append(m[2])
        if m[3] or m[4]:
            if m[3] == "e" or m[4] == "*":
                ret.append({"type_": "cdot"})
            else:
                ret.append({"type_": "times"})
    if m[5]:
        ret.append("10^{" + m[5] + "}")
    return ret


def _pu_number_power(_buffer, m, _option=None):
    ret: list = []
    if m[0] in ("+-", "+/-"):
        ret.append("\\pm ")
    elif m[0]:
        ret.append(m[0])
    _concat(ret, go(m[1], "pu-9,9"))
    ret.append("^{" + m[2] + "}")
    return ret


def _degrees(text: str) -> str:
    text = re.sub(r"\u00B0C|\^oC|\^\{o\}C", lambda _: "{}^{\\circ}C", text)
    return re.sub(r"\u00B0F|\^oF|\^\{o\}F", lambda _: "{}^{\\circ}F", text)


def _pu_output(buffer, _m=None, _option=None):
    md = match_("{(...)}", buffer.get("d") or "")
    if md and md["remainder"] == "":
        buffer["d"] = md["match_"]
    mq = match_("{(...)}", buffer.get("q") or "")
    if mq and mq["remainder"] == "":
        buffer["q"] = mq["match_"]
    if buffer.get("d"):
        buffer["d"] = _degrees(buffer["d"])
    if buffer.get("q"):
        buffer["q"] = _degrees(buffer["q"])
        b5 = {"d": go(buffer.get("d"), "pu"), "q": go(buffer.get("q"), "pu")}
        if buffer.get("o") == "//":
            ret: list | dict = {"type_": "pu-frac", "p1": b5["d"], "p2": b5["q"]}
        else:
            ret = b5["d"]
            if len(b5["d"]) > 1 or len(b5["q"]) > 1:
                ret.append({"type_": " / "})
            else:
                ret.append({"type_": "/"})
            _concat(ret, b5["q"])
    else:
        ret = go(buffer.get("d"), "pu-2")
    _clear(buffer)
    return ret


def _pu2_power(buffer, m, _option=None):
    rm = buffer.get("rm")
    buffer["rm"] = ("undefined" if rm is None else rm) + "^{" + m + "}"


def _pu2_output(buffer, _m=None, _option=None):
    ret: list | dict = []
    if buffer.get("rm"):
        mrm = match_("{(...)}", buffer.get("rm") or "")
        if mrm and mrm["remainder"] == "":
            ret = go(mrm["match_"], "pu")
        else:
            ret = {"type_": "rm", "p1": buffer["rm"]}
    _clear(buffer)
    return ret


def _pu99_output_0(buffer, _m=None, _option=None):
    ret: list = []
    text = buffer.get("text_") or ""
    if len(text) > 4:
        a = len(text) % 3
        if a == 0:
            a = 3
        i = len(text) - 3
        while i > 0:
            ret.append(text[i:i + 3])
            ret.append({"type_": "1000 separator"})
            i -= 3
        ret.append(text[:a])
        ret.reverse()
    else:
        ret.append(text)
    _clear(buffer)
    return ret


def _pu99_output_o(buffer, _m=None, _option=None):
    ret: list = []
    text = buffer.get("text_") or ""
    if len(text) > 4:
        a = len(text) - 3
        i = 0
        while i < a:
            ret.append(text[i:i + 3])
            ret.append({"type_": "1000 separator"})
            i += 3
        ret.append(text[i:])
    else:
        ret.append(text)
    _clear(buffer)
    return ret


#
# the state machines
#
_ANY_ESCAPE = "\\,|\\x{}{}|\\x{}|\\x"
_PU_INSERT = [{"type_": "write", "option": "{"}, "pu", {"type_": "write", "option": "}"}]

MACHINES = {
    "tex": {
        "transitions": _create_transitions({
            "empty": {"0": {"action_": "copy"}},
            "\\ce{(...)}": {"0": {"action_": [{"type_": "write", "option": "{"}, "ce", {"type_": "write", "option": "}"}]}},
            "\\pu{(...)}": {"0": {"action_": [{"type_": "write", "option": "{"}, "pu", {"type_": "write", "option": "}"}]}},
            "else": {"0": {"action_": "copy"}},
        }),
        "actions": {},
    },
    "ce": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": "output"}},
            "else": {"0|1|2": {"action_": "beginsWithBond=false", "revisit": True, "toContinue": True}},
            "oxidation$": {"0": {"action_": "oxidation-output"}},
            "CMT": {"r": {"action_": "rdt=", "nextState": "rt"},
                    "rd": {"action_": "rqt=", "nextState": "rdt"}},
            "arrowUpDown": {"0|1|2|as": {"action_": ["sb=false", "output", "operator"], "nextState": "1"}},
            "uprightEntities": {"0|1|2": {"action_": ["o=", "output"], "nextState": "1"}},
            "orbital": {"0|1|2|3": {"action_": "o=", "nextState": "o"}},
            "->": {"0|1|2|3": {"action_": "r=", "nextState": "r"},
                   "a|as": {"action_": ["output", "r="], "nextState": "r"},
                   "*": {"action_": ["output", "r="], "nextState": "r"}},
            "+": {"o": {"action_": "d= kv", "nextState": "d"},
                  "d|D": {"action_": "d=", "nextState": "d"},
                  "q": {"action_": "d=", "nextState": "qd"},
                  "qd|qD": {"action_": "d=", "nextState": "qd"},
                  "dq": {"action_": ["output", "d="], "nextState": "d"},
                  "3": {"action_": ["sb=false", "output", "operator"], "nextState": "0"}},
            "amount": {"0|2": {"action_": "a=", "nextState": "a"}},
            "pm-operator": {"0|1|2|a|as": {"action_": ["sb=false", "output", {"type_": "operator", "option": "\\pm"}],
                                           "nextState": "0"}},
            "operator": {"0|1|2|a|as": {"action_": ["sb=false", "output", "operator"], "nextState": "0"}},
            "-$": {"o|q": {"action_": ["charge or bond", "output"], "nextState": "qd"},
                   "d": {"action_": "d=", "nextState": "d"},
                   "D": {"action_": ["output", {"type_": "bond", "option": "-"}], "nextState": "3"},
                   "q": {"action_": "d=", "nextState": "qd"},
                   "qd": {"action_": "d=", "nextState": "qd"},
                   "qD|dq": {"action_": ["output", {"type_": "bond", "option": "-"}], "nextState": "3"}},
            "-9": {"3|o": {"action_": ["output", {"type_": "insert", "option": "hyphen"}], "nextState": "3"}},
            "- orbital overlap": {"o": {"action_": ["output", {"type_": "insert", "option": "hyphen"}], "nextState": "2"},
                                  "d": {"action_": ["output", {"type_": "insert", "option": "hyphen"}], "nextState": "2"}},
            "-": {"0|1|2": {"action_": [{"type_": "output", "option": 1}, "beginsWithBond=true",
                                        {"type_": "bond", "option": "-"}], "nextState": "3"},
                  "3": {"action_": {"type_": "bond", "option": "-"}},
                  "a": {"action_": ["output", {"type_": "insert", "option": "hyphen"}], "nextState": "2"},
                  "as": {"action_": [{"type_": "output", "option": 2}, {"type_": "bond", "option": "-"}], "nextState": "3"},
                  "b": {"action_": "b="},
                  "o": {"action_": {"type_": "- after o/d", "option": False}, "nextState": "2"},
                  "q": {"action_": {"type_": "- after o/d", "option": False}, "nextState": "2"},
                  "d|qd|dq": {"action_": {"type_": "- after o/d", "option": True}, "nextState": "2"},
                  "D|qD|p": {"action_": ["output", {"type_": "bond", "option": "-"}], "nextState": "3"}},
            "amount2": {"1|3": {"action_": "a=", "nextState": "a"}},
            "letters": {"0|1|2|3|a|as|b|p|bp|o": {"action_": "o=", "nextState": "o"},
                        "q|dq": {"action_": ["output", "o="], "nextState": "o"},
                        "d|D|qd|qD": {"action_": "o after d", "nextState": "o"}},
            "digits": {"o": {"action_": "q=", "nextState": "q"},
                       "d|D": {"action_": "q=", "nextState": "dq"},
                       "q": {"action_": ["output", "o="], "nextState": "o"},
                       "a": {"action_": "o=", "nextState": "o"}},
            "space A": {"b|p|bp": {"action_": []}},
            "space": {"a": {"action_": [], "nextState": "as"},
                      "0": {"action_": "sb=false"},
                      "1|2": {"action_": "sb=true"},
                      "r|rt|rd|rdt|rdq": {"action_": "output", "nextState": "0"},
                      "*": {"action_": ["output", "sb=true"], "nextState": "1"}},
            "1st-level escape": {"1|2": {"action_": ["output", {"type_": "insert+p1", "option": "1st-level escape"}]},
                                 "*": {"action_": ["output", {"type_": "insert+p1", "option": "1st-level escape"}],
                                       "nextState": "0"}},
            "[(...)]": {"r|rt": {"action_": "rd=", "nextState": "rd"},
                        "rd|rdt": {"action_": "rq=", "nextState": "rdq"}},
            "...": {"o|d|D|dq|qd|qD": {"action_": ["output", {"type_": "bond", "option": "..."}], "nextState": "3"},
                    "*": {"action_": [{"type_": "output", "option": 1}, {"type_": "insert", "option": "ellipsis"}],
                          "nextState": "1"}},
            ". __* ": {"*": {"action_": ["output", {"type_": "insert", "option": "addition compound"}], "nextState": "1"}},
            "state of aggregation $": {"*": {"action_": ["output", "state of aggregation"], "nextState": "1"}},
            "{[(": {"a|as|o": {"action_": ["o=", "output", "parenthesisLevel++"], "nextState": "2"},
                    "0|1|2|3": {"action_": ["o=", "output", "parenthesisLevel++"], "nextState": "2"},
                    "*": {"action_": ["output", "o=", "output", "parenthesisLevel++"], "nextState": "2"}},
            ")]}": {"0|1|2|3|b|p|bp|o": {"action_": ["o=", "parenthesisLevel--"], "nextState": "o"},
                    "a|as|d|D|q|qd|qD|dq": {"action_": ["output", "o=", "parenthesisLevel--"], "nextState": "o"}},
            ", ": {"*": {"action_": ["output", "comma"], "nextState": "0"}},
            "^_": {"*": {"action_": []}},
            "^{(...)}|^($...$)": {"0|1|2|as": {"action_": "b=", "nextState": "b"},
                                  "p": {"action_": "b=", "nextState": "bp"},
                                  "3|o": {"action_": "d= kv", "nextState": "D"},
                                  "q": {"action_": "d=", "nextState": "qD"},
                                  "d|D|qd|qD|dq": {"action_": ["output", "d="], "nextState": "D"}},
            "^a|^\\x{}{}|^\\x{}|^\\x|'": {"0|1|2|as": {"action_": "b=", "nextState": "b"},
                                         "p": {"action_": "b=", "nextState": "bp"},
                                         "3|o": {"action_": "d= kv", "nextState": "d"},
                                         "q": {"action_": "d=", "nextState": "qd"},
                                         "d|qd|D|qD": {"action_": "d="},
                                         "dq": {"action_": ["output", "d="], "nextState": "d"}},
            "_{(state of aggregation)}$": {"d|D|q|qd|qD|dq": {"action_": ["output", "q="], "nextState": "q"}},
            "_{(...)}|_($...$)|_9|_\\x{}{}|_\\x{}|_\\x": {"0|1|2|as": {"action_": "p=", "nextState": "p"},
                                                        "b": {"action_": "p=", "nextState": "bp"},
                                                        "3|o": {"action_": "q=", "nextState": "q"},
                                                        "d|D": {"action_": "q=", "nextState": "dq"},
                                                        "q|qd|qD|dq": {"action_": ["output", "q="], "nextState": "q"}},
            "=<>": {"0|1|2|3|a|as|o|q|d|D|qd|qD|dq": {"action_": [{"type_": "output", "option": 2}, "bond"],
                                                      "nextState": "3"}},
            "#": {"0|1|2|3|a|as|o": {"action_": [{"type_": "output", "option": 2}, {"type_": "bond", "option": "#"}],
                                     "nextState": "3"}},
            "{}^": {"*": {"action_": [{"type_": "output", "option": 1}, {"type_": "insert", "option": "tinySkip"}],
                          "nextState": "1"}},
            "{}": {"*": {"action_": {"type_": "output", "option": 1}, "nextState": "1"}},
            "{...}": {"0|1|2|3|a|as|b|p|bp": {"action_": "o=", "nextState": "o"},
                      "o|d|D|q|qd|qD|dq": {"action_": ["output", "o="], "nextState": "o"}},
            "$...$": {"a": {"action_": "a="},
                      "0|1|2|3|as|b|p|bp|o": {"action_": "o=", "nextState": "o"},
                      "as|o": {"action_": "o="},
                      "q|d|D|qd|qD|dq": {"action_": ["output", "o="], "nextState": "o"}},
            "\\bond{(...)}": {"*": {"action_": [{"type_": "output", "option": 2}, "bond"], "nextState": "3"}},
            "\\frac{(...)}": {"*": {"action_": [{"type_": "output", "option": 1}, "frac-output"], "nextState": "3"}},
            "\\overset{(...)}": {"*": {"action_": [{"type_": "output", "option": 2}, "overset-output"], "nextState": "3"}},
            "\\underset{(...)}": {"*": {"action_": [{"type_": "output", "option": 2}, "underset-output"],
                                        "nextState": "3"}},
            "\\underbrace{(...)}": {"*": {"action_": [{"type_": "output", "option": 2}, "underbrace-output"],
                                          "nextState": "3"}},
            "\\color{(...)}{(...)}": {"*": {"action_": [{"type_": "output", "option": 2}, "color-output"],
                                            "nextState": "3"}},
            "\\color{(...)}": {"*": {"action_": [{"type_": "output", "option": 2}, "color0-output"]}},
            "\\ce{(...)}": {"*": {"action_": [{"type_": "output", "option": 2}, "ce"], "nextState": "3"}},
            "\\,": {"*": {"action_": [{"type_": "output", "option": 1}, "copy"], "nextState": "1"}},
            "\\pu{(...)}": {"*": {"action_": ["output", *_PU_INSERT], "nextState": "3"}},
            "\\x{}{}|\\x{}|\\x": {"0|1|2|3|a|as|b|p|bp|o|c0": {"action_": ["o=", "output"], "nextState": "3"},
                                  "*": {"action_": ["output", "o=", "output"], "nextState": "3"}},
            "others": {"*": {"action_": [{"type_": "output", "option": 1}, "copy"], "nextState": "3"}},
            "else2": {"a": {"action_": "a to o", "nextState": "o", "revisit": True},
                      "as": {"action_": ["output", "sb=true"], "nextState": "1", "revisit": True},
                      "r|rt|rd|rdt|rdq": {"action_": ["output"], "nextState": "0", "revisit": True},
                      "*": {"action_": ["output", "copy"], "nextState": "3"}},
        }),
        "actions": CE_ACTIONS,
    },
    "a": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": []}},
            "1/2$": {"0": {"action_": "1/2"}},
            "else": {"0": {"action_": [], "nextState": "1", "revisit": True}},
            "${(...)}$__$(...)$": {"*": {"action_": "tex-math tight", "nextState": "1"}},
            ",": {"*": {"action_": {"type_": "insert", "option": "commaDecimal"}}},
            "else2": {"*": {"action_": "copy"}},
        }),
        "actions": {},
    },
    "o": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": []}},
            "1/2$": {"0": {"action_": "1/2"}},
            "else": {"0": {"action_": [], "nextState": "1", "revisit": True}},
            "letters": {"*": {"action_": "rm"}},
            "\\ca": {"*": {"action_": {"type_": "insert", "option": "circa"}}},
            "\\pu{(...)}": {"*": {"action_": list(_PU_INSERT)}},
            "\\x{}{}|\\x{}|\\x": {"*": {"action_": "copy"}},
            "${(...)}$__$(...)$": {"*": {"action_": "tex-math"}},
            "{(...)}": {"*": {"action_": [{"type_": "write", "option": "{"}, "text", {"type_": "write", "option": "}"}]}},
            "else2": {"*": {"action_": "copy"}},
        }),
        "actions": {},
    },
    "text": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": "output"}},
            "{...}": {"*": {"action_": "text="}},
            "${(...)}$__$(...)$": {"*": {"action_": "tex-math"}},
            "\\greek": {"*": {"action_": ["output", "rm"]}},
            "\\pu{(...)}": {"*": {"action_": ["output", *_PU_INSERT]}},
            _ANY_ESCAPE: {"*": {"action_": ["output", "copy"]}},
            "else": {"*": {"action_": "text="}},
        }),
        "actions": {"output": _text_output},
    },
    "pq": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": []}},
            "state of aggregation $": {"*": {"action_": "state of aggregation"}},
            "i$": {"0": {"action_": [], "nextState": "!f", "revisit": True}},
            "(KV letters),": {"0": {"action_": "rm", "nextState": "0"}},
            "formula$": {"0": {"action_": [], "nextState": "f", "revisit": True}},
            "1/2$": {"0": {"action_": "1/2"}},
            "else": {"0": {"action_": [], "nextState": "!f", "revisit": True}},
            "${(...)}$__$(...)$": {"*": {"action_": "tex-math"}},
            "{(...)}": {"*": {"action_": "text"}},
            "a-z": {"f": {"action_": "tex-math"}},
            "letters": {"*": {"action_": "rm"}},
            "-9.,9": {"*": {"action_": "9,9"}},
            ",": {"*": {"action_": {"type_": "insert+p1", "option": "comma enumeration S"}}},
            "\\color{(...)}{(...)}": {"*": {"action_": "color-output"}},
            "\\color{(...)}": {"*": {"action_": "color0-output"}},
            "\\ce{(...)}": {"*": {"action_": "ce"}},
            "\\pu{(...)}": {"*": {"action_": list(_PU_INSERT)}},
            _ANY_ESCAPE: {"*": {"action_": "copy"}},
            "else2": {"*": {"action_": "copy"}},
        }),
        "actions": {
            "state of aggregation": lambda _buffer, m, _option=None: {"type_": "state of aggregation subscript",
                                                                      "p1": go(m, "o")},
            "color-output": lambda _buffer, m, _option=None: {"type_": "color", "color1": m[0], "color2": go(m[1], "pq")},
        },
    },
    "bd": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": []}},
            "x$": {"0": {"action_": [], "nextState": "!f", "revisit": True}},
            "formula$": {"0": {"action_": [], "nextState": "f", "revisit": True}},
            "else": {"0": {"action_": [], "nextState": "!f", "revisit": True}},
            "-9.,9 no missing 0": {"*": {"action_": "9,9"}},
            ".": {"*": {"action_": {"type_": "insert", "option": "electron dot"}}},
            "a-z": {"f": {"action_": "tex-math"}},
            "x": {"*": {"action_": {"type_": "insert", "option": "KV x"}}},
            "letters": {"*": {"action_": "rm"}},
            "'": {"*": {"action_": {"type_": "insert", "option": "prime"}}},
            "${(...)}$__$(...)$": {"*": {"action_": "tex-math"}},
            "{(...)}": {"*": {"action_": "text"}},
            "\\color{(...)}{(...)}": {"*": {"action_": "color-output"}},
            "\\color{(...)}": {"*": {"action_": "color0-output"}},
            "\\ce{(...)}": {"*": {"action_": "ce"}},
            "\\pu{(...)}": {"*": {"action_": list(_PU_INSERT)}},
            _ANY_ESCAPE: {"*": {"action_": "copy"}},
            "else2": {"*": {"action_": "copy"}},
        }),
        "actions": {
            "color-output": lambda _buffer, m, _option=None: {"type_": "color", "color1": m[0], "color2": go(m[1], "bd")},
        },
    },
    "oxidation": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": "roman-numeral"}},
            "pm-operator": {"*": {"action_": {"type_": "o=+p1", "option": "\\pm"}}},
            "else": {"*": {"action_": "o="}},
        }),
        "actions": {"roman-numeral": lambda buffer, _m=None, _option=None: {"type_": "roman numeral",
                                                                            "p1": buffer.get("o") or ""}},
    },
    "tex-math": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": "output"}},
            "\\ce{(...)}": {"*": {"action_": ["output", "ce"]}},
            "\\pu{(...)}": {"*": {"action_": ["output", *_PU_INSERT]}},
            "{...}|" + _ANY_ESCAPE: {"*": {"action_": "o="}},
            "else": {"*": {"action_": "o="}},
        }),
        "actions": {"output": _tex_math_output},
    },
    "tex-math tight": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": "output"}},
            "\\ce{(...)}": {"*": {"action_": ["output", "ce"]}},
            "\\pu{(...)}": {"*": {"action_": ["output", *_PU_INSERT]}},
            "{...}|" + _ANY_ESCAPE: {"*": {"action_": "o="}},
            "-|+": {"*": {"action_": "tight operator"}},
            "else": {"*": {"action_": "o="}},
        }),
        "actions": {"tight operator": _tight_operator, "output": _tex_math_output},
    },
    "9,9": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": []}},
            ",": {"*": {"action_": "comma"}},
            "else": {"*": {"action_": "copy"}},
        }),
        "actions": {"comma": lambda _buffer=None, _m=None, _option=None: {"type_": "commaDecimal"}},
    },
    "pu": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": "output"}},
            "space$": {"*": {"action_": ["output", "space"]}},
            "{[(|)]}": {"0|a": {"action_": "copy"}},
            "(-)(9)^(-9)": {"0": {"action_": "number^", "nextState": "a"}},
            "(-)(9.,9)(e)(99)": {"0": {"action_": "enumber", "nextState": "a"}},
            "space": {"0|a": {"action_": []}},
            "pm-operator": {"0|a": {"action_": {"type_": "operator", "option": "\\pm"}, "nextState": "0"}},
            "operator": {"0|a": {"action_": "copy", "nextState": "0"}},
            "//": {"d": {"action_": "o=", "nextState": "/"}},
            "/": {"d": {"action_": "o=", "nextState": "/"}},
            "{...}|else": {"0|d": {"action_": "d=", "nextState": "d"},
                           "a": {"action_": ["space", "d="], "nextState": "d"},
                           "/|q": {"action_": "q=", "nextState": "q"}},
        }),
        "actions": {
            "enumber": _pu_enumber,
            "number^": _pu_number_power,
            "operator": lambda _buffer, m, p1=None: {"type_": "operator", "kind_": p1 or m},
            "space": lambda _buffer=None, _m=None, _option=None: {"type_": "pu-space-1"},
            "output": _pu_output,
        },
    },
    "pu-2": {
        "transitions": _create_transitions({
            "empty": {"*": {"action_": "output"}},
            "*": {"*": {"action_": ["output", "cdot"], "nextState": "0"}},
            "\\x": {"*": {"action_": "rm="}},
            "space": {"*": {"action_": ["output", "space"], "nextState": "0"}},
            "^{(...)}|^(-1)": {"1": {"action_": "^(-1)"}},
            "-9.,9": {"0": {"action_": "rm=", "nextState": "0"},
                      "1": {"action_": "^(-1)", "nextState": "0"}},
            "{...}|else": {"*": {"action_": "rm=", "nextState": "1"}},
        }),
        "actions": {
            "cdot": lambda _buffer=None, _m=None, _option=None: {"type_": "tight cdot"},
            "^(-1)": _pu2_power,
            "space": lambda _buffer=None, _m=None, _option=None: {"type_": "pu-space-2"},
            "output": _pu2_output,
        },
    },
    "pu-9,9": {
        "transitions": _create_transitions({
            "empty": {"0": {"action_": "output-0"},
                      "o": {"action_": "output-o"}},
            ",": {"0": {"action_": ["output-0", "comma"], "nextState": "o"}},
            ".": {"0": {"action_": ["output-0", "copy"], "nextState": "o"}},
            "else": {"*": {"action_": "text="}},
        }),
        "actions": {
            "comma": lambda _buffer=None, _m=None, _option=None: {"type_": "commaDecimal"},
            "output-0": _pu99_output_0,
            "output-o": _pu99_output_o,
        },
    },
}


def go(input_, state_machine: str = "ce") -> list:
    """mhchem's parser (`_mhchemParser.go`): the input as a list of strings and parsed pieces ({type_: ...})"""
    if not input_:
        return []
    state = "0"
    buffer: dict = {"parenthesisLevel": 0}
    input_ = input_.replace("\n", " ")
    input_ = re.sub("[\u2212\u2013\u2014\u2010]", "-", input_)
    input_ = input_.replace("\u2026", "...")
    last_input = None
    watchdog = 10
    output: list = []
    machine = MACHINES[state_machine]
    while True:
        if last_input != input_:
            watchdog = 10
            last_input = input_
        else:
            watchdog -= 1
        transitions = machine["transitions"].get(state)
        if transitions is None:
            transitions = machine["transitions"]["*"]
        for transition in transitions:
            matches = match_(transition["pattern"], input_)
            if matches:
                task = transition["task"]
                for action in task["action_"]:
                    name = action["type_"]
                    function = machine["actions"].get(name) or ACTIONS.get(name)
                    if function is None:
                        raise MhchemError(f"mhchem bug A. Please report. ({name})")
                    if "option" in action:
                        o = function(buffer, matches["match_"], action["option"])
                    else:
                        o = function(buffer, matches["match_"])
                    _concat(output, o)
                state = task.get("nextState") or state
                if len(input_) > 0:
                    if not task.get("revisit"):
                        input_ = matches["remainder"]
                    if not task.get("toContinue"):
                        break
                else:
                    return output
        if watchdog <= 0:
            raise MhchemError("mhchem bug U. Please report.")


#
# _mhchemTexify: the parser's output as TeX
#
def texify(input_, add_outer_braces: bool = False) -> str:
    if not input_:
        return ""
    res = ""
    cee = False
    for item in input_:
        if isinstance(item, str):
            res += item
        else:
            res += _go2(item)
            if item["type_"] == "1st-level escape":
                cee = True
    if add_outer_braces and not cee and res:
        res = "{" + res + "}"
    return res


def _inner(input_) -> str:
    return texify(input_, False)


ARROWS = {"->": "rightarrow", "\u2192": "rightarrow", "\u27F6": "rightarrow", "<-": "leftarrow",
          "<->": "leftrightarrow", "<-->": "leftrightarrows", "<=>": "rightleftharpoons",
          "\u21CC": "rightleftharpoons", "<=>>": "Rightleftharpoons", "<<=>": "Leftrightharpoons"}
BONDS = {"-": "{-}", "1": "{-}", "=": "{=}", "2": "{=}", "#": "{\\equiv}", "3": "{\\equiv}", "~": "{\\tripledash}",
         "~-": "{\\rlap{\\lower.1em{-}}\\raise.1em{\\tripledash}}",
         "~=": "{\\rlap{\\lower.2em{-}}\\rlap{\\raise.2em{\\tripledash}}-}",
         "~--": "{\\rlap{\\lower.2em{-}}\\rlap{\\raise.2em{\\tripledash}}-}",
         "-~-": "{\\rlap{\\lower.2em{-}}\\rlap{\\raise.2em{-}}\\tripledash}",
         "...": "{{\\cdot}{\\cdot}{\\cdot}}", "....": "{{\\cdot}{\\cdot}{\\cdot}{\\cdot}}",
         "->": "{\\rightarrow}", "<-": "{\\leftarrow}", "<": "{<}", ">": "{>}"}
OPERATORS = {"+": " {}+{} ", "-": " {}-{} ", "=": " {}={} ", "<": " {}<{} ", ">": " {}>{} ", "<<": " {}\\ll{} ",
             ">>": " {}\\gg{} ", "\\pm": " {}\\pm{} ", "\\approx": " {}\\approx{} ", "$\\approx$": " {}\\approx{} ",
             "v": " \\downarrow{} ", "(v)": " \\downarrow{} ", "^": " \\uparrow{} ", "(^)": " \\uparrow{} "}
SIMPLE = {"space": " ", "tinySkip": "\\mkern2mu", "entitySkip": "~", "pu-space-1": "~", "pu-space-2": "\\mkern3mu ",
          "1000 separator": "\\mkern2mu ", "commaDecimal": "{,}", "hyphen": "\\text{-}",
          "addition compound": "\\,{\\cdot}\\,", "electron dot": "\\mkern1mu \\bullet\\mkern1mu ", "KV x": "{\\times}",
          "prime": "\\prime ", "cdot": "\\cdot ", "tight cdot": "\\mkern1mu{\\cdot}\\mkern1mu ", "times": "\\times ",
          "circa": "{\\sim}", "^": "uparrow", "v": "downarrow", "ellipsis": "\\ldots ", "/": "/", " / ": "\\,/\\,"}


def _go2(buf: dict) -> str:
    kind = buf["type_"]
    if kind == "chemfive":
        res = ""
        b5 = {key: _inner(buf[key]) for key in ("a", "b", "p", "o", "q", "d")}
        if b5["a"]:
            if re.match(r"[+\-]", b5["a"]):
                b5["a"] = "{" + b5["a"] + "}"
            res += b5["a"] + "\\,"
        if b5["b"] or b5["p"]:
            res += "{\\vphantom{A}}"
            res += "^{\\hphantom{" + (b5["b"] or "") + "}}_{\\hphantom{" + (b5["p"] or "") + "}}"
            res += "\\mkern-1.5mu"
            res += "{\\vphantom{A}}"
            res += "^{\\smash[t]{\\vphantom{2}}\\llap{" + (b5["b"] or "") + "}}"
            res += "_{\\vphantom{2}\\llap{\\smash[t]{" + (b5["p"] or "") + "}}}"
        if b5["o"]:
            if re.match(r"[+\-]", b5["o"]):
                b5["o"] = "{" + b5["o"] + "}"
            res += b5["o"]
        if buf.get("dType") == "kv":
            if b5["d"] or b5["q"]:
                res += "{\\vphantom{A}}"
            if b5["d"]:
                res += "^{" + b5["d"] + "}"
            if b5["q"]:
                res += "_{\\smash[t]{" + b5["q"] + "}}"
        elif buf.get("dType") == "oxidation":
            if b5["d"]:
                res += "{\\vphantom{A}}"
                res += "^{" + b5["d"] + "}"
            if b5["q"]:
                res += "{\\vphantom{A}}"
                res += "_{\\smash[t]{" + b5["q"] + "}}"
        else:
            if b5["q"]:
                res += "{\\vphantom{A}}"
                res += "_{\\smash[t]{" + b5["q"] + "}}"
            if b5["d"]:
                res += "{\\vphantom{A}}"
                res += "^{" + b5["d"] + "}"
        return res
    if kind in ("rm", "roman numeral"):
        return "\\mathrm{" + buf["p1"] + "}"
    if kind == "text":
        p1 = buf["p1"]
        if re.search(r"[\^_]", p1):
            p1 = p1.replace(" ", "~", 1).replace("-", "\\text{-}", 1)
            return "\\mathrm{" + p1 + "}"
        return "\\text{" + p1 + "}"
    if kind == "state of aggregation":
        return "\\mskip2mu " + _inner(buf["p1"])
    if kind == "state of aggregation subscript":
        return "\\mskip1mu " + _inner(buf["p1"])
    if kind == "bond":
        res = BONDS.get(buf["kind_"])
        if not res:
            raise MhchemError(f"mhchem Error. Unknown bond type ({buf['kind_']})")
        return res
    if kind == "frac":
        c = "\\frac{" + buf["p1"] + "}{" + buf["p2"] + "}"
        return "\\mathchoice{\\textstyle" + c + "}{" + c + "}{" + c + "}{" + c + "}"
    if kind == "pu-frac":
        d = "\\frac{" + _inner(buf["p1"]) + "}{" + _inner(buf["p2"]) + "}"
        return "\\mathchoice{\\textstyle" + d + "}{" + d + "}{" + d + "}{" + d + "}"
    if kind == "tex-math":
        return buf["p1"] + " "
    if kind == "frac-ce":
        return "\\frac{" + _inner(buf["p1"]) + "}{" + _inner(buf["p2"]) + "}"
    if kind in ("overset", "underset"):
        return "\\" + kind + "{" + _inner(buf["p1"]) + "}{" + _inner(buf["p2"]) + "}"
    if kind == "underbrace":
        return "\\underbrace{" + _inner(buf["p1"]) + "}_{" + _inner(buf["p2"]) + "}"
    if kind == "color":
        return "{\\color{" + buf["color1"] + "}{" + _inner(buf["color2"]) + "}}"
    if kind == "color0":
        return "\\color{" + buf["color"] + "}"
    if kind == "arrow":
        rd, rq = _inner(buf["rd"]), _inner(buf["rq"])
        arrow = ARROWS.get(buf["r"])
        if arrow is None:
            raise MhchemError("mhchem bug T. Please report.")
        if rd or rq:
            if buf["r"] in ("<=>", "<=>>", "<<=>", "<-->"):
                arrow = "\\long" + arrow
                if rd:
                    arrow = "\\overset{" + rd + "}{" + arrow + "}"
                if rq:
                    if buf["r"] == "<-->":
                        arrow = "\\underset{\\lower2mu{" + rq + "}}{" + arrow + "}"
                    else:
                        arrow = "\\underset{\\lower6mu{" + rq + "}}{" + arrow + "}"
                return " {}\\mathrel{" + arrow + "}{} "
            if rq:
                arrow += "[{" + rq + "}]"
            arrow += "{" + rd + "}"
            return " {}\\mathrel{\\x" + arrow + "}{} "
        return " {}\\mathrel{\\long" + arrow + "}{} "
    if kind == "operator":
        res = OPERATORS.get(buf["kind_"])
        if res is None:
            raise MhchemError("mhchem bug T. Please report.")
        return res
    if kind == "1st-level escape":
        return buf["p1"] + " "
    if kind == "comma enumeration L":
        return "{" + buf["p1"] + "}\\mkern6mu "
    if kind == "comma enumeration M":
        return "{" + buf["p1"] + "}\\mkern3mu "
    if kind == "comma enumeration S":
        return "{" + buf["p1"] + "}\\mkern1mu "
    if kind in SIMPLE:
        return SIMPLE[kind]
    raise MhchemError("mhchem bug T. Please report.")


def parse(input_: str, kind: str = "ce") -> list:
    """mhchem's parse of `input_` (the text of a \\ce, a \\pu, or TeX with them in it: kind "ce", "pu" or "tex")"""
    return go(input_, kind)


def to_tex(input_: str, kind: str = "ce") -> str:
    """The TeX mhchem makes of `input_` (`mhchemParser.toTex`): `to_tex("H2O")` is
    `{\\mathrm{H}{\\vphantom{A}}_{\\smash[t]{2}}\\mathrm{O}}`. Raises MhchemError when mhchem cannot read it."""
    return texify(go(input_, kind), kind != "tex")
