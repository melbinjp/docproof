"""What the documentation promises about installing, checked against the install metadata.

Two claims, chosen because `pyproject.toml` answers both *completely* rather than
partially — which is the property the flags verifier had to learn the hard way:

* **"<project> requires Python 3.x."** `requires-python` is the whole answer. If the
  documented minimum is lower than the declared one, `pip install` refuses on exactly the
  versions the document invites, and the reader finds out instead of the author.
* **`pip install <project>[extra]`.** `[project.optional-dependencies]` is the entire set
  of extras that exist. An extra outside it is not a subtle disagreement — the install
  command in the README does not work.

**The subject rule, which is the only interesting part.** A first pass over forty public
repositories matched every "requires Python 3.x" sentence in every non-historical
document. Seventeen matches, four disagreements, and only one of the four was real:

    black    docs/integrations/github_actions.md   "Note that this requires Python >= 3.11"
    poetry   docs/faq.md                           "scipy requires Python >=3.7,<3.11"
    poetry   docs/contributing.md                  "Poetry's development toolchain requires
                                                    Python 3.9 or newer"
    datasette README.md                            "Datasette requires Python 3.8 or higher"

Only the last is a claim about the package. The first is about a *feature* of a GitHub
Action, the second is quoted output about a *third-party dependency*, and the third is
about a *toolchain* that shares the project's name. So the rule is: **judge the sentence
only when the project's own distribution name is its subject, standing alone.** Not a
possessive, not a pronoun, not another package. Re-measured with that rule, eight claims
were judged, seven held, and the single contradiction was the real one.

The nine sentences it drops are not thrown away — each becomes a skip that names the
subject it found instead, so a reader can see that the tool declined rather than missed.

**On silence.** `Outcome.silent` treats "found nothing at all" as breakage, because a
verifier whose extraction has stopped matching looks exactly like a clean run. That
premise holds for a claim type every project makes. It does not hold here: of forty
repositories, twenty document neither a Python requirement nor an install extra, and they
are not broken — they simply do not make the claim. Turning half a corpus red would be the
same false alarm this tool exists to avoid, pointed at its own users. So this verifier
declares that its silence carries no signal, and pays for it by making every *rejected*
extraction visible as a skip, which is where extraction drift would actually show up.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from ..docs import command_lines, spans
from ..model import Claim, Finding
from ..project import Project
from .base import Document, Verifier

# A `>=X.Y` clause anywhere in the specifier. `>=3.10,<4.0` and `>=3.10.0` both answer
# the only question being asked: what is the lowest Python this package installs on.
LOWER_BOUND = re.compile(r">=\s*(\d+)\.(\d+)")

# `pip install thing[a,b]`, however the document spells the installer.
INSTALL_EXTRA = re.compile(
    r"(?:pip|pip3|uv pip|pipx|python -m pip|python3 -m pip)\s+install\s+"
    r"(?:--?\S+\s+)*"
    r"['\"]?(?P<dist>[A-Za-z0-9._-]+)\[(?P<extras>[^\]]+)\]"
)

# Any sentence asserting a Python requirement, regardless of what it is about. Used only
# to find the claims the subject rule then accepts or declines — so that declining is
# visible instead of silent.
# The subject is **the single token immediately before the verb**, separated by spaces or
# tabs and never across a line break. An earlier version allowed up to four words and
# `\s`, and on datasette's README — where `pip install datasette` sits two lines above
# `Datasette requires Python 3.8 or higher.` — it captured "pip install datasette
# Datasette", failed its own name check, and skipped the one true finding in the corpus.
# A subject rule that reaches backwards past the sentence is not a subject rule.
#
# The `` ` `` and `*` around the subject are not decoration to this pattern — a README
# almost always writes its own name as `` `project` `` or **project**, and without them
# this verifier read docproof's own "`docproof` requires Python 3.10 or newer" as having
# no subject at all and judged nothing. Found by running the tool on itself after making
# its own README state the claim properly.
ANY_REQUIREMENT = re.compile(
    r"[`*_]*(?P<subject>[\w.'’-]+)[`*_]*[ \t]+"
    r"(?P<verb>requires?|needs?|supports?)[ \t]+"
    r"Python[ \t]*(?P<bound>>=?[ \t]*)?(?P<ver>\d+\.\d+)"
    r"(?P<open>[ \t]*\+|[ \t]+or[ \t]+(?:high|new|late)er)?",
    re.IGNORECASE,
)


def normalise(name: str) -> str:
    """PEP 503 normalisation. `Foo.Bar`, `foo_bar` and `foo-bar` are one distribution.

    Without this the check reports every project whose README writes the name with an
    underscore, which is a spelling difference pip does not care about.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _name_variants(dist: str) -> set[str]:
    """How a document might reasonably spell this distribution's name."""
    return {normalise(dist), normalise(dist).replace("-", " "), normalise(dist).replace("-", "")}


