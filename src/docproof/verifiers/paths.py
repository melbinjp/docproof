"""Documented paths that are not there any more.

The cheapest kind of documentation drift and one of the most common: a file moves, and
four documents keep pointing at where it used to be. It is also the kind a reader hits
first, because a path in a README is usually an instruction to go and look.

**The soundness rule, which is the whole design.** A path is only called broken when the
repository can be shown to have *had* it and deleted it, and the deleting commit is the
receipt. Everything else is a skip with a reason.

That rule was arrived at twice, and both times by running the thing rather than reasoning
about it. Two versions of this file have been wrong:

1. **"Does this path exist on disk."** Every finding it produced on real repositories was
   a false positive — `build/outputs/`, `.venv/bin/activate`, a runtime database. All
   three documents were correct; existence was the wrong question.
2. **"Is it absent under a tracked directory."** Better, and still wrong for a reason
   twenty public Python projects made obvious: `src/`, `tests/` and `docs/` exist in
   almost every repository, so a tracked ancestor is nearly no evidence at all. That
   version produced **187 findings across twenty repos and every single one was wrong** —
   click telling readers to create `src/hello/__init__.py` in *their* project, flask's
   tutorial having them write `tests/test_factory.py`, fastapi's release notes correctly
   describing a directory that moved four versions ago.

History separates them perfectly. An illustration has never existed here; a file that
moved has a commit that moved it. The cost, taken deliberately: a path *promised and never
written* is no longer reported. It is a skip, it is visible under `--show-skips`, and it is
a better trade than 187 wrong findings.

Every rule below has a test named after the repository that produced it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import PurePosixPath

from .. import tree
from ..docs import Span, spans
from ..model import Claim, Finding
from ..project import Project
from ..vcs import Git
from .base import Document, Verifier

# Anything that reads as "a place in this repository". Deliberately conservative: one
# slash at minimum, or a filename with a suffix that a project would own.
PATHISH = re.compile(r"^[\w.\-/]+$")

# Where a project keeps code that installs to the top level. A path found under one
# of these has moved, not disappeared.
SOURCE_ROOTS = ("src", "lib", "python")

OWNED_SUFFIXES = frozenset(
    {
        ".py",
        ".md",
        ".toml",
        ".cfg",
        ".ini",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".lock",
        ".rst",
        ".sh",
        ".ps1",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".html",
        ".css",
        ".sql",
        ".Dockerfile",
        ".dockerfile",
        ".env",
    }
)

# Stand-ins a reader is expected to substitute. Matching one is not drift.
PLACEHOLDERS = re.compile(
    r"(?i)(^|/)(path/to|your|my|some|example|foo|bar|baz|\.\.\.|<[^>]*>|\{[^}]*\})(/|$)"
)

# `application/json` has a slash and no other tell. Requests' README mentions it twice and
# it was read as a directory. Narrow on purpose: only the IANA top-level type names, only
# when the whole token is two parts, and only when the second part carries no extension.
MIME_TYPES = frozenset(
    {
        "application",
        "text",
        "image",
        "audio",
        "video",
        "multipart",
        "font",
        "model",
        "message",
        "example",
        "chemical",
    }
)


def looks_like_a_media_type(text: str) -> bool:
    parts = text.split("/")
    return len(parts) == 2 and parts[0].lower() in MIME_TYPES and "." not in parts[1]


def looks_like_a_repo_path(text: str) -> bool:
    text = text.strip()
    if not text or " " in text or "\n" in text:
        return False
    if "://" in text or text.startswith(("/", "~", "-", "@")):
        return False
    if any(character in text for character in "*?<>${}|"):
        return False
    if PLACEHOLDERS.search(text):
        return False
    if looks_like_a_media_type(text):
        return False
    if not PATHISH.match(text):
        return False
    if text in {".", "..", "./", "../"}:
        return False
    stem = text.rstrip("/")
    if "/" in stem:
        return True
    # A bare filename only counts when its suffix is one a project owns, so that `json`
    # or `utf-8` in backticks are not read as missing files.
    dot = stem.rfind(".")
    return dot > 0 and stem[dot:] in OWNED_SUFFIXES


# A transcript: a prompt, then whatever the program printed. `>>> ` is the Python one and
# it matters as much as `$ ` — requests' quickstart shows a traceback whose frames name
# `requests/models.py`, a file that really did move to `src/` in 2023. The traceback is
# what the program printed, not a claim about where the file lives, and without `>>>` in
# this pattern the block was not a transcript and every line of it read as a command.
PROMPT = re.compile(r"^\s*(?:[$#]\s+\S|>>>\s|\.\.\.\s|>\s+\S)")

# Shell verbs that CREATE their path operands. A path a transcript tells the reader to
# make is not a claim that it exists in the documented project. Restricted to touch and
# mkdir, whose every operand is created; `cp`/`mv` are left out because their source can
# be a path that must already exist.
CREATES = re.compile(r"^(?:sudo\s+)?(?:touch|mkdir)\b")

# The same instruction as `CREATES`, written in prose instead of a shell transcript.
#
# `CREATES` catches `$ touch tests/__init__.py`. It does not catch hypothesis's
# `CONTRIBUTING.rst:12`, *"2. Create ``hypothesis/RELEASE.rst`` with ``RELEASE_TYPE: patch``"*
# — a changelog fragment every contributor creates and every release consumes, deleted in
# `6384deef4` ("Bump hypothesis version to 6.165.10"). The deletion is the file's lifecycle,
# and the sentence is an instruction to the reader, not a claim about this repository. pipx
# (`changelog.d/1234.bugfix.md`) and twine (`changelog/5678.feature.rst`) document the same
# towncrier workflow and would have gone the same way.
#
# **`create` and nothing else, because that is what the corpus supports.** Measured over the
# hundred repositories by `mind/work/docproof-sweep/measure_create.py`: 283 candidate sites
# across seven creation verbs, of which
#
#     58   create   every one an instruction to the reader. No exceptions.
#    188   add      almost entirely changelog prose — "Add `meta.total` to the search
#                   endpoint" — about API parameters, not files
#     28   make     changelog prose again: "Make `click.progressbar` work with `codecs.open`"
#      5   write    mixed, and the mix is the disqualifier: "Write a `sitecustomize.py`"
#                   creates, "doesn't write `Pipfile.lock`" describes what the code does
#      4   put      mixed the same way: "put the `requirements.txt` file" against
#                   "put `uvicorn.run` into an `if __name__` clause"
#
# A verb whose hits are mixed cannot be used, because the wrong half silences real drift.
CREATES_IN_PROSE = re.compile(
    r"(?i)\bcreate\s+(?:a\s+|an\s+|the\s+|new\s+|your\s+|this\s+)*"
    r"[`'\"]{1,2}([\w.\-/]+)[`'\"]{1,2}"
)

# A path that names the revision it lives in, which is a claim about THAT revision.
#
# `sharkdp/bat`'s README shows how to read an old file with highlighting:
#
#     git show v0.6.0:src/main.rs | bat -l rs
#
# `src/main.rs` moved into `src/bin/` in 2019, so it is absent at HEAD and the command is
# still exactly correct — it reads from tag `v0.6.0`, where the file is. The revision is
# stated in the same breath as the path.
#
# The pairing is destroyed one line below, by `:` being in the split class: `v0.6.0:src/main.rs`
# arrives as two tokens and the second is judged against HEAD with nothing left to say where
# it came from. So the pairs are read off the raw line first, before anything splits it.
#
# Measured across all 116 cloned repositories: **five occurrences, and they are the same
# sentence in bat's README translated into five languages.** Every other `x:y` pair on a
# `git` line in the whole corpus is an SSH clone URL (`git@github.com:owner/repo.git`),
# which `URLISH` already drops. A tiny class, but a false positive is a false positive, and
# this one would have gone to a 50k-star repository.
REV_QUALIFIED = re.compile(r"(?<![\w:/.@-])[\w.\-]+:([\w.\-/]+)(?![\w:])")

# Named rather than inlined, because the inline version of this was written through a shell
# heredoc and arrived in the file as `r"\x08git\x08"` — `\b` collapsed into a literal
# BACKSPACE byte instead of a word boundary. The guard could never match, `qualified` stayed
# empty, and the rule above was inert. Every reading of the file looked correct, `grep`
# printed the backspace as nothing, and the suite passed, because a silently-disabled rule
# breaks no test. It was found only by printing `repr()` of the compiled source.
#
# That is the fourth instrument this week that reported success while unable to see, and the
# third time a heredoc has eaten a backslash. Regexes are defined at module level here where
# they can be read and tested, and edits to them do not go through a heredoc.
GIT_COMMAND = re.compile(r"\bgit\b")

# A markdown REFERENCE LINK label, which is a link and not a path.
#
# `kubernetes/test-infra`'s README:
#
#     - [Deck](https://prow.k8s.io) shows what jobs are running ([`prow/cmd/deck`])
#     ...thirty lines later...
#     [`prow/cmd/deck`]: https://github.com/kubernetes-sigs/prow/tree/main/cmd/deck
#
# Prow's source moved to another repository in 2024 and this README documents that move
# correctly — the label points at the new home. `URLISH` cannot catch it, because the line
# where the label is USED contains no URL; the URL is in a definition far below. Without
# this, the finding is a wrong pull request to kubernetes/test-infra.
#
# The document defines the label itself, so there is nothing to infer. Measured across the
# 134 cloned repositories: 15 documents, 10 path-shaped labels resolving to a URL and 24
# resolving inside the repo (mostly the `[//]: #` comment idiom). A small class, and the one
# it would have cost was expensive.
#
# The first version of this skipped the label only where it was USED, on the reasoning that
# the definition line's target should still be judged. The findings moved from README.md:33
# to README.md:65 — the definition lines — because what gets extracted there is the LABEL
# again, not the target. A link target is bare text rather than backticked, so it was never
# an inline span and was never being judged in the first place. The reasoning described
# behaviour the tool does not have, and the fix is to skip the label wherever it appears.
#
# Judging reference-link targets that point inside the repo is a real feature and would find
# broken internal links. It is not this, and pretending otherwise in a comment is how a file
# ends up describing a tool nobody wrote.
REF_DEFINITION = re.compile(r"(?m)^\[`?([^\]`]+)`?\]:\s*\S+")
URLISH = re.compile(r"(https?://|github\.com|gitlab\.com|\bgit@|\.git\b|\]\(|\bpip install\b)")


def command_span(span: Span) -> bool:
    """Whether a fenced block is a transcript whose non-prompt lines are output."""
    return (
        span.info.lower()
        in {"console", "shell-session", "shellsession", "session", "term", "terminal", "pycon"}
        or PROMPT.search(span.text) is not None
    )


def candidates(span: Span) -> Iterator[str]:
    """Path-shaped tokens in a span.

    Inline spans are taken whole. Fenced blocks are split on whitespace, because a
    directory tree or a command line carries several paths and each is its own claim.

    **Program output is not a claim.** black's docs show `black src/ -q` printing
    `error: cannot parse: src/black_primer/cli.py`. That module really was deleted, but
    the sentence is an example of an error message, not an assertion that the file is
    there — so in a transcript only the lines with a prompt are read.
    """
    if not span.fenced:
        text = span.text.strip()
        if not URLISH.search(text):
            yield text
        return

    transcript = command_span(span)
    for line in span.text.split("\n"):
        if transcript and not PROMPT.match(line):
            continue
        if transcript and CREATES.match(re.sub(r"^\s*[$>]\s*", "", line)):
            # `touch`/`mkdir` operands are paths the reader is told to CREATE in their
            # own project, not claims that they exist in this one. falcon's tutorial
            # says `$ touch tests/__init__.py`; falcon deleted its own
            # tests/__init__.py in 2019, so without this the reader's instruction is
            # read as the project's drift. Narrow to these two verbs on purpose — a
            # `cp`/`mv` source can be a path that must already exist, so it is left
            # judged. Measured over 53 repos: 7 such operands, every one a
            # reader-project path, one of them a live false positive.
            continue
        if URLISH.search(line):
            continue
        # Read off the raw line, because the split below eats the colon that carries the
        # meaning. Only on a git line: elsewhere `x:y` is a mapping key, a port, a label.
        qualified = set()
        if GIT_COMMAND.search(line):
            qualified = {m.group(1) for m in REV_QUALIFIED.finditer(line)}
        for raw in re.split(r"[\s,;:'\"()\[\]]+", line):
            token = raw.strip().rstrip(".,;:")
            # Tree-drawing characters, comment markers and prompts.
            token = token.lstrip("│├└─#$>+*")
            if token and token not in qualified:
                yield token


class DocumentedPaths(Verifier):
    name = "paths"
    describes = "files and directories the documentation points at"

    def check(self, project: Project, documents: Iterable[Document]) -> Iterator[Finding]:
        git = Git(root=project.root)
        for item in self.extract(project, documents):
            yield item if isinstance(item, Finding) else self._judge(project, item, git)

    def extract(self, project: Project, documents: Iterable[Document]) -> Iterator[Finding | Claim]:
        """Every path claim the documents make, before any judging.

        Yields `Claim`s ready for `_judge`, plus the occasional skip `Finding` where the
        text announced a claim and then withheld it — an ambiguous diagram, a leaf drawn
        above its own root. Those count as the document *making* claims, which is why
        they are yielded rather than dropped: extraction alone is what `history` replays
        over old snapshots to ask whether silence today is new, and a document that has
        always been all ambiguous diagrams has always been loud.
        """
        seen: set[tuple[str, str]] = set()
        for document in documents:
            lines = document.text.split("\n")
            ref_labels = {m.group(1).strip() for m in REF_DEFINITION.finditer(document.text)}
            for span in spans(document.text):
                # A directory diagram is read as a diagram: its leaves are only
                # meaningful once indentation has been turned back into a full path.
                if span.fenced and tree.looks_like_a_tree(span.text):
                    drawn = tree.parse(span.text, span.line)
                    if not drawn:
                        yield self.skip(
                            Claim(
                                kind="tree",
                                subject="(directory diagram)",
                                doc=document.path,
                                line=span.line,
                                span=span.text[:200],
                            ),
                            "this looks like a directory diagram but its indentation is "
                            "ambiguous, so no path was read out of it rather than guessing",
                        )
                        continue
                    for entry in drawn:
                        if document.silenced(entry.line):
                            continue
                        if entry.above_root:
                            yield self.skip(
                                Claim(
                                    kind="tree-path",
                                    subject=entry.name,
                                    doc=document.path,
                                    line=entry.line,
                                    span=entry.name,
                                ),
                                "this sits under a `..` in the diagram, so it is drawn "
                                "relative to somewhere above the diagram's own root and "
                                "there is nothing to say where that is",
                            )
                            continue
                        key = (project.relative(document.path), entry.path)
                        if key in seen:
                            continue
                        seen.add(key)
                        yield Claim(
                            kind="tree-path",
                            subject=entry.path,
                            doc=document.path,
                            line=entry.line,
                            span=entry.name,
                        )
                    continue

                if document.silenced(span.line):
                    continue
                # An inline span is the backticked token alone, so `span.text` was the path
                # repeated — no surrounding text at all, though `Claim.span` is documented as
                # "the surrounding text it was read out of". That cost a rule: whether the
                # sentence says CREATE cannot be asked of a string that is only the path.
                # Fenced blocks keep the token, because there the line is a whole command.
                source_line = lines[span.line - 1] if 0 < span.line <= len(lines) else span.text
                for token in candidates(span):
                    if not looks_like_a_repo_path(token):
                        continue
                    # The document defines this as a reference-link label, so it is a link
                    # and the definition says where it goes.
                    if token in ref_labels:
                        continue
                    key = (project.relative(document.path), token)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield Claim(
                        kind="path",
                        subject=token,
                        doc=document.path,
                        line=span.line,
                        span=source_line if not span.fenced else token,
                    )

    def _judge(self, project: Project, claim: Claim, git: Git) -> Finding:
        # `lstrip("./")` strips *characters*, not a prefix, so it turned `.poetry/plugins`
        # into `poetry/plugins` — a directory poetry really did delete in its src-layout
        # move, which is how a documented runtime path in the user's own project came back
        # as drift. Strip the one prefix that means "here", and nothing else.
        subject = claim.subject
        while subject.startswith("./"):
            subject = subject[2:]
        subject = subject.rstrip("/")
        if not subject:
            return self.skip(claim, "no path left after normalising")

        target = (project.root / subject).resolve()
        try:
            target.relative_to(project.root.resolve())
        except ValueError:
            return self.skip(claim, "resolves outside the project")

        if git.tracks(subject):
            return self.holds(claim, f"tracked at {subject}")

        if not git.available:
            # Deliberately does not say *why*. It said "this is not a git checkout" until
            # it met a real checkout that git refused to read — Windows reporting dubious
            # ownership, on this tool's own repository. Naming a cause it has not
            # established is the failure this tool exists to catch, in its own output.
            return self.skip(
                claim,
                f"git could not answer for this directory ({git.unavailable_because}), and "
                f"without the index there is no way to tell a path the project ships from "
                f"one it generates",
            )

        if subject in git.ignored([subject]):
            return self.skip(claim, "matched by .gitignore, so it is generated rather than shipped")

        if target.exists():
            return self.skip(claim, f"{subject} is present but untracked, so it is not a shipped path")

        # **Git cannot represent an empty directory, so for a path written as a directory,
        # absence from the index is not evidence of deletion.**
        #
        # `PostHog/posthog-python`'s RELEASING.md says changesets must live in
        # `.sampo/changesets/`, and this called it broken because the last file under it was
        # deleted in `0fc7ec6`. That commit is the release bot CONSUMING a changeset — the
        # normal lifecycle of the directory, on a v7.39.1 release four days before the sweep.
        # The sentence is not a claim that files are there; it says where `sampo add` PUTS
        # them, and it will be right again the next time anyone adds one.
        #
        # The trailing slash is the whole signal, which is why it is read before
        # `rstrip("/")` throws it away. Requiring the parent to be tracked keeps the case
        # this must still catch: a documented directory whose entire tree really did go.
        if any(found.rstrip("/") == subject for found in CREATES_IN_PROSE.findall(claim.span)):
            return self.skip(
                claim,
                f"the sentence tells the reader to CREATE `{subject}`, so it is an "
                f"instruction rather than a claim that this repository has it",
            )

        if claim.subject.rstrip().endswith("/") and git.tracks(str(PurePosixPath(subject).parent)):
            return self.skip(
                claim,
                f"`{subject}` is written as a directory and its parent is tracked. Git "
                f"stores files, not directories, so an empty one is indistinguishable from "
                f"a deleted one and this cannot be called drift",
            )

        # A bare filename is a *name*, not a location, and the two are easy to confuse
        # because a project usually has a file by that name too. Every one of these was
        # reported against a well-known repository before this rule came back:
        #
        #   black    `setup.py`, `setup.cfg`   files black looks for in *your* project,
        #                                      and which black itself dropped in 2022
        #   flask    `flask.py`                "do not call your file this" — advice
        #                                      about the reader's filename, and flask
        #                                      deleted its own in 2010
        #   click    `LICENSE`                 a leaf in a diagram of the reader's app
        #
        # In all three the repository really did delete a file by that name, so history
        # agreed and was still answering the wrong question. A path with a directory in
        # it is anchored somewhere; a bare name is not.
        if "/" not in subject:
            return self.skip(
                claim,
                "a bare filename with no directory to place it: it names a kind of file "
                "rather than a location in this repository",
            )

        # git says this is not part of the project. Whether that is drift or an
        # illustration is a question only history can answer — see `Git.deleted`.
        if git.shallow:
            return self.skip(
                claim,
                "this clone has no history, so there is no way to tell a path the project "
                "deleted from one it never had. Check out with full history "
                "(`fetch-depth: 0` on GitHub Actions) to judge these",
            )

        # **A file that moved under `src/` did not vanish, and the document may be naming
        # the import path rather than the repository path.** pdm's docs say to add
        # `pdm/pep582/sitecustomize.py` to the search path; the repository moved it to
        # `src/pdm/...` in 2022 and the sentence stayed correct, because after installation
        # that *is* where it lives. requests says `requests/models.py` for the same reason.
        for root in SOURCE_ROOTS:
            if git.tracks(f"{root}/{subject}"):
                return self.skip(
                    claim,
                    f"tracked at `{root}/{subject}` — the repository moved it under "
                    f"`{root}/`, and a document naming the import path is still right",
                )

        removal = git.deleted(subject)
        if removal is None:
            return self.skip(
                claim,
                "this repository has never had this path, so it is far more likely to be "
                "an illustration — a file the reader is told to create, or an example — "
                "than something that moved",
            )

        commit, date, subject_line = removal

        # **The receipt proves the event, not the relevance.** The repository really did
        # delete this path — and the sentence may never have been about it. If this line
        # was written after the deletion, its author typed the path knowing no such file
        # was here, which makes it an example rather than a claim that rotted. See
        # `Git.line_written_after` for the three public false positives that forced this.
        if git.claim_introduced_after(project.relative(claim.doc), subject, commit):
            return self.skip(
                claim,
                f"this document first mentioned it after {commit} ({date}) removed that "
                f"path, so whoever wrote it knew the file was not here — an example, not "
                f"a claim this repository stopped honouring",
            )

        return self.broken(
            claim,
            f'deleted in {commit} ({date}, "{subject_line[:60]}") and never restored, '
            f"and the documentation still points at it",
        )
