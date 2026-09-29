"""Read-only package revisions preview; saving still uses optimistic revision checks."""

from presales.rules.repository import RuleConflict

from ..common import view
from .readiness import package_readiness
from .schemas import KnowledgePackage
from .service import Definitions


def preview_package(session, identity, change):
    service = Definitions(session)
    before = view(service.entities.get(identity, kind="knowledge_package"))
    if before["revision"] != change.expected_revision:
        raise RuleConflict("知识包已有新修订，请刷新后重新预览")
    payload = service.package_payload(KnowledgePackage.model_validate(change.payload))
    after = dict(id=identity, revision=before["revision"] + 1, **payload)
    changes = [
        dict(field=key, before=before.get(key), after=value)
        for key, value in payload.items()
        if key not in {"rules", "definition"} and before.get(key) != value
    ]
    old_rules = {r["id"]: r for r in before["rules"]}
    new_rules = {r["id"]: r for r in after["rules"]}
    relations = [
        dict(id=key, before=old_rules.get(key), after=new_rules.get(key))
        for key in sorted(old_rules.keys() | new_rules.keys())
        if old_rules.get(key) != new_rules.get(key)
    ]
    latest = {r["id"]: r["revision"] for r in service.entities.list("knowledge")}
    latest.update({d["id"]: d["revision"] for d in service.entities.list("system_definition")})
    return dict(
        expected_revision=before["revision"],
        payload=change.payload,
        changes=changes,
        relations=relations,
        definition=dict(before=before["definition"], after=after["definition"]),
        readiness=package_readiness(after, latest=latest),
    )
