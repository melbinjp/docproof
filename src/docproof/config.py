"""Letting a project say which documents are not promises.

Some documents are deliberately not descriptions of the current state. A build guide
written in an aspirational voice — *what this becomes* — sitting beside a README scoped to
what is true today is a common and perfectly sensible arrangement, and the project usually
says so in as many words. A checker that reports drift in the aspirational one is not
finding a bug; it is arguing with a decision the author already made and wrote down.

So there are two ways to say it, and both live with the project rather than in a flag
somebody has to remember to pass:

    # pyproject.toml
    [tool.docproof]
    exclude = ["agent.md", "docs/rfc/*.md"]

    <!-- docproof: skip-file — this describes the design, not the tree -->

The marker is deliberately the more visible of the two. A reader who finds a wrong path
in a document can see, in the document, that nobody is checking it.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any

SKIP_MARKER = re.compile(r"<!--\s*docproof:\s*skip-file\b", re.IGNORECASE)
SKIP_BLOCK = re.compile(r"<!--\s*docproof:\s*skip\s*(?:-->)?", re.IGNORECASE)

# Documents whose job is to describe the past. A changelog saying "0.68 moved
# `docs_src/websockets`" is *correct* and always will be, however many times that
# directory moves afterwards — the sentence is about a release, not about the tree.
#
# This is the largest single source of wrong findings there is: fastapi's
# `release-notes.md` alone produced 162 of them, more than every other document in
# twenty repositories combined. Recognised by the conventional names rather than by
# reading dates out of headings, because the convention is near-universal and a
# misread heading would put the tool back to guessing.
#
# `upgrading` and `migrat(e|ion|ing)` joined the list after probing the `symbols`
# verifier: marshmallow's `docs/upgrading.rst` shows `from marshmallow import
# MarshallingError`, a class removed in 3.0, as an illustration of the *old* API a
# reader is migrating away from. The sentence was true when written and stays true —
# it is a statement about a past release, exactly like a changelog entry, and the only
# reason it was not already caught is that "upgrading" was never on this list.
_HISTORICAL_NAMES = (
    r"changelog | changes | history | news | releases? | release[-_ ]?notes"
    r" | whatsnew | what[-_]s[-_]new | upgrad(?:e|ing) | migrat(?:e|ion|ing)"
)
# Matches the file's own name *and* any directory on the way to it. Pillow keeps its
# release notes as `docs/releasenotes/2.3.2.rst`, one file per version, and all eight of
# its findings came from there: the directory is the thing that says "this is history",
# and the filenames never could.
HISTORICAL = re.compile(
    rf"(?ix) (^|/) (?: {_HISTORICAL_NAMES} ) (?: \.[a-z0-9]+ )? (?: / | $ )"
    rf" | (^|/) changelog\.d/ "
)


def is_historical(relative_path: str) -> bool:
    """Whether a document describes the past rather than the current tree."""
    return bool(HISTORICAL.search(relative_path))


# A page can also say it in prose rather than in its name. bandit keeps doc pages for
# plugins B109 and B111 that open with "This plugin has been removed." — deliberate
# tombstones, kept so old links keep resolving — and pdm's `docs/dev/benchmark.md` opens
# "This page has been removed, please visit …". A stale example path inside such a page
# is not drift; the page has already told its reader it describes something that no
# longer exists.
#
# Narrow on purpose, from reading every candidate in the forty-repo corpus (a broad net
# matched eleven lines; exactly two were tombstones). The subject must be
# self-referential — "This page/plugin/module …" — and the verb must be *removed*.
# Deprecated is not removed: structlog's thread-local page documents a deprecated module
# that still exists, still makes promises, and still deserves judgment. A removal note
# about something else ("The ``scrapy deploy`` command has been removed in 1.0") is a
# live page stating history, not a tombstone.
TOMBSTONE = re.compile(r"(?i)^[\s>*_-]{0,8}This\s+\w+\s+(?:has been|was)\s+removed\b")


def declares_removed(text: str) -> bool:
    """Whether a document opens by declaring its own subject removed.

    Only the first ten non-blank lines are considered, for the same reason `opts_out`
    stops at forty: a declaration buried where no reader would see it before trusting
    the page should not silence the checker either.
    """
    lede = [line for line in text.split("\n") if line.strip()][:10]
    return any(TOMBSTONE.match(line) for line in lede)


@dataclass
class Config:
    exclude: tuple[str, ...] = ()
    docs: tuple[str, ...] = ()
    """Extra globs to treat as documentation, beyond the default discovery."""

    disable: frozenset[str] = field(default_factory=frozenset)
    """Verifier names to skip entirely."""

    @classmethod
    def from_pyproject(cls, data: dict[str, Any]) -> Config:
        table = data.get("tool", {})
        table = table.get("docproof", {}) if isinstance(table, dict) else {}
        if not isinstance(table, dict):
            return cls()

        def strings(key: str) -> tuple[str, ...]:
            value = table.get(key, [])
            if isinstance(value, str):
                return (value,)
            if isinstance(value, list):
                return tuple(str(v) for v in value)
            return ()

        return cls(
            exclude=strings("exclude"),
            docs=strings("docs"),
            disable=frozenset(strings("disable")),
        )

    def excludes(self, relative_path: str) -> bool:
        return any(fnmatch.fnmatch(relative_path, pattern) for pattern in self.exclude)


def opts_out(text: str) -> bool:
    """Whether a document has marked itself as not a claim about the current tree.

    Only the first 40 lines are searched. A marker buried at the bottom of a long file is
    invisible to the reader it is meant to inform, so it should not be effective either.
    """
    return bool(SKIP_MARKER.search("\n".join(text.split("\n")[:40])))


def suppressed_lines(text: str) -> frozenset[int]:
    """Line numbers covered by a `<!-- docproof: skip -->` marker.

    Documentation is full of paths that are illustrations rather than claims —
    *"suppose your entry point is `src/pkg/main.py`"* — and no amount of pattern matching
    separates a hypothetical from an assertion. This README's own examples were reported
    as drift the first time it checked itself, which is how the need for this was found.

    A marker covers the paragraph it introduces: from its own line to the next blank
    line. Paragraph scope rather than whole-file scope on purpose — a marker that
    silences a document forever is one nobody notices has outlived its reason.
    """
    lines = text.split("\n")
    covered: set[int] = set()
    for index, line in enumerate(lines):
        if not SKIP_BLOCK.search(line) or SKIP_MARKER.search(line):
            continue
        cursor = index
        while cursor < len(lines) and lines[cursor].strip():
            covered.add(cursor + 1)
            cursor += 1
        # A marker on a line of its own introduces the paragraph after the blank line.
        if lines[index].strip().startswith("<!--") and cursor < len(lines):
            cursor += 1
            while cursor < len(lines) and lines[cursor].strip():
                covered.add(cursor + 1)
                cursor += 1
    return frozenset(covered)
