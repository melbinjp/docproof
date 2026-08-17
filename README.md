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

Claims the code contradicts
===========================

  docs/contributing.md:28  [path]
    says   `.github/workflows/test-flask.yaml`
    but    deleted in 97b300c (2026-04-03, "add zizmor to scan workflows") and never
           restored, and the documentation still points at it

1 broken, 6 checked, 47 not judged.
```

**That is a verbatim run against pallets/click, and you can check every word of it
yourself.** The line wraps are the only edit. `docs/contributing.md` tells contributors
that a CI workflow runs Flask's test suite against every change; that workflow was deleted
in April, and the directory holds six others and not that one.

Two other things in that output are the design rather than decoration. Two changelogs were
set aside without being read, because a changelog describing a directory that has since
moved is correct and always will be. And `cli-flags` reported itself **not applicable**
rather than reporting zero problems — click is a library with no console scripts, and a
clean bill of health nobody examined is worth less than nothing.

## Why it is not another LLM documentation reviewer

There are several tools that hand your README to a model and ask whether it looks right.
They find real things. They also disagree with themselves between runs, and they produce
findings you have to investigate before you can believe them — which is how a check ends
up advisory, and how an advisory check ends up muted.

`docproof` has no model in it, and no network. Every verdict comes from asking the project
a question with one answer: did a commit delete this path, does `.gitignore` match it,
does an `add_argument` call name this option. Run it twice and you get the same output.
That is what makes it safe as a required check rather than a report somebody reads on
Fridays.

## The three-verdict rule

Most checkers can only pass or fail, so when they cannot locate a claim they have to guess,
and a guess in either direction is a lie: guessing pass hides drift, guessing fail trains
you to ignore the tool. `docproof` has a third verdict, and the design turns on it.

|  | means |
|---|---|
| **holds** | the project agrees with the document |
| **broken** | the project contradicts it — the only verdict that fails a run |
| **skipped** | it could not be checked reliably, and guessing was refused |

The property this buys is worth stating directly:

> **Rewording a sentence makes a check skip. Changing the code it describes makes a check
> fail.**

You can edit prose freely without ever turning CI red, and you cannot quietly break a
documented path.

Every skip carries a reason and `--show-skips` prints all of them, because a checker that
silently skips everything looks exactly like a clean one.

## What it checks

Two things, each done properly:

**`paths`** — files and directories the documentation points at, including the leaves of
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
a directory that moved four versions ago. History separates those from real drift — an
illustration has never existed here, and a file that moved has a commit that moved it.

### What it scores on forty repositories

The current version, run over forty well-known Python projects with full history:

| | |
|---|---|
| Repositories | 40 |
| Documents read | 3,138 |
| Claims examined | 6,734 |
| — confirmed | 2,165 |
| — **contradicted** | **5** |
| — not judged, with a reason | 4,564 |
| Of the 5: genuine | **2** |
| Of the 5: wrong | **3** |

Those are counted, not estimated. The large "not judged" column is the design working
rather than failing — most of it is *"this repository has never had this path"*, which is
what a tutorial's example looks like from the inside.

**Held on thirteen repositories it was never tuned on.** The rules above were built against
those forty. The honest test of a checker is a disjoint set, so it was then run over
thirteen more (`starlette`, `sanic`, `aiohttp`, `anyio`, `cattrs`, `msgspec`, `invoke`,
`bottle`, `pendulum`, `falcon`, `tornado`, `faker`, `paramiko`) — 321 documents, 709
claims, 424 confirmed. That pass found **one real bug** — `anyio`'s install page said
Python 3.8 while its `pyproject.toml` requires 3.10 — and **one false positive of a new
kind**: `falcon`'s tutorial says `$ touch tests/__init__.py`, an instruction to the reader,
and `falcon` happened to have deleted its own `tests/__init__.py` in 2019. The fix (a path
that a `touch`/`mkdir` command *creates* is not a claim that it exists) was measured across
all fifty-three repositories before it was written: seven such operands, every one a
reader-project path, exactly one of them a live false positive. After it, the out-of-sample
set is **zero false positives**, and these forty are unchanged.

That is not zero and this README is not going to round it to zero. The two genuine ones:
click's `docs/contributing.md` tells contributors that `.github/workflows/test-flask.yaml`
runs Flask's suite against every change — that workflow was deleted in April, and the
directory holds six others and not that one. And datasette's README tells readers it needs
Python 3.8 when `pyproject.toml` requires 3.10.

An earlier version of this table said **4** genuine, and the two it lost are worth the
paragraph. bandit keeps documentation pages for plugins it removed years ago, and each
opens with *"This plugin has been removed."* — deliberate tombstones, kept on purpose so
old links keep resolving. Reporting a stale example path inside one is not finding drift;
it is arguing with a decision the maintainers already made and wrote down. Pages that open
by declaring their own subject removed are now treated like changelogs: history, not
promises. The rule stayed narrow after reading every candidate in the corpus — *deprecated*
is not *removed*, because a deprecated module still exists and its documentation still
makes promises that can rot.

**The three wrong ones are all the same thing**, and it is the honest limit of the design:
*an illustration of the reader's project whose path happens to have existed here once.*
`build`'s docs show an example `.github/workflows/build.yml` for your project, and `build`
itself had a file by that name in 2020. pytest's explanation of `sys.path` sketches a
`testing/` layout that pytest really did have, in 2010. Nothing in the document
distinguishes those from a stale reference, and rather than guess, `docproof` reports them
and lets you dismiss them — the receipt names the commit, so dismissing takes one look.

An obvious-looking fix is to ask whether the document was written *after* the deletion, on
the theory that an author who writes a path they just deleted must have meant it as an
example. It was tested against the finding above before being written, and it does not
hold. click deleted that workflow in `97b300c` on 2026-04-03. `docs/contributing.md` was
then edited on 2026-04-10 in `32ac271`, *"Compile Click-specific guidelines"* — somebody
working on that exact file, a week later — and the stale sentence survived it.

Documentation does not rot because nobody looks at it. It rots because looking at a file
is not the same as re-reading every claim in it, which is the entire reason to have a
machine do the second thing.

**`cli-flags`** — command-line options the documentation shows, checked against the
options the program's `argparse` code actually defines. Two things have to hold before a
missing option counts as drift, and both are about evidence:

* **The command has to be yours.** `pip install --upgrade yourtool` documents pip's
  option. Attribution comes from the console scripts you declare in your own
  `pyproject.toml`, and pipelines count — `seq 100 | yourtool --bytes` is your command.
* **The option list has to be provably complete.** A parser built in a loop, handed to a
  helper, or calling `parse_known_args` can accept options no static read can name. When
  that is so, an option missing from the list is *unjudged* and the reason is said out
  loud. Unambiguous abbreviations are honoured, because argparse honours them.

It also declines to read options out of a quoted value (`--pip-args="--no-cache-dir"` is
pip's option inside yours) and out of a command the documentation is showing *failing*,
which is how a tutorial teaches you what not to type.

**`versions`** — what the documentation promises about *installing*, against the metadata
that decides it. Two claims, both chosen because `pyproject.toml` answers them completely
rather than partially:

* **"`yourpkg` requires Python 3.8 or newer"** against `requires-python`. When the
  documented minimum is below the declared one, `pip` refuses on exactly the versions the
  README invites, and the reader discovers it instead of the author.
* **`pip install yourpkg[extra]`** against `[project.optional-dependencies]`, which is the
  entire set of extras that exist. An extra outside it is not a nuance — the install
  command in the README does not work. Unless the table is `dynamic`, in which case the
  set is not provably complete and the claim goes unjudged, exactly as with flags.

The rule that makes it usable is **the sentence has to be about your project.** Run loosely
over forty repositories, "requires Python 3.x" matched seventeen places and disagreed with
`pyproject.toml` four times — of which one was real. The other three were a sentence about
a *GitHub Action's* feature, quoted error output about a *dependency*, and a *toolchain*
that shares the project's name. Judging only sentences whose subject is the distribution
name itself leaves eight claims, seven holding and one contradiction, and that one is real:

```
  README.md:39  [python-requirement]
    says   `3.8`
    but    requires-python = '>=3.10', so pip refuses to install on Python 3.8. The
           document invites a reader the package turns away; the minimum has moved to 3.10
