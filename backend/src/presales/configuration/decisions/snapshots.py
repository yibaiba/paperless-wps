"""Immutable compiled evidence, separate from quantity/calculation schema versions."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.exc import IntegrityError

from ..common import Entities
from ..models import Entity
from .compiler import COMPILER_VERSION, ENGINE_VERSION, compile_rules

LEGACY_RUNTIME = "python-v3"
ZEN_RUNTIME = "zen-v1"


def resolve_bundle(session, rules, *, identity=None, refresh=False, compiler=compile_rules):
    compiled = compiler(rules)
    if identity and not refresh:
        stored = Entities(session).get(identity, kind="decision_bundle").payload
        if (stored["compiler_version"], stored["engine_version"]) != (
            COMPILER_VERSION,
            ENGINE_VERSION,
        ):
            raise ValueError("固定的决策运行时版本不可用，不能静默重编译历史资料")
        if stored["rules"] == rules:
            if stored["hash"] != compiled["hash"]:
                raise ValueError("固定知识的编译语义已变化，不能静默重编译")
            return stored, identity
    identity = str(uuid5(NAMESPACE_URL, "presales-decision:" + compiled["hash"]))
    existing = session.get(Entity, identity)
    if existing is None:
        try:
            with session.begin_nested():
                session.add(Entity(id=identity, kind="decision_bundle", payload=compiled))
                session.flush()
        except IntegrityError:
            existing = session.get(Entity, identity)
            if existing is None or existing.payload != compiled:
                raise
    elif existing.kind != "decision_bundle" or existing.payload != compiled:
        raise ValueError("决策资料标识与内容不一致")
    return compiled, identity


def decision_metadata(bundle, identity):
    return dict(
        runtime=ZEN_RUNTIME,
        bundle_id=identity,
        hash=bundle["hash"],
        compiler_version=bundle["compiler_version"],
        engine_version=bundle["engine_version"],
        rules=[
            dict(id=r["id"], revision=r["revision"], evidence_refs=r.get("evidence_refs", []))
            for r in bundle["rules"]
        ],
    )
