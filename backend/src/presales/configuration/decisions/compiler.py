"""Compile authored predicates into a controlled, versioned ZEN decision graph."""

from collections import defaultdict

from presales.rules.calculation import digest

COMPILER_VERSION = "knowledge-zen-1"
ENGINE_VERSION = "0.53.0"


def aggregate(expressions):
    values = "[" + ", ".join(expressions) + "]"
    return (
        f'contains({values}, "fail") ? "fail" : contains({values}, "unknown") ? "unknown" : "pass"'
    )


def predicate(condition, index):
    item = f"p{index}"
    operator = condition["operator"]
    tests = {
        "eq": (
            f"({item}.numeric ? number({item}.value) == number({item}.expected) : "
            f"{item}.value == {item}.expected)"
        ),
        "any": f"some({item}.expected, contains({item}.values, #))",
        "all": f"all({item}.expected, contains({item}.values, #))",
        "range": (
            f"(({item}.minimum == null or number({item}.value) >= number({item}.minimum)) "
            f"and ({item}.maximum == null or number({item}.value) <= number({item}.maximum)))"
        ),
    }
    if operator not in tests:
        raise ValueError(f"条件 {index}：不支持的操作符 {operator}")
    return (
        f'not {item}.known or {item}.unit != {item}.expectedUnit ? "unknown" : '
        f'({tests[operator]} ? "pass" : "fail")'
    )


def expression_node(identity, expressions):
    return dict(
        id=identity,
        type="expressionNode",
        name=identity,
        position=dict(x=0, y=0),
        content=dict(expressions=[dict(id=k, key=k, value=v) for k, v in expressions.items()]),
    )


def compile_rules(rules):
    predicates, bindings, outcomes, activations = {}, [], {}, {}
    for index, rule in enumerate(rules):
        keys = {}
        for group in ("activation_conditions", "conditions"):
            names = []
            for position, condition in enumerate(rule.get(group, [])):
                key = f"c{len(bindings)}"
                predicates[key] = predicate(condition, len(bindings))
                bindings.append(
                    dict(
                        rule_index=index,
                        rule_id=rule["id"],
                        rule_revision=rule["revision"],
                        group=group,
                        position=position,
                        condition=condition,
                        node=key,
                    )
                )
                names.append(key)
            keys[group] = names
        activation = aggregate(keys["activation_conditions"])
        activations[f"a{index}"] = activation
        outcomes[f"r{index}"] = (
            f'({activation}) == "fail" ? "not_applicable" : '
            f'({activation}) == "unknown" ? "unknown" : ({aggregate(keys["conditions"])})'
        )
    nodes = [
        dict(id="input", type="inputNode", name="input", position=dict(x=0, y=0)),
        expression_node("predicates", predicates or {"empty": "true"}),
        expression_node("rules", {**{k: k for k in predicates}, **outcomes, **activations}),
        expression_node(
            "decision",
            {
                **{k: k for k in [*predicates, *outcomes, *activations]},
                "status": status_expression(rules),
            },
        ),
        dict(id="output", type="outputNode", name="output", position=dict(x=0, y=0)),
    ]
    graph = dict(
        contentType="application/vnd.gorules.decision",
        nodes=nodes,
        edges=[
            dict(id=f"edge{i}", sourceId=a["id"], targetId=b["id"], type="edge")
            for i, (a, b) in enumerate(zip(nodes, nodes[1:]))
        ],
    )
    from .combination import combination_bundle

    combinations = {
        str((rule["id"], rule["revision"])): combination_bundle(rule["combination"]["mode"])
        for rule in rules
        if rule.get("kind") == "combination" and rule.get("combination")
    }
    payload = dict(
        combinations=combinations,
        compiler_version=COMPILER_VERSION,
        engine_version=ENGINE_VERSION,
        rules=rules,
        bindings=bindings,
        graph=graph,
    )
    return dict(payload, hash=digest(payload))


def status_expression(rules):
    allows, denials = defaultdict(list), []
    for index, rule in enumerate(rules):
        if rule["effect"] == "deny":
            denials.append(f"r{index}")
        else:
            allows[rule.get("alternative_group") or rule["id"]].append(f"r{index}")
    groups = [alternative(items) for items in allows.values()]
    denied = "[" + ",".join(denials) + "]"
    allowed = "[" + ",".join(groups) + "]"
    return (
        f'contains({denied}, "pass") or contains({allowed}, "fail") ? "conflict" : '
        f'contains({denied}, "unknown") or contains({allowed}, "unknown") or '
        f'not contains({allowed}, "pass") ? "unknown" : "pass"'
    )


def alternative(items):
    values = "[" + ",".join(items) + "]"
    return (
        f'(contains({values}, "pass") ? "pass" : contains({values}, "unknown") ? "unknown" : '
        f'contains({values}, "fail") ? "fail" : "not_applicable")'
    )
