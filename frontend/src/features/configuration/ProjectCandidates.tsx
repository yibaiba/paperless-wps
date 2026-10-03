import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Empty, Input, Pagination, Select, Space, Typography } from "antd";
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
import { NewSupplyDialog, type SupplyChoice } from "./projects/NewSupplyDialog";

const CANDIDATES_PER_PAGE = 10;

interface Props {
  configuration: Configuration;
  requirement?: Requirement;
  replacement?: Deployment;
  onSelect: (device: Deployment, existing: boolean, supply?: SupplyChoice) => void;
  busy: boolean;
}

export function ProjectCandidates(props: Props) {
  const { configuration, requirement, onSelect, busy } = props;
  const [search, setSearch] = useState("");
  const [semanticInput, setSemanticInput] = useState("");
  const [semanticQuery, setSemanticQuery] = useState("");
  const [mode, setMode] = useState<CandidateMode>(props.replacement && !requirement ? "all" : "known");
  const [page, setPage] = useState(1);
  const [pendingDevice, setPendingDevice] = useState<Deployment>();
  const system = configuration.systems.find((item) => item.id === requirement?.system_id);
  const environment = [...new Map([...(system?.inputs ?? []).map((a) => ({ ...a, purpose: "project_input" as const })), ...(requirement?.environment ?? [])].map((a) => [a.key, a])).values()];
  const query = useQuery({
    queryKey: configurationKeys.candidates(configuration.calculation_version, system?.definition_id, requirement?.role_id, configuration.definition_snapshot_id, system?.knowledge_package_id,
      system?.kind,
      requirement?.role,
      environment,
      configuration.knowledge_snapshot_id,
      mode,
      semanticQuery,
      { runtime: configuration.decision_runtime, bundle: configuration.decision_bundle_id, systems: configuration.systems, requirements: configuration.requirements,
        devices: configuration.devices.map(({ id, variant_id, quantity }) => ({ id, variant_id, quantity })),
        accessories: configuration.accessory_allocations, choices: configuration.accessory_choices, included: configuration.included_allocations,
        rooms: configuration.room_inputs, project: configuration.project_inputs },
    ),
    enabled: (!!requirement || !!props.replacement) && (mode !== "semantic" || !!semanticQuery),
    queryFn: () =>
      api<Candidate[]>(ROOT + "/candidates", {
        method: "POST",
        body: JSON.stringify({
          system: system?.kind ?? "",
          configuration: requirement ? configuration : undefined,
          requirement_id: requirement?.id ?? "",
          calculation_version: configuration.calculation_version,
          decision_runtime: configuration.decision_runtime ?? "python-v3",
          decision_bundle_id: configuration.decision_bundle_id ?? null,
          system_definition_id: system?.definition_id ?? "",
          role_id: requirement?.role_id ?? "",
          definition_snapshot_id: configuration.definition_snapshot_id ?? null,
          knowledge_package_id: system?.knowledge_package_id ?? "",
          role: requirement?.role ?? "",
          environment,
          knowledge_snapshot_id: configuration.knowledge_snapshot_id ?? null,
          mode,
          query_text: mode === "semantic" ? semanticQuery : "",
        }),
      }),
  });
  const [sourceIds, setSourceIds] = useState<Record<string, string>>({});
  const [kinds, setKinds] = useState<Record<string, Deployment["kind"]>>({});
  const [expanded, setExpanded] = useState<string>();
  if (!requirement && !props.replacement) return <MissingRequirement />;
  const candidates = filterCandidates(query.data ?? [], search);
  const activePage = Math.min(page, Math.max(1, Math.ceil(candidates.length / CANDIDATES_PER_PAGE)));
  const choose = (variant: Variant) => {
    const sourceId = sourceIds[variant.id] ?? singleSource(variant);
    const kind = kinds[variant.id];
    if (!sourceId || !kind) return;
    const device = newDeployment(variant, sourceId, kind);
    if (configuration.calculation_version === 3) setPendingDevice(device);
    else onSelect(device, false);
  };
  return (
    <Card title={props.replacement ? `替换 ${props.replacement.name}` : `${system?.name} · ${requirement?.role}`} loading={query.isLoading}>
      {pendingDevice ? <NewSupplyDialog name={pendingDevice.name} onClose={() => setPendingDevice(undefined)} onConfirm={(supply) => { onSelect(pendingDevice, false, supply); setPendingDevice(undefined); }} /> : null}
      {query.error ? <Alert type="error" title={query.error.message} /> : null}
      <Alert type="info" title="候选来自当前产品目录；已选设备仍保留其项目版本。" />
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
      {requirement && !props.replacement ? <ExistingDeviceSelect
        configuration={configuration}
        requirement={requirement}
        onSelect={onSelect}
        busy={busy}
      /> : null}
      <Input.Search
        allowClear
        placeholder="在当前结果中筛选型号或配置"
        value={search}
        onChange={(event) => {
          setSearch(event.target.value);
          setPage(1);
        }}
        style={{ marginBottom: 16 }}
      />
      {query.data && !query.error ? <Typography.Paragraph type="secondary">当前显示 {candidates.length} / {query.data.length} 个候选配置</Typography.Paragraph> : null}
      <Space orientation="vertical" style={{ width: "100%" }}>
        {candidates.slice((activePage - 1) * CANDIDATES_PER_PAGE, activePage * CANDIDATES_PER_PAGE).map((candidate) => (
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
        hideOnSinglePage
        current={activePage}
        total={candidates.length}
        pageSize={CANDIDATES_PER_PAGE}
        onChange={setPage}
        style={{ marginTop: 16 }}
      />
      {!candidates.length && !query.isLoading && !query.error ? <Empty description={search.trim() && query.data?.length ? '当前筛选没有匹配的型号或配置' : emptyText(mode, semanticQuery)}>
        {search ? <Button onClick={() => { setSearch(''); setPage(1); }}>清除筛选</Button> : null}
      </Empty> : null}
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
  const text = search.trim().toLowerCase();
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
