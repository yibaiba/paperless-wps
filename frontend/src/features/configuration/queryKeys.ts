export const configurationKeys = {
  referenceCases: ["configuration", "reference-cases"] as const,
  caseComparison: (configuration: unknown) => ["configuration", "case-comparison", configuration] as const,
  materials: ["configuration", "materials"] as const,
  materialRevision: (id: string | undefined, revision: number) => ["configuration", "material", id, revision] as const,
  packageReadiness: (scope: { id: string; revision: number; knowledgeRevision: string; definitionRevision: number }) =>
    ["configuration", "package-readiness", scope] as const,
  all: ["configuration"] as const,
  quoteTemplate: ["configuration", "quote-template"] as const,
  products: ["configuration", "products"] as const,
  variants: ["configuration", "variants"] as const,
  attributeDefinitions: ["configuration", "attribute-definitions"] as const,
  knowledge: ["configuration", "knowledge"] as const,
  audit: (importId?: string) => ["configuration", "audit", importId] as const,
  history: (id?: string) => ["configuration", "history", id] as const,
  project: (id?: string) => ["configuration", "project", id] as const,
  draftDeviceUsage: (id?: string, revision?: number, deviceId?: string) =>
    ["configuration", "draft-device-usage", id, revision, deviceId] as const,
  candidates: (...parts: unknown[]) => ["configuration", "candidates", ...parts] as const,
};
