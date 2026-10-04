from types import SimpleNamespace

import pytest
from presales.wps.next_edits import recent_requirement


def edit(**overrides):
    return SimpleNamespace(
        **dict(
            dict(
                operation_id="quantity-change",
                kind="quantity",
                device_id=None,
                requirement_id=None,
                changes=[],
                sequence=1,
            ),
            **overrides,
        )
    )


def requirement(identity, system_id):
    return dict(
        id=identity,
        system_id=system_id,
        device_id=None,
        allocations=[dict(device_id="existing-hardware", quantity="2")],
    )


@pytest.mark.parametrize("structured", [False, True])
def test_quantity_change_tracks_allocated_device_in_current_system(structured):
    change = (
        edit(changes=[SimpleNamespace(kind="devices", id="existing-hardware")])
        if structured
        else edit(device_id="existing-hardware")
    )
    request = SimpleNamespace(scope=SimpleNamespace(system_id="current"), recent_edits=[change])
    checked = dict(
        configuration=dict(
            requirements=[requirement("other-room", "other"), requirement("current-use", "current")]
        )
    )
    assert recent_requirement(request, checked) == "current-use"


def test_undone_allocated_device_edit_is_not_prioritized():
    request = SimpleNamespace(
        scope=SimpleNamespace(system_id="current"),
        recent_edits=[edit(device_id="existing-hardware"), edit(kind="undo", sequence=2)],
    )
    checked = dict(configuration=dict(requirements=[requirement("current-use", "current")]))
    assert recent_requirement(request, checked) is None
