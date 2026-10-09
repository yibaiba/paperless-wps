from copy import deepcopy

from presales.application.idempotency import once
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities, view
from presales.configuration.models import SourceLink
from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict

from .differences import build_rows
from .hashing import configuration_hash
from .impacts import affected
from .prices import Prices
from .products import apply_product, stable_id
from .schemas import Decision


class Batches:
    def __init__(self, session):
        self.session, self.entities = session, Entities(session)

    def create(self, request):
        def perform():
            rows = build_rows(self.session, request)
            if not rows:
                raise ValueError("选定范围没有可以处理的产品来源或配置")
            return self.entities.save(
                "catalog_update", dict(**request.model_dump(mode="json"), rows=rows)
            )

        return once(
            self.session, namespace="catalog-update-create", request=request, perform=perform
        )

    def get(self, identity):
        return view(self.entities.get(identity, kind="catalog_update"))

    def edit(self, identity, request):
        def perform():
            current = self.get(identity)
            rows = deepcopy(current["rows"])
            edits = {e.row_id: e for e in request.edits}
            if len(edits) != len(request.edits) or edits.keys() - {r["id"] for r in rows}:
                raise ValueError("修改行重复或不在此更新批次中")
            for row in rows:
                if row["id"] not in edits:
                    continue
                if row["state"] == "applied":
                    raise ValueError("已发布行不能重写，请创建新批次更正")
                row["decision"] = edits[row["id"]].decision.model_dump(mode="json")
            return self.entities.save(
                "catalog_update",
                {**self.payload(current), "rows": rows},
                entity_id=identity,
                expected_revision=request.expected_revision,
            )

        return once(
            self.session,
            namespace=f"catalog-update-edit:{identity}",
            request=request,
            perform=perform,
        )

    def preview(self, identity, request):
        batch = self.get(identity)
        if batch["revision"] != request.expected_revision:
            raise RuleConflict("更新草稿已有新修订，请重新载入")
        selected = set(request.row_ids)
        if len(selected) != len(request.row_ids) or selected - {r["id"] for r in batch["rows"]}:
            raise ValueError("选择的行重复或不在批次中")
        changes = [
            self.prepare(row, batch_id=identity) for row in batch["rows"] if row["id"] in selected
        ]
        slots = [p["id"] for c in changes for p in c["prices"]]
        if len(slots) != len(set(slots)):
            raise ValueError("多行修改同一配置同日价格，请核对重复来源后分别处理")
        return dict(changes=changes, fingerprint=digest([identity, batch["revision"], changes]))

    def prepare(self, row, *, batch_id):
        if row["state"] == "applied" or row["decision"] is None:
            raise ValueError("所选行已发布或尚未填写处理结论")
        decision = Decision.model_validate(row["decision"])
        variant = None
        if decision.variant_id:
            values = CatalogService(self.session).variants(ids=[decision.variant_id])
            if not values:
                raise ValueError("选择的配置不存在")
            variant = values[0]
            if variant["revision"] != decision.expected_variant_revision:
                raise RuleConflict("配置已有新修订，请重新核对本行")
        if decision.action not in {"new_variant", "new_product", "defer"} and not variant:
            raise ValueError("必须明确选择配置，不能仅按型号确认")
        if (
            decision.action in {"display", "correct", "new_variant", "new_product"}
            and not decision.variant
        ):
            raise ValueError("请填写修改后或新增的配置资料")
        if decision.action == "new_product" and not decision.product:
            raise ValueError("请填写新产品身份")
        if decision.action == "defer" and any(
            p.state not in {"keep", "skip"} for p in decision.prices
        ):
            raise ValueError("待核对行不能同时发布价格")
        target = (
            stable_id(batch_id, row["id"], "variant")
            if decision.action in {"new_variant", "new_product"}
            else decision.variant_id
        )
        from .prices import price_id

        prices = []
        for change in decision.prices:
            if change.state in {"keep", "skip"}:
                continue
            previous = Prices(self.session).slot(target, change)
            prices.append(
                dict(
                    id=price_id(target, change.column, change.effective_date),
                    before=previous,
                    expected_revision=previous["revision"] if previous else 0,
                    after=change.model_dump(mode="json"),
                )
            )
        link = self.session.get(SourceLink, row["source"]["id"]) if row.get("source") else None
        return dict(
            row_id=row["id"],
            variant_id=target,
            variant=variant,
            decision=row["decision"],
            source=row.get("source"),
            source_link_revision=link.revision if link else 0,
            prices=prices,
            pending_prices=[p.column for p in decision.prices if p.state == "keep"],
            impact=affected(self.session, variant) if variant else None,
            copied_rules=[
                dict(id=identity, revision=self.entities.get(identity, kind="knowledge").revision)
                for identity in decision.copy_rule_ids
            ],
        )

    def apply(self, identity, request):
        def perform():
            preview = self.preview(identity, request)
            if preview["fingerprint"] != request.fingerprint:
                raise RuleConflict("预览内容已有变化，请重新核对；本批未发布")
            batch = self.get(identity)
            rows = deepcopy(batch["rows"])
            by_id = {r["id"]: r for r in rows}
            for change in sorted(preview["changes"], key=lambda c: c["row_id"]):
                row = by_id[change["row_id"]]
                decision = Decision.model_validate(row["decision"])
                variant = apply_product(self.session, row=row, decision=decision, batch_id=identity)
                if variant:
                    self.publish_prices(change, variant=variant, decision=decision)
                row.update(
                    state=(
                        "deferred"
                        if decision.action == "defer"
                        or (decision.action == "prices" and not change["prices"])
                        else "partial"
                        if change["pending_prices"]
                        else "applied"
                    ),
                    result_variant_id=variant["id"] if variant else None,
                    pending_prices=change["pending_prices"],
                    published_prices=[*row.get("published_prices", []), *change["prices"]],
                )
                if variant and change["pending_prices"]:
                    row["decision"] = dict(
                        action="prices",
                        variant_id=variant["id"],
                        expected_variant_revision=variant["revision"],
                        actor=decision.actor,
                        evidence=decision.evidence,
                        prices=[
                            p.model_dump(mode="json") for p in decision.prices if p.state == "keep"
                        ],
                    )
            return self.entities.save(
                "catalog_update",
                {**self.payload(batch), "rows": rows},
                entity_id=identity,
                expected_revision=request.expected_revision,
            )

        return once(
            self.session,
            namespace=f"catalog-update-apply:{identity}",
            request=request,
            perform=perform,
        )

    def publish_prices(self, change, *, variant, decision):
        for price in change["prices"]:
            Prices(self.session).publish(
                dict(
                    **price["after"],
                    variant_id=variant["id"],
                    variant_revision=variant["revision"],
                    configuration_hash=configuration_hash(variant),
                    source_id=(change["source"] or {}).get("id"),
                    source_cells=(change["source"] or {}).get("sources", {}),
                    actor=decision.actor,
                    evidence=decision.evidence,
                ),
                expected_revision=price["expected_revision"],
            )

    @staticmethod
    def payload(batch):
        return {k: v for k, v in batch.items() if k not in {"id", "revision", "updated_at"}}
