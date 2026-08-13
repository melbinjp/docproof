"""Judging documented paths.

Every skip rule here exists because the first version of this verifier produced a false
positive without it, on a real repository. They are written as tests so the tool cannot
quietly reacquire the habit.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.docs import read
from docproof.model import Verdict
from docproof.project import Project
from docproof.verifiers.base import Document
from docproof.verifiers.paths import DocumentedPaths


def run(repo: Path) -> dict[str, tuple[Verdict, str]]:
    project = Project(root=repo)
    documents = [Document(path=p, text=read(p)) for p in sorted(repo.glob("*.md"))]
    outcome = DocumentedPaths().run(project, documents)
    return {f.claim.subject: (f.verdict, f.detail) for f in outcome.findings}


def test_a_tracked_path_holds(make_repo: Callable[..., Path]):
    repo = make_repo(
        {
            "README.md": "The entry point is `src/pkg/main.py`.\n",
            "src/pkg/main.py": "",
        }
    )
    assert run(repo)["src/pkg/main.py"][0] is Verdict.HOLDS


def test_a_path_the_project_deleted_is_broken(make_repo: Callable[..., Path]):
    """The receipt is the commit that removed it."""
    repo = make_repo(
        {"README.md": "The entry point is `src/pkg/main.py`.\n", "src/pkg/other.py": ""},
        deleted={"src/pkg/main.py": "print('hi')\n"},
    )
    verdict, detail = run(repo)["src/pkg/main.py"]
    assert verdict is Verdict.BROKEN
    assert "deleted in" in detail and "Farewell" in detail


def test_a_path_the_project_never_had_is_not_judged(make_repo: Callable[..., Path]):
    """click tells readers to create `src/hello/__init__.py`; flask's tutorial tells them
    to write `tests/test_factory.py`. Neither has ever existed in those repositories, and
    reporting them is arguing with a tutorial rather than finding drift. History is the
    only thing that tells the two apart, and it does it perfectly across twenty repos."""
    repo = make_repo(
        {
            "README.md": "The entry point is `src/pkg/main.py`.\n",
            "src/pkg/other.py": "",
        }
    )
    verdict, detail = run(repo)["src/pkg/main.py"]
    assert verdict is Verdict.SKIPPED
    assert "never had this path" in detail


def test_a_gitignored_path_is_not_drift(make_repo: Callable[..., Path]):
    """`build/outputs/` and `.venv/bin/activate` are absent on purpose.

    The first version reported both, on Linearty and monie. The documentation was right
    and the checker was reasoning from "is this file here" instead of "does this project
    ship it".
    """
    repo = make_repo(
        {"README.md": "Artifacts land in `build/outputs/report.html`.\n", "src/keep.py": ""},
        gitignore="build/\n",
    )
    verdict, detail = run(repo)["build/outputs/report.html"]
    assert verdict is Verdict.SKIPPED
    assert "gitignore" in detail


def test_a_bare_filename_at_the_root_is_not_judged(make_repo: Callable[..., Path]):
    """`./monie_memory.db` is created when the program runs. Nothing in the document
    places it inside the repository rather than beside it."""
    repo = make_repo({"README.md": "It writes `./runtime_state.db` as it goes.\n", "a.py": ""})
    verdict, detail = run(repo)["./runtime_state.db"]
    assert verdict is Verdict.SKIPPED


def test_an_untracked_but_present_file_is_not_judged(make_repo: Callable[..., Path]):
    repo = make_repo({"README.md": "See `src/scratch.py`.\n", "src/real.py": ""})
    (repo / "src" / "scratch.py").write_text("", encoding="utf-8")
    verdict, detail = run(repo)["src/scratch.py"]
    assert verdict is Verdict.SKIPPED
    assert "untracked" in detail


def test_a_path_with_no_tracked_ancestor_is_not_judged(make_repo: Callable[..., Path]):
    """Probably describing another repository, or the reader's own tree."""
    repo = make_repo({"README.md": "Compare with `elsewhere/thing.py`.\n", "src/a.py": ""})
    verdict, detail = run(repo)["elsewhere/thing.py"]
    assert verdict is Verdict.SKIPPED


