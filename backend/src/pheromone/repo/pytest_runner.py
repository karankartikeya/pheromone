"""Run a target repo's tests in a worktree and parse pytest-json-report output.

Three shapes of red, all reported uniformly:
- failed tests (report["tests"])
- failed collectors: a test module that cannot import (report["collectors"])
- session abort: conftest import error, pytest exits before the report plugin
  writes anything. Returned as one pseudo collector for the whole repo.
"""

import asyncio
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from pheromone.config import PARAMS

# "E   pydantic.warnings.PydanticDeprecatedSince20: message"
_E_LINE = re.compile(r"^E\s+([A-Za-z_][\w.]*): (.*)$")


@dataclass
class Red:
    nodeid: str  # test node id, or "<path>::__collect__" for collection errors
    kind: str  # "test" | "collect" | "session"
    exc_type: str
    message: str
    frames: list[tuple[str, int]]  # (repo-relative path, line), innermost last
    longrepr: str = ""


@dataclass
class TestRun:
    __test__ = False  # not a pytest test class

    passed: set[str] = field(default_factory=set)
    red: list[Red] = field(default_factory=list)
    ms: int = 0
    timed_out: bool = False

    @property
    def red_ids(self) -> set[str]:
        return {r.nodeid for r in self.red}


def collect_id(path: str) -> str:
    return f"{path}::__collect__"


async def run_pytest(
    worktree: Path, python: Path, nodeids: list[str] | None = None, timeout_s: int | None = None
) -> TestRun:
    """Run pytest in `worktree` with the target repo's interpreter `python`."""
    timeout_s = timeout_s or PARAMS.test_timeout_s
    fd, report_path = tempfile.mkstemp(suffix=".json", prefix="pheromone-report-")
    os.close(fd)
    os.unlink(report_path)
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONHOME")}
    src = worktree / "src"
    env["PYTHONPATH"] = str(src if src.is_dir() else worktree)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    args = [
        str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "--continue-on-collection-errors", "--tb=short",
        "--json-report", f"--json-report-file={report_path}",
        *(nodeids or []),
    ]
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=worktree, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return TestRun(ms=int((time.monotonic() - t0) * 1000), timed_out=True)
    ms = int((time.monotonic() - t0) * 1000)
    text = out.decode(errors="replace")
    try:
        report = json.loads(Path(report_path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return TestRun(ms=ms, red=[_session_abort(text, worktree)])
    finally:
        Path(report_path).unlink(missing_ok=True)
    run = parse_report(report, worktree)
    run.ms = ms
    return run


def parse_report(report: dict, worktree: Path) -> TestRun:
    run = TestRun()
    for c in report.get("collectors", []):
        if c.get("outcome") == "failed" and c.get("nodeid"):
            exc_type, msg = _exc_from_longrepr(c.get("longrepr", ""))
            run.red.append(Red(
                nodeid=collect_id(c["nodeid"]), kind="collect", exc_type=exc_type,
                message=msg, frames=_frames_from_text(c.get("longrepr", ""), worktree),
                longrepr=c.get("longrepr", ""),
            ))
    for t in report.get("tests", []):
        if t["outcome"] == "passed":
            run.passed.add(t["nodeid"])
            continue
        if t["outcome"] in ("skipped", "xfailed"):
            continue
        stage = next((t[s] for s in ("call", "setup", "teardown") if t.get(s, {}).get("outcome") == "failed"), {})
        crash = stage.get("crash", {})
        exc_type, msg = _split_exc(crash.get("message", ""))
        frames = [f for f in ((_rel(e["path"], worktree), e["lineno"]) for e in stage.get("traceback", [])) if f[0]]
        longrepr = stage.get("longrepr", "")
        logged = _logged_error(stage.get("log") or [], worktree)
        if logged and _uninformative(exc_type, frames):
            # The code under test caught the real exception and only logged it (e.g. a CLI
            # that exits 1): use the logged traceback as the cause.
            exc_type, msg, frames, text = logged
            longrepr = f"{longrepr}\n\n--- logged error (the actual cause) ---\n{text}"
        run.red.append(Red(nodeid=t["nodeid"], kind="test", exc_type=exc_type, message=msg,
                           frames=frames, longrepr=longrepr))
    return run


_GENERIC = {"AssertionError", "Exit", "SystemExit", "Failed", "Error"}


def _uninformative(exc_type: str, frames: list[tuple[str, int]]) -> bool:
    from pheromone.seed.seeder import is_test_file  # local import: seeder imports this module

    return exc_type in _GENERIC or all(is_test_file(p) for p, _ in frames)


def _logged_error(records: list[dict], worktree: Path) -> tuple[str, str, list[tuple[str, int]], str] | None:
    """Last ERROR log record with a traceback, preferring Pydantic errors."""
    errs = [r for r in records if r.get("levelname") in ("ERROR", "CRITICAL") and r.get("exc_text")]
    if not errs:
        return None
    rec = next((r for r in reversed(errs) if "pydantic" in r["exc_text"].lower()), errs[-1])
    text = rec["exc_text"]
    frames = [(_rel(m.group(1), worktree), int(m.group(2))) for m in _FILE_LINE.finditer(text)]
    last = next((l.strip() for l in reversed(text.splitlines()) if l.strip()), "")
    exc_type, msg = _split_exc(last)
    return exc_type, msg, [f for f in frames if f[0]], text[-3000:]


_FILE_LINE = re.compile(r'File "([^"]+)", line (\d+)')


def _session_abort(text: str, worktree: Path) -> Red:
    exc_type, msg = _exc_from_longrepr(text)
    return Red(nodeid=collect_id("conftest.py"), kind="session", exc_type=exc_type,
               message=msg, frames=_frames_from_text(text, worktree), longrepr=text[-4000:])


def _split_exc(message: str) -> tuple[str, str]:
    head = message.strip().splitlines()[0] if message.strip() else ""
    if head.startswith("assert "):  # bare assert: pytest shows the expression, not the type
        return "AssertionError", head
    if ": " in head:
        exc, rest = head.split(": ", 1)
        if " " not in exc.strip():
            return exc.rsplit(".", 1)[-1].strip(), rest.strip()
    return head.rsplit(".", 1)[-1].strip() or "Error", ""


def _exc_from_longrepr(text: str) -> tuple[str, str]:
    """Last 'E   SomeError: msg' line in a pytest longrepr."""
    for line in reversed(text.splitlines()):
        m = _E_LINE.match(line.strip())
        if m:
            return m.group(1).rsplit(".", 1)[-1], m.group(2).strip()
    return "Error", text.strip().splitlines()[-1][:300] if text.strip() else ""


def _frames_from_text(text: str, worktree: Path) -> list[tuple[str, int]]:
    """'path/to/file.py:12: in <module>' lines inside the repo."""
    frames = []
    for line in text.splitlines():
        s = line.strip()
        if ".py:" not in s:
            continue
        path, _, rest = s.partition(".py:")
        num = rest.split(":", 1)[0]
        if num.isdigit():
            rel = _rel(path + ".py", worktree)
            if rel:
                frames.append((rel, int(num)))
    return frames


def _rel(path: str, worktree: Path) -> str:
    """Repo-relative path, or '' for files outside the repo (site-packages)."""
    p = Path(path)
    if not p.is_absolute():
        p = (worktree / p).resolve()
    try:
        rel = p.resolve().relative_to(worktree.resolve())
    except ValueError:
        return ""
    s = str(rel)
    return "" if s.startswith(".venv") or "site-packages" in s else s
