from __future__ import annotations
import ast
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module: roots.add(node.module.split(".")[0])
    return roots

def test_domain_has_no_outward_dependencies():
    forbidden = {"application", "ports", "adapters", "infrastructure", "api"}
    for path in (ROOT / "domain").glob("*.py"): assert imported_roots(path).isdisjoint(forbidden), path

def test_application_depends_only_on_domain_and_ports_from_project():
    forbidden = {"adapters", "infrastructure", "api"}
    for path in (ROOT / "application").glob("*.py"): assert imported_roots(path).isdisjoint(forbidden), path

def test_ports_do_not_depend_on_adapters_or_infrastructure():
    forbidden = {"application", "adapters", "infrastructure", "api"}
    for path in (ROOT / "ports").glob("*.py"): assert imported_roots(path).isdisjoint(forbidden), path
