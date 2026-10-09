from copy import deepcopy

from presales.pricing.hashing import configuration_hash
from presales.pricing.prices import Prices
from presales.quotation.calculation import with_quotation
from presales.rules.repository import RuleConflict


def capture_prices(session, configuration, variants):
    quote = configuration.get("quotation")
    if not quote or not quote["price_column"] or not quote.get("price_adoption_date"):
        return {}
    prices = Prices(session)
    return {
        v["id"]: prices.effective(v["id"], quote["price_column"], quote["price_adoption_date"])
        for v in variants
    }


def quote_plan(checked, prices):
    result = deepcopy(checked)
    data = result["configuration"]
    if not data.get("quotation"):
        return result
    quote = data["quotation"]
    by_device = {d["id"]: d for d in data["devices"]}
    selections = []
    for selection in quote["prices"]:
        device = by_device[selection["device_id"]]
        price = prices.get(device["variant_id"])
        if selection["mode"] in {"manual", "import", "version"} or price is None:
            selections.append(selection)
            continue
        if price["state"] == "amount" and price["configuration_hash"] == configuration_hash(
            device["variant_snapshot"]
        ):
            selections.append(
                dict(
                    device_id=device["id"],
                    variant_id=device["variant_id"],
                    source_id=device["source_id"],
                    mode="version",
                    price_column=price["column"],
                    unit_price=price["amount"],
                    evidence=price["evidence"],
                    price_reference=dict(
                        id=price["id"],
                        revision=price["revision"],
                        adopted_on=quote["price_adoption_date"],
                        configuration_hash=price["configuration_hash"],
                    ),
                )
            )
        else:
            # Explicit missing price prevents falling back to a historic source price.
            selections.append(
                dict(
                    device_id=device["id"],
                    variant_id=device["variant_id"],
                    source_id=device["source_id"],
                    mode="pending",
                    price_column=price["column"],
                    unit_price=None,
                    evidence="价格版本为待询价或配置不一致，待维护者确认",
                )
            )
    quote["prices"] = selections
    from ..services.issue_actions import with_issue_actions

    return with_issue_actions(with_quotation(result))


def validate_new_prices(session, *, before, proposed):
    previous = {p["device_id"]: p for p in (before.get("quotation") or {}).get("prices", [])}
    prices = Prices(session)
    for selection in (proposed.get("quotation") or {}).get("prices", []):
        if selection["mode"] != "version" or previous.get(selection["device_id"]) == selection:
            continue
        ref = selection["price_reference"]
        current = prices.effective(
            selection["variant_id"], selection["price_column"], ref["adopted_on"]
        )
        if not current or (current["id"], current["revision"]) != (ref["id"], ref["revision"]):
            raise RuleConflict("PROPOSAL_PRICE_STALE：提案采用的价格已更正，请重新生成提案")
