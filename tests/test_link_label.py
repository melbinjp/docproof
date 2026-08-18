"""A stale path that is only the LABEL of a link whose target works.

    see [`docs/STATE-MD-LIFECYCLE.md`](reference/state-md.md) for the field reference

The label is a display string that went stale. The target resolves. Nobody following that
link lands anywhere wrong, so calling it drift argues with a document that is doing its job.

docproof already skipped the reference form, `[label]: target`, on exactly this reasoning.
Judging the inline form while skipping the reference form was an inconsistency rather than a
position, and the inline form is the common one: 137,937 of them across the 134 cloned
repositories against a few dozen reference definitions.

**Measured before it was built**, and the measurement is why the rule is narrow:

    137,937 inline links, 7,426 with a path-shaped label
      5,529 where the label is not in the tree and the target resolves
      4,838 of those resolve to a URL - and almost all are org/repo slugs used as a label
            (`shadcn/ui`, `encode/broadcaster`), which were never repository paths
        687 resolve to a file on disk, which is the real class
          4 of the 217 corpus findings sit in it, and none was ever filed

The 4 were excluded by hand at filing time with the reasoning written into the issue, and a
gsd-core maintainer verified that exclusion independently while triaging #3620.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

PYPROJECT = """\
[project]
name = "linklabel"
version = "0.1.0"
"""


def test_a_label_whose_target_resolves_is_skipped_and_the_reason_is_given(
    make_repo: Callable[..., Path], capsys
) -> None:
    """The shape itself, end to end.

    Asserted as a SKIP rather than silence: this rule decides by itself that a path is a
    display string, so over-firing must show as a named skip and not as a report that
    quietly got cleaner.
    """
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "reference/state-md.md": "# State\n"},
        documented_before={
            "GUIDE.md": "See [`docs/STATE-MD-LIFECYCLE.md`](reference/state-md.md) for detail.\n"
        },
        deleted={"docs/STATE-MD-LIFECYCLE.md": "# old\n"},
    )
    main([str(repo), "--show-skips"])
    out = capsys.readouterr().out

    assert "nobody following the link lands anywhere wrong" in out


def test_a_url_target_earns_no_skip(make_repo: Callable[..., Path], capsys) -> None:
    """The whole safety of the rule, and the reason it is not the larger number.

    docproof cannot fetch, and when a repository deletes a file the blob URL pointing at it
    dies with it. Trusting a URL would turn a real broken reference into silence, which is
    the failure this tool exists to remove.
    """
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": PYPROJECT},
        documented_before={
            "GUIDE.md": "See [`src/gone.py`](https://example.invalid/blob/main/src/gone.py).\n"
        },
        deleted={"src/gone.py": "x = 1\n"},
    )
    main([str(repo)])
    out = capsys.readouterr().out

    assert "src/gone.py" in out, "a URL target must not silence a deleted path"


def test_a_label_whose_target_is_also_missing_is_still_reported(
    make_repo: Callable[..., Path], capsys
) -> None:
    """A broken link is not a display name. If the target does not resolve either, the
    reader lands nowhere and the finding stands."""
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": PYPROJECT},
        documented_before={"GUIDE.md": "See [`src/gone.py`](also/missing.md) for detail.\n"},
        deleted={"src/gone.py": "x = 1\n"},
    )
    main([str(repo)])
    out = capsys.readouterr().out

    assert "src/gone.py" in out


def test_a_bare_mention_is_untouched(make_repo: Callable[..., Path], capsys) -> None:
    """The rule is about links. A path named in prose is still a claim about the tree, and
    this is the case that would break if the label matching ever went token-wide."""
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "reference/state-md.md": "# State\n"},
        documented_before={"GUIDE.md": "The entry point is `src/gone.py` today.\n"},
        deleted={"src/gone.py": "x = 1\n"},
    )
    main([str(repo)])
    out = capsys.readouterr().out

    assert "src/gone.py" in out


def test_the_target_may_resolve_from_the_repository_root(
    make_repo: Callable[..., Path], capsys
) -> None:
    """Real documents write both. `docs/x.md` from a doc in `docs/` resolves against the
    root, not against the document's own directory, and a rule that only tried one of the
    two would fire on half the class and look like it worked."""
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": PYPROJECT, "reference/state-md.md": "# State\n"},
        documented_before={
            "docs/GUIDE.md": "See [`docs/OLD.md`](reference/state-md.md) for detail.\n"
        },
        deleted={"docs/OLD.md": "# old\n"},
    )
    main([str(repo), "--show-skips"])
    out = capsys.readouterr().out

    assert "nobody following the link lands anywhere wrong" in out


def test_an_anchor_only_link_earns_no_skip(make_repo: Callable[..., Path], capsys) -> None:
    """`[label](#section)` goes nowhere near the tree, so it is no evidence at all that a
    path exists. Left explicit because treating it as 'resolves' is the easy mistake."""
    from docproof.cli import main

    repo = make_repo(
        {"pyproject.toml": PYPROJECT},
        documented_before={"GUIDE.md": "See [`src/gone.py`](#details) below.\n"},
        deleted={"src/gone.py": "x = 1\n"},
    )
    main([str(repo)])
    out = capsys.readouterr().out

    assert "src/gone.py" in out
