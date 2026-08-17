"""Blocks the prose labels as the thing you are moving away from.

Every case here comes from `mind/work/docproof-sweep/measure_supersede.py`, which read the
hundred-repo corpus rather than guessing: 54 label-then-block sites, 33 on the superseded
side, 20 on the current side, 1 false match. The two that matter are
`test_the_plaid_case` — the false positive that produced this rule — and
`test_the_after_half_is_still_judged`, which is the over-correction it must not become.
"""

from __future__ import annotations

from docproof.config import superseded_lines

PLAID = """\
#### Client initialization

From:

```python
from plaid import Client
Client(client_id=os.environ['CLIENT_ID'])
```

To:

```python
from plaid.api import plaid_api
configuration = plaid.Configuration(host=plaid.Environment.Sandbox)
```
"""


def lines_of(text: str, sentinel: str) -> set[int]:
    return {i for i, line in enumerate(text.split("\n"), 1) if sentinel in line}


def test_the_plaid_case() -> None:
    """`from plaid import Client` under a `From:` label is the pre-8.0.0 API, shown so an
    upgrading reader recognises it. `plaid.Client` not existing is the point of the passage."""
    covered = superseded_lines(PLAID)
    assert lines_of(PLAID, "from plaid import Client") <= covered


def test_the_after_half_is_still_judged() -> None:
    """The over-correction this must not become: twenty of the corpus's 54 sites are the
    CURRENT side, and silencing those would drop live, correct, checkable code."""
    covered = superseded_lines(PLAID)
    assert not lines_of(PLAID, "plaid_api") & covered
    assert not lines_of(PLAID, "plaid.Configuration") & covered


def test_before_and_after_stops_at_the_first_fence() -> None:
    text = "Before:\n\n```python\nold()\n```\n\nAfter:\n\n```python\nnew()\n```\n"
    covered = superseded_lines(text)
    assert lines_of(text, "old()") <= covered
    assert not lines_of(text, "new()") & covered


def test_old_code_is_the_datasette_upgrade_guide_shape() -> None:
    text = "Old code:\n\n```python\nds.metadata()\n```\n\nNew code:\n\n```python\nds.get_query()\n```\n"
    covered = superseded_lines(text)
    assert lines_of(text, "ds.metadata()") <= covered
    assert not lines_of(text, "ds.get_query()") & covered


def test_a_heading_naming_a_directory_is_not_a_label() -> None:
    """The single false match in the corpus: gunicorn's `### From repository root:`, which
    says where to run a command, not that the command is obsolete."""
    text = "### From repository root:\n\n```bash\npytest tests/\n```\n"
    assert superseded_lines(text) == frozenset()


def test_deprecated_is_not_removed() -> None:
    """`TOMBSTONE` already draws this line and it is drawn the same way here: a deprecated
    API still exists, still makes promises, and still deserves judgment."""
    text = "Deprecated:\n\n```python\nlegacy_call()\n```\n"
    assert superseded_lines(text) == frozenset()


def test_an_import_line_is_not_a_label() -> None:
    """298 of the first pass's 391 sites were this: a Python import that happens to begin
    with the word `from`. The rule keys on line shape, not vocabulary."""
    text = "```python\nfrom myapp import app\n```\n"
    assert superseded_lines(text) == frozenset()


def test_a_label_with_no_block_after_it_covers_nothing() -> None:
    assert superseded_lines("Before:\n\nSome prose, no code at all.\n") == frozenset()
