"""Isolated two-system acceptance projects; no business database connection."""
import json
import sys
from copy import deepcopy
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from presales.main import create_app
from presales.storage import ProductRecord

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'backend/tests'))
from configuration.conftest import BASE, post
from configuration.test_evolution_sharing import cross_system, add_server, allocate
from configuration.test_evolution import modern_rule
from configuration.package_helpers import publish_members
fixture=json.loads((ROOT/'outputs/core-closing/browser.json').read_text())
factory=sessionmaker(create_engine('sqlite:///'+fixture['database']),expire_on_commit=False)
with TestClient(create_app(session_factory=factory)) as client:
    variants=client.get(BASE+'/variants').json()
    by_memory={str(next(a['value'] for a in v['attributes'] if a['key']=='memory')):v for v in variants}
    variants=[by_memory['64'],by_memory['128']]
    with factory() as session:
        sources={p.id:dict(id=p.id,**p.payload) for p in session.scalars(select(ProductRecord))}
    catalog=dict(variants=variants,sources=[sources[v['source_ids'][0]] for v in variants])
    data,refs=cross_system(client,catalog)
    initial=post(client,'/check',dict(configuration=data))
    cases={}
    def save_case(key,value):
        project=client.post('/api/projects',json=dict(name='隔离双系统验收 · '+key)).json()
        result=client.put(BASE+'/projects/'+project['id'],json=dict(configuration=value['configuration'],expected_revision=0))
        assert result.status_code==200,result.text
        cases[key]=dict(project_id=project['id'],checks=[dict(kind=c['kind'],status=c['status']) for c in value['checks'] if c['kind'] in ['sharing','capacity']])
    independent=deepcopy(initial['configuration'])
    add_server(independent,catalog,'server0');add_server(independent,catalog,'server1')
    allocate(independent,initial['suggestions'],['server0','server1'])
    save_case('两台独立服务器',post(client,'/check',dict(configuration=independent)))
    shared=deepcopy(initial['configuration']);add_server(shared,catalog,'shared')
    allocate(shared,initial['suggestions'],['shared','shared'])
    save_case('一台共享缺依据',post(client,'/check',dict(configuration=shared)))
    rule=modern_rule(client,catalog['variants'][1],kind='sharing',shared_role_refs=refs)
    publish_members(client,shared['systems'],[rule])
    confirmed=post(client,'/check',dict(configuration=shared,refresh_knowledge=True))
    save_case('测试依据共享通过',confirmed)
    existing=deepcopy(confirmed['configuration'])
    next(a for a in existing['supply_allocations'] if a['device_id']=='shared')['source']='existing'
    save_case('客户已有服务器',post(client,'/check',dict(configuration=existing)))
    existing['requirements'][0]['resources'][0]['amount']='120'
    save_case('共享容量超量',post(client,'/check',dict(configuration=existing)))
(ROOT/'outputs/core-closing/shared-browser.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
print(json.dumps(cases,ensure_ascii=False))
