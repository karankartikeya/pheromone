# Pheromone

**Six coding agents, zero messages, one FalkorDB graph.**

Pheromone is a swarm of identical coding agents that migrates Python code from Pydantic v1 to v2 with no orchestrator. The agents never talk to each other. They coordinate only by reading and writing a FalkorDB graph of failures, hypotheses, attempts and pheromone-weighted edges, the way ants coordinate through trails. Tests decide what gets reinforced, never the LLM. Fixes that keep winning crystallize into Recipes in a shared graph that outlives every run, and later runs start from them.

Built for WeMakeDevs **Graph Hacks** (FalkorDB). Tracks: **Track 02, Agent Memory and Coordination** and **Track 01, Agents That Act on Connected Data**.

> Live dashboard (replay of recorded runs): _link added at deploy time_ · Demo video: _link_ · Blog post: _link_

---

## Why a graph

Independent coding agents working on the same red test suite need *some* coordination mechanism: without one they patch the same file at once, repeat each other's dead ends and redo fixes someone already made. Pheromone's coordination mechanism is shared, evidence-weighted state with no planner, and the state it coordinates on is a web of relations: failures, candidate fixes, attempts, agents, tests, files and the imports between them. A key-value store could hold the same state with enough extra indexes and scripts; in a graph those relations are represented directly, each coordination step is one atomic query, and the reasoning behind every decision can be inspected as a path.

- **Claims are a compare-and-set** on a Hypothesis node with a lease. No agent assigns work; an expired lease is how work is handed off, with the full attempt history attached.
- **Pheromone lives on edges.** `(:Failure)-[:SUSPECTS {pheromone}]->(:Hypothesis)` is changed only by deterministic test results and evaporates over time, so dead ends fade and fixes that work are chosen again.
- **Picking work is one read across relations:** pheromone on the edge, past attempts, agents holding same-signature fixes in other files, claimed sibling fixes, and fixes waiting to merge.
- **The graph knows the code.** `File-[:IMPORTS]->File` gives every patch a multi-hop blast radius (`IMPORTS*0..3`) of tests that must stay green before it merges. PageRank over imports weights central modules; WCC groups independent failures.
- **Memory outlives the run.** Repeated wins become Recipes in a separate `recipes` graph that a later run, on another repo, seeds hypotheses from.

