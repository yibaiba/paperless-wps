import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { api } from './api';
import type { CatalogImport } from './types';

export function useCatalog() {
  const [params, setParams] = useSearchParams();
  const imports = useQuery({ queryKey: ['imports'], queryFn: () => api<CatalogImport[]>('/imports') });
  const selectedId = params.get('import') ?? imports.data?.[0]?.id;
  return {
    imports, selectedId,
    current: imports.data?.find((item) => item.id === selectedId),
    select: (id: string) => setParams((previous) => {
      const next = new URLSearchParams(previous); next.set('import', id); return next;
    }),
  };
}
