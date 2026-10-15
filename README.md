# Pheromone

**Six coding agents, zero messages, one FalkorDB graph.**

Pheromone is a swarm of identical coding agents that migrates Python code from Pydantic v1 to v2 with no orchestrator. The agents never talk to each other. They coordinate only by reading and writing a FalkorDB graph of failures, hypotheses, attempts and pheromone-weighted edges, the way ants coordinate through trails. Tests decide what gets reinforced, never the LLM. Fixes that keep winning crystallize into Recipes in a shared graph that outlives every run, and later runs start from them.

Built for WeMakeDevs **Graph Hacks** (FalkorDB). Tracks: **Track 02, Agent Memory and Coordination** and **Track 01, Agents That Act on Connected Data**.

> Live dashboard (replay of recorded runs): _link added at deploy time_ · Demo video: _link_ · Blog post: _link_

---

## Why a graph

Run six LLM agents on the same failing test suite without shared memory and they collide: they patch the same file at once, repeat each other's dead ends and redo work someone already finished. Pheromone puts the coordination in the data instead of in a planner:

- **Claims are a compare-and-set** on a Hypothesis node with a lease. No agent assigns work; an expired lease is how work is handed off.
- **Pheromone lives on edges.** `(:Failure)-[:SUSPECTS {pheromone}]->(:Hypothesis)` is reinforced only by deterministic test results and evaporates over time, so dead ends fade and fixes that work get chosen again.
- **The graph knows the code.** `File-[:IMPORTS]->File` edges give every patch a multi-hop blast radius that must stay green before it merges. PageRank weights central modules; WCC clusters spread agents out.
- **Memory outlives the run.** Repeated wins become Recipes in a separate `recipes` graph; a later run seeds its hypotheses from them.

The **Baseline** mode is the ablation: the same agents, model, budget and hypothesis templates, with every graph read taken away. Each baseline agent learns the failures from the test suite itself and keeps its own private candidate list. The scoreboard compares the two on the same repo.

## How a run works

