from copy import deepcopy

from presales.configuration.projects.drawing import project_drawing
from presales.configuration.projects.services.device_removal import remove_devices


def test_removal_cleans_owned_references_without_changing_other_equipment():
    devices = [dict(id=i, name=i, quantity="1") for i in ("remove", "keep")]
    data = dict(
        devices=devices,
        requirements=[
            dict(
                id="role",
                device_id=None,
                allocations=[dict(device_id=d["id"], quantity="1") for d in devices],
            )
        ],
        drawing_xml=project_drawing("", devices=devices, add_ids=["remove", "keep", "remove"]),
        accessory_allocations=[
            dict(id="a1", device_id="keep", demand_id="removed-demand"),
            dict(id="a2", device_id="keep", demand_id="kept-demand"),
        ],
        included_allocations=[dict(id="i1", device_id="remove", demand_id="kept-demand")],
        accessory_choices=[
            dict(demand_id=d, selected=True) for d in ("removed-demand", "kept-demand")
        ],
        supply_allocations=[dict(device_id=d["id"]) for d in devices],
        quotation=dict(
            prices=[dict(device_id=d["id"]) for d in devices],
            sections={"remove": "x", "keep": "y"},
            descriptions={"remove": "x", "keep": "y"},
        ),
        generation=dict(
            preferences=[
                dict(
                    requirement_id="role",
                    reusable_device_ids=["remove", "keep"],
                    required_variant_id="preserved",
                )
            ],
            sources=[dict(object_id=i) for i in ("remove", "keep")],
            features_confirmed=["system"],
        ),
        manual_edits=dict(
            requirements=["role"], accessory_allocations=["a1", "a2"], included_allocations=["i1"]
        ),
    )
    before = deepcopy(data)
    result = remove_devices(
        data, ["remove"], demands=[dict(id="removed-demand", scope="device", scope_id="remove")]
    )
    assert data == before
    assert [d["id"] for d in result["devices"]] == ["keep"]
    assert result["requirements"][0]["allocations"] == [dict(device_id="keep", quantity="1")]
    assert 'cfg_device_id="remove"' not in result["drawing_xml"]
    assert 'cfg_device_id="keep"' in result["drawing_xml"]
    assert result["quotation"] == dict(
        prices=[dict(device_id="keep")], sections={"keep": "y"}, descriptions={"keep": "y"}
    )
    assert result["generation"]["preferences"][0]["reusable_device_ids"] == ["keep"]
    assert result["generation"]["preferences"][0]["required_variant_id"] == "preserved"
    assert result["generation"]["sources"] == [dict(object_id="keep")]
    assert result["generation"]["features_confirmed"] == ["system"]
    assert result["manual_edits"] == dict(
        requirements=["role"], accessory_allocations=["a2"], included_allocations=[]
    )
    assert result["accessory_choices"] == [dict(demand_id="kept-demand", selected=True)]
    assert result["supply_allocations"] == [dict(device_id="keep")]
