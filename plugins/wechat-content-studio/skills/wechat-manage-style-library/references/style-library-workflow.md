# Style Library Workflow

## Layers

Resolution order is project, private, built-in, then baseline safety rules. Imports are a review area and are not selected as stable styles.

Storage locations are resolved by Core:

```text
resources/builtin-styles/<style-id>-v<version>/
<workspace>/styles/private/<style-id>-v<version>/
<workspace>/styles/imports/<style-id>-v<version>/
<project>/styles/local/<style-id>-v<version>/
<workspace>/writing-profiles/<profile-id>-v<version>.yaml
<workspace>/writing-profiles/imports/<profile-id>-v<version>.yaml
<workspace>/presets/<preset-id>-v<version>.yaml
```

## Candidate lifecycle

Validate first. Import a Style Pack with `style import-candidate` or a standalone writing profile with `style import-writing-profile`. Review evidence and maturity with the user. Promote only after explicit approval, passing `--confirmed-by-user` and optionally a stable `--target-version`.

Promotion copies and rewrites into the private library; it does not mutate the source candidate. Existing private versions are immutable.

## Presets

`style save-preset` pins one layout reference and an optional writing-profile reference. Every reference must include ID, version, and layer. Presets live in the private workspace and can be archived without deleting dependencies.

## Archive

Archive hides an asset from new default choices but keeps the file for historical resolution. Use `--include-archived` to inspect it later.
