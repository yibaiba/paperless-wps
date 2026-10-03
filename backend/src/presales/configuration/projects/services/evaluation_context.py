"""Resolve one fixed set of business and compiled revisions for a calculation."""

from dataclasses import dataclass

from .definition_snapshot import project_knowledge, resolve_definitions


@dataclass(frozen=True, kw_only=True)
class EvaluationContext:
    configuration: dict
    data: dict
    variants: dict
    catalog: dict
    definitions: dict
    decisions: object
    metadata: dict


def prepare_evaluation(repository, payload, *, variants, catalog, refresh=False):
    definitions, identity = resolve_definitions(repository.session, payload, refresh=refresh)
    configuration = dict(payload, definition_snapshot_id=identity)
    data = dict(configuration, knowledge_snapshot=project_knowledge(configuration, definitions))
    decisions, metadata = repository.resolve_decisions(data, refresh=refresh)
    configuration["decision_bundle_id"] = data.get("decision_bundle_id")
    return EvaluationContext(
        configuration=configuration,
        data=data,
        variants=variants,
        catalog=catalog,
        definitions=definitions,
        decisions=decisions,
        metadata=metadata,
    )
