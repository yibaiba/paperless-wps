from copy import deepcopy
from itertools import product

import pytest
import zen

from presales.configuration.decisions.compiler import compile_rules
from presales.configuration.decisions.runtime import ZenDecisions
from presales.configuration.knowledge.evaluator import check_condition
from presales.configuration.knowledge.semantics import evaluate_rules_v3


@pytest.fixture
def decisions():
    return ZenDecisions(zen.ZenEngine())


def condition(**patch):
    return dict(
        field="product.memory",
        operator="eq",
        value="32",
        unit="GB",
        minimum=None,
        maximum=None,
        **patch,
    )


def rule(identity="one", **patch):
    return dict(
        id=identity,
        revision=1,
        name="验证条件",
        effect="allow",
        evidence="隔离测试",
        conditions=[],
        **patch,
    )


@pytest.mark.parametrize(
    "operator,expected", [("eq", "32"), ("any", ["32", "64"]), ("all", ["32"]), ("range", None)]
)
@pytest.mark.parametrize(
    "value,kind,unit",
    [
        (None, "quantity", "GB"),
        ("32", "quantity", "GB"),
        ("31", "quantity", "GB"),
        ("64", "quantity", "GB"),
        ("32", "quantity", "MB"),
        ("bad", "quantity", "GB"),
        (["32", "64"], "enum", "GB"),
        ("32.00", "quantity", "GB"),
    ],
)
def test_predicates_match_legacy(decisions, operator, expected, value, kind, unit):
    predicate = dict(
        field="product.memory",
        operator=operator,
        value=expected,
        minimum="32",
        maximum="64",
        unit="GB",
    )
    context = {"product.memory": dict(value=value, kind=kind, unit=unit)}
    assert decisions.check_condition(predicate, context) == check_condition(predicate, context)


def test_all_rule_states_match_and_collect_every_evidence(decisions):
    predicate = condition()
    context = {"product.memory": dict(value="32", kind="quantity", unit="GB")}
    for effects in product(["allow", "deny"], repeat=2):
        for values in product(["32", "64", None], repeat=2):
            rules = [
                dict(rule(str(i)), effect=effect, conditions=[dict(predicate, value=value)])
                for i, (effect, value) in enumerate(zip(effects, values))
            ]
            assert decisions.evaluate_rules(rules, context) == evaluate_rules_v3(rules, context)


def test_activation_and_alternatives(decisions):
    context = {"product.memory": dict(value="32", kind="quantity", unit="GB")}
    rules = [
        dict(rule("one"), conditions=[dict(condition(), value="64")], alternative_group="A"),
        dict(rule("two"), conditions=[condition()], alternative_group="A"),
    ]
    assert decisions.evaluate_rules(rules, context) == evaluate_rules_v3(rules, context)
    rules[1]["activation_conditions"] = [dict(condition(), value="64")]
    assert decisions.evaluate_rules(rules, context) == evaluate_rules_v3(rules, context)
    del context["product.memory"]
    assert decisions.evaluate_rules(rules, context) == evaluate_rules_v3(rules, context)


def test_unknown_and_capacity(decisions):
    assert decisions.evaluate_rules([], {})["status"] == "unknown"
    assert decisions.capacity(required="0.07", capacity="0.0700") == "pass"
    assert decisions.capacity(required="32.0001", capacity="32") == "conflict"
    assert decisions.capacity(required="32", capacity=None) == "unknown"


def test_model_corruption_and_execution_failure_are_not_python_fallback(decisions):
    bundle = compile_rules([rule()])
    corrupt = deepcopy(bundle)
    corrupt["graph"]["nodes"] = []
    with pytest.raises(ValueError, match="校验值"):
        decisions.load(corrupt)

    class BrokenEngine:
        def create_decision(self, value):
            raise RuntimeError("broken")

    with pytest.raises(ValueError, match="执行失败"):
        ZenDecisions(BrokenEngine()).evaluate_rules([rule()], {})


def test_values_cannot_inject_expressions(decisions):
    value = '" or true or "'
    result = decisions.check_condition(
        condition(), {"product.memory": dict(value=value, kind="text", unit="GB")}
    )
    assert result == "fail"
