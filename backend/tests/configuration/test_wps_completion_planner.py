from presales.wps.completion_planner import fulfilled_alternative_ids, plan_relations


def variant(identity, *, category="终端"):
    return {
        "id": identity,
        "product": {"model": identity, "name": identity, "category": category},
        "series": [],
    }


def rule(*, selectors, targets, accessory_type="required"):
    return {
        "id": "relation",
        "name": "确认配套",
        "kind": "accessory",
        "status": "confirmed",
        "selector": {
            "variant_ids": selectors,
            "exclude_variant_ids": [],
            "category": "",
            "series": [],
        },
        "target_variant_ids": targets,
        "accessory_type": accessory_type,
    }


def test_satisfied_alternative_does_not_recommend_the_other_choice():
    hardware = variant("hardware")
    relation = rule(selectors=["hardware"], targets=["software-a", "software-b"])

    plans = plan_relations(hardware, [relation], {"hardware", "software-a"})

    assert plans == []


def test_satisfied_relation_suppresses_unselected_alternatives_from_contextual_completion():
    hardware = variant("hardware")
    selected = variant("software-a", category="客户端软件")
    relation = rule(selectors=["hardware"], targets=["software-a", "software-b"])

    suppressed = fulfilled_alternative_ids([hardware, selected], [relation])

    assert suppressed == {"software-b"}


def test_missing_required_relation_becomes_a_decisive_plan_step():
    hardware = variant("hardware")
    relation = rule(selectors=["hardware"], targets=["software"])

    [plan] = plan_relations(hardware, [relation], {"hardware"})

    assert plan.variant_ids == ("software",)
    assert plan.reason == "补齐当前方案尚缺的必配项"
    assert plan.decisive is True


def test_selected_software_plans_its_corresponding_hardware_in_reverse():
    software = variant("software", category="客户端软件")
    relation = rule(selectors=["hardware"], targets=["software"])

    [plan] = plan_relations(software, [relation], {"software"})

    assert plan.variant_ids == ("hardware",)
    assert plan.direction == "reverse"
    assert plan.reason == "补齐已选产品的对应主设备"


def test_recommended_relation_never_becomes_a_decisive_tab_step():
    hardware = variant("hardware")
    relation = rule(
        selectors=["hardware"], targets=["accessory"], accessory_type="recommended"
    )

    [plan] = plan_relations(hardware, [relation], {"hardware"})

    assert plan.decisive is False


def test_full_sheet_selection_satisfies_a_relation_outside_the_local_window():
    hardware = variant("hardware")
    relation = rule(selectors=["hardware"], targets=["software"])

    plans = plan_relations(hardware, [relation], {"hardware", "software"})

    assert plans == []
