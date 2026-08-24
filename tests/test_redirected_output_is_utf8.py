"""A redirected report must be valid UTF-8, including the characters we did not write.

0.2.2 removed all 202 em dashes because cp1252 encodes U+2014 as the single byte 0x97 and a
redirected report was therefore corrupt at its own header. That fixed every character docproof
EMITS. It could not fix the ones docproof QUOTES, and quoting the document back at the reader
is the entire job of the tool.

Reproduced against the shipped 0.2.2, on a project whose README names `docs/cafe-guide.md`
with an acute accent:

    docproof --show-skips > report.txt
    b'  README.md:3  `docs/caf\\xe9-guide.md` - this repository has never had this path...'
    UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 637

Nothing raises on the writing side, which is why this outlived the em dash sweep: 0xe9 is a
perfectly good cp1252 encoding of an accented letter. It is simply not UTF-8, so the file is
corrupt to every reader downstream - a CI log viewer, an editor, the next tool in the pipe.

**A REAL REDIRECT, deliberately.** The first attempt at this measurement ran the CLI under
PowerShell with `>`, which decodes the child's output and re-encodes it as UTF-8 with a BOM.
That test could not have failed no matter how broken the tool was, which is this repository's
oldest lesson (`test_output_encoding.py` says the same thing about reassigning `sys.stdout`).
So: a subprocess, a file opened by the operating system, and bytes compared as bytes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

PYPROJECT = """\
[project]
name = "accented"
version = "0.1.0"
"""

# An accented path in a documented claim. Not exotic: any French, Spanish, German or
# Portuguese project names files like this, and docproof quotes the claim back verbatim.
ACCENTED_DOC = "# Guide\n\nSee `docs/café-guide.md` for setup, and `docs/naïve.md` too.\n"


def run_redirected(repo: Path, tmp_path: Path, *args: str) -> bytes:
    """Run the CLI with stdout attached to a real file. Returns the file's raw bytes.

    `PYTHONIOENCODING` is explicitly REMOVED rather than left alone: pytest may be running
    under one, and the fix defers to it by design, so inheriting it would disable the very
    behaviour under test.
    """
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    env.pop("PYTHONIOENCODING", None)
    out = tmp_path / "report.txt"
    with out.open("wb") as fh:
        subprocess.run(
            [sys.executable, "-c", "import sys; from docproof.cli import main; sys.exit(main())", *args],
            cwd=str(repo),
            stdout=fh,
            stderr=subprocess.PIPE,
            timeout=300,
            env=env,
            check=False,
        )
    return out.read_bytes()


def test_a_quoted_accented_path_survives_a_redirect(make_repo: Callable[..., Path], tmp_path: Path) -> None:
    """The bug, end to end. Decoding is the assertion: it raises if the bytes are wrong."""
    repo = make_repo({"pyproject.toml": PYPROJECT, "README.md": ACCENTED_DOC})

    raw = run_redirected(repo, tmp_path, "--show-skips")

    text = raw.decode("utf-8")  # the whole point: this raised on 0.2.2
    # And it must actually have quoted the thing, or the file is clean because it is empty.
    assert "café-guide.md" in text, text[-1500:]
    assert "naïve.md" in text, text[-1500:]


def test_the_character_is_preserved_rather_than_stripped(
    make_repo: Callable[..., Path], tmp_path: Path
) -> None:
    """Valid UTF-8 is achievable by mangling every accent to `?`, which would be a worse tool.

    This pins the difference between fixing the encoding and deleting the information: the
    report has to carry the path a reader can actually search their repository for.
    """
    repo = make_repo({"pyproject.toml": PYPROJECT, "README.md": ACCENTED_DOC})

    raw = run_redirected(repo, tmp_path, "--show-skips")

    assert "café".encode() in raw, "the accented byte sequence should be UTF-8, intact"
    assert b"caf?" not in raw
    assert b"caf\\u00e9" not in raw, "escaped rather than encoded means the handler fired"


def test_a_pinned_encoding_is_still_obeyed(make_repo: Callable[..., Path], tmp_path: Path) -> None:
    """PYTHONIOENCODING is a user decision and outranks this fix.

    Without this, `test_output_encoding.py` would quietly stop testing what it says it tests:
    it pins cp1252 through a pipe to exercise the narrow-console path, and a blanket UTF-8
    conversion on every non-tty stream would turn that into a UTF-8 test wearing a cp1252 name.
    """
    repo = make_repo({"pyproject.toml": PYPROJECT, "README.md": ACCENTED_DOC})
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        "PYTHONIOENCODING": "cp1252",
    }
    out = tmp_path / "pinned.txt"
    with out.open("wb") as fh:
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from docproof.cli import main; sys.exit(main())",
                "--show-skips",
            ],
            cwd=str(repo),
            stdout=fh,
            stderr=subprocess.PIPE,
            timeout=300,
            env=env,
            check=False,
        )
    raw = out.read_bytes()

    assert b"\xe9" in raw, "a pinned cp1252 should still write cp1252"
    assert "café".encode() not in raw
