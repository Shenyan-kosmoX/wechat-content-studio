---
name: wechat-manage-style-library
description: Inspect, validate, import, explicitly promote, combine, version, preset, and archive WeChat Content Studio style assets. Use when the user wants to view the growing style library, compare built-in/private/project/import candidates, save a layout and writing combination as a preset, approve a candidate for the private library, retain historical versions, or archive a style, writing profile, or preset. Do not use to collect reference samples or to draft and lay out an article.
---

# Manage the Style Library

Manage the persistent, versioned style library without mutating built-in styles or changing historical article references.

## Start

1. Read [references/runtime-and-cli.md](references/runtime-and-cli.md) before the first CLI call.
2. Read [references/style-library-workflow.md](references/style-library-workflow.md) before importing, promoting, presetting, or archiving.
3. Read [references/version-and-safety.md](references/version-and-safety.md) before changing persistent library state.

## Inspect and validate

1. Use `style list` with the needed archived, candidate, import, or project flags.
2. Present each item with ID, version, layer, status, maturity, and path. Keep every style and profile tied to an explicit versioned location.
3. Validate a candidate or document before any persistent change.

## Import and promote

1. Import Style Pack candidates with `style import-candidate`; import standalone writing candidates with `style import-writing-profile`.
2. Explain the candidate's evidence scope, maturity, conflicts, and target stable version.
3. Require explicit user approval in the current conversation before running `style promote` or `style promote-writing-profile` with `--confirmed-by-user`.
4. Never overwrite an existing private version. Create a new version instead.

## Presets

1. Resolve exact layout and optional writing-profile references.
2. Create a preset with `style save-preset`, pinning IDs, versions, and layers.
3. Use presets only for combinations; do not duplicate Style Pack component files inside a preset.

## Archive

1. Archive instead of delete so historical article projects remain reproducible.
2. Use the matching command for a Style Pack, standalone writing profile, or preset.
3. Never archive built-in assets in place.

## Boundaries

- Do not collect or analyze reference articles; use `$wechat-distill-style`.
- Do not write article prose, arrange article blocks, render previews, or serve delivery pages; use `$wechat-compose-article`.
- Do not treat sample count alone as maturity.
- Do not promote without explicit confirmation or silently repoint existing projects to a newer version.
- Do not delete user styles or overwrite an existing version.

## Success

Finish with an explicit versioned path and reference for every changed asset, and report whether the change was import, promotion, preset creation, or archive.
