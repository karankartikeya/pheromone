"""Copy recorded run graphs (and the recipes graph) to a FalkorDB Cloud instance, read-only for judges.

    uv run python ../bench/copy_to_cloud.py run:krr-swarm-1015-185816 recipes ...    # from backend/

Credentials come from backend/.env: FALKORDB_CLOUD_HOST, FALKORDB_CLOUD_PORT, FALKORDB_CLOUD_PASSWORD
(and optionally FALKORDB_CLOUD_USERNAME). Graphs are rebuilt with plain Cypher rather than DUMP/RESTORE,
so the copy does not depend on both servers running the same FalkorDB version. Node and edge counts
are compared after each copy.

The copies carry no indexes: judges run small read-only queries on ~200-node graphs, and on a
free 100 MB instance 51 graphs with nine indexes each used most of the memory. The temporary
_cid indexes used while copying edges are dropped at the end.
"""

import asyncio
import os
import sys

from falkordb.asyncio import FalkorDB

from pheromone import config  # loads backend/.env
from pheromone.graph.client import Graph

BATCH = 500


def cloud(local_test: bool) -> FalkorDB:
    if local_test:  # copy onto the local server under a prefix, to test the copy itself
        return FalkorDB(host=config.FALKORDB_HOST, port=config.FALKORDB_PORT)
    host = os.environ.get("FALKORDB_CLOUD_HOST")
    if not host:
        sys.exit("set FALKORDB_CLOUD_HOST / FALKORDB_CLOUD_PORT / FALKORDB_CLOUD_PASSWORD in backend/.env")
    port = int(os.environ.get("FALKORDB_CLOUD_PORT", "6379"))
    if host in ("localhost", "127.0.0.1", "::1") and port == config.FALKORDB_PORT:
        sys.exit("cloud target is the local FalkorDB; refusing (the copy deletes the destination first)")
    return FalkorDB(host=host, port=int(os.environ.get("FALKORDB_CLOUD_PORT", "6379")),
                    username=os.environ.get("FALKORDB_CLOUD_USERNAME") or None,
                    password=os.environ.get("FALKORDB_CLOUD_PASSWORD") or None)


async def copy(name: str, dst_db: FalkorDB, prefix: str = "") -> None:
    src = Graph(name)
    nodes = await src.ro("MATCH (n) RETURN id(n) AS id, labels(n)[0] AS label, properties(n) AS props")
    edges = await src.ro(
        "MATCH (a)-[e]->(b) RETURN id(a) AS a, id(b) AS b, type(e) AS type, properties(e) AS props")
    dst = dst_db.select_graph(prefix + name)
    try:
        await dst.delete()
    except Exception:
        pass
    by_label: dict[str, list] = {}
    for n in nodes:
        by_label.setdefault(n["label"], []).append({"cid": n["id"], "props": n["props"]})
    for label, rows in by_label.items():
        for i in range(0, len(rows), BATCH):
            await dst.query(f"UNWIND $rows AS r CREATE (n:`{label}`) SET n = r.props, n._cid = r.cid",
                            {"rows": rows[i:i + BATCH]})
    for label in by_label:  # index the temporary id so edge matches are lookups, not scans
        try:
            await dst.query(f"CREATE INDEX FOR (n:`{label}`) ON (n._cid)")
        except Exception:
            pass
    label_of = {n["id"]: n["label"] for n in nodes}
    groups: dict[tuple, list] = {}
    for e in edges:
        key = (e["type"], label_of[e["a"]], label_of[e["b"]])
        groups.setdefault(key, []).append({"a": e["a"], "b": e["b"], "props": e["props"]})
    for (etype, la, lb), rows in groups.items():
        for i in range(0, len(rows), BATCH):
            await dst.query(
                f"UNWIND $rows AS r MATCH (a:`{la}` {{_cid:r.a}}), (b:`{lb}` {{_cid:r.b}}) "
                f"CREATE (a)-[e:`{etype}`]->(b) SET e = r.props",
                {"rows": rows[i:i + BATCH]})
    await dst.query("MATCH (n) REMOVE n._cid")
    for label in by_label:
        try:
            await dst.query(f"DROP INDEX ON :`{label}`(_cid)")
        except Exception:
            pass
    got_n = (await dst.ro_query("MATCH (n) RETURN count(n)")).result_set[0][0]
    got_e = (await dst.ro_query("MATCH ()-[e]->() RETURN count(e)")).result_set[0][0]
    status = "ok" if (got_n, got_e) == (len(nodes), len(edges)) else "MISMATCH"
    print(f"{prefix}{name}: {len(nodes)} nodes, {len(edges)} edges -> cloud {got_n} / {got_e} [{status}]")


async def main(names: list[str], local_test: bool) -> None:
    dst = cloud(local_test)
    prefix = "copytest:" if local_test else ""
    for name in names:
        await copy(name, dst, prefix)
        if local_test:
            await dst.select_graph(prefix + name).delete()


if __name__ == "__main__":
    args = sys.argv[1:]
    local = "--local-test" in args
    asyncio.run(main([a for a in args if a != "--local-test"], local))
