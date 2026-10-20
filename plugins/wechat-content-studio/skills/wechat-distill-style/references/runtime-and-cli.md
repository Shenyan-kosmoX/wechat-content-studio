# Runtime and CLI

Public source version: 0.1.1. Use `scripts/run_cli.py` relative to this skill directory; resolve it to an absolute path.

```text
python <absolute-skill-directory>/scripts/run_cli.py --format json <domain> <action>
```

Skills installed through the repository's `tools/install_skills.py` carry a local `runtime.json` with the Python interpreter containing Core and CLI. The runner uses it. Keep the editable source repository in place. In the source checkout, use the Python where Core and CLI were installed, or set `WECHAT_STUDIO_PYTHON`.

If the CLI cannot be imported, follow the repository quickstart. Do not substitute an unrelated handwritten page for the tool workflow.

Global overrides precede the domain command:

```text
python <skill>/scripts/run_cli.py --format json --workspace <path> --state-root <path> <domain> <action>
```

Inspect `ok`, `error.code` and `error.context`. Use CLI commands rather than private Core imports. The public source includes `basic-editorial` v1.0.0; inspect the user's styles before selecting other layouts. Personal style packs and reference-account templates are managed in the user's workspace.

## Commands

```text
sample import
sample analyze
style validate
```

Use `<domain> <action> --help` for details. `preview serve` prints a local URL and remains running while the user previews or copies the article.
