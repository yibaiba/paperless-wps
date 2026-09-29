"""Validate the identity of a quantity scope independently of its formula."""

from .questions import question


def scope_gap(basis, system, configuration):
    if basis["scope"] != "room":
        return None
    if system.get("room_id") in {r["id"] for r in configuration["rooms"]}:
        return None
    return question(
        "quantity_scope_missing",
        system["id"],
        "room_id",
        "数量按房间计算，请先关联实际房间",
        recipient="customer",
        evidence=[basis],
    )
