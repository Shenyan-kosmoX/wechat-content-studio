"""project.* commands."""

from __future__ import annotations

import argparse

from wechat_studio.migrations import migrate_project

from ..output import CommandExecution
from .common import project_path, workspace_manager


def configure(top: argparse._SubParsersAction) -> None:
    parser = top.add_parser("project", help="Project schema lifecycle commands.")
    actions = parser.add_subparsers(dest="project_action", required=True)
    migrate = actions.add_parser("migrate")
    migrate.add_argument("project", help="Project ID or directory path.")
    migrate.add_argument("--target-version", default="1.0")
    migrate.add_argument("--backup-root")
    migrate.add_argument("--dry-run", action="store_true")
    migrate.set_defaults(handler=run_migrate, command_name="project.migrate")


def run_migrate(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    result = migrate_project(
        project_path(args.project, manager),
        target_version=args.target_version,
        backup_root=args.backup_root,
        dry_run=args.dry_run,
    )
    data = result.to_dict()
    data["result_type"] = "project.migrated"
    return CommandExecution("project.migrate", data)
