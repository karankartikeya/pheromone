# pydantic-migration-gym

A small Pydantic **v1** codebase used as run-1 target for Pheromone. Every module is a self-contained domain model with its own test file, so failures after a v2 bump are mostly independent. The patterns come from the official Pydantic v2 migration guide, weighted toward what `bump-pydantic` leaves behind: validators that read `values`, method calls (`.dict()`, `.json()`, `parse_obj`, `from_orm`, ...), `__root__` models, `__init__` overrides and introspection through `__fields__`.

Tests pass on Pydantic 1.10. Deprecation warnings are errors (`pyproject.toml`), so a migration is only done when no v1 API is left.
