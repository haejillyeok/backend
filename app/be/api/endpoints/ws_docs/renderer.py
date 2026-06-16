from app.be.api.endpoints.ws_docs.document import render_websocket_docs_page
from app.be.api.endpoints.ws_docs.markdown_renderer import render_markdown_body


def render_websocket_api_docs(markdown: str) -> str:
    """서버 내장 WebSocket API Markdown을 브라우저용 HTML 페이지로 변환합니다."""
    return render_websocket_docs_page(render_markdown_body(markdown))
