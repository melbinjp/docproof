"""The silent verdict, judged from history rather than guessed.

Failing every silent run was measured over 53 public repositories: five alarms, one
real. Each class below is named after the repository that produced it, so the corpus
that set the rule is the test that keeps it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.cli import main
from docproof.config import Config, suppressed_lines
from docproof.docs import find_docs, read
from docproof.history import classify, sample_indices
from docproof.model import Finding, Outcome, Silence, SilenceVerdict
from docproof.project import Project
from docproof.report import Report
from docproof.verifiers.base import Document
from docproof.verifiers.cli_flags import DocumentedFlags
from docproof.verifiers.paths import DocumentedPaths

PYPROJECT = """\
[project]
name = "prog"
version = "0"

[project.scripts]
prog = "prog:main"
"""


def live(repo: Path) -> tuple[Project, list[Document]]:
    """The live documents exactly as `cli.main` would build them."""
    project = Project(root=repo)
    documents = []
    for path in find_docs(repo):
        text = read(path)
        documents.append(Document(path=path, text=text, suppressed=suppressed_lines(text)))
    return project, documents


# -- the four classes, one repository each ------------------------------------------------


def test_httpx_never_documented_flags_so_silence_is_its_steady_state(
    make_repo: Callable[..., Path],
) -> None:
    """httpx shows its CLI as a screenshot and always has. Its silence is not a
    regression, and failing it teaches people to switch the tool off."""
    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "README.md": "A fine HTTP tool, shown as a picture.\n"}
    )
    project, documents = live(repo)
    verdict = classify(project, Config(), DocumentedFlags(), documents)
    assert verdict.kind is Silence.NEVER
    assert not verdict.alarming
    assert "steady state" in verdict.detail


def test_twine_stopped_documenting_the_flag_and_the_text_left_with_it(
    make_repo: Callable[..., Path],
) -> None:
    """twine's `--repository-url` walked out of the README in 2019 along with the
    workflow it described. The docs moved on; the check should say so quietly, with
    the last loud commit as the receipt."""
    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "README.md": "Docs live at the website now.\n"},
        deleted={"README.md": "```\n$ prog --repository-url https://upload.example/\n```\n"},
    )
    project, documents = live(repo)
    verdict = classify(project, Config(), DocumentedFlags(), documents)
    assert verdict.kind is Silence.STOPPED
    assert not verdict.alarming
    assert "--repository-url" in verdict.detail


def test_rigout_the_flag_survives_in_prose_but_extraction_lost_it(
    make_repo: Callable[..., Path],
) -> None:
    """The rigout case, and the one alarm that was real: the documentation still talks
    about the thing, but a rewrite took it out of the shape extraction matches. The
    check went quiet while the claim stood — exactly what must fail the run."""
    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "README.md": "Pass --dry-run to preview changes.\n"},
        deleted={"README.md": "```\n$ prog --dry-run\n```\n"},
    )
    project, documents = live(repo)
    verdict = classify(project, Config(), DocumentedFlags(), documents)
    assert verdict.kind is Silence.REGRESSED
    assert verdict.alarming
    assert "--dry-run" in verdict.detail and "README.md:1" in verdict.detail


def test_paramiko_deleted_the_file_and_its_mention_together(
    make_repo: Callable[..., Path],
) -> None:
    """paramiko removed `./test.py` and the sentence pointing at it in the same era.
    Nothing is wrong: the project stopped making the claim, on purpose."""
    repo = make_repo(
        {"README.md": "Use pytest.\n", "src/keep.py": ""},
        deleted={"README.md": "Run `./test.py` to see it all pass.\n"},
    )
    project, documents = live(repo)
    verdict = classify(project, Config(), DocumentedPaths(), documents)
    assert verdict.kind is Silence.STOPPED
    assert not verdict.alarming
    assert "./test.py" in verdict.detail


def test_litecli_a_checkout_broken_since_clone_day_is_caught_first(
    make_repo: Callable[..., Path],
) -> None:
    """The first time this classifier ran over a real corpus it found a clone that had
    been half-empty since clone day — a tracked filename NTFS refuses. When HEAD's
    blobs are loud and the files on disk are silent, no history reading matters: the
    checkout itself is broken."""
    repo = make_repo({"README.md": "The entry point is `src/app.py`.\n", "src/app.py": ""})
    (repo / "README.md").write_text("", encoding="utf-8")
    project, documents = live(repo)
    verdict = classify(project, Config(), DocumentedPaths(), documents)
    assert verdict.kind is Silence.TREE_MISMATCH
    assert verdict.alarming
    assert "src/app.py" in verdict.detail


def test_litecli_a_checkout_with_no_documents_at_all_still_alarms(
    make_repo: Callable[..., Path],
) -> None:
    """The real litecli clone was worse than a mismatched README: the failed checkout
    left no documents on disk at all, so the run ended at "nothing to prove" — exit 0,
    forever. An empty run must ask HEAD before it calls the emptiness fine."""
    repo = make_repo({"README.md": "The entry point is `src/app.py`.\n", "src/app.py": ""})
    (repo / "README.md").unlink()
    exit_code = main([str(repo)])
    assert exit_code == 1


def test_a_project_with_no_documentation_anywhere_has_nothing_to_prove(
    make_repo: Callable[..., Path],
) -> None:
    """The ordinary empty case stays ordinary: nothing on disk, nothing at HEAD,
    exit 0."""
    repo = make_repo({"src/keep.py": ""})
    assert main([str(repo)]) == 0


# -- when history cannot answer -----------------------------------------------------------


def test_a_shallow_clone_cannot_be_judged_and_names_the_fix(
    make_repo: Callable[..., Path],
) -> None:
    """A CI checkout with `fetch-depth: 1` has no history to read. That is the
    environment refusing to answer, not the project misbehaving: visible, exit 0,
    and the message names the setting that fixes it."""
    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "README.md": "Quiet on purpose.\n"}, shallow=True
    )
    project, documents = live(repo)
    verdict = classify(project, Config(), DocumentedFlags(), documents)
    assert verdict.kind is Silence.UNKNOWN
    assert not verdict.alarming
    assert "fetch-depth: 0" in verdict.detail


def test_a_verifier_that_cannot_replay_extraction_keeps_the_old_alarm() -> None:
    """Until a verifier separates extraction from judging, its silence cannot be
    classified — and the conservative reading is the strict one it always had."""

    class Monolithic:
        name = "monolith"

    verdict = classify(
        Project(root=Path(".")), Config(), Monolithic(), []  # type: ignore[arg-type]
    )
    assert verdict.kind is Silence.UNKNOWN
    assert verdict.alarming


# -- what the report does with the classification -----------------------------------------


def test_history_explained_silence_does_not_gate() -> None:
    outcome = Outcome(
        verifier="cli-flags",
        silence=SilenceVerdict(kind=Silence.NEVER, detail="never made such claims", alarming=False),
    )
    report = Report(project=Project(root=Path(".")), outcomes=[outcome])
    assert report.exit_code == 0
    assert "never made such claims" in report.render()


def test_an_alarming_silence_still_gates() -> None:
    outcome = Outcome(
        verifier="paths",
        silence=SilenceVerdict(kind=Silence.TREE_MISMATCH, detail="HEAD is loud", alarming=True),
    )
    report = Report(project=Project(root=Path(".")), outcomes=[outcome])
    assert report.exit_code == 1


def test_an_unclassified_silence_keeps_the_old_strict_behaviour() -> None:
    """An Outcome built without asking history — older callers, hand-rolled tests —
    must not quietly acquire a pass."""
    report = Report(project=Project(root=Path(".")), outcomes=[Outcome(verifier="paths")])
    assert report.exit_code == 1
    assert "worth a look" in report.render()


def test_unknown_silence_is_visible_but_does_not_gate() -> None:
    outcome = Outcome(
        verifier="cli-flags",
        silence=SilenceVerdict(kind=Silence.UNKNOWN, detail="no history here", alarming=False),
    )
    report = Report(project=Project(root=Path(".")), outcomes=[outcome])
    assert report.exit_code == 0
    assert "!!" in report.render()


# -- the machinery underneath -------------------------------------------------------------


def test_extraction_is_check_minus_the_judging(make_repo: Callable[..., Path]) -> None:
    """`extract` must see exactly the claims `check` judges, or history replays a
    different question than the run asked."""
    repo = make_repo(
        {
            "README.md": "Start at `src/pkg/main.py`; artifacts land in `build/out.html`.\n",
            "src/pkg/main.py": "",
        }
    )
    project, documents = live(repo)
    verifier = DocumentedPaths()
    extracted = [
        item.claim if isinstance(item, Finding) else item
        for item in verifier.extract(project, documents)
    ]
    judged = [finding.claim for finding in verifier.check(project, documents)]
    assert extracted == judged


def test_sampling_always_includes_both_ends() -> None:
    """"Ever" and "still" are the words the classification turns on, so the newest and
    oldest commits are never left out, whatever the total."""
    for total in (1, 2, 3, 7, 100, 5000):
        indices = sample_indices(total)
        assert indices[0] == 0 and indices[-1] == total - 1
        assert all(0 <= index < total for index in indices)
