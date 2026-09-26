import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Empty, Input, Pagination, Select, Space } from "antd";
import { api } from "../../shared/api";
import { CandidateCard } from "./CandidateCard";
import { CandidateModeSelector } from "./CandidateModeSelector";
import type {
  Candidate,
  CandidateMode,
  Configuration,
  Deployment,
  Requirement,
  Variant,
} from "./types";
import { ROOT } from "./shared";
import { configurationKeys } from "./queryKeys";

interface Props {
  configuration: Configuration;
  requirement?: Requirement;
  onSelect: (device: Deployment, existing: boolean) => void;
  busy: boolean;
}

export function ProjectCandidates(props: Props) {
  const { configuration, requirement, onSelect, busy } = props;
  const [search, setSearch] = useState("");
  const [semanticInput, setSemanticInput] = useState("");
  const [semanticQuery, setSemanticQuery] = useState("");
  const [mode, setMode] = useState<CandidateMode>("known");
  const [page, setPage] = useState(1);
  const system = configuration.systems.find((item) => item.id === requirement?.system_id);
  const query = useQuery({
    queryKey: configurationKeys.candidates(
      system?.kind,
      requirement?.role,
      requirement?.environment,
      configuration.knowledge_snapshot_id,
      mode,
      semanticQuery,
    ),
    enabled: !!requirement && (mode !== "semantic" || !!semanticQuery),
    queryFn: () =>
      api<Candidate[]>(ROOT + "/candidates", {
        method: "POST",
        body: JSON.stringify({
          system: system!.kind,
          role: requirement!.role,
          environment: requirement!.environment,
          knowledge_snapshot_id: configuration.knowledge_snapshot_id ?? null,
          mode,
          query_text: mode === "semantic" ? semanticQuery : "",
        }),
      }),
  });
  const [sourceIds, setSourceIds] = useState<Record<string, string>>({});
  const [kinds, setKinds] = useState<Record<string, Deployment["kind"]>>({});
  const [expanded, setExpanded] = useState<string>();
  if (!requirement) return <MissingRequirement />;
  const candidates = filterCandidates(query.data ?? [], search);
  const choose = (variant: Variant) => {
    const sourceId = sourceIds[variant.id] ?? singleSource(variant);
    const kind = kinds[variant.id];
    if (!sourceId || !kind) return;
    onSelect(newDeployment(variant, sourceId, kind), false);
  };
  return (
    <Card title={`${system?.name} · ${requirement.role}`} loading={query.isLoading}>
      {query.error ? <Alert type="error" title={query.error.message} /> : null}
      <CandidateModeSelector
        mode={mode}
        semanticInput={semanticInput}
        onModeChange={(value) => {
          setMode(value);
          setPage(1);
        }}
        onInputChange={setSemanticInput}
        onSearch={() => {
          setSemanticQuery(semanticInput.trim());
          setPage(1);
        }}
      />
      <ExistingDeviceSelect
        configuration={configuration}
        requirement={requirement}
        onSelect={onSelect}
        busy={busy}
      />
      <Input.Search
        placeholder="在当前结果中筛选型号或配置"
        value={search}
        onChange={(event) => {
          setSearch(event.target.value);
          setPage(1);
        }}
        style={{ marginBottom: 16 }}
      />
      <Space orientation="vertical" style={{ width: "100%" }}>
        {candidates.slice((page - 1) * 10, page * 10).map((candidate) => (
          <CandidateCard
            key={candidate.variant.id}
            candidate={candidate}
            busy={busy}
            expanded={expanded === candidate.variant.id}
            sourceId={sourceIds[candidate.variant.id]}
            kind={kinds[candidate.variant.id]}
            onSourceChange={(id) =>
              setSourceIds((current) => ({ ...current, [candidate.variant.id]: id }))
            }
            onKindChange={(kind) =>
              setKinds((current) => ({ ...current, [candidate.variant.id]: kind }))
            }
            onChoose={() => choose(candidate.variant)}
            onExpand={() =>
              setExpanded(expanded === candidate.variant.id ? undefined : candidate.variant.id)
            }
          />
        ))}
      </Space>
      <Pagination
        simple
        current={page}
        total={candidates.length}
        pageSize={10}
        onChange={setPage}
        style={{ marginTop: 16 }}
      />
      {!candidates.length && !query.isLoading ? <Empty description={emptyText(mode, semanticQuery)} /> : null}
    </Card>
  );
}

function ExistingDeviceSelect(props: Props & { requirement: Requirement }) {
  return (
    <Select
      placeholder="关联已有设备（明确共用）"
      style={{ width: "100%", marginBottom: 16 }}
      value={props.requirement.device_id ?? undefined}
      disabled={props.busy}
      options={props.configuration.devices.map((device) => ({ value: device.id, label: device.name }))}
      onChange={(id) =>
        props.onSelect(props.configuration.devices.find((device) => device.id === id)!, true)
      }
    />
  );
}

function newDeployment(variant: Variant, sourceId: string, kind: Deployment["kind"]): Deployment {
  return {
    id: crypto.randomUUID(),
    name: `${variant.product.model} · ${variant.name}`,
    variant_id: variant.id,
    source_id: sourceId,
    quantity: "1",
    kind,
    note: "",
    variant_snapshot: variant,
    source_snapshot: null,
    origin_suggestion: null,
  };
}

function filterCandidates(candidates: Candidate[], search: string) {
  const text = search.toLowerCase();
  return candidates.filter((candidate) =>
    `${candidate.variant.product.model} ${candidate.variant.name}`.toLowerCase().includes(text),
  );
}

function singleSource(variant: Variant) {
  return variant.source_ids.length === 1 ? variant.source_ids[0] : undefined;
}

function MissingRequirement() {
  return (
    <Card title="产品候选">
      <Empty description="先选择左侧系统，再添加并选中一个角色需求" />
    </Card>
  );
}

function emptyText(mode: CandidateMode, query: string) {
  if (mode === "semantic" && !query) return "填写需求描述后开始智能查找";
  if (mode === "semantic") return "没有找到可用的最新产品索引结果";
  if (mode === "all") return "尚未整理产品配置";
  return "当前版本和角色还没有关联候选，可使用智能查找或查看全部产品";
}
