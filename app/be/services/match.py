from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocketDisconnect

from app.be.services.game import GameSessionParticipantRecord
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.be.services.match_vote import MatchVoteService
from app.be.services.realtime import parse_realtime_message
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException
from app.shared.core.timezone import kst_now, to_kst_isoformat


MatchMessage = dict[str, Any]
WORD_REJECTION_REASONS = {
    "word_already_used",
    "word_not_in_dictionary",
    "word_start_char_mismatch",
}


@dataclass(frozen=True)
class MatchParticipantSnapshot:
    display_name: str
    seat_number: int
    is_me: bool


@dataclass(frozen=True)
class MatchTurnSnapshot:
    phase_id: UUID
    round_number: int
    turn_number: int
    actor_seat_number: int
    deadline_at: datetime | None
    required_start_char: str | None


@dataclass(frozen=True)
class MatchTurnTimer:
    phase_id: UUID
    deadline_at: datetime


@dataclass(frozen=True)
class MatchVotingTimer:
    deadline_at: datetime


MatchTimer = MatchTurnTimer | MatchVotingTimer


@dataclass(frozen=True)
class MatchScoreSnapshot:
    display_name: str
    seat_number: int
    score: int
    is_me: bool


@dataclass(frozen=True)
class MatchResultSnapshot:
    display_name: str
    seat_number: int
    revealed_participant_type: str
    final_score: int
    rank: int
    is_winner: bool
    vote_score_delta: int
    is_me: bool


@dataclass(frozen=True)
class MatchSnapshotResult:
    game_session_public_id: UUID
    status: str
    rule_config: dict[str, int]
    participants: list[MatchParticipantSnapshot]
    current_round_number: int | None
    current_turn: MatchTurnSnapshot | None
    used_words: list[str]
    scoreboard: list[MatchScoreSnapshot]
    server_time: datetime
    voting_deadline_at: datetime | None = None
    results: list[MatchResultSnapshot] = field(default_factory=list)


@dataclass(frozen=True)
class MatchConnection:
    game_session_public_id: UUID
    participant_id: UUID
    participant: GameSessionParticipantRecord


class MatchRepositoryProtocol(Protocol):
    async def get_snapshot(
        self,
        *,
        game_session_public_id: UUID,
        participant_id: UUID,
    ) -> MatchSnapshotResult:
        """현재 match 화면 복구에 필요한 익명 snapshot을 조회합니다."""


class MatchService:
    """match WebSocket 연결 직후와 재접속 때 사용할 snapshot을 제공합니다."""

    def __init__(self, repository: MatchRepositoryProtocol) -> None:
        self.repository = repository

    async def get_snapshot(
        self,
        *,
        game_session_public_id: UUID,
        participant_id: UUID,
    ) -> MatchSnapshotResult:
        """참가자 기준으로 익명 처리된 match snapshot을 반환합니다."""
        return await self.repository.get_snapshot(
            game_session_public_id=game_session_public_id,
            participant_id=participant_id,
        )


class EmptyMatchRepository:
    """match 진행 구현 전까지 최소 snapshot을 제공하는 repository입니다.

    실제 턴/점수/단어 기록 조회는 다음 구현 단위에서 DB 기반 repository로 대체합니다.
    """

    async def get_snapshot(
        self,
        *,
        game_session_public_id: UUID,
        participant_id: UUID,
    ) -> MatchSnapshotResult:
        return MatchSnapshotResult(
            game_session_public_id=game_session_public_id,
            status="starting",
            rule_config={},
            participants=[],
            current_round_number=None,
            current_turn=None,
            used_words=[],
            scoreboard=[],
            server_time=kst_now(),
        )


