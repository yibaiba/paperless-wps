import type { ResolutionAction } from '../businessTypes';
import { issueText } from '../businessContextPresentation';
import { resolutionActions } from '../resolutionActions';

export function IssueActions({ issue, onResolve }: {
  issue: unknown; onResolve?: (action: ResolutionAction) => void;
}) {
  return <div className="issue">
    <span>{issueText(issue)}</span>
    {onResolve && <div className="issue-actions">{resolutionActions(issue).map((action) =>
      <button type="button" key={action.kind} onClick={() => onResolve(action)}>{action.label}</button>)}</div>}
  </div>;
}
