#!/usr/bin/env python3
"""Render the Shenyan V1 Markdown subset to WeChat HTML delivery pages."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from urllib.parse import urlparse


DIRECTIVE_COMPONENTS = {
    "lead": "lead",
    "key": "key_sentence",
    "key_sentence": "key_sentence",
    "caption": "caption",
    "ending": "ending",
}

ARTICLE_ROOT_STYLE = (
    "box-sizing:border-box;width:100%;max-width:677px;margin:0 auto;"
    "font-family:system-ui,-apple-system,BlinkMacSystemFont,'Helvetica Neue',"
    "'PingFang SC','Hiragino Sans GB','Microsoft YaHei UI','Microsoft YaHei',"
    "Arial,sans-serif;font-size:16px;line-height:1.6;color:rgba(0,0,0,0.9);"
    "letter-spacing:0.034em;text-align:justify;word-break:normal;"
    "overflow-wrap:break-word;"
)

SPECIAL_START = re.compile(
    r"^(?:#{2,3}\s+|```|:::|>\s?|[-*+]\s+|\d+[.)]\s+|!\[[^]]*\]\([^)]*\)|(?:-{3,}|\*{3,}|_{3,})\s*$)"
)
IMAGE_RE = re.compile(r"^!\[([^]]*)\]\((\S+?)(?:\s+[\"']([^\"']*)[\"'])?\)\s*$")
LINK_RE = re.compile(r"\[([^]]+)\]\(([^)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def load_templates(components_dir: Path) -> dict[str, str]:
    names = (
        "paragraph",
        "section_title",
        "sub_title",
        "key_sentence",
        "quote",
        "image",
        "caption",
        "divider",
        "code",
        "list",
        "lead",
        "ending",
    )
    templates: dict[str, str] = {}
    for name in names:
        path = components_dir / f"{name}.html"
        templates[name] = path.read_text(encoding="utf-8").strip()
    return templates


def fill(template: str, **values: str) -> str:
    output = template
    for name, value in values.items():
        output = output.replace("{{" + name + "}}", value)
    unresolved = re.findall(r"\{\{[a-z_]+\}\}", output)
    if unresolved:
        raise ValueError(f"Unresolved component placeholders: {', '.join(unresolved)}")
    return output


def safe_url(raw: str) -> str:
    value = html.unescape(raw.strip())
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Only http/https URLs are allowed: {raw}")
    return html.escape(value, quote=True)


def render_inline(raw: str) -> str:
    escaped = html.escape(raw.strip(), quote=False)

    code_tokens: list[str] = []

    def protect_code(match: re.Match[str]) -> str:
        code_tokens.append(
            '<code style="font-family:Menlo,Consolas,monospace;font-size:0.92em;'
            'color:#333333;background-color:#f6f8fa;padding:1px 4px;border-radius:3px;">'
            + match.group(1)
            + "</code>"
        )
        return f"\x00CODE{len(code_tokens) - 1}\x00"

    escaped = CODE_RE.sub(protect_code, escaped)
    escaped = BOLD_RE.sub(r'<strong style="font-weight:700;">\1</strong>', escaped)

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        try:
            href = safe_url(match.group(2))
        except ValueError:
            return label
        return f'<a href="{href}" style="color:#576b95;text-decoration:none;">{label}</a>'

    escaped = LINK_RE.sub(replace_link, escaped)
    for index, token in enumerate(code_tokens):
        escaped = escaped.replace(f"\x00CODE{index}\x00", token)
    return escaped


def parse_front_matter(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    if not lines or lines[0].strip() != "---":
        return {}, lines
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, lines
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"\'')
    return metadata, lines[end + 1 :]


def is_special(line: str) -> bool:
    return bool(SPECIAL_START.match(line.strip()))


def render_blocks(lines: list[str], templates: dict[str, str]) -> list[str]:
    output: list[str] = []
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith(":::") and stripped != ":::":
            directive = stripped[3:].strip().lower()
            if directive not in DIRECTIVE_COMPONENTS:
                raise ValueError(f"Unknown directive on line {index + 1}: {directive}")
            index += 1
            content_lines: list[str] = []
            while index < len(lines) and lines[index].strip() != ":::":
                if lines[index].strip():
                    content_lines.append(lines[index].strip())
                index += 1
            if index >= len(lines):
                raise ValueError(f"Directive '{directive}' is missing its closing :::")
            index += 1
            content = "<br />".join(render_inline(line) for line in content_lines)
            output.append(fill(templates[DIRECTIVE_COMPONENTS[directive]], content=content))
            continue

        if stripped.startswith("```"):
            language = stripped[3:].strip()
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index >= len(lines):
                raise ValueError("Code fence is missing its closing ```")
            index += 1
            content = html.escape("\n".join(code_lines), quote=False)
            if language:
                content = (
                    f'<span style="color:#888888;">{html.escape(language)}</span>\n' + content
                )
            output.append(fill(templates["code"], content=content))
            continue

        if stripped.startswith("## "):
            output.append(
                fill(templates["section_title"], content=render_inline(stripped[3:]))
            )
            index += 1
            continue

        if stripped.startswith("### "):
            output.append(fill(templates["sub_title"], content=render_inline(stripped[4:])))
            index += 1
            continue

        if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
            output.append(templates["divider"])
            index += 1
            continue

        image_match = IMAGE_RE.match(stripped)
        if image_match:
            output.append(
                fill(
                    templates["image"],
                    src=safe_url(image_match.group(2)),
                    alt=html.escape(image_match.group(1), quote=True),
                )
            )
            index += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip()[1:].lstrip())
                index += 1
            content = "<br />".join(render_inline(line) for line in quote_lines)
            output.append(fill(templates["quote"], content=content))
            continue

        unordered = re.match(r"^[-*+]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if unordered or ordered:
            list_tag = "ul" if unordered else "ol"
            items: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                match = (
                    re.match(r"^[-*+]\s+(.+)$", current)
                    if list_tag == "ul"
                    else re.match(r"^\d+[.)]\s+(.+)$", current)
                )
                if not match:
                    break
                items.append(
                    '<li style="margin:0 0 8px;padding:0;">'
                    + render_inline(match.group(1))
                    + "</li>"
                )
                index += 1
            output.append(
                fill(templates["list"], list_tag=list_tag, items="".join(items))
            )
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(lines) and lines[index].strip() and not is_special(lines[index]):
            paragraph_lines.append(lines[index].strip())
            index += 1
        content = " ".join(render_inline(line) for line in paragraph_lines)
        output.append(fill(templates["paragraph"], content=content))

    return output


def render_article(source: Path, components_dir: Path) -> tuple[str, str]:
    raw_lines = source.read_text(encoding="utf-8").splitlines()
    metadata, content_lines = parse_front_matter(raw_lines)
    templates = load_templates(components_dir)
    blocks = render_blocks(content_lines, templates)
    return metadata.get("title", source.stem), "\n".join(blocks)


def render_article_root(article: str, root_id: str) -> str:
    return (
        f'<section id="{root_id}" style="{ARTICLE_ROOT_STYLE}">\n'
        f"{article}\n"
        "  </section>"
    )


def render_document_from_article(title: str, article: str) -> str:
    escaped_title = html.escape(title, quote=True)
    article_root = render_article_root(article, "js_content")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{escaped_title}</title>
</head>
<body style="margin:0;padding:24px 0;background-color:#ffffff;">
  {article_root}
</body>
</html>
"""


