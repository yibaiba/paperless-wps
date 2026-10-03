"""Injected ZEN execution. Invalid models and engine failures are explicit errors."""

import json
from decimal import Decimal, InvalidOperation

from presales.rules.calculation import digest

from .compiler import ENGINE_VERSION, compile_rules, expression_node


class ZenDecisions:
    def __init__(self, engine):
        self.engine = engine
        self.compiled = {}
        self.bundles = {}
        self.results = {}

    def request(self):
        service = ZenDecisions(self.engine)
        service.compiled = self.compiled
        service.bundles = self.bundles
        return service

    def bundle(self, rules):
        key = digest(rules)
        if key not in self.bundles:
            self.bundles[key] = compile_rules(rules)
        return self.bundles[key]

    def load(self, bundle):
        key = bundle["hash"]
        if digest({k: v for k, v in bundle.items() if k != "hash"}) != key:
            raise ValueError("ZEN 编译资料校验值不一致")
        if bundle["engine_version"] != ENGINE_VERSION:
            raise ValueError("ZEN 引擎版本与固定编译资料不一致")
        if key not in self.compiled:
            try:
                self.compiled[key] = self.engine.create_decision(json.dumps(bundle["graph"]))
            except Exception as error:
                raise ValueError("ZEN 知识编译失败，请检查条件和编译版本") from error
        return self.compiled[key]

    def evaluate_rules(self, rules, context):
        bundle = self.bundle(rules)
        values = {
            f"p{i}": input_value(b["condition"], context) for i, b in enumerate(bundle["bindings"])
        }
        try:
            result_key = digest([bundle["hash"], values])
            if result_key not in self.results:
                self.results[result_key] = self.load(bundle).evaluate(values)["result"]
            output = self.results[result_key]
        except Exception as error:
            raise ValueError("ZEN 知识执行失败，未产生有效检查结果") from error
        details = [
            evidence(rule, index=i, bundle=bundle, output=output, context=context)
            for i, rule in enumerate(rules)
        ]
        return dict(status=output["status"], evidence=details)

    def condition_result(self, conditions, context):
        # Empty conjunction is still evaluated by ZEN once, then reused in this request.
        key = ("empty_condition",)
        if not conditions and key in self.results:
            return self.results[key]
        rule = dict(
            id="conditions",
            revision=1,
            name="条件",
            evidence="",
            effect="allow",
            conditions=conditions,
        )
        result = self.evaluate_rules([rule], context)["evidence"][0]["result"]
        if not conditions:
            self.results[key] = result
        return result

    def check_condition(self, condition, context):
        return self.condition_result([condition], context)

    def capacity(self, *, required, capacity):
        if capacity is None:
            return "unknown"
        key = ("capacity", str(required), str(capacity))
        if key in self.results:
            return self.results[key]
        bundle = compile_rules([])
        node = expression_node(
            "capacity", {"status": 'number(capacity) >= number(required) ? "pass" : "conflict"'}
        )
        graph = bundle["graph"]
        graph["nodes"] = [graph["nodes"][0], node, graph["nodes"][-1]]
        graph["edges"] = [
            dict(id="in", sourceId="input", targetId="capacity", type="edge"),
            dict(id="out", sourceId="capacity", targetId="output", type="edge"),
        ]
        bundle["hash"] = digest({k: v for k, v in bundle.items() if k != "hash"})
        try:
            self.results[key] = self.load(bundle).evaluate(
                dict(required=str(required), capacity=str(capacity))
            )["result"]["status"]
            return self.results[key]
        except Exception as error:
            raise ValueError("ZEN 容量比较失败") from error


def finite(value):
    try:
        return Decimal(str(value)).is_finite()
    except (InvalidOperation, ValueError):
        return False


def input_value(condition, context):
    actual = context.get(condition["field"]) or {}
    value, expected = actual.get("value"), condition.get("value")
    numeric = actual.get("kind") in {"number", "quantity"}
    operator = condition["operator"]
    known = value is not None
    if operator == "range":
        known = known and finite(value)
    elif operator == "eq" and numeric:
        known = known and finite(value) and finite(expected)
    scalar = str(value) if value is not None else ""
    return dict(
        known=known,
        numeric=numeric,
        value=scalar,
        expected=expected if operator in {"any", "all"} else str(expected),
        values=value if isinstance(value, list) else [scalar],
        unit=actual.get("unit", ""),
        expectedUnit=condition.get("unit", ""),
        minimum=condition.get("minimum"),
        maximum=condition.get("maximum"),
    )


def evidence(rule, *, index, bundle, output, context):
    conditions = [
        dict(b["condition"], actual=context.get(b["condition"]["field"]), result=output[b["node"]])
        for b in bundle["bindings"]
        if b["rule_index"] == index and b["group"] == "conditions"
    ]
    return dict(
        id=rule["id"],
        revision=rule["revision"],
        name=rule["name"],
        effect=rule["effect"],
        evidence=rule["evidence"],
        conditions=conditions,
        activation=output[f"a{index}"],
        activation_conditions=rule.get("activation_conditions", []),
        alternative_group=rule.get("alternative_group", ""),
        result=output[f"r{index}"],
        evidence_refs=rule.get("evidence_refs", []),
    )
