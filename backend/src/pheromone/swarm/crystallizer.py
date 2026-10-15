"""Environment job: turn repeated wins into Recipes (procedural memory).

A (signature, kind) that passed for 2+ different hypotheses in this run is
upserted into the shared `recipes` graph, which outlives runs. Idempotent: a
run contributes one Contribution node per recipe, so re-running a tick does
not inflate support. Run 2 seeds hypotheses from these Recipes.
"""

import asyncio
from collections.abc import Callable

from pheromone import config
from pheromone.config import PARAMS
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph
from pheromone.graph.schema import ensure_indexes


def shortest(diffs: list[str]) -> str:
    real = [d for d in diffs if d and d.strip()]
    return min(real, key=len) if real else ""


async def tick(g: Graph, run_id: str) -> list[dict]:
    rg = Graph(config.RECIPES_GRAPH)
    out = []
    for row in await g.q(Q.CRYSTALLIZE_CANDIDATES):
        if row["sig"].startswith("other:"):
            continue  # too generic to transfer
        rows = await rg.q(
            Q.UPSERT_RECIPE, sig=row["sig"], kind=row["kind"], transform=row["text"],
            example=shortest(row["diffs"])[:4000], run=run_id, wins=row["wins"],
        )
        out += rows
    return out


async def run(g: Graph, run_id: str, stop: asyncio.Event, emit: Callable[[dict], None] = lambda e: None) -> None:
    await ensure_indexes(Graph(config.RECIPES_GRAPH), recipes=True)
    known: dict[tuple, int] = {}
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=PARAMS.crystallize_every_s)
            final = True
        except asyncio.TimeoutError:
            final = False
        for r in await tick(g, run_id):
            key = (r["signature"], r["kind"])
            if known.get(key) != r["support"]:
                known[key] = r["support"]
                emit({"type": "recipe", "signature": r["signature"], "kind": r["kind"], "support": r["support"]})
        if final:
            return
