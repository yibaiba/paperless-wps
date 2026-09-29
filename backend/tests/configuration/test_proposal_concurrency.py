from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from .conftest import catalog as catalog_fixture
from .test_evolution_contracts import postgres_client as postgres_client
from .test_proposal_generation import draft_for, published, read


def test_plan_and_apply_concurrent_retries(postgres_client, workbook):
    client = postgres_client
    catalog = catalog_fixture.__wrapped__(client, workbook)
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    request = dict(
        draft_id=draft["id"], expected_revision=draft["revision"], operation_id=str(uuid4())
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: client.post("/api/list-tools/list_plan", json=request), range(2))
        )
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    proposal = responses[0].json()
    request = dict(
        request,
        operation_id=str(uuid4()),
        operations=[
            dict(
                action="proposal_apply",
                proposal_id=proposal["proposal_id"],
                option_id=proposal["option"]["id"],
                fingerprint=proposal["fingerprint"],
            )
        ],
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: client.post("/api/list-tools/list_update", json=request), range(2))
        )
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert len(read(client, draft)["configuration"]["devices"]) == 2
