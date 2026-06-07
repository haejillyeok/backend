# Database Migrations

이 디렉터리는 Alembic DB schema migration을 관리합니다.

- `env.py`: DB 설정과 SQLAlchemy metadata를 Alembic에 연결합니다.
- `versions/`: Git으로 형상관리하는 migration revision 파일을 둡니다.

새 ORM 모델을 만들면 `app.be.models.base.Base`를 상속하고,
revision 생성 전 모델 모듈이 `migrations/env.py`에서 import되도록 연결합니다.
