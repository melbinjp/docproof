"""`docproof [path]` — check a project's documentation against the project."""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import (
    Config,
    declares_removed,
    directory_disclaimer,
    is_historical,
    opts_out,
    superseded_lines,
    suppressed_lines,
)
from .docs import find_docs, read
from .history import classify, vanished_documents
from .project import Project, find_root
from .report import Report
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
        print(f"   describing the past, not judged: {', '.join(sorted(historical))}")
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

    documents = []
    historical: list[str] = []
    # Keyed by (directory, the sentence it said), so the report can quote the reason once and
    # list the files under it rather than repeating a disclaimer thirty times.
    disclaimed: dict[tuple[str, str], list[str]] = {}
    read_directory: dict[Path, str | None] = {}
    for path in find_docs(project.root, tuple(args.docs) + config.docs):
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
    report = Report(project=project, outcomes=outcomes)
    print(f"docproof {__version__} — {project.root.name}, {len(documents)} document(s)")
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
    print()
    print(report.render(show_skips=args.show_skips))
    if args.exit_zero and not report.stopped_checking:
        return 0
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
