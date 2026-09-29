"""Unresolved customer interpretations remain visible after a proposal is adopted."""


def interpretation_checks(data):
    systems = {s["id"] for s in data["systems"]}
    requirements = {r["id"]: r for r in data["requirements"]}
    results = []
    for source in data.get("generation", {}).get("sources", []):
        if source["kind"] != "agent_interpretation" or source["confirmed"]:
            continue
        identity = source["object_id"]
        requirement = requirements.get(identity, {})
        results.append(
            dict(
                kind="interpretation",
                code="interpretation_unconfirmed",
                status="unknown",
                source_id=source["id"],
                object_id=identity,
                system_id=identity if identity in systems else requirement.get("system_id"),
                requirement_id=requirement.get("id"),
                field=source["field"],
                message="请确认 Agent 对需求的理解：" + source["quote"],
                choices=["确认", "修正", "不采用"],
                evidence=[source],
            )
        )
    return results
