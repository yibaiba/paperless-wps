class RevisionConflict(Exception):
    """The caller attempted to update a stale or mismatched revision."""


# The established public name remains available while ownership moves out of rules.
RuleConflict = RevisionConflict
