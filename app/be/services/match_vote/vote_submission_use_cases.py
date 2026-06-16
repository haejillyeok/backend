from datetime import datetime
from uuid import UUID

from app.be.services.match_progress import MatchBroadcastEvent
from app.be.services.match_vote.constants import VOTE_ACCEPTED_MESSAGE_TYPE
from app.be.services.match_vote.records import VoteAcceptedRecord, VoteSubmissionRecord
from app.be.services.match_vote.result_events import result_event_from_vote_record


class MatchVoteSubmissionUseCaseMixin:
    async def submit_vote(
        self,
        *,
        game_session_public_id: UUID,
        voter_participant_id: UUID,
        target_seat_number: int,
        now: datetime,
    ) -> list[MatchBroadcastEvent]:
        """AI 지목 투표를 저장하고 commit 이후 전송할 event 목록을 반환합니다."""
        async with self.repository_scope():
            return await self._submit_vote(
                game_session_public_id=game_session_public_id,
                voter_participant_id=voter_participant_id,
                target_seat_number=target_seat_number,
                now=now,
            )

    async def _submit_vote(
        self,
        *,
        game_session_public_id: UUID,
        voter_participant_id: UUID,
        target_seat_number: int,
        now: datetime,
    ) -> list[MatchBroadcastEvent]:
        """투표 제출 transaction 안에서 vote, event, 결과 확정을 처리합니다."""
        game_session = await self.repository.get_game_session_for_update(game_session_public_id)
        self.vote_policy.ensure_voting_session(game_session)
        voting_phase = await self.repository.get_voting_phase(game_session=game_session)
        self.vote_policy.ensure_voting_deadline_not_exceeded(
            voting_phase=voting_phase,
            now=now,
        )
        voter = await self.repository.get_participant(
            session_id=game_session.id,
            participant_id=voter_participant_id,
        )
        target = await self.repository.get_participant_by_seat_number(
            session_id=game_session.id,
            seat_number=target_seat_number,
        )
        self.vote_policy.ensure_user_voter(voter)

        participants = await self.repository.list_participants(game_session.id)
        existing_votes = await self.repository.list_votes(game_session.id)
        self.vote_policy.ensure_vote_not_submitted(
            voter=voter,
            existing_votes=existing_votes,
        )
        base_scores = await self.repository.get_score_totals(game_session.id)
        action_number = await self.repository.get_next_action_number(game_session.id)
        action = await self.repository.create_vote_submit_action(
            session_id=game_session.id,
            voter=voter,
            target=target,
            action_number=action_number,
            now=now,
        )
        vote = await self.repository.create_vote(
            session_id=game_session.id,
            voter=voter,
            target=target,
            is_correct=self.vote_policy.is_correct_vote(target),
            now=now,
        )
        await self.repository.flush()

        submitted_vote_count = len(existing_votes) + 1
        required_vote_count = self.vote_policy.count_required_user_votes(participants)
        accepted_sequence = await self.repository.get_next_event_sequence(game_session.id)
        accepted_event = await self.repository.create_vote_accepted_event(
            session_id=game_session.id,
            voter=voter,
            action=action,
            event_sequence=accepted_sequence,
            submitted_vote_count=submitted_vote_count,
            required_vote_count=required_vote_count,
            now=now,
        )

        result_records = None
        result_event_sequence = None
        if submitted_vote_count >= required_vote_count:
            result_event_sequence = accepted_sequence + 1
            result_records = await self.publish_results(
                game_session=game_session,
                participants=participants,
                votes=[*existing_votes, vote],
                base_scores=base_scores,
                event_sequence=result_event_sequence,
                now=now,
            )

        await self.repository.flush()
        record = VoteSubmissionRecord(
            accepted=VoteAcceptedRecord(
                game_session_public_id=game_session.public_id,
                event_sequence=accepted_event.sequence,
                voter_display_name=voter.display_name,
                voter_seat_number=voter.seat_number,
                submitted_vote_count=submitted_vote_count,
                required_vote_count=required_vote_count,
                created_at=now,
            ),
            result=result_records,
            result_event_sequence=result_event_sequence,
            result_created_at=now if result_records is not None else None,
        )
        await self.repository.commit()
        events = [
            MatchBroadcastEvent(
                game_session_public_id=record.accepted.game_session_public_id,
                message={
                    "type": VOTE_ACCEPTED_MESSAGE_TYPE,
                    "payload": {
                        "event_sequence": record.accepted.event_sequence,
                        "voter": {
                            "display_name": record.accepted.voter_display_name,
                            "seat_number": record.accepted.voter_seat_number,
                        },
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
