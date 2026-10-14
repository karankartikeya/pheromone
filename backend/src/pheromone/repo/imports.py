"""Static import scan: which repo files import which (File IMPORTS File)."""

import ast
from pathlib import Path

SKIP_DIRS = {".venv", "venv", ".git", "node_modules", "build", "dist", "__pycache__", ".tox", "docs"}


def python_files(root: Path) -> list[str]:
    out = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root)
        if not SKIP_DIRS.intersection(rel.parts):
            out.append(str(rel))
    return sorted(out)


def _module_name(rel: str, src_prefix: str) -> str:
    parts = Path(rel).with_suffix("").parts
    if src_prefix and parts and parts[0] == src_prefix:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def scan(root: Path) -> list[tuple[str, str]]:
    """Return (importer, imported) pairs of repo-relative paths."""
    files = python_files(root)
    src_prefix = "src" if (root / "src").is_dir() else ""
    by_module = {_module_name(f, src_prefix): f for f in files}
    edges: set[tuple[str, str]] = set()
    for f in files:
        try:
            tree = ast.parse((root / f).read_text(errors="replace"), filename=f)
        except SyntaxError:
            continue
        own = _module_name(f, src_prefix)
        package = own if f.endswith("__init__.py") else own.rpartition(".")[0]
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    pkg = package.split(".") if package else []
                    pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                    base = ".".join([*pkg, base] if base else pkg)
                targets = [base] + [f"{base}.{a.name}" for a in node.names]
            for t in targets:
                # longest prefix that is a repo module: "a.b.c" -> "a.b.c" | "a.b" | "a"
                parts = t.split(".")
                for i in range(len(parts), 0, -1):
                    hit = by_module.get(".".join(parts[:i]))
                    if hit:
                        if hit != f:
                            edges.add((f, hit))
                        break
    return sorted(edges)
