"""A character the console cannot encode must not take the whole report down.

Found by running docproof on a real repository from a Windows shell. It printed the header
and the skip list and then died:

    File "src/docproof/cli.py", line 154, in main
        print(report.render(show_skips=args.show_skips))
    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2192'

The arrow was not ours. docproof quotes the COMMIT MESSAGE that removed a file, as part of
explaining itself:

    but    deleted in c354ee5bb (2026-04-25, "feat(resilience): rename tradeSanctions
           -> tradePolicy + drop") and never restored

so the trigger is any repository whose relevant commit subject contains a character outside
the console's codepage. Arrows, accented author prose, CJK, an emoji in a conventional-commit
scope: none of that is exotic, and none of it survives cp1252.

The exit code on that crash is 1, which is also the code for "claims were contradicted", so a
Windows user sees a red build and a traceback where the report should be and cannot tell a
broken tool from a broken document.

**Run as a SUBPROCESS with a real narrow stdout, deliberately.** Reassigning `sys.stdout`
inside the test process would exercise a Python object rather than the encoder the operating
system actually hands us, and this repository has already shipped one test that passed while
testing nothing for exactly that reason.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

PYPROJECT = """\
[project]
name = "narrow"
version = "0.1.0"
"""

# The real one, from worldmonitor's history. A conventional-commit subject with an arrow in
# it is an ordinary thing for a rename to say.
ARROW_COMMIT = "feat(resilience): rename tradeSanctions → tradePolicy + drop"

DOC = """\
# Testing

The mapping is covered by `tests/resilience-sanctions-field-mapping.test.mts`.
"""


def run_cli(repo: Path, encoding: str) -> subprocess.CompletedProcess[bytes]:
    """docproof, with stdout pinned to `encoding`, captured as BYTES.

    Bytes rather than text: decoding here with the wrong codec would hide the very failure
    the test is about.
    """
    env = {
        **os.environ,
        "PYTHONIOENCODING": encoding,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    return subprocess.run(
        [sys.executable, "-c", "import sys; from docproof.cli import main; sys.exit(main())"],
        cwd=str(repo),
        capture_output=True,
        timeout=300,
        env=env,
    )


def test_a_commit_message_the_console_cannot_encode_still_produces_a_report(
    make_repo: Callable[..., Path],
) -> None:
    """The whole bug, end to end: narrow console, wide commit subject, real report out."""
    repo = make_repo(
        {"pyproject.toml": PYPROJECT},
        # `documented_before`, NOT `files`. A document committed after the deletion mentions
        # a path that was already gone, which docproof correctly reads as an illustration and
        # skips - the first version of this test did that and rendered no finding at all, so
        # it proved nothing about encoding. Real drift is a document that was true when
        # written and was broken later, and only this argument builds that history.
        documented_before={"docs/testing.md": DOC},
        deleted={"tests/resilience-sanctions-field-mapping.test.mts": "test\n"},
        removal_message=ARROW_COMMIT,
    )

    result = run_cli(repo, "cp1252")
    out = result.stdout.decode("cp1252", "replace") + result.stderr.decode("cp1252", "replace")

    assert "UnicodeEncodeError" not in out, out[-2000:]
    assert "Traceback" not in out, out[-2000:]
    # It must have got all the way to the summary, not merely survived the header.
    assert "checked" in out
    # And it must still have FOUND the thing, rather than surviving by reporting nothing.
    assert "resilience-sanctions-field-mapping" in out


def test_the_same_run_is_unchanged_on_a_utf8_console(
    make_repo: Callable[..., Path],
) -> None:
    """Where stdout can already carry it, the character arrives intact.

    This is the half that stops the fix from becoming a different kind of damage: the repair
    is an error HANDLER, not a re-encoding, so nothing is degraded on the consoles that were
    always fine - which is every CI runner, and the reason CI never caught this.
    """
    repo = make_repo(
        {"pyproject.toml": PYPROJECT},
        # `documented_before`, NOT `files`. A document committed after the deletion mentions
        # a path that was already gone, which docproof correctly reads as an illustration and
        # skips - the first version of this test did that and rendered no finding at all, so
        # it proved nothing about encoding. Real drift is a document that was true when
        # written and was broken later, and only this argument builds that history.
        documented_before={"docs/testing.md": DOC},
        deleted={"tests/resilience-sanctions-field-mapping.test.mts": "test\n"},
        removal_message=ARROW_COMMIT,
    )

    result = run_cli(repo, "utf-8")
    out = result.stdout.decode("utf-8", "replace")

    assert "UnicodeEncodeError" not in out
    assert "→" in out, "the arrow should survive a console that can encode it"
