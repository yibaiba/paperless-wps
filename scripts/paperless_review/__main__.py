"""Preview first, then atomically apply the reviewed file; no schema or project mutations."""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .maintenance import apply_plan
from .planning import build_plan

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with Session(engine) as session:
            plan = json.loads(args.plan.read_text()) if args.apply else build_plan(session)
            result = apply_plan(session, plan)
            if args.apply:
                session.commit()
            else:
                session.rollback()
                args.plan.parent.mkdir(parents=True, exist_ok=True)
                args.plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
            print(
                json.dumps(
                    dict(
                        mode="applied" if args.apply else "validated-preview",
                        changed=len(result),
                        fingerprint=plan["fingerprint"],
                        records=[
                            dict(id=r["id"], name=r["name"], revision=r["revision"]) for r in result
                        ],
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
