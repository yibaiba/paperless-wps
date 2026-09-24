import {useDeferredValue, useMemo, useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Alert, Button, Card, Checkbox, Empty, Input, Pagination, Select, Space, Spin, Typography} from 'antd';
import {api} from '../../shared/api';
import type {CatalogImport, Product} from '../../shared/types';

interface Props {
  onAdd: (productIds: string[]) => Promise<void>; onDetail: (id: string) => void;
  binding: boolean; busy: boolean;
}
const PAGE_SIZE = 6;
export function ProductPalette({onAdd, onDetail, binding, busy}: Props) {
  const imports = useQuery({queryKey: ['imports'], queryFn: () => api<CatalogImport[]>('/imports')});
  const [selected, setSelected] = useState<string>();
  const importId = selected ?? imports.data?.[0]?.id;
  const products = useQuery({queryKey: ['products', importId], enabled: Boolean(importId),
    queryFn: () => api<Product[]>(`/products?import_id=${importId}`)});
  const [search, setSearch] = useState(''), [page, setPage] = useState(1);
  const [sheet, setSheet] = useState<string>();
  const [checked, setChecked] = useState<string[]>([]);
  const [addError, setAddError] = useState<string>();
  const query = useDeferredValue(search).toLowerCase();
  const filtered = useMemo(() => (products.data ?? []).filter(p => (!sheet || sheet === p.sheet)
    && `${p.model} ${p.name}`.toLowerCase().includes(query)), [products.data, query, sheet]);
  const sheets = [...new Set(products.data?.map(p => p.sheet))];
  const error = imports.error || products.error;
  const visible = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const selectedOnPage = visible.filter(p => checked.includes(p.id)).length;
  const toggle = (ids: string[], value: boolean) => setChecked(previous => value
    ? [...new Set([...previous, ...ids])] : previous.filter(id => !ids.includes(id)));
  const add = async (ids: string[]) => {
    setAddError(undefined);
    try {
      await onAdd(ids);
      setChecked(previous => previous.filter(id => !ids.includes(id)));
    } catch (error) {
      setAddError(error instanceof Error ? error.message : String(error));
    }
  };
  return <Card title="产品库" size="small" className="topology-palette">
    <Space orientation="vertical" className="topology-full" size={12}>
      <Select aria-label="拓扑产品库版本" className="topology-full" disabled={busy} value={importId} placeholder="选择已导入产品库"
        onChange={value => {setSelected(value); setSheet(undefined); setPage(1); setChecked([]); setAddError(undefined);}}
        options={imports.data?.map(i => ({value: i.id, label: i.filename}))}/>
      <Input.Search aria-label="拓扑搜索产品" placeholder="搜索型号或名称" value={search}
        onChange={e => {setSearch(e.target.value); setPage(1);}} allowClear/>
      <Select aria-label="拓扑来源工作表" className="topology-full" placeholder="全部工作表" allowClear value={sheet}
        onChange={value => {setSheet(value); setPage(1);}} options={sheets.map(value => ({value, label: value}))}/>
      <Typography.Text type="secondary">{binding ? '选择一个产品绑定到当前图形。' : '支持跨搜索、跨页勾选；切换产品库会清空勾选。'}</Typography.Text>
      {error ? <Alert type="error" title={error.message}/> : null}
      {products.isLoading ? <Spin/> : null}
      {!filtered.length && !products.isLoading ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配产品"/> : null}
      {!binding ? <Checkbox disabled={busy || !visible.length} checked={visible.length > 0 && selectedOnPage === visible.length}
        indeterminate={selectedOnPage > 0 && selectedOnPage < visible.length}
        onChange={event => toggle(visible.map(p => p.id), event.target.checked)}>全选本页</Checkbox> : null}
      {visible.map(product => <div className={`topology-product${checked.includes(product.id) ? ' is-selected' : ''}`} key={product.id}>
        {binding ? <Typography.Text strong>{product.model}</Typography.Text>
          : <Checkbox disabled={busy} checked={checked.includes(product.id)}
            onChange={event => toggle([product.id], event.target.checked)}>
            <Typography.Text strong>{product.model}</Typography.Text>
          </Checkbox>}
        <div>{product.name}</div>
        <Typography.Text type="secondary">{product.sheet} · 第 {product.row} 行</Typography.Text>
        <Space wrap size={4}>
          <Button size="small" disabled={busy} onClick={() => void add([product.id])}>{binding ? '绑定' : '直接添加'}</Button>
          <Button size="small" type="link" onClick={() => onDetail(product.id)}>资料</Button>
        </Space>
      </div>)}
      <Pagination simple current={page} total={filtered.length} pageSize={PAGE_SIZE} showSizeChanger={false} onChange={setPage}/>
    </Space>
    <div className="topology-product-actions">
      {addError ? <Alert type="error" showIcon title={addError}/> : null}
      {!binding ? <>
        <div className="topology-product-selection"><Typography.Text aria-live="polite">已选 {checked.length} 个产品</Typography.Text>
          <Button type="link" size="small" disabled={busy || !checked.length} onClick={() => setChecked([])}>清空选择</Button></div>
        <Button type="primary" block loading={busy} disabled={!checked.length || busy}
          onClick={() => void add([...checked])}>添加所选产品（{checked.length}）</Button>
      </> : null}
    </div>
  </Card>;
}
