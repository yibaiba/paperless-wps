from uuid import NAMESPACE_URL, uuid5

from presales.rules.repository import RuleConflict
from presales.storage import Project
from sqlalchemy import select

from ...common import Entities, view
from ...definitions.service import Definitions
from ...models import Entity
from ..projections.comparison import configuration_diff
from .confirmation_inputs import saved_input_checks


class ProjectLifecycle:
    def __init__(self, session, repository):
        self.session, self.repository = session, repository
        self.entities = Entities(session)

    def confirm(self, project_id, data):
        self.session.scalar(select(Project).where(Project.id == project_id).with_for_update())
        record = self.repository.record(project_id)
        if not record or record.revision != data.expected_revision:
            raise RuleConflict("项目版本已变化，请重新载入后确认")
        checked = record.payload
        if checked["fingerprint"] != data.fingerprint:
            raise RuleConflict("检查结果与保存版本不一致")
        identity = confirmation_id(project_id, record.revision)
        previous = self.session.get(Entity, identity)
        if previous:
            return view(previous)
        from ..calculation.customer_constraints import budget_checks, product_constraints
        from ..calculation.interpretations import interpretation_checks

        # Old saved checks may predate customer constraints; use their frozen
        # configuration and prices, without rewriting the saved revision.
        constraints = [
            *product_constraints(checked["configuration"]),
            *budget_checks(checked["configuration"], checked),
            *interpretation_checks(checked["configuration"]),
            *saved_input_checks(checked["configuration"], entities=self.entities),
        ]
        if not checked["readiness"].get("ready_for_confirmation") or any(
            c["status"] != "pass" for c in constraints
        ):
            raise ValueError("本版本仍有冲突或待确认事项，已保留草稿")
        return self.entities.save(
            "project_confirmation",
            dict(
                project_id=project_id,
                project_revision=record.revision,
                fingerprint=data.fingerprint,
                actor=data.actor,
                evidence=data.evidence,
            ),
            create_id=identity,
        )

    def confirmation(self, project_id, revision):
        record = self.session.get(Entity, confirmation_id(project_id, revision))
        return view(record) if record else None

    def compare(self, project_id, *, base_revision, target_revision):
        record = self.repository.record(project_id)
        if not record:
            raise ValueError("项目还没有保存版本")
        history = Definitions(self.session)
        before = history.revision(record.id, base_revision, kind="project")
        after = history.revision(record.id, target_revision, kind="project")
        return dict(
            base_revision=base_revision,
            target_revision=target_revision,
            changes=configuration_diff(before["configuration"], after["configuration"]),
            procurement_changes=procurement_diff(before, after),
            before_checks=before["checks"],
            after_checks=after["checks"],
        )


def confirmation_id(project_id, revision):
    return str(uuid5(NAMESPACE_URL, f"presales-project-confirmation:{project_id}:{revision}"))


def procurement_diff(before, after):
    from ..projections.comparison import collection_diff

    def lines(value):
        return [
            dict(line, id=line["device_id"])
            for line in value.get("project_output", {}).get("procurement_lines", [])
        ]

    old, new = lines(before), lines(after)
    changes = collection_diff(
        "procurement",
        [procurement_value(line) for line in old],
        [procurement_value(line) for line in new],
    )
    old_by_id, new_by_id = {line["id"]: line for line in old}, {line["id"]: line for line in new}
    return [dict(c, before=old_by_id.get(c["id"]), after=new_by_id.get(c["id"])) for c in changes]


def procurement_value(line):
    # Usage diagnostics have their own diff; adding trace fields is not a purchase change.
    ignored = {"group_ids", "allocated_quantity", "fulfilled_by_demand_ids"}
    consumers = [
        {key: value for key, value in consumer.items() if key not in ignored}
        for consumer in line.get("consumers", [])
    ]
    return dict(
        {key: value for key, value in line.items() if key not in {"quantity_summary", "consumers"}},
        consumers=sorted(
            consumers,
            key=lambda c: (c["requirement_id"], c["via"], c.get("demand_id") or ""),
        ),
    )
