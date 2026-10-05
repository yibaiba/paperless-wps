"""Read project inputs once; hypothetical candidate checks never write devices."""

from copy import deepcopy

from ...knowledge.semantics import role_matches
from ..calculation.combinations import combination_checks, role_definition
from ..calculation.context import prepare_demands, prepare_roles
from ..calculation.coverage import coverage_checks
from ..calculation.usage import build_usage_projection
from ..calculation.usage.checks import usage_checks
from ..planning.quantities import role_quantity
from ..role_allocations import restore_requirement_ids
from ..schemas import Deployment
from .evaluation_context import prepare_evaluation


class CandidateCombinations:
    def __init__(self, repository, request):
        self.repository = repository
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
        context = prepare_evaluation(
            repository, self.data, variants=self.variants, catalog=self.catalog
        )
        self.context = context
        self.data, self.definitions = context.data, context.definitions
        self.decisions = context.decisions
        roles = prepare_roles(self.data, definitions=self.definitions)
        self.role = next(
            r
            for r in roles.data["requirements"]
            if r.get("allocation_parent_id", r["id"]) == requirement.id
        )
        self.input_checks = restore_requirement_ids(
            [
                c
                for c in roles.checks
                if roles.aliases.get(c.get("requirement_id"), c.get("requirement_id"))
                == requirement.id
            ],
            roles.aliases,
        )
        self.requirement = requirement.model_dump(mode="json")
        self.quantity, self.gap, _ = role_quantity(
            role_definition(system.model_dump(mode="json"), requirement.role_id, self.definitions),
            system.model_dump(mode="json"),
            configuration=self.data,
            engine=repository.engine,
        )

    def check(self, candidate):
        if self.gap or not self.quantity:
            return dict(
                candidate,
                status="conflict" if candidate["status"] == "conflict" else "unknown",
                compatibility_status=candidate["status"],
                usage_status="unknown",
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
        context = prepare_roles(data, definitions=self.definitions)
        data, aliases = context.data, context.aliases
        variants = dict(self.variants, **{identity: variant})
        suggestions, _ = prepare_demands(
            context,
            variants=variants,
            catalog=self.catalog,
            engine=self.repository.engine,
            decisions=self.decisions,
        )
        checks = combination_checks(
            data,
            variants=variants,
            suggestions=suggestions,
            definitions=self.definitions,
            engine=self.repository.engine,
            decisions=self.decisions,
        )
        _, policies = coverage_checks(data, self.definitions, variants, demands=suggestions)
        projection = build_usage_projection(
            data,
            demands=[d for d in suggestions if d["selected"]],
            definitions=self.definitions,
            policies=policies,
            inspections=context.policies,
        )
        related = [
            c
            for c in usage_checks(
                data, projection.views(), variants=variants, decisions=self.decisions
            )
            if c.get("device_id") == identity or c.get("requirement_id") == self.role["id"]
        ]
        related = restore_requirement_ids(related, aliases)
        checks = restore_requirement_ids(checks, aliases)
        # The replaced device may remain unassigned. Its unrelated gaps belong to
        # full project checks; retain both constraints triggered by and targeting this role.
        checks = [
            check
            for check in checks
            if identity in check["device_ids"]
            or self.requirement["id"] in check["trigger_requirement_ids"]
            or any(self.requirement["id"] in group["requirement_ids"] for group in check["groups"])
        ]
        statuses = {c["status"] for c in [*checks, *related]} | {candidate["status"]}
        status = (
            "conflict" if "conflict" in statuses else "unknown" if "unknown" in statuses else "pass"
        )
        return dict(
            candidate,
            status=status,
            compatibility_status=candidate["status"],
            usage_status=(
                "conflict"
                if any(c["status"] == "conflict" for c in related)
                else "unknown"
                if any(c["status"] == "unknown" for c in related)
                else "pass"
            ),
            combination_checks=checks,
            usage_checks=related,
            usage_projection=dict(version=projection.version, fingerprint=projection.fingerprint),
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
