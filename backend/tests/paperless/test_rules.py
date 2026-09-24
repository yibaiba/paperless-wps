import pytest

from .conftest import DISTRIBUTED


def test_no_rules_exposes_uncovered_paperless_products(paperless):
    paperless.add(paperless.product("IPH-S156AM"), quantity="20")
    preview = paperless.preview()
    assert preview["active_rule_count"] == 0
    assert preview["suggestions"] == []
    assert preview["uncovered_items"][0]["model"] == "IPH-S156AM"


def test_configured_software_counts_group_deduction_apply_and_history(paperless):
    terminal = paperless.product("PCS-6580T")
    software = paperless.product("RS-MSC100C-W")
    rule = paperless.rule(terminal, software)
    original = paperless.add(terminal, quantity="10")
    paperless.add(terminal, quantity="11")
    paperless.add(software, quantity="3")
    paperless.add(terminal, quantity="4", group="会议室 B")
    preview = paperless.preview()
    a, b = preview["suggestions"]
    assert (a["required"], a["existing"], a["missing"]) == ("21", "3", "18")
    assert (b["required"], b["existing"], b["missing"]) == ("4", "0", "4")
    paperless.apply(preview).raise_for_status()
    assert paperless.apply(preview).status_code == 409
    assert all(s["missing"] == "0" for s in paperless.preview()["suggestions"])
    items = paperless.request("get", paperless.path)["items"]
    assert next(i for i in items if i["id"] == original["id"]) == original
    history = paperless.request("get", paperless.path + "/rule-history")
    trace = history[0]["calculation"]["suggestions"][0]["rules"][0]
    assert trace["rule_id"] == rule["id"] and trace["revision"] == 1
    assert trace["trace"]["calculate"]["input"]["quantity"] == "21"


def test_same_model_other_product_line_does_not_trigger_red_rule(paperless):
    red_terminal = paperless.product("PCS-6580T")
    other_terminal = paperless.product("PCS-6580T", sheet=DISTRIBUTED)
    paperless.rule(red_terminal, paperless.product("RS-MSC100C-W"))
    paperless.add(other_terminal, quantity="12")
    preview = paperless.preview()
    assert preview["suggestions"] == []
    assert preview["uncovered_items"][0]["product_id"] == other_terminal["id"]


@pytest.mark.parametrize("quantity,expected", [("49", "1"), ("50", "1"), ("51", "2")])
def test_explicit_capacity_arithmetic_only(paperless, quantity, expected):
    # This is not approval to solve a 51-terminal deployment with two servers.
    terminal = paperless.product("PCS-6580T")
    paperless.rule(
        terminal,
        paperless.product("PCS-1516N"),
        mode="per_capacity",
        factor="50",
        evidence="I6 原文 50 台以内；只测试 50 的容量算式，不确认分片或部署方案。",
    )
    paperless.add(terminal, quantity=quantity)
    assert paperless.preview()["suggestions"][0]["required"] == expected


def test_editing_terminal_quantity_invalidates_saved_preview(paperless):
    terminal = paperless.product("PCS-6580T")
    paperless.rule(terminal, paperless.product("RS-MSC100C-W"))
    item = paperless.add(terminal, quantity="20")
    preview = paperless.preview()
    paperless.request(
        "patch",
        paperless.path + f"/items/{item['id']}",
        json={
            "quantity": "25",
            "group_name": "会议室 A",
            "note": "增加席位",
        },
    )
    assert paperless.apply(preview).status_code == 409
    assert paperless.preview()["suggestions"][0]["required"] == "25"


def test_accepted_shared_pool_should_round_combined_terminal_count(paperless):
    # Conditional acceptance scenario: a designer has allowed these terminals to share one pool.
    server = paperless.product("PCS-1516N", sheet=DISTRIBUTED)
    first = paperless.product("PCS-6580T", sheet=DISTRIBUTED)
    second = paperless.product("PCS-6780T", sheet=DISTRIBUTED)
    paperless.rule(
        first,
        server,
        mode="per_capacity",
        factor="50",
        additional_source_ids=[second["id"]],
        evidence="隔离测试假设：两种终端已批准共用 50 容量池，不作为实际部署确认。",
    )
    paperless.add(first, quantity="20")
    paperless.add(second, quantity="20")
    preview = paperless.preview()
    assert preview["suggestions"][0]["required"] == "1"
    assert len(preview["suggestions"][0]["rules"][0]["contributions"]) == 2
    assert preview["uncovered_items"] == []
    paperless.add(first, quantity="30", group="系统 B")
    paperless.add(second, quantity="30", group="系统 B")
    assert sorted(s["required"] for s in paperless.preview()["suggestions"]) == ["1", "2"]


def test_mandatory_module_and_host_should_be_identified(paperless):
    lift = paperless.product("IPH-S156AM", sheet=DISTRIBUTED)
    assert paperless.detail(lift)["note"] == "必配升降话筒单元模块和会议主机"
    paperless.add(lift, quantity="20")
    paperless.rule(
        lift,
        paperless.product("ACS-320M", sheet=DISTRIBUTED),
        relation="required",
        mode="per_group",
        factor="1",
        evidence="I42:I49 必配会议主机；本次验证至少存在一台，不验证容量和回路。",
    )
    suggestions = paperless.preview()["suggestions"]
    assert suggestions[0]["target"]["model"] == "ACS-320M"
    assert suggestions[0]["mandatory"] and suggestions[0]["missing"] == "1"
    paperless.apply(paperless.preview()).raise_for_status()
    assert paperless.preview()["suggestions"][0]["missing"] == "0"
