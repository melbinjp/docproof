"""Link targets are path claims, and the wrong ones are the ones a reader clicks.

`inline_link_labels` used to say outright that judging link targets was "a real feature and
this is not it". The sample that made it worth building is `elementor/elementor#37006`: eleven
documented paths pointing at files that are gone, of which this tool reported six. Three of the
five it missed were link targets, and every one was the same broken path it had already flagged
a line or two above in backticks.

Measured on that document with its real move history: three findings before, six after, and the
one link that still resolves is not among them.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.docs import read
from docproof.model import Verdict
from docproof.project import Project
from docproof.verifiers.base import Document
from docproof.verifiers.paths import DocumentedPaths, link_targets


def run(repo: Path) -> list[tuple[str, int, Verdict]]:
    project = Project(root=repo)
    documents = [Document(path=p, text=read(p)) for p in sorted(repo.rglob("*.md"))]
    outcome = DocumentedPaths().run(project, documents)
    return sorted((f.claim.subject, f.claim.line, f.verdict) for f in outcome.findings)


def test_a_link_to_a_file_that_moved_is_broken(make_repo: Callable[..., Path]):
    """The elementor shape, minimally: a doc in a subdirectory linking up and across."""
    repo = make_repo(
        renamed={"src/views/empty.js": "src/other/empty.js"},
        documented_before={"docs/guide/index.md": "See [empty.js](../../src/views/empty.js) for the view.\n"},
        files={"NOTES.md": "Nothing to check here." + chr(10)},
    )
    found = run(repo)
    assert [(s, v) for s, _, v in found] == [("src/views/empty.js", Verdict.BROKEN)]


def test_a_link_that_still_resolves_is_left_alone(make_repo: Callable[..., Path]):
    """`view.js` genuinely stayed behind in the real document. Leaving correct lines alone is
    what makes the wrong ones believable."""
    repo = make_repo(
        files={
            "docs/guide/index.md": "See [view.js](../../src/views/view.js).\n",
            "src/views/view.js": "",
        }
    )
    assert [(s, v) for s, _, v in run(repo) if v is Verdict.BROKEN] == []


def test_the_same_path_twice_is_reported_at_both_lines(make_repo: Callable[..., Path]):
    """A backticked mention must not swallow the link 300 lines below it.

    Both lines need editing. A report naming one of them reads as a single defect, and
    somebody working from it fixes the sentence and leaves the live 404 in place.
    """
    repo = make_repo(
        renamed={"src/views/empty.js": "src/other/empty.js"},
        documented_before={
            "docs/guide/index.md": "The view is `src/views/empty.js`.\n\n"
            "Filler.\n\n"
            "Link to the actual file: [empty.js](../../src/views/empty.js)\n"
        },
        files={"NOTES.md": "Nothing to check here." + chr(10)},
    )
    lines = sorted(line for subject, line, verdict in run(repo) if verdict is Verdict.BROKEN)
    assert lines == [1, 5], lines


def test_what_is_not_ours_to_resolve_is_dropped(tmp_path: Path):
    """URLs, anchors, mail and other schemes are not paths, and a target that escapes the
    repository is not something this tool can say anything about."""
    doc = tmp_path / "docs" / "index.md"
    doc.parent.mkdir(parents=True)
    text = (
        "[a](https://example.invalid/x.js) [b](http://example.invalid/y.js) "
        "[c](mailto:someone@example.invalid) [d](#a-heading) [e](//cdn.example.invalid/z.js) "
        "[f](ftp://example.invalid/w.js) [g](../../../../outside/the/repo.js) "
        "[h](src/real.js) [i](src/real.js#L4)"
    )
    doc.write_text(text, encoding="utf-8")
    got = [token for token, _ in link_targets(text, doc, tmp_path)]
    assert got == ["docs/src/real.js", "docs/src/real.js"]


def test_a_target_with_a_fragment_keeps_only_the_file(tmp_path: Path):
    doc = tmp_path / "index.md"
    text = "[x](src/a.js#L10) and [y](src/b.js?raw=1)"
    doc.write_text(text, encoding="utf-8")
    assert [t for t, _ in link_targets(text, doc, tmp_path)] == ["src/a.js", "src/b.js"]
