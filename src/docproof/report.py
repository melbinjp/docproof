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

from .model import Outcome
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
    def exit_code(self) -> int:
        """Non-zero when a claim is contradicted, or when a check stopped checking."""
        return 1 if self.broken or self.silent else 0

    def render(self, *, show_skips: bool = False) -> str:
        lines: list[str] = []
        root = self.project.root

        for outcome in self.outcomes:
            if not outcome.applicable:
                lines.append(f"{DASH} {outcome.verifier}: not applicable — {outcome.reason}")
                continue
            if outcome.silent:
                lines.append(
                    f"{WARN} {outcome.verifier}: applies here but found nothing to check. "
                    f"Either the documentation stopped mentioning these, or the extraction "
                    f"stopped matching. Both are worth a look; neither is a pass. If this "
                    f"project genuinely documents none, silence it with "
                    f'[tool.docproof] disable = ["{outcome.verifier}"].'
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
        elif self.silent:
            lines.append(f"No contradictions, but {len(self.silent)} check(s) found nothing to check.")
        else:
            lines.append(f"Nothing contradicted. {self.checked} claims checked, {self.skipped} not judged.")
            if self.skipped and not show_skips:
                lines.append("Run with --show-skips to see what was left unjudged and why.")
        return "\n".join(lines)
