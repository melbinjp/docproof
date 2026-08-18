"""Judging documented paths.

Every skip rule here exists because the first version of this verifier produced a false
positive without it, on a real repository. They are written as tests so the tool cannot
quietly reacquire the habit.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from docproof.docs import read
from docproof.model import Verdict
from docproof.project import Project
from docproof.verifiers.base import Document
from docproof.verifiers.paths import DocumentedPaths


def run(repo: Path) -> dict[str, tuple[Verdict, str]]:
    project = Project(root=repo)
    documents = [Document(path=p, text=read(p)) for p in sorted(repo.glob("*.md"))]
    outcome = DocumentedPaths().run(project, documents)
    return {f.claim.subject: (f.verdict, f.detail) for f in outcome.findings}


def test_a_tracked_path_holds(make_repo: Callable[..., Path]):
    repo = make_repo(
        {
            "README.md": "The entry point is `src/pkg/main.py`.\n",
            "src/pkg/main.py": "",
        }
    )
    assert run(repo)["src/pkg/main.py"][0] is Verdict.HOLDS


def test_a_path_the_project_deleted_is_broken(make_repo: Callable[..., Path]):
    """The receipt is the commit that removed it.

    The README is committed *before* the removal on purpose: that is what real drift is —
    a sentence that was true when written and was broken by a later commit. Written the
    other way round this test passed for years while asserting nothing, because both
    fixture commits landed in the same second and the ordering check could not fire.
    """
    repo = make_repo(
        {"src/pkg/other.py": ""},
        deleted={"src/pkg/main.py": "print('hi')\n"},
        documented_before={"README.md": "The entry point is `src/pkg/main.py`.\n"},
    )
    verdict, detail = run(repo)["src/pkg/main.py"]
    assert verdict is Verdict.BROKEN
    assert "deleted in" in detail and "Farewell" in detail


def test_a_shallow_clone_says_so_rather_than_claiming_the_path_never_existed(
    make_repo: Callable[..., Path],
):
    """A guard that only protects an explanation, which is why nothing was testing it.

    Without history, `git.deleted` returns None for every path, so a shallow checkout
    falls straight through to the "this repository has never had this path" skip. The
    verdict is the same either way — nothing breaks, no alarm fires — and the tool tells
    the reader something false about their project: it never had the file, when in truth
    the clone was truncated. Found by disabling each guard in turn and seeing which ones
    no test noticed; this was the only one.
    """
    repo = make_repo(
        {"README.md": "The entry point is `src/pkg/main.py`.\n", "src/pkg/other.py": ""},
        deleted={"src/pkg/main.py": "print('hi')\n"},
        shallow=True,
    )
    verdict, detail = run(repo)["src/pkg/main.py"]
    assert verdict is Verdict.SKIPPED
    assert "no history" in detail and "fetch-depth: 0" in detail
    assert "never had this path" not in detail


def test_pytest_a_path_named_only_after_it_was_deleted_is_an_example(
    make_repo: Callable[..., Path],
):
    """pytest's docs illustrate `--import-mode=append` with a `testing/__init__.py` tree.
    pytest really did delete a file of that name — in 2010, eleven years before the
    sentence was written. Whoever wrote it knew no such file was here, so it is an
    example, and calling it drift puts a wrong patch in front of a maintainer."""
    repo = make_repo(
        {"README.md": "For example, a project may have `src/pkg/main.py`.\n", "src/pkg/other.py": ""},
        deleted={"src/pkg/main.py": "print('hi')\n"},
    )
    verdict, detail = run(repo)["src/pkg/main.py"]
    assert verdict is Verdict.SKIPPED
    assert "first mentioned it after" in detail


def test_click_a_claim_reworded_after_the_deletion_is_still_drift(
    make_repo: Callable[..., Path],
):
    """The case that killed the obvious implementation. click's contributing docs named a
    CI workflow deleted on 2026-04-03; the line was rewrapped on 2026-04-10, so `git
    blame` dated the claim a week *after* the deletion and read a real finding as an
    example. What matters is when the document first said it, not when the line was last
    touched — here the claim predates the removal and survives a later edit."""
    repo = make_repo(
        {
            "README.md": "The entry point, reworded later, is still `src/pkg/main.py`.\n",
            "src/pkg/other.py": "",
        },
        deleted={"src/pkg/main.py": "print('hi')\n"},
        documented_before={"README.md": "Entry point: `src/pkg/main.py`.\n"},
    )
    verdict, _detail = run(repo)["src/pkg/main.py"]
    assert verdict is Verdict.BROKEN


def test_a_path_the_project_never_had_is_not_judged(make_repo: Callable[..., Path]):
    """click tells readers to create `src/hello/__init__.py`; flask's tutorial tells them
    to write `tests/test_factory.py`. Neither has ever existed in those repositories, and
    reporting them is arguing with a tutorial rather than finding drift. History is the
    only thing that tells the two apart, and it does it perfectly across twenty repos."""
    repo = make_repo(
        {
            "README.md": "The entry point is `src/pkg/main.py`.\n",
            "src/pkg/other.py": "",
        }
    )
    verdict, detail = run(repo)["src/pkg/main.py"]
    assert verdict is Verdict.SKIPPED
    assert "never had this path" in detail


def test_a_gitignored_path_is_not_drift(make_repo: Callable[..., Path]):
    """`build/outputs/` and `.venv/bin/activate` are absent on purpose.

    The first version reported both, on Linearty and monie. The documentation was right
    and the checker was reasoning from "is this file here" instead of "does this project
    ship it".
    """
    repo = make_repo(
        {"README.md": "Artifacts land in `build/outputs/report.html`.\n", "src/keep.py": ""},
        gitignore="build/\n",
    )
    verdict, detail = run(repo)["build/outputs/report.html"]
    assert verdict is Verdict.SKIPPED
    assert "gitignore" in detail


def test_a_bare_filename_at_the_root_is_not_judged(make_repo: Callable[..., Path]):
    """`./monie_memory.db` is created when the program runs. Nothing in the document
    places it inside the repository rather than beside it."""
    repo = make_repo({"README.md": "It writes `./runtime_state.db` as it goes.\n", "a.py": ""})
    verdict, detail = run(repo)["./runtime_state.db"]
    assert verdict is Verdict.SKIPPED


def test_an_untracked_but_present_file_is_not_judged(make_repo: Callable[..., Path]):
    repo = make_repo({"README.md": "See `src/scratch.py`.\n", "src/real.py": ""})
    (repo / "src" / "scratch.py").write_text("", encoding="utf-8")
    verdict, detail = run(repo)["src/scratch.py"]
    assert verdict is Verdict.SKIPPED
    assert "untracked" in detail


def test_a_path_with_no_tracked_ancestor_is_not_judged(make_repo: Callable[..., Path]):
    """Probably describing another repository, or the reader's own tree."""
    repo = make_repo({"README.md": "Compare with `elsewhere/thing.py`.\n", "src/a.py": ""})
    verdict, detail = run(repo)["elsewhere/thing.py"]
    assert verdict is Verdict.SKIPPED


