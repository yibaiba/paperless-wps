"""Real stdio + HTTP readback of the browser fixture, with immutable saved revisions."""
import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads((ROOT / 'outputs/core-closing/browser.json').read_text())
REPORT = ROOT / 'docs/reviews/2026-10-03-core-closing/protocol-readback.json'
RESULTS = []


async def verify():
    parameters = StdioServerParameters(command=sys.executable, args=['-m', 'presales.mcp_server'], env={
        'DATABASE_URL': 'sqlite:///' + FIXTURE['database'],
        'PYTHONPATH': str(ROOT / 'backend/src'),
        'PRESALES_ARTIFACT_DIR': str(ROOT / 'outputs/core-closing/artifacts'),
    })
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=15) as client:
            await client.initialize()
            async def call(name, request):
                start = time.perf_counter()
                value = await client.call_tool(name, {'request': request})
                assert not value.is_error, value
                RESULTS.append(dict(tool=name, elapsed_ms=round((time.perf_counter()-start)*1000, 2)))
                return value.structured_content

            with httpx.Client(base_url='http://127.0.0.1:8032', timeout=15) as http:
                base_revision = http.get('/api/configuration/projects/' + FIXTURE['generation_project']).json()['revision']
                await shared_cases(call, http)
                saved_request = dict(project_id=FIXTURE['generation_project'], revision=base_revision)
                for view in ('devices', 'procurement', 'quotation', 'issues', 'allocations'):
                    request = dict(saved_request, view=view)
                    actual = await call('list_get', request)
                    response = http.post('/api/list-tools/list_get', json=request)
                    response.raise_for_status()
                    assert actual == response.json(), view
                    RESULTS.append(dict(view=view, exact_http_match=True))
                devices = (await call('list_get', dict(saved_request, view='devices')))['items']
                assert sorted(d['quantity'] for d in devices) == ['1', '16']
                draft = await call('list_create', dict(**saved_request, name='隔离协议改单', operation_id=str(uuid4()), actor='软件验收', evidence='隔离测试'))
                system = http.get('/api/configuration/projects/' + FIXTURE['generation_project']).json()['configuration']['systems'][0]
                for seats in ('32', '48', '16'):
                    request = dict(draft_id=draft['id'], expected_revision=draft['revision'], operation_id=str(uuid4()), operations=[dict(action='requirements_patch', systems=[dict(system=dict(system, inputs=[dict(key='seats', kind='quantity', value=seats, unit='台')]), features_confirmed=True)])])
                    draft = await call('list_update', request)
                    assert await call('list_update', request) == draft
                    plan_request = dict(draft_id=draft['id'], expected_revision=draft['revision'], operation_id=str(uuid4()))
                    proposal = await call('list_plan', plan_request)
                    request = dict(draft_id=draft['id'], expected_revision=draft['revision'], operation_id=str(uuid4()), operations=[dict(action='proposal_apply', proposal_id=proposal['proposal_id'], option_id=proposal['option']['id'], fingerprint=proposal['fingerprint'])])
                    draft = await call('list_update', request)
                    items = (await call('list_get', dict(draft_id=draft['id'], view='devices')))['items']
                    assert sorted(d['quantity'] for d in items) == sorted(['1', seats])
                    RESULTS.append(dict(seats=seats, quantities=sorted(d['quantity'] for d in items)))
                checked = await call('list_check', dict(draft_id=draft['id'], expected_revision=draft['revision'], operation_id=str(uuid4())))
                saved = await call('list_save', dict(draft_id=draft['id'], expected_revision=checked['revision'], expected_project_revision=base_revision, fingerprint=checked['check_fingerprint'], operation_id=str(uuid4())))
                exported = await call('list_export', dict(project_id=saved['project_id'], revision=saved['project_revision'], operation_id=str(uuid4())))
                assert len(exported['artifacts']) == 2
                RESULTS.append(dict(saved_revision=saved['project_revision'], artifacts=exported['artifacts']))
                historical = await call('list_get', dict(saved_request, view='devices'))
                assert historical['items'] == devices
    REPORT.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2))


async def shared_cases(call, http):
    cases = json.loads((ROOT/'outputs/core-closing/shared-browser.json').read_text())
    for name, case in cases.items():
        draft = await call('list_create', dict(project_id=case['project_id'], revision=1,
                           name=name, actor='协议验收', evidence='隔离测试', operation_id=str(uuid4())))
        await call('list_check', dict(draft_id=draft['id'], expected_revision=draft['revision'], operation_id=str(uuid4())))
        issues = await call('list_get', dict(draft_id=draft['id'], view='issues'))
        actual = [dict(kind=c['kind'],status=c['status']) for c in issues['items'] if c['kind'] in ['sharing','capacity']]
        assert actual == case['checks'], (name, actual)
        procurement = await call('list_get', dict(draft_id=draft['id'], view='procurement'))
        hardware = [i for i in procurement['items'] if i['kind']=='hardware']
        expected = 2 if name=='两台独立服务器' else 0 if name in ('客户已有服务器','共享容量超量') else 1
        assert len(hardware)==expected, (name, hardware)
        request = dict(project_id=case['project_id'], revision=1, view='issues')
        same = await call('list_get', request)
        response = http.post('/api/list-tools/list_get', json=request)
        response.raise_for_status()
        assert same == response.json()
        RESULTS.append(dict(scenario=name, checks=actual, procurement_hardware=expected, exact_http_match=True))


if __name__ == '__main__':
    asyncio.run(verify())
