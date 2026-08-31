# docproof

Prove your documentation against your code.

<!-- docproof: skip -->
Your README says the entry point is `src/pkg/main.py`. You moved it eight months ago.
Nothing failed, nobody noticed, and the next person to read that line lost twenty minutes.

`docproof` reads the checkable claims out of your documentation and checks each one
against your project. It finds real drift, it explains every finding with a receipt, and
when it cannot be sure it says so instead of guessing.

```
$ docproof
docproof 0.1.0 — click, 38 document(s)
   describing the past, not judged: CHANGES.md, docs/changes.md

BROKEN paths: 1 broken (6 checked, 47 skipped)
-- cli-flags: not applicable — this project declares no console scripts in pyproject.toml,
   so there is no command whose options a document could be describing
ok versions: 0 checked
ok symbols: 4 checked

Claims the code contradicts
===========================

  docs/contributing.md:28  [path]
    says   `.github/workflows/test-flask.yaml`
    but    deleted in 97b300c (2026-04-03, "add zizmor to scan workflows") and never
           restored, and the documentation still points at it

1 broken, 10 checked, 47 not judged.
```

**That is a verbatim run against `pallets/click` at `00e592c`, and the line wraps are the
only edit.** `docs/contributing.md` told contributors that a CI workflow runs Flask's test
suite against every change. The workflow was gone, and the directory held six others and not
that one.

