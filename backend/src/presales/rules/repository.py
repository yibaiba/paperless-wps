from sqlalchemy import select
from sqlalchemy.orm import Session

from presales.storage import ProductRecord, now

from .definition import source_ids, target_ids, with_defaults
from .models import AccessoryRule, RuleRevision
from .schemas import RuleInput, RuleUpdate
from .selector import SourceResolver


class RuleConflict(Exception):
    pass


def product_label(product: ProductRecord) -> dict:
    return {
        "id": product.id,
        "import_id": product.import_id,
        "model": product.model,
        "name": product.name,
        "sheet": product.sheet,
        "row": product.payload["row"],
        "unit": product.payload["unit"],
    }


class RuleRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[dict]:
        records = list(
            self.session.scalars(select(AccessoryRule).order_by(AccessoryRule.updated_at.desc()))
        )
        return self.views(records)

    def view(self, rule: AccessoryRule) -> dict:
        return self.views([rule])[0]

    def views(self, rules: list[AccessoryRule], *, lock_sources: bool = False) -> list[dict]:
        resolver = SourceResolver(
            self.session, payloads=[r.payload for r in rules], lock=lock_sources
        )
        payloads = [resolver.resolve(r.payload) for r in rules]
        products = self.labels(payloads)
        return [
            {
                "id": rule.id,
                "revision": rule.revision,
                "updated_at": rule.updated_at,
                **self.labeled(payload, products),
                "matching_errors": self.matching_errors(payload, products),
            }
            for rule, payload in zip(rules, payloads, strict=True)
        ]

    def labels(self, payloads: list[dict]) -> dict:
        product_ids = {
            product_id
            for payload in payloads
            for product_id in [*source_ids(payload), *target_ids(payload)]
        }
        return {
            p.id: product_label(p)
            for p in self.session.scalars(
                select(ProductRecord).where(ProductRecord.id.in_(product_ids))
            )
        }

    @staticmethod
    def labeled(payload: dict, products: dict) -> dict:
        return {
            **with_defaults(payload),
            "source": products[source_ids(payload)[0]] if source_ids(payload) else None,
            "target": products[payload["target_product_id"]],
            "sources": [products[p] for p in source_ids(payload)],
            "targets": [products[p] for p in target_ids(payload)],
        }

    def history(self, rule_id: str) -> list[dict] | None:
        if self.session.get(AccessoryRule, rule_id) is None:
            return None
        records = list(
            self.session.scalars(
                select(RuleRevision)
                .where(RuleRevision.rule_id == rule_id)
                .order_by(RuleRevision.revision.desc())
            )
        )
        products = self.labels([r.payload for r in records])
        return [
            {
                "revision": r.revision,
                "created_at": r.created_at,
                **self.labeled(r.payload, products),
                **(
                    {"sources": r.payload["source_snapshot"]}
                    if "source_snapshot" in r.payload
                    else {}
                ),
            }
            for r in records
        ]

    def validate_products(self, data: RuleInput):
        payload = data.model_dump(mode="json")
        resolver = SourceResolver(self.session, payloads=[payload], lock=True)
        self.validate_resolved(resolver.resolve(payload))

    def validate_resolved(self, payload: dict):
        labels = self.labels([payload])
        errors = self.matching_errors(payload, labels)
        if errors:
            raise ValueError("；".join(errors))

    @staticmethod
    def matching_errors(payload: dict, labels: dict) -> list[str]:
        ids = set(source_ids(payload) + target_ids(payload))
        if not ids <= set(labels):
            return ["选择的产品记录不存在，请重新选择"]
        errors = []
        if set(source_ids(payload)) & set(target_ids(payload)):
            errors.append("属性条件匹配到了配套产品自身，请收窄条件或将其列为例外")
        if len({labels[p]["unit"] for p in source_ids(payload)}) > 1:
            errors.append("合计的触发产品必须使用相同计量单位，请调整属性或条件")
        if len({labels[p]["unit"] for p in target_ids(payload)}) > 1:
            errors.append("候选配套产品必须使用相同计量单位")
        return errors

    def create(self, data: RuleInput, *, commit: bool = True) -> dict:
        self.validate_products(data)
        rule = AccessoryRule(revision=1, payload=data.model_dump(mode="json"))
        self.session.add(rule)
        self.session.flush()
        self.save_revision(rule, commit=commit)
        return self.view(rule)

    def update(self, rule_id: str, data: RuleUpdate) -> dict | None:
        rule = self.session.scalar(
            select(AccessoryRule).where(AccessoryRule.id == rule_id).with_for_update()
        )
        if rule is None:
            return None
        if rule.revision != data.expected_revision:
            raise RuleConflict("规则已有新版本，请刷新后重新编辑")
        self.validate_products(data)
        rule.payload = data.model_dump(mode="json", exclude={"expected_revision"})
        rule.revision += 1
        rule.updated_at = now()
        self.save_revision(rule)
        return self.view(rule)

    def resolved_revision(self, rule: AccessoryRule) -> dict:
        resolver = SourceResolver(self.session, payloads=[rule.payload])
        resolved = resolver.resolve(rule.payload)
        return {
            "resolved_source_ids": source_ids(resolved),
            "attribute_snapshot": resolved.get("attribute_snapshot", {}),
        }

    def save_revision(self, rule: AccessoryRule, *, commit: bool = True):
        self.session.add(
            RuleRevision(
                rule_id=rule.id,
                revision=rule.revision,
                payload={
                    **rule.payload,
                    "source_snapshot": self.view(rule)["sources"],
                    **self.resolved_revision(rule),
                },
            )
        )
        if commit:
            self.session.commit()
