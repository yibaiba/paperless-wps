"""Real stdio/HTTP checks of source-backed booking mapping in an isolated database."""

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paperless_review.booking_mapping import BUSINESS_SELECTION, build_mapping_plan
from paperless_review.maintenance import apply_plan
from verification.distributed_charging import run

DEFINITION = "e401b647-18ee-42b0-9f9f-120628e5b1b9"
VARIANT = "df40a90f-cfec-4d67-98ad-18395c685ae9"
BASE = "/api/configuration"


def os_input(description):
    role = next(r for r in description["roles"] if r["id"] == "server-software")
    return [i for i in role["inputs"] if i["key"] == "os"]


async def exercise(mcp, args):
    from presales.configuration.common import Entities
    from presales.storage import database_factory

    async def call(name, query):
        reply = await mcp.call_tool(name, {"request": query})
        assert not reply.is_error, reply
        return reply.structured_content

    draft = await call(
        "list_create",
        dict(
            name="隔离：会议预约关联前的固定快照",
            operation_id=str(uuid4()),
            actor="隔离关联验收",
            evidence="真实资料副本，仅验证关联和历史保护",
        ),
    )
    fixed_query = dict(
        definition_id=DEFINITION,
        **{
            key: draft[key]
            for key in ("definition_snapshot_id", "knowledge_snapshot_id", "catalog_snapshot_id")
        },
    )
    fixed_before = await call("systems_list", fixed_query)
    assert not os_input(fixed_before["requirement_description"])
    package_path = BASE + "/knowledge-packages/" + BUSINESS_SELECTION.package_id
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        before = (await http.get(package_path + "/readiness")).raise_for_status().json()
        gaps = [g for g in before["gaps"] if g["code"] == "relation_role_unmapped"]
        assert len(gaps) == 1 and gaps[0]["object_id"] == BUSINESS_SELECTION.rule_id
        with database_factory("sqlite:///" + str(args.database.resolve()))() as session:
            plan = build_mapping_plan(session)
            assert len(apply_plan(session, plan)) == 2
            session.commit()
            assert apply_plan(session, build_mapping_plan(session)) == []
            history = Entities(session).history(BUSINESS_SELECTION.package_id)
            assert (
                next(p for p in history if p["revision"] == 1)["members"] != history[0]["members"]
            )
        after = (await http.get(package_path + "/readiness")).raise_for_status().json()
        assert not after["unmapped_rule_ids"] and after["status"] == "draft"
        assert next(r for r in after["roles"] if r["id"] == "server-software")["candidate_ids"] == [
            VARIANT
        ]
        query = dict(definition_id=DEFINITION)
        current = await call("systems_list", query)
        response = await http.post("/api/list-tools/systems_list", json=query)
        assert response.raise_for_status().json() == current
        assert os_input(current["requirement_description"])
        assert not current["requirement_description"]["generation"]["supported"]
        assert await call("systems_list", fixed_query) == fixed_before
        trials = []
        for environment, expected in (
            ("Linux", "pass"),
            ("Windows", "conflict"),
            (None, "unknown"),
        ):
            response = await http.post(
                package_path + "/trial",
                json=dict(
                    expected_revision=after["revision"],
                    role_id="server-software",
                    variant_id=VARIANT,
                    environment=[]
                    if environment is None
                    else [dict(key="os", kind="text", value=environment)],
                ),
            )
            trial = response.raise_for_status().json()
            assert trial["status"] == expected, trial
            trials.append(
                dict(environment=environment, status=trial["status"], evidence=trial["evidence"])
            )
        response = await http.post(
            package_path + "/trial",
            json=dict(
                expected_revision=before["revision"], role_id="server-software", variant_id=VARIANT
            ),
        )
        assert response.status_code == 409
        draft_query = dict(
            definition_id=DEFINITION, knowledge_package_id=BUSINESS_SELECTION.package_id
        )
        assert (await mcp.call_tool("systems_list", {"request": draft_query})).is_error
        assert (
            await http.post("/api/list-tools/systems_list", json=draft_query)
        ).status_code == 422
    return dict(
        source_backed_isolated_copy=True,
        draft_id=draft["id"],
        package_revision=after["revision"],
        package_status=after["status"],
        current_role_os_input=os_input(current["requirement_description"]),
        fixed_snapshot_unchanged=True,
        draft_not_published=True,
        http_stdio_equal=True,
        mapping_gap_before=gaps,
        unmapped_after=after["unmapped_rule_ids"],
        trials=trials,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args(), exercise_case=exercise))
