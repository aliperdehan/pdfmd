"""The `.kit` file, format 1.

A kit is a folder that holds a YAML file named `.kit` (or `NAME.kit`). pdfmd names no package and no course: the
file is the data. Every path in it is relative to the kit's folder and stays inside it.

    kit-format: 1                  # required; a larger number stops with "needs a newer pdfmd"
    name: nulabreport              # defaults to the folder's name
    version: 1.30.0                # optional: left out, it is the version `<package>.sty` announces in \\ProvidesPackage
    description: House style of a chemistry department's lab reports
    package: nulabreport           # the LaTeX package the kit ships (NAME.sty beside this file); writes \\usepackage
    default-mode: genchem          # the mode used when none is asked for (optional)
    modes:                         # one named variant: package options, a defaults file, default text
      qca:
        aliases: [220, "chem 220"] # other names of the mode, matched like names (case, - _ . and spaces ignored)
        options: [qca]             # package options (a list or one word)
        defaults: qca-metadata.yaml  # a metadata file (a list works too), below the kit-level defaults
        metadata: {course: "CHEM 220L"}   # default text: front-matter keys, over `defaults`
        latex: ['\\LabScheme{word}']      # lines written after the package line, for this mode
    latex: ['\\input{chemicals}']  # lines written after the package line, for every mode
    lua: [nulabreport.lua]         # Lua filters the kit adds to the build
    defaults: metadata.yaml        # metadata file(s) every mode gets (pdfmd-options, fonts, csl, bibliography ...)
    metadata: {}                   # default front-matter keys of every mode
    latex-keys: {experiment: LabExperiment}   # the helper blocks of `<package>-pdfmd.yaml`, with the same meaning:
    picture-cache: {}              #   latex-keys, picture-cache, draft-skip, office
    carry: [nulabreport.sty, chemicals.tex, assets/]   # the parts an attached source or a bundle takes along
    no-auto: [margin]              # pdfmd's own defaults the kit takes over (v3.32.8): margin, mainfont, monofont, mathfont,
                                   #   font, tablewidth; the document, a folder or the command line can still switch one back on

Reserved and accepted without a word, built later: `settings`, `requires`, `options`. Any other key is a WARN (a typo
should be seen), not a stop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

FORMAT = 1
FILE = ".kit"
SUFFIX = ".kit"

HELPER_BLOCKS = ("latex-keys", "picture-cache", "draft-skip", "office")
TOP_KEYS = frozenset({"kit-format", "name", "version", "description", "package", "default-mode", "modes", "latex", "lua",
                      "defaults", "metadata", "carry", "no-auto", *HELPER_BLOCKS})
# What `no-auto:` may name: the defaults that are decided once the kit is known. A kit is chosen from the layers and
# the discovered files, so it cannot switch off the finding of those (metadata, lua, preamble, kit ...).
KIT_NO_AUTO_KINDS = ("margin", "mainfont", "monofont", "mathfont", "font", "tablewidth")
RESERVED_KEYS = frozenset({"settings", "requires", "options"})
MODE_KEYS = frozenset({"aliases", "options", "defaults", "metadata", "latex", "description"})


def normalise(text) -> str:
    """A name for comparing: case folded, `-` `_` `.` and white space left out (`Nu-Lab-Report` = `nulab_report`)."""
    return re.sub(r"[-_.\s]+", "", str(text).strip()).casefold()


class KitError(Exception):
    """A kit that cannot be used. `problems` are whole sentences, one per fault, each naming the file or the key."""

    def __init__(self, problems, path: Path | None = None):
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        self.path = path
        super().__init__("\n".join(self.problems))


@dataclass(frozen=True)
class Mode:
    name: str
    aliases: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    defaults: tuple[Path, ...] = ()          # absolute, inside the kit's folder
    metadata: dict = field(default_factory=dict)
    latex: tuple[str, ...] = ()
    description: str = ""

    def answers_to(self, text) -> bool:
        wanted = normalise(text)
        return wanted == normalise(self.name) or any(wanted == normalise(alias) for alias in self.aliases)


@dataclass(frozen=True)
class Kit:
    path: Path                                # the `.kit` file
    folder: Path
    name: str
    version: str = ""
    description: str = ""
    package: str = ""
    default_mode: str = ""
    modes: dict = field(default_factory=dict)   # name -> Mode
    latex: tuple[str, ...] = ()
    lua: tuple[Path, ...] = ()
    defaults: tuple[Path, ...] = ()
    metadata: dict = field(default_factory=dict)
    helper: dict = field(default_factory=dict)  # the helper blocks that are there, by their names
    carry: tuple[str, ...] = ()
    no_auto: tuple[str, ...] = ()               # pdfmd defaults the kit switches off (KIT_NO_AUTO_KINDS)
    warnings: tuple[str, ...] = ()

    def answers_to(self, text) -> bool:
        return normalise(text) == normalise(self.name)


def _strings(value, where: str, problems: list[str]) -> tuple[str, ...]:
    """A string or a list of scalars as a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return (str(value),)
    if isinstance(value, (list, tuple)) and all(isinstance(item, (str, int, float)) and not isinstance(item, bool) for item in value):
        return tuple(str(item) for item in value)
    problems.append(f"{where} must be a word or a list of words")
    return ()