def test_placeholders_are_not_claims(make_repo: Callable[..., Path]):
    repo = make_repo({"README.md": "Put it in `path/to/your/config.yaml`.\n", "src/a.py": ""})
    assert "path/to/your/config.yaml" not in run(repo)


def test_urls_are_not_paths(make_repo: Callable[..., Path]):
    repo = make_repo({"README.md": "Open `https://example.com/docs/guide.md`.\n", "src/a.py": ""})
    assert not any("example.com" in subject for subject in run(repo))


def test_a_diagram_leaf_is_judged_by_its_full_path(make_repo: Callable[..., Path]):
    """`server.py` alone is meaningless; the claim is `src/pkg/server.py`."""
    repo = make_repo(
        {
            "README.md": "```\nroot/\n├── src/pkg/\n│   ├── server.py\n│   └── gone.py\n```\n",
            "src/pkg/server.py": "",
        },
        deleted={"src/pkg/gone.py": ""},
    )
    results = run(repo)
    assert results["src/pkg/server.py"][0] is Verdict.HOLDS
    assert results["src/pkg/gone.py"][0] is Verdict.BROKEN


def test_escaping_the_project_is_not_judged(make_repo: Callable[..., Path]):
    repo = make_repo({"README.md": "See `src/../../secrets.txt`.\n", "src/a.py": ""})
    results = run(repo)
    assert all(v is not Verdict.BROKEN for v, _ in results.values())


