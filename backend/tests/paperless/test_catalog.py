from .conftest import DISTRIBUTED, RED


def test_all_paperless_source_rows_and_hidden_version_are_preserved(paperless):
    expected = {
        RED: 41,
        "红盾无纸化充电柜传输版": 9,
        "红盾无纸化会议系统华为版本": 23,
        "安全无纸化V3.0": 11,
        DISTRIBUTED: 60,
    }
    assert len(paperless.products) == 459
    for sheet, count in expected.items():
        rows = [p for p in paperless.products if p["sheet"] == sheet]
        assert len(rows) == count
        assert all(p["hidden"] == ("华为版本" in sheet) for p in rows)


def test_sizes_and_merged_mandatory_note_remain_separate(paperless):
    for size, label in [("156", "15.6"), ("173", "17.3"), ("185", "18.5"), ("215", "21.5")]:
        for screen in ("A", "B"):
            product = paperless.detail(
                paperless.product(f"IPH-S{size}{screen}M", sheet=DISTRIBUTED)
            )
            assert label in product["name"]
            assert "必配升降话筒单元模块和会议主机" == product["note"]
            assert product["sources"]["note"] == "I42:I49"
            assert "RS-485" in product["specification"] or "RS485" in product["specification"]
    plain = paperless.detail(paperless.product("IPH-S156A", sheet=DISTRIBUTED))
    assert plain["note"] == ""


def test_conflicting_capacity_is_preserved_without_rewriting(paperless):
    master = next(
        p for p in paperless.products if p["sheet"] == "报价总表（此表勿动）" and p["row"] == 104
    )
    detail = paperless.detail(master)
    assert detail["model"] == "PCS-1516N"
    assert "5台终端以内" in detail["note"]
    assert detail["sources"]["note"] == "J104"
    distributed = paperless.detail(paperless.product("PCS-1516N", sheet=DISTRIBUTED))
    assert "50台终端" in distributed["note"]
    assert distributed["sources"]["note"] == "I17"


def test_selected_configuration_snapshot_retains_source_and_os(paperless):
    windows = paperless.add(paperless.product("RS-MSC100C-W"))
    kylin = paperless.add(paperless.product("RS-MSC100C-K"))
    charging = paperless.add(paperless.product("RS-MSC200", sheet="红盾无纸化充电柜传输版"))
    assert "windows" in windows["snapshot"]["note"]
    assert "麒麟" in kylin["snapshot"]["note"]
    assert charging["snapshot"]["model"] == "RS-MSC200"
    assert charging["snapshot"]["sources"]["model"] == "E8"
    assert len({i["product_id"] for i in (windows, kylin, charging)}) == 3
