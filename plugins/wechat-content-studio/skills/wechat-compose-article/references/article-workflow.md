# Article Workflow

## Project creation

Use `article create` with one of `co_write`, `organize`, or `layout_only`. Supply source text, references, and images with repeated `--text`, `--reference`, and `--image` flags. Use exact versioned style references or a preset.

For an existing project, run `article inspect`, then use `article update`. That command can replace `brief.md`, `article.md`, update `article-plan.yaml`, and import more materials. Plan updates preserve existing locked blocks.

## Article plan

Use these stable IDs:

```text
TEXT-001, REF-001, BLOCK-001, IMG-001
```

Each plan block requires `id`, `type`, `purpose`, and `locked`. Image blocks also require `material_id` and exactly one `before`, `after`, or `inside` placement with a `locked` flag.

Translate user language into constraints:

- “这句话不要改” → hard wording constraint and locked block.
- “图片放在解释功能之后” → locked image placement after that block.
- “大概在第二节附近” → soft placement suggestion.
- “只排版” → no new facts or argument changes.

Keep the canonical article in `article.md`. Use the supported component directives only when they serve meaning: lead, section title, subtitle, key sentence, quote, list, divider, image, caption, code, and ending.

## Validation

Run `article validate` before render. Fix missing material, invalid anchors, unresolved styles, malformed project files, and delivery errors through supported commands. Do not manually edit user library metadata to bypass validation.
