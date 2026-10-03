"""Preview or apply source-backed facts and knowledge corrections as one transaction."""

import argparse
import json
import os
import signal
from pathlib import Path

from dotenv import load_dotenv
from paperless_review.maintenance import apply_plan
from paperless_review.reconciliation import build_reconciliation
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    signal.alarm(60)
    load_dotenv(ROOT / ".env")
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with Session(engine) as session:
            plan = (
                json.loads(args.plan.read_text()) if args.apply else build_reconciliation(session)
            )
            applied = apply_plan(session, plan)
            if args.apply:
                session.commit()
            else:
                session.rollback()
                args.plan.parent.mkdir(parents=True, exist_ok=True)
                args.plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
            summary = dict(
                mode="applied" if args.apply else "validated-preview",
                records=[dict(id=r["id"], name=r["name"], revision=r["revision"]) for r in applied],
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
