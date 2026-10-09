from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.exc import IntegrityError

from presales.application.hashing import digest
from presales.application.models import Entity
from presales.application.revisions import Entities

from .service import CatalogService


def capture_catalog(session):
    payload = {"variants": CatalogService(session).variants()}
    identity = str(uuid5(NAMESPACE_URL, "presales-list-catalog:" + digest(payload)))
    if session.get(Entity, identity) is None:
        _create_snapshot(session, identity, payload)
    return identity


def _create_snapshot(session, identity, payload):
    try:
        with session.begin_nested():
            session.add(Entity(id=identity, kind="list_catalog_snapshot", payload=payload))
            session.flush()
    except IntegrityError:
        existing = session.get(Entity, identity)
        if existing is None or existing.payload != payload:
            raise


class DraftCatalog:
    def __init__(self, session, snapshot_id):
        self.session = session
        self.snapshot_id = snapshot_id
        self._data = None

    def variants(self, *, ids=None):
        if self._data is None:
            self._data = Entities(self.session).get(
                self.snapshot_id, kind="list_catalog_snapshot"
            ).payload
        return deepcopy([v for v in self._data["variants"] if ids is None or v["id"] in ids])


def edit_catalog_snapshot(session, payload, operations):
    if any(operation.action == "knowledge_refresh" for operation in operations):
        return capture_catalog(session)
    return payload["catalog_snapshot_id"]
