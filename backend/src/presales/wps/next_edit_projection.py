"""Translate verified domain edits into managed worksheet patches."""

from uuid import NAMESPACE_URL, uuid5

from presales.rules.calculation import digest

PRODUCT_FIELDS = ("model", "name", "description", "unit", "brand", "price")


def project_next_edit(option, *, request, profile, projection):
    option = normalized_identities(option, request=request, projection=projection)
    changes = option["changes"]
    devices = [c for c in changes if c["kind"] == "devices"]
    patches, bindings, errors, used = [], [], [], set()
    for change in devices:
        device = change["after"]
        if device is None:
            errors.append("移除产品需要明确选择对应工作簿行")
            continue
        target = find_target(change, request=request, used=used)
        if target is None:
            errors.append("当前业务区没有足够的目标行，请选择空白产品行或插行后重试")
            continue
        used.add((target.sheet, target.row))
        variant = device["variant_snapshot"]
        values = dict(
            model=variant["product"]["model"],
            name=variant["product"]["name"],
            description=variant.get("description", ""),
            unit=source_unit(device),
            brand=variant["product"].get("brand", ""),
            price="",
            quantity=str(device["quantity"]),
        )
        fields = [*profile["managed_fields"], "quantity"]
        for field in dict.fromkeys(fields):
            before, after = target.values.get(field, ""), values[field]
            if (
                field == "price"
                and change["before"]
                and all(change["before"][key] == device[key] for key in ("variant_id", "source_id"))
            ):
                continue
            if before == after:
                continue
            if field not in profile["field_columns"]:
                errors.append(f"模板未映射 {field} 列")
                continue
            if field in target.formula_fields or field in target.merged_fields:
                errors.append(f"第 {target.row} 行 {field} 是公式或合并单元格")
            patches.append(
                dict(
                    sheet=target.sheet,
                    row=target.row,
                    column=profile["field_columns"][field],
                    field=field,
                    before=before,
                    after=after,
                )
            )
        old = next((line for line in request.lines if line.device_id == device["id"]), None)
        bindings.append(
            dict(
                line_id=old.line_id if old else option["line_ids"][device["id"]],
                device_id=device["id"],
                sheet=target.sheet,
                row=target.row,
                variant_id=device["variant_id"],
                source_id=device["source_id"],
                kind=device["kind"],
                section=target.values.get("section", ""),
                confirmed_values=values,
                anchor_fingerprint="\0".join([values["model"], values["name"]]).lower(),
                requirement_id=next(
                    (
                        r["id"]
                        for r in option["configuration"]["requirements"]
                        if r.get("device_id") == device["id"]
                    ),
                    None,
                ),
            )
        )
    operations = semantic_operations(option["configuration"], changes)
    issues = [*option["questions"], *errors]
    issue_baseline = {digest(c) for c in projection["checked"]["checks"] if c["status"] != "pass"}
    issues.extend(
        c
        for c in option["checked"]["checks"]
        if c["status"] != "pass" and digest(c) not in issue_baseline
    )
    touched = {c["id"] for c in devices}
    linked = {
        r["id"]
        for r in option["configuration"]["requirements"]
        if r.get("device_id") in touched
        or any(a["device_id"] in touched for a in r.get("allocations", []))
    }
    blocking = [
        i
        for i in issues
        if isinstance(i, dict)
        and (
            i.get("status") == "conflict"
            or i.get("device_id") in touched
            or i.get("requirement_id") in linked
        )
    ]
    identity = digest([patches, bindings, operations])
    return dict(
        id=identity,
        kind="product" if len(devices) == 1 else "business",
        label="应用当前方案的下一步修改",
        patches=patches,
        line_bindings=bindings,
        business_operations=operations,
        inverse_business_operations=semantic_operations(
            projection["checked"]["configuration"],
            [dict(c, before=c["after"], after=c["before"]) for c in reversed(changes)],
        ),
        changes=changes,
        evidence=option["evidence"],
        issues=issues,
        applicable=not errors and not option["questions"] and not blocking,
        acceptance="inline"
        if len(devices) == 1
        and not any(p["field"] == "quantity" for p in patches)
        and not any(c["kind"] in {"accessory_allocations", "included_allocations"} for c in changes)
        else "preview",
        context_fingerprint=projection["fingerprint"],
        local_revision=request.local_revision,
    )


def source_unit(device):
    source = device.get("source_snapshot") or {}
    return source.get("unit", "")


def normalized_identities(option, *, request, projection):
    existing = {d["id"] for d in projection["checked"]["configuration"]["devices"]}
    identities = {
        d["id"]: str(uuid5(NAMESPACE_URL, f"presales-wps-device:{request.binding_id}:{d['id']}"))
        for d in option["configuration"]["devices"]
        if d["id"] not in existing
    }

    def remap(value):
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        if isinstance(value, list):
            return [remap(item) for item in value]
        return identities.get(value, value) if isinstance(value, str) else value

    result = remap(option)
    result["line_ids"] = {value: key for key, value in identities.items()}
    return result


def find_target(change, *, request, used):
    line = next((line for line in request.lines if line.device_id == change["id"]), None)
    targets = [request.active_cell, *request.target_cells]
    for target in targets:
        if (target.sheet, target.row) in used or target.sheet != request.scope.sheet:
            continue
        if not request.scope.start_row <= target.row <= request.scope.end_row:
            continue
        if line and (line.sheet, line.row) == (target.sheet, target.row):
            return target
        if not line and not any(target.values.get(k, "").strip() for k in ("model", "name")):
            return target
        if not line and request.query and target == request.active_cell:
            return target
    return None


def semantic_operations(configuration, changes):
    operations = []
    for change in changes:
        kind, after, before = change["kind"], change["after"], change["before"]
        if kind == "requirements" and after:
            operations.append(dict(action="requirement_put", value=after))
        if kind == "requirements" and not after:
            operations.append(dict(action="remove", collection="requirements", id=before["id"]))
        if kind == "accessory_allocations":
            if before:
                operations.append(dict(action="accessory_remove", allocation_id=before["id"]))
            if after:
                operations.append(dict(action="accessory_link", value=after))
        if kind == "included_allocations":
            if before:
                operations.append(dict(action="included_remove", allocation_id=before["id"]))
            if after:
                operations.append(dict(action="included_link", value=after))
    devices = {
        c[side]["device_id"]
        for c in changes
        if c["kind"] == "supply_allocations"
        for side in ("before", "after")
        if c[side]
    }
    operations.extend(
        dict(
            action="supply_set",
            device_id=identity,
            allocations=[
                a for a in configuration["supply_allocations"] if a["device_id"] == identity
            ],
        )
        for identity in sorted(devices)
    )
    return operations
