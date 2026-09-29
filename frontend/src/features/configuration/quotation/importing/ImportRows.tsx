import { Button, Checkbox, Input, Select, Space, Table, Typography } from 'antd';
import { matchingChoices, type Choice, type ImportRow } from './model';
export function ImportRows({ rows, choices, onChange }: { rows: ImportRow[]; choices: Choice[]; onChange: (rows: ImportRow[]) => void }) {
  const update = (row: ImportRow, patch: Partial<ImportRow>) => onChange(rows.map((r) => r.id === row.id ? { ...r, ...patch } : r));
  const input = (row: ImportRow, field: 'quantity' | 'price' | 'note' | 'section' | 'unit') => <Input aria-label={`第${row.sourceRow}行${field}`} value={row[field]} onChange={(e) => update(row, { [field]: e.target.value })} />;
  return <Space orientation="vertical" style={{ width: '100%' }}>
    <Space wrap><Button onClick={() => onChange(rows.map((row) => {
      const found = matchingChoices(row, choices); return row.include && found.length === 1 ? { ...row, choice: found[0].key } : row;
    }))}>采用唯一型号候选</Button><Typography.Text type="secondary">多个版本或多个来源仍需逐行选择；相同型号的多行分别创建独立设备。</Typography.Text></Space>
    <Table rowKey="id" size="small" dataSource={rows} pagination={{ pageSize: 8 }} scroll={{ x: 1550 }} columns={[
      { title: '导入', width: 65, render: (_, row) => <Checkbox aria-label={`导入第${row.sourceRow}行`} checked={row.include} onChange={(e) => update(row, { include: e.target.checked })} /> },
      { title: '原表', width: 190, render: (_, row) => <><div>第 {row.sourceRow} 行 · {row.name}</div><div>{row.model} / {row.unit}</div>{row.mergedNoteRange ? <Typography.Text type="secondary">共享备注：{row.mergedNoteRange}</Typography.Text> : null}</> },
      { title: '选择配置与来源（必选）', width: 370, render: (_, row) => {
        const exact = matchingChoices(row, choices), rest = choices.filter((c) => !exact.includes(c));
        return <Select aria-label={`第${row.sourceRow}行产品配置`} showSearch optionFilterProp="label" style={{ width: '100%' }} value={row.choice || undefined}
          placeholder={exact.length ? `${exact.length} 个同型号来源，请确认版本` : '未匹配，搜索产品库'} onChange={(choice) => update(row, { choice })}
          options={[...exact, ...rest].map((c) => ({ value: c.key, label: c.label }))} />;
      } },
      { title: '类型', width: 115, render: (_, row) => <Select value={row.kind || undefined} placeholder="请选择" style={{ width: 100 }} onChange={(kind) => update(row, { kind })} options={['hardware', 'software', 'license', 'accessory'].map((value, i) => ({ value, label: ['硬件', '软件', '授权', '配件'][i] }))} /> },
      { title: '单位', width: 110, render: (_, row) => <>{input(row, 'unit')}<small>产品库：{choices.find((c) => c.key === row.choice)?.unit || '未提供'}</small></> },
      { title: '采购量', width: 100, render: (_, row) => input(row, 'quantity') },
      { title: '导入单价', width: 110, render: (_, row) => input(row, 'price') },
      { title: '分区', width: 130, render: (_, row) => input(row, 'section') },
      { title: '项目说明（不改产品库）', width: 260, render: (_, row) => <Input.TextArea aria-label={`第${row.sourceRow}行说明`} autoSize={{ minRows: 2, maxRows: 5 }} value={row.description} onChange={(e) => update(row, { description: e.target.value })} /> },
      { title: '备注', width: 160, render: (_, row) => input(row, 'note') },
    ]} expandable={{ expandedRowRender: (row) => <div style={{ whiteSpace: 'pre-wrap' }}>原表内容：{row.raw.map((value, index) => value ? `第${index + 1}列：${value}` : '').filter(Boolean).join('\n')}<hr />产品库原始参数：{choices.find((c) => c.key === row.choice)?.specification ?? '先选择配置'}</div> }} />
  </Space>;
}