class DocumentedVersions(Verifier):
    name = "versions"
    describes = "the Python version and install extras the documentation promises"

    # See the module docstring: absence of these claims is the common case, not a fault.
    silence_is_signal = False

    def applies(self, project: Project) -> str | None:
        if not project.metadata:
            return (
                "this project has no [project] table in pyproject.toml, so there is no "
                "declared Python requirement or extras list for a document to contradict"
            )
        if not project.requires_python and not self._extras(project)[1]:
            return (
                "this project declares neither requires-python nor optional-dependencies, "
                "so there is nothing installable for a document to get wrong"
            )
        return None

    @staticmethod
    def _extras(project: Project) -> tuple[set[str], bool]:
        """(declared extras, whether that set is provably the complete one).

        Completeness is the same requirement the flags verifier needs and for the same
        reason: a set that might be incomplete can confirm a documented extra but can
        never contradict one. `dynamic` is the honest disqualifier — it says in the file
        that the real list is computed elsewhere, at build time, by code this never runs.
        """
        metadata = project.metadata
        dynamic = metadata.get("dynamic")
        if isinstance(dynamic, list) and "optional-dependencies" in dynamic:
            return set(), False
        table = metadata.get("optional-dependencies")
        if isinstance(table, dict):
            return {normalise(k) for k in table if isinstance(k, str)}, True
        # No table and not dynamic: the complete set is genuinely the empty one.
        return set(), True

    def check(self, project: Project, documents: Iterable[Document]) -> Iterator[Finding]:
        yield from self._check_python(project, documents)
        yield from self._check_extras(project, documents)

    # -- the documented Python requirement ---------------------------------------------

    def _check_python(self, project: Project, documents: Iterable[Document]) -> Iterator[Finding]:
        specifier = project.requires_python
        dist = project.name
        if not specifier or not dist:
            return
        variants = _name_variants(dist)

        for document in documents:
            for match in ANY_REQUIREMENT.finditer(document.text):
                line = document.text.count("\n", 0, match.start()) + 1
                if document.silenced(line):
                    continue
                sentence = " ".join(match.group(0).split())
                subject = " ".join(match.group("subject").split())
                claim = Claim(
                    kind="python-requirement",
                    subject=match.group("ver"),
                    doc=document.path,
                    line=line,
                    span=sentence,
                )

                if normalise(subject) not in variants:
                    yield self.skip(
                        claim,
                        f"the sentence is about `{subject}`, not `{dist}` — a requirement "
                        f"stated for a feature, a dependency or a toolchain is not this "
                        f"project's to keep",
                    )
                    continue

                # "supports Python 3.13" is a statement about the top of a range as often
                # as the bottom. Without `+`, `>=` or "or newer" there is no minimum here
                # to compare, and reading one in would be the guess this tool refuses.
                if match.group("verb").lower().startswith("support") and not (
                    match.group("open") or match.group("bound")
                ):
                    yield self.skip(
                        claim,
                        "reads as a supported version rather than a minimum — no `+`, "
                        '`>=` or "or newer" to say which',
                    )
                    continue

                bound = LOWER_BOUND.search(specifier)
                if not bound:
                    yield self.skip(
                        claim,
                        f"requires-python is {specifier!r}, which states no `>=` lower "
                        f"bound to compare against",
                    )
                    continue

                declared = (int(bound.group(1)), int(bound.group(2)))
                documented = tuple(int(part) for part in match.group("ver").split("."))
                shown = f"{declared[0]}.{declared[1]}"
                if documented == declared:
                    yield self.holds(claim, f"requires-python = {specifier!r}")
                elif documented < declared:
                    yield self.broken(
                        claim,
                        f"requires-python = {specifier!r}, so pip refuses to install on "
                        f"Python {match.group('ver')}. The document invites a reader the "
                        f"package turns away; the minimum has moved to {shown}",
                    )
                else:
                    yield self.broken(
                        claim,
                        f"requires-python = {specifier!r}, so the package installs on "
                        f"Python {shown} and the document claims it needs "
                        f"{match.group('ver')} — the documentation is stricter than the "
                        f"package it describes",
                    )

    # -- documented install extras -----------------------------------------------------

    def _check_extras(self, project: Project, documents: Iterable[Document]) -> Iterator[Finding]:
        dist = project.name
        if not dist:
            return
        declared, complete = self._extras(project)
        ours = normalise(dist)

        for document in documents:
            for span in spans(document.text):
                if document.silenced(span.line):
                    continue
                for command in command_lines(span):
                    for match in INSTALL_EXTRA.finditer(command):
                        if normalise(match.group("dist")) != ours:
                            continue  # somebody else's package, not this project's claim
                        for raw in match.group("extras").split(","):
                            extra = raw.strip()
                            if not extra:
                                continue
                            claim = Claim(
                                kind="install-extra",
                                subject=extra,
                                doc=document.path,
                                line=span.line,
                                span=command.strip(),
                            )
                            if normalise(extra) in declared:
                                yield self.holds(claim, "declared in [project.optional-dependencies]")
                            elif not complete:
                                yield self.skip(
                                    claim,
                                    "pyproject.toml marks optional-dependencies as "
                                    "dynamic, so the declared extras are not the whole "
                                    "set and an absence proves nothing",
                                )
                            elif declared:
                                yield self.broken(
                                    claim,
                                    f"[project.optional-dependencies] declares "
                                    f"{sorted(declared)} and not `{extra}`, so this "
                                    f"install command fails for the reader who copies it",
                                )
                            else:
                                yield self.broken(
                                    claim,
                                    "pyproject.toml declares no optional-dependencies at "
                                    "all, so there is no extra this command could install",
                                )