class MatchConnectionManager:
    """match WebSocket 연결과 세션별 구독 registry를 관리합니다.

    연결 identity는 `game_session_public_id + participant_id`로 고정합니다. DB의 match 상태가 최종
    사실이고, manager는 process-local 연결만 보관합니다.
    """

    def __init__(self) -> None:
        self._connections: dict[WebSocket, MatchConnection] = {}
        self._session_subscriptions: dict[UUID, set[WebSocket]] = {}

    @property
    def connection_count(self) -> int:
        """현재 match manager에 등록된 active WebSocket 연결 수를 반환합니다."""
        return len(self._connections)

    async def connect(
        self,
        websocket: WebSocket,
        *,
        game_session_public_id: UUID,
        participant_id: UUID,
        participant: GameSessionParticipantRecord,
    ) -> None:
        """인증된 match WebSocket 연결을 수락하고 세션 구독자로 등록합니다."""
        await websocket.accept()
        self._connections[websocket] = MatchConnection(
            game_session_public_id=game_session_public_id,
            participant_id=participant_id,
            participant=participant,
        )
        self._session_subscriptions.setdefault(game_session_public_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """match WebSocket 연결을 registry에서 제거합니다."""
        connection = self._connections.pop(websocket, None)
        if connection is None:
            return
        subscribers = self._session_subscriptions.get(connection.game_session_public_id)
        if subscribers is not None:
            subscribers.discard(websocket)
            if not subscribers:
                self._session_subscriptions.pop(connection.game_session_public_id, None)

    async def send(self, websocket: WebSocket, message: MatchMessage) -> None:
        """특정 match WebSocket 연결로 JSON envelope 메시지를 전송합니다."""
        await websocket.send_json(jsonable_encoder(message))

    def get_connection(self, websocket: WebSocket) -> MatchConnection | None:
        """WebSocket에 고정된 match 참가자 identity를 반환합니다."""
        return self._connections.get(websocket)

    async def send_error_and_close(self, websocket: WebSocket, error: AppException) -> None:
        """오류 envelope를 전송한 뒤 error definition의 WebSocket close code로 연결을 닫습니다."""
        await self.send(websocket, {"type": "error", "payload": error.to_error_payload()})
        await websocket.close(code=error.websocket_close_code)

    async def send_connected(self, websocket: WebSocket) -> None:
        """연결 직후 클라이언트가 본인 참가자 순서를 확인할 수 있는 event를 보냅니다."""
        connection = self._connections[websocket]
        await self.send(
            websocket,
            {
                "type": "match.connected",
                "payload": {
                    "game_session_public_id": connection.game_session_public_id,
                    "participant": {
                        "display_name": connection.participant.display_name,
                        "seat_number": connection.participant.seat_number,
                    },
                },
            },
        )

    async def send_snapshot(
        self,
        websocket: WebSocket,
        snapshot: MatchSnapshotResult,
    ) -> None:
        """연결 직후 또는 재접속 시 현재 match 화면 복구 snapshot을 보냅니다."""
        await self.send(
            websocket,
            {
                "type": "match.snapshot",
                "payload": {
                    "game_session_public_id": snapshot.game_session_public_id,
                    "status": snapshot.status,
                    "rule_config": snapshot.rule_config,
                    "participants": [
                        {
                            "display_name": participant.display_name,
                            "seat_number": participant.seat_number,
                            "is_me": participant.is_me,
                        }
                        for participant in snapshot.participants
                    ],
                    "current_round_number": snapshot.current_round_number,
                    "current_turn": (
                        {
                            "phase_id": snapshot.current_turn.phase_id,
                            "round_number": snapshot.current_turn.round_number,
                            "turn_number": snapshot.current_turn.turn_number,
                            "actor_seat_number": snapshot.current_turn.actor_seat_number,
                            "deadline_at": (
                                to_kst_isoformat(snapshot.current_turn.deadline_at)
                                if snapshot.current_turn.deadline_at
                                else None
                            ),
                            "required_start_char": snapshot.current_turn.required_start_char,
                        }
                        if snapshot.current_turn
                        else None
                    ),
                    "used_words": snapshot.used_words,
                    "scoreboard": [
                        {
                            "display_name": score.display_name,
                            "seat_number": score.seat_number,
                            "score": score.score,
                            "is_me": score.is_me,
                        }
                        for score in snapshot.scoreboard
                    ],
                    "server_time": to_kst_isoformat(snapshot.server_time),
                    "voting_deadline_at": (
                        to_kst_isoformat(snapshot.voting_deadline_at)
                        if snapshot.voting_deadline_at
                        else None
                    ),
                    "results": [
                        {
                            "participant": {
                                "display_name": result.display_name,
                                "seat_number": result.seat_number,
                                "revealed_participant_type": result.revealed_participant_type,
                            },
                            "final_score": result.final_score,
                            "rank": result.rank,
                            "is_winner": result.is_winner,
                            "vote_score_delta": result.vote_score_delta,
                            "is_me": result.is_me,
                        }
                        for result in snapshot.results
                    ],
                },
            },
        )

    async def broadcast_session(self, game_session_public_id: UUID, message: MatchMessage) -> None:
        """특정 game session에 연결된 모든 match WebSocket에 event를 전송합니다."""
        for websocket in list(self._session_subscriptions.get(game_session_public_id, set())):
            try:
                await self.send(websocket, message)
            except (RuntimeError, WebSocketDisconnect):
                self.disconnect(websocket)


match_connection_manager = MatchConnectionManager()


def parse_match_message(raw_message: str) -> MatchMessage:
    """WebSocket text frame을 match JSON envelope로 파싱하고 검증합니다."""
    return parse_realtime_message(raw_message)


async def handle_match_message(
    *,
    manager: MatchConnectionManager,
    websocket: WebSocket,
    message: MatchMessage,
    progress_service: MatchProgressService,
    vote_service: MatchVoteService,
    ai_turn_service: MatchAiTurnService | None,
    now: datetime,
) -> list[MatchMessage]:
    """`/ws/match` WebSocket message type을 처리합니다.

    현재 구현된 공개 command는 연결 유지 확인용 `ping`입니다. 단어 제출과 투표 command는 이후
    match 진행 service가 준비되면 같은 handler에 추가합니다.
    """
    if message["type"] == "ping":
        await manager.send(websocket, {"type": "match.pong", "payload": message["payload"]})
        return []

    if message["type"] == "word.submit":
        connection = manager.get_connection(websocket)
        if connection is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "match_connection_missing"},
            )
        payload = message["payload"]
        phase_id = _parse_phase_id(payload.get("phase_id"))
        word = payload.get("word")
        if not isinstance(word, str):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "word_required"},
            )
        try:
            event = await progress_service.submit_word(
                game_session_public_id=connection.game_session_public_id,
                phase_id=phase_id,
                participant_id=connection.participant_id,
                word=word,
                now=now,
            )
        except AppException as exc:
            if _is_turn_deadline_exception(exc):
                timeout_event = await progress_service.timeout_turn_if_due(
                    game_session_public_id=connection.game_session_public_id,
                    phase_id=phase_id,
                    now=now,
                )
                if timeout_event is None:
                    return []
                await manager.broadcast_session(
                    timeout_event.game_session_public_id, timeout_event.message
                )
                broadcast_messages = [timeout_event.message]
                if ai_turn_service is not None:
                    next_phase_id = _extract_next_turn_phase_id(timeout_event.message)
                    if next_phase_id is not None:
                        ai_event = await ai_turn_service.play_ai_turn(
                            game_session_public_id=timeout_event.game_session_public_id,
                            phase_id=next_phase_id,
                            now=now,
                        )
                        if ai_event is not None:
                            await manager.broadcast_session(
                                ai_event.game_session_public_id, ai_event.message
                            )
                            broadcast_messages.append(ai_event.message)
                return broadcast_messages
            rejection = _word_rejection_from_exception(exc)
            if rejection is None:
                raise
            reason, details = rejection
            event = await progress_service.reject_word(
                game_session_public_id=connection.game_session_public_id,
                phase_id=phase_id,
                participant_id=connection.participant_id,
                word=word,
                reason=reason,
                details=details,
                now=now,
            )
            await manager.broadcast_session(event.game_session_public_id, event.message)
            return [event.message]
        await manager.broadcast_session(event.game_session_public_id, event.message)
        broadcast_messages = [event.message]
        if ai_turn_service is not None:
            next_phase_id = _extract_next_turn_phase_id(event.message)
            if next_phase_id is not None:
                ai_event = await ai_turn_service.play_ai_turn(
                    game_session_public_id=event.game_session_public_id,
                    phase_id=next_phase_id,
                    now=now,
                )
                if ai_event is not None:
                    await manager.broadcast_session(
                        ai_event.game_session_public_id, ai_event.message
                    )
                    broadcast_messages.append(ai_event.message)
        return broadcast_messages

    if message["type"] == "vote.submit":
        connection = manager.get_connection(websocket)
        if connection is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "match_connection_missing"},
            )
        target_seat_number = _parse_target_seat_number(message["payload"].get("target_seat_number"))
        try:
            events = await vote_service.submit_vote(
                game_session_public_id=connection.game_session_public_id,
                voter_participant_id=connection.participant_id,
                target_seat_number=target_seat_number,
                now=now,
            )
        except AppException as exc:
            if not _is_vote_deadline_exception(exc):
                raise
            events = await vote_service.timeout_vote(
                game_session_public_id=connection.game_session_public_id,
                now=now,
            )
        for event in events:
            await manager.broadcast_session(event.game_session_public_id, event.message)
        return [event.message for event in events]

    raise AppException(
        code=ErrorCode.VALIDATION_ERROR,
        details={"reason": "unsupported_message_type", "type": message["type"]},
    )


