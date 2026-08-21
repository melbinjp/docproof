"""`docproof [path]` — check a project's documentation against the project."""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from . import __version__
from . import genre as document_genre
from .config import (
    Config,
    declares_removed,
    directory_disclaimer,
    is_historical,
    opts_out,
    superseded_lines,
    suppressed_lines,
)
from .docs import (
    by_directory,
    find_docs,
    likeliest_docs_directory,
    read,
    unread_documents,
)
from .history import classify, vanished_documents
from .model import Verdict
from .project import Project, find_root
from .report import Report
from .vcs import Git
from .verifiers.base import Document, Verifier
from .verifiers.cli_flags import DocumentedFlags
from .verifiers.paths import DocumentedPaths
from .verifiers.symbols import DocumentedSymbols
from .verifiers.versions import DocumentedVersions

ALL_VERIFIERS: tuple[type[Verifier], ...] = (
    DocumentedPaths,
    DocumentedFlags,
    DocumentedVersions,
    DocumentedSymbols,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docproof",
        description="Prove a project's documentation against the project. "
        "Deterministic: no model, no network, no guesses.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "path", nargs="?", default=".", help="a file or directory inside the project to check"
    )
    parser.add_argument(
        "--show-skips", action="store_true", help="list every claim that was not judged, and why"
    )
    parser.add_argument(
        "--only", metavar="NAME", action="append", default=None, help="run only this check; repeatable"
    )
    parser.add_argument("--list", action="store_true", help="list the available checks and exit")
    parser.add_argument(
        "--docs",
        metavar="GLOB",
        action="append",
        default=[],
        help="also treat files matching this glob as documentation; repeatable",
    )
    # **A gate that fails on day one gets removed on day one.**
    #
    # Adding this to a repository that already has drift breaks its build immediately, so
    # the only projects that can adopt it as-is are the ones already clean, which is
    # exactly the 93% of the corpus that has nothing to find. Every linter that got
    # adopted shipped this: report first, enforce once you are level.
    #
    # It suppresses the CONTRADICTION exit only. A check that demonstrably stopped
    # checking still fails, because that is not a finding you are deferring, it is the
    # tool telling you it went blind, and there is no version of "later" that makes a
    # blind check acceptable. See `Report.stopped_checking`.
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="report contradictions without failing the run; a check that stopped checking still fails",
    )
    parser.add_argument(
        "--all-genres",
        action="store_true",
        help="also judge planning and record documents; they measured 0/14 and 1/4 real",
    )
    parser.add_argument("--version", action="version", version=f"docproof {__version__}")
    return parser


