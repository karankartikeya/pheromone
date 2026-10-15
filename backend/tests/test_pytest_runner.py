from pathlib import Path

from pheromone.repo.pytest_runner import parse_report


def report(tmp: Path, log: list[dict]) -> dict:
    return {
        "collectors": [],
        "tests": [{
            "nodeid": "tests/test_cli.py::test_run",
            "outcome": "failed",
            "call": {
                "outcome": "failed",
                "crash": {"message": "AssertionError: banner text"},
                "traceback": [{"path": str(tmp / "tests/test_cli.py"), "lineno": 9}],
                "longrepr": "assert result.exit_code == 0",
                "log": log,
            },
        }],
    }


def test_logged_pydantic_error_becomes_the_cause(tmp_path: Path):
    exc = (
        "Traceback (most recent call last):\n"
        f'  File "{tmp_path}/app/runner.py", line 481, in _collect\n'
        "    settings=self.settings.dict(),\n"
        "pydantic.warnings.PydanticDeprecatedSince20: The `dict` method is deprecated; use `model_dump` instead."
    )
    noise = 'Traceback (most recent call last):\n  File "x.py", line 1\nAttributeError: no loader'
    run = parse_report(report(tmp_path, [
        {"levelname": "ERROR", "msg": "cluster summary", "exc_text": noise},
        {"levelname": "ERROR", "msg": "unexpected", "exc_text": exc},
    ]), tmp_path)
    red = run.red[0]
    assert red.exc_type == "PydanticDeprecatedSince20"
    assert red.message.startswith("The `dict` method is deprecated")
    assert red.frames == [("app/runner.py", 481)]


def test_without_logs_the_assertion_stays(tmp_path: Path):
    red = parse_report(report(tmp_path, []), tmp_path).red[0]
    assert red.exc_type == "AssertionError"
