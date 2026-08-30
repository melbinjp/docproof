"""Running the checker must not change the project it is checking.

@fschutt asserted this in `azul`'s CI before adding docproof to it: the workflow fails the
build if a run leaves a single tracked file modified, on the grounds that the tool "is
documented as read-only". It was not documented as read-only. It was true, nobody had
written it down, and nothing checked it, which is the exact shape of defect this project
exists to find, found in this project by somebody reading it before they trusted it.

A guarantee a stranger is willing to assert in their own CI is one worth owning here.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from docproof.cli import main


def _tracked_bytes(repo: Path) -> dict[str, bytes]:
    """Every tracked file's exact contents, asked of git rather than of a walk."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=60,
    )
    names = [chunk.decode() for chunk in listing.stdout.split(b"\0") if chunk]
    return {name: (repo / name).read_bytes() for name in names}


def _porcelain(repo: Path) -> str:
    """Modified tracked files AND new untracked ones, which `git status` reports as `??`."""
    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout


def test_a_run_that_finds_drift_still_leaves_every_tracked_byte_alone(
    make_repo: Callable[..., Path],
) -> None:
    """The repository has real drift, so the run does real work before it is measured.

    Asserting exit 1 is not decoration. A read-only check that judged nothing would pass
    this test while proving nothing, and a vacuous version of this assertion is worth less
    than no assertion at all.
    """
    repo = make_repo(
        {"pyproject.toml": '[project]\nname = "prog"\nversion = "0"\n'},
        deleted={"tools/gone.py": ""},
        documented_before={"README.md": "Run `tools/gone.py` first."},
    )
    before = _tracked_bytes(repo)
    assert _porcelain(repo) == "", "the fixture itself must start clean"

    assert main([str(repo)]) == 1, "the run has to have found the drift, or this proves nothing"

    assert _porcelain(repo) == "", "a docproof run left the working tree dirty"
    assert _tracked_bytes(repo) == before, "a docproof run rewrote a tracked file"


def test_a_clean_run_creates_no_files_either(make_repo: Callable[..., Path]) -> None:
    """The quiet path writes nothing too, including no cache, log or report dropped into
    the project. `git status --porcelain` lists untracked files, so this catches those."""
    repo = make_repo(
        {
            "pyproject.toml": '[project]\nname = "prog"\nversion = "0"\n',
            "README.md": "The entry point is `src/app.py`.\n",
            "src/app.py": "",
        }
    )
    before = _tracked_bytes(repo)
    assert main([str(repo)]) == 0

    assert _porcelain(repo) == "", "a clean docproof run still touched the tree"
    assert _tracked_bytes(repo) == before
