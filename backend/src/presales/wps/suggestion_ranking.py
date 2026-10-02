from presales.lists.search_matching import query_match_score

from .catalog_sequences import build_catalog_transitions, model_family

__all__ = ["build_catalog_transitions", "model_family", "rank_candidates"]

STATUS_SCORE = {"pass": 20, "unknown": 10, "unassessed": 5, "conflict": -100}
GROUP_SCORE = {"direct": 0, "series": 20, "alternative": 25, "accessory": 25, "related": 0}
STRONG_RELATION_GROUPS = {"alternative", "accessory"}
NEIGHBOR_DISTANCE_PENALTY = 6
TRANSITION_DISTANCE_PENALTY = 10
SOURCE_SEQUENCE_MATCH_SCORE = 160
SOURCE_CONTEXT_MATCH_SCORE = 180
SOURCE_SCOPE_MATCH_SCORE = 260
MIN_SEQUENCE_COMPLETION_SUPPORT = 2
SHORT_SEQUENCE_BONUS = 70
SYSTEM_CONTEXT_MATCH_SCORE = 120


def text_matches(value, context):
    left, right = value.casefold().strip(), context.casefold().strip()
    return bool(left and right and (left in right or right in left))


def exact_context_match(value, contexts):
    normalized = value.casefold().strip()
    return bool(normalized) and any(
        normalized == context.casefold().strip() for context in contexts if context.strip()
    )


def context_variants(identities, by_id):
    result, seen = [], set()
    for identity in identities:
        if not identity or identity in seen or identity not in by_id:
            continue
        seen.add(identity)
        result.append(by_id[identity])
    return result


def rank_candidates(
    items, request, by_id, transitions=None, learned_scores=None, catalog_scope=None
):
    previous = context_variants(
        [request.context.selected_variant_id, *request.context.previous_variant_ids], by_id
    )
    following = context_variants(request.context.next_variant_ids, by_id)
    ranked = []
    for index, item in enumerate(items):
        variant = by_id[item["variant_id"]]
        learned_score, learned_reason = _learned_candidate_score(item, learned_scores or {})
        context_score, reasons, transition_strong = _context_score(
            variant,
            request,
            previous,
            following,
            transitions or {},
            learned_score,
            learned_reason,
            scope_confirmed=bool(catalog_scope),
        )
        relation_score = item.get("_confirmed_relation_score", 0)
        relation_reason = item.get("_confirmed_relation_reason", "")
        query_score = query_match_score(variant, request.query)
        source_score, source_match, scope_match = _source_context_score(
            item, request, catalog_scope
        )
        if scope_match:
            reasons = ["匹配模板产品来源", *reasons][:3]
        elif source_match:
            reasons = ["匹配当前来源工作表", *reasons][:3]
        if relation_reason:
            reasons = [relation_reason, *reasons][:3]
        score = (
            context_score
            + relation_score
            + query_score
            + source_score
            + GROUP_SCORE[item["group"]]
            + STATUS_SCORE.get(item["status"], 0)
        )
        candidate = {
            **item,
            "context_reasons": reasons,
            "confidence": _confidence(item["group"], query_score, context_score),
            "_ranking_score": score,
            "_source_context_match": source_match,
            "_source_scope_match": scope_match,
            "_scope_confirmed": bool(catalog_scope),
            "_query_match_score": query_score,
            "_strong_completion_evidence": bool(
                scope_match
                or source_match
                or learned_reason
                or query_score >= 80
                or transition_strong
                or relation_score > 0
                or item["group"] in STRONG_RELATION_GROUPS
            ),
        }
        scope_order = int(scope_match) if catalog_scope else 0
        ranked.append((scope_order, score, -index, candidate))
    ranked.sort(key=lambda value: (value[0], value[1], value[2]), reverse=True)
    return [item for _, _, _, item in ranked]


def _learned_candidate_score(item, learned_scores):
    variant_score, variant_reason = learned_scores.get(item["variant_id"], (0, ""))
    source_id = item.get("source_id")
    source_score, source_reason = learned_scores.get(
        (item["variant_id"], source_id), (0, "")
    )
    return variant_score + source_score, source_reason or variant_reason


def exclude_selected_models(items, identities, by_id):
    models = {
        item["product"].get("model", "").casefold().strip()
        for item in context_variants(identities, by_id)
        if item["product"].get("model", "").strip()
    }
    return [item for item in items if item["model"].casefold().strip() not in models]


def _context_score(
    variant,
    request,
    previous,
    following,
    transitions,
    learned_score,
    learned_reason,
    *,
    scope_confirmed=False,
):
    reasons, score = [], 0
    if learned_reason:
        reasons.append(learned_reason)
    score += learned_score
    sequence_contexts = [
        request.context.section,
        request.context.system,
        request.current_row.get("section", ""),
    ]
    transition_score, transition_reason, transition_strong = _best_transition_match(
        variant, previous, following, transitions, sequence_contexts, scope_confirmed
    )
    if transition_reason:
        reasons.append(transition_reason)
        score += transition_score
    if any(exact_context_match(system, sequence_contexts) for system in variant.get("systems", [])):
        reasons.append("匹配当前系统")
        score += SYSTEM_CONTEXT_MATCH_SCORE
    role_values = [variant["product"].get("category", ""), *variant.get("functions", [])]
    if any(text_matches(value, request.context.role) for value in role_values):
        reasons.append("匹配当前角色")
        score += 25
    previous_score, previous_reason = _best_neighbor_match(variant, previous, "previous")
    following_score, following_reason = _best_neighbor_match(variant, following, "next")
    if previous_reason:
        reasons.append(previous_reason)
        score += previous_score
    if following_reason:
        reasons.append(following_reason)
        score += following_score
    return score, reasons[:3], transition_strong


