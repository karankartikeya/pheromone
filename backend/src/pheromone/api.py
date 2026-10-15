"""Control API: starts runs and streams graph events. It does not assign work.

    uv run uvicorn pheromone.api:app --port 8000
"""

import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from pheromone import config
from pheromone.config import RUNS_DIR
from pheromone.events import read
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph, meter
from pheromone.run import MODES, RunHandle, launch

app = FastAPI(title=config.PROJECT_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
RUNS: dict[str, RunHandle] = {}


class RunRequest(BaseModel):
    target: str = "gym"
    mode: str = "swarm"
    workers: int = config.PARAMS.workers
    budget: int = 2_000_000
    minutes: float = 0
    seed: int = 0


@app.post("/runs")
async def start_run(req: RunRequest) -> dict:
    if req.mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    h = await launch(req.target, req.mode, req.workers, req.budget, req.minutes, req.seed)
    RUNS[h.run_id] = h
    return {"run_id": h.run_id}


@app.get("/runs")
async def list_runs() -> list[dict]:
    out = []
    for p in sorted(RUNS_DIR.glob("*.events.jsonl")):
        run_id = p.name.removesuffix(".events.jsonl")
        out.append({"run_id": run_id, "live": run_id in RUNS and not RUNS[run_id].task.done()})
    return out


@app.post("/runs/{run_id}/agents/{agent}/kill")
async def kill_agent(run_id: str, agent: str) -> dict:
    h = RUNS.get(run_id)
    if not h or h.task.done():
        raise HTTPException(404, "no live run with that id")
    h.kill(agent)
    return {"killed": agent}


@app.get("/runs/{run_id}/events")
async def events(run_id: str):
    """Recorded events first (so late joiners catch up), then live ones."""
    path = RUNS_DIR / f"{run_id}.events.jsonl"
    if not path.exists():
        raise HTTPException(404, "unknown run")
    h = RUNS.get(run_id)

    async def stream():
        q = h.rec.subscribe() if h and not h.task.done() else None
        try:
            for e in read(path):
                yield {"data": json.dumps(e)}
            while q is not None:
                try:
                    e = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield {"data": json.dumps(e)}
                    if e.get("type") == "stopped":
                        break
                except asyncio.TimeoutError:
                    yield {"event": "stats", "data": json.dumps({"writes_per_sec": meter.per_sec()})}
        finally:
            if q is not None:
                h.rec.unsubscribe(q)

    return EventSourceResponse(stream())


@app.get("/runs/{run_id}/snapshot")
async def snapshot(run_id: str) -> dict:
    """Current bipartite view: failures, hypotheses, pheromone, who holds what."""
    g = Graph(config.run_graph(run_id))
    edges = await g.ro(
        """
        MATCH (f:Failure)-[s:SUSPECTS]->(h:Hypothesis)
        RETURN f.id AS failure, f.signature AS signature, f.status AS failure_status,
               h.id AS hypothesis, h.kind AS kind, h.status AS status, h.claimed_by AS holder,
               h.origin AS origin, s.pheromone AS tau
        """
    )
    suite = (await g.ro(Q.SUITE_STATUS))[0]
    return {"edges": edges, "green": int(suite["green"] or 0), "red": int(suite["red"] or 0),
            "writes_per_sec": meter.per_sec()}
