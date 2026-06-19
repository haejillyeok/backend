# Result Announcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `31. 결과 발표` reliable by publishing a result event that includes winner, AI reveal, and per-participant display data in a frontend-friendly shape.

**Architecture:** Keep result calculation in `MatchVoteService`, but isolate event shaping in `match_vote/result_events.py`. Do not expose original user IDs or original nicknames unless the product explicitly decides to reveal them.

**Tech Stack:** FastAPI WebSocket, match vote service, pytest.

---

## Request To Start This Work

Ask: `31. 결과 발표 작업 진행해줘`

## File Structure

- Modify `app/be/services/match_vote/records.py`: add event fields only if needed.
- Modify `app/be/services/match_vote/result_events.py`: shape `match.result.published`.
- Modify `app/be/services/match/connection_messages.py`: ensure reconnect snapshot matches event result shape.
- Test `test/test_match_vote.py`: result event payload.
- Test `test/test_match_repository.py`: result snapshot after reconnect.
- Modify `app/be/api/docs/ws-api.md`, `llm-wiki/wiki/realtime-websocket.md`.

## Contract

`match.result.published.payload.results[]` should include:

```json
{
  "participant": {
    "display_name": "1번 손님",
    "seat_number": 1,
    "revealed_participant_type": "user"
  },
  "final_score": 20,
  "rank": 1,
  "is_winner": true,
  "vote_score_delta": 10
}
```

Frontend can render:

- winner banner from `is_winner`
- AI reveal from `revealed_participant_type == "ai"`
- ranking from `rank`
- anonymous names from `participant.display_name`

## Task 1: Lock Result Event Shape

**Files:**
- Modify: `test/test_match_vote.py`
- Modify: `app/be/services/match_vote/result_events.py`

- [ ] **Step 1: Write event payload test**

Add a test named `test_result_event_publishes_winner_and_ai_reveal_fields`.

```python
def test_result_event_publishes_winner_and_ai_reveal_fields() -> None:
    record = VoteSubmissionRecord(
        accepted=VoteAcceptedRecord(
            game_session_public_id=uuid4(),
            event_sequence=7,
            voter_display_name="1번 손님",
            voter_seat_number=1,
            submitted_vote_count=2,
            required_vote_count=2,
            created_at=datetime.now(KST),
        ),
        result=[
            MatchResultParticipantPayload(
                display_name="1번 손님",
                seat_number=1,
                revealed_participant_type="user",
                final_score=20,
                rank=1,
                is_winner=True,
                vote_score_delta=10,
            ),
            MatchResultParticipantPayload(
                display_name="2번 손님",
                seat_number=2,
                revealed_participant_type="ai",
                final_score=-5,
                rank=2,
                is_winner=False,
                vote_score_delta=-5,
            ),
        ],
        result_event_sequence=8,
        result_created_at=datetime.now(KST),
    )

    event = result_event_from_vote_record(record)

    payload = event.message["payload"]
    assert payload["event_sequence"] == 8
    assert payload["results"][0]["is_winner"] is True
    assert payload["results"][0]["participant"]["revealed_participant_type"] == "user"
    assert payload["results"][1]["participant"]["revealed_participant_type"] == "ai"
```

- [ ] **Step 2: Run test**

Run:

```bash
.venv/bin/python -m pytest test/test_match_vote.py::test_result_event_publishes_winner_and_ai_reveal_fields -q --no-cov
```

Expected: PASS if the current event already matches the desired contract. If it fails, update `result_event_from_vote_record` only enough to pass.

## Task 2: Lock Reconnect Snapshot Shape

**Files:**
- Modify: `test/test_match_repository.py`
- Modify: `app/be/services/match/connection_messages.py`

- [ ] **Step 1: Write snapshot serialization test**

Add a test named `test_match_snapshot_result_shape_matches_result_event_shape`.

```python
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
    assert result["is_me"] is False
```

- [ ] **Step 2: Run test**

Run:

```bash
.venv/bin/python -m pytest test/test_match_repository.py::test_match_snapshot_result_shape_matches_result_event_shape -q --no-cov
```

Expected: PASS if reconnect shape is already adequate. If it fails, update `match_snapshot_message`.

## Task 3: Result Screen Convenience Fields

**Files:**
- Modify: `app/be/services/match_vote/result_events.py`
- Modify: `app/be/services/match/connection_messages.py`
- Test: `test/test_match_vote.py`

- [ ] **Step 1: Decide if frontend needs convenience fields**

Use existing fields by default. Add root `winners` only if frontend requests a root-level winner list. If adding it, shape it as:

```json
"winners": [
  {"display_name": "1번 손님", "seat_number": 1}
]
```

- [ ] **Step 2: Write failing test only if adding `winners`**

Expected failure: missing `payload.winners`.

- [ ] **Step 3: Implement only the tested convenience field**

Build `winners` from `result.is_winner`.

## Task 4: Documentation And Verification

**Files:**
- Modify: `app/be/api/docs/ws-api.md`
- Modify: `llm-wiki/wiki/realtime-websocket.md`
- Modify: `llm-wiki/log.md`

- [ ] **Step 1: Document result event**

Show `participant.revealed_participant_type`, `final_score`, `rank`, `is_winner`, and `vote_score_delta`.

- [ ] **Step 2: Run verification**

Run:

```bash
.venv/bin/python -m pytest test/test_match_vote.py test/test_match_repository.py -q
.venv/bin/python -m pytest -q
```

Expected: PASS.

