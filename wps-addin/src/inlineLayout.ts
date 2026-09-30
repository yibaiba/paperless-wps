export const INLINE_DIALOG_MIN_WIDTH = 240;
export const INLINE_DIALOG_LIST_WIDTH = 360;

const MAX_DIALOG_WIDTH = 520;
const MIN_INPUT_ROW_HEIGHT = 32;
const STATUS_ROW_HEIGHT = 30;
const CANDIDATE_ROW_HEIGHT = 48;
const MAX_VISIBLE_CANDIDATES = 4;

export interface InlineLayoutOptions {
  anchorWidth: number;
  anchorHeight: number;
  candidateCount: number;
  listVisible: boolean;
  showStatus: boolean;
  windowChromeHeight?: number;
}

export interface InlineDialogSize { width: number; height: number }

export type InlinePlacement = 'above' | 'below';

export interface InlineLayoutResult {
  placement: InlinePlacement;
  anchor: { width: number; height: number };
}

export function inlineDialogSize(options: InlineLayoutOptions): InlineDialogSize {
  const inputHeight = Math.max(MIN_INPUT_ROW_HEIGHT, Math.round(options.anchorHeight));
  const visibleCandidates = options.listVisible
    ? Math.min(options.candidateCount, MAX_VISIBLE_CANDIDATES) : 0;
  const contentHeight = inputHeight
    + (options.showStatus ? STATUS_ROW_HEIGHT : 0)
    + (visibleCandidates * CANDIDATE_ROW_HEIGHT);
  const desiredWidth = options.listVisible
    ? Math.max(options.anchorWidth, INLINE_DIALOG_LIST_WIDTH)
    : Math.max(options.anchorWidth, INLINE_DIALOG_MIN_WIDTH);
  return {
    width: Math.min(MAX_DIALOG_WIDTH, Math.round(desiredWidth)),
    height: contentHeight + Math.max(0, options.windowChromeHeight ?? 0),
  };
}
