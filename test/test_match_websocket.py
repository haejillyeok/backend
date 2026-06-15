from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from app.be.dependencies.database import get_db_session
from app.be.dependencies.services import (
    get_auth_service,
    get_game_service,
    get_optional_match_ai_turn_service,
    get_match_progress_service,
    get_match_service,
    get_match_vote_service,
)
from app.be.main import create_app
from app.be.services.auth import CurrentUser, SessionExpiredError
from app.be.services.game import GameSessionEntryResult, GameSessionParticipantRecord
from app.be.services.match import (
    MatchParticipantSnapshot,
    MatchResultSnapshot,
    MatchSnapshotResult,
    MatchTurnTimer,
    MatchTurnSnapshot,
    MatchVotingTimer,
    broadcast_match_event_with_round_finished,
    match_connection_manager,
    process_match_turn_timeout,
    process_match_vote_timeout,
    seconds_until_match_wait_timeout,
)
from app.be.services.match_progress import MatchBroadcastEvent
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


KST = ZoneInfo("Asia/Seoul")


class FakeDbSession:
    def __init__(self) -> None:
        self.rolled_back = False

    async def rollback(self) -> None:
        self.rolled_back = True


def use_fake_db_session(app, db_session: FakeDbSession | None = None) -> FakeDbSession:
    fake_db_session = db_session or FakeDbSession()

    async def fake_db_session_dependency():
        yield fake_db_session

    app.dependency_overrides[get_db_session] = fake_db_session_dependency
    app.dependency_overrides[get_optional_match_ai_turn_service] = lambda: None
    return fake_db_session


def current_user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )


def participant(
    *,
    game_session_public_id: UUID,
    user_id: UUID | None,
    participant_id: UUID | None = None,
    display_name: str = "1번 손님",
    seat_number: int = 1,
) -> GameSessionParticipantRecord:
    return GameSessionParticipantRecord(
        participant_id=participant_id or uuid4(),
        game_session_public_id=game_session_public_id,
        user_id=user_id,
        participant_type="user",
        display_name=display_name,
        seat_number=seat_number,
        is_uninvited_guest=False,
    )


def snapshot(game_session_public_id: UUID) -> MatchSnapshotResult:
    return MatchSnapshotResult(
        game_session_public_id=game_session_public_id,
        status="starting",
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
        participants=[
            MatchParticipantSnapshot(display_name="1번 손님", seat_number=1, is_me=True),
            MatchParticipantSnapshot(display_name="2번 손님", seat_number=2, is_me=False),
        ],
        current_round_number=None,
        current_turn=None,
        used_words=[],
        scoreboard=[],
        server_time=datetime(2026, 6, 13, tzinfo=KST),
    )


def snapshot_with_current_turn(
    *,
    game_session_public_id: UUID,
    phase_id: UUID,
) -> MatchSnapshotResult:
    return MatchSnapshotResult(
        game_session_public_id=game_session_public_id,
        status="playing",
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
        participants=[
            MatchParticipantSnapshot(display_name="1번 손님", seat_number=1, is_me=True),
            MatchParticipantSnapshot(display_name="2번 손님", seat_number=2, is_me=False),
        ],
        current_round_number=1,
        current_turn=MatchTurnSnapshot(
            phase_id=phase_id,
            round_number=1,
            turn_number=3,
            actor_seat_number=1,
            started_at=datetime(2099, 6, 13, 0, 0, 0, tzinfo=KST),
            deadline_at=datetime(2099, 6, 13, 0, 0, 10, tzinfo=KST),
            required_start_char="가",
        ),
        used_words=["사과"],
        scoreboard=[],
        server_time=datetime(2026, 6, 13, tzinfo=KST),
    )


def result_snapshot(game_session_public_id: UUID) -> MatchSnapshotResult:
    return MatchSnapshotResult(
        game_session_public_id=game_session_public_id,
        status="result",
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
        participants=[
            MatchParticipantSnapshot(display_name="1번 손님", seat_number=1, is_me=True),
            MatchParticipantSnapshot(display_name="2번 손님", seat_number=2, is_me=False),
        ],
        current_round_number=None,
        current_turn=None,
        used_words=["사과"],
        scoreboard=[],
        server_time=datetime(2026, 6, 13, tzinfo=KST),
        results=[
            MatchResultSnapshot(
                display_name="1번 손님",
                seat_number=1,
                revealed_participant_type="user",
                final_score=20,
                rank=1,
                is_winner=True,
                vote_score_delta=10,
                is_me=True,
            ),
            MatchResultSnapshot(
                display_name="2번 손님",
                seat_number=2,
                revealed_participant_type="ai",
                final_score=-5,
                rank=2,
                is_winner=False,
                vote_score_delta=-5,
                is_me=False,
            ),
        ],
    )


