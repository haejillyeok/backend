from app.be.services.game.entry_use_cases import GameEntryUseCaseMixin
from app.be.services.game.membership_use_cases import GameMembershipUseCaseMixin
from app.be.services.game.repository_protocol import GameRepositoryProtocol
from app.be.services.game.room_membership_policy import RoomMembershipPolicy
from app.be.services.game.room_use_cases import GameRoomUseCaseMixin
from app.be.services.game.session_credential_policy import SessionCredentialPolicy
from app.be.services.game.session_initial_turn_policy import SessionInitialTurnPolicy
from app.be.services.game.session_participant_policy import SessionParticipantPolicy
from app.be.services.game.session_use_cases import GameSessionUseCaseMixin
from app.be.services.repository_scope import RepositoryContextFactory, RepositoryScopedService


class GameService(
    GameRoomUseCaseMixin,
    GameMembershipUseCaseMixin,
    GameSessionUseCaseMixin,
    GameEntryUseCaseMixin,
    RepositoryScopedService[GameRepositoryProtocol],
):
    """게임 room, session, entry 유스케이스를 조합하는 facade service입니다."""

    def __init__(
        self,
        repository: GameRepositoryProtocol | None = None,
        *,
        repository_context_factory: RepositoryContextFactory[GameRepositoryProtocol] | None = None,
        room_membership_policy: RoomMembershipPolicy | None = None,
        participant_policy: SessionParticipantPolicy | None = None,
        credential_policy: SessionCredentialPolicy | None = None,
        initial_turn_policy: SessionInitialTurnPolicy | None = None,
    ) -> None:
        super().__init__(
            repository=repository,
            repository_context_factory=repository_context_factory,
        )
        self.room_membership_policy = room_membership_policy or RoomMembershipPolicy()
        self.participant_policy = participant_policy or SessionParticipantPolicy()
        self.credential_policy = credential_policy or SessionCredentialPolicy()
        self.initial_turn_policy = initial_turn_policy or SessionInitialTurnPolicy()