def survive_a_narrow_console() -> None:
    """Stop a character the console cannot encode from killing the whole report.

    Found by running docproof on `worldmonitor` from a Windows shell: it printed the header
    and the skip list, then died on `cli.py` line 154 with

        UnicodeEncodeError: 'charmap' codec can't encode character '\\u2192'

    The arrow was not ours. It came out of the documentation being quoted back in a finding,
    so **any repository whose docs contain a character outside the console's codepage takes
    the CLI down** - arrows, box drawing, CJK, an emoji in a heading. Our own output makes it
    likelier still: `tree.py` and `verifiers/paths.py` carry 37 box-drawing characters, and
    none of the four survive cp1252.

    The exit code on that crash is 1, which is also the code for "claims were contradicted".
    So a Windows user sees a failing build and a traceback where a report should be, and
    cannot tell a broken tool from a broken document.

    **CI could never have caught this.** GitHub's Windows runners hand Python a UTF-8 stdout,
    so `docproof on docproof, through the action (windows-latest)` is green and always was.
    The failure only exists where a real person runs it, which is the worst place to keep it.

    The error handler is changed and the ENCODING IS NOT. Forcing UTF-8 would replace a crash
    with mojibake on a legacy console, which is a quieter kind of wrong; `backslashreplace`
    keeps whatever the terminal can already show and degrades the rest to a visible escape.
    Where stdout is already UTF-8, which is every CI runner, this changes nothing at all.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # a stream someone replaced with their own object
            continue
        with contextlib.suppress(ValueError, OSError):
            reconfigure(errors="backslashreplace")


TOP_DIRECTORIES = 5
SET_ASIDE_NAMES = 10


def report_coverage(project: Project, unread: list[Path]) -> str | None:
    """Say how much of the tree was in scope at all, whether or not any of it was missed.

    Returns the directory a reader should widen to, or None when nothing unread is named
    like documentation, so the VERDICT at the bottom can carry the same judgement this
    header already makes. It used to be computed here and thrown away, and the two ends of
    one report then said different things about the same number - see `Report.render`.

    **This prints on every run, including the clean one, and that is the whole point.** The
    other skip reports in this file stay quiet when they have nothing to say, which is right
    for them: the count of documents they set aside is visible in the header line beside the
    count they judged. Documents that were never DISCOVERED have no such counterpart. Left
    silent, "4 document(s)" over a tree of 168 is indistinguishable from "4 document(s)"
    over a tree of 4, and the reader has no way to tell which one they are looking at.

    The directory list is capped at five, and the line says so with the remainder counted -
    a truncated list under an untruncated total is how a reader concludes from an absence
    somebody else manufactured.
    """
    if not unread:
        print("   every documentation file in the tree was in scope")
        return None
    groups = by_directory(project.root, unread)
    shown = groups[:TOP_DIRECTORIES]
    rest = groups[TOP_DIRECTORIES:]
    where = ", ".join(f"{name}/ {count}" for name, count in shown)
    if rest:
        where += f", and {len(rest)} more director{'y' if len(rest) == 1 else 'ies'} holding "
        where += str(sum(count for _, count in rest))
    print(
        f"   {len(unread)} documentation file(s) elsewhere in the tree were NOT read; the "
        f"default scope is top-level files plus doc/ and docs/"
    )
    print(f"     {where}")
    # The directory to widen TO is not the biggest one. Measured over sweep batch 10:
    # the largest unread segments across twenty-three repositories are `skills/`, `tools/`,
    # `src/`, `crates/` and `.changeset/`, and one entry in the top nine is documentation.
    # See `likeliest_docs_directory`.
    widen = likeliest_docs_directory(groups)
    if widen:
        print(
            f"     read them too with --docs '{widen}/**/*.md' or "
            f'[tool.docproof] docs = ["{widen}/**/*.md"]'
        )
    else:
        print(
            "     none of them is named like a documentation tree; if one is, widen with "
            "--docs 'DIR/**/*.md' or [tool.docproof] docs = [\"DIR/**/*.md\"]"
        )
    return widen


def report_set_aside(historical: list[str], disclaimed: dict[tuple[str, str], list[str]]) -> None:
    """Name every document that was found and deliberately not judged, and why.

    Printed, not swallowed. Dropping documents quietly is the same failure as skipping
    claims quietly: the run looks cleaner than the evidence supports.

    It is a function rather than two blocks inline because it has to run on BOTH exits - the
    ordinary one and the one where every document was set aside. The second path used to
    return before reaching this, so a repository whose only docs sit in a marked folder was
    told "No documentation found", which is the same lie in a friendlier voice.
    """
    if historical:
        # **Capped, with the remainder counted, and that was learned from trino.** This list
        # was unbounded, and trino keeps 330 release notes under `docs/src/main/sphinx/release/`.
        # The run printed every one of their filenames on a single line thousands of characters
        # long, which buried the report underneath it and told the reader nothing that the
        # count does not. Ten names is enough to see WHAT KIND of document was set aside,
        # which is the only question a reader has here.
        #
        # The remainder is stated rather than trimmed away. A truncated list under no total
        # is how somebody concludes from an absence the tool manufactured.
        shown = sorted(historical)[:SET_ASIDE_NAMES]
        tail = "" if len(historical) <= SET_ASIDE_NAMES else f", and {len(historical) - SET_ASIDE_NAMES} more"
        print(f"   describing the past, not judged ({len(historical)}): {', '.join(shown)}{tail}")
    # The directory reason is QUOTED, and it has to be. Every other skip can be audited by
    # opening the document that was skipped; this one's reason lives in a neighbouring file
    # the reader is not looking at, so a bare count would be a skip nobody could check.
    for (directory, marker), names in sorted(disclaimed.items()):
        print(
            f"   {directory}/ says its own contents are not current, "
            f"not judged ({len(names)}): {', '.join(sorted(names))}"
        )
        print(f'     its README: "{marker[:200]}"')


def main(argv: Sequence[str] | None = None) -> int:
    survive_a_narrow_console()
    args = build_parser().parse_args(argv)

    if args.list:
        for cls in ALL_VERIFIERS:
            instance = cls()
            print(f"{instance.name:12} {instance.describes}")
        return 0

    project = Project(root=find_root(Path(args.path)))
    config = Config.from_pyproject(project.pyproject)
    # An empty set means git could not answer, NOT that the project tracks nothing;
    # passing it through as-is would report every document as read.
    tracked = Git(root=project.root).tracked_files or None

    documents = []
    historical: list[str] = []
    # Keyed by (directory, the sentence it said), so the report can quote the reason once and
    # list the files under it rather than repeating a disclaimer thirty times.
    disclaimed: dict[tuple[str, str], list[str]] = {}
    read_directory: dict[Path, str | None] = {}
    # Held rather than iterated directly, because `unread_documents` needs to know what WAS
    # in scope. Comparing against `documents` instead would double-count: a document set
    # aside as historical or disclaimed was found, and `report_set_aside` already names it.
    in_scope = find_docs(project.root, tuple(args.docs) + config.docs)
    for path in in_scope:
        relative = project.relative(path)
        if config.excludes(relative):
            continue
        if is_historical(relative):
            historical.append(relative)
            continue
        # A README at the project root speaks for the project, not for a folder of drafts.
        # Letting it disclaim would silence everything, which is the whole repository.
        if path.parent != project.root:
            if path.parent not in read_directory:
                read_directory[path.parent] = directory_disclaimer(path.parent)
            marker = read_directory[path.parent]
            if marker:
                disclaimed.setdefault((project.relative(path.parent), marker), []).append(path.name)
                continue
        text = read(path)
        if declares_removed(text):
            historical.append(relative)
            continue
        if opts_out(text):
            continue
        documents.append(
            Document(
                path=path, text=text, suppressed=suppressed_lines(text), superseded=superseded_lines(text)
            )
        )

    if not documents:
        # "No documentation" is ambiguous the same way a silent verifier is: the first
        # broken checkout this tool found had no documents on disk at all, and "nothing
        # to prove" was the wrong verdict for it. HEAD settles which case this is.
        #
        # ...but only when nothing was deliberately set aside. If every document was skipped
        # for a stated reason then documentation WAS found and we chose not to judge it, so
        # "no documentation on disk" is simply false, and `vanished_documents` compares a
        # HEAD that knows nothing about those reasons against a disk we filtered ourselves.
        # A repository whose only docs live in a folder marked "not the source of truth"
        # would otherwise be told its checkout is broken. Found by a test, not in the wild.
        if not historical and not disclaimed:
            vanished = vanished_documents(project, config)
            if vanished:
                print(vanished)
                return 1
            print(f"No documentation found under {project.root}. Nothing to prove.")
            return 0
        # Documentation WAS found and all of it was set aside. Saying "no documentation
        # found" here would be the same lie in a friendlier voice, so the reasons are
        # printed on this path exactly as they are on the ordinary one.
        print(f"docproof {__version__} — {project.root.name}, every document set aside")
        report_coverage(project, unread_documents(project.root, in_scope, tracked))
        report_set_aside(historical, disclaimed)
        print()
        print("Nothing was judged, and each reason is above. Nothing to prove.")
        return 0

    chosen = [
        c
        for c in ALL_VERIFIERS
        if (args.only is None or c.name in args.only) and c.name not in config.disable
    ]
    if not chosen:
        print(f"No check matches {args.only}. Try --list.", file=sys.stderr)
        return 2

    outcomes = []
    for cls in chosen:
        verifier = cls()
        outcome = verifier.run(project, documents)
        if outcome.silent:
            # Silence alone is ambiguous between "never made such claims" and "the
            # extraction broke", and only history can say which — see `history`.
            outcome.silence = classify(project, config, verifier, documents)
        outcomes.append(outcome)

    # THE GENRE GATE. A plan is a statement about a decision at a moment; a reference is a
    # statement about the system now, and only the second can be contradicted by the tree.
    # Measured over 61 hand-judged findings: reference 35/37 real, plan 0/14, record 1/4.
    # Holding the two back moves precision from 0.69 to 0.95 and costs one real finding.
    # Full working and the pre-registered falsification test live in `genre.py`.
    #
    # NOTHING IS DELETED. The findings are still found and still counted, and the line below
    # names every document held back, because this file already knows the rule: over-firing
    # should be visible as a shrinking count, not as a report that quietly got cleaner. The
    # same applies to under-firing, which is what a gate is.
    withheld: list[str] = []
    if not args.all_genres:
        for outcome in outcomes:
            for index, finding in enumerate(outcome.findings):
                if finding.verdict is not Verdict.BROKEN:
                    continue
                relative = document_genre.relative_doc(finding.claim.doc, project.root)
                if not document_genre.held_back(relative):
                    continue
                kind = document_genre.genre(relative)
                withheld.append(f"{finding.claim.where(project.root)} ({kind})")
                # SKIPPED, NOT DELETED, and the model already had the right word for this:
                # "the claim could not be checked reliably, and guessing was refused. Every
                # skip carries a reason, and the reasons are reported rather than hidden."
                # That is exactly what a plan document is - a statement about a decision at a
                # moment, which the tree cannot contradict.
                #
                # Removing the finding outright was the first attempt and it was WRONG in a
                # way the suite caught: an outcome with no findings left is `silent`, silence
                # with no classification is alarming, and the run then failed claiming the
                # check had gone blind. A gate must not be able to make a verifier that
                # looked and found things look like one that could not see.
                outcome.findings[index] = replace(
                    finding,
                    verdict=Verdict.SKIPPED,
                    detail=(
                        f"{kind}-genre document, not judged: findings in planning and "
                        f"record documents measured 1 real in 18. --all-genres judges "
                        f"them. Original finding: {finding.detail}"
                    ),
                )

    report = Report(project=project, outcomes=outcomes)
    print(f"docproof {__version__} — {project.root.name}, {len(documents)} document(s)")
    unread = unread_documents(project.root, in_scope, tracked)
    docs_directory = report_coverage(project, unread)
    report_set_aside(historical, disclaimed)
    # Same principle, one level down, and it applies harder: nobody asked for this rule.
    # A `Before:` label is the tool deciding by itself that a block is not a claim, so the
    # place it fired is named — over-firing should be visible as a shrinking count, not as
    # a report that quietly got cleaner.
    superseded = [
        f"{d.path.relative_to(project.root).as_posix()}:{min(d.superseded)}"
        for d in documents
        if d.superseded
    ]
    if superseded:
        print(f"   labelled superseded by the prose above, not judged: {', '.join(sorted(superseded))}")
    if withheld:
        print(
            f"   held back as planning or record documents, where findings measured "
            f"1 real in 18: {', '.join(sorted(withheld))}"
        )
        print("   --all-genres judges them anyway.")
    print()
    print(
        report.render(
            show_skips=args.show_skips,
            read=len(documents),
            unread=len(unread),
            docs_directory=docs_directory,
        )
    )
    if args.exit_zero and not report.stopped_checking:
        return 0
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
