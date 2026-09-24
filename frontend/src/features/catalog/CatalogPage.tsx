import { useDeferredValue, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Col, Empty, Flex, Input, Row, Select, Space, Statistic, Table, Tag, Typography, Upload } from 'antd';
import UploadOutlined from '@ant-design/icons/UploadOutlined';
import SearchOutlined from '@ant-design/icons/SearchOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import { useNavigate } from 'react-router-dom';
import { api } from '../../shared/api';
import { PageHeader } from '../../shared/PageHeader';
import { useCatalog } from '../../shared/useCatalog';
import type { CatalogImport, Product } from '../../shared/types';
import {AttributeBatchModal} from './attributes/AttributeBatchModal';
import { ProductDrawer } from './ProductDrawer';
import { ReviewSummaryTag } from './ReviewSummaryTag';

export default function CatalogPage() {
  const { imports, selectedId, current, select } = useCatalog();
  const [selection,setSelection] = useState<React.Key[]>([]);
  const [batch,setBatch] = useState<Product[]>();
  const [search, setSearch] = useState('');
  const [sheet, setSheet] = useState<string>();
  const [detailId, setDetailId] = useState<string>();
  const deferredSearch = useDeferredValue(search).toLowerCase();
  const client = useQueryClient();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const products = useQuery({
    queryKey: ['products', selectedId], enabled: Boolean(selectedId),
    queryFn: () => api<Product[]>(`/products?import_id=${selectedId}`),
  });
  const upload = useMutation({
    mutationFn: (file: File) => { const form = new FormData(); form.append('file', file); return api<CatalogImport>('/imports', { method: 'POST', body: form }); },
    onSuccess: async (result) => {
      await client.invalidateQueries({ queryKey: ['imports'] });
      select(result.id); setSheet(undefined);setSelection([]);
      message.success(result.already_imported ? '该文件已经导入，已切换到对应版本' : `导入完成，保留 ${result.record_count} 条来源记录`);
    },
    onError: (error) => message.error(error.message),
  });
  const sheets = useMemo(() => [...new Set(products.data?.map(p => p.sheet) ?? [])], [products.data]);
  const filtered = useMemo(() => (products.data ?? []).filter(p =>
    (!sheet || p.sheet === sheet) && `${p.name} ${p.model} ${p.brand} ${p.note}`.toLowerCase().includes(deferredSearch),
  ), [products.data, sheet, deferredSearch]);
  const error = imports.error || products.error;

  return <>
    <PageHeader title="产品资料库" description="从现有 Excel 出发，让每条产品资料都有据可查。" actions={
      <Upload accept=".xlsx" showUploadList={false} beforeUpload={file => { upload.mutate(file); return false; }} disabled={upload.isPending}>
        <Button type="primary" icon={<UploadOutlined />} loading={upload.isPending}>导入产品 Excel</Button>
      </Upload>
    } />
    {error ? <Alert type="error" showIcon title={error.message} className="section-bottom" /> : null}
    <Row gutter={[16, 16]} className="section-bottom">
      <Col xs={24} sm={8}><Card><Statistic title="当前版本来源记录" value={current?.record_count ?? 0} suffix="条" /><span className="stat-caption">保留各表记录，尚未合并为唯一产品</span></Card></Col>
      <Col xs={24} sm={8}><Card><Statistic title="包含产品的工作表" value={sheets.length} suffix="张" /><span className="stat-caption">产品线、总表及配套资料</span></Card></Col>
      <Col xs={24} sm={8}><Card><Statistic title="来源差异总数" value={current?.issue_count ?? 0} suffix="项" /><Button type="link" className="stat-link" onClick={() => navigate(`/issues${selectedId ? `?import=${selectedId}` : ''}`)}>查看处理进度 <ArrowRightOutlined /></Button></Card></Col>
    </Row>
    <Card className="catalog-card">
      <Flex justify="space-between" align="center" wrap gap={16} className="section-bottom">
        <Space><div className="section-indicator" /><Typography.Title level={4} className="no-margin">全部来源记录</Typography.Title><Tag>{filtered.length}</Tag></Space>
        <Select aria-label="产品库版本" className="version-select" value={selectedId} placeholder="尚未导入产品库" onChange={value => { select(value); setSheet(undefined);setSelection([]); }}
          options={imports.data?.map(item => ({ value: item.id, label: item.filename }))} />
      </Flex>
      <Flex gap={12} wrap className="section-bottom">
        <Input className="search-input" aria-label="搜索产品" prefix={<SearchOutlined />} placeholder="搜索型号、名称、品牌或备注" allowClear value={search} onChange={event => setSearch(event.target.value)} />
        <Select aria-label="筛选来源工作表" className="sheet-select" placeholder="全部来源工作表" allowClear value={sheet} onChange={setSheet} options={sheets.map(value => ({ value, label: value }))} />
      </Flex>
      <Button className="section-bottom" disabled={!selection.length} onClick={()=>setBatch((products.data??[]).filter(p=>selection.includes(p.id)))}>批量维护属性（{selection.length}）</Button>
      <Table<Product> rowSelection={{selectedRowKeys:selection,onChange:setSelection,preserveSelectedRowKeys:true}} rowKey="id" dataSource={filtered} loading={products.isLoading || imports.isLoading}
        pagination={{ pageSize: 12, showSizeChanger: false, showTotal: total => `共 ${total} 条来源记录` }} scroll={{ x: 950 }}
        locale={{ emptyText: <Empty description="导入产品 Excel 后，在这里查看和筛选真实资料" /> }}
        columns={[
          { title: '产品 / 型号', key: 'product', width: 280, render: (_, item) => <Space orientation="vertical" size={3}><Button type="link" className="product-link" onClick={() => setDetailId(item.id)}>{item.name || '名称待核对'}</Button><Typography.Text type="secondary" className="model-text">{item.model}</Typography.Text></Space> },
          { title: '来源工作表', dataIndex: 'sheet', width: 215, render: (value, item) => <Space orientation="vertical" size={3}><Typography.Text>{value}</Typography.Text><Typography.Text type="secondary">第 {item.row} 行{item.hidden ? ' · 隐藏工作表' : ''}</Typography.Text></Space> },
          { title: '资料核对', key: 'review', width: 230, render: (_, item) => <ReviewSummaryTag summary={item.review_summary} /> },
          { title: '配套与适用说明', dataIndex: 'note', width: 220, ellipsis: true, render: value => value || <Typography.Text type="secondary">原表未填写</Typography.Text> },
          { title: '单位', dataIndex: 'unit', width: 60 },
          { title: '操作', key: 'action', width: 90, render: (_, item) => <Button size="small" onClick={() => setDetailId(item.id)}>查看详情</Button> },
        ]} />
    </Card>
    <Typography.Paragraph type="secondary" className="footnote">各版本独立保留。同型号不同配置、隐藏表及来源差异均保留原值，待核对后再确定适用范围。</Typography.Paragraph>
    {batch?<AttributeBatchModal products={batch} onClose={()=>{setBatch(undefined);setSelection([]);}}/>:null}
    <ProductDrawer id={detailId} onClose={() => setDetailId(undefined)} />
  </>;
}
