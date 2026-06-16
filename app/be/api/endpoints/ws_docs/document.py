from app.be.api.endpoints.ws_docs.page_assets import (
    WEBSOCKET_DOCS_PAGE_SCRIPTS,
    WEBSOCKET_DOCS_PAGE_STYLE,
)


def render_websocket_docs_page(body: str) -> str:
    """렌더링된 WebSocket 문서 body를 독립 HTML 페이지로 감쌉니다."""
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebSocket API</title>
  <style>{WEBSOCKET_DOCS_PAGE_STYLE}</style>
{WEBSOCKET_DOCS_PAGE_SCRIPTS}
</head>
<body>
  <main>
    <p class="meta">GET /ws-docs</p>
    <article>
      {body}
    </article>
  </main>
</body>
</html>
"""
