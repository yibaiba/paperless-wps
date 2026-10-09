"""Compatibility imports for configuration callers.

New cross-module code imports these primitives from ``presales.application``.
"""

from presales.application.contracts import Authored, Change, Input, Text
from presales.application.revisions import Entities, view

__all__ = ["Authored", "Change", "Entities", "Input", "Text", "view"]
