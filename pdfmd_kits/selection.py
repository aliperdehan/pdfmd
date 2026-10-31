"""Choosing kits: what a `kit:` value says, and how the layers' choices stack.

A `kit:` value (in the config, a preset, a folder's files, a document's `pdfmd-options:`, or `--kit` on the command line)
is read by `parse`:

    nulabreport                     the kit, no mode asked for (its default mode applies)
    nulabreport:qca                 the short form: no quotes needed in YAML or in a shell
    nulabreport[qca]                the same (zsh wants quotes on a command line: the brackets are a glob)
    "[qca]nulabreport"              the same; MUST be quoted in YAML
    {nulabreport: qca}              a mapping: the key is the kit, a scalar value is its mode
    {nulabreport: {mode: qca, ...}} a mapping value may carry more (kept in `Selection.options`)
    [nulabreport:qca, other]        a list: the order is the order of the stack
    none | off | false | no         no kit: drops what the layers below chose
    ~/kits/x, ./kits/x, C:\\kits\\x   a value with `/` `\\` or a leading `~` or `.` is a PATH (its mode only in the mapping form)

`stack` puts the layers on top of each other (lowest first): the same kit named again in a higher layer replaces the keys it
names (the mode, the options) and keeps the rest; a different kit is added after; `none` empties what is below. `combine`
adds the command line: `--kit` replaces every `kit:` unless the `kit-stack` setting says which layers it stacks on.

Pure: no pdfmd import.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .kitfile import normalise

LAYERS = ("global", "preset", "folder", "document")      # lowest first; the command line is above them all
OFF_WORDS = frozenset({"none", "off", "false", "no"})


class SelectionError(ValueError):
    """A `kit:` value that cannot be read; the message says which and why."""


@dataclass(frozen=True)
class Selection:
    ref: str | None                 # a name or a path; None for "no kit" (drop what is below)
    mode: str | None = None
    options: dict = field(default_factory=dict, hash=False, compare=False)
    layer: str = ""                 # the layer that set it, for messages and for the folder rule

    @property
    def off(self) -> bool:
        return self.ref is None

    @property
    def key(self) -> str:
        return "" if self.ref is None else normalise(self.ref) if not path_like(self.ref) else self.ref.replace("\\", "/")


OFF = Selection(None)


def path_like(text: str) -> bool:
    return "/" in text or "\\" in text or text.startswith(("~", "."))


def _text(value) -> str | None:
    """A mode written as a scalar (220 is a number in YAML)."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _from_string(text: str) -> Selection:
    text = text.strip()
    if not text:
        raise SelectionError("an empty kit name")
    if text.casefold() in OFF_WORDS:
        return OFF
    if path_like(text):
        return Selection(text)
    if text.startswith("["):                              # [qca]nulabreport
        mode, close, rest = text[1:].partition("]")
        if not close or not rest.strip() or not mode.strip():
            raise SelectionError(f"cannot read {text!r}: write [mode]name, name[mode] or name:mode")
        return Selection(rest.strip(), mode.strip())
    if text.endswith("]") and "[" in text:                # nulabreport[qca]
        name, _, mode = text[:-1].partition("[")
        if not name.strip() or not mode.strip():
            raise SelectionError(f"cannot read {text!r}: write [mode]name, name[mode] or name:mode")
        return Selection(name.strip(), mode.strip())
    if "[" in text or "]" in text:
        raise SelectionError(f"cannot read {text!r}: write [mode]name, name[mode] or name:mode")
    if ":" in text:                                       # nulabreport:qca
        name, _, mode = text.partition(":")
        if not name.strip() or not mode.strip():
            raise SelectionError(f"cannot read {text!r}: write [mode]name, name[mode] or name:mode")
        return Selection(name.strip(), mode.strip())
    return Selection(text)


def parse(value, layer: str = "") -> list[Selection]:
    """The selections a `kit:` value makes, in order; [] for no value. ``OFF`` stands for the switch-off words."""
    if value is None:
        return []
    found: list[Selection]
    if value is False:                                    # YAML reads `off`, `no` and `false` as False
        found = [OFF]
    elif value is True:
        raise SelectionError("`kit: true` names no kit; write a name (nulabreport) or none")
    elif isinstance(value, (str, int, float)):
        found = [_from_string(str(value))]
    elif isinstance(value, list):
        found = []
        for item in value:
            found += parse(item, layer)
    elif isinstance(value, dict):
        found = []
        for name, detail in value.items():
            ref = str(name).strip()
            if not ref:
                raise SelectionError("an empty kit name")
            if ref.casefold() in OFF_WORDS:
                found.append(OFF)
            elif detail is True:
                raise SelectionError(f"cannot read the settings of kit {ref!r}: a mode, or a mapping with `mode:`")
            elif detail is False:
                found.append(OFF)
            elif isinstance(detail, dict):
                options = dict(detail)
                mode = _text(options.pop("mode", None))
                found.append(Selection(ref, mode, options))
            elif isinstance(detail, (str, int, float)) or detail is None:
                found.append(Selection(ref, _text(detail)))
            else:
                raise SelectionError(f"cannot read the settings of kit {ref!r}: a mode, or a mapping with `mode:`")
    else:
        raise SelectionError(f"cannot read a kit from {value!r}")
    return [replace(item, layer=layer) for item in found]


def stack(layers: list[list[Selection]]) -> list[Selection]:
    """The layers (lowest first) laid over each other; a list of selections where none is OFF."""
    result: list[Selection] = []
    for selections in layers:
        for item in selections:
            if item.off:
                result = []
                continue
            for index, below in enumerate(result):
                if below.key == item.key:
                    result[index] = replace(below, ref=item.ref, mode=item.mode or below.mode,
                                            options={**below.options, **item.options}, layer=item.layer)
                    break
            else:
                result.append(item)
    return result


def parse_stack_setting(value) -> frozenset[str] | str:
    """The `kit-stack` setting: "off" (the command line replaces every `kit:`), "all", or the layers (a subset of LAYERS) whose
    choices the command line stacks on."""
    if value is None or value is False:
        return "off"
    if value is True:
        return "all"
    words = [str(item).strip().casefold() for item in value] if isinstance(value, list) else \
        [part.strip().casefold() for part in str(value).replace(",", " ").split()]
    words = [word for word in words if word]
    if not words or words == ["off"] or words == ["no"] or words == ["false"] or words == ["none"]:
        return "off"
    if words == ["all"] or words == ["true"] or words == ["yes"] or words == ["on"]:
        return "all"
    unknown = [word for word in words if word not in LAYERS]
    if unknown:
        raise SelectionError(f"kit-stack: {', '.join(unknown)} is not off, all or a layer ({', '.join(LAYERS)})")
    return frozenset(words)


def combine(layers: dict[str, list[Selection]], cli: list[Selection] | None, kit_stack: frozenset[str] | str = "off") -> list[Selection]:
    """The stack of the layers (a dict by layer name, each already parsed) with the command line's ``cli`` on top.
    ``cli`` None: no `--kit` was given, so the layers alone. A cli that is only OFF (bare `--kit`, `--kit none`) is no kit at
    all. Otherwise `--kit` replaces the layers unless ``kit_stack`` ("all", or a set of layers) keeps them."""
    if cli is None:
        return stack([layers.get(name, []) for name in LAYERS])
    if not cli or all(item.off for item in cli):
        return []
    if kit_stack == "off":
        kept: list[str] = []
    elif kit_stack == "all":
        kept = list(LAYERS)
    else:
        kept = [name for name in LAYERS if name in kit_stack]
    return stack([*(layers.get(name, []) for name in kept), cli])
