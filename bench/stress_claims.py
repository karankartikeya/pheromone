"""Concurrency stress test for the coordination queries. No LLM, no tests: just the graph.

    uv run python ../bench/stress_claims.py --agents 30 --seconds 60     # from backend/

N agents hammer one graph for T seconds with the real queries (FRONTIER, CLAIM, REPORT,
lease release). Leases are short and some agents deliberately stall past
their lease before reporting, to force handoffs and stale reports. Afterwards we check:

1. No double claims: no two agents ever held overlapping, unreleased leases on one hypothesis.
2. Stale reports change nothing: every report whose lease had been taken over was rejected.
3. Pheromone is exactly what the accepted reports imply: replaying them in Python gives the
   same tau on every edge as the graph. (Evaporation is off here because its ticks race with
   reports at millisecond resolution; its clamp is covered by the unit tests.)

Prints claim/report latency percentiles and writes runs/stress_<agents>x<seconds>.json.
"""

import argparse
import asyncio
import json
import random
import time
import uuid
from collections import defaultdict

from pheromone.config import PARAMS, RUNS_DIR
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph, meter
from pheromone.graph.schema import ensure_indexes

LEASE_MS = 800
TMIN = PARAMS.tau_min


def now_ms() -> int:
    return int(time.time() * 1000)


BUSY = {"rejected": 0}


async def q(g: Graph, cypher: str, **params):
    """FalkorDB caps its query queue (MAX_QUEUED_QUERIES, 25 by default) and rejects the
    overflow with 'Max pending queries exceeded'. Back off with jitter and retry, and count it."""
    for attempt in range(50):
        try:
            return await g.q(cypher, **params)
        except Exception as e:
            if "Max pending queries" not in str(e):
                raise
            BUSY["rejected"] += 1
            await asyncio.sleep(random.uniform(0.005, 0.03) * (1 + attempt))
    raise RuntimeError("server stayed saturated")


async def seed(g: Graph, n_failures: int, per_failure: int, agents: int) -> None:
    await ensure_indexes(g)
    hyps = [{"f": f"f{i}", "h": f"f{i}#h{j}"} for i in range(n_failures) for j in range(per_failure)]
    await g.q(
        """
        UNWIND $hs AS x
        MERGE (f:Failure {id:x.f}) ON CREATE SET f.status = 'open', f.signature = 's'
        CREATE (f)-[:SUSPECTS {pheromone:$tau0}]->(:Hypothesis {id:x.h, status:'open', signature:'s',
                                                                eta:1.0, lease_until:0})
        """,
        hs=hyps, tau0=PARAMS.tau0,
    )
    await g.q("UNWIND $ids AS id CREATE (:Agent {id:id})", ids=[f"A{i}" for i in range(agents)])


async def agent(g: Graph, aid: str, stop_at: float, log: dict, rng: random.Random) -> None:
    while time.monotonic() < stop_at:
        t0 = time.perf_counter()
        rows = await q(g, Q.FRONTIER, limit=12, use_tau=True)
        log["frontier_ms"].append((time.perf_counter() - t0) * 1000)
        if not rows:
            await asyncio.sleep(0.02)
            continue
        hid = rng.choice(rows)["id"]
        t0 = time.perf_counter()
        claim_at = now_ms()
        won = await q(g, Q.CLAIM, hid=hid, agent=aid, now=claim_at, lease_ms=LEASE_MS)
        log["claim_ms"].append((time.perf_counter() - t0) * 1000)
        if not won:
            log["lost"] += 1
            continue
        log["claims"].append({"h": hid, "a": aid, "start": claim_at, "lease_until": claim_at + LEASE_MS})
        # simulated work; 10% of the time stall past the lease to force a handoff
        await asyncio.sleep(LEASE_MS * 1.6 / 1000 if rng.random() < 0.1 else rng.uniform(0.01, 0.15))
        outcome = "pass" if rng.random() < 0.15 else "fail"
        mult, add = (1.0, 1.0) if outcome == "pass" else (PARAMS.fail_mult, 0.0)
        t0 = time.perf_counter()
        at = now_ms()
        rows = await q(
            g, Q.REPORT, hid=hid, agent=aid, aid=f"{aid}-{uuid.uuid4().hex[:8]}", outcome=outcome, dh="x", diff="",
            fixed=1 if outcome == "pass" else 0, broken=0, ms=1, tok=0, now=at, mode="stress",
            mult=mult, add=add, tmin=TMIN, max_fails=10**9,
        )
        log["report_ms"].append((time.perf_counter() - t0) * 1000)
        accepted = bool(rows)
        log["reports"].append({"h": hid, "a": aid, "at": at, "claim": claim_at, "accepted": accepted,
                               "mult": mult, "add": add, "status": rows[0]["status"] if rows else None})


