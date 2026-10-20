# Version and Safety

- Keep built-in assets read-only.
- Keep project candidates local until the user chooses to import them.
- Require explicit confirmation for promotion.
- Promote prerelease candidates to stable semantic versions; never overwrite an existing target.
- Pin article projects and presets to exact IDs, versions, and layers.
- Never silently update old projects when a newer style version appears.
- Archive instead of deleting user-owned assets.
- Report the source path, destination path, reference, status, and maturity after every persistent change.

Local schema validation does not establish WeChat-side compatibility. Component or article validation in the WeChat backend remains user-reported and never requires a screenshot.
