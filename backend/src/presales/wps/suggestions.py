from collections import defaultdict

from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.knowledge.evaluator import scope_matches
from presales.lists.queries import search_catalog
from presales.lists.schemas import CatalogSearch

from .feedback import CompletionFeedback
from .schemas import SuggestionRequest
from .suggestion_ranking import (
    build_catalog_transitions,
    context_variants,
    exclude_context_models,
    model_family,
    rank_candidates,
)

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
        "source": {"sheet": source.get("sheet"), "row": source.get("row")},
    }


class Suggestions:
    def __init__(self, session, actor=None):
        self.session = session
        self.catalog = CatalogService(session)
        self.actor = actor

    def search(self, request: SuggestionRequest):
        variants = self.catalog.variants()
        by_id = {variant["id"]: variant for variant in variants}
        transitions = build_catalog_transitions(variants)
        learned_scores = CompletionFeedback(self.session).scores(request, self.actor)
        direct = self._direct(request, by_id) if request.query.strip() else []
        seeds = self._seed_variants(request, direct, by_id)
        related = self._related(seeds, variants, by_id)
        if not request.query.strip():
            related = exclude_context_models(related, request, by_id)
        direct = rank_candidates(
            self._deduplicate(direct), request, by_id, transitions, learned_scores
        )
        related = rank_candidates(
            self._deduplicate(related), request, by_id, transitions, learned_scores
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

    def _related(self, seeds, variants, by_id):
        results = []
        knowledge = Entities(self.session).list("knowledge")
        for seed in seeds:
            for identity in seed.get("replacements", []):
                results.extend(self._variant_candidates(by_id.get(identity), "alternative"))
            for rule in knowledge:
                if (
                    rule["kind"] == "accessory"
                    and rule["status"] == "confirmed"
                    and scope_matches(seed, rule["selector"])
                ):
                    for identity in rule["target_variant_ids"]:
                        results.extend(
                            self._variant_candidates(
                                by_id.get(identity), "accessory", evidence=[rule["name"]]
                            )
                        )
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
    top = items[0]
    top_key = _logical_product(top)
    same_product = [item for item in items if _logical_product(item) == top_key]
    source_matches = [item for item in same_product if item.get("_source_context_match")]
    concrete_unique = len(same_product) == 1 or (
        bool(top.get("_source_context_match")) and len(source_matches) == 1
    )
    competitor = next((item for item in items[1:] if _logical_product(item) != top_key), None)
    margin = (
        float("inf") if competitor is None else top["_ranking_score"] - competitor["_ranking_score"]
    )
    exact = _is_unique_exact_match(items, query, top_key)
    strong_evidence = bool(top.get("_strong_completion_evidence"))
    ready = (
        concrete_unique
        and top["confidence"] == "high"
        and (exact or (strong_evidence and margin >= MIN_COMPLETION_MARGIN))
    )
    return [
        {
            **{
                key: value
                for key, value in item.items()
                if key
                not in {
                    "_ranking_score",
                    "_source_context_match",
                    "_strong_completion_evidence",
                }
            },
            "completion_ready": index == 0 and ready,
        }
        for index, item in enumerate(items)
    ]


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
