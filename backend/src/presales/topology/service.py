from sqlalchemy import select

from presales.rules.repository import RuleConflict, RuleRepository
from presales.rules.schemas import RuleInput

from .models import TopologyRule
from .repository import TopologyRepository
from .schemas import ConvertInput, TopologyInput


def rule_from_relation(topology: dict, *, relation_id: str, actor: str):
    data = TopologyInput.model_validate({key: topology[key] for key in TopologyInput.model_fields})
    relation = next((r for r in data.relations if r.id == relation_id), None)
    if relation is None:
        raise ValueError("关系不存在，请重新打开拓扑")
    if relation.kind != "required":
        raise ValueError("只有必配关系可生成数量规则，可选和接线关系只作方案记录")
    if not relation.evidence:
        raise ValueError("请先填写必配关系的依据并保存拓扑")
    devices = {d.id: d for d in data.devices}
    source, target = devices[relation.source], devices[relation.target]
    if source.group_id != target.group_id or source.serves_group_ids or target.serves_group_ids:
        raise ValueError("跨系统或共享设备关系不能直接转为同组数量规则，请在配套规则中维护共享条件")
    return RuleInput(
        name=f"{data.name}：{topology['products'][source.product_id]['model']} 必配 "
        f"{topology['products'][target.product_id]['model']}",
        source_product_id=source.product_id,
        target_product_id=target.product_id,
        relation="required",
        mode=relation.mode,
        factor=relation.factor,
        actor=actor,
        status="draft",
        evidence=f"来自拓扑 {topology['id']} v{topology['revision']}，关系 {relation.id}。"
        f"原依据：{relation.evidence}。此草稿按项目同组计算，不限定于原拓扑，启用前确认适用范围。",
    )


class TopologyRules:
    def __init__(self, session):
        self.session = session
        self.topologies = TopologyRepository(session)

    def convert(self, topology_id: str, *, relation_id: str, data: ConvertInput):
        record = self.topologies.locked(topology_id, expected_revision=data.expected_revision)
        if record is None:
            return None
        linked = self.session.scalar(
            select(TopologyRule).where(
                TopologyRule.topology_id == topology_id,
                TopologyRule.relation_id == relation_id,
            )
        )
        if linked:
            raise RuleConflict("此关系已生成草稿，请到配套规则查看或修改，避免重复参与计算")
        definition = rule_from_relation(
            self.topologies.view(record),
            relation_id=relation_id,
            actor=data.actor,
        )
        rule = RuleRepository(self.session).create(definition, commit=False)
        self.session.add(
            TopologyRule(
                topology_id=record.id,
                topology_revision=record.revision,
                relation_id=relation_id,
                rule_id=rule["id"],
            )
        )
        self.session.commit()
        return rule
