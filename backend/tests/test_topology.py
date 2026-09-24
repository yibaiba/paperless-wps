from copy import deepcopy

import pytest


@pytest.fixture
def topology_setup(client, workbook):
    imported = client.post("/api/imports", files={"file": ("topology.xlsx", workbook)}).json()
    products = client.get("/api/products", params={"import_id": imported["id"]}).json()
    data = {
        "name": "拓扑测试",
        "actor": "测试维护人",
        "groups": [
            {
                "id": "g",
                "name": "会议室",
                "product_line": "测试产品线",
                "position": {"x": 10, "y": 20},
                "width": 600,
                "height": 300,
            }
        ],
        "devices": [
            {
                "id": "a",
                "product_id": products[0]["id"],
                "quantity": "2.5",
                "group_id": "g",
                "position": {"x": 30, "y": 40},
            },
            {
                "id": "b",
                "product_id": products[1]["id"],
                "quantity": "1",
                "group_id": "g",
                "position": {"x": 300, "y": 40},
            },
        ],
        "relations": [
            {
                "id": "r",
                "source": "a",
                "target": "b",
                "kind": "required",
                "mode": "per_capacity",
                "factor": "2",
                "evidence": "测试依据",
            }
        ],
    }
    return data


def create(client, data):
    response = client.post("/api/topologies", json=data)
    response.raise_for_status()
    return response.json()


def convert(client, topology, *, revision=None):
    return client.post(
        f"/api/topologies/{topology['id']}/relations/r/rule",
        json={
            "expected_revision": revision or topology["revision"],
            "actor": "测试规则人",
        },
    )


def test_save_reload_revision_conflict_and_frozen_history(client, topology_setup):
    data = topology_setup
    original = create(client, data)
    path = f"/api/topologies/{original['id']}"
    reloaded = client.get(path).json()
    assert {k: v for k, v in reloaded.items() if k != "updated_at"} == {
        k: v for k, v in original.items() if k != "updated_at"
    }
    changed = deepcopy(data)
    changed["devices"][0]["quantity"] = "9"
    response = client.put(path, json={**changed, "expected_revision": 1})
    response.raise_for_status()
    assert response.json()["revision"] == 2
    assert client.put(path, json={**changed, "expected_revision": 1}).status_code == 409
    history = client.get(path + "/history").json()
    assert [h["revision"] for h in history] == [2, 1]
    assert history[1]["devices"][0]["quantity"] == "2.5"
    assert history[0]["products"] == history[1]["products"]
    assert len(client.get("/api/topologies").json()) == 1


def test_shared_device_counted_once_and_exact_decimal_bom(client, topology_setup):
    data = topology_setup
    data["groups"].append({**data["groups"][0], "id": "g2", "name": "第二会议室"})
    data["devices"][0].update(quantity="0.1", serves_group_ids=["g2"])
    data["devices"].append({**data["devices"][0], "id": "c", "quantity": "0.2"})
    result = create(client, data)
    assert len(result["bom"]) == 2
    quantity = next(
        r["quantity"] for r in result["bom"] if r["product_id"] == data["devices"][0]["product_id"]
    )
    assert quantity == "0.3"
    assert result["devices"][0]["serves_group_ids"] == ["g2"]


@pytest.mark.parametrize(
    "bad",
    [
        "missing_product",
        "dangling_edge",
        "self_loop",
        "duplicate_id",
        "missing_group",
        "zero_quantity",
        "duplicate_group",
    ],
)
def test_invalid_topology_is_not_persisted(client, topology_setup, bad):
    data = deepcopy(topology_setup)
    if bad == "missing_product":
        data["devices"][0]["product_id"] = "absent"
    elif bad == "dangling_edge":
        data["relations"][0]["target"] = "absent"
    elif bad == "self_loop":
        data["relations"][0]["target"] = "a"
    elif bad == "duplicate_id":
        data["devices"][0]["id"] = "b"
    elif bad == "missing_group":
        data["devices"][0]["serves_group_ids"] = ["absent"]
    elif bad == "zero_quantity":
        data["devices"][0]["quantity"] = "0"
    else:
        data["groups"].append({**data["groups"][0], "id": "g2"})
    assert client.post("/api/topologies", json=data).status_code == 422
    assert client.get("/api/topologies").json() == []


def test_rule_conversion_real_engine_draft_and_no_duplicate(client, topology_setup):
    topology = create(client, topology_setup)
    response = convert(client, topology)
    response.raise_for_status()
    rule = response.json()
    assert rule["status"] == "draft"
    assert rule["relation"] == "required"
    assert rule["source_product_id"] == topology_setup["devices"][0]["product_id"]
    assert rule["target_product_id"] == topology_setup["devices"][1]["product_id"]
    assert topology["id"] in rule["evidence"]
    trial = client.post(f"/api/rules/{rule['id']}/trial", json={"quantity": "5"})
    trial.raise_for_status()
    assert trial.json()["quantity"] == "3"
    assert convert(client, topology).status_code == 409
    assert len(client.get("/api/rules").json()) == 1
    assert len(client.get(f"/api/topologies/{topology['id']}").json()["rules"]) == 1
    history = client.get(f"/api/rules/{rule['id']}/history").json()
    assert len(history) == 1


@pytest.mark.parametrize(
    "case",
    ["optional", "connection", "missing_evidence", "shared", "different_group", "same_product"],
)
def test_unsupported_conversion_exposes_reason_and_creates_nothing(client, topology_setup, case):
    data = topology_setup
    if case in ("optional", "connection"):
        data["relations"][0]["kind"] = case
    elif case == "missing_evidence":
        data["relations"][0]["evidence"] = ""
    elif case == "shared":
        data["devices"][0]["serves_group_ids"] = ["g"]
    elif case == "different_group":
        data["devices"][0]["group_id"] = None
    else:
        data["devices"][1]["product_id"] = data["devices"][0]["product_id"]
    topology = create(client, data)
    response = convert(client, topology)
    assert response.status_code == 422
    assert client.get("/api/rules").json() == []
    assert client.get(f"/api/topologies/{topology['id']}").json()["rules"] == []


def test_conversion_rejects_stale_revision(client, topology_setup):
    topology = create(client, topology_setup)
    client.put(
        f"/api/topologies/{topology['id']}", json={**topology_setup, "expected_revision": 1}
    ).raise_for_status()
    assert convert(client, topology).status_code == 409
    assert client.get("/api/rules").json() == []


def test_empty_graph_and_unknown_topology(client):
    topology = create(client, {"name": "空白方案", "actor": "测试"})
    assert topology["bom"] == []
    assert client.get("/api/topologies/absent").status_code == 404
    assert client.get("/api/topologies/absent/history").status_code == 404
