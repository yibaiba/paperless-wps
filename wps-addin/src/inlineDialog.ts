import type { InlineEditorContext } from './types';
import {
  inlineDialogSize,
  type InlineDialogSize,
  type InlineLayoutOptions,
  type InlineLayoutResult,
  type InlinePlacement,
} from './inlineLayout.ts';

const CONTEXT_KEY = 'presales_inline_context';
const CONTEXT_NONCE_KEY = 'presales_inline_context_nonce';
const DIALOG_KEY = 'presales_inline_dialog_id';
const DIALOG_GAP = 2;
const DIALOG_RESIZE_EDGE = 2;
const DIALOG_LOADING_TIMEOUT_MS = 0;
const SYNC_INLINE_CONTEXT_SCRIPT =
  'window.PresalesInlineRefresh && window.PresalesInlineRefresh()';
const REFRESH_INLINE_EDITOR_SCRIPT = [
  'window.focus()',
  SYNC_INLINE_CONTEXT_SCRIPT,
].join(';');
const CLOSE_INLINE_EDITOR_SCRIPT = 'window.close()';

interface DialogConfig {
  app: any;
  href: string;
  screen?: {
    availWidth: number;
    availHeight: number;
    availLeft?: number;
    availTop?: number;
  };
  get: (key: string) => string | null;
  set: (key: string, value: string | number) => void;
}

interface DialogGeometry {
  dialogId: number;
  width: number;
  height: number;
  x: number;
  y: number;
}

export class InlineDialogManager {
  private readonly config: DialogConfig;
  private dialogRef?: any;
  private geometry?: DialogGeometry;

  constructor(config: DialogConfig) { this.config = config; }

  context() {
    const raw = this.config.get(CONTEXT_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw) as InlineEditorContext; }
    catch { throw new Error('单元格联想上下文损坏，请重新选择单元格'); }
  }

  show(context: Omit<InlineEditorContext, 'nonce' | 'session_id' | 'anchor'>) {
    const anchor = this.anchor();
    const previous = Number(this.config.get(CONTEXT_NONCE_KEY) || 0);
    const nonce = Math.max(Date.now(), previous + 1);
    this.config.set(CONTEXT_NONCE_KEY, nonce);
    this.config.set(CONTEXT_KEY, JSON.stringify({
      ...context,
      nonce,
      session_id: crypto.randomUUID(),
      anchor: { width: anchor.width, height: anchor.height },
    }));
    const size = inlineDialogSize({
      anchorWidth: anchor.width,
      anchorHeight: anchor.height,
      candidateCount: 0,
      listVisible: false,
      showStatus: false,
    });
    const dialog = this.dialog(true, size);
    if (!dialog) throw new Error('WPS 未能创建单元格联想浮层');
    this.place(dialog, size, anchor);
    dialog.Visible = true;
    if (typeof dialog.ExecuteJavaScript === 'function') {
      dialog.ExecuteJavaScript(REFRESH_INLINE_EDITOR_SCRIPT);
    }
  }

  hide() {
    this.config.set(CONTEXT_KEY, '');
    const dialog = this.dialog(false);
    if (!dialog) return;
    dialog.Visible = false;
    dialog.ExecuteJavaScript(SYNC_INLINE_CONTEXT_SCRIPT);
  }

  dispose() { this.closeDialog(); }

  layout(options: Omit<InlineLayoutOptions, 'anchorWidth' | 'anchorHeight'>): InlineLayoutResult {
    if (!this.context()) return { placement: 'below', anchor: { width: 1, height: 1 } };
    const dialog = this.dialog(false);
    if (!dialog) return { placement: 'below', anchor: { width: 1, height: 1 } };
    const anchor = this.anchor();
    const size = inlineDialogSize({
      ...options,
      anchorWidth: anchor.width,
      anchorHeight: anchor.height,
    });
    return {
      placement: this.place(dialog, size, anchor),
      anchor: { width: anchor.width, height: anchor.height },
    };
  }

  private closeDialog() {
    const dialog = this.dialog(false);
    if (!dialog) return;
    dialog.Visible = false;
    if (typeof dialog.ExecuteJavaScript !== 'function') {
      throw new Error('当前 WPS 版本无法关闭单元格联想浮层');
    }
    dialog.ExecuteJavaScript(CLOSE_INLINE_EDITOR_SCRIPT);
    this.config.set(DIALOG_KEY, '');
    this.dialogRef = undefined;
    this.geometry = undefined;
  }

  private dialog(create: boolean, size?: InlineDialogSize) {
    if (this.dialogRef) return this.dialogRef;
    const id = Number(this.config.get(DIALOG_KEY) || 0);
    if (id) {
      try {
        const existing = this.config.app.GetWebDialog(id);
        if (existing) {
          this.dialogRef = existing;
          return existing;
        }
      } catch { /* A stale dialog id is replaced below. */ }
    }
    if (!create) return null;
    const url = new URL('inline.html', this.config.href).href;
    const dialog = this.config.app.CreateWebDialog(
      url,
      '',
      size?.width,
      size?.height,
      false,
      false,
      DIALOG_RESIZE_EDGE,
      '',
      DIALOG_LOADING_TIMEOUT_MS,
      true,
      false,
      true,
    );
    if (dialog?.ID) this.config.set(DIALOG_KEY, dialog.ID);
    this.dialogRef = dialog;
    return dialog;
  }

  private anchor() {
    const range = this.config.app.Selection;
    const activeWindow = this.config.app.ActiveWindow;
    const left = Number(activeWindow.PointsToScreenPixelsX(range.Left));
    const top = Number(activeWindow.PointsToScreenPixelsY(range.Top));
    const right = Number(activeWindow.PointsToScreenPixelsX(range.Left + Number(range.Width ?? 0)));
    const bottom = Number(activeWindow.PointsToScreenPixelsY(range.Top + range.Height));
    return {
      x: left,
      y: top,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - top),
      bottom,
    };
  }

  private place(dialog: any, size: InlineDialogSize, anchor: ReturnType<InlineDialogManager['anchor']>) {
    const availableLeft = this.config.screen?.availLeft ?? 0;
    const availableTop = this.config.screen?.availTop ?? 0;
    const availableRight = availableLeft
      + (this.config.screen?.availWidth ?? anchor.x + size.width);
    const availableBottom = availableTop
      + (this.config.screen?.availHeight ?? anchor.y + size.height);
    const x = Math.max(availableLeft, Math.min(anchor.x, availableRight - size.width));
    const placement: InlinePlacement = anchor.y + size.height <= availableBottom
      ? 'below' : 'above';
    const y = placement === 'below'
      ? anchor.y : Math.max(availableTop, anchor.bottom - size.height - DIALOG_GAP);
    const next = {
      dialogId: Number(dialog.ID || 0), width: size.width, height: size.height, x, y,
    };
    if (!this.geometry || this.geometry.dialogId !== next.dialogId
      || this.geometry.width !== next.width || this.geometry.height !== next.height) {
      dialog.Resize(size.width, size.height);
    }
    if (!this.geometry || this.geometry.dialogId !== next.dialogId
      || this.geometry.x !== next.x || this.geometry.y !== next.y) {
      dialog.Move(x, y);
    }
    this.geometry = next;
    return placement;
  }
}
