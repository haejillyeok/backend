from uuid import UUID

from app.be.models.game import SessionParticipant, Vote
from app.be.services.match_vote.records import (
    MatchResultParticipantPayload,
    ScoreBreakdownItem,
    ScoreBreakdownPayload,
)


VOTE_SCORE_REASONS = {"vote_correct", "vote_wrong", "voted_as_ai"}


class MatchVoteResultPolicy:
    """투표 결과 점수, 순위, 공개 payload 계산 규칙을 담당합니다."""

    def build_result_payloads(
        self,
        *,
        participants: list[SessionParticipant],
        votes: list[Vote],
        base_scores: dict[UUID, int],
    ) -> list[MatchResultParticipantPayload]:
        """기본 점수와 투표 내역으로 참가자별 최종 결과 payload를 계산합니다."""
        vote_deltas = self._vote_deltas_by_participant(participants=participants, votes=votes)
        final_scores = {
            participant.id: base_scores.get(participant.id, 0) + vote_deltas.get(participant.id, 0)
            for participant in participants
        }
        ranks = self.rank_by_score(final_scores)
        max_score = max(final_scores.values()) if final_scores else 0
        return [
            MatchResultParticipantPayload(
                display_name=participant.display_name,
                seat_number=participant.seat_number,
                final_score=final_scores[participant.id],
                rank=ranks[participant.id],
                is_winner=final_scores[participant.id] == max_score,
                revealed_participant_type=participant.participant_type,
                vote_score_delta=vote_deltas.get(participant.id, 0),
            )
            for participant in sorted(participants, key=lambda item: item.seat_number)
        ]

    def rank_by_score(self, final_scores: dict[UUID, int]) -> dict[UUID, int]:
        """동점자는 같은 등수로 계산합니다."""
        ranked_items = sorted(final_scores.items(), key=lambda item: item[1], reverse=True)
        ranks: dict[UUID, int] = {}
        previous_score: int | None = None
        previous_rank = 0
        for index, (participant_id, score) in enumerate(ranked_items, start=1):
            if previous_score is None or score != previous_score:
                previous_rank = index
                previous_score = score
            ranks[participant_id] = previous_rank
        return ranks

    def build_score_breakdown(self, items: list[ScoreBreakdownItem]) -> ScoreBreakdownPayload:
        """점수 원장 사유를 frontend 설명용 범주별 점수로 묶습니다."""
        word_score = 0
        vote_score = 0
        penalty_score = 0
        for item in items:
            if item.reason in VOTE_SCORE_REASONS:
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

    def _vote_deltas_by_participant(
        self,
        *,
        participants: list[SessionParticipant],
        votes: list[Vote],
    ) -> dict[UUID, int]:
        """투표 정답/오답과 AI 지목 패널티를 참가자별 점수 변화량으로 환산합니다."""
        participants_by_id = {participant.id: participant for participant in participants}
        vote_deltas = {participant.id: 0 for participant in participants}
        for vote in votes:
            voter_delta = 10 if vote.is_correct else -5
            vote_deltas[vote.voter_participant_id] = (
                vote_deltas.get(vote.voter_participant_id, 0) + voter_delta
            )
            target = participants_by_id.get(vote.target_participant_id)
            if target is not None and target.is_uninvited_guest:
                vote_deltas[target.id] = vote_deltas.get(target.id, 0) - 5
        return vote_deltas
