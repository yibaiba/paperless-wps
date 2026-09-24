import {useState} from 'react';
import {Button, Dropdown, Form, Input, Modal, Tooltip} from 'antd';
import {ArrowLeftOutlined, CheckCircleOutlined, ClockCircleOutlined, DownOutlined, EditOutlined,
  ExpandOutlined, HistoryOutlined, MoreOutlined, PlusOutlined, ShrinkOutlined,
  ApartmentOutlined, AppstoreOutlined, LinkOutlined, ProfileOutlined} from '@ant-design/icons';

interface Props {
  name: string; actor: string; dirty: boolean; revision?: number; expanded: boolean;
  ready: boolean; busy: boolean; saving: boolean; canRelate: boolean; devices: number; unbound: number;
  onInfo: (info: {name: string; actor: string}) => void;
  onBack: () => void; onSave: () => void; onExpand: () => void; onHistory: () => void;
  onProducts: () => void; onBusiness: () => void; onBindings: () => void;
  onGroup: () => void; onRelation: () => void;
}
export function EditorToolbar(props: Props) {
  const [settings, setSettings] = useState(!props.name);
  const status = props.dirty ? '有未保存修改' : props.revision ? `已保存 · v${props.revision}` : '尚未保存';
  return <>
    <header className="topology-heading">
      <Tooltip title="返回方案列表"><Button type="text" icon={<ArrowLeftOutlined/>} aria-label="返回方案列表" onClick={props.onBack}/></Tooltip>
      <div className="topology-heading-title">
        <Button type="text" className="topology-title-button" onClick={() => setSettings(true)} disabled={props.busy} title="编辑方案信息">
          <span>{props.name || '未命名方案'}</span><EditOutlined/>
        </Button>
        <span className={`topology-save-state${props.dirty ? ' is-dirty' : ''}`}>
          {props.dirty ? <ClockCircleOutlined/> : <CheckCircleOutlined/>}{status}
        </span>
      </div>
      <Button type="primary" className="topology-save-button" loading={props.saving}
        disabled={!props.ready || !props.name.trim() || !props.actor.trim()} onClick={props.onSave}>保存方案</Button>
      <Dropdown trigger={['click']} menu={{items: [
        {key: 'info', label: '方案信息', icon: <EditOutlined/>, disabled: props.busy},
        {key: 'history', label: '版本记录', icon: <HistoryOutlined/>, disabled: !props.revision},
        {type: 'divider'},
        {key: 'expand', label: props.expanded ? '显示工作台导航' : '专注画图', icon: props.expanded ? <ShrinkOutlined/> : <ExpandOutlined/>},
      ], onClick: ({key}) => {if (key === 'info') setSettings(true); if (key === 'history') props.onHistory(); if (key === 'expand') props.onExpand();}}}>
        <Button type="text" icon={<MoreOutlined/>} aria-label="更多方案操作"/>
      </Dropdown>
    </header>
    <nav className="topology-commandbar" aria-label="方案编辑工具">
      <div className="topology-command-group">
        <Button className="topology-add-product" icon={<PlusOutlined/>} disabled={!props.ready} onClick={props.onProducts}>添加产品</Button>
        <Dropdown trigger={['click']} menu={{items: [
          {key: 'group', label: '添加系统区域', icon: <ApartmentOutlined/>},
          {key: 'relation', label: '添加业务关系', icon: <LinkOutlined/>, disabled: !props.canRelate},
        ], onClick: ({key}) => key === 'group' ? props.onGroup() : props.onRelation()}}>
          <Button type="text" disabled={!props.ready}>添加<DownOutlined/></Button>
        </Dropdown>
      </div>
      <div className="topology-command-group topology-business-tools">
        <Button type="text" icon={<ProfileOutlined/>} disabled={!props.ready} onClick={props.onBusiness}>配置清单<span className="topology-count">{props.devices}</span></Button>
        <Button type="text" icon={<AppstoreOutlined/>} disabled={!props.ready} onClick={props.onBindings}>图形绑定{props.unbound > 0 ? <span className="topology-count topology-count-pending">{props.unbound}</span> : null}</Button>
      </div>
    </nav>
    {settings ? <Modal open title="方案信息" footer={null} onCancel={() => setSettings(false)}>
      <Form layout="vertical" initialValues={{name: props.name, actor: props.actor}} onFinish={values => {props.onInfo(values); setSettings(false);}}>
        <Form.Item name="name" label="方案名称" rules={[{required: true, whitespace: true, message: '请填写方案名称'}]}><Input placeholder="例如：三楼无纸化会议室" autoFocus/></Form.Item>
        <Form.Item name="actor" label="维护人" rules={[{required: true, whitespace: true, message: '请填写维护人'}]}><Input placeholder="负责维护此方案的人"/></Form.Item>
        <div className="topology-info-actions"><Button onClick={() => setSettings(false)}>取消</Button><Button type="primary" htmlType="submit">确定</Button></div>
      </Form>
    </Modal> : null}
  </>;
}
