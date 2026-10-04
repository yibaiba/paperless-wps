import json
from io import BytesIO

from openpyxl import Workbook

from .conftest import AUTHOR, BASE, knowledge

ROOT = BASE + "/extraction/materials"


def workbook_bytes(text="服务器可共用，环境待核对"):
    book = Workbook()
    sheet = book.active
    sheet.title = "版本说明"
    sheet["A1"] = text
    sheet.merge_cells("A1:B2")
    sheet["C1"] = "=SUM(C2:C3)"
    sheet["C2"] = 0
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def upload(client, content, **extra):
    preview = client.post(ROOT + "/xlsx/preview", files={"file": ("版本.xlsx", content)})
    assert preview.status_code == 200, preview.text
    options = (
        dict(
            name="隔离版本说明",
            digest=preview.json()["digest"],
            operation_id="material-create",
            ranges=[dict(sheet="版本说明", range="B2:C3")],
            **AUTHOR,
        )
        | extra
    )
    return client.post(
        ROOT + "/xlsx",
        files={"file": ("版本.xlsx", content)},
        data={"options": json.dumps(options)},
    )


def test_merged_evidence_pinned_revision_and_replay(client, catalog):
    content = workbook_bytes()
    response = upload(client, content)
    assert response.status_code == 200, response.text
    material = response.json()
    assert upload(client, content).json() == material
    segment = next(s for s in material["segments"] if s["cell"] == "B2")
    assert segment["anchor"] == "A1" and segment["merge_range"] == "A1:B2"
    assert segment["text"] == "服务器可共用，环境待核对"
    reference = dict(
        material_id=material["id"],
        material_revision=1,
        segment_id=segment["id"],
        locator=segment["location"],
        quote=segment["text"],
    )
    rule = knowledge(client, catalog["variants"][0], evidence_refs=[reference])
    changed = upload(
        client,
        workbook_bytes("新版需确认软件许可"),
        material_id=material["id"],
        expected_revision=1,
        operation_id="material-edit",
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2
    old = client.get(ROOT + f"/{material['id']}/revisions/1").json()
    assert old["segments"] == material["segments"]
    assert knowledge(client, catalog["variants"][0], evidence_refs=[reference])["evidence_refs"]
    wrong = {**reference, "material_revision": 2}
    payload = {
        k: v
        for k, v in rule.items()
        if k not in {"id", "revision", "updated_at", "completion", "missing_fields"}
    }
    payload["evidence_refs"] = [wrong]
    assert client.post(BASE + "/knowledge", json=payload).status_code == 422
    assert len(
        client.get("/api/products", params={"import_id": catalog["imported"]["id"]}).json()
    ) == len(catalog["sources"])


def test_formula_is_literal_and_wrong_preview_is_rejected(client):
    response = upload(client, workbook_bytes(), ranges=[dict(sheet="版本说明", range="A1:C2")])
    assert response.status_code == 200, response.text
    segments = response.json()["segments"]
    assert next(s for s in segments if s["cell"] == "C1")["text"] == "=SUM(C2:C3)"
    assert next(s for s in segments if s["cell"] == "C2")["text"] == "0"
    assert upload(client, workbook_bytes(), digest="wrong", operation_id="bad").status_code == 409
    assert (
        upload(
            client,
            workbook_bytes(),
            ranges=[dict(sheet="missing", range="A1")],
            operation_id="missing",
        ).status_code
        == 422
    )
