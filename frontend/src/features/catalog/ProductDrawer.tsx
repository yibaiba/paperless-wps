import { Alert, Button, Card, Descriptions, Drawer, Spin, Tabs, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import {AttributeEditor} from './attributes/AttributeEditor';
import { api } from '../../shared/api';
import type { ProductDetail } from '../../shared/types';
import { useNavigate } from 'react-router-dom';
import { ReviewSummaryTag } from './ReviewSummaryTag';
import { reviewColors, reviewLabels } from './reviewLabels';

export function ProductDrawer({ id, onClose }: { id?: string; onClose: () => void }) {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ['product', id], enabled: Boolean(id),
    queryFn: () => api<ProductDetail>(`/products/${id}`),
  });
  const product = query.data;
  return <Drawer title="产品来源详情" open={Boolean(id)} onClose={onClose} size={740}>
    {query.isLoading ? <Spin /> : null}
    {query.error ? <Alert type="error" title={query.error.message} showIcon /> : null}
    {product ? <>
      <Tag>{product.sheet}</Tag>
      <ReviewSummaryTag summary={product.review_summary} />
      <Typography.Title level={3}>{product.name || '名称待核对'}</Typography.Title>
      <Typography.Paragraph copyable className="model-text">{product.model}</Typography.Paragraph>
      <Descriptions column={2} size="small" items={[
        { key: 'brand', label: '品牌', children: product.brand || '未提供' },
        { key: 'unit', label: '单位', children: product.unit || '未提供' },
        { key: 'category', label: '原表分组', children: product.category || '未提供' },
        { key: 'source', label: '原表位置', children: `${product.sheet} · 第 ${product.row} 行` },
      ]} />
      {product.hidden ? <Alert className="section-gap" type="warning" title="这条记录来自隐藏工作表，适用状态需要核对。" /> : null}
      <Tabs className="section-gap" defaultActiveKey="spec" items={[
        { key: 'review', label: `资料核对（${product.issues.length}）`, children: <>
          <Typography.Paragraph type="secondary">这里显示当前来源版本关联的差异；没有差异记录不代表已经完成业务校验。</Typography.Paragraph>
          {product.issues.map(issue => <Card key={issue.id} size="small" className="section-bottom" title={issue.title}>
            <Tag color={reviewColors[issue.review.status]}>{reviewLabels[issue.review.status]}</Tag>
            <Typography.Paragraph className="source-text section-gap">{issue.review.note ?? issue.description}</Typography.Paragraph>
          </Card>)}
          {product.issues.length ? <Button onClick={() => {
            onClose(); navigate(`/issues?${new URLSearchParams({ import: product.import_id, model: product.model })}`);
          }}>查看依据与处理历史</Button> : null}
        </> },
        {key:'attributes',label:'规则属性',children:<AttributeEditor key={`${product.id}-${product.attribute_profile.revision}`} product={product}/>},
        { key: 'spec', label: '完整参数', children: <div className="source-text">{product.specification || '原表未提供'}</div> },
        { key: 'note', label: '配套与备注', children: <>
          <Typography.Paragraph type="secondary">来源：{product.sources.note}</Typography.Paragraph>
          <div className="source-text">{product.note || '原表未提供备注；不能据此认定没有配套要求。'}</div>
        </> },
        { key: 'tender', label: '招标参数', children: <div className="source-text">{product.tender_specification || '原表未提供'}</div> },
        { key: 'price', label: '来源价格', children: <>
          <Alert type="info" title="保留原表的价格口径，未进行项目批价或自动折算。" showIcon />
          <Descriptions className="section-gap" column={1} items={Object.entries(product.prices).map(([key, value]) => ({
            key, label: key, children: value || '未提供',
          }))} />
        </> },
      ]} />
    </> : null}
  </Drawer>;
}
