from presales.configuration.projects.output import project_output


def test_project_output_keeps_source_and_shared_consumers():
    data = {
        "calculation_version": 2,
        "knowledge_snapshot_id": "knowledge-1",
        "devices": [
            {
                "id": "server-1",
                "kind": "hardware",
                "name": "共享服务器",
                "source_id": "source-1",
                "variant_snapshot": {"product": {"model": "SERVER-1"}},
                "source_snapshot": {
                    "id": "source-1",
                    "import_id": "import-1",
                    "sheet": "服务器",
                    "row": 8,
                    "model": "SERVER-1",
                    "specification": "128GB / 32 核",
                    "unit": "台",
                    "prices": {"最低客户报价": "10000"},
                },
                "quantity": "1",
                "note": "",
            }
        ],
    }
    usages = [
        {
            "device_id": "server-1",
            "consumers": [
                {
                    "requirement_id": "paperless",
                    "system_name": "无纸化",
                    "role": "服务端",
                    "via": "accessory",
                },
                {
                    "requirement_id": "booking",
                    "system_name": "会议预约",
                    "role": "服务端",
                    "via": "accessory",
                },
            ],
        }
    ]
    readiness = {"ready_for_confirmed_output": False}

    result = project_output(data, usages, readiness)

    assert result["status"] == "draft"
    assert result["knowledge_snapshot_id"] == "knowledge-1"
    assert result["lines"] == [
        {
            "device_id": "server-1",
            "kind": "hardware",
            "name": "共享服务器",
            "model": "SERVER-1",
            "specification": "128GB / 32 核",
            "unit": "台",
            "quantity": "1",
            "note": "",
            "prices": {"最低客户报价": "10000"},
            "consumers": [
                {
                    "requirement_id": "paperless",
                    "system_name": "无纸化",
                    "role": "服务端",
                    "via": "accessory",
                },
                {
                    "requirement_id": "booking",
                    "system_name": "会议预约",
                    "role": "服务端",
                    "via": "accessory",
                },
            ],
            "source": {
                "id": "source-1",
                "import_id": "import-1",
                "sheet": "服务器",
                "row": 8,
            },
        }
    ]


def test_project_output_marks_confirmed_only_after_readiness_passes():
    result = project_output(
        {"devices": [], "calculation_version": 2},
        [],
        {"ready_for_confirmed_output": True},
    )

    assert result["status"] == "confirmed"
    assert result["ready_for_confirmed_output"] is True
