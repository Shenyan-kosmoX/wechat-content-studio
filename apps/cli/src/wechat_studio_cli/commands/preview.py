"""preview.* commands."""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from wechat_studio.rendering import create_preview_server
from wechat_studio.rendering.server import HOST, PREVIEW_FILE

from ..output import CommandExecution
from .common import load_project, workspace_manager


def configure(top: argparse._SubParsersAction) -> None:
    parser = top.add_parser("preview", help="Serve a generated preview on localhost.")
    actions = parser.add_subparsers(dest="preview_action", required=True)
    serve = actions.add_parser("serve")
    source = serve.add_mutually_exclusive_group(required=True)
    source.add_argument("--project", help="Project ID or path.")
    source.add_argument("--build-directory")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--no-open-browser", action="store_true")
    serve.set_defaults(handler=run_serve, command_name="preview.serve")


def run_serve(args: argparse.Namespace) -> CommandExecution:
    if args.project:
        project = load_project(args.project, workspace_manager(args))
        build = project.build_directory
        project_id = project.project_id
    else:
        build = Path(args.build_directory).resolve()
        project_id = None
    server = create_preview_server(build, port=args.port)
    actual_port = int(server.server_address[1])
    url = f"http://{HOST}:{actual_port}/{PREVIEW_FILE}"

    def serve() -> None:
        if not args.no_open_browser:
            webbrowser.open(url, new=2)
        try:
            server.serve_forever()
        finally:
            server.server_close()

    return CommandExecution(
        "preview.serve",
        {
            "result_type": "preview.serving",
            "project_id": project_id,
            "build_directory": str(build),
            "url": url,
            "host": HOST,
            "port": actual_port,
            "open_browser": not args.no_open_browser,
        },
        after_emit=serve,
    )
