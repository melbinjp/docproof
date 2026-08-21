"""What KIND of document this is, because that predicts precision better than anything else.

Measured 2026-08-19 over 61 findings judged one at a time against the clone, across 44
repositories, with a written reason on every verdict:

| genre | precision | repositories |
|---|---|---|
| **reference** - README, how-to, API guide, architecture page | **35/37 = 0.95** | 10 |
| **plan** - design doc, workstream, ship plan, TODO, evidence log | **0/14 = 0.00** | 5 |
| record - validation report, solutions write-up, known-limitations | 1/4 = 0.25 | 1 |

**Zero of fourteen findings in planning documents were real**, across five unrelated
repositories - merman, ctx, worldmonitor, rue and wealthfolio. That is not one repository
shouting.

THE MECHANISM IS ONE SENTENCE, and it is why this is a real distinction rather than a fitted
one: **a plan is a statement about a decision at a moment; a reference is a statement about
the system now, and only the second can be contradicted by the tree.** In the sharpest cases
the document had *asked* for the state being reported - a completed cleanup checklist reading
"Remove `docs/spec/tools/mdbook-spec/`" is not wrong when that directory is gone. It is right.
Reporting it is telling a maintainer their own decision record is a bug.

WHY A PATH RULE AND NOT A CONTENT RULE. A content classifier was built and it LOST, and that
is recorded here rather than quietly dropped: scoring documents on checkboxes, `## In Scope`,
`Phase N` and `Status:` lines named only 31% of documents against the path rule's 90%, and
**every document it named, the path rule had already named the same way.** The idea that the
signal lives inside the document is plausible and failed its first measurement. The path rule
misses about a third of documents (`CONTRIBUTING.md`, `modernization-prd.md`) and that gap is
real and open - it is simply not closed by the thing that looked like it would close it.

THIS IS POST-HOC AND A PREDICTION IS ON THE RECORD. The buckets were written after the
verdicts and could therefore be fitted to them. `mind/work/docproof-sweep/PRECISION-VERDICT.md`
pre-registered, before the next batch was chosen: *plan-genre findings come in at <=0.25 and
reference-genre at >=0.85; if reference lands below 0.85 the split is an artifact of these 44
repositories.* That test has not been run yet, which is exactly why nothing here is deleted -
findings in held-back genres are still found, still counted and still printed on request.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

# The three lists are copied verbatim from `measure_genre.py`, the script that produced the
# table above. They are not "improved" here on the way in: the rule that ships has to be the
# rule that was measured, or the number in the docstring is about a different program.
PLAN = (
    "design",
    "workstream",
    "plan",
    "todo",
    "roadmap",
    "proposal",
    "rfc",
    "adr",
    "evidence",
    "audit",
    "alignment",
    "upgrade",
)
RECORD = (
    "report",
    "validation",
    "postmortem",
    "solutions",
    "known-limitations",
    "internal/",
    "changelog",
    "history",
)
REFERENCE = (
    "reference",
    "guide",
    "usage",
    "readme",
    "architecture",
    "book",
    "agents.md",
    "feature_map",
    "attributions",
    "troubleshooting",
)

#: Genres whose findings are held back by default. `record` is here on 1/4 = 0.25, which is
#: four findings and far too few to be sure of; it is grouped with plan because both are
#: statements about a past decision rather than about the system now, which is the mechanism
#: rather than the number.
HELD_BACK = ("plan", "record")


def genre(doc: str) -> str:
    """`plan`, `record`, `reference` or `other`, from the path alone.

    ORDER MATTERS and it is not alphabetical: `docs/references/file/architecture.md` is a
    reference that happens to contain an architecture word, and `docs/workstreams/.../DESIGN.md`
    is a plan that happens to sit under `docs/`. The narrower signal is tested first.
    """
    d = str(doc).lower().replace("\\", "/")
    if any(w in d for w in PLAN):
        return "plan"
    if any(w in d for w in RECORD):
        return "record"
    if any(w in d for w in REFERENCE):
        return "reference"
    return "other"


def held_back(doc: str) -> bool:
    """Would a finding in this document be held back by default?

    `other` is NOT held back. It is 36% of findings on the broad corpus and the path rule has
    nothing to say about it, so holding it back would be acting on an absence of evidence
    rather than on evidence.
    """
    return genre(doc) in HELD_BACK


def relative_doc(doc: Path | str, root: Path | None) -> str:
    """The document's path as the project sees it, which is the only shape this rule fits.

    The genre words were measured against repo-relative paths. An absolute path carries every
    directory above the checkout with it, and those are not the project's choice of name -
    they are the user's home directory, a CI workspace, or a temporary folder. The test suite
    found this in under a minute: a pytest tmp directory called
    `test_exit_zero_reports_a_contr0` contains "report", so a README was classified as a
    record and its finding was held back.

    That is the direction of failure that matters. A gate that over-reports is annoying and
    visible; a gate that silently swallows real findings because of where somebody checked
    the repository out is the tool lying about a clean bill of health.
    """
    path = Path(doc)
    if root is not None:
        with contextlib.suppress(ValueError):
            return path.relative_to(root).as_posix()
    return path.name
