"""Read project inputs once; hypothetical candidate checks never write devices."""

from copy import deepcopy

from ...knowledge.semantics import role_matches
from ..calculation.combinations import combination_checks, role_definition
from ..calculation.demands import accessory_demands_v3
from ..calculation.inclusions import included_fulfillment
from ..planning.quantities import role_quantity
from ..role_allocations import project_allocations
from ..schemas import Deployment
from .definition_snapshot import project_knowledge, resolve_definitions


class CandidateCombinations:
    def __init__(self, repository, request):
        self.repository = repository
        self.decisions = repository.decisions if request.decision_runtime == "zen-v1" else None
        configuration = request.configuration
        requirement = next(
            (r for r in configuration.requirements if r.id == request.requirement_id), None
        )
        if requirement is None:
            raise ValueError("候选检查引用的项目角色不存在")
        system = next(s for s in configuration.systems if s.id == requirement.system_id)
        identity = dict(
            system_definition_id=system.definition_id,
            role_id=requirement.role_id,
            system=system.kind,
            role=requirement.role,
        )
        if not role_matches(identity, request.model_dump(mode="json")):
            raise ValueError("候选查询与项目角色不一致")
        self.data, self.variants, self.catalog = repository.prepare(configuration)
        self.definitions, _ = resolve_definitions(repository.session, self.data)
        self.data["knowledge_snapshot"] = project_knowledge(self.data, self.definitions)
        self.requirement = requirement.model_dump(mode="json")
        self.quantity, self.gap, _ = role_quantity(
            role_definition(system.model_dump(mode="json"), requirement.role_id, self.definitions),
            system.model_dump(mode="json"),
            configuration=self.data,
            engine=repository.engine,
        )

    def check(self, candidate):
        relevant = [
            r
            for r in self.data["knowledge_snapshot"]
            if r["kind"] == "combination" and r["status"] != "disabled"
        ]
        if not relevant:
            return candidate
        if self.gap or not self.quantity:
            return dict(
                candidate,
                status="conflict" if candidate["status"] == "conflict" else "unknown",
                combination_checks=[],
                combination_notice="角色数量依据或输入不足，组合检查待确认",
            )
        variant = candidate["variant"]
        identity = "candidate:" + self.requirement["id"]
        data = deepcopy(self.data)
        if not variant["source_ids"]:
            return dict(
                candidate,
                status="conflict" if candidate["status"] == "conflict" else "unknown",
                combination_notice="候选缺少来源，组合检查待确认",
            )
        device = Deployment(
            id=identity,
            name=variant["name"],
            variant_id=variant["id"],
            source_id=variant["source_ids"][0],
            quantity=self.quantity,
            kind="hardware",
            variant_snapshot=variant,
        ).model_dump(mode="json")
        data["devices"].append(device)
        data["requirements"] = [
            dict(r, device_id=identity, allocations=[]) if r["id"] == self.requirement["id"] else r
            for r in data["requirements"]
        ]
        data, _ = project_allocations(data)
        variants = dict(self.variants, **{identity: variant})
        suggestions = accessory_demands_v3(
            data,
            variants=variants,
            catalog_variants=self.catalog,
            engine=self.repository.engine,
            decisions=self.decisions,
        )
        suggestions, _ = included_fulfillment(data, suggestions)
        checks = combination_checks(
            data,
            variants=variants,
            suggestions=suggestions,
            definitions=self.definitions,
            engine=self.repository.engine,
            decisions=self.decisions,
        )
        statuses = {c["status"] for c in checks} | {candidate["status"]}
        status = (
            "conflict" if "conflict" in statuses else "unknown" if "unknown" in statuses else "pass"
        )
        return dict(
            candidate,
            status=status,
            combination_checks=checks,
            evidence=[
                *candidate["evidence"],
                *[
                    dict(
                        name=c["message"], evidence=c["evidence"][0]["evidence"], result=c["status"]
                    )
                    for c in checks
                ],
            ],
            combination_notice="按新增独立设备试查，未加入清单；关联已有设备后仍需整套检查",
        )
