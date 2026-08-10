"""Reading the directory diagrams that live in nearly every README.

```
rigout/
├── src/rigout/
│   ├── server.py
│   └── lifecycle.py
└── tests/
```

Every leaf there is a claim, and none of them can be checked as written: `server.py`
alone is meaningless, and looking for it at the repository root finds nothing. The claim
is `src/rigout/server.py`, and recovering it means reading the indentation.

These diagrams rot faster than prose does — they are copied once, at the point when
somebody was proud of the layout, and then files move. They are also the first thing a
new reader uses to orient, so a wrong one costs more than its size suggests.

**Where this refuses to guess.** A diagram whose indentation is inconsistent, or that
mixes tab and space alignment in a way that makes depth ambiguous, yields nothing at all
rather than a plausible-looking reconstruction. Half a tree read wrongly produces
confident findings about paths nobody wrote.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

# The box-drawing vocabulary, plus the ASCII forms people use when they cannot type it.
# Longest first: `|--` has to win over `|-`, and a regex with `|` in the indentation class
# eats the first character of the ASCII connectors, which is why this is scanned by hand.
CONNECTORS = ("├──", "└──", "├─", "└─", "|--", "`--", "+--", "|__", "\\--", "|-", "`-", "+-")

# Comments people hang off entries: `server.py   # the MCP server`.
TRAILING_COMMENT = re.compile(r"\s+(#|//|<-|←|--\s).*$")

# A diagram is only treated as one if it looks like one. Two independent signals, so a
# plain list of filenames in a code block is not mistaken for a layout.
TREE_CHARACTERS = re.compile(r"[│├└]|\|--|`--|\+--")


@dataclass(frozen=True)
class Entry:
    path: str
    """Full path from the diagram's root, e.g. `src/rigout/server.py`."""

    name: str
    """The leaf as written, for quoting back."""

    line: int
    """1-based line within the document."""

    directory: bool

    above_root: bool = False
    """This line hangs under a `..` in the diagram, so its real location is unknown.

    citerag's `docs/README.md` draws its own directory and then, at the same depth, a
    second block rooted at `../` listing the repository's top-level files. Those entries
    are real and their paths are real — but they are relative to somewhere above the
    diagram's own root, and nothing in the drawing says where that is. Reported rather
    than dropped, because a silently discarded claim and a checked one look identical
    from the outside.
    """


def split_line(line: str) -> tuple[int, str | None, str]:
    """Split a diagram line into (indent columns, connector, name).

    Scanned left to right rather than matched, because the indentation of an ASCII
    diagram is made of the same `|` character that starts its connectors, and any regex
    treating `|` as indentation swallows the first character of `|--`.

    **Columns, not levels.** Counting vertical bars looks like it should work and does
    not: the last child of a directory is drawn `└── ` and its continuation is four
    spaces, not `│   `, so a bar count reads the deepest branch of every subtree as
    shallower than its siblings. The column where the entry begins is the only thing
    every style agrees on. Turning columns into levels needs a stride, and the stride is
    a property of the diagram rather than of the line — see `parse`.
    """
    index = 0
    while index < len(line):
        for connector in CONNECTORS:
            if line.startswith(connector, index):
                return index, connector, line[index + len(connector) :].strip()
        if line[index] in "│| \t":
            index += 1
        else:
            break
    return index, None, line[index:].strip()


def _stride(indents: list[int]) -> int:
    """How many columns one level of nesting is worth, in this diagram.

    The smallest non-zero indent, confirmed against every other one. A diagram whose
    indents are not all multiples of it is not something this can read, and saying so is
    better than picking the most popular stride and misplacing the rest.
    """
    positive = [indent for indent in indents if indent > 0]
    if not positive:
        return 1
    stride = min(positive)
    if any(indent % stride for indent in positive):
        return 0
    return stride


