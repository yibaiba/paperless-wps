import { Suspense, lazy } from 'react';
import { Layout, Menu, Space, Spin, Tag, Typography } from 'antd';
import DatabaseOutlined from '@ant-design/icons/DatabaseOutlined';
import AuditOutlined from '@ant-design/icons/AuditOutlined';
import ProfileOutlined from '@ant-design/icons/ProfileOutlined';
import ApartmentOutlined from '@ant-design/icons/ApartmentOutlined';
import SettingOutlined from '@ant-design/icons/SettingOutlined';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

const CatalogPage = lazy(() => import('./features/catalog/CatalogPage'));
const IssuesPage = lazy(() => import('./features/catalog/IssuesPage'));
const ProjectsPage = lazy(() => import('./features/projects/ProjectsPage'));
const TopologyPage = lazy(() => import('./features/topology/TopologyPage'));
const OrganizePage = lazy(() => import('./features/configuration/CatalogOrganizePage'));
const KnowledgePage = lazy(() => import('./features/configuration/KnowledgePage'));
const ExtractionPage = lazy(() => import('./features/configuration/ExtractionPage'));
const ConfigurationPage = lazy(() => import('./features/configuration/ProjectConfigurationPage'));
const RulesPage = lazy(() => import('./features/rules/RulesPage'));

export function Workbench() {
  const location = useLocation();
  const navigate = useNavigate();
  const configuring = location.pathname.startsWith('/configuration/');
  return <Layout className={configuring ? 'workbench configuration-workbench' : 'workbench'}>
    <Layout.Sider collapsed={configuring ? true : undefined} width={224} breakpoint="lg" collapsedWidth={64} className="sidebar">
      <div className="brand"><div className="brand-mark">A</div><div className="brand-copy">
        <strong>艾索技术</strong><span>售前工作台</span></div></div>
      <div className="nav-label">工作空间</div>
      <Menu mode="inline" selectedKeys={[location.pathname.split('/')[1] || 'catalog']}
        onClick={({ key }) => navigate(`/${key}`)} items={[
          { key: 'product-workspace', icon: <DatabaseOutlined />, label: '产品与价格', children: [
            { key: 'catalog', label: '产品资料库' },
            { key: 'organize', label: '产品整理与价格' },
          ] },
          { key: 'knowledge', icon: <ApartmentOutlined />, label: '系统与搭配知识' },
          { key: 'projects', icon: <ProfileOutlined />, label: '售前项目' },
          { key: 'maintenance', icon: <AuditOutlined />, label: '资料维护', children: [
            { key: 'issues', label: '资料核对' },
            { key: 'extraction', label: 'AI 资料整理' },
            { key: 'advanced-history', icon: <SettingOutlined />, label: '高级与历史', children: [
              { key: 'rules', label: '旧配套规则' },
              { key: 'topologies', label: '独立拓扑' },
            ] },
          ] },
        ]} />
      <div className="sidebar-footer"><span className="status-dot" />本地工作空间</div>
    </Layout.Sider>
    <Layout>
      <Layout.Header className="topbar"><Typography.Text type="secondary">售前业务 / 产品与配置</Typography.Text>
        <Space><Tag variant="filled">开发版</Tag><Typography.Text>艾索工作空间</Typography.Text></Space>
      </Layout.Header>
      <Layout.Content className="content"><Suspense fallback={<Spin className="page-loading" />}>
        <Routes>
          <Route path="/organize" element={<OrganizePage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/extraction" element={<ExtractionPage />} />
          <Route path="/configuration/:projectId" element={<ConfigurationPage />} />
          <Route path="/catalog" element={<CatalogPage />} />
          <Route path="/issues" element={<IssuesPage />} />
          <Route path="/rules" element={<RulesPage />} />
          <Route path="/topologies" element={<TopologyPage />} />
          <Route path="/topologies/:topologyId" element={<TopologyPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectsPage />} />
          <Route path="*" element={<Navigate to="/catalog" replace />} />
        </Routes>
      </Suspense></Layout.Content>
    </Layout>
  </Layout>;
}
