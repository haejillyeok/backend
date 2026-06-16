from app.be.schemas.response.auth import AuthUserResponse, LoginResponse, SignupResponse
from app.be.services.auth import AuthLoginResult


def map_login_response(result: AuthLoginResult) -> LoginResponse:
    """인증 service의 로그인 결과를 public API response로 변환합니다."""
    return LoginResponse(
        user=AuthUserResponse(
            public_id=result.user.public_id,
            account_id=result.user.account_id,
            nickname=result.user.nickname,
        ),
        expires_at=result.expires_at,
    )


def map_signup_response(result: AuthLoginResult) -> SignupResponse:
    """인증 service의 회원가입 결과를 public API response로 변환합니다."""
    return SignupResponse(
        user=AuthUserResponse(
            public_id=result.user.public_id,
            account_id=result.user.account_id,
            nickname=result.user.nickname,
        ),
        expires_at=result.expires_at,
    )
