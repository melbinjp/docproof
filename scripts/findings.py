"""Generate docproof/FINDINGS.md from real, live filing data.

M-0416: "docproof do which is best for the betterment of the tool ... no need fake things but
use your wisdom to frame it well."

The framing decision, stated so the next person does not have to reverse-engineer it:

  - ONLY external projects. Fixes to melbinjp's own repositories are not evidence that the
    tool finds real drift in code its author has never seen, so they are excluded even though
    they inflate the count. The honest number is smaller and means more.

  - LIVE status, read from the API, not a hand-kept trophy list. A merged PR can be reverted
    and an open one can be merged; a static page would rot. This reads `outstanding.json`,
    which `work/outward-watch/outstanding.py` regenerates against the GitHub API, so the page
    is only ever as stale as the last sweep and says when that was.

  - MERGED is the only claim made in the tool's voice. "Found by docproof" is asserted only
    where a maintainer accepted the change into their own tree. Open filings are listed
    plainly as open, and a reader can click either.

  - ATTRIBUTION is not faked. docproof finds a documented path that no longer resolves; it
    does NOT find a bare name in prose or a semantic claim, and several filings mixed both.
    Rather than claim the tool found what a human found by reading, the page says what the
    tool does and does not see, once, at the top, and links the issues where that split is
    already disclosed. Framing it well is telling the truth in a way that still reads as
    strong, because the truth here is strong.

Input lives in the mind repo; this script takes its path as an argument so docproof carries no
dependency on that layout. Writes FINDINGS.md at the repo root.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OWN_PREFIX = "melbinjp/"

# Filings that are external but are NOT documented-path findings, so they do not belong on a
# page whose first sentence says "a documentation defect docproof surfaced". Excluded by name
# with the reason, because that is more honest than a heuristic that might silently drop a real
# one - and because leaving them in would be exactly the fake framing this page exists to avoid.
NOT_A_DOC_FINDING = {
    ("chaterm/Chaterm", 2501): "a CI security-gate bug, found by reading a workflow file",
    ("paperclipai/paperclip", 11771): "a CI security-gate bug, found by reading a workflow file",
    ("Optexity/optexity", 210): "a broken requirements.txt, found by running pip, not docproof",
    ("testthedocs/awesome-docs", 119): "adds docproof to a curated list; a listing, not a finding",
}


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def external(filings: list[dict]) -> list[dict]:
    return [
        f
        for f in filings
        if not f["repo"].startswith(OWN_PREFIX) and (f["repo"], f["num"]) not in NOT_A_DOC_FINDING
    ]


def render(filings: list[dict], swept: str) -> str:
    ext = external(filings)
    merged = sorted((f for f in ext if f.get("merged")), key=lambda f: f["repo"].lower())
    still_open = sorted((f for f in ext if f.get("state") == "open"), key=lambda f: f["repo"].lower())

    lines: list[str] = []
    add = lines.append

    add("# What docproof has found in the wild")
    add("")
    add(
        "Every row here is a real documentation defect docproof surfaced in a project its "
        "author does not maintain, with a link you can open. The list is generated from the "
        "live state of each filing, not written by hand, so a merged row is merged today and "
        "an open row is open today."
    )
    add("")
    add(
        "**What docproof actually found, and what it did not.** docproof resolves a documented "
        "path against the repository and its git history and reports the ones that no longer "
        "exist. That is the whole of its claim on these. It does not read prose for meaning, "
        "and it does not judge a bare name that is not written as a path. A few of the filings "
        "below also fix something a person noticed while checking the tool's output by hand; "
        "where that happened, the issue itself says so. Nothing here credits the tool with a "
        "human's reading."
    )
    add("")
    add(f"Regenerated from live data; last swept {swept}.")
    add("")

    add(f"## Merged into the project ({len(merged)})")
    add("")
    add(
        "A maintainer read the change and accepted it into their own tree. This is the "
        "strongest thing the list contains."
    )
    add("")
    add("| Project | What was stale |")
    add("|---|---|")
    for f in merged:
        url = f"https://github.com/{f['repo']}/pull/{f['num']}"
        title = f["title"].replace("|", "\\|")
        add(f"| [{f['repo']}#{f['num']}]({url}) | {title} |")
    add("")

    add(f"## Open, awaiting a maintainer ({len(still_open)})")
    add("")
    add(
        "Filed and verified against the project's main branch, waiting on review. Some ask a "
        "question only a maintainer can answer, which is why they are issues rather than pull "
        "requests."
    )
    add("")
    add("| Project | Kind | What was stale |")
    add("|---|---|---|")
    for f in still_open:
        kind = "PR" if f["kind"] == "pull" else "issue"
        stub = "pull" if f["kind"] == "pull" else "issues"
        url = f"https://github.com/{f['repo']}/{stub}/{f['num']}"
        title = f["title"].replace("|", "\\|")
        add(f"| [{f['repo']}#{f['num']}]({url}) | {kind} | {title} |")
    add("")

    add(
        "Regenerate with `python scripts/findings.py <path-to-outstanding.json>`. The input is "
        "produced by the outward watcher, which reads each filing through the GitHub API rather "
        "than a search index."
    )
    add("")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: findings.py <outstanding.json> [YYYY-MM-DD]", file=sys.stderr)
        return 2
    data = load(Path(sys.argv[1]))
    swept = sys.argv[2] if len(sys.argv) > 2 else "the date in the commit"
    out = Path(__file__).resolve().parents[1] / "FINDINGS.md"
    out.write_text(render(data, swept), encoding="utf-8")
    ext = external(data)
    merged = sum(1 for f in ext if f.get("merged"))
    openish = sum(1 for f in ext if f.get("state") == "open")
    print(f"wrote {out}: {merged} merged, {openish} open, from {len(ext)} external filings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
