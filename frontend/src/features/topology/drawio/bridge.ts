import editorTheme from './editor-theme.css?inline';

/** Adapter for the locally hosted, pinned draw.io 29.6.5 plugin API. */
interface DrawingFile {getShadowPages(): unknown[]; patch(patches: unknown[], resolver: null, undoable: boolean): void}
interface DrawingUi {
  pages: unknown[];
  editor: {graph: {
    isCellEditable(cell:{value?:Element}):boolean;
    getModel(): {addListener(name:string, listener:()=>void):void};
    getSelectionCell(): {value?: Element} | undefined;
    getSelectionModel(): {addListener(name:string, listener:()=>void):void};
  }; undoManager: {undo:()=>void; redo:()=>void}};
  fitDiagramToWindow(maxScale: number, borders: {x: number; y: number; width: number; height: number}, zoomOutOnly: boolean): void;
  diffPages(before: unknown[], after: unknown[]): unknown;
  getCurrentFile(): DrawingFile;
  getFileData(ignoreSelection: boolean): string;
}
interface DrawingWindow extends Window {
  Draw: {loadPlugin(register: (ui: DrawingUi) => void): void};
  LocalFile: new(ui: DrawingUi, xml: string) => DrawingFile;
}
export interface DrawingBridge {apply: (xml: string) => string; fit: () => void}

export interface DrawingCallbacks {onGraphChange?:(xml:string)=>void;onSelection?:(id:string|undefined)=>void; onUndo?:()=>void; onRedo?:()=>void}
export function connectDrawing(frame: HTMLIFrameElement, callbacks?:DrawingCallbacks): DrawingBridge {
  const editorWindow = frame.contentWindow as DrawingWindow | null;
  if (!editorWindow || new URL(frame.src).origin !== window.location.origin) {
    throw new Error('产品配置需要通过工作台的本地绘图地址打开，请检查 /diagram-editor/ 代理。');
  }
  const themeId = 'presales-editor-theme';
  let theme = editorWindow.document.getElementById(themeId);
  if (!theme) {
    theme = editorWindow.document.createElement('style');
    theme.id = themeId;
    editorWindow.document.head.append(theme);
  }
  theme.textContent = editorTheme;
  let ui: DrawingUi | undefined;
  editorWindow.Draw.loadPlugin(instance => {ui = instance;});
  if (!ui) throw new Error('绘图扩展尚未就绪，请重新载入页面。');
  const editor = ui;
  if(callbacks?.onSelection) editor.editor.graph.getSelectionModel().addListener('change',()=>{
    const value=editor.editor.graph.getSelectionCell()?.value;
    callbacks.onSelection?.(value && typeof value.getAttribute === 'function' ? value.getAttribute('cfg_device_id')??undefined : undefined);
  });
  if(callbacks?.onGraphChange) editor.editor.graph.getModel().addListener('change',()=>callbacks.onGraphChange?.(editor.getFileData(true)));
  if(callbacks?.onUndo) {
    const graph=editor.editor.graph;
    const editable=graph.isCellEditable.bind(graph);
    graph.isCellEditable=cell=>cell.value?.getAttribute?.('cfg_device_id') ? false : editable(cell);
    editor.editor.undoManager.undo=callbacks.onUndo;
  }
  if(callbacks?.onRedo) editor.editor.undoManager.redo=callbacks.onRedo;
  // Reserve room for the floating tools without changing saved geometry or paper settings.
  const fit = () => editor.fitDiagramToWindow(1, {x: 100, y: 80, width: 60, height: 80}, false);
  fit();
  return {fit, apply: xml => {
    const incoming = new editorWindow.LocalFile(editor, xml).getShadowPages();
    const patch = editor.diffPages(editor.pages, incoming);
    // Apply an explicit local edit: merge treats host metadata as remote changes and can
    // resolve it back to stale local values. Undoable patches share the drawing's undo stack.
    editor.getCurrentFile().patch([patch], null, true);
    return editor.getFileData(true);
  }};
}
