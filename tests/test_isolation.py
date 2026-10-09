"""The seam: this package must work without the harness it was extracted from.

Three independent checks, because they fail differently: an import check
(nothing from ``evals`` is loaded at runtime), a source scan (nothing names it,
so the coupling cannot come back through a lazy import), and a standalone load
of the session reader (its metrics are usable without Harbor installed).
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE_ROOT / "src" / "harbor_omp"
SESSION_MODULE = SOURCE_ROOT / "session.py"

EVALS_REFERENCE = re.compile(r"\bevals[.\"']")


def test_importing_the_package_pulls_no_evals_module() -> None:
    """A fresh interpreter imports ``harbor_omp`` and nothing named ``evals``."""
    code = (
        "import harbor_omp, sys;"
        "print('|'.join(sorted(m for m in sys.modules"
        " if m == 'evals' or m.startswith('evals.'))))"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=PACKAGE_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"evals modules imported: {result.stdout.strip()}"


def test_no_source_file_references_the_evals_package() -> None:
    """No line in the package names ``evals`` — the fusion cannot come back."""
    offenders: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if EVALS_REFERENCE.search(line):
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{number}: {line.strip()}")

    assert offenders == []


class _BlockModules:
    """An import hook that refuses a named set of top-level packages."""

    def __init__(self, *blocked: str) -> None:
        self.blocked = set(blocked)

    def find_spec(self, fullname: str, path: object = None, target: object = None):
        root = fullname.split(".")[0]
        if root in self.blocked:
            raise ImportError(f"{root} is blocked for this test")
        return None


def _load_module_standalone(name: str, path: Path):
    """Load a module straight from its file, with ``harbor`` absent."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    finder = _BlockModules("harbor", "pydantic")
    # The module must be registered while it executes: dataclasses resolve their
    # own module through sys.modules.
    sys.modules[name] = module
    sys.meta_path.insert(0, finder)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop(name, None)
    return module


def test_the_session_reader_loads_without_harbor_or_pydantic() -> None:
    """The metric reader is importable on its own, which is what lets another
    harness — or a shell script — read a session without Harbor installed."""
    module = _load_module_standalone("harbor_omp_session_probe", SESSION_MODULE)

    assert callable(module.sum_session_usage)
    assert callable(module.iter_session_events)


def test_the_session_reader_imports_only_the_standard_library() -> None:
    """Stdlib only, stated as a property of the source rather than a promise."""
    tree = ast.parse(SESSION_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = {"__future__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])

    third_party = sorted(imported - set(sys.stdlib_module_names))
    assert third_party == [], f"non-stdlib imports: {third_party}"
