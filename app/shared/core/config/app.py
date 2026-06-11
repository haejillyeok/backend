import os
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_TIMEZONE = "Asia/Seoul"


class AppSettings(BaseSettings):
    app_name: str
    environment: str | None = Field(default=None, validation_alias="BE_ENV")
    timezone: str = Field(default=DEFAULT_TIMEZONE, validation_alias="APP_TIMEZONE")
    app_version: str = "0.1.0"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def configure_app_timezone(timezone: str = DEFAULT_TIMEZONE) -> None:
    """서버 프로세스의 로컬 타임존을 설정합니다.

    주요 입력은 IANA timezone 이름이며, 기본값은 KST(`Asia/Seoul`)입니다.
    반환값은 없고 `TZ` 환경변수와 C runtime timezone 상태를 갱신하는 부작용이 있습니다.
    """
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone}") from exc

    os.environ["TZ"] = timezone
    if hasattr(time, "tzset"):
        time.tzset()
