from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from presales.storage import ReviewEvent, ReviewIssue

from .review_schemas import ReviewInput


class ReviewConflict(Exception):
    pass


def event_view(event: ReviewEvent) -> dict:
    return {
        key: getattr(event, key)
        for key in ("id", "revision", "status", "actor", "note", "created_at")
    }


def issue_view(issue: ReviewIssue, events: list[ReviewEvent]) -> dict:
    history = [event_view(event) for event in events]
    review = history[0] if history else {"status": "pending", "revision": 0}
    return {
        "id": issue.id,
        "import_id": issue.import_id,
        **issue.payload,
        "review": review,
        "history": history,
    }


def applies_to_record(issue: dict, product: dict) -> bool:
    if not any(e["model"] == product["model"] for e in issue["evidence"]):
        return False
    if issue["kind"] != "missing_name":
        return True
    return any(
        e["sheet"] == product["sheet"] and e["range"] == product["sources"]["model"]
        for e in issue["evidence"]
    )


def review_summary(issues: list[dict]) -> dict:
    return {
        "total": len(issues),
        "pending": sum(i["review"]["status"] == "pending" for i in issues),
        "source_error": sum(i["review"]["status"] == "source_error" for i in issues),
    }


class ReviewIndex:
    def __init__(self, issues: list[dict]):
        self.by_model = defaultdict(list)
        for issue in issues:
            for model in {e["model"] for e in issue["evidence"]}:
                self.by_model[(issue["import_id"], model)].append(issue)

    def related(self, import_id: str, product: dict) -> list[dict]:
        return [
            i
            for i in self.by_model.get((import_id, product["model"]), [])
            if applies_to_record(i, product)
        ]


class ReviewRepository:
    def __init__(self, session: Session):
        self.session = session

    def for_imports(self, import_ids: set[str]) -> list[dict]:
        if not import_ids:
            return []
        issues = self.session.scalars(
            select(ReviewIssue).where(ReviewIssue.import_id.in_(import_ids))
        ).all()
        events = self.session.scalars(
            select(ReviewEvent)
            .join(ReviewIssue)
            .where(ReviewIssue.import_id.in_(import_ids))
            .order_by(ReviewEvent.revision.desc())
        )
        grouped = defaultdict(list)
        for event in events:
            grouped[event.issue_id].append(event)
        return [issue_view(issue, grouped[issue.id]) for issue in issues]

    def record(self, issue_id: str, data: ReviewInput) -> dict | None:
        # Lock the source issue so concurrent conclusions cannot overwrite one another.
        issue = self.session.scalar(
            select(ReviewIssue).where(ReviewIssue.id == issue_id).with_for_update()
        )
        if issue is None:
            return None
        history = list(
            self.session.scalars(
                select(ReviewEvent)
                .where(ReviewEvent.issue_id == issue_id)
                .order_by(ReviewEvent.revision.desc())
            )
        )
        revision = history[0].revision if history else 0
        if data.expected_revision != revision:
            raise ReviewConflict("该差异已有新的处理记录，请刷新后查看最新结论再保存。")
        event = ReviewEvent(
            issue_id=issue_id,
            revision=revision + 1,
            status=data.status,
            actor=data.actor,
            note=data.note,
        )
        self.session.add(event)
        self.session.commit()
        return issue_view(issue, [event, *history])
