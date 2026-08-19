"""An empty directory and a removed one look the same to git, until you replay the history.

`paths.py` skips a claim written with a trailing slash when the directory's parent is
tracked. The reason is real: git stores files, not directories, so a directory with no files
is indistinguishable from one that never existed - and `PostHog/posthog-python`'s
RELEASING.md says changesets live in `.sampo/changesets/`, a directory every release empties
as the bot consumes them. The sentence says where `sampo add` PUTS files. Reporting it argues
with a lifecycle.

The guard's own comment then claimed the tracked-parent requirement "keeps the case this must
still catch: a documented directory whose entire tree really did go". It keeps none of them.
A removed SUBdirectory of a live tree has a tracked parent too:

    stacklok/toolhive   docs/arch/06-registry-system.md:864   `pkg/container/verifier/`
                        7095e8e1  "Remove /verifier in favour of one coming from toolhive-core"

`pkg/container` is alive. `verifier` is gone, and the tool said nothing.

MEASURED over the 47 clones of sweep batches 10 and 11, every `--show-skips` run captured to
disk rather than sampled: the guard silences **38 directory claims, 31 of them never tracked
at all** - promises, and places the reader creates, and the guard is right about all 31 -
**and 7 populated and wholly emptied**, across toolhive, hive, onyx and openmed.

The test for the posthog case builds its own history because the shape under test is a
directory that goes empty and REFILLS, and a fixture that commits once and deletes once
cannot express it. That distinction is the whole rule, and the previous test asserted the
posthog verdict over a history posthog does not have.
"""

from __future__ import annotations

import os
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
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        },
    )


def _add(repo: Path, path: str, message: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("contents\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message, "--no-gpg-sign")


def _remove(repo: Path, path: str, message: str) -> None:
    _git(repo, "rm", "-q", path)
    _git(repo, "commit", "-qm", message, "--no-gpg-sign")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "tree"
    root.mkdir()
    _git(root, "init", "-q")
    _add(root, "keep/anchor.txt", "something so the repository is not empty")
    return root


def test_the_posthog_case_a_directory_that_refills(repo: Path) -> None:
    """Filled, consumed, filled, consumed. This is what a changeset directory does.

    Verified against the real repository rather than only the fixture: at the clone on disk
    `PostHog/posthog-python` has a file under `.sampo/changesets/` again, and
    `emptied_and_stayed` returns None for it.
    """
    _add(repo, ".sampo/changesets/gallant-prince.md", "add a changeset")
    _remove(repo, ".sampo/changesets/gallant-prince.md", "release v7.39.0, consume changesets")
    _add(repo, ".sampo/changesets/brave-otter.md", "add another changeset")
    _remove(repo, ".sampo/changesets/brave-otter.md", "release v7.39.1, consume changesets")

    assert Git(root=repo).emptied_and_stayed(".sampo/changesets") is None


def test_the_toolhive_case_a_subsystem_removed_under_a_live_parent(repo: Path) -> None:
    """The case the guard's comment claimed to keep and did not.

    Three files added over three commits, then all of them removed at once, and the parent
    `pkg/container` still holds other code. That is a subsystem leaving, and every one of
    the seven found in the corpus has this shape.
    """
    _add(repo, "pkg/container/runtime.go", "the container package")
    _add(repo, "pkg/container/verifier/sigstore.go", "add sigstore verification")
    _add(repo, "pkg/container/verifier/cosign.go", "add cosign verification")
    _git(repo, "rm", "-q", "-r", "pkg/container/verifier")
    _git(
        repo,
        "commit",
        "-qm",
        "Remove /verifier in favour of one coming from toolhive-core",
        "--no-gpg-sign",
    )

    git = Git(root=repo)
    # The premise: the parent is alive, which is exactly why the old guard fired.
    assert git.tracks("pkg/container")
    assert git.emptied_and_stayed("pkg/container/verifier") is not None


def test_a_directory_that_never_existed_names_nothing(repo: Path) -> None:
    """31 of the 38 silenced claims are this, and the guard is right about every one of them.

    A documented directory git has never tracked a file under is a promise, or a place the
    reader is told to create. There is no receipt and there must be no finding.
    """
    assert Git(root=repo).emptied_and_stayed("docs/changesets") is None


def test_a_directory_that_still_has_files_names_nothing(repo: Path) -> None:
    _add(repo, "pkg/live/thing.go", "a package that is still here")
    assert Git(root=repo).emptied_and_stayed("pkg/live") is None


def test_emptied_then_refilled_then_emptied_is_still_churn(repo: Path) -> None:
    """The boundary, because a single trailing emptying is what the rule keys on.

    A directory that has been empty before and filled again is a lifecycle whatever state it
    happens to be in at HEAD, and reporting it on the down-swing would be reporting the same
    directory differently depending on when the run happened.
    """
    _add(repo, "fragments/one.md", "first fragment")
    _remove(repo, "fragments/one.md", "consume it")
    _add(repo, "fragments/two.md", "second fragment")
    _remove(repo, "fragments/two.md", "consume that one too")

    assert Git(root=repo).emptied_and_stayed("fragments") is None
