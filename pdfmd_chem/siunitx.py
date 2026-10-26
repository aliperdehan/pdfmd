"""siunitx's numbers and units (`\\num`, `\\qty`/`\\SI`, `\\unit`/`\\si`, `\\ang`, ranges and lists) as text and as plain
TeX math, the way siunitx 3 prints them: the document's `\\sisetup` (decimal marker, digit groups, the product
between a number and its unit, `per-mode`), its `\\DeclareSIUnit`s and its unit shortcuts (`\\newcommand{\\gml}{\\gram
\\per\\milli\\liter}`) included. What siunitx would refuse (`\\num{2 x 3}`), or a macro this module does not know,
raises SiunitxError: the caller leaves that one to LaTeX.

The result is a list of runs, (text, place): place "" is on the line, "sup" and "sub" above and below it, "word" is
prose ("to", "and") and "op" an operator (the × of 1.5 × 10⁻³). `runs_text()` gives the runs as text runs,
`runs_tex()` as math TeX that Pandoc's converter (texmath) reads: units upright, prose in \text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

THIN = "\u202f"          # siunitx's \, between digit groups and between a number and its unit: thin, no break
MINUS = "\u2212"


class SiunitxError(Exception):
    """siunitx would refuse this input, or it uses something this module does not know."""


PREFIXES = {
    "quecto": "q", "ronto": "r", "yocto": "y", "zepto": "z", "atto": "a", "femto": "f", "pico": "p", "nano": "n",
    "micro": "\u00b5", "milli": "m", "centi": "c", "deci": "d", "deca": "da", "deka": "da", "hecto": "h", "kilo": "k",
    "mega": "M", "giga": "G", "tera": "T", "peta": "P", "exa": "E", "zetta": "Z", "yotta": "Y", "ronna": "R",
    "quetta": "Q", "kibi": "Ki", "mebi": "Mi", "gibi": "Gi", "tebi": "Ti", "pebi": "Pi", "exbi": "Ei", "zebi": "Zi",
    "yobi": "Yi",
}

# siunitx's named units (symbol, product before it: None = the quantity product, "" = none: 90°)
UNITS = {
    "ampere": "A", "candela": "cd", "kelvin": "K", "kilogram": "kg", "gram": "g", "metre": "m", "meter": "m",
    "mole": "mol", "second": "s", "becquerel": "Bq", "degreeCelsius": "\u00b0C", "celsius": "\u00b0C", "coulomb": "C",
    "farad": "F", "gray": "Gy", "hertz": "Hz", "henry": "H", "joule": "J", "katal": "kat", "lumen": "lm", "lux": "lx",
    "newton": "N", "ohm": "\u03a9", "pascal": "Pa", "radian": "rad", "siemens": "S", "sievert": "Sv",
    "steradian": "sr", "tesla": "T", "volt": "V", "watt": "W", "weber": "Wb", "astronomicalunit": "au",
    "bel": "B", "dalton": "Da", "day": "d", "decibel": "dB", "electronvolt": "eV", "hectare": "ha", "hour": "h",
    "litre": "L", "liter": "L", "minute": "min", "neper": "Np", "tonne": "t", "arcminute": "\u2032",
    "arcsecond": "\u2033", "degree": "\u00b0", "angstrom": "\u00c5", "bar": "bar", "barn": "b", "knot": "kn",
    "millimetremercury": "mmHg", "nauticalmile": "M", "atomicmassunit": "u", "bohr": "a\u2080", "clight": "c\u2080",
    "electronmass": "m\u2091", "elementarycharge": "e", "hartree": "E\u2095", "percent": "%", "planckbar": "\u210f",
    "byte": "B", "bit": "bit",
}
NO_PRODUCT = {"\u00b0", "\u2032", "\u2033"}            # \degree, \arcminute, \arcsecond: 90°, not 90 °

# siunitx-abbreviations.cfg: each is prefix + unit
ABBREVIATIONS = {
    "A": "ampere", "pA": "pico ampere", "nA": "nano ampere", "uA": "micro ampere", "mA": "milli ampere",
    "kA": "kilo ampere", "Hz": "hertz", "mHz": "milli hertz", "kHz": "kilo hertz", "MHz": "mega hertz",
    "GHz": "giga hertz", "THz": "tera hertz", "mol": "mole", "fmol": "femto mole", "pmol": "pico mole",
    "nmol": "nano mole", "umol": "micro mole", "mmol": "milli mole", "kmol": "kilo mole", "V": "volt",
    "pV": "pico volt", "nV": "nano volt", "uV": "micro volt", "mV": "milli volt", "kV": "kilo volt",
    "hl": "hecto litre", "l": "litre", "ml": "milli litre", "ul": "micro litre", "hL": "hecto liter", "L": "liter",
    "mL": "milli liter", "uL": "micro liter", "fg": "femto gram", "pg": "pico gram", "ng": "nano gram",
    "ug": "micro gram", "mg": "milli gram", "g": "gram", "kg": "kilo gram", "amu": "atomicmassunit", "W": "watt",
    "uW": "micro watt", "mW": "milli watt", "kW": "kilo watt", "MW": "mega watt", "GW": "giga watt", "J": "joule",
    "uJ": "micro joule", "mJ": "milli joule", "kJ": "kilo joule", "eV": "electronvolt", "meV": "milli electronvolt",
    "keV": "kilo electronvolt", "MeV": "mega electronvolt", "GeV": "giga electronvolt", "TeV": "tera electronvolt",
    "kWh": "kilo watt hour", "m": "metre", "pm": "pico metre", "nm": "nano metre", "um": "micro metre",
    "mm": "milli metre", "cm": "centi metre", "dm": "deci metre", "km": "kilo metre", "K": "kelvin", "dB": "decibel",
    "kibit": "kibi bit", "Mibit": "mebi bit", "Gibit": "gibi bit", "kiB": "kibi byte", "MiB": "mebi byte",
    "GiB": "gibi byte", "F": "farad", "fF": "femto farad", "pF": "pico farad", "nF": "nano farad",
    "uF": "micro farad", "mF": "milli farad", "H": "henry", "fH": "femto henry", "pH": "pico henry",
    "nH": "nano henry", "mH": "milli henry", "uH": "micro henry", "C": "coulomb", "nC": "nano coulomb",
    "mC": "milli coulomb", "uC": "micro coulomb", "s": "second", "as": "atto second", "fs": "femto second",
    "ps": "pico second", "ns": "nano second", "us": "micro second", "ms": "milli second", "N": "newton",
    "mN": "milli newton", "kN": "kilo newton", "MN": "mega newton", "Pa": "pascal", "kPa": "kilo pascal",
    "MPa": "mega pascal", "GPa": "giga pascal", "mohm": "milli ohm", "kohm": "kilo ohm", "Mohm": "mega ohm",
    "lm": "lumen", "lx": "lux", "Gy": "gray", "mGy": "milli gray", "uGy": "micro gray", "Sv": "sievert",
    "mSv": "milli sievert", "uSv": "micro sievert", "Bq": "becquerel", "kBq": "kilo becquerel",
    "MBq": "mega becquerel", "GBq": "giga becquerel", "kat": "katal", "da": "dalton", "kDa": "kilo dalton",
    "MDa": "mega dalton", "T": "tesla", "mT": "milli tesla", "uT": "micro tesla", "nT": "nano tesla",
}

COMPARATORS = (("<=", "\u2264", "\\leq"), (">=", "\u2265", "\\geq"), ("\\leq", "\u2264", "\\leq"),
               ("\\geq", "\u2265", "\\geq"), ("\\le", "\u2264", "\\leq"), ("\\ge", "\u2265", "\\geq"),
               ("\\ll", "\u226a", "\\ll"), ("\\gg", "\u226b", "\\gg"), ("\\approx", "\u2248", "\\approx"),
               ("\\sim", "\u223c", "\\sim"), ("<", "<", "<"), (">", ">", ">"), ("~", "\u223c", "\\sim"),
               ("\\propto", "\u221d", "\\propto"))
SIGNS = (("+-", "\u00b1", "\\pm"), ("\\pm", "\u00b1", "\\pm"), ("-+", "\u2213", "\\mp"), ("\\mp", "\u2213", "\\mp"),
         ("+", "+", "+"), ("-", MINUS, "-"))


@dataclass
class Settings:
    """siunitx's keys this module follows, with siunitx 3's defaults"""
    decimal_marker: str = "."
    group_separator: str = THIN
    group_minimum_digits: int = 5
    group_digits: str = "all"
    per_mode: str = "power"
    quantity_product: str = THIN
    inter_unit_product: str = THIN
    range_phrase: str = " to "
    list_separator: str = ", "
    list_final_separator: str = " and "
    list_pair_separator: str = " and "
    exponent_product: str = "\u00d7"
    uncertainty_mode: str = "compact"
    print_unity_mantissa: bool = True
    units: dict = field(default_factory=dict)          # \DeclareSIUnit: macro -> (definition, quantity product or None)
    shortcuts: dict = field(default_factory=dict)      # \newcommand{\gml}{\gram\per\milli\liter}


TEXT_VALUES = {"\\,": THIN, "\\ ": " ", "~": "\u00a0", "{}": "", "\\;": "\u2005", "\\:": "\u2005", "\\quad": "\u2003",
               "\\times": "\u00d7", "\\cdot": "\u22c5"}


def _value(text: str) -> str:
    """a key's value (`{,}`, `\\,`, `{}`) as the text it prints"""
    text = text.strip()
    while len(text) >= 2 and text[0] == "{" and text[-1] == "}" and _balanced(text[1:-1]):
        if text in TEXT_VALUES:
            break
        text = text[1:-1].strip()
    return TEXT_VALUES.get(text, text.replace("\\,", THIN).replace("~", "\u00a0"))


