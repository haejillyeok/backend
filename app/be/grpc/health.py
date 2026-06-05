from app.be.grpc.proto import internal_health_pb2
from app.be.grpc.proto import internal_health_pb2_grpc


PingResponse = getattr(internal_health_pb2, "PingResponse")


class BeInternalHealthServicer(internal_health_pb2_grpc.InternalHealthServicer):
    async def Ping(self, request, context):
        return PingResponse(
            service="haejillyeok-be",
            status="ok",
        )


def register_internal_health_service(server) -> None:
    internal_health_pb2_grpc.add_InternalHealthServicer_to_server(
        BeInternalHealthServicer(),
        server,
    )
