"""Scoreboard metrics, computed only from a recorded run (runs/<id>.json).

Nothing here is estimated: every number is counted from the event log and
the attempts stored in the run graph.

    uv run python -m pheromone.metrics <run_id> [<run_id> ...]
"""

import json
import sys
from collections import defaultdict

from pheromone.config import RUNS_DIR


def hyp_file(hid: str) -> str:
    """Hypothesis ids are '<signature>@<file>#<kind>'."""
    return hid.split("@", 1)[-1].split("#", 1)[0]


def compute(d: dict) -> dict:
    ev = d["events"]
    seeded = next(e for e in ev if e["type"] == "seeded")
    stopped = next((e for e in ev if e["type"] == "stopped"), {})
    attempts = sorted(d["attempts"], key=lambda a: int(a["at"] or 0))

    # burn-down: red tests after each merge
    burn = [(0.0, seeded["red_tests"])] + [(e["t"], int(e["red"])) for e in ev if e["type"] == "merged"]
    green_at = next((t for t, red in burn if red == 0), None)

    # wasted work
    failed_diffs: set[str] = set()
    failed_hyps: dict[str, set[str]] = defaultdict(set)
    repeated_diffs = repeated_dead_ends = 0
    for a in attempts:
        if a["outcome"] in ("pass", "superseded", "stale"):
            continue
        if a["diff_hash"] in failed_diffs:
            repeated_diffs += 1
        if failed_hyps[a["hypothesis"]] - {a["agent"]}:
            repeated_dead_ends += 1
        failed_diffs.add(a["diff_hash"])
        failed_hyps[a["hypothesis"]].add(a["agent"])
    outcomes = defaultdict(int)
    for a in attempts:
        outcomes[a["outcome"]] += 1

    # collisions: two agents working on the same file at overlapping times
    spans = [(hyp_file(a["hypothesis"]), int(a["at"]) - int(a["ms"] or 0), int(a["at"]), a["agent"]) for a in attempts]
    collisions = 0
    for i, (f1, s1, e1, ag1) in enumerate(spans):
        for f2, s2, e2, ag2 in spans[i + 1:]:
            if f1 == f2 and ag1 != ag2 and s1 < e2 and s2 < e1:
                collisions += 1

    # recipe hit rate: failures whose merged fix came from a Recipe-seeded hypothesis
    origin = {e["hypothesis"]: e.get("origin") for e in d["edges"]}
    merged = [a for a in attempts if str(a.get("merged")) in ("True", "true", "1")]
    by_recipe = sum(1 for a in merged if origin.get(a["hypothesis"]) == "recipe")

    return {
        "run": d["run"].get("id"), "mode": d["run"].get("mode"), "model": d["run"].get("model"),
        "workers": seeded.get("workers"),
        "red_at_start": seeded["red_tests"], "red_at_end": stopped.get("red"),
        "green_at_end": stopped.get("green"),
        "seconds_to_green": green_at, "seconds": stopped.get("seconds"),
        "tokens": stopped.get("tokens"), "attempts": len(attempts),
        "merged": len(merged), "superseded": outcomes["superseded"],
        "repeated_diffs": repeated_diffs, "repeated_dead_ends": repeated_dead_ends,
        "collisions": collisions, "proposals": sum(1 for e in ev if e["type"] == "proposed"),
        "recipe_hit_rate": round(by_recipe / len(merged), 3) if merged else 0.0,
        "outcomes": dict(outcomes), "burn_down": burn,
    }


def load(run_id: str) -> dict:
    return compute(json.loads((RUNS_DIR / f"{run_id}.json").read_text()))


if __name__ == "__main__":
    cols = ["mode", "red_at_start", "red_at_end", "seconds_to_green", "tokens", "attempts", "merged",
            "superseded", "repeated_diffs", "repeated_dead_ends", "collisions", "proposals", "recipe_hit_rate"]
    rows = [load(r) for r in sys.argv[1:]]
    print("run".ljust(30), *(c[:10].rjust(11) for c in cols))
    for m in rows:
        print(str(m["run"])[:30].ljust(30), *(str(m[c]).rjust(11) for c in cols))
