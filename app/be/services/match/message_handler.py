from datetime import datetime

from fastapi import WebSocket

from app.be.services.match.connection_manager import MatchConnectionManager, MatchMessage
from app.be.services.match.message_parsing import parse_match_message
from app.be.services.match.ping_handler import handle_ping_message
from app.be.services.match.vote_submit_handler import handle_vote_submit_message
from app.be.services.match.word_submit_handler import handle_word_submit_message
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.be.services.match_vote import MatchVoteService
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


__all__ = ["handle_match_message", "parse_match_message"]


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
    """`/ws/match` WebSocket message type을 command handler로 분기합니다.

    현재 공개 command는 연결 유지 확인용 `ping`, 단어 제출 `word.submit`, AI 지목 투표
    `vote.submit`입니다.
    """
    if message["type"] == "ping":
        return await handle_ping_message(
            manager=manager,
            websocket=websocket,
            message=message,
            now=now,
        )

    if message["type"] == "word.submit":
        return await handle_word_submit_message(
            manager=manager,
            websocket=websocket,
            message=message,
            progress_service=progress_service,
            ai_turn_service=ai_turn_service,
            now=now,
        )

    if message["type"] == "vote.submit":
        return await handle_vote_submit_message(
            manager=manager,
            websocket=websocket,
            message=message,
            vote_service=vote_service,
            now=now,
        )

    raise AppException(
        code=ErrorCode.VALIDATION_ERROR,
        details={"reason": "unsupported_message_type", "type": message["type"]},
    )
