"""Conservative business dependency closure for read-only next-edit checks."""

from collections import defaultdict
from dataclasses import dataclass, replace

from presales.rules.calculation import digest

from ...knowledge.package_scope import package_allows
from ..calculation.demand_identity import DemandIdentities


def connect(graph, nodes):
    nodes = list(nodes)
    if not nodes:
        return
    first = nodes[0]
    for node in nodes[1:]:
        graph[first].add(node)
        graph[node].add(first)


def requirement_edges(data, graph):
    for requirement in data["requirements"]:
        devices = [a["device_id"] for a in requirement.get("allocations", [])]
        if requirement.get("device_id"):
            devices.append(requirement["device_id"])
        connect(
            graph,
            [
                ("system", requirement["system_id"]),
                ("requirement", requirement["id"]),
                *(("device", identity) for identity in devices),
            ],
        )


def rule_groups(data, rule):
    scope = rule.get("calculation_scope")
    if scope == "device":
        return {d["id"]: [("device", d["id"])] for d in data["devices"]}
    systems = [s for s in data["systems"] if package_allows(rule, s["knowledge_package_id"])]
    groups = defaultdict(list)
    for system in systems:
        key = (
            "project" if scope == "project" else system.get("room_id" if scope == "room" else "id")
        )
        if key:
            groups[key].append(("system", system["id"]))
    if scope == "project":
        # Project-scoped rules can include unassigned products as contributors.
        groups["project"].extend(("device", d["id"]) for d in data["devices"])
    return groups


def dependency_graph(data, rules):
    graph = defaultdict(set)
    requirement_edges(data, graph)
    identities = DemandIdentities(data, rules=rules)
    for rule in rules:
        if rule["status"] == "disabled":
            continue
        if rule["kind"] == "combination":
            # Combination targets may belong to another package in the same business scope.
            scoped = dict(
                rule, calculation_scope=rule["combination"].get("scope"), _knowledge_packages=None
            )
            for members in rule_groups(data, scoped).values():
                connect(graph, members)
            continue
        if rule["kind"] != "accessory":
            continue
        for scope_id, members in rule_groups(data, rule).items():
            legacy = digest([rule["id"], rule.get("calculation_scope"), scope_id])
            connect(
                graph,
                [*members, ("demand", identities.identity(rule, scope_id)), ("demand", legacy)],
            )
    for collection in ("accessory_allocations", "included_allocations"):
        for allocation in data[collection]:
            members = [("device", allocation["device_id"]), ("demand", allocation["demand_id"])]
            if allocation.get("id"):
                members.append(("allocation", allocation["id"]))
            connect(graph, members)
    for device in data["devices"]:
        if device.get("origin_suggestion"):
            connect(graph, [("device", device["id"]), ("demand", device["origin_suggestion"])])
    return graph


@dataclass(frozen=True)
class DependencyScope:
    system_id: str
    references: frozenset[str] = frozenset()

    def retaining(self, data, rules):
        identities = set().union(*self.closure(data, rules).values())
        return replace(self, references=self.references | identities)

    def closure(self, data, rules):
        graph = dependency_graph(data, rules)
        roots = {("system", self.system_id)}
        roots.update(
            ("system", s["id"])
            for s in data["systems"]
            if {s["id"], s.get("room_id")} & self.references
        )
        roots.update(node for node in graph if node[1] in self.references)
        roots.update(("device", d["id"]) for d in data["devices"] if d["id"] in self.references)
        seen, pending = set(), list(roots)
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            pending.extend(graph[node] - seen)
        return {
            kind: {identity for tag, identity in seen if tag == kind}
            for kind in ("system", "requirement", "device", "demand")
        }


def operation_references(operations):
    """Only structured operation identities are roots, never spreadsheet free text."""
    fields = {
        "id",
        "device_id",
        "system_id",
        "room_id",
        "requirement_id",
        "demand_id",
        "allocation_id",
    }

    def collect(value):
        if isinstance(value, list):
            return set().union(*(collect(item) for item in value))
        if not isinstance(value, dict):
            return set()
        found = {value[key] for key in fields & value.keys() if isinstance(value[key], str)}
        return found | set().union(*(collect(item) for item in value.values()))

    return frozenset(collect(operations))
