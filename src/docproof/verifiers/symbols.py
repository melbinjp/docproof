"""What `from pkg import Thing` in a document promises, checked against what the package
actually defines — without ever importing it, for the same reason `project.py` gives for
everything else here: importing arbitrary code runs its module-level side effects, which
is a strange thing for a linter to do to someone's CI.

**The hard part, found by probing forty public repositories rather than by guessing.**
`versions` had one soundness problem (a set of extras that might be incomplete). This one
has three, because Python has three ways to make `from pkg import name` succeed without
`name` ever being written down as a binding in `pkg`'s own source:

1. **Implicit submodule import.** `from PIL import Image` works because `PIL/Image.py`
   exists, whether or not `PIL/__init__.py` ever imports it — the `from` statement
   imports the submodule as a side effect of the attribute lookup failing. The first
   pass of this probe reported `PIL.Image`, `attrs.validators`, `rich.pretty`,
   `scrapy.signals` and `datasette.tracer` as broken. All five were wrong, and all five
   share this one shape.
2. **PEP 562 `__getattr__`, and its pre-562 equivalent.** A module can define
   `def __getattr__(name):` and answer for names that do not exist until asked —
   pydantic's public API is built this way. pygments predates PEP 562 and gets the same
   effect by swapping `sys.modules[__name__]` for an instance of a `types.ModuleType`
   subclass whose `__getattr__` looks names up in a table. Both make "name not found"
   unprovable, the identical problem `cli_flags.py` already solved for
   `parse_known_args`.
3. **`from .other import *`.** Already handled the same way `versions`' extras handled
   an incomplete set: an absence next to a wildcard is not evidence.

Measured on the corpus: **1,859 own-package import claims, 1,428 statically resolved,
430 landed in one of the three categories above, and exactly one genuine disagreement**
— which turned out to be marshmallow's own upgrade guide illustrating a class it removed
in 3.0, fixed by widening `config.is_historical` rather than by this file.
`work/docproof-sweep/probe_symbols.py` is the measurement, kept for the next repository
that breaks one of these three assumptions.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from pathlib import Path

from ..docs import spans
from ..model import Claim, Finding
from ..project import Project
from .base import Document, Verifier

PY_SOURCE_INFO = frozenset({"python", "py", "python3", "py3"})
PY_TRANSCRIPT_INFO = frozenset({"pycon", "doctest"})


def _to_python_source(info: str, text: str) -> str | None:
    """A span's text as parseable Python, or `None` when this refuses to guess.

    Only an explicit `python`/`py` fence is read directly, and only an explicit
    `pycon`/`doctest` fence (or text that unambiguously opens a line with `>>>`) has its
    prompts stripped. An unlabelled fence is exactly as likely to be JSON or a shell
    transcript as Python in these documents, and guessing wrong invents an import that
    was never written.
    """
    lowered = info.lower()
    if lowered in PY_TRANSCRIPT_INFO or text.startswith(">>> ") or "\n>>> " in text:
        lines: list[str] = []
        for raw in text.split("\n"):
            if raw.startswith(">>> "):
                lines.append(raw[4:])
            elif raw == ">>>":
                lines.append("")
            elif raw.startswith("... "):
                lines.append(raw[4:])
            elif raw == "...":
                lines.append("")
            # Anything else is interpreter output, not source.
        return "\n".join(lines)
    if lowered in PY_SOURCE_INFO:
        return text
    return None


def _collect_target_names(target: ast.expr, names: set[str]) -> None:
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _collect_target_names(elt, names)
    elif isinstance(target, ast.Starred):
        _collect_target_names(target.value, names)
    # ast.Attribute / ast.Subscript targets (`obj.attr = x`) bind no module-level name.


def _subclasses_module_type(node: ast.ClassDef) -> bool:
    """pygments' pre-PEP-562 idiom: a `types.ModuleType` subclass with `__getattr__`,
    later swapped in for the real module via `sys.modules[__name__] = ...`."""
    is_module_subclass = any(
        (isinstance(base, ast.Name) and base.id == "ModuleType")
        or (isinstance(base, ast.Attribute) and base.attr == "ModuleType")
        for base in node.bases
    )
    if not is_module_subclass:
        return False
    return any(
        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__getattr__"
        for item in node.body
    )


def _collect_module_bindings(module: ast.Module) -> tuple[set[str], bool, bool]:
    """Every name a module binds at its own top level; whether a `*` import taints it;
    whether something makes it answer dynamically for names this cannot see.

    Walks into `if`, `try` and `with` bodies at module level — a name bound in only one
    branch of a version- or platform-guarded import is still a real name once that
    branch runs — but never into a `def` or `class` body, whose locals are not module
    attributes.
    """
    names: set[str] = set()
    wildcard = False
    dynamic = False

    def visit(body: list[ast.stmt]) -> None:
        nonlocal wildcard, dynamic
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__getattr__":
                    dynamic = True
                if isinstance(node, ast.ClassDef) and _subclasses_module_type(node):
                    dynamic = True
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    _collect_target_names(target, names)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                _collect_target_names(node.target, names)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        wildcard = True
                    else:
                        names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.If):
                visit(node.body)
                visit(node.orelse)
            elif isinstance(node, ast.Try):
                visit(node.body)
                for handler in node.handlers:
                    visit(handler.body)
                visit(node.orelse)
                visit(node.finalbody)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is not None:
                        _collect_target_names(item.optional_vars, names)
                visit(node.body)

    visit(module.body)
    return names, wildcard, dynamic


def _package_roots(project: Project) -> dict[str, Path]:
    """Top-level import package name -> its directory. Filesystem only, never imported."""
    roots: dict[str, Path] = {}
    for directory in project.source_dirs:
        if directory.name == "src" and directory.is_dir():
            for child in sorted(directory.iterdir()):
                if child.is_dir() and (child / "__init__.py").exists():
                    roots[child.name] = child
        elif (directory / "__init__.py").exists():
            roots[directory.name] = directory
    return roots


def _resolve_module(dotted: str, roots: dict[str, Path]) -> Path | None:
    """`pkg.sub.deep` -> the file whose top level defines that module's names, or None."""
    parts = dotted.split(".")
    if parts[0] not in roots:
        return None
    path: Path = roots[parts[0]]
    for part in parts[1:]:
        subdir = path / part
        subfile = path / f"{part}.py"
        if subdir.is_dir() and (subdir / "__init__.py").exists():
            path = subdir
        elif subfile.is_file():
            return subfile
        else:
            return None  # a C extension, a generated file, or genuinely absent
    init = path / "__init__.py"
    return init if init.is_file() else None


