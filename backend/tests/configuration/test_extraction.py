from io import BytesIO

import httpx
import pytest
from pypdf import PdfWriter

from presales.configuration.extraction.materials import pdf_material
from presales.configuration.extraction.provider import ModelClient
from presales.configuration.extraction.service import ExtractionService
from presales.configuration.extraction.settings import ModelSettings, PrivateSettings
from presales.configuration.extraction.worker import interrupt_running, process_one
from presales.configuration.models import ExtractionJob

from .conftest import AUTHOR, BASE, post

PATH = "/extraction"


def task(client):
    material = post(
        client,
        PATH + "/materials/text",
        dict(name="隔离测试说明", text="测试服务器具备64GB内存。\n\n容量上限未知。"),
    )
    return post(client, PATH + "/jobs", dict(material_ids=[material["id"]], **AUTHOR))


class IsolatedProvider:
    """Deterministic model boundary for isolated tests only; never installed in the app."""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_empty_real_response_completes_segments_without_publishing(client):
    job = task(client)
    provider = IsolatedProvider({"drafts": []})
    assert process_one(client.app.state.session_factory, provider)
    jobs = client.get(BASE + PATH + "/jobs").json()
    assert jobs[0]["id"] == job["id"] and jobs[0]["status"] == "completed"
    assert all(s["status"] == "completed" for s in jobs[0]["segments"])
    assert provider.calls == 2
    assert client.get(BASE + "/knowledge").json() == []


@pytest.mark.parametrize(
    "response",
    [
        ValueError("模型请求超时"),
        {"wrong": True},
        {
            "drafts": [
                {"kind": "question", "quotation": "不存在的原文", "proposal": {"question": "未知"}}
            ]
        },
    ],
)
def test_failure_not_success_and_manual_retry(client, response):
    job = task(client)
    provider = IsolatedProvider(response)
    process_one(client.app.state.session_factory, provider)
    failed = client.get(BASE + PATH + "/jobs").json()[0]
    assert failed["status"] == "failed" and failed["error"]
    assert failed["segments"][0]["status"] == "failed"
    assert client.get(BASE + PATH + "/drafts").json() == []
    assert post(client, PATH + "/jobs/" + job["id"] + "/retry", {})["status"] == "queued"


def test_draft_review_preserves_quote_and_not_auto_confirmed(client):
    job = task(client)
    factory = client.app.state.session_factory
    with factory() as session:
        record = session.get(ExtractionJob, job["id"])
        segment = record.payload["segments"][0]
        ExtractionService(session).store_output(
            {
                "drafts": [
                    dict(
                        kind="product",
                        quotation="64GB内存",
                        proposal=dict(name="测试服务器", model="TEST-ONLY", **AUTHOR),
                    )
                ]
            },
            job_id=job["id"],
            segment=segment,
        )
        session.commit()
    assert client.get(BASE + "/products").json() == []
    draft = client.get(BASE + PATH + "/drafts").json()[0]
    post(client, PATH + "/decisions", dict(draft_ids=[draft["id"]], action="accept", **AUTHOR))
    product = client.get(BASE + "/products").json()[0]
    assert "64GB内存" in product["evidence"] and "段落 1" in product["evidence"]
    assert (
        client.post(
            BASE + PATH + "/decisions",
            json=dict(draft_ids=[draft["id"]], action="accept", **AUTHOR),
        ).status_code
        == 409
    )


def test_scan_and_invalid_pdf_are_explicit_errors():
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(stream)
    with pytest.raises(ValueError, match="未提取到文字"):
        pdf_material(name="scan.pdf", content=stream.getvalue())
    with pytest.raises(ValueError, match="无法解析"):
        pdf_material(name="broken.pdf", content=b"invalid pdf")


def test_interrupted_tasks_mark_segments_and_preserve_completion(client):
    job = task(client)
    factory = client.app.state.session_factory
    with factory() as session:
        record = session.get(ExtractionJob, job["id"])
        segments = record.payload["segments"]
        record.status = "running"
        record.payload = {
            **record.payload,
            "segments": [
                {**segments[0], "status": "completed"},
                {**segments[1], "status": "running"},
            ],
        }
        session.commit()
    interrupt_running(factory)
    result = client.get(BASE + PATH + "/jobs").json()[0]
    assert result["status"] == "interrupted"
    assert [s["status"] for s in result["segments"]] == ["completed", "interrupted"]
    post(client, PATH + "/jobs/" + job["id"] + "/retry", {})
    provider = IsolatedProvider({"drafts": []})
    process_one(factory, provider)
    assert provider.calls == 1