```

The nine sentences it declines are printed as skips naming the subject they *did* find, so
"it decided not to" and "it stopped working" stay distinguishable.

This verifier is also the one that says its own silence means nothing. Twenty of the forty
repositories document neither claim, and none of them is broken — so unlike `paths`, finding
nothing here is ordinary rather than evidence the extraction has died. Encoding that is the
difference between a check and a check that fails half a healthy corpus.

**`symbols`** — `from yourpkg import Thing` in the documentation, against what `yourpkg`
actually defines, read from its source and never imported. The soundness problem here is a
step past `versions`': there are three distinct ways Python lets an import succeed without
the name ever being written down as a binding in the package's own source, and a checker
that only knows one of them reports real, correct code as broken.

* **Implicit submodule import.** `from PIL import Image` works because `PIL/Image.py`
  exists as a file, whether or not `PIL/__init__.py` ever imports it.
* **`__getattr__` (PEP 562), and the idiom that predates it.** pydantic's public API and
  pygments' lexer and formatter registries are both built on a module that computes an
  attribute when asked rather than binding it up front — pygments predates PEP 562 and
  gets there by swapping in a `types.ModuleType` subclass, which is the same trick under a
  different name. Either way, "not found" cannot be proven.
* **`from ... import *`**, the identical incompleteness `versions`' extras table already
  had to account for.

Measured on the same forty repositories `versions` was: **1,859 documented imports from a
project's own package, 1,428 resolved directly, 430 landed in one of the three categories
above, and exactly one disagreement survived** — marshmallow's own upgrade guide, showing
`from marshmallow import MarshallingError` to illustrate the API it removed in 3.0. That
sentence is correct about the release it describes and always will be, which is what
widened the historical-document list below to recognise upgrade and migration guides
alongside changelogs, rather than adding a fourth escape hatch to this verifier for one
document that was never making a current claim.

Zero real findings is not this verifier having nothing to do — it is what running the same
probe-first discipline as `versions` looks like on a harder problem: measure the corpus
before writing the rule, and let the disagreements decide what the rule has to account for.

## Install and run

**Not on PyPI yet.** From a checkout:

```bash
git clone https://github.com/melbinjp/docproof && cd docproof
pip install -e .

