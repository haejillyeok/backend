import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict


class GrpcSettings(BaseModel):
    app_name: str
    host: str
    port: int

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_app_name(
        cls,
        app_name: str,
        env_file: str | Path = ".env",
    ) -> "GrpcSettings":
        env_prefix = format_grpc_env_prefix(app_name)
        values = load_grpc_env_values(env_prefix, env_file)
        return cls(
            app_name=app_name,
            host=values["host"],
            port=int(values["port"]),
        )

    @property
    def bind_address(self) -> str:
        return f"{self.host}:{self.port}"


def format_grpc_env_prefix(app_name: str) -> str:
    service_name = app_name.rsplit("-", maxsplit=1)[-1]
    return service_name.upper().replace("-", "_") + "_GRPC"


def load_grpc_env_values(
    env_prefix: str,
    env_file: str | Path = ".env",
) -> dict[str, str]:
    dotenv = dotenv_values(env_file)
    host_key = f"{env_prefix}_HOST"
    port_key = f"{env_prefix}_PORT"

    host = os.environ.get(host_key) or dotenv.get(host_key)
    port = os.environ.get(port_key) or dotenv.get(port_key)

    missing = [
        key
        for key, value in (
            (host_key, host),
            (port_key, port),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            "Missing required gRPC environment variables: " + ", ".join(missing)
        )

    return {
        "host": str(host),
        "port": str(port),
    }
