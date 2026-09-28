import { useEffect, useMemo, useState } from 'react';
import { Alert, App, Button, Drawer, Input, Modal, Select, Space, Spin, Typography } from 'antd';
import { PriceForm } from '../QuotationForms';
import type { QuotationOutput } from '../types';
import { ProjectCandidates } from '../../ProjectCandidates';
import { SupplyEditor } from '../../projects/SupplyPanel';
import { sheetRows, PRICE_COLUMN, isDeviceRow, rowDeviceId, type SortOrder } from './model';
import { useSheetEditing, type SheetContext } from './useSheetEditing';
import { BatchPreview } from './BatchPreview';
import { SheetDetails } from './SheetDetails';
import './sheet.css';

import SheetEditor from './SheetEditor';
import { ImportDialog } from '../importing/ImportDialog';
import { TemplateHeader } from './TemplateHeader';
import { DeviceSettings } from './DeviceSettings';
export interface SheetControls extends SheetContext {
  onUndo: () => void; onRedo: () => void; canUndo: boolean; canRedo: boolean;
}
export default function QuotationSheet(props: SheetControls & { output?: QuotationOutput | null; stale: boolean }) {
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [showDetails, setShowDetails] = useState(false);
  const [sort, setSort] = useState<SortOrder>('original'), [selected, setSelected] = useState<string[]>([]);
  const [priceOpen, setPriceOpen] = useState(false), [price, setPrice] = useState('');
  const [settingsId, setSettingsId] = useState<string>();
  const [replacementId, setReplacementId] = useState<string>();
  const [priceDeviceId, setPriceDeviceId] = useState<string>();
  const [supplyId, setSupplyId] = useState<string>();
  const editor = useSheetEditing({ ...props, reviewing: importOpen }), { message } = App.useApp();
  useEffect(() => {
    const ids = new Set(props.configuration.devices.map((device) => device.id));
    setSelected((current) => current.every((id) => ids.has(id)) ? current : current.filter((id) => ids.has(id)));
  }, [props.configuration.devices]);
  const rows = useMemo(() => sheetRows(props.configuration, props.output, sort), [props.configuration, props.output, sort]);
  const settingsDevice = props.configuration.devices.find((item) => item.id === settingsId);
  const replacement = props.configuration.devices.find((item) => item.id === replacementId);
  const priceDevice = props.configuration.devices.find((item) => item.id === priceDeviceId);
  const supplyDevice = props.configuration.devices.find((item) => item.id === supplyId);
  return <Space orientation="vertical" style={{ width: '100%' }}>
    <Space wrap>
      <Button disabled={!props.canUndo || editor.busy || !!editor.pending} onClick={props.onUndo}>撤销编辑</Button>
      <Button disabled={!props.canRedo || editor.busy || !!editor.pending} onClick={props.onRedo}>重做编辑</Button>
      <Select aria-label="工作表排序" value={sort} style={{ width: 150 }} disabled={editor.busy || !!editor.pending} onChange={setSort}
        options={[{ value: 'original', label: '模板分区顺序' }, { value: 'name', label: '按产品名称排序' }]} />
      <Button disabled={!selected.length || !props.configuration.quotation || editor.busy || !!editor.pending} onClick={() => { setPrice(''); setPriceOpen(true); }}>批量调整单价（{selected.length}）</Button>
      <Button disabled={!props.configuration.quotation || editor.busy || !!editor.pending} onClick={() => { editor.resetPreview(); setImportText(''); setImportOpen(true); }}>导入 / 粘贴清单</Button>
      <Button onClick={() => setShowDetails((value) => !value)}>{showDetails ? '收起业务与来源' : '业务与来源'}</Button>
      <Typography.Text type="secondary">双击编辑产品说明、采购数量、单价或备注；整行 Excel 清单请用“导入 / 粘贴清单”。Ctrl / ⌘ Z 撤销。</Typography.Text>
    </Space>
    {editor.error && !editor.pending ? <Alert type="error" title={editor.error} /> : null}
    {!props.output ? <Alert type="info" title="请先检查并计算报价，生成与导出一致的产品明细" /> : null}
    <TemplateHeader quotation={props.configuration.quotation} />
    <div className={`quotation-sheet-workspace${showDetails ? '' : ' quote-sheet-wide'}`}>
      <Spin spinning={editor.busy}>
          <SheetEditor rows={rows} busy={editor.busy || !!editor.pending || importOpen} onImport={(text) => { editor.resetPreview(); setImportText(text); setImportOpen(true); }} onEdit={editor.edit} onSelect={setSelected}
            onError={(text) => { void message.error(text); }} onUndo={props.onUndo} onRedo={props.onRedo} />
      </Spin>
      <div className="quote-business-panel">
      <Select aria-label="选择配置设备" showSearch optionFilterProp="label" value={selected[0]} placeholder="查看全部部署 / 已有设备" style={{ width: '100%' }}
        onChange={(id) => setSelected([id])} options={props.configuration.devices.map((device) => ({ value: device.id, label: device.name }))} />
      <SheetDetails configuration={props.configuration} output={props.output} stale={props.stale} busy={editor.busy || !!editor.pending}
        selected={selected[0]} selectionCount={selected.length} onSupply={setSupplyId} onPrice={setPriceDeviceId} onProduct={setReplacementId} onSettings={setSettingsId} onRestoreDescription={(id) => { void editor.execute([{ action: 'description_set', device_id: id, text: null }], true); }} />
      </div>
    </div>
    <footer className="quote-template-footer"><strong>报价合计：{props.output?.total ?? '待确认'}</strong><span>{props.configuration.quotation?.tax_terms}</span></footer>
    {settingsDevice ? <DeviceSettings device={settingsDevice} section={props.configuration.quotation?.sections[settingsDevice.id] ?? ''} busy={editor.busy}
      onClose={() => setSettingsId(undefined)} onApply={(operations) => { void editor.execute(operations, true); setSettingsId(undefined); }} /> : null}
    {importOpen ? <ImportDialog configuration={props.configuration} editor={editor} initialText={importText} onClose={() => { editor.resetPreview(); setImportOpen(false); }} /> : null}
    {editor.pending ? <BatchPreview editor={editor} rows={rows} /> : null}
    <Modal open={priceOpen} title="批量设置报价单价" onCancel={() => setPriceOpen(false)} onOk={() => {
      editor.edit(rows.flatMap((row, index) => isDeviceRow(row) && selected.includes(rowDeviceId(row)) ? [{ deviceId: rowDeviceId(row), row: index + 1, column: PRICE_COLUMN, value: price }] : []), true);
      setPriceOpen(false);
    }}>
      <Input aria-label="批量单价" value={price} onChange={(event) => setPrice(event.target.value)} placeholder="输入非负单价；下一步填写共同依据" />
    </Modal>
    {replacement ? <Drawer open title="产品换型" size={680} onClose={() => setReplacementId(undefined)}>
      <Alert type="info" title="替换同一设备的产品，保留部署数量与系统引用。原单价会标记过期；请明确新产品供货来源。" />
      <ProjectCandidates configuration={props.configuration} replacement={replacement}
        requirement={props.configuration.requirements.find((item) => item.device_id === replacement.id)} busy={editor.busy}
        onSelect={(chosen, _existing, supply) => {
          const value = { id: replacement.id, name: chosen.name, variant_id: chosen.variant_id, source_id: chosen.source_id,
            quantity: replacement.quantity, kind: chosen.kind, note: replacement.note };
          void editor.execute([{ action: 'device_put', value }, { action: 'supply_set', device_id: replacement.id,
            allocations: supply ? [{ id: crypto.randomUUID(), device_id: replacement.id, quantity: replacement.quantity, ...supply }] : [] }], true);
          setReplacementId(undefined);
        }} />
    </Drawer> : null}
    {priceDevice && props.configuration.quotation ? <PriceForm device={priceDevice} quotation={props.configuration.quotation}
      onClose={() => setPriceDeviceId(undefined)} onApply={(quotation) => {
        const value = quotation.prices.find((item) => item.device_id === priceDevice.id);
        if (!value) { void message.error('未收到该设备的报价信息'); return; }
        void editor.execute([{ action: 'price_set', value }, { action: 'section_set', device_id: priceDevice.id, section: quotation.sections[priceDevice.id] ?? '' }], true);
        setPriceDeviceId(undefined);
      }} /> : null}
    {supplyDevice ? <SupplyEditor deviceId={supplyDevice.id} name={supplyDevice.name}
      initial={(props.configuration.supply_allocations ?? []).filter((item) => item.device_id === supplyDevice.id)}
      onClose={() => setSupplyId(undefined)} onSave={(allocations) => {
        void editor.execute([{ action: 'supply_set', device_id: supplyDevice.id, allocations }], true);
        setSupplyId(undefined);
      }} /> : null}
  </Space>;
}
