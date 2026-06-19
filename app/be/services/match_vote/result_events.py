from app.be.services.match_progress import MatchBroadcastEvent
from app.be.services.match_vote.constants import RESULT_PUBLISHED_MESSAGE_TYPE
from app.be.services.match_vote.records import ScoreBreakdownPayload, VoteSubmissionRecord


def score_breakdown_to_payload(breakdown: ScoreBreakdownPayload) -> dict:
    """점수 breakdown record를 WebSocket JSON payload로 변환합니다."""
    return {
        "word_score": breakdown.word_score,
        "vote_score": breakdown.vote_score,
        "penalty_score": breakdown.penalty_score,
        "items": [
            {
                "reason": item.reason,
                "score_delta": item.score_delta,
            }
            for item in breakdown.items
        ],
    }


def result_event_from_vote_record(record: VoteSubmissionRecord) -> MatchBroadcastEvent:
    """투표 결과 record를 WebSocket 결과 publish event payload로 변환합니다."""
    return MatchBroadcastEvent(
        game_session_public_id=record.accepted.game_session_public_id,
        message={
            "type": RESULT_PUBLISHED_MESSAGE_TYPE,
            "payload": {
                "event_sequence": record.result_event_sequence,
                "results": [
                    {
                        "participant": {
                            "display_name": result.display_name,
                            "seat_number": result.seat_number,
                            "revealed_participant_type": result.revealed_participant_type,
                        },
                        "final_score": result.final_score,
                        "rank": result.rank,
                        "is_winner": result.is_winner,
                        "vote_score_delta": result.vote_score_delta,
                        "score_breakdown": score_breakdown_to_payload(result.score_breakdown),
                    }
                    for result in record.result or []
                ],
                "created_at": record.result_created_at,
                "server_time": record.result_created_at,
            },
        },
    )
