from datetime import datetime
from uuid import UUID

from app.be.models.game import GameSession, SessionParticipant, Vote
from app.be.services.match_vote.records import MatchResultParticipantPayload
from app.be.services.match_vote.repository_protocol import MatchVoteRepositoryProtocol
from app.be.services.match_vote.result_policy import MatchVoteResultPolicy
from app.be.services.match_vote.vote_submission_use_cases import (
    MatchVoteSubmissionUseCaseMixin,
)
from app.be.services.match_vote.vote_timeout_use_cases import MatchVoteTimeoutUseCaseMixin
from app.be.services.match_vote.vote_policy import MatchVotePolicy
from app.be.services.repository_scope import RepositoryContextFactory, RepositoryScopedService
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


class MatchVoteService(
    MatchVoteSubmissionUseCaseMixin,
    MatchVoteTimeoutUseCaseMixin,
    RepositoryScopedService[MatchVoteRepositoryProtocol],
):
    """투표 제출과 timeout 유스케이스를 조합하는 facade service입니다."""

    def __init__(
        self,
        repository: MatchVoteRepositoryProtocol | None = None,
        *,
        repository_context_factory: RepositoryContextFactory[MatchVoteRepositoryProtocol]
        | None = None,
        vote_policy: MatchVotePolicy | None = None,
        result_policy: MatchVoteResultPolicy | None = None,
    ) -> None:
        super().__init__(
            repository=repository,
            repository_context_factory=repository_context_factory,
        )
        self.vote_policy = vote_policy or MatchVotePolicy()
        self.result_policy = result_policy or MatchVoteResultPolicy()

    async def publish_results(
        self,
        *,
        game_session: GameSession,
        participants: list[SessionParticipant],
        votes: list[Vote],
        base_scores: dict[UUID, int],
        event_sequence: int,
        now: datetime,
    ) -> list[MatchResultParticipantPayload]:
        """투표 결과 계산과 결과 저장 단계를 repository DB 함수로 조립합니다."""
        participants_by_id = {participant.id: participant for participant in participants}
        participants_by_seat = {
            participant.seat_number: participant for participant in participants
        }
        result_records = self.result_policy.build_result_payloads(
            participants=participants,
            votes=votes,
            base_scores=base_scores,
        )

        for vote in votes:
            voter_delta = 10 if vote.is_correct else -5
            await self.repository.create_vote_score_ledger(
                session_id=game_session.id,
                participant_id=vote.voter_participant_id,
                source_vote_id=vote.id,
                reason="vote_correct" if vote.is_correct else "vote_wrong",
                score_delta=voter_delta,
                now=now,
            )
            target = participants_by_id.get(vote.target_participant_id)
            if target is not None and target.is_uninvited_guest:
                await self.repository.create_vote_score_ledger(
                    session_id=game_session.id,
                    participant_id=target.id,
                    source_vote_id=vote.id,
                    reason="voted_as_ai",
                    score_delta=-5,
                    now=now,
                )

        for result in result_records:
            await self.repository.create_session_result(
                session_id=game_session.id,
                participant=participants_by_seat[result.seat_number],
                result=result,
                now=now,
            )

        await self.repository.mark_game_session_result(game_session=game_session, now=now)
        room = await self.repository.get_room_for_update(game_session.room_id)
        if room is None:
            raise AppException(
                code=ErrorCode.GAME_ROOM_NOT_FOUND,
                details={"reason": "room_not_found"},
            )
        await self.repository.mark_room_waiting(room=room, now=now)
        await self.repository.create_result_published_event(
            session_id=game_session.id,
            event_sequence=event_sequence,
            results=result_records,
            now=now,
        )
        return result_records
