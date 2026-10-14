"""Constants and environment. Every tunable lives here and is logged on the Run node."""

import os
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_NAME = "pheromone"

ROOT = Path(__file__).resolve().parents[3]
TARGETS_DIR = ROOT / "targets"
WORKTREES_DIR = ROOT / "worktrees"
RUNS_DIR = ROOT / "runs"

FALKORDB_HOST = os.environ.get("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.environ.get("FALKORDB_PORT", "6380"))
FALKORDB_PASSWORD = os.environ.get("FALKORDB_PASSWORD") or None

RECIPES_GRAPH = "recipes"


def run_graph(run_id: str) -> str:
    return f"run:{run_id}"


@dataclass(frozen=True)
class Params:
    """Swarm constants. Starting points from the plan; tuned Thursday."""

    workers: int = 6
    alpha: float = 1.0
    beta: float = 2.0
    tau0: float = 0.5
    tau_min: float = 0.05
    keep: float = 0.95  # evaporation factor per tick
    evaporate_every_s: float = 10.0
    crystallize_every_s: float = 60.0
    lease_ms: int = 120_000
    frontier_limit: int = 12
    pass_per_fixed: float = 1.0
    pass_per_broken: float = -0.5
    fail_mult: float = 0.7
    max_children: int = 2
    max_depth: int = 2
    test_timeout_s: int = 120

    def as_props(self) -> dict:
        return asdict(self)


PARAMS = Params()
