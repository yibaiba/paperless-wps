import json
from decimal import Decimal

EXPRESSIONS = {
    "per_capacity": "ceil(number(quantity) / number(factor))",
    "per_unit": "number(quantity) * number(factor)",
    "per_group": "number(quantity) > 0 ? number(factor) : 0",
}


def decision_graph(expression: str) -> dict:
    return {
        "contentType": "application/vnd.gorules.decision",
        "nodes": [
            {"id": "input", "type": "inputNode", "name": "input", "position": {"x": 0, "y": 0}},
            {
                "id": "calculate",
                "type": "expressionNode",
                "name": "quantity",
                "position": {"x": 200, "y": 0},
                "content": {
                    "expressions": [{"id": "quantity", "key": "quantity", "value": expression}]
                },
            },
            {
                "id": "output",
                "type": "outputNode",
                "name": "output",
                "position": {"x": 400, "y": 0},
            },
        ],
        "edges": [
            {"id": "first", "sourceId": "input", "targetId": "calculate", "type": "edge"},
            {"id": "last", "sourceId": "calculate", "targetId": "output", "type": "edge"},
        ],
    }


class ZenQuantityEngine:
    def __init__(self, engine):
        self.decisions = {
            mode: engine.create_decision(json.dumps(decision_graph(expression)))
            for mode, expression in EXPRESSIONS.items()
        }

    def calculate(self, *, mode: str, quantity: str, factor: str) -> dict:
        response = self.decisions[mode].evaluate(
            {"quantity": quantity, "factor": factor}, {"trace": True}
        )
        result = Decimal(str(response["result"]["quantity"]))
        if not result.is_finite() or result < 0:
            raise ValueError("规则引擎返回了无效数量")
        return {
            "quantity": str(result),
            "engine": "GoRules ZEN 0.53.0",
            "expression": EXPRESSIONS[mode],
            "input": {"quantity": quantity, "factor": factor},
            "trace": response["trace"],
            "performance": response["performance"],
        }
