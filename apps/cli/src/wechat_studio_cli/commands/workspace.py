"""workspace.* commands."""

from __future__ import annotations

import argparse

from wechat_studio.version import CORE_VERSION, SCHEMA_VERSION

from ..output import CommandExecution
from .common import workspace_manager


def configure(top: argparse._SubParsersAction) -> None:
    parser = top.add_parser("workspace", help="Initialize product-owned user directories.")
    actions = parser.add_subparsers(dest="workspace_action", required=True)
    init = actions.add_parser("init", help="Initialize settings, registry, and data roots.")
    init.set_defaults(handler=run_init, command_name="workspace.init")


def run_init(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    paths = manager.paths
    return CommandExecution(
        "workspace.init",
        {
            "result_type": "workspace.initialized",
            "core_version": CORE_VERSION,
            "schema_version": SCHEMA_VERSION,
            "user_root": str(paths.user_root),
            "state_root": str(paths.state_root),
            "resources_root": str(paths.resources_root),
            "settings": str(paths.settings),
            "registry": str(paths.registry),
        },
    )