class FakeAuthService:
    def __init__(self, user: CurrentUser) -> None:
        self.user = user

    async def authenticate_session(self, session_token: str | None) -> CurrentUser:
        if session_token != "valid-session":
            raise SessionExpiredError
        return self.user


def test_match_websocket_connects_with_session_cookie_and_sends_anonymous_snapshot() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    participant_record = participant(game_session_public_id=game_session_public_id, user_id=user.id)
    db_session = FakeDbSession()

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            assert user_id == user.id
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            assert participant_id == participant_record.participant_id
            return snapshot(game_session_public_id)

    app = create_app()
    use_fake_db_session(app, db_session)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json() == {
            "type": "match.connected",
            "payload": {
                "game_session_public_id": str(game_session_public_id),
                "participant": {
                    "display_name": "1번 손님",
                    "seat_number": 1,
                },
            },
        }
        received_snapshot = websocket.receive_json()

    assert received_snapshot == {
        "type": "match.snapshot",
        "payload": {
            "game_session_public_id": str(game_session_public_id),
            "status": "starting",
            "rule_config": {"max_rounds": 8, "turn_time_seconds": 10},
            "participants": [
                {"display_name": "1번 손님", "seat_number": 1, "is_me": True},
                {"display_name": "2번 손님", "seat_number": 2, "is_me": False},
            ],
            "current_round_number": None,
            "current_turn": None,
            "used_words": [],
            "scoreboard": [],
            "server_time": "2026-06-13T00:00:00+09:00",
            "voting_deadline_at": None,
            "results": [],
        },
    }
    assert "participant_type" not in str(received_snapshot)
    assert "is_uninvited_guest" not in str(received_snapshot)
    assert "방장" not in str(received_snapshot)
    assert db_session.rolled_back is True
    assert match_connection_manager.connection_count == 0


def test_match_websocket_resumes_with_game_session_token_without_login_cookie() -> None:
    game_session_public_id = uuid4()
    participant_record = participant(game_session_public_id=game_session_public_id, user_id=uuid4())

    class FakeGameService:
        async def authorize_resume_token(self, game_session_token: str):
            assert game_session_token == "resume-token"
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token=game_session_token,
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            return snapshot(game_session_public_id)

    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    client = TestClient(app)

    with client.websocket_connect("/ws/match?game_session_token=resume-token") as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        assert websocket.receive_json()["type"] == "match.snapshot"


def test_match_websocket_snapshot_includes_published_results_for_reconnect() -> None:
    game_session_public_id = uuid4()
    participant_record = participant(game_session_public_id=game_session_public_id, user_id=uuid4())

    class FakeGameService:
        async def authorize_resume_token(self, game_session_token: str):
            assert game_session_token == "resume-token"
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token=game_session_token,
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            assert participant_id == participant_record.participant_id
            return result_snapshot(game_session_public_id)

    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    client = TestClient(app)

    with client.websocket_connect("/ws/match?game_session_token=resume-token") as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        received_snapshot = websocket.receive_json()

    assert received_snapshot["type"] == "match.snapshot"
    assert received_snapshot["payload"]["status"] == "result"
    assert received_snapshot["payload"]["results"] == [
        {
            "participant": {
                "display_name": "1번 손님",
                "seat_number": 1,
                "revealed_participant_type": "user",
            },
            "final_score": 20,
            "rank": 1,
            "is_winner": True,
            "vote_score_delta": 10,
            "is_me": True,
        },
        {
            "participant": {
                "display_name": "2번 손님",
                "seat_number": 2,
                "revealed_participant_type": "ai",
            },
            "final_score": -5,
            "rank": 2,
            "is_winner": False,
            "vote_score_delta": -5,
            "is_me": False,
        },
    ]
    assert "방장" not in str(received_snapshot)


