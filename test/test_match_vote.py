from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.be.models.game import (
    GameEvent,
    GameSession,
    ParticipantAction,
    Room,
    ScoreLedger,
    SessionParticipant,
    SessionPhase,
    SessionResult,
    Vote,
)
from app.be.repository.match_vote import MatchVoteRepository
from app.be.services.match_vote import (
    MatchVoteService,
)
from app.shared.core.exceptions import AppException


KST = ZoneInfo("Asia/Seoul")


class FakeScalarCollection:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeResult:
    def __init__(self, *, scalar=None, scalars=None, rows=None) -> None:
        self.scalar = scalar
        self.scalar_rows = scalars or []
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar

    def scalars(self):
        return FakeScalarCollection(self.scalar_rows)

    def all(self):
        return self.rows


class FakeDbSession:
    def __init__(self, results=None) -> None:
        self.results = list(results or [])
        self.added = []
        self.flush_count = 0
        self.committed = False

    async def execute(self, statement):
        return self.results.pop(0)

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    async def commit(self) -> None:
        self.committed = True


class LateVoteFakeDbSession:
    def __init__(
        self,
        *,
        game_session: GameSession,
        voting_phase: SessionPhase,
        voter: SessionParticipant,
        target: SessionParticipant,
    ) -> None:
        self.game_session = game_session
        self.voting_phase = voting_phase
        self.voter = voter
        self.target = target
        self.added = []

    async def execute(self, statement):
        statement_text = str(statement)
        if "game_sessions" in statement_text:
            return FakeResult(scalar=self.game_session)
        if "session_phases" in statement_text:
            return FakeResult(scalar=self.voting_phase)
        if (
            "session_participants" in statement_text
            and "session_participants.seat_number =" in statement_text
        ):
            return FakeResult(scalar=self.target)
        if "session_participants" in statement_text:
            return FakeResult(scalar=self.voter)
        if "votes" in statement_text:
            return FakeResult(scalars=[])
        if "score_ledger" in statement_text:
            return FakeResult(rows=[])
        if "participant_actions" in statement_text:
            return FakeResult(scalar=0)
        if "game_events" in statement_text:
            return FakeResult(scalar=0)
        raise AssertionError(f"unexpected statement: {statement_text}")

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass


