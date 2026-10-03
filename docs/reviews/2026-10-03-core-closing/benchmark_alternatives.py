"""Record first-option and replayed second-option cost with identical isolated inputs."""
import json
import sys
import time
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend/tests'))
from conftest import client as client_fixture, workbook
from configuration.conftest import catalog
from configuration.test_proposal_generation import published, draft_for, plan

fixture = client_fixture.__wrapped__()
client = next(fixture)
try:
    products = catalog.__wrapped__(client, workbook.__wrapped__())
    definition, package = published(client, products)
    draft = draft_for(client, definition, package)
    samples = []
    for _ in range(9):
        started = time.perf_counter()
        first = plan(client, draft)
        first_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        second = plan(client, draft, proposal_id=first['proposal_id'], option_offset=1)
        second_ms = (time.perf_counter() - started) * 1000
        assert first['option']['id'] != second['option']['id']
        samples.append(dict(first_ms=first_ms, replay_second_ms=second_ms))
    result = dict(candidate_count=2, role_count=1, samples=samples,
                  median_first_ms=median(s['first_ms'] for s in samples),
                  median_replay_second_ms=median(s['replay_second_ms'] for s in samples),
                  scope='TestClient HTTP service elapsed including generation, not browser network')
    (ROOT/'docs/reviews/2026-10-03-core-closing/alternatives-performance.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
finally:
    fixture.close()
