from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.be.models.game import GameSession, Room, SessionParticipant, SessionPhase, WordTurn
from app.be.services.game.records import (
    GameRoomListItem,
    GameRoomRecord,
    GameSessionParticipantRecord,
    GameSessionTurnRecord,
    RoomLeaveResult,
    RoomMemberRecord,
    RoomUpdateResult,
)


class GameRepositoryProtocol(Protocol):
    async def list_rooms(self, *, user_id: UUID) -> list[GameRoomListItem]:
        """로비 목록과 현재 유저의 활성 room membership 여부를 조회합니다."""

    async def lock_waiting_room_membership_for_user(self, *, user_id: UUID) -> None:
        """한 유저의 대기 room membership 변경을 transaction 안에서 직렬화합니다."""

    async def list_active_waiting_room_public_ids_for_user(self, *, user_id: UUID) -> list[UUID]:
        """유저가 현재 active member로 남아 있는 대기 room public_id 목록을 조회합니다."""

    async def list_active_room_public_ids_for_user(self, *, user_id: UUID) -> list[UUID]:
        """유저가 현재 active member로 남아 있는 닫히지 않은 room public_id 목록을 조회합니다."""

    async def create_room(
        self,
        *,
        owner_user_id: UUID,
        name: str,
        game_type: str,
        status: str,
        max_players: int,
    ) -> GameRoomRecord:
        """대기 상태 room을 생성하고 service record로 변환합니다."""

    async def get_oldest_joinable_waiting_room_for_update(
        self,
        *,
        user_id: UUID,
    ) -> GameRoomRecord | None:
        """빠른입장 대상이 될 가장 오래된 참여 가능 대기 room을 잠그고 조회합니다."""

    async def get_room_by_public_id(self, room_public_id: UUID) -> GameRoomRecord | None:
        """WebSocket 로비 연결 권한 확인용으로 room을 lock 없이 조회합니다."""

    async def get_room_by_public_id_for_update(self, room_public_id: UUID) -> GameRoomRecord | None:
        """게임 시작 transaction 동안 room row를 잠그고 시작 정보를 조회합니다."""

    async def get_active_game_session_for_room(
        self,
        room_id: UUID,
    ) -> tuple[GameSession, Room] | None:
        """room의 최신 active game_session row와 room row를 조회합니다."""

    async def list_session_participants(
        self,
        *,
        game_session_id: UUID,
        game_session_public_id: UUID,
    ) -> list[GameSessionParticipantRecord]:
        """game_session에 고정된 참가자 snapshot을 seat 순서로 조회합니다."""

    async def get_current_word_turn(
        self,
        *,
        game_session: GameSession,
    ) -> GameSessionTurnRecord | None:
        """game_session의 현재 단어 턴 정보를 조회합니다."""

    async def list_active_room_members(self, room_id: UUID) -> list[RoomMemberRecord]:
        """게임 시작 시 참가자로 고정할 활성 room member를 입장 순서대로 조회합니다."""

    async def get_active_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
    ) -> RoomMemberRecord | None:
        """유저가 현재 room에 활성 멤버로 참여 중인지 조회합니다."""

    async def create_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        nickname: str,
    ) -> RoomMemberRecord:
        """유저를 room의 활성 멤버로 추가합니다."""

    async def mark_room_member_left(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        left_at: datetime,
    ) -> RoomLeaveResult | None:
        """활성 room member의 퇴장 시각을 기록하고 없으면 None을 반환합니다."""

    async def transfer_room_owner(self, *, room_id: UUID, owner_user_id: UUID) -> None:
        """활성 멤버가 남아 있는 room의 방장을 새 유저로 승계합니다."""

    async def close_room(self, *, room_id: UUID, closed_at: datetime) -> None:
        """활성 멤버가 없는 room을 더 이상 사용할 수 없도록 닫습니다."""

    async def abort_active_session_for_room(self, *, room_id: UUID, ended_at: datetime) -> None:
        """room의 active 게임 세션을 중단 상태로 닫습니다."""

    async def update_room_settings(
        self,
        *,
        room_id: UUID,
        name: str,
        max_players: int,
        rule_config: dict[str, int],
    ) -> RoomUpdateResult:
        """대기 room의 표시 정보와 게임 시작 전 룰 설정을 갱신합니다."""

    async def create_game_session_row(
        self,
        *,
        room_id: UUID,
        game_session_public_id: UUID,
        game_type: str,
        status: str,
        rule_config: dict[str, int],
        started_at: datetime,
    ) -> GameSession:
        """game_sessions row 하나를 추가합니다."""

    async def create_session_participant_row(
        self,
        *,
        game_session_id: UUID,
        participant: GameSessionParticipantRecord,
    ) -> SessionParticipant:
        """session_participants row 하나를 추가합니다."""

    async def mark_room_status(
        self,
        *,
        room_id: UUID,
        status: str,
        updated_at: datetime,
    ) -> None:
        """room status 하나를 변경합니다."""

    async def get_random_round_start_char(self, *, game_type: str) -> str | None:
        """첫 끝말잇기 턴 시작 글자 후보를 하나 조회합니다."""

    async def create_session_phase_row(
        self,
        *,
        session_id: UUID,
        phase_type: str,
        phase_number: int,
        actor_participant_id: UUID,
        condition_payload: dict,
        time_limit_seconds: int,
        started_at: datetime,
        deadline_at: datetime,
    ) -> SessionPhase:
        """session_phases row 하나를 추가합니다."""

    async def create_word_turn_row(
        self,
        *,
        phase_id: UUID,
        participant_id: UUID,
        round_number: int,
        turn_number: int,
        condition_payload: dict,
    ) -> WordTurn:
        """word_game.turns row 하나를 추가합니다."""

    async def mark_game_session_current_phase(
        self,
        *,
        game_session: GameSession,
        current_phase_id: UUID,
    ) -> None:
        """game_session의 current_phase_id를 변경합니다."""

    async def get_user_participant_for_session(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionParticipantRecord | None:
        """로그인 유저가 해당 게임 세션 참가자인지 조회합니다."""

    async def get_participant_for_game_session_token(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> GameSessionParticipantRecord | None:
        """유효한 게임 세션 토큰 해시로 match 참가자를 조회합니다."""

    async def save_game_session_token(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        """게임 참가자의 match 복구 토큰 해시와 만료 시각을 저장합니다."""

    async def commit(self) -> None:
        """게임 시작 transaction을 확정합니다."""
