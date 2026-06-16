from html import escape

from app.be.api.endpoints.ws_docs.markdown_helpers import (
    heading_id,
    render_doc_toolbar,
    render_inline,
    render_toc,
)


def render_markdown_body(markdown: str) -> str:
    """현재 WebSocket API 문서에서 쓰는 Markdown subset을 HTML body로 렌더링합니다."""
    html_parts: list[str] = []
    toc_items: list[tuple[int, str, str]] = []
    paragraph_lines: list[str] = []
    table_lines: list[str] = []
    code_lines: list[str] = []
    in_code_block = False
    code_language = ""
    used_heading_ids: set[str] = set()
    section_is_open = False

    def flush_paragraph() -> None:
        if paragraph_lines:
            html_parts.append(f"<p>{render_inline(' '.join(paragraph_lines))}</p>")
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
            header = "".join(f"<th>{render_inline(cell)}</th>" for cell in rows[0])
            body_rows = rows[1:]
            body = "".join(
                "<tr>" + "".join(f"<td>{render_inline(cell)}</td>" for cell in row) + "</tr>"
                for row in body_rows
            )
            html_parts.append(
                f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"
            )
        table_lines.clear()

    def close_section() -> None:
        nonlocal section_is_open
        if section_is_open:
            html_parts.append("</details>")
            section_is_open = False

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
            anchor_id = heading_id(heading, used_heading_ids)
            html_parts.append(f'<h3 id="{anchor_id}">{render_inline(heading)}</h3>')
        elif stripped.startswith("## "):
            flush_paragraph()
            close_section()
            heading = stripped[3:]
            anchor_id = heading_id(heading, used_heading_ids)
            toc_items.append((2, anchor_id, heading))
            html_parts.append(
                '<details class="doc-section" open>'
                f'<summary id="{anchor_id}"><span class="section-title">'
                f"{render_inline(heading)}</span></summary>"
            )
            section_is_open = True
        elif stripped.startswith("# "):
            flush_paragraph()
            close_section()
            heading = stripped[2:]
            anchor_id = heading_id(heading, used_heading_ids)
            html_parts.append(f'<h1 id="{anchor_id}">{render_inline(heading)}</h1>')
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
    close_section()

    return "\n".join([render_toc(toc_items), render_doc_toolbar(), *html_parts])
