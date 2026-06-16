from uuid import UUID

from app.be.services.game.errors import (
    GameSessionEntryForbiddenError,
)
from app.be.services.game.records import (
    GameSessionCredential,
    GameSessionEntryResult,
)
from app.shared.core.timezone import kst_now


class GameEntryUseCaseMixin:
    async def authorize_entry(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionEntryResult:
        """로그인 유저가 게임 시작 시 고정된 참가자인지 확인하고 진입 정보를 반환합니다."""
        async with self.repository_scope():
            return await self._authorize_entry(
                game_session_public_id=game_session_public_id,
                user_id=user_id,
            )

    async def _authorize_entry(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionEntryResult:
        """게임 세션 참가자 인증 transaction 안에서 복구 토큰을 발급합니다."""
        participant = await self.repository.get_user_participant_for_session(
            game_session_public_id=game_session_public_id,
            user_id=user_id,
        )
        if participant is None:
            raise GameSessionEntryForbiddenError
        credential = await self._issue_game_session_credential(
            game_session_public_id=game_session_public_id,
            user_id=user_id,
        )
        await self.repository.commit()
        return GameSessionEntryResult(
            game_session_public_id=game_session_public_id,
            participant=participant,
            game_session_token=credential.game_session_token,
            game_session_token_expires_at=credential.expires_at,
        )

    async def authorize_resume_token(self, game_session_token: str) -> GameSessionEntryResult:
        """로그인 세션 만료 후에도 유효한 게임 세션 토큰으로 match 참가자를 복원합니다."""
        async with self.repository_scope():
            return await self._authorize_resume_token(game_session_token)

    async def _authorize_resume_token(self, game_session_token: str) -> GameSessionEntryResult:
        """게임 세션 복구 토큰을 조회해 match 참가자를 복원합니다."""
        participant = await self.repository.get_participant_for_game_session_token(
            token_hash=self.credential_policy.hash_token(game_session_token),
            now=kst_now(),
        )
        if participant is None:
            raise GameSessionEntryForbiddenError
        return GameSessionEntryResult(
            game_session_public_id=participant.game_session_public_id,
            participant=participant,
            game_session_token=game_session_token,
            game_session_token_expires_at=participant.resume_token_expires_at or kst_now(),
        )

    async def _issue_game_session_credential(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionCredential:
        """로그인 세션과 별개로 특정 match 참가자에게만 유효한 복구 토큰을 발급합니다."""
        credential = self.credential_policy.issue()
        await self.repository.save_game_session_token(
            game_session_public_id=game_session_public_id,
            user_id=user_id,
            token_hash=self.credential_policy.hash_token(credential.game_session_token),
            expires_at=credential.expires_at,
        )
        return credential
