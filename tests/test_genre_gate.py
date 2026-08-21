"""The genre gate: what it holds back, and the two ways it must never fail.

Measured over 61 hand-judged findings across 44 repositories - reference 35/37 real, plan
0/14, record 1/4. Holding plan and record back moves precision from 0.69 to 0.95 at the cost
of one real finding. `docproof.genre` carries the full working and the pre-registered
falsification test.

These tests pin the two failure directions, which are not symmetric:

- Holding back something real because of where the repository was CHECKED OUT is silent and
  is the tool lying about a clean bill of health. That one already happened, in this suite,
  within a minute of the gate being written.
- Holding back nothing is merely the old behaviour, and is visible.
"""

from __future__ import annotations

from pathlib import Path

from docproof.genre import genre, held_back, relative_doc


def test_the_shipped_lists_are_the_measured_lists():
    """The rule that ships has to be the rule that was measured, or the 0.95 in the docstring
    is a number about a different program."""
    assert genre("docs/workstreams/DESIGN.md") == "plan"
    assert genre("TODO.md") == "plan"
    assert genre("docs/validation-report.md") == "record"
    assert genre("CHANGELOG.md") == "record"
    assert genre("README.md") == "reference"
    assert genre("docs/architecture.md") == "reference"
    assert genre("src/thing.md") == "other"


def test_order_matters_and_the_narrower_signal_wins():
    """`docs/references/.../architecture.md` is a reference that contains an architecture
    word; `docs/workstreams/.../DESIGN.md` is a plan that happens to sit under docs/."""
    assert genre("docs/workstreams/auth/DESIGN.md") == "plan"
    # `reference` and `architecture` are both REFERENCE words, so that path is unambiguous.
    assert genre("docs/reference/architecture.md") == "reference"
    # A plan word anywhere outranks a reference word, by construction and on purpose.
    assert genre("docs/reference/upgrade-guide.md") == "plan"


def test_other_is_not_held_back():
    """36% of findings on the broad corpus are `other`. The path rule has nothing to say
    about them, and holding them back would be acting on an absence of evidence."""
    assert not held_back("src/thing.md")
    assert not held_back("CONTRIBUTING.md")
    assert held_back("TODO.md")
    assert held_back("docs/postmortem.md")


def test_a_checkout_directory_cannot_change_a_documents_genre(tmp_path: Path):
    """THE ONE THAT ALREADY BIT.

    A pytest tmp directory named `test_exit_zero_reports_a_contr0` contains "report", so an
    absolute path classified a README as a record and its finding vanished. Anybody whose
    code lives under a folder containing plan, report, history or audit would have lost
    findings with no indication that anything had been withheld.
    """
    for hostile in ("test_exit_zero_reports_a_contr0", "my-plans", "audit-2026", "history", "work/roadmap"):
        root = tmp_path / hostile
        doc = root / "README.md"
        assert relative_doc(doc, root) == "README.md"
        assert genre(relative_doc(doc, root)) == "reference"
        assert not held_back(relative_doc(doc, root)), (
            f"a README under {hostile}/ was held back because of its parent directory"
        )


def test_a_document_outside_the_root_falls_back_to_its_name(tmp_path: Path):
    """`relative_to` raises when the document is not under the root. Falling back to the
    bare filename keeps the rule on the narrowest true thing rather than on a path whose
    directories were never the project's choice."""
    assert relative_doc(tmp_path / "elsewhere" / "TODO.md", tmp_path / "other") == "TODO.md"
    assert held_back(relative_doc(tmp_path / "elsewhere" / "TODO.md", tmp_path / "other"))


def test_the_gate_holds_back_a_plan_finding_and_says_so(make_repo, capsys):
    """End to end, and the SAYING is half the test: a report that quietly got cleaner is the
    failure this codebase already names in `cli.py`."""
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": "[project]"},
        deleted={"tools/gone.py": ""},
        documented_before={"docs/ROADMAP.md": "Run `tools/gone.py` first."},
    )
    code = main([str(repo)])
    out = capsys.readouterr().out
    assert "held back" in out, "the gate withheld a finding without naming it"
    assert "ROADMAP" in out
    assert "--all-genres" in out, "the reader was not told how to see it anyway"
    assert code == 0, "a held-back finding should not fail the run"


def test_all_genres_judges_them_anyway(make_repo):
    """The escape hatch has to actually work, or the gate is a deletion."""
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": "[project]"},
        deleted={"tools/gone.py": ""},
        documented_before={"docs/ROADMAP.md": "Run `tools/gone.py` first."},
    )
    assert main([str(repo), "--all-genres"]) == 1


def test_a_reference_finding_still_fails_the_run(make_repo):
    """The gate must not have made everything pass."""
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": "[project]"},
        deleted={"tools/gone.py": ""},
        documented_before={"README.md": "Run `tools/gone.py` first."},
    )
    assert main([str(repo)]) == 1
