"""Calculation-only membership; never stored in authored knowledge revisions."""


def package_allows(rule, package_id):
    memberships = rule.get("_knowledge_packages")
    return memberships is None or (package_id or None) in memberships
