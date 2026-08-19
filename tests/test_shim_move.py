"""A deleted re-export is not a deleted file.

`moved_to` asks what the DELETING commit renamed, and the commonest large refactor there
is defeats it. A split copies a file to its new home and leaves a one-line re-export at the
old path so nothing breaks; weeks later a tidy-up deletes the re-export. Git calls that
second commit a plain `D`, correctly - a one-line stub resembles nothing - so the finding
reads "deleted and never restored", which is true of the path and false of the content.

`zhukunpenglinyutong/desktop-cc-gui`:

    b66a616b3  "Split app-shell.tsx"    C099  app-shell-parts/modelSelection.ts
                                              -> app-shell/domains/modelSelection.ts
    772b6c681  "Clean up useless code"    D   app-shell-parts/modelSelection.ts  (1 line)

Its onboarding guide - `status: active` in its own frontmatter, calibrated to the current
release - lists the old path among the files you must edit to add an engine. Six of that
project's eleven findings are that one commit pair, which is the shape of this: rare across
projects, and everywhere at once inside the project that does it.

The two negative tests are the point of the design. Accepting a same-basename file at HEAD
is the rule `BARE-FILENAME-VERDICT.md` rejected wearing a different hat, and accepting any
git-visible copy admits `bytebase`, where `feat: implement oracle generate migration` copied
the Postgres migration generator to start the Oracle one and both went on living.

These build their own history rather than using `make_repo`: the shape under test is a copy
and a deletion in two separate commits, and a fixture that cannot produce that cannot test
this.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from docproof.vcs import Git

BODY = "\n".join(f"export const value{n} = {n};" for n in range(60)) + "\n"
SHIM = 'export * from "../../new/home/modelSelection";\n'


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


def _write(repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "split"
    root.mkdir()
    _git(root, "init", "-q")
    _write(root, "src/old/parts/modelSelection.ts", BODY)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the file, at its original home", "--no-gpg-sign")
    return root


def _split_leaving_a_shim(repo: Path) -> None:
    """One commit: the content lands at the new path, the old path becomes a re-export.

    Both in the same commit, because that is what lets git's copy detection pair them -
    and it is what the real refactor does, so nothing breaks between the two commits.
    """
    _write(repo, "src/new/home/modelSelection.ts", BODY)
    _write(repo, "src/old/parts/modelSelection.ts", SHIM)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "Split app-shell.tsx", "--no-gpg-sign")


def _sweep_up_the_shim(repo: Path) -> None:
    _git(repo, "rm", "-q", "src/old/parts/modelSelection.ts")
    _git(repo, "commit", "-qm", "Clean up useless code", "--no-gpg-sign")


def test_the_shim_pattern_names_where_the_content_went(repo: Path) -> None:
    """The case that forced this to exist."""
    _split_leaving_a_shim(repo)
    _sweep_up_the_shim(repo)

    git = Git(root=repo)
    receipt = git.deleted("src/old/parts/modelSelection.ts")
    assert receipt is not None

    # The premise: git calls this a plain deletion, so the existing path finds nothing.
    assert git.moved_to("src/old/parts/modelSelection.ts", receipt[0]) is None

    destination = git.succeeded_by("src/old/parts/modelSelection.ts", receipt[0])
    assert destination == "src/new/home/modelSelection.ts"
    # Same invariant `moved_to` holds: never name a path that is not there now.
    assert git.tracks(destination)


def test_a_forked_sibling_is_refused(repo: Path) -> None:
    """`bytebase`, reduced to its bones.

    `044c898364 "feat: implement oracle generate migration"` copied the Postgres generator
    to start the Oracle one. Git records `C077`, so lineage alone would accept it. The
    Postgres file then grew from 1583 lines to 5192 and was deleted on its own a year later.
    Nothing moved; there are four `generate_migration.go` at that HEAD, one per dialect.

    What separates the two cases is the source AFTER the copy: a file on its way out is
    frozen, a forked sibling keeps being developed.
    """
    _write(repo, "src/new/home/modelSelection.ts", BODY)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "start a second dialect from the first", "--no-gpg-sign")

    _write(repo, "src/old/parts/modelSelection.ts", BODY + BODY)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "keep developing the original", "--no-gpg-sign")

    _git(repo, "rm", "-q", "src/old/parts/modelSelection.ts")
    _git(repo, "commit", "-qm", "retire the original, much later", "--no-gpg-sign")

    git = Git(root=repo)
    receipt = git.deleted("src/old/parts/modelSelection.ts")
    assert receipt is not None
    assert git.succeeded_by("src/old/parts/modelSelection.ts", receipt[0]) is None


def test_a_namesake_with_no_lineage_is_refused(repo: Path) -> None:
    """Basename finds candidates. It never accepts one.

    Of the 160 corpus findings that say "never restored", 25 have a same-basename file at
    HEAD with no lineage to it, and they are `sdk/package.json` -> `package.json`,
    `pkg/registry/types.go` -> `pkg/git/types.go`, and
    `website/content/getting-started.md` -> a vendored copy under `third-party/`.
    """
    _write(repo, "src/unrelated/modelSelection.ts", "export const different = true;\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "a different file that shares a name", "--no-gpg-sign")

    _git(repo, "rm", "-q", "src/old/parts/modelSelection.ts")
    _git(repo, "commit", "-qm", "delete the original outright", "--no-gpg-sign")

    git = Git(root=repo)
    receipt = git.deleted("src/old/parts/modelSelection.ts")
    assert receipt is not None
    assert git.succeeded_by("src/old/parts/modelSelection.ts", receipt[0]) is None


def test_a_file_with_no_namesake_at_all_names_nothing(repo: Path) -> None:
    _git(repo, "rm", "-q", "src/old/parts/modelSelection.ts")
    _git(repo, "commit", "-qm", "gone, and nothing took its place", "--no-gpg-sign")

    git = Git(root=repo)
    receipt = git.deleted("src/old/parts/modelSelection.ts")
    assert receipt is not None
    assert git.succeeded_by("src/old/parts/modelSelection.ts", receipt[0]) is None


def test_a_plain_rename_is_left_to_moved_to(repo: Path) -> None:
    """No regression on the path that already worked.

    A single `git mv` is what `moved_to` is for, and it must keep answering first - this
    only ever runs when that one returns None.
    """
    (repo / "src" / "new" / "home").mkdir(parents=True)
    _git(repo, "mv", "src/old/parts/modelSelection.ts", "src/new/home/modelSelection.ts")
    _git(repo, "commit", "-qm", "just move it", "--no-gpg-sign")

    git = Git(root=repo)
    receipt = git.deleted("src/old/parts/modelSelection.ts")
    assert receipt is not None
    assert git.moved_to("src/old/parts/modelSelection.ts", receipt[0]) == "src/new/home/modelSelection.ts"