def test_placeholders_are_not_claims(make_repo: Callable[..., Path]):
    repo = make_repo({"README.md": "Put it in `path/to/your/config.yaml`.\n", "src/a.py": ""})
    assert "path/to/your/config.yaml" not in run(repo)


def test_urls_are_not_paths(make_repo: Callable[..., Path]):
    repo = make_repo({"README.md": "Open `https://example.com/docs/guide.md`.\n", "src/a.py": ""})
    assert not any("example.com" in subject for subject in run(repo))


def test_a_diagram_leaf_is_judged_by_its_full_path(make_repo: Callable[..., Path]):
    """`server.py` alone is meaningless; the claim is `src/pkg/server.py`."""
    repo = make_repo(
        {
            "README.md": "```\nroot/\n├── src/pkg/\n│   ├── server.py\n│   └── gone.py\n```\n",
            "src/pkg/server.py": "",
        },
        deleted={"src/pkg/gone.py": ""},
    )
    results = run(repo)
    assert results["src/pkg/server.py"][0] is Verdict.HOLDS
    assert results["src/pkg/gone.py"][0] is Verdict.BROKEN


def test_escaping_the_project_is_not_judged(make_repo: Callable[..., Path]):
    repo = make_repo({"README.md": "See `src/../../secrets.txt`.\n", "src/a.py": ""})
    results = run(repo)
    assert all(v is not Verdict.BROKEN for v, _ in results.values())


def test_the_verifier_is_silent_when_it_finds_nothing(make_repo: Callable[..., Path]):
    """Applicable and yet checked nothing: a failure, not a pass."""
    repo = make_repo({"README.md": "Prose with no paths in it at all.\n", "src/a.py": ""})
    project = Project(root=repo)
    outcome = DocumentedPaths().run(
        project, [Document(path=repo / "README.md", text=read(repo / "README.md"))]
    )
    assert outcome.checked == 0
    assert outcome.silent is True


# --- rules that exist because a well-known repository proved them necessary -------
#
# Twenty public Python projects, 2026-08-06. The first run produced 187 findings and
# every single one was wrong. Each test below is named for what produced it.


def test_output_in_a_transcript_is_not_a_claim(make_repo: Callable[..., Path]):
    """black's docs show `black src/ -q` printing an error that names a file it deleted.

    The sentence is an example of an error message, not an assertion that the file is
    there. Only prompt lines in a transcript are read.
    """
    repo = make_repo(
        {
            "README.md": "```console\n$ tool run\nerror: cannot parse: src/pkg/old.py:5:6\n```\n",
            "src/pkg/new.py": "",
        },
        deleted={"src/pkg/old.py": ""},
    )
    assert "src/pkg/old.py" not in run(repo)


def test_a_github_slug_in_a_link_is_not_read_as_a_path(make_repo: Callable[..., Path]):
    """tqdm's README mentions `tqdm/tqdm`, which is a repository, not a directory.

    A span carrying a URL, a `.git`, or a markdown link target is not read for paths.
    That is noise reduction, not the safety property: a bare `owner/repo` in backticks
    with no link around it is genuinely indistinguishable from a directory, and this
    does not pretend otherwise. It stays harmless because a repository that never had
    such a directory cannot have deleted one — the second assertion is the real
    guarantee, and it does not depend on recognising the shape at all.
    """
    repo = make_repo(
        {
            "README.md": "Clone from `https://github.com/pkg/pkg.git`, or see `pkg/pkg` there.\n",
            "src/a.py": "",
        }
    )
    results = run(repo)
    assert not any("github.com" in subject for subject in results)
    assert all(verdict is not Verdict.BROKEN for verdict, _ in results.values())


def test_a_media_type_is_not_a_path(make_repo: Callable[..., Path]):
    """requests' README says `application/json` twice."""
    repo = make_repo({"README.md": "It returns `application/json`.\n", "src/a.py": ""})
    assert "application/json" not in run(repo)


def test_a_verifier_that_explained_itself_is_not_silent(make_repo: Callable[..., Path]):
    """requests, attrs and jinja were each turned red by reading silence as
    `checked == 0`. They had claims, every claim was skipped with a stated reason, and
    nothing was wrong. A tool that fails a healthy repository gets switched off."""
    repo = make_repo({"README.md": "Do not name your file `flask.py`.\n", "src/a.py": ""})
    project = Project(root=repo)
    outcome = DocumentedPaths().run(
        project, [Document(path=repo / "README.md", text=read(repo / "README.md"))]
    )
    assert outcome.checked == 0
    assert outcome.skipped
    assert outcome.silent is False