def test_match_websocket_snapshot_includes_current_turn_phase_id() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_record = participant(game_session_public_id=game_session_public_id, user_id=user.id)

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            return snapshot_with_current_turn(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
            )

    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        received_snapshot = websocket.receive_json()

    assert received_snapshot["payload"]["current_turn"]["phase_id"] == str(phase_id)


def test_match_wait_timeout_uses_earlier_turn_deadline() -> None:
    now = datetime(2026, 6, 13, 0, 0, tzinfo=KST)
    timer = MatchTurnTimer(
        phase_id=uuid4(),
        deadline_at=datetime(2026, 6, 13, 0, 0, 3, tzinfo=KST),
    )

    assert seconds_until_match_wait_timeout(timer, now=now, heartbeat_seconds=45) == 3


def test_match_wait_timeout_uses_earlier_voting_deadline() -> None:
    now = datetime(2026, 6, 13, 0, 0, tzinfo=KST)
    timer = MatchVotingTimer(deadline_at=datetime(2026, 6, 13, 0, 0, 7, tzinfo=KST))

    assert seconds_until_match_wait_timeout(timer, now=now, heartbeat_seconds=45) == 7


async def test_process_match_turn_timeout_broadcasts_event_and_returns_next_timer() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    next_phase_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
    next_deadline_at = datetime(2026, 6, 13, 0, 0, 21, tzinfo=KST)

    class FakeManager:
        def __init__(self) -> None:
            self.broadcasts = []

        async def broadcast_session(self, game_session_public_id, message):
            self.broadcasts.append((game_session_public_id, message))

    class FakeProgressService:
        async def timeout_turn_if_due(self, **kwargs):
            assert kwargs == {
                "game_session_public_id": game_session_public_id,
                "phase_id": phase_id,
                "now": now,
            }
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "result": "timeout",
                        "next_turn": {
                            "phase_id": next_phase_id,
                            "round_number": 2,
                            "turn_number": 1,
                            "actor_seat_number": 2,
                            "deadline_at": next_deadline_at,
                            "required_start_char": None,
                        },
                    },
                },
            )

    manager = FakeManager()

    next_timer = await process_match_turn_timeout(
        manager=manager,
        progress_service=FakeProgressService(),
        ai_turn_service=None,
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert manager.broadcasts[0][0] == game_session_public_id
    assert manager.broadcasts[0][1]["type"] == "match.turn.resolved"
    assert manager.broadcasts[0][1]["payload"]["result"] == "timeout"
    assert next_timer == MatchTurnTimer(phase_id=next_phase_id, deadline_at=next_deadline_at)


async def test_process_match_turn_timeout_broadcasts_round_finished_event() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    next_phase_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
    next_deadline_at = datetime(2026, 6, 13, 0, 0, 21, tzinfo=KST)

    class FakeManager:
        def __init__(self) -> None:
            self.broadcasts = []

        async def broadcast_session(self, game_session_public_id, message):
            self.broadcasts.append((game_session_public_id, message))

    class FakeProgressService:
        async def timeout_turn_if_due(self, **kwargs):
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "event_sequence": 7,
                        "phase_id": phase_id,
                        "round_number": 1,
                        "participant": {"display_name": "1번 손님", "seat_number": 1},
                        "result": "timeout",
                        "reason": "deadline_exceeded",
                        "deadline_at": datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
                        "created_at": now,
                        "next_turn": {
                            "phase_id": next_phase_id,
                            "round_number": 2,
                            "turn_number": 1,
                            "actor_seat_number": 2,
                            "deadline_at": next_deadline_at,
                            "required_start_char": None,
                        },
                    },
                },
            )

    manager = FakeManager()

    await process_match_turn_timeout(
        manager=manager,
        progress_service=FakeProgressService(),
        ai_turn_service=None,
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert [message["type"] for _, message in manager.broadcasts] == [
        "match.turn.resolved",
        "match.round.finished",
        "match.round.started",
    ]
    assert manager.broadcasts[1][1]["payload"]["round_number"] == 1
    assert manager.broadcasts[1][1]["payload"]["next_turn"]["round_number"] == 2
    assert manager.broadcasts[2][1]["payload"]["round_number"] == 2
    assert manager.broadcasts[2][1]["payload"]["current_turn"]["phase_id"] == next_phase_id


async def test_broadcast_match_event_waits_until_delayed_round_start() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    next_phase_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
    round_started_at = datetime(2026, 6, 13, 0, 0, 16, tzinfo=KST)
    sleeps = []

    class FakeManager:
        def __init__(self) -> None:
            self.broadcasts = []

        async def broadcast_session(self, game_session_public_id, message):
            self.broadcasts.append((game_session_public_id, message))

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    manager = FakeManager()
    event = MatchBroadcastEvent(
        game_session_public_id=game_session_public_id,
        message={
            "type": "match.turn.resolved",
            "payload": {
                "event_sequence": 7,
                "phase_id": phase_id,
                "round_number": 1,
                "participant": {"display_name": "1번 손님", "seat_number": 1},
                "result": "timeout",
                "reason": "deadline_exceeded",
                "deadline_at": datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
                "created_at": now,
                "next_turn": {
                    "phase_id": next_phase_id,
                    "round_number": 2,
                    "turn_number": 1,
                    "actor_seat_number": 2,
                    "started_at": round_started_at,
                    "deadline_at": datetime(2026, 6, 13, 0, 0, 26, tzinfo=KST),
                    "required_start_char": None,
                },
            },
        },
    )

    await broadcast_match_event_with_round_finished(
        manager=manager,
        event=event,
        now=now,
        sleep=fake_sleep,
    )

    assert sleeps == [5.0]
    assert [message["type"] for _, message in manager.broadcasts] == [
        "match.turn.resolved",
        "match.round.finished",
        "match.round.started",
    ]
    assert manager.broadcasts[2][1]["payload"]["started_at"] == round_started_at


async def test_process_match_turn_timeout_does_not_trigger_ai_when_round_moves_to_voting() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
    voting_deadline_at = datetime(2026, 6, 13, 0, 0, 31, tzinfo=KST)

    class FakeManager:
        def __init__(self) -> None:
            self.broadcasts = []

        async def broadcast_session(self, game_session_public_id, message):
            self.broadcasts.append((game_session_public_id, message))

    class FakeProgressService:
        async def timeout_turn_if_due(self, **kwargs):
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "phase_id": phase_id,
                        "round_number": 8,
                        "result": "timeout",
                        "reason": "deadline_exceeded",
                        "next_status": "voting",
                        "voting_deadline_at": voting_deadline_at,
                        "created_at": now,
                    },
                },
            )

    class FakeAiTurnService:
        async def play_ai_turn(self, **kwargs):
            raise AssertionError("투표 전환에는 AI 턴을 실행하면 안 됩니다.")

    manager = FakeManager()

    next_timer = await process_match_turn_timeout(
        manager=manager,
        progress_service=FakeProgressService(),
        ai_turn_service=FakeAiTurnService(),
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert next_timer == MatchVotingTimer(deadline_at=voting_deadline_at)
    assert [message["type"] for _, message in manager.broadcasts] == [
        "match.turn.resolved",
        "match.round.finished",
    ]


async def test_process_match_turn_timeout_keeps_ai_timer_after_failed_ai_answer() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    ai_phase_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST)
    ai_deadline_at = datetime(2026, 6, 13, 0, 0, 21, tzinfo=KST)

    class FakeManager:
        def __init__(self) -> None:
            self.broadcasts = []

        async def broadcast_session(self, game_session_public_id, message):
            self.broadcasts.append((game_session_public_id, message))

    class FakeProgressService:
        async def timeout_turn_if_due(self, **kwargs):
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "phase_id": phase_id,
                        "round_number": 1,
                        "result": "timeout",
                        "reason": "deadline_exceeded",
                        "next_turn": {
                            "phase_id": ai_phase_id,
                            "round_number": 2,
                            "turn_number": 1,
                            "actor_seat_number": 2,
                            "deadline_at": ai_deadline_at,
                            "required_start_char": None,
                        },
                        "created_at": now,
                    },
                },
            )

    class FakeAiTurnService:
        async def play_ai_turn(self, **kwargs):
            assert kwargs["phase_id"] == ai_phase_id
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "phase_id": ai_phase_id,
                        "result": "failed",
                        "reason": "no_candidate",
                        "created_at": now,
                    },
                },
            )

    manager = FakeManager()

    next_timer = await process_match_turn_timeout(
        manager=manager,
        progress_service=FakeProgressService(),
        ai_turn_service=FakeAiTurnService(),
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )

    assert next_timer == MatchTurnTimer(phase_id=ai_phase_id, deadline_at=ai_deadline_at)
    assert [message["type"] for _, message in manager.broadcasts] == [
        "match.turn.resolved",
        "match.round.finished",
        "match.round.started",
        "match.turn.resolved",
    ]
    assert manager.broadcasts[-1][1]["payload"]["result"] == "failed"


