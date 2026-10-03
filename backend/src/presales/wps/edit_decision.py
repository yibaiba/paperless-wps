"""Choose a primary business action, never interpret list order as authorization."""

from decimal import Decimal

from presales.configuration.projects.planning.typed_intent import product_terms


def products(item):
    return [c["after"] for c in item["changes"] if c["kind"] == "devices" and c["after"]]


def added_purchase(item):
    def purchased(value):
        return Decimal(value["quantity"]) if value and value["source"] == "purchase" else Decimal(0)

    return sum(
        (
            max(purchased(c["after"]) - purchased(c["before"]), Decimal(0))
            for c in item["changes"]
            if c["kind"] == "supply_allocations"
        ),
        Decimal(0),
    )


def ambiguity(items):
    variants, sources = {}, {}
    for item in items:
        for device in products(item):
            variant = device["variant_snapshot"]
            product = variant["product"]
            key = product.get("model") or product["id"]
            variants.setdefault(key, set()).add(device["variant_id"])
            sources.setdefault(device["variant_id"], set()).add(device["source_id"])
    if any(len(values) > 1 for values in sources.values()):
        return "source_ambiguous"
    if any(len(values) > 1 for values in variants.values()):
        return "variant_ambiguous"
    return None


def recommendations(value):
    if isinstance(value, list):
        return [rule for entry in value for rule in recommendations(entry)]
    if not isinstance(value, dict):
        return []
    found = [value] if value.get("status") == "confirmed" and "variant_ids" in value else []
    return found + [rule for entry in value.values() for rule in recommendations(entry)]


def primary_choice(items, query):
    valid = [i for i in items if i["applicable"]]
    if not valid:
        return None, "evidence_required"
    if len(valid) == 1:
        return valid[0], "unique_candidate"
    minimum = min(added_purchase(i) for i in valid)
    reuse = [i for i in valid if added_purchase(i) == minimum]
    if len(reuse) == 1 and minimum == 0 and len(reuse) < len(valid):
        return reuse[0], "existing_reuse"
    exact = exact_choice(valid, query)
    if exact:
        return exact, "exact_input"
    blocked = ambiguity(valid)
    if blocked:
        return None, blocked
    confirmed = confirmed_choice(valid)
    return (confirmed, "confirmed_order") if confirmed else (None, "alternatives")


def exact_choice(valid, query):
    if not query:
        return None
    exact = [
        i
        for i in valid
        if any(
            query.casefold() in {text.casefold() for text in product_terms(d["variant_snapshot"])}
            for d in products(i)
        )
    ]
    return exact[0] if len(exact) == 1 else None


def confirmed_choice(valid):
    orders = {tuple(r["variant_ids"]) for i in valid for r in recommendations(i["evidence"])}
    if len(orders) == 1:
        order = next(iter(orders))
        identities = {d["variant_id"] for i in valid for d in products(i)}
        preferred = [identity for identity in order if identity in identities]
        if identities <= set(order) and preferred:
            first = [i for i in valid if any(d["variant_id"] == preferred[0] for d in products(i))]
            if len(first) == 1:
                return first[0]
    return None


def decision_for(items, *, query, issues, suppressed):
    if not items:
        codes = {q.get("code") for q in issues if isinstance(q, dict)}
        if "role_ambiguous" in codes or "product_source_ambiguous" in codes:
            return None, dict(status="choice_required", reason_code="identity_ambiguous")
        if suppressed:
            return None, dict(status="dismissed", reason_code="suggestion_dismissed")
        if query and "typed_no_match" in codes:
            return None, dict(status="no_match", reason_code="typed_no_match")
        if issues:
            return None, dict(status="confirmation_required", reason_code="evidence_required")
        return None, dict(
            status="no_match" if query else "satisfied",
            reason_code="typed_no_match" if query else "requirements_satisfied",
        )
    primary, reason = primary_choice(items, query)
    if primary:
        status = "ready" if primary["acceptance"] == "inline" else "confirmation_required"
    else:
        status = "confirmation_required" if reason == "evidence_required" else "choice_required"
    return primary, dict(status=status, reason_code=reason)


def next_target(item, *, request):
    if not item:
        return None
    patches = item["patches"]
    quantity = next((p for p in patches if p["field"] == "quantity"), next(iter(patches), None))
    patch = next((p for p in patches if p["column"] == request.active_cell.column), quantity)
    if not patch:
        return None  # Pure relationship changes have no implied cell edit.
    line = next(
        (
            b
            for b in [*request.lines, *request.removed_lines]
            if (b.sheet, b.row) == (patch["sheet"], patch["row"])
        ),
        None,
    )
    return {
        **{k: patch[k] for k in ("sheet", "row", "column", "field")},
        "line_id": line.line_id if line else None,
        "expected_value": patch["before"],
        "local_revision": request.local_revision,
        "context_fingerprint": item["context_fingerprint"],
    }
