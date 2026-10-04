"""Verify nested included-item scopes over real stdio/HTTP in an isolated database."""

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification.distributed_charging import run
from verification.included_partitions import AUTHOR, credit, operations, role, seed


def prepare(session):
    from presales.configuration.common import Entities
    from presales.configuration.knowledge.schemas import KnowledgeInput

    variant_id, source_id = seed(session)
    entities = Entities(session)
    original = next(
        r for r in entities.list("knowledge") if r["selector"]["variant_ids"] == [variant_id]
    )
    entities.save(
        "knowledge",
        KnowledgeInput.model_validate(
            {
                **{k: v for k, v in original.items() if k in KnowledgeInput.model_fields},
                "name": "隔离指定角色授权需求",
                "need_name": "隔离房间角色授权",
                "role": "隔离终端",
                "calculation_scope": "room",
            }
        ),
    )
    session.commit()
    batch = operations(variant_id, source_id)
    batch[3]["value"] = role("role1", "system1", "4")
    batch.append(
        dict(
            action="requirement_put", value=dict(role("role3", "system1", "4"), role="隔离附加终端")
        )
    )
    return batch


def demand(issues, scope_id):
    return next(
        s for s in issues["items"] if s["kind"] == "accessory" and s["scope_id"] == scope_id
    )


async def exercise(mcp, args):
    from presales.storage import database_factory

    with database_factory("sqlite:///" + str(args.database.resolve()))() as session:
        batch = prepare(session)

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
        issues = await call("list_get", query)
        response = await http.post(args.api + "/api/list-tools/list_get", json=query)
        response.raise_for_status()
        assert response.json() == issues
        return issues

    draft = await call(
        "list_create", dict(name="隔离：系统与房间重叠抵扣", operation_id=str(uuid4()), **AUTHOR)
    )
    draft = await call("list_update", mutation(draft, operations=batch))
    draft = await call("list_check", mutation(draft, upgrade_decisions=True))
    async with httpx.AsyncClient(timeout=20) as http:
        initial = await compare(draft, http)
        system = dict(credit(demand(initial, "system1"), "8"), id="system-credit")
        room = dict(credit(demand(initial, "room1"), "4"), id="room-credit")
        draft = await call(
            "list_update", mutation(draft, operations=[dict(action="included_link", value=system)])
        )
        checked = await compare(draft, http)
        assert demand(checked, "room1")["included_offers"][0]["available"] == "0"
        rejected = mutation(draft, operations=[dict(action="included_link", value=room)])
        assert (await mcp.call_tool("list_update", {"request": rejected})).is_error
        response = await http.post(args.api + "/api/list-tools/list_update", json=rejected)
        assert response.status_code == 422
        assert await compare(draft, http) == checked
        request = mutation(
            draft,
            operations=[
                dict(action="included_remove", allocation_id="system-credit"),
                dict(action="included_link", value=room),
                dict(action="included_link", value=dict(system, quantity="4")),
            ],
        )
        draft = await call("list_update", request)
        assert await call("list_update", request) == draft
        checked = await compare(draft, http)
        assert all(
            s["status"] == "pass" for s in checked["items"] if s["kind"] == "included_allocation"
        )
        assert demand(checked, "system2")["included_offers"][0]["available"] == "24"
        checkpoint = draft["revision"]
        draft = await call(
            "list_update",
            mutation(
                draft,
                operations=[dict(action="requirement_put", value=role("role1", "system1", "2"))],
            ),
        )
        changed = await compare(draft, http)
        conflicts = [s for s in changed["items"] if s["kind"] == "included_allocation"]
        assert len(conflicts) == 2 and all(c["status"] == "conflict" for c in conflicts)
        affected = {c["allocation_id"]: c["action"]["requirement_ids"] for c in conflicts}
        assert set(affected["system-credit"]) == {"role1", "role3"}
        assert affected["room-credit"] == ["role1"]
        response = await http.post(
            args.api + "/api/work-drafts/" + draft["id"] + "/restore",
            json=mutation(draft, checkpoint_revision=checkpoint),
        )
        response.raise_for_status()
        draft = response.json()
        draft = await call("list_check", mutation(draft))
        checked = await compare(draft, http)
    saved = await call(
        "list_save",
        mutation(draft, expected_project_revision=0, fingerprint=draft["check_fingerprint"]),
    )
    reopened = await call(
        "list_get", dict(project_id=saved["project_id"], revision=1, view="issues", limit=1000)
    )
    assert reopened["items"] == checked["items"]
    return dict(
        project_id=saved["project_id"],
        draft_id=draft["id"],
        http_stdio_equal=True,
        nested_double_credit_rejected=True,
        affected_roles_scoped=True,
        retry_idempotent=True,
        restored=True,
        saved_reopened=True,
        reduced_conflicts=conflicts,
        synthetic_knowledge=True,
        decision_runtime="zen-v1",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args(), exercise_case=exercise))
