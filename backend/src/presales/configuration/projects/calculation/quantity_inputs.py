"""Resolve accessory inputs without losing the identity of their owning scope."""

from decimal import Decimal, InvalidOperation


def find_input(inputs, key):
    return next((item for item in inputs if item["key"] == key), None)


def scoped_input(data, *, rule, system):
    scope, key = rule.get("calculation_scope"), rule.get("quantity_key")
    if scope == "project":
        return find_input(data.get("project_inputs", []), key), scope, "project"
    if scope == "room":
        room_id = system.get("room_id")
        inputs = data.get("room_inputs", {}).get(room_id, [])
        return find_input(inputs, key), scope, room_id
    return find_input(system.get("inputs", []), key), "system", system.get("id")


def resolve_input(data, *, rule, requirement, system):
    key = rule.get("quantity_key")
    attribute, scope, identity = scoped_input(data, rule=rule, system=system)
    role_input = find_input(requirement.get("environment", []), key)
    # Room/project inputs have their own schema scope; same-key role fields are independent.
    if attribute is not None and scope in {"room", "project"}:
        return attribute, scope, identity, False
    system_input = find_input(system.get("inputs", []), key)
    if system_input is not None:
        conflict = role_input is not None and input_value(system_input) != input_value(role_input)
        return system_input, "system", system["id"], conflict
    if role_input is None and rule.get("calculation_scope") != "device":
        return None, scope, identity, False
    # Retain historical role-level contributions when no scoped value has been provided.
    role_id = requirement.get("allocation_parent_id", requirement.get("id"))
    return role_input, "role", role_id, False


def input_value(attribute):
    return attribute.get("value"), attribute.get("unit", "")


def numeric_quantity(attribute, *, rule):
    if attribute is None or attribute.get("value") is None:
        return None, "缺少需求参数：" + rule.get("quantity_key", "")
    try:
        value = Decimal(str(attribute["value"]))
    except InvalidOperation:
        return None, "需求参数不是有效数值：" + rule.get("quantity_key", "")
    if not value.is_finite() or value < 0:
        return None, "数量输入必须是有限非负数"
    if attribute.get("unit", "") != rule.get("quantity_unit", ""):
        return None, "需求数量单位与公式口径不一致，请核对数量依据"
    return value, None


def quantity_input(data, *, rule, device, requirement, system):
    if rule.get("quantity_source", "device_quantity") == "device_quantity":
        value = Decimal(device["quantity"])
        error = None if value.is_finite() and value >= 0 else "数量输入必须是有限非负数"
        return (None if error else value, error), dict(
            input_scope="device", input_scope_id=device["id"], input_conflict=False
        )
    attribute, scope, identity, conflict = resolve_input(
        data, rule=rule, requirement=requirement, system=system
    )
    quantity = (
        (None, "系统输入与角色输入不一致，请明确本次采用值")
        if conflict
        else numeric_quantity(attribute, rule=rule)
    )
    return quantity, dict(input_scope=scope, input_scope_id=identity, input_conflict=conflict)
