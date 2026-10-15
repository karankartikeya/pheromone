"""Start a run from the command line.

    uv run python -m pheromone.run --target gym --mode swarm --workers 6 --budget 2000000
"""

import argparse
import asyncio
import time
from datetime import datetime

from pheromone import config
from pheromone.config import PARAMS, TARGETS_DIR, WORKTREES_DIR
from pheromone.events import Recorder
from pheromone.graph.client import Graph
from pheromone.repo import worktrees as wt
from pheromone.seed.seeder import seed
from pheromone.swarm import evaporator
from pheromone.swarm.llm import provider
from pheromone.swarm.worker import Budget, RunCtx, Worker

MODES = ("swarm", "swarm+recipes")  # baseline lands with baseline.py


async def start(target: str, mode: str, workers: int, budget: int, minutes: float, seed_value: int) -> str:
    run_id = f"{target}-{mode.replace('+', '-')}-{datetime.now():%m%d-%H%M%S}"
    repo = TARGETS_DIR / target
    python = repo / ".venv/bin/python"
    base = (await wt.git(repo, "rev-parse", "pheromone-base")).strip()
    rec = Recorder(run_id, echo=True)
    llm = provider()

    summary = await seed(run_id, target, repo, python, mode, commit=base, model=llm.model, budget=budget)
    rec.emit({"type": "seeded", "run": run_id, "model": llm.model, **summary})

    g = Graph(config.run_graph(run_id))
    ctx = RunCtx(graph=g, run_id=run_id, mode=mode, repo=repo, python=python, run_ref="pheromone-base",
                 llm=llm, budget=Budget(budget), emit=rec.emit)
    trees = [await wt.create(repo, WORKTREES_DIR / run_id / f"A{i}", f"A{i}", base) for i in range(workers)]
    pool = [Worker(f"A{i}", ctx, trees[i], seed=seed_value + i) for i in range(workers)]
    jobs = [asyncio.create_task(evaporator.run(g, ctx.stop, rec.emit))]
    t0 = time.monotonic()
    try:
        tasks = [asyncio.create_task(w.run(), name=w.id) for w in pool]
        done, pending = await asyncio.wait(tasks, timeout=minutes * 60 if minutes else None)
        for t in done:
            if t.exception():
                rec.emit({"type": "worker_error", "agent": t.get_name(), "error": repr(t.exception())})
    finally:
        ctx.stop.set()
        await asyncio.gather(*jobs, *tasks, return_exceptions=True)
        for t in trees:
            await wt.git(repo, "worktree", "remove", "--force", str(t), check=False)
    rec.emit({"type": "stopped", "tokens": ctx.budget.used, "seconds": round(time.monotonic() - t0, 1)})
    rec.close()
    return run_id


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="gym")
    p.add_argument("--mode", default="swarm", choices=MODES)
    p.add_argument("--workers", type=int, default=PARAMS.workers)
    p.add_argument("--budget", type=int, default=2_000_000, help="token budget for the whole run")
    p.add_argument("--minutes", type=float, default=0, help="wall-clock cap (0 = none)")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    print(asyncio.run(start(a.target, a.mode, a.workers, a.budget, a.minutes, a.seed)))


if __name__ == "__main__":
    main()
