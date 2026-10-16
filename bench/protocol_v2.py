"""Second measured batch: adds the no-pheromone ablation, shuffled order, per-run log.

    uv run python ../bench/protocol_v2.py            # from backend/
    uv run python ../bench/protocol_v2.py --smoke    # 1 run per cell, to check the pipeline

Phase 1, gym: baseline / coordinated / swarm, N each, shuffled. Swarm runs write Recipes;
the other modes use --no-learn.
Phase 2, krr: baseline / coordinated / swarm / swarm+recipes, M each, shuffled, all --no-learn,
so the Recipes learned in phase 1 stay frozen while they are evaluated.

Every run is appended to runs/protocol_v2.csv with the commit, phase, target, mode, seed,
start/end time, run id and exit code. The same model, workers, budget and code are used
for every run; the commit is tagged before the batch starts.
"""

import argparse
import asyncio
import csv
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
LOG = ROOT / "runs" / "protocol_v2.csv"
WORKERS, BUDGET, MINUTES = 6, 2_000_000, 15


def sh(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=BACKEND, capture_output=True, text=True)


def commit() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def run(phase: str, target: str, mode: str, seed: int, learn: bool, writer) -> None:
    start = datetime.now(timezone.utc)
    cmd = ["uv", "run", "python", "-m", "pheromone.run", "--target", target, "--mode", mode, "--seed", str(seed),
           "--workers", str(WORKERS), "--budget", str(BUDGET), "--minutes", str(MINUTES)]
    if not learn:
        cmd.append("--no-learn")
    res = sh(*cmd)
    lines = [l for l in res.stdout.strip().splitlines() if l and not l.startswith("{")]
    run_id = lines[-1] if lines else ""
    end = datetime.now(timezone.utc)
    row = [commit(), phase, target, mode, seed, start.isoformat(timespec="seconds"),
           end.isoformat(timespec="seconds"), run_id, res.returncode]
    writer.writerow(row)
    print(f"{end:%H:%M} {phase} {target:4} {mode:14} seed={seed:<3} -> {run_id or 'FAILED'} (exit {res.returncode})", flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--gym-runs", type=int, default=10)
    p.add_argument("--krr-runs", type=int, default=5)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--shuffle-seed", type=int, default=20261016)
    a = p.parse_args()
    if a.smoke:
        a.gym_runs, a.krr_runs = 1, 1
    rng = random.Random(a.shuffle_seed)

    print("resetting recipes graph and rebuilding targets", flush=True)
    sh("uv", "run", "python", "-c",
       "import asyncio; from pheromone.graph.client import Graph; asyncio.run(Graph('recipes').delete())")
    for target in ("gym", "krr"):
        r = sh("uv", "run", "python", "-m", "pheromone.repo.bootstrap", target, "--force")
        if r.returncode:
            sys.exit(f"bootstrap {target} failed:\n{r.stderr[-2000:]}")

    gym = [(m, s) for m in ("baseline", "coordinated", "swarm") for s in range(1, a.gym_runs + 1)]
    krr = [(m, s) for m in ("baseline", "coordinated", "swarm", "swarm+recipes") for s in range(1, a.krr_runs + 1)]
    rng.shuffle(gym)
    rng.shuffle(krr)

    LOG.parent.mkdir(exist_ok=True)
    new = not LOG.exists()
    with LOG.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["commit", "phase", "target", "mode", "seed", "start", "end", "run_id", "exit"])
        for mode, seed in gym:
            run("smoke" if a.smoke else "gym", "gym", mode, seed, learn=(mode == "swarm"), writer=w)
            f.flush()
        for mode, seed in krr:
            run("smoke" if a.smoke else "krr", "krr", mode, seed, learn=False, writer=w)
            f.flush()
    print("done", flush=True)


if __name__ == "__main__":
    main()
