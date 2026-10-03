"""Combination targets refer to business needs; they do not invent quantities."""

from typing import Literal

from pydantic import Field, model_validator

from ..common import Input, Text


class CombinationTarget(Input):
    id: Text
    name: Text
    system_definition_id: str = ""
    role_id: str = ""
    need_key: str = ""
    variant_ids: list[str] = Field(default_factory=list)


class Combination(Input):
    mode: Literal["exclude", "require_all", "require_any"]
    scope: Literal["system", "room", "project"] | None = None
    targets: list[CombinationTarget] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_targets(self):
        if len({t.id for t in self.targets}) != len(self.targets):
            raise ValueError("组合需求项标识不能重复")
        return self


def missing_combination(value):
    item = value.get("combination") or {}
    missing = []
    if not item.get("scope"):
        missing.append("combination.scope")
    if not item.get("targets"):
        missing.append("combination.targets")
    for target in item.get("targets", []):
        if not target.get("role_id") and not target.get("need_key"):
            missing.append("combination.targets." + target["id"] + ".need")
    return missing


def require_combination_runtime(rules, *, enabled):
    if not enabled and any(r["kind"] == "combination" and r["status"] != "disabled" for r in rules):
        raise ValueError("组合知识需要 ZEN 决策，请先预览运行时升级")