1. **Bootstrap.** Check out the target at its last Pydantic v1 commit, run [`bump-pydantic`](https://github.com/pydantic/bump-pydantic), upgrade to v2. What the codemod leaves behind is the swarm's job.
2. **Seed.** Run the suite, group every red test into a Failure with a repo-agnostic signature (`validator-values`, `dict-call`, `json-encoders`, ...), link Tests, Files and imports, and attach 1-3 competing Hypotheses per Failure from hand-written templates.
3. **Swarm.** Every worker runs the same loop: read the frontier, pick by roulette on `τ^α · η^β / ((1+tries)(1+crowd)(1+w·siblings))`, claim with one atomic query, ask the LLM for SEARCH/REPLACE edits, run the target tests plus the blast radius, report. Only the reporter writes pheromone.
4. **Merge.** Passing patches are re-checked and merged one at a time onto a run branch; a full-suite rerun closes fixed Failures and opens the ones a fix reveals (fixing an import error usually uncovers the next layer).
5. **Propose.** When nothing is left to try for a Failure, any idle worker claims it and asks the LLM for two new hypotheses, validated before they enter the graph.
6. **Crystallize.** Winning (signature, fix kind) pairs become Recipes in the shared `recipes` graph.

## Graph model

Run graph `run:<id>` (one per run) and the shared `recipes` graph.

| Edge | Meaning |
| --- | --- |
| `(Test)-[:FAILS_WITH]->(Failure)` | a red test and the failure behind it |
| `(Test)-[:DEFINED_IN]->(File)`, `(Failure)-[:IN]->(File)` | where tests and failures live |
| `(File)-[:IMPORTS]->(File)` | static import graph (blast radius, PageRank) |
| `(Failure)-[:SUSPECTS {pheromone}]->(Hypothesis)` | a candidate fix and its trail strength |
| `(Hypothesis)-[:TOUCHES]->(File)`, `(Hypothesis)-[:SAME_SIGNATURE]-(Hypothesis)` | what a fix edits; crowding across files |
| `(Agent)-[:CLAIMED {at}]->(Hypothesis)` | claims, including handoffs after a lease expires |
| `(Agent)-[:MADE]->(Attempt)-[:TESTED]->(Hypothesis)` | episodic memory: every attempt with outcome, diff, tokens |
| `(Attempt)-[:FIXED\|BROKE]->(Test)`, `(Attempt)-[:FOLLOWED]->(Attempt)` | test effects; building on another agent's attempt |
| `(Contribution {run})-[:FOR]->(Recipe)` (recipes graph) | procedural memory, support counted per run |

## The Cypher that runs it

All queries live in [`backend/src/pheromone/graph/queries.py`](backend/src/pheromone/graph/queries.py); [`docs/QUERIES.md`](docs/QUERIES.md) is generated from it. The core ones:

**Claim (compare-and-set).** An empty result means another agent won. An expired lease counts as open: that is the handoff.

```cypher
MATCH (h:Hypothesis {id:$hid}), (ag:Agent {id:$agent})
WHERE h.status = 'open' OR (h.status = 'claimed' AND h.lease_until < $now)
SET h.status = 'claimed', h.claimed_by = $agent, h.lease_until = $now + $lease_ms
CREATE (ag)-[:CLAIMED {at:$now}]->(h)
RETURN h.id AS id
```

**Report and deposit.** Guarded so an agent that lost its lease cannot overwrite the new owner; one deposit formula for pass and fail, clamped at τ_min; hypotheses retire after 3 failures.

```cypher
MATCH (h:Hypothesis {id:$hid}), (ag:Agent {id:$agent})
WHERE h.status = 'claimed' AND h.claimed_by = $agent
CREATE (ag)-[:MADE]->(a:Attempt {id:$aid, outcome:$outcome, diff_hash:$dh, diff:$diff,
        fixed:$fixed, broken:$broken, ms:$ms, tokens:$tok, at:$now, mode:$mode})-[:TESTED]->(h)
SET h.fails = coalesce(h.fails, 0) + CASE WHEN $outcome = 'pass' THEN 0 ELSE 1 END,
    h.claimed_by = null
SET h.status = CASE WHEN $outcome = 'pass' THEN 'fixed'
                    WHEN h.fails >= $max_fails THEN 'dead' ELSE 'open' END
WITH h, a
MATCH (h)<-[s:SUSPECTS]-(:Failure)
SET s.pheromone = CASE WHEN s.pheromone * $mult + $add < $tmin THEN $tmin
                       ELSE s.pheromone * $mult + $add END
RETURN a.id AS id, count(s) AS edges, h.status AS status
```

**Frontier**, **evaporation**, **lease release**, **blast radius** (`IMPORTS*0..3`), **crystallization**, **the trail behind a fix**, **PageRank** and **WCC** are in [`docs/QUERIES.md`](docs/QUERIES.md).

Two FalkorDB facts shaped every query: writes to a graph are serialized and each query is atomic, but there are no multi-query transactions, so every coordination step is one compare-and-set query; and `SET`/`CREATE` run on every matched row even if a `LIMIT` comes later, so no write relies on `LIMIT`.

## Targets

- **[`gym/`](gym/)**: a small Pydantic v1 codebase written for this project (38 modules, one test file each). Patterns come from the official migration guide, weighted toward what `bump-pydantic` leaves behind, plus ten v2 *behaviour* changes (union coercion, number-to-string coercion, float truncation, custom types, Decimal and UTC JSON output, ...). Its pytest config treats `DeprecationWarning` and `UserWarning` as errors: a migration counts as done only when no v1 API and no removed config key is left.
- **[robusta-dev/krr](https://github.com/robusta-dev/krr)** at the merge base of PR [#512](https://github.com/robusta-dev/krr/pull/512) (`c40fe37`). PR #512 is a human v2 migration that was **open, not merged**, when we picked it; we use it as a human reference, not as ground truth. krr runs with `-W error::pydantic.warnings.PydanticDeprecatedSince20`, the same definition of done.

## Run it locally

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node 20+ with pnpm, an OpenAI API key.

```bash
docker compose up -d                       # FalkorDB on localhost:6380, Browser on :3000
cd backend
echo "OPENAI_API_KEY=sk-..." > .env        # never committed
uv sync
uv run python -m pheromone.repo.bootstrap gym      # or: krr
uv run python -m pheromone.run --target gym --mode swarm --workers 6
uv run python -m pheromone.run --target gym --mode baseline --workers 6
uv run python -m pheromone.run --target krr --mode swarm+recipes --workers 6
```

Dashboard with live runs:

```bash
uv run uvicorn pheromone.api:app --port 8765          # in backend/
cd ../web && pnpm install && NEXT_PUBLIC_API_URL=http://localhost:8765 pnpm dev --port 3100
```

Useful flags: `--lease-s 20` (short leases make the kill-agent handoff visible), `--no-learn` (keep a control run out of the shared recipes graph), `--seed`, `--budget`, `--minutes`. Publish recorded runs to the static dashboard with `uv run python -m pheromone.publish <run_id> ...`. Tests: `uv run pytest` (needs FalkorDB running).

Model: one model for every agent in every mode (`LLM_MODEL`, default `gpt-6-luna`); it is recorded on every Run node.

## Results

Measured with [`bench/protocol.sh`](bench/protocol.sh): same repo, commit, model (`gpt-6-luna`), 6 workers and 2M-token budget for every run. The gym was run 3 times per mode, krr twice. Swarm runs on the gym wrote the Recipes; every krr run used `--no-learn` so it could not feed the Recipes it was tested with. Numbers are medians with the min–max range; the dashboard's scoreboard shows the same data, and each run's graph is kept as `run:<id>`. Every one of the 12 runs ended fully green.

| Target | Mode | Tokens | Time to green | Collisions | Wasted attempts |
| --- | --- | --- | --- | --- | --- |
| gym (37 red tests) | Baseline, no graph | 176k (123k–192k) | 191 s (133–210) | 131 (98–159) | 71 (54–71) |
| gym | **Swarm** | **50k** (46k–51k) | **61 s** (61–64) | **9** (6–11) | **11** (6–12) |
| krr (suite blocked at import) | Baseline, no graph | 231k (173k–290k) | 245 s (222–267) | 92 (86–97) | 36 (33–39) |
| krr | **Swarm** | **94k** (67k–120k) | 231 s (199–264) | **8** (5–11) | **5** (3–7) |
| krr | Swarm + Recipes | 91k (62k–119k) | 217 s (190–244) | 9 (5–12) | 6 (3–8) |

_Collisions: two agents patching the same file at overlapping times. Wasted attempts: passing patches for a failure another agent had already fixed._

What this shows, and what it doesn't:

- **The graph is load-bearing.** Take it away and the same agents spend 2.5–3.6× the tokens and collide 11–15× more often, because they keep picking the same failures and redoing each other's fixes.
- **On the gym it is also 3× faster.** Its failures are independent, so coordination turns directly into parallelism.
- **On krr it saves cost, not time.** krr's failures form a chain (each fix reveals the next layer), so every layer waits for a merge and a full test run whichever mode runs it.
- **Recipes did not measurably help yet.** Recipe-seeded hypotheses produced 67–70% of the merged krr fixes, but tokens and time stayed within the swarm's own range over two runs. The hand-written templates already cover the signatures krr needs; Recipes should matter more on repos whose failures the templates don't cover. We report this as measured.
- **krr vs the human migration.** In all four measured swarm runs the final diff touches 7 files (+26, −17 to −19); human PR #512 touches 8 (+33/−21). Every one of those runs also replaced a deprecated `result.json(indent=2)` in `formatters/json.py` that the PR left in place. The PR additionally changed a mutable default and an `__init__` override that no test exercises; the swarm left those alone.

## Honest notes

- **Stigmergy for LLM agents is not new.** What we add is graph-native pheromone on FalkorDB over real code, test-verified reinforcement, a multi-hop merge gate, and procedural Recipes that carry across repos.
- **Tests decide, so tests can be fooled.** In an early run an agent made a frozen-model test pass by overriding `__eq__` and `__setattr__` instead of using `frozen=True`. We tightened the gym (removed config keys are now errors) and the prompts (no dunder overrides). Diffs are worth reading; the Trails screen shows every one.
- **krr's last tests are hard.** Its tests depend on run order and global config, and its CLI swallows exceptions into logs. Pheromone reads the logged traceback as the real cause and judges regressions against the same test selection before and after a patch.
- **FalkorDB crash.** One query shape (properties plus `collect()` on a hypothesis that was just claimed) crashed the server with a panic in `reply_compact`. We split it into plain-row queries.

## AI use (rule 11)

This project was built with an AI coding assistant (Claude Code), which wrote most of the code from a design and plan the author wrote and reviewed, ran the experiments and reported results. Every design decision, the target choice and every number in this README were reviewed by the author. At runtime, the swarm agents use an OpenAI model to propose patches and hypotheses; tests, not the model, decide what is kept.

## License

MIT
