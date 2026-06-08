from pathlib import Path

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
