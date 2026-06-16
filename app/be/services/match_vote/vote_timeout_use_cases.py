from datetime import datetime
from uuid import UUID

from app.be.services.match_progress import MatchBroadcastEvent
from app.be.services.match_vote.constants import VOTE_TIMEOUT_MESSAGE_TYPE
from app.be.services.match_vote.records import VoteAcceptedRecord, VoteSubmissionRecord
from app.be.services.match_vote.result_events import result_event_from_vote_record


class MatchVoteTimeoutUseCaseMixin:
    async def timeout_vote(
        self,
        *,
        game_session_public_id: UUID,
        now: datetime,
    ) -> list[MatchBroadcastEvent]:
        """투표 deadline 초과를 확정하고 결과 broadcast event를 반환합니다."""
        async with self.repository_scope():
            return await self._timeout_vote(
                game_session_public_id=game_session_public_id,
                now=now,
            )

    async def _timeout_vote(
        self,
        *,
        game_session_public_id: UUID,
        now: datetime,
    ) -> list[MatchBroadcastEvent]:
        """투표 timeout transaction 안에서 결과를 확정합니다."""
        game_session = await self.repository.get_game_session_for_update(game_session_public_id)
        if self.vote_policy.is_result_session(game_session):
            return []
        self.vote_policy.ensure_voting_session(game_session)

        participants = await self.repository.list_participants(game_session.id)
        votes = await self.repository.list_votes(game_session.id)
        base_scores = await self.repository.get_score_totals(game_session.id)
        submitted_vote_count = len(votes)
        required_vote_count = self.vote_policy.count_required_user_votes(participants)
        timeout_sequence = await self.repository.get_next_event_sequence(game_session.id)
        timeout_event = await self.repository.create_vote_timeout_event(
            session_id=game_session.id,
            event_sequence=timeout_sequence,
            submitted_vote_count=submitted_vote_count,
            required_vote_count=required_vote_count,
            now=now,
        )
        result_event_sequence = timeout_sequence + 1
        result_records = await self.publish_results(
            game_session=game_session,
            participants=participants,
            votes=votes,
            base_scores=base_scores,
            event_sequence=result_event_sequence,
            now=now,
        )
        await self.repository.flush()
        record = VoteSubmissionRecord(
            accepted=VoteAcceptedRecord(
                game_session_public_id=game_session.public_id,
                event_sequence=timeout_event.sequence,
                voter_display_name="",
                voter_seat_number=0,
                submitted_vote_count=submitted_vote_count,
                required_vote_count=required_vote_count,
                created_at=now,
            ),
            result=result_records,
            result_event_sequence=result_event_sequence,
            result_created_at=now,
        )
        await self.repository.commit()
        events = [
            MatchBroadcastEvent(
                game_session_public_id=record.accepted.game_session_public_id,
                message={
                    "type": VOTE_TIMEOUT_MESSAGE_TYPE,
                    "payload": {
                        "event_sequence": record.accepted.event_sequence,
                        "submitted_vote_count": record.accepted.submitted_vote_count,
                        "required_vote_count": record.accepted.required_vote_count,
                        "created_at": record.accepted.created_at,
                        "server_time": record.accepted.created_at,
                    },
                },
            )
        ]
        if record.result is not None:
            events.append(result_event_from_vote_record(record))
        return events
