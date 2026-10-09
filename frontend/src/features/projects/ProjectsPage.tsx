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
import type { ProjectConfiguration } from '../configuration/types';

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
  const configuration = useQuery({ queryKey: ['configuration-project', projectId], enabled: Boolean(projectId), queryFn: () => api<ProjectConfiguration>(`/configuration/projects/${projectId}`) });
  const unified = (configuration.data?.revision ?? 0) > 0;
  const legacyActions = configuration.isSuccess && !unified;
  const create = useMutation({
    mutationFn: (values: { name: string }) => api<Project>('/projects', { method: 'POST', body: JSON.stringify(values) }),
    onSuccess: async result => { await client.invalidateQueries({ queryKey: ['projects'] }); setCreating(false); form.resetFields(); navigate(`/configuration/${result.id}`); },
    onError: error => message.error(error.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/projects/${projectId}/items/${id}`, { method: 'DELETE' }),
    onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ['project', projectId] }), client.invalidateQueries({ queryKey: ['projects'] })]); message.success('已移除清单行'); },
    onError: error => message.error(error.message),
  });
  const error = projects.error || detail.error || configuration.error;
  return <>
    {projectId ? <Button className="section-bottom" icon={<ArrowLeftOutlined />} onClick={() => navigate('/projects')}>返回项目</Button> : null}
    <PageHeader title={projectId ? detail.data?.name ?? '项目清单' : '项目清单'} description={projectId ? '按区域和系统组织设备，保留具体配置与选用依据。' : '从真实产品资料建立项目清单，保留每一项的来源。'} actions={
      <Space wrap>{projectId?<Button type="primary" onClick={()=>navigate(`/configuration/${projectId}`)}>需求选配与拓扑</Button>:null}{projectId&&legacyActions?<Button onClick={()=>setCalculating(true)}>旧配套计算</Button>:null}{!projectId||legacyActions?<Button type="primary" icon={<PlusOutlined />} onClick={() => projectId ? setAdding(true) : setCreating(true)}>{projectId ? '添加产品' : '新建项目'}</Button>:null}</Space>
    } />
    {error ? <Alert type="error" title={error.message} showIcon className="section-bottom" /> : null}
    {projectId ? <>
      <Alert type="info" showIcon className="section-bottom" title={unified?'此清单由统一项目配置生成。':'这是尚未导入统一配置的旧项目清单。'} description={unified?'请在“需求选配与拓扑”中修改设备、关联已有配套并检查缺量；此页只读展示同一份清单。':'可继续使用旧清单流程，导入统一配置后将改为只读投影。'} />
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
          { title: '操作', key: 'action', width: 150, render: (_, item) => !legacyActions?<Button size="small" onClick={()=>navigate(`/configuration/${projectId}`)}>在配置中查看</Button>:<Space><Button size="small" onClick={() => setEditing(item)}>编辑</Button><Popconfirm title="移除这条清单记录？" onConfirm={() => remove.mutate(item.id)}><Button size="small" danger loading={remove.isPending && remove.variables === item.id}>移除</Button></Popconfirm></Space> },
        ]} /></Card>
      {legacyActions&&(adding || editing) ? <ItemModal key={editing?.id ?? 'new'} projectId={projectId} item={editing} open onClose={() => { setAdding(false); setEditing(undefined); }} /> : null}
      {legacyActions&&calculating?<ProjectRulesDrawer projectId={projectId} onClose={()=>setCalculating(false)}/>:null}
    </> : <Card><Table<Project> rowKey="id" loading={projects.isLoading} dataSource={projects.data} locale={{ emptyText: <Empty description="还没有项目，创建后即可从产品库添加配置" /> }} columns={[
      { title: '项目名称', dataIndex: 'name', render: (name, project) => <Button type="link" onClick={() => navigate(`/configuration/${project.id}`)}>{name}</Button> },
      { title: '清单行数', dataIndex: 'item_count', render: value => <Tag>{value} 项</Tag> },
      { title: '创建时间', dataIndex: 'created_at', render: value => new Date(value).toLocaleString('zh-CN') },
      { title: '操作', key: 'action', render: (_, project) => <Button onClick={() => navigate(`/configuration/${project.id}`)}>进入售前配置</Button> },
    ]} /></Card>}
    <Modal title="新建项目" open={creating} onCancel={() => setCreating(false)} onOk={() => form.submit()} confirmLoading={create.isPending} okText="创建项目" cancelText="取消">
      <Form form={form} layout="vertical" onFinish={values => create.mutate(values)}><Form.Item label="项目名称" name="name" rules={[{ required: true, whitespace: true, message: '请填写项目名称' }]}><Input placeholder="例如：办公楼会议系统改造" /></Form.Item></Form>
    </Modal>
  </>;
}