def _relative(text: str, folder: Path, where: str, problems: list[str], must_exist: bool = True) -> Path | None:
    """`text` as a path inside ``folder`` (never absolute, never leaving it), or None with the fault added to ``problems``."""
    if not text.strip():
        problems.append(f"{where} has an empty path")
        return None
    spelled = text.replace("\\", "/")
    if PurePosixPath(spelled).is_absolute() or PureWindowsPath(text).is_absolute() or PureWindowsPath(text).drive or spelled.startswith("~"):
        problems.append(f"{where}: {text!r} is not relative to the kit's folder")
        return None
    if ".." in PurePosixPath(spelled).parts:
        problems.append(f"{where}: {text!r} leaves the kit's folder")
        return None
    path = folder / spelled
    if must_exist and not path.is_file():
        problems.append(f"{where}: {text!r} is not a file in the kit's folder")
        return None
    return path


def _files(value, folder: Path, where: str, problems: list[str]) -> tuple[Path, ...]:
    found = [_relative(item, folder, where, problems) for item in _strings(value, where, problems)]
    return tuple(path for path in found if path is not None)


def _yaml(path: Path):
    try:
        import yaml
    except ImportError:
        raise KitError(f"{path}: reading a .kit file needs PyYAML (pip install pyyaml)", path) from None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise KitError(f"{path}: cannot be read ({error.strerror or error})", path) from None
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        first = str(error).strip().splitlines()[0] if str(error).strip() else "not valid YAML"
        raise KitError(f"{path}: not valid YAML ({first})", path) from None