async def janitor(g: Graph, stop_at: float, log: dict) -> None:
    while time.monotonic() < stop_at:
        await asyncio.sleep(0.5)
        await q(g, Q.RELEASE_LEASES, now=now_ms())


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 2) if xs else 0.0


async def main(agents: int, seconds: float) -> None:
    g = Graph(f"stress:{uuid.uuid4().hex[:6]}")
    await seed(g, n_failures=40, per_failure=3, agents=agents)
    log = defaultdict(list)
    log["lost"] = 0
    rng = random.Random(7)
    stop_at = time.monotonic() + seconds
    writes0 = meter.total
    await asyncio.gather(janitor(g, stop_at, log),
                         *(agent(g, f"A{i}", stop_at, log, random.Random(rng.random())) for i in range(agents)))
    writes = meter.total - writes0

    # 1. no overlapping held claims: a claim is held from start until the earlier of its
    #    accepted report or its lease end; two holds on one hypothesis must not overlap
    released = {(r["h"], r["a"], r["claim"]): r["at"] for r in log["reports"] if r["accepted"]}
    holds = defaultdict(list)
    for c in log["claims"]:
        end = min(c["lease_until"], released.get((c["h"], c["a"], c["start"]), c["lease_until"]))
        holds[c["h"]].append((c["start"], end, c["a"]))
    double = 0
    for spans in holds.values():
        spans.sort()
        for (s1, e1, _), (s2, _, _) in zip(spans, spans[1:]):
            if s2 < e1:
                double += 1

    # 2. an accepted report must never follow another agent's takeover of that hypothesis
    def taken_over(r):
        return any(c["h"] == r["h"] and c["a"] != r["a"] and r["claim"] < c["start"] <= r["at"] for c in log["claims"])
    takeovers = sum(1 for r in log["reports"] if taken_over(r))
    accepted_after_takeover = sum(1 for r in log["reports"] if r["accepted"] and taken_over(r))
    stale = sum(1 for r in log["reports"] if not r["accepted"])

    # 3. replay accepted deposits in time order (serialized per hypothesis by the claim)
    tau = defaultdict(lambda: PARAMS.tau0)
    for r in sorted((r for r in log["reports"] if r["accepted"]), key=lambda r: r["at"]):
        tau[r["h"]] = max(TMIN, tau[r["h"]] * r["mult"] + r["add"])
    graph_tau = {row["h"]: row["p"] for row in await g.q(
        "MATCH (:Failure)-[s:SUSPECTS]->(h:Hypothesis) RETURN h.id AS h, s.pheromone AS p")}
    touched = {h for h in tau}
    tau_mismatch = sum(1 for h in touched if abs(graph_tau[h] - tau[h]) > 1e-6)

    result = {
        "agents": agents, "seconds": seconds, "lease_ms": LEASE_MS,
        "claims_won": len(log["claims"]), "claims_lost": log["lost"],
        "reports": len(log["reports"]), "stale_rejected": stale, "takeovers": takeovers,
        "graph_writes": writes, "writes_per_sec": round(writes / seconds, 1),
        "server_busy_rejections": BUSY["rejected"],
        "double_claims": double, "accepted_after_takeover": accepted_after_takeover, "pheromone_mismatches": tau_mismatch,
        "claim_ms_p50": pct(log["claim_ms"], 0.5), "claim_ms_p95": pct(log["claim_ms"], 0.95),
        "report_ms_p50": pct(log["report_ms"], 0.5), "report_ms_p95": pct(log["report_ms"], 0.95),
        "frontier_ms_p50": pct(log["frontier_ms"], 0.5), "frontier_ms_p95": pct(log["frontier_ms"], 0.95),
    }
    await g.delete()
    out = RUNS_DIR / f"stress_{agents}x{int(seconds)}.json"
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--agents", type=int, default=30)
    p.add_argument("--seconds", type=float, default=60)
    a = p.parse_args()
    asyncio.run(main(a.agents, a.seconds))
