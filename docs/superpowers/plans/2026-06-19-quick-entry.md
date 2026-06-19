# Quick Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend quick-entry API that atomically selects a joinable waiting room or creates one when none is available.

**Architecture:** Keep lobby room selection authoritative in `GameService` so the frontend can call one endpoint for the `빠른입장` button. Reuse existing room membership cleanup and join rules; avoid adding matchmaking queues until the product needs explicit matching states.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async repository pattern, pytest.

---

## Request To Start This Work

Ask: `빠른입장 작업 진행해줘`

## File Structure

- Modify `app/be/services/game/room_member_use_cases.py`: add `quick_join_room`.
- Modify `app/be/services/game/repository_protocol.py`: add repository methods needed to lock/select a quick-entry room.
- Modify `app/be/repository/game/repository.py`: implement joinable room lookup with row locking.
- Create `app/be/services/game/records/quick_room_join_result.py`: optional record only if `RoomJoinResult` cannot express create-vs-join metadata cleanly.
- Modify `app/be/services/game/records/__init__.py`: export new record if created.
- Modify `app/be/api/endpoints/game/room_membership_routes.py`: add `POST /rooms/quick-join`.
- Modify `app/be/schemas/response/game.py`: add response fields only if quick-entry must tell whether a room was created.
- Modify `docs/api.md`: document quick-entry endpoint.
- Modify `llm-wiki/wiki/sunset-game-domain.md`: update current quick-entry contract after implementation.
- Test `test/test_game_session_entry.py` or `test/test_game_rooms_api.py`: service/API behavior.

## Contract

- Endpoint: `POST /api/v1/game/rooms/quick-join`
- Auth: `session_token` cookie via `get_current_user`
- Selection rule: join the oldest `waiting` room with `member_count < max_players`, excluding rooms where the user is already an active member.
- Fallback rule: if no room is joinable, create a `waiting` room with default `game_type=word_chain`, default name, and `max_players=4`.
- Response: same shape as room join/create handoff, including `room_public_id`, `already_member`, `lobby_websocket_path`, and whether the room was created.
- Broadcast: if an existing room gains a new member, broadcast `lobby.room.joined`. If a new room is created, no existing room subscribers need a room event.

## Task 1: Service Quick-Join Behavior

**Files:**
- Modify: `app/be/services/game/room_member_use_cases.py`
- Modify: `app/be/services/game/repository_protocol.py`
- Modify: `app/be/repository/game/repository.py`
- Test: `test/test_game_session_entry.py`

- [ ] **Step 1: Write failing service test for joining an existing room**

Add a test named `test_game_service_quick_join_uses_oldest_joinable_waiting_room` using the existing fake repository style in `test/test_game_session_entry.py`.

```python
async def test_game_service_quick_join_uses_oldest_joinable_waiting_room() -> None:
    user = CurrentUser(id=uuid4(), public_id=uuid4(), account_id="player_001", nickname="초보자")
    room_public_id = uuid4()
    repository = FakeGameRepository()
    repository.quick_joinable_room = GameRoomRecord(
        id=uuid4(),
        public_id=room_public_id,
        owner_user_id=uuid4(),
        name="첫 객실",
        game_type="word_chain",
        status="waiting",
        max_players=4,
    )
    service = GameService(repository=repository)

    result = await service.quick_join_room(user=user)

    assert result.room_public_id == room_public_id
    assert result.already_member is False
    assert repository.created_members[0].user_id == user.id
    assert repository.created_rooms == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_game_session_entry.py::test_game_service_quick_join_uses_oldest_joinable_waiting_room -q --no-cov
```

Expected: FAIL with `AttributeError: 'GameService' object has no attribute 'quick_join_room'`.

- [ ] **Step 3: Implement minimal service method**

Add `quick_join_room` to `GameRoomMemberUseCaseMixin`. Reuse `_leave_existing_rooms_for_lobby_move`, `create_room_member`, and `RoomJoinResult`.

