import { Component, type ReactNode } from 'react';
import { Alert } from 'antd';

export class SheetBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { console.error('报价工作表加载或渲染失败', error); }
  render() {
    return this.state.failed ? <Alert type="error" showIcon title="报价工作表加载或渲染失败"
      description="项目草稿仍保留，可继续使用其他视图。请先保存草稿，再刷新页面重试；具体错误已记录在浏览器控制台。" /> : this.props.children;
  }
}
