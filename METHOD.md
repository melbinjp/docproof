# How docproof decides

The README says what the tool is and how to run it. This says why any of it should be
believed: why there is no model in it, what the three verdicts mean, and what happened when
the same four checks were measured against forty public repositories.

Every claim here is checked by docproof on every run, the same as the README.

## Why it is not another LLM documentation reviewer

There are several tools that hand your README to a model and ask whether it looks right.
They find real things. They also disagree with themselves between runs, and they produce
findings you have to investigate before you can believe them, which is how a check ends
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
| **broken** | the project contradicts it; the only verdict that fails a run |
| **skipped** | it could not be checked reliably, and guessing was refused |

The property this buys is worth stating directly:

> **Rewording a sentence makes a check skip. Changing the code it describes makes a check
> fail.**

You can edit prose freely without ever turning CI red, and you cannot quietly break a
documented path.

Every skip carries a reason and `--show-skips` prints all of them, because a checker that
silently skips everything looks exactly like a clean one.

The same rule applies one level up, to whole documents. Every run says how many
documentation files it did not read and which directories they are in, so a clean report
over two files in a project with three hundred cannot be mistaken for a clean report over
three hundred. See [what gets read](README.md#what-gets-read).

**That sentence was printed in the header and the verdict was at the bottom, which is not the
same promise.** A run would end `Nothing contradicted. 149 claims checked` with the coverage
note forty lines above it, and the line anyone quotes from a CI log is the last one. So the
verdict now carries it:

```
1 broken, 149 checked, 497 not judged.
This judged 11 of 383 documentation file(s). 372 were never read, so this verdict
covers 2% of the documentation in this project.
```

That is a real run against a real repository. It was measured: over nine public repositories
docproof read **972 of 3,782** documentation files under the default scope, and re-running two
of them across the whole tree took one from 1 finding to 19 and another from 23 to 111. Those
runs were never clean; they were narrow, and only the header said so.

## What it scores on forty repositories

The current version, run over forty well-known Python projects with full history:

| | |
|---|---|
| Repositories | 40 |
| Documents read | 3,138 |
| Claims examined | 6,734 |
| of those, confirmed | 2,165 |
| of those, **contradicted** | **5** |
| of those, not judged, with a reason | 4,564 |
| Of the 5: genuine | **2** |
| Of the 5: wrong | **3** |

Those are counted, not estimated. The large "not judged" column is the design working
rather than failing: most of it is *"this repository has never had this path"*, which is
what a tutorial's example looks like from the inside.

**Held on thirteen repositories it was never tuned on.** The rules above were built against
those forty. The honest test of a checker is a disjoint set, so it was then run over
thirteen more (`starlette`, `sanic`, `aiohttp`, `anyio`, `cattrs`, `msgspec`, `invoke`,
`bottle`, `pendulum`, `falcon`, `tornado`, `faker`, `paramiko`): 321 documents, 709
claims, 424 confirmed. That pass found **one real bug**: `anyio`'s install page said
Python 3.8 while its `pyproject.toml` requires 3.10, and **one false positive of a new
kind**: `falcon`'s tutorial says `$ touch tests/__init__.py`, an instruction to the reader,
and `falcon` happened to have deleted its own `tests/__init__.py` in 2019. The fix (a path
that a `touch`/`mkdir` command *creates* is not a claim that it exists) was measured across
all fifty-three repositories before it was written: seven such operands, every one a
reader-project path, exactly one of them a live false positive. After it, the out-of-sample
set is **zero false positives**, and these forty are unchanged.

That is not zero and this README is not going to round it to zero. The two genuine ones:
click's `docs/contributing.md` tells contributors that `.github/workflows/test-flask.yaml`
runs Flask's suite against every change; that workflow was deleted in April, and the
directory holds six others and not that one. And datasette's README tells readers it needs
Python 3.8 when `pyproject.toml` requires 3.10.

An earlier version of this table said **4** genuine, and the two it lost are worth the
paragraph. bandit keeps documentation pages for plugins it removed years ago, and each
opens with *"This plugin has been removed."*: deliberate tombstones, kept on purpose so
old links keep resolving. Reporting a stale example path inside one is not finding drift;
it is arguing with a decision the maintainers already made and wrote down. Pages that open
by declaring their own subject removed are now treated like changelogs: history, not
promises. The rule stayed narrow after reading every candidate in the corpus: *deprecated*
is not *removed*, because a deprecated module still exists and its documentation still
makes promises that can rot.

**The three wrong ones are all the same thing**, and it is the honest limit of the design:
*an illustration of the reader's project whose path happens to have existed here once.*
`build`'s docs show an example `.github/workflows/build.yml` for your project, and `build`
itself had a file by that name in 2020. pytest's explanation of `sys.path` sketches a
`testing/` layout that pytest really did have, in 2010. Nothing in the document
distinguishes those from a stale reference, and rather than guess, `docproof` reports them
and lets you dismiss them: the receipt names the commit, so dismissing takes one look.

An obvious-looking fix is to ask whether the document was written *after* the deletion, on
the theory that an author who writes a path they just deleted must have meant it as an
example. It was tested against the finding above before being written, and it does not
hold. click deleted that workflow in `97b300c` on 2026-04-03. `docs/contributing.md` was
then edited on 2026-04-10 in `32ac271`, *"Compile Click-specific guidelines"*: somebody
working on that exact file, a week later, and the stale sentence survived it.

Documentation does not rot because nobody looks at it. It rots because looking at a file
is not the same as re-reading every claim in it, which is the entire reason to have a
machine do the second thing.

**`cli-flags`**: command-line options the documentation shows, checked against the
options the program's `argparse` code actually defines. Two things have to hold before a
missing option counts as drift, and both are about evidence:

* **The command has to be yours.** `pip install --upgrade yourtool` documents pip's
  option. Attribution comes from the console scripts you declare in your own
  `pyproject.toml`, and pipelines count: `seq 100 | yourtool --bytes` is your command.
* **The option list has to be provably complete.** A parser built in a loop, handed to a
  helper, or calling `parse_known_args` can accept options no static read can name. When
  that is so, an option missing from the list is *unjudged* and the reason is said out
  loud. Unambiguous abbreviations are honoured, because argparse honours them.

It also declines to read options out of a quoted value (`--pip-args="--no-cache-dir"` is
pip's option inside yours) and out of a command the documentation is showing *failing*,
which is how a tutorial teaches you what not to type.

**`versions`**: what the documentation promises about *installing*, against the metadata
that decides it. Two claims, both chosen because `pyproject.toml` answers them completely
rather than partially:

* **"`yourpkg` requires Python 3.8 or newer"** against `requires-python`. When the
  documented minimum is below the declared one, `pip` refuses on exactly the versions the
  README invites, and the reader discovers it instead of the author.
* **`pip install yourpkg[extra]`** against `[project.optional-dependencies]`, which is the
  entire set of extras that exist. An extra outside it is not a nuance: the install
  command in the README does not work. Unless the table is `dynamic`, in which case the
  set is not provably complete and the claim goes unjudged, exactly as with flags.

The rule that makes it usable is **the sentence has to be about your project.** Run loosely
over forty repositories, "requires Python 3.x" matched seventeen places and disagreed with
`pyproject.toml` four times, of which one was real. The other three were a sentence about
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
repositories document neither claim, and none of them is broken, so unlike `paths`, finding
nothing here is ordinary rather than evidence the extraction has died. Encoding that is the
difference between a check and a check that fails half a healthy corpus.

**`symbols`**: `from yourpkg import Thing` in the documentation, against what `yourpkg`
actually defines, read from its source and never imported. The soundness problem here is a
step past `versions`': there are three distinct ways Python lets an import succeed without
the name ever being written down as a binding in the package's own source, and a checker
that only knows one of them reports real, correct code as broken.

* **Implicit submodule import.** `from PIL import Image` works because `PIL/Image.py`
  exists as a file, whether or not `PIL/__init__.py` ever imports it.
* **`__getattr__` (PEP 562), and the idiom that predates it.** pydantic's public API and
  pygments' lexer and formatter registries are both built on a module that computes an
  attribute when asked rather than binding it up front: pygments predates PEP 562 and
  gets there by swapping in a `types.ModuleType` subclass, which is the same trick under a
  different name. Either way, "not found" cannot be proven.
* **`from ... import *`**, the identical incompleteness `versions`' extras table already
  had to account for.

Measured on the same forty repositories `versions` was: **1,859 documented imports from a
project's own package, 1,428 resolved directly, 430 landed in one of the three categories
above, and exactly one disagreement survived**: marshmallow's own upgrade guide, showing
`from marshmallow import MarshallingError` to illustrate the API it removed in 3.0. That
sentence is correct about the release it describes and always will be, which is what
widened the historical-document list below to recognise upgrade and migration guides
alongside changelogs, rather than adding a fourth escape hatch to this verifier for one
document that was never making a current claim.

Zero real findings is not this verifier having nothing to do: it is what running the same
probe-first discipline as `versions` looks like on a harder problem: measure the corpus
before writing the rule, and let the disagreements decide what the rule has to account for.

## What is already skipped, and what you still have to say

Some of the class above is recognised without being told. The list matters because **the
documents it does not recognise are exactly where the remaining false positives live**, and
nothing in a report tells you which side of the line a document fell on.

Skipped automatically, on the path alone:

| | |
|---|---|
| a path segment that *is* one of `changelog`, `changes`, `history`, `news`, `releases`, `release-notes`, `whatsnew`, `upgrade`/`upgrading`, `migrate`/`migration`/`migrating` | `docs/upgrading.md`, `docs/releasenotes/2.3.2.rst` |
| `changelog.d/` | fragment directories |
| `archive/`, `archived/`, or a file named `archive.*` | `docs/ARCHIVE.md` |
| `adr/`, `adrs/`, `prd/`, `prds/`, `decisions/`, `decision-records/` | `docs/adr/0007-caching.md` |
| any path carrying a **full** date | `docs/post-mortems/2019-02-05.md` |

Still judged, and deliberately:

| | why |
|---|---|
| `design/`, `designs/`, `workstreams/` | a folder called `design` can hold a living architecture page |
| `rfc/`, `rfcs/`, `plan.md`, `roadmap.md` | a filename is a weak signal; `modernization-plan.md` can be a live roadmap |
| `2026-roadmap.md` | a full date is a stamp, a bare year is a topic |
| `migration-guide.md`, `migrations/` | the rule matches a whole segment, so neither of these is one |

**What it costs to leave a planning tree in.** Hand-checking 62 findings across 44
repositories: of the 14 that landed in a document describing a decision or a piece of work
rather than the present tree (design notes, workstream records, ship plans and evidence logs,
in five unrelated projects), **every single one was a false positive.** Findings in reference
documentation over the same run were right 35 times out of 37.

So if your project keeps design documents under a name not in the first table, `exclude` them
before you read the report. Otherwise most of what you read will be this tool arguing with
decisions you already made and wrote down. One of those fourteen was a completed cleanup
checklist whose line read *"Remove `docs/spec/tools/mdbook-spec/`"*, reported because the
directory it asked you to delete had been deleted.

That sample is one measurement, not a law: it says what these 44 repositories did, and the
split has not yet been reproduced on a corpus chosen after it was noticed.

