"""How much of the project was in scope at all, said out loud on every run.

**The defect this fixes was measured, not imagined.** Run against the repository docproof
was written in service of, the report read:

    docproof 0.1.4 - mind, 4 document(s)
    ...
    Nothing contradicted. 64 claims checked

There are 299 tracked documentation files in that tree. It read 5, judged 4, and said
nothing whatsoever about the other 294 - which live in `work/`, `journal/`, `unsent/` and
`daemon/`, none of which is `docs/`. The scope is deliberate and `find_docs` argues for it.
The SILENCE about the scope was not deliberate, and it is the same failure this tool's own
README names for claims: *"a checker that silently skips everything looks exactly like a
clean one."*

**The first version of the fix was worse than the bug and these tests exist because of it.**
Walking the filesystem, that same repository reported **38,402** unread documents, because it
keeps 217 cloned repositories under `work/` for testing. All gitignored. A number dominated
by other people's code is not a coverage report, it is noise that teaches the reader to skip
the line. Asking git what the project TRACKS turns 38,402 into 294, and 294 is the true
answer.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.cli import main
from docproof.docs import by_directory, find_docs, unread_documents
from docproof.vcs import Git

README = """\
# A project

See `src/thing.py` for the details.
"""


def _tracked(repo: Path) -> frozenset[str]:
    return Git(root=repo).tracked_files


def test_it_names_documents_outside_the_default_scope(make_repo: Callable[..., Path]) -> None:
    """The motivating shape: documentation that is not at the root and is not in `docs/`."""
    repo = make_repo(
        {
            "README.md": README,
            "src/thing.py": "x = 1\n",
            "guides/install.md": "# Install\n",
            "guides/deep/tuning.md": "# Tuning\n",
            "handbook/onboarding.md": "# Onboarding\n",
        }
    )
    unread = unread_documents(repo, find_docs(repo), _tracked(repo))
    names = {p.relative_to(repo).as_posix() for p in unread}
    assert names == {
        "guides/install.md",
        "guides/deep/tuning.md",
        "handbook/onboarding.md",
    }
    assert by_directory(repo, unread) == [("guides", 2), ("handbook", 1)]


def test_a_gitignored_tree_is_not_this_project_s_documentation(make_repo: Callable[..., Path]) -> None:
    """**The 38,402 case, in miniature.**

    A checkout of somebody else's repository inside yours is not your documentation, and no
    directory-name heuristic can know that in general - the real one was called `work/`, which
    no blocklist would ever have carried. Git already knows, because you told it.
    """
    repo = make_repo(
        {"README.md": README, "src/thing.py": "x = 1\n", "mine/notes.md": "# Notes\n"},
        gitignore="corpus/\n",
    )
    clone = repo / "corpus" / "somebody-else"
    clone.mkdir(parents=True)
    for n in range(30):
        (clone / f"doc{n}.md").write_text("# Theirs\n", encoding="utf-8")

    tracked = unread_documents(repo, find_docs(repo), _tracked(repo))
    assert {p.relative_to(repo).as_posix() for p in tracked} == {"mine/notes.md"}

    # And the fallback, which is what runs when git cannot answer, sees all thirty of them.
    # Asserted rather than assumed, because "the filter works" is only meaningful against a
    # measurement of what it filtered.
    walked = unread_documents(repo, find_docs(repo), None)
    assert len(walked) == 31


def test_the_clean_case_still_says_something(make_repo: Callable[..., Path], capsys) -> None:
    """A coverage report that only speaks when it has bad news cannot be told from one
    that did not run. This is the line that makes the check visible on a clean project."""
    repo = make_repo({"README.md": README, "src/thing.py": "x = 1\n", "docs/guide.md": "# Guide\n"})
    main([str(repo)])
    out = capsys.readouterr().out
    assert "every documentation file in the tree was in scope" in out


def test_the_directory_list_says_how_much_it_did_not_show(make_repo: Callable[..., Path], capsys) -> None:
    """**No silent caps.** Five directories are named and the rest are counted, because a
    truncated list under an untruncated total is how a reader concludes from an absence the
    tool manufactured."""
    files = {"README.md": README, "src/thing.py": "x = 1\n"}
    for n in range(8):
        files[f"area{n}/note.md"] = "# Note\n"
    repo = make_repo(files)
    main([str(repo)])
    out = capsys.readouterr().out
    assert "8 documentation file(s) elsewhere in the tree were NOT read" in out
    assert "and 3 more directories holding 3" in out
    assert "--docs" in out and "[tool.docproof] docs" in out


def test_one_leftover_directory_is_singular(make_repo: Callable[..., Path], capsys) -> None:
    """Six directories leaves one unshown, and "1 more directories" is the kind of seam that
    makes a reader stop trusting the rest of the number."""
    files = {"README.md": README, "src/thing.py": "x = 1\n"}
    for n in range(6):
        files[f"area{n}/note.md"] = "# Note\n"
    repo = make_repo(files)
    main([str(repo)])
    assert "and 1 more directory holding 1" in capsys.readouterr().out


def test_it_does_not_double_count_a_document_that_was_set_aside(make_repo: Callable[..., Path]) -> None:
    """A CHANGELOG is found by `find_docs` and then set aside as historical. It is already
    named by `report_set_aside`, so counting it again as unread would report one document
    twice under two different explanations."""
    repo = make_repo({"README.md": README, "src/thing.py": "x = 1\n", "CHANGELOG.md": "# 1.0\n"})
    unread = unread_documents(repo, find_docs(repo), _tracked(repo))
    assert unread == []


def test_the_historical_list_is_capped_and_says_the_remainder(make_repo: Callable[..., Path], capsys) -> None:
    """**Found by running the new coverage report on trino**, which keeps 358 release notes
    under `docs/src/main/sphinx/release/`. This list was unbounded, so the run printed 358
    filenames on one line thousands of characters long and buried its own report underneath.
    Same principle as the cap above, in a neighbour that predates it."""
    files = {"README.md": README, "src/thing.py": "x = 1\n"}
    for n in range(40):
        files[f"docs/release/release-{n:03d}.md"] = f"# Release {n}\n"
    repo = make_repo(files)
    main([str(repo)])
    out = capsys.readouterr().out
    assert "describing the past, not judged (40):" in out
    assert "and 30 more" in out
    # The whole block stays on one line, so its length is the thing that was wrong before.
    line = next(ln for ln in out.splitlines() if "describing the past" in ln)
    assert len(line) < 500, line[:200]
