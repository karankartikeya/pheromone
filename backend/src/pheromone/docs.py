"""Generate docs/QUERIES.md from graph/queries.py so the docs never drift from the code.

    uv run python -m pheromone.docs
"""

import ast
from pathlib import Path

from pheromone.config import ROOT
from pheromone.graph import queries

SRC = Path(queries.__file__)


def comment_above(lines: list[str], lineno: int) -> str:
    out = []
    i = lineno - 2
    while i >= 0 and lines[i].startswith("#"):
        out.append(lines[i].lstrip("# ").rstrip())
        i -= 1
    return " ".join(reversed(out))


def main() -> None:
    text = SRC.read_text()
    lines = text.splitlines()
    tree = ast.parse(text)
    parts = [
        "# Cypher queries",
        "",
        "Every query Pheromone runs, generated from "
        "[`backend/src/pheromone/graph/queries.py`](../backend/src/pheromone/graph/queries.py).",
        "",
        ast.get_docstring(tree) or "",
    ]
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        value = getattr(queries, name)
        parts += ["", f"## `{name}`", ""]
        note = comment_above(lines, node.lineno)
        if note:
            parts += [note, ""]
        body = "\n".join(value) if isinstance(value, list) else value.strip()
        parts += ["```cypher", body, "```"]
    out = ROOT / "docs" / "QUERIES.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(parts) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
