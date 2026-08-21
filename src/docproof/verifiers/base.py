"""What every verifier has to be able to say about itself.

Three questions, and the second one is the one most tools skip:

1. What did you check, and what came of it?
2. **Do you even apply here?** A project with no console scripts has no CLI flags to get
   wrong, and a verifier that reports "0 problems" there is claiming a clean bill of
   health it never examined. Applicability is answered *from the project*, so that
   "nothing to check" and "checked, found nothing" are different results.
3. When you could not tell, why not?

Given 2, `Outcome.silent` becomes meaningful: a verifier that applies and still checked
nothing is broken, not clean.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from ..model import Claim, Finding, Outcome, Verdict
from ..project import Project


@dataclass(frozen=True)
class Document:
    path: Path
    text: str
    suppressed: frozenset[int] = frozenset()
    """Lines a `<!-- docproof: skip -->` marker covers. Claims there are never raised."""

    superseded: frozenset[int] = frozenset()
    """Lines in a block the prose labels `Before:` / `Old code:` / `From:`.

    Kept separate from `suppressed` rather than merged into it, because the two silences
    are not the same kind. A marker is the author opting out and knowing they did. This is
    the tool deciding on its own, and a rule nobody asked for that quietly drops blocks
    would go wrong invisibly - so the CLI prints where it fired.
    """

    def silenced(self, line: int) -> bool:
        return line in self.suppressed or line in self.superseded


class Verifier(ABC):
    """Extracts one kind of claim and checks it against the project."""

    name: str = "verifier"
    describes: str = ""
    """One line, shown in reports: what this verifier believes the docs are promising."""

    silence_is_signal: bool = True
    """Whether "this verifier said nothing at all" is evidence that it is broken.

    True for a claim type essentially every project makes: if no document mentions a
    single path, the extraction has stopped working, and that is worth failing over
    because a broken extraction is indistinguishable from a clean run.

    False for a claim type most projects simply do not make. Measured on the forty-repo
    corpus: twenty of them document neither a Python requirement nor an install extra,
    and nothing is wrong with any of them. Treating that as breakage would fail half a
    healthy sample - the same false alarm this tool exists to prevent, aimed at its own
    users. A verifier that sets this False owes the reader visible skips instead, so that
    drift still has somewhere to show up.
    """

    def applies(self, project: Project) -> str | None:
        """None when this verifier applies. A reason string when it does not."""
        return None

    @abstractmethod
    def check(self, project: Project, documents: Iterable[Document]) -> Iterator[Finding]:
        """Yield one finding per claim examined, including the ones that were skipped."""

    def run(self, project: Project, documents: Iterable[Document]) -> Outcome:
        documents = list(documents)
        reason = self.applies(project)
        if reason is not None:
            return Outcome(verifier=self.name, applicable=False, reason=reason)
        return Outcome(
            verifier=self.name,
            findings=list(self.check(project, documents)),
            silence_is_signal=self.silence_is_signal,
        )

    # -- helpers every verifier ends up wanting ------------------------------------

    @staticmethod
    def holds(claim: Claim, detail: str) -> Finding:
        return Finding(claim=claim, verdict=Verdict.HOLDS, detail=detail)

    @staticmethod
    def broken(claim: Claim, detail: str) -> Finding:
        return Finding(claim=claim, verdict=Verdict.BROKEN, detail=detail)

    @staticmethod
    def skip(claim: Claim, detail: str) -> Finding:
        return Finding(claim=claim, verdict=Verdict.SKIPPED, detail=detail)
