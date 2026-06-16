from datetime import datetime, timedelta

from app.be.models.game import GameSession, SessionParticipant, SessionPhase, WordTurn
from app.be.schemas.game_enum import GameSessionStatus
from app.be.services.match_progress.constants import ROUND_START_DELAY_SECONDS
from app.be.services.match_progress.records import MatchTurnEventPayload
from app.be.services.match_progress.round_transition_drafts import RoundTransitionDraft
from app.shared.core.identifiers import generate_uuid_v7


class MatchProgressRoundTransitionPolicy:
    """턴 종료 뒤 다음 라운드 또는 투표 phase 전환 규칙을 계산합니다."""

    def build_round_end_transition(
        self,
        *,
        game_session: GameSession,
        phase: SessionPhase,
        turn: WordTurn,
        next_participant: SessionParticipant,
        round_start_char: str | None,
        now: datetime,
    ) -> RoundTransitionDraft:
        """현재 turn 종료 후 이어질 phase, turn, public payload를 만듭니다."""
        max_rounds = int(game_session.rule_config.get("max_rounds", 8))
        if turn.round_number >= max_rounds:
            vote_time_seconds = int(game_session.rule_config.get("vote_time_seconds", 20))
            voting_phase = SessionPhase(
                id=generate_uuid_v7(),
                session_id=game_session.id,
                phase_type="voting",
                phase_number=phase.phase_number + 1,
                actor_participant_id=None,
                condition_payload={},
                time_limit_seconds=vote_time_seconds,
                started_at=now,
                deadline_at=now + timedelta(seconds=vote_time_seconds),
            )
            return RoundTransitionDraft(
                phase=voting_phase,
                turn=None,
                payload={
                    "next_status": GameSessionStatus.VOTING.value,
                    "voting_deadline_at": voting_phase.deadline_at.isoformat(),
                },
                next_turn=None,
                next_status=GameSessionStatus.VOTING.value,
                voting_deadline_at=voting_phase.deadline_at,
            )

        turn_time_seconds = int(game_session.rule_config.get("turn_time_seconds", 10))
        next_round_started_at = now + timedelta(seconds=ROUND_START_DELAY_SECONDS)
        next_phase = SessionPhase(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_type="turn",
            phase_number=phase.phase_number + 1,
            actor_participant_id=next_participant.id,
            condition_payload={"required_start_char": round_start_char},
            time_limit_seconds=turn_time_seconds,
            started_at=next_round_started_at,
            deadline_at=next_round_started_at + timedelta(seconds=turn_time_seconds),
        )
        next_turn = WordTurn(
            id=generate_uuid_v7(),
            phase_id=next_phase.id,
            participant_id=next_participant.id,
            round_number=turn.round_number + 1,
            turn_number=1,
            condition_payload=next_phase.condition_payload,
        )
        next_turn_payload = {
            "phase_id": str(next_phase.id),
            "round_number": next_turn.round_number,
            "turn_number": next_turn.turn_number,
            "actor_seat_number": next_participant.seat_number,
            "started_at": next_phase.started_at.isoformat(),
            "deadline_at": next_phase.deadline_at.isoformat(),
            "required_start_char": round_start_char,
        }
        return RoundTransitionDraft(
            phase=next_phase,
            turn=next_turn,
            payload={"next_turn": next_turn_payload},
            next_turn=MatchTurnEventPayload(
                phase_id=next_phase.id,
                round_number=next_turn.round_number,
                turn_number=next_turn.turn_number,
                actor_seat_number=next_participant.seat_number,
                started_at=next_phase.started_at,
                deadline_at=next_phase.deadline_at,
                required_start_char=round_start_char,
            ),
            next_status=None,
            voting_deadline_at=None,
        )
