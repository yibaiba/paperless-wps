from .test_proposal_generation import apply, plan, read, write, call
from .test_proposal_evolution import two_systems
from .test_proposal_prices_and_cycles import priced
from .conftest import AUTHOR


def test_regeneration_preserves_manual_fulfilled_role_binding(client, catalog):
    draft = two_systems(client, catalog)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)['configuration']
    roles = [r for r in data['requirements'] if r['role_id'] == 'server']
    changed = dict(roles[0], device_id=roles[1]['device_id'])
    draft = write(client, draft, [dict(action='requirement_put', value=changed)])
    before = read(client, draft)['configuration']
    assert next(r for r in before['requirements'] if r['id'] == changed['id'])['device_id'] == changed['device_id']
    draft = apply(client, draft, plan(client, draft))
    after = read(client, draft)['configuration']
    actual = next(r for r in after['requirements'] if r['id'] == changed['id'])
    assert actual['device_id'] == changed['device_id'], 'Manually changed server association was silently reset'


def test_pending_interpretation_survives_apply_check_and_confirmation(client, catalog, project):
    draft = priced(client, catalog, amount='10')
    data = read(client, draft)['configuration']
    generation = dict(data['generation'], sources=[dict(id='unresolved', object_id='system', field='inputs.seats', kind='agent_interpretation', confirmed=False, quote='客户可能要求48席，尚待确认')])
    draft = write(client, draft, [dict(action='requirements_patch', generation=generation)])
    proposal = plan(client, draft)
    questions = call(client, 'list_get', dict(draft_id=draft['id'], proposal_id=proposal['proposal_id'], option_id=proposal['option']['id'], view='proposal_questions'))
    assert any(q['code'] == 'interpretation_unconfirmed' for q in questions['items'])
    draft = apply(client, draft, proposal)
    actual = read(client, draft)
    url='/api/configuration/projects/'+project['id']
    saved=client.put(url,json=dict(expected_revision=0,configuration=actual['configuration']))
    assert saved.status_code == 200, saved.text
    response=client.post(url+'/confirm',json=dict(expected_revision=1,fingerprint=saved.json()['fingerprint'],**AUTHOR))
    assert response.status_code == 422, f'Unresolved interpretation was confirmed; ready={actual["checked"]["readiness"]}, HTTP={response.status_code}'


def test_regeneration_preserves_manual_allocation_evidence(client, catalog):
    draft=two_systems(client,catalog)
    draft=apply(client,draft,plan(client,draft))
    data=read(client,draft)['configuration']
    allocation=data['accessory_allocations'][0]
    changed=dict(allocation,quantity='0.5',evidence='维护者核对：本次只确认一部分分配')
    draft=write(client,draft,[dict(action='accessory_remove',allocation_id=allocation['id']),dict(action='accessory_link',value=changed)])
    assert next(a for a in read(client,draft)['configuration']['accessory_allocations'] if a['id']==allocation['id']) == changed
    draft=apply(client,draft,plan(client,draft))
    after=read(client,draft)['configuration']
    assert next(a for a in after['accessory_allocations'] if a['id']==allocation['id']) == changed, 'Manual allocation evidence was overwritten'
