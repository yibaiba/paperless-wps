import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from presales.configuration.search.documents import variant_document, variant_document_record
from presales.configuration.search.provider import SearchModelClient
from presales.configuration.search.service import SearchIndexer, SearchIndexService
from presales.configuration.search.settings import PrivateSearchSettings, SearchSettings
from presales.configuration.search.worker import process_one
from presales.main import create_app
from presales.storage import Base

from .conftest import AUTHOR, BASE, post


class DeterministicSearchProvider:
    def embeddings(self, texts):
        return [self._vector(text) for text in texts]

    def rerank(self, query, documents):
        return [10.0 if "128GB" in document else 1.0 for document in documents]

    @staticmethod
    def _vector(text):
        vector = [0.0] * 1024
        vector[1 if "128" in text else 0] = 1.0
        return vector


def configured_store(tmp_path: Path):
    store = PrivateSearchSettings(tmp_path / "private" / "search.json")
    store.write(
        SearchSettings(
            embedding_url="http://127.0.0.1:9000/v1/embeddings",
            embedding_model="Qwen3-Embedding-0.6B",
            reranker_url="http://127.0.0.1:9001/rerank",
            reranker_model="Qwen3-Reranker-0.6B",
        )
    )
    return store


def test_search_settings_are_private_and_preserve_key(tmp_path):
    store = configured_store(tmp_path)
    store.write(
        SearchSettings(
            embedding_url="http://127.0.0.1:9000/v1/embeddings",
            embedding_model="Qwen3-Embedding-0.6B",
            reranker_url="http://127.0.0.1:9001/rerank",
            reranker_model="Qwen3-Reranker-0.6B",
            api_key="secret",
        )
    )
    public = store.public()
    assert public["configured"] is True
    assert public["has_key"] is True
    assert "api_key" not in public
    saved = {
        key: value
        for key, value in public.items()
        if key not in {"configured", "has_key"}
    }
    store.write(SearchSettings(**saved, api_key=""))
    assert store.read().api_key == "secret"