def test_the_verifier_is_silent_when_it_finds_nothing(make_repo: Callable[..., Path]):
    """Applicable and yet checked nothing: a failure, not a pass."""
    repo = make_repo({"README.md": "Prose with no paths in it at all.\n", "src/a.py": ""})
    project = Project(root=repo)
    outcome = DocumentedPaths().run(
        project, [Document(path=repo / "README.md", text=read(repo / "README.md"))]
    )
    assert outcome.checked == 0
    assert outcome.silent is True


# --- rules that exist because a well-known repository proved them necessary -------
#
# Twenty public Python projects. The first run produced 187 findings and
# every single one was wrong. Each test below is named for what produced it.


def test_output_in_a_transcript_is_not_a_claim(make_repo: Callable[..., Path]):
    """black's docs show `black src/ -q` printing an error that names a file it deleted.

    The sentence is an example of an error message, not an assertion that the file is
    there. Only prompt lines in a transcript are read.
    """
    repo = make_repo(
        {
            "README.md": "```console\n$ tool run\nerror: cannot parse: src/pkg/old.py:5:6\n```\n",
            "src/pkg/new.py": "",
        },
        deleted={"src/pkg/old.py": ""},
    )
    assert "src/pkg/old.py" not in run(repo)


def test_a_path_the_reader_is_told_to_create_is_not_a_claim(make_repo: Callable[..., Path]):
    """falcon's ASGI tutorial says `$ touch tests/__init__.py` — an instruction to the
    reader to make that file in their own project. falcon happens to have deleted its own
    tests/__init__.py in 2019, so the deleted-path receipt fires and the tutorial line
    reads as falcon's drift. A `touch`/`mkdir` operand is created, never asserted to
    pre-exist. Found out-of-sample, 2026-08-14; the common name is what made it bite."""
    repo = make_repo(
        {
            "README.md": (
                "Set up your tests:\n\n```console\n$ mkdir -p tests\n$ touch tests/__init__.py\n```\n"
            ),
            "src/pkg/keep.py": "",
        },
        deleted={"tests/__init__.py": ""},
    )
    assert "tests/__init__.py" not in run(repo)


def test_a_github_slug_in_a_link_is_not_read_as_a_path(make_repo: Callable[..., Path]):
    """tqdm's README mentions `tqdm/tqdm`, which is a repository, not a directory.

    A span carrying a URL, a `.git`, or a markdown link target is not read for paths.
    That is noise reduction, not the safety property: a bare `owner/repo` in backticks
    with no link around it is genuinely indistinguishable from a directory, and this
    does not pretend otherwise. It stays harmless because a repository that never had
    such a directory cannot have deleted one — the second assertion is the real
    guarantee, and it does not depend on recognising the shape at all.
    """
    repo = make_repo(
        {
            "README.md": "Clone from `https://github.com/pkg/pkg.git`, or see `pkg/pkg` there.\n",
            "src/a.py": "",
        }
    )
    results = run(repo)
    assert not any("github.com" in subject for subject in results)
    assert all(verdict is not Verdict.BROKEN for verdict, _ in results.values())


def test_a_media_type_is_not_a_path(make_repo: Callable[..., Path]):
    """requests' README says `application/json` twice."""
    repo = make_repo({"README.md": "It returns `application/json`.\n", "src/a.py": ""})
    assert "application/json" not in run(repo)


