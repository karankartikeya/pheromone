"""LLM proposer: new hypotheses for failures that templates cannot cover.

Run by any worker that finds the frontier empty (no planner). The LLM only
suggests (kind, file, text); deterministic validation decides what enters the
graph: the file must be a non-test file linked to the failure.
"""

import json
import re
import time
from pathlib import Path

from pheromone.config import PARAMS
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph
from pheromone.repo.pytest_runner import run_pytest
from pheromone.seed.seeder import is_test_file

MAX_PROPOSALS = 2  # proposal rounds per failure

INSTRUCTIONS = """You help a swarm of agents migrate a Python codebase from Pydantic v1 to Pydantic v2.
A test still fails and no known fix applies. Propose exactly 2 different, concrete hypotheses for a source-code fix.
Each hypothesis must name ONE file to change, chosen from the candidate files, and describe the change precisely
enough for another agent to implement it. Never propose editing tests or silencing warnings.
Prefer the idiomatic Pydantic v2 API (model_config keys such as frozen=True, field/model validators and
serializers). Never propose overriding dunder methods (__eq__, __setattr__, ...) to imitate v1 behaviour.
Answer with JSON only: [{"kind": "short-kebab-name", "file": "path/from/candidates.py", "text": "what to change"}, ...]"""


def parse_proposals(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [i for i in items if isinstance(i, dict) and {"kind", "file", "text"} <= i.keys()]


def validate(items: list[dict], candidates: set[str]) -> list[dict]:
    out, kinds = [], set()
    for i in items:
        kind = re.sub(r"[^a-z0-9-]+", "-", str(i["kind"]).lower()).strip("-")[:40] or "llm"
        if i["file"] in candidates and not is_test_file(i["file"]) and kind not in kinds and len(i["text"]) > 20:
            kinds.add(kind)
            out.append({"kind": kind, "file": i["file"], "text": i["text"].strip()})
    return out


async def propose(g: Graph, llm, worker_id: str, tree: Path, python: Path, fid: str) -> tuple[list[str], int]:
    """Returns (created hypothesis ids, tokens used)."""
    f = (await g.q("MATCH (f:Failure {id:$fid}) RETURN f.signature AS sig, f.message_head AS msg", fid=fid))[0]
    tests = [r["nodeid"] for r in await g.q(Q.FAILURE_TESTS, fid=fid)]
    c = (await g.q(Q.CANDIDATE_FILES, fid=fid))[0]
    candidates = {p for p in [c["src"], *c["deps"]] if p and not is_test_file(p)}
    if not candidates:
        return [], 0

    run = await run_pytest(tree, python, sorted({t.removesuffix("::__collect__") for t in tests}))
    trace = "\n\n".join(r.longrepr[-2500:] for r in run.red[:3]) or f["msg"] or ""
    files = {p: (tree / p).read_text() for p in sorted(candidates) if (tree / p).is_file()}
    tried = await g.q(
        "MATCH (:Failure {id:$fid})-[:SUSPECTS]->(h:Hypothesis) RETURN h.text AS text", fid=fid)
    parts = [f"## Failing tests\n{', '.join(tests)}\n\n## Traceback\n{trace}"]
    if tried:
        parts.append("## Already tried and failed\n" + "\n".join(f"- {t['text']}" for t in tried))
    parts += [f"## {p}\n```python\n{s}\n```" for p, s in files.items()]
    parts.append(f"## Candidate files\n{', '.join(sorted(candidates))}")

    text, tokens = await llm.complete(INSTRUCTIONS, "\n\n".join(parts))
    created = []
    for i in validate(parse_proposals(text), candidates):
        hid = f"{fid}#llm-{i['kind']}"
        rows = await g.q(Q.ADD_PROPOSED, fid=fid, file=i["file"], hid=hid, text=i["text"], kind=f"llm-{i['kind']}",
                         agent=worker_id, tau0=PARAMS.tau0)
        created += [r["id"] for r in rows]
    await g.q("MATCH (f:Failure {id:$fid}) SET f.proposal_lease = 0, f.proposed_at = $now",
              fid=fid, now=int(time.time() * 1000))
    return created, tokens
