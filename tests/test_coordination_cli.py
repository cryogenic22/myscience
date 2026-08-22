"""CLI contract tests for agent-facing coordination commands."""

from __future__ import annotations

import json
from pathlib import Path

import coordination.__main__ as cli
from coordination.__main__ import build_parser, main
import pytest


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = str(ROOT / "coordination" / "contracts" / "example_snapshot.json")


def _args(*args: str) -> list[str]:
    return ["--snapshot", SYNTHETIC, "--allow-synthetic", *args]


def _payload(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_validate_command_is_machine_readable(capsys):
    assert main(_args("validate")) == 0
    assert _payload(capsys) == {"ok": True, "violations": []}


@pytest.mark.parametrize("command", ["next", "review-queue", "state"])
def test_phase1_parser_has_no_agent_facing_state_or_queue_command(command):
    with pytest.raises(SystemExit):
        build_parser().parse_args(_args(command))


def test_malformed_graph_fails_closed(monkeypatch, capsys):
    def reject(_path: str) -> dict:
        raise ValueError("graph must contain one JSON object")

    monkeypatch.setattr(cli, "_load", reject)
    assert main(_args("validate")) == 1
    payload = _payload(capsys)

    assert payload["ok"] is False
    assert payload["violations"][0]["code"] == "INPUT_ERROR"


def test_cli_rejects_duplicate_json_keys_before_validation(monkeypatch):
    monkeypatch.setattr(
        cli.Path,
        "read_text",
        lambda *_args, **_kwargs: '{"schema":"shadow","schema":"valid"}',
    )

    with pytest.raises(ValueError, match="duplicate JSON object key"):
        cli._load("ignored.json")


def test_synthetic_snapshot_needs_explicit_fixture_flag(capsys):
    assert main(["--snapshot", SYNTHETIC, "validate"]) == 1
    payload = _payload(capsys)

    assert payload["violations"][0]["code"] == "SYNTHETIC_SNAPSHOT"


def test_verifier_runner_derives_every_test_from_the_protected_graph(
    monkeypatch, capsys
):
    observed: list[list[str]] = []

    class Result:
        returncode = 0

    def run(command, **kwargs):
        observed.append(command)
        assert kwargs["cwd"] == ROOT
        assert kwargs["check"] is False
        return Result()

    monkeypatch.setattr(cli.subprocess, "run", run)

    assert main(_args("run-verifiers")) == 0
    payload = _payload(capsys)
    assert payload == {
        "ok": True,
        "tests": [
            "tests/test_coordination_cli.py",
            "tests/test_coordination_kernel.py",
            "tests/test_protected_surface_sync.py",
        ],
    }
    assert observed[0][0:3] == [cli.sys.executable, "-m", "pytest"]
    assert set(observed[0][3:6]) == set(payload["tests"])
    assert observed[0][-4:] == ["-q", "--no-header", "-p", "no:cacheprovider"]


def test_verifier_runner_propagates_test_failure(monkeypatch, capsys):
    class Result:
        returncode = 1

    monkeypatch.setattr(cli.subprocess, "run", lambda *_args, **_kwargs: Result())

    assert main(_args("run-verifiers")) == 1
    assert _payload(capsys)["ok"] is False


def test_workflow_is_pr_hard_pinned_and_runs_the_real_suite():
    workflow = (ROOT / ".github" / "workflows" / "coordination-gate.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:" in workflow
    assert "branches: [main]" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "name: coordination-kernel" in workflow
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in workflow
    assert "actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b" in workflow
    assert "tests/test_coordination_kernel.py" not in workflow
    assert "tests/test_coordination_cli.py" not in workflow
    assert "tests/test_protected_surface_sync.py" not in workflow
    assert "python -m coordination" in workflow
    assert "--snapshot coordination/contracts/example_snapshot.json" in workflow
    assert "--allow-synthetic" in workflow
    assert "run-verifiers" in workflow
    assert "pull_request_target" not in workflow
