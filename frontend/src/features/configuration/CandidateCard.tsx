import { Alert, Button, Card, Descriptions, Select, Space, Tag, Typography } from "antd";
import type { Candidate, Deployment } from "./types";
import { EvidenceDetails } from "./EvidenceDetails";
import { Status, sourceOptions } from "./shared";

interface Props {
  candidate: Candidate;
  busy: boolean;
  expanded: boolean;
  sourceId?: string;
  kind?: Deployment["kind"];
  onSourceChange: (id: string) => void;
  onKindChange: (kind: Deployment["kind"]) => void;
  onChoose: () => void;
  onExpand: () => void;
}

export function CandidateCard(props: Props) {
  const { candidate, sourceId, kind } = props;
  const variant = candidate.variant;
  const selectedSource =
    sourceId ?? (variant.source_ids.length === 1 ? variant.source_ids[0] : undefined);
  return (
    <Card
      size="small"
      title={variant.product.model}
      extra={
        <Space>
          {candidate.ranking ? <Tag>智能排序第 {candidate.ranking.rank}</Tag> : null}
          <Status value={candidate.status} />
        </Space>
      }
    >
      <Typography.Paragraph>{variant.name}</Typography.Paragraph>
      {candidate.ranking ? <RankingNotice candidate={candidate} /> : null}
      <Space wrap style={{ width: "100%" }}>
        <Select
          style={{ minWidth: 260 }}
          placeholder="选择采购资料来源"
          disabled={!variant.source_ids.length}
          value={selectedSource}
          options={sourceOptions(variant)}
          onChange={props.onSourceChange}
        />
        <Select
          style={{ width: 150 }}
          placeholder="选择清单类型"
          value={kind}
          onChange={props.onKindChange}
          options={[
            { value: "hardware", label: "硬件" },
            { value: "software", label: "软件" },
            { value: "license", label: "授权" },
            { value: "accessory", label: "配件" },
          ]}
        />
      </Space>
      <Space style={{ marginTop: 10 }}>
        <Button disabled={props.busy || !selectedSource || !kind} onClick={props.onChoose}>
          选用此配置
        </Button>
        <Button type="link" onClick={props.onExpand}>
          依据
        </Button>
      </Space>
      {props.expanded ? <CandidateEvidence candidate={candidate} /> : null}
    </Card>
  );
}

function RankingNotice({ candidate }: { candidate: Candidate }) {
  return (
    <Alert
      type="info"
      showIcon
      title="语义相关，不代表已经确认兼容"
      description={`排序模型：${candidate.ranking!.reranker_model}；配置索引版本：${candidate.ranking!.document_revision}`}
      style={{ marginBottom: 12 }}
    />
  );
}

function CandidateEvidence({ candidate }: { candidate: Candidate }) {
  return (
    <Descriptions
      column={1}
      size="small"
      items={candidate.evidence.map((evidence, index) => ({
        key: index,
        label: String(evidence.name),
        children: (
          <>
            <Status
              value={String(evidence.result) === "fail" ? "conflict" : String(evidence.result)}
            />
            <EvidenceDetails evidence={evidence} />
          </>
        ),
      }))}
    />
  );
}
