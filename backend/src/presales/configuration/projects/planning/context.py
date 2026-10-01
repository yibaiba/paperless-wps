from dataclasses import dataclass, field

from ...knowledge.evaluator import context_for
from ...knowledge.semantics import condition_result
from ..calculation.inspections import effective_environment
from ..candidates import candidate_results
from ..schemas import CandidateRequest
from ..services.definition_snapshot import resolve_definitions
from .questions import question


@dataclass
class PlanningContext:
    repository: object
    configuration: dict
    proposal_id: str
    deployment: str
    variants: dict = field(init=False)
    packages: dict = field(init=False)
    candidate_cache: dict = field(default_factory=dict)
    decisions: list = field(default_factory=list)

    def __post_init__(self):
        self.variants = {v["id"]: v for v in self.repository.catalog.variants()}
        definitions, _ = resolve_definitions(self.repository.session, self.configuration)
        self.packages = {p["id"]: p for p in definitions["packages"]}

    def candidates(self, requirement, system):
        key = requirement["id"]
        if key not in self.candidate_cache:
            request = CandidateRequest(
                calculation_version=3,
                system=system["kind"],
                role=requirement["role"],
                system_definition_id=system["definition_id"],
                role_id=requirement["role_id"],
                knowledge_package_id=system["knowledge_package_id"],
                definition_snapshot_id=self.configuration["definition_snapshot_id"],
                knowledge_snapshot_id=self.configuration["knowledge_snapshot_id"],
                environment=effective_environment(system, requirement)[0],
                include_all=bool(self.preference(requirement["id"]).get("required_variant_id")),
            )
            self.candidate_cache[key] = candidate_results(
                request, session=self.repository.session, catalog=self.repository.catalog
            )
        return self.candidate_cache[key]

    def preference(self, requirement_id):
        return next(
            (
                p
                for p in self.configuration["generation"]["preferences"]
                if p["requirement_id"] == requirement_id
            ),
            {},
        )


def select_candidates(items, preferences):
    for preference in preferences:
        items = [
            i for i in items if i["variant"]["id"] not in preference.get("excluded_variant_ids", [])
        ]
        specified = preference.get("required_variant_id")
        if specified:
            items = [i for i in items if i["variant"]["id"] == specified]
        source_id = preference.get("source_id")
        if source_id:
            items = [i for i in items if source_id in i["variant"]["source_ids"]]
    return items


def ordered_candidates(context, items, *, requirement, system, need_key=""):
    preference = context.preference(requirement["id"]) if not need_key else {}
    items = select_candidates(items, [preference])
    orders, evidence = [], []
    package = context.packages.get(system["knowledge_package_id"], {})
    for rule in package.get("recommendations", []):
        if rule["status"] != "confirmed" or (rule["role_id"], rule["need_key"]) != (
            requirement["role_id"],
            need_key,
        ):
            continue
        environment = effective_environment(system, requirement)[0]
        applicable = {
            i["variant"]["id"]
            for i in items
            if condition_result(rule["conditions"], context_for(i["variant"], environment))
            == "pass"
        }
        order = [identity for identity in rule["variant_ids"] if identity in applicable]
        if order:
            orders.append(order)
            evidence.append(rule)
    unique = {tuple(order) for order in orders}
    order = next(iter(unique)) if len(unique) == 1 else ()
    feasible = [i for i in items if i["status"] != "conflict"]
    missing = None
    if len(feasible) > 1 and (not order or any(i["variant"]["id"] not in order for i in feasible)):
        missing = question(
            "recommendation_missing",
            requirement["id"],
            "recommendations",
            "存在多个可行候选，缺少一致且覆盖候选的公司推荐顺序",
            evidence=evidence,
        )
    rank = {identity: index for index, identity in enumerate(order)}
    # ID is only deterministic branch enumeration, never a business recommendation.
    return (
        sorted(
            feasible,
            key=lambda i: (
                i["status"] != "pass",
                rank.get(i["variant"]["id"], len(rank)),
                i["variant"]["id"],
            ),
        ),
        missing,
        evidence,
    )
