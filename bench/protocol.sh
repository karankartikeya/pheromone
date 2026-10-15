#!/usr/bin/env bash
# Measured protocol for the scoreboard. Same model, workers and budget for every run.
#   1. empty the shared recipes graph, rebuild both targets clean
#   2. gym: 3 seeds x (baseline, swarm); swarm runs write Recipes (run 1)
#   3. krr: 2 seeds x (baseline, swarm, swarm+recipes), all --no-learn (run 2, transfer)
#   4. publish every run to the dashboard
# Run ids are appended to runs/protocol.txt.
set -euo pipefail
cd "$(dirname "$0")/../backend"

WORKERS=6
BUDGET=2000000
MINUTES=15
LOG=../runs/protocol.txt
mkdir -p ../runs
echo "# protocol started $(date -u +%FT%TZ) model=${LLM_MODEL:-gpt-6-luna} workers=$WORKERS budget=$BUDGET" >> "$LOG"

run() {  # target mode seed [extra flags]
  local id
  id=$(uv run python -m pheromone.run --target "$1" --mode "$2" --seed "$3" --workers "$WORKERS" \
         --budget "$BUDGET" --minutes "$MINUTES" "${@:4}" 2>/dev/null | tail -1)
  echo "$id" >> "$LOG"
  echo "$(date +%H:%M) $1 $2 seed=$3 -> $id"
}

uv run python -c "import asyncio; from pheromone.graph.client import Graph; asyncio.run(Graph('recipes').delete())"
uv run python -m pheromone.repo.bootstrap gym --force
uv run python -m pheromone.repo.bootstrap krr --force

for seed in 1 2 3; do
  run gym baseline "$seed"
  run gym swarm "$seed"
done

for seed in 1 2; do
  run krr baseline "$seed" --no-learn
  run krr swarm "$seed" --no-learn
  run krr swarm+recipes "$seed" --no-learn
done

uv run python -m pheromone.publish $(grep -v '^#' "$LOG" | tail -12)
echo "done $(date +%H:%M)"
