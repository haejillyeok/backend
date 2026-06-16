from app.be.services.match_progress.ai_failure_use_cases import (
    MatchProgressAiFailureUseCaseMixin,
)
from app.be.services.match_progress.repository_protocol import MatchProgressRepositoryProtocol
from app.be.services.match_progress.round_transition_policy import (
    MatchProgressRoundTransitionPolicy,
)
from app.be.services.match_progress.turn_policy import MatchProgressTurnPolicy
from app.be.services.match_progress.word_submission_policy import WordSubmissionPolicy
from app.be.services.match_progress.word_turn_use_cases import (
    MatchProgressWordTurnUseCaseMixin,
)
from app.be.services.repository_scope import RepositoryContextFactory, RepositoryScopedService


class MatchProgressService(
    MatchProgressAiFailureUseCaseMixin,
    MatchProgressWordTurnUseCaseMixin,
    RepositoryScopedService[MatchProgressRepositoryProtocol],
):
    """게임 진행 event를 확정하고 WebSocket 브로드캐스트용 envelope로 변환합니다."""

    def __init__(
        self,
        repository: MatchProgressRepositoryProtocol | None = None,
        *,
        repository_context_factory: RepositoryContextFactory[MatchProgressRepositoryProtocol]
        | None = None,
        round_transition_policy: MatchProgressRoundTransitionPolicy | None = None,
        turn_policy: MatchProgressTurnPolicy | None = None,
        word_submission_policy: WordSubmissionPolicy | None = None,
    ) -> None:
        super().__init__(
            repository=repository,
            repository_context_factory=repository_context_factory,
        )
        self.round_transition_policy = (
            round_transition_policy or MatchProgressRoundTransitionPolicy()
        )
        self.turn_policy = turn_policy or MatchProgressTurnPolicy()
        self.word_submission_policy = word_submission_policy or WordSubmissionPolicy()
