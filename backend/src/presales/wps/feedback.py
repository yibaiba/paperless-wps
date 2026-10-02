from collections import defaultdict
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from presales.configuration.catalog.service import CatalogService

from .models import WpsSuggestionFeedback

WORKBOOK_CONTEXT_FEEDBACK_SCORE = 300
TEMPLATE_CONTEXT_FEEDBACK_SCORE = 220
WORKBOOK_FEEDBACK_SCORE = 70
TEMPLATE_FEEDBACK_SCORE = 50
ACTOR_FEEDBACK_SCORE = 25
TEAM_CONTEXT_FEEDBACK_SCORE = 140
MIN_TEAM_CONTEXT_ACTORS = 2
MAX_LEARNED_SCORE = 360
MAX_REJECTION_PENALTY = 180
PREVIOUS_CONTEXT_LIMIT = 3
NEXT_CONTEXT_LIMIT = 1
CONTEXTUAL_QUERY_KIND = "contextual"


def context_hash(sheet, section, previous=(), following=()):
    values = [
        sheet,
        section,
        *previous[:PREVIOUS_CONTEXT_LIMIT],
        *following[:NEXT_CONTEXT_LIMIT],
    ]
    normalized = "\x00".join(value.casefold().strip() for value in values)
    return sha256(normalized.encode()).hexdigest()


