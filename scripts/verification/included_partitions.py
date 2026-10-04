"""Isolated synthetic bundles: real stdio/HTTP editing, rejection, undo and save."""

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification.distributed_charging import run

AUTHOR = dict(actor="隔离抵扣验收", evidence="合成测试数据，不是真实产品或授权结论")


def seed(session):
    from presales.configuration.catalog.schemas import ProductInput, VariantInput
    from presales.configuration.common import Entities
    from presales.configuration.knowledge.schemas import KnowledgeInput
    from presales.configuration.models import SourceLink
    from presales.storage import CatalogImport, ProductRecord

    entities = Entities(session)
    identity = str(uuid4())
    session.add(
        CatalogImport(
            id=identity,
            filename="合成隔离资料",
            digest=identity,
            sheets=["测试"],
            record_count=1,
            issue_count=0,
        )
    )
    product = entities.save(
        "product", ProductInput(name="隔离终端与授权", model="TEST-BUNDLE", **AUTHOR)
    )
    target = entities.save(
        "variant",
        VariantInput(product_id=product["id"], name="隔离授权", status="confirmed", **AUTHOR),
    )
    host = entities.save(
        "variant",
        VariantInput(
            product_id=product["id"],
            name="隔离已含授权终端",
            status="confirmed",
            included_items=[
                dict(
                    id="bundled",
                    name="隔离随附授权",
                    variant_id=target["id"],
                    kind="license",
                    quantity="1",
                    need_keys=["license"],
                    status="confirmed",
                    evidence=AUTHOR["evidence"],
                )
            ],
            **AUTHOR,
        ),
    )
    source_id = str(uuid4())
    session.add(
        ProductRecord(
            id=source_id,
            import_id=identity,
            name="隔离终端",
            model="TEST-BUNDLE",
            sheet="测试",
            payload=dict(
                row=2,
                specification="合成测试，每台包含一份授权",
                unit="台",
                prices={"出厂指导价": "1"},
                note="非业务数据",
            ),
        )
    )
    session.flush()
    session.add(SourceLink(source_id=source_id, variant_id=host["id"], **AUTHOR))
    entities.save(
        "knowledge",
        KnowledgeInput(
            name="隔离双授权需求",
            schema_version=2,
            kind="accessory",
            status="confirmed",
            selector=dict(variant_ids=[host["id"]]),
            need_key="license",
            need_name="隔离授权需求",
            target_variant_ids=[target["id"]],
            calculation_scope="system",
            mode="per_unit",
            factor="2",
            quantity_review="confirmed",
            quantity_evidence=AUTHOR["evidence"],
            output_kind="license",
            resource_policy="not_applicable",
            **AUTHOR,
        ),
    )
    session.commit()
    return host["id"], source_id


def role(identity, system, quantity):
    return dict(
        id=identity,
        system_id=system,
        role="隔离终端",
        allocations=[
            dict(
                device_id="host",
                quantity=quantity,
                evidence=AUTHOR["evidence"],
            )
        ],
    )


def operations(variant_id, source_id):
    result = [
        dict(
            action="device_put",
            value=dict(
                id="host",
                name="隔离已含授权终端",
                variant_id=variant_id,
                source_id=source_id,
                quantity="32",
                kind="hardware",
            ),
        )
    ]
    for index, quantity in ((1, "8"), (2, "24")):
        room_id, system_id = f"room{index}", f"system{index}"
        result.extend(
            [
                dict(action="room_put", value=dict(id=room_id, name=f"隔离会议室{index}")),
                dict(
                    action="system_put",
                    value=dict(
                        id=system_id, name=f"隔离系统{index}", kind="隔离无纸化", room_id=room_id
                    ),
                ),
                dict(action="requirement_put", value=role(f"role{index}", system_id, quantity)),
            ]
        )
    return result


def credit(demand, quantity):
    offer = demand["included_offers"][0]
    return dict(
        id="credit",
        demand_id=demand["id"],
        quantity=quantity,
        evidence=AUTHOR["evidence"],
        **{
            k: offer[k]
            for k in ("device_id", "included_item_id", "host_variant_id", "host_variant_revision")
        },
    )


async def exercise(mcp, args):
    from presales.storage import database_factory

    factory = database_factory("sqlite:///" + str(args.database.resolve()))
    with factory() as session:
        variant_id, source_id = seed(session)

    async def call(name, payload):
        reply = await mcp.call_tool(name, {"request": payload})
        assert not reply.is_error, reply
        return reply.structured_content

    def mutation(draft, **extra):
        return dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id=str(uuid4()),
            **extra,
        )

    async def compare(draft, http):
        query = dict(draft_id=draft["id"], view="issues", limit=1000)
        response = await http.post(args.api + "/api/list-tools/list_get", json=query)
        response.raise_for_status()
        issues = await call("list_get", query)
        assert response.json() == issues
        return issues

    draft = await call(
        "list_create", dict(name="隔离：分房间已含授权抵扣", operation_id=str(uuid4()), **AUTHOR)
    )
    draft = await call("list_update", mutation(draft, operations=operations(variant_id, source_id)))
    draft = await call("list_check", mutation(draft, upgrade_decisions=True))
    async with httpx.AsyncClient(timeout=20) as http:
        issues = await compare(draft, http)
        demands = [s for s in issues["items"] if s["kind"] == "accessory"]
        first = next(s for s in demands if s["scope_id"] == "system1")
        assert first["included_offers"][0]["available"] == "8"
        rejected = mutation(
            draft, operations=[dict(action="included_link", value=credit(first, "16"))]
        )
        reply = await mcp.call_tool("list_update", {"request": rejected})
        assert reply.is_error
        response = await http.post(args.api + "/api/list-tools/list_update", json=rejected)
        assert response.status_code == 422
        assert (await compare(draft, http)) == issues
        accepted = mutation(
            draft, operations=[dict(action="included_link", value=credit(first, "8"))]
        )
        draft = await call("list_update", accepted)
        assert await call("list_update", accepted) == draft
        checkpoint = draft["revision"]
        draft = await call(
            "list_update",
            mutation(
                draft,
                operations=[dict(action="requirement_put", value=role("role1", "system1", "4"))],
            ),
        )
        issues = await compare(draft, http)
        conflict = next(c for c in issues["items"] if c["kind"] == "included_allocation")
        assert (conflict["status"], conflict["scope_capacity"], conflict["counted_quantity"]) == (
            "conflict",
            "4",
            "0",
        )
        response = await http.post(
            args.api + "/api/work-drafts/" + draft["id"] + "/restore",
            json=mutation(draft, checkpoint_revision=checkpoint),
        )
        response.raise_for_status()
        draft = response.json()
        draft = await call("list_check", mutation(draft))
        issues = await compare(draft, http)
        assert (
            next(c for c in issues["items"] if c["kind"] == "included_allocation")[
                "counted_quantity"
            ]
            == "8"
        )
    saved = await call(
        "list_save",
        mutation(draft, expected_project_revision=0, fingerprint=draft["check_fingerprint"]),
    )
    reopened = await call(
        "list_get", dict(project_id=saved["project_id"], revision=1, view="issues", limit=1000)
    )
    assert reopened["items"] == issues["items"]
    return dict(
        project_id=saved["project_id"],
        draft_id=draft["id"],
        http_stdio_equal=True,
        over_credit_rejected_atomically=True,
        retry_idempotent=True,
        reduced_credit_conflict=conflict,
        restored=True,
        saved_reopened=True,
        decision_runtime="zen-v1",
        synthetic_knowledge=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args(), exercise_case=exercise))
