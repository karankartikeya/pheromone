from pheromone.metrics import compute


def run(attempts, events):
    return {
        "run": {"id": "r", "mode": "swarm"},
        "events": [{"type": "seeded", "t": 0, "red_tests": 3, "workers": 2}, *events],
        "edges": [{"hypothesis": "sig@pmg/a.py#k", "origin": "recipe"}],
        "attempts": attempts,
    }


def att(id, agent, hyp, outcome, dh, at, ms=1000, merged=False):
    return {"id": id, "agent": agent, "hypothesis": hyp, "outcome": outcome, "diff_hash": dh,
            "at": at, "ms": ms, "merged": merged}


def test_counts_and_burn_down():
    d = run(
        [
            att("1", "A0", "sig@pmg/a.py#k", "fail", "x", 2000),
            att("2", "A1", "sig@pmg/a.py#k", "fail", "x", 2500),  # same diff, same dead end, overlaps A0
            att("3", "A0", "sig@pmg/a.py#k", "pass", "y", 5000, merged=True),
            att("4", "A1", "other@pmg/b.py#k", "superseded", "z", 9000),
        ],
        [{"type": "merged", "t": 5.0, "red": 1}, {"type": "merged", "t": 8.0, "red": 0},
         {"type": "stopped", "t": 9.0, "tokens": 100, "seconds": 9.0, "red": 0}],
    )
    m = compute(d)
    assert m["repeated_diffs"] == 1
    assert m["repeated_dead_ends"] == 1
    assert m["collisions"] == 1
    assert m["superseded"] == 1
    assert m["seconds_to_green"] == 8.0
    assert m["burn_down"] == [(0.0, 3), (5.0, 1), (8.0, 0)]
    assert m["recipe_hit_rate"] == 1.0
