# What docproof has found in the wild

Every row here is a real documentation defect docproof surfaced in a project its author does not maintain, with a link you can open.

**What docproof actually found, and what it did not.** docproof resolves a documented path against the repository and its git history and reports the ones that no longer exist. That is the whole of its claim on these. It does not read prose for meaning, and it does not judge a bare name that is not written as a path. A few of the filings below also fix something a person noticed while checking the tool's output by hand; where that happened, the issue itself says so. Nothing here credits the tool with a human's reading.

**How to check this list.** Every row was verified against the GitHub API on 2026-08-31. A merged row means a pull request authored here was merged. A fixed row means the project closed the report as completed and the change came from someone else, which is a weaker claim and is kept separate for that reason. An open row was open on that date.

This file covers documentation-path findings only. Other filings exist that came from reading rather than from the tool, and they are deliberately not counted here.

## Merged into the project (16)

A maintainer read a change authored here and accepted it into their own tree. This is the strongest thing the list contains.

| Project | What was stale |
|---|---|
| [agronholm/anyio#1280](https://github.com/agronholm/anyio/pull/1280) | docs: minimum Python is 3.10, not 3.8 |
| [benoitc/gunicorn#3690](https://github.com/benoitc/gunicorn/pull/3690) | docs: point CONTRIBUTING at the mkdocs settings reference |
| [denoland/deno#36685](https://github.com/denoland/deno/pull/36685) | docs: drop the removed typescript_go_client crate |
| [embassy-rs/embassy#6812](https://github.com/embassy-rs/embassy/pull/6812) | docs: the mcxa examples are at examples/mcxa2xx |
| [getsentry/sentry-react-native#6594](https://github.com/getsentry/sentry-react-native/pull/6594) | docs: update CONTRIBUTING paths for the monorepo layout |
| [IQSS/dataverse#12632](https://github.com/IQSS/dataverse/pull/12632) | Troubleshooting guide points at glassfish-web.xml, which is now payara |
| [koala73/worldmonitor#6926](https://github.com/koala73/worldmonitor/pull/6926) | docs: point the release-packaging cross-reference at its current filename |
| [langwatch/langwatch#7172](https://github.com/langwatch/langwatch/pull/7172) | docs: point FEATURE_MAP at the SKILL.mdx sources |
| [paperclipai/paperclip#11677](https://github.com/paperclipai/paperclip/pull/11677) | docs: point section 11 at the renamed implementation plan |
| [prettier/prettier#19881](https://github.com/prettier/prettier/pull/19881) | docs: point CONTRIBUTING at the current run-format-test.js path |
| [pypa/pipenv#6709](https://github.com/pypa/pipenv/pull/6709) | docs: the documented Python floor is 3.7, pyproject requires 3.10 |
| [rolldown/rolldown#10719](https://github.com/rolldown/rolldown/pull/10719) | docs(agents): point the never-edit list at the binding files that exist |
| [rvben/rumdl#826](https://github.com/rvben/rumdl/pull/826) | docs: config.rs became a module directory |
| [sanity-io/sanity#14169](https://github.com/sanity-io/sanity/pull/14169) | docs: drop eslint-config from the ARCHITECTURE package tree |
| [stacklok/toolhive#6388](https://github.com/stacklok/toolhive/pull/6388) | Point five stale doc paths at the moved files |
| [wekan/wekan#6610](https://github.com/wekan/wekan/pull/6610) | docs: the Theme file table points at the pre-reorganisation path |

Searching GitHub for `is:pr author:melbinjp is:merged -user:melbinjp merged:>2026-08-01` returns seventeen, one more than this table. The extra is [testthedocs/awesome-docs#119](https://github.com/testthedocs/awesome-docs/pull/119), which adds docproof to a list. It is not a documentation defect and it is not counted here.

## Fixed by the project after the report, without a pull request from here (12)

The report named the defect, the project closed it as completed, and the change came from a maintainer or another contributor. Weaker than the table above, and separated from it for that reason.

| Project | What was stale | How it was fixed |
|---|---|---|
| [agronholm/apscheduler#1133](https://github.com/agronholm/apscheduler/issues/1133) | Documented `psycopg` extra is not declared in pyproject.toml | fixed in #1134, closed by the maintainer |
| [CherryHQ/cherry-studio#18815](https://github.com/CherryHQ/cherry-studio/issues/18815) | renderer-architecture.md documents features/ as the domain axis; it was removed in June | fixed in-tree; the pull request opened here (#18819) was closed unmerged in favour of it |
| [CherryHQ/cherry-studio#18850](https://github.com/CherryHQ/cherry-studio/issues/18850) | docs/references/command: the targeted-test command runs nothing, and the paths moved on 2026-06-19 | closed as completed by a maintainer |
| [huggingface/huggingface_hub#4676](https://github.com/huggingface/huggingface_hub/issues/4676) | German docs still document Repository, removed in v1.0, while the English docs were updated | closed as completed by a maintainer |
| [Latias94/merman#78](https://github.com/Latias94/merman/issues/78) | five documents in two finished workstreams are still headed "Status: Active" | closed as completed by the maintainer |
| [Latias94/merman#79](https://github.com/Latias94/merman/issues/79) | FIXTURE_EXPANSION_TODO still describes ZenUML as a translation-based compatibility mode | closed as completed by the maintainer |
| [OpenHands/OpenHands#16783](https://github.com/OpenHands/OpenHands/issues/16783) | AGENTS.md cites new-conversation-button.tsx, removed in f6097bda5 | closed as completed by a maintainer |
| [open-gsd/gsd-core#3604](https://github.com/open-gsd/gsd-core/issues/3604) | check-glossary-refs reports clean while three tracked CONTEXT.md paths are absent | closed as completed by a maintainer |
| [open-gsd/gsd-core#3620](https://github.com/open-gsd/gsd-core/issues/3620) | INVENTORY.md names six drift-control tests; five are deleted, and the translations name a seventh | fixed by a maintainer in [#3658](https://github.com/open-gsd/gsd-core/pull/3658) |
| [pallets/click#3766](https://github.com/pallets/click/issues/3766) | docs/contributing.md describes .github/workflows/test-flask.yaml, which was removed in 97b300c | the workflow had been deleted by accident; a maintainer restored it in [#3768](https://github.com/pallets/click/pull/3768) |
| [Tracer-Cloud/opensre#5081](https://github.com/Tracer-Cloud/opensre/issues/5081) | AGENTS.md cites two precedent files that are not in the repository | closed as completed by a maintainer |
| [zeroclaw-labs/zeroclaw#10074](https://github.com/zeroclaw-labs/zeroclaw/issues/10074) | SECURITY.md documents a CI job that was removed in April, so the container checks are convention now | closed as completed by a maintainer |

## Open, awaiting a maintainer (15)

Filed and verified against the project's main branch, waiting on review. Some ask a question only a maintainer can answer, which is why they are issues rather than pull requests.

| Project | Kind | What was stale |
|---|---|---|
| [aden-hive/hive#7383](https://github.com/aden-hive/hive/issues/7383) | issue | A skills cleanup also removed the MCP and editor configs, and four docs still name them |
| [aden-hive/hive#7384](https://github.com/aden-hive/hive/pull/7384) | PR | docs: remove directories that no longer exist from the structure diagram |
| [aden-hive/hive#7385](https://github.com/aden-hive/hive/issues/7385) | issue | docs/draft-flowchart-schema.md: four of six Key files are gone |
| [elementor/elementor#37006](https://github.com/elementor/elementor/pull/37006) | PR | Fix: correct eleven doc paths that point at files which no longer exist |
| [kubevirt/kubevirt#18848](https://github.com/kubevirt/kubevirt/issues/18848) | issue | docs/debugging.md:118 uses cluster-up/kubectl.sh; the other six commands moved to kubevirtci |
| [kubevirt/kubevirt#18860](https://github.com/kubevirt/kubevirt/pull/18860) | PR | docs: Use the kubevirtci path in the debugging patch example |
| [python-poetry/cleo#539](https://github.com/python-poetry/cleo/pull/539) | PR | docs: import Command and Application from where they live |
| [sendgrid/sendgrid-python#1133](https://github.com/sendgrid/sendgrid-python/pull/1133) | PR | docs: fix four links to test files that moved in 2021 |
| [simonw/datasette#2878](https://github.com/simonw/datasette/pull/2878) | PR | README: minimum Python is 3.10, not 3.8 |
| [slint-ui/slint#12946](https://github.com/slint-ui/slint/issues/12946) | issue | docs: item-tree.md still points at dynamic_item_tree.rs, removed in the rewrite |
| [stacklok/toolhive#6387](https://github.com/stacklok/toolhive/issues/6387) | issue | docs/: fifteen paths name files and directories that are not in the tree |
| [theopenco/llmgateway#3864](https://github.com/theopenco/llmgateway/pull/3864) | PR | docs: apps/admin moved to ee/admin |
| [tutti-os/tutti#2468](https://github.com/tutti-os/tutti/issues/2468) | issue | Two troubleshooting entries point at files that moved |
| [tutti-os/tutti#2507](https://github.com/tutti-os/tutti/pull/2507) | PR | docs: Point the session-replay references at the moved state.go |
| [Unstructured-IO/unstructured#4439](https://github.com/Unstructured-IO/unstructured/pull/4439) | PR | Fix example document paths in README quickstart |

Verified by hand against the GitHub API on 2026-08-31. `scripts/findings.py` regenerates this file from an `outstanding.json` produced by a watcher that no longer runs, so it cannot be trusted to keep these tables current, and the counts above rot the moment a maintainer acts. Recheck before quoting a number.
