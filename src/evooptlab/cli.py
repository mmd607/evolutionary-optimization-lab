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
``evooptlab plan STUDY``
    Validate a study config and print its run matrix without running anything.
``evooptlab run STUDY [--resume]``
    Run every planned cell of a study. ``--resume`` continues a study and skips settled cells.
``evooptlab diagnose STUDY [--json] [--project-budget N --project-replicates N]``
    Integrity, fairness and timing checks of a study's stored runs. Exit code 1 on any FAIL.
``evooptlab aggregate STUDY [--output DIR]``
    Write per-run and per-cell tables and a manifest. Refuses if diagnostics fail.

Study commands load configs strictly, and read and write artifacts under the study's
``output_dir`` unless ``--root`` is given. They exit with code 2 on a config or study error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from evooptlab import __version__
from evooptlab.config import (
    ConfigError,
    StudyConfig,
    StudyFile,
    config_hash,
    load_config,
    unresolved_fields,
)
from evooptlab.experiments import (
    RunCell,
    StudyError,
    build_matrix,
    collect_study,
    default_output_dir,
    diagnose,
    matrix_summary,
    projected_seconds,
    run_study,
    write_aggregate,
)
from evooptlab.storage import ArtifactLayout, RunMetadata
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

    def study_command(name: str, help_text: str) -> argparse.ArgumentParser:
        command = sub.add_parser(name, help=help_text)
        command.add_argument("study", type=Path, metavar="STUDY", help="study config YAML")
        command.add_argument(
            "--root", type=Path, default=None, help="artifact root (default: study output_dir)"
        )
        return command

    study_command("plan", "print a study's run matrix without running it")
    run = study_command("run", "run a study matrix")
    run.add_argument("--resume", action="store_true", help="continue; skip settled cells")
    run.add_argument("--lock-file", type=Path, default=None, help="lock file to hash")
    diag = study_command("diagnose", "check a study's stored runs")
    diag.add_argument("--json", action="store_true", help="print the report as JSON")
    diag.add_argument("--project-budget", type=int, default=None, metavar="N")
    diag.add_argument("--project-replicates", type=int, default=None, metavar="N")
    agg = study_command("aggregate", "write result tables for a study")
    agg.add_argument("--output", type=Path, default=None, help="new output directory")
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


def _load_study(path: Path, root: Path | None) -> tuple[StudyConfig, ArtifactLayout]:
    config = load_config(path, strict=True)
    if not isinstance(config, StudyFile):
        raise ConfigError(f"{path}: expected a study config (top-level key 'study')")
    study = config.study
    return study, ArtifactLayout(root if root is not None else Path(study.output_dir))


def _cmd_plan(study: StudyConfig) -> int:
    cells = build_matrix(study)
    print(json.dumps(matrix_summary(study, cells), indent=2))
    for cell in cells:
        print(
            f"{cell.problem.name:8} {cell.algorithm.name:14} "
            f"replicate {cell.replicate:<3} seed {cell.seed}"
        )
    return 0


def _cmd_run(study: StudyConfig, layout: ArtifactLayout, args: argparse.Namespace) -> int:
    def progress(position: int, total: int, cell: RunCell, status: str) -> None:
        name = f"{cell.problem.name}/{cell.algorithm.name}/replicate {cell.replicate}"
        print(f"[{position}/{total}] {name}: {status}", flush=True)

    report = run_study(
        study, layout, resume=args.resume, lock_file=args.lock_file, progress=progress
    )
    print(
        f"executed {len(report.executed)}, skipped {len(report.skipped)}, "
        f"failed {report.n_failed}; artifacts under {layout.stage_dir(study.stage)}"
    )
    return 1 if report.n_failed else 0


def _cmd_diagnose(study: StudyConfig, layout: ArtifactLayout, args: argparse.Namespace) -> int:
    report = diagnose(collect_study(study, layout))
    projection = None
    if args.project_budget is not None and args.project_replicates is not None:
        projection = projected_seconds(report.timings, args.project_budget, args.project_replicates)
    if args.json:
        data = report.to_dict()
        data["projected_sequential_seconds"] = projection
        print(json.dumps(data, indent=2))
        return 1 if report.status == "FAIL" else 0
    label = " PRELIMINARY" if study.stage != "final" else ""
    print(f"study {study.name} [{study.stage}{label}]: {report.status}")
    for check in report.checks:
        print(f"  {check.status:4}  {check.name}: {check.summary}")
        for detail in check.details:
            print(f"          - {detail}")
    if report.timings:
        print("  timing (median per completed run):")
        for t in report.timings:
            print(
                f"    {t.problem:8} {t.algorithm:14} n={t.n_runs:<3} "
                f"wall {t.median_wall_seconds:9.3f} s  "
                f"{t.median_seconds_per_evaluation * 1e3:8.4f} ms/eval  "
                f"overhead {t.median_overhead_fraction:6.1%}"
            )
    if projection is not None:
        print(
            f"  projected sequential time at {args.project_budget} evaluations x "
            f"{args.project_replicates} replicates: {projection:.0f} s = {projection / 3600:.2f} h "
            "(linear estimate)"
        )
    return 1 if report.status == "FAIL" else 0


def _cmd_aggregate(study: StudyConfig, layout: ArtifactLayout, output: Path | None) -> int:
    collection = collect_study(study, layout)
    report = diagnose(collection)
    target = output if output is not None else default_output_dir(layout.root, collection)
    path = write_aggregate(collection, report, target)
    print(f"wrote {path} (diagnostics {report.status})")
    return 0


def _cmd_study(args: argparse.Namespace) -> int:
    try:
        study, layout = _load_study(args.study, args.root)
        if args.command == "plan":
            return _cmd_plan(study)
        if args.command == "run":
            return _cmd_run(study, layout, args)
        if args.command == "diagnose":
            return _cmd_diagnose(study, layout, args)
        return _cmd_aggregate(study, layout, args.output)
    except (ConfigError, StudyError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


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
    if args.command in {"plan", "run", "diagnose", "aggregate"}:
        return _cmd_study(args)
    parser.error(f"unknown command {args.command!r}")  # pragma: no cover - argparse guards this
