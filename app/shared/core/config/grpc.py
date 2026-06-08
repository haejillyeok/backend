from pathlib import Path
import os

from dotenv import dotenv_values

from app.shared.core.config.endpoint import (
    EndpointSettings,
    format_service_env_prefix,
    load_endpoint_port_value,
)


DEFAULT_GRPC_HOST = "localhost"
DEFAULT_GRPC_PORTS = {
    "BE_GRPC": 50051,
    "AGENT_GRPC": 50052,
}
FALSE_VALUES = {"0", "false", "no", "off"}
TRUE_VALUES = {"1", "true", "yes", "on"}


class GrpcSettings(EndpointSettings):
    @classmethod
    def from_app_name(
        cls,
        app_name: str,
        env_file: str | Path = ".env",
    ) -> "GrpcSettings":
        """앱 이름에 맞는 gRPC bind 설정을 환경변수에서 읽습니다."""
        env_prefix = format_grpc_env_prefix(app_name)
        port = load_endpoint_port_value(
            env_prefix,
            env_file,
            default_port=DEFAULT_GRPC_PORTS.get(env_prefix),
        )
        return cls(
            app_name=app_name,
            host=DEFAULT_GRPC_HOST,
            port=int(port),
        )


def format_grpc_env_prefix(app_name: str) -> str:
    """앱 이름에서 gRPC 환경변수 prefix를 만듭니다."""
    return format_service_env_prefix(app_name) + "_GRPC"


def load_embedded_grpc_enabled(
    app_name: str,
    env_file: str | Path = ".env",
    *,
    default: bool = True,
) -> bool:
    """HTTP 앱 lifespan에서 gRPC 서버를 함께 실행할지 환경변수에서 읽습니다."""
    env_key = f"{format_grpc_env_prefix(app_name)}_EMBEDDED"
    dotenv = dotenv_values(env_file)
    value = os.environ.get(env_key) or dotenv.get(env_key)

    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False

    raise ValueError(f"Invalid boolean value for {env_key}: {value}")


def load_grpc_env_values(
    env_prefix: str,
    env_file: str | Path = ".env",
) -> dict[str, str]:
    """기존 호출부를 위해 gRPC endpoint 값을 읽는 helper를 유지합니다."""
    port = load_endpoint_port_value(
        env_prefix,
        env_file,
        default_port=DEFAULT_GRPC_PORTS.get(env_prefix),
    )
    return {
        "host": DEFAULT_GRPC_HOST,
        "port": port,
    }
