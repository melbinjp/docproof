"""A directory diagram whose entries carry a description column is still a diagram.

**Measured on `ComposioHQ/composio`.** Its README draws the repository layout like this:

    ```text
    ts/                TypeScript SDK workspace
      packages/core/       @composio/core
      packages/providers/  Provider adapters
      packages/cli/        Composio CLI
    python/            Python SDK and provider packages
    ```

`looks_like_a_tree` said no, because the indentation-only branch demanded that every line
be a single token and that some line END in a slash. Both fail here: the description sits
where the slash would be. So the block fell through to the plain path reader, which took
`packages/providers/` as a path from the repository root and reported it deleted.

`ts/packages/providers` exists.

**The trigger is what makes this worth fixing rather than tolerating.** A path is only
reported as deleted when history has a commit that removed it, and composio moved
`packages/` under `ts/` on 2025-06-16. A directory that never sat at the root produces no
finding at all. So the misreading fires precisely on projects that reorganised, which are
the projects whose layout diagrams are most likely to be stale and most worth checking.

Measured after the change: **106 of 110,615 fenced blocks across 217 repositories** newly
read as diagrams, and re-sweeping batch 10 moved exactly one repository, composio, from one
finding to zero. No new findings anywhere.
"""

from __future__ import annotations

from docproof.tree import looks_like_a_tree, parse

COMPOSIO = """\
ts/                TypeScript SDK workspace
  packages/core/       @composio/core
  packages/providers/  Provider adapters
  packages/cli/        Composio CLI
python/            Python SDK and provider packages
docs/              Documentation site (docs.composio.dev)"""


def test_the_composio_block_is_a_diagram_and_resolves_under_its_parent() -> None:
    assert looks_like_a_tree(COMPOSIO)
    at = {entry.path: entry.line for entry in parse(COMPOSIO, 156)}
    # The claim that was reported deleted, now carrying the prefix the drawing gives it.
    assert "ts/packages/providers" in at
    assert "packages/providers" not in at
    # Siblings at column zero stay at the top level rather than inheriting `ts/`.
    assert "python" in at and "docs" in at
    # And the line is the entry's own, which is what a maintainer opens.
    assert at["ts/packages/providers"] == 158


def test_an_options_list_is_not_a_diagram() -> None:
    """The first token has to be path-shaped, and `--verbose` is not."""
    assert not looks_like_a_tree("Options:\n  --verbose      be loud\n  --quiet        be quiet")


def test_a_shell_transcript_is_not_a_diagram() -> None:
    """`python` is a bare word, so the block never reaches the slash test."""
    assert not looks_like_a_tree("python -m pip install x\n  python -m pytest\npython -m build")


def test_one_bare_word_disqualifies_the_whole_block() -> None:
    """**The narrow part of the relaxation, asserted directly.**

    Two of these three lines are paths and one is the word `make`. Accepting the block
    would claim `make` as a path at the top level. Every first token has to qualify, not
    most of them, because the cost of being wrong here is a finding about a file nobody
    wrote.
    """
    assert not looks_like_a_tree("src/     source\nbuild/   output\n  make     run it")


def test_a_flat_list_of_files_is_not_a_layout() -> None:
    """Nothing ends in a slash, so there is no directory for a description column to
    hang off, and a list of filenames in a code block stays a list."""
    assert not looks_like_a_tree("alpha.py   the first\n  beta.py    the second\ngamma.py   third")


def test_a_line_holding_several_entries_under_claims_rather_than_guesses() -> None:
    """`rustfs` writes `p0-before/  p0-after/` on one line, two directories side by side.

    `parse` reads the first token and drops the rest, so the second entry is not claimed.
    That is a gap and it is the safe direction: a claim not made costs coverage, a claim
    invented costs the reader's trust. Asserted so that nobody 'fixes' it into guessing.
    """
    text = "bench/\n  p0-before/  p0-after/   summaries\n  p1-before/  p1-after/   deltas"
    assert looks_like_a_tree(text)
    paths = {entry.path for entry in parse(text, 1)}
    # `bench/` is the diagram's own root with everything nested under it, so it names the
    # repository and is dropped. That is existing behaviour and this test asserted the
    # opposite on the first attempt, which is worth leaving recorded: the prefix rule and
    # the root rule interact, and only one of them is new here.
    assert paths == {"p0-before", "p1-before"}
    # The second entry on each line is not claimed. A claim not made costs coverage; a
    # claim invented costs the reader's trust.
    assert "p0-after" not in paths
