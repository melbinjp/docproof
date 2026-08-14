"""`docproof [path]` — check a project's documentation against the project."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import Config, declares_removed, is_historical, opts_out, suppressed_lines
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
    parser.add_argument("--version", action="version", version=f"docproof {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
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
    for path in find_docs(project.root, tuple(args.docs) + config.docs):
        relative = project.relative(path)
        if config.excludes(relative):
            continue
        if is_historical(relative):
            historical.append(relative)
            continue
        text = read(path)
        if declares_removed(text):
            historical.append(relative)
            continue
        if opts_out(text):
            continue
        documents.append(Document(path=path, text=text, suppressed=suppressed_lines(text)))

    if not documents:
        # "No documentation" is ambiguous the same way a silent verifier is: the first
        # broken checkout this tool found had no documents on disk at all, and "nothing
        # to prove" was the wrong verdict for it. HEAD settles which case this is.
        vanished = vanished_documents(project, config)
        if vanished:
            print(vanished)
            return 1
        print(f"No documentation found under {project.root}. Nothing to prove.")
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
    if historical:
        # Printed, not swallowed. Dropping documents quietly is the same failure as
        # skipping claims quietly: the run looks cleaner than the evidence supports.
        print(f"   describing the past, not judged: {', '.join(sorted(historical))}")
    print()
    print(report.render(show_skips=args.show_skips))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
