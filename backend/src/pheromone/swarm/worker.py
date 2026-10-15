"""One swarm worker. Every worker runs this same loop with no knowledge of the others.

1. read frontier  2. roulette  3. claim (CAS)  4. patch (LLM)  5. run tests
6. report (deterministic, deposits pheromone)  7. pass -> merge gate
"""

import asyncio
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pheromone.config import PARAMS
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph
from pheromone.repo import worktrees as wt
from pheromone.repo.pytest_runner import run_pytest
from pheromone.swarm import reporter
from pheromone.swarm.llm import PatchRequest, read_files
from pheromone.swarm.scoring import roulette_order


@dataclass
class Budget:
    limit: int
    used: int = 0

    @property
    def exhausted(self) -> bool:
        return self.limit > 0 and self.used >= self.limit


@dataclass
class RunCtx:
    graph: Graph
    run_id: str
    mode: str
    repo: Path  # target repo (shared git object store)
    python: Path  # target repo interpreter
    run_ref: str  # branch the merger commits to; workers reset to it
    llm: object
    budget: Budget
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    killed: set[str] = field(default_factory=set)
    emit: Callable[[dict], None] = lambda e: None
    merger: object | None = None


def now_ms() -> int:
    return int(time.time() * 1000)


class Worker:
    def __init__(self, agent_id: str, ctx: RunCtx, tree: Path, seed: int = 0):
        self.id = agent_id
        self.ctx = ctx
        self.tree = tree
        self.rng = random.Random(seed)
        self.g = ctx.graph

    @property
    def alive(self) -> bool:
        return self.id not in self.ctx.killed and not self.ctx.stop.is_set() and not self.ctx.budget.exhausted

    async def beat(self, status: str, doing: str = "") -> None:
        await self.g.q(Q.AGENT_HEARTBEAT, id=self.id, status=status, doing=doing, now=now_ms())
        self.ctx.emit({"type": "agent", "agent": self.id, "status": status, "doing": doing})

    async def run(self) -> None:
        await self.beat("reading frontier")
        while self.alive:
            hid = await self.claim_next()
            if hid is None:
                work = (await self.g.q(Q.OPEN_WORK))[0]
                if work["failures"] == 0:
                    break
                await asyncio.sleep(1 + self.rng.random())
                continue
            await self.attempt(hid)
        if self.id in self.ctx.killed:
            await self.beat("killed")  # lease is NOT released: the evaporator reopens it later
        else:
            await self.beat("done")

    async def claim_next(self) -> str | None:
        rows = await self.g.q(Q.FRONTIER, limit=PARAMS.frontier_limit)
        for row in roulette_order(rows, self.rng):
            won = await self.g.q(Q.CLAIM, hid=row["id"], agent=self.id, now=now_ms(), lease_ms=PARAMS.lease_ms)
            if won:
                self.ctx.emit({"type": "claim", "agent": self.id, "hypothesis": row["id"], "tau": row["tau"]})
                return row["id"]
            self.ctx.emit({"type": "claim_lost", "agent": self.id, "hypothesis": row["id"]})
        return None

    async def attempt(self, hid: str) -> None:
        h = (await self.g.q(Q.HYPOTHESIS_CONTEXT, hid=hid))[0]
        attempts = await self.g.q(Q.ATTEMPTS_ON, hid=hid)
        follows = attempts[-1]["id"] if attempts and attempts[-1]["agent"] != self.id else None
        targets = [r["nodeid"] for r in await self.g.q(Q.FAILURE_TESTS, fid=h["failure_id"])]
        blast = [r["nodeid"] for r in await self.g.q(Q.BLAST_RADIUS, path=h["file"])]
        tests = sorted(set(targets) | set(blast))
        green = set((await self.g.q(Q.GREEN_AMONG, ids=tests))[0]["green"])

        await self.beat("patching", h["kind"])
        await wt.reset(self.tree, self.ctx.run_ref)
        t0 = time.monotonic()
        req = PatchRequest(
            hypothesis=h["text"], signature=h["signature"], failure=h["message"] or "",
            tests=targets, files=read_files(self.tree, [h["file"]]),
            prior_attempts=attempts, recipe_example=h["example"],
        )
        res = await self.ctx.llm.patch(req)
        self.ctx.budget.used += res.tokens
        if not self.alive:
            return  # killed mid-attempt: keep the lease, report nothing

        diff, verdict = "", None
        try:
            wt.apply_edits(self.tree, res.edits, allowed={h["file"]})
            diff = await wt.diff(self.tree)
            if not diff.strip():
                raise wt.ApplyError("no change")
        except wt.ApplyError:
            verdict = reporter.Verdict("apply_error")
        dh = wt.diff_hash(diff) if diff else "none"
        if verdict is None and (await self.g.q(Q.FAILED_DIFF, dh=dh))[0]["n"] > 0:
            verdict = reporter.Verdict("duplicate")
        if verdict is None:
            await self.beat("testing", h["kind"])
            nodeids = sorted({t.removesuffix("::__collect__") for t in tests})
            run = await run_pytest(self.tree, self.ctx.python, nodeids)
            verdict = reporter.decide(self.tree, h["failure_id"], targets, green, run)
        if not self.alive:
            return

        await self.beat("reporting", verdict.outcome)
        aid = f"{self.id}-{uuid.uuid4().hex[:8]}"
        ok = await reporter.report(
            self.g, hid=hid, agent=self.id, aid=aid, verdict=verdict, diff=diff, diff_hash=dh,
            ms=int((time.monotonic() - t0) * 1000), tokens=res.tokens, mode=self.ctx.mode, follows=follows,
        )
        mult, add = verdict.deposit()
        self.ctx.emit({
            "type": "attempt", "agent": self.id, "hypothesis": hid, "failure": h["failure_id"],
            "outcome": verdict.outcome if ok else "stale", "mult": mult, "add": add,
            "resolved": len(verdict.resolved), "broken": len(verdict.broken), "tokens": res.tokens,
        })
        if ok and verdict.outcome == "pass" and self.ctx.merger is not None:
            await self.ctx.merger.submit(self.id, aid, hid, diff, verdict)
        await self.beat("reading frontier")
