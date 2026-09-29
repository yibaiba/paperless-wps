"""Feature confirmation follows the project's pinned system definitions."""


def defined_systems(data, definitions):
    packages = {p["id"]: p for p in definitions["packages"]}
    catalog = {d["id"]: d for d in definitions["definitions"]}
    for system in data["systems"]:
        package = packages.get(system.get("knowledge_package_id"))
        definition = (
            package["definition"] if package else catalog.get(system.get("definition_id"), {})
        )
        yield system, definition


def feature_checks(data, definitions):
    confirmed = set(data.get("generation", {}).get("features_confirmed", []))
    checks = []
    for system, definition in defined_systems(data, definitions):
        features = sorted({r["feature"] for r in definition.get("roles", []) if r["feature"]})
        if not features or system["id"] in confirmed:
            continue
        checks.append(
            dict(
                kind="feature_selection",
                code="features_unknown",
                status="unknown",
                system_id=system["id"],
                message="请确认需要启用的功能，未填写不等于不需要",
                choices=features,
                evidence=[
                    dict(
                        definition_id=definition["id"],
                        definition_revision=definition["revision"],
                        available_features=features,
                        selected_features=system["features"],
                    )
                ],
            )
        )
    return checks
