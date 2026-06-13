from html import escape
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, status
from starlette.responses import HTMLResponse


router = APIRouter(tags=["docs"])
WEBSOCKET_API_DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "ws-api.md"


@router.get(
    "/ws-docs",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="WebSocket API 문서 페이지",
    operation_id="be_ws_docs",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "WebSocket API 문서 원본을 찾을 수 없음",
        },
    },
)
async def get_websocket_api_docs() -> HTMLResponse:
    """WebSocket API Markdown 원본을 HTML 문서 페이지로 렌더링해 반환합니다.

    주요 입력은 없고, 반환값은 `app/be/api/docs/ws-api.md` 기반 HTML 응답입니다.
    문서 파일이 누락된 경우 HTTP 404로 변환하며 파일 시스템에서 Markdown 파일을 읽는 부작용이 있습니다.
    """
    if not WEBSOCKET_API_DOC_PATH.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WebSocket API 문서를 찾을 수 없습니다.",
        )

    markdown = WEBSOCKET_API_DOC_PATH.read_text(encoding="utf-8")
    return HTMLResponse(render_websocket_api_docs(markdown))


def render_websocket_api_docs(markdown: str) -> str:
    """서버 내장 WebSocket API Markdown을 브라우저용 HTML 페이지로 변환합니다."""
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebSocket API</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --text: #17202a;
      --muted: #5f6b7a;
      --line: #d9dee7;
      --panel: #ffffff;
      --code: #101828;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
    }}
    main {{
      width: min(920px, calc(100% - 32px));
      margin: 0 auto;
      padding: 44px 0 72px;
    }}
    article {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 32px;
    }}
    h1, h2, h3 {{ line-height: 1.25; margin: 28px 0 12px; }}
    h1 {{ margin-top: 0; font-size: 32px; }}
    h2 {{ border-top: 1px solid var(--line); padding-top: 24px; font-size: 24px; }}
    h3 {{ font-size: 19px; }}
    p {{ margin: 10px 0; }}
    code {{
      border-radius: 5px;
      background: #eef2f7;
      padding: 2px 5px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.94em;
    }}
    pre {{
      overflow-x: auto;
      border-radius: 8px;
      background: var(--code);
      color: #f8fafc;
      padding: 16px;
    }}
    pre code {{ background: transparent; color: inherit; padding: 0; }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
    th, td {{ border: 1px solid var(--line); padding: 9px 11px; text-align: left; }}
    th {{ background: #f0f3f8; }}
    .meta {{ color: var(--muted); margin-bottom: 24px; }}
    .toc {{
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 0 0 28px;
      padding: 18px 20px;
    }}
    .toc strong {{ display: block; margin-bottom: 8px; }}
    .toc ol {{ margin: 0; padding-left: 20px; }}
    .toc a {{ color: #1d4ed8; text-decoration: none; }}
    .toc a:hover {{ text-decoration: underline; }}
    .mermaid {{
      background: #ffffff;
      color: var(--text);
      border: 1px solid var(--line);
      text-align: center;
    }}
  </style>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, securityLevel: "strict" }});
  </script>
</head>
<body>
  <main>
    <p class="meta">GET /ws-docs</p>
    <article>
      {_render_markdown_body(markdown)}
    </article>
  </main>
</body>
</html>
"""


def _render_markdown_body(markdown: str) -> str:
    """현재 WebSocket API 문서에서 쓰는 Markdown subset을 HTML body로 렌더링합니다."""
    html_parts: list[str] = []
    toc_items: list[tuple[int, str, str]] = []
    paragraph_lines: list[str] = []
    table_lines: list[str] = []
    code_lines: list[str] = []
    in_code_block = False
    code_language = ""
    used_heading_ids: set[str] = set()

    def flush_paragraph() -> None:
        if paragraph_lines:
            html_parts.append(f"<p>{_render_inline(' '.join(paragraph_lines))}</p>")
            paragraph_lines.clear()

    def flush_table() -> None:
        if not table_lines:
            return
        rows = [
            [cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in table_lines
            if "---" not in line
        ]
        if rows:
            header = "".join(f"<th>{_render_inline(cell)}</th>" for cell in rows[0])
            body_rows = rows[1:]
            body = "".join(
                "<tr>" + "".join(f"<td>{_render_inline(cell)}</td>" for cell in row) + "</tr>"
                for row in body_rows
            )
            html_parts.append(
                f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"
            )
        table_lines.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code_block:
                code = escape(chr(10).join(code_lines))
                if code_language == "mermaid":
                    html_parts.append(f'<pre class="mermaid">{code}</pre>')
                else:
                    html_parts.append(f"<pre><code>{code}</code></pre>")
                code_lines.clear()
                in_code_block = False
                code_language = ""
            else:
                flush_paragraph()
                flush_table()
                in_code_block = True
                code_language = stripped.removeprefix("```").strip()
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_table()
            continue

        if stripped.startswith("|"):
            flush_paragraph()
            table_lines.append(line)
            continue

        flush_table()

        if stripped.startswith("### "):
            flush_paragraph()
            heading = stripped[4:]
            heading_id = _heading_id(heading, used_heading_ids)
            html_parts.append(f'<h3 id="{heading_id}">{_render_inline(heading)}</h3>')
        elif stripped.startswith("## "):
            flush_paragraph()
            heading = stripped[3:]
            heading_id = _heading_id(heading, used_heading_ids)
            toc_items.append((2, heading_id, heading))
            html_parts.append(f'<h2 id="{heading_id}">{_render_inline(heading)}</h2>')
        elif stripped.startswith("# "):
            flush_paragraph()
            heading = stripped[2:]
            heading_id = _heading_id(heading, used_heading_ids)
            html_parts.append(f'<h1 id="{heading_id}">{_render_inline(heading)}</h1>')
        else:
            paragraph_lines.append(stripped)

    flush_paragraph()
    flush_table()
    if in_code_block:
        code = escape(chr(10).join(code_lines))
        if code_language == "mermaid":
            html_parts.append(f'<pre class="mermaid">{code}</pre>')
        else:
            html_parts.append(f"<pre><code>{code}</code></pre>")

    return "\n".join([_render_toc(toc_items), *html_parts])


def _heading_id(text: str, used_heading_ids: set[str]) -> str:
    """heading text를 문서 안에서 유일한 anchor id로 변환합니다."""
    normalized = re.sub(r"[^0-9A-Za-z가-힣]+", "-", text.lower()).strip("-")
    heading_id = normalized or "section"
    if heading_id not in used_heading_ids:
        used_heading_ids.add(heading_id)
        return heading_id

    suffix = 2
    while f"{heading_id}-{suffix}" in used_heading_ids:
        suffix += 1
    unique_heading_id = f"{heading_id}-{suffix}"
    used_heading_ids.add(unique_heading_id)
    return unique_heading_id


def _render_toc(items: list[tuple[int, str, str]]) -> str:
    """문서 heading 목록을 anchor 기반 목차로 렌더링합니다."""
    if not items:
        return ""
    links = "".join(
        f'<li class="level-{level}"><a href="#{heading_id}">{_render_inline(title)}</a></li>'
        for level, heading_id, title in items
    )
    return f'<nav class="toc" aria-label="문서 목차"><strong>목차</strong><ol>{links}</ol></nav>'


def _render_inline(text: str) -> str:
    """inline code를 보존하면서 Markdown inline text를 HTML로 escape합니다."""
    parts = text.split("`")
    rendered: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            rendered.append(f"<code>{escape(part)}</code>")
        else:
            rendered.append(escape(part))
    return "".join(rendered)
