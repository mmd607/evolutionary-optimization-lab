"""Command-line interface.

Commands
--------
``evooptlab version``
    Print the installed package version.
``evooptlab validate-config PATH [PATH ...] [--strict]``
    Validate config files. Unresolved protocol decisions are reported as warnings, or as errors
    with ``--strict``. Exit code 0 on success, 1 on any validation failure.
``evooptlab env``
    Print environment metadata (Python, platform, packages, git) as JSON.
``evooptlab schema run-metadata``
    Print the JSON Schema for ``run_metadata.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from evooptlab import __version__
from evooptlab.config import ConfigError, config_hash, load_config, unresolved_fields
from evooptlab.storage import RunMetadata
from evooptlab.utils.environment import capture_environment
from evooptlab.utils.logging import configure_logging, get_logger

log = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evooptlab",
        description="EvoOptLab: reproducible, budget-aware optimization experiments.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging verbosity (default: WARNING)",
    )
    parser.add_argument(
        "--log-format",
        default="text",
        choices=["text", "json"],
        help="log output format (default: text)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="print the package version")

    validate = sub.add_parser("validate-config", help="validate configuration files")
    validate.add_argument("paths", nargs="+", type=Path, metavar="PATH")
    validate.add_argument(
        "--strict",
        action="store_true",
        help="treat unresolved protocol decisions (placeholders) as errors",
    )

    env = sub.add_parser("env", help="print environment metadata as JSON")
    env.add_argument("--lock-file", type=Path, default=None, help="lock file to hash")

    schema = sub.add_parser("schema", help="print a JSON Schema")
    schema.add_argument("name", choices=["run-metadata"])
    return parser


def _cmd_validate(paths: Sequence[Path], strict: bool) -> int:
    failures = 0
    for path in paths:
        try:
            config = load_config(path, strict=strict)
        except ConfigError as exc:
            failures += 1
            print(f"FAIL  {path}\n{exc}", file=sys.stderr)
            continue
        unresolved = unresolved_fields(config)
        print(f"OK    {path}  (sha256 {config_hash(config)[:12]})")
        for field, value in unresolved:
            print(f"  unresolved: {field} = {value!r}")
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.log_format)
    log.debug("command parsed", extra={"command": args.command})

    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "validate-config":
        return _cmd_validate(args.paths, args.strict)
    if args.command == "env":
        print(capture_environment(lock_file=args.lock_file).model_dump_json(indent=2))
        return 0
    if args.command == "schema":
        print(json.dumps(RunMetadata.model_json_schema(), indent=2))
        return 0
    parser.error(f"unknown command {args.command!r}")  # pragma: no cover - argparse guards this
