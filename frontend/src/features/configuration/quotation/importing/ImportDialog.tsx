import { SystemForm } from "../../projects/forms/SystemForm";
import { ImportAssignment } from "./ImportAssignment";
import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, ConfigProvider, Input, InputNumber, Modal, Select, Space, Spin, Typography, Upload } from 'antd';
import { api } from '../../../../shared/api';
import type { Variant, Configuration } from '../../types';
import type { useSheetEditing } from '../sheet/useSheetEditing';
import { parseClipboard } from '../sheet/model';
import { catalogChoices, detectHeader, detectMapping, fields, importOperations, mappedRows, type ImportRow, type Mapping } from './model';
import { ImportRows } from './ImportRows';
import { withMergedNotes, type MergedRegion } from './mergedNotes';

type Workbook = { sheets: { name: string; rows: string[][]; merges?: MergedRegion[] }[] };
export function ImportDialog({ editor, initialText, onClose, configuration }: {
  configuration: Configuration;
  editor: ReturnType<typeof useSheetEditing>; initialText?: string; onClose: () => void;
}) {
  const [staged, setStaged] = useState(configuration), [systemOpen, setSystemOpen] = useState(false);
  const [book, setBook] = useState<Workbook>(), [sheet, setSheet] = useState(0), [header, setHeader] = useState(0);
  const [mapping, setMapping] = useState<Mapping>({}), [rows, setRows] = useState<ImportRow[]>([]);
  const [variants, setVariants] = useState<Variant[]>([]), [loading, setLoading] = useState(false);
  const [error, setError] = useState(''), [text, setText] = useState(initialText ?? ''), [evidence, setEvidence] = useState('');
  const [pricesConfirmed, setPricesConfirmed] = useState(false);
  const choices = useMemo(() => catalogChoices(variants), [variants]);
  const matrix = book?.sheets[sheet]?.rows ?? [];
  const merges = book?.sheets[sheet]?.merges ?? [];
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api<Variant[]>('/configuration/variants', { signal: controller.signal }).then(setVariants)
      .catch((cause) => { if (!controller.signal.aborted) setError(String(cause)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  const reset = () => { editor.resetPreview(); setError(''); };
  const selectSheet = (value: Workbook, index: number) => {
    const cells = value.sheets[index].rows, found = detectHeader(cells);
    setBook(value); setSheet(index); setHeader(found); setMapping(detectMapping(cells[found] ?? [])); setRows([]); reset();
  };
  const upload = async (file: File) => {
    setLoading(true); setError(''); setBook(undefined); setRows([]); editor.resetPreview();
    try {
      const body = new FormData(); body.append('file', file);
      const result = await api<Workbook>('/quotation/import-cells', { method: 'POST', body });
      if (!result.sheets.length) throw new Error('文件没有工作表');
      selectSheet(result, 0); setEvidence(`导入 ${file.name}`); setPricesConfirmed(false);
    } catch (cause) { setError(String(cause)); }
    finally { setLoading(false); }
  };
  const prepare = () => {
    reset();
    try {
      if (!pricesConfirmed) throw new Error('请确认导入单价采用本报价含税含运口径；不同口径请先修正单价。');
      const operations = importOperations(rows, { choices, evidence: `${evidence}；工作表：${book?.sheets[sheet]?.name ?? '粘贴清单'}；已确认含税含运口径`, configuration: staged, newId: () => crypto.randomUUID() });
      const additions = [
        ...staged.rooms.filter((r) => !configuration.rooms.some((old) => old.id === r.id)).map((value) => ({ action: 'room_put' as const, value })),
        ...staged.systems.filter((r) => !configuration.systems.some((old) => old.id === r.id)).map((value) => ({ action: 'system_put' as const, value })),
      ];
      void editor.execute([...additions, ...operations], false);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  };
  return <Modal open title="从 Excel 导入 / 粘贴清单" width="94vw" styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }} mask={{ closable: false }} closable={!loading && !editor.busy}
    onCancel={onClose} footer={<Space><Button disabled={loading || editor.busy} onClick={onClose}>取消</Button>
      <Button disabled={loading || !rows.length} loading={editor.busy} onClick={prepare}>检查所选明细</Button>
      <Button type="primary" disabled={!editor.preview || loading || editor.busy} onClick={() => { if (editor.apply()) onClose(); }}>整批加入清单</Button></Space>}>
    <ConfigProvider componentDisabled={loading || editor.busy}><Spin spinning={loading}><Space orientation="vertical" style={{ width: '100%' }}>
      <Alert type="info" title="导入本次采购清单，不导入 Excel 版式或公式" description="新增明细创建独立设备，部署量初始等于采购量；也可明确关联已有设备，仅建立用途。不会按型号合并或推定系统搭配。金额重新计算，空单价保留待确认。" />
      <Space><Upload accept=".xlsx" showUploadList={false} beforeUpload={(file) => { void upload(file); return false; }}><Button>选择 XLSX 工作簿</Button></Upload>
        <Typography.Text type="secondary">也可以复制 Excel 的表头和明细，粘贴到下方。</Typography.Text></Space>
      <Input.TextArea aria-label="粘贴 Excel 清单" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="名称　型号　产品说明　数量　单位　单价　备注" />
      <Button onClick={() => { try { selectSheet({ sheets: [{ name: '粘贴清单', rows: parseClipboard(text) }] }, 0); setEvidence('Excel 粘贴清单'); setPricesConfirmed(false); } catch (cause) { setError(String(cause)); } }}>读取粘贴内容</Button>
      {book ? <>
        <Space wrap><Select aria-label="选择工作表" value={sheet} style={{ width: 240 }} onChange={(index) => selectSheet(book, index)} options={book.sheets.map((s, value) => ({ value, label: s.name }))} />
          <Typography.Text>表头行（0 表示无表头）</Typography.Text><InputNumber aria-label="表头行" min={0} max={Math.max(1, matrix.length)} value={header + 1} onChange={(value) => { const h = Number(value ?? 1) - 1; setHeader(h); setMapping(detectMapping(matrix[h] ?? [])); setRows([]); reset(); }} />
          <Typography.Text>共 {matrix.length} 行</Typography.Text></Space>
        <Space wrap>{fields.map(([key, label]) => <label key={key}>{label} <Select allowClear aria-label={`${label}对应列`} value={mapping[key]} style={{ width: 135 }}
          options={Array.from({ length: matrix.reduce((maximum, row) => Math.max(maximum, row.length), 0) }, (_, value) => ({ value, label: `第${value + 1}列 ${matrix[header]?.[value] ?? ''}` }))}
          onChange={(value) => { setMapping((m) => ({ ...m, [key]: value })); setRows([]); reset(); }} /></label>)}</Space>
        {merges.length ? <Alert type="info" title={`原表含 ${merges.length} 个合并区域`} description={<>
          <div>纵向单列备注会带入对应明细并标明出处，请逐行核对。数量、单价及跨列内容保留原值，不自动复制或拆分。</div>
          <Typography.Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开合并范围' }}>{merges.map((region) => region.range).join('、')}</Typography.Paragraph>
        </>} /> : null}
        <Button onClick={() => { setRows(withMergedNotes(mappedRows(matrix, header, mapping), { matrix, header, mapping, merges })); reset(); }}>生成逐行核对表</Button>
      </> : null}
      {rows.length ? <ImportRows rows={rows} choices={choices} onChange={(value) => { setRows(value); reset(); }} /> : null}
      {systemOpen ? <SystemForm configuration={staged} onApply={(next) => { setStaged(next); reset(); }} onClose={() => setSystemOpen(false)} /> : null}
      {rows.length ? <Button onClick={() => setSystemOpen(true)}>本批新增房间 / 系统</Button> : null}
      {rows.length ? <ImportAssignment rows={rows} configuration={staged} onChange={(value) => { setRows(value); reset(); }} /> : null}
      <Input.TextArea aria-label="导入依据" value={evidence} onChange={(e) => { setEvidence(e.target.value); reset(); }} placeholder="清单来源、价格采用依据" />
      <Select aria-label="导入价格口径确认" value={pricesConfirmed} style={{ width: '100%' }} onChange={(value) => { setPricesConfirmed(value); reset(); }}
        options={[{ value: false, label: '价格口径待确认（可继续核对，不能应用）' }, { value: true, label: '已核对：填写的单价符合本报价含税含运说明，缺价保留待确认' }]} />
      {error || editor.error ? <Alert type="error" title={error || editor.error} /> : null}
      {editor.preview ? <Alert type="info" title={`预览：新增 ${rows.filter((r) => r.include && !r.existingDeviceId).length} 台/项独立设备记录；报价合计 ${editor.preview.checked.quotation_output?.total ?? '待确认'}`}
        description={<><div>已知金额小计：{editor.preview.checked.quotation_output?.known_subtotal}。资料不足仍可保存草稿。</div>
          <div>检查：{editor.preview.checked.readiness.counts.conflicts} 项冲突、{editor.preview.checked.readiness.counts.unknowns} 项资料不足、{editor.preview.checked.readiness.counts.open_accessories} 项待补配套。</div>
          {editor.preview.checked.quotation_output?.issues.map((item) => <div key={`${item.device_id}-${item.message}`}>{item.message}</div>)}</>} /> : null}
    </Space></Spin></ConfigProvider>
  </Modal>;
}
