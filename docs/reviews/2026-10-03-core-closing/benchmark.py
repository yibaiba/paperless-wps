import json, time
from copy import deepcopy
from pathlib import Path
from statistics import median
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
import zen
from presales.configuration.projects.repository import ProjectConfigurations
from presales.configuration.projects.schemas import Configuration
from presales.rules.engine import ZenQuantityEngine
from presales.configuration.models import Entity
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.rules.calculation import digest
from uuid import uuid5, NAMESPACE_URL

root = Path.cwd()
folder = root / ".mission/20261003-zen-decisions"
fixture = json.loads((folder / "acceptance.json").read_text())
engine = create_engine("sqlite:///" + str(folder / "acceptance.db"))
quantity = ZenQuantityEngine(zen.ZenEngine())
query = []


@event.listens_for(engine, "before_cursor_execute")
def start(conn, *args):
    conn.info["query_started"] = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def stop(conn, *args):
    query.append((time.perf_counter() - conn.info["query_started"]) * 1000)


results = []
for size in [100, 500]:
    for runtime in ["python-v3", "zen-v1"]:
        samples = []
        for repeat in range(3):
            data = deepcopy(fixture["configuration"])
            # Compare the same isolated pinned suitability condition in both runtimes.
            with Session(engine) as session:
                repository = ProjectConfigurations(session, quantity)
                base = repository.get(fixture["legacy_project"])["configuration"]
                data = deepcopy(base)
                d = data["devices"][0]
                r = data["requirements"][0]
                rule = KnowledgeInput(
                    name="隔离性能适用",
                    actor="benchmark",
                    evidence="隔离测试",
                    kind="suitability",
                    status="confirmed",
                    system="无纸化",
                    role="服务端",
                    selector={"variant_ids": [d["variant_id"]]},
                    conditions=[
                        {
                            "field": "product.memory",
                            "operator": "range",
                            "minimum": "32",
                            "unit": "GB",
                        }
                    ],
                ).model_dump(mode="json")
                rule.update(id="benchmark-rule", revision=1)
                snapshot_id = str(
                    uuid5(NAMESPACE_URL, "benchmark-knowledge:" + digest(rule))
                )
                if session.get(Entity, snapshot_id) is None:
                    session.add(
                        Entity(
                            id=snapshot_id,
                            kind="knowledge_snapshot",
                            payload={"knowledge": [rule]},
                        )
                    )
                    session.flush()
                data.update(
                    knowledge_snapshot=[rule], knowledge_snapshot_id=snapshot_id
                )
                data.update(
                    decision_runtime=runtime,
                    decision_bundle_id=None,
                    devices=[],
                    requirements=[],
                )
                for i in range(size):
                    data["devices"].append(dict(d, id=f"device-{i}"))
                    data["requirements"].append(
                        dict(r, id=f"role-{i}", device_id=f"device-{i}")
                    )
                query.clear()
                start_time = time.perf_counter()
                checked = repository.check(Configuration.model_validate(data))
                elapsed = (time.perf_counter() - start_time) * 1000
                samples.append(
                    dict(
                        total_ms=elapsed,
                        db_ms=sum(query),
                        queries=len(query),
                        checks=len(checked["checks"]),
                    )
                )
        results.append(
            dict(
                rows=size,
                runtime=runtime,
                median_total_ms=median(s["total_ms"] for s in samples),
                median_db_ms=median(s["db_ms"] for s in samples),
                samples=samples,
            )
        )
print(json.dumps(results, indent=2))
(root / "docs/reviews/2026-10-03-core-closing/after-context-project.json").write_text(
    json.dumps(results, indent=2)
)
