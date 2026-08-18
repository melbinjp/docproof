"""A folder that says, in its own README, that its contents are not current.

The fifth skip shape and the first that reads a file other than the document being judged.
People mark a drafts folder by putting a sentence in the folder's README, and nothing in
docproof could see it:

    docs/Docs_To_Review/README.md
    Files here are internal / archival / pending-audit. They are not the source of truth.

Twenty-nine findings in one repository sat under that sentence.

**Every test below is a defect that was measured, not imagined.** The naive form of this rule
silenced 95 of 217 corpus findings, 66 of them in a repository whose findings had been filed
as pull requests hours earlier, and each near-miss here is one of the reasons why.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.config import directory_disclaimer

WORLDMONITOR = """\
# Docs To Review (archival)

This directory is **not published by Mintlify** (`.mintignore` excludes it).

Files here are internal / archival / pending-audit. They are **not** the source of truth.
"""

WEKAN = """\
# Migrations

**Everything in this directory is a historical record.** It documents the old
cron-driven migration system.
"""


def test_it_reads_the_two_sentence_form(tmp_path: Path) -> None:
    """The clearest example in the corpus splits the claim across two sentences.

    "Files here are internal / archival / pending-audit." then "They are not the source of
    truth." A rule reading one line at a time would miss the one case that motivated it.
    """
    (tmp_path / "README.md").write_text(WORLDMONITOR, encoding="utf-8")
    said = directory_disclaimer(tmp_path)
    assert said is not None
    # `not the source of truth` is NOT what carries this one, and finding that out was worth
    # the failing test: the real sentence writes it as `**not** the source of truth`, and the
    # markdown emphasis sits between the words. What satisfies the denial half is `archival`,
    # in the same breath as `Files here are`. A pattern built to match the bolded phrase would
    # have been fitted to a fixture rather than to the corpus.
    assert "archival" in said
    assert said.startswith("Files here are")


def test_it_reads_a_quantifier_opening(tmp_path: Path) -> None:
    """ "Everything in this directory is a historical record" - the subject phrase is behind a
    quantifier, and an anchor that did not allow for one dropped this real marker."""
    (tmp_path / "README.md").write_text(WEKAN, encoding="utf-8")
    said = directory_disclaimer(tmp_path)
    assert said is not None
    assert "historical record" in said


def test_a_folder_that_is_current_is_not_silenced_by_a_sentence_about_something_else(
    tmp_path: Path,
) -> None:
    """The exact near miss, from a real PRD folder.

    The phrase "this directory" is present and the words "historical record" are present, and
    the sentence is about a FILE ELSEWHERE that predates the folder. The folder then says
    outright that new work lives there. Matching it would silence a live directory.
    """
    (tmp_path / "README.md").write_text(
        "# PRDs\n\n"
        "`docs/adr/0011-review-default-reviewers-prd.md` predates this directory and is\n"
        "preserved as immutable historical record. It is not a pattern to follow. New PRDs\n"
        "live here.\n",
        encoding="utf-8",
    )
    assert directory_disclaimer(tmp_path) is None


def test_does_not_currently_use_is_not_a_denial(tmp_path: Path) -> None:
    """`not current` as a bare string matched "does not currently use Nix flakes".

    The denial has to be a predicate about the documents, so it carries a copula. This is a
    real CI directory that would have gone quiet on a sentence about a build tool.
    """
    (tmp_path / "README.md").write_text(
        "# bender\n\n"
        "**bender** is configured via the `configuration.nix` file in this directory, and\n"
        "does not currently use Nix flakes.\n",
        encoding="utf-8",
    )
    assert directory_disclaimer(tmp_path) is None


def test_vocabulary_in_a_table_is_not_a_declaration(tmp_path: Path) -> None:
    """Defect 1, and the expensive one: a contents table listing the WORD.

    One repository's `docs/README.md` has a row reading "Archived history | Preserves
    completed or superseded context", and an ADR folder elsewhere lists `Deprecated` as an
    allowed status VALUE. Reading either as a folder marker silenced 66 findings in a
    repository whose findings had already been filed.
    """
    (tmp_path / "README.md").write_text(
        "# Docs\n\n"
        "| Section | Purpose | Where |\n"
        "| --- | --- | --- |\n"
        "| Archived history | Preserves completed or superseded context | `ARCHIVE.md` |\n"
        "| Status values | `Proposed`, `Accepted`, `Deprecated`, `Superseded` | `adr/` |\n",
        encoding="utf-8",
    )
    assert directory_disclaimer(tmp_path) is None


def test_a_disclaimer_buried_far_down_does_not_count(tmp_path: Path) -> None:
    """Same reasoning as `declares_removed` stopping at ten lines.

    A reader decides whether to trust a folder from what they see first. A sentence a hundred
    lines into a changelog is not a marker, and treating it as one would let any long README
    silence its directory by accident.
    """
    (tmp_path / "README.md").write_text(
        "# Guide\n\n" + ("filler line\n" * 60) + "Files here are archival.\n",
        encoding="utf-8",
    )
    assert directory_disclaimer(tmp_path) is None


def test_a_directory_with_no_readme_says_nothing(tmp_path: Path) -> None:
    assert directory_disclaimer(tmp_path) is None


PYPROJECT = """\
[project]
name = "disclaimed"
version = "0.1.0"
"""

DOC = "# Notes\n\nSee `src/gone.py` for the detail.\n"


def test_end_to_end_the_document_is_skipped_and_the_reason_is_quoted(
    make_repo: Callable[..., Path], capsys
) -> None:
    """The skip must be visible AND attributed.

    Every other skip can be audited by opening the document that was skipped. This one's
    reason lives in a neighbouring file the reader is not looking at, so printing a count
    without the sentence would be a skip nobody could check.
    """
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "docs/drafts/README.md": WORLDMONITOR},
        documented_before={"docs/drafts/notes.md": DOC},
        deleted={"src/gone.py": "x = 1\n"},
    )
    main([str(repo)])
    out = capsys.readouterr().out

    assert "docs/drafts/ says its own contents are not current" in out
    assert "notes.md" in out
    # The sentence as it really appears, markdown emphasis and all - asserting the plain
    # phrase would pass against a fixture nobody writes.
    assert "archival" in out
    # and the claim inside it was never judged
    assert "src/gone.py" not in out


def test_a_document_one_level_below_the_marked_folder_is_still_judged(
    make_repo: Callable[..., Path], capsys
) -> None:
    """NOT recursive, deliberately.

    A marker is a statement about the things beside it. Letting it reach down through
    subdirectories is how the defect that silenced an entire docs tree gets back in.
    """
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "docs/drafts/README.md": WORLDMONITOR},
        documented_before={"docs/drafts/deeper/notes.md": DOC},
        deleted={"src/gone.py": "x = 1\n"},
    )
    main([str(repo)])
    out = capsys.readouterr().out

    assert "src/gone.py" in out, "a subdirectory is not covered by the parent's marker"


def test_the_project_root_readme_cannot_disclaim_the_project(make_repo: Callable[..., Path], capsys) -> None:
    """A root README speaks for the project, not for a folder of drafts.

    If it could disclaim, one sentence would silence the entire repository - which is the
    loudest possible version of a checker that checks nothing.
    """
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "README.md": WORLDMONITOR},
        documented_before={"notes.md": DOC},
        deleted={"src/gone.py": "x = 1\n"},
    )
    main([str(repo)])
    out = capsys.readouterr().out

    assert "src/gone.py" in out, "the root README must not silence the repository"


TWO_LINE = """# Notes