def _balanced(text: str) -> bool:
    depth = 0
    for c in text:
        depth += c == "{"
        depth -= c == "}"
        if depth < 0:
            return False
    return depth == 0


def _keyvals(text: str) -> dict:
    out, depth, start = {}, 0, 0
    parts = []
    for i, c in enumerate(text):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "," and depth == 0 and not (i and text[i - 1] == "\\"):
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    for part in parts:
        if "=" in part:
            key, _, value = part.partition("=")
            out[key.strip()] = value.strip()
        elif part.strip():
            out[part.strip()] = "true"
    return out


KEYS = {"output-decimal-marker": "decimal_marker", "group-separator": "group_separator",
        "quantity-product": "quantity_product", "inter-unit-product": "inter_unit_product",
        "range-phrase": "range_phrase", "list-separator": "list_separator",
        "list-final-separator": "list_final_separator", "list-pair-separator": "list_pair_separator",
        "exponent-product": "exponent_product"}


def apply_options(settings: Settings, options: dict) -> Settings:
    """`settings` with siunitx keys (a \\sisetup's, or a command's optional argument) applied; unknown keys stay unknown"""
    for key, value in options.items():
        if key in KEYS:
            setattr(settings, KEYS[key], _value(value))
        elif key == "group-minimum-digits" and value.strip().isdigit():
            settings.group_minimum_digits = int(value)
        elif key == "group-digits":
            settings.group_digits = value.strip() if value.strip() in ("all", "none", "integer", "decimal") else (
                "none" if value.strip() == "false" else "all")
        elif key == "per-mode":
            settings.per_mode = value.strip()
        elif key == "uncertainty-mode":
            settings.uncertainty_mode = value.strip()
        elif key == "print-unity-mantissa":
            settings.print_unity_mantissa = value.strip() != "false"
    return settings


