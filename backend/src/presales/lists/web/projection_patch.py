"""Sparse JSON projection patches; unchanged branches are absent."""


def projection_patch(before, after):
    if before == after:
        return None
    if isinstance(before, dict) and isinstance(after, dict):
        fields = {}
        for key, value in after.items():
            patch = projection_patch(before[key], value) if key in before else {"value": value}
            if patch is not None:
                fields[key] = patch
        return {"fields": fields, "removed": [key for key in before if key not in after]}
    if isinstance(before, list) and isinstance(after, list):
        items = {}
        for index, value in enumerate(after):
            patch = (
                projection_patch(before[index], value) if index < len(before) else {"value": value}
            )
            if patch is not None:
                items[str(index)] = patch
        return {"items": items, "length": len(after)}
    return {"value": after}
