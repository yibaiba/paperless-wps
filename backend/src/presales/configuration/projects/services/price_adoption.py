"""Explicit price adoption; immutable references keep historical quotes reproducible."""

from decimal import ROUND_HALF_UP, Decimal

from presales.application.errors import RevisionConflict
from presales.application.hashing import digest
from presales.pricing.hashing import configuration_hash
from presales.pricing.prices import Prices
from presales.quotation.calculation import CENT, adopt_prices, unit_price


def preview_prices(session, configuration, *, adoption_date):
    from presales.configuration.catalog.service import CatalogService
    from presales.configuration.projects.calculation.supply import supply_projection
    from presales.configuration.projects.schemas import Configuration

    data = adopt_prices(Configuration.model_validate(configuration).model_dump(mode="json"))
    quote = data.get("quotation")
    if not quote or not quote["price_column"]:
        raise ValueError("请先设置报价及价格列")
    prices = Prices(session)
    current = {
        v["id"]: v
        for v in CatalogService(session).variants(ids=[d["variant_id"] for d in data["devices"]])
    }
    old = {p["device_id"]: p for p in quote["prices"]}
    supply, _ = supply_projection(data)
    rows = []
    for device in data["devices"]:
        latest = prices.effective(device["variant_id"], quote["price_column"], adoption_date)
        previous = old.get(device["id"])
        amount, error = unit_price(device, previous)
        issues = price_issues(device, latest=latest, current=current.get(device["variant_id"]))
        new = Decimal(latest["amount"]) if latest and not issues else None
        quantity = Decimal(supply[device["id"]]["purchase"])
        before = (
            (quantity * amount).quantize(CENT, rounding=ROUND_HALF_UP)
            if amount is not None
            else None
        )
        after = (quantity * new).quantize(CENT, rounding=ROUND_HALF_UP) if new is not None else None
        rows.append(
            dict(
                device_id=device["id"],
                variant_id=device["variant_id"],
                old=previous,
                old_unit_price=str(amount) if amount is not None else None,
                old_issue=error,
                price=latest,
                purchase_quantity=str(quantity),
                before_amount=str(before) if before is not None else None,
                after_amount=str(after) if after is not None else None,
                difference=str(after - before)
                if before is not None and after is not None
                else None,
                issues=issues,
                protected=bool(previous and previous["mode"] in {"manual", "import"}),
                legacy=bool(previous and previous["mode"] == "source"),
            )
        )
    return dict(
        adoption_date=str(adoption_date),
        price_column=quote["price_column"],
        rows=rows,
        fingerprint=digest([data, str(adoption_date), rows]),
    )


def price_issues(device, *, latest, current):
    issues = []
    if current and current.get("supply_status", "available") != "available":
        issues.append("产品已停止选用，请先核对供货")
    if not latest:
        return issues + ["此日期没有已发布价格；现有旧来源价不会自动替换"]
    if latest["state"] == "inquiry":
        issues.append("此日期已发布待询价，不沿用更早价格")
    snapshot = device.get("variant_snapshot") or current
    if not snapshot or configuration_hash(snapshot) != latest["configuration_hash"]:
        issues.append("价格对应的配置参数与项目配置不一致")
    return issues


def adopt_versions(session, configuration, operation):
    preview = preview_prices(session, configuration, adoption_date=operation.adoption_date)
    if preview["fingerprint"] != operation.fingerprint:
        raise RevisionConflict("价格预览已过期，请重新检查价格更新")
    items = {i.device_id: i for i in operation.items}
    if len(items) != len(operation.items):
        raise ValueError("同一设备不能重复采用价格")
    rows = {r["device_id"]: r for r in preview["rows"]}
    if items.keys() - rows.keys():
        raise ValueError("所选设备不在项目中")
    data = adopt_prices(configuration)
    devices = {d["id"]: d for d in data["devices"]}
    replacements = {}
    for identity, item in items.items():
        row, device = rows[identity], devices[identity]
        price = row["price"]
        if row["issues"] or not price:
            raise ValueError("所选价格不可采用：" + "；".join(row["issues"]))
        if item.price.id != price["id"] or item.price.revision != price["revision"]:
            raise RevisionConflict("所选价格修订与预览不一致")
        replacements[identity] = dict(
            device_id=identity,
            variant_id=device["variant_id"],
            source_id=device["source_id"],
            mode="version",
            price_column=price["column"],
            unit_price=price["amount"],
            evidence=price["evidence"],
            price_reference=dict(
                id=price["id"],
                revision=price["revision"],
                adopted_on=str(operation.adoption_date),
                configuration_hash=price["configuration_hash"],
            ),
        )
    data["quotation"]["prices"] = [
        replacements.get(p["device_id"], p) for p in data["quotation"]["prices"]
    ]
    data["quotation"]["price_adoption_date"] = str(operation.adoption_date)
    return data


def validate_references(session, configuration):
    """Validate trusted revision amounts even on legacy full-snapshot save endpoints."""
    quote = configuration.get("quotation") or {}
    prices = Prices(session)
    for selected in quote.get("prices", []):
        if selected["mode"] != "version":
            continue
        ref = selected.get("price_reference")
        if not ref:
            raise ValueError("版本价格缺少修订引用")
        record = prices.revision(ref["id"], ref["revision"])
        if (
            record["configuration_hash"] != ref["configuration_hash"]
            or record["variant_id"] != selected["variant_id"]
            or record["column"] != selected["price_column"]
            or record["effective_date"] > ref["adopted_on"]
            or record["state"] != "amount"
            or Decimal(record["amount"]) != Decimal(str(selected["unit_price"]))
        ):
            raise ValueError("价格引用与已发布修订不一致，不能提交客户端价格快照")
        from presales.pricing.adoption_records import validate_adoption

        validate_adoption(session, selected, prices=prices)
