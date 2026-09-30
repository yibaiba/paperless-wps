from collections import defaultdict

from sqlalchemy import select

from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.models import SourceLink
from presales.lists.queries import search_catalog
from presales.lists.schemas import CatalogSearch
from presales.storage import ProductRecord

from .catalog_index import CatalogSuggestionIndex
from .completion_planner import RelationPlan, fulfilled_alternative_ids, plan_relations
from .feedback import CompletionFeedback
from .schemas import SuggestionRequest
from .suggestion_ranking import (
    build_catalog_transitions,
    context_variants,
    exclude_context_models,
    model_family,
    rank_candidates,
)
from .templates import TemplateProfiles

GROUP_ORDER = {"direct": 0, "series": 1, "alternative": 2, "accessory": 3, "related": 4}
MIN_COMPLETION_MARGIN = 35


def candidate_view(variant, source, *, group, status="unknown", evidence=()):
    product = variant["product"]
    return {
        "key": f"{variant['id']}:{source['id']}",
        "group": group,
        "variant_id": variant["id"],
        "source_id": source["id"],
        "model": product["model"],
        "name": product["name"],
        "brand": product.get("brand", ""),
        "variant_name": variant["name"],
        "description": source.get("specification") or variant.get("description", ""),
        "unit": source.get("unit", ""),
        "price": None,
        "price_status": "pending",
        "status": status,
        "confidence": "low",
        "evidence": list(evidence),
        "context_reasons": [],
        "source": {
            "import_id": source.get("import_id"),
            "sheet": source.get("sheet"),
            "row": source.get("row"),
        },
    }


class Suggestions:
    def __init__(self, session, actor=None, catalog_index: CatalogSuggestionIndex | None = None):
        self.session = session
        self.catalog = CatalogService(session)
        self.actor = actor
        self.catalog_index = catalog_index

    def search(self, request: SuggestionRequest):
        catalog_scope = self._catalog_scope(request)
        if self.catalog_index:
            snapshot = self.catalog_index.snapshot(self.session, catalog_scope)
            variants, transitions = snapshot.variants, snapshot.transitions
        else:
            variants = self.catalog.variants()
            transitions = build_catalog_transitions(variants, catalog_scope)
        by_id = {variant["id"]: variant for variant in variants}
        learned_scores = CompletionFeedback(self.session).scores(request, self.actor)
        direct = self._direct(request, by_id) if request.query.strip() else []
        seeds = self._seed_variants(request, direct, by_id)
        selected_ids = self._selected_variant_ids(request)
        selected_variants = [by_id[identity] for identity in selected_ids if identity in by_id]
        knowledge = Entities(self.session).list("knowledge")
        related = self._related(seeds, variants, by_id, selected_ids, knowledge)
        if not request.query.strip():
            related = exclude_context_models(related, request, by_id)
            suppressed = fulfilled_alternative_ids(selected_variants, knowledge)
            related = [item for item in related if item["variant_id"] not in suppressed]
        direct = rank_candidates(
            self._deduplicate(direct),
            request,
            by_id,
            transitions,
            learned_scores,
            catalog_scope,
        )
        related = rank_candidates(
            self._deduplicate(related),
            request,
            by_id,
            transitions,
            learned_scores,
            catalog_scope,
        )
        direct_limit = min(6, request.limit)
        ordered = [*direct[:direct_limit], *related, *direct[direct_limit:]] if direct else related
        combined = finalize_completion_readiness(
            self._deduplicate(ordered)[: request.limit], request.query
        )
        groups = defaultdict(list)
        for item in combined:
            groups[item["group"]].append(item)
        return {
            "items": combined,
            "groups": [
                {"kind": kind, "items": groups[kind]}
                for kind in sorted(groups, key=lambda value: GROUP_ORDER[value])
            ],
        }

    def _catalog_scope(self, request):
        if request.template_profile_id:
            profile = TemplateProfiles(self.session).get(
                request.template_profile_id, request.template_profile_revision
            )
            if profile.get("catalog_scope"):
                return profile["catalog_scope"]
        return self._context_source_scope(request)

    def _context_source_scope(self, request):
        pairs = [
            (request.context.selected_variant_id, request.context.selected_source_id),
            *zip(
                request.context.previous_variant_ids,
                request.context.previous_source_ids,
                strict=False,
            ),
            *zip(
                request.context.next_variant_ids,
                request.context.next_source_ids,
                strict=False,
            ),
        ]
        for variant_id, source_id in pairs:
            if not variant_id or not source_id:
                continue
            link = self.session.scalar(
                select(SourceLink).where(
                    SourceLink.variant_id == variant_id,
                    SourceLink.source_id == source_id,
                )
            )
            source = self.session.get(ProductRecord, source_id) if link else None
            if source:
                return {"import_id": source.import_id, "sheet": source.sheet}
        return None

    def _direct(self, request, by_id):
        page = search_catalog(
            self.session,
            CatalogSearch(
                query=request.query,
                draft_id=request.draft_id,
                requirement_id=request.requirement_id,
                include_other_products=not bool(request.requirement_id),
                limit=request.limit,
            ),
        )
        items = []
        for result in page["items"]:
            variant = by_id.get(result["variant_id"])
            if not variant:
                continue
            for source in variant["source_details"]:
                items.append(
                    candidate_view(
                        variant,
                        source,
                        group="direct",
                        status=result["status"],
                        evidence=result["evidence"],
                    )
                )
        return items

    def _seed_variants(self, request, direct, by_id):
        ids = [
            request.context.selected_variant_id,
            *request.context.previous_variant_ids,
            *request.context.next_variant_ids,
        ]
        ids.extend(item["variant_id"] for item in direct[:3])
        return context_variants(ids, by_id)

    @staticmethod
    def _selected_variant_ids(request):
        return {
            identity
            for identity in [
                request.context.selected_variant_id,
                *request.context.previous_variant_ids,
                *request.context.next_variant_ids,
            ]
            if identity
        }

    def _related(self, seeds, variants, by_id, selected_ids, knowledge):
        results = []
        for distance, seed in enumerate(seeds):
            for identity in seed.get("replacements", []):
                results.extend(self._variant_candidates(by_id.get(identity), "alternative"))
            for plan in plan_relations(seed, knowledge, selected_ids, distance):
                results.extend(self._planned_accessories(plan, by_id))
            for variant in variants:
                same_category = seed["product"].get("category") and (
                    seed["product"].get("category") == variant["product"].get("category")
                )
                same_series = bool(set(seed.get("series", [])) & set(variant.get("series", [])))
                seed_family = model_family(seed["product"].get("model", ""))
                same_family = seed_family and seed_family == model_family(
                    variant["product"].get("model", "")
                )
                if variant["id"] == seed["id"]:
                    continue
                if same_series or same_family:
                    results.extend(self._variant_candidates(variant, "series"))
                elif same_category:
                    results.extend(self._variant_candidates(variant, "related"))
        return results

    def _planned_accessories(self, plan: RelationPlan, by_id):
        results = []
        for identity in plan.variant_ids:
            candidates = self._variant_candidates(
                by_id.get(identity), "accessory", evidence=[plan.rule_name]
            )
            for candidate in candidates:
                candidate["_confirmed_relation_score"] = plan.score
                candidate["_confirmed_relation_reason"] = plan.reason
                candidate["_confirmed_relation_direction"] = plan.direction
                candidate["_confirmed_relation_seed_id"] = plan.seed_id
                candidate["_confirmed_relation_rule_id"] = plan.rule_id
                candidate["_confirmed_relation_decisive"] = plan.decisive
            results.extend(candidates)
        return results

    @staticmethod
    def _variant_candidates(variant, group, evidence=()):
        if not variant or variant.get("supply_status", "available") != "available":
            return []
        return [
            candidate_view(variant, source, group=group, evidence=evidence)
            for source in variant["source_details"]
        ]

    @staticmethod
    def _deduplicate(items):
        result, seen = [], set()
        for item in items:
            identity = (item["variant_id"], item["source_id"])
            if identity in seen:
                continue
            seen.add(identity)
            result.append(item)
        return result


