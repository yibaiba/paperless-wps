import { useQuery } from "@tanstack/react-query";
import { api } from "../../../shared/api";
import { ROOT } from "../shared";
import type { Definitions } from "../types";
export const definitionsKey = ["configuration", "definitions"] as const;
export const packagesKey = ["configuration", "knowledge-packages"] as const;
export function useDefinitions(snapshotId?: string | null) {
  return useQuery({ queryKey: [...definitionsKey, snapshotId ?? "current"], queryFn: () => api<Definitions>(ROOT + (snapshotId ? "/definition-snapshots/" + snapshotId : "/definitions")) });
}
