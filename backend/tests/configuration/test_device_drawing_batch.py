from copy import deepcopy

import pytest

from presales.configuration.projects import drawing
from presales.configuration.projects.edit_schemas import DevicePut, DrawingSet, QuoteSet, SectionSet
from presales.configuration.projects.schemas import Configuration
from presales.configuration.projects.services.editing import (
    EditError,
    apply_operation,
    edit_configuration,
)
from presales.topology.drawio.document import Document


def device_operation(index, *, name=None, quantity="1"):
    return DevicePut(
        action="device_put",
        value=dict(
            id=f"device-{index}",
            name=name or f"设备 {index}",
            quantity=quantity,
            variant_id="variant",
            source_id="source",
            kind="hardware",
        ),
    )


def configuration():
    return Configuration(actor="隔离测试", evidence="仅验证图形批处理").model_dump(mode="json")


def semantic_drawing(xml):
    return [
        (
            cell.element.get("cfg_device_id"),
            cell.element.get("label"),
            dict(cell.node.find("mxGeometry").attrib),
        )
        for cell in Document(xml).cells.values()
        if cell.element.get("cfg_device_id")
    ]


def sequential(data, operations):
    result = deepcopy(data)
    for operation in operations:
        result = apply_operation(result, operation=operation, repository=object())
    return result


def test_row_operations_project_drawing_twice_not_once_per_product(monkeypatch):
    data = configuration()
    operations = [QuoteSet(action="quotation_set", value={"project_name": "隔离报价"})]
    for index in range(20):
        operations.extend(
            [
                device_operation(index),
                SectionSet(action="section_set", device_id=f"device-{index}", section="业务区"),
            ]
        )
    expected = sequential(data, operations)
    count = 0
    actual_document = drawing.Document

    def counted_document(xml):
        nonlocal count
        count += 1
        return actual_document(xml)

    monkeypatch.setattr(drawing, "Document", counted_document)
    original = deepcopy(data)
    actual = edit_configuration(data, operations, repository=object()).model_dump(mode="json")
    assert count == 2
    assert data == original
    assert semantic_drawing(actual["drawing_xml"]) == semantic_drawing(expected["drawing_xml"])
    assert actual["devices"] == expected["devices"]


def test_drawing_set_flushes_previous_edits_and_keeps_later_node_layout():
    data = configuration()
    first = device_operation(0)
    replacement = drawing.project_drawing(
        "", devices=[first.value.model_dump(mode="json")], add_ids=["device-0"]
    )
    operations = [
        first,
        device_operation(1),
        DrawingSet(action="drawing_set", xml=replacement),
        device_operation(2),
        device_operation(2, name="更新名称", quantity="3"),
    ]
    expected = sequential(data, operations)
    actual = edit_configuration(data, operations, repository=object()).model_dump(mode="json")
    assert semantic_drawing(actual["drawing_xml"]) == semantic_drawing(expected["drawing_xml"])


def test_invalid_initial_drawing_cannot_be_repaired_by_a_later_row():
    data = configuration()
    later = device_operation(1).value.model_dump(mode="json")
    data["drawing_xml"] = drawing.project_drawing("", devices=[later], add_ids=[later["id"]])
    with pytest.raises(EditError, match="图形引用的设备不存在") as error:
        edit_configuration(data, [device_operation(0), device_operation(1)], repository=object())
    assert error.value.detail["operation_index"] == 0