async def test_process_match_vote_timeout_broadcasts_result_events() -> None:
    game_session_public_id = uuid4()
    now = datetime(2026, 6, 13, 0, 0, 21, tzinfo=KST)

    class FakeManager:
        def __init__(self) -> None:
            self.broadcasts = []

        async def broadcast_session(self, game_session_public_id, message):
            self.broadcasts.append((game_session_public_id, message))

    class FakeVoteService:
        async def timeout_vote(self, **kwargs):
            assert kwargs == {
                "game_session_public_id": game_session_public_id,
                "now": now,
            }
            return [
                MatchBroadcastEvent(
                    game_session_public_id=game_session_public_id,
                    message={"type": "match.vote.timeout", "payload": {}},
                ),
                MatchBroadcastEvent(
                    game_session_public_id=game_session_public_id,
                    message={"type": "match.result.published", "payload": {}},
                ),
            ]

    manager = FakeManager()

    next_timer = await process_match_vote_timeout(
        manager=manager,
        vote_service=FakeVoteService(),
        game_session_public_id=game_session_public_id,
        now=now,
    )

    assert next_timer is None
    assert [message["type"] for _, message in manager.broadcasts] == [
        "match.vote.timeout",
        "match.result.published",
    ]


def test_match_websocket_replies_to_ping_after_snapshot() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    participant_record = participant(game_session_public_id=game_session_public_id, user_id=user.id)

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            return snapshot(game_session_public_id)

    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        assert websocket.receive_json()["type"] == "match.snapshot"
        websocket.send_json({"type": "ping", "payload": {"client_time": "now"}})

        assert websocket.receive_json() == {
            "type": "match.pong",
            "payload": {"client_time": "now"},
        }