def finalize_completion_readiness(items, query):
    if not items:
        return []
    ready, blocker = _completion_decision(items, query)
    internal = {
        "_confirmed_relation_direction",
        "_confirmed_relation_decisive",
        "_confirmed_relation_reason",
        "_confirmed_relation_rule_id",
        "_confirmed_relation_score",
        "_confirmed_relation_seed_id",
        "_ranking_score",
        "_scope_confirmed",
        "_source_context_match",
        "_source_scope_match",
        "_strong_completion_evidence",
    }
    return [
        {
            **{key: value for key, value in item.items() if key not in internal},
            "completion_ready": index == 0 and ready,
            "completion_blocker": blocker if index == 0 else "insufficient_evidence",
        }
        for index, item in enumerate(items)
    ]


def _completion_decision(items, query):
    top = items[0]
    if top.get("_scope_confirmed") and not top.get("_source_scope_match"):
        return False, "source_ambiguous"
    if not top.get("_scope_confirmed") and not query.strip():
        return False, "template_source_unconfirmed"
    if _confirmed_relation_is_ambiguous(items, top):
        return False, "variant_ambiguous"
    product_items = [item for item in items if _logical_product(item) == _logical_product(top)]
    concrete = _concrete_candidates(top, product_items)
    if len({item["variant_id"] for item in concrete}) > 1:
        return False, "variant_ambiguous"
    if len(concrete) > 1:
        return False, "source_ambiguous"
    exact = _is_unique_exact_match(items, query, _logical_product(top))
    if top["confidence"] != "high" or not (exact or top.get("_strong_completion_evidence")):
        return False, "insufficient_evidence"
    if top.get("_confirmed_relation_decisive"):
        return True, None
    competitor = _completion_competitor(items, top)
    margin = float("inf") if competitor is None else (
        top["_ranking_score"] - competitor["_ranking_score"]
    )
    if not exact and margin < MIN_COMPLETION_MARGIN:
        return False, "insufficient_margin"
    return True, None


def _confirmed_relation_is_ambiguous(items, top):
    if not top.get("_confirmed_relation_rule_id"):
        return False
    related = [
        item
        for item in items
        if item.get("_confirmed_relation_rule_id") == top.get("_confirmed_relation_rule_id")
        and item.get("_confirmed_relation_seed_id") == top.get("_confirmed_relation_seed_id")
    ]
    concrete = _concrete_candidates(top, related)
    return len({item["variant_id"] for item in concrete}) > 1


def _concrete_candidates(top, product_items):
    match_key = "_source_scope_match" if top.get("_scope_confirmed") else "_source_context_match"
    matched = [item for item in product_items if item.get(match_key)]
    return matched if top.get(match_key) and matched else product_items


def _completion_competitor(items, top):
    for item in items[1:]:
        if _logical_product(item) == _logical_product(top):
            continue
        if top.get("_scope_confirmed") and not item.get("_source_scope_match"):
            continue
        return item
    return None


def _logical_product(item):
    return (item["model"].casefold().strip(), item["name"].casefold().strip())


def _is_unique_exact_match(items, query, top_key):
    normalized = query.casefold().strip()
    if not normalized:
        return False
    exact = {
        _logical_product(item)
        for item in items
        if normalized in {item["model"].casefold().strip(), item["name"].casefold().strip()}
    }
    return exact == {top_key}