def test_private_settings_permissions_and_no_key_echo(client, tmp_path):
    settings = PrivateSettings(tmp_path / "private/model.json")
    client.app.state.model_settings = settings
    payload = dict(
        base_url="https://example.test/v1", model="test-model", api_key="test-secret-only"
    )
    response = client.put(BASE + PATH + "/settings", json=payload)
    assert response.status_code == 200
    assert "test-secret-only" not in response.text
    assert settings.path.stat().st_mode & 0o777 == 0o600
    response = client.put(BASE + PATH + "/settings", json={**payload, "base_url": "invalid"})
    assert response.status_code == 422 and "test-secret-only" not in response.text
    response = client.get(BASE + PATH + "/settings")
    assert "test-secret-only" not in response.text
    settings.write(ModelSettings(**{**payload, "api_key": "", "base_url": "https://other.test/v1"}))
    assert settings.read().api_key == ""
    settings.path.write_text('{"api_key":"test-secret-only","base_url":"invalid","model":"m"}')
    response = client.get(BASE + PATH + "/settings")
    assert response.status_code == 422 and "test-secret-only" not in response.text


@pytest.mark.parametrize("failure", ["timeout", "http", "format"])
def test_model_adapter_fails_clearly(failure):
    def handle(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private payload must not appear", request=request)
        if failure == "http":
            return httpx.Response(401, text="secret response")
        return httpx.Response(200, json={"choices": []})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        model = ModelClient(client, ModelSettings(base_url="https://example.test/v1", model="test"))
        with pytest.raises(ValueError) as error:
            model.complete(instruction="test", material={})
        assert "secret" not in str(error.value) and "private" not in str(error.value)


def test_only_selected_catalog_context_sent(client, catalog):
    material = post(
        client, PATH + "/materials/text", dict(name="范围测试", text="仅说明一个配置。")
    )
    job = post(
        client,
        PATH + "/jobs",
        dict(material_ids=[material["id"]], variant_ids=[catalog["variants"][0]["id"]], **AUTHOR),
    )
    assert [v["id"] for v in job["context"]["variants"]] == [catalog["variants"][0]["id"]]
    assert [p["id"] for p in job["context"]["products"]] == [catalog["product"]["id"]]
    assert catalog["variants"][1]["id"] not in str(job["context"])
    factory = client.app.state.session_factory
    with factory() as session:
        segment = session.get(ExtractionJob, job["id"]).payload["segments"][0]
        with pytest.raises(ValueError, match="超出"):
            ExtractionService(session).store_output(
                {
                    "drafts": [
                        dict(
                            kind="source_link",
                            quotation="仅说明一个配置",
                            proposal=dict(
                                variant_id=catalog["variants"][1]["id"],
                                items=[
                                    dict(source_id=catalog["sources"][1]["id"], expected_revision=1)
                                ],
                                **AUTHOR,
                            ),
                        )
                    ]
                },
                job_id=job["id"],
                segment=segment,
            )


def test_model_cannot_publish_confirmed_knowledge(client, catalog):
    job = task(client)
    factory = client.app.state.session_factory
    with factory() as session:
        segment = session.get(ExtractionJob, job["id"]).payload["segments"][0]
        with pytest.raises(ValueError):
            ExtractionService(session).store_output(
                {
                    "drafts": [
                        dict(
                            kind="knowledge",
                            quotation="64GB内存",
                            proposal=dict(
                                name="不应自动确认",
                                kind="suitability",
                                status="confirmed",
                                selector={"category": "服务器"},
                                system="无纸化",
                                role="服务端",
                                **AUTHOR,
                            ),
                        )
                    ]
                },
                job_id=job["id"],
                segment=segment,
            )
    assert client.get(BASE + "/knowledge").json() == []


def test_text_pdf_retains_page_numbers():
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 100 Td (Server memory 64GB) Tj ET")
    page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    material = pdf_material(name="text.pdf", content=output.getvalue())
    assert material["segments"][0]["location"] == "第 1 页"
    assert "Server memory 64GB" in material["segments"][0]["text"]
