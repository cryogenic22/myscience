"""CLI for the deterministic Market Zero coordination kernel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from .kernel import CoordinationKernel, CoordinationViolation, Violation
from .model import strict_json_loads


def _load(path: str) -> dict:
    value = strict_json_loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _violations_json(violations: list[Violation] | tuple[Violation, ...]) -> list[dict]:
    return [
        {"code": item.code, "item_id": item.item_id, "message": item.message}
        for item in violations
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m coordination")
    parser.add_argument(
        "--graph",
        default="coordination/contracts/work_graph.json",
        help="protected work-graph JSON",
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        help="controller observation snapshot JSON",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="allow a declared synthetic snapshot (tests/bootstrap only)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("run-verifiers")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        graph = _load(args.graph)
        snapshot = _load(args.snapshot)
        repository_root = Path.cwd().resolve()
        if snapshot.get("synthetic") is True and not args.allow_synthetic:
            raise CoordinationViolation(
                [Violation("SYNTHETIC_SNAPSHOT", "snapshot", "synthetic state cannot drive an agent queue")]
            )
        kernel = CoordinationKernel(
            graph,
            snapshot,
            repository_root=repository_root,
            graph_path=Path(args.graph).resolve(),
        )
        kernel.require_valid()
        if args.command == "validate":
            payload = {"ok": True, "violations": []}
        elif args.command == "run-verifiers":
            tests = list(kernel.test_verifiers())
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *tests,
                    "-q",
                    "--no-header",
                    "-p",
                    "no:cacheprovider",
                ],
                cwd=repository_root,
                check=False,
            )
            payload = {"ok": result.returncode == 0, "tests": tests}
            print(json.dumps(payload, indent=2, sort_keys=True))
            return result.returncode
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (CoordinationViolation, OSError, ValueError, json.JSONDecodeError) as exc:
        violations = exc.violations if isinstance(exc, CoordinationViolation) else (
            Violation("INPUT_ERROR", "cli", str(exc)),
        )
        print(json.dumps({"ok": False, "violations": _violations_json(violations)}, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
