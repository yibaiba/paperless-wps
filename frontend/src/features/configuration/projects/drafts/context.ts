import { createContext, useContext } from 'react';
import type { EditPreview } from '../../quotation/sheet/useSheetEditing';
import type { EditOperation } from '../../quotation/sheet/model';

export const DraftPreviewContext = createContext<((operations: EditOperation[], version: number) => Promise<EditPreview>) | undefined>(undefined);
export const useDraftPreview = () => useContext(DraftPreviewContext);