def looks_like_a_tree(text: str) -> bool:
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < 3:
        return False
    drawn = sum(1 for line in lines if TREE_CHARACTERS.search(line))
    if drawn >= 2:
        return True
    # A diagram drawn with indentation alone. Three signals together, because any one of
    # them on its own also describes an ordinary code block: something is indented, at
    # least one entry is marked as a directory, and every line is a bare path-shaped
    # token rather than a statement.
    if not any(line[:1] in " \t" for line in lines):
        return False
    if not any(line.rstrip().endswith("/") for line in lines):
        return False
    return all(len(line.split()) == 1 and not set(line) & set("=(){};") for line in lines)


def parse(text: str, first_line: int) -> list[Entry]:
    """Full paths for every entry, or an empty list if the diagram is not readable.

    Returning nothing is the honest answer for an ambiguous diagram, and the caller
    reports it as unchecked rather than as clean.
    """
    if not looks_like_a_tree(text):
        return []

    # Pass one: read every line into (indent columns, has connector, name, line number).
    raw_lines: list[tuple[int, bool, str, bool, int]] = []
    for offset, raw in enumerate(text.replace("\t", "    ").split("\n")):
        if not raw.strip():
            continue
        indent, connector, name = split_line(TRAILING_COMMENT.sub("", raw.rstrip()))
        # Ellipses and annotations standing in for entries nobody listed.
        if not name or name in {"...", "…", "etc.", "(...)"} or name.startswith(("#", "//")):
            continue
        name = name.split(" ")[0].strip()
        if not name or any(character in name for character in "*?<>|"):
            continue
        raw_lines.append(
            (indent, connector is not None, name.rstrip("/"), name.endswith("/"), first_line + offset)
        )

    if not raw_lines:
        return []

    # Pass two: columns become levels, once, for the whole diagram.
    stride = _stride([indent for indent, *_ in raw_lines])
    if stride == 0:
        return []
    read_lines = [
        (indent // stride + (1 if connector else 0), name, is_dir, line)
        for indent, connector, name, is_dir, line in raw_lines
    ]

    # Pass two: a leading `.` or `name/` with everything else below it is the diagram's
    # own root. It names the repository rather than a directory inside it, so it is
    # dropped and the rest becomes zero-based. A diagram with no root line — a flat list
    # of top-level entries — is left alone.
    head_depth, head_name, head_is_dir, _ = read_lines[0]
    if (
        head_depth == 0
        and (head_name in {".", "./"} or head_is_dir)
        and all(depth > 0 for depth, _, _, _ in read_lines[1:])
    ):
        read_lines = [(depth - 1, name, is_dir, line) for depth, name, is_dir, line in read_lines[1:]]

    entries: list[Entry] = []
    stack: list[str] = []
    # Depth of a `..` entry whose subtree cannot be placed. Everything nested under it is
    # reported as unplaceable rather than resolved.
    above: int | None = None
    for depth, name, is_directory, line in read_lines:
        if above is not None:
            if depth > above:
                entries.append(
                    Entry(path=name, name=name, line=line, directory=is_directory, above_root=True)
                )
                continue
            above = None
        if depth > len(stack):
            # A jump deeper than one level means a line was skipped or read wrongly.
            return []
        stack = stack[:depth]
        if not name or name in {".", ".."}:
            # **Truncate the stack first, then skip.** Skipping before truncating was a
            # real bug: citerag's `docs/README.md` draws `docs/` and then a second block
            # rooted at `../`, and every entry under that second root inherited `docs/`.
            # `CONTRIBUTING.md` at the repository root was reported as
            # `docs/CONTRIBUTING.md`. It skipped rather than failed only because that
            # path had never existed — in a repository that had once had it and deleted
            # it, the same bug manufactures a BROKEN out of a correct document.
            above = depth
            continue
        full = "/".join([*stack, name])
        entries.append(Entry(path=full, name=name, line=line, directory=is_directory))
        if is_directory:
            stack = [*stack, name]

    return entries


def entries(text: str, first_line: int) -> Iterator[Entry]:
    yield from parse(text, first_line)
