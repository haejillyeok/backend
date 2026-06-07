from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
import grpc


@asynccontextmanager
async def grpc_server_lifespan(
    app: FastAPI,
    server_factory: Callable[[], grpc.aio.Server],
    bind_address: str,
    stop_grace: float = 5,
) -> AsyncIterator[None]:
    server = server_factory()
    server.add_insecure_port(bind_address)
    await server.start()
    app.state.grpc_server = server

    try:
        yield
    finally:
        await server.stop(grace=stop_grace)
