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


# How far `moved_to` will follow a chain of renames before giving up. Ten is far past
# anything real - the worst case in the corpus is two - and it exists only so a rename cycle
# costs a bounded number of `git show` calls rather than a hang.
_MAX_RENAME_HOPS = 10

# How many same-basename files `succeeded_by` will test for lineage. Five, because the
# candidates are ranked by how much of the original directory chain survives and the
# lineage proof is what accepts one - the cap only bounds the cost on a monorepo with a
# hundred and fifty `index.ts`. The worst real case needed the third.
_MAX_MOVE_CANDIDATES = 5


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

    def _renamed_in(self, path: str, commit: str) -> str | None:
        """One hop: where `commit` put `path`, if git called that deletion a rename."""
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

        **FOLLOWED TO THE END, and it was one hop until 2026-08-18.** A file can be renamed
        more than once, and reporting the first hop names a path that may itself be gone -
        which is the worst thing this function can do, because the whole point of it is to
        save the reader a search and it would be sending them somewhere empty.

        Found on `open-gsd/gsd-core`. `docs/CONFIGURATION.md` cites
        `sdk/shared/model-catalog.json` and the chain is two hops:

            11918dcc  sdk/shared/model-catalog.json      -> get-shit-done/bin/shared/model-catalog.json
            463cffd8  get-shit-done/bin/shared/...json   -> gsd-core/bin/shared/model-catalog.json

        The old answer was the middle one. `get-shit-done/` has **zero** files at HEAD, so
        the advice pointed into a directory that no longer exists anywhere in the tree.

        So the invariant is now the one a reader assumes: **a destination is only named if it
        is there now.** If the chain dead-ends somewhere that is not tracked, this returns
        None and the finding says "deleted ... and never restored", which is true, instead of
        naming a phantom. Bounded, because a rename cycle is cheaper to survive than to prove
        impossible.
        """
        destination = self._renamed_in(path, commit)
        if destination is None:
            return None
        seen = {path, destination}
        for _ in range(_MAX_RENAME_HOPS):
            if self.tracks(destination):
                return destination
            onward = self.deleted(destination)
            if onward is None:
                return None
            following = self._renamed_in(destination, onward[0])
            if following is None or following in seen:
                return None
            seen.add(following)
            destination = following
        return None

    @cached_property
    def _tracked_by_basename(self) -> dict[str, tuple[str, ...]]:
        index: dict[str, list[str]] = {}
        for path in self.tracked_files:
            index.setdefault(path.rsplit("/", 1)[-1], []).append(path)
        return {name: tuple(sorted(paths)) for name, paths in index.items()}

    def split_siblings(self, path: str, commit: str) -> tuple[str, ...]:
        """Same-named files that this commit ADDED alongside `path`.

        A rename that SPLIT one file into two leaves `moved_to` naming whichever destination
        git paired the content with, and that is not always the one the sentence meant.
        `sendgrid/sendgrid-python` split `test/test_sendgrid.py` into `test/unit/` and
        `test/integ/` in one commit; git pairs the content with integ, and the sentence around
        the link asks the reader to add **unit** tests. Naming one destination with no sign a
        choice existed sends them to the wrong file while looking like a correct report.

        **Restricted to what the SAME commit added, which is what makes it a split rather than
        a coincidence.** Every repository has many files called `README.md` and `__init__.py`,
        and a rule keyed on the basename alone would append a caveat to most renames of a
        common name - noise on exactly the findings that are otherwise clearest.
        """
        code, out, _ = _run(
            ["git", "show", "--name-status", "--diff-filter=A", "--format=", commit], self.root
        )
        if code != 0:
            return ()
        name = path.rsplit("/", 1)[-1]
        # TAB via chr(9): git separates status from path with one, and a literal tab
        # byte in source is what the control-byte guard exists to reject.
        sep = chr(9)
        added = (line.split(sep, 1)[1].strip() for line in out.splitlines() if sep in line)
        return tuple(sorted(p for p in added if p != path and p.rsplit("/", 1)[-1] == name))

    def _size_at(self, revision: str, path: str) -> int | None:
        code, out, _ = _run(["git", "cat-file", "-s", f"{revision}:{path}"], self.root)
        if code != 0:
            return None
        try:
            return int(out.strip())
        except ValueError:
            return None

    def succeeded_by(self, path: str, commit: str) -> str | None:
        """Where the content went when the DELETING commit is not the move.

        `moved_to` asks git what the deleting commit renamed, and a very common refactor
        defeats it. A split copies a file to its new home and leaves a one-line re-export
        behind; a later commit sweeps up the re-export. Git records that second commit as
        a plain `D` and is right to - a one-line stub resembles nothing - so the finding
        says "deleted and never restored", which is true of the path and false of the
        content.

        `zhukunpenglinyutong/desktop-cc-gui`, the case that forced this:

            b66a616b3  "Split app-shell.tsx"    C099  app-shell-parts/modelSelection.ts
                                                      -> app-shell/domains/modelSelection.ts
            772b6c681  "Clean up useless code"    D   app-shell-parts/modelSelection.ts  (1 line)

        Its onboarding guide - `status: active`, calibrated to the current release - lists
        that path as a file you must edit to add an engine. The function is at line 112 of
        the new one. Six of that project's eleven findings are this same commit pair.

        THE LINEAGE IS PROVED, NOT GUESSED. The obvious version looks for a file at HEAD
        with the same basename, and that is the rule `BARE-FILENAME-VERDICT.md` rejected
        wearing a different hat. Measured on the 160 corpus findings that say
        "never restored", 25 have a same-basename file at HEAD and no lineage, and reading
        them is enough: `sdk/package.json` -> `package.json`, `pkg/registry/types.go` ->
        `pkg/git/types.go`, `website/content/getting-started.md` ->
        `third-party/vendor/logos-0.14.4/book/src/getting-started.md`. So a candidate is
        only accepted when `log --follow --find-copies` from it names this exact path as an
        ancestor. Basename is how candidates are FOUND; it is never how one is accepted.

        AND THE SOURCE MUST NOT HAVE GROWN AFTER THE COPY. Ten findings had proven lineage
        and one of them was plainly wrong:

            bytebase  docs/adding-new-object-to-sdl-mode.md:492
                      says    backend/plugin/schema/pg/generate_migration.go
                      C077 in 044c898364 "feat: implement oracle generate migration (#16546)"

        Somebody copied the Postgres implementation to start the Oracle one. Nothing moved:
        there are four `generate_migration.go` at HEAD, one per dialect. Taking only `R` and
        dropping `--find-copies` would remove it and would also remove desktop-cc-gui, which
        git records as `C099`. Size at deletion does not separate it either - the true group
        runs from 1 line to 252 and cherry-studio sits at 0.979 of its destination.

        What separates them is what happened to the SOURCE after the copy landed. A file on
        its way out is frozen; it becomes a stub, or sits untouched while callers migrate.
        A forked sibling is developed, because it is now a second thing.

            desktop-cc-gui  x6   1 -> 1 bytes-equivalent, 0 commits    move
            bytebase        directiveUtils.ts   252 -> 252, 0 commits  move
            cherry-studio   useToolApproval.ts  143 -> 143, 0 commits  move
            sentry-rn       build.gradle         42 ->  22, 4 commits  move   (shrank)
            bytebase        generate_migration 1583 -> 5192, 44        FORK   (grew)

        So: refuse the candidate if the source was bigger when it was deleted than when the
        copy landed. Nine of ten survive, and the tenth is the fork.

        HONEST LIMITS. Recall is 9 of 160 findings, 5.6%, and six of the nine are one commit
        pair in one project - this pattern is concentrated, not common, which is also why it
        matters: a project that does one split-with-shims gets every finding mis-explained at
        once. And the growth rule is fitted against a single negative case. It is stated this
        way because a rule chosen from n=1 should say so.

        VALIDATED BY SOMEONE ELSE. `getsentry/sentry-react-native` made this exact edit
        unprompted in `fd677570` (2026-08-18, "docs: update CONTRIBUTING paths for the
        monorepo layout", #6594), replacing `sample/android/build.gradle` with
        `samples/react-native/android/build.gradle` - the destination this computes.

        The verdict never changes. The path really is gone and the document really is stale.
        This only decides whether the reader is told where to look.
        """
        candidates = self._tracked_by_basename.get(path.rsplit("/", 1)[-1], ())
        if not candidates:
            return None
        original = set(path.split("/")[:-1])
        ranked = sorted(
            candidates,
            key=lambda found: (-len(set(found.split("/")[:-1]) & original), len(found)),
        )
        for candidate in ranked[:_MAX_MOVE_CANDIDATES]:
            copied_in = self._copied_from(candidate, path)
            if copied_in is None:
                continue
            when_copied = self._size_at(copied_in, path)
            when_deleted = self._size_at(f"{commit}^", path)
            if when_copied is None or when_deleted is None:
                continue
            if when_deleted > when_copied:
                continue
            return candidate
        return None

    def _copied_from(self, destination: str, source: str) -> str | None:
        """The commit where `source` became `destination`, as git tells it.

        Asked from the destination, because that is the direction that answers. A pathspec
        on the deleted path finds nothing - it is the source of the copy, not a file the
        commit changed - and the query returns empty. Tested before this was written.
        """
        code, out, _ = _run(
            [
                "git",
                "log",
                "--follow",
                "--find-copies",
                "--diff-filter=CR",
                "--name-status",
                "--format=commit %h",
                "--",
                destination,
            ],
            self.root,
        )
        if code != 0:
            return None
        commit: str | None = None
        for line in out.splitlines():
            if line.startswith("commit "):
                commit = line[len("commit ") :].strip()
                continue
            parts = line.split("\t")
            if len(parts) == 3 and parts[0][:1] in {"R", "C"} and parts[1] == source:
                return commit
        return None

    def emptied_and_stayed(self, directory: str) -> str | None:
        """The commit that took the last file out of a directory, if it never refilled.

        **A guard whose stated intent and behaviour disagreed.** `paths.py` skips a claim
        written with a trailing slash when the directory's parent is tracked, because git
        cannot represent an empty directory - `PostHog/posthog-python`'s RELEASING.md says
        changesets live in `.sampo/changesets/`, that directory is emptied by every release
        as the bot consumes them, and reporting it argues with a lifecycle. Right.

        Its comment then claims the tracked-parent requirement "keeps the case this must
        still catch: a documented directory whose entire tree really did go". It keeps none
        of them, because a wholly removed subdirectory of a live tree has a tracked parent
        too. `stacklok/toolhive` documents `pkg/container/verifier/` for Sigstore
        verification; `pkg/container` is alive and `verifier` went in `7095e8e1`
        *"Remove /verifier in favour of one coming from toolhive-core"*.

        **Measured across the 47 clones of sweep batches 10 and 11**, every `--show-skips`
        run captured to disk: the guard silences **38 directory claims, of which 31 were
        never tracked at all** - promises, or places the reader creates, and the guard is
        right about every one - **and 7 were populated and wholly emptied**, in four
        repositories. None of the 38 is the churning case in this corpus, which is the shape
        the guard was written for and which `composio/.changeset` confirms is real.

        So the skip keeps its reason and gains a receipt, which is the soundness rule the
        rest of this verifier already runs on: a path is only called broken when the
        repository can be shown to have HAD it and dropped it.

        THE REPLAY RUNS FORWARDS, and the first version of the measurement did not. Walking
        newest-first and calling it a refill on the first add after a delete marks every
        directory that was created before it was deleted, which is all of them; that run
        reported zero emptied directories and put toolhive's verifier in the churn column.
        Nothing about the output looked wrong. So: replay oldest-first, count how many times
        the live set falls to empty, and only once means it stayed empty.
        """
        code, out, _ = _run(
            [
                "git",
                "log",
                "--reverse",
                "-M",
                "--name-status",
                "--format=commit %h",
                "--",
                directory,
            ],
            self.root,
        )
        if code != 0 or not out.strip():
            return None

        wanted = directory.strip("/")
        prefix = wanted + "/"

        def inside(path: str) -> bool:
            return path == wanted or path.startswith(prefix)

        live: set[str] = set()
        commit: str | None = None
        emptyings: list[str] = []
        refilled = False
        for line in out.splitlines():
            if line.startswith("commit "):
                commit = line[len("commit ") :].strip()
                continue
            parts = line.split("\t")
            if len(parts) < 2 or commit is None:
                continue
            was_empty = not live
            status = parts[0][:1]
            if status == "D":
                live.discard(parts[1])
            elif status in {"R", "C"} and len(parts) == 3:
                if inside(parts[1]):
                    live.discard(parts[1])
                if inside(parts[2]):
                    live.add(parts[2])
            elif inside(parts[1]):
                live.add(parts[1])
            if live and was_empty and emptyings:
                refilled = True
            elif not live and not was_empty:
                emptyings.append(commit)

        if refilled or not emptyings:
            return None
        return emptyings[-1]

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
