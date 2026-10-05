from copy import deepcopy

import pytest

from .conftest import knowledge, post


@pytest.mark.parametrize("runtime", ["python-v3", "zen-v1"])
def test_candidate_uses_project_environment_without_duplicate_request_fields(
    client, catalog, config, runtime
):
    knowledge(
        client,
        catalog["variants"][0],
        conditions=[dict(field="project.os", operator="eq", value="Windows")],
    )
    data = deepcopy(config)
    data.update(calculation_version=3, decision_runtime=runtime)
    data["systems"][0]["inputs"] = [dict(key="os", value="Windows", kind="text", unit="")]
    checked = post(client, "/check", dict(configuration=data))
    assert next(c for c in checked["checks"] if c["kind"] == "compatibility")["status"] == "pass"
    candidates = post(
        client,
        "/candidates",
        dict(
            configuration=checked["configuration"],
            requirement_id="r1",
            system="无纸化",
            role="服务端",
            include_all=True,
        ),
    )
    candidate = next(c for c in candidates if c["variant"]["id"] == catalog["variants"][0]["id"])
    assert candidate["compatibility_status"] == "pass"
    assert candidate["status"] == "unknown" and candidate["usage_status"] == "unknown"
    assert candidate["evidence"][0]["conditions"][0]["actual"]["value"] == "Windows"


def test_preparing_another_branch_does_not_mutate_first_context(config):
    from presales.configuration.projects.calculation.context import prepare_roles

    data = deepcopy(config)
    data["systems"][0]["inputs"] = [dict(key="os", value="Windows", kind="text", unit="")]
    definitions = dict(definitions=[], packages=[])
    first = prepare_roles(data, definitions=definitions)
    data["systems"][0]["inputs"][0]["value"] = "Linux"
    second = prepare_roles(data, definitions=definitions)
    assert first.data["requirements"][0]["environment"][0]["value"] == "Windows"
    assert second.data["requirements"][0]["environment"][0]["value"] == "Linux"
