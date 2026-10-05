"""Compare paged usage, procurement and quotation through real stdio and HTTP."""

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification.accessory_capacity import edit, tool
from verification.booking_quantity_scope import mutation
from verification.distributed_charging import run


async def read_equal(mcp, args, request):
    result = await tool(mcp, "list_get", request)
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        response = await http.post("/api/list-tools/list_get", json=request)
        assert response.raise_for_status().json() == result
    return result


async def paged_usage(mcp, args, identity):
    first = await read_equal(mcp, args, dict(identity, view="device_usages", limit=2))
    items = list(first["items"])
    for offset in range(2, first["total"], 2):
        page = await read_equal(
            mcp, args, dict(identity, view="device_usages", offset=offset, limit=2)
        )
        items.extend(page["items"])
    assert len(items) == first["total"] and len({u["device_id"] for u in items}) == len(items)
    if items:
        selected = await read_equal(
            mcp, args, dict(identity, view="device_usages", device_id=items[-1]["device_id"])
        )
        assert selected["total"] == 1 and selected["items"] == items[-1:]
    return first, items


async def quote_existing(mcp, args, draft):
    devices = await read_equal(mcp, args, dict(draft_id=draft["id"], view="devices"))
    pool = next(d for d in devices["items"] if d["device_id"] == "pool")
    operations = [
        dict(
            action="supply_set",
            device_id="pool",
            allocations=[
                dict(
                    id="existing",
                    device_id="pool",
                    quantity="1",
                    source="existing",
                    evidence="隔离：客户已有",
                ),
                dict(
                    id="purchase",
                    device_id="pool",
                    quantity="2",
                    source="purchase",
                    evidence="隔离：明确采购",
                ),
                dict(
                    id="pending",
                    device_id="pool",
                    quantity="2",
                    source="unknown",
                    evidence="隔离：供货待确认",
                ),
            ],
        ),
        dict(
            action="quotation_set",
            value=dict(project_name="隔离用途对账", price_column="甲方指导价"),
        ),
        dict(
            action="price_set",
            value=dict(
                device_id="pool",
                variant_id=pool["variant_id"],
                source_id=pool["source_id"],
                mode="manual",
                unit_price="12.345",
                evidence="隔离小数价格，不是产品真实价格",
            ),
        ),
    ]
    draft = await edit(mcp, draft, operations)
    quotation = await read_equal(mcp, args, dict(draft_id=draft["id"], view="quotation"))
    priced = next(p for p in quotation["items"] if p["device_id"] == "pool")
    assert priced["purchase_quantity"] == "2" and priced["amount"] == "24.69"
    assert quotation["total"] is None and quotation["known_subtotal"] == "24.69"
    procurement = await read_equal(mcp, args, dict(draft_id=draft["id"], view="procurement"))
    assert next(p for p in procurement["items"] if p["device_id"] == "pool")["quantity"] == "2"
    return draft, quotation


async def exercise(mcp, args):
    if args.project_id:
        return await compare_project(mcp, args)
    alias = json.loads((args.database.parent / "alias-stdio.json").read_text())
    project_id = alias["project_id"]
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        response = await http.get("/api/configuration/projects/" + project_id)
        baseline_revision = response.raise_for_status().json()["revision"]
    draft = await tool(
        mcp,
        "list_create",
        dict(
            name="隔离：用途采购金额对账",
            project_id=project_id,
            revision=baseline_revision,
            operation_id=str(uuid4()),
            actor="隔离验收",
            evidence="隔离数量与价格",
        ),
    )
    initial, usages = await paged_usage(mcp, args, dict(draft_id=draft["id"]))
    pool = next(u for u in usages if u["device_id"] == "pool")
    assert pool["quantity_summary"]["total_quantity"] == "5"
    assert pool["quantity_summary"]["reserved_quantity"] == "2"
    assert len(pool["allocation_groups"]) == 2 and len(pool["role_references"]) == 2
    assert all(c["capacity"] == "128" for c in pool["resource_calculations"])
    draft, quotation = await quote_existing(mcp, args, draft)
    current, updated = await paged_usage(mcp, args, dict(draft_id=draft["id"]))
    assert updated == usages and current["usage_projection"] == initial["usage_projection"]
    draft = await tool(mcp, "list_check", mutation(draft))
    saved = await tool(
        mcp,
        "list_save",
        mutation(
            draft,
            expected_project_revision=baseline_revision,
            fingerprint=draft["check_fingerprint"],
        ),
    )
    _, reopened = await paged_usage(
        mcp, args, dict(project_id=project_id, revision=saved["project_revision"])
    )
    assert reopened == updated
    exports = await tool(
        mcp,
        "list_export",
        dict(
            project_id=project_id,
            revision=saved["project_revision"],
            output="both",
            operation_id=str(uuid4()),
        ),
    )
    assert len(exports["artifacts"]) == 2 and all(
        Path(a["path"]).is_file() for a in exports["artifacts"]
    )
    return dict(
        project_id=project_id,
        draft_id=draft["id"],
        usage_projection=current["usage_projection"],
        device_usages=updated,
        quotation=quotation,
        exports=exports,
        http_stdio_equal=True,
        paged_device_filter=True,
        supply_price_reuses_usage=True,
    )


async def compare_project(mcp, args):
    identity = dict(project_id=args.project_id, revision=args.revision)
    summary, usages = await paged_usage(mcp, args, identity)
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        result = await http.get(
            "/api/configuration/projects/" + args.project_id, params=dict(revision=args.revision)
        )
        assert result.raise_for_status().json()["device_usages"] == usages
    views = {}
    for view in ("devices", "procurement", "quotation", "issues", "case_comparison"):
        views[view] = await read_equal(mcp, args, dict(identity, view=view, limit=1000))
    assert all(row["reason"] for row in views["case_comparison"]["items"])
    return dict(
        project_id=args.project_id,
        revision=args.revision,
        usage_projection=summary["usage_projection"],
        device_usages=usages,
        views=views,
        http_stdio_equal=True,
        native_project_http_equal=True,
        paged_device_filter=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--revision", type=int, default=1)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args(), exercise_case=exercise))
