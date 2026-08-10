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

# `owner/repo` as it appears in a badge, a link or a clone URL. black's docs mention
# `tqdm/tqdm`; that is a GitHub slug, not a directory called tqdm inside tqdm.
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
        if URLISH.search(line):
            continue
        for raw in re.split(r"[\s,;:'\"()\[\]]+", line):
            token = raw.strip().rstrip(".,;:")
            # Tree-drawing characters, comment markers and prompts.
            token = token.lstrip("│├└─#$>+*")
            if token:
                yield token


class DocumentedPaths(Verifier):
    name = "paths"
    describes = "files and directories the documentation points at"

    def check(self, project: Project, documents: Iterable[Document]) -> Iterator[Finding]:
        seen: set[tuple[str, str]] = set()
        git = Git(root=project.root)
        for document in documents:
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
                        yield self._judge(
                            project,
                            Claim(
                                kind="tree-path",
                                subject=entry.path,
                                doc=document.path,
                                line=entry.line,
                                span=entry.name,
                            ),
                            git,
                        )
                    continue

                if document.silenced(span.line):
                    continue
                for token in candidates(span):
                    if not looks_like_a_repo_path(token):
                        continue
                    key = (project.relative(document.path), token)
                    if key in seen:
                        continue
                    seen.add(key)
                    claim = Claim(
                        kind="path",
                        subject=token,
                        doc=document.path,
                        line=span.line,
                        span=span.text if not span.fenced else token,
                    )
                    yield self._judge(project, claim, git)

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
        return self.broken(
            claim,
            f'deleted in {commit} ({date}, "{subject_line[:60]}") and never restored, '
            f"and the documentation still points at it",
        )
