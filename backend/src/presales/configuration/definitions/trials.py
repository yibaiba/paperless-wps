"""Read-only checks of a package's pinned suitability rules, without a project or approval."""

from pydantic import Field, model_validator

from presales.rules.repository import RuleConflict

from ..catalog.service import CatalogService
from ..common import Entities, Input, Text, view
from ..knowledge.evaluator import scope_matches
from ..knowledge.semantics import candidate_check_v3, role_matches
from ..projects.calculation.coverage import role_coverage
from ..projects.schemas import EnvironmentParameter


class PackageTrial(Input):
    expected_revision: int = Field(ge=1)
    role_id: Text
    variant_id: Text
    environment: list[EnvironmentParameter] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct_inputs(self):
        if len({p.key for p in self.environment}) != len(self.environment):
            raise ValueError("试查输入字段重复，请明确每个参数采用的值")
        return self


def evaluate_trial(package, variant, data, *, decisions=None):
    if package["revision"] != data.expected_revision:
        raise RuleConflict("知识包已有新修订，请刷新后重新试查")
    definition = package["definition"]
    role = next((r for r in definition["roles"] if r["id"] == data.role_id), None)
    if role is None:
        raise ValueError("此角色不属于知识包引用的系统定义修订")
    requirement = dict(
        id="package-trial",
        device_id="package-trial",
        role_id=role["id"],
        role=role["name"],
        system_definition_id=definition["id"],
        system=definition["name"],
        capability_ids=role.get("capability_ids", []),
        environment=[p.model_dump(mode="json") for p in data.environment],
    )
    result = candidate_check_v3(
        variant, requirement=requirement, knowledge=package["rules"], decisions=decisions
    )
    coverage = role_coverage(requirement, variant, package)
    drafts = [
        dict(id=r["id"], revision=r["revision"], name=r["name"], evidence=r["evidence"])
        for r in package["rules"]
        if r["kind"] == "suitability"
        and r["status"] == "draft"
        and role_matches(r, requirement)
        and scope_matches(variant, r["selector"])
    ]
    return dict(
        package_id=package["id"],
        package_revision=package["revision"],
        package_status=package["status"],
        definition_revision=definition["revision"],
        definition_status=definition["status"],
        role_id=role["id"],
        variant_id=variant["id"],
        variant_revision=variant["revision"],
        variant_name=variant["name"],
        status=result["status"],
        evidence=result["evidence"],
        draft_relations=drafts,
        coverage=coverage["check"],
        notice="只试查此角色、当前产品配置和包内固定适用关系。未检查整套配套、数量、共享和容量；"
        "草稿关系不作为通过依据。项目还会使用匹配的通用知识，最终以项目检查为准。",
    )


def run_trial(session, identity, data, *, decisions=None):
    decisions = decisions.request() if decisions else None
    package = view(Entities(session).get(identity, kind="knowledge_package"))
    variants = CatalogService(session).variants(ids=[data.variant_id])
    if not variants:
        raise ValueError("试查的产品配置不存在")
    return evaluate_trial(package, variants[0], data, decisions=decisions)