def test_a_verifier_that_explained_itself_is_not_silent(make_repo: Callable[..., Path]):
    """requests, attrs and jinja were each turned red by reading silence as
    `checked == 0`. They had claims, every claim was skipped with a stated reason, and
    nothing was wrong. A tool that fails a healthy repository gets switched off."""
    repo = make_repo({"README.md": "Do not name your file `flask.py`.\n", "src/a.py": ""})
    project = Project(root=repo)
    outcome = DocumentedPaths().run(
        project, [Document(path=repo / "README.md", text=read(repo / "README.md"))]
    )
    assert outcome.checked == 0
    assert outcome.skipped
    assert outcome.silent is False


def test_a_bare_filename_is_not_judged_even_when_it_was_deleted(make_repo: Callable[..., Path]):
    """flask's quickstart says "do not call your file `flask.py`" — advice about the
    reader's filename. Flask really did delete its own `flask.py` in 2010, so history
    agreed and was still answering the wrong question."""
    repo = make_repo(
        {"README.md": "Do not name your module `pkg.py`.\n", "src/a.py": ""},
        deleted={"pkg.py": ""},
    )
    verdict, detail = run(repo)["pkg.py"]
    assert verdict is Verdict.SKIPPED
    assert "bare filename" in detail


def test_a_tombstone_page_describes_the_past():
    """bandit keeps doc pages for plugins B109/B111 that open "This plugin has been
    removed." — deliberate tombstones (their PR #864 added the sentence), kept so old
    links resolve — and a stale example path inside one was reported as drift. pdm's
    `docs/dev/benchmark.md` ("This page has been removed, please visit …") is the same
    class. Deprecated is not removed: structlog's thread-local page documents a
    deprecated module that still exists, still promises, and still deserves judgment.
    """
    from docproof.config import declares_removed

    bandit = (
        "----------------------------------------------\n"
        "B109: password_config_option_not_marked_secret\n"
        "----------------------------------------------\n"
        "\n"
        "This plugin has been removed.\n"
    )
    pdm = "# Benchmark\n\nThis page has been removed, please visit [elsewhere](x).\n"
    assert declares_removed(bandit)
    assert declares_removed(pdm)

    structlog = "# Thread-local\n\nThe `structlog.threadlocal` module is deprecated as of 22.1.0.\n"
    assert not declares_removed(structlog)

    # A removal note about something else is a live page stating history.
    scrapy = "Commands\n========\n\n(The ``scrapy deploy`` command has been removed in 1.0.)\n"
    assert not declares_removed(scrapy)

    # A declaration buried past the lede does not silence the whole page.
    buried = "# Title\n" + "still here\n" * 20 + "This section has been removed.\n"
    assert not declares_removed(buried)


def test_a_changelog_describes_the_past(make_repo: Callable[..., Path]):
    """fastapi's release-notes.md alone produced 162 findings — more than every other
    document in twenty repositories combined. "0.68 moved `docs_src/websockets`" is
    correct and always will be."""
    from docproof.config import is_historical

    assert is_historical("CHANGELOG.md")
    assert is_historical("HISTORY.md")
    assert is_historical("docs/en/docs/release-notes.md")
    assert is_historical("doc/en/changelog.rst")
    assert is_historical("changelog.d/1234.bugfix.md")
    assert not is_historical("README.md")
    assert not is_historical("docs/changelog-policy.md")


def test_an_archive_directory_describes_the_past(make_repo: Callable[..., Path]):
    """`coollabsio/coolify` documents `scripts/coold-vm.sh` inside `docs/v5/archive/dev/`,
    and the commit that deleted the script is named *"archive V5 implementation"* — the same
    change that made the archive. Judging it reports a project for correctly describing what
    it archived.

    Narrow on purpose. The segment must BE `archive` or `archived`: `src/archiver/` is a
    package that archives things and its docs are live, and `docs/architecture.md` merely
    starts with the same letters. `deprecated/` is deliberately absent — one document in 134
    repositories is not evidence, and `TOMBSTONE` already holds that deprecated is not
    removed.
    """
    from docproof.config import is_historical

    assert is_historical("docs/v5/archive/dev/coold-dev.md.txt")
    assert is_historical("docs/archived/old-plan.md")
    assert not is_historical("src/archiver/main.py")
    assert not is_historical("docs/architecture.md")


