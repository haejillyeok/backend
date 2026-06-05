from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.dependencies.database import get_db_session
from app.be.repository.auth import AuthRepository
from app.be.services.auth import AuthService


def get_auth_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthService:
    """요청 단위 DB session으로 인증 service를 생성합니다."""
    return AuthService(AuthRepository(db_session))
