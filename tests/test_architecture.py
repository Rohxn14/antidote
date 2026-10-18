# tests/test_architecture.py
"""tests/reference.py is a test oracle: an independent solver that checks the Cypher
engine's answers. The product must never use it, or FalkorDB would not be the one
deciding what holds. Checked by reading every import in app/ and api/."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def imports_of(path: Path) -> set[str]:
    """Every module (and module.name) a Python file imports."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_scanner_sees_imports():
    assert "tests.builders" in imports_of(ROOT / "tests" / "test_support.py")


def test_product_code_never_imports_the_reference_solver():
    offenders = [
        f"{path.relative_to(ROOT)} imports {name}"
        for folder in ("app", "api")
        for path in sorted((ROOT / folder).rglob("*.py"))
        for name in imports_of(path)
        if name == "tests" or name.startswith("tests.") or name.split(".")[-1] == "reference"
    ]
    assert offenders == []
