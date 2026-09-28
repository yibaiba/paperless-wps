import { useEffect, useRef, useState } from 'react';
import { Alert } from 'antd';
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets';
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import zhCN from '@univerjs/preset-sheets-core/locales/zh-CN';
import '@univerjs/preset-sheets-core/lib/index.css';
import { columns, isDeviceRow, rowDeviceId } from './model';
import { bindSheetEvents, type SheetProps } from './sheetEvents';
import { applyProjection, diffProjection, initialProjection, snapshotRows } from './projection';
import { projectionPort, sdkCells } from './projectionAdapter';
import { rowLayout, updateRowLayout, DETAIL_HEIGHT } from './rowLayout';
import { startSheetMeasure } from './performance';

type Runtime = ReturnType<typeof createUniver>;
const layout = { titles: columns.map((column) => column.title), minimumRows: 30 };

export default function SheetEditor(props: SheetProps) {
  const host = useRef<HTMLDivElement>(null), latest = useRef(props);
  const runtime = useRef<Runtime | null>(null), projecting = useRef(false), failed = useRef(false);
  const previous = useRef(snapshotRows(props.rows));
  const [failure, setFailure] = useState('');
  latest.current = props;
  useEffect(() => {
    const container = document.createElement('div');
    container.style.height = '100%'; host.current!.appendChild(container);
    const subscriptions: { dispose: () => void }[] = [];
    let instance: Runtime | undefined;
    const dispose = () => {
      subscriptions.forEach((subscription) => subscription.dispose());
      runtime.current = null;
      // Univer owns a nested React root; dispose after the parent commit.
      queueMicrotask(() => { instance?.univer.dispose(); container.remove(); startSheetMeasure('dispose')(); });
    };
    try {
      const initialize = startSheetMeasure('initialize'), rendered = startSheetMeasure('rendered');
      const initial = initialProjection(latest.current.rows, layout);
      instance = createRuntime(container);
      const { univerAPI } = instance;
      subscriptions.push(univerAPI.addEvent(univerAPI.Event.LifeCycleChanged, ({ stage }) => {
        if (stage === univerAPI.Enum.LifecycleStages.Rendered) rendered({ rows: latest.current.rows.length });
      }));
      univerAPI.createWorkbook({ id: 'project-quotation', name: '项目清单与报价', sheetOrder: ['quotation'],
        sheets: { quotation: { id: 'quotation', name: '清单与报价', rowCount: initial.rowCount,
          columnCount: columns.length, defaultRowHeight: DETAIL_HEIGHT, ...rowLayout(latest.current.rows), cellData: sdkCells(initial.cells),
          columnData: Object.fromEntries(columns.map((column, index) => [index, { w: column.width }])),
          freeze: { startRow: 1, startColumn: 3, xSplit: 3, ySplit: 1 } } } });
      subscriptions.push(...bindSheetEvents(instance, { latest, projecting, failed }));
      previous.current = snapshotRows(latest.current.rows);
      runtime.current = instance;
      initialize({ rows: latest.current.rows.length, writes: 1, cells: initial.cellCount });
    } catch (error) { dispose(); throw error; }
    return dispose;
  }, []);
  useEffect(() => {
    const worksheet = runtime.current?.univerAPI.getActiveWorkbook()?.getActiveSheet();
    if (!worksheet || failed.current) return;
    const projection = startSheetMeasure('projection');
    const plan = diffProjection(previous.current, props.rows, layout);
    const selections = worksheet.getSelection()?.getActiveRangeList().map((range) => range.getRange()) ?? [];
    const selectedRows = previous.current.filter((row, i) => isDeviceRow(row) && selections.some((r) => i + 1 >= r.startRow && i + 1 <= r.endRow));
    const remainingIds = new Set(props.rows.map((row) => row.id));
    const selectionDeleted = selectedRows.some((row) => !remainingIds.has(row.id));
    projecting.current = true;
    let success = false;
    try {
      if (plan.reordered) updateRowLayout(runtime.current!, previous.current, true);
      applyProjection(plan, projectionPort(runtime.current!));
      if (plan.reordered) updateRowLayout(runtime.current!, props.rows);
      previous.current = snapshotRows(props.rows);
      success = true;
      if (plan.reordered) {
        if (selectionDeleted) {
          worksheet.getRange('A1').activate();
          latest.current.onSelect([]);
        } else {
          latest.current.onSelect(props.rows.filter((row, i) => isDeviceRow(row) && selections.some((r) => i + 1 >= r.startRow && i + 1 <= r.endRow)).map(rowDeviceId));
        }
      }
    } catch (error) {
      failed.current = true;
      const message = error instanceof Error ? error.message : String(error);
      setFailure(message); latest.current.onError(`工作表同步失败：${message}`);
    } finally {
      projecting.current = false;
      projection({ rows: props.rows.length, writes: plan.cellCount ? 1 : 0, cells: plan.cellCount, rowResizes: plan.resized ? 1 : 0, success });
    }
  }, [props.rows]);
  return <>
    {failure ? <Alert type="error" title="工作表同步失败，已停止表格编辑" description={`${failure}。项目草稿仍保留，请先使用其他视图保存，再刷新重试。`} /> : null}
    <div ref={host} className="quotation-sheet-canvas" aria-label="项目报价工作表" />
  </>;
}

function createRuntime(container: HTMLElement) {
  return createUniver({ locale: LocaleType.ZH_CN, locales: { [LocaleType.ZH_CN]: mergeLocales(zhCN) },
    presets: [UniverSheetsCorePreset({ container, header: false, toolbar: false, contextMenu: false, formulaBar: false,
      footer: { sheetBar: false, statisticBar: false, menus: false, zoomSlider: true },
      sheets: { disableForceStringAlert: true, disableForceStringMark: true } })] });
}
