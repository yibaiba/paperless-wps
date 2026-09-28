import { startSheetMeasure } from './sheet/performance';

let pending: Promise<typeof import('./sheet/QuotationSheet')> | undefined;

// Module lifetime cache: preloading must not create a workbook or make business requests.
export function loadQuotationSheet() {
  if (!pending) {
    const finished = startSheetMeasure('workbench-module');
    pending = import('./sheet/QuotationSheet').then((module) => {
      finished({ success: true });
      return module;
    }, (error: unknown) => {
      finished({ success: false });
      throw error;
    });
  }
  return pending;
}

export function preloadQuotationSheet() {
  // Retain the rejection for the workbench error boundary when the tab is opened.
  void loadQuotationSheet().catch((error: unknown) => console.error('报价工作表预加载失败', error));
}