async def test_match_vote_service_orchestrates_vote_submission_repository_steps() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    voter_participant_id = uuid4()
    target_participant_id = uuid4()
    voted_at = datetime(2026, 6, 13, tzinfo=KST)
    game_session = GameSession(
        id=session_id,
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="voting",
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
        current_phase_id=phase_id,
    )
    voter = SessionParticipant(
        id=voter_participant_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    target = SessionParticipant(
        id=target_participant_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=True,
    )
    waiting_voter = SessionParticipant(
        id=uuid4(),
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="3번 손님",
        seat_number=3,
        is_uninvited_guest=False,
    )
    action = ParticipantAction(
        id=uuid4(),
        session_id=session_id,
        phase_id=None,
        participant_id=voter_participant_id,
        action_type="vote_submit",
        action_number=1,
        attempt_number=1,
        payload={"target_seat_number": target.seat_number},
        submitted_at=voted_at,
        response_ms=None,
        is_valid=True,
    )
    vote = Vote(
        id=uuid4(),
        session_id=session_id,
        voter_participant_id=voter_participant_id,
        target_participant_id=target_participant_id,
        voted_at=voted_at,
        is_correct=True,
    )
    accepted_event = GameEvent(
        id=uuid4(),
        session_id=session_id,
        phase_id=None,
        participant_id=voter_participant_id,
        action_id=action.id,
        sequence=2,
        event_type="vote.accepted",
        payload={
            "voter": {
                "display_name": voter.display_name,
                "seat_number": voter.seat_number,
            },
            "submitted_vote_count": 1,
            "required_vote_count": 2,
        },
        created_at=voted_at,
    )

    class FakeRepository:
        def __init__(self) -> None:
            self.calls = []

        async def get_game_session_for_update(self, public_id):
            self.calls.append("get_game_session_for_update")
            assert public_id == game_session_public_id
            return game_session

        async def get_voting_phase(self, *, session_id, phase_id):
            self.calls.append("get_voting_phase")
            assert session_id == game_session.id
            assert phase_id == game_session.current_phase_id
            return None

        async def get_participant(self, *, session_id, participant_id):
            self.calls.append("get_participant")
            assert session_id == game_session.id
            assert participant_id == voter_participant_id
            return voter

        async def get_participant_by_seat_number(self, *, session_id, seat_number):
            self.calls.append("get_participant_by_seat_number")
            assert session_id == game_session.id
            assert seat_number == target.seat_number
            return target

        async def list_participants(self, session_id):
            self.calls.append("list_participants")
            assert session_id == game_session.id
            return [voter, target, waiting_voter]

        async def list_votes(self, session_id):
            self.calls.append("list_votes")
            assert session_id == game_session.id
            return []

        async def get_score_totals(self, session_id):
            self.calls.append("get_score_totals")
            assert session_id == game_session.id
            return {}

        async def get_next_action_number(self, session_id):
            self.calls.append("get_next_action_number")
            assert session_id == game_session.id
            return 1

        async def create_vote_submit_action(self, **kwargs):
            self.calls.append("create_vote_submit_action")
            assert kwargs["session_id"] == game_session.id
            assert kwargs["voter"] is voter
            assert kwargs["target"] is target
            assert kwargs["now"] == voted_at
            return action

        async def create_vote(self, **kwargs):
            self.calls.append("create_vote")
            assert kwargs["session_id"] == game_session.id
            assert kwargs["voter"] is voter
            assert kwargs["target"] is target
            assert kwargs["is_correct"] is True
            assert kwargs["now"] == voted_at
            return vote

        async def flush(self):
            self.calls.append("flush")

        async def get_next_event_sequence(self, session_id):
            self.calls.append("get_next_event_sequence")
            assert session_id == game_session.id
            return 2

        async def create_vote_accepted_event(self, **kwargs):
            self.calls.append("create_vote_accepted_event")
            assert kwargs["session_id"] == game_session.id
            assert kwargs["voter"] is voter
            assert kwargs["action"] is action
            assert kwargs["event_sequence"] == 2
            assert kwargs["submitted_vote_count"] == 1
            assert kwargs["required_vote_count"] == 2
            assert kwargs["now"] == voted_at
            return accepted_event

        async def commit(self):
            self.calls.append("commit")

    repository = FakeRepository()
    service = MatchVoteService(repository)

    events = await service.submit_vote(
        game_session_public_id=game_session_public_id,
        voter_participant_id=voter_participant_id,
        target_seat_number=target.seat_number,
        now=voted_at,
    )

    assert repository.calls == [
        "get_game_session_for_update",
        "get_voting_phase",
        "get_participant",
        "get_participant_by_seat_number",
        "list_participants",
        "list_votes",
        "get_score_totals",
        "get_next_action_number",
        "create_vote_submit_action",
        "create_vote",
        "flush",
        "get_next_event_sequence",
        "create_vote_accepted_event",
        "flush",
        "commit",
    ]
    assert events[0].message["payload"]["submitted_vote_count"] == 1
    assert events[0].message["payload"]["required_vote_count"] == 2


async def test_match_vote_service_publishes_result_when_all_users_voted() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    voter_id = uuid4()
    first_voter_id = uuid4()
    ai_id = uuid4()
    voted_at = datetime(2026, 6, 13, tzinfo=KST)
    game_session = GameSession(
        id=session_id,
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="voting",
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
    )
    room = Room(
        id=game_session.room_id,
        public_id=uuid4(),
        owner_user_id=uuid4(),
        name="첫 객실",
        game_type="word_chain",
        status="playing",
        max_players=2,
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
    )
    first_voter = SessionParticipant(
        id=first_voter_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    voter = SessionParticipant(
        id=voter_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=False,
    )
    ai = SessionParticipant(
        id=ai_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="3번 손님",
        seat_number=3,
        is_uninvited_guest=True,
    )
    existing_vote = Vote(
        id=uuid4(),
        session_id=session_id,
        voter_participant_id=first_voter_id,
        target_participant_id=ai_id,
        voted_at=voted_at,
        is_correct=True,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=voter),
            FakeResult(scalar=first_voter),
            FakeResult(scalars=[first_voter, voter, ai]),
            FakeResult(scalars=[existing_vote]),
            FakeResult(rows=[(first_voter_id, 10)]),
            FakeResult(scalar=2),
            FakeResult(scalar=3),
            FakeResult(scalar=room),
        ]
    )
    repository = MatchVoteRepository(db_session)
    service = MatchVoteService(repository)

    events = await service.submit_vote(
        game_session_public_id=game_session_public_id,
        voter_participant_id=voter_id,
        target_seat_number=1,
        now=voted_at,
    )

    action = db_session.added[0]
    vote = db_session.added[1]
    accepted_event = db_session.added[2]
    score_ledgers = [item for item in db_session.added if isinstance(item, ScoreLedger)]
    session_results = [item for item in db_session.added if isinstance(item, SessionResult)]
    result_event = db_session.added[-1]
    assert isinstance(action, ParticipantAction)
    assert action.action_type == "vote_submit"
    assert action.participant_id == voter_id
    assert isinstance(vote, Vote)
    assert vote.voter_participant_id == voter_id
    assert vote.target_participant_id == first_voter_id
    assert vote.is_correct is False
    assert isinstance(accepted_event, GameEvent)
    assert accepted_event.event_type == "vote.accepted"
    assert accepted_event.payload["submitted_vote_count"] == 2
    assert len(score_ledgers) == 3
    assert sorted(
        (ledger.participant_id, ledger.score_delta) for ledger in score_ledgers
    ) == sorted(
        [
            (first_voter_id, 10),
            (voter_id, -5),
            (ai_id, -5),
        ]
    )
    assert len(session_results) == 3
    result_by_participant = {result.participant_id: result for result in session_results}
    assert result_by_participant[first_voter_id].final_score == 20
    assert result_by_participant[first_voter_id].rank == 1
    assert result_by_participant[first_voter_id].is_winner is True
    assert result_by_participant[voter_id].final_score == -5
    assert result_by_participant[ai_id].final_score == -5
    assert isinstance(result_event, GameEvent)
    assert result_event.event_type == "result.published"
    assert game_session.status == "result"
    assert game_session.ended_at == voted_at
    assert room.status == "waiting"
    assert [event.message["type"] for event in events] == [
        "match.vote.accepted",
        "match.result.published",
    ]
    assert events[0].message["payload"]["submitted_vote_count"] == 2
    assert events[1].message["payload"]["event_sequence"] == 5
    assert [
        item["participant"]["seat_number"] for item in events[1].message["payload"]["results"]
    ] == [
        1,
        2,
        3,
    ]
    assert db_session.committed is True


