from uuid import UUID

from app.be.services.match.repository_protocol import MatchRepositoryProtocol
from app.be.services.match.snapshots import (
    MatchParticipantSnapshot,
    MatchScoreSnapshot,
    MatchSnapshotResult,
)
from app.be.services.repository_scope import RepositoryContextFactory, RepositoryScopedService
from app.shared.core.timezone import kst_now


class MatchService(RepositoryScopedService[MatchRepositoryProtocol]):
    """match WebSocket 연결 직후와 재접속 때 사용할 snapshot을 제공합니다."""

    def __init__(
        self,
        repository: MatchRepositoryProtocol | None = None,
        *,
        repository_context_factory: RepositoryContextFactory[MatchRepositoryProtocol] | None = None,
        now_provider=kst_now,
    ) -> None:
        super().__init__(
            repository=repository,
            repository_context_factory=repository_context_factory,
        )
        self._now_provider = now_provider

    async def get_snapshot(
        self,
        *,
        game_session_public_id: UUID,
        participant_id: UUID,
    ) -> MatchSnapshotResult:
        """참가자 기준으로 익명 처리된 match snapshot을 반환합니다."""
        async with self.repository_scope():
            return await self._get_snapshot(
                game_session_public_id=game_session_public_id,
                participant_id=participant_id,
            )

    async def _get_snapshot(
        self,
        *,
        game_session_public_id: UUID,
        participant_id: UUID,
    ) -> MatchSnapshotResult:
        """snapshot 조회 transaction 안에서 match 화면 상태를 조립합니다."""
        game_session = await self.repository.get_game_session(
            game_session_public_id=game_session_public_id
        )
        if game_session is None:
            return MatchSnapshotResult(
                game_session_public_id=game_session_public_id,
                status="aborted",
                rule_config={},
                participants=[],
                current_round_number=None,
                current_turn=None,
                used_words=[],
                scoreboard=[],
                server_time=self._now_provider(),
            )

        participants = await self.repository.list_participants(game_session_id=game_session.id)
        scores_by_participant_id = await self.repository.list_score_totals(
            game_session_id=game_session.id,
        )
        current_turn = await self.repository.get_current_turn(game_session=game_session)
        used_words = (
            await self.repository.list_used_words_for_round(
                game_session_id=game_session.id,
                round_number=current_turn.round_number,
            )
            if current_turn
            else []
        )
        voting_deadline_at = (
            await self.repository.get_voting_deadline(game_session=game_session)
            if game_session.status == "voting"
            else None
        )
        results = (
            await self.repository.list_results(
                game_session_id=game_session.id,
                participant_id=participant_id,
            )
            if game_session.status == "result"
            else []
        )

        return MatchSnapshotResult(
            game_session_public_id=game_session.public_id,
            status=game_session.status,
            rule_config=game_session.rule_config,
            participants=[
                MatchParticipantSnapshot(
                    display_name=participant.display_name,
                    seat_number=participant.seat_number,
                    is_me=participant.id == participant_id,
                )
                for participant in participants
            ],
            current_round_number=current_turn.round_number if current_turn else None,
            current_turn=current_turn,
            used_words=used_words,
            scoreboard=[
                MatchScoreSnapshot(
                    display_name=participant.display_name,
                    seat_number=participant.seat_number,
                    score=scores_by_participant_id.get(participant.id, 0),
                    is_me=participant.id == participant_id,
                )
                for participant in participants
            ],
            server_time=self._now_provider(),
            voting_deadline_at=voting_deadline_at,
            results=results,
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