def test_a_dotted_directory_is_not_stripped_to_a_real_one(make_repo: Callable[..., Path]):
    """`lstrip("./")` strips characters, not a prefix.

    poetry's docs describe `.poetry/plugins` in the *reader's* project. Stripping the dot
    turned it into `poetry/plugins`, a directory poetry really did delete in its
    src-layout move, and a correct sentence came back as drift.
    """
    repo = make_repo(
        {"README.md": "Plugins land in `.poetry/plugins`.\n", "src/a.py": ""},
        deleted={"poetry/plugins/keep.py": ""},
    )
    verdict, _ = run(repo)[".poetry/plugins"]
    assert verdict is not Verdict.BROKEN


def test_a_file_that_moved_under_src_did_not_vanish(make_repo: Callable[..., Path]):
    """pdm's docs say to add `pdm/pep582/sitecustomize.py` to the search path. The
    repository moved it under `src/` in 2022 and the sentence stayed correct, because
    after installation that is where it lives."""
    repo = make_repo(
        {"README.md": "Add `pkg/thing.py` to the path.\n", "src/pkg/thing.py": ""},
        deleted={"pkg/thing.py": ""},
    )
    verdict, detail = run(repo)["pkg/thing.py"]
    assert verdict is Verdict.SKIPPED
    assert "moved it under" in detail


def test_the_posthog_case_an_empty_directory_is_not_a_deleted_one(make_repo: Callable[..., Path]):
    """Git stores files, not directories, so it cannot tell empty from absent.

    `PostHog/posthog-python`'s RELEASING.md says changesets must live in
    `.sampo/changesets/`. The last file under it was deleted in `0fc7ec6` — the release bot
    consuming a changeset on the v7.39.1 release, which is the directory's normal lifecycle,
    not its removal. The sentence says where `sampo add` PUTS files and is still true.
    """
    repo = make_repo(
        {".sampo/config.toml": "", "src/a.py": ""},
        deleted={".sampo/changesets/gallant-prince-ukko.md": ""},
        documented_before={"README.md": "Changesets must live in `.sampo/changesets/`.\n"},
    )
    verdict, detail = run(repo)[".sampo/changesets/"]
    assert verdict is Verdict.SKIPPED
    assert "empty one is indistinguishable" in detail


def test_a_directory_whose_whole_tree_went_is_still_broken(make_repo: Callable[..., Path]):
    """The recall this must not cost: requiring the PARENT to be tracked is what keeps a
    genuinely removed directory tree reportable.

    The README goes in `documented_before` so it exists on the far side of the removal.
    Written as an ordinary file it lands in the last commit and `claim_introduced_after`
    calls it an example — a skip this rule had nothing to do with, and a test that would
    have passed while asserting nothing.
    """
    repo = make_repo(
        {"src/a.py": ""},
        deleted={"oldpkg/plugins/keep.py": ""},
        documented_before={"README.md": "See `oldpkg/plugins/`.\n"},
    )
    verdict, _ = run(repo)["oldpkg/plugins/"]
    assert verdict is Verdict.BROKEN


def test_the_hypothesis_case_a_path_the_reader_is_told_to_create(make_repo: Callable[..., Path]):
    """`CREATES` already knew this shape for shell transcripts; prose was uncovered.

    hypothesis's `CONTRIBUTING.rst:12` says *"Create ``hypothesis/RELEASE.rst``"* — a
    changelog fragment every contributor creates and every release consumes, deleted in
    `6384deef4` while bumping to 6.165.10. The deletion is the file's lifecycle. pipx and
    twine document the same towncrier workflow and would have gone the same way.
    """
    repo = make_repo(
        {"src/a.py": ""},
        deleted={"pkg/RELEASE.rst": ""},
        documented_before={"README.md": "2. Create `pkg/RELEASE.rst` with a release type.\n"},
    )
    verdict, detail = run(repo)["pkg/RELEASE.rst"]
    assert verdict is Verdict.SKIPPED
    assert "tells the reader to CREATE" in detail


