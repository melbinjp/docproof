# What docproof has found in the wild

Every row here is a real documentation defect docproof surfaced in a project its author does not maintain, with a link you can open. The list is generated from the live state of each filing, not written by hand, so a merged row is merged today and an open row is open today.

**What docproof actually found, and what it did not.** docproof resolves a documented path against the repository and its git history and reports the ones that no longer exist. That is the whole of its claim on these. It does not read prose for meaning, and it does not judge a bare name that is not written as a path. A few of the filings below also fix something a person noticed while checking the tool's output by hand; where that happened, the issue itself says so. Nothing here credits the tool with a human's reading.

Regenerated from live data; last swept 2026-08-25.

## Merged into the project (14)

A maintainer read the change and accepted it into their own tree. This is the strongest thing the list contains.

| Project | What was stale |
|---|---|
| [agronholm/anyio#1280](https://github.com/agronholm/anyio/pull/1280) | docs: minimum Python is 3.10, not 3.8 |
| [benoitc/gunicorn#3690](https://github.com/benoitc/gunicorn/pull/3690) | docs: point CONTRIBUTING at the mkdocs settings reference |
| [embassy-rs/embassy#6812](https://github.com/embassy-rs/embassy/pull/6812) | docs: the mcxa examples are at examples/mcxa2xx |
| [getsentry/sentry-react-native#6594](https://github.com/getsentry/sentry-react-native/pull/6594) | docs: update CONTRIBUTING paths for the monorepo layout |
| [IQSS/dataverse#12632](https://github.com/IQSS/dataverse/pull/12632) | Troubleshooting guide points at glassfish-web.xml, which is now payara |
| [koala73/worldmonitor#6926](https://github.com/koala73/worldmonitor/pull/6926) | docs: point the release-packaging cross-reference at its current filen |
| [open-gsd/gsd-core#3658](https://github.com/open-gsd/gsd-core/pull/3658) | fix(#3620): point the docs at files that actually exist |
| [prettier/prettier#19881](https://github.com/prettier/prettier/pull/19881) | docs: point CONTRIBUTING at the current run-format-test.js path |
| [pypa/pipenv#6709](https://github.com/pypa/pipenv/pull/6709) | docs: the documented Python floor is 3.7, pyproject requires 3.10 |
| [rolldown/rolldown#10719](https://github.com/rolldown/rolldown/pull/10719) | docs(agents): point the never-edit list at the binding files that exis |
| [rvben/rumdl#826](https://github.com/rvben/rumdl/pull/826) | docs: config.rs became a module directory |
| [sanity-io/sanity#14169](https://github.com/sanity-io/sanity/pull/14169) | docs: drop eslint-config from the ARCHITECTURE package tree |
| [stacklok/toolhive#6388](https://github.com/stacklok/toolhive/pull/6388) | Point five stale doc paths at the moved files |
| [wekan/wekan#6610](https://github.com/wekan/wekan/pull/6610) | docs: the Theme file table points at the pre-reorganisation path |

## Open, awaiting a maintainer (20)

Filed and verified against the project's main branch, waiting on review. Some ask a question only a maintainer can answer, which is why they are issues rather than pull requests.

| Project | Kind | What was stale |
|---|---|---|
| [aden-hive/hive#7385](https://github.com/aden-hive/hive/issues/7385) | issue | docs/draft-flowchart-schema.md: four of six Key files are gone, and sa |
| [aden-hive/hive#7384](https://github.com/aden-hive/hive/pull/7384) | PR | docs: remove directories that no longer exist from the structure diagr |
| [aden-hive/hive#7383](https://github.com/aden-hive/hive/issues/7383) | issue | A skills cleanup also removed the MCP and editor configs, and four doc |
| [agronholm/apscheduler#1133](https://github.com/agronholm/apscheduler/issues/1133) | issue | Documented `psycopg` extra is not declared in pyproject.toml |
| [CherryHQ/cherry-studio#18815](https://github.com/CherryHQ/cherry-studio/issues/18815) | issue | renderer-architecture.md documents features/ as the domain axis; it wa |
| [denoland/deno#36632](https://github.com/denoland/deno/issues/36632) | issue | docs: libs/typescript_go_client is named in two docs and no longer exi |
| [denoland/deno#36685](https://github.com/denoland/deno/pull/36685) | PR | docs: drop the removed typescript_go_client crate |
| [elementor/elementor#37006](https://github.com/elementor/elementor/pull/37006) | PR | Fix: correct eleven doc paths that point at files which no longer exis |
| [kubevirt/kubevirt#18848](https://github.com/kubevirt/kubevirt/issues/18848) | issue | docs/debugging.md:118 uses cluster-up/kubectl.sh; the other six comman |
| [kubevirt/kubevirt#18860](https://github.com/kubevirt/kubevirt/pull/18860) | PR | docs: Use the kubevirtci path in the debugging patch example |
| [langwatch/langwatch#7172](https://github.com/langwatch/langwatch/pull/7172) | PR | docs: point FEATURE_MAP at the SKILL.mdx sources |
| [paperclipai/paperclip#11677](https://github.com/paperclipai/paperclip/pull/11677) | PR | docs: point section 11 at the renamed implementation plan |
| [python-poetry/cleo#539](https://github.com/python-poetry/cleo/pull/539) | PR | docs: import Command and Application from where they live |
| [sendgrid/sendgrid-python#1133](https://github.com/sendgrid/sendgrid-python/pull/1133) | PR | docs: fix four links to test files that moved in 2021 |
| [simonw/datasette#2878](https://github.com/simonw/datasette/pull/2878) | PR | README: minimum Python is 3.10, not 3.8 |
| [slint-ui/slint#12946](https://github.com/slint-ui/slint/issues/12946) | issue | docs: item-tree.md still points at dynamic_item_tree.rs, removed by th |
| [stacklok/toolhive#6387](https://github.com/stacklok/toolhive/issues/6387) | issue | docs/: fifteen paths name files and directories that are not in the tr |
| [tutti-os/tutti#2468](https://github.com/tutti-os/tutti/issues/2468) | issue | Two troubleshooting entries point at files that moved; three of the re |
| [tutti-os/tutti#2507](https://github.com/tutti-os/tutti/pull/2507) | PR | docs: Point the session-replay references at the moved state.go |
| [Unstructured-IO/unstructured#4439](https://github.com/Unstructured-IO/unstructured/pull/4439) | PR | Fix example document paths in README quickstart |

Regenerate with `python scripts/findings.py <path-to-outstanding.json>`. The input is produced by the outward watcher, which reads each filing through the GitHub API rather than a search index.
