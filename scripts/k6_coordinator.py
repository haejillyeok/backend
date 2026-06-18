from __future__ import annotations

import os
from dataclasses import dataclass, field

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class AssignmentRequest(BaseModel):
    test_id: str
    vu: int = Field(ge=1)
    iteration: int = Field(ge=0)
    room_size: int | None = Field(default=None, ge=1, le=4)


class RoomPayload(BaseModel):
    room_public_id: str


class ReadyPayload(BaseModel):
    slot_index: int = Field(ge=0)


class SessionPayload(BaseModel):
    game_session_public_id: str


@dataclass
class GroupState:
    group_id: str
    room_size: int
    room_public_id: str | None = None
    game_session_public_id: str | None = None
    claimed_slots: set[int] = field(default_factory=set)
    ready_slots: set[int] = field(default_factory=set)


def create_app() -> FastAPI:
    app = FastAPI(title="k6 local coordinator")
    groups: dict[str, GroupState] = {}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/assignments/claim")
    async def claim_assignment(request: AssignmentRequest) -> dict[str, object]:
        room_size = request.room_size or _choose_room_size(request.vu, request.iteration)
        group_number = (request.vu - 1) // room_size
        slot_index = (request.vu - 1) % room_size
        group_id = f"{request.test_id}-{room_size}-{request.iteration}-{group_number}"
        group = groups.setdefault(group_id, GroupState(group_id=group_id, room_size=room_size))
        group.claimed_slots.add(slot_index)
        return {
            "group_id": group_id,
            "room_size": room_size,
            "slot_index": slot_index,
            "is_owner": slot_index == 0,
        }

    @app.post("/groups/{group_id}/room")
    async def set_room(group_id: str, payload: RoomPayload) -> dict[str, str]:
        group = _get_group(groups, group_id)
        group.room_public_id = payload.room_public_id
        return {"room_public_id": payload.room_public_id}

    @app.get("/groups/{group_id}/room")
    async def get_room(group_id: str) -> dict[str, str | None]:
        group = _get_group(groups, group_id)
        return {"room_public_id": group.room_public_id}

    @app.post("/groups/{group_id}/ready")
    async def set_ready(group_id: str, payload: ReadyPayload) -> dict[str, object]:
        group = _get_group(groups, group_id)
        if payload.slot_index >= group.room_size:
            raise HTTPException(status_code=422, detail="slot_index exceeds room size")
        group.ready_slots.add(payload.slot_index)
        return _ready_payload(group)

    @app.get("/groups/{group_id}/ready")
    async def get_ready(group_id: str) -> dict[str, object]:
        return _ready_payload(_get_group(groups, group_id))

    @app.post("/groups/{group_id}/session")
    async def set_session(group_id: str, payload: SessionPayload) -> dict[str, str]:
        group = _get_group(groups, group_id)
        group.game_session_public_id = payload.game_session_public_id
        return {"game_session_public_id": payload.game_session_public_id}

    @app.get("/groups/{group_id}/session")
    async def get_session(group_id: str) -> dict[str, str | None]:
        group = _get_group(groups, group_id)
        return {"game_session_public_id": group.game_session_public_id}

    return app


def _choose_room_size(vu: int, iteration: int) -> int:
    bucket = (vu + iteration) % 20
    if bucket < 10:
        return 1
    if bucket < 14:
        return 2
    if bucket < 17:
        return 3
    return 4


def _get_group(groups: dict[str, GroupState], group_id: str) -> GroupState:
    group = groups.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    return group


def _ready_payload(group: GroupState) -> dict[str, object]:
    ready_count = len(group.ready_slots)
    return {
        "ready_count": ready_count,
        "required_count": group.room_size,
        "all_ready": ready_count >= group.room_size,
    }


app = create_app()


if __name__ == "__main__":
    host = os.getenv("K6_COORDINATOR_HOST", "127.0.0.1")
    port = int(os.getenv("K6_COORDINATOR_PORT", "8787"))
    uvicorn.run(app, host=host, port=port, log_level="info")
