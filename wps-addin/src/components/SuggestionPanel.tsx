import { CheckOutlined, SearchOutlined } from '@ant-design/icons';

import type { ActiveCell, Candidate } from '../types';

const GROUPS: Record<Candidate['group'], string> = {
  direct: '直接匹配', series: '同系列', alternative: '同类 / 替代',
  accessory: '相关配套', related: '相似产品',
};
const STATUS: Record<Candidate['status'], string> = {
  pass: '适用', unknown: '待核对', conflict: '冲突', unassessed: '未评估',
};

export function SuggestionPanel({ cell, candidates, busy, error, onAccept }: {
  cell?: ActiveCell;
  candidates: Candidate[];
  busy: boolean;
  error: string;
  onAccept: (candidate: Candidate) => void;
}) {
  const grouped = Object.entries(candidates.reduce<Partial<Record<Candidate['group'], Candidate[]>>>(
    (result, item) => ({ ...result, [item.group]: [...(result[item.group] ?? []), item] }), {},
  )) as Array<[Candidate['group'], Candidate[]]>;
  return <section className="suggestions" aria-labelledby="suggestions-title">
    <div className="section-heading">
      <div><h2 id="suggestions-title">产品联想</h2>
        <p>{cell ? `${cell.sheet} · ${cell.row} 行 · “${cell.value}”` : '等待产品输入'}</p>
      </div>
      {busy ? <span className="spinner" aria-label="查询中" /> : <SearchOutlined />}
    </div>
    {error ? <div className="error" role="alert">{error}</div> : null}
    {!busy && cell && candidates.length === 0 && !error
      ? <div className="empty">没有找到可用配置</div> : null}
    {candidates.length > 1 ? <div className="notice">多个具体配置待确认</div> : null}
    {grouped.map(([group, items]) => <div className="candidate-group" key={group}>
      <h3>{GROUPS[group]}</h3>
      {items.map((item) => <button className="candidate" key={item.key} onClick={() => onAccept(item)}>
        <span className="candidate-main">
          <strong>{item.model}</strong><span>{item.name}</span>
          <small>{item.variant_name} · {item.source.sheet} 第 {item.source.row} 行</small>
          {item.context_reasons[0] ? <small>{item.context_reasons.join(' · ')}</small> : null}
          {item.price_status === 'pending' ? <small>价格待确认</small> : null}
        </span>
        <span className={`status ${item.status}`}><CheckOutlined />{STATUS[item.status]}</span>
      </button>)}
    </div>)}
  </section>;
}
