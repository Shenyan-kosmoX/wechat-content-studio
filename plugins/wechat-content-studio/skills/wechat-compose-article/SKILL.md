---
name: wechat-compose-article
description: Create, organize, revise, lay out, preview, and deliver recoverable WeChat Official Account article projects from a topic, draft, loose text, images, or an existing WeChat Content Studio project. Use when the user wants to co-write an article, turn materials into an article, format a finished draft, place images or text at specified positions, reopen a previous project, generate a browser preview, or copy final rich text into the WeChat editor. Do not use for learning a new reference-author style or for maintaining the long-term style library.
---

# Compose a WeChat Article

Produce a recoverable article project and a local preview with one-click rich-text copy. Preserve the user's facts, locked wording, material order, and image positions.

## Start

1. Read [references/runtime-and-cli.md](references/runtime-and-cli.md) before the first CLI call.
2. Read [references/article-workflow.md](references/article-workflow.md) before creating or changing project files.
3. Read [references/delivery-boundaries.md](references/delivery-boundaries.md) before rendering or describing validation.
4. Initialize the workspace through the CLI if needed.

## Choose the mode

- Use `co_write` when the user starts from a topic or needs substantive drafting. Confirm one article blueprint before drafting the full article.
- Use `organize` when the user supplies fragmented material that needs a coherent structure.
- Use `layout_only` when a complete draft already exists. Do not introduce facts, claims, or viewpoint changes.
- If the user supplies a project ID or existing project directory, inspect and update that project rather than creating a replacement.

## Build the project

1. Convert explicit user instructions into hard constraints. Treat image placement, quoted wording, material order, and “do not change” requests as locked.
2. Keep source materials separate from normalized article content. Import files through `article create` or `article update`; never overwrite the originals.
3. Select an existing layout style, writing profile, or preset with `style list`. If the user wants a new style learned from references, hand that task to `$wechat-distill-style` first.
4. Create or update `article-plan.yaml` and `article.md`. Use stable `BLOCK-*` and `IMG-*` IDs and preserve locked blocks on updates.
5. Validate before rendering. Resolve actionable errors; do not bypass a failed contract or missing material.

## Deliver

1. Run `article render`, then serve the generated preview with `preview serve` when the user wants to inspect or copy it.
2. Give the user the local preview URL and identify the project/build paths.
3. Tell the user to click the main copy button and paste into the WeChat Official Account editor. The copied payload contains both `text/html` and `text/plain`.
4. If images do not survive pasting, use the preview's placeholder-copy fallback and the generated image checklist.
5. Ask for text feedback after the user verifies in WeChat. Do not request a screenshot.

## Boundaries

- Do not log in to, control, save drafts in, or publish through the WeChat backend.
- Do not claim that local preview or validation proves WeChat-side rendering.
- Do not add external facts in `layout_only` mode.
- Do not move locked content or images silently. Report a compatibility conflict while retaining the requested position.
- Do not promote or archive long-term styles; use `$wechat-manage-style-library`.

## Success

Finish with a valid, recoverable project, a generated `wechat_preview.html`, one-click rich-text copy, and a clear statement that final WeChat verification belongs to the user.
