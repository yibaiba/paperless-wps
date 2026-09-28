export const configurationKeys = {
  all: ["configuration"] as const,
  quoteTemplate: ["configuration", "quote-template"] as const,
  products: ["configuration", "products"] as const,
  variants: ["configuration", "variants"] as const,
  attributeDefinitions: ["configuration", "attribute-definitions"] as const,
  knowledge: ["configuration", "knowledge"] as const,
  audit: (importId?: string) => ["configuration", "audit", importId] as const,
  history: (id?: string) => ["configuration", "history", id] as const,
  project: (id?: string) => ["configuration", "project", id] as const,
  candidates: (...parts: unknown[]) => ["configuration", "candidates", ...parts] as const,
};
