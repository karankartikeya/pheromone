"""Night-1 gate: the core queries behave as the plan assumes, against a live FalkorDB."""

import asyncio
import uuid

import pytest

from pheromone.config import PARAMS
from pheromone.graph import queries as Q
from pheromone.graph.client import Graph
from pheromone.graph.schema import ensure_indexes

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def g():
    graph = Graph(f"test:{uuid.uuid4().hex[:8]}")
    await ensure_indexes(graph)
    yield graph
    await graph.delete()


async def seed_one(g: Graph, agents: int) -> None:
    await g.q(
        """
        CREATE (f:Failure {id:'f1', signature:'dict-call', status:'open'})
               -[:SUSPECTS {pheromone:$tau0}]->
               (h:Hypothesis {id:'h1', text:'use model_dump', kind:'model_dump',
                              signature:'dict-call', status:'open', eta:1.0})
        """,
        tau0=PARAMS.tau0,
    )
    for i in range(agents):
        await g.q("CREATE (:Agent {id:$id})", id=f"A{i}")


async def claim(g: Graph, agent: str, now: int) -> bool:
    rows = await g.q(Q.CLAIM, hid="h1", agent=agent, now=now, lease_ms=PARAMS.lease_ms)
    return len(rows) == 1


async def test_claim_race_has_one_winner(g):
    await seed_one(g, 20)
    results = await asyncio.gather(*(claim(g, f"A{i}", 1_000) for i in range(20)))
    assert sum(results) == 1
    rows = await g.q("MATCH (:Agent)-[c:CLAIMED]->(:Hypothesis) RETURN count(c) AS n")
    assert rows[0]["n"] == 1


async def test_expired_lease_is_handoff(g):
    await seed_one(g, 2)
    assert await claim(g, "A0", 1_000)
    assert not await claim(g, "A1", 2_000)
    assert await claim(g, "A1", 1_000 + PARAMS.lease_ms + 1)


async def report(g, agent, outcome, mult, add, aid="a1"):
    return await g.q(
        Q.REPORT, hid="h1", agent=agent, aid=aid, outcome=outcome, dh="x", diff="",
        fixed=0, broken=0, ms=1, tok=1, now=5, mode="swarm",
        mult=mult, add=add, tmin=PARAMS.tau_min,
    )


async def tau(g) -> float:
    rows = await g.q("MATCH (:Failure)-[s:SUSPECTS]->(:Hypothesis {id:'h1'}) RETURN s.pheromone AS p")
    return rows[0]["p"]


async def test_stale_report_changes_nothing(g):
    await seed_one(g, 2)
    assert await claim(g, "A0", 1_000)
    assert await claim(g, "A1", 1_000 + PARAMS.lease_ms + 1)  # A0's lease expired
    assert await report(g, "A0", "pass", 1.0, 1.0) == []
    assert await tau(g) == PARAMS.tau0
    rows = await g.q("MATCH (h:Hypothesis {id:'h1'}) RETURN h.claimed_by AS c")
    assert rows[0]["c"] == "A1"


async def test_pass_deposit_is_clamped(g):
    await seed_one(g, 1)
    assert await claim(g, "A0", 1_000)
    await report(g, "A0", "pass", 1.0, -1.5)  # fixed=0, broken=3
    assert await tau(g) == pytest.approx(PARAMS.tau_min)


async def test_evaporation_floor(g):
    await seed_one(g, 1)
    for _ in range(100):
        await g.q(Q.EVAPORATE, keep=PARAMS.keep, tmin=PARAMS.tau_min)
    assert await tau(g) == pytest.approx(PARAMS.tau_min)


async def test_blast_radius_includes_own_tests(g):
    await g.q(
        """
        CREATE (c:File {path:'pmg/common.py'}), (m:File {path:'pmg/m05.py'}),
               (tc:File {path:'tests/test_m05.py'}), (tl:File {path:'tests/test_common.py'}),
               (m)-[:IMPORTS]->(c), (tc)-[:IMPORTS]->(m), (tl)-[:IMPORTS]->(c),
               (:Test {nodeid:'tests/test_m05.py::a'})-[:DEFINED_IN]->(tc),
               (:Test {nodeid:'tests/test_common.py::b'})-[:DEFINED_IN]->(tl)
        """
    )
    rows = await g.q(Q.BLAST_RADIUS, path="pmg/common.py")
    assert {r["nodeid"] for r in rows} == {"tests/test_m05.py::a", "tests/test_common.py::b"}
    rows = await g.q(Q.BLAST_RADIUS, path="tests/test_m05.py")
    assert {r["nodeid"] for r in rows} == {"tests/test_m05.py::a"}


async def test_pagerank_and_wcc_run(g):
    await g.q(
        """
        CREATE (a:File {path:'a'}), (b:File {path:'b'}), (c:File {path:'c'}),
               (a)-[:IMPORTS]->(b), (c)-[:IMPORTS]->(b),
               (:Failure {id:'f1'})-[:IN]->(a), (:Failure {id:'f2'})-[:IN]->(c)
        """
    )
    pr = await g.q(Q.PAGERANK)
    assert pr[0]["path"] == "b"
    comps = await g.q(Q.WCC)
    assert len(comps) >= 2


async def test_evaporator_tick_releases_expired_leases(g):
    from pheromone.swarm.evaporator import tick

    await seed_one(g, 1)
    assert await claim(g, "A0", 1_000)  # lease long expired by wall-clock time
    assert await tick(g) == ["h1"]
    assert await tau(g) == pytest.approx(PARAMS.tau0 * PARAMS.keep)
