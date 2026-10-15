import random
from collections import Counter

from pheromone.config import PARAMS
from pheromone.swarm.scoring import roulette_order, score


def row(id, tau=0.5, eta=1.0, tries=0, crowd=0):
    return {"id": id, "tau": tau, "eta": eta, "tries": tries, "crowd": crowd}


def test_score_formula():
    assert score(row("a", tau=2.0, eta=1.5, tries=1, crowd=1)) == 2.0 * 1.5**2 / (2 * 2)


def test_tau_floor_applies():
    assert score(row("a", tau=0.0)) == PARAMS.tau_min


def test_crowd_and_tries_lower_score():
    base = score(row("a"))
    assert score(row("a", crowd=2)) < base
    assert score(row("a", tries=3)) < base


def test_roulette_returns_every_row_once():
    rows = [row(str(i)) for i in range(12)]
    out = roulette_order(rows, random.Random(1))
    assert sorted(r["id"] for r in out) == sorted(r["id"] for r in rows)


def test_roulette_prefers_strong_trails():
    rows = [row("strong", tau=5.0), row("weak", tau=0.5)]
    rng = random.Random(7)
    firsts = Counter(roulette_order(rows, rng)[0]["id"] for _ in range(2000))
    assert firsts["strong"] > 1700  # expected share 5/5.5 = 0.91
    assert firsts["weak"] > 0  # weak trails stay explorable


def test_equal_scores_spread_agents():
    rows = [row(str(i)) for i in range(12)]
    rng = random.Random(3)
    firsts = Counter(roulette_order(rows, rng)[0]["id"] for _ in range(6))
    assert len(firsts) >= 4  # six agents at t=0 mostly pick different candidates
