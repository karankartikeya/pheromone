"""Merge gate (environment job, not an orchestrator).

Serialized: one merge at a time onto the run branch. For each passing attempt:
apply the diff to the merge worktree, re-check the blast radius on top of
everything merged so far, commit, rerun the full suite, then sync the graph:
close failures that are gone, open the ones the fix revealed.
"""

import asyncio
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from pheromone.config import PARAMS
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph
from pheromone.repo import worktrees as wt
from pheromone.repo.pytest_runner import run_pytest
from pheromone.seed.seeder import add_failures, group_failures, sync_tests
from pheromone.swarm import reporter


class Merger:
    def __init__(self, g: Graph, repo: Path, tree: Path, python: Path, branch: str, mode: str,
                 emit: Callable[[dict], None] = lambda e: None):
        self.g, self.repo, self.tree, self.python = g, repo, tree, python
        self.branch, self.mode, self.emit = branch, mode, emit
        self.lock = asyncio.Lock()
        self.merged = 0

    @classmethod
    async def create(cls, g: Graph, repo: Path, tree: Path, python: Path, run_id: str, base: str,
                     mode: str, emit=lambda e: None) -> "Merger":
        branch = f"run/{run_id}"
        await wt.git(repo, "branch", "-f", branch, base)
        tree.parent.mkdir(parents=True, exist_ok=True)
        await wt.git(repo, "worktree", "add", "-f", str(tree), branch)
        return cls(g, repo, tree, python, branch, mode, emit)

    async def submit(self, agent: str, aid: str, hid: str, diff: str, verdict: reporter.Verdict) -> bool:
        async with self.lock:
            return await self._merge(agent, aid, hid, diff)

    async def _reject(self, aid: str, hid: str, agent: str, reason: str) -> bool:
        await wt.reset(self.tree, "HEAD")
        await self.g.q(Q.MERGE_REJECTED, aid=aid, mult=PARAMS.fail_mult, tmin=PARAMS.tau_min)
        self.emit({"type": "merge_rejected", "agent": agent, "hypothesis": hid, "reason": reason})
        return False

    async def _merge(self, agent: str, aid: str, hid: str, diff: str) -> bool:
        # 0. someone else's merge already closed this failure while we worked on it
        status = await self.g.q(Q.FAILURE_OF_ATTEMPT, aid=aid)
        if status and status[0]["status"] != "open":
            await self.g.q(Q.MARK_SUPERSEDED, aid=aid)
            self.emit({"type": "superseded", "agent": agent, "hypothesis": hid})
            return False

        # 1. the gate's test selection, run once on the current run branch as the baseline
        #    (tests can depend on order and shared state, so compare like with like)
        h = (await self.g.q(Q.HYPOTHESIS_CONTEXT, hid=hid))[0]
        targets = [r["nodeid"] for r in await self.g.q(Q.FAILURE_TESTS, fid=h["failure_id"])]
        blast = [r["nodeid"] for r in await self.g.q(Q.BLAST_RADIUS, path=h["file"])]
        selection = sorted({t.removesuffix("::__collect__") for t in set(targets) | set(blast)})
        before = await run_pytest(self.tree, self.python, selection)

        # 2. apply on top of everything merged so far
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False) as f:
            f.write(diff)
        try:
            await wt.git(self.tree, "apply", "--3way", f.name)
        except RuntimeError as e:
            return await self._reject(aid, hid, agent, f"conflict: {str(e)[-200:]}")
        finally:
            Path(f.name).unlink(missing_ok=True)

        # 3. blast-radius gate against the same selection
        gate = await run_pytest(self.tree, self.python, selection)
        v = reporter.decide(self.tree, h["failure_id"], targets, before.passed, gate)
        if v.outcome != "pass":
            return await self._reject(aid, hid, agent, f"gate: {v.outcome}, broken={v.broken[:3]}")

        # 4. commit to the run branch (workers reset to it on their next attempt)
        await wt.git(self.tree, "add", "-A")
        await wt.git(self.tree, "commit", "-q", "-m", f"{agent}: {h['kind']} on {h['file']} ({h['signature']})")
        commit = (await wt.git(self.tree, "rev-parse", "HEAD")).strip()
        await self.g.q(Q.MARK_MERGED, aid=aid, commit=commit)
        self.merged += 1

        # 5. full-suite rerun and graph sync
        full = await run_pytest(self.tree, self.python)
        await sync_tests(self.g, full)
        await self.g.q(
            "MATCH (t:Test) WHERE t.nodeid ENDS WITH '::__collect__' AND NOT t.nodeid IN $red "
            "SET t.status = 'resolved'", red=sorted(full.red_ids),
        )
        failures = group_failures(self.tree, full)
        hyps, unseeded = await add_failures(self.g, failures, self.mode)
        closed = (await self.g.q(Q.CLOSE_FAILURES, open_ids=[f.id for f in failures],
                                 now=int(time.time() * 1000)))[0]["closed"]
        suite = (await self.g.q(Q.SUITE_STATUS))[0]
        self.emit({
            "type": "merged", "agent": agent, "hypothesis": hid, "commit": commit[:8],
            "closed": closed, "revealed": sorted({x["failure"] for x in hyps} | set(unseeded)),
            "green": suite["green"], "red": suite["red"],
        })
        return True
