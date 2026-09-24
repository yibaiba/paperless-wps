from dataclasses import asdict

from sqlalchemy import select

from presales.storage import CatalogImport, ProductRecord, ReviewIssue

from .checks import detect_issues
from .models import SourceProduct


def issue_key(payload: dict) -> tuple:
    evidence = payload["evidence"]
    records = tuple(sorted({(e["sheet"], e["range"]) for e in evidence}))
    return (
        payload["kind"],
        tuple(sorted({e["model"] for e in evidence})),
        records if payload["kind"] == "missing_name" else (),
    )


def recheck_import(session, import_id: str) -> dict | None:
    record = session.scalar(
        select(CatalogImport).where(CatalogImport.id == import_id).with_for_update()
    )
    if record is None:
        return None
    products = session.scalars(select(ProductRecord).where(ProductRecord.import_id == import_id))
    issues = session.scalars(select(ReviewIssue).where(ReviewIssue.import_id == import_id)).all()
    keys = {issue_key(issue.payload) for issue in issues}
    detected = detect_issues([SourceProduct(**p.payload) for p in products])
    new = [asdict(issue) for issue in detected if issue_key(asdict(issue)) not in keys]
    session.add_all([ReviewIssue(import_id=import_id, payload=payload) for payload in new])
    record.issue_count = len(issues) + len(new)
    session.commit()
    return {"added": len(new), "total": record.issue_count}
