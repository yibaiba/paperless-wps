"""Stored checks retain their original result until an explicit fresh check."""

from .models import PROJECTION_VERSION


def current_projection(checked):
    if checked["configuration"].get("calculation_version", 1) != 3:
        return True
    projection = checked.get("usage_projection") or {}
    return projection.get("version") == PROJECTION_VERSION and bool(projection.get("fingerprint"))


def projection_status(checked):
    if checked["configuration"].get("calculation_version", 1) != 3:
        return checked
    return dict(
        checked,
        usage_projection=dict(
            checked.get("usage_projection") or {},
            current=current_projection(checked),
            required_version=PROJECTION_VERSION,
            message=None
            if current_projection(checked)
            else "历史用途结果未含当前分配明细，请预览重新检查差异",
        ),
    )
