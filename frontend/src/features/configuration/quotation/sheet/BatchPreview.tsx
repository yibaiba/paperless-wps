import { useState } from 'react';
import { Alert, Button, Input, Modal, Space, Table, Typography } from 'antd';
import { address, columns, PRICE_COLUMN, type SheetRow } from './model';
import { reviewRows } from './batchReview';
import type { useSheetEditing } from './useSheetEditing';

type Editor = ReturnType<typeof useSheetEditing>;
export function BatchPreview({ editor, rows }: { editor: Editor; rows: SheetRow[] }) {
  const [evidence, setEvidence] = useState('');
  const hasPrices = editor.pending?.edits.some((edit) => edit.column === PRICE_COLUMN);
  return <Modal open title="核对并应用工作表修改" width={960} onCancel={editor.cancel} mask={{ closable: false }} footer={<Space>
    <Button disabled={editor.busy} onClick={editor.cancel}>取消</Button>
    <Button loading={editor.busy} onClick={() => editor.prepare(evidence)}>检查本批修改</Button>
    <Button type="primary" disabled={!editor.preview || editor.busy} onClick={editor.apply}>整批应用</Button>
  </Space>}>
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Typography.Text>核对产品及修改前后值，可直接修正新值后重新检查。整批应用只产生一次撤销记录；采购数量修改不会改变部署数量、已有数量或待定供货；超量或未分配会显示在检查结果中。</Typography.Text>
      <Table size="small" rowKey={(item) => `${item.deviceId}-${item.column}`} pagination={{ pageSize: 6 }}
        dataSource={reviewRows(editor.pending?.edits ?? [], rows)} scroll={{ x: 760 }} columns={[
          { title: '产品 / 型号', render: (_, item) => <><div>{item.name}</div><Typography.Text type="secondary">{item.model}</Typography.Text></>, width: 190 },
          { title: '字段', render: (_, item) => <>{columns[item.column].title}<div>{address(item.row, item.column)}</div></>, width: 120 },
          { title: '原值', dataIndex: 'previous', render: (value: string) => <span className="batch-review-value">{value || '（空）'}</span>, width: 180 },
          { title: '新值（可修改）', render: (_, item) => <Input.TextArea aria-label={`${address(item.row, item.column)} 新值`}
            autoSize={{ minRows: 1, maxRows: 4 }} disabled={editor.busy} value={item.value} onChange={(event) => editor.revise({ ...item, value: event.target.value })} /> },
        ]} />
      {hasPrices ? <Input.TextArea aria-label="本批单价调整依据" placeholder="本批单价共同调整依据（必填）" disabled={editor.busy} value={evidence}
        onChange={(event) => { setEvidence(event.target.value); editor.resetPreview(); }} /> : null}
      {editor.error ? <Alert type="error" title={editor.error} /> : null}
      {editor.preview ? <Alert type="info" title={`检查完成 · ${editor.preview.changes.length} 项变化`}
        description={<>
          <div>报价合计：{editor.preview.checked.quotation_output?.total ?? '待确认'}</div>
          <div>已知金额小计：{editor.preview.checked.quotation_output?.known_subtotal ?? '未设置报价'}</div>
          {editor.preview.checked.quotation_output?.issues.map((issue) => <div key={`${issue.device_id}-${issue.message}`}>{issue.message}</div>)}
          <div>项目检查：{editor.preview.checked.readiness.counts.conflicts} 项冲突、{editor.preview.checked.readiness.counts.unknowns} 项资料不足、{editor.preview.checked.readiness.counts.open_accessories} 项待补配套。应用后可在项目检查区查看依据。</div>
          <div>有资料缺口仍可应用并保存草稿，不表示业务搭配已确认。</div>
        </>} /> : null}
    </Space>
  </Modal>;
}
