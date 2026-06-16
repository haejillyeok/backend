from datetime import datetime

from app.be.models.game import GameSession, SessionParticipant, SessionPhase, Vote
from app.be.schemas.game_enum import GameSessionStatus
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


class MatchVotePolicy:
    """투표 제출과 timeout 처리에 필요한 순수 게임 규칙을 검증합니다."""

    def ensure_voting_session(self, game_session: GameSession) -> None:
        """게임 세션이 투표 단계인지 확인합니다."""
        if game_session.status != GameSessionStatus.VOTING.value:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "game_session_not_voting"},
            )

    def is_result_session(self, game_session: GameSession) -> bool:
        """이미 결과가 확정된 세션인지 반환합니다."""
        return game_session.status == GameSessionStatus.RESULT.value

    def ensure_voting_deadline_not_exceeded(
        self,
        *,
        voting_phase: SessionPhase | None,
        now: datetime,
    ) -> None:
        """투표 phase deadline 이후 제출된 vote command는 저장하지 않도록 막습니다."""
        if voting_phase is None or voting_phase.deadline_at is None:
            return
        if now >= voting_phase.deadline_at:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "vote_deadline_exceeded"},
            )

    def ensure_user_voter(self, voter: SessionParticipant) -> None:
        """실제 유저 참가자만 투표할 수 있는지 확인합니다."""
        if voter.participant_type != "user":
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "only_user_can_vote"},
            )

    def ensure_vote_not_submitted(
        self,
        *,
        voter: SessionParticipant,
        existing_votes: list[Vote],
    ) -> None:
        """동일 참가자가 한 세션에서 중복 투표하지 않았는지 확인합니다."""
        if any(vote.voter_participant_id == voter.id for vote in existing_votes):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "vote_already_submitted"},
            )

    def count_required_user_votes(self, participants: list[SessionParticipant]) -> int:
        """투표 완료 판단에 필요한 실제 유저 참가자 수를 계산합니다."""
        return len(
            [participant for participant in participants if participant.participant_type == "user"]
        )

    def is_correct_vote(self, target: SessionParticipant) -> bool:
        """AI 참가자를 지목한 투표인지 확인합니다."""
        return target.is_uninvited_guest is True
