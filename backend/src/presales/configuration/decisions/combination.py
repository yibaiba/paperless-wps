"""Controlled combination programs; the caller supplies resolved business need states."""

from presales.rules.calculation import digest
from presales.rules.engine import decision_graph

from .compiler import COMPILER_VERSION, ENGINE_VERSION

EXPRESSIONS = {
    "exclude": (
        'contains(present, true) ? "conflict" : contains(states, "unknown") ? "unknown" : "pass"'
    ),
    "require_all": (
        'contains(states, "fail") ? "conflict" : '
        'contains(states, "unknown") or len(states) == 0 ? "unknown" : "pass"'
    ),
    "require_any": (
        'contains(states, "pass") ? "pass" : '
        'contains(states, "unknown") or len(states) == 0 ? "unknown" : "conflict"'
    ),
}


def combination_bundle(mode):
    if mode not in EXPRESSIONS:
        raise ValueError("不支持的组合规则类型")
    graph = decision_graph(EXPRESSIONS[mode])
    expression = graph["nodes"][1]["content"]["expressions"][0]
    expression.update(id="status", key="status")
    payload = dict(
        compiler_version=COMPILER_VERSION, engine_version=ENGINE_VERSION, graph=graph, mode=mode
    )
    return dict(payload, hash=digest(payload))


def combination_result(decisions, *, mode, groups):
    program = combination_bundle(mode)
    try:
        response = decisions.load(program).evaluate(
            dict(states=[g["state"] for g in groups], present=[g["present"] for g in groups])
        )
        return response["result"]["status"]
    except Exception as error:
        raise ValueError("ZEN 组合判断失败，未产生有效检查结果") from error
