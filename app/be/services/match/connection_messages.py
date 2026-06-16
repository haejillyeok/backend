from typing import Any

from app.be.services.match.connection_records import MatchConnection
from app.be.services.match.snapshots import MatchSnapshotResult
from app.shared.core.timezone import to_kst_isoformat


MatchMessage = dict[str, Any]


def match_connected_message(connection: MatchConnection) -> MatchMessage:
    """match 연결 직후 참가자 순서를 알려주는 `match.connected` event를 조립합니다."""
    return {
        "type": "match.connected",
        "payload": {
            "game_session_public_id": connection.game_session_public_id,
            "participant": {
                "display_name": connection.participant.display_name,
                "seat_number": connection.participant.seat_number,
            },
        },
    }


def match_snapshot_message(snapshot: MatchSnapshotResult) -> MatchMessage:
    """현재 match 화면 복구용 `match.snapshot` event를 조립합니다."""
    return {
        "type": "match.snapshot",
        "payload": {
            "game_session_public_id": snapshot.game_session_public_id,
            "status": snapshot.status,
            "rule_config": snapshot.rule_config,
            "participants": [
                {
                    "display_name": participant.display_name,
                    "seat_number": participant.seat_number,
                    "is_me": participant.is_me,
                }
                for participant in snapshot.participants
            ],
            "current_round_number": snapshot.current_round_number,
            "current_turn": (
                {
                    "phase_id": snapshot.current_turn.phase_id,
                    "round_number": snapshot.current_turn.round_number,
                    "turn_number": snapshot.current_turn.turn_number,
                    "actor_seat_number": snapshot.current_turn.actor_seat_number,
                    "started_at": to_kst_isoformat(snapshot.current_turn.started_at),
                    "deadline_at": (
                        to_kst_isoformat(snapshot.current_turn.deadline_at)
                        if snapshot.current_turn.deadline_at
                        else None
                    ),
                    "required_start_char": snapshot.current_turn.required_start_char,
                }
                if snapshot.current_turn
                else None
            ),
            "used_words": snapshot.used_words,
            "scoreboard": [
                {
                    "display_name": score.display_name,
                    "seat_number": score.seat_number,
                    "score": score.score,
                    "is_me": score.is_me,
                }
                for score in snapshot.scoreboard
            ],
            "server_time": to_kst_isoformat(snapshot.server_time),
            "voting_deadline_at": (
                to_kst_isoformat(snapshot.voting_deadline_at)
                if snapshot.voting_deadline_at
                else None
            ),
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
                    "is_me": result.is_me,
                }
                for result in snapshot.results
            ],
        },
    }
