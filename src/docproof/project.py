"""The artifact side: what the project actually is, read from the project itself.

Everything here is derived at read time. Nothing about a target project is configured,
guessed from its name, or carried in a table in this package — because the moment a
checker holds its own copy of the truth, it starts checking the copy.

Nothing in this module imports the project under test. A linter that imports arbitrary
code to inspect it runs that code's module-level side effects, which is a strange thing
to do to someone's CI. Everything is filesystem and AST.
"""

from __future__ import annotations

import ast
import contextlib
import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib

MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", ".git")


def find_root(start: Path) -> Path:
    """Walk up until something says "a project starts here"."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if any((candidate / marker).exists() for marker in MARKERS):
            return candidate
    return start


@dataclass
class Project:
    root: Path

    @cached_property
    def pyproject(self) -> dict[str, Any]:
        path = self.root / "pyproject.toml"
        if not path.is_file():
            return {}
        try:
            loaded: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
            return loaded
        except Exception:
            # A pyproject this cannot parse means every check that depends on it reports
            # itself inapplicable, with a reason. It does not mean those checks pass.
            return {}

    @property
    def metadata(self) -> dict[str, Any]:
        value = self.pyproject.get("project")
        return value if isinstance(value, dict) else {}

    @property
    def name(self) -> str | None:
        name = self.metadata.get("name")
        return name if isinstance(name, str) else None

    @property
    def version(self) -> str | None:
        version = self.metadata.get("version")
        return version if isinstance(version, str) else None

    @property
    def requires_python(self) -> str | None:
        value = self.metadata.get("requires-python")
        return value if isinstance(value, str) else None

    @property
    def console_scripts(self) -> dict[str, str]:
        scripts = self.metadata.get("scripts")
        if not isinstance(scripts, dict):
            return {}
        return {k: v for k, v in scripts.items() if isinstance(k, str) and isinstance(v, str)}

    @cached_property
    def source_dirs(self) -> list[Path]:
        """Where this project's own Python lives.

        `src/` when there is one, otherwise top-level packages. Test directories are
        included because documentation legitimately points at them, and vendored or
        virtual-environment trees are not, because their contents are not this project's
        claims to keep.
        """
        src = self.root / "src"
        if src.is_dir():
            return [src]
        dirs = [
            path
            for path in sorted(self.root.iterdir())
            if path.is_dir()
            and not path.name.startswith(".")
            and path.name not in {"docs", "doc", "node_modules", "venv", ".venv", "build", "dist"}
            and (path / "__init__.py").exists()
        ]
        return dirs or [self.root]

    @cached_property
    def python_files(self) -> list[Path]:
        seen: dict[Path, None] = {}
        for directory in self.source_dirs:
            for path in sorted(directory.rglob("*.py")):
                parts = set(path.relative_to(self.root).parts)
                if parts & {"__pycache__", ".venv", "venv", "node_modules", "build", "dist"}:
                    continue
                seen[path] = None
        return list(seen)

    def parse(self, path: Path) -> ast.Module | None:
        """AST for one file, or None when it will not parse.

        A file this cannot parse is reported as a gap in coverage by whichever verifier
        needed it, never silently treated as containing nothing.
        """
        try:
            return ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            return None

    def relative(self, path: Path) -> str:
        with contextlib.suppress(ValueError):
            return path.relative_to(self.root).as_posix()
        return path.as_posix()
