"""A real git repository per test, because the checker's truth source is a real one.

`vcs.Git` shells out to git and asks the index what the project ships. Faking that away
would test a mock's opinion of git rather than git's. These fixtures are cheap — an empty
`git init` and one commit — and they mean every assertion about tracked, ignored and
missing paths is checked against the tool that actually decides it.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
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
    ) -> Path:
        """`deleted` is committed first and then removed in a second commit.

        That second commit is the only thing that separates real drift from an
        illustration, so a fixture that cannot produce one cannot test the rule.
        """
        counter["n"] += 1
        repo = tmp_path / f"repo{counter['n']}"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "docproof tests")

        if gitignore:
            (repo / ".gitignore").write_text(gitignore, encoding="utf-8")

        for name, contents in (deleted or {}).items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents or "placeholder\n", encoding="utf-8")
        if deleted:
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "add what will later be removed", "--no-gpg-sign")
            for name in deleted:
                _git(repo, "rm", "-q", name)
            _git(repo, "commit", "-q", "-m", "Farewell, it was nice knowing you", "--no-gpg-sign")

        for name, contents in files.items():
            target = repo / name.rstrip("/")
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                (target / ".keep").write_text("", encoding="utf-8")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")

        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "initial", "--no-gpg-sign")
        return repo

    return build


@pytest.fixture(scope="session", autouse=True)
def _require_git() -> None:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True, timeout=30)
    except Exception:  # pragma: no cover - only on a machine without git
        pytest.skip("these tests check behaviour that is defined by git", allow_module_level=True)
