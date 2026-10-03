import { Alert, Button, Card, Form, Select, Space, Typography } from 'antd';
import type { Knowledge, Variant } from '../types';
import { useKnowledge, variantOptions } from '../shared';
import { useDefinitions } from './useDefinitions';

type Combination = NonNullable<Knowledge['combination']>;
export function CombinationFields({ variants }: { variants?: Variant[] }) {
  return <Form.Item name="combination" label="组合要求" rules={[{ required: true, message: '请选择组合类型与需求' }]}>
    <CombinationEditor variants={variants} />
  </Form.Item>;
}
function CombinationEditor({ value, onChange, variants }: {
  value?: Combination; onChange?: (value: Combination) => void; variants?: Variant[];
}) {
  const definitions = useDefinitions(), knowledge = useKnowledge();
  const targets = value?.targets ?? [];
  const update = (patch: Partial<Combination>) => onChange?.({ mode: 'require_all', scope: null, targets, ...value, ...patch });
  const roleOptions = definitions.data?.definitions.flatMap(d => d.roles.map(r => ({
    value: JSON.stringify([d.id, r.id, '']), label: `${d.name} / ${r.name}`, name: r.name,
  }))) ?? [];
  const needOptions = (knowledge.data ?? []).filter(k => k.kind === 'accessory' && k.need_key).map(k => ({
    value: JSON.stringify([k.system_definition_id, k.role_id, k.need_key]),
    label: `${k.system || '通用'} / ${k.need_name || k.name}（配套）`, name: k.need_name || k.name,
  }));
  const options = [...new Map([...roleOptions, ...needOptions].map(o => [o.value, o])).values()];
  return <Space orientation="vertical" style={{ width: '100%' }}>
    <Alert type="info" showIcon title="组合条件只检查明确关联的需求" description="不同需求项可以都需要，单项中的多个型号互为候选。数量沿用角色或配套依据，未知数量不会默认为一件。" />
    {definitions.error || knowledge.error ? <Alert type="error" title={definitions.error?.message ?? knowledge.error?.message} /> : null}
    <Space wrap>
      <Select aria-label="组合类型" style={{ width: 220 }} placeholder="选择组合类型" value={value?.mode} onChange={mode => update({ mode })}
        options={[{ value: 'exclude', label: '不能同时选用（互斥）' }, { value: 'require_all', label: '以下每项需求都必须满足' }, { value: 'require_any', label: '以下至少一项需求满足' }]} />
      <Select aria-label="组合范围" style={{ width: 180 }} placeholder="选择检查范围" value={value?.scope ?? undefined} onChange={scope => update({ scope })}
        options={[{ value: 'system', label: '同一系统实例' }, { value: 'room', label: '同一房间' }, { value: 'project', label: '整个项目' }]} />
    </Space>
    {targets.map((target, index) => <Card key={target.id} size="small" title={`需求 ${index + 1}`} extra={<Button danger type="text" onClick={() => update({ targets: targets.filter(t => t.id !== target.id) })}>移除</Button>}>
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Select aria-label={`组合需求 ${index + 1}`} style={{ width: '100%' }} showSearch optionFilterProp="label" placeholder="选择已有角色或配套需求" options={options}
          value={target.role_id || target.need_key ? JSON.stringify([target.system_definition_id, target.role_id, target.need_key]) : undefined}
          onChange={(key, option) => { const [system_definition_id, role_id, need_key] = JSON.parse(key) as string[];
            update({ targets: targets.map(t => t.id === target.id ? { ...t, system_definition_id, role_id, need_key, name: (option as { name: string }).name } : t) }); }} />
        <Select aria-label={`需求 ${index + 1} 候选配置`} style={{ width: '100%' }} mode="multiple" showSearch optionFilterProp="label" placeholder="限定候选配置（可留空，沿用原需求）"
          value={target.variant_ids} options={variantOptions(variants)} onChange={variant_ids => update({ targets: targets.map(t => t.id === target.id ? { ...t, variant_ids } : t) })} />
      </Space>
    </Card>)}
    <Button onClick={() => update({ targets: [...targets, { id: crypto.randomUUID(), name: '待选择需求', system_definition_id: '', role_id: '', need_key: '', variant_ids: [] }] })}>添加需求项</Button>
    <Typography.Text type="secondary">缺少范围、目标或数量依据时保留待确认。发布不会让未知搭配自动通过。</Typography.Text>
  </Space>;
}