**Baseline** is the comparison: the same agents, model, budget, hypothesis templates, prompts and merge gate, with every graph read removed. Each baseline agent learns the failures by running the test suite itself and keeps a private candidate list, so it has no shared claims, pheromone or attempt history. It answers "does this coordination system beat independent agents?". It does not isolate graph storage from shared state in general (see [Results](#results)).

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

**First measured batch** (Thursday): [`bench/protocol.sh`](bench/protocol.sh), 12 runs. Same target commits, model (`gpt-6-luna`), 6 workers, prompts, templates and merge gate in every run. The token budget is a per-run cap of 2M; no run came close. The gym was run 3 times per mode and krr twice. Recipes were learned only from the gym swarm runs; every krr run used `--no-learn`, so it could not write to the Recipes it was evaluated with. The run order was gym (baseline, swarm alternating), then krr. Every run reached the green criterion: all tests pass with Pydantic deprecation warnings treated as errors (60/60 on the gym, 55/55 on krr). Each run's graph is kept as `run:<id>`; the dashboard's scoreboard shows the same numbers.

Medians, with min–max:

| Target | Mode | Tokens | Time to green | Collisions | Wasted attempts |
| --- | --- | --- | --- | --- | --- |
| gym (37 red tests at start) | Baseline (independent agents) | 176k (123k–192k) | 191 s (133–210) | 131 (98–159) | 71 (54–71) |
| gym | **Swarm** | **50k** (46k–51k) | **61 s** (61–64) | **9** (6–11) | **11** (6–12) |
| krr (one import error blocks all 55 tests) | Baseline (independent agents) | 231k (173k–290k) | 245 s (222–267) | 92 (86–97) | 36 (33–39) |
| krr | **Swarm** | **94k** (67k–120k) | 231 s (199–264) | **8** (5–11) | **5.5** (3–8) |
| krr | Swarm + Recipes | 91k (62k–119k) | 217 s (190–244) | 9 (5–12) | 6.5 (3–10) |

Every run:

| Run | Target | Mode | Tests green | Tokens | Time to green | Attempts | Wasted | Collisions | Proposals | Recipe share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gym-baseline-1015-184132` | gym | baseline | 60/60 | 176,204 | 191 s | 110 | 71 | 159 | 72 | – |
| `gym-baseline-1015-184547` | gym | baseline | 60/60 | 122,508 | 133 s | 89 | 54 | 98 | 45 | – |
| `gym-baseline-1015-184906` | gym | baseline | 60/60 | 192,340 | 210 s | 111 | 71 | 131 | 76 | – |
| `gym-swarm-1015-184444` | gym | swarm | 60/60 | 46,292 | 61 s | 42 | 6 | 6 | 9 | – |
| `gym-swarm-1015-184801` | gym | swarm | 60/60 | 50,617 | 64 s | 47 | 12 | 11 | 8 | – |
| `gym-swarm-1015-185238` | gym | swarm | 60/60 | 49,608 | 61 s | 46 | 11 | 9 | 8 | – |
| `krr-baseline-1015-185340` | krr | baseline | 55/55 | 289,901 | 267 s | 50 | 39 | 97 | 6 | – |
| `krr-baseline-1015-190541` | krr | baseline | 55/55 | 172,764 | 222 s | 42 | 33 | 86 | 0 | – |
| `krr-swarm-1015-185816` | krr | swarm | 55/55 | 120,228 | 199 s | 22 | 8 | 11 | 1 | – |
| `krr-swarm-1015-190930` | krr | swarm | 55/55 | 67,237 | 264 s | 14 | 3 | 5 | 1 | – |
| `krr-swarm-recipes-1015-190136` | krr | swarm+recipes | 55/55 | 62,285 | 244 s | 13 | 3 | 5 | 1 | 70% |
| `krr-swarm-recipes-1015-191354` | krr | swarm+recipes | 55/55 | 118,773 | 190 s | 23 | 10 | 12 | 2 | 67% |

**Metric definitions** (computed by [`metrics.py`](backend/src/pheromone/metrics.py) from the event log and the attempts stored in each run graph):

- **Tokens**: all LLM input and output tokens in the run: patch generation, proposals, retries and failed patches.
- **Time to green**: seconds from seeding until the merge after which no test is red.
- **Collisions**: pairs of attempts by different agents on the same file whose time windows overlap.
- **Wasted attempts**: passing patches for a failure another agent had already fixed (superseded), plus attempts that repeated a diff or a hypothesis that had already failed.
- **Recipe share**: share of merged fixes whose hypothesis was seeded from a Recipe. It says where the winning hypothesis came from, not that the run needed it.

**Reading these numbers.** In these runs, coordinated agents used 59–72% fewer tokens than independent agents (medians) and recorded far fewer collisions and wasted attempts. On the gym, where failures are independent, median time to green was also 68% lower. On krr it was only 6% lower: krr's failures form a chain where each fix reveals the next layer, so every layer waits for a merge and a full test run whichever mode runs it. With 3 and 2 runs per mode these are preliminary, descriptive results. They don't show that the approach generalizes, and the baseline compares the whole coordination system against independent agents: it does not separate shared claims from pheromone-weighted ranking, or a graph from other shared stores. Recipe-seeded hypotheses produced about two thirds of the merged krr fixes, but their effect on cost and time was within the swarm's own range over two runs, so it is inconclusive.

**Parameters.** α = 1, β = 2, τ0 = 0.5, τ_min = 0.05, evaporation ×0.95 every 10 s, lease 120 s, retirement after 3 failed or duplicate attempts. η = template prior (1, or 1 + ln(1 + support) for Recipe-seeded hypotheses) × (1 + PageRank of the file). These are starting values from the plan except `sibling_weight = 10`, which was chosen after watching gym runs; treat the gym as the development benchmark and krr as the check on a repo we did not tune on.

**krr vs the human migration.** In all four measured swarm runs on krr the final diff touches 7 files (+26, −17 to −19); human PR #512 touches 8 (+33/−21). Similar file counts don't establish equal quality. Two concrete differences: every swarm run also replaced a deprecated `result.json(indent=2)` in `formatters/json.py` that the PR left in place, and the PR changed a mutable default and an `__init__` override that no test exercises, which the swarm left alone.

## Honest notes

- **Stigmergy for LLM agents is not new.** What we add is graph-native pheromone on FalkorDB over real code, test-verified reinforcement, a multi-hop merge gate, and procedural Recipes that carry across repos.
- **Tests decide, so tests can be fooled.** In an early run an agent made a frozen-model test pass by overriding `__eq__` and `__setattr__` instead of using `frozen=True`. We tightened the gym (removed config keys are now errors) and the prompts (no dunder overrides). Diffs are worth reading; the Trails screen shows every one.
- **krr's last tests are hard.** Its tests depend on run order and global config, and its CLI swallows exceptions into logs. Pheromone reads the logged traceback as the real cause and judges regressions against the same test selection before and after a patch.
- **FalkorDB crash.** One query shape (properties plus `collect()` on a hypothesis that was just claimed) crashed the server with a panic in `reply_compact`. We split it into plain-row queries.

## AI use (rule 11)

This project was built with an AI coding assistant (Claude Code), which wrote most of the code from a design and plan the author wrote and reviewed, ran the experiments and reported results. Every design decision, the target choice and every number in this README were reviewed by the author. At runtime, the swarm agents use an OpenAI model to propose patches and hypotheses; tests, not the model, decide what is kept.

## License

MIT
