from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.be.models.game import (
    GameSession,
    SessionParticipant,
    SessionPhase,
    SessionResult,
    UsedWord,
    WordTurn,
)
from app.be.repository.match import MatchRepository
from app.be.services.match import MatchResultSnapshot, MatchService, MatchSnapshotResult
from app.be.services.match.connection_messages import match_snapshot_message
from app.be.services.match_vote import ScoreBreakdownItem, ScoreBreakdownPayload


KST = ZoneInfo("Asia/Seoul")


def test_match_snapshot_result_shape_matches_result_event_shape() -> None:
    snapshot = MatchSnapshotResult(
        game_session_public_id=uuid4(),
        status="result",
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
        participants=[],
        current_round_number=None,
        current_turn=None,
        used_words=[],
        scoreboard=[],
        server_time=datetime.now(KST),
        results=[
            MatchResultSnapshot(
                display_name="2번 손님",
                seat_number=2,
                revealed_participant_type="ai",
                final_score=-5,
                rank=2,
                is_winner=False,
                vote_score_delta=-5,
                is_me=False,
                score_breakdown=ScoreBreakdownPayload(
                    word_score=0,
                    vote_score=-5,
                    penalty_score=0,
                    items=[ScoreBreakdownItem(reason="voted_as_ai", score_delta=-5)],
                ),
            )
        ],
    )

    message = match_snapshot_message(snapshot)

    result = message["payload"]["results"][0]
    assert result["participant"]["display_name"] == "2번 손님"
    assert result["participant"]["seat_number"] == 2
    assert result["participant"]["revealed_participant_type"] == "ai"
    assert result["final_score"] == -5
    assert result["rank"] == 2
    assert result["is_winner"] is False
    assert result["vote_score_delta"] == -5
    assert result["score_breakdown"]["vote_score"] == -5
    assert result["score_breakdown"]["items"] == [{"reason": "voted_as_ai", "score_delta": -5}]
    assert result["is_me"] is False


class FakeScalarCollection:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeResult:
    def __init__(self, *, scalar=None, rows=None, scalars=None) -> None:
        self.scalar = scalar
        self.rows = rows or []
        self.scalar_rows = scalars or []

    def scalar_one_or_none(self):
        return self.scalar

    def all(self):
        return self.rows

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def scalars(self):
        return FakeScalarCollection(self.scalar_rows)


class FakeDbSession:
    def __init__(self, results) -> None:
        self.results = list(results)

    async def execute(self, statement):
        return self.results.pop(0)


async def test_match_repository_builds_anonymous_snapshot_from_session_state() -> None:
    game_session_public_id = uuid4()
    game_session = GameSession(
        id=uuid4(),
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="playing",
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
    )
    first_participant = SessionParticipant(
        id=uuid4(),
        session_id=game_session.id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        original_nickname="방장",
        seat_number=1,
        is_uninvited_guest=False,
    )
    second_participant = SessionParticipant(
        id=uuid4(),
        session_id=game_session.id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        original_nickname=None,
        seat_number=2,
        is_uninvited_guest=True,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalars=[first_participant, second_participant]),
            FakeResult(rows=[(first_participant.id, 10), (second_participant.id, -10)]),
        ]
    )
    repository = MatchRepository(db_session)
    service = MatchService(repository, now_provider=lambda: datetime(2026, 6, 13, tzinfo=KST))

    snapshot = await service.get_snapshot(
        game_session_public_id=game_session_public_id,
        participant_id=first_participant.id,
    )

    assert isinstance(snapshot, MatchSnapshotResult)
    assert snapshot.game_session_public_id == game_session_public_id
    assert snapshot.status == "playing"
    assert snapshot.rule_config == {"max_rounds": 8, "turn_time_seconds": 10}
    assert [
        (item.display_name, item.seat_number, item.is_me) for item in snapshot.participants
    ] == [
        ("1번 손님", 1, True),
        ("2번 손님", 2, False),
    ]
    assert snapshot.used_words == []
    assert [(item.display_name, item.score, item.is_me) for item in snapshot.scoreboard] == [
        ("1번 손님", 10, True),
        ("2번 손님", -10, False),
    ]
    assert "방장" not in str(snapshot)
    assert "is_uninvited_guest" not in str(snapshot)


