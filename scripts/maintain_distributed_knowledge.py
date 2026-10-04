"""Preview/apply source-backed distributed 2.0 revisions without publishing packages."""

import argparse
import json
import os
import signal
from pathlib import Path

from dotenv import load_dotenv
from paperless_review.distributed import build_distributed_plan
from paperless_review.distributed_sources import build_source_plan
from paperless_review.maintenance import apply_plan
from presales.configuration.common import Entities
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--source-details",
        action="store_true",
        help="补齐明确参数、环境关系与条件配套，不发布资料包",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    signal.alarm(60)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with Session(engine) as session:
            plan = (build_source_plan if args.source_details else build_distributed_plan)(session)
            updated = apply_plan(session, plan)
            report = dict(
                mode="applied" if args.apply else "validated-preview",
                fingerprint=plan["fingerprint"],
                changes=[
                    {k: c[k] for k in ("id", "kind", "changed", "result_revision")}
                    for c in plan["changes"]
                ],
                updated=len(updated),
                definition=Entities(session).get(plan["changes"][0]["id"]).payload,
            )
            session.commit() if args.apply else session.rollback()
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(
                json.dumps(
                    {k: v for k, v in report.items() if k not in {"changes", "definition"}},
                    ensure_ascii=False,
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