docproof                 # check the project you are standing in
docproof path/to/project
docproof --show-skips    # and everything it declined to judge, with reasons
docproof --list          # the available checks
```

The `pip install docproof` line goes in when there is something on PyPI to install. A
tool whose whole argument is that documentation should be checkable does not get to open
with an instruction that does not work.

To run the suite, which is the thing worth checking before trusting any of the above:

```bash
pip install -e ".[dev]"
pytest
```

`pip install -e .` alone gets you the tool but not `pytest`, so the extra is not optional
if you want to verify rather than take this document's word for it.

Exit code is `0` when nothing is contradicted, `1` when something is — or when a check
that applies to your project found nothing at all to check, which means its extraction
stopped matching and is not a pass either.

## Configuration

Some documents are deliberately not descriptions of the present. A design note, an RFC, a
build guide written in the future tense — reporting drift in those is arguing with a
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

For one paragraph rather than a whole file — an example, a hypothetical, a path belonging
to something else — the same marker without `-file` covers the paragraph it introduces:

```markdown
<!-- docproof: skip -->
Suppose your entry point is `src/pkg/main.py` and you move it.
```

This README uses it twice, for exactly that reason. It was the first thing running
`docproof` on `docproof` found.

## Requirements

`docproof` requires Python 3.10 or newer, and `git` on the path, and **full history**.

That sentence used to begin "Python 3.10 or newer, and…", and the `versions` check below
declined to judge it — a requirement with no stated subject could be about anything. Naming
the thing that has the requirement costs one word and turns a sentence nobody was checking
into one that fails CI the day it stops being true.

That last one matters more than it sounds. GitHub Actions checks out at depth 1 by
default, and a clone with its history cut off cannot tell a deleted file from one that
never existed — so `docproof` reports that and judges nothing rather than guessing:

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0        # docproof needs history to tell drift from an example
- run: pipx run docproof
```

There are no dependencies at all on Python 3.11+; on 3.10 it installs `tomli` to read
`pyproject.toml`.

Without git, `docproof` cannot tell a file a project ships from one it generates, so it
reports that — in git's own words, not a guess at the cause — and skips every judgement
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

## License

MIT.
