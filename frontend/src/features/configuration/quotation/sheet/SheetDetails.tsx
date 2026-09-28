import { Alert, Button, Descriptions, Empty, Space, Tag, Typography } from 'antd';
import type { Configuration } from '../../types';
import type { QuotationOutput } from '../types';

export function SheetDetails({ configuration, output, stale, busy, selected, selectionCount, onSupply, onProduct, onPrice, onSettings, onRestoreDescription }: {
  configuration: Configuration; output?: QuotationOutput | null; selected?: string;
  stale: boolean; busy: boolean; selectionCount: number;
  onRestoreDescription: (id: string) => void;
  onSettings: (id: string) => void;
  onPrice: (id: string) => void;
  onSupply: (id: string) => void; onProduct: (id: string) => void;
}) {
  const device = configuration.devices.find((item) => item.id === selected);
  const line = output?.lines.find((item) => item.device_id === selected);
  const price = configuration.quotation?.prices.find((item) => item.device_id === selected);
  return <aside className="quotation-sheet-details">
    <Typography.Title level={5}>选中产品详情</Typography.Title>
    {!device ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择工作表中的设备查看来源" /> : <Space orientation="vertical" style={{ width: '100%' }}>
      {selectionCount > 1 ? <Typography.Text type="secondary">已选 {selectionCount} 项，以下为首项详情；批量调价使用上方按钮。</Typography.Text> : null}
      <Typography.Text strong>{device.name}</Typography.Text>
      {stale ? <Alert type="warning" title="以下采购数量、金额与问题为上次检查结果" /> : null}
      <Descriptions column={2} size="small" items={[
        { key: 'quantity', label: '部署', children: device.quantity },
        { key: 'purchase', label: '采购', children: line?.purchase_quantity ?? '未检查' },
        { key: 'existing', label: '已有', children: line?.supply?.existing ?? '未检查' },
        { key: 'unknown', label: '待定', children: line?.unknown_quantity ?? '未检查' },
        { key: 'amount', label: '金额', span: 2, children: line?.amount != null ? `¥ ${line.amount}` : '待确认' },
      ]} />
      <Typography.Text type="secondary">报价按本次采购量计算；修改部署量后需核对供货。</Typography.Text>
      <Space wrap><Button disabled={busy || !configuration.quotation} onClick={() => onSettings(device.id)}>部署 / 分区 / 备注</Button><Button disabled={busy || !configuration.quotation} onClick={() => onPrice(device.id)}>采用价格列 / 调整依据</Button><Button disabled={busy} onClick={() => onSupply(device.id)}>分配已有与采购</Button><Button disabled={busy} onClick={() => onProduct(device.id)}>产品候选与换型</Button></Space>
      <Descriptions column={1} size="small" items={[
        { key: 'model', label: '型号', children: line?.model || String(device.source_snapshot?.model ?? '待确认') },
        { key: 'source', label: '产品来源', children: line?.source ? `${line.source.sheet} · 第 ${line.source.row} 行` : device.source_id },
        { key: 'brand', label: '品牌', children: line?.brand || '来源未提供' },
        { key: 'price', label: '价格依据', children: price && price.mode !== 'source' ? price.evidence : price?.price_column || '未指定' },
        { key: 'systems', label: '服务系统', children: line?.consumers.map((item) => <Tag key={item.requirement_id}>{item.system_name} / {item.role}</Tag>) },
      ]} />
      {configuration.quotation?.descriptions?.[device.id] ? <Button disabled={busy} onClick={() => onRestoreDescription(device.id)}>恢复产品库原始说明</Button> : null}
      <Typography.Text strong>原始参数</Typography.Text>
      <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 8, expandable: true }}>{line?.original_specification ?? line?.specification ?? '请在产品来源中核对'}</Typography.Paragraph>
      <Typography.Text strong>待确认事项</Typography.Text>
      {line?.issues.length ? line.issues.map((issue) => <Typography.Text type="warning" key={issue}>{issue}</Typography.Text>) : <Typography.Text type="secondary">{line ? '本行暂无报价问题，搭配结论见项目检查区。' : '本行尚未计算报价，请先检查。'}</Typography.Text>}
      <Typography.Text type="secondary" copyable>设备 ID：{device.id}</Typography.Text>
    </Space>}
  </aside>;
}
