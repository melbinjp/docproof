"""`moved to X` has to mean X is there now.

`Git.moved_to` looked at the deleting commit and stopped. A file can be renamed more than
once, and reporting the first hop names a path that may itself be gone - which is the worst
thing that function can do, because its entire purpose is to save the reader a search and it
would be sending them somewhere empty.

Found on `open-gsd/gsd-core`, where `docs/CONFIGURATION.md` cites
`sdk/shared/model-catalog.json` and the chain is two hops:

    11918dcc  sdk/shared/model-catalog.json     -> get-shit-done/bin/shared/model-catalog.json
    463cffd8  get-shit-done/bin/shared/...json  -> gsd-core/bin/shared/model-catalog.json

The reported answer was the middle one, and `get-shit-done/` has zero files at that
repository's HEAD.

These build their own history rather than using `make_repo`, because the shape under test is
two renames in two separate commits and pairing only happens within one commit - a fixture
that cannot produce that cannot test this.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from docproof.vcs import Git


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=True,
        timeout=60,
        env={
            "GIT_AUTHOR_NAME": "docproof tests",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "docproof tests",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00",
            "PATH": __import__("os").environ.get("PATH", ""),
            "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
        },
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "chain"
    root.mkdir()
    _git(root, "init", "-q")
    # Content big enough that git scores the rename at R100 rather than guessing.
    body = "\n".join(f"line {n} of a file worth following" for n in range(40)) + "\n"
    first = root / "sdk" / "shared"
    first.mkdir(parents=True)
    (first / "catalog.json").write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "one", "--no-gpg-sign")
    return root


def _move(repo: Path, old: str, new: str, message: str) -> None:
    (repo / new).parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "mv", old, new)
    _git(repo, "commit", "-qm", message, "--no-gpg-sign")


def test_two_hops_reports_where_the_file_actually_is(repo: Path) -> None:
    """The real shape, and the whole reason this exists."""
    _move(repo, "sdk/shared/catalog.json", "middle/bin/shared/catalog.json", "retire the sdk seam")
    _move(repo, "middle/bin/shared/catalog.json", "final/bin/shared/catalog.json", "rename middle")

    git = Git(root=repo)
    receipt = git.deleted("sdk/shared/catalog.json")
    assert receipt is not None
    destination = git.moved_to("sdk/shared/catalog.json", receipt[0])

    assert destination == "final/bin/shared/catalog.json"
    # The invariant, stated as an assertion rather than trusted: whatever is named exists.
    assert git.tracks(destination)


def test_one_hop_still_works(repo: Path) -> None:
    """The behaviour that was already right must survive the fix."""
    _move(repo, "sdk/shared/catalog.json", "kept/catalog.json", "move once")

    git = Git(root=repo)
    receipt = git.deleted("sdk/shared/catalog.json")
    assert receipt is not None
    assert git.moved_to("sdk/shared/catalog.json", receipt[0]) == "kept/catalog.json"


def test_a_chain_that_ends_in_a_real_deletion_names_nothing(repo: Path) -> None:
    """Renamed, then genuinely deleted.

    The honest answer is None, so the finding reads "deleted ... and never restored" - which
    is true - instead of pointing at an intermediate path that is no longer there. Naming a
    phantom is worse than saying less.
    """
    _move(repo, "sdk/shared/catalog.json", "middle/catalog.json", "move it")
    _git(repo, "rm", "-q", "middle/catalog.json")
    _git(repo, "commit", "-qm", "and now really delete it", "--no-gpg-sign")

    git = Git(root=repo)
    receipt = git.deleted("sdk/shared/catalog.json")
    assert receipt is not None
    assert git.moved_to("sdk/shared/catalog.json", receipt[0]) is None


def test_a_file_that_was_never_renamed_reports_nothing(repo: Path) -> None:
    _git(repo, "rm", "-q", "sdk/shared/catalog.json")
    _git(repo, "commit", "-qm", "plain deletion", "--no-gpg-sign")

    git = Git(root=repo)
    receipt = git.deleted("sdk/shared/catalog.json")
    assert receipt is not None
    assert git.moved_to("sdk/shared/catalog.json", receipt[0]) is None
