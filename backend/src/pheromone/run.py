"""Start a run (CLI or API).

    uv run python -m pheromone.run --target gym --mode swarm --workers 6 --budget 2000000
"""

import argparse
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime

from pheromone import config
from pheromone.config import PARAMS, TARGETS_DIR, WORKTREES_DIR
from pheromone.events import Recorder
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph
from pheromone.repo import worktrees as wt
from pheromone.seed.seeder import seed
from pheromone.swarm import evaporator
from pheromone.swarm.llm import provider
from pheromone.swarm.merger import Merger
from pheromone.swarm.worker import Budget, RunCtx, Worker

MODES = ("swarm", "swarm+recipes")  # baseline lands with baseline.py


@dataclass
class RunHandle:
    run_id: str
    ctx: RunCtx
    rec: Recorder
    task: asyncio.Task

    def kill(self, agent: str) -> None:
        self.ctx.killed.add(agent)
        self.rec.emit({"type": "killed", "agent": agent})


async def launch(target: str, mode: str, workers: int, budget: int, minutes: float = 0,
                 seed_value: int = 0, echo: bool = False) -> RunHandle:
    run_id = f"{target}-{mode.replace('+', '-')}-{datetime.now():%m%d-%H%M%S}"
    repo = TARGETS_DIR / target
    python = repo / ".venv/bin/python"
    base = (await wt.git(repo, "rev-parse", "pheromone-base")).strip()
    rec = Recorder(run_id, echo=echo)
    llm = provider()

    summary = await seed(run_id, target, repo, python, mode, commit=base, model=llm.model, budget=budget)
    rec.emit({"type": "seeded", "run": run_id, "model": llm.model, "workers": workers, **summary})

    g = Graph(config.run_graph(run_id))
    merger = await Merger.create(g, repo, WORKTREES_DIR / run_id / "merge", python, run_id, base, mode, rec.emit)
    ctx = RunCtx(graph=g, run_id=run_id, mode=mode, repo=repo, python=python, run_ref=merger.branch,
                 llm=llm, budget=Budget(budget), emit=rec.emit, merger=merger)
    trees = [await wt.create(repo, WORKTREES_DIR / run_id / f"A{i}", f"A{i}", base) for i in range(workers)]
    pool = [Worker(f"A{i}", ctx, trees[i], seed=seed_value + i) for i in range(workers)]

    async def body() -> None:
        jobs = [asyncio.create_task(evaporator.run(g, ctx.stop, rec.emit))]
        tasks = [asyncio.create_task(w.run(), name=w.id) for w in pool]
        t0 = time.monotonic()
        try:
            done, _ = await asyncio.wait(tasks, timeout=minutes * 60 if minutes else None)
            for t in done:
                if t.exception():
                    rec.emit({"type": "worker_error", "agent": t.get_name(), "error": repr(t.exception())})
        finally:
            ctx.stop.set()
            await asyncio.gather(*jobs, *tasks, return_exceptions=True)
            for t in [*trees, merger.tree]:
                await wt.git(repo, "worktree", "remove", "--force", str(t), check=False)
            suite = (await g.q(Q.SUITE_STATUS))[0]
            await g.q("MATCH (r:Run {id:$id}) SET r.stopped_at = $now, r.tokens = $tok, r.merged = $m",
                      id=run_id, now=int(time.time() * 1000), tok=ctx.budget.used, m=merger.merged)
            rec.emit({"type": "stopped", "tokens": ctx.budget.used, "seconds": round(time.monotonic() - t0, 1),
                      "merged": merger.merged, "branch": merger.branch,
                      "green": int(suite["green"] or 0), "red": int(suite["red"] or 0)})
            rec.close()

    return RunHandle(run_id, ctx, rec, asyncio.create_task(body(), name=run_id))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="gym")
    p.add_argument("--mode", default="swarm", choices=MODES)
    p.add_argument("--workers", type=int, default=PARAMS.workers)
    p.add_argument("--budget", type=int, default=2_000_000, help="token budget for the whole run")
    p.add_argument("--minutes", type=float, default=0, help="wall-clock cap (0 = none)")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()

    async def go() -> str:
        h = await launch(a.target, a.mode, a.workers, a.budget, a.minutes, a.seed, echo=True)
        await h.task
        return h.run_id

    print(asyncio.run(go()))


if __name__ == "__main__":
    main()
