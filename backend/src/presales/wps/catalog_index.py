from dataclasses import dataclass
from threading import RLock

from sqlalchemy import func, select

from presales.configuration.catalog.service import CatalogService
from presales.configuration.models import Entity, SourceLink
from presales.storage import CatalogImport, ProductRecord

from .catalog_sequences import build_catalog_transitions


@dataclass(frozen=True)
class CatalogSuggestionSnapshot:
    variants: tuple[dict, ...]
    transitions: dict


class CatalogSuggestionIndex:
    def __init__(self):
        self._lock = RLock()
        self._fingerprint = None
        self._variants: tuple[dict, ...] = ()
        self._transitions: dict[tuple[str, str] | None, dict] = {}

    def snapshot(self, session, catalog_scope=None):
        fingerprint = self._version_fingerprint(session)
        scope_key = self._scope_key(catalog_scope)
        with self._lock:
            if fingerprint != self._fingerprint:
                self._variants = tuple(CatalogService(session).variants())
                self._transitions = {}
                self._fingerprint = fingerprint
            if scope_key not in self._transitions:
                self._transitions[scope_key] = build_catalog_transitions(
                    self._variants, catalog_scope
                )
            return CatalogSuggestionSnapshot(
                variants=self._variants,
                transitions=self._transitions[scope_key],
            )

    @staticmethod
    def _scope_key(catalog_scope):
        if not catalog_scope:
            return None
        return catalog_scope["import_id"], catalog_scope["sheet"]

    @staticmethod
    def _version_fingerprint(session):
        entity_version = session.execute(
            select(func.count(Entity.id), func.max(Entity.updated_at)).where(
                Entity.kind.in_(["product", "variant"])
            )
        ).one()
        link_version = session.execute(
            select(
                func.count(SourceLink.source_id),
                func.coalesce(func.sum(SourceLink.revision), 0),
            )
        ).one()
        source_version = session.execute(
            select(
                func.count(ProductRecord.id),
                func.count(CatalogImport.id),
                func.max(CatalogImport.created_at),
            ).select_from(ProductRecord).join(CatalogImport)
        ).one()
        return (*entity_version, *link_version, *source_version)
