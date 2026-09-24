import {useEffect, useRef, useState} from 'react';
import {connectDrawing, type DrawingBridge, type DrawingCallbacks} from './bridge';

const editorUrl = new URL('/diagram-editor/', window.location.origin);
for (const [key, value] of Object.entries({embed: '1', proto: 'json', configure: '1', libraries: '1',
  noExitBtn: '1', noSaveBtn: '1', lang: 'zh', ui: 'sketch', sketch: '0', p: 'props', https: '0', spin: '1'})) editorUrl.searchParams.set(key, value);
const RESPONSE_TIMEOUT_MS = 20_000;
interface Options extends DrawingCallbacks {xml: string; onChange: (xml: string) => void; onSave: (xml: string) => void}

export function useDrawio(options: Options) {
  const frame = useRef<HTMLIFrameElement>(null);
  const bridge = useRef<DrawingBridge | undefined>(undefined);
  const callbacks = useRef(options);
  const [ready, setReady] = useState(false), [error, setError] = useState<string>();
  useEffect(() => {callbacks.current = options;});
  const send = (data: object) => frame.current?.contentWindow?.postMessage(JSON.stringify(data), editorUrl.origin);
  useEffect(() => {
    const timer = setTimeout(() => setError('绘图服务尚未响应，请检查本地绘图服务后重新载入。'), RESPONSE_TIMEOUT_MS);
    const receive = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow || event.origin !== editorUrl.origin || typeof event.data !== 'string') return;
      let data;
      try {data = JSON.parse(event.data);} catch {return; /* Ignore unrelated window messages. */}
      if (!data || typeof data.event !== 'string') return;
      if (data.event === 'configure') send({action: 'configure', config: {
        defaultLibraries: 'general;arrows2;network;rack;electrical', compressXml: false,
        defaultEdgeStyle: {edgeStyle: 'orthogonalEdgeStyle', rounded: '0', strokeColor: '#52677b'},
      }});
      if (data.event === 'init') send({action: 'load', xml: callbacks.current.xml, autosave: 1, title: '方案拓扑', saveAndExit: '0'});
      if (data.event === 'load') {
        clearTimeout(timer);
        try {bridge.current = connectDrawing(frame.current!, {
          onSelection: id=>callbacks.current.onSelection?.(id),
          ...(callbacks.current.onUndo ? {onUndo:()=>callbacks.current.onUndo?.(),onRedo:()=>callbacks.current.onRedo?.(),onGraphChange:xml=>callbacks.current.onChange(xml)} : {}),
        }); setReady(true); setError(undefined);}
        catch (error) {setError((error as Error).message);}
      }
      if ((data.event === 'autosave' || data.event === 'save') && typeof data.xml === 'string') {
        callbacks.current.onChange(data.xml);
        if (data.event === 'save') callbacks.current.onSave(data.xml);
      }
    };
    window.addEventListener('message', receive);
    let resizeFrame = 0;
    const resize = new ResizeObserver(() => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(() => bridge.current?.fit());
    });
    if (frame.current) resize.observe(frame.current);
    return () => {clearTimeout(timer); window.removeEventListener('message', receive);
      resize.disconnect(); cancelAnimationFrame(resizeFrame); bridge.current = undefined;};
  }, []);
  const apply = (xml: string) => {
    if (!bridge.current) throw new Error('绘图服务尚未就绪');
    const normalized = bridge.current.apply(xml);
    callbacks.current.onChange(normalized);
    return normalized;
  };
  return {frame, ready, error, apply, src: editorUrl.href,
    saved: () => send({action: 'status', message: '已保存到方案库', modified: false})};
}