def _best_transition_match(
    variant, previous, following, transitions, sequence_contexts, scope_confirmed=False
):
    candidate_model = _variant_model(variant)
    candidate_label = _variant_model_label(variant)
    matches = []
    if len(previous) >= 2:
        key = (_variant_model(previous[1]), _variant_model(previous[0]), candidate_model)
        labels = (
            f"{_variant_model_label(previous[1])} → {_variant_model_label(previous[0])}",
            candidate_label,
        )
        matches.append(
            _transition_evidence(
                key,
                labels,
                transitions,
                sequence_contexts,
                0,
                "延续短序列",
                SHORT_SEQUENCE_BONUS,
                scope_confirmed,
            )
        )
    for distance, neighbor in enumerate(previous):
        key = (_variant_model(neighbor), candidate_model)
        labels = (_variant_model_label(neighbor), candidate_label)
        matches.append(
            _transition_evidence(
                key,
                labels,
                transitions,
                sequence_contexts,
                distance,
                "延续",
                scope_confirmed=scope_confirmed,
            )
        )
    for distance, neighbor in enumerate(following):
        key = (candidate_model, _variant_model(neighbor))
        labels = (candidate_label, _variant_model_label(neighbor))
        matches.append(
            _transition_evidence(
                key,
                labels,
                transitions,
                sequence_contexts,
                distance,
                "衔接",
                scope_confirmed=scope_confirmed,
            )
        )
    return max(matches, default=(0, "", False), key=lambda item: item[0])


def _transition_evidence(
    key,
    labels,
    transitions,
    sequence_contexts,
    distance,
    direction,
    bonus=0,
    scope_confirmed=False,
):
    sheets = transitions.get(key, [])
    if not sheets:
        return 0, "", False
    normalized_contexts = {value.casefold().strip() for value in sequence_contexts if value.strip()}
    sheet_match = any(sheet.casefold().strip() in normalized_contexts for sheet in sheets)
    score = 100 + min(len(sheets) * 5, 20) + bonus
    if sheet_match:
        score += SOURCE_SEQUENCE_MATCH_SCORE
    score = max(0, score - distance * TRANSITION_DISTANCE_PENALTY)
    strong = scope_confirmed or sheet_match or len(sheets) >= MIN_SEQUENCE_COMPLETION_SUPPORT
    return score, f"{direction}清单顺序 {labels[0]} → {labels[1]}", strong


def _best_neighbor_match(variant, neighbors, direction):
    best_score, best_reason = 0, ""
    for distance, neighbor in enumerate(neighbors):
        relation_score, relation = _variant_relation(variant, neighbor)
        score = max(0, relation_score - distance * NEIGHBOR_DISTANCE_PENALTY)
        if score <= best_score:
            continue
        prefix = "衔接" if direction == "next" else "延续"
        best_score, best_reason = score, f"{prefix}{relation}"
    return best_score, best_reason


def _variant_relation(variant, neighbor):
    if variant["id"] == neighbor["id"]:
        return 0, ""
    shared = set(variant.get("series", [])) & set(neighbor.get("series", []))
    if shared:
        return 60, f"同系列 {sorted(shared)[0]}"
    family = model_family(variant["product"].get("model", ""))
    if family and family == model_family(neighbor["product"].get("model", "")):
        return 50, f"型号族 {family}"
    category = variant["product"].get("category")
    if category and category == neighbor["product"].get("category"):
        return 15, "相邻行分类"
    return 0, ""


def _variant_model(variant):
    return variant["product"].get("model", "").casefold().strip()


def _variant_model_label(variant):
    return variant["product"].get("model", "").strip()


def _source_context_score(item, request, catalog_scope=None):
    source_sheet = (item.get("source") or {}).get("sheet") or ""
    source_import = (item.get("source") or {}).get("import_id") or ""
    normalized_source = source_sheet.casefold().strip()
    active_sheet = request.context.sheet.casefold().strip()
    matched = bool(normalized_source) and normalized_source == active_sheet
    scope_match = bool(catalog_scope) and (
        source_import == catalog_scope.get("import_id")
        and source_sheet == catalog_scope.get("sheet")
    )
    if scope_match:
        return SOURCE_SCOPE_MATCH_SCORE, matched, True
    return (SOURCE_CONTEXT_MATCH_SCORE, True, False) if matched else (0, False, False)


def _confidence(group, query_score, context_score):
    if query_score >= 80 or context_score >= 50:
        return "high"
    if group in STRONG_RELATION_GROUPS and context_score > 0:
        return "high"
    if query_score >= 40 or context_score >= 25:
        return "medium"
    return "low"
