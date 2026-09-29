from decimal import Decimal, InvalidOperation

from .quantity_scope import scope_gap
from .questions import question


def role_quantity(role, system, *, configuration, engine):
    basis = role.get("quantity_basis")
    identity = system["id"] + "/" + role["id"]
    if not basis or basis["status"] != "confirmed":
        return (
            None,
            question("role_quantity_missing", identity, "quantity_basis", "角色数量依据尚未确认"),
            None,
        )
    gap = scope_gap(basis, system, configuration)
    if gap:
        return None, gap, None
    value = "1"
    if basis["mode"] != "per_group":
        fields = scope_inputs(basis["scope"], system, configuration)
        attribute = next((a for a in fields if a["key"] == basis["input_key"]), None)
        if attribute is None or attribute["value"] is None:
            return (
                None,
                question(
                    "quantity_input_missing",
                    system["id"],
                    basis["input_key"],
                    "请补充数量输入：" + basis["input_key"],
                    recipient="customer",
                    evidence=[basis],
                ),
                None,
            )
        if attribute.get("unit", "") != basis["input_unit"]:
            return (
                None,
                question(
                    "quantity_unit_conflict",
                    system["id"],
                    basis["input_key"],
                    "数量输入单位与角色数量依据不一致",
                    recipient="customer",
                    evidence=[basis],
                ),
                None,
            )
        value = attribute["value"]
    try:
        amount = Decimal(str(value))
    except (ValueError, InvalidOperation):
        raise ValueError("角色数量输入不是数值：" + basis["input_key"]) from None
    if not amount.is_finite() or amount < 0:
        raise ValueError("角色数量输入必须是有限非负数")
    result = engine.calculate(mode=basis["mode"], quantity=str(amount), factor=basis["factor"])
    evidence = dict(
        basis=basis,
        calculation={k: result[k] for k in ("quantity", "input", "expression", "engine")},
    )
    return Decimal(result["quantity"]), None, evidence


def scope_inputs(scope, system, configuration):
    if scope == "project":
        return configuration.get("project_inputs", [])
    if scope == "room":
        return configuration.get("room_inputs", {}).get(system.get("room_id"), [])
    return system["inputs"]
