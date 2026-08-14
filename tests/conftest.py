"""A real git repository per test, because the checker's truth source is a real one.

`vcs.Git` shells out to git and asks the index what the project ships. Faking that away
would test a mock's opinion of git rather than git's. These fixtures are cheap — an empty
`git init` and one commit — and they mean every assertion about tracked, ignored and
missing paths is checked against the tool that actually decides it.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


def _git(repo: Path, *args: str, when: str | None = None) -> None:
    env = None
    if when is not None:
        env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


# Fixture history has to be spread across real time, not compressed into whatever second
# the test runs in. `Git.claim_introduced_after` compares author dates, and commits made
# in the same second compare equal — so a same-second fixture cannot express "the document
# said this before the file was deleted" at all, and every test of that rule silently
# asserts nothing. This bit the suite once already: a deletion test passed for a year
# while its README was committed on the wrong side of the removal.
_EARLY, _REMOVAL, _LATE = (
    "2020-01-01T00:00:00+00:00",
    "2021-01-01T00:00:00+00:00",
    "2022-01-01T00:00:00+00:00",
)


@pytest.fixture
def make_repo(tmp_path: Path) -> Callable[..., Path]:
    """Build a committed git repository from a {path: contents} mapping.

    Paths ending in `/` become directories with a `.keep` file, so a test can talk about
    a tracked directory without inventing a file for it.
    """
    counter = {"n": 0}

    def build(
        files: dict[str, str],
        gitignore: str = "",
        deleted: dict[str, str] | None = None,
        shallow: bool = False,
        documented_before: dict[str, str] | None = None,
    ) -> Path:
        """`deleted` is committed first and then removed in a second commit.

        That second commit is the only thing that separates real drift from an
        illustration, so a fixture that cannot produce one cannot test the rule.

        `documented_before` lands in the SAME first commit as `deleted`, so its claims
        exist before the removal. Ordinary `files` are committed last, which means a
        document passed there mentions a deleted path only *after* it was already gone —
        an example, by `Git.claim_introduced_after`. Real drift is a document that was
        true when written and was broken by a later commit, and that is a different
        history, not a different sentence. A fixture that cannot build both can only
        test one of them, and this one silently only tested the wrong one.

        `shallow` hands back a depth-1 clone of the built repository instead of the
        repository itself — a real shallow checkout, because "this clone has no
        history" is a state git defines and only git can produce.
        """
        counter["n"] += 1
        repo = tmp_path / f"repo{counter['n']}"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "docproof tests")

        if gitignore:
            (repo / ".gitignore").write_text(gitignore, encoding="utf-8")

        for name, contents in {**(deleted or {}), **(documented_before or {})}.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents or "placeholder\n", encoding="utf-8")
        if deleted:
            _git(repo, "add", "-A")
            _git(
                repo, "commit", "-q", "-m", "add what will later be removed",
                "--no-gpg-sign", when=_EARLY,
            )
            for name in deleted:
                _git(repo, "rm", "-q", name)
            _git(
                repo, "commit", "-q", "-m", "Farewell, it was nice knowing you",
                "--no-gpg-sign", when=_REMOVAL,
            )

        for name, contents in files.items():
            target = repo / name.rstrip("/")
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                (target / ".keep").write_text("", encoding="utf-8")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")

        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "initial", "--no-gpg-sign", when=_LATE)

        if shallow:
            # `--depth` only applies over a transport; a plain local-path clone
            # hardlinks the object store and keeps full history, so the file:// URL
            # is the whole point of this line.
            clone = tmp_path / f"repo{counter['n']}-shallow"
            _git(tmp_path, "clone", "-q", "--depth", "1", repo.as_uri(), str(clone))
            return clone
        return repo

    return build


@pytest.fixture(scope="session", autouse=True)
def _require_git() -> None:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True, timeout=30)
    except Exception:  # pragma: no cover - only on a machine without git
        pytest.skip("these tests check behaviour that is defined by git", allow_module_level=True)
