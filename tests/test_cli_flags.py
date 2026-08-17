"""Judging documented command-line options.

The verifier's first run over twenty public Python projects produced nine findings and
every one was wrong. Each test below is named for what produced it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.docs import Span, read
from docproof.model import Verdict
from docproof.project import Project
from docproof.verifiers.base import Document
from docproof.verifiers.cli_flags import DocumentedFlags, demonstrated_failures, options_in

PYPROJECT = """
[project]
name = "toolkit"
version = "0.1.0"
[project.scripts]
toolkit = "toolkit.cli:main"
"""

PARSER = """
import argparse


def build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="toolkit")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="-")
    return parser
"""


def check(repo: Path) -> dict[str, tuple[Verdict, str]]:
    project = Project(root=repo)
    documents = [Document(path=p, text=read(p)) for p in sorted(repo.glob("*.md"))]
    outcome = DocumentedFlags().run(project, documents)
    return {f.claim.subject: (f.verdict, f.detail) for f in outcome.findings}


def toolkit(readme: str, parser: str = PARSER) -> dict[str, str]:
    return {"pyproject.toml": PYPROJECT, "README.md": readme, "toolkit/cli.py": parser}


def test_a_documented_option_that_exists_holds(make_repo: Callable[..., Path]):
    repo = make_repo(toolkit("Run `toolkit --dry-run` to see what would happen.\n"))
    assert check(repo)["--dry-run"][0] is Verdict.HOLDS


def test_a_documented_option_that_does_not_exist_is_broken(make_repo: Callable[..., Path]):
    repo = make_repo(toolkit("Run `toolkit --dryrun` first.\n"))
    verdict, detail = check(repo)["--dryrun"]
    assert verdict is Verdict.BROKEN
    assert "--dry-run" in detail


def test_another_program_s_option_is_not_our_claim(make_repo: Callable[..., Path]):
    """`pip install --upgrade toolkit` documents pip's option, not toolkit's."""
    repo = make_repo(toolkit("Install with `pip install --upgrade toolkit`.\n"))
    assert "--upgrade" not in check(repo)


def test_an_option_inside_a_quoted_value_is_not_a_claim(make_repo: Callable[..., Path]):
    """pipx's docs carry `pipx install pycowsay --pip-args="--no-cache-dir"`.

    Six of this verifier's first eight findings were pip options sitting inside the value
    of one of pipx's own, and two more were the same thing in single quotes.
    """
    readme = "Try `toolkit --output=\"--no-cache-dir\"` and `toolkit --output '--trusted-host x'`.\n"
    results = check(make_repo(toolkit(readme)))
    assert "--no-cache-dir" not in results
    assert "--trusted-host" not in results


def test_a_command_shown_failing_is_not_a_claim(make_repo: Callable[..., Path]):
    """pipx's tutorial shows `pipx run pycowsay --py` printing an ambiguity error, to
    teach the reader what not to type."""
    readme = (
        "Do not do this:\n\n```console\n$ toolkit --dr\n"
        "toolkit: error: ambiguous option: --dr could match --dry-run, --draft\n```\n"
    )
    assert "--dr" not in check(make_repo(toolkit(readme)))


def test_program_output_is_not_another_command(make_repo: Callable[..., Path]):
    """The error line begins with the program's own name, so a reader of lines rather
    than of transcripts takes it for a second invocation and reads the flag out of the
    message complaining about that flag."""
    span = Span(
        text="$ toolkit --dr\ntoolkit: error: ambiguous option: --dr\n",
        line=1,
        fenced=True,
        info="console",
    )
    assert demonstrated_failures(span) == {"toolkit --dr"}


def test_an_option_in_a_pipeline_is_found(make_repo: Callable[..., Path]):
    """tqdm's README is almost entirely `seq 9999999 | tqdm --bytes | wc -l`, and looking
    only at the head of the line read every one of them as `seq`."""
    repo = make_repo(toolkit("```console\n$ cat f | toolkit --dry-run | wc -l\n```\n"))
    assert check(repo)["--dry-run"][0] is Verdict.HOLDS


def test_an_unambiguous_abbreviation_holds(make_repo: Callable[..., Path]):
    """argparse accepts any unambiguous prefix unless told not to, so `--dry` works."""
    repo = make_repo(toolkit("Run `toolkit --dry`.\n"))
    verdict, detail = check(repo)["--dry"]
    assert verdict is Verdict.HOLDS
    assert "abbreviation" in detail


def test_an_ambiguous_abbreviation_is_broken(make_repo: Callable[..., Path]):
    parser = PARSER.replace("    return parser", '    parser.add_argument("--dropped")\n    return parser')
    repo = make_repo(toolkit("Run `toolkit --dr`.\n", parser=parser))
    verdict, detail = check(repo)["--dr"]
    assert verdict is Verdict.BROKEN
    assert "ambiguous" in detail


def test_a_parser_that_forwards_unknown_options_cannot_be_authoritative(
    make_repo: Callable[..., Path],
):
    """pipx forwards what it does not recognise to pip. A program calling
    `parse_known_args` accepts options it never declared, so a documented option missing
    from the parser is not evidence of anything."""
    parser = PARSER.replace("    return parser", "    parser.parse_known_args()\n    return parser")
    repo = make_repo(toolkit("Run `toolkit --whatever`.\n", parser=parser))
    verdict, detail = check(repo)["--whatever"]
    assert verdict is Verdict.SKIPPED
    assert "parse_known_args" in detail


def test_a_parser_handed_to_a_helper_blocks_judgement(make_repo: Callable[..., Path]):
    """mitmproxy registers its command line through `opts.make_parser(parser, "mode")`, so
    the flags come from an option registry and not from any literal `add_argument`. Reading
    only the literals produced a set that looked authoritative, and `--mode` and `--certs`,
    which plainly exist, came back contradicted in four of its documents at once."""
    parser = PARSER.replace(
        "    return parser", '    registry.make_parser(parser, "mode")\n    return parser'
    )
    repo = make_repo(toolkit("Run `toolkit --mode transparent`.\n", parser=parser))
    verdict, detail = check(repo)["--mode"]
    assert verdict is Verdict.SKIPPED
    assert "passes the parser to make_parser()" in detail


def test_a_parser_s_own_methods_are_not_handing_it_away(make_repo: Callable[..., Path]):
    """The guard above must not fire on ordinary use, or every argparse project becomes
    unjudgeable and the verifier stops saying anything at all."""
    repo = make_repo(toolkit("Run `toolkit --dry-run`.\n"))
    assert check(repo)["--dry-run"][0] is Verdict.HOLDS


def test_an_option_name_built_from_an_expression_blocks_judgement(
    make_repo: Callable[..., Path],
):
    parser = PARSER.replace("    return parser", '    parser.add_argument("--" + name)\n    return parser')
    repo = make_repo(toolkit("Run `toolkit --whatever`.\n", parser=parser))
    verdict, detail = check(repo)["--whatever"]
    assert verdict is Verdict.SKIPPED
    assert "not known to be complete" in detail


def test_a_project_with_no_console_scripts_is_not_applicable(make_repo: Callable[..., Path]):
    """click, jinja, requests and attrs are libraries. Reporting "0 problems" for a CLI
    they do not have would be a clean bill of health nobody examined."""
    repo = make_repo(
        {
            "pyproject.toml": '[project]\nname = "lib"\nversion = "0"\n',
            "README.md": "A library.\n",
            "lib/__init__.py": "",
        }
    )
    outcome = DocumentedFlags().run(
        Project(root=repo), [Document(path=repo / "README.md", text="A library.\n")]
    )
    assert outcome.applicable is False
    assert "console scripts" in outcome.reason


def test_options_are_read_from_tokens_not_from_the_raw_line():
    assert list(options_in('prog --output="--no-cache-dir"')) == ["--output"]
    assert list(options_in("prog --flag -- --not-an-option")) == ["--flag"]
    assert list(options_in("prog --a '--b --c'")) == ["--a"]


def test_a_project_whose_cli_is_not_argparse_is_never_judged(make_repo: Callable[..., Path]):
    """datasette's CLI is click, and there is no argparse in its package at all.

    What made its option list look authoritative was a single `--directory` scraped out of
    a shell script at the repo root: `names` was non-empty, nothing had marked the set
    incomplete, and every real click option in its documentation came back contradicted.
    Sixty-four findings, all wrong, from one missing guard.
    """
    files = {
        "pyproject.toml": PYPROJECT,
        "README.md": "Run `toolkit --serve`.\n",
        "toolkit/cli.py": "import click\n\n\n@click.command()\ndef main():\n    pass\n",
        "run.sh": "#!/bin/sh\nexec toolkit --directory .\n",
    }
    verdict, detail = check(make_repo(files))["--serve"]
    assert verdict is Verdict.SKIPPED
    assert "no argparse parser" in detail
