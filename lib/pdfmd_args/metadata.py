"""British spellings of Pandoc's own metadata and template variables.

The names are aliases, not new pdfmd options. Normalise each layer before merging, so a document's British spelling can
replace a lower layer's Pandoc spelling. Template variables (-V) bypass filters and must be renamed on the command line.
"""

from __future__ import annotations

import re

from pdfmd_base import core

# Pandoc's default templates (including partials) and its manual's Variables section.
ALIASES = {key.replace("color", "colour"): key for key in (
    "backgroundcolor", "backgroundcolordark", "citecolor", "colorlinks", "colortheme", "colorthemeoptions",
    "contrastcolor", "filecolor", "fontcolor", "fontcolordark", "linkcolor", "linkcolordark", "linkcontrastcolor",
    "monobackgroundcolor", "monobackgroundcolordark", "quotebordercolor", "quotebordercolordark", "quotecolor",
    "quotecolordark", "toccolor", "urlcolor",
)} | {"centre": "center", "licence": "license", "organisation": "organization"}


def ignored(alias, key, where):
    message = f"NOTE  {alias} ignored in {where}: Pandoc's {key} wins"
    seen = core.BUILD.setdefault("metadata-alias-notes", [])
    if message not in seen:
        seen.append(message)
        print(message)


def command_aliases(arguments):
    """Rename only variable/metadata keys, preserving values, token forms and the -- boundary."""
    parts = []
    tokens = iter(arguments)
    for token in tokens:
        if token == "--":
            parts.append(([token, *tokens], None, None))
            break
        option, equals, value = token.partition("=")
        if option in ("-V", "--var", "--variable", "-M", "--metadata"):
            original = [token] if equals else [token, next(tokens, "")]
            value = value if equals else original[-1]
            prefix = option + "=" if equals else None
        elif token.startswith(("-V", "-M")) and len(token) > 2:
            option, value, prefix, original = token[:2], token[2:], token[:2], [token]
        else:
            parts.append(([token], None, None))
            continue
        kind = "metadata" if option in ("-M", "--metadata") else "variable"
        key = re.split("[:=]", value, maxsplit=1)[0]
        parts.append((original, (kind, key), (prefix, value)))
    present = {key for _, key, _ in parts if key is not None}
    result = []
    for original, identity, payload in parts:
        if identity is None or identity[1] not in ALIASES:
            result.extend(original)
            continue
        kind, alias = identity
        key = ALIASES[alias]
        if (kind, key) in present:
            ignored(alias, key, "command-line " + kind)
            continue
        prefix, value = payload
        renamed = key + value[len(alias):]
        result.extend([prefix + renamed] if prefix is not None else [original[0], renamed])
    return result


def metadata_alias_layers(layers, where):
    """Canonical layers plus the canonical keys needing an override of Pandoc's unnormalised input."""
    result, touched, removed = [], set(), set()
    for mapping, is_document in layers:
        data = dict(mapping)
        for alias, key in ALIASES.items():
            if alias not in data:
                continue
            touched.add(key)
            removed.add(alias)
            value = data.pop(alias)
            if key in data:
                ignored(alias, key, where)
            else:
                data[key] = value
        result.append((data, is_document))
    return result, touched, removed


def merged_alias_metadata(layers, append, where, arguments):
    """Finish metadata appending and alias precedence together, before the first user filter."""
    from pdfmd_args import metadata_command_layers, metadata_keys

    layers, touched, removed = metadata_alias_layers(layers, where)
    command_layers = metadata_command_layers(arguments)
    cli_appends = {key[:-1] for layer, _ in command_layers for key in layer if core.metadata_plus_key(key)}
    combined = [*layers, *command_layers]
    merged = core.merge_metadata_layers(combined, append, where)
    # Later layers replace earlier ones, except values already finished by the append merger.
    for key in touched - set(merged):
        for mapping, _ in reversed(combined):
            if key in mapping:
                merged[key] = mapping[key]
                break
    for key in metadata_keys(arguments) - cli_appends:
        merged.pop(key, None)
    if removed:
        merged["pdfmd-remove-keys"] = sorted(removed)
    return merged
