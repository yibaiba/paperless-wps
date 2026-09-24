import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Pagination,
  Select,
  Space,
  Typography,
} from "antd";
import { api } from "../../shared/api";
import type {
  Candidate,
  Configuration,
  Deployment,
  Requirement,
  Variant,
} from "./types";
import { EvidenceDetails } from "./EvidenceDetails";
import { ROOT, Status, sourceOptions } from "./shared";
interface Props {
  configuration: Configuration;
  requirement?: Requirement;
  onSelect: (device: Deployment, existing: boolean) => void;
  busy: boolean;
}
export function ProjectCandidates({
  configuration,
  requirement,
  onSelect,
  busy,
}: Props) {
  const [search, setSearch] = useState(""),
    [page, setPage] = useState(1);
  const system = configuration.systems.find(
    (s) => s.id === requirement?.system_id,
  );
  const query = useQuery({
    queryKey: [
      "configuration",
      "candidates",
      system?.kind,
      requirement?.role,
      requirement?.environment,
    ],
    enabled: !!requirement,
    queryFn: () =>
      api<Candidate[]>(ROOT + "/candidates", {
        method: "POST",
        body: JSON.stringify({
          system: system!.kind,
          role: requirement!.role,
          environment: requirement!.environment,
        }),
      }),
  });
  const [sourceIds, setSourceIds] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<string>();
  const choose = (variant: Variant) => {
    const sourceId =
      sourceIds[variant.id] ??
      (variant.source_ids.length === 1 ? variant.source_ids[0] : undefined);
    if (!sourceId) return;
    onSelect(
      {
        id: crypto.randomUUID(),
        name: variant.product.model + " · " + variant.name,
        variant_id: variant.id,
        source_id: sourceId,
        quantity: "1",
        kind: "hardware",
        note: "",
        variant_snapshot: variant,
        source_snapshot: null,
        origin_suggestion: null,
      },
      false,
    );
  };
  if (!requirement)
    return (
      <Card title="产品候选">
        <Empty description="先选择左侧系统，再添加并选中一个角色需求" />
      </Card>
    );
  const candidates = [...(query.data ?? [])]
    .filter((c) =>
      `${c.variant.product.model} ${c.variant.name}`
        .toLowerCase()
        .includes(search.toLowerCase()),
    )
    .sort(
      (a, b) =>
        ({ pass: 0, unknown: 1, conflict: 2 })[a.status] -
        { pass: 0, unknown: 1, conflict: 2 }[b.status],
    );
  return (
    <Card
      title={`${system?.name} · ${requirement.role}`}
      loading={query.isLoading}
    >
      {query.error ? <Alert type="error" title={query.error.message} /> : null}
      <Typography.Paragraph type="secondary">
        未知或冲突的选择可以保留，检查结果会持续展示。
      </Typography.Paragraph>
      <Select
        placeholder="关联已有设备（明确共用）"
        style={{ width: "100%", marginBottom: 16 }}
        value={requirement.device_id ?? undefined}
        disabled={busy}
        options={configuration.devices.map((d) => ({
          value: d.id,
          label: d.name,
        }))}
        onChange={(id) =>
          onSelect(
            configuration.devices.find((d) => d.id === id)!,
            true,
          )
        }
      />
      <Input.Search
        placeholder="搜索型号或配置"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
        style={{ marginBottom: 16 }}
      />
      <Space orientation="vertical" style={{ width: "100%" }}>
        {candidates.slice((page - 1) * 10, page * 10).map((c) => (
          <Card
            size="small"
            key={c.variant.id}
            title={c.variant.product.model}
            extra={<Status value={c.status} />}
          >
            <Typography.Paragraph>{c.variant.name}</Typography.Paragraph>
            <Select
              style={{ width: "100%" }}
              placeholder="选择采购资料来源"
              disabled={!c.variant.source_ids.length}
              value={
                sourceIds[c.variant.id] ??
                (c.variant.source_ids.length === 1
                  ? c.variant.source_ids[0]
                  : undefined)
              }
              options={sourceOptions(c.variant)}
              onChange={(id) =>
                setSourceIds({ ...sourceIds, [c.variant.id]: id })
              }
            />
            <Space style={{ marginTop: 10 }}>
              <Button
                disabled={
                  busy ||
                  !(
                    sourceIds[c.variant.id] || c.variant.source_ids.length === 1
                  )
                }
                onClick={() => choose(c.variant)}
              >
                选用此配置
              </Button>
              <Button
                type="link"
                onClick={() =>
                  setExpanded(
                    expanded === c.variant.id ? undefined : c.variant.id,
                  )
                }
              >
                依据
              </Button>
            </Space>
            {expanded === c.variant.id ? (
              <Descriptions
                column={1}
                size="small"
                items={c.evidence.map((e, i) => ({
                  key: i,
                  label: String(e.name),
                  children: (
                    <>
                      <Status
                        value={
                          String(e.result) === "fail"
                            ? "conflict"
                            : String(e.result)
                        }
                      />
                      <EvidenceDetails evidence={e} />
                    </>
                  ),
                }))}
              />
            ) : null}
          </Card>
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
      {!candidates.length ? (
        <Empty description="尚未整理产品配置，请先完成产品库核对" />
      ) : null}
    </Card>
  );
}
