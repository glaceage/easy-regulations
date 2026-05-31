from __future__ import annotations

import html
import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+\{#([a-zA-Z0-9_-]+)\})?\s*$")

_CHINESE_CSS = """
@page {
    size: A4;
    margin: 2cm;
}
body {
    font-family:
        "WenQuanYi Zen Hei", "文泉驿正黑",
        "Noto Sans CJK SC", "Noto Sans CJK JP",
        "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
        sans-serif;
    font-size: 12pt;
    line-height: 1.8;
    color: #1a1a1a;
}
header.doc-header {
    border-bottom: 2px solid #333;
    margin-bottom: 1.5em;
    padding-bottom: 0.75em;
}
header.doc-header h1 {
    font-size: 20pt;
    margin: 0 0 0.25em 0;
}
header.doc-header .version {
    font-size: 10pt;
    color: #666;
}
main h1, main h2, main h3, main h4, main h5, main h6 {
    margin-top: 1.2em;
    margin-bottom: 0.5em;
}
main p {
    margin: 0.6em 0;
    text-align: justify;
}
"""


def _render_markdown_body(markdown: str) -> str:
    lines = markdown.splitlines()
    parts: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = html.escape(" ".join(paragraph))
            parts.append(f"<p>{text}</p>")
            paragraph.clear()

    for line in lines:
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            text = html.escape(heading_match.group(2).strip())
            parts.append(f"<h{level}>{text}</h{level}>")
        elif not line.strip():
            flush_paragraph()
        else:
            paragraph.append(line.strip())

    flush_paragraph()
    return "\n".join(parts)


def markdown_to_html(markdown: str, *, title: str, version: str) -> str:
    body = _render_markdown_body(markdown)
    safe_title = html.escape(title)
    safe_version = html.escape(version)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{safe_title}</title>
<style>
{_CHINESE_CSS}
</style>
</head>
<body>
<header class="doc-header">
<h1>{safe_title}</h1>
<div class="version">版本：{safe_version}</div>
</header>
<main>
{body}
</main>
</body>
</html>
"""


def html_to_pdf(html_content: str) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise ImportError(
            "WeasyPrint is required for PDF generation. "
            "Install WeasyPrint and its system dependencies, or mock HTML.write_pdf in tests."
        ) from exc
    return HTML(string=html_content).write_pdf()