def test_a_bare_filename_is_not_judged_even_when_it_was_deleted(make_repo: Callable[..., Path]):
    """flask's quickstart says "do not call your file `flask.py`" — advice about the
    reader's filename. Flask really did delete its own `flask.py` in 2010, so history
    agreed and was still answering the wrong question."""
    repo = make_repo(
        {"README.md": "Do not name your module `pkg.py`.\n", "src/a.py": ""},
        deleted={"pkg.py": ""},
    )
    verdict, detail = run(repo)["pkg.py"]
    assert verdict is Verdict.SKIPPED
    assert "bare filename" in detail


def test_a_tombstone_page_describes_the_past():
    """bandit keeps doc pages for plugins B109/B111 that open "This plugin has been
    removed." — deliberate tombstones (their PR #864 added the sentence), kept so old
    links resolve — and a stale example path inside one was reported as drift. pdm's
    `docs/dev/benchmark.md` ("This page has been removed, please visit …") is the same
    class. Deprecated is not removed: structlog's thread-local page documents a
    deprecated module that still exists, still promises, and still deserves judgment.
    """
    from docproof.config import declares_removed

    bandit = (
        "----------------------------------------------\n"
        "B109: password_config_option_not_marked_secret\n"
        "----------------------------------------------\n"
        "\n"
        "This plugin has been removed.\n"
    )
    pdm = "# Benchmark\n\nThis page has been removed, please visit [elsewhere](x).\n"
    assert declares_removed(bandit)
    assert declares_removed(pdm)

    structlog = "# Thread-local\n\nThe `structlog.threadlocal` module is deprecated as of 22.1.0.\n"
    assert not declares_removed(structlog)

    # A removal note about something else is a live page stating history.
    scrapy = "Commands\n========\n\n(The ``scrapy deploy`` command has been removed in 1.0.)\n"
    assert not declares_removed(scrapy)

    # A declaration buried past the lede does not silence the whole page.
    buried = "# Title\n" + "still here\n" * 20 + "This section has been removed.\n"
    assert not declares_removed(buried)


def test_a_changelog_describes_the_past(make_repo: Callable[..., Path]):
    """fastapi's release-notes.md alone produced 162 findings — more than every other
    document in twenty repositories combined. "0.68 moved `docs_src/websockets`" is
    correct and always will be."""
    from docproof.config import is_historical

    assert is_historical("CHANGELOG.md")
    assert is_historical("HISTORY.md")
    assert is_historical("docs/en/docs/release-notes.md")
    assert is_historical("doc/en/changelog.rst")
    assert is_historical("changelog.d/1234.bugfix.md")
    assert not is_historical("README.md")
    assert not is_historical("docs/changelog-policy.md")


def test_a_dotted_directory_is_not_stripped_to_a_real_one(make_repo: Callable[..., Path]):
    """`lstrip("./")` strips characters, not a prefix.

    poetry's docs describe `.poetry/plugins` in the *reader's* project. Stripping the dot
    turned it into `poetry/plugins`, a directory poetry really did delete in its
    src-layout move, and a correct sentence came back as drift.
    """
    repo = make_repo(
        {"README.md": "Plugins land in `.poetry/plugins`.\n", "src/a.py": ""},
        deleted={"poetry/plugins/keep.py": ""},
    )
    verdict, _ = run(repo)[".poetry/plugins"]
    assert verdict is not Verdict.BROKEN


def test_a_file_that_moved_under_src_did_not_vanish(make_repo: Callable[..., Path]):
    """pdm's docs say to add `pdm/pep582/sitecustomize.py` to the search path. The
    repository moved it under `src/` in 2022 and the sentence stayed correct, because
    after installation that is where it lives."""
    repo = make_repo(
        {"README.md": "Add `pkg/thing.py` to the path.\n", "src/pkg/thing.py": ""},
        deleted={"pkg/thing.py": ""},
    )
    verdict, detail = run(repo)["pkg/thing.py"]
    assert verdict is Verdict.SKIPPED
    assert "moved it under" in detail