async def test_match_vote_service_rejects_vote_after_voting_deadline() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    voter_id = uuid4()
    target_id = uuid4()
    deadline_at = datetime(2026, 6, 13, 0, 0, 20, tzinfo=KST)
    submitted_at = datetime(2026, 6, 13, 0, 0, 21, tzinfo=KST)
    game_session = GameSession(
        id=session_id,
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="voting",
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
        current_phase_id=phase_id,
    )
    voting_phase = SessionPhase(
        id=phase_id,
        session_id=session_id,
        phase_type="voting",
        phase_number=4,
        condition_payload={},
        time_limit_seconds=20,
        deadline_at=deadline_at,
    )
    voter = SessionParticipant(
        id=voter_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    target = SessionParticipant(
        id=target_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=True,
    )
    db_session = LateVoteFakeDbSession(
        game_session=game_session,
        voting_phase=voting_phase,
        voter=voter,
        target=target,
    )
    repository = MatchVoteRepository(db_session)
    service = MatchVoteService(repository)

    with pytest.raises(AppException) as exc_info:
        await service.submit_vote(
            game_session_public_id=game_session_public_id,
            voter_participant_id=voter_id,
            target_seat_number=2,
            now=submitted_at,
        )

    assert exc_info.value.details == {"reason": "vote_deadline_exceeded"}
    assert db_session.added == []


async def test_match_vote_repository_returns_none_when_session_is_missing() -> None:
    db_session = FakeDbSession([FakeResult(scalar=None)])
    repository = MatchVoteRepository(db_session)

    game_session = await repository.get_game_session_for_update(uuid4())

    assert game_session is None


async def test_match_vote_service_rejects_missing_session() -> None:
    db_session = FakeDbSession([FakeResult(scalar=None)])
    repository = MatchVoteRepository(db_session)
    service = MatchVoteService(repository)

    with pytest.raises(AppException) as exc_info:
        await service.submit_vote(
            game_session_public_id=uuid4(),
            voter_participant_id=uuid4(),
            target_seat_number=1,
            now=datetime(2026, 6, 13, tzinfo=KST),
        )

    assert exc_info.value.details == {"reason": "game_session_not_found"}
    assert db_session.added == []


async def test_match_vote_service_rejects_missing_target_participant() -> None:
    session_id = uuid4()
    phase_id = uuid4()
    game_session = GameSession(
        id=session_id,
        public_id=uuid4(),
        room_id=uuid4(),
        game_type="word_chain",
        status="voting",
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
        current_phase_id=phase_id,
    )
    voter = SessionParticipant(
        id=uuid4(),
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalar=None),
            FakeResult(scalar=voter),
            FakeResult(scalar=None),
        ]
    )
    repository = MatchVoteRepository(db_session)
    service = MatchVoteService(repository)

    with pytest.raises(AppException) as exc_info:
        await service.submit_vote(
            game_session_public_id=game_session.public_id,
            voter_participant_id=voter.id,
            target_seat_number=2,
            now=datetime(2026, 6, 13, tzinfo=KST),
        )

    assert exc_info.value.details == {"reason": "target_participant_not_found"}
    assert db_session.added == []


