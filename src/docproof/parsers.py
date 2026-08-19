"""What options a program really accepts, read out of its source without running it.

**The problem this module exists to be honest about.** Reading `add_argument("--foo")`
calls out of an AST gives a set of options the program certainly accepts. It does *not*
give a set it certainly rejects, and those are different facts. A parser built in a loop,
or handed to a helper that adds to it, or assembled from a table of names, will still
answer to flags this never saw.

That distinction decides what may be reported. A documented flag found in the set is
confirmed. A documented flag *not* in the set is only drift if the set is known to be
complete — otherwise the honest answer is "I could not tell", and the reason is the
incompleteness itself.

So every result carries `complete`, and `complete` is false the moment anything is seen
that could add an option this cannot name.

Nothing here imports or runs the project. Running `prog --help` would give a complete
answer, and it would do it by executing whatever the project does at startup inside
somebody's CI. That is a strange thing for a linter to do, and the abstention above is
cheaper than the surprise.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from .project import Project

# Constructors that produce something you can call `.add_argument` on. `add_parser` is a
# subparser, `add_argument_group` and `add_mutually_exclusive_group` are containers whose
# `add_argument` lands on the parent parser.
PARSER_FACTORIES = frozenset(
    {
        "ArgumentParser",
        "add_parser",
        "add_argument_group",
        "add_mutually_exclusive_group",
    }
)


@dataclass
class FlagSet:
    """Options a project accepts, and whether this is all of them."""

    names: set[str] = field(default_factory=set)
    complete: bool = True
    reasons: list[str] = field(default_factory=list)
    """Why completeness could not be established. Empty when it could."""

    files: set[str] = field(default_factory=set)
    """Where the parsers were found, for the report."""

    def incomplete(self, reason: str) -> None:
        self.complete = False
        if reason not in self.reasons:
            self.reasons.append(reason)

    def __bool__(self) -> bool:
        return bool(self.names)


def _is_parser_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name in PARSER_FACTORIES


class _Scan(ast.NodeVisitor):
    """One module's worth of argparse evidence."""

    def __init__(self, flags: FlagSet, where: str) -> None:
        self.flags = flags
        self.where = where
        self.saw_parser = False
        self.parser_names: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802 - ast's naming
        """Remember which names hold a parser, so handing one away can be noticed."""
        if _is_parser_call(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.parser_names.add(target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast's naming
        if _is_parser_call(node):
            self.saw_parser = True
            self.flags.files.add(self.where)

        func = node.func
        self._check_handed_off(node, func)
        if isinstance(func, ast.Attribute) and func.attr == "add_argument":
            self._read_add_argument(node)
        elif isinstance(func, ast.Attribute) and func.attr == "parse_known_args":
            # A program that calls this accepts options it never declared and hands them
            # somewhere else. A documented option missing from the parser may be one of
            # those, so the list can never be authoritative about absence.
            self.flags.incomplete(
                f"{self.where} calls parse_known_args, so the program accepts options it does not declare"
            )

        self.generic_visit(node)

    def _check_handed_off(self, node: ast.Call, func: ast.expr) -> None:
        """A parser passed to something else can come back with options nothing here named.

        This is the "handed to a helper" half of the module docstring's completeness rule,
        which was documented and not implemented. mitmproxy builds its command line with
        `opts.make_parser(parser, "mode", short="m")` - the flags come from an option
        registry, not from any literal `add_argument`. Reading only the literals produced a
        six-option set that looked authoritative, and `--mode` and `--certs`, which plainly
        exist, came back contradicted in four of its documents at once.

        Over-firing here is the safe direction and the module already prefers it: an
        unnecessary incompleteness turns a possible finding into a missed one, never into a
        wrong one, and a wrong one is a pull request against someone else's project.
        """
        holder = (
            func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None
        )
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            if not isinstance(argument, ast.Name) or argument.id not in self.parser_names:
                continue
            if argument.id == holder:
                continue  # `parser.foo(parser)` is still the parser's own method
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "a call")
            self.flags.incomplete(
                f"{self.where} passes the parser to {called}(), which can add options no static read can name"
            )
            return

    def _read_add_argument(self, node: ast.Call) -> None:
        if any(isinstance(argument, ast.Starred) for argument in node.args):
            self.flags.incomplete(
                f"{self.where} unpacks a list into add_argument, so the option names are "
                f"not visible without running it"
            )
            return
        if not node.args:
            self.flags.incomplete(f"{self.where} calls add_argument with no positional name")
            return

        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if argument.value.startswith("-"):
                    self.flags.names.add(argument.value)
                # A positional such as `path` is not an option and not a claim about one.
            else:
                self.flags.incomplete(
                    f"{self.where} builds an option name from an expression rather than a "
                    f"literal, so it cannot be named here"
                )


def argparse_flags(project: Project) -> FlagSet:
    """Every long or short option this project's argparse code names literally.

    Subparsers are unioned into one set rather than tracked per command. That
    over-approximates — an option valid only on one subcommand will confirm a document
    that attaches it to another — and the direction is deliberate: over-approximating
    turns a possible finding into a missed one, never into a wrong one.
    """
    flags = FlagSet()
    seen_a_parser = False
    for path in project.python_files:
        module = project.parse(path)
        where = project.relative(path)
        if module is None:
            # A file that would not parse might have been the one defining the parser.
            flags.incomplete(f"{where} could not be parsed, so anything it defines is unseen")
            continue
        if "argparse" not in path.read_text(encoding="utf-8", errors="replace"):
            continue
        scan = _Scan(flags, where)
        scan.visit(module)
        seen_a_parser = seen_a_parser or scan.saw_parser

    if not seen_a_parser:
        # **A set with no parser behind it can never be complete**, and saying so is the
        # difference between abstaining and inventing sixty-four findings. datasette's CLI
        # is click; there is no argparse in its package at all. What made the list look
        # authoritative was one `--directory` scraped out of a shell script at the repo
        # root, so `names` was non-empty, nothing had marked it incomplete, and every real
        # click option in its documentation came back contradicted.
        flags.incomplete(
            "no argparse parser was found in this project, so its command line is built "
            "with something this cannot read — click, typer, cleo or a hand-rolled parser"
        )
    for command, package in _console_script_packages(project):
        elsewhere = _built_with_something_else(project, package)
        if elsewhere:
            flags.incomplete(
                f"`{command}` is `{package}`, which imports {elsewhere}, so its options are "
                f"declared where this cannot read them however much argparse the rest of the "
                f"repository contains"
            )
    return flags


# **`seen_a_parser` is repository-wide, and a monorepo is not one program.** The datasette
# rule above catches a project with NO argparse. It does not catch `unslothai/unsloth`, whose
# console script is a typer app in `unsloth_cli/` and whose backend, tests and scripts contain
# enough argparse for 153 flags and a `complete: True`. Its README shows
# `unsloth start claude --as-subagent`, declared at `unsloth_cli/commands/start.py:340` as
# `typer.Option(False, "--as-subagent", ...)`, and the verifier reported it BROKEN with the
# sentence "no parser in this project defines it".
#
# That is the one thing this file's docstring promises cannot happen: *"when it says no, a flag
# it has not seen is unjudged."* It said yes, from the wrong parsers.
#
# So completeness is asked of the COMMAND, not of the repository. The console script names its
# module; if that package reaches for click or typer, the argparse set cannot describe it.
CLI_FRAMEWORKS = ("typer", "click", "cleo", "docopt", "fire")


def _console_script_packages(project: Project) -> list[tuple[str, str]]:
    """(command, top-level module) for each declared console script, deduplicated."""
    out, seen = [], set()
    for command, target in project.console_scripts.items():
        package = target.split(":", 1)[0].split(".", 1)[0].strip()
        if package and (command, package) not in seen:
            seen.add((command, package))
            out.append((command, package))
    return out


def _built_with_something_else(project: Project, package: str) -> str:
    """Which CLI framework this package imports, or empty.

    Reads the package's own files only. A framework imported by a sibling tool in the same
    repository says nothing about this command, and widening it to the whole tree would
    silence the verifier on every repository that vendors an example.
    """
    directory = project.root / package
    if not directory.is_dir():
        single = project.root / (package + ".py")
        files = [single] if single.is_file() else []
    else:
        files = [p for p in directory.rglob("*.py") if p.is_file()]
    found: set[str] = set()
    for path in files[:400]:  # a package with more files than this has been found already
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name in CLI_FRAMEWORKS:
            if re.search(r"^\s*(?:import|from)\s+" + name + r"\b", text, re.MULTILINE):
                found.add(name)
    return " and ".join(sorted(found))


def wrapper_flags(project: Project) -> set[str]:
    """Options named in shell or PowerShell wrappers shipped beside the program.

    A project that ships `prog.sh` forwarding to Python often documents flags the wrapper
    handles itself. Those are real and argparse has never heard of them.
    """
    found: set[str] = set()
    for pattern in ("*.sh", "*.ps1", "*.bat", "*.cmd"):
        for path in sorted(Path(project.root).glob(pattern)):
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in text.replace("=", " ").split():
                if token.startswith("--") and len(token) > 2 and token[2].isalpha():
                    found.add(token.strip("\"'`,;)"))
    return found
