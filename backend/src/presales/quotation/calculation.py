from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


def adopt_prices(configuration):
    """Bind source prices once; replacing a product leaves the old binding visibly stale."""
    data = deepcopy(configuration)
    quote = data.get("quotation")
    if quote is None:
        return data
    previous = {p["device_id"]: p for p in quote["prices"]}
    prices = []
    for device in data["devices"]:
        old = previous.get(device["id"])
        if old and (
            old["mode"] in ("manual", "import", "version", "pending")
            or old["price_column"] == quote["price_column"]
        ):
            prices.append(old)
            continue
        prices.append(
            dict(
                device_id=device["id"],
                variant_id=device["variant_id"],
                source_id=device["source_id"],
                mode="source",
                price_column=quote["price_column"],
                unit_price=None,
                evidence="采用本次报价指定的原资料价格列",
            )
        )
    quote["prices"] = prices
    device_ids = {d["id"] for d in data["devices"]}
    quote["sections"] = {k: v for k, v in quote["sections"].items() if k in device_ids}
    return data


def unit_price(device, selection):
    if not selection:
        return None, "尚未采用报价单价"
    if selection["mode"] == "pending":
        return None, selection["evidence"]
    identity_fields = (
        ("variant_id",) if selection["mode"] == "version" else ("variant_id", "source_id")
    )
    if any(selection[k] != device[k] for k in identity_fields):
        return None, "型号或资料来源已更换，原报价单价已过期，请重新采用价格"
    if selection["mode"] == "version":
        from presales.catalog_updates.hashing import configuration_hash

        if (
            configuration_hash(device.get("variant_snapshot") or {})
            != selection["price_reference"]["configuration_hash"]
        ):
            return None, "配置参数已变化，原版本价格已过期，请重新核对价格"
    raw = (
        selection["unit_price"]
        if selection["mode"] in ("manual", "import", "version", "pending")
        else (
            (device.get("source_snapshot") or {}).get("prices", {}).get(selection["price_column"])
        )
    )
    try:
        amount = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None, "所选价格列缺价或不是数值，请提供有依据的单价"
    if not amount.is_finite() or amount < 0:
        return None, "单价必须是有限非负数"
    return amount, None


def quote_projection(configuration, output):
    quote = configuration.get("quotation")
    if quote is None:
        return None
    devices = {d["id"]: d for d in configuration["devices"]}
    prices = {p["device_id"]: p for p in quote["prices"]}
    lines = [
        quote_line(
            line,
            device=devices[line["device_id"]],
            quote=quote,
            selection=prices.get(line["device_id"]),
        )
        for line in output["lines"]
    ]
    issues = [
        dict(kind="quotation", status="unknown", device_id=line["device_id"], message=message)
        for line in lines
        for message in line["issues"]
    ]
    total = sum(
        (Decimal(line["amount"]) for line in lines if line["amount"] is not None), Decimal(0)
    )
    return dict(
        template_id=quote["template_id"],
        currency="CNY",
        lines=lines,
        issues=issues,
        known_subtotal=str(total.quantize(CENT)),
        total=None if issues else str(total.quantize(CENT)),
        status="draft" if issues else "priced",
        tax_terms=quote["tax_terms"],
    )


def quote_line(line, *, device, quote, selection):
    supply = line.get("supply")
    purchase = Decimal(supply["purchase"]) if supply else Decimal(0)
    unknown = (
        Decimal(supply["unknown"]) + Decimal(supply["unassigned"])
        if supply
        else Decimal(line["quantity"])
    )
    price, error = unit_price(device, selection)
    issues = [error] if error and purchase > 0 else []
    if unknown:
        issues.append("供货数量待确认，不计为零元采购")
    overallocated = bool(
        supply
        and Decimal(supply["purchase"]) + Decimal(supply["existing"]) + Decimal(supply["unknown"])
        > Decimal(line["quantity"])
    )
    if overallocated:
        issues.append("供货分配超过部署数量")
    amount = (
        (purchase * price).quantize(CENT, rounding=ROUND_HALF_UP) if price is not None else None
    )
    if purchase == 0:
        amount = Decimal(0)
    names = sorted({c["system_name"] for c in line["consumers"]})
    section = quote["sections"].get(device["id"]) or (
        "公共设备" if len(names) > 1 else names[0] if names else "其他辅助设备"
    )
    if not quote["sections"].get(device["id"]) and "无纸化" in section:
        section = "无纸化会议系统"
    specification, description_error = project_description(line, device=device, quote=quote)
    if description_error:
        issues.append(description_error)
    return dict(
        **{**line, "specification": specification},
        original_specification=line["specification"],
        purchase_quantity=str(purchase),
        unknown_quantity=str(unknown),
        supply_complete=not (unknown or overallocated),
        unit_price=str(price) if price is not None else None,
        amount=str(amount) if amount is not None else None,
        section=section,
        brand=(device.get("source_snapshot") or {}).get("brand", ""),
        price_selection=selection,
        issues=issues,
    )


def project_description(line, *, device, quote):
    description = quote.get("descriptions", {}).get(device["id"])
    if not description:
        return line["specification"], None
    if any(description[key] != device[key] for key in ("variant_id", "source_id")):
        return (
            line["specification"],
            "产品已更换，项目产品说明已过期；当前展示原资料，请重新确认说明",
        )
    return description["text"], None


def with_quotation(checked):
    result = dict(checked)
    result["quotation_output"] = quote_projection(result["configuration"], result["project_output"])
    return result
