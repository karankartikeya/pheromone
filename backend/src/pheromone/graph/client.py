"""Async FalkorDB access. One pool shared by every worker and job."""

import re
import time
from collections import deque

from falkordb.asyncio import FalkorDB
from redis.asyncio import BlockingConnectionPool

from pheromone import config

_WRITE = re.compile(r"\b(CREATE|MERGE|SET|DELETE|REMOVE)\b", re.IGNORECASE)


class WriteMeter:
    """Counts write queries for the writes/sec tile."""

    def __init__(self, window_s: float = 5.0):
        self.total = 0
        self.window_s = window_s
        self._stamps: deque[float] = deque()

    def hit(self) -> None:
        now = time.monotonic()
        self.total += 1
        self._stamps.append(now)
        while self._stamps and now - self._stamps[0] > self.window_s:
            self._stamps.popleft()

    def per_sec(self) -> float:
        now = time.monotonic()
        while self._stamps and now - self._stamps[0] > self.window_s:
            self._stamps.popleft()
        return len(self._stamps) / self.window_s


meter = WriteMeter()
_db: FalkorDB | None = None


def db() -> FalkorDB:
    global _db
    if _db is None:
        pool = BlockingConnectionPool(
            host=config.FALKORDB_HOST,
            port=config.FALKORDB_PORT,
            password=config.FALKORDB_PASSWORD,
            max_connections=32,
            timeout=10,
            decode_responses=True,
        )
        _db = FalkorDB(connection_pool=pool)
    return _db


class Graph:
    def __init__(self, name: str):
        self.name = name
        self._g = db().select_graph(name)

    async def q(self, cypher: str, **params) -> list[dict]:
        """Run one query; rows come back as dicts keyed by RETURN alias."""
        res = await self._g.query(cypher, params or None)
        if _WRITE.search(cypher):
            meter.hit()
        cols = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
        return [dict(zip(cols, row)) for row in res.result_set]

    async def ro(self, cypher: str, **params) -> list[dict]:
        res = await self._g.ro_query(cypher, params or None)
        cols = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
        return [dict(zip(cols, row)) for row in res.result_set]

    async def delete(self) -> None:
        try:
            await self._g.delete()
        except Exception:
            pass  # graph did not exist
