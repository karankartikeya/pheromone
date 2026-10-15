"""Environment job (not an orchestrator): evaporation and lease release every tick."""

import asyncio
import time
from collections.abc import Callable

from pheromone.config import PARAMS
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph


async def tick(g: Graph) -> list[str]:
    await g.q(Q.EVAPORATE, keep=PARAMS.keep, tmin=PARAMS.tau_min)
    rows = await g.q(Q.RELEASE_LEASES, now=int(time.time() * 1000))
    return rows[0]["released"] if rows else []


async def run(g: Graph, stop: asyncio.Event, emit: Callable[[dict], None] = lambda e: None) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=PARAMS.evaporate_every_s)
        except asyncio.TimeoutError:
            released = await tick(g)
            emit({"type": "evaporation", "keep": PARAMS.keep})
            for hid in released:
                emit({"type": "lease_expired", "hypothesis": hid})
