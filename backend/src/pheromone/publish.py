"""Publish recorded runs to the dashboard: web/public/runs/<id>.json + index.json.

The deployed dashboard is static and replays these files. Every number comes
from the run graph and event log via export.py and metrics.py.

    uv run python -m pheromone.publish <run_id> [<run_id> ...]
"""

import asyncio
import json
import shutil
import sys
from datetime import datetime, timezone

from pheromone import config
from pheromone.config import ROOT, RUNS_DIR
from pheromone.export import export
from pheromone.graph.client import Graph
from pheromone.metrics import compute

WEB_RUNS = ROOT / "web" / "public" / "runs"


async def recipes() -> list[dict]:
    rows = await Graph(config.RECIPES_GRAPH).ro(
        """
        MATCH (r:Recipe) OPTIONAL MATCH (c:Contribution)-[:FOR]->(r)
        RETURN r.signature AS signature, r.kind AS kind, r.transform AS transform,
               r.support AS support, collect(c.run) AS runs
        ORDER BY support DESC
        """
    )
    return [{**r, "support": int(r["support"] or 0)} for r in rows]


async def publish(run_ids: list[str]) -> None:
    WEB_RUNS.mkdir(parents=True, exist_ok=True)
    index_path = WEB_RUNS / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"runs": []}
    by_id = {m["run"]: m for m in index["runs"]}
    for run_id in run_ids:
        data = await export(run_id)
        m = compute(data)
        m["repo"] = data["run"].get("repo")
        m.pop("outcomes", None)
        by_id[run_id] = m
        shutil.copy(RUNS_DIR / f"{run_id}.json", WEB_RUNS / f"{run_id}.json")
        print(f"published {run_id}: {m['mode']}, {m['attempts']} attempts, {m['tokens']} tokens")
    index = {
        "runs": sorted(by_id.values(), key=lambda m: m["run"]),
        "recipes": await recipes(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    index_path.write_text(json.dumps(index, indent=1, default=str))


if __name__ == "__main__":
    asyncio.run(publish(sys.argv[1:]))
