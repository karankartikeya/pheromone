"""Baseline worker: the same agent with the shared memory taken away (the ablation).

What stays the same: model, budget, templates, proposer prompt, patching,
tests, the merger and the run branch everyone resets to.

What is removed: every read of the graph. A baseline agent learns which
failures exist by running the suite on the run branch itself, keeps its own
local candidate list and pheromone, and claims only in its own memory. It
never sees what other agents are doing, so two agents can work on the same
thing. Attempts are still written to the graph (write-only) so the metrics
and replay cover baseline runs the same way.
"""

import asyncio
import random
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from pheromone.config import PARAMS
from pheromone.graph import queries as Q
from pheromone.repo import imports
from pheromone.repo import worktrees as wt
from pheromone.repo.pytest_runner import run_pytest
from pheromone.seed import templates
from pheromone.seed.seeder import FailureSeed, group_failures, is_test_file
from pheromone.swarm import proposer, reporter
from pheromone.swarm.llm import PatchRequest, read_files
from pheromone.swarm.scoring import roulette_order
from pheromone.swarm.worker import RunCtx, now_ms


@dataclass
class LocalHyp:
    id: str
    failure: FailureSeed
    kind: str
    text: str
    file: str
    tau: float = PARAMS.tau0
    tries: int = 0
    fails: int = 0
    done: bool = False


