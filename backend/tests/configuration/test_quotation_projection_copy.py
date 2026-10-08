from copy import deepcopy

from presales.quotation.calculation import adopt_prices


def test_adopt_prices_only_copies_the_modified_quotation_branch():
    configuration = dict(
        devices=[
            dict(
                id="device",
                variant_id="variant",
                source_id="source",
            )
        ],
        quotation=dict(
            price_column="报价",
            prices=[],
            sections={"removed": "旧分区"},
        ),
    )
    original = deepcopy(configuration)

    result = adopt_prices(configuration)

    assert configuration == original
    assert result is not configuration
    assert result["devices"] is configuration["devices"]
    assert result["quotation"] is not configuration["quotation"]
    assert result["quotation"]["sections"] == {}
    assert result["quotation"]["prices"][0]["device_id"] == "device"
