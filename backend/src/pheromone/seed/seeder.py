"""Seed a run graph from a red test suite.

Test, Failure, File, Hypothesis nodes; FAILS_WITH, DEFINED_IN, IN, IMPORTS,
SUSPECTS, TOUCHES, SAME_SIGNATURE edges; PageRank on files, WCC clusters on
failures. Hypotheses come from templates and (run 2) Recipes; failures with
neither are flagged for the LLM proposer.
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pheromone import config
from pheromone.config import PARAMS
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph
from pheromone.graph.schema import ensure_indexes
from pheromone.repo import imports
from pheromone.repo.pytest_runner import Red, TestRun, run_pytest
from pheromone.seed import templates
from pheromone.seed.signatures import signature


@dataclass
class FailureSeed:
    id: str
    signature: str
    file: str
    line: int
    phase: str
    message: str
    tests: list[str]


def is_test_file(path: str) -> bool:
    name = Path(path).name
    return path.startswith("tests/") or "/tests/" in path or name.startswith("test_") or name == "conftest.py"


def root_frame(red: Red) -> tuple[str, int]:
    """Innermost frame in non-test code; else innermost frame; else the test file."""
    for path, line in reversed(red.frames):
        if not is_test_file(path):
            return path, line
    if red.frames:
        return red.frames[-1]
    return red.nodeid.split("::")[0], 0


def source_around(root: Path, path: str, line: int, before: int = 3, after: int = 8) -> str:
    try:
        lines = (root / path).read_text(errors="replace").splitlines()
    except OSError:
        return ""
    lo, hi = max(0, line - 1 - before), min(len(lines), line + after)
    return "\n".join(lines[lo:hi])


def group_failures(root: Path, run: TestRun) -> list[FailureSeed]:
    groups: dict[str, FailureSeed] = {}
    for red in run.red:
        path, line = root_frame(red)
        sig = signature(red.exc_type, red.message, source_around(root, path, line))
        fid = f"{sig}@{path}"
        if fid not in groups:
            groups[fid] = FailureSeed(fid, sig, path, line, red.kind, f"{red.exc_type}: {red.message}"[:400], [])
        groups[fid].tests.append(red.nodeid)
    return list(groups.values())


async def seed(run_id: str, repo: str, worktree: Path, python: Path, mode: str,
               commit: str = "", model: str = "", budget: int = 0) -> dict:
    g = Graph(config.run_graph(run_id))
    await ensure_indexes(g)
    now = int(time.time() * 1000)
    await g.q(
        "CREATE (r:Run {id:$id, repo:$repo, commit:$commit, mode:$mode, model:$model, "
        "budget:$budget, started_at:$now}) SET r += $params",
        id=run_id, repo=repo, commit=commit, mode=mode, model=model, budget=budget,
        now=now, params=PARAMS.as_props(),
    )

    run = await run_pytest(worktree, python)
    failures = group_failures(worktree, run)

    # Files and imports
    files = imports.python_files(worktree)
    await g.q("UNWIND $paths AS p MERGE (:File {path:p, pagerank:0.0})", paths=files)
    edges = imports.scan(worktree)
    await g.q(
        "UNWIND $edges AS e MATCH (a:File {path:e[0]}), (b:File {path:e[1]}) MERGE (a)-[:IMPORTS]->(b)",
        edges=[list(e) for e in edges],
    )

    # Tests (green and red) with DEFINED_IN
    tests = sorted(run.passed | run.red_ids)
    await g.q(
        """
        UNWIND $tests AS t
        MERGE (x:Test {nodeid:t[0]}) SET x.status = t[2]
        MERGE (f:File {path:t[1]}) ON CREATE SET f.pagerank = 0.0
        MERGE (x)-[:DEFINED_IN]->(f)
        """,
        tests=[[t, t.split("::")[0], "red" if t in run.red_ids else "green"] for t in tests],
    )

    # Failures with FAILS_WITH and IN
    await g.q(
        """
        UNWIND $fs AS f
        CREATE (x:Failure {id:f.id, signature:f.signature, file:f.file, line:f.line,
                           phase:f.phase, message_head:f.message, status:'open'})
        MERGE (file:File {path:f.file}) ON CREATE SET file.pagerank = 0.0
        CREATE (x)-[:IN]->(file)
        WITH x, f
        UNWIND f.tests AS tid
        MATCH (t:Test {nodeid:tid})
        CREATE (t)-[:FAILS_WITH]->(x)
        """,
        fs=[f.__dict__ for f in failures],
    )

    # PageRank (agent tool #1): central modules get a higher prior
    pr = {r["path"]: r["score"] for r in await g.q(Q.PAGERANK)}

    # Recipes from earlier runs (run 2)
    recipes: dict[str, list[dict]] = defaultdict(list)
    if mode == "swarm+recipes":
        rg = Graph(config.RECIPES_GRAPH)
        for r in await rg.q(Q.RECIPES_FOR, sigs=sorted({f.signature for f in failures})):
            recipes[r["signature"]].append(r)

    # Hypotheses: templates, merged with matching Recipes
    hyps, unseeded = [], []
    for f in failures:
        options = {kind: {"kind": kind, "text": text, "recipe_id": None, "prior": 1.0}
                   for kind, text in templates.for_signature(f.signature)}
        for r in recipes.get(f.signature, []):
            prior = 1.0 + math.log(1.0 + (r["support"] or 0))
            h = options.setdefault(r["kind"], {"kind": r["kind"], "text": r["transform"]})
            h.update(recipe_id=f"{r['signature']}/{r['kind']}", prior=prior, example=r["example"])
        if not options:
            unseeded.append(f.id)
        for o in options.values():
            hyps.append({
                "id": f"{f.id}#{o['kind']}", "failure": f.id, "file": f.file,
                "signature": f.signature, "kind": o["kind"], "text": o["text"],
                "recipe_id": o.get("recipe_id"), "example": o.get("example"),
                "eta": o["prior"] * (1.0 + pr.get(f.file, 0.0)), "origin": "recipe" if o.get("recipe_id") else "template",
            })
    await g.q(
        """
        UNWIND $hs AS h
        MATCH (f:Failure {id:h.failure}), (file:File {path:h.file})
        CREATE (x:Hypothesis {id:h.id, text:h.text, kind:h.kind, signature:h.signature, file:h.file,
                              status:'open', claimed_by:null, lease_until:0, eta:h.eta,
                              recipe_id:h.recipe_id, example:h.example, origin:h.origin, depth:0})
        CREATE (f)-[:SUSPECTS {pheromone:$tau0}]->(x)
        CREATE (x)-[:TOUCHES]->(file)
        """,
        hs=hyps, tau0=PARAMS.tau0,
    )
    if unseeded:
        await g.q("UNWIND $ids AS id MATCH (f:Failure {id:id}) SET f.needs_proposal = true", ids=unseeded)
    await g.q(
        """
        MATCH (a:Hypothesis), (b:Hypothesis)
        WHERE a.signature = b.signature AND a.file <> b.file AND id(a) < id(b)
        CREATE (a)-[:SAME_SIGNATURE]->(b)
        """
    )

    # WCC (agent tool #2): independent failure clusters spread agents out
    for row in await g.q(Q.WCC):
        ids = [n.properties.get("id") for n in row["members"] if "Failure" in n.labels]
        if ids:
            await g.q(
                "UNWIND $ids AS id MATCH (:Failure {id:id})-[:SUSPECTS]->(h:Hypothesis) SET h.cluster = $c",
                ids=ids, c=row["componentId"],
            )

    summary = {
        "tests": len(tests), "red_tests": len(run.red), "failures": len(failures),
        "hypotheses": len(hyps), "unseeded_failures": len(unseeded),
        "files": len(files), "imports": len(edges), "pytest_ms": run.ms,
    }
    await g.q("MATCH (r:Run {id:$id}) SET r += $s", id=run_id, s=summary)
    return summary
