"""What a verifier's silence means here, answered from this branch's history.

`Outcome.silent` names the failure mode this tool is prone to: a verifier that applies
and produced nothing at all. Failing the run on that alone was measured against 53 public
repositories and fired five times, once rightly. httpx documents its CLI as a screenshot
and always has; twine's `--repository-url` walked out of its README in 2019 along with
the workflow it described. Healthy projects are silent for reasons of their own, and an
alarm that fires on healthy projects gets switched off — after which it is not catching
the thing it was switched on for.

History tells the cases apart, the same way it tells drift from illustration in
`verifiers.paths`: extraction — extraction alone, none of the judging — is re-run over
sampled historical snapshots of the documentation, and today's silence is read against
what those snapshots said. The four answers, and the one real alarm among them, are
documented on `model.Silence`.

The tree-mismatch check runs first and is nearly free: one extraction pass over the
documents *as HEAD records them*. If that is loud while the working tree was silent, no
amount of history reading matters — the checkout itself is broken, and the first time
this check ran it found a real one (a tracked filename NTFS refuses, so the clone had
been half-empty since clone day and every run against it was judging air).

Sampling is honest about being sampling: HEAD, the root, exponential spacing back from
HEAD, and twenty evenly spaced points. A claim that lived only between samples is missed.
That is good enough for the question actually being asked — "is silence this project's
steady state?" — which no single missed commit can flip.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

from .config import Config, declares_removed, is_historical, opts_out, suppressed_lines
from .docs import DOC_SUFFIXES, SKIP_DIRS
from .model import Claim, Finding, Silence, SilenceVerdict
from .project import Project
from .vcs import Git
from .verifiers.base import Document, Verifier
from .verifiers.cli_flags import DocumentedFlags

# History reads are batch work over every sampled commit, not one lookup, so they get
# longer than `vcs.TIMEOUT`. Any overrun surfaces as UNKNOWN with the error as receipt.
TIMEOUT = 120


class GitReadError(RuntimeError):
    """git could not be read. Callers turn this into UNKNOWN, never into a guess."""


def _run(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    """One git call, bytes in and bytes out.

    Deliberately not `vcs._run`: that one is text-mode, and `cat-file --batch` headers
    give sizes in *bytes*, so slicing its output demands the raw stream.
    """
    try:
        finished = subprocess.run(
            ["git", *args], cwd=root, input=stdin, capture_output=True, timeout=TIMEOUT
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise GitReadError(f"{type(error).__name__}: {error}") from error
    if finished.returncode != 0:
        message = (finished.stderr or b"").decode("utf-8", "replace").strip()
        raise GitReadError(message.splitlines()[0][:200] if message else f"git {args[0]} failed")
    return finished.stdout


def sample_indices(total: int) -> list[int]:
    """Which of `total` commits (0 = newest) to look at: ends, exponential, and evenly.

    Exponential from HEAD because documentation drift clusters near the present; twenty
    even points so a long-lived era cannot hide between the powers of two; both ends
    always, because "ever" and "still" are the two words the classification turns on.
    """
    indices = {0, total - 1}
    step = 1
    while step < total:
        indices.add(step)
        step *= 2
    for k in range(1, 20):
        indices.add(k * total // 20)
    return sorted(i for i in indices if 0 <= i < total)


def doc_paths_at(root: Path, commit: str, config: Config) -> list[str]:
    """`docs.find_docs`, restated over a historical tree listing.

    Kept in step with `find_docs` by eye rather than by sharing code, because that one
    walks a filesystem and this one reads `ls-tree` — the same rule (top-level files
    plus `docs`/`doc`, documentation suffixes, skip vendored directories) expressed over
    names instead of paths. The `[tool.docproof] docs` extras are honoured with fnmatch,
    which is a superset of pathlib's glob (`*` crosses `/`); for the patterns people
    actually write, a historical doc admitted slightly early beats one silently ignored.
    """
    raw = _run(root, "ls-tree", "-r", "-z", "--name-only", commit)
    names = [chunk.decode("utf-8", "replace") for chunk in raw.split(b"\0") if chunk]
    kept: set[str] = set()
    for name in names:
        parts = name.split("/")
        suffixed = name.lower().endswith(DOC_SUFFIXES)
        top_level = len(parts) == 1
        under_docs = parts[0] in ("docs", "doc") and not (SKIP_DIRS & set(parts))
        extra = any(fnmatch.fnmatch(name, pattern) for pattern in config.docs)
        if (suffixed and (top_level or under_docs)) or extra:
            kept.add(name)
    return sorted(kept)


def blobs_at(root: Path, commit: str, paths: list[str]) -> dict[str, str]:
    """The named blobs as they were at `commit`, in one `cat-file --batch` call.

    Missing entries are dropped rather than raised: a path listed at one commit and
    asked about at another is an ordinary consequence of sampling, not an error.
    """
    if not paths:
        return {}
    stdin = "".join(f"{commit}:{path}\n" for path in paths).encode("utf-8")
    data = _run(root, "cat-file", "--batch", stdin=stdin)

    texts: dict[str, str] = {}
    position = 0
    try:
        for path in paths:
            newline = data.index(b"\n", position)
            header = data[position:newline].decode("utf-8", "replace")
            position = newline + 1
            if header.endswith((" missing", " ambiguous")):
                continue
            size = int(header.rsplit(" ", 1)[-1])
            body = data[position : position + size]
            position += size + 1  # the LF cat-file appends after every object
            texts[path] = body.decode("utf-8", "replace").replace("\r\n", "\n")
    except (ValueError, IndexError) as error:
        raise GitReadError(f"could not parse cat-file output: {error}") from error
    return texts


def documents_from(root: Path, texts: dict[str, str], config: Config) -> list[Document]:
    """Historical texts filtered exactly as `cli.main` filters the live ones.

    The same excludes, the same historical-name rule, the same tombstone and opt-out
    markers — because the question is "would the run have seen claims", and the run
    never sees a changelog.
    """
    documents: list[Document] = []
    for relative, text in sorted(texts.items()):
        if config.excludes(relative) or is_historical(relative):
            continue
        if declares_removed(text) or opts_out(text):
            continue
        documents.append(
            Document(path=root / relative, text=text, suppressed=suppressed_lines(text))
        )
    return documents


def scripts_at(root: Path, commit: str) -> tuple[set[str], str | None]:
    """The console scripts and project name pyproject declared at `commit`.

    Any failure — no pyproject yet, unparseable TOML, a setup.py era — degrades to
    "no extra names", never to an error: the union with today's names still stands.
    """
    try:
        blob = blobs_at(root, commit, ["pyproject.toml"]).get("pyproject.toml")
        if blob is None:
            return set(), None
        table = tomllib.loads(blob).get("project", {})
        return set(table.get("scripts", {})), table.get("name")
    except Exception:
        return set(), None


def _extract(
    verifier: Verifier,
    project: Project,
    documents: list[Document],
    commands: set[str] | None = None,
    package: str | None = None,
) -> list[Claim]:
    """Everything extraction produced — a skip `Finding` counts, because a document that
    earned even an explained abstention was making claims."""
    if isinstance(verifier, DocumentedFlags):
        items = verifier.extract(project, documents, commands=commands, package=package)
    else:
        items = verifier.extract(project, documents)  # type: ignore[attr-defined]
    return [item.claim if isinstance(item, Finding) else item for item in items]


def vanished_documents(project: Project, config: Config) -> str | None:
    """Whether "no documentation found" is itself a broken checkout, with the receipt.

    The whole-tree case of TREE_MISMATCH: the first broken clone this tool ever found
    had no documents on disk at all — the checkout had failed on clone day and the run
    that mattered never got past "nothing to prove". So an empty run asks HEAD the same
    question a silent verifier asks it: if HEAD records documents the configuration
    would have admitted and the disk yields none, the checkout is broken, not the docs
    absent. Anything git cannot answer degrades to None — the plain "nothing to prove"
    exit — because a directory that was never a repository is the ordinary case here.
    """
    git = Git(root=project.root)
    if not git.available:
        return None
    try:
        recorded = documents_from(
            project.root,
            blobs_at(project.root, "HEAD", doc_paths_at(project.root, "HEAD", config)),
            config,
        )
    except GitReadError:
        return None
    if not recorded:
        return None
    example = project.relative(recorded[0].path)
    return (
        f"No documentation on disk, but HEAD records {len(recorded)} document(s) — "
        f"e.g. `{example}`. The checkout does not match the repository: look for a "
        f"failed checkout, or a sparse or filtered clone."
    )


def classify(
    project: Project, config: Config, verifier: Verifier, documents: list[Document]
) -> SilenceVerdict:
    """What this verifier's silence means, with the receipt.

    `documents` are the live documents the run actually checked — already filtered for
    excludes, historical names and tombstones — because "does the text survive today"
    has to be asked of what a reader can still reach. twine's `--repository-url` does
    survive in its changelog, and a changelog is the past, labelled as the past.
    """
    if not hasattr(verifier, "extract"):
        # Extraction and judging are still one piece in this verifier, so its silence
        # cannot be replayed. Keep the old blanket alarm rather than inventing a pass.
        return SilenceVerdict(
            kind=Silence.UNKNOWN,
            alarming=True,
            detail=(
                f"the {verifier.name} check cannot yet re-run its extraction over "
                f"history, so its silence stays what it always was: worth a look"
            ),
        )

    git = Git(root=project.root)
    if not git.available:
        return SilenceVerdict(
            kind=Silence.UNKNOWN,
            alarming=False,
            detail=(
                f"git could not answer for this directory ({git.unavailable_because}), "
                f"so there is no history to judge the silence against"
            ),
        )
    if git.shallow:
        return SilenceVerdict(
            kind=Silence.UNKNOWN,
            alarming=False,
            detail=(
                "this clone has no history, so a project that never made such claims "
                "cannot be told from one whose claims stopped extracting. Check out "
                "with full history (`fetch-depth: 0` on GitHub Actions) to judge it"
            ),
        )

    try:
        return _classify(project, config, verifier, documents)
    except GitReadError as error:
        return SilenceVerdict(
            kind=Silence.UNKNOWN,
            alarming=False,
            detail=f"git could not answer ({error}), so the silence could not be judged",
        )


def _classify(
    project: Project, config: Config, verifier: Verifier, documents: list[Document]
) -> SilenceVerdict:
    root = project.root

    # The checkout itself, before any history: extraction over the documents as HEAD
    # records them. Loud blobs behind a silent working tree end the questioning.
    recorded = _extract(
        verifier,
        project,
        documents_from(root, blobs_at(root, "HEAD", doc_paths_at(root, "HEAD", config)), config),
    )
    if recorded:
        example = recorded[0]
        return SilenceVerdict(
            kind=Silence.TREE_MISMATCH,
            alarming=True,
            detail=(
                f"the documents as HEAD records them yield {len(recorded)} claim(s) — "
                f"e.g. `{example.subject}` at {project.relative(example.doc)}:{example.line} — "
                f"but the files on disk yield none. The checkout does not match the "
                f"repository: look for a failed checkout, or a sparse or filtered clone"
            ),
        )

    raw = _run(root, "log", "--format=%H\t%ad", "--date=short", "HEAD")
    commits = [line.split("\t", 1) for line in raw.decode("utf-8", "replace").splitlines() if "\t" in line]
    if not commits:
        raise GitReadError("git log named no commits")
    indices = sample_indices(len(commits))

    # Ascending index is newest-first, so the first loud sample is the most recent one —
    # exactly the commit whose subjects "does the text survive today" should be asked of.
    loud: tuple[str, str, list[Claim]] | None = None
    todays_commands = set(project.console_scripts)
    for index in indices:
        sha, date = commits[index]
        historical = documents_from(root, blobs_at(root, sha, doc_paths_at(root, sha, config)), config)
        if isinstance(verifier, DocumentedFlags):
            old_commands, old_name = scripts_at(root, sha)
            name = project.name or old_name
            claims = _extract(
                verifier,
                project,
                historical,
                commands=todays_commands | old_commands,
                package=name.replace("-", "_") if name else None,
            )
        else:
            claims = _extract(verifier, project, historical)
        if claims:
            loud = (sha, date, claims)
            break

    if loud is None:
        return SilenceVerdict(
            kind=Silence.NEVER,
            alarming=False,
            detail=(
                f"no sampled commit ({len(indices)} of {len(commits)}) extracts a claim "
                f"of this kind, so silence is this project's steady state rather than a "
                f"regression"
            ),
        )

    sha, date, claims = loud
    subjects: list[str] = []
    for claim in claims:
        if claim.subject not in subjects:
            subjects.append(claim.subject)

    # A plain substring search, deliberately broader than extraction: the whole question
    # is whether the *text* outlived the *extraction*. Searching spans-only would use
    # the very machinery under suspicion to decide whether the machinery failed.
    for subject in subjects:
        for document in documents:
            offset = document.text.find(subject)
            if offset < 0:
                continue
            line = document.text.count("\n", 0, offset) + 1
            return SilenceVerdict(
                kind=Silence.REGRESSED,
                alarming=True,
                detail=(
                    f"`{subject}` extracted as a claim at {sha[:9]} ({date}) and still "
                    f"appears at {project.relative(document.path)}:{line}, but extraction "
                    f"no longer produces it — the documentation's format has defeated the "
                    f"extraction"
                ),
            )

    examples = ", ".join(f"`{subject}`" for subject in subjects[:3])
    return SilenceVerdict(
        kind=Silence.STOPPED,
        alarming=False,
        detail=(
            f"claims of this kind still extracted at {sha[:9]} ({date}) — {examples} — "
            f"and none of those subjects appears in today's documents. The project "
            f"stopped making such claims"
        ),
    )
