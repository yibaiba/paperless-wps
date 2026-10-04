import { useEffect, useRef } from 'react';
import type { NextEditSuggestion } from '../businessTypes';
import { businessCandidatePresentation } from '../businessCandidatePresentation';

export function BusinessCandidateList({ items, selected, column, ready, onChoose }: {
  items: NextEditSuggestion[]; selected: number; column: number; ready: boolean;
  onChoose: (suggestion: NextEditSuggestion, index: number) => void;
}) {
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = list.current;
    const option = container?.children[selected];
    if (!container || !(option instanceof HTMLElement)) return;
    const bounds = container.getBoundingClientRect();
    const target = option.getBoundingClientRect();
    // Scroll only this list, leaving the input and surrounding window in place.
    if (target.top < bounds.top) container.scrollTop += target.top - bounds.top;
    else if (target.bottom > bounds.bottom) container.scrollTop += target.bottom - bounds.bottom;
  }, [selected, items]);
  return <div ref={list} className="inline-candidates business-candidates" id="business-candidates"
    role="listbox" aria-label="业务产品候选">{items.map((candidate, i) => {
      const copy = businessCandidatePresentation(candidate, column);
      return <button key={candidate.id} id={`business-candidate-${i}`} role="option" aria-selected={i === selected}
        disabled={!ready} className={i === selected ? 'selected' : ''}
        title={[copy.title, copy.location, copy.configuration, copy.source, copy.identity].filter(Boolean).join('\n')}
        onMouseDown={(e) => e.preventDefault()} onClick={() => onChoose(candidate, i)}>
        <span className="business-candidate-title"><strong>{copy.title}</strong><small>{copy.location}</small></span>
        <span>配置：{copy.configuration}</span>
        {copy.source && <span>来源：{copy.source}</span>}
      </button>;
    })}</div>;
}
