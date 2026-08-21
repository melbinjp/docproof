"""What a claim is, what a verdict is, and why there are three of them and not two.

A documentation checker that can only say PASS or FAIL has to guess when it cannot
locate a claim, and a guess in either direction is a lie: guessing PASS hides drift,
guessing FAIL trains people to ignore the tool. So there is a third verdict, and the
whole design turns on it.

**Asymmetric degradation.** Rewording a sentence should make a check *skip*. Changing
the code the sentence describes should make it *fail*. A checker with that property can
be a required CI gate, because the only way to make it red is to actually break
something. A checker without it is an advisory report, and advisory reports get muted.

The other half of the same idea: a verifier that found nothing to check has not passed.
It has stopped working, and it looks exactly like success. See `Outcome.checked`.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Verdict(str, Enum):
    """What checking one claim came to."""

    HOLDS = "holds"
    """The artifact agrees with the document."""

    BROKEN = "broken"
    """The artifact contradicts the document. This is the only verdict that fails a run."""

    SKIPPED = "skipped"
    """The claim could not be checked reliably, and guessing was refused.

    Every skip carries a reason, and the reasons are reported rather than hidden, so
    that a checker quietly skipping everything is visible instead of green.
    """


@dataclass(frozen=True)
class Claim:
    """One checkable assertion a document makes about the project.

    `subject` is the thing being asserted - a flag, a path, a version string - in the
    form the verifier will look up. `span` is the surrounding text it was read out of,
    kept verbatim because a finding is only useful if it can quote what it read.
    """

    kind: str
    subject: str
    doc: Path
    line: int
    span: str

    def where(self, root: Path | None = None) -> str:
        """`README.md:42`, relative to the project when that makes sense."""
        path = self.doc
        if root is not None:
            with contextlib.suppress(ValueError):
                path = self.doc.relative_to(root)
        return f"{path.as_posix()}:{self.line}"


class Silence(str, Enum):
    """What a verifier's silence turned out to mean, judged from this branch's history.

    `Outcome.silent` names the condition; this names the diagnosis. Failing every silent
    run was measured against 53 public repositories and produced five alarms of which one
    was real: httpx documents its CLI as a screenshot and always has, twine's
    `--repository-url` walked out of its README in 2019 along with the workflow it
    described. An alarm that fires on healthy projects gets switched off, and then it is
    not catching the thing it was switched on for. History tells the cases apart, the
    same way it tells drift from illustration in `verifiers.paths`.
    """

    NEVER = "never"
    """No sampled commit ever extracted a claim of this kind. Silence is this project's
    steady state, not a regression. Quiet."""

    STOPPED = "stopped"
    """Claims used to extract, and none of their subjects survives in today's documents.
    The project stopped making such claims; the last loud commit is the receipt. Quiet."""

    REGRESSED = "regressed"
    """A subject that used to extract still sits in today's documents, but extraction no
    longer produces it. The format defeated the extraction - the one case this alarm
    exists for. Fails the run."""

    TREE_MISMATCH = "tree-mismatch"
    """Extraction over what HEAD records finds claims; the working tree yields none. The
    checkout does not match the repository. Found live the first time this classifier
    ran: a clone silently broken since clone day by a tracked filename NTFS refuses.
    Fails the run."""

    UNKNOWN = "unknown"
    """History could not answer - a shallow clone, no git, or a verifier whose extraction
    cannot be re-run alone. Reported visibly; whether it fails the run is carried on the
    verdict, not guessed from the kind."""


@dataclass(frozen=True)
class SilenceVerdict:
    """A `Silence` with its receipt, and the one bit CI actually gates on.

    `alarming` is carried explicitly rather than derived from `kind` because UNKNOWN
    faces both ways: a shallow clone is the *environment* refusing to answer (exit 0,
    with the fix named), while a verifier that cannot replay its extraction keeps the
    old blanket-alarm behaviour until it can (exit 1, conservatively).
    """

    kind: Silence
    detail: str
    alarming: bool


@dataclass(frozen=True)
class Finding:
    """A claim, what checking it came to, and where the truth actually is.

    `detail` is the receipt. For BROKEN it says what the artifact does instead; for
    SKIPPED it says what could not be established. A finding whose detail does not let
    the reader fix or dismiss it without re-deriving the check has failed at its job.
    """

    claim: Claim
    verdict: Verdict
    detail: str


@dataclass
class Outcome:
    """Everything one verifier concluded, including how much it actually looked at."""

    verifier: str
    applicable: bool = True
    reason: str = ""
    """Why the verifier did not apply. Empty when it did."""

    findings: list[Finding] = field(default_factory=list)

    silence_is_signal: bool = True
    """Whether saying nothing at all means this verifier is broken. See `Verifier`.

    Carried on the outcome rather than looked up from the verifier, so a report can be
    rendered from outcomes alone - which is what the tests, and any future JSON output,
    actually hold.
    """

    silence: SilenceVerdict | None = None
    """What this verifier's silence means, once history has been asked - see `history`.

    None when the outcome is not silent, or when nobody asked. A report treats an
    unclassified silence as alarming, so constructing an Outcome by hand keeps the old
    strict behaviour rather than quietly acquiring a pass.
    """

    @property
    def checked(self) -> int:
        """Claims that produced a real answer. Skips do not count as looking."""
        return sum(1 for f in self.findings if f.verdict is not Verdict.SKIPPED)

    @property
    def broken(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict is Verdict.BROKEN]

    @property
    def skipped(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict is Verdict.SKIPPED]

    @property
    def silent(self) -> bool:
        """Applicable, and it found nothing at all to say. A failure, not a pass.

        This is the failure mode the whole tool exists to avoid, turned on itself. A
        verifier whose extraction stops matching - because the docs were restructured,
        or because a constant moved - goes quiet, and quiet is indistinguishable from
        clean. rigout's own documentation tests hit exactly this: a derivation narrowed
        to one place in the source, the code moved, and the check "skipped itself out of
        existence".

        **No findings at all**, rather than no *judged* findings - and the difference
        matters enough that getting it wrong once was a real bug. Reading it as
        `checked == 0` turned requests, attrs and jinja red: each of them had claims,
        every claim was skipped for a stated reason, and nothing was wrong. A tool that
        fails a healthy repository is a tool somebody switches off, and then it is not
        catching the thing it was switched on for. An explained abstention is not
        silence; a verifier with nothing to say at all is.

        **Unless the claim type is one most projects never make.** `silence_is_signal`
        says which, because this alarm only works when the absence of a claim is
        surprising. Where it is ordinary - twenty of forty public repositories document
        no Python requirement and no install extra, and none of them is broken - the
        same alarm fails half a healthy corpus and teaches people to switch the tool off.
        """
        return self.applicable and self.silence_is_signal and not self.findings