class CompletionFeedback:
    def __init__(self, session):
        self.session = session

    def record(self, data, actor):
        existing = self.session.scalar(
            select(WpsSuggestionFeedback).where(
                WpsSuggestionFeedback.operation_id == data.operation_id
            )
        )
        if existing:
            if existing.actor != actor:
                raise ValueError("反馈操作编号已被其他账号使用")
            return self._view(existing)
        self._validate_products(data)
        feedback = WpsSuggestionFeedback(
            operation_id=data.operation_id,
            actor=actor,
            workbook_instance_id=data.workbook_instance_id,
            template_profile_id=data.template_profile_id,
            template_profile_revision=data.template_profile_revision,
            context_hash=context_hash(
                data.sheet,
                data.section,
                data.context_previous_variant_ids,
                data.context_next_variant_ids,
            ),
            previous_variant_id=data.previous_variant_id,
            suggested_variant_id=data.suggested_variant_id,
            chosen_variant_id=data.chosen_variant_id,
            chosen_source_id=data.chosen_source_id,
            query_kind=data.query_kind,
        )
        try:
            with self.session.begin_nested():
                self.session.add(feedback)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(WpsSuggestionFeedback).where(
                    WpsSuggestionFeedback.operation_id == data.operation_id
                )
            )
            if not existing or existing.actor != actor:
                raise ValueError("反馈操作编号已被其他账号使用")
            return self._view(existing)
        return self._view(feedback)

    def scores(self, request, actor):
        # Typed choices do not retain query features, so applying them to another
        # query or to blank-row completion would teach the wrong transition.
        if request.query.strip():
            return {}
        previous = next(iter(request.context.previous_variant_ids), None)
        if not previous or not actor:
            return {}
        current_hash = context_hash(
            request.context.sheet,
            request.context.section,
            request.context.previous_variant_ids,
            request.context.next_variant_ids,
        )
        personal_rows = self.session.scalars(
            select(WpsSuggestionFeedback).where(
                WpsSuggestionFeedback.actor == actor,
                WpsSuggestionFeedback.previous_variant_id == previous,
                WpsSuggestionFeedback.query_kind == CONTEXTUAL_QUERY_KIND,
            )
        ).all()
        team_rows = self.session.scalars(
            select(WpsSuggestionFeedback).where(
                WpsSuggestionFeedback.actor != actor,
                WpsSuggestionFeedback.previous_variant_id == previous,
                WpsSuggestionFeedback.query_kind == CONTEXTUAL_QUERY_KIND,
                WpsSuggestionFeedback.template_profile_id == request.template_profile_id,
                WpsSuggestionFeedback.template_profile_revision
                == request.template_profile_revision,
                WpsSuggestionFeedback.context_hash == current_hash,
            )
        ).all()
        personal = self._personal_scores(personal_rows, request, current_hash)
        team = self._team_scores(team_rows, actor, request, current_hash)
        return self._merge_scores(personal, team)

    def _personal_scores(self, rows, request, current_hash):
        scores, reasons, reason_weights = {}, {}, {}
        for row in rows:
            weight, reason = self._scope(row, request, current_hash)
            scores[row.chosen_variant_id] = scores.get(row.chosen_variant_id, 0) + weight
            if weight > reason_weights.get(row.chosen_variant_id, -1):
                reasons[row.chosen_variant_id] = reason
                reason_weights[row.chosen_variant_id] = weight
            if row.suggested_variant_id and row.suggested_variant_id != row.chosen_variant_id:
                penalty = weight // 2
                scores[row.suggested_variant_id] = scores.get(row.suggested_variant_id, 0) - penalty
        return {
            identity: (self._clamp(score), reasons.get(identity, ""))
            for identity, score in scores.items()
        }

    def _team_scores(self, rows, actor, request, current_hash):
        latest_by_actor = {}
        for row in rows:
            if row.actor == actor or not self._same_template_context(row, request, current_hash):
                continue
            current = latest_by_actor.get(row.actor)
            if current is None or (row.created_at, row.id) > (current.created_at, current.id):
                latest_by_actor[row.actor] = row
        voters = defaultdict(set)
        for row in latest_by_actor.values():
            voters[row.chosen_variant_id].add(row.actor)
        return {
            identity: (TEAM_CONTEXT_FEEDBACK_SCORE, "采用团队确认的模板顺序")
            for identity, actors in voters.items()
            if len(actors) >= MIN_TEAM_CONTEXT_ACTORS
        }

    @classmethod
    def _merge_scores(cls, personal, team):
        result = {}
        for identity in personal.keys() | team.keys():
            personal_score, personal_reason = personal.get(identity, (0, ""))
            team_score, team_reason = team.get(identity, (0, ""))
            result[identity] = (
                cls._clamp(personal_score + team_score),
                personal_reason or team_reason,
            )
        return result

    @staticmethod
    def _same_template_context(row, request, current_hash):
        return (
            row.context_hash == current_hash
            and row.template_profile_id == request.template_profile_id
            and row.template_profile_revision == request.template_profile_revision
        )

    def _validate_products(self, data):
        variants = CatalogService(self.session).variants()
        by_id = {variant["id"]: variant for variant in variants}
        for identity in [
            data.previous_variant_id,
            data.suggested_variant_id,
            data.chosen_variant_id,
        ]:
            if identity and identity not in by_id:
                raise ValueError("联想反馈引用了不存在的产品配置")
        sources = {source["id"] for source in by_id[data.chosen_variant_id]["source_details"]}
        if data.chosen_source_id not in sources:
            raise ValueError("联想反馈的资料来源不属于所选产品配置")

    @staticmethod
    def _scope(row, request, current_hash):
        same_context = row.context_hash == current_hash
        same_workbook = row.workbook_instance_id == request.workbook_instance_id
        same_template = (
            row.template_profile_id == request.template_profile_id
            and row.template_profile_revision == request.template_profile_revision
        )
        if same_workbook and same_context:
            return WORKBOOK_CONTEXT_FEEDBACK_SCORE, "采用当前工作簿上下文顺序"
        if same_template and same_context:
            return TEMPLATE_CONTEXT_FEEDBACK_SCORE, "采用当前模板上下文顺序"
        if same_workbook:
            return WORKBOOK_FEEDBACK_SCORE, "参考当前工作簿历史顺序"
        if not same_template:
            return ACTOR_FEEDBACK_SCORE, "采用个人历史顺序"
        return TEMPLATE_FEEDBACK_SCORE, "参考模板历史顺序"

    @staticmethod
    def _clamp(score):
        return max(-MAX_REJECTION_PENALTY, min(score, MAX_LEARNED_SCORE))

    @staticmethod
    def _view(feedback):
        return {
            "id": feedback.id,
            "operation_id": feedback.operation_id,
            "status": "recorded",
        }
