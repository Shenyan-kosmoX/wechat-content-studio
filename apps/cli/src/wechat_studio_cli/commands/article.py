"""article.* commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from wechat_studio.projects import create_article_project
from wechat_studio.rendering import build_article_project
from wechat_studio.styles import PresetRegistry
from wechat_studio.validation import validate_article_project

from ..errors import usage_error
from ..output import CommandExecution
from .common import load_mapping, load_project, workspace_manager


def configure(top: argparse._SubParsersAction) -> None:
    parser = top.add_parser("article", help="Create, inspect, validate, and render articles.")
    actions = parser.add_subparsers(dest="article_action", required=True)

    create = actions.add_parser("create", help="Create one recoverable article project.")
    create.add_argument("--name", required=True)
    create.add_argument("--mode", choices=("co_write", "organize", "layout_only"), required=True)
    create.add_argument("--project-id")
    brief = create.add_mutually_exclusive_group()
    brief.add_argument("--brief")
    brief.add_argument("--brief-file")
    create.add_argument("--article-file")
    create.add_argument("--plan-file")
    create.add_argument("--text", action="append", default=[], help="Import a text material file.")
    create.add_argument("--reference", action="append", default=[], help="Import a reference file.")
    create.add_argument("--image", action="append", default=[], help="Import an image file.")
    create.add_argument("--layout-style-id")
    create.add_argument("--layout-style-version")
    create.add_argument("--layout-style-layer", choices=("project", "private", "builtin"))
    create.add_argument("--writing-profile-id")
    create.add_argument("--writing-profile-version")
    create.add_argument("--writing-profile-layer", choices=("project", "private"))
    create.add_argument("--preset-id")
    create.add_argument("--preset-version")
    create.add_argument("--preset-layer", choices=("private",))
    create.set_defaults(handler=run_create, command_name="article.create")

    update = actions.add_parser("update", help="Update one existing article project safely.")
    update.add_argument("project", help="Project ID or project directory path.")
    brief = update.add_mutually_exclusive_group()
    brief.add_argument("--brief")
    brief.add_argument("--brief-file")
    update.add_argument("--article-file")
    update.add_argument("--plan-file")
    update.add_argument("--text", action="append", default=[], help="Import a text material file.")
    update.add_argument("--reference", action="append", default=[], help="Import a reference file.")
    update.add_argument("--image", action="append", default=[], help="Import an image file.")
    update.set_defaults(handler=run_update, command_name="article.update")

    for action, handler in (
        ("inspect", run_inspect),
        ("validate", run_validate),
        ("render", run_render),
    ):
        sub = actions.add_parser(action)
        sub.add_argument("project", help="Project ID or project directory path.")
        sub.set_defaults(handler=handler, command_name=f"article.{action}")


def _reference(args: argparse.Namespace, prefix: str, *, default: dict | None = None):
    values = {
        "id": getattr(args, f"{prefix}_id", None),
        "version": getattr(args, f"{prefix}_version", None),
        "layer": getattr(args, f"{prefix}_layer", None),
    }
    supplied = [value is not None for value in values.values()]
    if any(supplied) and not all(supplied):
        raise usage_error(
            f"{prefix.replace('_', ' ')} requires id, version, and layer together.",
            fields=values,
        )
    return values if all(supplied) else default


def run_create(args: argparse.Namespace) -> CommandExecution:
    manager = workspace_manager(args)
    if args.brief_file:
        brief = Path(args.brief_file).read_text(encoding="utf-8")
    else:
        brief = args.brief or ""
    layout = _reference(args, "layout_style")
    writing = _reference(args, "writing_profile")
    preset = _reference(args, "preset")
    if preset is not None:
        resolved_preset = PresetRegistry(manager.paths).resolve(
            preset["id"], version=preset["version"]
        )
        if layout is not None and layout != resolved_preset["layout_style"]:
            raise usage_error(
                "Explicit layout style conflicts with the selected preset.",
                layout_style=layout,
                preset_layout_style=resolved_preset["layout_style"],
            )
        if writing is not None and writing != resolved_preset["writing_profile"]:
            raise usage_error(
                "Explicit writing profile conflicts with the selected preset.",
                writing_profile=writing,
                preset_writing_profile=resolved_preset["writing_profile"],
            )
        layout = dict(resolved_preset["layout_style"])
        writing = (
            dict(resolved_preset["writing_profile"])
            if resolved_preset["writing_profile"] is not None
            else None
        )
    project = create_article_project(
        manager,
        name=args.name,
        mode=args.mode,
        project_id=args.project_id,
        brief=brief,
        layout_style=layout,
        writing_profile=writing,
        preset=preset,
    )
    imported: list[dict] = []
    for kind, sources in (
        ("text", args.text),
        ("reference", args.reference),
        ("image", args.image),
    ):
        for source in sources:
            imported.append(project.material_store.import_file(source, kind=kind))
    if args.plan_file:
        project.save_plan(load_mapping(args.plan_file), preserve_locked=False)
    if args.article_file:
        project.write_article(Path(args.article_file).read_text(encoding="utf-8"))
    data = project.inspect()
    data.update(
        {
            "result_type": "article.created",
            "root": str(project.root),
            "imported_materials": imported,
        }
    )
    return CommandExecution("article.create", data)


def run_inspect(args: argparse.Namespace) -> CommandExecution:
    project = load_project(args.project, workspace_manager(args))
    data = project.inspect()
    data["result_type"] = "article.inspected"
    data["root"] = str(project.root)
    return CommandExecution("article.inspect", data)


def run_update(args: argparse.Namespace) -> CommandExecution:
    project = load_project(args.project, workspace_manager(args))
    updated_files: list[str] = []
    imported: list[dict] = []
    if args.brief_file:
        updated_files.append(
            str(project.write_brief(Path(args.brief_file).read_text(encoding="utf-8")))
        )
    elif args.brief is not None:
        updated_files.append(str(project.write_brief(args.brief)))
    if args.article_file:
        updated_files.append(
            str(project.write_article(Path(args.article_file).read_text(encoding="utf-8")))
        )
    for kind, sources in (
        ("text", args.text),
        ("reference", args.reference),
        ("image", args.image),
    ):
        for source in sources:
            imported.append(project.material_store.import_file(source, kind=kind))
    if args.plan_file:
        updated_files.append(
            str(project.save_plan(load_mapping(args.plan_file), preserve_locked=True))
        )
    if not updated_files and not imported:
        raise usage_error("article update requires content, a plan, a brief, or materials.")
    data = project.inspect()
    data.update(
        {
            "result_type": "article.updated",
            "root": str(project.root),
            "updated_files": updated_files,
            "imported_materials": imported,
        }
    )
    return CommandExecution("article.update", data)


def run_validate(args: argparse.Namespace) -> CommandExecution:
    project = load_project(args.project, workspace_manager(args))
    result = validate_article_project(project)
    result.raise_for_error()
    data = result.to_dict()
    data["result_type"] = "article.validated"
    return CommandExecution("article.validate", data, result.warnings)


def run_render(args: argparse.Namespace) -> CommandExecution:
    project = load_project(args.project, workspace_manager(args))
    result = build_article_project(project)
    data = result.to_dict()
    data["result_type"] = "article.rendered"
    return CommandExecution("article.render", data)
