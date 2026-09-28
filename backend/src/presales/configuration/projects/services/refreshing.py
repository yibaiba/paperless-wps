from presales.rules.repository import RuleConflict

from ..schemas import Configuration


def refresh_knowledge(data, operation, *, repository):
    result = repository.check(
        Configuration.model_validate(data), refresh=True, upgrade=operation.upgrade
    )["configuration"]
    for name in ("knowledge_snapshot_id", "definition_snapshot_id"):
        expected = getattr(operation, "expected_" + name)
        if expected and result[name] != expected:
            raise RuleConflict("资料在预览后再次变化，请重新预览再应用")
    for device in result["devices"]:
        expected = operation.expected_variant_revisions.get(device["variant_id"])
        if expected and device["variant_snapshot"]["revision"] != expected:
            raise RuleConflict("产品在预览后再次变化，请重新预览再应用")
        product = device['variant_snapshot']['product']
        expected_product = operation.expected_product_revisions.get(product['id'])
        if expected_product and product['revision'] != expected_product:
            raise RuleConflict('产品身份资料在预览后再次变化，请重新预览再应用')
    return result
