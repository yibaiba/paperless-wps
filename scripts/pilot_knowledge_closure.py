"""Create evidence-linked pilot drafts without confirming compatibility or quantities.

Default is a read-only preview. --apply creates only missing definitions/packages;
existing maintainer records and historical knowledge are never overwritten.
"""

import argparse
import json

import httpx

PILOTS = (
    {
        "name": "红盾无纸化会议系统 · Windows",
        "sheet": "红盾无纸化会议系统",
        "rows": (6, 7, 8),
        "software_row": 8,
        "gaps": "第8行软件要求 Windows；第6-7行主机备注为优班图。Windows 部署主机、授权数量、资源需求及共用条件待确认。",
    },
    {
        "name": "会议预约与信息发布系统",
        "sheet": "会议预约与信发系统",
        "rows": (17, 18),
        "software_row": 18,
        "gaps": "第17行服务器支持 Linux，第18行软件支持 Linux 部署；数量、容量、授权和跨系统共用条件待确认。",
    },
)


def request(client, method, path, **kwargs):
    response = client.request(method, "/api/configuration" + path, **kwargs)
    response.raise_for_status()
    return response.json()


def proposal(pilot, variants, knowledge):
    sources = [
        (v, s)
        for v in variants
        for s in v.get("source_details", [])
        if s["sheet"] == pilot["sheet"] and s["row"] in pilot["rows"]
    ]
    if {s["row"] for _, s in sources} != set(pilot["rows"]):
        raise ValueError("试点原始来源不完整：" + pilot["name"])
    software = {v["id"] for v, s in sources if s["row"] == pilot["software_row"]}
    rules = [
        k
        for k in knowledge
        if software.intersection(k["selector"]["variant_ids"])
        and k["kind"] != "sharing"
        and k["status"] != "disabled"
    ]
    evidence = "\n".join(
        f"{s['sheet']} 第{s['row']}行；来源 {s['id']}；{v['product']['model']} {v['product']['name']}；备注：{s.get('note', '')}"
        for v, s in sources
    )
    return {
        "name": pilot["name"],
        "status": "draft",
        "legacy_names": [],
        "roles": [
            {"id": "server-software", "name": "服务端软件", "required": False},
            {"id": "server", "name": "服务器", "required": False},
            {"id": "terminal", "name": "终端", "required": False},
            {"id": "license", "name": "授权", "required": False},
        ],
        "actor": "资料整理",
        "evidence": evidence
        + "\n"
        + pilot["gaps"]
        + "\n角色必要性尚待维护者确认；草稿不代表这些角色均为可选。",
    }, rules


def maintain(client, *, apply=False):
    variants = request(client, "GET", "/variants")
    knowledge = request(client, "GET", "/knowledge")
    definitions = request(client, "GET", "/definitions")["definitions"]
    packages = request(client, "GET", "/knowledge-packages")
    results = []
    for pilot in PILOTS:
        payload, rules = proposal(pilot, variants, knowledge)
        definition = next(
            (d for d in definitions if d["name"] == payload["name"]), None
        )
        if apply and definition is None:
            definition = request(client, "POST", "/definitions", json=payload)
        package_name = pilot["name"] + " · 试点资料核对"
        package = next((p for p in packages if p["name"] == package_name), None)
        if apply and package is None:
            package = request(
                client,
                "POST",
                "/knowledge-packages",
                json={
                    "name": package_name,
                    "system_definition_id": definition["id"],
                    "definition_revision": definition["revision"],
                    "branch": pilot["name"],
                    "status": "draft",
                    "members": [{"id": k["id"], "revision": k["revision"]} for k in rules],
                    "coverage": [],
                    "actor": payload["actor"],
                    "evidence": payload["evidence"],
                },
            )
        results.append(
            {
                "definition": definition or payload,
                "package_id": package["id"] if package else None,
                "referenced_rules": len(rules),
                "unresolved": pilot["gaps"],
            }
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8016")
    parser.add_argument("--apply", action="store_true")
    options = parser.parse_args()
    with httpx.Client(base_url=options.base_url, timeout=30) as client:
        print(
            json.dumps(
                maintain(client, apply=options.apply), ensure_ascii=False, indent=2
            )
        )