class DocumentedSymbols(Verifier):
    name = "symbols"
    describes = "the names the documentation imports from this project's own package"

    # Twelve of forty measured repositories document no own-package import at all —
    # not broken, just not a claim every project makes. Same shape as `versions`.
    silence_is_signal = False

    def applies(self, project: Project) -> str | None:
        if not _package_roots(project):
            return (
                "no importable top-level package was found under this project's source "
                "layout, so there is nothing a documented import could be checked against"
            )
        return None

    def check(self, project: Project, documents: Iterable[Document]) -> Iterator[Finding]:
        roots = _package_roots(project)
        module_cache: dict[str, tuple[set[str], bool, bool] | None] = {}
        submodule_cache: dict[str, bool] = {}

        def bindings_of(dotted: str) -> tuple[set[str], bool, bool] | None:
            if dotted not in module_cache:
                file = _resolve_module(dotted, roots)
                if file is None:
                    module_cache[dotted] = None
                else:
                    try:
                        tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
                    except SyntaxError:
                        module_cache[dotted] = None
                    else:
                        module_cache[dotted] = _collect_module_bindings(tree)
            return module_cache[dotted]

        def is_submodule(dotted: str) -> bool:
            if dotted not in submodule_cache:
                submodule_cache[dotted] = _resolve_module(dotted, roots) is not None
            return submodule_cache[dotted]

        def judge(module: str, name: str, doc: Document, line: int, context: str) -> Finding:
            claim = Claim(kind="import", subject=f"{module}.{name}", doc=doc.path, line=line, span=context)
            resolved = bindings_of(module)
            if resolved is None:
                return self.skip(
                    claim,
                    f"`{module}` could not be found as a file under this project's own "
                    f"source tree (a compiled extension, generated code, or genuinely "
                    f"absent), so there is nothing to check `{name}` against",
                )
            names, wildcard, dynamic = resolved
            if name in names:
                return self.holds(claim, f"`{name}` is bound at the top level of `{module}`")
            if is_submodule(f"{module}.{name}"):
                return self.holds(claim, f"`{name}` is itself an importable submodule of `{module}`")
            if dynamic:
                return self.skip(
                    claim,
                    f"`{module}` defines `__getattr__` (PEP 562, or the equivalent "
                    f"`types.ModuleType` subclass), so it can answer for `{name}` "
                    f"dynamically in a way this cannot see without running it",
                )
            if wildcard:
                return self.skip(
                    claim,
                    f"`{module}` contains a `from ... import *`, so `{name}` being absent "
                    f"from its own source proves nothing about whether it is available",
                )
            return self.broken(
                claim,
                f"`{name}` is not defined, imported, or re-exported anywhere in "
                f"`{module}`, and nothing in it explains how it could be created "
                f"dynamically",
            )

        for document in documents:
            for span_text, span_line, span_info in _python_spans(document.text):
                source = _to_python_source(span_info, span_text)
                if source is None:
                    continue
                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    continue
                source_lines = source.split("\n")
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ImportFrom) or node.module is None or node.level:
                        continue  # relative imports name no dotted path to resolve
                    top = node.module.split(".")[0]
                    if top not in roots:
                        continue  # somebody else's package, not this project's claim
                    line = span_line + node.lineno - 1
                    in_range = node.lineno - 1 < len(source_lines)
                    context = source_lines[node.lineno - 1].strip() if in_range else ""
                    if document.silenced(line):
                        continue
                    for alias in node.names:
                        if alias.name == "*":
                            continue  # claims nothing about one name
                        yield judge(node.module, alias.name, document, line, context)


def _python_spans(text: str) -> Iterator[tuple[str, int, str]]:
    """Fenced code spans as (text, starting line, info string)."""
    for span in spans(text):
        if span.fenced:
            yield span.text, span.line, span.info
