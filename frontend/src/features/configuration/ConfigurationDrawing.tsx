import { useEffect, useRef } from "react";
import { Alert } from "antd";
import { useDrawio } from "../topology/drawio/useDrawio";
import { emptyDrawing } from "../topology/drawio/useDrawing";
import { drawingIdentity } from "./drawingIdentity";
interface Props {
  xml: string;
  saved: boolean;
  onXml: (xml: string) => void;
  onSelection: (id: string | undefined) => void;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
}
export function ConfigurationDrawing(props: Props) {
  const applying = useRef(false),
    lastInput = useRef(props.xml || emptyDrawing);
  const lastApplied = useRef(drawingIdentity(props.xml || emptyDrawing));
  const editor = useDrawio({
    xml: props.xml || emptyDrawing,
    onChange: (xml) => {
      if (applying.current) return;
      const identity = drawingIdentity(xml);
      if (identity === lastApplied.current) return;
      lastApplied.current = identity;
      lastInput.current = xml;
      props.onXml(xml);
    },
    onSave: () => props.onSave(),
    onSelection: props.onSelection,
    onUndo: props.onUndo,
    onRedo: props.onRedo,
  });
  useEffect(() => {
    if (!editor.ready || lastInput.current === props.xml || !props.xml) return;
    applying.current = true;
    lastInput.current = props.xml;
    try {
      lastApplied.current = drawingIdentity(editor.apply(props.xml));
    } finally {
      applying.current = false;
    }
  }, [props.xml, editor.ready]);
  useEffect(() => {
    if (editor.ready && props.saved) editor.saved();
  }, [props.saved, props.xml, editor.ready]);
  return (
    <div className="config-drawing">
      {editor.error ? <Alert type="error" title={editor.error} /> : null}
      <iframe ref={editor.frame} src={editor.src} title="项目配置图纸" />
      {!editor.ready && !editor.error ? (
        <div className="drawio-loading">正在载入图纸…</div>
      ) : null}
    </div>
  );
}
