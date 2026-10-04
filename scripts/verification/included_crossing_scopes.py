"""Real stdio/HTTP verification of partially intersecting included-item credits."""

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
    for index, key in enumerate(("test_a", "test_b")):
        payload = KnowledgeInput.model_validate(
            {
                **{k: v for k, v in original.items() if k in KnowledgeInput.model_fields},
                "name": "隔离交叉授权 " + key,
                "activation_conditions": [dict(field="project." + key, operator="eq", value="on")],
            }
        )
        entities.save(
            "knowledge",
            payload,
            **(
                dict(entity_id=original["id"], expected_revision=original["revision"])
                if index == 0
                else {}
            ),
        )
    session.commit()
    batch = [
        item for item in operations(variant_id, source_id) if item["action"] != "requirement_put"
    ]
    for identity, system, quantity, enabled in (
        ("role1", "system1", "4", {"test_a"}),
        ("role2", "system1", "4", {"test_a", "test_b"}),
        ("role3", "system1", "4", {"test_b"}),
        ("role4", "system2", "20", set()),
    ):
        value = dict(
            role(identity, system, quantity),
            environment=[
                dict(
                    key=key,
                    kind="text",
                    value="on" if key in enabled else "off",
                    purpose="project_input",
                )
                for key in ("test_a", "test_b")
            ],
        )
        batch.append(dict(action="requirement_put", value=value))
    return batch


async def exercise(mcp, args):
    from presales.storage import database_factory

    with database_factory("sqlite:///" + str(args.database.resolve()))() as session:
        batch = prepare(session)

    async def call(name, request):
        reply = await mcp.call_tool(name, {"request": request})
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
        result = await call("list_get", query)
        response = await http.post(args.api + "/api/list-tools/list_get", json=query)
        response.raise_for_status()
        assert response.json() == result
        return result

    draft = await call(
        "list_create", dict(name="隔离：A+B / B+C 交叉抵扣", operation_id=str(uuid4()), **AUTHOR)
    )
    draft = await call("list_update", mutation(draft, operations=batch))
    draft = await call("list_check", mutation(draft, upgrade_decisions=True))
    async with httpx.AsyncClient(timeout=20) as http:
        initial = await compare(draft, http)
        demands = {i["rule"]["name"]: i for i in initial["items"] if i["kind"] == "accessory"}
        a, b = [demands["隔离交叉授权 " + key] for key in ("test_a", "test_b")]
        first = dict(credit(a, "8"), id="credit-a")
        second = dict(credit(b, "4"), id="credit-b")
        draft = await call(
            "list_update", mutation(draft, operations=[dict(action="included_link", value=first)])
        )
        checked = await compare(draft, http)
        offer = next(i for i in checked["items"] if i["kind"] == "accessory" and i["id"] == b["id"])
        assert offer["included_offers"][0]["available"] == "4"
        rejected = mutation(
            draft, operations=[dict(action="included_link", value=dict(second, quantity="8"))]
        )
        assert (await mcp.call_tool("list_update", {"request": rejected})).is_error
        response = await http.post(args.api + "/api/list-tools/list_update", json=rejected)
        assert response.status_code == 422
        assert await compare(draft, http) == checked
        request = mutation(draft, operations=[dict(action="included_link", value=second)])
        draft = await call("list_update", request)
        assert await call("list_update", request) == draft
        valid = await compare(draft, http)
        assert all(
            i["status"] == "pass" for i in valid["items"] if i["kind"] == "included_allocation"
        )
        checkpoint = draft["revision"]
        value = role("role3", "system1", "2")
        value["environment"] = [
            dict(
                key=key,
                kind="text",
                value="on" if key == "test_b" else "off",
                purpose="project_input",
            )
            for key in ("test_a", "test_b")
        ]
        draft = await call(
            "list_update", mutation(draft, operations=[dict(action="requirement_put", value=value)])
        )
        changed = await compare(draft, http)
        conflicts = [i for i in changed["items"] if i["kind"] == "included_allocation"]
        assert len(conflicts) == 2 and all(i["status"] == "conflict" for i in conflicts)
        assert all("role4" not in i["action"]["requirement_ids"] for i in conflicts)
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
        crossing_available="4",
        overspend_rejected=True,
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
