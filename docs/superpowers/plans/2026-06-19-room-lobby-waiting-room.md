# Room Lobby Waiting Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the room/waiting-room WebSocket snapshot contain all fields needed to render and recover the room screen after reconnect.

**Architecture:** Keep room state in DB and expose it through the existing `/ws/lobby/rooms/{room_public_id}` snapshot. Preserve current member events, but enrich initial `lobby.room.snapshot` and `lobby.room.updated` so the client does not need an extra REST fetch to draw room settings.

**Tech Stack:** FastAPI WebSocket, dataclass records, Pydantic-ish response mapping, pytest.

---

## Request To Start This Work

Ask: `객실/대기방 작업 진행해줘`

## File Structure

- Modify `app/be/services/game/records/room_lobby_snapshot_result.py`: add room metadata fields.
- Modify `app/be/services/game/room_lobby_use_cases.py`: populate room metadata in snapshot.
- Modify `app/be/services/lobby/connection_messages.py`: serialize enriched snapshot.
- Modify `app/be/api/endpoints/game/room_settings_routes.py`: ensure `lobby.room.updated` event matches snapshot metadata shape.
- Modify `app/be/schemas/response/game.py`: no change unless REST response lacks a needed field.
- Test `test/test_lobby_websocket.py`: initial snapshot.
- Test `test/test_game_rooms_api.py`: room update event payload.
- Modify `app/be/api/docs/ws-api.md`, `docs/api.md`, `llm-wiki/wiki/realtime-websocket.md`.

## Contract

`lobby.room.snapshot.payload` should include:

```json
{
  "room_public_id": "...",
  "name": "첫 객실",
  "game_type": "word_chain",
  "status": "waiting",
  "max_players": 4,
  "member_count": 2,
  "rule_config": {
    "max_rounds": 8,
    "turn_time_seconds": 10
  },
  "owner_user_public_id": "...",
  "members": []
}
```

## Task 1: Enrich Snapshot Record

**Files:**
- Modify: `app/be/services/game/records/room_lobby_snapshot_result.py`
- Modify: `app/be/services/game/room_lobby_use_cases.py`
- Test: `test/test_game_session_entry.py`

- [x] **Step 1: Write failing service snapshot test**

Add a test named `test_room_lobby_connection_snapshot_includes_room_settings`.

```python
async def test_room_lobby_connection_snapshot_includes_room_settings() -> None:
    user = CurrentUser(id=uuid4(), public_id=uuid4(), account_id="player_001", nickname="방장")
    room_public_id = uuid4()
    repository = FakeGameRepository()
    repository.rooms[room_public_id] = GameRoomRecord(
        id=uuid4(),
        public_id=room_public_id,
        owner_user_id=user.id,
        name="달빛 객실",
        game_type="word_chain",
        status="waiting",
        max_players=4,
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
    )
    repository.active_members = [
        RoomMemberRecord(
            id=uuid4(),
            room_id=repository.rooms[room_public_id].id,
            user_id=user.id,
            user_public_id=user.public_id,
            nickname=user.nickname,
            joined_at=datetime.now(KST),
        )
    ]
    service = GameService(repository=repository)

    result = await service.authorize_room_lobby_connection(
        room_public_id=room_public_id,
        user_id=user.id,
    )

    assert result.snapshot.name == "달빛 객실"
    assert result.snapshot.game_type == "word_chain"
    assert result.snapshot.status == "waiting"
    assert result.snapshot.max_players == 4
    assert result.snapshot.member_count == 1
    assert result.snapshot.rule_config == {"max_rounds": 8, "turn_time_seconds": 10}
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_game_session_entry.py::test_room_lobby_connection_snapshot_includes_room_settings -q --no-cov
```

Expected: FAIL with missing `snapshot.name`.

- [x] **Step 3: Add fields to snapshot dataclass**

Update `RoomLobbySnapshotResult`:

