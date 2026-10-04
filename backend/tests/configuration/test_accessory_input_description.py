from presales.configuration.definitions.requirements import describe_requirements


def records():
    definition = dict(
        id="sys",
        revision=1,
        name="隔离系统",
        status="confirmed",
        roles=[
            dict(id="software", name="服务端软件", required=True, feature=""),
            dict(id="screen", name="字幕", required=True, feature="subtitles"),
        ],
    )
    selector = dict(variant_ids=["software"], category="", series=[], exclude_variant_ids=[])
    base = dict(
        id="suitable",
        revision=1,
        kind="suitability",
        status="confirmed",
        effect="allow",
        system_definition_id="sys",
        role_id="software",
        selector=selector,
        conditions=[],
        activation_conditions=[],
    )
    capture = dict(
        base,
        id="capture",
        kind="accessory",
        role_id="",
        system_definition_id="",
        target_variant_ids=["box"],
        accessory_type="required",
        need_key="capture",
        calculation_scope="system",
        quantity_source="environment",
        quantity_key="audio_capture_room_count",
        quantity_unit="",
    )
    subtitle = dict(
        capture,
        id="subtitle",
        accessory_type="optional",
        need_key="subtitle",
        quantity_key="subtitle_room_count",
    )
    return definition, [base, capture, subtitle]


def test_preselection_discovers_generic_accessory_inputs_and_does_not_invent_products():
    definition, rules = records()
    output = describe_requirements(definition, rules=rules, features=[])
    fields = {f["key"]: f for f in output["roles"][0]["inputs"]}
    assert fields["audio_capture_room_count"]["purpose"] == "project_input"
    assert fields["audio_capture_room_count"]["scope"] == "system"
    assert fields["subtitle_room_count"]["conditional"] is True
    assert fields["subtitle_room_count"]["candidate_variant_ids"] == ["software"]
    assert not output["roles"][1]["active"]


def test_face_licensing_input_has_business_label_and_is_not_a_hardware_requirement():
    definition, rules = records()
    rules[1]["quantity_key"] = "face_terminal_count"
    output = describe_requirements(definition, rules=rules, features=[])
    field = next(f for f in output["shared_inputs"] if f["key"] == "face_terminal_count")
    assert (field["label"], field["purpose"], field["unit"]) == (
        "启用人脸签到的终端数量",
        "project_input",
        "",
    )


def test_chain_cycles_and_different_units_are_visible_without_truncating():
    definition, rules = records()
    chained = dict(
        rules[1],
        id="chained",
        selector=dict(rules[1]["selector"], variant_ids=["box"]),
        target_variant_ids=["software"],
        quantity_unit="台",
    )
    output = describe_requirements(definition, rules=[*rules, chained], features=[])
    assert any(
        g["code"] == "accessory_input_cycle" and g["rule_ids"] == ["capture", "chained"]
        for g in output["input_gaps"]
    )
    assert any(g["code"] == "input_definition_conflict" for g in output["input_gaps"])
    fields = [f for f in output["roles"][0]["inputs"] if f["key"] == "audio_capture_room_count"]
    assert {f["unit"] for f in fields} == {"", "台"}


def test_different_role_inputs_are_not_shared():
    definition, rules = records()
    rules[1] = dict(rules[1], calculation_scope="device")
    output = describe_requirements(definition, rules=rules, features=[])
    assert output["roles"][0]["inputs"][0]["scope"] == "role"
    assert output["roles"][1]["inputs"] == []


def test_shared_inputs_keep_consumers_and_report_cross_role_units():
    definition, rules = records()
    definition["roles"][1]["feature"] = ""
    rules += [
        dict(
            rules[0],
            id="other-role",
            role_id="screen",
            selector=dict(rules[0]["selector"], variant_ids=["display"]),
        ),
        dict(
            rules[1],
            id="other-unit",
            selector=dict(rules[1]["selector"], variant_ids=["display"]),
            quantity_unit="间",
        ),
    ]
    output = describe_requirements(definition, rules=rules, features=[])
    assert any(
        g["code"] == "input_definition_conflict" and g["role_id"] == ""
        for g in output["input_gaps"]
    )
    assert {r for f in output["shared_inputs"] for r in f["consumer_role_ids"]} == {
        "screen",
        "software",
    }
