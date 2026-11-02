"""Choosing one document among several for bare `pdfmd` (entry 3eu of the maintainer's notes).

The steps, in order:
  1. each document's own `priority` value is read (`Ranking.read`); `never` documents leave the list;
  2. a FAMILY is a base name plus trailing version words (`report`, `report.final`, `report_draft`); a family whose members
     set no priority themselves is collapsed to one document by its names (names settle which version of a document);
  3. everything left is ranked by priority, a missing one being `unset` (priority settles which document);
  4. equal tops are settled by the other criteria of `by` (the newest file by default), with a warning, or are an error.

Pure: paths and modification times come in as `Candidate`s; messages go out in the `Choice`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from .rules import Rank, Ranking, compare

MISSING: Any = object()


@dataclass
class Candidate:
    path: Path
    value: Any = MISSING          # the raw `priority` value, MISSING when the document sets none
    where: str = "priority"       # where it was written, for the messages ("priority", "pdfmd-options priority")
    mtime_ns: int = 0


@dataclass
class Choice:
    winner: Path | None = None
    skipped: list[tuple[Path, str]] = field(default_factory=list)      # (document, why it lost)
    warnings: list[str] = field(default_factory=list)                  # full `WARN  ...` lines
    error: str | None = None
    settled_by: str | None = None                                      # "newest" ... when equal priorities were settled

    def beaten(self, show: Callable[[Path], str]) -> str:
        """`a.md [name: draft], b.md [priority: never]`: what lost and why, for the AUTO line."""
        return ", ".join(f"{show(path)} [{why}]" for path, why in self.skipped)


@dataclass
class _Item:
    cand: Candidate
    value: Any = None                  # the parsed `Value` when the document set a usable priority, else None
    parts: Any = None                  # NameParts
    name_rank: Rank | None = None      # the rank its name gives (used when names: folder, or inside a family)


def _natural(text: str) -> list:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text)]


def _best(items: Sequence[_Item], rank_of: Callable[[_Item], Rank]) -> list[_Item]:
    ranks = [rank_of(item) for item in items]
    return [item for item, rank in zip(items, ranks) if not any(compare(other, rank) > 0 for other in ranks)]


def _stamp(nanoseconds: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(nanoseconds / 1e9))


def _settle(pool: Sequence[_Item], tail: Sequence[str]) -> tuple[_Item | None, str | None]:
    """The one of `pool` the criteria after `priority` pick, and the criterion that did, or (None, None)."""
    pool = list(pool)
    for criterion in tail:
        if criterion == "newest":
            top = max(item.cand.mtime_ns for item in pool)
            pool = [item for item in pool if item.cand.mtime_ns == top]
        elif criterion == "oldest":
            low = min(item.cand.mtime_ns for item in pool)
            pool = [item for item in pool if item.cand.mtime_ns == low]
        elif criterion == "name":
            last = max(_natural(item.cand.path.name) for item in pool)
            pool = [item for item in pool if _natural(item.cand.path.name) == last]
        if len(pool) == 1:
            return pool[0], criterion
    return None, None


def explain(candidates: Sequence[Candidate], ranking: Ranking, choice: Choice,
            show: Callable[[Path], str] = lambda path: path.name) -> list[tuple[str, str, str, str]]:
    """One row per candidate for `pdfmd --which`: (document, verdict, what it says, when it was last changed)."""
    skipped = dict(choice.skipped)
    rows = []
    for candidate in candidates:
        says = []
        if candidate.value is not MISSING:
            value = ranking.read(candidate.value)
            says.append(f"{candidate.where}: {candidate.value}" if value.kind != "invalid" else f"{candidate.where}: {candidate.value!r} (not a priority)")
        parts = ranking.name_parts(candidate.path.stem)
        if parts.suffix:
            says.append(f"name: {parts.suffix}")
        if candidate.path == choice.winner:
            verdict = "BUILT"
        elif choice.winner is None:
            verdict = "tied"
        else:
            verdict = "left: " + skipped.get(candidate.path, "ranks lower")
        rows.append((show(candidate.path), verdict, "; ".join(says) or "nothing set", _stamp(candidate.mtime_ns)))
    return rows


def choose(candidates: Sequence[Candidate], ranking: Ranking, by: Sequence[str] | None = None,
           show: Callable[[Path], str] = lambda path: path.name, include_excluded: bool = False) -> Choice:
    """Pick one of ``candidates``. ``include_excluded``: the documents that say `never` (by priority or by name) take part as if
    they had said nothing."""
    chain = tuple(ranking.by if by is None else by)
    tail = [criterion for criterion in chain if criterion != "priority"]
    choice = Choice()
    live: list[_Item] = []

    for candidate in candidates:
        item = _Item(candidate)
        if candidate.value is not MISSING:
            value = ranking.read(candidate.value)
            if value.kind == "invalid":
                choice.warnings.append(f"WARN  {show(candidate.path)}: {candidate.where}: {candidate.value!r} is not a priority "
                                       f"({value.why}); treated as if it were not set")
            elif value.kind == "excluded":
                if include_excluded:
                    live.append(item)
                    continue
                choice.skipped.append((candidate.path, f"{candidate.where}: {value.label or candidate.value}"))
                continue
            elif value.rank.cls != "unset":
                item.value = value
        live.append(item)

    if not live:
        choice.error = ("Every Markdown file here is marked `priority: never`. Name one (`pdfmd NAME`), "
                        "or list them all with --all.")
        return choice

    def describe(item: _Item, by_name: bool = False) -> str:
        if item.value is not None:
            return f"{item.cand.where}: {item.cand.value}"
        if by_name and item.parts is not None and item.parts.suffix:
            return f"name: {item.parts.suffix}"
        return "no priority set"

    def label(item: _Item) -> str:
        if item.value is not None:
            return f"priority: {item.value.label}"
        if ranking.names == "folder" and item.name_rank is not None and item.parts is not None and item.parts.suffix:
            return f"name: {item.parts.suffix}"
        return "no priority"

    def tie(pool: Sequence[_Item], what: str, by_name: bool = False) -> _Item | None:
        """One of equal documents, picked by the criteria after `priority` (a warning), or None with the error set."""
        winner, how = _settle(pool, tail)
        names = ", ".join(show(item.cand.path) for item in pool)
        if winner is None:
            lines = [f"Several Markdown files tie for first place ({what}): {names}."]
            lines += [f"  {show(item.cand.path)}: {describe(item, by_name)}" for item in pool]
            if tail:
                lines.append("They were last changed at the same moment too, so there is nothing left to choose by.")
            else:
                lines.append("Name one (`pdfmd NAME`), give one a `priority:`, or let the newest win "
                             "(`ranking: {by: [priority, newest]}`).")
            choice.error = "\n".join(lines)
            return None
        reason = {"newest": f"the newest ({_stamp(winner.cand.mtime_ns)})", "oldest": f"the oldest ({_stamp(winner.cand.mtime_ns)})",
                  "name": "the last by name"}[how]
        choice.warnings.append(f"WARN  {len(pool)} Markdown files tie ({what}): {names}; using {show(winner.cand.path)}, {reason}. "
                               "Give one a `priority:`, or set `ranking: {by: [priority]}` to make a tie an error.")
        choice.settled_by = how
        for item in pool:
            if item is not winner:
                choice.skipped.append((item.cand.path, f"tie, not the {how}" if how in ("newest", "oldest") else "tie, earlier by name"))
        return winner

    if "priority" not in chain:
        if len(live) == 1:
            choice.winner = live[0].cand.path
            return choice
        winner, how = _settle(live, tail)
        if winner is None:
            names = ", ".join(show(item.cand.path) for item in live)
            choice.error = (f"Several Markdown files are equal ({names}) and nothing is left to choose by: "
                            f"{'they were last changed at the same moment' if tail else '`ranking: {by: []}` names no criterion'}.")
            return choice
        choice.winner = winner.cand.path
        choice.settled_by = how
        choice.skipped += [(item.cand.path, {"newest": "older", "oldest": "newer", "name": "earlier by name"}[how])
                           for item in live if item is not winner]
        return choice

    reps = live
    if ranking.names != "off" and len(live) > 1:
        groups: dict[str, list[_Item]] = {}
        for item in live:
            item.parts = ranking.name_parts(item.cand.path.stem)
            groups.setdefault(item.parts.key, []).append(item)
        reps = []
        for group in groups.values():
            if len(group) == 1:
                parts = group[0].parts
                if parts.suffix and parts.value.kind == "rank":
                    group[0].name_rank = parts.value.rank          # only used when names: folder
                reps.append(group[0])
                continue
            if any(item.value is not None for item in group):
                reps.extend(group)                                  # the author wrote a priority: the names are not consulted
                continue

            def name_rank(item: _Item) -> Rank:
                parts = item.parts
                return parts.value.rank if parts.suffix and parts.value.kind == "rank" else ranking.unset

            kept = []
            for item in group:
                if item.parts.suffix and item.parts.value.kind == "excluded" and not include_excluded:
                    choice.skipped.append((item.cand.path, f"name: {item.parts.suffix}"))
                else:
                    kept.append(item)
            kept = kept or group
            top = _best(kept, name_rank)
            winner = top[0] if len(top) == 1 else tie(top, "the names rank them equally", by_name=True)
            if winner is None:
                return choice
            for item in kept:
                item.name_rank = name_rank(item)
                if item is not winner and item not in top:
                    choice.skipped.append((item.cand.path, f"name: {item.parts.suffix or 'bare name'}"))
            reps.append(winner)

    def rank_of(item: _Item) -> Rank:
        if item.value is not None:
            return item.value.rank
        if ranking.names == "folder" and item.name_rank is not None:
            return item.name_rank
        return ranking.unset

    top = _best(reps, rank_of)
    if len(top) == 1:
        winner = top[0]
    else:
        shown = label(top[0]) if len({label(item) for item in top}) == 1 else "equal priority"
        winner = tie(top, shown, by_name=ranking.names == "folder")
        if winner is None:
            return choice
    for item in reps:
        if item is not winner and item not in top:
            choice.skipped.append((item.cand.path, label(item)))
    choice.winner = winner.cand.path
    order = {candidate.path: index for index, candidate in enumerate(candidates)}
    choice.skipped.sort(key=lambda entry: order.get(entry[0], 0))
    return choice
