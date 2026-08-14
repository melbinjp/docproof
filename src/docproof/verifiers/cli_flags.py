"""Options the documentation shows, checked against the options the program defines.

A README that shows `prog --dry-run` is asserting that `--dry-run` exists. It is the kind
of claim a reader tests immediately and involuntarily, by copying the line, and the kind
that breaks silently when a flag is renamed.

**Two things have to be true before a missing flag is drift**, and both are about evidence
rather than about flags:

* **The command has to be this project's.** `pip install --upgrade prog` documents pip's
  option. The first word of the line decides it, matched against the console scripts the
  project declares in its own `pyproject.toml` — so attribution is derived from the
  project, not from its name or a guess.
* **The set of known options has to be provably complete.** `parsers.argparse_flags`
  answers that honestly and usually says no: a parser built in a loop, or handed to a
  helper, can accept options no static read can name. When it says no, a flag it has not
  seen is *unjudged*, and the reason given is the incompleteness itself.

The result is a check that confirms far more than it contradicts. That is the right shape:
a documented flag that exists is the common case and worth saying, and the rare
contradiction is worth trusting when it comes.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Iterator

from ..docs import Span, command_lines, spans
from ..model import Claim, Finding
from ..parsers import FlagSet, argparse_flags, wrapper_flags
from ..project import Project
from .base import Document, Verifier

LONG_FLAG = re.compile(r"^--[A-Za-z][\w-]*$")
ENV_ASSIGNMENT = re.compile(r"^[A-Z_][A-Z0-9_]*=")
# Shell operators that end one command and start another.
SEPARATORS = re.compile(r"\s*(?:\|\||\||&&|;)\s*")

# Options every argparse program answers to without anyone declaring them.
IMPLICIT = frozenset({"--help"})


def options_in(line: str) -> Iterator[str]:
    """Option names in a command line — and nothing that merely looks like one.

    pipx's docs carry `pipx install pycowsay --pip-args="--no-cache-dir"`. Scanning that
    line with a regex finds `--no-cache-dir` and reports that pipx does not define it,
    which is true and beside the point: it is pip's option, sitting inside the *value* of
    one of pipx's. Six of the eight findings this verifier first produced were that, and
    the other two were the same thing inside single quotes.

    Two rules take all of them, and both are properties of shell syntax rather than
    guesses about intent: an option token never contains whitespace, so anything that
    does was quoted and is a value; and `--name=value` claims `--name` only. Everything
    after a bare `--` is positional by definition.
    """
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        # An unbalanced quote in a documentation snippet. Splitting naively would read
        # the inside of the broken quote as options, which is the bug this exists to fix.
        return

    for token in tokens:
        if token == "--":
            return
        if not token.startswith("--") or any(character.isspace() for character in token):
            continue
        name = token.split("=", 1)[0]
        if LONG_FLAG.match(name):
            yield name


# What a program prints when it has refused. argparse's own refusal is `usage:` followed
# by `prog: error: ...`, and everything else in the wild says `error` or `Traceback` too.
# Searched rather than anchored: argparse writes `pipx run: error: ambiguous option`, where
# the program name carries a space, and anchoring at the line start missed exactly that.
ERROR_OUTPUT = re.compile(r"(?i)(^\s*(?:usage:|traceback)|\berrors?:)")


def demonstrated_failures(span: Span) -> set[str]:
    """Commands in a transcript whose own recorded output is an error message.

    A transcript is prompt lines interleaved with what the program printed. Grouping each
    command with the output beneath it — up to the next prompt — is enough to tell a
    worked example from a warning about what not to type.
    """
    if not span.fenced:
        return set()
    failed: set[str] = set()
    current: str | None = None
    output: list[str] = []

    def close() -> None:
        if current is not None and any(ERROR_OUTPUT.search(line) for line in output):
            failed.add(current)

    for raw in span.text.split("\n"):
        line = raw.strip()
        if line.startswith(("$ ", "> ", "# ")):
            close()
            current, output = line[2:].strip(), []
        elif current is not None:
            output.append(raw)
    close()
    return failed


class DocumentedFlags(Verifier):
    name = "cli-flags"
    describes = "command-line options the documentation shows"

    def applies(self, project: Project) -> str | None:
        if not project.console_scripts:
            return (
                "this project declares no console scripts in pyproject.toml, so there is no "
                "command whose options a document could be describing"
            )
        return None

    def check(self, project: Project, documents: Iterable[Document]) -> Iterator[Finding]:
        known = argparse_flags(project)
        known.names |= wrapper_flags(project)
        for claim in self.extract(project, documents):
            yield self._judge(claim, known)

    def extract(
        self,
        project: Project,
        documents: Iterable[Document],
        commands: set[str] | None = None,
        package: str | None = None,
    ) -> Iterator[Claim]:
        """Every flag claim the documents make, before any judging.

        `commands` and `package` decide which command lines are *this project's*; by
        default they are read from the working pyproject. `history` passes the union of
        today's names and a sampled era's, because a line written when the command had
        its old name was a claim then and reading it back demands then's vocabulary.
        """
        if commands is None:
            commands = set(project.console_scripts)
        if package is None:
            package = project.name.replace("-", "_") if project.name else None

        seen: set[tuple[str, str]] = set()
        for document in documents:
            for span in spans(document.text):
                if document.silenced(span.line):
                    continue
                for line in self._our_command_lines(span, commands, package):
                    for flag in options_in(line):
                        key = (project.relative(document.path), flag)
                        if key in seen:
                            continue
                        seen.add(key)
                        yield Claim(
                            kind="cli-flag",
                            subject=flag,
                            doc=document.path,
                            line=span.line,
                            span=line.strip()[:120],
                        )

    def _our_command_lines(self, span: Span, commands: set[str], package: str | None) -> Iterator[str]:
        """Lines that invoke this project, and only those.

        A bare `--flag` in prose with no command attached is *not* accepted. It reads like
        the project's own option and usually is, but "usually" is the word this tool does
        not get to use: `--upgrade` and `--no-cache-dir` appear in plenty of READMEs
        belonging to pip rather than to the project documenting them.

        **A command shown failing is not a claim that it works.** pipx's tutorial prints

            $ pipx run pycowsay --py
            pipx run: error: ambiguous option: --py could match --python-args, ...

        to teach the reader what *not* to type. Reporting that pipx does not define `--py`
        is true, useless, and exactly what the paragraph already says. So in a transcript,
        a command whose own recorded output is an error is dropped along with its options.
        """
        failures = demonstrated_failures(span)
        for whole in command_lines(span):
            if whole in failures:
                continue
            # A pipeline is several commands, and the interesting one is rarely first.
            # tqdm's README is almost entirely `seq 9999999 | tqdm --bytes | wc -l`, and
            # looking only at the head of the line read every one of them as `seq`.
            for line in SEPARATORS.split(whole):
                yield from self._one_command(line, commands, package)

    def _one_command(self, line: str, commands: set[str], package: str | None) -> Iterator[str]:
        """Yield the line if its first word is one of this project's commands."""
        tokens = line.split()
        while tokens and ENV_ASSIGNMENT.match(tokens[0]):
            tokens = tokens[1:]
        if not tokens:
            return
        head = tokens[0].rsplit("/", 1)[-1]
        runs_the_module = (
            package is not None
            and head in {"python", "python3", "py"}
            and len(tokens) > 2
            and tokens[1] == "-m"
            and tokens[2].split(".")[0] == package
        )
        if head in commands or runs_the_module:
            yield line

    def _judge(self, claim: Claim, known: FlagSet) -> Finding:
        if claim.subject in known.names or claim.subject in IMPLICIT:
            return self.holds(claim, "defined in " + ", ".join(sorted(known.files)[:3]))

        if not known.names:
            return self.skip(
                claim,
                "no argument parser could be read from this project's source, so there is "
                "nothing to check the option against",
            )

        if not known.complete:
            return self.skip(
                claim,
                f"the option list read from the source is not known to be complete, so an "
                f"option missing from it is not evidence of anything — {known.reasons[0]}",
            )

        # argparse accepts any unambiguous abbreviation unless `allow_abbrev=False`, so a
        # documented `--dry` is a working way to write `--dry-run` and not a broken claim.
        # Found by pipx documenting `--py`, which matches three of its options and is
        # therefore genuinely refused — the prefix rule has to count, not just match.
        expansions = [name for name in known.names if name.startswith(claim.subject)]
        if len(expansions) == 1:
            return self.holds(claim, f"an unambiguous abbreviation of {expansions[0]}")
        if len(expansions) > 1:
            return self.broken(
                claim,
                f"ambiguous: it abbreviates {', '.join(sorted(expansions))}, so argparse "
                f"refuses it rather than choosing",
            )

        return self.broken(
            claim,
            f"no parser in this project defines it; the options it does define are "
            f"{', '.join(sorted(known.names)[:8])}" + (" and others" if len(known.names) > 8 else ""),
        )
