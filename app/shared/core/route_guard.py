from collections import OrderedDict
from collections.abc import Sequence
from threading import Lock
from typing import Any

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.routing import Match


MAX_BLOCKED_ACCESS_LOG_PATHS = 4096
_blocked_access_log_paths: OrderedDict[str, int] = OrderedDict()
_blocked_access_log_paths_lock = Lock()


class RegisteredRouteGuardMiddleware(BaseHTTPMiddleware):
    """등록된 HTTP route가 아닌 요청을 로그 미들웨어 전에 조용히 차단합니다."""

    def __init__(self, app: Any, route_owner: FastAPI) -> None:
        super().__init__(app)
        self.route_owner = route_owner

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """등록된 path만 다음 middleware로 넘기고, 미등록 path는 빈 404로 종료합니다."""
        if _matches_registered_http_route(request.scope, self.route_owner.routes):
            return await call_next(request)
        mark_blocked_access_log_path(request.url.path)
        return Response(status_code=404)


def add_registered_route_guard_middleware(app: FastAPI) -> None:
    """앱에 등록된 HTTP route allowlist 기반 차단 middleware를 등록합니다."""
    app.add_middleware(RegisteredRouteGuardMiddleware, route_owner=app)


def _matches_registered_http_route(scope: dict[str, Any], routes: Sequence[Any]) -> bool:
    """Starlette route matcher로 현재 요청 path가 등록된 route인지 확인합니다."""
    for route in routes:
        matches = getattr(route, "matches", None)
        if matches is None:
            continue
        match, _ = matches(scope)
        if match in {Match.FULL, Match.PARTIAL}:
            return True
    return False


def mark_blocked_access_log_path(path: str) -> None:
    """route guard가 차단한 path를 Uvicorn access log 필터가 한 번 버릴 수 있게 표시합니다."""
    with _blocked_access_log_paths_lock:
        _blocked_access_log_paths[path] = _blocked_access_log_paths.get(path, 0) + 1
        _blocked_access_log_paths.move_to_end(path)
        while len(_blocked_access_log_paths) > MAX_BLOCKED_ACCESS_LOG_PATHS:
            _blocked_access_log_paths.popitem(last=False)


def consume_blocked_access_log_path(path: str) -> bool:
    """표시된 차단 path를 하나 소비하고 access log를 버릴지 반환합니다."""
    with _blocked_access_log_paths_lock:
        count = _blocked_access_log_paths.get(path, 0)
        if count < 1:
            return False
        if count == 1:
            del _blocked_access_log_paths[path]
        else:
            _blocked_access_log_paths[path] = count - 1
        return True
