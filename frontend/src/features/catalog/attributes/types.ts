export const attributeLabels = {series:'系列', functions:'功能', interfaces:'接口 / 协议', systems:'适用系统'};
export type AttributeKey = keyof typeof attributeLabels;
export type AttributeValues = Record<AttributeKey,string[]>;
export interface AttributeProfile {
  revision:number; values:AttributeValues; actor?:string; evidence?:string; updated_at?:string;
}
export interface AttributeCondition {field:AttributeKey; operator:'all'|'any'; values:string[]}
export interface SourceSelector {import_id:string; conditions:AttributeCondition[]; exclude_product_ids:string[]}
export const attributeQueryKeys = ['products','product','rules','rule-preview','attribute-history'];
