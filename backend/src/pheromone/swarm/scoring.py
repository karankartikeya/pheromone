"""Ant Colony Optimization choice (MAX-MIN variant).

score(h) = tau^alpha * eta^beta / ((1 + tries) * (1 + crowd) * (1 + w * siblings))

crowd: same-signature hypotheses in other files claimed right now.
siblings: other hypotheses on the same failure claimed right now; a second
agent there usually ends up superseded, so it weighs more (w = sibling_weight).

The worker draws candidates in proportion to score; on a lost claim it moves
to the next draw without re-reading the frontier.
"""

import random

from pheromone.config import PARAMS, Params


def score(row: dict, p: Params = PARAMS) -> float:
    tau = max(row.get("tau") or p.tau_min, p.tau_min)
    eta = row.get("eta") or 1.0
    return (tau ** p.alpha) * (eta ** p.beta) / (
        (1 + (row.get("tries") or 0))
        * (1 + (row.get("crowd") or 0))
        * (1 + p.sibling_weight * (row.get("siblings") or 0))
    )


def roulette_order(rows: list[dict], rng: random.Random, p: Params = PARAMS) -> list[dict]:
    """All rows, ordered by repeated weighted draws without replacement."""
    pool = [(r, score(r, p)) for r in rows]
    order = []
    while pool:
        total = sum(w for _, w in pool)
        x = rng.uniform(0, total)
        acc = 0.0
        for i, (r, w) in enumerate(pool):
            acc += w
            if x <= acc:
                order.append(r)
                pool.pop(i)
                break
        else:  # float rounding at the top end
            order.append(pool.pop()[0])
    return order
