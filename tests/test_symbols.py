"""Judging documented imports.

Every escape-hatch test here is named for the real project that produced it during the
forty-repository probe. The first pass of that probe reported PIL, attrs, rich, scrapy,
datasette, pydantic and pygments — some of the most widely used packages in the
ecosystem — as broken. All of them were wrong, for three distinct reasons, and each
reason is its own test rather than folded into one "it is complicated" fixture.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.config import suppressed_lines
from docproof.docs import read
from docproof.model import Verdict
from docproof.project import Project
from docproof.verifiers.base import Document
from docproof.verifiers.symbols import DocumentedSymbols

PYPROJECT = """
[project]
name = "toolkit"
version = "0.1.0"
"""


def toolkit(readme: str, source: dict[str, str]) -> dict[str, str]:
    files = {"pyproject.toml": PYPROJECT, "README.md": readme}
    files.update(source)
    return files


def check(repo: Path) -> list[tuple[str, Verdict, str]]:
    project = Project(root=repo)
    documents = [
        Document(path=p, text=read(p), suppressed=suppressed_lines(read(p)))
        for p in sorted(repo.glob("*.md"))
    ]
    outcome = DocumentedSymbols().run(project, documents)
    return [(f.claim.subject, f.verdict, f.detail) for f in outcome.findings]


# -- the plain case ----------------------------------------------------------------------


def test_a_bound_name_holds(make_repo: Callable[..., Path]) -> None:
    repo = make_repo(
        toolkit(
            "```python\nfrom toolkit import Widget\n```\n",
            {"toolkit/__init__.py": "class Widget:\n    pass\n"},
        )
    )
    assert check(repo) == [
        ("toolkit.Widget", Verdict.HOLDS, "`Widget` is bound at the top level of `toolkit`")
    ]


def test_an_undefined_name_is_broken(make_repo: Callable[..., Path]) -> None:
    repo = make_repo(
        toolkit(
            "```python\nfrom toolkit import Gadget\n```\n",
            {"toolkit/__init__.py": "class Widget:\n    pass\n"},
        )
    )
    found = check(repo)
    assert [(s, v) for s, v, _ in found] == [("toolkit.Gadget", Verdict.BROKEN)]
    assert "Gadget" in found[0][2]


def test_multiple_names_in_one_import_are_judged_separately(make_repo: Callable[..., Path]) -> None:
    repo = make_repo(
        toolkit(
            "```python\nfrom toolkit import Widget, Gadget\n```\n",
            {"toolkit/__init__.py": "class Widget:\n    pass\n"},
        )
    )
    assert [(s, v) for s, v, _ in check(repo)] == [
        ("toolkit.Widget", Verdict.HOLDS),
        ("toolkit.Gadget", Verdict.BROKEN),
    ]


def test_a_try_except_import_still_counts_as_bound(make_repo: Callable[..., Path]) -> None:
    """A name bound in only one branch of a version- or platform-guarded import is still
    a real name once that branch runs — a common shape this must not miss."""
    module_src = "try:\n    from ujson import loads\nexcept ImportError:\n    from json import loads\n"
    repo = make_repo(
        toolkit("```python\nfrom toolkit import loads\n```\n", {"toolkit/__init__.py": module_src})
    )
    assert [(s, v) for s, v, _ in check(repo)] == [("toolkit.loads", Verdict.HOLDS)]


# -- the three escape hatches, one test per real project that needed it -----------------


def test_the_pil_image_case_implicit_submodule_import_holds(make_repo: Callable[..., Path]) -> None:
    """`from PIL import Image` works because `PIL/Image.py` exists, whatever
    `PIL/__init__.py` does or does not import. The first probe pass reported this shape
    as broken on PIL, attrs, rich, scrapy and datasette — five widely used projects,
    five wrong findings, all one bug."""
    repo = make_repo(
        toolkit(
            "```python\nfrom toolkit import utils\n```\n",
            {"toolkit/__init__.py": "", "toolkit/utils.py": "def helper():\n    pass\n"},
        )
    )
    found = check(repo)
    assert [(s, v) for s, v, _ in found] == [("toolkit.utils", Verdict.HOLDS)]
    assert "submodule" in found[0][2]


def test_a_wildcard_import_makes_absence_unprovable(make_repo: Callable[..., Path]) -> None:
    repo = make_repo(
        toolkit(
            "```python\nfrom toolkit import Anything\n```\n",
            {
                "toolkit/__init__.py": "from .core import *\n",
                "toolkit/core.py": "class Widget:\n    pass\n",
            },
        )
    )
    found = check(repo)
    assert [v for _, v, _ in found] == [Verdict.SKIPPED]
    assert "import *" in found[0][2]


def test_pydantic_style_pep_562_getattr_makes_absence_unprovable(make_repo: Callable[..., Path]) -> None:
    """pydantic's public API answers `from pydantic import BaseModel` via a module-level
    `__getattr__` rather than a static binding — a name this cannot see without running
    the module, not a broken claim."""
    repo = make_repo(
        toolkit(
            "```python\nfrom toolkit import BaseModel\n```\n",
            {"toolkit/__init__.py": "def __getattr__(name):\n    raise AttributeError(name)\n"},
        )
    )
    found = check(repo)
    assert [v for _, v, _ in found] == [Verdict.SKIPPED]
    assert "__getattr__" in found[0][2]


def test_the_pygments_case_moduletype_subclass_getattr(make_repo: Callable[..., Path]) -> None:
    """pygments predates PEP 562 and gets the same effect by swapping
    `sys.modules[__name__]` for an instance of a `types.ModuleType` subclass whose
    `__getattr__` method looks names up in a table. Functionally identical to PEP 562;
    syntactically invisible to a check that only looks for a module-level function."""
    module_src = (
        "import sys\n"
        "import types\n\n"
        "class _automodule(types.ModuleType):\n"
        "    def __getattr__(self, name):\n"
        "        raise AttributeError(name)\n\n"
        "sys.modules[__name__].__class__ = _automodule\n"
    )
    repo = make_repo(
        toolkit("```python\nfrom toolkit import PythonLexer\n```\n", {"toolkit/__init__.py": module_src})
    )
    assert [v for _, v, _ in check(repo)] == [Verdict.SKIPPED]


# -- what is not a claim at all ----------------------------------------------------------


def test_a_foreign_package_import_is_not_our_claim(make_repo: Callable[..., Path]) -> None:
    repo = make_repo(toolkit("```python\nfrom os import path\n```\n", {"toolkit/__init__.py": ""}))
    assert check(repo) == []


def test_a_relative_import_in_docs_names_no_dotted_path(make_repo: Callable[..., Path]) -> None:
    repo = make_repo(toolkit("```python\nfrom . import something\n```\n", {"toolkit/__init__.py": ""}))
    assert check(repo) == []


def test_an_unlabelled_fence_is_not_guessed_at(make_repo: Callable[..., Path]) -> None:
    """An unlabelled fence is exactly as likely to be JSON or a shell transcript as
    Python in real READMEs — dropped on purpose rather than guessed at."""
    repo = make_repo(
        toolkit(
            "```\nfrom toolkit import Gadget\n```\n",
            {"toolkit/__init__.py": "class Widget:\n    pass\n"},
        )
    )
    assert check(repo) == []


def test_a_pycon_transcript_strips_prompts(make_repo: Callable[..., Path]) -> None:
    repo = make_repo(
        toolkit(
            "```pycon\n>>> from toolkit import Widget\n>>> Widget()\n<toolkit.Widget object>\n```\n",
            {"toolkit/__init__.py": "class Widget:\n    pass\n"},
        )
    )
    assert [(s, v) for s, v, _ in check(repo)] == [("toolkit.Widget", Verdict.HOLDS)]


def test_a_skip_marker_silences_a_claim(make_repo: Callable[..., Path]) -> None:
    repo = make_repo(
        toolkit(
            "<!-- docproof: skip -->\n```python\nfrom toolkit import Gadget\n```\n",
            {"toolkit/__init__.py": "class Widget:\n    pass\n"},
        )
    )
    assert check(repo) == []


# -- applicability and silence ------------------------------------------------------------


def test_not_applicable_without_an_importable_package(tmp_path: Path) -> None:
    repo = tmp_path / "bare"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (repo / "README.md").write_text("```python\nfrom toolkit import Widget\n```\n", encoding="utf-8")
    outcome = DocumentedSymbols().run(Project(root=repo), [])
    assert not outcome.applicable
    assert "importable" in outcome.reason


def test_saying_nothing_is_not_a_failure_here(make_repo: Callable[..., Path]) -> None:
    """Twelve of forty public repositories document no own-package import at all, and
    none of them is broken — the same shape `versions` already established."""
    repo = make_repo(
        toolkit(
            "A README with nothing to say about imports.\n",
            {"toolkit/__init__.py": "class Widget:\n    pass\n"},
        )
    )
    project = Project(root=repo)
    documents = [Document(path=repo / "README.md", text=read(repo / "README.md"))]
    outcome = DocumentedSymbols().run(project, documents)
    assert outcome.findings == []
    assert not outcome.silent
