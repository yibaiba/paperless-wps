"""Validate source-backed drafts; --apply commits without publishing any knowledge."""

import argparse
import json
import os
import signal
from pathlib import Path

from dotenv import load_dotenv
from paperless_review.multiroom import maintain
from presales.configuration.extraction.workbooks import workbook_preview
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    signal.alarm(60)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    preview = workbook_preview(args.workbook.read_bytes(), filename=args.workbook.name)
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with Session(engine) as session:
            result = maintain(session, preview)
            report = dict(
                mode="applied-drafts" if args.apply else "validated-preview",
                digest=preview["digest"],
                material_id=result["material"]["id"],
                rule_count=result["rule_count"],
                definitions=[
                    dict(id=d["id"], name=d["name"], status=d["status"])
                    for d in result["definitions"]
                ],
                packages=[
                    dict(id=p["id"], name=p["name"], status=p["status"])
                    for p in result["packages"]
                ],
                sharing_id=result["sharing"]["id"],
            )
            if args.apply:
                session.commit()
            else:
                session.rollback()
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps(report, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