def test_a_path_merely_mentioned_is_still_judged(make_repo: Callable[..., Path]):
    """The rule keys on the verb governing THIS path, not on the word appearing nearby."""
    repo = make_repo(
        {"src/a.py": ""},
        deleted={"pkg/thing.py": ""},
        documented_before={"README.md": "Create an account, then read `pkg/thing.py`.\n"},
    )
    verdict, _ = run(repo)["pkg/thing.py"]
    assert verdict is Verdict.BROKEN


def test_the_bat_case_a_path_that_names_its_own_revision(make_repo: Callable[..., Path]):
    """`git show v0.6.0:src/main.rs | bat -l rs` is correct forever.

    sharkdp/bat's README shows how to read an old file with highlighting. `src/main.rs`
    moved into `src/bin/` in 2019, so it is absent at HEAD — and the command still works,
    because it reads from the tag named in the same breath as the path.

    This test would have failed for the whole life of the first fix: the guard was written
    through a shell heredoc and arrived as `r"\x08git\x08"`, a literal backspace byte
    rather than a word boundary, so it never matched and the rule was inert. Nothing else
    noticed, because a disabled rule breaks no test.
    """
    repo = make_repo(
        {"src/bin/main.rs": ""},
        deleted={"src/main.rs": ""},
        documented_before={"README.md": "```bash\ngit show v0.6.0:src/main.rs | cat\n```\n"},
    )
    assert "src/main.rs" not in run(repo)


def test_a_path_on_a_line_with_no_git_command_is_still_judged(make_repo: Callable[..., Path]):
    """`x:y` is a mapping key, a port or a label everywhere else, so the rule is confined
    to git lines. Confining it is what keeps ordinary drift reportable."""
    repo = make_repo(
        {"src/a.py": ""},
        deleted={"pkg/thing.py": ""},
        documented_before={"README.md": "See `pkg/thing.py`.\n"},
    )
    verdict, _ = run(repo)["pkg/thing.py"]
    assert verdict is Verdict.BROKEN


def test_the_kubernetes_case_a_reference_link_label_is_not_a_path(make_repo: Callable[..., Path]):
    """`kubernetes/test-infra`'s README documents a move, correctly.

        - [Deck](https://prow.k8s.io) shows what jobs are running ([`prow/cmd/deck`])
        [`prow/cmd/deck`]: https://github.com/kubernetes-sigs/prow/tree/main/cmd/deck

    Prow's source left the repository in 2024 and the README points at its new home. The
    bracketed token is a link label; `URLISH` cannot see that, because the line where the
    label is USED carries no URL at all. Without this the finding is a wrong pull request
    to a Kubernetes repository.
    """
    readme = (
        "Deck shows what jobs are running ([`prow/cmd/deck`]).\n\n"
        "[`prow/cmd/deck`]: https://github.com/kubernetes-sigs/prow/tree/main/cmd/deck\n"
    )
    repo = make_repo(
        {"src/a.py": ""},
        deleted={"prow/cmd/deck/main.go": ""},
        documented_before={"README.md": readme},
    )
    assert "prow/cmd/deck" not in run(repo)


def test_a_path_that_is_not_a_defined_label_is_still_judged(make_repo: Callable[..., Path]):
    """Only labels the document itself defines are skipped. Everything else is a claim."""
    readme = (
        "See `prow/cmd/tide` for the merge bot.\n\n"
        "[`prow/cmd/deck`]: https://github.com/kubernetes-sigs/prow/tree/main/cmd/deck\n"
    )
    repo = make_repo(
        {"src/a.py": ""},
        deleted={"prow/cmd/tide/main.go": ""},
        documented_before={"README.md": readme},
    )
    verdict, _ = run(repo)["prow/cmd/tide"]
    assert verdict is Verdict.BROKEN


