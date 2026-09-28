import React from 'react';
import ReactDOM from 'react-dom/client';
import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
const router = createBrowserRouter([{ path: '*', element: <Workbench /> }]);
import { Workbench } from './Workbench';
import 'antd/dist/reset.css';
import './styles.css';

const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 15_000 } } });
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ConfigProvider locale={zhCN} theme={{ token: {
    colorPrimary: '#185b49', colorInfo: '#185b49', colorBgLayout: '#f5f7f8',
    colorPrimaryBg: '#edf6f2', colorPrimaryBgHover: '#e0ede6',
    colorInfoBg: '#edf6f2', colorInfoBorder: '#c9dfd4',
    colorText: '#1d2b35', colorTextSecondary: '#65717d', borderRadius: 8,
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif',
    controlHeight: 38,
  } }}><AntApp><QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider></AntApp></ConfigProvider></React.StrictMode>,
);