def current_turn_timer_from_snapshot(snapshot: MatchSnapshotResult) -> MatchTurnTimer | None:
    """match snapshot의 현재 턴 deadline을 WebSocket receive 대기 기준으로 변환합니다."""
    if snapshot.current_turn is None or snapshot.current_turn.deadline_at is None:
        return None
    return MatchTurnTimer(
        phase_id=snapshot.current_turn.phase_id,
        deadline_at=snapshot.current_turn.deadline_at,
    )


def current_match_timer_from_snapshot(snapshot: MatchSnapshotResult) -> MatchTimer | None:
    """snapshot의 현재 진행 상태를 WebSocket receive 대기 timer로 변환합니다."""
    turn_timer = current_turn_timer_from_snapshot(snapshot)
    if turn_timer is not None:
        return turn_timer
    if snapshot.voting_deadline_at is not None:
        return MatchVotingTimer(deadline_at=snapshot.voting_deadline_at)
    return None


def seconds_until_match_wait_timeout(
    timer: MatchTimer | None,
    *,
    now: datetime,
    heartbeat_seconds: int = 45,
) -> float:
    """heartbeat와 현재 진행 deadline 중 더 이른 시점까지 기다릴 초를 계산합니다."""
    if timer is None:
        return float(heartbeat_seconds)
    seconds_until_deadline = (timer.deadline_at - now).total_seconds()
    return max(0.0, min(float(heartbeat_seconds), seconds_until_deadline))