```python
async def quick_join_room(self, *, user: CurrentUser) -> RoomJoinResult:
    """빠른입장용으로 참여 가능한 대기 room을 고르거나 새 room을 만든 뒤 참여시킵니다."""
    async with self.repository_scope():
        await self.repository.lock_waiting_room_membership_for_user(user_id=user.id)
        room = await self.repository.get_oldest_joinable_waiting_room_for_update(user_id=user.id)
        if room is None:
            room = await self.repository.create_room(
                owner_user_id=user.id,
                name=f"{user.nickname}의 객실",
                game_type="word_chain",
                max_players=4,
            )
        await self._leave_existing_rooms_for_lobby_move(
            user=user,
            excluded_room_public_id=room.public_id,
        )
        member = await self.repository.create_room_member(
            room_id=room.id,
            user_id=user.id,
            nickname=user.nickname,
        )
        await self.repository.commit()
        return RoomJoinResult(
            room_public_id=room.public_id,
            user_public_id=user.public_id,
            nickname=member.nickname,
            joined_at=member.joined_at,
            already_member=False,
        )
```

- [ ] **Step 4: Implement repository protocol and SQL query**

Add to `GameRepositoryProtocol`:

```python
async def get_oldest_joinable_waiting_room_for_update(self, *, user_id: UUID) -> GameRoomRecord | None: ...
```

Implement in `GameRepository` using `Room.status == "waiting"`, active member count `< Room.max_players`, and `with_for_update(skip_locked=True)`.

- [ ] **Step 5: Run service test**

Run:

```bash
.venv/bin/python -m pytest test/test_game_session_entry.py::test_game_service_quick_join_uses_oldest_joinable_waiting_room -q --no-cov
```

Expected: PASS.

## Task 2: Quick-Join HTTP Endpoint

**Files:**
- Modify: `app/be/api/endpoints/game/room_membership_routes.py`
- Modify: `app/be/schemas/response/game.py`
- Modify: `app/be/api/endpoints/game/room_mappers.py`
- Test: `test/test_game_rooms_api.py`

- [ ] **Step 1: Write failing API test**

Add a test named `test_quick_join_room_api_returns_lobby_websocket_path`.

```python
def test_quick_join_room_api_returns_lobby_websocket_path() -> None:
    app = create_app()
    user = CurrentUser(id=uuid4(), public_id=uuid4(), account_id="player_001", nickname="초보자")
    room_public_id = uuid4()

    class FakeGameService:
        async def quick_join_room(self, *, user: CurrentUser) -> RoomJoinResult:
            return RoomJoinResult(
                room_public_id=room_public_id,
                user_public_id=user.public_id,
                nickname=user.nickname,
                joined_at=datetime.now(KST),
                already_member=False,
            )

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.post("/api/v1/game/rooms/quick-join")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["room_public_id"] == str(room_public_id)
    assert body["lobby_websocket_path"] == f"/ws/lobby/rooms/{room_public_id}"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest test/test_game_rooms_api.py::test_quick_join_room_api_returns_lobby_websocket_path -q --no-cov
```

Expected: FAIL with `404 Not Found`.

- [ ] **Step 3: Add route and response field**

Add `lobby_websocket_path` to the quick-join response mapper using `build_lobby_websocket_path(result.room_public_id)`.

- [ ] **Step 4: Run API test**

Run:

```bash
.venv/bin/python -m pytest test/test_game_rooms_api.py::test_quick_join_room_api_returns_lobby_websocket_path -q --no-cov
```

Expected: PASS.

## Task 3: Documentation And Verification

**Files:**
- Modify: `docs/api.md`
- Modify: `llm-wiki/wiki/sunset-game-domain.md`
- Modify: `llm-wiki/log.md`

- [ ] **Step 1: Document endpoint**

Add `POST /api/v1/game/rooms/quick-join` with auth, response, and selection rules.

- [ ] **Step 2: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest test/test_game_rooms_api.py test/test_game_session_entry.py -q
```

Expected: PASS.

- [ ] **Step 3: Run format check**

Run:

```bash
.venv/bin/python -m ruff format --check app test migrations
```

Expected: PASS, unless unrelated existing formatting drift is present; if drift is unrelated, run a changed-file-only format check and mention the residual risk.

