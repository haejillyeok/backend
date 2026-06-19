import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import Request
from starlette.responses import Response
from fastapi.testclient import TestClient

from app.be.api.endpoints import auth as auth_endpoints
from app.be.dependencies.services import get_auth_service
from app.be.main import create_app
from app.be.models.user import User
from app.be.security.password import hash_password
from app.be.services.auth import AuthService
from app.shared.core.exceptions import AppException, InvalidCredentialsError

KST = ZoneInfo("Asia/Seoul")


class FakeAuthRepository:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.sessions: list[dict[str, object]] = []
        self.active_session_result: tuple[User, object] | None = None
        self.touched_session: object | None = None
        self.committed = False

    async def get_user_by_account_id(self, account_id: str) -> User | None:
        return self.users.get(account_id)

    async def get_user_by_nickname(self, nickname: str) -> User | None:
        return next((user for user in self.users.values() if user.nickname == nickname), None)

    async def create_user(
        self,
        *,
        account_id: str,
        nickname: str,
        password_hash: str,
        last_access_ip: str | None,
    ) -> User:
        user = User(
            id=uuid4(),
            public_id=uuid4(),
            account_id=account_id,
            nickname=nickname,
            password_hash=password_hash,
            last_access_ip=last_access_ip,
        )
        self.users[account_id] = user
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

    async def get_active_session_user(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> tuple[User, object] | None:
        return self.active_session_result

    async def touch_user_session(self, session: object, *, now: datetime) -> None:
        self.touched_session = session

    async def commit(self) -> None:
        self.committed = True


def test_session_cookie_uses_local_browser_policy_by_default(monkeypatch):
    monkeypatch.setattr(
        auth_endpoints,
        "settings",
        type("Settings", (), {"environment": None})(),
    )
    response = Response()

    auth_endpoints._set_session_cookie(
        response,
        session_token="plain-session-token",
        expires_at=datetime.now(KST) + timedelta(days=1),
    )

    set_cookie = response.headers["set-cookie"].lower()
    assert "session_token=plain-session-token" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "secure" not in set_cookie


def test_session_cookie_uses_cross_site_browser_policy_in_prod(monkeypatch):
    monkeypatch.setattr(
        auth_endpoints,
        "settings",
        type("Settings", (), {"environment": "prod"})(),
    )
    response = Response()

    auth_endpoints._set_session_cookie(
        response,
        session_token="plain-session-token",
        expires_at=datetime.now(KST) + timedelta(days=1),
    )

    set_cookie = response.headers["set-cookie"].lower()
    assert "session_token=plain-session-token" in set_cookie
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=none" in set_cookie


def test_auth_service_signup_creates_user_and_session():
    repository = FakeAuthRepository()
    service = AuthService(repository)

    result = asyncio.run(
        service.signup(
            account_id="player_001",
            nickname="초보자",
            password="secret-password",
            last_access_ip="203.0.113.7",
            user_agent="pytest",
        )
    )

    assert result.user.account_id == "player_001"
    assert result.user.nickname == "초보자"
    assert result.session_token
    assert repository.committed is True
    assert repository.users["player_001"].last_access_ip == "203.0.113.7"
    assert len(repository.sessions) == 1


def test_auth_service_login_checks_password_for_existing_account_id():
    repository = FakeAuthRepository()
    user = User(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
        password_hash=hash_password("right-password"),
        last_access_ip=None,
    )
    repository.users[user.account_id] = user
    service = AuthService(repository)

    with pytest.raises(InvalidCredentialsError):
        asyncio.run(
            service.login(
                account_id="player_001",
                password="wrong-password",
                last_access_ip=None,
                user_agent=None,
            )
        )


def test_auth_service_login_does_not_register_unknown_account_id():
    repository = FakeAuthRepository()
    service = AuthService(repository)

    with pytest.raises(InvalidCredentialsError):
        asyncio.run(
            service.login(
                account_id="player_001",
                password="secret-password",
                last_access_ip=None,
                user_agent=None,
            )
        )

    assert repository.users == {}
    assert repository.sessions == []
    assert repository.committed is False


def test_auth_service_returns_login_required_message_when_session_cookie_missing():
    repository = FakeAuthRepository()
    service = AuthService(repository)

    with pytest.raises(AppException) as exc_info:
        asyncio.run(service.authenticate_session(None))

    assert exc_info.value.code == "SESSION_EXPIRED"
    assert exc_info.value.message == "로그인이 필요합니다."
    assert exc_info.value.http_status_code == 401
    assert repository.committed is False


def test_auth_service_returns_expired_message_when_session_cookie_is_inactive():
    repository = FakeAuthRepository()
    service = AuthService(repository)

    with pytest.raises(AppException) as exc_info:
        asyncio.run(service.authenticate_session("inactive-session-token"))

    assert exc_info.value.code == "SESSION_EXPIRED"
    assert exc_info.value.message == "세션이 만료되었습니다."
    assert exc_info.value.http_status_code == 401
    assert repository.committed is False


def test_auth_service_signup_rejects_duplicate_account_id():
    repository = FakeAuthRepository()
    repository.users["player_001"] = User(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
        password_hash=hash_password("right-password"),
        last_access_ip=None,
    )
    service = AuthService(repository)

    with pytest.raises(AppException) as exc_info:
        asyncio.run(
            service.signup(
                account_id="player_001",
                nickname="새유저",
                password="right-password",
                last_access_ip=None,
                user_agent=None,
            )
        )

    assert exc_info.value.code == "AUTH_USER_CONFLICT"
    assert exc_info.value.http_status_code == 409


def test_auth_service_signup_rejects_duplicate_nickname():
    repository = FakeAuthRepository()
    repository.users["player_001"] = User(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
        password_hash=hash_password("right-password"),
        last_access_ip=None,
    )
    service = AuthService(repository)

    with pytest.raises(AppException) as exc_info:
        asyncio.run(
            service.signup(
                account_id="player_002",
                nickname="초보자",
                password="right-password",
                last_access_ip=None,
                user_agent=None,
            )
        )

    assert exc_info.value.code == "AUTH_USER_CONFLICT"
    assert exc_info.value.http_status_code == 409


def test_login_endpoint_sets_session_cookie_for_auth_success():
    app = create_app()

    class FakeAuthService:
        async def login(
            self,
            *,
            account_id: str,
            password: str,
            last_access_ip: str | None,
            user_agent: str | None,
        ):
            assert account_id == "player_001"
            assert password == "secret-password"
            assert last_access_ip is not None
            return type(
                "AuthResult",
                (),
                {
                    "user": type(
                        "AuthUser",
                        (),
                        {"public_id": uuid4(), "account_id": account_id, "nickname": "초보자"},
                    )(),
                    "session_token": "plain-session-token",
                    "expires_at": datetime.now(KST) + timedelta(days=1),
                },
            )()

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.post(
        "/api/v1/auth/login",
        json={
            "account_id": "player_001",
            "password": "secret-password",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["account_id"] == "player_001"
    assert "is_new_user" not in body["data"]
    assert "error" not in body
    assert response.cookies.get("session_token") == "plain-session-token"
    assert "httponly" in response.headers["set-cookie"].lower()


def test_login_endpoint_prefers_forwarded_client_ip_for_access_record():
    app = create_app()
    captured: dict[str, str | None] = {}

    class FakeAuthService:
        async def login(
            self,
            *,
            account_id: str,
            password: str,
            last_access_ip: str | None,
            user_agent: str | None,
        ):
            captured["last_access_ip"] = last_access_ip
            return type(
                "AuthResult",
                (),
                {
                    "user": type(
                        "AuthUser",
                        (),
                        {"public_id": uuid4(), "account_id": account_id, "nickname": "초보자"},
                    )(),
                    "session_token": "plain-session-token",
                    "expires_at": datetime.now(KST) + timedelta(days=1),
                },
            )()

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app, client=("10.0.0.12", 50000))

    response = client.post(
        "/api/v1/auth/login",
        json={
            "account_id": "player_001",
            "password": "secret-password",
        },
        headers={"x-forwarded-for": "203.0.113.7, 10.0.0.12"},
    )

    assert response.status_code == 200
    assert captured["last_access_ip"] == "203.0.113.7"


def test_login_endpoint_returns_401_for_wrong_password():
    app = create_app()

    class FakeAuthService:
        async def login(self, **kwargs):
            raise InvalidCredentialsError

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"account_id": "player_001", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {
            "code": "INVALID_CREDENTIALS",
            "message": "계정 ID 또는 비밀번호가 올바르지 않습니다.",
            "details": None,
        },
    }
    assert response.cookies.get("session_token") is None


def test_login_endpoint_returns_common_validation_error_response():
    app = create_app()

    class FakeAuthService:
        async def login(self, **kwargs):
            raise AssertionError("validation 실패 요청은 service까지 도달하지 않아야 합니다.")

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"account_id": "player_001"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "요청 값이 올바르지 않습니다."
    assert body["error"]["details"][0]["field"] == "body.password"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"account_id": "ab", "password": "secret12"}, "body.account_id"),
        (
            {"account_id": "한글id", "password": "secret12"},
            "body.account_id",
        ),
        (
            {"account_id": "player_001", "password": "short"},
            "body.password",
        ),
    ],
)
def test_login_endpoint_validates_account_id_and_password_rules(payload, field):
    app = create_app()

    class FakeAuthService:
        async def login(self, **kwargs):
            raise AssertionError("validation 실패 요청은 service까지 도달하지 않아야 합니다.")

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app)

    response = client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["field"] == field


