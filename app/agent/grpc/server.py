import asyncio
import logging

import grpc

from app.agent.grpc.health import register_internal_health_service
from app.shared.core.config import GrpcSettings


SERVICE_NAME = "haejillyeok-agent"


def create_grpc_server() -> grpc.aio.Server:
    server = grpc.aio.server()
    register_internal_health_service(server)
    return server


async def serve() -> None:
    settings = GrpcSettings.from_app_name(SERVICE_NAME)
    server = create_grpc_server()
    server.add_insecure_port(settings.bind_address)

    logging.info("Starting %s gRPC server on %s", SERVICE_NAME, settings.bind_address)
    await server.start()
    await server.wait_for_termination()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
