"""Night-1 gate: agents' worktrees are isolated (no editable install leaks)."""

from pathlib import Path

import pytest

from pheromone.config import TARGETS_DIR
from pheromone.repo import worktrees as wt
from pheromone.repo.pytest_runner import run_pytest

GYM = TARGETS_DIR / "gym"
pytestmark = pytest.mark.skipif(not (GYM / ".venv").exists(), reason="gym target not bootstrapped")


async def test_breaking_one_worktree_leaves_other_green(tmp_path: Path):
    a = await wt.create(GYM, tmp_path / "A", "a", "HEAD")
    b = await wt.create(GYM, tmp_path / "B", "b", "HEAD")
    try:
        node = "tests/test_m04_app_settings.py"  # green after the v2 bump
        target = "pmg/m04_app_settings.py"
        wt.apply_edits(a, [wt.Edit(target, "workers: int = 2", "workers: int = 3")])
        ra = await run_pytest(a, GYM / ".venv/bin/python", [node])
        rb = await run_pytest(b, GYM / ".venv/bin/python", [node])
        assert ra.red and not rb.red
        assert wt.diff_hash(await wt.diff(a)) != wt.diff_hash(await wt.diff(b))
        await wt.reset(a, "HEAD")
        assert (await wt.diff(a)) == ""
    finally:
        await wt.git(GYM, "worktree", "remove", "--force", str(a), check=False)
        await wt.git(GYM, "worktree", "remove", "--force", str(b), check=False)


def test_parse_and_apply_rejects_ambiguous(tmp_path: Path):
    (tmp_path / "m.py").write_text("x = 1\nx = 1\n")
    edits = wt.parse_edits("m.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n")
    assert len(edits) == 1
    with pytest.raises(wt.ApplyError):
        wt.apply_edits(tmp_path, edits)
