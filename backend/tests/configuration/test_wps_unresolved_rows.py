from copy import deepcopy

from .test_wps_dependency_scope import seed_unrelated_systems
from .test_wps_next_edits import accept, completion_body, preview, sync_body


def unknown(*, system="system", device=None, confirmed=None):
    return dict(
        sheet="报价表",
        row=30,
        line_id="unknown-30",
        device_id=device,
        system_id=system,
        reason_code="identity_unconfirmed",
        confirmed_line=confirmed,
    )


def test_current_unknown_row_prevents_duplicate_purchase_and_has_resolution(client, catalog):
    headers, body = completion_body(client, catalog)
    body["unresolved_rows"] = [unknown()]
    result = preview(client, headers, body)
    assert not result["items"]
    issue = next(q for q in result["issues"] if q.get("code") == "workbook_row_unresolved")
    assert issue["blocking"]
    assert issue["row"] == 30
    assert issue["resolution_actions"][0]["row"] == 30
    assert issue["resolution_actions"][0]["kind"] == "confirm_identity"


def test_unrelated_unknown_only_warns_but_unassigned_row_requires_confirmation(client, catalog):
    headers, body = completion_body(client, catalog)
    seed_unrelated_systems(client, headers, body, 1)
    body["unresolved_rows"] = [unknown(system="unrelated-0")]
    result = preview(client, headers, body)
    assert result["items"]
    issue = next(q for q in result["issues"] if q.get("code") == "workbook_row_unresolved")
    assert not issue["blocking"]
    body["unresolved_rows"][0]["system_id"] = None
    assert not preview(client, headers, body)["items"]


def test_unsynced_unknown_retains_confirmed_identity_without_new_purchase(client, catalog):
    headers, body = completion_body(client, catalog)
    body = accept(body, preview(client, headers, body)["items"][0])
    line = body["lines"].pop()
    body["unresolved_rows"] = [
        dict(
            unknown(device=line["device_id"], confirmed=line),
            line_id=line["line_id"],
            row=line["row"],
        )
    ]
    result = preview(client, headers, body)
    assert not result["items"]
    assert any(d["id"] == line["device_id"] for d in result["configuration"]["devices"])
    response = client.post("/api/wps/sync/preview", headers=headers, json=sync_body(body))
    assert response.status_code == 422


def test_known_device_cannot_be_hidden_by_claiming_an_unrelated_system(client, catalog):
    headers, body = completion_body(client, catalog)
    seed_unrelated_systems(client, headers, body, 1)
    body = accept(body, preview(client, headers, body)["items"][0])
    line = body["lines"].pop()
    body["unresolved_rows"] = [
        dict(
            unknown(system="unrelated-0", device=line["device_id"], confirmed=deepcopy(line)),
            line_id=line["line_id"],
            row=line["row"],
        )
    ]
    result = preview(client, headers, body)
    assert not result["items"]
