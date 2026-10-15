"""Deterministic reporter: tests decide the outcome, and only this module writes pheromone.

pass  = the hypothesis' own failure no longer occurs in its target tests, and no
        test that was green before is red now. Targets may still be red for a
        *different* reason: fixing an import error often reveals the next layer
        (e.g. json_encoders fixed -> a .json() call underneath now fails). Those
        reds become new Failures when the patch merges.
fail  = otherwise (including apply errors, timeouts and duplicate diffs).
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

from pheromone.config import PARAMS
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph
from pheromone.repo.pytest_runner import Red, TestRun
from pheromone.seed.seeder import failure_key


@dataclass
class Verdict:
    outcome: str  # pass | fail | apply_error | timeout | duplicate
    resolved: list[str] = field(default_factory=list)  # targets no longer failing with this failure
    fixed: list[str] = field(default_factory=list)  # targets now fully green
    broken: list[str] = field(default_factory=list)  # green before, red now
    revealed: list[Red] = field(default_factory=list)  # reds with a different failure id

    def deposit(self, p=PARAMS) -> tuple[float, float]:
        """(mult, add) for the report query."""
        if self.outcome == "pass":
            return 1.0, p.pass_per_fixed * len(self.resolved) + p.pass_per_broken * len(self.broken)
        return p.fail_mult, 0.0


def decide(worktree: Path, failure_id: str, targets: list[str], green_before: set[str], run: TestRun) -> Verdict:
    if run.timed_out:
        return Verdict("timeout")
    red_by_id = {r.nodeid: r for r in run.red}
    same, revealed = set(), []
    for r in run.red:
        if failure_key(worktree, r)[0] == failure_id:
            same.add(r.nodeid)
        elif r.nodeid not in green_before:
            revealed.append(r)
    # A collection pseudo-test disappears once its module imports; its real tests appear.
    resolved = [t for t in targets if t not in same]
    fixed = [t for t in targets if t in run.passed or (t.endswith("::__collect__") and t not in red_by_id)]
    broken = sorted(t for t in green_before if t in red_by_id)
    ok = not same and not broken
    return Verdict("pass" if ok else "fail", resolved, fixed, broken, revealed)


async def report(g: Graph, *, hid: str, agent: str, aid: str, verdict: Verdict, diff: str, diff_hash: str,
                 ms: int, tokens: int, mode: str, follows: str | None = None) -> bool:
    """Write the Attempt and deposit pheromone. Returns False if the lease was lost (stale)."""
    mult, add = verdict.deposit()
    now = int(time.time() * 1000)
    rows = await g.q(
        Q.REPORT, hid=hid, agent=agent, aid=aid, outcome=verdict.outcome, dh=diff_hash, diff=diff,
        fixed=len(verdict.resolved), broken=len(verdict.broken), ms=ms, tok=tokens, now=now, mode=mode,
        mult=mult, add=add, tmin=PARAMS.tau_min,
    )
    if not rows:
        await g.q(Q.REPORT_STALE, hid=hid, agent=agent, aid=aid, dh=diff_hash, ms=ms, tok=tokens, now=now, mode=mode)
        return False
    if verdict.fixed:
        await g.q(Q.LINK_FIXED, aid=aid, nodeids=verdict.fixed)
    if verdict.broken:
        await g.q(Q.LINK_BROKE, aid=aid, nodeids=verdict.broken)
    if follows:
        await g.q(Q.LINK_FOLLOWED, prev=follows, next=aid)
    return True
