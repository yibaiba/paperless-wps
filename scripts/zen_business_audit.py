"""Audit pinned decision runtimes and combination coverage without writing data."""

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from presales.configuration.models import Entity
from presales.rules.calculation import digest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
AUDITED_KINDS = {
    "knowledge",
    "knowledge_package",
    "project",
    "list_draft",
    "decision_bundle",
}


def configuration_for(record):
    payload = record["payload"]
    return payload.get("configuration", payload)


def summarize(records):
    selected = [record for record in records if record["kind"] in AUDITED_KINDS]
    knowledge = [r for r in selected if r["kind"] == "knowledge"]
    packages = [r for r in selected if r["kind"] == "knowledge_package"]
    configurations = [r for r in selected if r["kind"] in {"project", "list_draft"}]
    kind_counts = Counter(r["payload"].get("kind", "unknown") for r in knowledge)
    status_counts = Counter(r["payload"].get("status", "unknown") for r in knowledge)
    runtime_counts = Counter(
        configuration_for(record).get("decision_runtime", "python-v3")
        for record in configurations
    )
    package_rows = []
    for record in packages:
        rules = record["payload"].get("rules", [])
        package_rows.append(
            {
                "id": record["id"],
                "revision": record["revision"],
                "name": record["payload"].get("name", ""),
                "status": record["payload"].get("status", "unknown"),
                "rule_count": len(rules),
                "combination_count": sum(
                    rule.get("kind") == "combination" for rule in rules
                ),
            }
        )
    project_rows = []
    for record in configurations:
        configuration = configuration_for(record)
        project_rows.append(
            {
                "id": record["id"],
                "kind": record["kind"],
                "revision": record["revision"],
                "calculation_version": configuration.get("calculation_version"),
                "decision_runtime": configuration.get("decision_runtime", "python-v3"),
                "decision_bundle_id": configuration.get("decision_bundle_id"),
            }
        )
    return {
        "mode": "read_only",
        "knowledge": {
            "count": len(knowledge),
            "kind_counts": dict(sorted(kind_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "combination_count": kind_counts["combination"],
        },
        "packages": package_rows,
        "runtimes": dict(sorted(runtime_counts.items())),
        "configurations": project_rows,
        "decision_bundle_count": sum(r["kind"] == "decision_bundle" for r in selected),
        "fingerprint": digest(selected),
    }


def database_records(session):
    return [
        {
            "id": record.id,
            "kind": record.kind,
            "revision": record.revision,
            "payload": record.payload,
        }
        for record in session.scalars(select(Entity).order_by(Entity.kind, Entity.id))
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with Session(engine) as session:
            report = summarize(database_records(session))
            session.rollback()
    finally:
        engine.dispose()
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
