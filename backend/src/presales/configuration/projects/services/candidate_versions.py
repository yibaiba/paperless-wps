"""Candidate knowledge and its fixed decision artifact must describe the same revisions."""

from presales.rules.calculation import digest

from ...common import Entities
from ...decisions.snapshots import resolve_bundle


def validate_bundle(request, *, knowledge, session, decisions):
    stored = Entities(session).get(request.decision_bundle_id, kind="decision_bundle").payload
    selected = [
        r
        for r in stored["rules"]
        if "_knowledge_packages" not in r
        or (request.knowledge_package_id or None) in r["_knowledge_packages"]
    ]
    if signatures(selected) != signatures(knowledge):
        raise ValueError("候选知识快照与固定决策资料不一致，请重新读取项目版本")
    bundle, _ = resolve_bundle(
        session,
        stored["rules"],
        identity=request.decision_bundle_id,
        compiler=decisions.bundle,
    )
    decisions.load(bundle)


def signatures(rules):
    # Revision payloads omit the current-record timestamp; it is not rule semantics.
    metadata = {"_knowledge_packages", "updated_at"}
    return sorted(digest({k: v for k, v in r.items() if k not in metadata}) for r in rules)
