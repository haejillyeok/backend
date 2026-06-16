from app.be.services.auth.login_use_cases import AuthLoginUseCaseMixin
from app.be.services.auth.repository_protocol import AuthRepositoryProtocol
from app.be.services.auth.session_results import AuthSessionResultMixin
from app.be.services.auth.session_use_cases import AuthSessionUseCaseMixin
from app.be.services.auth.signup_use_cases import AuthSignupUseCaseMixin
from app.be.services.repository_scope import RepositoryContextFactory, RepositoryScopedService


class AuthService(
    AuthSignupUseCaseMixin,
    AuthLoginUseCaseMixin,
    AuthSessionUseCaseMixin,
    AuthSessionResultMixin,
    RepositoryScopedService[AuthRepositoryProtocol],
):
    """계정 ID/비밀번호 기반 회원가입, 로그인, 세션 인증 use case를 조합합니다."""

    def __init__(
        self,
        repository: AuthRepositoryProtocol | None = None,
        *,
        repository_context_factory: RepositoryContextFactory[AuthRepositoryProtocol] | None = None,
    ) -> None:
        super().__init__(
            repository=repository,
            repository_context_factory=repository_context_factory,
        )