def test_the_wekan_case_a_page_labelled_obsolete_describes_the_past():
    """`TOMBSTONE` needs a sentence with a subject; some pages use a LABEL instead.

    `wekan/docs/Databases/Migrations/CODE_CHANGES_SUMMARY.md` opens
    "> **OBSOLETE - historical record.** This documents the old cron-driven migration
    system ... since removed", then documents `server/cronMigrationManager.js`, deleted in
    `a440d44ea`. The page could not be clearer, and this reported it as drift.

    Measured over 134 repositories: seven documents, all seven genuine, across flask,
    gsd-core and wekan. Anchored at line start so a page merely *discussing* obsolete
    formats keeps being judged.
    """
    from docproof.config import declares_removed

    assert declares_removed("> **OBSOLETE - historical record.** This documents the old system.")
    assert declares_removed("Obsolete, see /appcontext instead.")
    assert declares_removed("# ADR 10\n\n- **Superseded:** 2026-05-13\n")
    assert not declares_removed("# Guide\n\nThis page explains obsolete formats you may meet.\n")
    assert not declares_removed("# Guide\n\nNormal live documentation.\n")


def test_the_sparkyfitness_case_a_path_relative_to_a_package_root(make_repo: Callable[..., Path]):
    """In a monorepo a documented path is often relative to the PACKAGE, not the repository.

    `CodeWithCJ/SparkyFitness` documents `src/components/LanguageHandler.tsx`; it lives at
    `SparkyFitnessFrontend/src/components/LanguageHandler.tsx`, and the next line of that
    document spells the full path out. Read against the repository root the short form looks
    deleted, so a correct sentence was reported as drift.

    38 of the 134 cloned repositories (28%) have two or more nested package roots, so this
    is more than a quarter of everything the tool gets pointed at.
    """
    repo = make_repo(
        {
            "README.md": "The handler is `src/components/Thing.tsx`.\n",
            "frontend/package.json": '{"name":"frontend"}\n',
            "frontend/src/components/Thing.tsx": "",
            "pkg/a.py": "",
        }
    )
    verdict, detail = run(repo)["src/components/Thing.tsx"]
    assert verdict is Verdict.SKIPPED
    assert "nested package roots" in detail


def test_a_path_under_no_package_root_is_still_judged(make_repo: Callable[..., Path]):
    """The recall this must not cost: only paths that actually resolve under a package root
    get the benefit, so ordinary drift in a monorepo is still reported."""
    repo = make_repo(
        {"frontend/package.json": '{"name":"frontend"}\n', "frontend/src/keep.tsx": ""},
        deleted={"tools/build.py": ""},
        documented_before={"README.md": "Run `tools/build.py` first.\n"},
    )
    verdict, _ = run(repo)["tools/build.py"]
    assert verdict is Verdict.BROKEN


def test_a_decision_record_describes_a_decision_taken_then():
    """An ADR body is frozen at authorship by convention, and projects say so themselves.

    gsd-core's contributor standards: *"Amendments are appended as `## Amendment
    (YYYY-MM-DD)` sections - the original body is never rewritten."* So a path in an
    accepted ADR describes the tree as it was when the decision was taken, exactly like a
    changelog entry, and reporting it argues with a policy the project wrote down.

    Of 175 path findings across 134 repositories, **83 are in `adr/` or `prd/`** - the
    single largest class. Narrow: the segment must BE the directory, so `docs/adrian/` and
    `src/prdemo/` keep being judged.
    """
    from docproof.config import is_historical

    assert is_historical("docs/adr/0001-dispatch-policy-module.md")
    assert is_historical("docs/prd/2264-golden-parity-redesign.md")
    assert is_historical("docs/decisions/use-postgres.md")
    assert is_historical("docs/decision-records/0002-x.md")
    assert not is_historical("docs/adrian/notes.md")
    assert not is_historical("src/prdemo/main.py")