The header says `0.1.0` because that is what the tool printed at the time. It read its own
version from the wrong place, so every release up to and including `0.1.2` announced itself
as `0.1.0`. Fixed in [#9](https://github.com/melbinjp/docproof/pull/9), which is why
`--version` and the report header now agree. The block is left uncorrected because it is a
real run, and editing the output would make it a mock-up: the same move as editing a
document instead of fixing the code.

**It is pinned to a commit because the finding no longer exists.** It was reported as
[click#3766](https://github.com/pallets/click/issues/3766) and closed as completed on
2026-08-15. A maintainer replied that the removal had not been deliberate, and that it
"probably got overwritten" while configs were being copied between projects
([kdeldycke](https://github.com/pallets/click/issues/3766)). The fix was `3ee9309`,
*"Run Flask's test suite in the nightly workflow"*: they restored the CI job rather than
editing the sentence.

That is the case for checking documentation against code, and it is not the case anyone
expects. The stale sentence was not the problem. It was the only surviving evidence that a
CI job had been deleted by accident four months earlier, and nothing else in the repository
was still saying so.

Two other things in that output are the design rather than decoration. Two changelogs were
set aside without being read, because a changelog describing a directory that has since
moved is correct and always will be. And `cli-flags` reported itself **not applicable**
rather than reporting zero problems: click is a library with no console scripts, and a
clean bill of health nobody examined is worth less than nothing.

## Install and run

```bash
pip install docproof

docproof                 # check the project you are standing in
docproof path/to/project
docproof --show-skips    # and everything it declined to judge, with reasons
docproof --list          # the available checks
```

From a checkout instead, which is what you want if you are changing it:

```bash
git clone https://github.com/melbinjp/docproof && cd docproof
pip install -e .
```

To run the suite, which is the thing worth checking before trusting any of the above:

```bash
pip install -e ".[dev]"
pytest
```

`pip install -e .` alone gets you the tool but not `pytest`, so the extra is not optional
if you want to verify rather than take this document's word for it.

Exit code is `0` when nothing is contradicted, `1` when something is, or when a check
that applies to your project found nothing at all to check, which means its extraction
stopped matching and is not a pass either.

### Adding it to a project that already has drift

A gate that fails on day one gets removed on day one. `--exit-zero` prints the findings and
leaves the run green, so you can adopt this while you are still working through them:

```yaml
- uses: melbinjp/docproof@v0.2.4
  with:
    fail-on-findings: false
```

Flip it back when you are level, and the gate keeps you there.

**It suppresses the contradiction exit only.** A check that stopped checking still fails,
because that is not a finding you are deferring, it is the tool saying it went blind, and
there is no version of *later* that makes a blind check acceptable. The whole reason to run
this is that a green check which judged nothing is worse than no check, and an opt-out that
could buy one would defeat the tool with its own flag.

## Put it in your CI

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0        # docproof needs history to tell drift from an example
- uses: melbinjp/docproof@v0.2.4
```

**Both lines are load-bearing, and the action refuses to run without the first.**
`actions/checkout` gives you depth 1 unless you ask otherwise, and a clone with its history
cut off cannot tell a deleted file from one that never existed. Measured on `pallets/click`:
a full clone reports `1 broken` and exits 1, and the same repository at `--depth 1` reports
"Nothing contradicted" and exits **0**. A silent version of this check would hand you a
permanently green gate that had judged nothing, so it fails with the one-line fix in the
message instead. [Requirements](#requirements) has the rest.

**Pin it to a commit rather than to the tag.** `melbinjp/docproof@v0.2.4` is a tag, and a
tag can be repointed after you have read the code behind it. Anyone able to push here,
including anyone who takes this account, could move it onto something else and your CI would
run that without a diff for you to review. Resolve the tag once, and pin what it resolved to:

```bash
git ls-remote https://github.com/melbinjp/docproof refs/tags/v0.2.4
```

```yaml
- uses: melbinjp/docproof@<the 40 characters that printed>   # v0.2.4
```

This file cannot print that SHA for you: the commit it would name is the one this file is
in. An earlier version of this section hardcoded one anyway, which pinned the release before
it and would have gone stale at every release after.

Raised by [@fschutt](https://github.com/fschutt) while security-reviewing this action
before putting it into `azul`'s CI, which is the right order to do those two things in.

**It only reads.** A run shells out to `git` for history and opens documents for reading,
and that is the whole of its contact with your tree: nothing written, nothing moved,
nothing created, including inside the project being checked. So it is safe ahead of any
step that expects a clean checkout. That is not a promise in prose. `tests/test_read_only.py`
runs a full check over a real repository with real drift and fails if one tracked byte
changed, or one untracked file appeared, afterwards. The guarantee is there because
@fschutt asserted it in `azul`'s CI before this repository had documented or tested it.

Adopting on a project that already has drift, which is most of them:
`fail-on-findings: false` prints every finding and leaves the run green while you work
through them. [What that suppresses, and the one thing it
will not](#adding-it-to-a-project-that-already-has-drift).

Everything below is why you would want that.

## What it checks

Two things, each done properly:

**`paths` works on any repository, not just Python ones.** It reads documentation and git
history, and neither is language-specific. The other three checks read `pyproject.toml` and
say so when there isn't one, so pointing `docproof` at a Go or Rust project is not a
degraded mode: it is the path check running and the rest abstaining, out loud.

Measured, rather than hoped: sixteen well-known projects across Go, Rust, JavaScript, Ruby
and PHP (cobra, gin, caddy, helm, ripgrep, bat, clap, express, axios, prettier, jekyll,
sinatra, symfony/console and others) produced **one finding, fifteen clean, none errored**:
a broken link in `prettier`'s contributor guide, pointing at a file deleted in January.

**`paths`**: files and directories the documentation points at, including the leaves of
ASCII directory diagrams.
<!-- docproof: skip -->
Those are reconstructed to full paths first, since `server.py`
on its own is not a claim anybody can check; `src/pkg/server.py` is. Box-drawing and
`|--` styles both read, as does plain indentation at whatever stride the diagram uses.

**A path is called broken only when the repository can be shown to have had it and
deleted it,** and the commit that deleted it is the receipt. That rule is not an
implementation detail; it is the difference between finding drift and arguing with a
tutorial, and it was chosen by measurement.

Run over twenty well-known Python projects, the first version produced 187 findings and
every one of them was wrong. Documentation is full of paths that were never meant to be
here: click tells you to create `src/hello/__init__.py` in *your* project, flask's
tutorial has you write `tests/test_factory.py`, fastapi's release notes correctly describe
a directory that moved four versions ago. History separates those from real drift: an
illustration has never existed here, and a file that moved has a commit that moved it.

The corpus this was measured against, and what each verdict is for, are in
[METHOD.md](METHOD.md).
## Configuration

Some documents are deliberately not descriptions of the present. A design note, an RFC, a
build guide written in the future tense: reporting drift in those is arguing with a
decision you already made.

```toml
[tool.docproof]
exclude = ["agent.md", "docs/rfc/*.md"]
docs = ["CONTRIBUTING/*.md"]
disable = []
```

Or say it in the document itself, where a reader can see it:

```markdown
<!-- docproof: skip-file — this describes the design, not the tree -->
```

For one paragraph rather than a whole file (an example, a hypothetical, a path belonging
to something else), the same marker without `-file` covers the paragraph it introduces:

```markdown
<!-- docproof: skip -->
Suppose your entry point is `src/pkg/main.py` and you move it.
```

This README uses it twice, for exactly that reason. It was the first thing running
`docproof` on `docproof` found.

### What gets read

Top-level documentation files, plus everything under `doc/` or `docs/`. Not every Markdown
file in the tree: a fixture, a vendored README or a changelog fragment deep in a package is
not a promise the project is making.

**Every run says what that left out**, because the scope being deliberate does not make its
silence harmless:

```
docproof 0.2.4 - myproject, 6 document(s)
   41 documentation file(s) elsewhere in the tree were NOT read; the default scope is top-level files plus doc/ and docs/
     guides/ 22, website/ 14, handbook/ 4, .github/ 1
     read them too with --docs 'guides/**/*.md' or [tool.docproof] docs = ["guides/**/*.md"]
```

and when there is nothing outside the scope it says that instead, so the line is never
missing:

```
   every documentation file in the tree was in scope
```

Only files the project **tracks in git** are counted. A gitignored tree is not your
documentation, and the alternative measures the wrong thing badly: on one repository that
keeps 217 cloned repositories for testing, walking the filesystem reported 38,402 unread
documents against a true figure of 294.

What it already skips without being told, and the one thing you still have to say
yourself, are in [METHOD.md](METHOD.md).
## Requirements

`docproof` requires Python 3.10 or newer, and `git` on the path, and **full history**.

That sentence used to begin "Python 3.10 or newer, and…", and the `versions` check below
declined to judge it: a requirement with no stated subject could be about anything. Naming
the thing that has the requirement costs one word and turns a sentence nobody was checking
into one that fails CI the day it stops being true.

That last one matters more than it sounds. GitHub Actions checks out at depth 1 by
default, and a clone with its history cut off cannot tell a deleted file from one that
never existed, so `docproof` reports that and judges nothing rather than guessing:

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0        # docproof needs history to tell drift from an example
- uses: melbinjp/docproof@v0.2.4
```

**The action refuses to run without `fetch-depth: 0`, on purpose.** Measured on
`pallets/click`: a full clone reports `1 broken` and exits 1, and the same repository
cloned at `--depth 1` reports "Nothing contradicted" and exits **0**. Since
`actions/checkout` gives you depth 1 unless you ask otherwise, a silent version of this
check would hand you a permanently green gate that had judged nothing. It fails with the
one-line fix in the message instead. CI here runs that refusal as a test.

*Both halves of this were wrong once. This block read `pipx run docproof`, and the install
section above opened by saying the package was not published yet, and neither survived
docproof actually going up on PyPI on 24 August 2026. A tool whose whole argument is that
documentation should be checkable does not get to ship an install instruction that does not
work. The `self` job installs through the action above so the snippet cannot rot again
without the build going red, and `RELEASING.md` names both places as things the shipping
commit has to change.*

There are no dependencies at all on Python 3.11+; on 3.10 it installs `tomli` to read
`pyproject.toml`.

Without git, `docproof` cannot tell a file a project ships from one it generates, so it
reports that (in git's own words, not a guess at the cause) and skips every judgement
that would have depended on it. It does not fall back to a weaker rule: a check that means
different things on different machines is worse than one that abstains.

Changelogs, release notes and `changelog.d/` fragments are never judged. A changelog
saying "0.68 moved `docs_src/websockets`" is correct and always will be, however many
times that directory moves afterwards.

## Layout

```
docproof/
├── src/docproof/
│   ├── model.py        claims, verdicts, and why there are three
│   ├── docs.py         finding documents and the code spans in them
│   ├── tree.py         reading ASCII directory diagrams
│   ├── project.py      what the project is, read from the project
│   ├── vcs.py          asking git what it ships
│   ├── config.py       documents that are not promises
│   ├── report.py       findings, receipts, and the exit code
│   ├── parsers.py      what options a program really accepts
│   └── verifiers/
│       ├── paths.py        the path check
│       ├── cli_flags.py    the option check
│       ├── versions.py     the install-metadata check
│       └── symbols.py      the import check
└── tests/
```

## What it has found

[FINDINGS.md](FINDINGS.md) lists the documentation defects docproof has surfaced in projects
it does not maintain, fourteen of them merged by the project's own maintainers. The list is
generated from the live state of each filing rather than kept by hand, and it says plainly what
the tool found versus what a person noticed while reading its output.

## Writing about it

Notes from running this against real repositories, including the things it got wrong:

- [A clean verdict over five per cent of a repository is not a clean repository](https://log.wecanuseai.com/p/a-clean-verdict-over-five-per-cent.html)
  - three ways this tool reported success while blind in one evening, why a translated
  documentation tree produced twelve false positives, and why every report says what it read.

More at [log.wecanuseai.com](https://log.wecanuseai.com/).

## License

MIT.
