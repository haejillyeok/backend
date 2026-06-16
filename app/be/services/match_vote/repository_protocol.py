from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.be.models.game import (
    GameEvent,
    GameSession,
    ParticipantAction,
    Room,
    ScoreLedger,
    SessionParticipant,
    SessionPhase,
    SessionResult,
    Vote,
)
from app.be.services.match_vote.records import MatchResultParticipantPayload


class MatchVoteRepositoryProtocol(Protocol):
    async def get_game_session_for_update(self, public_id: UUID) -> GameSession:
        """투표 처리 기준 game session row를 잠그고 조회합니다."""

    async def get_room_for_update(self, room_id: UUID) -> Room:
        """결과 확정 후 room 상태 변경 대상 row를 잠그고 조회합니다."""

    async def get_voting_phase(self, *, game_session: GameSession) -> SessionPhase | None:
        """현재 voting phase row를 조회합니다."""

    async def get_participant(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
    ) -> SessionParticipant:
        """세션 안의 참가자를 참가자 id로 조회합니다."""

    async def get_participant_by_seat_number(
        self,
        *,
        session_id: UUID,
        seat_number: int,
    ) -> SessionParticipant:
        """세션 안의 참가자를 좌석 번호로 조회합니다."""

    async def list_participants(self, session_id: UUID) -> list[SessionParticipant]:
        """세션 참가자 목록을 조회합니다."""

    async def list_votes(self, session_id: UUID) -> list[Vote]:
        """세션 vote row 목록을 조회합니다."""

    async def get_score_totals(self, session_id: UUID) -> dict[UUID, int]:
        """참가자별 누적 점수를 조회합니다."""

    async def get_next_action_number(self, session_id: UUID) -> int:
        """다음 participant action 번호를 조회합니다."""

    async def get_next_event_sequence(self, session_id: UUID) -> int:
        """다음 game event sequence를 조회합니다."""

    async def create_vote_submit_action(
        self,
        *,
        session_id: UUID,
        voter: SessionParticipant,
        target: SessionParticipant,
        action_number: int,
        now: datetime,
    ) -> ParticipantAction:
        """투표 제출 action row 하나를 추가합니다."""

    async def create_vote(
        self,
        *,
        session_id: UUID,
        voter: SessionParticipant,
        target: SessionParticipant,
        is_correct: bool,
        now: datetime,
    ) -> Vote:
        """투표 선택 row 하나를 추가합니다."""

    async def create_vote_accepted_event(
        self,
        *,
        session_id: UUID,
        voter: SessionParticipant,
        action: ParticipantAction,
        event_sequence: int,
        submitted_vote_count: int,
        required_vote_count: int,
        now: datetime,
    ) -> GameEvent:
        """투표 접수 event row 하나를 추가합니다."""

    async def create_vote_timeout_event(
        self,
        *,
        session_id: UUID,
        event_sequence: int,
        submitted_vote_count: int,
        required_vote_count: int,
        now: datetime,
    ) -> GameEvent:
        """투표 timeout event row 하나를 추가합니다."""

    async def create_vote_score_ledger(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
        source_vote_id: UUID,
        reason: str,
        score_delta: int,
        now: datetime,
    ) -> ScoreLedger:
        """투표 결과 점수 ledger row 하나를 추가합니다."""

    async def create_session_result(
        self,
        *,
        session_id: UUID,
        participant: SessionParticipant,
        result: MatchResultParticipantPayload,
        now: datetime,
    ) -> SessionResult:
        """참가자 최종 결과 row 하나를 추가합니다."""

    async def mark_game_session_result(
        self,
        *,
        game_session: GameSession,
        now: datetime,
    ) -> None:
        """게임 세션 row 하나를 결과 상태로 변경합니다."""

    async def mark_room_waiting(self, *, room: Room, now: datetime) -> None:
        """room row 하나를 대기 상태로 변경합니다."""

    async def create_result_published_event(
        self,
        *,
        session_id: UUID,
        event_sequence: int,
        results: list[MatchResultParticipantPayload],
        now: datetime,
    ) -> GameEvent:
        """결과 발표 event row 하나를 추가합니다."""

    async def flush(self) -> None:
        """pending DB 변경을 반영합니다."""

    async def commit(self) -> None:
        """투표 상태 변경 transaction을 확정합니다."""
