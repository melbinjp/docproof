"""The version is declared once, and the build reads it from there.

THE DEFECT, MEASURED 2026-08-18
-------------------------------
`pyproject.toml` carried `version = "0.1.2"` while `src/docproof/__init__.py` carried
`__version__ = "0.1.0"`. Three releases had shipped and the README pinned v0.1.2, so a user
who followed the README got a tool whose every report header read:

    docproof 0.1.0 - their-repo, N document(s)

`--version` said the same. The packaging metadata was right and the number the tool SAYS
ABOUT ITSELF was two releases stale, which is a documented claim contradicted by the
repository - the exact thing docproof is for, inside docproof.

Found while checking whether the tool was fit to offer into another project's CI, after a
gsd-core maintainer had been pointed at it.

WHY THIS IS A STRUCTURAL TEST AND NOT A VALUE TEST
--------------------------------------------------
Asserting the two numbers are EQUAL would pass today and rot the moment someone bumps one
of them, which is precisely how this arose. The fix was to delete the second copy: hatchling
reads the package attribute, so there is nothing left to disagree. This test asserts THAT,
because a rule that says "keep these in sync" is a rule somebody has to remember, and the
whole point of this repository is that those are the rules that fail.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "src" / "docproof" / "__init__.py"


def _pyproject() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


def test_pyproject_declares_no_version_of_its_own() -> None:
    """A static `version = "..."` under [project] is the second copy that caused this."""
    project_block = _pyproject().split("[project]", 1)[1].split("\n[", 1)[0]
    static = re.findall(r"^version\s*=", project_block, re.M)

    assert static == [], (
        "pyproject declares a static version again. That is the second source of truth "
        "that printed 0.1.0 on a v0.1.2 install. Use the package attribute."
    )


def test_pyproject_marks_version_dynamic_and_points_at_the_package() -> None:
    text = _pyproject()

    assert 'dynamic = ["version"]' in text
    assert "[tool.hatch.version]" in text
    assert 'path = "src/docproof/__init__.py"' in text


def test_the_package_carries_exactly_one_version_literal() -> None:
    literals = re.findall(r'__version__\s*=\s*"([^"]+)"', INIT.read_text(encoding="utf-8"))

    assert len(literals) == 1, f"expected one version literal, found {literals}"


def test_the_reported_version_is_the_declared_one() -> None:
    """What `--version` and every report header print comes from that literal.

    The header is the user-visible surface that was wrong, so it is asserted directly
    rather than trusting that importing the name is enough.
    """
    from docproof import __version__

    declared = re.search(r'__version__\s*=\s*"([^"]+)"', INIT.read_text(encoding="utf-8"))
    assert declared is not None
    assert __version__ == declared.group(1)


def test_the_version_is_a_plain_release_number() -> None:
    """Guards the bump itself: a stray suffix or an empty string would ship silently."""
    from docproof import __version__

    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


# THE GAP THIS FILE LEFT OPEN, FOUND 2026-08-19
# ---------------------------------------------
# `test_pyproject_declares_no_version_of_its_own` asserts that `project.version` is ABSENT.
# `.github/workflows/release.yml` read exactly that key to decide whether the tag matched the
# package. Both facts lived in this repository and nothing compared them, so the release gate
# raised KeyError on every tag from v0.1.3 onward and every job behind it was skipped -
# including the GitHub release the Action installs from.
#
# It stayed invisible because the workaround worked: v0.1.0 to v0.1.2 were published by
# github-actions[bot], and v0.1.3 and v0.1.4 by hand. A broken automation somebody routes
# around is a broken automation nobody sees.
WORKFLOWS = ROOT / ".github" / "workflows"


def test_no_workflow_reads_a_static_project_version() -> None:
    """The key the first test guarantees is missing must not be what a gate depends on."""
    offenders = [
        path.name
        for path in sorted(WORKFLOWS.glob("*.yml"))
        if '["project"]["version"]' in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], (
        f"{offenders} read pyproject's project.version, which this file's first test "
        "asserts is absent. That combination crashed the release gate for two releases."
    )


def test_the_release_gate_reads_the_same_file_the_build_does() -> None:
    """Reading the version from a hardcoded path would be the second source of truth again.

    Asserted on the workflow text rather than by running it, because a release workflow can
    only be exercised by tagging, and a check that can only run at the moment it is needed is
    the one that is not there when it is.
    """
    release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")

    assert '["tool"]["hatch"]["version"]["path"]' in release, (
        "release.yml no longer resolves the version file through [tool.hatch.version]. "
        "Hardcoding it lets the gate and the build drift onto different files."
    )
