# Delivery Boundaries

`article render` generates:

```text
build/wechat.html
build/wechat_preview.html
build/image-checklist.md
build/delivery-report.yaml
```

The preview page is the user-facing deliverable. Its primary copy action writes both `text/html` and `text/plain` to the clipboard. The HTML includes inline styles and image nodes. A fallback copy mode replaces unreliable images with insertion placeholders and pairs them with `image-checklist.md`.

Use the exact language “ready for user WeChat validation” when local checks pass. Do not say “WeChat validated” until the user reports a successful paste in the WeChat Official Account editor.

Do not enter or automate the WeChat backend. Do not ask the user for screenshots. Ask for concise text feedback about spacing, fonts, components, image positions, or failed image transfer, then revise locally.
