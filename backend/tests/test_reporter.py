import uuid
from pathlib import Path

import pytest

from pheromone.config import PARAMS
from pheromone.graph.client import Graph
from pheromone.graph.schema import ensure_indexes
from pheromone.repo.pytest_runner import Red, TestRun
from pheromone.swarm.reporter import Verdict, decide, report

DEP = "PydanticDeprecatedSince20"
ENC = "`json_encoders` is deprecated."
FID = "json-encoders@pmg/common.py"
T5, T6 = "tests/test_m05.py::__collect__", "tests/test_m06.py::__collect__"


def red(nodeid, msg, frame=("pmg/common.py", 6)):
    return Red(nodeid=nodeid, kind="collect", exc_type=DEP, message=msg, frames=[frame])


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "pmg").mkdir()
    (tmp_path / "pmg/common.py").write_text("x = 1\n")
    (tmp_path / "pmg/m06.py").write_text("x = 1\n")
    return tmp_path


def test_same_failure_still_there_is_fail(tree):
    run = TestRun(red=[red(T5, ENC), red(T6, ENC)])
    v = decide(tree, FID, [T5, T6], set(), run)
    assert v.outcome == "fail" and v.resolved == []


def test_failure_gone_and_targets_green_is_pass(tree):
    run = TestRun(passed={"tests/test_m05.py::test_a"})
    v = decide(tree, FID, [T5], set(), run)
    assert v.outcome == "pass" and v.resolved == [T5] and v.fixed == [T5]


def test_next_layer_revealed_still_counts_as_pass(tree):
    # json_encoders fixed; underneath, m06 calls .json() and now fails at call time
    nxt = Red("tests/test_m06.py::test_wire", "test", DEP, "The `json` method is deprecated", [("pmg/m06.py", 1)])
    run = TestRun(passed={"tests/test_m05.py::test_a"}, red=[nxt])
    v = decide(tree, FID, [T5, T6], set(), run)
    assert v.outcome == "pass"
    assert v.resolved == [T5, T6]
    assert [r.nodeid for r in v.revealed] == ["tests/test_m06.py::test_wire"]


def test_breaking_a_green_test_is_fail(tree):
    broke = Red("tests/test_m27.py::test_x", "test", "AssertionError", "assert 1 == 2", [("pmg/m06.py", 1)])
    run = TestRun(red=[broke])
    v = decide(tree, FID, [T5], {"tests/test_m27.py::test_x"}, run)
    assert v.outcome == "fail" and v.broken == ["tests/test_m27.py::test_x"]


def test_timeout(tree):
    assert decide(tree, FID, [T5], set(), TestRun(timed_out=True)).outcome == "timeout"


def test_deposit_values():
    assert Verdict("pass", resolved=["a", "b"]).deposit() == (1.0, 2 * PARAMS.pass_per_fixed)
    assert Verdict("fail").deposit() == (PARAMS.fail_mult, 0.0)


@pytest.fixture
async def g():
    graph = Graph(f"test:{uuid.uuid4().hex[:8]}")
    await ensure_indexes(graph)
    await graph.q(
        """
        CREATE (f:Failure {id:'f1', status:'open'})-[:SUSPECTS {pheromone:0.5}]->
               (h:Hypothesis {id:'h1', status:'claimed', claimed_by:'A0', lease_until:9e15}),
               (:Agent {id:'A0'}), (:Agent {id:'A1'}), (:Test {nodeid:'t1'})
        """
    )
    yield graph
    await graph.delete()


async def tau(g):
    return (await g.q("MATCH ()-[s:SUSPECTS]->() RETURN s.pheromone AS p"))[0]["p"]


async def test_report_pass_reinforces_and_links(g):
    ok = await report(g, hid="h1", agent="A0", aid="a1", verdict=Verdict("pass", resolved=["t1"], fixed=["t1"]),
                      diff="d", diff_hash="x", ms=1, tokens=10, mode="swarm")
    assert ok and await tau(g) == pytest.approx(1.5)
    rows = await g.q("MATCH (:Attempt {id:'a1'})-[:FIXED]->(t:Test) RETURN t.nodeid AS n")
    assert rows == [{"n": "t1"}]


async def test_report_from_non_owner_is_stale(g):
    ok = await report(g, hid="h1", agent="A1", aid="a2", verdict=Verdict("pass", resolved=["t1"]),
                      diff="d", diff_hash="x", ms=1, tokens=10, mode="swarm")
    assert not ok and await tau(g) == pytest.approx(0.5)
    rows = await g.q("MATCH (a:Attempt {id:'a2'}) RETURN a.outcome AS o")
    assert rows == [{"o": "stale"}]