async def process_match_turn_timeout(
    *,
    manager: MatchConnectionManager,
    progress_service: MatchProgressService,
    ai_turn_service: MatchAiTurnService | None,
    game_session_public_id: UUID,
    phase_id: UUID,
    now: datetime,
) -> MatchTimer | None:
    """현재 턴 timeout을 확정하고 broadcast한 뒤 다음 턴 timer를 반환합니다."""
    event = await progress_service.timeout_turn_if_due(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )
    if event is None:
        return None
    await manager.broadcast_session(event.game_session_public_id, event.message)
    next_timer = next_match_timer_from_message(event.message)
    if ai_turn_service is not None and next_timer is not None:
        ai_event = await ai_turn_service.play_ai_turn(
            game_session_public_id=event.game_session_public_id,
            phase_id=next_timer.phase_id,
            now=now,
        )
        if ai_event is not None:
            await manager.broadcast_session(ai_event.game_session_public_id, ai_event.message)
            return next_match_timer_from_message(ai_event.message)
    return next_timer


async def process_match_vote_timeout(
    *,
    manager: MatchConnectionManager,
    vote_service: MatchVoteService,
    game_session_public_id: UUID,
    now: datetime,
) -> None:
    """투표 timeout을 확정하고 반환된 event들을 broadcast합니다."""
    events = await vote_service.timeout_vote(
        game_session_public_id=game_session_public_id,
        now=now,
    )
    for event in events:
        await manager.broadcast_session(event.game_session_public_id, event.message)
    return None


