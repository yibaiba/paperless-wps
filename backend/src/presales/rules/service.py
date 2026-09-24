from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from presales.storage import ProductRecord, Project, ProjectItem

from .calculation import choice_checks, digest, suggestions
from .definition import source_ids
from .models import AccessoryRule, RuleApplication
from .repository import RuleConflict, RuleRepository
from .review_context import pending_relations, source_concerns
from .schemas import ApplyInput


class ProjectRules:
    def __init__(self, session: Session, engine):
        self.session = session
        self.engine = engine

    def preview(self, project_id: str, *, lock: bool = False) -> dict | None:
        from presales.configuration.projects.repository import ProjectConfigurations

        if ProjectConfigurations(self.session, self.engine).record(project_id):
            raise ValueError("该项目已使用统一配置，请在“需求选配与拓扑”中检查和应用配套")
        project_query = select(Project).where(Project.id == project_id)
        project = self.session.scalar(project_query.with_for_update() if lock else project_query)
        if project is None:
            return None
        records = list(
            self.session.scalars(
                select(ProjectItem)
                .where(ProjectItem.project_id == project_id)
                .order_by(ProjectItem.id)
            )
        )
        items = [
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "group_name": item.group_name,
                "model": item.snapshot["model"],
            }
            for item in records
        ]
        rule_query = select(AccessoryRule).order_by(AccessoryRule.id)
        rule_records = self.session.scalars(rule_query.with_for_update() if lock else rule_query)
        repo = RuleRepository(self.session)
        all_rules = repo.views(list(rule_records), lock_sources=lock)
        rules = [rule for rule in all_rules if rule["status"] == "active"]
        present = {item["product_id"] for item in items}
        for rule in rules:
            if rule["matching_errors"] and present.intersection(source_ids(rule)):
                raise ValueError(
                    f"规则「{rule['name']}」无法计算：" + "；".join(rule["matching_errors"])
                )
        rule_inputs = [{k: v for k, v in rule.items() if k != "updated_at"} for rule in rules]
        fingerprint = digest({"project": project_id, "items": items, "rules": rule_inputs})
        covered = {product_id for rule in rules for product_id in source_ids(rule)}
        return {
            "project_id": project_id,
            "fingerprint": fingerprint,
            "engine": "GoRules ZEN 0.53.0",
            "active_rule_count": len(rules),
            "uncovered_items": [item for item in items if item["product_id"] not in covered],
            "suggestions": suggestions(items=items, rules=rules, engine=self.engine),
            "choice_checks": choice_checks(items=items, rules=rules, engine=self.engine),
            "pending_relations": pending_relations(all_rules, items),
            "source_concerns": source_concerns(self.session, records=records, rules=rules),
        }

    def apply(self, project_id: str, data: ApplyInput) -> dict | None:
        preview = self.preview(project_id, lock=True)
        if preview is None:
            return None
        if preview["fingerprint"] != data.fingerprint:
            raise RuleConflict("清单或规则已变化，请重新计算后再应用")
        chosen = self.select_suggestions(preview, data.suggestion_ids)
        items = [self.create_item(project_id, suggestion) for suggestion in chosen]
        self.session.add_all(items)
        self.session.flush()
        application = RuleApplication(
            project_id=project_id,
            calculation={**preview, "suggestions": chosen},
            item_ids=[item.id for item in items],
        )
        self.session.add(application)
        self.session.commit()
        return {
            "id": application.id,
            "item_ids": application.item_ids,
            "created_at": application.created_at,
        }

    @staticmethod
    def select_suggestions(preview: dict, selected: list[str]) -> list[dict]:
        if len(set(selected)) != len(selected):
            raise ValueError("不能重复选择同一建议")
        choices = {s["id"]: s for s in preview["suggestions"]}
        if any(key not in choices for key in selected):
            raise ValueError("所选建议不存在，请重新计算")
        chosen = [choices[key] for key in selected]
        if any(Decimal(s["missing"]) <= 0 for s in chosen):
            raise ValueError("所选配套数量已满足，无需重复补入")
        return chosen

    def create_item(self, project_id: str, suggestion: dict) -> ProjectItem:
        target = self.session.get(ProductRecord, suggestion["target"]["id"])
        names = "、".join(f"{r['name']} v{r['revision']}" for r in suggestion["rules"])
        return ProjectItem(
            project_id=project_id,
            product_id=target.id,
            quantity=suggestion["missing"],
            group_name=suggestion["group_name"],
            note=f"规则补足：{names}；需求 {suggestion['required']}，原有 {suggestion['existing']}",
            snapshot={**target.payload, "import_id": target.import_id},
        )

    def history(self, project_id: str) -> list[dict] | None:
        if self.session.get(Project, project_id) is None:
            return None
        records = self.session.scalars(
            select(RuleApplication)
            .where(RuleApplication.project_id == project_id)
            .order_by(RuleApplication.created_at.desc())
        )
        return [
            {
                "id": r.id,
                "created_at": r.created_at,
                "item_ids": r.item_ids,
                "calculation": r.calculation,
            }
            for r in records
        ]
