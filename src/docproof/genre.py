"""What KIND of document this is, because that predicts precision better than anything else.

Measured over **103 findings** judged one at a time against the clone, across three sweep
batches and 60-odd repositories, with a written reason on every verdict:

| genre | precision | repositories |
|---|---|---|
| **reference** - README, how-to, API guide, architecture page | **0.92-0.94** | 16 |
| other - path carries no genre word | **20/21 = 0.95** | 7 |
| record - validation report, release notes, investigation, session summary | 2/15 = 0.13 | |
| **plan** - design doc, workstream, ship plan, TODO, ticket | **0/19 = 0.00** | **7** |

**Zero of eighteen findings in planning documents were real**, across seven unrelated
repositories - merman, ctx, worldmonitor, rue, wealthfolio, passivbot and superset. That is
not one repository shouting.

**Holding plan and record back is worth 0.65 -> 0.93 and costs one real finding in 103.**

That figure was 0.65 -> 0.81 until the vocabulary was widened on 2026-08-21, and 0.69 -> 0.95
for an hour before that, which was batch-8-and-9 specific and overstated. Both corrections are
left visible, because a number in the docstring of the thing being sold is the number that
gets quoted.

**The residual `other` bucket is now 20/21 = 0.95**, so what the path rule cannot name is no
longer where the errors are. It got there by READING, not by a third mechanism - see below.

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
signal lives inside the document is plausible and failed its first measurement.

A SECOND mechanism was then tried and also lost: scoring the CLAIM's own sentence for past,
future, supersession and illustration markers. On `other` it bought nine points and threw away
half the real findings. `TENSE-VERDICT.md` has the working.

**What finally worked was reading the eleven `other` false positives one at a time.** Nine of
them were genre after all - release notes, a dated INVESTIGATION, a session summary, a ticket
under a heading reading "Files to Create" - and the vocabulary was simply short. Both failures
had invented a mechanism where the existing one needed more words.

**THIS ROUND WAS FITTED, and the mitigation is stated rather than assumed.** Those words were
chosen after reading rows they then classify. Three things bound the risk: each word is
record-or-plan by ordinary meaning to anyone who never saw the data; **all ten rows the new
words moved were FALSE and not one was real**, which is not what noise looks like; and four of
them (`retro`, `incident`, `triage`, `prd`, `backlog`, `milestone`) fired on zero rows and so
cannot have been fitted to anything.

**PRE-REGISTERED, before the next batch is chosen or cloned:** on fresh verdicts the residual
`other` bucket comes in at **>=0.80**. If it lands below that, the widened vocabulary was
fitted to these eleven rows and this paragraph is the evidence against itself.

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
    # Same reading, same day. A ticket is intended work - the one that prompted this sat under
    # a heading reading literally "Files to Create", so its paths were intentions and not
    # claims about the tree. `prd`, `backlog` and `milestone` fired on zero rows and are here
    # from meaning alone.
    "ticket",
    "prd",
    "backlog",
    "milestone",
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
    # ADDED 2026-08-21 by READING the eleven `other` false positives rather than by inventing
    # a mechanism. Two mechanisms had already been tried against that bucket and both lost -
    # a whole-document content classifier, and a claim-level tense rule. Nine of the eleven
    # turned out to be genre after all; the vocabulary was simply short. Release notes are
    # historical by construction, an INVESTIGATION is a dated write-up, a session summary is a
    # record of one sitting.
    "release_note",
    "release-note",
    "release notes",
    "investigation",
    "session_summary",
    "session-summary",
    "gap",
    # These four fired on ZERO rows in the judged set. They are here from meaning alone and
    # cannot have been fitted to anything, which is the opposite of the risk carried by the
    # words above.
    "retro",
    "incident",
    "triage",
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
