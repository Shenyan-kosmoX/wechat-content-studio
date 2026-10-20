"""sample.* commands for evidence collection and candidate generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from wechat_studio.distillation import SampleRegistry, aggregate_evidence, build_candidate
from wechat_studio.errors import DistillationInsufficientEvidenceError, DistillationInvalidError
from wechat_studio.storage.yaml_io import write_json_atomic

from ..errors import usage_error
from ..output import CommandExecution
from .common import workspace_manager


def configure(top: argparse._SubParsersAction) -> None:
    parser = top.add_parser("sample", help="Register and analyze style-reference samples.")
    actions = parser.add_subparsers(dest="sample_action", required=True)

    import_parser = actions.add_parser("import")
    import_parser.add_argument("--collection", required=True)
    source = import_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--file")
    import_parser.add_argument("--payload-file", help="Attach captured HTML/text to --url.")
    import_parser.add_argument("--kind", choices=("html", "text"))
    import_parser.add_argument("--title", default="")
    import_parser.add_argument(
        "--article-type",
        choices=("opinion", "tutorial", "review", "news", "interview", "essay", "other"),
        default="other",
    )
    import_parser.add_argument(
        "--accessibility",
        choices=("unverified", "accessible", "unavailable", "missing"),
        default="unverified",
    )
    import_parser.add_argument("--confirmed-by-user", action="store_true")
    import_parser.set_defaults(handler=run_import, command_name="sample.import")

    analyze = actions.add_parser("analyze")
    analyze.add_argument("--collection", required=True)
    analyze.add_argument("--sample-id", action="append", default=[])
    analyze.add_argument("--confirmed-only", action="store_true")
    analyze.add_argument("--aggregate-output")
    analyze.add_argument("--candidate-id")
    analyze.add_argument("--candidate-name")
    analyze.add_argument("--candidate-version", default="0.1.0-candidate.1")
    analyze.add_argument("--candidate-storage", choices=("project", "imports"), default="project")
    analyze.add_argument("--candidate-root")
    analyze.add_argument("--publisher-or-author", default="")
    analyze.add_argument("--tag", action="append", default=[])
    analyze.add_argument("--reviewed-for-established", action="store_true")
    analyze.set_defaults(handler=run_analyze, command_name="sample.analyze")


def run_import(args: argparse.Namespace) -> CommandExecution:
    registry = SampleRegistry(args.collection).initialize()
    if args.url and args.payload_file:
        result = registry.import_path(
            args.payload_file,
            kind=args.kind,
            source_url=args.url,
            title=args.title,
            article_type=args.article_type,
            confirmed_by_user=args.confirmed_by_user,
        )
    elif args.url:
        result = registry.register_url(
            args.url,
            title=args.title,
            article_type=args.article_type,
            accessibility=args.accessibility,
            confirmed_by_user=args.confirmed_by_user,
        )
    else:
        if args.payload_file:
            raise usage_error("--payload-file can only be used with --url.")
        result = registry.import_path(
            args.file,
            kind=args.kind,
            title=args.title,
            article_type=args.article_type,
            confirmed_by_user=args.confirmed_by_user,
        )
    return CommandExecution(
        "sample.import",
        {
            "result_type": "sample.imported",
            "collection": str(registry.root),
            "created": result.created,
            "duplicate_of": result.duplicate_of,
            "sample": result.record,
        },
    )


def run_analyze(args: argparse.Namespace) -> CommandExecution:
    registry = SampleRegistry(args.collection).initialize()
    records = registry.list()
    selected_ids = args.sample_id or [record["sample_id"] for record in records]
    by_id = {record["sample_id"]: record for record in records}
    missing = [sample_id for sample_id in selected_ids if sample_id not in by_id]
    if missing:
        from wechat_studio.errors import SampleNotFoundError

        raise SampleNotFoundError(
            "One or more samples do not exist.", context={"sample_ids": missing}
        )
    if args.confirmed_only:
        selected_ids = [sample_id for sample_id in selected_ids if by_id[sample_id]["confirmed_by_user"]]
    if not selected_ids:
        raise DistillationInsufficientEvidenceError(
            "No samples were selected for analysis.", context={"collection": str(registry.root)}
        )
    reports = [registry.analyze(sample_id) for sample_id in selected_ids]
    aggregate = aggregate_evidence(reports)
    aggregate_path = Path(args.aggregate_output).resolve() if args.aggregate_output else registry.root / "aggregate.json"
    write_json_atomic(aggregate_path, aggregate)

    candidate_data = None
    wants_candidate = any(
        value is not None for value in (args.candidate_id, args.candidate_name, args.candidate_root)
    )
    if wants_candidate:
        if not args.candidate_id or not args.candidate_name:
            raise usage_error("Candidate generation requires --candidate-id and --candidate-name.")
        unconfirmed = [sample_id for sample_id in selected_ids if not by_id[sample_id]["confirmed_by_user"]]
        if unconfirmed:
            raise DistillationInvalidError(
                "Candidate generation requires user-confirmed samples.",
                context={"unconfirmed_sample_ids": unconfirmed},
            )
        if args.candidate_storage == "imports":
            destination = (
                Path(args.candidate_root).resolve()
                if args.candidate_root
                else workspace_manager(args).paths.imported_styles
            )
        else:
            if not args.candidate_root:
                raise usage_error(
                    "Project candidates require --candidate-root pointing to styles/local."
                )
            destination = Path(args.candidate_root).resolve()
        candidate = build_candidate(
            aggregate,
            destination,
            style_id=args.candidate_id,
            name=args.candidate_name,
            version=args.candidate_version,
            storage=args.candidate_storage,
            publisher_or_author=args.publisher_or_author,
            tags=args.tag,
            reviewed_for_established=args.reviewed_for_established,
        )
        candidate_data = {
            "kind": candidate.kind,
            "path": str(candidate.path),
            "reference": candidate.reference,
            "maturity": candidate.maturity.to_dict(),
        }

    return CommandExecution(
        "sample.analyze",
        {
            "result_type": "sample.analyzed",
            "collection": str(registry.root),
            "analyzed_sample_ids": selected_ids,
            "aggregate_path": str(aggregate_path),
            "aggregate": aggregate,
            "candidate": candidate_data,
        },
    )