def load_kit(path: Path, extra_aliases: dict | None = None) -> Kit:
    """The kit of the `.kit` file ``path``, checked. ``extra_aliases`` ({mode: [alias, ...]}) are names a user added without
    editing the kit (the config's `kits:` entry). Raises KitError listing every fault found, not just the first."""
    path = Path(path)
    data = _yaml(path)
    if not isinstance(data, dict):
        raise KitError(f"{path}: a .kit file is a mapping (kit-format: 1, name: ...); this one is not", path)
    problems: list[str] = []
    warnings: list[str] = []
    if "kit-format" not in data:
        raise KitError(f"{path}: no `kit-format:`; write `kit-format: {FORMAT}` as the first line", path)
    declared = data["kit-format"]
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 1:
        raise KitError(f"{path}: `kit-format:` must be a whole number (this pdfmd reads {FORMAT})", path)
    if declared > FORMAT:
        raise KitError(f"{path}: kit-format {declared} needs a newer pdfmd (this one reads kit-format {FORMAT}); "
                       "pip install --upgrade pdfmd-cli", path)
    for key in data:
        if key not in TOP_KEYS and key not in RESERVED_KEYS:
            warnings.append(f"{path}: unknown key `{key}` (ignored)")
    folder = path.parent
    name = data.get("name", folder.name if folder.name else path.stem)
    if not isinstance(name, (str, int, float)) or isinstance(name, bool) or not str(name).strip() or not normalise(name):
        problems.append("`name:` must be a word")
        name = folder.name
    version = data.get("version", "")
    version = "" if version is None else str(version)
    description = data.get("description", "")
    description = description if isinstance(description, str) else ""
    package = data.get("package", "")
    if package is None:
        package = ""
    if not isinstance(package, str) or (package and not re.fullmatch(r"[A-Za-z0-9_.+-]+", package)):
        problems.append("`package:` must be the name of one LaTeX package (letters, digits, - _ . +)")
        package = ""
    modes: dict[str, Mode] = {}
    seen: dict[str, str] = {}
    raw_modes = data.get("modes", {})
    if raw_modes is None:
        raw_modes = {}
    if not isinstance(raw_modes, dict):
        problems.append("`modes:` must be a mapping of mode name -> its settings")
        raw_modes = {}
    extra = extra_aliases or {}
    for raw_name, raw in raw_modes.items():
        mode_name = str(raw_name)
        where = f"mode `{mode_name}`"
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            problems.append(f"{where} must be a mapping (options:, aliases:, defaults:, metadata:, latex:)")
            continue
        for key in raw:
            if key not in MODE_KEYS:
                warnings.append(f"{path}: unknown key `{key}` in {where} (ignored)")
        aliases = _strings(raw.get("aliases"), f"{where}: `aliases:`", problems)
        for given, aliased in extra.items():
            if normalise(given) == normalise(mode_name):
                aliases += _strings(aliased, f"the config's aliases of mode `{mode_name}`", problems)
        metadata = raw.get("metadata", {}) or {}
        if not isinstance(metadata, dict):
            problems.append(f"{where}: `metadata:` must be a mapping of front-matter keys")
            metadata = {}
        for word in (mode_name, *aliases):
            key = normalise(word)
            if not key:
                problems.append(f"{where}: an empty name")
            elif key in seen and seen[key] != mode_name:
                problems.append(f"{where}: `{word}` is also a name of mode `{seen[key]}`")
            else:
                seen[key] = mode_name
        modes[mode_name] = Mode(
            name=mode_name, aliases=aliases, options=_strings(raw.get("options"), f"{where}: `options:`", problems),
            defaults=_files(raw.get("defaults"), folder, f"{where}: `defaults:`", problems), metadata=metadata,
            latex=_strings(raw.get("latex"), f"{where}: `latex:`", problems),
            description=raw.get("description", "") if isinstance(raw.get("description", ""), str) else "")
    default_mode = data.get("default-mode", "")
    default_mode = "" if default_mode is None else str(default_mode)
    if default_mode:
        match = [mode for mode in modes.values() if mode.answers_to(default_mode)]
        if match:
            default_mode = match[0].name
        else:
            problems.append(f"`default-mode: {default_mode}` is not one of the modes ({', '.join(modes) or 'none'})")
            default_mode = ""
    metadata = data.get("metadata", {}) or {}
    if not isinstance(metadata, dict):
        problems.append("`metadata:` must be a mapping of front-matter keys")
        metadata = {}
    helper = {}
    for block in HELPER_BLOCKS:
        if block in data and data[block] is not None:
            if isinstance(data[block], (dict, list)):
                helper[block] = data[block]
            else:
                problems.append(f"`{block}:` must be a mapping" if block != "draft-skip" else "`draft-skip:` must be a mapping")
    carry = []
    for item in _strings(data.get("carry"), "`carry:`", problems):
        if _relative(item.rstrip("/"), folder, "`carry:`", problems, must_exist=False) is not None:
            carry.append(item)
    no_auto: list[str] = []
    given = data.get("no-auto")
    if given is True or (isinstance(given, str) and given.casefold() in ("true", "yes", "all")):
        warnings.append(f"{path}: `no-auto:` names the kinds to switch off ({', '.join(KIT_NO_AUTO_KINDS)}), not everything (ignored)")
    elif given not in (None, False):
        for item in _strings(given, "`no-auto:`", problems):
            if item in KIT_NO_AUTO_KINDS:
                if item not in no_auto:
                    no_auto.append(item)
            else:
                warnings.append(f"{path}: `no-auto: {item}` is not something a kit can switch off (it may name "
                                f"{', '.join(KIT_NO_AUTO_KINDS)}); ignored")
    latex = _strings(data.get("latex"), "`latex:`", problems)
    lua = _files(data.get("lua"), folder, "`lua:`", problems)
    defaults = _files(data.get("defaults"), folder, "`defaults:`", problems)
    if problems:
        raise KitError([f"{path}: {problem}" for problem in problems], path)
    if not version and package:
        version = package_file_version(folder, package)
    return Kit(path=path, folder=folder, name=str(name), version=version, description=description, package=package,
               default_mode=default_mode, modes=modes, latex=latex, lua=lua, defaults=defaults, metadata=metadata,
               helper=helper, carry=tuple(carry), no_auto=tuple(no_auto), warnings=tuple(warnings))


def package_file_version(folder: Path, package: str) -> str:
    """The version a kit's own `<package>.sty` announces in its `\\ProvidesPackage{package}[date vX.Y.Z ...]` line, or "" (no
    such file, no such line). A kit that leaves `version:` out takes it from here, so it cannot go stale at a release."""
    try:
        text = (Path(folder) / f"{package}.sty").read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    provides = re.search(rf"\\ProvidesPackage\{{{re.escape(package)}\}}\[([^\]]*)\]", text)
    version = re.search(r"\bv(\d+(?:\.\d+)*[a-zA-Z]*)\b", provides.group(1)) if provides else None
    return version.group(1) if version else ""


def resolve_mode(kit: Kit, text) -> Mode | None:
    """The mode ``text`` names (by name or alias), ``kit.default_mode`` for no text, None when the kit has no mode to give.
    An unknown mode raises KitError listing the modes."""
    if text is None or not str(text).strip():
        return kit.modes.get(kit.default_mode) if kit.default_mode else None
    for mode in kit.modes.values():
        if mode.answers_to(text):
            return mode
    known = "; ".join(f"{mode.name}" + (f" ({', '.join(mode.aliases)})" if mode.aliases else "") for mode in kit.modes.values())
    raise KitError(f"kit `{kit.name}` has no mode `{text}`" + (f" (its modes: {known})" if known else " (it has no modes)"), kit.path)
