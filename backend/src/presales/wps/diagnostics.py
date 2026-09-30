from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from presales.storage import now

from .models import WpsDiagnosticEvent

DIAGNOSTIC_RETENTION_DAYS = 30


class WpsDiagnostics:
    def __init__(self, session):
        self.session = session

    def record(self, batch):
        purged = self.purge_expired()
        existing = set(
            self.session.scalars(
                select(WpsDiagnosticEvent.event_id).where(
                    WpsDiagnosticEvent.event_id.in_([event.event_id for event in batch.events])
                )
            )
        )
        accepted = 0
        for event in batch.events:
            if event.event_id in existing:
                continue
            accepted += int(self._insert(event))
        return {
            "accepted": accepted,
            "duplicates": len(batch.events) - accepted,
            "purged": purged,
        }

    def purge_expired(self):
        cutoff = now() - timedelta(days=DIAGNOSTIC_RETENTION_DAYS)
        result = self.session.execute(
            delete(WpsDiagnosticEvent).where(WpsDiagnosticEvent.received_at < cutoff)
        )
        return result.rowcount or 0

    def _insert(self, event):
        record = WpsDiagnosticEvent(**event.model_dump(mode="python"))
        try:
            with self.session.begin_nested():
                self.session.add(record)
                self.session.flush()
            return True
        except IntegrityError:
            return False
