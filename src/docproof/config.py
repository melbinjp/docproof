"""Letting a project say which documents are not promises.

Some documents are deliberately not descriptions of the current state. A build guide
written in an aspirational voice — *what this becomes* — sitting beside a README scoped to
what is true today is a common and perfectly sensible arrangement, and the project usually
says so in as many words. A checker that reports drift in the aspirational one is not
finding a bug; it is arguing with a decision the author already made and wrote down.

So there are two ways to say it, and both live with the project rather than in a flag
somebody has to remember to pass:

    # pyproject.toml
    [tool.docproof]
    exclude = ["agent.md", "docs/rfc/*.md"]

    <!-- docproof: skip-file — this describes the design, not the tree -->

The marker is deliberately the more visible of the two. A reader who finds a wrong path
in a document can see, in the document, that nobody is checking it.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SKIP_MARKER = re.compile(r"<!--\s*docproof:\s*skip-file\b", re.IGNORECASE)
SKIP_BLOCK = re.compile(r"<!--\s*docproof:\s*skip\s*(?:-->)?", re.IGNORECASE)

# Documents whose job is to describe the past. A changelog saying "0.68 moved
# `docs_src/websockets`" is *correct* and always will be, however many times that
# directory moves afterwards — the sentence is about a release, not about the tree.
#
# This is the largest single source of wrong findings there is: fastapi's
# `release-notes.md` alone produced 162 of them, more than every other document in
# twenty repositories combined. Recognised by the conventional names rather than by
# reading dates out of headings, because the convention is near-universal and a
# misread heading would put the tool back to guessing.
#
# `upgrading` and `migrat(e|ion|ing)` joined the list after probing the `symbols`
# verifier: marshmallow's `docs/upgrading.rst` shows `from marshmallow import
# MarshallingError`, a class removed in 3.0, as an illustration of the *old* API a
# reader is migrating away from. The sentence was true when written and stays true —
# it is a statement about a past release, exactly like a changelog entry, and the only
# reason it was not already caught is that "upgrading" was never on this list.
_HISTORICAL_NAMES = (
    r"changelog | changes | history | news | releases? | release[-_ ]?notes"
    r" | whatsnew | what[-_]s[-_]new | upgrad(?:e|ing) | migrat(?:e|ion|ing)"
)
# Matches the file's own name *and* any directory on the way to it. Pillow keeps its
# release notes as `docs/releasenotes/2.3.2.rst`, one file per version, and all eight of
# its findings came from there: the directory is the thing that says "this is history",
# and the filenames never could.
#
# `archive/` and `archived/` join on the same reasoning as `changelog.d/`: the directory name
# is the project saying, in the path, that what is inside has been retired.
#
# `coollabsio/coolify` documents `scripts/coold-vm.sh` inside `docs/v5/archive/dev/`, and the
# commit that deleted the script is named *"archive V5 implementation and remove runtime
# inte[gration]"* — the same change that created the archive. Judging it reports a project for
# correctly describing what it archived.
#
# Measured across 134 repositories: 464 documents under `archived/` (gsd-core) and 129 under
# `archive/` (coolify). Two repositories is a thin base for a rule, and it is taken anyway
# because the semantics do not depend on the count — a directory called `archive` means what
# the word means, and a project keeping live documentation there would be perverse.
#
# `deprecated/`, `legacy/` and `old/` are NOT included. `deprecated/` matched exactly one
# document in the whole corpus and the other two matched none, which is not evidence; and
# `TOMBSTONE` already draws the line that deprecated is not removed.
HISTORICAL = re.compile(
    rf"(?ix) (^|/) (?: {_HISTORICAL_NAMES} ) (?: \.[a-z0-9]+ )? (?: / | $ )"
    rf" | (^|/) changelog\.d/ "
    rf" | (^|/) archived? / "
    # A FILE called archive, not only a directory. This rule already believes the word means
    # what it means; it simply was not looking at filenames. `merman/docs/ARCHIVE.md` is an
    # index of retired documents and was reported for naming two ADRs that were renumbered
    # under it - the archive index is doing exactly its job by still listing them.
    #
    # Consistency rather than a new claim, which is why it is taken on one document: the
    # alternative is a rule that skips `archive/adr.md` and judges `ARCHIVE.md`, and no reading
    # of the word supports that.
    rf" | (^|/) archives? \.[a-z0-9]+ $ "
    # Decision records: an ADR body is frozen at authorship BY CONVENTION, and the projects
    # that keep them say so themselves. gsd-core's contributor standards:
    # *"Amendments are appended as `## Amendment (YYYY-MM-DD)` sections - the original body is
    # never rewritten."* So a path in an accepted ADR describes the tree as it was when the
    # decision was taken, exactly like a changelog entry, and reporting it argues with a
    # policy the project wrote down.
    #
    # Measured over the whole corpus rather than sampled - which took fixing the sweep's own
    # truncation first, because the sampled view showed none of this. Of **175 path findings
    # across 134 repositories, 83 are in `adr/` or `prd/`**, the single largest class by a
    # wide margin. They sit in one repository, and that is the honest weakness of the count;
    # the rule is taken anyway on the same footing as `archive/`, because what carries it is
    # what the directory MEANS and not how many projects happen to have one.
    rf" | (^|/) (?: adrs? | prds? | decision[-_]?records? | decisions? ) / "
    # A DATE in the path, which is the project stamping a document with the day it
    # describes. Same reasoning as `archive/`: the name says what the contents are.
    #
    # Found by trying three times to demonstrate that this tool belongs in CI as a gate,
    # failing three times, and measuring what the raw output was actually full of instead.
    # **41 of 92 reported path findings across the corpus sit in a path carrying a date,
    # in 3 repositories and 12 documents**, which is the largest remaining class by a wide
    # margin now that `adr/` and `prd/` are handled.
    #
    # Every one of the twelve is unmistakable once looked at. `docs/post-mortems/2019-02-05.md`
    # is reported for naming files deleted in the seven years since. wekan's
    # `docs/DeveloperDocs/Optimized-2025-02-07/Priority_2_optimizations.md` opens *"All
    # Priority 2 optimizations have been successfully implemented"* and lists, under a
    # heading literally reading **Files:**, *"Created: `server/publications/cronJobs.js`"*.
    # That file was removed in 2026 by a commit named *"Remove the cron migration subsystem:
    # it never ran"*. The document is not wrong. It is a true record of what was built on a
    # day, and nobody is going to rewrite a dated summary to keep it in step with a tree it
    # was never describing.
    #
    # Full date only, never a bare year: `docs/2026-roadmap.md` is a live document and must
    # keep being judged. A date is a stamp; a year is a topic.
    #
    # **Regression-checked against every finding I have filed with a human behind it** -
    # click, pipenv (merged), prettier, sentry-react-native. None of their documents carries
    # a date, so this rule silences none of them. That check is the point: a skip rule that
    # quietly eats real findings is worse than the noise it removes.
    r" | [0-9]{4} - [0-9]{2} - [0-9]{2} "
    #
    # THREE NEIGHBOURING RULES WERE MEASURED THE SAME DAY AND REJECTED. Written down so
    # they are not re-proposed by someone who only sees that the date rule paid off.
    #
    # * **An absolute or home path** (`cd /Users/diego/Dev/get-shit-done`). 6 findings, ONE
    #   repository, and four of those are the same line duplicated across translations of one
    #   document. A path on somebody's laptop is obviously not a claim about this project, and
    #   the rule is still rejected, because one repository is not evidence and this costs
    #   nothing to leave.
    #
    # * **A plan/PRD/design/spec FILENAME**, as against the `prd/` and `adr/` DIRECTORIES
    #   above. 8 findings, ONE repository. A directory called `adr` means what the word means;
    #   a file called `modernization-plan.md` could just as easily be a living roadmap, and
    #   the whole reason the directory rule was defensible on one repository was that its
    #   semantics did not depend on the count. A filename's do.
    #
    # * **A date STAMPED IN THE DOCUMENT** rather than in its path, e.g. pipenv's
    #   `**Generated**: 2026-05-12`. 7 findings, two repositories, which is the size of the
    #   removal-verb class already rejected. It also failed on its own terms: any pattern
    #   broad enough to catch "Generated:" catches "Last updated:", and a last-updated stamp
    #   marks a document somebody is MAINTAINING. That rule would skip live documentation,
    #   which is the one failure worse than the noise it removes.
)


def is_historical(relative_path: str) -> bool:
    """Whether a document describes the past rather than the current tree."""
    return bool(HISTORICAL.search(relative_path))


# A page can also say it in prose rather than in its name. bandit keeps doc pages for
# plugins B109 and B111 that open with "This plugin has been removed." — deliberate
# tombstones, kept so old links keep resolving — and pdm's `docs/dev/benchmark.md` opens
# "This page has been removed, please visit …". A stale example path inside such a page
# is not drift; the page has already told its reader it describes something that no
# longer exists.
#
# Narrow on purpose, from reading every candidate in the forty-repo corpus (a broad net
# matched eleven lines; exactly two were tombstones). The subject must be
# self-referential — "This page/plugin/module …" — and the verb must be *removed*.
# Deprecated is not removed: structlog's thread-local page documents a deprecated module
# that still exists, still makes promises, and still deserves judgment. A removal note
# about something else ("The ``scrapy deploy`` command has been removed in 1.0") is a
# live page stating history, not a tombstone.
TOMBSTONE = re.compile(r"(?i)^[\s>*_-]{0,8}This\s+\w+\s+(?:has been|was)\s+removed\b")

# The other way a page says it, which `TOMBSTONE` misses because there is no sentence: a
# LABEL at the top of the document rather than a claim about a subject.
#
# `wekan/docs/Databases/Migrations/CODE_CHANGES_SUMMARY.md` opens
# *"> **OBSOLETE — historical record.** This documents the old cron-driven migration system
# … since **removed**"*. It then documents `server/cronMigrationManager.js`, deleted in
# `a440d44ea`. The page could not be clearer about what it is, and this reported it as drift.
#
# Measured with the same discipline as `TOMBSTONE`, over 134 repositories: **seven documents,
# all seven genuine** — flask's `reqcontext.rst` and `patterns/jquery.rst` ("Obsolete, see …
# instead"), a superseded ADR in gsd-core, and four wekan migration records. Three separate
# repositories, which made this the easiest of the three to take.
#
# `no longer used|maintained|accurate` matched NOTHING in the corpus and is therefore absent,
# on the same rule that kept `deprecated/` out of `HISTORICAL`.
#
# `historical` takes three more nouns, and the list is deliberately closed. `merman` labels
# three documents this way and each says outright that it is not current:
#
#     > Historical backlog, not current implementation guidance.
#     > Historical completion snapshot. References to ... mechanisms removed on 2026-07-15
#     > Historical roadmap. References to root/text/SVG override tables ...
#
# **A bare `historical \w+` was measured and REJECTED.** It would match a live document opening
# "Historical context is important here", which is a normal way to begin a design note and the
# opposite of a retirement label. Only nouns that name the whole document's kind are taken.
#
# Thin base, said plainly: 7 findings in 3 documents, all in one repository. That is thinner
# than the status-field rule and thinner than `archive/`. It is taken on the same footing as
# the ADR rule, which also rested on one repository: what carries it is that the sentence
# means what it says, not how many projects happen to have written it.
RETIRED_LABEL = re.compile(
    r"(?i)^[\s>*_#-]{0,8}\**\s*(?:obsolete|superseded"
    r"|historical\s+(?:\w+\s+)?(?:record|backlog|snapshot|roadmap))\b"
)


# The THIRD form, and the one both of the above miss because it is neither a sentence nor a
# label: a machine-readable STATUS FIELD. `merman` keeps a document per workstream and each
# opens with a header line -
#
#     Status: Completed; historical snapshot
#     Status: Superseded on 2026-07-15 by `docs/alignment/STATUS.md`
#     Status: Closed
#
# and those documents then describe the tree as it stood when the work finished. Reporting
# them argues with a field the project maintains on purpose.
#
# **The value is read, not just the field.** This is the whole difficulty, and it was found by
# measurement rather than foreseen: `pipenv/docs/dev/initiative-f-typed-design.md` opens
# `Status: **awaiting maintainer sign-off**`, which is a LIVE document waiting on a person -
# and `pipenv#6709` was filed against that very file and merged. A rule keyed on the presence
# of a `Status:` line would have suppressed a real, accepted contribution. So the value must
# name a terminal state, and `draft`, `proposed`, `active`, `in progress` and `awaiting`
# deliberately do not.
#
# Measured over 217 findings in 134 repositories: **58 suppressed across 22 documents, and
# zero of the filings already made** - checked one by one against click, prettier, pipenv,
# gsd-core, wekan, zeroclaw and sentry-react-native, including the two that merged.
#
# The honest weakness is the same one the ADR rule carries: 21 of the 22 documents are
# `merman` and the 22nd is `wekan`. Two repositories is a thin base. It is taken anyway on the
# same reasoning - a project writing `Status: Complete` in a structured field has said what
# the document is, and a project keeping live documentation under that header would be
# perverse.
STATUS_FIELD = re.compile(r"(?i)^[\s>*_#-]{0,8}\**\s*status\**\s*[:=]\s*(.+)$")
STATUS_DONE = re.compile(
    "(?i)^[^a-z0-9]*(?:completed?|done|finished|shipped|historical|archived|superseded"
    "|obsolete|retired|closed|abandoned|withdrawn)(?![a-z])"
)


def declares_done(line: str) -> bool:
    """Whether one line is a status field naming a terminal state."""
    match = STATUS_FIELD.match(line)
    return bool(match and STATUS_DONE.match(match.group(1).strip()))


def declares_removed(text: str) -> bool:
    """Whether a document opens by declaring its own subject removed or retired.

    Only the first ten non-blank lines are considered, for the same reason `opts_out`
    stops at forty: a declaration buried where no reader would see it before trusting
    the page should not silence the checker either.
    """
    lede = [line for line in text.split("\n") if line.strip()][:10]
    return any(TOMBSTONE.match(line) or RETIRED_LABEL.match(line) or declares_done(line) for line in lede)


# A code block can be shown precisely BECAUSE it is wrong — the API you are migrating off,
# the anti-example, the "before" of a before-and-after. Judging it inverts the tool: the
# passage is correct exactly when the code in it does not work.
#
# `plaid/plaid-python`'s README has five of these under `#### Client initialization`, each
# introduced by a line reading `From:`, showing `from plaid import Client` — the pre-8.0.0
# interface, removed in August 2021 and shown so an upgrading reader recognises it. This
# reported that README as contradicting its code. Filing it would have been a wrong pull
# request against a payments company.
#
# **Derived by measuring, not by guessing, and the first attempt was three-quarters noise.**
# A wide net over the hundred-repo corpus (`mind/work/docproof-sweep/measure_supersede.py`)
# found 391 sites, of which 298 began with the word `from` because that is also how a Python
# import line starts. The signal is not the vocabulary, it is the LINE SHAPE: a line that is
# only a label and a colon, carrying no code of its own.
#
# Narrowed to that shape the corpus gives 54 sites, and every one was read:
#
#     33  the superseded side   Before: / Old code: / From: / Old: / Instead of: / Old example:
#     20  the CURRENT side      After: / New code: / New: / New setting: / Now we have:
#      1  a false match         `### From repository root:` — a heading naming a directory
#
# So the rule takes the superseded side only. Matching `After:` too would have silenced
# twenty blocks of live, correct, checkable code — the exact over-correction that makes a
# checker useless — and headings are excluded, which is what removes the single false match.
#
# **`Deprecated:` is deliberately NOT here**, for the reason `TOMBSTONE` already gives:
# deprecated is not removed. A deprecated API still exists, still makes promises, and still
# deserves judgment.
SUPERSEDED_LABEL = re.compile(
    r"(?i)^[\s>*_-]{0,8}(?:before|old(?:\s+\w+)?|from|previously|legacy|instead\s+of)"
    r"(?:\s+\w+){0,2}\s*:[\s*_]*$"
)
FENCE = re.compile(r"^\s*(?:```|~~~)")


def superseded_lines(text: str) -> frozenset[int]:
    """Line numbers inside a code block that the prose above labels as superseded.

    Scope is one block, reached within two lines of the label — deliberately tight. A
    before-and-after runs `Before:` block `After:` block, so a rule that ran further than
    the next fence would swallow the half that is current and correct.
    """
    lines = text.split("\n")
    covered: set[int] = set()
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#") or not SUPERSEDED_LABEL.match(line):
            continue
        cursor = next(
            (c for c in range(index + 1, min(index + 3, len(lines))) if FENCE.match(lines[c])), None
        )
        if cursor is None:
            continue
        covered.add(cursor + 1)
        cursor += 1
        while cursor < len(lines) and not FENCE.match(lines[cursor]):
            covered.add(cursor + 1)
            cursor += 1
        if cursor < len(lines):
            covered.add(cursor + 1)  # the closing fence
    return frozenset(covered)


@dataclass
class Config:
    exclude: tuple[str, ...] = ()
    docs: tuple[str, ...] = ()
    """Extra globs to treat as documentation, beyond the default discovery."""

    disable: frozenset[str] = field(default_factory=frozenset)
    """Verifier names to skip entirely."""

    @classmethod
    def from_pyproject(cls, data: dict[str, Any]) -> Config:
        table = data.get("tool", {})
        table = table.get("docproof", {}) if isinstance(table, dict) else {}
        if not isinstance(table, dict):
            return cls()

        def strings(key: str) -> tuple[str, ...]:
            value = table.get(key, [])
            if isinstance(value, str):
                return (value,)
            if isinstance(value, list):
                return tuple(str(v) for v in value)
            return ()

        return cls(
            exclude=strings("exclude"),
            docs=strings("docs"),
            disable=frozenset(strings("disable")),
        )

    def excludes(self, relative_path: str) -> bool:
        return any(fnmatch.fnmatch(relative_path, pattern) for pattern in self.exclude)


def opts_out(text: str) -> bool:
    """Whether a document has marked itself as not a claim about the current tree.

    Only the first 40 lines are searched. A marker buried at the bottom of a long file is
    invisible to the reader it is meant to inform, so it should not be effective either.
    """
    return bool(SKIP_MARKER.search("\n".join(text.split("\n")[:40])))


def suppressed_lines(text: str) -> frozenset[int]:
    """Line numbers covered by a `<!-- docproof: skip -->` marker.

    Documentation is full of paths that are illustrations rather than claims —
    *"suppose your entry point is `src/pkg/main.py`"* — and no amount of pattern matching
    separates a hypothetical from an assertion. This README's own examples were reported
    as drift the first time it checked itself, which is how the need for this was found.

    A marker covers the paragraph it introduces: from its own line to the next blank
    line. Paragraph scope rather than whole-file scope on purpose — a marker that
    silences a document forever is one nobody notices has outlived its reason.
    """
    lines = text.split("\n")
    covered: set[int] = set()
    for index, line in enumerate(lines):
        if not SKIP_BLOCK.search(line) or SKIP_MARKER.search(line):
            continue
        cursor = index
        while cursor < len(lines) and lines[cursor].strip():
            covered.add(cursor + 1)
            cursor += 1
        # A marker on a line of its own introduces the paragraph after the blank line.
        if lines[index].strip().startswith("<!--") and cursor < len(lines):
            cursor += 1
            while cursor < len(lines) and lines[cursor].strip():
                covered.add(cursor + 1)
                cursor += 1
    return frozenset(covered)


# --- a DIRECTORY that declares its own contents non-authoritative ---------------------------
#
# The fifth shape, and the first one that reads a file OTHER than the document being judged.
# The four before it are path-scoped (`HISTORICAL`), sentence-scoped (`TOMBSTONE`),
# label-line-scoped (`RETIRED_LABEL`) and field-scoped (`declares_done`). None of them can see
# a folder marked by its own README, which is how people actually mark a drafts folder:
#
#     docs/Docs_To_Review/README.md
#     # Docs To Review (archival)
#     Files here are internal / archival / pending-audit. They are not the source of truth.
#
# Twenty-nine findings sat under that sentence. Reporting them is not a wrong claim about the
# tree - the files really are stale - it is arguing with a decision the project wrote down, in
# the one place a reader would look for it.
#
# **The naive version was measured first and it was a disaster.** Matching the vocabulary
# anywhere in a directory README silenced 95 of 217 corpus findings, 66 of them in a
# repository whose findings had been filed as pull requests hours earlier. A rule that
# retracts a filing is not a precision rule. Three separate defects, each visible only by
# running it:
#
#   1. it matched VOCABULARY rather than declarations. One repository's `docs/README.md` has a
#      contents-table row reading "Archived history | Preserves completed or superseded
#      context"; another's ADR folder lists `Deprecated` as an allowed status VALUE. Neither
#      says the folder is not current.
#   2. the README that matched sat at `docs/`, so one loose hit silenced an entire docs tree.
#   3. "not published" is about npm and crates.io and Maven, and says nothing about whether a
#      document is authoritative. It caught four repositories that way.
#
# So this requires a CONJUNCTION - the sentence must name the directory's contents and deny
# their authority - and it requires the naming half to OPEN the line. That second condition is
# grammatical rather than lexical: English puts the subject first, and a folder marker is a
# statement whose subject is the folder. It is what separates
#
#     "Everything in this directory is a historical record."          <- a marker
#
# from the two sentences the anchor removed, where the phrase is present and the sentence is
# about something else entirely:
#
#     "docs/adr/0011-....md predates this directory and is preserved as immutable historical
#      record. ... New PRDs live here."                               <- the folder is CURRENT
#     "bender is configured via the configuration.nix file in this directory, and does not
#      currently use Nix flakes."                                     <- about a tool
#
# Final measurement over 171 repositories: **two directories, both readings correct, 29
# findings silenced, and zero of them a document behind a filing.** That last check is
# per-document and not per-repository, which matters here more than it looks: the repository
# in question holds two different files called `TAURI_VALIDATION_REPORT.md`, one at `docs/`
# that a pull request was opened about and an archival copy inside the marked folder. A count
# by repository cannot tell those apart and briefly said the opposite.
#
# Thin base, taken anyway, and the commercial reason is the honest one: that repository would
# otherwise be shown 34 findings of which one is real, and a tool that cries wolf gets
# uninstalled inside a minute whatever else is true about it.
#
# NOT recursive, deliberately. Only a document sitting DIRECTLY in the marked directory is
# skipped. A marker is a statement about the things beside it, and letting it reach down
# through subdirectories is how defect 2 above gets back in.
_DIR_QUANT = "(?:everything|anything|all|the|these)[ ](?:files|documents|docs|of[ ]it|)[ ]?"
_DIR_SUBJECT = (
    "files[ ]here|files[ ]in[ ]th|documents[ ]here|documents[ ]in[ ]th|docs[ ]here"
    "|this[ ]directory|this[ ]folder|these[ ]docs|these[ ]documents|contents[ ]of[ ]this"
    "|everything[ ]here|anything[ ]here"
    "|" + _DIR_QUANT + "in[ ]th(?:is|e[ ]following)[ ](?:directory|folder)"
)
# "not current" needs the copula in front of it: bare, it matched "does not currently use".
_DIR_DENIAL = (
    "not[ ]the[ ]source[ ]of[ ]truth|not[ ]authoritative|archival"
    "|(?:is|are|were|remain)[ ]not[ ]current"
    "|no[ ]longer[ ]maintained|pending[ ]audit|superseded|out[ ]of[ ]date|historical"
)
_DIR_LEAD = "^[ >*_#-]{0,8}"
DIR_DECLARES = re.compile("(?i)" + _DIR_LEAD + "(?:" + _DIR_SUBJECT + ")[^.]{0,120}(?:" + _DIR_DENIAL + ")")
DIR_NAMES_CONTENTS = re.compile("(?i)" + _DIR_LEAD + "(?:" + _DIR_SUBJECT + ")")
DIR_DENIES = re.compile("(?i)(?:" + _DIR_DENIAL + ")")

# The files that speak for a directory. Nothing else in it does.
DIRECTORY_README = ("README.md", "readme.md", "README.rst", "index.md")


def directory_disclaimer(directory: Path) -> str | None:
    """The sentence in this directory's own README declaring its contents not current.

    Returns the sentence so the caller can QUOTE it. A skip whose reason cannot be shown is
    the same failure as a silent skip, and this one is easier to get wrong than the others
    because the reason lives in a file the reader is not looking at.

    Only the first forty lines, for the reason `declares_removed` stops at ten: a disclaimer
    buried where nobody would see it before trusting the folder should not silence the checker
    either.

    The denial is allowed to arrive on the NEXT line, because that is how the clearest example
    in the corpus writes it - "Files here are internal / archival / pending-audit." and then
    "They are not the source of truth." - and a rule reading one line at a time would miss it.
    """
    for name in DIRECTORY_README:
        readme = directory / name
        if not readme.is_file():
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = [line.strip() for line in text.split("\n")[:40]]
        for index, line in enumerate(lines):
            if not line or len(line) > 300:
                continue
            if DIR_DECLARES.search(line):
                return line
            if DIR_NAMES_CONTENTS.search(line):
                following = lines[index + 1] if index + 1 < len(lines) else ""
                if following and len(following) <= 300 and DIR_DENIES.search(following):
                    return f"{line} {following}"
    return None
