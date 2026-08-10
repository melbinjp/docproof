"""Finding documentation, and pulling the checkable parts out of it.

Claims worth checking live in code spans, not in prose. `--no-auth` inside backticks is
an assertion that a flag exists; the same characters in a sentence usually are not. So
extraction works on spans, and everything downstream gets a line number with it, because
a finding without a line number makes the reader search for their own bug.

What this deliberately does not do is parse Markdown properly. A full parser would buy
very little here — the constructs that carry claims are inline code, fenced blocks and
plain paths — and would buy it at the cost of a dependency and a lot of behaviour that is
hard to explain when it goes wrong. Where this scanner cannot be sure, the rule from
`model.Verdict.SKIPPED` applies: it yields nothing rather than yielding a guess.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DOC_SUFFIXES = (".md", ".markdown", ".rst", ".txt")

# Directories that hold other people's documentation, or generated copies of your own.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        "site-packages",
        "dist",
        "build",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "htmlcov",
        "target",
        "vendor",
        "third_party",
    }
)

# ```lang ... ``` and ~~~ ... ~~~, non-greedy, with the opening fence's info string.
FENCE_RE = re.compile(
    r"^(?P<fence>```+|~~~+)(?P<info>[^\n]*)\n(?P<body>.*?)^(?P=fence)[ \t]*$", re.DOTALL | re.MULTILINE
)

# Inline code: one or more backticks, the same number closing, no blank line between.
INLINE_RE = re.compile(r"(?P<ticks>`+)(?P<body>(?:(?!(?P=ticks))[^\n]|\n(?!\n))+?)(?P=ticks)")

# reStructuredText literal blocks. Enormously common in Python documentation — flask,
# pytest, scrapy and urllib3 all keep their command examples this way — and invisible to
# a markdown-only reader. Missing them was found by this tool's own "checked nothing"
# rule firing on scrapy, whose docs are full of `scrapy crawl` lines it never saw.
RST_DIRECTIVE = re.compile(
    r"^(?P<indent>[ \t]*)\.\.[ \t]+(?:code-block|code|sourcecode|parsed-literal)::"
    r"[ \t]*(?P<info>\S*)[ \t]*$"
)
# A paragraph ending in `::` introduces a literal block in plain RST.
RST_LITERAL = re.compile(r"^(?P<indent>[ \t]*)(?:\S.*)?::[ \t]*$")
# `:option: value` lines belong to the directive, not to the block.
RST_FIELD = re.compile(r"^[ \t]*:[\w-]+:")


@dataclass(frozen=True)
class Span:
    """A run of text a document presents as code, and where it came from."""

    text: str
    line: int
    fenced: bool
    info: str = ""
    """The fence's info string — `bash`, `python`, `console` — or empty for inline."""


class LineIndex:
    """Offset to 1-based line number, without rescanning the document each time."""

    def __init__(self, text: str) -> None:
        self._starts = [0]
        for match in re.finditer(r"\n", text):
            self._starts.append(match.end())

    def at(self, offset: int) -> int:
        return bisect_right(self._starts, offset)


def find_docs(root: Path, extra: tuple[str, ...] = ()) -> list[Path]:
    """Documentation files a reader would plausibly believe.

    Top-level files and anything under a `doc`/`docs` directory. Not every Markdown file
    in the tree: a fixture, a vendored README or a changelog fragment deep in a package
    is not a promise the project is making, and treating it as one produces findings
    nobody asked for.
    """
    found: list[Path] = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix.lower() in DOC_SUFFIXES:
            found.append(path)
    for name in ("docs", "doc"):
        directory = root / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in DOC_SUFFIXES:
                continue
            if SKIP_DIRS & set(path.relative_to(root).parts):
                continue
            found.append(path)
    for pattern in extra:
        found.extend(sorted(p for p in root.glob(pattern) if p.is_file()))
    return sorted(set(found))


