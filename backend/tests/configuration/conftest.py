import pytest

BASE = "/api/configuration"
AUTHOR = dict(actor="测试维护者", evidence="隔离测试资料，不是业务确认")


def post(client, path, data):
    response = client.post(BASE + path, json=data)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def catalog(client, workbook):
    imported = client.post("/api/imports", files={"file": ("test.xlsx", workbook)}).json()
    sources = client.get("/api/products", params={"import_id": imported["id"]}).json()
    sources = [client.get("/api/products/" + s["id"]).json() for s in sources]
    product = post(
        client, "/products", dict(name="测试服务器", model="SERVER-X", category="服务器", **AUTHOR)
    )
    variants = []
    for source in sources:
        memory = source["specification"].replace("GB", "")
        variant = post(
            client,
            "/variants",
            dict(
                product_id=product["id"],
                name=memory + "GB",
                status="confirmed",
                attributes=[
                    dict(key="memory", kind="quantity", value=memory, unit="GB"),
                    dict(key="cpu_arch", kind="text", value="x86", unit=""),
                ],
                **AUTHOR,
            ),
        )
        post(
            client,
            "/source-links",
            dict(
                variant_id=variant["id"],
                items=[dict(source_id=source["id"], expected_revision=0)],
                **AUTHOR,
            ),
        )
        variants.append(variant)
    return dict(imported=imported, sources=sources, product=product, variants=variants)


@pytest.fixture
def config(catalog):
    device = dict(
        id="device-1",
        name="服务器一",
        variant_id=catalog["variants"][0]["id"],
        source_id=catalog["sources"][0]["id"],
        quantity="1",
        kind="hardware",
    )
    return dict(
        **AUTHOR,
        rooms=[dict(id="room", name="测试会议室")],
        systems=[
            dict(id="paper", room_id="room", name="无纸化系统", kind="无纸化"),
            dict(id="booking", room_id="room", name="会议预约系统", kind="会议预约"),
        ],
        requirements=[
            dict(
                id="r1",
                system_id="paper",
                role="服务端",
                device_id="device-1",
                environment=[],
                resources=[dict(key="memory", amount="40", unit="GB")],
            )
        ],
        devices=[device],
        drawing_xml="",
        knowledge_snapshot=None,
    )


@pytest.fixture
def project(client):
    return client.post("/api/projects", json={"name": "隔离验证项目"}).json()


def knowledge(client, variant, **extra):
    return post(
        client,
        "/knowledge",
        {
            **dict(
                name="测试适用条件",
                kind="suitability",
                status="confirmed",
                selector={"variant_ids": [variant["id"]]},
                system="无纸化",
                role="服务端",
                **AUTHOR,
            ),
            **extra,
        },
    )
