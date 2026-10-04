"""Exact occupancy of bundled units across intersecting role sets; no product selection."""

from collections import deque
from decimal import Decimal

SOURCE, SINK, HOST, QUERY = ("source",), ("sink",), ("host",), ("query",)


class ResidualCapacity:
    def __init__(self):
        self.edges = {}

    def connect(self, start, end, capacity):
        self.edges.setdefault(start, {})[end] = capacity
        self.edges.setdefault(end, {}).setdefault(start, Decimal(0))

    def paths(self):
        parents, pending = {SOURCE: None}, deque([SOURCE])
        while pending:
            start = pending.popleft()
            for end, remaining in self.edges.get(start, {}).items():
                if remaining > 0 and end not in parents:
                    parents[end] = start
                    pending.append(end)
        return parents

    def allocate(self):
        allocated = Decimal(0)
        while SINK in (parents := self.paths()):
            path, end = [], SINK
            while parents[end] is not None:
                start = parents[end]
                path.append((start, end))
                end = start
            quantity = min(self.edges[start][end] for start, end in path)
            for start, end in path:
                self.edges[start][end] -= quantity
                self.edges[end][start] += quantity
            allocated += quantity
        return allocated

    def copy(self):
        result = ResidualCapacity()
        result.edges = {node: dict(edges) for node, edges in self.edges.items()}
        return result


class IncludedOccupancy:
    def __init__(self, *, capacities, total, reservations):
        self.available_cache = {}
        self.capacities = dict(capacities)
        unassigned = max(total - sum(capacities.values(), Decimal(0)), Decimal(0))
        self.capacities[None] = unassigned
        self.network = ResidualCapacity()
        for role, quantity in self.capacities.items():
            self.network.connect(("role", role), HOST, quantity)
        self.network.connect(HOST, SINK, total)
        self.scopes = {}
        ordered = sorted(reservations, key=lambda s: (s is not None, sorted(s or [])))
        for index, scope in enumerate(ordered):
            node = ("reservation", index)
            self.scopes[scope] = node
            self.network.connect(SOURCE, node, reservations[scope])
            self.connect_scope(self.network, node, scope=scope, quantity=reservations[scope])
        self.network.allocate()
        reachable = self.network.paths()
        self.conflicting = {scope for scope, node in self.scopes.items() if node in reachable}
        self.conflict_quantity = sum((reservations[s] for s in self.conflicting), Decimal(0))
        self.conflict_capacity = sum(
            (quantity for role, quantity in self.capacities.items() if ("role", role) in reachable),
            Decimal(0),
        )

    def connect_scope(self, network, node, *, scope, quantity):
        roles = self.capacities if scope is None else sorted(scope)
        for role in roles:
            network.connect(node, ("role", role), quantity)

    def available(self, scope, *, upper_bound):
        if upper_bound <= 0:
            return Decimal(0)
        key = scope, upper_bound
        if key not in self.available_cache:
            self.available_cache[key] = self.remaining(scope, upper_bound=upper_bound)
        return self.available_cache[key]

    def remaining(self, scope, *, upper_bound):
        network = self.network.copy()
        # Existing credits retain their allocation; residual paths may redistribute
        # their host units, but never reduce an existing fulfilled quantity.
        for node in self.scopes.values():
            network.edges[SOURCE][node] = Decimal(0)
        network.connect(SOURCE, QUERY, upper_bound)
        self.connect_scope(network, QUERY, scope=scope, quantity=upper_bound)
        return network.allocate()
