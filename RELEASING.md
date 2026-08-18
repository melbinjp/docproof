# Releasing docproof

Releases are published by pushing a tag. Everything after the tag is automatic, and every
step is designed to refuse rather than guess.

There is **no PyPI API token in this repository** — not in a secret, not in a file.
Publishing uses [PyPI trusted publishing]: PyPI is configured to trust this repository, this
workflow file and this environment, and GitHub mints a short-lived OIDC token for the single
job that uploads. A credential that does not exist cannot leak.

[PyPI trusted publishing]: https://docs.pypi.org/trusted-publishers/

## One-time setup on PyPI

Until this is done, no tag publishes to PyPI. It used to FAIL at the upload step, and that
was changed on 2026-08-18 because it also failed the GitHub release, which needs no PyPI at
all. Now `publish-pypi` is conditional on the repository variable `PYPI_ARMED`, and a job
named **`PyPI was NOT published, the publisher is not armed`** runs instead and prints what
did not happen. The intent is unchanged: an unarmed path must never look ready. It just
should not take the working half down with it.

On <https://pypi.org> → **Your account** → **Publishing** → **Add a new pending publisher**:

| Field | Value |
|---|---|
| PyPI Project Name | `docproof` |
| Owner | `melbinjp` |
| Repository name | `docproof` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

A *pending* publisher is the correct form while the project does not yet exist on PyPI; the
first successful run creates it.

Optionally, add a required reviewer to the `pypi` environment under
Settings → Environments. A tag will then build, test and check everything and wait for
approval before uploading. The workflow already declares the environment, so this needs no
code change.

## Cutting a release

```bash
# `version` in pyproject.toml must already be the new number, and the commit must be on main
git tag v0.1.0
git push origin v0.1.0
```

## What the tag triggers, and why each step is there

| Step | The mistake it exists to catch |
|---|---|
| tag vs `pyproject.toml` | a release published under a number the package does not carry |
| tagged commit is an ancestor of `main` | shipping code that no merged branch contains |
| full CI, every supported OS and Python | relying on "it was green last week" |
| build, install the wheel clean, run it | a broken artifact built from working code |
| `twine check --strict` | a description that renders badly on PyPI — invisible locally, permanent once uploaded |

The fourth is the one most projects skip. Every other CI job installs `-e .` and runs from
the source tree, so none of them can see a packaging fault. The first sdist built for this
project was 2.2 MB and 549 files, of which 525 were an unrelated virtualenv that happened to
sit in the working directory under a name `.gitignore` did not match. The code was correct
and the artifact was junk.

## A release cannot be withdrawn

A file can be deleted from PyPI, but the version number is spent permanently and cannot be
reused. A mistake in 0.1.0 is corrected by releasing 0.1.1, never by replacing 0.1.0.
Deleting the project does not release the name for a fresh start either. This is why the
trigger is a tag rather than a push to `main`, and why the environment gate exists.

Two parts of `README.md` are written for a package that is not yet on PyPI: the install
instructions and the note saying so. **Both must change in the commit that ships** — a tool
that checks documentation against reality should not fail its own check on release day.

## What the version number claims

`0.1.0` and `Development Status :: 3 - Alpha` are meant literally: four verifiers —
`paths`, `cli-flags`, `versions`, `symbols` — each measured against the same forty public
repositories. The output format is not stable. Nothing here is more finished than that.

## One-time setup for GitHub Marketplace (the Action)

The package and the Action are two separate distribution channels, and this one has never
been opened. Until 2026-08-18 `melbinjp/rigout` consumed the Action as
`melbinjp/docproof@main`, because a branch was the only reachable form: there was no tag.
`v0.1.0` exists now and rigout is pinned to it, so a gate whose own version used to move
underneath it no longer does.

**The repository already meets every file requirement.** `action.yml` sits at the root with a
`name`, `description`, `author` and `branding` (icon and colour), which is what a listing
renders from.

**The name is free, checked 2026-08-18:** `github.com/marketplace/actions/docproof` returns
404, and of the 26 GitHub repositories matching "docproof", none ships an action file, so
the unique-name requirement is not contested.

**Two steps only the account owner can do:**

1. Accept the **GitHub Marketplace Developer Agreement** (once per account).
2. Tick *"Publish this Action to the GitHub Marketplace"* when the release is created.
   **Two-factor authentication is mandatory at this step**, which is why it cannot be
   automated from here.

Publishing is immediate: an Action goes live without review once the requirements are met.

## The order these have to happen in

**Corrected 2026-08-18. This section used to describe one chain, and there are two.** It
said the PyPI publisher had to be armed first, because a tag would otherwise fail at the
upload step. That was true of the workflow as written, and it made a step only Melbin can do
block a step that does not need him, for a channel that does not involve PyPI.

The Action is installed from a **GitHub release**. A GitHub release needs a tag. That is the
whole dependency.

**Chain A, the Action (no PyPI anywhere in it):**

1. **Tag the release.** The workflow checks the tag against `pyproject.toml`, confirms the
   commit is on `main`, runs the full matrix, builds, and creates the GitHub release.
2. **Marketplace listing**, ticked on that release. Needs the Developer Agreement once and
   **2FA at the tick**, which is the one part that cannot come from here.

**Chain B, the package:**

1. **PyPI pending publisher** (above), on pypi.org, by the account owner.
2. Set the repository variable `PYPI_ARMED` to `true`.
3. Any tag from then on publishes to PyPI as well.

Until step B2, every tag runs a job called **`PyPI was NOT published, the publisher is not
armed`**, which prints what did not happen. The release still succeeds, because the Action
half of it genuinely did.

`python -m build` and `twine check --strict` both pass locally as of 2026-08-18 on `0.1.0`,
so the artifact side is not what would break.
