"""Event bus: every state change goes to subscribers (SSE) and to runs/<id>.events.jsonl (replay)."""

import asyncio
import json
import time
from pathlib import Path

from pheromone.config import RUNS_DIR


class Recorder:
    def __init__(self, run_id: str, echo: bool = False):
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.path = RUNS_DIR / f"{run_id}.events.jsonl"
        self._f = self.path.open("a")
        self._t0 = time.time()
        self._subs: list[asyncio.Queue] = []
        self.echo = echo

    def emit(self, event: dict) -> None:
        e = {"t": round(time.time() - self._t0, 3), **event}
        line = json.dumps(e, default=str)
        self._f.write(line + "\n")
        self._f.flush()
        if self.echo:
            print(line, flush=True)
        for q in self._subs:
            q.put_nowait(e)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.remove(q)

    def close(self) -> None:
        self._f.close()


def read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
