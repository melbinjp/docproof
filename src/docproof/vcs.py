"""Asking git what the project actually ships.

The first version of the path check used "does this exist on disk", and running it over
real repositories showed why that is wrong. Every finding it produced was a false
positive, and they fell into one class: **paths that are absent on purpose.**

    build/outputs/roborazzi/   a build output          .gitignore: **/build/
    .venv/bin/activate         a virtualenv            .gitignore: .venv/
    ./monie_memory.db          created when it runs    not ignored, not shipped

The documentation was right about all three. The checker was reasoning from the wrong
fact. "Is this file here" is not the question; **"does this project ship this file"** is,
and the project already answers it — in its index and in its `.gitignore`. Those are
declarations by the author, which is exactly the kind of truth this tool is supposed to
derive rather than guess.

**When git is not available this reports so, and every judgement that depended on it
becomes a skip.** A checker that quietly falls back to a weaker rule is a checker whose
output means different things on different machines.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

TIMEOUT = 30


def _run(args: list[str], cwd: Path, stdin: str | None = None) -> tuple[int, str, str]:
    try:
        finished = subprocess.run(
            args,
            cwd=cwd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 127, "", f"{type(error).__name__}: {error}"
    return finished.returncode, finished.stdout, finished.stderr


@dataclass
class Git:
    """What the repository tracks and what it deliberately does not."""

    root: Path

    @cached_property
    def _probe(self) -> tuple[int, str]:
        code, _out, err = _run(["git", "rev-parse", "--is-inside-work-tree"], self.root)
        return code, " ".join(err.split())[:120]

    @cached_property
    def available(self) -> bool:
        return self._probe[0] == 0

    @property
    def unavailable_because(self) -> str:
        """git's own words, so a report never invents a cause it has not established."""
        return self._probe[1] or "no reason given"

    @cached_property
    def tracked_files(self) -> frozenset[str]:
        if not self.available:
            return frozenset()
        code, out, _ = _run(["git", "ls-files", "-z"], self.root)
        if code != 0:
            return frozenset()
        return frozenset(part for part in out.split("\0") if part)

    @cached_property
    def tracked_dirs(self) -> frozenset[str]:
        """Every directory that contains a tracked file, at any depth."""
        dirs: set[str] = set()
        for path in self.tracked_files:
            parts = path.split("/")[:-1]
            for index in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:index]))
        return frozenset(dirs)

    def tracks(self, path: str) -> bool:
        path = path.strip("/")
        return path in self.tracked_files or path in self.tracked_dirs

    def ignored(self, paths: list[str]) -> frozenset[str]:
        """The subset git would refuse to add, asked once for the whole list.

        `check-ignore` exits 1 when nothing matched, which is an answer and not an error.
        """
        if not self.available or not paths:
            return frozenset()
        code, out, _ = _run(["git", "check-ignore", "--stdin"], self.root, stdin="\n".join(paths))
        if code not in (0, 1):
            return frozenset()
        return frozenset(line.strip().replace("\\", "/") for line in out.splitlines() if line.strip())

    # -- history: the difference between drift and an illustration -------------------

    @cached_property
    def shallow(self) -> bool:
        """A clone with its history cut off cannot answer the question below.

        GitHub Actions checks out at `fetch-depth: 1` by default, which is exactly where
        this tool is meant to run, so this is not an edge case — it is the common one,
        and it has to be reported rather than silently weakening every verdict.
        """
        if not self.available:
            return True
        code, out, _ = _run(["git", "rev-parse", "--is-shallow-repository"], self.root)
        return code != 0 or out.strip() == "true"

    def deleted(self, path: str) -> tuple[str, str, str] | None:
        """The commit that removed this path, if this repository ever had it.

        **This is the whole difference between drift and an illustration.** Across twenty
        well-known public repositories, every path this tool wanted to call broken fell
        into one of two groups, and history told them apart perfectly:

        * `src/hello/__init__.py` in click's docs, `tests/test_factory.py` in flask's
          tutorial — the reader is told to create these in *their* project. They have
          never existed here, and calling them broken is arguing with a tutorial.
        * `src/black_primer/cli.py` in black's docs — deleted in `a57ab32`,
          *"Farewell black-primer, it was nice knowing you"*. The repository had it and
          removed it, and the documentation still says the word.

        So a claim is only contradicted when the project can be shown to have had the
        thing and dropped it, and the commit that dropped it is the receipt.
        """
        if not self.available or self.shallow:
            return None
        # **This branch's history, not `--all`.** A repository's other branches are not all
        # code: `gh-pages` holds a generated documentation site, and every rebuild deletes
        # and rewrites it. isort and mkdocs were each reported for a file removed by a
        # commit titled "Deployed with MkDocs version: 1.2.3" — a delete on a build-artefact
        # branch, presented as drift on main. The documents being checked are the ones on
        # this branch, so this branch's history is the relevant one.
        code, out, _ = _run(
            [
                "git",
                "log",
                "--diff-filter=D",
                "--max-count=1",
                "--format=%h\t%ad\t%s",
                "--date=short",
                "HEAD",
                "--",
                path,
            ],
            self.root,
        )
        if code != 0 or not out.strip():
            return None
        head, _, _ = out.strip().partition("\n")
        parts = head.split("\t")
        if len(parts) < 3:
            return None
        return parts[0], parts[1], parts[2]

    def ever_existed(self, path: str) -> bool:
        if not self.available or self.shallow:
            return False
        code, out, _ = _run(["git", "log", "--max-count=1", "--format=%h", "HEAD", "--", path], self.root)
        return code == 0 and bool(out.strip())
