import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict


class EndpointSettings(BaseModel):
    """서버 endpoint의 앱 이름, host, port와 bind address를 보관합니다."""

    app_name: str
    host: str
    port: int

    model_config = ConfigDict(frozen=True)

    @property
    def bind_address(self) -> str:
        return f"{self.host}:{self.port}"


def format_service_env_prefix(app_name: str) -> str:
    """앱 이름에서 서비스별 환경변수 prefix를 만듭니다."""
    service_name = app_name.rsplit("-", maxsplit=1)[-1]
    return service_name.upper().replace("-", "_")


def load_endpoint_port_value(
    env_prefix: str,
    env_file: str | Path = ".env",
    *,
    default_port: int | None = None,
) -> str:
    """OS 환경변수, `.env`, 기본값 순서로 endpoint port를 읽습니다."""
    dotenv = dotenv_values(env_file)
    port_key = f"{env_prefix}_PORT"

    port = os.environ.get(port_key) or dotenv.get(port_key)
    if port is None and default_port is not None:
        port = str(default_port)

    if not port:
        raise ValueError(f"Missing required endpoint environment variable: {port_key}")

    return str(port)
