import { Button, Result, Space, Typography } from 'antd';
import { isRouteErrorResponse, useRouteError } from 'react-router-dom';

export function errorMessage(error: unknown) {
  if (isRouteErrorResponse(error)) {
    const detail = typeof error.data === 'string' ? error.data : error.statusText;
    return `${error.status} ${detail || '路由请求失败'}`;
  }
  if (error instanceof Error) return error.message;
  return String(error || '未知页面错误');
}

export function AppErrorPage() {
  const error = useRouteError();
  return <Result status="error" title="页面运行失败" subTitle="错误已明确保留，请重新载入后继续。" extra={<Space direction="vertical">
    <Typography.Text type="secondary">{errorMessage(error)}</Typography.Text>
    <Space>
      <Button type="primary" onClick={() => window.location.reload()}>重新载入</Button>
      <Button href="/projects">返回项目列表</Button>
    </Space>
  </Space>} />;
}
