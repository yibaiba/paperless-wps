from presales.lists.search_matching import matches_query, query_match_score


def variant():
    return {
        "name": "Windows 客户端",
        "product": {
            "model": "RS-MSC100C-W",
            "name": "无纸化会议系统客户端软件",
            "category": "客户端软件",
        },
        "description": "",
        "series": ["无纸化终端"],
        "systems": ["红盾无纸化会议系统"],
        "functions": [],
        "interfaces": [],
        "attributes": [],
    }


def test_compact_chinese_keywords_match_across_product_context():
    item = variant()

    assert matches_query(item, "红盾软件")
    assert matches_query(item, "无纸化客户端软件")
    assert query_match_score(item, "红盾软件") >= 60


def test_fuzzy_chinese_match_requires_both_phrase_anchors():
    item = variant()

    assert not matches_query(item, "红盾摄像头")
    assert not matches_query(item, "红软")


def test_model_prefix_and_space_separated_terms_remain_supported():
    item = variant()

    assert query_match_score(item, "RS-MSC100") == 80
    assert matches_query(item, "红盾 软件")


def test_compact_product_name_beats_a_more_specialized_name_for_a_broad_query():
    generic = variant()
    specialized = {
        **variant(),
        "product": {
            **variant()["product"],
            "name": "红盾无纸化会议系统投票客户端软件（安卓）",
        },
    }

    assert query_match_score(generic, "无纸化客户端软件") > query_match_score(
        specialized, "无纸化客户端软件"
    )


def test_fuzzy_identity_search_does_not_promote_incidental_attribute_text():
    hardware = {
        **variant(),
        "name": "红盾无纸化会议系统华为版本 · 第 12 行",
        "product": {
            "model": "TABLET-1",
            "name": "会议平板",
            "category": "鸿蒙客户端",
        },
        "attributes": [{"key": "note", "value": "内置红盾无纸化软件"}],
    }

    assert not matches_query(hardware, "红盾软件")
    assert matches_query(hardware, "内置红盾无纸化软件")
