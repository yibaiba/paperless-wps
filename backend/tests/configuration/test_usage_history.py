"""Old results are marked for recheck, not repaired by a second calculation path."""

from copy import deepcopy

from presales.configuration.projects.calculation.usage.differences import usage_differences
from presales.configuration.projects.calculation.usage.versioning import projection_status
from presales.lists.schemas import GetList
from presales.lists.views import read_view

from .conftest import BASE
from .test_list_mcp import call, saved_project


def test_historical_status_does_not_rewrite_original_values():
    old = dict(configuration=dict(calculation_version=3), device_usages=[dict(device_id="old")])
    before = deepcopy(old)
    current = projection_status(old)
    assert current["usage_projection"]["current"] is False
    assert current["device_usages"] == old["device_usages"] and old == before
    assert projection_status(dict(configuration=dict(calculation_version=2))) == dict(
        configuration=dict(calculation_version=2)
    )


def test_mcp_usage_view_matches_saved_http_result_and_pages_by_device(client, catalog):
    saved = saved_project(client, catalog)
    http = client.get(BASE + "/projects/" + saved["project_id"]).json()
    request = dict(project_id=saved["project_id"], revision=1, view="device_usages", limit=1)
    mcp = call(client, "list_get", request)
    assert mcp["items"] == http["device_usages"][:1] and mcp["check_current"]
    assert mcp["usage_projection"]["fingerprint"] == http["usage_projection"]["fingerprint"]
    one = call(client, "list_get", request | dict(device_id="server"))
    assert one["total"] == 1 and one["items"][0]["device_id"] == "server"
    old = deepcopy(http)
    old.pop("usage_projection")
    old["device_usages"][0].pop("quantity_summary")
    assert read_view(old, GetList(**request))["check_current"] is False
    diff = usage_differences(old, http)
    assert diff[0]["device_id"] == "server" and diff[0]["previous"]["quantity_summary"] is None
