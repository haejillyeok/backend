from app.agent.schemas.request.answer import GameType
from app.agent.services.game_handlers.base import GameHandler
from app.agent.services.game_handlers.chosung import ChosungHandler
from app.agent.services.game_handlers.contains import ContainsHandler
from app.agent.services.game_handlers.word_chain import WordChainHandler


def build_handler_registry() -> dict[GameType, GameHandler]:
    """지원하는 game_type별 handler registry를 생성합니다."""
    return {
        GameType.WORD_CHAIN: WordChainHandler(),
        GameType.CHOSUNG: ChosungHandler(),
        GameType.CONTAINS: ContainsHandler(),
    }
