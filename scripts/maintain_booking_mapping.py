"""Preview and atomically apply the explicitly reviewed booking role association."""

import argparse
import json
import os
import signal
from pathlib import Path

from dotenv import load_dotenv
from paperless_review.booking_mapping import BUSINESS_SELECTION, build_mapping_plan
from paperless_review.maintenance import apply_plan
from presales.configuration.common import Entities, view
from presales.configuration.definitions.readiness import package_readiness
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def inventory(session):
    entities = Entities(session)
    package = view(entities.get(BUSINESS_SELECTION.package_id, kind="knowledge_package"))
    latest = {
        identity: entities.get(identity).revision
        for identity in [package["system_definition_id"], *[m["id"] for m in package["members"]]]
    }
    return package_readiness(package, latest=latest)


def main(*, build_plan=build_mapping_plan, description=__doc__):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with Session(engine) as session:
            plan = build_plan(session)
            if args.apply and args.expected_fingerprint != plan["fingerprint"]:
                raise ValueError("应用必须提供本次预览指纹；资料变化后请重新预览")
            before = inventory(session)
            updated = apply_plan(session, plan)
            after = inventory(session)
            report = dict(
                mode="applied" if args.apply else "validated-preview",
                fingerprint=plan["fingerprint"],
                changes=plan["changes"],
                updated=len(updated),
                before=before,
                after=after,
            )
            session.commit() if args.apply else session.rollback()
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps({k: report[k] for k in ("mode", "fingerprint", "updated")}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    signal.alarm(60)
    main()
