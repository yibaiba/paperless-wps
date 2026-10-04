"""Compare bundled occupancy with small, independently enumerated allocations."""

from decimal import Decimal
from itertools import product
from random import Random

from presales.configuration.projects.calculation.included_occupancy import IncludedOccupancy


def can_assign(capacities, requests):
    if not requests:
        return True
    scope, amount = requests[0]
    roles = list(capacities) if scope is None else sorted(scope)
    for assigned in product(*(range(min(amount, capacities[r]) + 1) for r in roles)):
        if sum(assigned) != amount:
            continue
        remaining = dict(capacities)
        for role, count in zip(roles, assigned, strict=True):
            remaining[role] -= count
        if can_assign(remaining, requests[1:]):
            return True
    return False


def test_available_agrees_with_exhaustive_small_integer_allocations():
    random = Random(20261004)
    roles = ("a", "b", "c")
    scopes = [
        frozenset(r for r, enabled in zip(roles, flags, strict=True) if enabled)
        for flags in product((False, True), repeat=3)
        if any(flags)
    ] + [None]
    for _ in range(80):
        capacities = {r: random.randint(1, 2) for r in roles}
        reservations = {s: random.randint(1, 2) for s in random.sample(scopes, 2)}
        pool = IncludedOccupancy(
            capacities={r: Decimal(q) for r, q in capacities.items()},
            total=Decimal(sum(capacities.values())),
            reservations={s: Decimal(q) for s, q in reservations.items()},
        )
        requests = list(reservations.items())
        feasible = can_assign(capacities, requests)
        assert bool(pool.conflicting) is not feasible
        if not feasible:
            continue
        for scope in scopes:
            expected = max(
                q
                for q in range(sum(capacities.values()) + 1)
                if can_assign(capacities, [*requests, (scope, q)])
            )
            assert pool.available(scope, upper_bound=Decimal(sum(capacities.values()))) == expected


def test_a_large_connected_scope_does_not_hide_an_overdrawn_subset():
    a, b, c = (frozenset(s) for s in ("ab", "bc", "cd"))
    pool = IncludedOccupancy(
        capacities={r: Decimal(q) for r, q in dict(a=1, b=1, c=1, d=20).items()},
        total=Decimal(23),
        reservations={a: Decimal(2), b: Decimal(2), c: Decimal(1)},
    )
    assert pool.conflicting == {a, b}
    assert (pool.conflict_capacity, pool.conflict_quantity) == (3, 4)


def test_available_redistributes_flexible_credits_without_changing_their_quantities():
    pool = IncludedOccupancy(
        capacities={r: Decimal("0.5") for r in "abc"},
        total=Decimal("1.5"),
        reservations={frozenset("ab"): Decimal("0.5"), frozenset("bc"): Decimal("0.5")},
    )
    assert pool.available(frozenset("a"), upper_bound=Decimal("0.5")) == Decimal("0.5")
    assert pool.available(frozenset("a"), upper_bound=Decimal("0.5")) == Decimal("0.5")
    assert not pool.conflicting


def test_unassigned_stock_only_available_to_unscoped_demand():
    pool = IncludedOccupancy(
        capacities={"a": Decimal(2)}, total=Decimal(5), reservations={None: Decimal(4)}
    )
    assert pool.available(frozenset({"a"}), upper_bound=Decimal(5)) == 1
    assert pool.available(None, upper_bound=Decimal(5)) == 1


def test_global_host_quantity_still_limits_shared_single_device():
    pool = IncludedOccupancy(
        capacities={"a": Decimal(1), "b": Decimal(1)},
        total=Decimal(1),
        reservations={frozenset({"a"}): Decimal(1)},
    )
    assert pool.available(frozenset({"b"}), upper_bound=Decimal(1)) == 0
