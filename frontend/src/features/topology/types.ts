import type {ProductDetail} from '../../shared/types';

export interface Position {x: number; y: number}
export interface SystemGroup {
  id: string; name: string; product_line: string; position: Position; width: number; height: number;
}
export interface Device {
  id: string; product_id: string; quantity: string; position: Position;
  group_id: string | null; role: string; serves_group_ids: string[]; note: string;
}
export const relationLabels = {unconfirmed: '待确认', required: '必须搭配', optional: '可选搭配', connection: '接口接线'};
export const modeLabels = {per_unit: '每件配套数量', per_capacity: '每件配套可带数量', per_group: '每组最低数量'};
export interface Relation {
  id: string; source: string; target: string; kind: keyof typeof relationLabels;
  mode: keyof typeof modeLabels; factor: string; evidence: string;
  source_port: string; target_port: string; cable: string; length_m: string | null;
}
export interface Diagram {groups: SystemGroup[]; devices: Device[]; relations: Relation[]}
export interface TopologySummary {id: string; name: string; revision: number; device_count: number; updated_at: string}
export interface Topology extends Diagram {
  id: string; name: string; actor: string; revision: number; drawing_xml?: string;
  products: Record<string, ProductDetail>;
  rules: {relation_id: string; rule_id: string; topology_revision: number}[];
  bom: {product_id: string; group_name: string; quantity: string; product: ProductDetail}[];
}
export const emptyDiagram: Diagram = {groups: [], devices: [], relations: []};
export const newRelation = (source: string, target: string): Relation => ({
  id: crypto.randomUUID(), source, target, kind: 'unconfirmed', mode: 'per_unit', factor: '1',
  evidence: '', source_port: '', target_port: '', cable: '', length_m: null,
});
