from datetime import UTC, datetime
import asyncio
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.be.dependencies.services import get_auth_service
from app.be.main import create_app
from app.be.models.user import User
from app.be.security.password import hash_password
from app.be.services.auth import AuthService
from app.shared.core.exceptions import InvalidCredentialsError


class FakeAuthRepository:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.sessions: list[dict[str, object]] = []
        self.committed = False

    async def get_user_by_nickname(self, nickname: str) -> User | None:
        return self.users.get(nickname)

    async def create_user(
        self,
        *,
        nickname: str,
        password_hash: str,
        last_access_ip: str | None,
    ) -> User:
        user = User(
            id=uuid4(),
            public_id=uuid4(),
            nickname=nickname,
            password_hash=password_hash,
            last_access_ip=last_access_ip,
        )
        self.users[nickname] = user
        return user

    async def create_user_session(
        self,
        *,
        user_id,
        token_hash: str,
        expires_at: datetime,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> None:
        self.sessions.append(
            {
                "user_id": user_id,
                "token_hash": token_hash,
                "expires_at": expires_at,
                "last_access_ip": last_access_ip,
                "user_agent": user_agent,
            }
        )

    async def commit(self) -> None:
        self.committed = True


def test_auth_service_registers_unknown_nickname_and_creates_session():
    repository = FakeAuthRepository()
    service = AuthService(repository)

    result = asyncio.run(
        service.login_or_register(
            nickname="초보자",
            password="secret-password",
            last_access_ip="203.0.113.7",
            user_agent="pytest",
        )
    )

    assert result.is_new_user is True
    assert result.user.nickname == "초보자"
    assert result.session_token
    assert repository.committed is True
    assert repository.users["초보자"].last_access_ip == "203.0.113.7"
    assert len(repository.sessions) == 1


def test_auth_service_checks_password_for_existing_nickname():
    repository = FakeAuthRepository()
    user = User(
        id=uuid4(),
        public_id=uuid4(),
        nickname="초보자",
        password_hash=hash_password("right-password"),
        last_access_ip=None,
    )
    repository.users[user.nickname] = user
    service = AuthService(repository)

    with pytest.raises(InvalidCredentialsError):
        asyncio.run(
            service.login_or_register(
                nickname="초보자",
                password="wrong-password",
                last_access_ip=None,
                user_agent=None,
            )
        )


def test_login_endpoint_sets_session_cookie_for_auth_success():
    app = create_app()

    class FakeAuthService:
        async def login_or_register(
            self,
            *,
            nickname: str,
            password: str,
            last_access_ip: str | None,
            user_agent: str | None,
        ):
            assert nickname == "초보자"
            assert password == "secret-password"
            assert last_access_ip is not None
            return type(
                "AuthResult",
                (),
                {
                    "user": type(
                        "AuthUser",
                        (),
                        {"public_id": uuid4(), "nickname": nickname},
                    )(),
                    "session_token": "plain-session-token",
                    "is_new_user": True,
                    "expires_at": datetime(2026, 6, 12, tzinfo=UTC),
                },
            )()

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"nickname": "초보자", "password": "secret-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["is_new_user"] is True
    assert body["error"] is None
    assert response.cookies.get("session_token") == "plain-session-token"
    assert "httponly" in response.headers["set-cookie"].lower()


def test_login_endpoint_returns_401_for_wrong_password():
    app = create_app()

    class FakeAuthService:
        async def login_or_register(self, **kwargs):
            raise InvalidCredentialsError

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"nickname": "초보자", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {
            "code": "INVALID_CREDENTIALS",
            "message": "닉네임 또는 비밀번호가 올바르지 않습니다.",
            "details": None,
        },
    }
    assert response.cookies.get("session_token") is None


def test_login_endpoint_returns_common_validation_error_response():
    app = create_app()

    class FakeAuthService:
        async def login_or_register(self, **kwargs):
            raise AssertionError("validation 실패 요청은 service까지 도달하지 않아야 합니다.")

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"nickname": "초보자"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "요청 값이 올바르지 않습니다."
    assert body["error"]["details"][0]["field"] == "body.password"