def test_provider_validates_embedding_and_reranker_contract():
    vector = [0.0] * 1024

    def handler(request):
        if request.url.path.endswith("embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": vector}]})
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.8},
                    {"index": 0, "relevance_score": 0.2},
                ]
            },
        )

    settings = SearchSettings(
        embedding_url="https://models.test/embeddings",
        embedding_model="embedding",
        reranker_url="https://models.test/rerank",
        reranker_model="reranker",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = SearchModelClient(client, settings)
        assert provider.embeddings(["query"]) == [vector]
        assert provider.rerank("query", ["a", "b"]) == [0.2, 0.8]


def test_document_contains_structured_product_facts(client, catalog):
    variant_id = catalog["variants"][0]["id"]
    variant = next(
        item for item in client.get(BASE + "/variants").json() if item["id"] == variant_id
    )
    document = variant_document(variant)
    assert "产品型号：SERVER-X" in document
    assert "属性 memory（数量）：64GB" in document
    assert variant_document_record(variant)["content_hash"] == variant_document_record(variant)[
        "content_hash"
    ]


def test_index_job_tracks_current_and_stale_documents(client, catalog, tmp_path):
    store = configured_store(tmp_path)
    provider = DeterministicSearchProvider()
    client.app.state.search_settings = store
    client.app.state.search_provider = lambda: provider
    before = client.get(BASE + "/search/status").json()
    assert before["pending"] == 2
    job = client.post(BASE + "/search/jobs").json()
    assert job["status"] == "queued"
    SearchIndexer(client.app.state.session_factory, store, lambda: provider).process(job["id"])
    after = client.get(BASE + "/search/status").json()
    assert after["indexed"] == 2
    assert client.get(BASE + "/search/jobs").json()[0]["status"] == "completed"
    update_variant(client, catalog["variants"][0], name="已修改配置")
    stale = client.get(BASE + "/search/status").json()
    assert stale["stale"] == 1
    assert stale["indexed"] == 1



class FailingSearchProvider:
    def embeddings(self, texts):
        raise ValueError("模型暂时不可用")


def test_failed_index_job_is_visible(client, catalog, tmp_path):
    store = configured_store(tmp_path)
    client.app.state.search_settings = store
    job = client.post(BASE + "/search/jobs").json()
    assert process_one(client.app.state.session_factory, store, FailingSearchProvider) is True
    result = client.get(BASE + "/search/jobs").json()[0]
    assert result["id"] == job["id"]
    assert result["status"] == "failed"
    assert result["error"] == "模型暂时不可用"
    status = client.get(BASE + "/search/status").json()
    assert status["failed"] == 2


def test_semantic_mode_requires_postgresql(client, catalog, tmp_path):
    store = configured_store(tmp_path)
    client.app.state.search_settings = store
    client.app.state.search_provider = DeterministicSearchProvider
    response = client.post(
        BASE + "/candidates",
        json={"system": "无纸化", "role": "服务端", "mode": "semantic", "query_text": "128GB"},
    )
    assert response.status_code == 422
    assert "PostgreSQL pgvector" in response.json()["detail"]


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="需要 PostgreSQL pgvector")
def test_postgresql_semantic_ranking_respects_business_status(workbook, tmp_path):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "semantic_search_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    factory = sessionmaker(isolated, expire_on_commit=False)
    store = configured_store(tmp_path)
    provider = DeterministicSearchProvider()
    try:
        Base.metadata.create_all(isolated)
        app = create_app(
            session_factory=factory,
            search_settings=store,
            search_provider=lambda: provider,
        )
        with TestClient(app) as client:
            catalog = create_catalog(client, workbook)
            create_suitability(client, catalog["variants"][0])
            with factory() as session:
                job = SearchIndexService(session, store).enqueue()
                session.commit()
            SearchIndexer(factory, store, lambda: provider).process(job["id"])
            response = client.post(
                BASE + "/candidates",
                json={
                    "system": "无纸化",
                    "role": "服务端",
                    "mode": "semantic",
                    "query_text": "需要128GB服务器",
                },
            )
            assert response.status_code == 200, response.text
            results = response.json()
            assert [item["status"] for item in results] == ["pass", "unknown"]
            assert [item["ranking"]["rank"] for item in results] == [2, 1]
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def create_catalog(client, workbook):
    imported = client.post("/api/imports", files={"file": ("test.xlsx", workbook)}).json()
    sources = client.get("/api/products", params={"import_id": imported["id"]}).json()
    sources = [client.get("/api/products/" + item["id"]).json() for item in sources]
    product = post(
        client,
        "/products",
        dict(name="服务器", model="SERVER-X", category="服务器", **AUTHOR),
    )
    variants = []
    for source in sources:
        memory = source["specification"].replace("GB", "")
        variant = post(
            client,
            "/variants",
            dict(
                product_id=product["id"],
                name=memory + "GB",
                status="confirmed",
                attributes=[dict(key="memory", kind="quantity", value=memory, unit="GB")],
                **AUTHOR,
            ),
        )
        post(
            client,
            "/source-links",
            dict(
                variant_id=variant["id"],
                items=[dict(source_id=source["id"], expected_revision=0)],
                **AUTHOR,
            ),
        )
        variants.append(variant)
    return dict(variants=variants, sources=sources)


def create_suitability(client, variant):
    return post(
        client,
        "/knowledge",
        dict(
            name="无纸化服务端",
            kind="suitability",
            status="confirmed",
            selector={"variant_ids": [variant["id"]]},
            system="无纸化",
            role="服务端",
            **AUTHOR,
        ),
    )


def update_variant(client, variant, *, name):
    payload = {
        key: variant[key]
        for key in (
            "product_id",
            "status",
            "attributes",
            "series",
            "functions",
            "interfaces",
            "systems",
            "actor",
            "evidence",
        )
    }
    response = client.put(
        BASE + "/variants/" + variant["id"],
        json={"expected_revision": variant["revision"], "payload": {**payload, "name": name}},
    )
    assert response.status_code == 200, response.text
