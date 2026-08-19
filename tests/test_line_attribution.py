"""A finding names the line the path is on, not the line the fence started on.

**Measured, not imagined.** Running docproof over `esengine/DeepSeek-Reasonix` produced

    docs/SESSION_REFERENCE_ARCHITECTURE.md:114  [path]
      says   `desktop/frontend/src/components/FileMenu.tsx`
      but    deleted in 98280862c ... and never restored

Line 114 of that document is `desktop/frontend/src/lib/types.ts`, which exists. The file the
finding is about sits three lines further down, at 117. A fenced block is one `Span` whose
`line` is its first body line, and every token read out of it inherited that line.

**The cost is not cosmetic.** The first thing a maintainer does with a finding is open the
line it names. They open a line that is fine, and the report is refuted at a glance by
evidence the tool supplied itself. It is the same shape as a check that reports success while
blind: the output looks exactly like a correct one.

`tree.parse` already carried per-entry lines, which is why directory diagrams were always
right and only prose blocks, transcripts and file lists were wrong. That is also why no test
caught it: every fenced fixture in the suite either was a tree or happened to put its broken
path on the first line of the block.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.docs import Span, spans
from docproof.project import Project
from docproof.verifiers.paths import DocumentedPaths, candidates

# Four paths, and the broken one is deliberately NOT first. The original defect is invisible
# on any block whose first line is the interesting one, which is exactly why it survived.
DOC = """\
# Session references

## Files to touch

```
desktop/frontend/src/lib/types.ts
desktop/frontend/src/lib/bridge.ts
src/pkg/kept.py
src/pkg/main.py
```
"""


def _claims(repo: Path) -> dict[str, int]:
    project = Project(root=repo)
    from docproof.docs import read
    from docproof.verifiers.base import Document

    document = Document(path=repo / "README.md", text=read(repo / "README.md"))
    found = {}
    for item in DocumentedPaths().extract(project, [document]):
        subject = getattr(item, "subject", None) or item.claim.subject
        line = getattr(item, "line", None) or item.claim.line
        found[subject] = line
    return found


def test_each_token_in_a_fenced_block_gets_its_own_line(make_repo: Callable[..., Path]) -> None:
    """The four paths are on four consecutive lines and must be reported on four."""
    repo = make_repo(
        {"README.md": DOC, "src/pkg/kept.py": "", "desktop/frontend/src/lib/types.ts": ""},
        deleted={"src/pkg/main.py": "print('hi')\n"},
        documented_before={"README.md": DOC},
    )
    at = _claims(repo)
    # Line 5 is the opening fence, so the body runs 6 to 9. These four numbers were written
    # as 7 to 10 on the first attempt and the test failed while the CODE was right - the
    # read-it-back test below passed throughout, which is the entire reason it is there.
    assert at["desktop/frontend/src/lib/types.ts"] == 6
    assert at["desktop/frontend/src/lib/bridge.ts"] == 7
    assert at["src/pkg/kept.py"] == 8
    # The one that matters: the broken path, three lines below the top of the block.
    assert at["src/pkg/main.py"] == 9


def test_an_inline_span_still_reports_its_own_line(make_repo: Callable[..., Path]) -> None:
    """The fix must not move the line for the ordinary case, which is most findings.

    An inline span is a single backticked token on one line, so its token line and its span
    line are the same number, and a change that got this wrong would move every finding in
    every README by however many lines the loop had counted.
    """
    text = "# Title\n\nsecond\n\nThe entry point is `src/pkg/main.py`.\n"
    repo = make_repo(
        {"README.md": text, "src/pkg/other.py": ""},
        deleted={"src/pkg/main.py": "print('hi')\n"},
        documented_before={"README.md": text},
    )
    assert _claims(repo)["src/pkg/main.py"] == 5


def test_candidates_reports_the_absolute_document_line() -> None:
    """Directly on the function, because the offset arithmetic is the whole fix.

    A span starting at document line 40 whose third body line holds a path must yield 42,
    and getting this off by one is the defect wearing a smaller hat.
    """
    span = Span(text="alpha/one.py\nbeta/two.py\ngamma/three.py", line=40, fenced=True)
    assert list(candidates(span)) == [
        ("alpha/one.py", 40),
        ("beta/two.py", 41),
        ("gamma/three.py", 42),
    ]


def test_the_line_matches_what_the_document_actually_says() -> None:
    """The strongest form of the assertion: read the line back out of the text.

    A test that hardcodes 10 passes if the fixture and the arithmetic drift together. This
    one fails unless the reported line, used as an index into the document, contains the
    path the finding is about - which is the property a maintainer relies on.
    """
    lines = DOC.split("\n")
    for span in spans(DOC):
        if not span.fenced:
            continue
        for token, at in candidates(span):
            assert token in lines[at - 1], f"{token!r} is not on line {at}: {lines[at - 1]!r}"
