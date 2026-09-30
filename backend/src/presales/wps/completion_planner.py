from dataclasses import dataclass

from presales.configuration.knowledge.evaluator import scope_matches

RELATION_TYPE_SCORE = {"required": 420, "recommended": 260, "optional": 120}
REVERSE_PAIR_BONUS = 80
SEED_DISTANCE_PENALTY = 20


@dataclass(frozen=True)
class RelationPlan:
    rule_id: str
    rule_name: str
    seed_id: str
    direction: str
    variant_ids: tuple[str, ...]
    score: int
    reason: str
    decisive: bool


def plan_relations(seed, rules, selected_ids, distance=0):
    plans = []
    for rule in rules:
        if rule.get("kind") != "accessory" or rule.get("status") != "confirmed":
            continue
        plan = _plan_rule(seed, rule, selected_ids, distance)
        if plan:
            plans.append(plan)
    return plans


def fulfilled_alternative_ids(selected_variants, rules):
    selected_ids = {variant["id"] for variant in selected_variants}
    suppressed = set()
    for rule in rules:
        if rule.get("kind") != "accessory" or rule.get("status") != "confirmed":
            continue
        targets = set(rule.get("target_variant_ids", []))
        selectors = set(rule.get("selector", {}).get("variant_ids", []))
        selector_selected = any(
            scope_matches(variant, rule["selector"]) for variant in selected_variants
        )
        target_selected = bool(targets & selected_ids)
        if selector_selected and target_selected:
            suppressed.update(targets - selected_ids)
            suppressed.update(selectors - selected_ids)
    return suppressed


def _plan_rule(seed, rule, selected_ids, distance):
    targets = tuple(dict.fromkeys(rule.get("target_variant_ids", [])))
    selectors = tuple(dict.fromkeys(rule.get("selector", {}).get("variant_ids", [])))
    if scope_matches(seed, rule["selector"]):
        if not targets or selected_ids.intersection(targets):
            return None
        direction, variants = "forward", targets
    elif seed["id"] in targets:
        if not selectors or selected_ids.intersection(selectors):
            return None
        direction, variants = "reverse", selectors
    else:
        return None
    relation_type = rule.get("accessory_type", "required")
    score = RELATION_TYPE_SCORE[relation_type] - distance * SEED_DISTANCE_PENALTY
    if direction == "reverse":
        score += REVERSE_PAIR_BONUS
    return RelationPlan(
        rule_id=rule["id"],
        rule_name=rule["name"],
        seed_id=seed["id"],
        direction=direction,
        variant_ids=variants,
        score=max(0, score),
        reason=_reason(direction, relation_type),
        decisive=seed["id"] in selected_ids and relation_type == "required",
    )


def _reason(direction, relation_type):
    if direction == "reverse":
        return "补齐已选产品的对应主设备"
    return {
        "required": "补齐当前方案尚缺的必配项",
        "recommended": "补充当前方案的推荐配套",
        "optional": "补充当前方案的可选配套",
    }[relation_type]
