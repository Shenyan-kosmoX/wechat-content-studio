"""Safe inline Markdown rendering for the supported WeChat subset."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse


LINK_RE = re.compile(r"\[([^]]+)\]\(([^)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def safe_web_url(raw: str) -> str:
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
            href = safe_web_url(match.group(2))
        except ValueError:
            return label
        return f'<a href="{href}" style="color:#576b95;text-decoration:none;">{label}</a>'

    escaped = LINK_RE.sub(replace_link, escaped)
    for index, token in enumerate(code_tokens):
        escaped = escaped.replace(f"\x00CODE{index}\x00", token)
    return escaped
