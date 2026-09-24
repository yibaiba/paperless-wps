import {useState} from 'react';
import {useMutation, useQueryClient} from '@tanstack/react-query';
import {Alert, App, Button, Drawer, Select, Table} from 'antd';
import {EditorToolbar} from './EditorToolbar';
import {api} from '../../shared/api';
import {ProductDrawer} from '../catalog/ProductDrawer';
import type {AccessoryRule} from '../rules/types';
import {newRelation, type Relation, type SystemGroup, type Topology} from './types';
import {ProductPalette} from './ProductPalette';
import {DeviceEditor, GroupEditor, RelationEditor} from './ElementEditors';
import {DiagramDetails} from './DiagramDetails';
import {TopologyHistory} from './TopologyHistory';
import {useDrawing, type Operation} from './drawio/useDrawing';
import {useDrawio} from './drawio/useDrawio';

interface Props {initial?: Topology; onCreated: (id: string) => void; onClose: () => void}
export function TopologyEditor({initial, onCreated, onClose}: Props) {
  const canvas = useDrawing(initial);
  const {drawing, dirty, setDirty} = canvas;
  const [saved, setSaved] = useState(initial), [name, setName] = useState(initial?.name ?? '');
  const [actor, setActor] = useState(initial?.actor ?? '');
  const [detail, setDetail] = useState<string>(), [history, setHistory] = useState(false);
  const [panel, setPanel] = useState<'products' | 'business' | 'bindings'>();
  const [bindId, setBindId] = useState<string>(), [shape, setShape] = useState('device');
  const [expanded, setExpanded] = useState(true);
  const [selection, setSelection] = useState<{id: string; kind: string}>();
  const [groupDraft, setGroupDraft] = useState<SystemGroup>(), [relationDraft, setRelationDraft] = useState<Relation>();
  const {message, modal} = App.useApp();
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (xml: string) => api<Topology>(saved ? `/topologies/${saved.id}` : '/topologies', {
      method: saved ? 'PUT' : 'POST', body: JSON.stringify({name, actor, drawing_xml: xml,
        ...(saved ? {expected_revision: saved.revision} : {})}),
    }),
    onSuccess: (result, xml) => {
      setSaved(result);
      if (canvas.latest.current === xml) {setDirty(false); editor.saved();}
      client.setQueryData(['topology', result.id], result);
      client.invalidateQueries({queryKey: ['topologies']});
      message.success(`图纸与产品清单已保存，版本 v${result.revision}`);
      if (!saved) onCreated(result.id);
    },
  });
  const editor = useDrawio({xml: canvas.xml, onChange: canvas.change, onSave: xml => {
    if (!name.trim() || !actor.trim()) {message.error('请先填写方案名称和维护人'); return;}
    if (!save.isPending) save.mutate(xml);
  }});
  const closeElement = () => {setSelection(undefined); setGroupDraft(undefined); setRelationDraft(undefined);};
  const update = useMutation({
    mutationFn: async (operation: Operation) => {
      const result = await canvas.prepare(operation);
      editor.apply(result.drawing_xml);
      // Read back the actual editor document after applying the undoable business edit.
      return result;
    },
    onSuccess: (_, operation) => {
      closeElement();
      if (operation.action === 'add_product' && operation.bind_id) {setBindId(undefined); setPanel(undefined);}
    },
  });
  const convert = useMutation({
    mutationFn: (id: string) => api<AccessoryRule>(`/topologies/${saved!.id}/relations/${encodeURIComponent(id)}/rule`, {
      method: 'POST', body: JSON.stringify({expected_revision: saved!.revision, actor}),
    }),
    onSuccess: (rule, relationId) => {
      setSaved(previous => previous ? {...previous, rules: [...previous.rules,
        {relation_id: relationId, rule_id: rule.id, topology_revision: previous.revision}]} : previous);
      client.invalidateQueries({queryKey: ['rules']}); message.success('已生成草稿，可在「配套规则」编辑和试算');
    },
  });
  const editingDevice = selection?.kind === 'device' ? drawing.devices.find(d => d.id === selection.id) : undefined;
  const editingGroup = groupDraft ?? (selection?.kind === 'group' ? drawing.groups.find(g => g.id === selection.id) : undefined);
  const editingRelation = relationDraft ?? (selection?.kind === 'relation' ? drawing.relations.find(r => r.id === selection.id) : undefined);
  const removeElement = () => {if (selection) update.mutate({action: 'remove', id: selection.id});};
  const close = () => {
    if (!dirty) {onClose(); return;}
    modal.confirm({title: '离开会丢失尚未保存的修改', content: '请先保存，或确认放弃本次编辑。', okText: '放弃修改并离开', cancelText: '继续编辑', onOk: onClose});
  };
  const error = save.error?.message || update.error?.message || convert.error?.message || canvas.error || editor.error;
  const busy = update.isPending || save.isPending || convert.isPending;
  const ready = editor.ready && !busy;
  return <div className={`topology-workspace${expanded ? ' topology-expanded' : ''}`}>
    <EditorToolbar name={name} actor={actor} dirty={dirty} revision={saved?.revision} expanded={expanded}
      ready={ready} busy={busy} saving={save.isPending} devices={drawing.devices.length} unbound={drawing.unbound_shapes.length}
      canRelate={drawing.devices.length >= 2 && !canvas.error} onInfo={info => {setName(info.name); setActor(info.actor); setDirty(true);}}
      onBack={close} onSave={() => save.mutate(canvas.latest.current)} onExpand={() => setExpanded(!expanded)} onHistory={() => setHistory(true)}
      onProducts={() => {setBindId(undefined); setPanel('products');}} onBusiness={() => setPanel('business')} onBindings={() => setPanel('bindings')}
      onGroup={() => setGroupDraft({id: crypto.randomUUID(), name: '', product_line: '', position: {x: 40, y: 40}, width: 600, height: 360})}
      onRelation={() => setRelationDraft(newRelation(drawing.devices[0].id, drawing.devices[1].id))}/>
    {error ? <Alert type="error" showIcon title={error} className="section-bottom"/> : null}
    <div className={`drawio-shell${busy ? ' drawio-busy' : ''}`}>
      {!editor.ready && !editor.error ? <div className="drawio-loading">正在载入本地绘图工作台…</div> : null}
      <iframe inert={busy} ref={editor.frame} src={editor.src} title="方案图纸编辑器" className="drawio-frame"/>
      {busy ? <div className="drawio-loading">正在同步图纸与业务数据…</div> : null}
    </div>
    <div className="topology-status"><span>{drawing.groups.length} 个系统<span className="topology-status-divider">/</span>{drawing.devices.length} 个产品<span className="topology-status-divider">/</span>{drawing.relations.length} 条关系</span><span>图形绑定产品后参与清单</span></div>
    <Drawer title={bindId ? '为图形绑定产品' : '添加产品到主图'} open={panel === 'products'} onClose={() => setPanel(undefined)} size={400}>
      {!bindId ? <Select disabled={busy} aria-label="设备外观" className="topology-full section-bottom" value={shape} onChange={setShape} options={[
        {value: 'device', label: '服务器 / 主机'}, {value: 'terminal', label: '桌面终端'}, {value: 'switch', label: '交换设备'}, {value: 'rack', label: '机柜'},
      ]}/> : <Alert className="section-bottom" type="info" title="保留现有图形样式，绑定所选产品；数量可在产品面板维护。"/>}
      <ProductPalette key={bindId ?? 'add'} binding={!!bindId} busy={!ready} onAdd={async productIds => {
        await update.mutateAsync(bindId
          ? {action: 'add_product', product_id: productIds[0], shape, bind_id: bindId}
          : {action: 'add_products', product_ids: productIds, shape});
        message.success(bindId ? '产品已绑定' : `已添加 ${productIds.length} 个产品，可继续选择`);
      }} onDetail={setDetail}/>
    </Drawer>
    <Drawer title="产品配置与业务关系" open={panel === 'business'} onClose={() => setPanel(undefined)} size={1040}>
      <div className={busy ? 'topology-busy' : ''}><DiagramDetails diagram={drawing} models={drawing.products} saved={saved} dirty={dirty || canvas.checking || !!canvas.error}
        onEdit={(id, kind) => setSelection({id, kind})} onConvert={id => convert.mutate(id)} converting={convert.isPending}/></div>
    </Drawer>
    <Drawer title="图形与产品绑定" open={panel === 'bindings'} onClose={() => setPanel(undefined)} size={640}>
      <Alert type="info" showIcon title="服务器、屏幕等图形可绑定产品；文字和装饰框可保持未绑定。"
        description={`当前另有 ${drawing.drawing_only_edges.length} 条普通连线；两端绑定产品后，会以「待确认」关系进入业务面板。`} className="section-bottom"/>
      <Table rowKey="id" size="small" dataSource={drawing.unbound_shapes} columns={[
        {title: '图形', dataIndex: 'label', render: value => <span className="drawing-shape-label">{value}</span>}, {title: '页面', dataIndex: 'page'},
        {title: '操作', render: (_, item) => <Button onClick={() => {setBindId(item.id); setPanel('products');}}>绑定产品</Button>},
      ]}/>
    </Drawer>
    {editingGroup ? <GroupEditor key={editingGroup.id} group={editingGroup} onSave={group => update.mutate({action: 'group', group})} onClose={closeElement} onDelete={groupDraft ? undefined : removeElement}/> : null}
    {editingDevice ? <DeviceEditor key={editingDevice.id} device={editingDevice} groups={drawing.groups} model={drawing.products[editingDevice.product_id].model}
      onClose={closeElement} onSave={device => update.mutate({action: 'device', device})} onDelete={removeElement} onDetail={() => setDetail(editingDevice.product_id)}/> : null}
    {editingRelation ? <RelationEditor key={editingRelation.id} relation={editingRelation} diagram={drawing} models={drawing.products} onClose={closeElement}
      onSave={relation => update.mutate({action: 'relation', relation})} onDelete={relationDraft ? undefined : removeElement}/> : null}
    <ProductDrawer id={detail} onClose={() => setDetail(undefined)}/>
    {history && saved ? <TopologyHistory id={saved.id} onClose={() => setHistory(false)}/> : null}
  </div>;
}
