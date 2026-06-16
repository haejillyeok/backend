from fastapi import APIRouter, HTTPException, status
from starlette.responses import HTMLResponse

from app.be.api.endpoints.ws_docs.paths import WEBSOCKET_API_DOC_PATH
from app.be.api.endpoints.ws_docs.renderer import render_websocket_api_docs


router = APIRouter(tags=["docs"])


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