def test_match_websocket_accepts_word_submit_and_broadcasts_result() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    participant_id = uuid4()
    phase_id = uuid4()
    participant_record = participant(
        game_session_public_id=game_session_public_id,
        user_id=user.id,
        participant_id=participant_id,
    )

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            return snapshot(game_session_public_id)

    class FakeMatchProgressService:
        def __init__(self) -> None:
            self.submitted_words = []

        async def submit_word(self, **kwargs):
            self.submitted_words.append(kwargs)
            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["phase_id"] == phase_id
            assert kwargs["participant_id"] == participant_id
            assert kwargs["word"] == "사과"
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "event_sequence": 1,
                        "phase_id": phase_id,
                        "participant": {"display_name": "1번 손님", "seat_number": 1},
                        "result": "accepted",
                        "word": "사과",
                        "normalized_word": "사과",
                        "score_delta": 10,
                        "next_turn": {
                            "phase_id": uuid4(),
                            "round_number": 1,
                            "turn_number": 2,
                            "actor_seat_number": 2,
                            "deadline_at": datetime(2099, 6, 13, 0, 0, 15, tzinfo=KST),
                            "required_start_char": "과",
                        },
                        "created_at": datetime(2026, 6, 13, 0, 0, 5, tzinfo=KST),
                    },
                },
            )

    progress_service = FakeMatchProgressService()
    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    app.dependency_overrides[get_match_progress_service] = lambda: progress_service
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        assert websocket.receive_json()["type"] == "match.snapshot"
        websocket.send_json(
            {
                "type": "word.submit",
                "payload": {"phase_id": str(phase_id), "word": "사과"},
            }
        )
        event = websocket.receive_json()

    assert event["type"] == "match.turn.resolved"
    assert event["payload"]["result"] == "accepted"
    assert event["payload"]["word"] == "사과"
    assert event["payload"]["next_turn"]["required_start_char"] == "과"
    assert progress_service.submitted_words


