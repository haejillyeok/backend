# Final Score Breakdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add score breakdown data for `32. 최종 점수 계산` so the frontend can explain final scores instead of showing only totals.

**Architecture:** Use `ScoreLedger` as the source of truth. Keep final result totals unchanged, and add a read model that groups ledger entries by participant and reason for result events and reconnect snapshots.

**Tech Stack:** SQLAlchemy async repository, match vote/result services, pytest.

---

## Request To Start This Work

Ask: `32. 최종 점수 계산 작업 진행해줘`

## File Structure

- Modify `app/be/services/match_vote/records.py`: add score breakdown payload records.
- Modify `app/be/services/match_vote/result_policy.py`: no total-rule change unless tests prove needed.
- Modify `app/be/services/match_vote/service.py`: attach breakdown after result calculation.
- Modify `app/be/repository/match_vote/repository.py`: list score ledger grouped by participant/reason.
- Modify `app/be/repository/match/repository.py`: include breakdown in result snapshots.
- Modify `app/be/services/match/snapshots.py`: add `score_breakdown`.
- Modify `app/be/services/match/connection_messages.py`: serialize breakdown.
- Test `test/test_match_vote.py`: result event breakdown.
- Test `test/test_match_repository.py`: reconnect snapshot breakdown.
- Modify docs: `app/be/api/docs/ws-api.md`, `llm-wiki/wiki/realtime-websocket.md`, `llm-wiki/wiki/sunset-game-domain.md`.

## Contract

Each result participant should include:

```json
{
  "final_score": 20,
  "score_breakdown": {
    "word_score": 10,
    "vote_score": 10,
    "penalty_score": 0,
    "items": [
      {"reason": "word_accepted", "score_delta": 10},
      {"reason": "vote_correct", "score_delta": 10}
    ]
  }
}
```

Reason grouping:

- `word_accepted`: word score
- `vote_correct`, `vote_wrong`, `voted_as_ai`: vote score
- other negative reasons: penalty score
- unknown positive reasons: word score until a new product category is defined

## Task 1: Define Breakdown Records

**Files:**
- Modify: `app/be/services/match_vote/records.py`
- Test: `test/test_match_vote.py`

- [x] **Step 1: Write failing record import test**

```python
def test_match_vote_records_expose_score_breakdown_payloads() -> None:
    item = ScoreBreakdownItem(reason="word_accepted", score_delta=10)
    breakdown = ScoreBreakdownPayload(
        word_score=10,
        vote_score=0,
        penalty_score=0,
        items=[item],
    )

    assert breakdown.items[0].reason == "word_accepted"
    assert breakdown.word_score == 10
```

- [x] **Step 2: Run test**

Run:

```bash
.venv/bin/python -m pytest test/test_match_vote.py::test_match_vote_records_expose_score_breakdown_payloads -q --no-cov
```

Expected: FAIL because records do not exist.

- [x] **Step 3: Add dataclasses**

```python
@dataclass(frozen=True)
class ScoreBreakdownItem:
    reason: str
    score_delta: int


@dataclass(frozen=True)
class ScoreBreakdownPayload:
    word_score: int
    vote_score: int
    penalty_score: int
    items: list[ScoreBreakdownItem] = field(default_factory=list)
```

- [x] **Step 4: Run test**

Expected: PASS.

## Task 2: Query Score Ledger Breakdown

**Files:**
- Modify: `app/be/services/match_vote/repository_protocol.py`
- Modify: `app/be/repository/match_vote/repository.py`
- Test: `test/test_be_repositories.py`

- [x] **Step 1: Write failing repository test**

Add `test_match_vote_repository_lists_score_breakdown_items`.

```python
async def test_match_vote_repository_lists_score_breakdown_items() -> None:
    session_id = uuid4()
    participant_id = uuid4()
    rows = [
        (participant_id, "word_accepted", 10),
        (participant_id, "vote_correct", 10),
    ]
    db_session = FakeDbSession([FakeResult(rows=rows)])
    repository = MatchVoteRepository(db_session)

    result = await repository.list_score_breakdown_items(session_id)

    assert result[participant_id][0].reason == "word_accepted"
    assert result[participant_id][0].score_delta == 10
    assert result[participant_id][1].reason == "vote_correct"
```

- [x] **Step 2: Run test**

Run:

```bash
.venv/bin/python -m pytest test/test_be_repositories.py::test_match_vote_repository_lists_score_breakdown_items -q --no-cov
```

Expected: FAIL because method is missing.

- [x] **Step 3: Implement query**

Select `ScoreLedger.participant_id`, `ScoreLedger.reason`, `ScoreLedger.score_delta` filtered by `session_id`, ordered by participant and `created_at`.

## Task 3: Attach Breakdown To Result Event

**Files:**
- Modify: `app/be/services/match_vote/service.py`
- Modify: `app/be/services/match_vote/result_events.py`
- Test: `test/test_match_vote.py`

- [x] **Step 1: Write failing result event test**

Assert `match.result.published.payload.results[0].score_breakdown.word_score == 10` and `vote_score == 10`.

- [x] **Step 2: Implement grouping policy**

Add a small helper:

```python
def build_score_breakdown(items: list[ScoreBreakdownItem]) -> ScoreBreakdownPayload:
    word_score = 0
    vote_score = 0
    penalty_score = 0
    for item in items:
        if item.reason in {"vote_correct", "vote_wrong", "voted_as_ai"}:
            vote_score += item.score_delta
        elif item.score_delta < 0:
            penalty_score += item.score_delta
        else:
            word_score += item.score_delta
    return ScoreBreakdownPayload(
        word_score=word_score,
        vote_score=vote_score,
        penalty_score=penalty_score,
        items=items,
    )
```

- [x] **Step 3: Serialize breakdown**

Add `score_breakdown` beside `vote_score_delta`.

## Task 4: Reconnect Snapshot Breakdown

**Files:**
- Modify: `app/be/services/match/snapshots.py`
- Modify: `app/be/repository/match/repository.py`
- Modify: `app/be/services/match/connection_messages.py`
- Test: `test/test_match_repository.py`

- [x] **Step 1: Write failing snapshot test**

Assert result snapshot after `status="result"` includes `score_breakdown`.

- [x] **Step 2: Implement repository read**

Reuse the same reason grouping as result event. Keep result event and reconnect snapshot shapes aligned.

## Task 5: Documentation And Verification

**Files:**
- Modify: `app/be/api/docs/ws-api.md`
- Modify: `llm-wiki/wiki/realtime-websocket.md`
- Modify: `llm-wiki/wiki/sunset-game-domain.md`
- Modify: `llm-wiki/log.md`

- [x] **Step 1: Document score breakdown**

Add `score_breakdown.word_score`, `score_breakdown.vote_score`, `score_breakdown.penalty_score`, and `items[]`.

- [x] **Step 2: Run tests**

Run:

```bash
.venv/bin/python -m pytest test/test_match_vote.py test/test_match_repository.py test/test_be_repositories.py -q
.venv/bin/python -m pytest -q
```

Expected: PASS.
