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

    def moved_to(self, path: str, commit: str) -> str | None:
        """Where the deleting commit PUT it, when git calls the deletion a rename.

        **A finding that says only "deleted" makes the reader go and look.** `melbinjp/3000`
        archived a whole cluster in one commit, `b43e0ec` *"archive dead AutoForge cluster to
        history/"*, and its onboarding guide - a document that opens "Read this FIRST" - still
        names `autoforge/main.py` as the entry point. That is real drift and the verdict does
        not change. But the file is sitting at `history/autoforge/main.py`, git recorded the
        move, and the tool knew and did not say.

        Measured on the 134-repository corpus: **23 of 89 findings were deleted by a commit
        git calls a rename**, so about a quarter of everything reported can name the
        replacement instead of leaving it as an exercise.

        This changes no verdict. It is the difference between a finding a reader has to
        investigate and one they can act on.
        """
        if not self.available or self.shallow:
            return None
        code, out, _ = _run(["git", "show", "-M", "--name-status", "--format=", commit], self.root)
        if code != 0:
            return None
        for line in out.split("\n"):
            parts = line.split("\t")
            # `R100\told\tnew`. The similarity score rides on the status, so `startswith`.
            if len(parts) == 3 and parts[0].startswith("R") and parts[1] == path:
                return parts[2]
        return None

    def claim_introduced_after(self, doc: str, subject: str, commit: str) -> bool | None:
        """Whether this document first mentioned `subject` *after* `commit` removed it.

        **A receipt proves the event, not the relevance.** `deleted` establishes that the
        repository once had a path and dropped it, and that fact is correctly computed —
        but it says nothing about whether *this sentence* was ever about that file. Three
        false positives found on 2026-08-15, checked against current upstream before they
        became pull requests:

        * pypa/build   `.github/workflows/build.yml`  captioning an example workflow the
                                                      reader is told to create
        * pytest       `testing/__init__.py`          a directory tree illustrating
                                                      `--import-mode=append`
        * tox          `tests/integration`            a sample tox config

        Each names a path this repository really did delete — in 2020, 2010 and 2020 — so
        history agreed, produced a dated commit, and made the wrong answer look rigorous.

        The discriminator is authorship order: a document cannot have stopped being true
        about a file that was already gone when the sentence was first written. Whoever
        wrote it typed the path knowing no such file was here, which makes it an example.

        **Ask when the document first said it, not when the line was last touched.** The
        obvious implementation is `git blame` on the claim's line, and it is wrong — it
        dates the last edit, and cosmetic edits re-date claims that are years old. It was
        tried first and it broke the one true positive in this very set: click's line was
        rewrapped on 2026-04-10, a week *after* the 2026-04-03 commit that deleted the
        workflow, so blame called a real finding an example. The pickaxe (`log -S`) dates
        the first commit that put this string into this document, which is the question
        actually being asked. On the four cases:

            repo    claim first written   file deleted    verdict
            build   2026-03-06            2020-06-30      example
            pytest  2021-03-12            2010-06-04      example
            tox     2026-02-18            2020-10-27      example
            click   2026-03-02            2026-04-03      REAL — pallets/click#3766

        **Author dates, not ancestry.** Topological order looks like the rigorous choice
        and answers a different question: it measures when the sentence *landed on this
        branch*, not when its author wrote it. click's line was authored on 2026-03-02,
        while the workflow still existed, and merged after the 2026-04-03 deletion — so
        `merge-base --is-ancestor` reports the claim as newer than the removal and calls a
        real finding an example. Every long-lived project merges work written weeks
        earlier, so this is the common case, not a corner. What the rule needs to know is
        what the author could see, and that is the author date.

        `None` means unanswerable — no history, or a document whose mention does not
        appear in this branch's record at all — and the caller keeps the verdict it
        already had rather than acquiring a pass it did not earn.
        """
        if not self.available or self.shallow:
            return None
        code, out, _ = _run(
            ["git", "log", "--reverse", "--format=%at", f"-S{subject}", "HEAD", "--", doc],
            self.root,
        )
        if code != 0 or not out.strip():
            return None
        try:
            introduced = int(out.strip().splitlines()[0])
        except ValueError:
            return None
        code, out, _ = _run(["git", "show", "-s", "--format=%at", commit], self.root)
        if code != 0 or not out.strip():
            return None
        try:
            removed = int(out.strip().splitlines()[0])
        except ValueError:
            return None
        return introduced > removed

    def ever_existed(self, path: str) -> bool:
        if not self.available or self.shallow:
            return False
        code, out, _ = _run(["git", "log", "--max-count=1", "--format=%h", "HEAD", "--", path], self.root)
        return code == 0 and bool(out.strip())
