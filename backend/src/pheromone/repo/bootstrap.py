"""Prepare a target repo: v1 checkout -> bump-pydantic -> Pydantic v2 venv.

Each target gets its own venv on the Python its pins need. Dependencies are
installed non-editable; tests run with PYTHONPATH=<worktree>.

    uv run python -m pheromone.repo.bootstrap gym [--force]
    uv run python -m pheromone.repo.bootstrap krr [--force]
"""

import argparse
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from pheromone.config import ROOT, TARGETS_DIR

TEST_DEPS = ["pytest", "pytest-json-report", "pytest-timeout"]
V2_DEPS = ["pydantic>=2,<3", "pydantic-settings"]


@dataclass(frozen=True)
class Target:
    name: str
    python: str  # version the target's pins need
    codemod_paths: tuple[str, ...]
    source: str  # "gym" or a git URL
    commit: str = ""  # v1 commit for git sources
    requirements: tuple[str, ...] = field(default_factory=tuple)
    # Same definition of "migrated" for every target: no Pydantic v1 deprecations left.
    # The gym sets this in its own pytest config; for real repos it is passed here.
    pytest_addopts: str = ""


TARGETS = {
    "gym": Target("gym", "3.12", ("pmg",), source="gym"),
    # robusta-dev/krr at the merge base of PR #512 (open, human reference migration)
    "krr": Target(
        "krr", "3.10.18", ("robusta_krr",),
        source="https://github.com/robusta-dev/krr.git",
        commit="c40fe379e12f29d6e82fbe35146069e65d0c7b0b",
        requirements=("-r", "requirements.txt"),
        pytest_addopts="-W error::pydantic.warnings.PydanticDeprecatedSince20",
    ),
}


def sh(cmd: list[str], cwd: Path, env: dict | None = None) -> str:
    res = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{res.stdout}\n{res.stderr}")
    return res.stdout


def git_commit(cwd: Path, message: str) -> str:
    sh(["git", "add", "-A"], cwd)
    sh(["git", "commit", "-q", "--allow-empty", "-m", message], cwd)
    return sh(["git", "rev-parse", "HEAD"], cwd).strip()


def checkout_v1(t: Target, dest: Path) -> None:
    if t.source == "gym":
        dest.mkdir(parents=True)
        for item in ("pmg", "tests", "pyproject.toml"):
            src = ROOT / "gym" / item
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, dest / item)
        (dest / ".gitignore").write_text(".venv/\n__pycache__/\n")
        sh(["git", "init", "-q", "-b", "main"], dest)
        git_commit(dest, "gym: pydantic v1")
    else:
        sh(["git", "clone", "-q", t.source, str(dest)], dest.parent)
        sh(["git", "checkout", "-q", "-b", "pheromone-v1", t.commit], dest)


def bootstrap(name: str, force: bool = False) -> Path:
    t = TARGETS[name]
    dest = TARGETS_DIR / name
    if dest.exists():
        if not force:
            raise SystemExit(f"{dest} exists; pass --force to rebuild it")
        shutil.rmtree(dest)
    TARGETS_DIR.mkdir(parents=True, exist_ok=True)

    checkout_v1(t, dest)
    sh(["uv", "venv", "-q", "--python", t.python, ".venv"], dest)
    env = {"VIRTUAL_ENV": str(dest / ".venv"), "PATH": f"{dest / '.venv/bin'}:/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"}
    sh(["uv", "pip", "install", "-q", *t.requirements, *TEST_DEPS], dest, env)

    # bump-pydantic runs in its own tool env; it only rewrites source files.
    sh(["uvx", "--python", "3.12", "bump-pydantic", *t.codemod_paths], dest)
    base = git_commit(dest, "bump-pydantic")
    sh(["git", "branch", "-f", "pheromone-base", base], dest)
    sh(["uv", "pip", "install", "-q", *V2_DEPS], dest, env)
    print(f"{name}: ready at {dest} (base {base[:8]}, python {t.python})")
    return dest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("target", choices=sorted(TARGETS))
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    bootstrap(a.target, a.force)


if __name__ == "__main__":
    main()
