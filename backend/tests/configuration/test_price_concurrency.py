from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from .conftest import catalog as catalog_fixture
from .test_catalog_updates import COLUMN, ROOT, batch_for, call, decision, edit
from .test_evolution_contracts import postgres_client as postgres_client


def test_atomic_price_publish_and_retry(postgres_client, workbook):
    client = postgres_client
    catalog = catalog_fixture.__wrapped__(client, workbook)
    variant = catalog["variants"][0]

    def request_for():
        batch = edit(
            client,
            batch_for(client, variant),
            decision(
                variant,
                prices=[
                    dict(column=COLUMN, state="amount", amount="30", effective_date="2026-09-29")
                ],
            ),
        )
        request = dict(expected_revision=batch["revision"], row_ids=[batch["rows"][0]["id"]])
        preview = call(client, "/" + batch["id"] + "/preview", request)
        return ROOT + "/" + batch["id"] + "/apply", dict(
            **request, fingerprint=preview["fingerprint"], operation_id=str(uuid4())
        )

    endpoint, request = request_for()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(endpoint, json=request), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    left, right = request_for(), request_for()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda p: client.post(p[0], json=p[1]), [left, right]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    result = client.get(ROOT + "/prices/" + variant["id"]).json()
    assert result["history"][0]["revision"] == 2