def read(path: Path) -> str:
    """UTF-8 with universal newlines, so a CRLF checkout reads the same as a LF one."""
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def spans(text: str) -> Iterator[Span]:
    """Every code span in the document, fenced blocks first, then inline.

    Inline spans inside a fenced block are not yielded twice: the fence is consumed and
    its interior is offered whole, because a shell transcript is one claim about how the
    program is invoked rather than a dozen claims about its punctuation.
    """
    index = LineIndex(text)
    fenced_ranges: list[tuple[int, int]] = []

    for match in FENCE_RE.finditer(text):
        fenced_ranges.append((match.start(), match.end()))
        body = match.group("body")
        body_start = match.start("body")
        yield Span(
            text=body,
            line=index.at(body_start),
            fenced=True,
            info=match.group("info").strip(),
        )

    for span, low, high in _rst_blocks(text):
        if any(a <= low < b for a, b in fenced_ranges):
            continue
        fenced_ranges.append((low, high))
        yield span

    for match in INLINE_RE.finditer(text):
        start = match.start()
        if any(low <= start < high for low, high in fenced_ranges):
            continue
        yield Span(text=match.group("body"), line=index.at(start), fenced=False)


def _rst_blocks(text: str) -> Iterator[tuple[Span, int, int]]:
    """Literal blocks introduced by a directive or by a paragraph ending in `::`.

    A block runs from the first indented line after the introducer until the indentation
    returns to the introducer's own level or shallower. Blank lines inside it belong to it.
    """
    lines = text.split("\n")
    offsets: list[int] = []
    running = 0
    for line in lines:
        offsets.append(running)
        running += len(line) + 1

    number = 0
    while number < len(lines):
        line = lines[number]
        directive = RST_DIRECTIVE.match(line)
        literal = None if directive else RST_LITERAL.match(line)
        if not directive and not literal:
            number += 1
            continue

        matched = directive or literal
        assert matched is not None
        base = len(matched.group("indent").expandtabs(4))
        info = directive.group("info") if directive else ""

        cursor = number + 1
        while cursor < len(lines) and (not lines[cursor].strip() or RST_FIELD.match(lines[cursor])):
            cursor += 1
        if cursor >= len(lines):
            break

        body_indent = len(lines[cursor][: len(lines[cursor]) - len(lines[cursor].lstrip())].expandtabs(4))
        if body_indent <= base:
            number += 1
            continue

        start = cursor
        end = cursor
        while cursor < len(lines):
            current = lines[cursor]
            if not current.strip():
                cursor += 1
                continue
            indent = len(current[: len(current) - len(current.lstrip())].expandtabs(4))
            if indent < body_indent:
                break
            end = cursor
            cursor += 1

        body = "\n".join(
            entry[body_indent:] if len(entry) > body_indent else entry.strip()
            for entry in lines[start : end + 1]
        )
        low = offsets[start]
        high = offsets[end] + len(lines[end])
        yield Span(text=body, line=start + 1, fenced=True, info=info), low, high
        number = end + 1


def command_lines(span: Span) -> Iterator[str]:
    """Shell command lines inside a span, with prompts and continuations resolved.

    **Once a block shows a prompt, the lines without one are output, not commands.** That
    sounds obvious and was not: pipx's docs print

        $ pipx run pycowsay --py
        pipx run: error: ambiguous option: --py could match --python-args, ...

    and the second line begins with the program's own name, so a reader of lines rather
    than of transcripts takes it for another invocation and reads `--py` out of the error
    message complaining about `--py`. A block with no prompts at all is a plain list of
    commands and every line counts.
    """
    prompted = any(line.strip().startswith(("$ ", "> ")) for line in span.text.split("\n"))
    pending = ""
    for raw in span.text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("$ ", "> ")):
            line = line[2:].strip()
        elif line in {"$", ">"} or (prompted and not pending):
            continue
        if pending:
            line = f"{pending} {line}"
            pending = ""
        if line.endswith("\\"):
            pending = line[:-1].strip()
            continue
        yield line
    if pending:
        yield pending
