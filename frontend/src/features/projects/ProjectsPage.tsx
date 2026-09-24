import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Empty, Form, Input, Modal, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import PlusOutlined from '@ant-design/icons/PlusOutlined';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../../shared/api';
import { PageHeader } from '../../shared/PageHeader';
import type { Project, ProjectDetail, ProjectItem } from '../../shared/types';
import { ItemModal } from './ItemModal';
import { ReviewSummaryTag } from '../catalog/ReviewSummaryTag';
import { ProjectRulesDrawer } from '../rules/ProjectRulesDrawer';

export default function ProjectsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [adding, setAdding] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [editing, setEditing] = useState<ProjectItem>();
  const [form] = Form.useForm<{ name: string }>();
  const client = useQueryClient();
  const { message } = App.useApp();
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/projects') });
  const detail = useQuery({ queryKey: ['project', projectId], enabled: Boolean(projectId), queryFn: () => api<ProjectDetail>(`/projects/${projectId}`) });
  const create = useMutation({
    mutationFn: (values: { name: string }) => api<Project>('/projects', { method: 'POST', body: JSON.stringify(values) }),
    onSuccess: async result => { await client.invalidateQueries({ queryKey: ['projects'] }); setCreating(false); form.resetFields(); navigate(`/projects/${result.id}`); },
    onError: error => message.error(error.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/projects/${projectId}/items/${id}`, { method: 'DELETE' }),
    onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ['project', projectId] }), client.invalidateQueries({ queryKey: ['projects'] })]); message.success('已移除清单行'); },
    onError: error => message.error(error.message),
  });
  const error = projects.error || detail.error;
  return <>
    {projectId ? <Button className="section-bottom" icon={<ArrowLeftOutlined />} onClick={() => navigate('/projects')}>返回项目</Button> : null}
    <PageHeader title={projectId ? detail.data?.name ?? '项目清单' : '项目清单'} description={projectId ? '按区域和系统组织设备，保留具体配置与选用依据。' : '从真实产品资料建立项目清单，保留每一项的来源。'} actions={
      <Space wrap>{projectId?<Button type="primary" onClick={()=>navigate(`/configuration/${projectId}`)}>需求选配与拓扑</Button>:null}{projectId?<Button onClick={()=>setCalculating(true)}>配套计算</Button>:null}<Button type="primary" icon={<PlusOutlined />} onClick={() => projectId ? setAdding(true) : setCreating(true)}>{projectId ? '添加产品' : '新建项目'}</Button></Space>
    } />
    {error ? <Alert type="error" title={error.message} showIcon className="section-bottom" /> : null}
    {projectId ? <>
      <Alert type="info" showIcon className="section-bottom" title="可使用已启用的配套规则计算缺少数量，并选择补入清单。" description="主设备仍需人工选型；计算仅覆盖录入的关系，不代表整套方案已完成校验或项目批价。" />
      <Card><Table<ProjectItem> rowKey="id" dataSource={detail.data?.items} loading={detail.isLoading} scroll={{ x: 950 }} pagination={false}
        locale={{ emptyText: <Empty description="清单还没有产品，点击“添加产品”开始配置" /> }} columns={[
          { title: '区域 / 系统', dataIndex: 'group_name', width: 160 },
          { title: '产品 / 型号', key: 'product', width: 260, render: (_, item) => <Space orientation="vertical" size={2}><Typography.Text strong>{item.snapshot.name}</Typography.Text><Typography.Text type="secondary">{item.snapshot.model}</Typography.Text></Space> },
          { title: '数量', dataIndex: 'quantity', width: 80 },
          { title: '单位', key: 'unit', width: 60, render: (_, item) => item.snapshot.unit },
          { title: '来源当前核对状态', key: 'review', width: 230, render: (_, item) => <Space orientation="vertical" size={4}>
            <ReviewSummaryTag summary={item.review_summary} />
            {item.review_summary.total ? <Button type="link" size="small" onClick={() => navigate(`/issues?${new URLSearchParams({ import: item.snapshot.import_id, model: item.snapshot.model })}`)}>查看依据</Button> : null}
          </Space> },
          { title: '备注 / 来源', key: 'note', render: (_, item) => <Space orientation="vertical" size={2}><span>{item.note || '未填写'}</span><Typography.Text type="secondary">{item.snapshot.sheet} · 第 {item.snapshot.row} 行</Typography.Text></Space> },
          { title: '操作', key: 'action', width: 150, render: (_, item) => <Space><Button size="small" onClick={() => setEditing(item)}>编辑</Button><Popconfirm title="移除这条清单记录？" onConfirm={() => remove.mutate(item.id)}><Button size="small" danger loading={remove.isPending && remove.variables === item.id}>移除</Button></Popconfirm></Space> },
        ]} /></Card>
      {adding || editing ? <ItemModal key={editing?.id ?? 'new'} projectId={projectId} item={editing} open onClose={() => { setAdding(false); setEditing(undefined); }} /> : null}
      {calculating?<ProjectRulesDrawer projectId={projectId} onClose={()=>setCalculating(false)}/>:null}
    </> : <Card><Table<Project> rowKey="id" loading={projects.isLoading} dataSource={projects.data} locale={{ emptyText: <Empty description="还没有项目，创建后即可从产品库添加配置" /> }} columns={[
      { title: '项目名称', dataIndex: 'name', render: (name, project) => <Button type="link" onClick={() => navigate(`/projects/${project.id}`)}>{name}</Button> },
      { title: '清单行数', dataIndex: 'item_count', render: value => <Tag>{value} 项</Tag> },
      { title: '创建时间', dataIndex: 'created_at', render: value => new Date(value).toLocaleString('zh-CN') },
      { title: '操作', key: 'action', render: (_, project) => <Button onClick={() => navigate(`/projects/${project.id}`)}>打开清单</Button> },
    ]} /></Card>}
    <Modal title="新建项目" open={creating} onCancel={() => setCreating(false)} onOk={() => form.submit()} confirmLoading={create.isPending} okText="创建项目" cancelText="取消">
      <Form form={form} layout="vertical" onFinish={values => create.mutate(values)}><Form.Item label="项目名称" name="name" rules={[{ required: true, whitespace: true, message: '请填写项目名称' }]}><Input placeholder="例如：办公楼会议系统改造" /></Form.Item></Form>
    </Modal>
  </>;
}
