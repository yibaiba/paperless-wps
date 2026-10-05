"""Prepare disposable 100/500-row projects on an explicitly supplied isolated API."""

import argparse
import json
import signal
from copy import deepcopy
from pathlib import Path

import httpx


def rows_configuration(base, *, size):
    stock = next(d for d in base["devices"] if d["id"] == "pool")
    roles = [r for r in base["requirements"] if r["role_id"] == "server"]
    data = deepcopy(base)
    data.update(
        devices=[],
        requirements=[],
        accessory_allocations=[],
        included_allocations=[],
        supply_allocations=[],
        accessory_choices=[],
        drawing_xml="",
    )
    for i in range(size):
        identity = f"device-{i}"
        data["devices"].append(dict(stock, id=identity, name=f"隔离性能设备 {i + 1}", quantity="1"))
        data["requirements"].append(
            dict(
                roles[i % len(roles)],
                id=f"role-{i}",
                device_id=identity,
                allocations=[],
                resources=[
                    dict(
                        key="memory",
                        amount="0",
                        unit="GB",
                        aggregation="sum",
                        capacity_basis="unit",
                        applies_to="selected_device",
                    )
                ],
            )
        )
        data["supply_allocations"].append(
            dict(
                id="supply-" + identity,
                device_id=identity,
                quantity="1",
                source="purchase",
                evidence="隔离性能测试",
            )
        )
    data["quotation"] = dict(
        project_name=f"隔离 {size} 行性能",
        price_column="甲方指导价",
        prices=[
            dict(
                device_id=d["id"],
                variant_id=d["variant_id"],
                source_id=d["source_id"],
                mode="manual",
                unit_price="1",
                evidence="隔离性能价格",
            )
            for d in data["devices"]
        ],
    )
    return data


def prepare(args):
    projects = {}
    with httpx.Client(base_url=args.api, timeout=30) as http:
        result = http.get("/api/configuration/projects/" + args.source_project_id)
        base = result.raise_for_status().json()["configuration"]
        for size in (100, 500):
            data = rows_configuration(base, size=size)
            project = http.post("/api/projects", json=dict(name=f"隔离：用途性能 {size} 行"))
            identity = project.raise_for_status().json()["id"]
            response = http.put(
                "/api/configuration/projects/" + identity,
                json=dict(expected_revision=0, configuration=data),
            )
            assert response.status_code == 200, response.text
            assert len(response.json()["device_usages"]) == size
            projects[str(size)] = identity
    args.output.write_text(json.dumps(projects, ensure_ascii=False, indent=2))
    print(projects)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True, help="已准备的隔离测试 API")
    parser.add_argument("--source-project-id", required=True, help="隔离 alias 容量项目")
    parser.add_argument("--output", type=Path, required=True)
    signal.alarm(60)
    prepare(parser.parse_args())