```python
@dataclass(frozen=True)
class RoomLobbySnapshotResult:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int
    rule_config: dict[str, int]
    owner_user_public_id: UUID | None
    members: list[RoomLobbyMemberSnapshot]
```

- [x] **Step 4: Populate fields in use case**

In `GameRoomLobbyUseCaseMixin._authorize_room_lobby_connection`, pass room metadata and `member_count=len(members)`.

- [x] **Step 5: Run focused test**

Run:

```bash
.venv/bin/python -m pytest test/test_game_session_entry.py::test_room_lobby_connection_snapshot_includes_room_settings -q --no-cov
```

Expected: PASS.

## Task 2: Serialize Enriched WebSocket Snapshot

**Files:**
- Modify: `app/be/services/lobby/connection_messages.py`
- Test: `test/test_lobby_websocket.py`

- [x] **Step 1: Write failing message test**

Add or update a test so `lobby.room.snapshot` includes `name`, `game_type`, `status`, `max_players`, `member_count`, and `rule_config`.

```python
def test_lobby_snapshot_message_includes_room_settings() -> None:
    snapshot = RoomLobbySnapshotResult(
        room_public_id=uuid4(),
        name="달빛 객실",
        game_type="word_chain",
        status="waiting",
        max_players=4,
        member_count=1,
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
        owner_user_public_id=uuid4(),
        members=[],
    )

    message = lobby_snapshot_message(snapshot)

    assert message["payload"]["name"] == "달빛 객실"
    assert message["payload"]["game_type"] == "word_chain"
    assert message["payload"]["status"] == "waiting"
    assert message["payload"]["max_players"] == 4
    assert message["payload"]["member_count"] == 1
    assert message["payload"]["rule_config"] == {"max_rounds": 8, "turn_time_seconds": 10}
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_lobby_websocket.py::test_lobby_snapshot_message_includes_room_settings -q --no-cov
```

Expected: FAIL because fields are missing.

- [x] **Step 3: Serialize fields**

Update `lobby_snapshot_message` payload with the new fields before `members`.

- [x] **Step 4: Run test**

Run:

```bash
.venv/bin/python -m pytest test/test_lobby_websocket.py::test_lobby_snapshot_message_includes_room_settings -q --no-cov
```

Expected: PASS.

## Task 3: Align Room Updated Event

**Files:**
- Modify: `app/be/api/endpoints/game/room_settings_routes.py`
- Test: `test/test_game_rooms_api.py`

- [x] **Step 1: Write failing event-shape test**

Ensure `lobby.room.updated` payload includes the same room metadata fields as snapshot: `name`, `game_type`, `status`, `max_players`, `rule_config`.

- [x] **Step 2: Run test**

Run:

```bash
.venv/bin/python -m pytest test/test_game_rooms_api.py -q --no-cov
```

Expected: FAIL on missing event field if current route omits any field.

- [x] **Step 3: Update event payload only if the test proves a gap**

Use the existing `map_room_update_result(result).model_dump(mode="json")` output if it already contains the fields. If it lacks `member_count`, add it only when the frontend explicitly needs member count in update events.

- [x] **Step 4: Run verification**

Run:

```bash
.venv/bin/python -m pytest test/test_lobby_websocket.py test/test_game_rooms_api.py test/test_game_session_entry.py -q
```

Expected: PASS.

## Task 4: Documentation

**Files:**
- Modify: `app/be/api/docs/ws-api.md`
- Modify: `docs/api.md`
- Modify: `llm-wiki/wiki/realtime-websocket.md`
- Modify: `llm-wiki/log.md`

- [x] **Step 1: Update WebSocket docs**

Document the enriched `lobby.room.snapshot` payload.

- [x] **Step 2: Update LLM Wiki**

Record the current rule: room lobby snapshot is sufficient for room screen recovery.

- [x] **Step 3: Run final checks**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff format --check app test migrations
```

Expected: PASS or report unrelated formatting drift separately.
