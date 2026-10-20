---
name: wechat-distill-style
description: Collect and analyze user-confirmed reference articles to distill reusable, evidence-traceable WeChat writing profiles and layout Style Pack candidates. Use when the user names a liked author or public account, supplies reference links, HTML, or text, asks to learn or imitate high-level writing or formatting traits, or wants multiple public samples compared before creating a candidate style. Do not use to write the user's article, to silently choose unconfirmed samples, or to promote candidates into the stable private library.
---

# Distill a WeChat Style

Create a candidate writing profile or Style Pack from confirmed evidence without copying reference prose or fabricating layout rules.

## Start

1. Read [references/runtime-and-cli.md](references/runtime-and-cli.md) before the first CLI call.
2. Read [references/distillation-workflow.md](references/distillation-workflow.md) before collecting or analyzing samples.
3. Read [references/evidence-and-copyright.md](references/evidence-and-copyright.md) before drafting the candidate summary.

## Collect samples

1. Ask what the user likes and dislikes about the reference style.
2. Prefer specific articles supplied by the user. If only an author, public account, or direction is named, publicly find multiple candidate articles and present titles, types, accessibility, and selection reasons.
3. Obtain explicit confirmation of the sample set before candidate generation. Register inaccessible items accurately and request HTML or text when needed.
4. Import only the agreed URLs, HTML, or text. Preserve stable `SAMPLE-*` IDs and let the CLI deduplicate content.

## Analyze evidence

1. Analyze confirmed samples and keep writing evidence separate from body HTML and inline-style evidence.
2. Ignore player, comments, likes, sharing controls, and other WeChat chrome.
3. Keep each inferred rule tied to `sample_ids` and a confidence level. Report conflicts instead of averaging them away.
4. If evidence is text-only or unstyled HTML, generate only a standalone writing-profile candidate. Never infer a layout style from prose alone.
5. Treat 3–5 useful samples as provisional. Do not mark a candidate established merely because eight files exist; require varied article types, both evidence classes, no unresolved conflicts, and explicit review.

## Generate the candidate

1. Write project candidates beneath the article project's `styles/local` area unless the user explicitly asks for an imports candidate.
2. Run `sample analyze` with a candidate ID and name only after every selected sample is confirmed.
3. Validate the generated profile or Style Pack through `style validate`.
4. Summarize observed high-level traits, evidence coverage, conflicts, maturity gates, and what still needs user judgment.
5. Stop at the candidate. Ask the user to review it; use `$wechat-manage-style-library` for import, promotion, preset creation, versioning, or archive.

## Boundaries

- Do not copy reference sentences, signature expressions, article-specific claims, branding, or personal identity.
- Do not claim to reproduce a specific living author's voice. Describe reusable traits and help the user form an original style.
- Do not generate a candidate from unconfirmed samples.
- Do not promote a candidate into the private stable library.
- Do not require screenshots or enter the WeChat backend.

## Success

Finish with a schema-valid candidate carrying stable evidence IDs, confidence, maturity reasons, and a truthful distinction between writing-only and writing-plus-layout evidence.
