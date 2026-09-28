from decimal import Decimal

from presales.rules.repository import RuleConflict
from presales.storage import identifier

from ..schemas import Configuration


class AccessoryApplication:
    def __init__(self, repository):
        self.repository = repository

    def apply(self, request):
        checked = self.repository.check(
            request.configuration,
            refresh=request.refresh_knowledge,
            upgrade=request.upgrade_calculation,
        )
        if checked["fingerprint"] != request.fingerprint:
            raise RuleConflict("配置已变化，请重新检查后应用配套")
        suggestion = next(
            (s for s in checked["suggestions"] if s["id"] == request.suggestion_id), None
        )
        if not suggestion or suggestion["status"] != "pass":
            raise ValueError("配套条件未通过或建议不存在")
        if data_version := checked["configuration"].get("calculation_version"):
            if data_version == 3 and not suggestion.get("selected"):
                raise ValueError("请先选用该推荐或可选需求，再检查并应用配套")
        if Decimal(suggestion["missing"]) <= 0:
            return checked
        data = checked["configuration"]
        amount = request.quantity or Decimal(suggestion["missing"])
        if amount > Decimal(suggestion["missing"]):
            raise ValueError("分配数量不能超过当前缺量")
        device_id = request.existing_device_id or identifier()
        if request.existing_device_id:
            if data.get("calculation_version", 1) < 2:
                raise ValueError("请先按最新计算方式重新检查，再关联已有设备")
            self._validate_existing_allocation(
                checked, suggestion=suggestion, device_id=device_id, amount=amount
            )
        else:
            self._append_suggested_device(data, suggestion, request, device_id, amount)
        if data.get("calculation_version") == 3 and not request.existing_device_id:
            data["supply_allocations"].append(
                dict(
                    id=identifier(),
                    device_id=device_id,
                    quantity=str(amount),
                    source=request.supply_source,
                    evidence=request.supply_evidence or "新增配套，供货来源尚待核对",
                )
            )
        data["accessory_allocations"].append(
            dict(
                id=identifier(),
                demand_id=suggestion["id"],
                device_id=device_id,
                quantity=str(amount),
                evidence="根据配套检查由售前确认分配",
            )
        )
        return self.repository.check(Configuration.model_validate(data))

    @staticmethod
    def _append_suggested_device(data, suggestion, request, device_id, amount):
        if request.variant_id not in suggestion["rule"]["target_variant_ids"]:
            raise ValueError("请选择建议范围内的配套配置")
        data["devices"].append(
            dict(
                id=device_id,
                name=suggestion["rule"].get("need_name") or suggestion["rule"]["name"],
                variant_id=request.variant_id,
                source_id=request.source_id,
                quantity=str(amount),
                kind=suggestion["rule"].get("output_kind", "accessory"),
                note="",
                variant_snapshot=None,
                source_snapshot=None,
                origin_suggestion=suggestion["id"],
            )
        )

    @staticmethod
    def _validate_existing_allocation(checked, *, suggestion, device_id, amount):
        data = checked["configuration"]
        device = next((item for item in data["devices"] if item["id"] == device_id), None)
        if not device or device["variant_id"] not in suggestion["rule"]["target_variant_ids"]:
            raise ValueError("已有设备不属于该配套需求的候选配置")
        allocations = data.get("accessory_allocations", [])
        demand_rules = {item["id"]: item["rule"] for item in checked["suggestions"]}
        used = sum(
            (
                Decimal(item["quantity"])
                for item in allocations
                if item["device_id"] == device_id
                and demand_rules.get(item["demand_id"], {}).get("allocation_mode", "consumable")
                == "consumable"
            ),
            Decimal(0),
        )
        if suggestion["rule"].get("allocation_mode", "consumable") == "consumable":
            if used + amount > Decimal(device["quantity"]):
                raise ValueError("已有设备的可分配数量不足")
        elif amount > Decimal(device["quantity"]):
            raise ValueError("共享设备的单次分配数量超过设备数量")
