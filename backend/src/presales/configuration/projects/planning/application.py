from copy import deepcopy

from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict

from ..drawing import project_drawing, remove_device_references
from ..schemas import Configuration
from .pricing import validate_new_prices


def verify_draft_proposal(repository, *, draft, operation):
    proposal = repository.entities.get(operation.proposal_id, kind="list_proposal").payload
    if (proposal["draft_id"], proposal["draft_revision"]) != (draft.id, draft.revision):
        raise RuleConflict("PROPOSAL_STALE：提案与当前草稿修订不一致，请重新生成")


def apply_proposal(configuration, operation, *, repository):
    proposal = repository.entities.get(operation.proposal_id, kind="list_proposal").payload
    if operation.fingerprint != proposal["fingerprint"] or digest(configuration) != digest(
        proposal["baseline"]
    ):
        raise RuleConflict("PROPOSAL_STALE：需求或提案指纹已变化，请重新生成")
    option = next((o for o in proposal["options"] if o["id"] == operation.option_id), None)
    if not option:
        raise ValueError("所选方案不属于此提案")
    removed = set(operation.remove_device_ids)
    if removed - set(option["removal_candidates"]):
        raise ValueError("仅能明确移除本提案列出的多余生成设备")
    data = deepcopy(option["configuration"])
    existing = {a["device_id"] for a in data["supply_allocations"] if a["source"] == "existing"}
    locked = {
        d["id"]
        for d in data["devices"]
        if not d.get("generated_origin")
        or d["generated_origin"]["variant_locked"]
        or d["generated_origin"]["quantity_locked"]
    }
    if removed & (existing | locked):
        raise ValueError("客户已有或人工锁定设备不能通过自动生成移除，请明确改单")
    for collection in (
        "devices",
        "supply_allocations",
        "accessory_allocations",
        "included_allocations",
    ):
        key = "id" if collection == "devices" else "device_id"
        data[collection] = [item for item in data[collection] if item[key] not in removed]
    for identity in removed:
        data["drawing_xml"] = remove_device_references(data["drawing_xml"], identity)
    if data.get("quotation"):
        data["quotation"]["prices"] = [
            price for price in data["quotation"]["prices"] if price["device_id"] not in removed
        ]
    validate_new_prices(repository.session, before=configuration, proposed=data)
    old_ids = {d["id"] for d in configuration["devices"]}
    data["drawing_xml"] = project_drawing(
        data["drawing_xml"],
        devices=data["devices"],
        add_ids=[d["id"] for d in data["devices"] if d["id"] not in old_ids],
    )
    return Configuration.model_validate(data).model_dump(mode="json")


def validate_proposal_batch(repository, draft, operations):
    proposals = [op for op in operations if op.action == "proposal_apply"]
    if proposals and len(operations) != 1:
        raise ValueError("整批采用提案必须单独提交，后续编辑使用新草稿修订")
    for operation in proposals:
        verify_draft_proposal(repository, draft=draft, operation=operation)