def test_match_websocket_triggers_ai_turn_after_word_submit_when_next_turn_is_ai() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    participant_id = uuid4()
    phase_id = uuid4()
    ai_phase_id = uuid4()
    participant_record = participant(
        game_session_public_id=game_session_public_id,
        user_id=user.id,
        participant_id=participant_id,
    )

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            return snapshot(game_session_public_id)

    class FakeMatchProgressService:
        async def submit_word(self, **kwargs):
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "event_sequence": 1,
                        "phase_id": phase_id,
                        "participant": {"display_name": "1번 손님", "seat_number": 1},
                        "result": "accepted",
                        "word": "사과",
                        "normalized_word": "사과",
                        "score_delta": 10,
                        "next_turn": {
                            "phase_id": ai_phase_id,
                            "round_number": 1,
                            "turn_number": 2,
                            "actor_seat_number": 2,
                            "deadline_at": datetime(2099, 6, 13, 0, 0, 15, tzinfo=KST),
                            "required_start_char": "과",
                        },
                        "created_at": datetime(2026, 6, 13, 0, 0, 5, tzinfo=KST),
                    },
                },
            )

    class FakeAiTurnService:
        def __init__(self) -> None:
            self.played_turns = []

        async def play_ai_turn(self, **kwargs):
            self.played_turns.append(kwargs)
            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["phase_id"] == ai_phase_id
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "result": "accepted",
                        "word": "과자",
                        "normalized_word": "과자",
                        "next_turn": {
                            "phase_id": uuid4(),
                            "round_number": 1,
                            "turn_number": 3,
                            "actor_seat_number": 1,
                            "deadline_at": datetime(2099, 6, 13, 0, 0, 25, tzinfo=KST),
                            "required_start_char": "자",
                        },
                    },
                },
            )

    ai_turn_service = FakeAiTurnService()
    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    app.dependency_overrides[get_match_progress_service] = lambda: FakeMatchProgressService()
    app.dependency_overrides[get_optional_match_ai_turn_service] = lambda: ai_turn_service
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        assert websocket.receive_json()["type"] == "match.snapshot"
        websocket.send_json(
            {
                "type": "word.submit",
                "payload": {"phase_id": str(phase_id), "word": "사과"},
            }
        )
        user_event = websocket.receive_json()
        ai_event = websocket.receive_json()

    assert user_event["payload"]["word"] == "사과"
    assert user_event["payload"]["result"] == "accepted"
    assert ai_event["payload"]["word"] == "과자"
    assert ai_event["payload"]["result"] == "accepted"
    assert ai_turn_service.played_turns


def test_match_websocket_broadcasts_dictionary_rejection_without_closing() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    participant_id = uuid4()
    phase_id = uuid4()
    participant_record = participant(
        game_session_public_id=game_session_public_id,
        user_id=user.id,
        participant_id=participant_id,
    )

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            return snapshot_with_current_turn(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
            )

    class FakeMatchProgressService:
        def __init__(self) -> None:
            self.rejected_words = []

        async def submit_word(self, **kwargs):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "word_not_in_dictionary"},
            )

        async def reject_word(self, **kwargs):
            self.rejected_words.append(kwargs)
            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["phase_id"] == phase_id
            assert kwargs["participant_id"] == participant_id
            assert kwargs["word"] == "사과"
            assert kwargs["reason"] == "word_not_in_dictionary"
            assert kwargs["details"] == {}
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "event_sequence": 1,
                        "phase_id": phase_id,
                        "participant": {"display_name": "1번 손님", "seat_number": 1},
                        "result": "rejected",
                        "word": "사과",
                        "normalized_word": "사과",
                        "reason": "word_not_in_dictionary",
                        "details": {},
                        "score_delta": -5,
                        "created_at": datetime(2026, 6, 13, 0, 0, 5, tzinfo=KST),
                    },
                },
            )

    progress_service = FakeMatchProgressService()
    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    app.dependency_overrides[get_match_progress_service] = lambda: progress_service
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        assert websocket.receive_json()["type"] == "match.snapshot"
        websocket.send_json(
            {
                "type": "word.submit",
                "payload": {"phase_id": str(phase_id), "word": "사과"},
            }
        )
        rejected_event = websocket.receive_json()
        websocket.send_json({"type": "ping", "payload": {"client_time": "after-reject"}})
        pong_event = websocket.receive_json()

    assert rejected_event["type"] == "match.turn.resolved"
    assert rejected_event["payload"]["result"] == "rejected"
    assert rejected_event["payload"]["reason"] == "word_not_in_dictionary"
    assert pong_event == {
        "type": "match.pong",
        "payload": {"client_time": "after-reject"},
    }
    assert progress_service.rejected_words


