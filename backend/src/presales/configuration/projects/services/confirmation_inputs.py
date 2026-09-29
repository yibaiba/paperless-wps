"""Validate newly introduced input checks against saved definition snapshots."""

from ..calculation.feature_choices import defined_systems, feature_checks
from ..planning.quantity_scope import scope_gap


def saved_input_checks(configuration, *, entities):
    snapshot_id = configuration.get("definition_snapshot_id")
    if not snapshot_id:
        return []  # Legacy projects without definitions have no definition-scoped rules.
    definitions = entities.get(snapshot_id, kind="definition_snapshot").payload
    checks = feature_checks(configuration, definitions)
    for system, definition in defined_systems(configuration, definitions):
        selected = {
            r.get("role_id")
            for r in configuration["requirements"]
            if r["system_id"] == system["id"]
        }
        for role in definition.get("roles", []):
            basis = role.get("quantity_basis")
            if role["id"] not in selected or not basis or basis["status"] != "confirmed":
                continue
            gap = scope_gap(basis, system, configuration)
            if gap:
                checks.append(dict(gap, status="unknown"))
    return checks