Documents in this folder are staged for review.
They are not authoritative until promoted.
"""


def test_the_denial_may_arrive_on_the_following_line(tmp_path: Path) -> None:
    """The subject opens one line and the denial lands on the next.

    Kept as its own case because the fixture that motivated the two-line lookahead turns out
    to satisfy the rule on ONE line, through `archival`. Without this test the lookahead would
    be code no test reaches, which is the same as code that does not work.
    """
    (tmp_path / "README.md").write_text(TWO_LINE, encoding="utf-8")
    said = directory_disclaimer(tmp_path)
    assert said is not None
    assert "not authoritative" in said


def test_an_all_disclaimed_repository_is_not_reported_as_a_broken_checkout(
    make_repo: Callable[..., Path], capsys
) -> None:
    """The interaction this rule surfaced, found by a test rather than in the wild.

    `vanished_documents` asks HEAD whether an empty run means a failed clone. HEAD knows
    nothing about a folder marker, so a repository whose only documents sit in a disclaimed
    folder was told "the checkout does not match the repository" - a frightening message,
    and false. Documentation was found; we chose not to judge it.
    """
    from docproof.cli import main

    repo = make_repo(
        {
            "pyproject.toml": PYPROJECT,
            "docs/drafts/README.md": WORLDMONITOR,
            "docs/drafts/notes.md": DOC,
        }
    )
    code = main([str(repo)])
    out = capsys.readouterr().out

    assert "does not match the repository" not in out
    assert "says its own contents are not current" in out
    assert code == 0
