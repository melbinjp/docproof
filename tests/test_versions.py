"""Judging what the documentation promises about installing.

Every test here is named for something the forty-repo measurement produced. The rule was
derived from that data rather than invented and then defended, and the two cases that
matter most are `test_the_datasette_case` - the single genuine contradiction in the whole
corpus - and `test_the_subject_must_not_reach_across_lines`, which is the bug that made
the first implementation skip it.
"""

from __future__ import annotations

from pathlib import Path

from docproof.config import suppressed_lines
from docproof.docs import read
from docproof.model import Verdict
from docproof.project import Project
from docproof.verifiers.base import Document
from docproof.verifiers.versions import DocumentedVersions

PYPROJECT = """
[project]
name = "datasette"
version = "1.0"
requires-python = ">=3.10"

[project.optional-dependencies]
docs = ["sphinx"]
test = ["pytest"]
"""


def build(tmp_path: Path, readme: str, pyproject: str = PYPROJECT) -> Path:
    repo = tmp_path / "project"
    repo.mkdir(exist_ok=True)
    (repo / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (repo / "README.md").write_text(readme, encoding="utf-8")
    return repo


def check(repo: Path) -> list[tuple[str, Verdict, str]]:
    project = Project(root=repo)
    documents = [
        Document(path=p, text=read(p), suppressed=suppressed_lines(read(p)))
        for p in sorted(repo.glob("*.md"))
    ]
    outcome = DocumentedVersions().run(project, documents)
    return [(f.claim.subject, f.verdict, f.detail) for f in outcome.findings]


# -- the documented Python requirement -------------------------------------------------


def test_the_datasette_case(tmp_path: Path) -> None:
    """The one real contradiction in forty public repositories.

    `Datasette requires Python 3.8 or higher` against `requires-python = ">=3.10"`. A
    reader on 3.8 follows the README and pip refuses them.
    """
    repo = build(tmp_path, "Datasette requires Python 3.8 or higher. See the docs.\n")
    found = check(repo)
    assert [(s, v) for s, v, _ in found] == [("3.8", Verdict.BROKEN)]
    assert ">=3.10" in found[0][2]


def test_the_subject_must_not_reach_across_lines(tmp_path: Path) -> None:
    """The bug that skipped the only true finding in the corpus.

    An earlier subject pattern allowed up to four words separated by `\\s`, so with an
    install command two lines above it captured "pip install datasette Datasette",
    decided the sentence was about something else, and declined the one claim it existed
    to catch. A false negative that looked exactly like careful restraint.
    """
    repo = build(
        tmp_path,
        "Install it:\n\n    pip install datasette\n\nDatasette requires Python 3.8 or higher.\n",
    )
    assert [(s, v) for s, v, _ in check(repo)] == [("3.8", Verdict.BROKEN)]


def test_agreement_holds(tmp_path: Path) -> None:
    repo = build(tmp_path, "Datasette requires Python 3.10 or higher.\n")
    assert [(s, v) for s, v, _ in check(repo)] == [("3.10", Verdict.HOLDS)]


def test_a_pronoun_subject_is_not_the_project(tmp_path: Path) -> None:
    """black's README: "It requires Python 3.10".

    "It" almost certainly does mean black - and resolving that is exactly the guess this
    tool refuses to make. Rewording a sentence makes a check skip; that is the property
    that lets it be a required gate.
    """
    found = check(build(tmp_path, "Datasette is a tool. It requires Python 3.8 or higher.\n"))
    assert [(s, v) for s, v, _ in found] == [("3.8", Verdict.SKIPPED)]
    assert "`It`" in found[0][2]


def test_a_third_party_requirement_is_not_ours(tmp_path: Path) -> None:
    """poetry's FAQ quotes "scipy requires Python >=3.7,<3.11" inside an error message."""
    found = check(build(tmp_path, "    - scipy requires Python >=3.7, so it will not be\n"))
    assert [v for _, v, _ in found] == [Verdict.SKIPPED]
    assert "`scipy`" in found[0][2]


def test_a_toolchain_that_shares_the_name_is_not_the_package(tmp_path: Path) -> None:
    """poetry's contributing guide: "Poetry's development toolchain requires Python 3.9".

    The head noun is the toolchain. The package is a different thing that happens to
    share a word, and a checker that cannot tell them apart is guessing.
    """
    found = check(build(tmp_path, "Datasette's development toolchain requires Python 3.9 or newer.\n"))
    assert [v for _, v, _ in found] == [Verdict.SKIPPED]
    assert "toolchain" in found[0][2]


def test_supports_without_a_bound_is_not_a_minimum(tmp_path: Path) -> None:
    """ "supports Python 3.13" is as likely to name the top of a range as the bottom."""
    found = check(build(tmp_path, "Datasette supports Python 3.13 on all platforms.\n"))
    assert [v for _, v, _ in found] == [Verdict.SKIPPED]
    assert "minimum" in found[0][2]


def test_supports_with_a_bound_is_a_minimum(tmp_path: Path) -> None:
    found = check(build(tmp_path, "Datasette supports Python 3.8+ on all platforms.\n"))
    assert [(s, v) for s, v, _ in found] == [("3.8", Verdict.BROKEN)]


def test_documentation_stricter_than_the_package_is_still_drift(tmp_path: Path) -> None:
    found = check(build(tmp_path, "Datasette requires Python 3.12 or higher.\n"))
    assert [(s, v) for s, v, _ in found] == [("3.12", Verdict.BROKEN)]
    assert "stricter" in found[0][2]


def test_a_requires_python_with_no_lower_bound_cannot_be_compared(tmp_path: Path) -> None:
    pyproject = PYPROJECT.replace('requires-python = ">=3.10"', 'requires-python = "<4.0"')
    found = check(build(tmp_path, "Datasette requires Python 3.8 or higher.\n", pyproject))
    assert [v for _, v, _ in found] == [Verdict.SKIPPED]
    assert "lower" in found[0][2]


# -- documented install extras ---------------------------------------------------------


def test_a_declared_extra_holds(tmp_path: Path) -> None:
    found = check(build(tmp_path, "Run:\n\n```\npip install datasette[docs]\n```\n"))
    assert [(s, v) for s, v, _ in found] == [("docs", Verdict.HOLDS)]


def test_an_undeclared_extra_breaks(tmp_path: Path) -> None:
    found = check(build(tmp_path, "Run:\n\n```\npip install datasette[secure]\n```\n"))
    assert [(s, v) for s, v, _ in found] == [("secure", Verdict.BROKEN)]
    assert "['docs', 'test']" in found[0][2]


def test_each_extra_in_a_list_is_judged_separately(tmp_path: Path) -> None:
    found = check(build(tmp_path, "```\npip install datasette[docs,secure]\n```\n"))
    assert [(s, v) for s, v, _ in found] == [("docs", Verdict.HOLDS), ("secure", Verdict.BROKEN)]


def test_an_extra_on_another_distribution_is_not_ours(tmp_path: Path) -> None:
    """`pip install uvicorn[standard]` in datasette's docs documents uvicorn."""
    assert check(build(tmp_path, "```\npip install uvicorn[standard]\n```\n")) == []


def test_underscores_and_case_are_the_same_distribution(tmp_path: Path) -> None:
    """PEP 503: writing the name with an underscore is not a different package."""
    found = check(build(tmp_path, "```\npip install DataSette[docs]\n```\n"))
    assert [(s, v) for s, v, _ in found] == [("docs", Verdict.HOLDS)]


def test_dynamic_optional_dependencies_cannot_be_contradicted(tmp_path: Path) -> None:
    """The completeness rule the flags verifier needed, in its other form.

    `dynamic = ["optional-dependencies"]` says in the file that the real list is computed
    at build time by code this never runs. An absence from a partial set proves nothing.
    """
    pyproject = """
[project]
name = "datasette"
version = "1.0"
requires-python = ">=3.10"
dynamic = ["optional-dependencies"]
"""
    found = check(build(tmp_path, "```\npip install datasette[secure]\n```\n", pyproject))
    assert [v for _, v, _ in found] == [Verdict.SKIPPED]
    assert "dynamic" in found[0][2]


def test_no_extras_table_at_all_is_a_complete_empty_set(tmp_path: Path) -> None:
    pyproject = '[project]\nname = "datasette"\nversion = "1.0"\nrequires-python = ">=3.10"\n'
    found = check(build(tmp_path, "```\npip install datasette[secure]\n```\n", pyproject))
    assert [(s, v) for s, v, _ in found] == [("secure", Verdict.BROKEN)]


# -- where the extras are actually declared --------------------------------------------


COHERE = """
[project]
name = "cohere"
version = "7.0.8"
requires-python = ">=3.9"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.poetry.extras]
oci = ["oci"]
aiohttp = ["aiohttp", "httpx-aiohttp"]
"""


def test_the_cohere_case_legacy_poetry_extras_are_real(tmp_path: Path) -> None:
    """The false positive that stopped a product, reduced to its pyproject.

    `cohere-python` has a `[project]` table and declares its extras the legacy Poetry way.
    Reading only `[project.optional-dependencies]`, this called `pip install 'cohere[oci]'`
    broken because the project "declares no optional-dependencies at all". The published
    cohere 7.0.8 carries `oci<3.0.0,>=2.165.0; extra == "oci"` in `requires_dist`, so the
    command works - the tool invented a contradiction in a company's README.

    An invented contradiction costs more than a missed one. A missed one is silence; this
    one is a confident sentence about a table, and a reader who opens `pyproject.toml`
    finds the answer two screens below where the tool stopped looking.
    """
    found = check(build(tmp_path, "```\npip install 'cohere[oci]'\n```\n", COHERE))
    assert [(s, v) for s, v, _ in found] == [("oci", Verdict.HOLDS)]
    assert "[tool.poetry.extras]" in found[0][2]


def test_an_undeclared_extra_still_breaks_under_legacy_poetry(tmp_path: Path) -> None:
    """Reading a second table must not turn the check off - recall stays where it was."""
    found = check(build(tmp_path, "```\npip install 'cohere[secure]'\n```\n", COHERE))
    assert [(s, v) for s, v, _ in found] == [("secure", Verdict.BROKEN)]
    assert "[tool.poetry.extras]" in found[0][2]
    assert "'aiohttp', 'oci'" in found[0][2].replace('"', "'")


# -- applicability and silence ---------------------------------------------------------


def test_not_applicable_without_project_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "bare"
    repo.mkdir()
    (repo / "README.md").write_text("Anything requires Python 3.8 or higher.\n", encoding="utf-8")
    outcome = DocumentedVersions().run(Project(root=repo), [])
    assert not outcome.applicable
    assert "[project] table" in outcome.reason


def test_no_requires_python_still_applies_if_extras_are_knowable(tmp_path: Path) -> None:
    """Written expecting "not applicable", and the code was right and the test was wrong.

    A project with no `requires-python` and no extras table still has a *provably empty*
    extras set, so `pip install pkg[anything]` is a claim this can contradict. Only when
    neither question is answerable does the verifier stand down.
    """
    pyproject = '[project]\nname = "datasette"\nversion = "1.0"\n'
    repo = build(tmp_path, "```\npip install datasette[secure]\n```\n", pyproject)
    assert DocumentedVersions().applies(Project(root=repo)) is None
    assert [v for _, v, _ in check(repo)] == [Verdict.BROKEN]


def test_not_applicable_when_neither_question_can_be_answered(tmp_path: Path) -> None:
    pyproject = '[project]\nname = "datasette"\nversion = "1.0"\ndynamic = ["optional-dependencies"]\n'
    repo = build(tmp_path, "hello\n", pyproject)
    outcome = DocumentedVersions().run(Project(root=repo), [])
    assert not outcome.applicable
    assert "requires-python" in outcome.reason


def test_saying_nothing_is_not_a_failure_here(tmp_path: Path) -> None:
    """Twenty of forty public repositories document neither claim, and none is broken.

    For `paths`, silence means the extraction has stopped working and failing is right.
    For this verifier it means the project simply never made the claim, and failing would
    turn half a healthy corpus red - the exact false alarm the tool exists to prevent,
    aimed at its own users.
    """
    repo = build(tmp_path, "A README with nothing to say about installing.\n")
    project = Project(root=repo)
    documents = [Document(path=repo / "README.md", text=read(repo / "README.md"))]
    outcome = DocumentedVersions().run(project, documents)
    assert outcome.findings == []
    assert not outcome.silent


def test_a_skip_marker_silences_a_claim(tmp_path: Path) -> None:
    repo = build(
        tmp_path,
        "<!-- docproof: skip -->\nDatasette requires Python 3.8 or higher.\n",
    )
    assert check(repo) == []
