from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.be.models.game import (
    GameEvent,
    GameSession,
    ParticipantAction,
    ScoreLedger,
    SessionParticipant,
    SessionPhase,
    UsedWord,
    ValidWord,
    WordSubmission,
    WordTurn,
)


class MatchProgressRepositoryProtocol(Protocol):
    async def get_game_session(self, game_session_public_id: UUID) -> GameSession | None:
        """게임 진행 기준 game session row를 조회합니다."""

    async def get_phase(self, *, session_id: UUID, phase_id: UUID) -> SessionPhase | None:
        """게임 진행 phase row를 잠그고 조회합니다."""

    async def get_turn_actor(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
    ) -> tuple[WordTurn, SessionParticipant] | None:
        """현재 단어 턴과 담당 참가자를 조회합니다."""

    async def get_participant(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
    ) -> SessionParticipant | None:
        """세션 내 참가자 row 하나를 조회합니다."""

    async def get_valid_word(self, *, game_type: str, normalized_word: str) -> ValidWord | None:
        """활성 사전 단어 row를 조회합니다."""

    async def get_used_word(
        self,
        *,
        session_id: UUID,
        round_number: int,
        normalized_word: str,
    ) -> UsedWord | None:
        """현재 라운드에서 이미 사용한 단어 row를 조회합니다."""

    async def get_random_round_start_char(self, game_type: str) -> str | None:
        """활성 유효 단어셋에서 다음 라운드 시작 글자 후보 하나를 무작위로 조회합니다."""

    async def list_participants(self, session_id: UUID) -> list[SessionParticipant]:
        """세션 참가자 목록을 좌석 번호 순으로 조회합니다."""

    async def get_next_action_number(self, session_id: UUID) -> int:
        """다음 participant action 번호를 조회합니다."""

    async def get_next_event_sequence(self, session_id: UUID) -> int:
        """다음 game event sequence를 조회합니다."""

    async def create_word_submit_action(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        action_number: int,
        normalized_word: str,
        now: datetime,
    ) -> ParticipantAction:
        """단어 제출 action row 하나를 session에 추가합니다."""

    async def create_ai_answer_failed_action(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        action_number: int,
        reason: str,
        details: dict[str, Any],
        response_ms: int | None,
        now: datetime,
    ) -> ParticipantAction:
        """AI 응답 실패 action row 하나를 session에 추가합니다."""

    async def create_turn_timeout_action(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action_number: int,
        now: datetime,
    ) -> ParticipantAction:
        """턴 deadline 초과 action row 하나를 session에 추가합니다."""

    async def create_word_reject_action(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        action_number: int,
        normalized_word: str,
        reason: str,
        details: dict[str, Any],
        now: datetime,
    ) -> ParticipantAction:
        """거절된 단어 제출 action row 하나를 session에 추가합니다."""

    async def create_word_submission(
        self,
        *,
        action_id: UUID,
        turn_id: UUID,
        normalized_word: str,
    ) -> WordSubmission:
        """단어 제출 상세 row 하나를 session에 추가합니다."""

    async def create_used_word(
        self,
        *,
        session_id: UUID,
        submission_id: UUID,
        round_number: int,
        normalized_word: str,
    ) -> UsedWord:
        """라운드 내 중복 방지용 used word row 하나를 session에 추가합니다."""

    async def create_word_submission_score(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
        submission_id: UUID,
        score_delta: int,
        now: datetime,
    ) -> ScoreLedger:
        """승인된 단어 제출 점수 ledger row 하나를 session에 추가합니다."""

    async def create_word_rejection_score(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
        action_id: UUID,
        reason: str,
        score_delta: int,
        now: datetime,
    ) -> ScoreLedger:
        """거절된 단어 제출 점수 ledger row 하나를 session에 추가합니다."""

    async def create_session_phase(self, phase: SessionPhase) -> SessionPhase:
        """다음 phase row 하나를 session에 추가합니다."""

    async def mark_phase_success(self, *, phase: SessionPhase, now: datetime) -> None:
        """현재 phase row 하나를 성공 종료 상태로 변경합니다."""

    async def mark_phase_timeout(self, *, phase: SessionPhase, now: datetime) -> None:
        """현재 phase row 하나를 timeout 종료 상태로 변경합니다."""

    async def mark_game_session_playing(
        self,
        *,
        game_session: GameSession,
        current_phase_id: UUID,
    ) -> None:
        """game session row 하나의 진행 상태와 현재 phase를 변경합니다."""

    async def mark_game_session_voting(
        self,
        *,
        game_session: GameSession,
        current_phase_id: UUID,
    ) -> None:
        """game session row 하나를 투표 상태와 현재 phase로 변경합니다."""

    async def create_word_turn(self, turn: WordTurn) -> WordTurn:
        """다음 word turn row 하나를 session에 추가합니다."""

    async def create_word_accepted_event(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action: ParticipantAction,
        event_sequence: int,
        payload: dict[str, object],
        now: datetime,
    ) -> GameEvent:
        """단어 승인 event row 하나를 session에 추가합니다."""

    async def create_ai_answer_failed_event(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action_id: UUID,
        event_sequence: int,
        payload: dict[str, object],
        now: datetime,
    ) -> GameEvent:
        """AI 응답 실패 event row 하나를 session에 추가합니다."""

    async def create_turn_timeout_event(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action: ParticipantAction,
        event_sequence: int,
        round_number: int,
        payload: dict[str, object],
        now: datetime,
    ) -> GameEvent:
        """턴 timeout event row 하나를 session에 추가합니다."""

    async def create_word_rejected_event(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action_id: UUID,
        event_sequence: int,
        payload: dict[str, object],
        now: datetime,
    ) -> GameEvent:
        """단어 거절 event row 하나를 session에 추가합니다."""

    async def flush(self) -> None:
        """현재 session의 pending 변경을 DB에 반영해 row id와 제약을 확정합니다."""

    async def commit(self) -> None:
        """진행 상태 변경 transaction을 확정합니다."""
