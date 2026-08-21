"""What KIND of document this is, because that predicts precision better than anything else.

Measured over **103 findings** judged one at a time against the clone, across three sweep
batches and 60-odd repositories, with a written reason on every verdict:

| genre | precision | repositories |
|---|---|---|
| **reference** - README, how-to, API guide, architecture page | **46/50 = 0.92** | 16 |
| other - path carries no genre word | 20/31 = 0.65 | 7 |
| record - validation report, solutions write-up, known-limitations | 1/4 = 0.25 | 1 |
| **plan** - design doc, workstream, ship plan, TODO, evidence log | **0/18 = 0.00** | **7** |

**Zero of eighteen findings in planning documents were real**, across seven unrelated
repositories - merman, ctx, worldmonitor, rue, wealthfolio, passivbot and superset. That is
not one repository shouting.

**Holding plan and record back is worth 0.65 -> 0.81 and costs one real finding in 103.**

THAT NUMBER WAS 0.69 -> 0.95 IN THIS DOCSTRING FOR AN HOUR AND IT WAS OVERSTATED. It is real
and it is batch-8-and-9 specific; the pooled figure is fourteen points lower. Corrected here
rather than left standing, because a number in the docstring of the thing being sold is the
number that gets quoted.

The reason for the gap is the open problem rather than an excuse: on the newest batch the
`other` bucket is **60% of all findings** and runs at 0.56, and the path rule is silent on
exactly those documents by construction. See `BATCH10-GENRE.md` in the sweep directory.

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

THIS WAS POST-HOC AND THE PREDICTION HAS NOW BEEN RUN. The buckets were written after the
first verdicts and could therefore have been fitted to them, so
`mind/work/docproof-sweep/PRECISION-VERDICT.md` pre-registered on 2026-08-19, before the next
batch was chosen: *plan-genre findings come in at <=0.25 and reference-genre at >=0.85; if
reference lands below 0.85 the split is an artifact.*

Tested 2026-08-21 on batch 10, judged before the buckets existed: **plan 0.00, reference
0.85.** Both halves held. Reference landed EXACTLY on the boundary, which is a pass and a thin
one - one more false positive in those thirteen would have falsified it.

Nothing here is deleted regardless. Findings in held-back genres are still found, still
counted, still printed, and `--all-genres` judges them.
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
