"""A translated docs tree is an overlay, not a copy, and the page nobody translated still ships.

FastAPI stages every language build by copying `docs/en/docs` wholesale and writing the
translated files over the top. A page deliberately left untranslated - `fastapi-people.md`,
`newsletter.md` - is therefore present in every language at build time, and a relative link to
it from a translated page resolves on the live site.

Without this rule the checker calls all of them broken. It called **twelve** broken in FastAPI,
on the first large repository the link-target feature was pointed at, and every one of them
works. That is the whole reason this file exists: recall bought at that price is not a gain.

The rule needs BOTH halves - the target exists next door AND the claiming document has a home
there too - because one parallel file is a coincidence and a mirrored tree is a structure.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.docs import read
from docproof.model import Verdict
from docproof.project import Project
from docproof.verifiers.base import Document
from docproof.verifiers.paths import DocumentedPaths, locale_sibling


def verdicts(repo: Path) -> dict[str, tuple[Verdict, str]]:
    """Verdict AND detail, because the verdict alone cannot tell these tests anything.

    The first version returned verdicts only and PASSED WITH THE RULE STUBBED OUT: without it
    the claim falls through to "this repository has never had this path", which is also
    SKIPPED. Two different reasons wearing one verdict, and the negative control is the only
    thing that showed it. Assert the reason.
    """
    project = Project(root=repo)
    documents = [Document(path=p, text=read(p)) for p in sorted(repo.rglob("*.md"))]
    outcome = DocumentedPaths().run(project, documents)
    return {f.claim.subject: (f.verdict, f.detail) for f in outcome.findings}


def test_a_link_to_an_untranslated_page_is_not_drift(make_repo: Callable[..., Path]):
    """The FastAPI shape. `zh` has the guide but not the people page; `en` has both."""
    repo = make_repo(
        files={
            "docs/en/docs/help.md": "See [people](people.md)." + chr(10),
            "docs/en/docs/people.md": "The people page." + chr(10),
            "docs/zh/docs/help.md": "See [people](people.md)." + chr(10),
        }
    )
    got = verdicts(repo)
    verdict, detail = got["docs/zh/docs/people.md"]
    assert verdict is Verdict.SKIPPED, got
    assert "docs/en/docs/people.md" in detail, detail
    assert "translation overlay" in detail, detail
    assert not [v for v, _ in got.values() if v is Verdict.BROKEN], got


def test_a_locale_tree_without_the_document_is_still_judged(make_repo: Callable[..., Path]):
    """The structural guard. `en` holds the target but has no copy of the claiming document,
    so these are not mirrored trees and the claim gets judged like any other."""
    repo = make_repo(
        renamed={"docs/zh/docs/people.md": "docs/zh/docs/moved/people.md"},
        documented_before={"docs/zh/docs/help.md": "See [people](people.md)." + chr(10)},
        files={"docs/en/docs/people.md": "The people page." + chr(10)},
    )
    verdict, detail = verdicts(repo)["docs/zh/docs/people.md"]
    assert verdict is Verdict.BROKEN, detail
    assert "translation overlay" not in detail, detail


def test_a_versioned_tree_is_not_a_locale_tree():
    """`docs/v1` and `docs/v2` mirror each other too, and a page present in one and missing
    from the next is a real gap. Only language tags count."""
    tracked = frozenset({"docs/v1/guide.md", "docs/v1/people.md", "docs/v2/guide.md"})
    assert locale_sibling("docs/v2/people.md", "docs/v2/guide.md", tracked) is None


def test_a_lone_parallel_file_is_not_a_mirrored_tree():
    """The target exists next door and the document does not. One file is a coincidence."""
    tracked = frozenset({"docs/en/people.md", "docs/zh/guide.md"})
    assert locale_sibling("docs/zh/people.md", "docs/zh/guide.md", tracked) is None


def test_the_sibling_it_finds_is_named():
    tracked = frozenset({"docs/en/docs/people.md", "docs/en/docs/help.md", "docs/zh/docs/help.md"})
    found = locale_sibling("docs/zh/docs/people.md", "docs/zh/docs/help.md", tracked)
    assert found == "docs/en/docs/people.md"


def test_a_multipart_tag_counts(make_repo: Callable[..., Path]):
    """FastAPI ships `zh-hant`, and it was one of the twelve."""
    tracked = frozenset({"docs/en/docs/people.md", "docs/en/docs/help.md", "docs/zh-hant/docs/help.md"})
    assert (
        locale_sibling("docs/zh-hant/docs/people.md", "docs/zh-hant/docs/help.md", tracked)
        == "docs/en/docs/people.md"
    )