class BaselineWorker:
    def __init__(self, agent_id: str, ctx: RunCtx, tree: Path, seed: int = 0):
        self.id, self.ctx, self.tree, self.g = agent_id, ctx, tree, ctx.graph
        self.rng = random.Random(seed)
        self.failures: dict[str, FailureSeed] = {}
        self.hyps: dict[str, LocalHyp] = {}
        self.history: list[dict] = []  # own attempts only
        self.proposals: dict[str, int] = {}
        self.green: set[str] = set()

    @property
    def alive(self) -> bool:
        return self.id not in self.ctx.killed and not self.ctx.stop.is_set() and not self.ctx.budget.exhausted

    async def beat(self, status: str, doing: str = "") -> None:  # write-only
        await self.g.q(Q.AGENT_HEARTBEAT, id=self.id, status=status, doing=doing, now=now_ms())
        self.ctx.emit({"type": "agent", "agent": self.id, "status": status, "doing": doing})

    async def sense(self) -> None:
        """Learn the current failures from the code on the run branch, not from the graph."""
        await wt.reset(self.tree, self.ctx.run_ref)
        run = await run_pytest(self.tree, self.ctx.python)
        self.green = run.passed
        current = {f.id: f for f in group_failures(self.tree, run)}
        for fid in set(self.failures) - set(current):
            for h in self.hyps.values():
                if h.failure.id == fid:
                    h.done = True
        for fid, f in current.items():
            if fid not in self.failures:
                for kind, text in templates.for_signature(f.signature):
                    hid = f"{fid}#{kind}"
                    self.hyps.setdefault(hid, LocalHyp(hid, f, kind, text, f.file))
            else:
                for h in self.hyps.values():
                    if h.failure.id == fid:
                        h.failure = f
        self.failures = current

    def frontier(self) -> list[dict]:
        rows = [
            {"id": h.id, "tau": h.tau, "eta": 1.0, "tries": h.tries, "crowd": 0, "siblings": 0}
            for h in self.hyps.values() if not h.done and h.failure.id in self.failures
        ]
        return sorted(rows, key=lambda r: -r["tau"])[: PARAMS.frontier_limit]

    async def run(self) -> None:
        while self.alive:
            await self.beat("sensing")
            await self.sense()
            if not self.failures:
                break
            rows = self.frontier()
            if rows:
                await self.attempt(self.hyps[roulette_order(rows, self.rng)[0]["id"]])
            elif not await self.propose():
                break  # everything this agent knows is retired and its proposals are used up
        await self.beat("killed" if self.id in self.ctx.killed else "done")

    async def propose(self) -> bool:
        for fid, f in self.failures.items():
            if self.proposals.get(fid, 0) >= proposer.MAX_PROPOSALS:
                continue
            self.proposals[fid] = self.proposals.get(fid, 0) + 1
            await self.beat("proposing", fid)
            test_files = {t.split("::")[0] for t in f.tests}
            deps = {b for a, b in imports.scan(self.tree) if a in test_files}
            candidates = {p for p in [f.file, *deps] if p and not is_test_file(p)}
            if not candidates:
                continue
            run = await run_pytest(self.tree, self.ctx.python, sorted(test_files))
            trace = "\n\n".join(r.longrepr[-2500:] for r in run.red[:3]) or f.message
            tried = [h.text for h in self.hyps.values() if h.failure.id == fid]
            parts = [f"## Failing tests\n{', '.join(f.tests)}\n\n## Traceback\n{trace}"]
            if tried:
                parts.append("## Already tried and failed\n" + "\n".join(f"- {t}" for t in tried))
            parts += [f"## {p}\n```python\n{s}\n```" for p, s in read_files(self.tree, sorted(candidates)).items()]
            parts.append(f"## Candidate files\n{', '.join(sorted(candidates))}")
            text, tokens = await self.ctx.llm.complete(proposer.INSTRUCTIONS, "\n\n".join(parts))
            self.ctx.budget.used += tokens
            created = []
            for i in proposer.validate(proposer.parse_proposals(text), candidates):
                hid = f"{fid}#llm-{i['kind']}"
                if hid not in self.hyps:
                    self.hyps[hid] = LocalHyp(hid, f, f"llm-{i['kind']}", i["text"], i["file"])
                    created.append(hid)
            self.ctx.emit({"type": "proposed", "agent": self.id, "failure": fid, "hypotheses": created, "tokens": tokens})
            return True
        return False

    async def attempt(self, h: LocalHyp) -> None:
        self.ctx.emit({"type": "claim", "agent": self.id, "hypothesis": h.id, "tau": h.tau})
        await self.beat("patching", h.kind)
        t0 = time.monotonic()
        prior = [a for a in self.history if a["hypothesis"] == h.id]
        req = PatchRequest(hypothesis=h.text, signature=h.failure.signature, failure=h.failure.message,
                           tests=h.failure.tests, files=read_files(self.tree, [h.file]), prior_attempts=prior)
        res = await self.ctx.llm.patch(req)
        self.ctx.budget.used += res.tokens
        if not self.alive:
            return

        diff, verdict = "", None
        try:
            wt.apply_edits(self.tree, res.edits, allowed={h.file})
            diff = await wt.diff(self.tree)
            if not diff.strip():
                raise wt.ApplyError("no change")
        except wt.ApplyError:
            verdict = reporter.Verdict("apply_error")
        dh = wt.diff_hash(diff) if diff else "none"
        if verdict is None and any(a["diff_hash"] == dh and a["outcome"] != "pass" for a in self.history):
            verdict = reporter.Verdict("duplicate")
        if verdict is None:
            await self.beat("testing", h.kind)
            test_files = sorted({t.removesuffix("::__collect__") for t in h.failure.tests})
            run = await run_pytest(self.tree, self.ctx.python, test_files)
            verdict = reporter.decide(self.tree, h.failure.id, h.failure.tests, self.green, run)

        mult, add = verdict.deposit()
        h.tries += 1
        h.tau = max(PARAMS.tau_min, h.tau * mult + add)
        if verdict.outcome == "pass":
            h.done = True
        else:
            h.fails += 1
            h.done = h.fails >= PARAMS.max_fails  # same retirement rule as the swarm
        aid = f"{self.id}-{uuid.uuid4().hex[:8]}"
        self.history.append({"id": aid, "agent": self.id, "hypothesis": h.id, "outcome": verdict.outcome,
                             "diff": diff, "diff_hash": dh})
        # write-only record for metrics, replay and the merger
        await self.g.q(
            Q.RECORD_BASELINE_ATTEMPT, fid=h.failure.id, hid=h.id, kind=h.kind, text=h.text, file=h.file,
            sig=h.failure.signature, agent=self.id, aid=aid, outcome=verdict.outcome, dh=dh, diff=diff,
            fixed=len(verdict.resolved), broken=len(verdict.broken),
            ms=int((time.monotonic() - t0) * 1000), tok=res.tokens, now=now_ms(),
        )
        self.ctx.emit({
            "type": "attempt", "agent": self.id, "hypothesis": h.id, "failure": h.failure.id,
            "outcome": verdict.outcome, "mult": mult, "add": add, "resolved": len(verdict.resolved),
            "broken": len(verdict.broken), "tokens": res.tokens,
        })
        if verdict.outcome == "pass" and self.ctx.merger is not None:
            await self.ctx.merger.submit(self.id, aid, h.id, diff, verdict)
