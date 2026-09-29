from uuid import NAMESPACE_URL, uuid5

from presales.rules.calculation import digest

from ...common import Entities
from ...definitions.service import Definitions


def resolve_definitions(session, data, *, refresh=False):
    identity = data.get("definition_snapshot_id")
    if identity and not refresh:
        return Entities(session).get(identity, kind="definition_snapshot").payload, identity
    snapshot = Definitions(session).current_snapshot()
    identity = str(uuid5(NAMESPACE_URL, "presales-definitions:" + digest(snapshot)))
    from ...models import Entity

    if session.get(Entity, identity) is None:
        # Content-derived identity makes repeated checks reuse an immutable bundle.
        from sqlalchemy.exc import IntegrityError

        try:
            with session.begin_nested():
                session.add(Entity(id=identity, kind="definition_snapshot", payload=snapshot))
                session.flush()
        except IntegrityError:
            stored = session.get(Entity, identity)
            if stored is None or stored.payload != snapshot:
                raise
    return snapshot, identity


def project_knowledge(data, definitions):
    packages = {item["id"]: item for item in definitions["packages"]}
    selected = {system.get("knowledge_package_id") or None for system in data["systems"]}
    if not selected or selected == {None}:
        return data["knowledge_snapshot"]
    scoped, pinned = {}, {}
    for system in data["systems"]:
        identity = system.get("knowledge_package_id")
        if not identity:
            continue
        package = packages.get(identity)
        if not package or package["system_definition_id"] != system.get("definition_id"):
            raise ValueError("项目知识包不存在、未发布或不属于所选系统")
        for rule in package["rules"]:
            if rule["id"] in pinned and pinned[rule["id"]] != rule["revision"]:
                raise ValueError("所选知识包引用同一关系的不同修订，请明确统一版本")
            pinned[rule["id"]] = rule["revision"]
            add_membership(scoped, rule, identity)
    if None in selected:
        for rule in data["knowledge_snapshot"]:
            add_membership(scoped, rule, None)
    return list(scoped.values())


def add_membership(scoped, rule, package_id):
    key = (rule["id"], rule["revision"])
    entry = scoped.setdefault(key, dict(rule, _knowledge_packages=[]))
    if package_id not in entry["_knowledge_packages"]:
        entry["_knowledge_packages"].append(package_id)


def definition_version_changes(session, data):
    identity = data.get("definition_snapshot_id")
    if not identity:
        return []
    entities = Entities(session)
    snapshot = entities.get(identity, kind="definition_snapshot").payload
    definitions = {d["id"]: d for d in snapshot["definitions"]}
    packages = {p["id"]: p for p in snapshot["packages"]}
    used = {}
    for system in data["systems"]:
        package = packages.get(system.get("knowledge_package_id"))
        definition = (
            package["definition"] if package else definitions.get(system.get("definition_id"))
        )
        for kind, record in (("system_definition", definition), ("knowledge_package", package)):
            if record:
                used[(kind, record["id"], record["revision"])] = record
        for profile in (definition or {}).get("inspection_profiles", []):
            used[("inspection_profile", profile["id"], profile["revision"])] = profile
    changes = []
    for (kind, identity, revision), record in used.items():
        current = entities.get(identity, kind=kind)
        if current.revision != revision:
            changes.append(
                dict(
                    kind=kind,
                    id=identity,
                    name=record["name"],
                    used=revision,
                    current=current.revision,
                )
            )
    return changes
