from pathlib import Path

from presales.catalog.parser import PRICE_HEADERS

from .schemas import TAX_TERMS, TEMPLATE_ID

TEMPLATE_SHA256 = "1209dba11ed73324ef1fbb2e361c9288049f07d8f8d3da9182152b6337d8800e"
TEMPLATE_PATH = Path(__file__).parent / "templates" / "meeting-system-v1.xlsx"
SECTIONS = (("无纸化会议系统", 10), ("会议扩声系统", 10), ("其他辅助设备", 5))
AUXILIARY_TITLE = (
    "其他辅助设备（周边辅材，需根据现场实际情况定，本次为估算值，不作为实际依据只做参考）"
)


def template_description():
    return dict(
        id=TEMPLATE_ID,
        mapping_version=1,
        sha256=TEMPLATE_SHA256,
        currency="CNY",
        price_columns=sorted(PRICE_HEADERS),
        tax_terms=TAX_TERMS,
        fields=[
            "customer",
            "project_name",
            "sales_contact",
            "designer_contact",
            "design_date",
            "room_description",
            "price_column",
        ],
        columns=[
            "序号",
            "产品名称",
            "产品型号",
            "产品说明",
            "数量",
            "单位",
            "单价",
            "金额",
            "品牌",
            "备注说明",
        ],
        sections=[dict(name=name, reserved_rows=count) for name, count in SECTIONS],
    )
