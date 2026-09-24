import {useEffect, useRef, useState} from 'react';
import {api} from '../../../shared/api';
import type {ProductDetail} from '../../../shared/types';
import type {Device, Diagram, Relation, SystemGroup, Topology} from '../types';

export const emptyDrawing = '<mxfile><diagram id="presales" name="主图"><mxGraphModel grid="1" gridSize="10" page="1" pageWidth="1169" pageHeight="827"><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel></diagram></mxfile>';
export interface Drawing extends Diagram {
  drawing_xml: string; products: Record<string, ProductDetail>;
  unbound_shapes: {id: string; label: string; page: string}[]; drawing_only_edges: {id: string; page: string}[];
}
export type Operation = {action: 'add_product'; product_id: string; shape: string; bind_id?: string}
  | {action: 'add_products'; product_ids: string[]; shape: string}
  | {action: 'device'; device: Device} | {action: 'group'; group: SystemGroup}
  | {action: 'relation'; relation: Relation} | {action: 'remove'; id: string};
const INSPECTION_DELAY_MS = 350;

export function useDrawing(initial?: Topology) {
  const firstXml = initial?.drawing_xml || emptyDrawing;
  const latest = useRef(firstXml);
  const sequence = useRef(0);
  const [xml, setXml] = useState(firstXml), [dirty, setDirty] = useState(false);
  const [drawing, setDrawing] = useState<Drawing>({drawing_xml: firstXml,
    groups: initial?.groups ?? [], devices: initial?.devices ?? [], relations: initial?.relations ?? [],
    products: initial?.products ?? {}, unbound_shapes: [], drawing_only_edges: []});
  const [error, setError] = useState<string>(), [checking, setChecking] = useState(true);
  const change = (value: string) => {latest.current = value; setXml(value); setDirty(true);};
  useEffect(() => {
    const request = ++sequence.current;
    const abort = new AbortController();
    const timer = setTimeout(() => {
      setChecking(true);
      api<Drawing>('/topologies/drawing', {method: 'POST', body: JSON.stringify({xml}), signal: abort.signal})
        .then(result => {if (sequence.current === request) {setDrawing(result); setError(undefined);}})
        .catch(error => {if (!abort.signal.aborted && sequence.current === request) setError(error.message);})
        .finally(() => {if (sequence.current === request) setChecking(false);});
    }, INSPECTION_DELAY_MS);
    return () => {clearTimeout(timer); abort.abort();};
  }, [xml]);
  const prepare = async (operation: Operation) => api<Drawing>('/topologies/drawing', {
    method: 'POST', body: JSON.stringify({xml: latest.current, operation}),
  });
  return {xml, latest, dirty, setDirty, change, drawing, error, checking, prepare};
}
