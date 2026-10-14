# Pheromone

A swarm of identical coding agents that migrates a Python repo from Pydantic v1 to v2 with no orchestrator. Agents coordinate only through a FalkorDB graph of failures, hypotheses, attempts and pheromone-weighted edges. Tests decide what gets reinforced, never the LLM.

Built for WeMakeDevs Graph Hacks (FalkorDB), Track 02 + Track 01. Submission deadline Sun Oct 18 2026, 20:29 Berlin; target 16:00.

## Layout

- `backend/` Python 3.12 (uv), FastAPI, asyncio workers. All Cypher lives in `backend/pheromone/graph/queries.py`.
- `web/` Next.js + Tailwind dashboard (Vercel, replay mode).
- `targets/` cloned target repos, each with its OWN venv on the Python its pins need (gitignored).
- `runs/` exported run recordings for replay (committed).

## Rules that must hold in all code

- Shared claims only through the claim query (`CLAIM` in queries.py). Baseline mode never calls it; it claims only in each worker's local state.
- Never put a LIMIT after a SET or CREATE in Cypher (FalkorDB runs SET/CREATE on every row). There are no multi-query transactions; every coordination step is one atomic query.
- Only the deterministic reporter writes pheromone. The LLM never writes to the graph directly.
- Pheromone never drops below `TAU_MIN`: clamp in every query that changes it.
- All three modes (baseline, swarm, swarm+recipes) use the same model, workers, budget, templates and proposer. The only difference is shared graph reads.
- Never hardcode, estimate or fabricate metrics. Scoreboard numbers come only from recorded runs.
- FalkorDB stays load-bearing: Baseline is the ablation, not a path that bypasses the graph for everything.
- Target repos: never `pip install -e`. Run pytest with `cwd=<worktree>` and `PYTHONPATH=<worktree>`.
- LLM patches are SEARCH/REPLACE blocks, applied in Python; `git diff` gives the real diff and `diff_hash`.
- Project name lives in one constant: `PROJECT_NAME` in `backend/pheromone/config.py`.
- Commits: no AI author or Co-Authored-By trailers. AI use is disclosed in the README (rule 11).
- Public repos at public commits only (rule 6).
