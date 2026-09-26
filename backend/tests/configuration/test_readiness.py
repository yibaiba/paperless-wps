from presales.configuration.projects.readiness import project_readiness


def configuration(*, selected=True):
    return {
        "rooms": [{"id": "room", "name": "会议室"}],
        "systems": [{"id": "system", "room_id": "room", "name": "无纸化", "kind": "无纸化"}],
        "requirements": [
            {
                "id": "requirement",
                "system_id": "system",
                "role": "服务端",
                "device_id": "device" if selected else None,
            }
        ],
        "devices": [{"id": "device"}] if selected else [],
    }


def stage(result, key):
    return next(item for item in result["stages"] if item["key"] == key)


def test_empty_project_is_a_savable_incomplete_draft():
    result = project_readiness(
        {"rooms": [], "systems": [], "requirements": [], "devices": []}, [], []
    )
    assert result["status"] == "unknown"
    assert result["ready_for_draft"] is False
    assert result["ready_for_confirmed_output"] is False
    assert "房间" in stage(result, "requirements")["message"]


def test_complete_known_configuration_is_ready_for_confirmed_output():
    result = project_readiness(
        configuration(),
        [{"kind": "compatibility", "status": "pass"}],
        [],
    )
    assert result["status"] == "pass"
    assert result["ready_for_confirmed_output"] is True
    assert all(item["status"] == "pass" for item in result["stages"])


def test_missing_selection_and_unapplied_accessory_keep_output_incomplete():
    result = project_readiness(
        configuration(selected=False),
        [{"kind": "selection", "status": "unknown"}],
        [{"status": "pass", "missing": "1"}],
    )
    assert stage(result, "selection")["status"] == "unknown"
    assert stage(result, "accessories")["message"] == "还有 1 项配套未应用"
    assert result["counts"]["open_accessories"] == 1
    assert result["status"] == "unknown"


def test_any_confirmed_conflict_blocks_confirmed_output():
    result = project_readiness(
        configuration(),
        [{"kind": "capacity", "status": "conflict"}],
        [],
    )
    assert stage(result, "verification")["status"] == "conflict"
    assert stage(result, "output")["status"] == "conflict"
    assert result["ready_for_confirmed_output"] is False
