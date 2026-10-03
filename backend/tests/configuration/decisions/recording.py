"""Test observer: delegate compilation and every successful evaluation to real ZEN."""

import json
from copy import deepcopy

import zen


class RecordingEngine:
    def __init__(self):
        self.engine = zen.ZenEngine()
        self.events = []
        self.fail_kind = None

    def create_decision(self, graph):
        nodes = json.loads(graph)["nodes"]
        identities = {node["id"] for node in nodes}
        kind = "predicates"
        if "capacity" in identities:
            kind = "capacity"
        elif "calculate" in identities:
            expression = next(n for n in nodes if n["id"] == "calculate")["content"]
            kind = (
                "quantity" if expression["expressions"][0]["key"] == "quantity" else "combination"
            )
        return RecordingDecision(self, kind=kind, decision=self.engine.create_decision(graph))


class RecordingDecision:
    def __init__(self, observer, *, kind, decision):
        self.observer = observer
        self.kind = kind
        self.decision = decision

    def evaluate(self, values, *args):
        if self.observer.fail_kind == self.kind:
            raise RuntimeError("隔离测试注入引擎执行故障")
        result = self.decision.evaluate(values, *args)
        self.observer.events.append(
            dict(kind=self.kind, input=deepcopy(values), result=deepcopy(result["result"]))
        )
        return result
