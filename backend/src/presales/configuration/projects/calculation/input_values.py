"""Compare validated project attributes without changing their stored representation."""

from decimal import Decimal

NUMERIC_KINDS = frozenset({"number", "quantity"})


def same_input_value(left, right):
    if left.get("unit", "") != right.get("unit", ""):
        return False
    values = left.get("value"), right.get("value")
    if None in values or not all(a.get("kind") in NUMERIC_KINDS for a in (left, right)):
        return values[0] == values[1]
    # Numeric attributes have already passed schema validation; do not coerce text or units.
    return Decimal(str(values[0])) == Decimal(str(values[1]))
