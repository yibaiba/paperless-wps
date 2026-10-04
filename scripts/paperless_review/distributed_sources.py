"""Transactional follow-up using existing catalogue, knowledge and package revisions."""

from copy import deepcopy

from presales.configuration.catalog.service import CatalogService
from presales.configuration.definitions.schemas import SystemDefinition
from presales.rules.calculation import digest
from presales.storage import ProductRecord

from .content import ReviewSources
from .distributed import package_changes
from .distributed_facts import FACTS, MODELS, OS_ROWS, source_variant
from .distributed_relations import matrix_needs, os_relation, tablet_candidates
from .maintenance import proposal, stable_id
from .reconciliation import current_records, evidence_source_ids
from .specs import DISTRIBUTED, THIRD_PARTY


def checked_source(sources, variants, *, sheet, row, model):
    identity, source = sources.get(sheet, row)
    if (
        variants[identity]["product"]["model"] != model
        and model not in variants[identity]["product"]["model"]
    ):
        raise ValueError(f"资料行对应型号已变化：{sheet}!{row} 预期 {model}")
    return identity, source


def build_source_plan(session):
    current = current_records(session)
    variants = {v["id"]: v for v in CatalogService(session).variants()}
    sources = ReviewSources(variants.values())
    definitions = [
        (i, r)
        for i, r in current.items()
        if r["kind"] == "system_definition" and r["payload"]["name"] == DISTRIBUTED
    ]
    if len(definitions) != 1:
        raise ValueError("分布式系统定义应唯一")
    identity, record = definitions[0]
    definition = dict(id=identity, **deepcopy(record["payload"]))
    payload = {k: v for k, v in definition.items() if k in SystemDefinition.model_fields}
    changes = [proposal(current, kind="system_definition", identity=identity, payload=payload)]
    for row in FACTS:
        variant_id, source = checked_source(
            sources, variants, sheet=DISTRIBUTED, row=row, model=MODELS[row]
        )
        changes.append(
            proposal(
                current,
                kind="variant",
                identity=variant_id,
                payload=source_variant(current[variant_id]["payload"], source),
            )
        )
        if row in OS_ROWS:
            changes.append(
                environment_change(
                    current, definition=definition, variant_id=variant_id, row=row, sources=sources
                )
            )
    for row, model in ((15, "BYD5-W10"), (16, "BYD5-AL10")):
        checked_source(sources, variants, sheet=THIRD_PARTY, row=row, model=model)
    additions = [*matrix_needs(definition, sources), *tablet_candidates(definition, sources)]
    for rule in additions:
        identity = stable_id(rule["need_key"] or rule["name"])
        payload = current[identity]["payload"] if identity in current else rule
        changes.append(proposal(current, kind="knowledge", identity=identity, payload=payload))
    changes.extend(package_changes(current, changes, definition_id=definition["id"]))
    guards = {
        i: digest(session.get(ProductRecord, i).payload)
        for c in changes
        for i in evidence_source_ids(c["payload"])
    }
    for row in FACTS:
        source_id = sources.get(DISTRIBUTED, row)[1]["id"]
        guards[source_id] = digest(session.get(ProductRecord, source_id).payload)
    return dict(changes=changes, fingerprint=digest(changes), source_guards=guards)


def environment_change(current, *, definition, variant_id, row, sources):
    matching = [
        (i, r)
        for i, r in current.items()
        if r["kind"] == "knowledge"
        and r["payload"]["kind"] == "suitability"
        and r["payload"].get("system_definition_id") == definition["id"]
        and r["payload"]["role"] == OS_ROWS[row]
        and r["payload"]["selector"]["variant_ids"] == [variant_id]
    ]
    if len(matching) != 1:
        raise ValueError("待核对的环境关系不唯一：" + OS_ROWS[row])
    identity, record = matching[0]
    return proposal(
        current,
        kind="knowledge",
        identity=identity,
        payload=os_relation(record["payload"], row=row, sources=sources),
    )