async def test_match_vote_service_publishes_result_on_vote_timeout() -> None:
    session_id = uuid4()
    game_session_public_id = uuid4()
    first_voter_id = uuid4()
    missing_voter_id = uuid4()
    ai_id = uuid4()
    timed_out_at = datetime(2026, 6, 13, tzinfo=KST)
    game_session = GameSession(
        id=session_id,
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="voting",
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
    )
    room = Room(
        id=game_session.room_id,
        public_id=uuid4(),
        owner_user_id=uuid4(),
        name="첫 객실",
        game_type="word_chain",
        status="playing",
        max_players=2,
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
    )
    first_voter = SessionParticipant(
        id=first_voter_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="1번 손님",
        seat_number=1,
        is_uninvited_guest=False,
    )
    missing_voter = SessionParticipant(
        id=missing_voter_id,
        session_id=session_id,
        user_id=uuid4(),
        participant_type="user",
        display_name="2번 손님",
        seat_number=2,
        is_uninvited_guest=False,
    )
    ai = SessionParticipant(
        id=ai_id,
        session_id=session_id,
        user_id=None,
        participant_type="ai",
        display_name="3번 손님",
        seat_number=3,
        is_uninvited_guest=True,
    )
    existing_vote = Vote(
        id=uuid4(),
        session_id=session_id,
        voter_participant_id=first_voter_id,
        target_participant_id=ai_id,
        voted_at=timed_out_at,
        is_correct=True,
    )
    db_session = FakeDbSession(
        [
            FakeResult(scalar=game_session),
            FakeResult(scalars=[first_voter, missing_voter, ai]),
            FakeResult(scalars=[existing_vote]),
            FakeResult(rows=[]),
            FakeResult(scalar=4),
            FakeResult(scalar=room),
        ]
    )
    repository = MatchVoteRepository(db_session)
    service = MatchVoteService(repository)

    events = await service.timeout_vote(
        game_session_public_id=game_session_public_id,
        now=timed_out_at,
    )

    timeout_event = db_session.added[0]
    score_ledgers = [item for item in db_session.added if isinstance(item, ScoreLedger)]
    session_results = [item for item in db_session.added if isinstance(item, SessionResult)]
    result_event = db_session.added[-1]
    assert isinstance(timeout_event, GameEvent)
    assert timeout_event.event_type == "vote.timeout"
    assert timeout_event.payload["submitted_vote_count"] == 1
    assert timeout_event.payload["required_vote_count"] == 2
    assert len(score_ledgers) == 2
    assert sorted(
        (ledger.participant_id, ledger.score_delta) for ledger in score_ledgers
    ) == sorted(
        [
            (first_voter_id, 10),
            (ai_id, -5),
        ]
    )
    assert len(session_results) == 3
    result_by_participant = {result.participant_id: result for result in session_results}
    assert result_by_participant[first_voter_id].final_score == 10
    assert result_by_participant[missing_voter_id].final_score == 0
    assert result_by_participant[ai_id].final_score == -5
    assert isinstance(result_event, GameEvent)
    assert result_event.event_type == "result.published"
    assert game_session.status == "result"
    assert room.status == "waiting"
    assert [event.message["type"] for event in events] == [
        "match.vote.timeout",
        "match.result.published",
    ]
    assert events[0].message["payload"]["submitted_vote_count"] == 1
    assert events[1].message["payload"]["event_sequence"] == 6
    assert db_session.committed is True


async def test_match_vote_service_ignores_stale_vote_timeout_after_result() -> None:
    game_session_public_id = uuid4()
    game_session = GameSession(
        id=uuid4(),
        public_id=game_session_public_id,
        room_id=uuid4(),
        game_type="word_chain",
        status="result",
        rule_config={"max_rounds": 1, "turn_time_seconds": 10},
    )
    db_session = FakeDbSession([FakeResult(scalar=game_session)])
    repository = MatchVoteRepository(db_session)
    service = MatchVoteService(repository)

    events = await service.timeout_vote(
        game_session_public_id=game_session_public_id,
        now=datetime(2026, 6, 13, tzinfo=KST),
    )

    assert events == []
    assert db_session.added == []
