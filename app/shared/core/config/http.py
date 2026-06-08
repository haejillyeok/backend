from pathlib import Path

from app.shared.core.config.endpoint import (
    EndpointSettings,
    format_service_env_prefix,
    load_endpoint_port_value,
)


DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORTS = {
    "BE_HTTP": 8000,
    "AGENT_HTTP": 8001,
}


class HttpSettings(EndpointSettings):
    @classmethod
    def from_app_name(
        cls,
        app_name: str,
        env_file: str | Path = ".env",
    ) -> "HttpSettings":
        """앱 이름에 맞는 HTTP 개발 서버 bind 설정을 환경변수에서 읽습니다."""
        env_prefix = format_http_env_prefix(app_name)
        port = load_endpoint_port_value(
            env_prefix,
            env_file,
            default_port=DEFAULT_HTTP_PORTS.get(env_prefix),
        )
        return cls(
            app_name=app_name,
            host=DEFAULT_HTTP_HOST,
            port=int(port),
        )


def format_http_env_prefix(app_name: str) -> str:
    """앱 이름에서 HTTP 환경변수 prefix를 만듭니다."""
    return format_service_env_prefix(app_name) + "_HTTP"
