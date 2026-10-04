"""Diagnose typed intent against the pinned catalog before business applicability."""


def product_terms(variant):
    product = variant["product"]
    aliases = [a["name"] for a in variant.get("aliases", []) if a["status"] == "confirmed"]
    return [product["name"], product["model"], variant["name"], *aliases]


def matches_query(variant, query):
    text = " ".join(product_terms(variant)).casefold()
    return all(token in text for token in query.casefold().split())


def matches_selection(variant, *, allowed_sources, variant_id, source_id):
    if variant_id and variant["id"] != variant_id:
        return False
    sources = set(variant["source_ids"]) & set(allowed_sources.get(variant["id"], []))
    return not source_id or source_id in sources


def resolution_status(catalog, scoped, selected):
    if not catalog:
        return "no_catalog_match"
    if not scoped:
        return "outside_source"
    return "matched" if selected else "selection_mismatch"


def preferred_variant_ids(variants, query):
    exact = [
        v for v in variants if query.strip().casefold() in {t.casefold() for t in product_terms(v)}
    ]
    return sorted(v["id"] for v in (exact or variants))


def resolve_input(variants, *, query, allowed_sources, selected_variant_id, selected_source_id):
    if not query:
        return None
    catalog = [v for v in variants if matches_query(v, query)]
    scoped = [v for v in catalog if set(v["source_ids"]) & set(allowed_sources.get(v["id"], []))]
    selected = [
        v
        for v in scoped
        if matches_selection(
            v,
            allowed_sources=allowed_sources,
            variant_id=selected_variant_id,
            source_id=selected_source_id,
        )
    ]
    return dict(
        status=resolution_status(catalog, scoped, selected),
        catalog_match_count=len(catalog),
        scoped_match_count=len(scoped),
        selected_match_count=len(selected),
        variant_ids=preferred_variant_ids(selected, query),
    )


def unresolved_input(resolution, *, task=None):
    reasons = {
        "no_catalog_match": (
            "typed_no_match",
            "catalog_data",
            "当前工作簿固定目录中没有匹配的型号、名称或已确认别名，请核对输入及目录版本",
        ),
        "outside_source": (
            "typed_source_excluded",
            "catalog_scope",
            f"固定目录中有 {resolution['catalog_match_count']} 个匹配配置，"
            "但均不在模板确认的来源范围，请核对模板来源",
        ),
        "selection_mismatch": (
            "typed_selection_stale",
            "business_context",
            "已选配置或来源与当前输入及模板来源不一致，请重新选择",
        ),
        "matched": (
            "typed_role_unresolved",
            "knowledge",
            "固定目录及模板来源内有匹配产品，但固定知识版本中没有它用于"
            + (f"当前用途「{task['role']['name']}」" if task else "当前系统用途")
            + "的适用依据，请核对用途及适用规则",
        ),
    }
    code, origin, message = reasons[resolution["status"]]
    issue = dict(code=code, origin=origin, message=message)
    if task:
        issue.update(requirement_id=task["requirement"]["id"], role_id=task["role"]["id"])
    return issue