def _group(text: str, start: int = 0) -> tuple[str | None, int]:
    """the brace group at `start` (spaces skipped): its inside and the index after it; (None, start) when there is none"""
    i = start
    while i < len(text) and text[i] in " \t\n":
        i += 1
    if i >= len(text) or text[i] != "{":
        return None, start
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "\\":
            continue
        if text[j] == "{" and (j == 0 or text[j - 1] != "\\"):
            depth += 1
        elif text[j] == "}" and (j == 0 or text[j - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
    return None, start


def _optional(text: str, start: int = 0) -> tuple[str | None, int]:
    i = start
    while i < len(text) and text[i] in " \t\n":
        i += 1
    if i >= len(text) or text[i] != "[":
        return None, start
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
        elif text[j] == "]" and depth == 0:
            return text[i + 1:j], j + 1
    return None, start


UNIT_MACRO = re.compile(r"\\([A-Za-z]+)")


def settings_from_preamble(preamble: str, settings: Settings | None = None) -> Settings:
    """the siunitx setup a LaTeX preamble makes: every \\sisetup, \\DeclareSIUnit, and a \\newcommand (or \\def) whose
    body is made of unit macros only (a shortcut such as \\gml)"""
    settings = settings or Settings()
    text = re.sub(r"(?<!\\)%.*", "", preamble)
    for found in re.finditer(r"\\sisetup\s*", text):
        body, _ = _group(text, found.end())
        if body is not None:
            apply_options(settings, _keyvals(body))
    for found in re.finditer(r"\\DeclareSIUnit\s*", text):
        options, after = _optional(text, found.end())
        name, after = _group(text, after)
        if name is None:
            bare = re.match(r"\s*\\([A-Za-z]+)", text[after:])
            if not bare:
                continue
            name, after = "\\" + bare.group(1), after + bare.end()
        body, _ = _group(text, after)
        if body is None:
            continue
        product = None
        if options:
            value = _keyvals(options).get("quantity-product")
            product = _value(value) if value is not None else None
        settings.units[name.strip().lstrip("\\")] = (body, product)
    for found in re.finditer(r"\\(?:re)?newcommand\*?\s*(?:\{\\([A-Za-z]+)\}|\\([A-Za-z]+))\s*|\\def\\([A-Za-z]+)\s*", text):
        name = found.group(1) or found.group(2) or found.group(3)
        argument_count, after = _optional(text, found.end())
        if argument_count:
            continue
        body, _ = _group(text, after)
        if body and body.strip() and all(_known_unit_macro(macro, settings) for macro in UNIT_MACRO.findall(body)) \
                and not re.sub(r"\\[A-Za-z]+|\s|\{|\}|[0-9]", "", body):
            settings.shortcuts[name] = body
    return settings


UNIT_COMMANDS = {"per", "square", "cubic", "squared", "cubed", "tothe", "raiseto", "of", "cancel", "highlight"}


def _known_unit_macro(name: str, settings: Settings) -> bool:
    return (name in UNITS or name in PREFIXES or name in ABBREVIATIONS or name in UNIT_COMMANDS
            or name in settings.units or name in settings.shortcuts)


#
# numbers
#
@dataclass
class Number:
    comparator: tuple | None = None       # (text, tex)
    sign: tuple | None = None
    integer: str = ""
    decimal: str | None = None            # digits after the marker, None when there is no marker
    uncertainty: str | None = None        # compact: the digits in brackets
    exponent: str | None = None           # "-3"


def parse_number(text: str) -> Number:
    source = " ".join(text.replace("{", " ").replace("}", " ").split())
    number = Number()
    rest = source
    for spelling, shown, tex in COMPARATORS:
        if rest.startswith(spelling) and (not spelling[-1].isalpha() or not rest[len(spelling):len(spelling) + 1].isalpha()):
            number.comparator = (shown, tex)
            rest = rest[len(spelling):].lstrip()
            break
    for spelling, shown, tex in SIGNS:
        if rest.startswith(spelling) and (not spelling[-1].isalpha() or not rest[len(spelling):len(spelling) + 1].isalpha()):
            number.sign = (shown, tex)
            rest = rest[len(spelling):].lstrip()
            break
    found = re.match(r"(\d*)(?:([.,])(\d*))?", rest)
    number.integer = found.group(1)
    if found.group(2) is not None:
        number.decimal = found.group(3)
    rest = rest[found.end():].strip()
    uncertainty = re.match(r"\((\d+(?:[.,]\d+)?)\)", rest)
    separate = re.match(r"(?:\+-|\\pm)\s*(\d*(?:[.,]\d*)?)", rest)
    if uncertainty:
        number.uncertainty = uncertainty.group(1).replace(",", ".")
        rest = rest[uncertainty.end():].strip()
    elif separate and separate.group(1):
        number.uncertainty = _compact(number, separate.group(1).replace(",", "."))
        rest = rest[separate.end():].strip()
    exponent = re.match(r"[eEdD]\s*([+-]?)\s*(\d+)", rest)
    if exponent:
        number.exponent = ("-" if exponent.group(1) == "-" else "") + exponent.group(2).lstrip("0") or "0"
        if exponent.group(2).strip("0") == "":
            number.exponent = "0"
        rest = rest[exponent.end():].strip()
    if rest or not (number.integer or number.decimal or number.exponent):
        raise SiunitxError(f"siunitx would not read the number {text!r}")
    if number.decimal == "":
        number.decimal = None                       # 5. is 5
    if number.decimal is not None and number.integer == "":
        number.integer = "0"                        # .5 is 0.5
    return number


def _compact(number: Number, uncertainty: str) -> str:
    """± 0.04 on 1.23 as siunitx's compact form: (4)"""
    places = len(number.decimal or "")
    whole, _, fraction = uncertainty.partition(".")
    if len(fraction) > places:
        number.decimal = (number.decimal or "") + "0" * (len(fraction) - places)
        places = len(fraction)
    digits = (whole + fraction.ljust(places, "0")).lstrip("0")
    return digits or "0"


def _grouped(digits: str, settings: Settings, from_left: bool) -> list[str]:
    if len(digits) < settings.group_minimum_digits:
        return [digits]
    if from_left:
        return [digits[i:i + 3] for i in range(0, len(digits), 3)]
    head = len(digits) % 3 or 3
    return [digits[:head]] + [digits[i:i + 3] for i in range(head, len(digits), 3)]


def number_runs(number: Number, settings: Settings) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    if number.comparator:
        runs.append((number.comparator[0], ""))
    if number.sign:
        runs.append((number.sign[0], ""))
    integer_groups = _grouped(number.integer, settings, False) if settings.group_digits in ("all", "integer") else [
        number.integer]
    mantissa = settings.group_separator.join(integer_groups)
    if number.decimal is not None:
        decimal_groups = _grouped(number.decimal, settings, True) if settings.group_digits in ("all", "decimal") else [
            number.decimal]
        mantissa += settings.decimal_marker + settings.group_separator.join(decimal_groups)
    if number.uncertainty is not None:
        mantissa += "(" + number.uncertainty + ")"
    if number.exponent is not None:
        unity = number.integer in ("", "1") and number.decimal is None and number.uncertainty is None
        if mantissa and not (unity and not settings.print_unity_mantissa) and number.integer != "":
            runs += [(mantissa, ""), (settings.exponent_product, "op"), ("10", "")]
        else:
            runs.append(("10", ""))
        runs.append((number.exponent.replace("-", MINUS), "sup"))
    else:
        runs.append((mantissa, ""))
    return _merge(runs)


#
# units
#
@dataclass
class Unit:
    symbol: str
    power: int | str = 1
    product: str | None = None           # None: the quantity product; "": none (90°)
    qualifier: str | None = None


def _expand(text: str, settings: Settings, depth: int = 0) -> str:
    if depth > 8:
        raise SiunitxError("a unit shortcut refers to itself")
    def replace(found):
        name = found.group(1)
        if name in settings.shortcuts:
            return " " + _expand(settings.shortcuts[name], settings, depth + 1) + " "
        return found.group(0)
    return UNIT_MACRO.sub(replace, text)


def parse_unit(text: str, settings: Settings) -> list[Unit]:
    text = _expand(text, settings)
    if "\\" not in text:
        return _literal_unit(text)
    units: list[Unit] = []
    prefix, per, before_power = "", False, 1
    i = 0
    while i < len(text):
        c = text[i]
        if c in " \t\n{}":
            i += 1
            continue
        if c != "\\":
            raise SiunitxError(f"siunitx unit with text in it: {text!r}")
        name = re.match(r"\\([A-Za-z]+)", text[i:])
        if not name:
            raise SiunitxError(f"siunitx unit: {text!r}")
        name = name.group(1)
        i += 1 + len(name)
        if name == "per":
            per = True
        elif name in ("square", "cubic"):
            before_power = 2 if name == "square" else 3
        elif name == "raiseto":
            argument, i = _group(text, i)
            if argument is None:
                raise SiunitxError(text)
            before_power = argument.strip()
        elif name in ("squared", "cubed", "tothe"):
            if not units:
                raise SiunitxError(text)
            if name == "tothe":
                argument, i = _group(text, i)
                if argument is None:
                    raise SiunitxError(text)
                power = argument.strip()
            else:
                power = 2 if name == "squared" else 3
            units[-1].power = _times(units[-1].power, power)
        elif name == "of":
            argument, i = _group(text, i)
            if argument is None or not units:
                raise SiunitxError(text)
            units[-1].qualifier = argument.strip()
        elif name in ("cancel", "highlight"):
            if name == "highlight":
                _, i = _group(text, i)
        elif name in PREFIXES:
            prefix += PREFIXES[name]
        else:
            symbol, product = _unit_symbol(name, settings)
            if symbol is None:
                raise SiunitxError(f"siunitx unit \\{name} is not known")
            units.append(Unit(prefix + symbol, _times(-1 if per else 1, before_power), product))
            prefix, per, before_power = "", False, 1
    if prefix or not units:
        raise SiunitxError(f"siunitx unit: {text!r}")
    return units


def _unit_symbol(name: str, settings: Settings) -> tuple[str | None, str | None]:
    if name in settings.units:
        body, product = settings.units[name]
        inner = parse_unit(body, Settings(units={k: v for k, v in settings.units.items() if k != name},
                                          shortcuts=settings.shortcuts)) if "\\" in body else [Unit(body.strip())]
        if len(inner) == 1 and inner[0].power == 1:
            return inner[0].symbol, product
        return None, None
    if name in ABBREVIATIONS:
        words = ABBREVIATIONS[name].split()
        return "".join(PREFIXES.get(word, "") for word in words[:-1]) + UNITS[words[-1]], None
    if name in UNITS:
        symbol = UNITS[name]
        return symbol, ("" if symbol in NO_PRODUCT else None)
    return None, None


def _times(a, b):
    try:
        return int(a) * int(b)
    except (TypeError, ValueError):
        if str(a) == "1":
            return b
        if str(b) == "1":
            return a
        if str(a) == "-1":
            return "-" + str(b)
        raise SiunitxError("a power siunitx would print as a product")


def _literal_unit(text: str) -> list[Unit]:
    """`g/mol`, `g.mol^{-1}`, `m~s^{-1}`: siunitx prints literal units as written, `.` and `~` as the product"""
    units: list[Unit] = []
    for piece in re.split(r"([.~ /])", text.replace("{", "").replace("}", "")):
        if piece in (".", "~", " ", ""):
            continue
        if piece == "/":
            units.append(Unit("/", 1, ""))
            continue
        found = re.fullmatch(r"([^\^_]+)(?:\^([+-]?\d+))?", piece)
        if not found:
            raise SiunitxError(f"siunitx literal unit: {text!r}")
        units.append(Unit(found.group(1), int(found.group(2)) if found.group(2) else 1))
    if not units:
        raise SiunitxError(f"siunitx literal unit: {text!r}")
    return units


def unit_runs(units: list[Unit], settings: Settings) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    if settings.per_mode in ("symbol", "repeated-symbol") and any(_negative(u.power) for u in units):
        top = [u for u in units if not _negative(u.power)]
        bottom = [Unit(u.symbol, _positive(u.power), u.product, u.qualifier) for u in units if _negative(u.power)]
        runs += _unit_list(top or [Unit("1")], settings)
        if len(bottom) > 1 and settings.per_mode == "symbol":
            runs.append(("/(", ""))
            runs += _unit_list(bottom, settings)
            runs.append((")", ""))
        else:
            for u in bottom:
                runs.append(("/", ""))
                runs += _unit_list([u], settings)
        return _merge(runs)
    return _merge(_unit_list(units, settings))


def _negative(power) -> bool:
    return str(power).startswith("-")


def _positive(power):
    return int(power) * -1 if isinstance(power, int) else str(power)[1:]


def _unit_list(units: list[Unit], settings: Settings) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    for index, unit in enumerate(units):
        if unit.symbol == "/":
            runs.append(("/", ""))
            continue
        if index and units[index - 1].symbol != "/":
            runs.append((settings.inter_unit_product, ""))
        runs.append((unit.symbol, ""))
        if unit.qualifier:
            runs.append((unit.qualifier, "sub"))
        if str(unit.power) != "1":
            runs.append((str(unit.power).replace("-", MINUS), "sup"))
    return runs


def _merge(runs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for text, place in runs:
        if not text:
            continue
        if out and out[-1][1] == place:
            out[-1] = (out[-1][0] + text, place)
        else:
            out.append((text, place))
    return out


#
# the commands
#
def _blank(text: str) -> bool:
    """`\\SI{1.8e-5}{}`: siunitx v2 style, an empty unit prints the number alone, as `\\num` does"""
    return not re.sub(r"[\s{}]", "", text)


def _quantity(number_text: str, unit_text: str, settings: Settings) -> list[tuple[str, str]]:
    number = parse_number(number_text)
    if _blank(unit_text):
        return number_runs(number, settings)
    units = parse_unit(unit_text, settings)
    product = units[0].product if units[0].product is not None else settings.quantity_product
    return _merge(number_runs(number, settings) + [(product, "")] + unit_runs(units, settings))


def _items(text: str) -> list[str]:
    return [item.strip() for item in text.split(";")]


def _join(parts: list[list[tuple[str, str]]], settings: Settings) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    for index, part in enumerate(parts):
        if index:
            if len(parts) == 2:
                runs.append((settings.list_pair_separator, "word"))
            elif index == len(parts) - 1:
                runs.append((settings.list_final_separator, "word"))
            else:
                runs.append((settings.list_separator, "word"))
        runs += part
    return _merge(runs)


def _angle(text: str, settings: Settings) -> list[tuple[str, str]]:
    parts = text.split(";")
    if len(parts) > 3:
        raise SiunitxError(f"siunitx angle: {text!r}")
    runs: list[tuple[str, str]] = []
    for value, symbol in zip(parts, ("\u00b0", "\u2032", "\u2033")):
        if value.strip():
            runs += number_runs(parse_number(value), settings) + [(symbol, "")]
    if not runs:
        raise SiunitxError(f"siunitx angle: {text!r}")
    return _merge(runs)


COMMANDS = {"num": 1, "numlist": 1, "numrange": 2, "numproduct": 1, "si": 1, "unit": 1, "SI": 2, "qty": 2,
            "SIlist": 2, "qtylist": 2, "SIrange": 3, "qtyrange": 3, "ang": 1}


def convert(command: str, settings: Settings | None = None) -> list[tuple[str, str]]:
    """the runs a siunitx command prints: convert(r"\\qty{25}{\\mL}") is [("25\u202fmL", "")]"""
    settings = settings or Settings()
    found = re.match(r"\\([A-Za-z]+)", command.strip())
    if not found or found.group(1) not in COMMANDS:
        raise SiunitxError(f"not a siunitx command: {command!r}")
    name = found.group(1)
    text = command.strip()
    options, after = _optional(text, found.end())
    local = Settings(**{key: value for key, value in vars(settings).items()})
    if options:
        apply_options(local, _keyvals(options))
    arguments = []
    for _ in range(COMMANDS[name]):
        argument, after = _group(text, after)
        if argument is None:
            raise SiunitxError(f"\\{name} needs {COMMANDS[name]} argument(s): {command!r}")
        arguments.append(argument)
    if text[after:].strip():
        raise SiunitxError(f"text after \\{name}: {command!r}")
    if name == "num":
        return number_runs(parse_number(arguments[0]), local)
    if name in ("si", "unit"):
        return [] if _blank(arguments[0]) else unit_runs(parse_unit(arguments[0], local), local)
    if name in ("SI", "qty"):
        return _quantity(arguments[0], arguments[1], local)
    if name == "ang":
        return _angle(arguments[0], local)
    if name == "numlist":
        return _join([number_runs(parse_number(item), local) for item in _items(arguments[0])], local)
    if name in ("SIlist", "qtylist"):
        return _join([_quantity(item, arguments[1], local) for item in _items(arguments[0])], local)
    if name == "numrange":
        return _merge(number_runs(parse_number(arguments[0]), local) + [(local.range_phrase, "word")]
                      + number_runs(parse_number(arguments[1]), local))
    if name in ("SIrange", "qtyrange"):
        return _merge(_quantity(arguments[0], arguments[2], local) + [(local.range_phrase, "word")]
                      + _quantity(arguments[1], arguments[2], local))
    raise SiunitxError(f"\\{name} is not supported")


#
# runs as TeX math
#
TEX_TEXT = {THIN: "\\,", "\u00a0": "\\ ", " ": "\\ ", MINUS: "-", "\u00d7": "\\times ", "\u00b1": "\\pm ",
            "\u2213": "\\mp ", "\u2264": "\\leq ", "\u2265": "\\geq ", "\u226a": "\\ll ", "\u226b": "\\gg ",
            "\u2248": "\\approx ", "\u223c": "\\sim ", "\u221d": "\\propto ", "\u22c5": "\\cdot ", "\u2005": "\\;",
            "\u2003": "\\quad ", "%": "\\%", "\u2193": "\\downarrow ", "\u2191": "\\uparrow ", "\u2261": "\\equiv ",
            "\u22ef": "\\cdots ", "\u2192": "\\rightarrow ", "\u2190": "\\leftarrow ", "\u2022": "\\bullet ",
            "\u00b7": "\\cdot "}


def _tex_text(text: str, upright: bool) -> str:
    """text as math: numbers as they are, a symbol or a unit upright (\\mathrm), the characters TeX spells otherwise
    (TEX_TEXT) as TeX"""
    out, word, kind = [], "", None

    def flush():
        nonlocal word
        if word:
            out.append(("\\mathrm{" + word + "}") if upright and kind == "symbol" else word)
            word = ""
    for c in text:
        if c in TEX_TEXT or c in "{},":
            flush()
            out.append(TEX_TEXT.get(c) or ("{,}" if c == "," else "\\" + c))
            continue
        now = "number" if c.isdigit() or c in ".()[]<>=+-/'" else "symbol"
        if now != kind:
            flush()
            kind = now
        word += c
    flush()
    return "".join(out)


def runs_text(runs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """runs for text: an operator between thin spaces, prose as it is; places "", "sup", "sub" only"""
    out = []
    for text, place in runs:
        if place == "op":
            out.append((THIN + text + THIN, ""))
        elif place == "word":
            out.append((text, ""))
        else:
            out.append((text, place))
    return _merge(out)


def runs_tex(runs: list[tuple[str, str]]) -> str:
    """runs as math TeX texmath reads: letters upright, `{,}` for a comma, thin spaces as `\\,`, prose in \\text"""
    out = []
    for text, place in runs:
        if place == "word":
            out.append("\\text{" + text.replace("{", "\\{").replace("}", "\\}") + "}")
            continue
        if place == "op":
            out.append(TEX_TEXT.get(text, text))
            continue
        body = _tex_text(text, True)
        if place == "sup":
            out.append("^{" + body + "}")
        elif place == "sub":
            out.append("_{" + body + "}")
        else:
            out.append(body)
    return "".join(out)
