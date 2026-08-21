"""When a rename has two plausible destinations, the report says so.

`moved_to` names whichever destination git paired the content with, and a reader following the
report takes it. That is right for an ordinary rename and wrong for a SPLIT, where one commit
moves a file and creates another of the same name elsewhere: the pairing is a fact about content
similarity, not about which file the documented sentence meant.

The rule is restricted to what the SAME commit added, and that restriction is the whole design.
Keyed on the basename alone it would fire on every repository's fortieth `README.md`, appending
a caveat to the findings that are otherwise clearest.

Written 2026-08-21. The case that prompted it - `sendgrid/sendgrid-python` - turned out on
inspection NOT to be a split at all: `1dcc378` recorded one `R100` rename and the same-named
unit file arrived two years later in an unrelated commit. That is exactly why the restriction is
here, and the narrowed rule declining to fire on it is what exposed the mistake.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from docproof.docs import read
from docproof.model import Verdict
from docproof.project import Project
from docproof.verifiers.base import Document
from docproof.verifiers.paths import DocumentedPaths

EARLY, SPLIT, LATE = (
    "2020-01-01T00:00:00+00:00",
    "2021-01-01T00:00:00+00:00",
    "2022-01-01T00:00:00+00:00",
)


def git(repo: Path, *args: str, when: str | None = None) -> None:
    env = None
    if when is not None:
        import os

        env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, timeout=60, env=env)


def build(tmp_path: Path, *, sibling_in_split: bool) -> Path:
    """A repo whose README documented `src/thing.py` before it moved.

    `sibling_in_split` decides whether the same commit also creates `src/unit/thing.py`,
    which is the difference between a split and a coincidence.
    """
    repo = tmp_path / ("split" if sibling_in_split else "coincidence")
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "docproof tests")

    (repo / "src").mkdir()
    (repo / "src" / "thing.py").write_text("original" + chr(10), encoding="utf-8")
    (repo / "README.md").write_text("The tests are in `src/thing.py`." + chr(10), encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "the layout the README describes", "--no-gpg-sign", when=EARLY)

    (repo / "src" / "integ").mkdir()
    git(repo, "mv", "src/thing.py", "src/integ/thing.py")
    if sibling_in_split:
        (repo / "src" / "unit").mkdir()
        (repo / "src" / "unit" / "thing.py").write_text("unit tests" + chr(10), encoding="utf-8")
        git(repo, "add", "-A")
    git(repo, "commit", "-q", "-a", "-m", "split up unit and integ tests", "--no-gpg-sign", when=SPLIT)

    if not sibling_in_split:
        (repo / "src" / "unit").mkdir()
        (repo / "src" / "unit" / "thing.py").write_text("unit tests" + chr(10), encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "much later, unrelated", "--no-gpg-sign", when=LATE)
    return repo


def detail(repo: Path) -> str:
    project = Project(root=repo)
    documents = [Document(path=p, text=read(p)) for p in sorted(repo.rglob("*.md"))]
    findings = DocumentedPaths().run(project, documents).findings
    broken = [f for f in findings if f.verdict is Verdict.BROKEN]
    assert len(broken) == 1, [(f.claim.subject, f.verdict) for f in findings]
    return broken[0].detail


def test_a_split_names_the_other_destination(tmp_path: Path):
    """Both files exist and only one was paired. The reader has to be told there was a choice."""
    text = detail(build(tmp_path, sibling_in_split=True))
    assert "src/integ/thing.py" in text
    assert "src/unit/thing.py" in text
    assert "read the sentence" in text


def test_a_same_named_file_from_another_commit_is_not_a_split(tmp_path: Path):
    """The restriction that keeps this off every repository's fortieth README.md."""
    text = detail(build(tmp_path, sibling_in_split=False))
    assert "src/integ/thing.py" in text
    assert "src/unit/thing.py" not in text
    assert "also exists" not in text
