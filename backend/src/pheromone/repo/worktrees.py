"""Git worktree per agent, SEARCH/REPLACE patch application, diff hashing."""

import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


async def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {err.decode().strip()}")
    return out.decode()


async def create(repo: Path, path: Path, branch: str, base: str) -> Path:
    """Detached worktree at `base`; workers reset to the run branch every loop."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        await git(repo, "worktree", "remove", "--force", str(path), check=False)
    await git(repo, "worktree", "add", "--detach", str(path), base)
    return path


async def reset(worktree: Path, ref: str) -> None:
    await git(worktree, "reset", "--hard", "-q", ref)
    await git(worktree, "clean", "-fdq", "-e", ".venv")


async def diff(worktree: Path) -> str:
    return await git(worktree, "diff", "--no-color", "--no-ext-diff")


def diff_hash(d: str) -> str:
    """Hash of the change ignoring index lines and hunk offsets."""
    keep = [l for l in d.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    return hashlib.sha1("\n".join(keep).encode()).hexdigest()[:16]


@dataclass
class Edit:
    path: str
    search: str
    replace: str


_BLOCK = re.compile(
    r"^(?P<path>[^\n`]+?\.py)\s*\n(?:```[a-z]*\n)?<<<<<<< SEARCH\n(?P<search>.*?)\n?=======\n(?P<replace>.*?)\n?>>>>>>> REPLACE",
    re.DOTALL | re.MULTILINE,
)


def parse_edits(text: str) -> list[Edit]:
    """Blocks of the form:

    path/to/file.py
    <<<<<<< SEARCH
    exact old lines
    =======
    new lines
    >>>>>>> REPLACE
    """
    return [Edit(m["path"].strip(), m["search"], m["replace"]) for m in _BLOCK.finditer(text)]


class ApplyError(Exception):
    pass


def apply_edits(worktree: Path, edits: list[Edit], allowed: set[str] | None = None) -> list[str]:
    """Apply exact-match edits; all-or-nothing. Returns touched paths."""
    staged: dict[str, str] = {}
    for e in edits:
        if allowed is not None and e.path not in allowed:
            raise ApplyError(f"edit outside allowed files: {e.path}")
        target = (worktree / e.path).resolve()
        if worktree.resolve() not in target.parents:
            raise ApplyError(f"path escapes worktree: {e.path}")
        text = staged.get(e.path)
        if text is None:
            text = target.read_text() if target.exists() else ""
        if e.search == "":
            if text:
                raise ApplyError(f"empty SEARCH on existing file {e.path}")
            staged[e.path] = e.replace + "\n"
            continue
        count = text.count(e.search)
        if count != 1:
            raise ApplyError(f"SEARCH matched {count} times in {e.path}")
        staged[e.path] = text.replace(e.search, e.replace, 1)
    for path, text in staged.items():
        (worktree / path).write_text(text)
    return sorted(staged)