def test_login_endpoint_accepts_six_character_ascii_password():
    app = create_app()

    class FakeAuthService:
        async def login(
            self,
            *,
            account_id: str,
            password: str,
            last_access_ip: str | None,
            user_agent: str | None,
        ):
            assert account_id == "player_001"
            assert password == "abc123"
            return type(
                "AuthResult",
                (),
                {
                    "user": type(
                        "AuthUser",
                        (),
                        {"public_id": uuid4(), "account_id": account_id, "nickname": "초보자"},
                    )(),
                    "session_token": "plain-session-token",
                    "expires_at": datetime.now(KST) + timedelta(days=1),
                },
            )()

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"account_id": "player_001", "password": "abc123"},
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"account_id": "player_001", "password": "한글pass1"}, "body.password"),
        ({"account_id": "player_001", "password": "pass word"}, "body.password"),
    ],
)
def test_login_endpoint_rejects_non_ascii_or_spaced_password(payload, field):
    app = create_app()

    class FakeAuthService:
        async def login(self, **kwargs):
            raise AssertionError("validation 실패 요청은 service까지 도달하지 않아야 합니다.")

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app)

    response = client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["field"] == field


def test_signup_endpoint_sets_session_cookie_for_auth_success():
    app = create_app()

    class FakeAuthService:
        async def signup(
            self,
            *,
            account_id: str,
            nickname: str,
            password: str,
            last_access_ip: str | None,
            user_agent: str | None,
        ):
            assert account_id == "player_001"
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
                        {"public_id": uuid4(), "account_id": account_id, "nickname": nickname},
                    )(),
                    "session_token": "plain-session-token",
                    "expires_at": datetime.now(KST) + timedelta(days=1),
                },
            )()

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "account_id": "player_001",
            "nickname": "초보자",
            "password": "secret-password",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["account_id"] == "player_001"
    assert body["data"]["user"]["nickname"] == "초보자"
    assert "is_new_user" not in body["data"]
    assert "error" not in body
    assert response.cookies.get("session_token") == "plain-session-token"
    assert "httponly" in response.headers["set-cookie"].lower()


def test_signup_endpoint_returns_409_for_duplicate_user():
    app = create_app()

    class FakeAuthService:
        async def signup(self, **kwargs):
            raise AppException(
                code="AUTH_USER_CONFLICT",
                message="이미 사용 중인 계정 ID 또는 닉네임입니다.",
                http_status_code=409,
            )

    async def override_get_auth_service(request: Request) -> FakeAuthService:
        return FakeAuthService()

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "account_id": "player_001",
            "nickname": "초보자",
            "password": "secret-password",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {
            "code": "AUTH_USER_CONFLICT",
            "message": "이미 사용 중인 계정 ID 또는 닉네임입니다.",
            "details": None,
        },
    }
