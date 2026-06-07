from app.agent.grpc.proto import internal_health_pb2
from app.agent.grpc.proto import internal_health_pb2_grpc


PingResponse = getattr(internal_health_pb2, "PingResponse")


class AgentInternalHealthServicer(internal_health_pb2_grpc.InternalHealthServicer):
    async def Ping(self, request, context):
        return PingResponse(
            service="haejillyeok-agent",
            status="ok",
        )


def register_internal_health_service(server) -> None:
    internal_health_pb2_grpc.add_InternalHealthServicer_to_server(
        AgentInternalHealthServicer(),
        server,
    )