def test_match_websocket_broadcasts_turn_timeout_without_closing_on_late_word_submit() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    participant_id = uuid4()
    phase_id = uuid4()
    participant_record = participant(
        game_session_public_id=game_session_public_id,
        user_id=user.id,
        participant_id=participant_id,
    )

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            return snapshot_with_current_turn(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
            )

    class FakeMatchProgressService:
        def __init__(self) -> None:
            self.timeout_calls = []

        async def submit_word(self, **kwargs):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "turn_deadline_exceeded"},
            )

        async def timeout_turn_if_due(self, **kwargs):
            self.timeout_calls.append(kwargs)
            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["phase_id"] == phase_id
            return MatchBroadcastEvent(
                game_session_public_id=game_session_public_id,
                message={
                    "type": "match.turn.resolved",
                    "payload": {
                        "event_sequence": 3,
                        "phase_id": phase_id,
                        "participant": {"display_name": "1번 손님", "seat_number": 1},
                        "result": "timeout",
                        "reason": "deadline_exceeded",
                        "deadline_at": datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
                        "created_at": datetime(2026, 6, 13, 0, 0, 11, tzinfo=KST),
                    },
                },
            )

    progress_service = FakeMatchProgressService()
    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    app.dependency_overrides[get_match_progress_service] = lambda: progress_service
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        assert websocket.receive_json()["type"] == "match.snapshot"
        websocket.send_json(
            {
                "type": "word.submit",
                "payload": {"phase_id": str(phase_id), "word": "가방"},
            }
        )
        timeout_event = websocket.receive_json()
        websocket.send_json({"type": "ping", "payload": {"client_time": "after-timeout"}})
        pong_event = websocket.receive_json()

    assert timeout_event["type"] == "match.turn.resolved"
    assert timeout_event["payload"]["result"] == "timeout"
    assert timeout_event["payload"]["reason"] == "deadline_exceeded"
    assert pong_event == {
        "type": "match.pong",
        "payload": {"client_time": "after-timeout"},
    }
    assert progress_service.timeout_calls


def test_match_websocket_accepts_vote_submit_and_broadcasts_result_events() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    participant_id = uuid4()
    participant_record = participant(
        game_session_public_id=game_session_public_id,
        user_id=user.id,
        participant_id=participant_id,
    )

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            result = snapshot(game_session_public_id)
            return MatchSnapshotResult(
                game_session_public_id=result.game_session_public_id,
                status="voting",
                rule_config=result.rule_config,
                participants=result.participants,
                current_round_number=None,
                current_turn=None,
                used_words=result.used_words,
                scoreboard=result.scoreboard,
                server_time=result.server_time,
            )

    class FakeMatchVoteService:
        def __init__(self) -> None:
            self.submitted_votes = []

        async def submit_vote(self, **kwargs):
            self.submitted_votes.append(kwargs)
            assert kwargs["game_session_public_id"] == game_session_public_id
            assert kwargs["voter_participant_id"] == participant_id
            assert kwargs["target_seat_number"] == 3
            return [
                MatchBroadcastEvent(
                    game_session_public_id=game_session_public_id,
                    message={
                        "type": "match.vote.accepted",
                        "payload": {
                            "submitted_vote_count": 2,
                            "required_vote_count": 2,
                        },
                    },
                ),
                MatchBroadcastEvent(
                    game_session_public_id=game_session_public_id,
                    message={
                        "type": "match.result.published",
                        "payload": {
                            "results": [
                                {
                                    "participant": {
                                        "display_name": "3번 손님",
                                        "seat_number": 3,
                                        "revealed_participant_type": "ai",
                                    },
                                    "final_score": -5,
                                    "rank": 2,
                                    "is_winner": False,
                                    "vote_score_delta": -5,
                                }
                            ]
                        },
                    },
                ),
            ]

    vote_service = FakeMatchVoteService()
    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    app.dependency_overrides[get_match_vote_service] = lambda: vote_service
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        assert websocket.receive_json()["type"] == "match.snapshot"
        websocket.send_json({"type": "vote.submit", "payload": {"target_seat_number": 3}})
        accepted_event = websocket.receive_json()
        result_event = websocket.receive_json()

    assert accepted_event["type"] == "match.vote.accepted"
    assert result_event["type"] == "match.result.published"
    assert result_event["payload"]["results"][0]["participant"]["revealed_participant_type"] == "ai"
    assert vote_service.submitted_votes


