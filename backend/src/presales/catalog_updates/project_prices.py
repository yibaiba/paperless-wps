"""Compatibility exports for existing catalog update API callers."""

from presales.configuration.projects.services.price_adoption import (
    adopt_versions,
    preview_prices,
    price_issues,
    validate_references,
)

__all__ = ["adopt_versions", "preview_prices", "price_issues", "validate_references"]
