from pheromone.graph import queries as Q
from pheromone.graph.client import Graph


async def ensure_indexes(g: Graph, recipes: bool = False) -> None:
    for stmt in Q.RECIPE_INDEXES if recipes else Q.INDEXES:
        try:
            await g.q(stmt)
        except Exception as e:  # index already exists
            if "already indexed" not in str(e).lower() and "exists" not in str(e).lower():
                raise