def test_match_websocket_broadcasts_vote_timeout_without_closing_on_late_vote_submit() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    participant_id = uuid4()
    participant_record = participant(
        game_session_public_id=game_session_public_id,
        user_id=user.id,
        participant_id=participant_id,
    )

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            result = snapshot(game_session_public_id)
            return MatchSnapshotResult(
                game_session_public_id=result.game_session_public_id,
                status="voting",
                rule_config=result.rule_config,
                participants=result.participants,
                current_round_number=None,
                current_turn=None,
                used_words=result.used_words,
                scoreboard=result.scoreboard,
                server_time=result.server_time,
                voting_deadline_at=datetime(2099, 6, 13, 0, 0, 20, tzinfo=KST),
            )

    class FakeMatchVoteService:
        def __init__(self) -> None:
            self.timeout_calls = []

        async def submit_vote(self, **kwargs):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "vote_deadline_exceeded"},
            )

        async def timeout_vote(self, **kwargs):
            self.timeout_calls.append(kwargs)
            assert kwargs["game_session_public_id"] == game_session_public_id
            return [
                MatchBroadcastEvent(
                    game_session_public_id=game_session_public_id,
                    message={
                        "type": "match.vote.timeout",
                        "payload": {
                            "event_sequence": 5,
                            "submitted_vote_count": 1,
                            "required_vote_count": 2,
                            "created_at": datetime(2026, 6, 13, 0, 0, 21, tzinfo=KST),
                        },
                    },
                ),
                MatchBroadcastEvent(
                    game_session_public_id=game_session_public_id,
                    message={
                        "type": "match.result.published",
                        "payload": {
                            "event_sequence": 6,
                            "results": [],
                            "created_at": datetime(2026, 6, 13, 0, 0, 21, tzinfo=KST),
                        },
                    },
                ),
            ]

    vote_service = FakeMatchVoteService()
    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    app.dependency_overrides[get_match_vote_service] = lambda: vote_service
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        assert websocket.receive_json()["type"] == "match.snapshot"
        websocket.send_json({"type": "vote.submit", "payload": {"target_seat_number": 2}})
        timeout_event = websocket.receive_json()
        result_event = websocket.receive_json()
        websocket.send_json({"type": "ping", "payload": {"client_time": "after-vote-timeout"}})
        pong_event = websocket.receive_json()

    assert timeout_event["type"] == "match.vote.timeout"
    assert result_event["type"] == "match.result.published"
    assert pong_event == {
        "type": "match.pong",
        "payload": {"client_time": "after-vote-timeout"},
    }
    assert vote_service.timeout_calls


def test_match_websocket_closes_on_unsupported_message_after_snapshot() -> None:
    user = current_user()
    game_session_public_id = uuid4()
    participant_record = participant(game_session_public_id=game_session_public_id, user_id=user.id)

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id: UUID, user_id: UUID):
            return GameSessionEntryResult(
                game_session_public_id=game_session_public_id,
                participant=participant_record,
                game_session_token="new-token",
                game_session_token_expires_at=datetime(2026, 6, 13, 3, tzinfo=KST),
            )

    class FakeMatchService:
        async def get_snapshot(self, *, game_session_public_id: UUID, participant_id: UUID):
            return snapshot(game_session_public_id)

    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    app.dependency_overrides[get_match_service] = lambda: FakeMatchService()
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(
        f"/ws/match?game_session_public_id={game_session_public_id}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "match.connected"
        assert websocket.receive_json()["type"] == "match.snapshot"
        websocket.send_json({"type": "unknown", "payload": {}})
        assert websocket.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 1008


def test_match_websocket_rejects_connection_without_session_identity() -> None:
    app = create_app()
    use_fake_db_session(app)
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/match"):
            pass

    assert exc_info.value.code == 1008
