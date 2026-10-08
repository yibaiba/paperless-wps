import type { CompletionPreviewResult, WorkbookBusinessContext } from './businessTypes';

export function requirePanelConfiguration(
  result: CompletionPreviewResult,
): WorkbookBusinessContext['configuration'] {
  if (!result.configuration || !Array.isArray(result.line_bindings)) {
    throw new Error('任务窗格响应缺少完整业务配置，请检查服务端与插件版本');
  }
  return result.configuration;
}
