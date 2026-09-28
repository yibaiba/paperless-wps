import type { ProjectOutputLine } from "../types";

export interface QuotedPrice {
  device_id: string;
  variant_id: string;
  source_id: string;
  mode: "source" | "manual" | "import";
  price_column: string;
  unit_price: string | null;
  evidence: string;
}
export interface Quotation {
  template_id: "meeting-system-v1";
  currency: "CNY";
  customer: string;
  project_name: string;
  sales_contact: string;
  designer_contact: string;
  design_date: string | null;
  room_description: string;
  price_column: string;
  tax_terms: string;
  prices: QuotedPrice[];
  sections: Record<string, string>;
  descriptions?: Record<string, { variant_id: string; source_id: string; text: string }>;
}
export interface QuoteLine extends ProjectOutputLine {
  original_specification?: string;
  purchase_quantity: string;
  unknown_quantity: string;
  unit_price: string | null;
  amount: string | null;
  section: string;
  brand: string;
  price_selection: QuotedPrice | null;
  issues: string[];
}
export interface QuotationOutput {
  total: string | null;
  known_subtotal: string;
  status: "draft" | "priced";
  lines: QuoteLine[];
  issues: { device_id: string; message: string }[];
}
export interface QuoteTemplate {
  id: "meeting-system-v1";
  tax_terms: string;
  price_columns: string[];
}