async def test_match_repository_includes_current_turn_from_session_phase() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    game_session = GameSession(
        id=uuid4(),
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="playing",
        rule_config={"max_rounds": 8, "turn_time_seconds": 10},
        current_phase_id=phase_id,
    )
    first_participant = SessionParticipant(
        id=participant_id,
        session_id=game_session.id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        original_nickname="방장",
        seat_number=1,
        is_uninvited_guest=False,
    )
    phase = SessionPhase(
        id=phase_id,
        session_id=game_session.id,
        phase_type="turn",
        phase_number=1,
        actor_participant_id=participant_id,
        condition_payload={"required_start_char": "가"},
        time_limit_seconds=10,
        deadline_at=datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST),
    )
    turn = WordTurn(
        id=uuid4(),
        phase_id=phase_id,
        participant_id=participant_id,
        round_number=1,
        turn_number=3,
        condition_payload={"required_start_char": "가"},
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalars=[first_participant]),
            FakeResult(rows=[]),
            FakeResult(rows=[(phase, turn, first_participant)]),
            FakeResult(
                scalars=[
                    UsedWord(
                        id=uuid4(),
                        session_id=game_session.id,
                        submission_id=uuid4(),
                        round_number=1,
                        normalized_word="사과",
                    )
                ]
            ),
        ]
    )
    repository = MatchRepository(db_session)
    service = MatchService(repository, now_provider=lambda: datetime(2026, 6, 13, tzinfo=KST))

    snapshot = await service.get_snapshot(
        game_session_public_id=game_session_public_id,
        participant_id=first_participant.id,
    )

    assert snapshot.current_round_number == 1
    assert snapshot.current_turn is not None
    assert snapshot.current_turn.phase_id == phase_id
    assert snapshot.current_turn.round_number == 1
    assert snapshot.current_turn.turn_number == 3
    assert snapshot.current_turn.actor_seat_number == 1
    assert snapshot.current_turn.deadline_at == datetime(2026, 6, 13, 0, 0, 10, tzinfo=KST)
    assert snapshot.current_turn.required_start_char == "가"
    assert snapshot.used_words == ["사과"]


async def test_match_repository_includes_voting_deadline_from_current_phase() -> None:
    game_session_public_id = uuid4()
    phase_id = uuid4()
    participant_id = uuid4()
    voting_deadline_at = datetime(2026, 6, 13, 0, 0, 20, tzinfo=KST)
    game_session = GameSession(
        id=uuid4(),
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="voting",
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
        current_phase_id=phase_id,
    )
    participant = SessionParticipant(
        id=participant_id,
        session_id=game_session.id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    voting_phase = SessionPhase(
        id=phase_id,
        session_id=game_session.id,
        phase_type="voting",
        phase_number=5,
        condition_payload={},
        time_limit_seconds=20,
        deadline_at=voting_deadline_at,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalars=[participant]),
            FakeResult(scalars=[]),
            FakeResult(rows=[]),
            FakeResult(scalar=voting_phase),
        ]
    )
    repository = MatchRepository(db_session)
    service = MatchService(repository, now_provider=lambda: datetime(2026, 6, 13, tzinfo=KST))

    snapshot = await service.get_snapshot(
        game_session_public_id=game_session_public_id,
        participant_id=participant_id,
    )

    assert snapshot.current_turn is None
    assert snapshot.voting_deadline_at == voting_deadline_at


async def test_match_repository_includes_result_snapshot_after_session_result() -> None:
    game_session_public_id = uuid4()
    user_participant_id = uuid4()
    ai_participant_id = uuid4()
    game_session = GameSession(
        id=uuid4(),
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="result",
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
    )
    user_participant = SessionParticipant(
        id=user_participant_id,
        session_id=game_session.id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        original_nickname="방장",
        seat_number=1,
        is_uninvited_guest=False,
    )
    ai_participant = SessionParticipant(
        id=ai_participant_id,
        session_id=game_session.id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        original_nickname=None,
        seat_number=2,
        is_uninvited_guest=True,
    )
    user_result = SessionResult(
        id=uuid4(),
        session_id=game_session.id,
        participant_id=user_participant_id,
        final_score=20,
        rank=1,
        is_winner=True,
        revealed_participant_type="user",
        result_payload={"vote_score_delta": 10},
        created_at=datetime(2026, 6, 13, 0, 1, tzinfo=KST),
    )
    ai_result = SessionResult(
        id=uuid4(),
        session_id=game_session.id,
        participant_id=ai_participant_id,
        final_score=-5,
        rank=2,
        is_winner=False,
        revealed_participant_type="ai",
        result_payload={"vote_score_delta": -5},
        created_at=datetime(2026, 6, 13, 0, 1, tzinfo=KST),
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalars=[user_participant, ai_participant]),
            FakeResult(rows=[(user_participant_id, 20), (ai_participant_id, -5)]),
            FakeResult(
                rows=[
                    (user_participant_id, "word_accepted", 10),
                    (user_participant_id, "vote_correct", 10),
                    (ai_participant_id, "voted_as_ai", -5),
                ]
            ),
            FakeResult(rows=[(user_result, user_participant), (ai_result, ai_participant)]),
        ]
    )
    repository = MatchRepository(db_session)
    service = MatchService(repository, now_provider=lambda: datetime(2026, 6, 13, tzinfo=KST))

    snapshot = await service.get_snapshot(
        game_session_public_id=game_session_public_id,
        participant_id=user_participant_id,
    )

    assert [
        (
            result.display_name,
            result.seat_number,
            result.revealed_participant_type,
            result.final_score,
            result.rank,
            result.is_winner,
            result.vote_score_delta,
            result.score_breakdown.word_score,
            result.score_breakdown.vote_score,
            result.is_me,
        )
        for result in snapshot.results
    ] == [
        ("1번 손님", 1, "user", 20, 1, True, 10, 10, 10, True),
        ("2번 손님", 2, "ai", -5, 2, False, -5, 0, -5, False),
    ]
    assert "방장" not in str(snapshot)
