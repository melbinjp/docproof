"""Turning outcomes into something a person can act on, and an exit code CI can gate on.

Two rules about the output, both learned from tools that get muted:

* **Every broken finding names the document line, quotes the claim, and says where the
  truth actually is.** A finding the reader has to investigate before they can believe it
  costs more than it saves.
* **Skips and inapplicable verifiers are printed, not swallowed.** The failure this tool
  exists to prevent is a document quietly ceasing to be true; the failure *it* is prone
  to is a check quietly ceasing to check. Both are invisible unless someone prints them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Outcome, Silence
from .project import Project

TICK, CROSS, DASH, WARN = "ok", "BROKEN", "--", "!!"


@dataclass
class Report:
    project: Project
    outcomes: list[Outcome]

    @property
    def broken(self) -> int:
        return sum(len(o.broken) for o in self.outcomes)

    @property
    def checked(self) -> int:
        return sum(o.checked for o in self.outcomes)

    @property
    def skipped(self) -> int:
        return sum(len(o.skipped) for o in self.outcomes)

    @property
    def silent(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.silent]

    @property
    def stopped_checking(self) -> list[Outcome]:
        """Silent outcomes whose silence history could not explain away.

        Measured over 53 public repositories, failing on *every* silence fired five
        alarms of which one was real. So only the classes with a receipt fail the run —
        REGRESSED and TREE_MISMATCH — while NEVER and STOPPED are said quietly. An
        unclassified silence (None) stays alarming: an Outcome built without asking
        history keeps the old strict behaviour rather than acquiring a pass.
        """
        return [o for o in self.silent if o.silence is None or o.silence.alarming]

    @property
    def exit_code(self) -> int:
        """Non-zero when a claim is contradicted, or when a check demonstrably stopped
        checking. Silence that history explains — never made such claims, or stopped on
        purpose — does not gate."""
        return 1 if self.broken or self.stopped_checking else 0

    def _silence_line(self, outcome: Outcome) -> str:
        """One line per silent verifier, toned by what its silence turned out to mean.

        Quiet classes get the same `--` as an inapplicable verifier, because that is
        what history showed them to be; the alarming classes get the warning marker and
        their receipt. An outcome nobody classified keeps the original strict wording.
        """
        verdict = outcome.silence
        if verdict is None:
            return (
                f"{WARN} {outcome.verifier}: applies here but found nothing to check. "
                f"Either the documentation stopped mentioning these, or the extraction "
                f"stopped matching. Both are worth a look; neither is a pass. If this "
                f"project genuinely documents none, silence it with "
                f'[tool.docproof] disable = ["{outcome.verifier}"].'
            )
        marker = WARN if verdict.alarming or verdict.kind is Silence.UNKNOWN else DASH
        return f"{marker} {outcome.verifier}: found nothing to check — {verdict.detail}."

    def render(self, *, show_skips: bool = False, read: int = 0, unread: int = 0) -> str:
        """`read` and `unread` put the document-level coverage INTO the verdict.

        **Measured defect, 2026-08-19.** The coverage note prints in the header and the verdict
        prints at the bottom, so the last line of a run said `Nothing contradicted. 28 claims
        checked` while 18 of that project's 26 documentation files had never been opened. The
        README promises the opposite in as many words: *"a clean report over two files in a
        project with three hundred cannot be mistaken for a clean report over three hundred."*
        Printed forty lines apart, it can be, and the line people quote is the last one.

        The measurement that forced this: across nine real repositories docproof read **972 of
        3,782** documentation files, 25.7%. Re-run over the whole tree, langwatch went from 1
        broken to 19 and cherry-studio from 23 to 111. Those runs were not clean, they were
        narrow, and only the header said so.
        """
        lines: list[str] = []
        root = self.project.root

        for outcome in self.outcomes:
            if not outcome.applicable:
                lines.append(f"{DASH} {outcome.verifier}: not applicable — {outcome.reason}")
                continue
            if outcome.silent:
                lines.append(self._silence_line(outcome))
                continue
            # **A verifier that checked NOTHING must not be printed with a tick.** Running
            # docproof cold on `rigout` produced `ok symbols: 0 checked`, which reads as
            # checked-and-passed and is the exact sentence this tool exists to prevent
            # appearing anywhere: a checker that skipped everything looking like a clean one.
            #
            # It is not a bug in `silent`. `symbols` and `versions` set
            # `silence_is_signal = False` on a measurement - twelve of forty repositories
            # document no own-package import, twenty document no Python requirement - so
            # their silence is ordinary and must not alarm. That decision is right and is
            # unchanged here. What was wrong was rendering an ordinary nothing as a pass.
            # The dash is the same marker an inapplicable verifier gets, because that is what
            # this is: nothing to say, said out loud.
            if not outcome.checked and not outcome.skipped:
                lines.append(
                    f"{DASH} {outcome.verifier}: nothing of this kind is documented here, and "
                    f"for this check that is ordinary rather than suspicious"
                )
                continue
            summary = f"{outcome.checked} checked"
            if outcome.skipped:
                summary += f", {len(outcome.skipped)} skipped"
            if outcome.broken:
                lines.append(f"{CROSS} {outcome.verifier}: {len(outcome.broken)} broken ({summary})")
            else:
                lines.append(f"{TICK} {outcome.verifier}: {summary}")

        broken = [f for o in self.outcomes for f in o.broken]
        if broken:
            lines.append("")
            lines.append("Claims the code contradicts")
            lines.append("=" * 27)
            for finding in sorted(broken, key=lambda f: (str(f.claim.doc), f.claim.line)):
                lines.append("")
                lines.append(f"  {finding.claim.where(root)}  [{finding.claim.kind}]")
                lines.append(f"    says   `{finding.claim.subject}`")
                lines.append(f"    but    {finding.detail}")

        if show_skips:
            skips = [f for o in self.outcomes for f in o.skipped]
            if skips:
                lines.append("")
                lines.append(f"Not judged ({len(skips)})")
                lines.append("=" * 20)
                for finding in sorted(skips, key=lambda f: (str(f.claim.doc), f.claim.line)):
                    lines.append(
                        f"  {finding.claim.where(root)}  `{finding.claim.subject}` — {finding.detail}"
                    )

        lines.append("")
        if self.broken:
            lines.append(f"{self.broken} broken, {self.checked} checked, {self.skipped} not judged.")
        elif self.stopped_checking:
            lines.append(f"No contradictions, but {len(self.stopped_checking)} check(s) stopped checking.")
        else:
            lines.append(f"Nothing contradicted. {self.checked} claims checked, {self.skipped} not judged.")
            if self.skipped and not show_skips:
                lines.append("Run with --show-skips to see what was left unjudged and why.")
        # Attached to the verdict itself, and to the BROKEN verdict too: "19 broken" over a
        # fifth of the tree is as easy to misread as "nothing contradicted" over a fifth.
        if unread:
            total = read + unread
            lines.append(
                f"This judged {read} of {total} documentation file(s). "
                f"{unread} were never read, so this verdict covers "
                f"{100 * read // total}% of the documentation in this project."
            )
        return "\n".join(lines)
