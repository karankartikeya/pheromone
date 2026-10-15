"""Export a recorded run from the graph to runs/<id>.json for replay.

The deployed dashboard replays these files; every number in them comes from
the run graph and the event log, nothing is computed for display.

    uv run python -m pheromone.export <run_id> [<run_id> ...]
"""

import asyncio
import json
import sys

from pheromone import config
from pheromone.config import RUNS_DIR
from pheromone.events import read
from pheromone.graph.client import Graph


async def export(run_id: str) -> dict:
    g = Graph(config.run_graph(run_id))
    run = await g.ro("MATCH (r:Run) RETURN properties(r) AS r")
    edges = await g.ro(
        """
        MATCH (f:Failure)-[s:SUSPECTS]->(h:Hypothesis)
        RETURN f.id AS failure, f.signature AS signature, f.status AS failure_status, f.file AS failure_file,
               h.id AS hypothesis, h.kind AS kind, h.text AS text, h.status AS status, h.origin AS origin,
               h.file AS file, s.pheromone AS tau
        """
    )
    attempts = await g.ro(
        """
        MATCH (ag:Agent)-[:MADE]->(a:Attempt)-[:TESTED]->(h:Hypothesis)
        RETURN a.id AS id, ag.id AS agent, h.id AS hypothesis, a.outcome AS outcome, a.diff AS diff,
               a.diff_hash AS diff_hash, a.fixed AS resolved, a.broken AS broken, a.tokens AS tokens,
               a.ms AS ms, a.at AS at, a.merged AS merged, a.commit AS commit
        ORDER BY a.at
        """
    )
    tests = await g.ro(
        """
        MATCH (t:Test) OPTIONAL MATCH (t)-[:FAILS_WITH]->(f:Failure)
        RETURN t.nodeid AS nodeid, t.status AS status, collect(f.id) AS failures
        """
    )
    data = {
        "run": run[0]["r"] if run else {"id": run_id},
        "events": read(RUNS_DIR / f"{run_id}.events.jsonl"),
        "edges": edges,
        "attempts": attempts,
        "tests": tests,
    }
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(data, indent=1, default=str))
    return data


async def main(ids: list[str]) -> None:
    for run_id in ids:
        d = await export(run_id)
        print(f"{run_id}: {len(d['events'])} events, {len(d['edges'])} edges, {len(d['attempts'])} attempts")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
