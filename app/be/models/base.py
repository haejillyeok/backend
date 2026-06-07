from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """be 서버 ORM 모델이 공유하는 SQLAlchemy declarative base입니다."""