def next_match_timer_from_message(message: MatchMessage) -> MatchTimer | None:
    """진행 event payload에서 다음 턴 또는 투표 deadline timer를 추출합니다."""
    next_turn_timer = next_turn_timer_from_message(message)
    if next_turn_timer is not None:
        return next_turn_timer
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    voting_deadline_at = _parse_optional_datetime(payload.get("voting_deadline_at"))
    if voting_deadline_at is None:
        return None
    return MatchVotingTimer(deadline_at=voting_deadline_at)


def next_turn_timer_from_message(message: MatchMessage) -> MatchTurnTimer | None:
    """진행 event의 `next_turn` payload를 다음 timeout timer로 변환합니다."""
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    next_turn = payload.get("next_turn")
    if not isinstance(next_turn, dict):
        return None

    phase_id = _parse_optional_uuid(next_turn.get("phase_id"))
    deadline_at = _parse_optional_datetime(next_turn.get("deadline_at"))
    if phase_id is None or deadline_at is None:
        return None
    return MatchTurnTimer(phase_id=phase_id, deadline_at=deadline_at)


def _parse_phase_id(value: Any) -> UUID:
    """client payload의 phase_id 문자열을 UUID로 검증합니다."""
    if not isinstance(value, str):
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "phase_id_required"},
        )
    try:
        return UUID(value)
    except ValueError as exc:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "phase_id_invalid"},
        ) from exc


def _parse_target_seat_number(value: Any) -> int:
    """투표 대상 공개 순서 번호를 검증합니다."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "target_seat_number_invalid"},
        )
    return value


def _extract_next_turn_phase_id(message: MatchMessage) -> UUID | None:
    """진행 event payload에서 다음 턴 phase_id를 추출합니다."""
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    next_turn = payload.get("next_turn")
    if not isinstance(next_turn, dict):
        return None
    phase_id = next_turn.get("phase_id")
    if isinstance(phase_id, UUID):
        return phase_id
    if isinstance(phase_id, str):
        try:
            return UUID(phase_id)
        except ValueError:
            return None
    return None


def _word_rejection_from_exception(exc: AppException) -> tuple[str, dict[str, Any]] | None:
    """게임 규칙 위반 AppException을 단어 제출 거절 event 입력으로 변환합니다."""
    if exc.code != ErrorCode.VALIDATION_ERROR or not isinstance(exc.details, dict):
        return None
    reason = exc.details.get("reason")
    if not isinstance(reason, str) or reason not in WORD_REJECTION_REASONS:
        return None
    return reason, {key: value for key, value in exc.details.items() if key != "reason"}


def _is_turn_deadline_exception(exc: AppException) -> bool:
    """deadline 이후 제출 예외인지 확인해 timeout 확정 경로로 보낼지 판단합니다."""
    return (
        exc.code == ErrorCode.VALIDATION_ERROR
        and isinstance(exc.details, dict)
        and exc.details.get("reason") == "turn_deadline_exceeded"
    )


def _is_vote_deadline_exception(exc: AppException) -> bool:
    """deadline 이후 투표 제출 예외인지 확인해 투표 timeout 확정 경로로 보낼지 판단합니다."""
    return (
        exc.code == ErrorCode.VALIDATION_ERROR
        and isinstance(exc.details, dict)
        and exc.details.get("reason") == "vote_deadline_exceeded"
    )


def _parse_optional_uuid(value: Any) -> UUID | None:
    """UUID 또는 UUID 문자열을 선택적으로 파싱합니다."""
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _parse_optional_datetime(value: Any) -> datetime | None:
    """datetime 또는 ISO 문자열을 선택적으로 파싱합니다."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
