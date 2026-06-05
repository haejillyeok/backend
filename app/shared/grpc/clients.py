import grpc


def create_insecure_channel_target(host: str, port: int) -> str:
    return f"{host}:{port}"


def create_insecure_aio_channel(host: str, port: int) -> grpc.aio.Channel:
    return grpc.aio.insecure_channel(create_insecure_channel_target(host, port))
