from .test_wps_addin import authorized, diagnostic_event, paired


def test_stage_timing_is_anonymous_and_deduplicated(client):
    token, _ = paired(client)
    headers = authorized(token)
    event = diagnostic_event(
        event_type="phase_timing", completion_phase="context-build", duration_ms=12
    )
    body = {"events": [event]}
    first = client.post("/api/wps/diagnostics/batch", headers=headers, json=body)
    assert first.status_code == 200, first.text
    repeated = client.post("/api/wps/diagnostics/batch", headers=headers, json=body)
    assert repeated.status_code == 200
    assert repeated.json()["accepted"] == 0
    assert repeated.json()["duplicates"] == 1
    private = dict(event, row_values={"name": "客户文字"})
    assert (
        client.post(
            "/api/wps/diagnostics/batch", headers=headers, json={"events": [private]}
        ).status_code
        == 422
    )