def render_preview_document_from_article(title: str, article: str) -> str:
    escaped_title = html.escape(title, quote=True)
    article_root = render_article_root(article, "wechat-copy-root")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta name="robots" content="noindex,nofollow" />
  <link rel="icon" href="data:," />
  <title>{escaped_title}｜公众号富文本预览</title>
  <style>
    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #f3f5f7;
      color: #1f2329;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
        "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
    }}
    .preview-toolbar {{
      position: sticky;
      z-index: 10;
      top: 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      width: 100%;
      padding: 16px max(20px, calc((100% - 980px) / 2));
      border-bottom: 1px solid #e5e7eb;
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 4px 18px rgba(15, 23, 42, 0.06);
      backdrop-filter: blur(12px);
    }}
    .preview-heading {{ margin: 0 0 4px; font-size: 17px; line-height: 1.4; }}
    .preview-help {{ margin: 0; color: #667085; font-size: 13px; line-height: 1.5; }}
    .preview-actions {{ min-width: 230px; text-align: right; }}
    .copy-button {{
      appearance: none;
      width: 100%;
      min-height: 42px;
      padding: 10px 18px;
      border: 0;
      border-radius: 8px;
      background: #07c160;
      color: #ffffff;
      cursor: pointer;
      font-size: 15px;
      font-weight: 700;
      line-height: 1.4;
      transition: background-color 0.16s ease, transform 0.16s ease;
    }}
    .copy-button:hover {{ background: #06ad56; }}
    .copy-button:active {{ transform: translateY(1px); }}
    .copy-button:disabled {{ cursor: wait; opacity: 0.72; }}
    .copy-status {{ min-height: 20px; margin: 6px 0 0; color: #667085; font-size: 12px; }}
    .copy-status[data-state="success"] {{ color: #07883f; }}
    .copy-status[data-state="error"] {{ color: #c62828; }}
    .preview-stage {{ padding: 32px 20px 64px; }}
    .article-paper {{
      width: min(100%, 757px);
      margin: 0 auto;
      padding: 40px;
      border: 1px solid #e8eaed;
      border-radius: 12px;
      background: #ffffff;
      box-shadow: 0 14px 40px rgba(15, 23, 42, 0.08);
    }}
    @media (max-width: 720px) {{
      .preview-toolbar {{ position: static; display: block; padding: 14px 16px; }}
      .preview-actions {{ min-width: 0; margin-top: 12px; text-align: left; }}
      .preview-stage {{ padding: 16px 0 40px; }}
      .article-paper {{ padding: 24px 12px; border-right: 0; border-left: 0; border-radius: 0; }}
    }}
  </style>
</head>
<body>
  <header class="preview-toolbar" data-preview-toolbar="true">
    <div>
      <h1 class="preview-heading">公众号富文本预览</h1>
      <p class="preview-help">复制后切换到微信公众号后台，直接按 Ctrl+V 粘贴。</p>
    </div>
    <div class="preview-actions">
      <button id="copy-rich-text" class="copy-button" type="button">一键复制公众号富文本</button>
      <p id="copy-status" class="copy-status" role="status" aria-live="polite">推荐通过 open_preview.cmd 打开本页。</p>
    </div>
  </header>
  <main class="preview-stage">
    <div class="article-paper">
      {article_root}
    </div>
  </main>
  <script>
    (() => {{
      "use strict";

      const copyRoot = document.getElementById("wechat-copy-root");
      const copyButton = document.getElementById("copy-rich-text");
      const copyStatus = document.getElementById("copy-status");

      function setStatus(message, state = "idle") {{
        copyStatus.textContent = message;
        copyStatus.dataset.state = state;
      }}

      function getClipboardPayload() {{
        return {{
          html: copyRoot.outerHTML,
          plain: copyRoot.innerText,
        }};
      }}

      function copyWithEventFallback(payload) {{
        return new Promise((resolve, reject) => {{
          const selection = window.getSelection();
          const previousRanges = [];
          for (let index = 0; index < selection.rangeCount; index += 1) {{
            previousRanges.push(selection.getRangeAt(index).cloneRange());
          }}

          const range = document.createRange();
          range.selectNode(copyRoot);
          selection.removeAllRanges();
          selection.addRange(range);

          const handleCopy = (event) => {{
            event.preventDefault();
            event.clipboardData.setData("text/html", payload.html);
            event.clipboardData.setData("text/plain", payload.plain);
          }};

          document.addEventListener("copy", handleCopy, {{ once: true }});
          let copied = false;
          try {{
            copied = document.execCommand("copy");
          }} finally {{
            document.removeEventListener("copy", handleCopy);
            selection.removeAllRanges();
            for (const previousRange of previousRanges) {{
              selection.addRange(previousRange);
            }}
          }}

          if (copied) {{
            resolve();
          }} else {{
            reject(new Error("浏览器未允许兼容复制命令。"));
          }}
        }});
      }}

      async function copyRichText() {{
        const payload = getClipboardPayload();
        copyButton.disabled = true;
        setStatus("正在写入富文本剪贴板……");

        try {{
          const supportsRichClipboard =
            navigator.clipboard &&
            typeof navigator.clipboard.write === "function" &&
            typeof ClipboardItem === "function";

          if (supportsRichClipboard) {{
            try {{
              const item = new ClipboardItem({{
                "text/html": new Blob([payload.html], {{ type: "text/html" }}),
                "text/plain": new Blob([payload.plain], {{ type: "text/plain" }}),
              }});
              await navigator.clipboard.write([item]);
            }} catch (clipboardError) {{
              await copyWithEventFallback(payload);
            }}
          }} else {{
            await copyWithEventFallback(payload);
          }}

          copyButton.textContent = "复制成功";
          setStatus("已复制，可粘贴到公众号后台。", "success");
        }} catch (error) {{
          copyButton.textContent = "重新复制";
          setStatus("复制失败，请通过 open_preview.cmd 打开后重试。", "error");
          console.error("Rich-text copy failed:", error);
        }} finally {{
          copyButton.disabled = false;
        }}
      }}

      copyButton.addEventListener("click", copyRichText);
    }})();
  </script>
</body>
</html>
"""


def render_document(source: Path, components_dir: Path) -> str:
    title, article = render_article(source, components_dir)
    return render_document_from_article(title, article)


def render_preview_document(source: Path, components_dir: Path) -> str:
    title, article = render_article(source, components_dir)
    return render_preview_document_from_article(title, article)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--components",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "components",
    )
    preview_group = parser.add_mutually_exclusive_group()
    preview_group.add_argument(
        "--preview",
        type=Path,
        help="Preview-page destination (default: wechat_preview.html beside destination).",
    )
    preview_group.add_argument(
        "--no-preview",
        action="store_true",
        help="Generate only the pure article HTML.",
    )
    args = parser.parse_args()

    title, article = render_article(args.source, args.components)
    rendered = render_document_from_article(title, article)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(rendered, encoding="utf-8")

    if not args.no_preview:
        preview_path = args.preview or args.destination.with_name("wechat_preview.html")
        preview = render_preview_document_from_article(title, article)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(preview, encoding="utf-8")


if __name__ == "__main__":
    main()
