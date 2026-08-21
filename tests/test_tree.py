"""Reading directory diagrams, in the styles people actually write them in."""

from __future__ import annotations

from docproof import tree

BOX = """\
myproject/
├── src/
│   ├── core.py
│   └── util.py
└── tests/
    └── test_core.py
"""

ASCII = """\
.
|-- src/rigout/
|   |-- server.py
|   |-- lifecycle.py
|-- tests/
|   |-- unit/
"""

TWO_SPACE = """\
pkg/
  a.py
  sub/
    b.py
"""


def paths(text: str) -> list[str]:
    return [entry.path for entry in tree.parse(text, first_line=1)]


def test_box_drawing_style_resolves_full_paths():
    assert paths(BOX) == ["src", "src/core.py", "src/util.py", "tests", "tests/test_core.py"]


def test_ascii_pipe_style_resolves_full_paths():
    """`|--` shares its first character with the indentation, which broke the first
    version of this parser: a regex treating `|` as indentation ate the connector."""
    assert paths(ASCII) == [
        "src/rigout",
        "src/rigout/server.py",
        "src/rigout/lifecycle.py",
        "tests",
        "tests/unit",
    ]


def test_plain_indentation_resolves_full_paths():
    assert paths(TWO_SPACE) == ["a.py", "sub", "sub/b.py"]


def test_the_root_line_is_not_itself_a_claim():
    """`myproject/` names the repository, not a directory inside it."""
    assert "myproject" not in paths(BOX)


def test_a_flat_list_keeps_its_top_level_entries():
    """With no root line, the first entries are real top-level claims."""
    assert paths("src/\n  a.py\ntests/\n  b.py\n") == ["src", "src/a.py", "tests", "tests/b.py"]


def test_trailing_comments_are_not_part_of_the_name():
    text = "root/\n├── src/      # where the code lives\n│   └── main.py  <- entry point\n"
    assert paths(text) == ["src", "src/main.py"]


def test_placeholders_are_not_claims():
    text = "root/\n├── src/\n│   ├── ...\n│   └── real.py\n"
    assert paths(text) == ["src", "src/real.py"]


def test_prose_is_not_a_tree():
    assert not tree.looks_like_a_tree("just some\nlines of text\nin a block\n")
    assert paths("just some\nlines of text\nin a block\n") == []


def test_a_diagram_that_jumps_past_its_own_parent_is_refused_whole():
    """Half a diagram read wrongly produces confident findings about invented paths, so
    an unreadable one yields nothing at all.

    Indents 0, 4 and 12 give a stride of 4, which puts the last entry three levels below
    a parent that is only one level deep. There is no honest reading of that.
    """
    assert paths("root/\n├── a/\n│   ├── b.py\n            └── deep.py\n") == []


def test_indentation_that_shares_no_stride_is_refused_whole():
    """Two- and three-space indents in one diagram have no common level size."""
    assert paths("pkg/\n  a.py\n   b.py\n  sub/\n") == []


def test_a_consistent_odd_stride_is_readable():
    """Three spaces per level is unusual and perfectly unambiguous.

    An earlier version guessed a stride of four, then two, per line, and refused
    anything else. Inferring one stride per diagram reads this correctly instead.
    """
    assert paths("pkg/\n   odd.py\n   sub/\n      deep.py\n") == ["odd.py", "sub", "sub/deep.py"]


def test_a_short_block_is_not_a_tree():
    """Two lines are a snippet, not a layout."""
    assert not tree.looks_like_a_tree("src/\n  a.py\n")


def test_a_second_root_of_dotdot_does_not_inherit_the_first() -> None:
    """Found by running docproof on citerag, which is not this project's repository.

    `docs/README.md` there draws its own directory and then, at the same depth, a second
    block rooted at `../` listing the repository's top-level files. Skipping the `..`
    entry *before* truncating the stack meant every line under that second root inherited
    `docs/`, so `CONTRIBUTING.md` at the repository root was read as `docs/CONTRIBUTING.md`.

    It only ever produced skips, because that path had never existed - in a repository
    that had once had it and deleted it, the same bug turns a correct document into a
    contradiction with a commit hash attached to it.
    """
    drawn = tree.parse(
        "docs/\n├── README.md\n└── FAQ.md\n\n../\n├── CONTRIBUTING.md\n└── LICENSE\n",
        1,
    )
    placed = {e.path for e in drawn if not e.above_root}
    assert placed == {"docs", "docs/README.md", "docs/FAQ.md"}

    # The second block is reported, not silently dropped: an unchecked claim and a
    # checked one must not look the same from the outside.
    unplaceable = {e.name for e in drawn if e.above_root}
    assert unplaceable == {"CONTRIBUTING.md", "LICENSE"}
    assert not any(e.path.startswith("docs/CONTRIBUTING") for e in drawn)
