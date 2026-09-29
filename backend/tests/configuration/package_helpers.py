from presales.configuration.definitions.schemas import KnowledgePackage


def publish_members(client, systems, rules):
    """Test maintenance must explicitly publish a common rule into each consumer package."""
    ids = {system.get("knowledge_package_id") for system in systems} - {None, ""}
    packages = client.get("/api/configuration/knowledge-packages").json()
    for package in packages:
        if package["id"] not in ids:
            continue
        payload = {
            key: value for key, value in package.items() if key in KnowledgePackage.model_fields
        }
        members = {m["id"]: m for m in payload["members"]}
        members.update(
            {rule["id"]: dict(id=rule["id"], revision=rule["revision"]) for rule in rules}
        )
        payload["members"] = list(members.values())
        response = client.put(
            "/api/configuration/knowledge-packages/" + package["id"],
            json=dict(
                expected_revision=package["revision"],
                payload=payload,
            ),
        )
        assert response.status_code == 200, response.text
