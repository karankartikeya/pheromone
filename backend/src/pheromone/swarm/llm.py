"""Patch proposals from the LLM. The LLM only writes code; it never touches the graph.

Provider-neutral interface with an OpenAI implementation (Responses API).
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

from pheromone import config
from pheromone.repo.worktrees import Edit, parse_edits

INSTRUCTIONS = """You are one of several identical agents migrating a Python codebase from Pydantic v1 to Pydantic v2.
You are given one failure, the hypothesis you must try, the relevant source files, and earlier attempts on this hypothesis by other agents.

Rules:
- Implement the given hypothesis. Do not try a different approach.
- Fix the root cause in source code. Do not edit tests and do not silence warnings.
- The finished code must not use deprecated Pydantic v1 APIs (tests treat DeprecationWarning as an error).
- Keep behaviour identical: same field names, aliases, defaults, output formats.
- Use the idiomatic Pydantic v2 API (model_config keys, validators, serializers). Never override dunder
  methods such as __eq__, __setattr__ or __init__ to imitate v1 behaviour, and never keep removed config keys.
- Learn from earlier attempts: do not repeat a diff that already failed.

Answer with SEARCH/REPLACE blocks only, no prose. Format, one block per edit:

path/to/file.py
<<<<<<< SEARCH
exact lines copied from the current file
=======
replacement lines
>>>>>>> REPLACE

SEARCH must match the current file exactly (including indentation) and be unique in it. Keep blocks small.
Only edit these files: {allowed}"""


@dataclass
class PatchRequest:
    hypothesis: str
    signature: str
    failure: str  # exception message head
    tests: list[str]
    files: dict[str, str]  # path -> current content
    prior_attempts: list[dict] = field(default_factory=list)  # {agent, outcome, diff}
    recipe_example: str | None = None
    trace: str = ""  # pytest traceback excerpt for the failure


@dataclass
class PatchResult:
    text: str
    edits: list[Edit]
    tokens_in: int
    tokens_out: int
    ms: int
    model: str

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


def render_input(req: PatchRequest) -> str:
    parts = [
        f"## Hypothesis to implement\n{req.hypothesis}",
        f"## Failure\nsignature: {req.signature}\n{req.failure}\nfailing tests: {', '.join(req.tests[:8])}",
    ]
    if req.trace:
        parts.append(f"## Traceback (excerpt)\n```\n{req.trace}\n```")
    for path, text in req.files.items():
        numbered = text if len(text) < 40_000 else text[:40_000] + "\n# ... truncated"
        parts.append(f"## {path}\n```python\n{numbered}\n```")
    if req.recipe_example:
        parts.append(f"## A diff that fixed the same signature in another repo\n```diff\n{req.recipe_example}\n```")
    for a in req.prior_attempts[-4:]:
        parts.append(f"## Earlier attempt by {a.get('agent', '?')}: {a.get('outcome')}\n```diff\n{(a.get('diff') or '')[:3000]}\n```")
    return "\n\n".join(parts)


class OpenAIProvider:
    def __init__(self, model: str):
        from openai import AsyncOpenAI

        self.model = model
        self.client = AsyncOpenAI(max_retries=3, timeout=120)

    async def patch(self, req: PatchRequest) -> PatchResult:
        t0 = time.monotonic()
        resp = await self.client.responses.create(
            model=self.model,
            instructions=INSTRUCTIONS.format(allowed=", ".join(req.files)),
            input=render_input(req),
            max_output_tokens=8000,
            prompt_cache_key=f"pheromone:{req.signature}",
        )
        text = resp.output_text or ""
        u = resp.usage
        return PatchResult(
            text=text, edits=parse_edits(text),
            tokens_in=u.input_tokens if u else 0, tokens_out=u.output_tokens if u else 0,
            ms=int((time.monotonic() - t0) * 1000), model=self.model,
        )


    async def complete(self, instructions: str, text: str) -> tuple[str, int]:
        resp = await self.client.responses.create(
            model=self.model, instructions=instructions, input=text, max_output_tokens=4000,
        )
        u = resp.usage
        return resp.output_text or "", (u.input_tokens + u.output_tokens) if u else 0


def provider():
    if config.LLM_PROVIDER == "openai":
        return OpenAIProvider(config.LLM_MODEL)
    raise ValueError(f"unknown LLM_PROVIDER {config.LLM_PROVIDER}")


def read_files(worktree: Path, paths: list[str]) -> dict[str, str]:
    return {p: (worktree / p).read_text() for p in paths if (worktree / p).is_file()}
