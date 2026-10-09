"""Compatibility exports for catalog update callers."""

from presales.configuration.catalog.impacts import (
    affected,
    apply_review_checks,
    pending_reviews,
    relevant_rule,
    usage_contexts,
)

__all__ = [
    "affected",
    "apply_review_checks",
    "pending_reviews",
    "relevant_rule",
    "usage_contexts",
]
