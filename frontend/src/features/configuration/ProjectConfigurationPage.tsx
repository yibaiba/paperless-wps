import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Space,
  Table,
  Tabs,
  Tree,
  Typography,
} from "antd";
import { api } from "../../shared/api";
import type { Deployment, ProjectConfiguration } from "./types";
import { ROOT } from "./shared";
import { businessKey, useProjectEditor } from "./projects/useProjectEditor";
import {
  DeploymentForm,
  ProjectAuthor,
  RequirementForm,
  SystemForm,
} from "./ProjectForms";
import { ProjectCandidates } from "./ProjectCandidates";
import { ConfigurationDrawing } from "./ConfigurationDrawing";
import { ProjectChecks } from "./ProjectChecks";
import "./configuration.css";
import { ProjectHistory } from "./projects/ProjectHistory";
import { ProjectImportDialog } from "./projects/ProjectImportDialog";
export default function ProjectConfigurationPage() {
  const { projectId } = useParams();
  const query = useQuery({
    queryKey: ["configuration", "project", projectId],
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    queryFn: () => api<ProjectConfiguration>(ROOT + "/projects/" + projectId),
  });
  if (query.error) return <Alert type="error" title={query.error.message} />;
  return query.data ? (
    <ConfigurationEditor
      key={projectId}
      projectId={projectId!}
      initial={query.data}
    />
  ) : (
    <Card loading />
  );
}
function ConfigurationEditor({
  projectId,
  initial,
}: {
  projectId: string;
  initial: ProjectConfiguration;
}) {
  const editor = useProjectEditor({ projectId, initial });
  const {
    draft,
    config,
    saved,
    dirty,
    checked,
    systemModal,
    setSystemModal,
    author,
    setAuthor,
    requirementModal,
    setRequirementModal,
    selectedSystem,
    setSelectedSystem,
    setSelectedRequirement,
    setDeviceModal,
    setImportOpen,
    tab,
    setTab,
    drawing,
    check,
    save,
    apply,
    busy,
    requirement,
    editingDevice,
    selectDevice,
    saveProject,
    close,
    tree,
  } = editor;
  return (
    <div className="configuration-page">
      <Space wrap>
        <Button onClick={close}>返回项目</Button>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {initial.name} · 配置
        </Typography.Title>
        <span>{dirty ? "有未保存修改" : `已保存 v${saved.revision}`}</span>
        <Button
          type="primary"
          onClick={saveProject}
          loading={save.isPending}
          disabled={busy}
        >
          保存项目版本
        </Button>
        <Button onClick={() => setAuthor(true)}>维护信息</Button>
        <ProjectHistory entityId={saved.id} />
        <Button disabled={!draft.canUndo || busy} onClick={draft.undo}>
          撤销
        </Button>
        <Button disabled={!draft.canRedo || busy} onClick={draft.redo}>
          重做
        </Button>
        <Button onClick={() => setImportOpen(true)}>导入旧清单 / 拓扑</Button>
      </Space>
      {initial.legacy_items && !saved.revision ? (
        <Alert
          type="warning"
          title={`原项目有 ${initial.legacy_items} 条清单，请先预览导入。原清单未改动。`}
        />
      ) : null}
      <div className="config-workspace" inert={busy}>
        <Card title="房间与系统">
          <Space orientation="vertical">
            <Button disabled={busy} onClick={() => setSystemModal(true)}>
              添加房间 / 系统
            </Button>
            <Button
              disabled={!selectedSystem || busy}
              onClick={() => setRequirementModal({ systemId: selectedSystem! })}
            >
              添加角色需求
            </Button>
          </Space>
          <Tree
            treeData={tree}
            defaultExpandAll
            onSelect={(keys) => {
              const [type, id] = String(keys[0] ?? "").split(":");
              if (type === "system") {
                setSelectedSystem(id);
                setSelectedRequirement(undefined);
              }
              if (type === "requirement") {
                setSelectedRequirement(id);
                setSelectedSystem(
                  config.requirements.find((r) => r.id === id)?.system_id,
                );
              }
            }}
          />
          {requirement ? (
            <Space wrap>
              <Button
                onClick={() =>
                  setRequirementModal({
                    systemId: requirement.system_id,
                    initial: requirement,
                  })
                }
              >
                编辑需求
              </Button>
              <Button
                onClick={() =>
                  draft.commit({
                    ...config,
                    requirements: config.requirements.map((r) =>
                      r.id === requirement.id ? { ...r, device_id: null } : r,
                    ),
                  })
                }
              >
                解除设备关联
              </Button>
            </Space>
          ) : null}
        </Card>
        <Card>
          <Tabs
            activeKey={tab}
            onChange={setTab}
            items={[
              {
                key: "list",
                label: `实际配置 ${config.devices.length}`,
                children: (
                  <Table<Deployment>
                    rowKey="id"
                    dataSource={config.devices}
                    pagination={false}
                    scroll={{ x: 600 }}
                    columns={[
                      { title: "设备 / 配置", dataIndex: "name" },
                      { title: "数量", dataIndex: "quantity" },
                      {
                        title: "服务系统",
                        render: (_, d) =>
                          config.requirements
                            .filter((r) => r.device_id === d.id)
                            .map(
                              (r) =>
                                config.systems.find((s) => s.id === r.system_id)
                                  ?.name,
                            )
                            .join("、") || "未分配",
                      },
                      {
                        title: "操作",
                        render: (_, d) => (
                          <Space>
                            <Button onClick={() => setDeviceModal(d.id)}>
                              编辑
                            </Button>
                            <Button
                              onClick={() =>
                                drawing.mutate({ next: config, addIds: [d.id] })
                              }
                            >
                              放入图纸
                            </Button>
                          </Space>
                        ),
                      },
                    ]}
                  />
                ),
              },
              {
                key: "drawing",
                label: "拓扑图纸",
                forceRender: true,
                children: (
                  <ConfigurationDrawing
                    xml={config.drawing_xml}
                    onXml={(xml) =>
                      draft.commit({
                        ...draft.current.current,
                        drawing_xml: xml,
                      })
                    }
                    onSelection={(id) => {
                      if (id) setDeviceModal(id);
                    }}
                    onUndo={draft.undo}
                    onRedo={draft.redo}
                    onSave={saveProject}
                  />
                ),
              },
            ]}
          />
        </Card>
        {editingDevice ? (
          <DeploymentForm
            key={editingDevice.id + editingDevice.quantity + editingDevice.name}
            device={editingDevice}
            onClose={() => setDeviceModal(undefined)}
            onApply={(d) =>
              drawing.mutate({
                next: {
                  ...config,
                  devices: config.devices.map((old) =>
                    old.id === d.id ? d : old,
                  ),
                },
              })
            }
            onDelete={() => {
              drawing.mutate({
                next: {
                  ...config,
                  devices: config.devices.filter(
                    (d) => d.id !== editingDevice.id,
                  ),
                  requirements: config.requirements.map((r) =>
                    r.device_id === editingDevice.id
                      ? { ...r, device_id: null }
                      : r,
                  ),
                  accessory_allocations: config.accessory_allocations.filter(
                    (item) => item.device_id !== editingDevice.id,
                  ),
                },
                removeId: editingDevice.id,
              });
              setDeviceModal(undefined);
            }}
            onClone={() => {
              const clone = {
                ...editingDevice,
                id: crypto.randomUUID(),
                name: editingDevice.name + " 副本",
                origin_suggestion: null,
              };
              drawing.mutate({
                next: { ...config, devices: [...config.devices, clone] },
                addIds: [clone.id],
              });
              setDeviceModal(undefined);
            }}
          />
        ) : (
          <ProjectCandidates
            configuration={config}
            requirement={requirement}
            busy={busy}
            onSelect={selectDevice}
          />
        )}
      </div>
      <ProjectChecks
        checked={checked}
        configuration={config}
        stale={
          !checked || businessKey(checked.configuration) !== businessKey(config)
        }
        busy={busy}
        onCheck={(refresh) => check.mutate(refresh)}
        onApply={(suggestion, choice) =>
          apply.mutate({ suggestion, choice })
        }
      />
      {systemModal ? (
        <SystemForm
          configuration={config}
          onApply={draft.commit}
          onClose={() => setSystemModal(false)}
        />
      ) : null}
      {author ? (
        <ProjectAuthor
          configuration={config}
          onApply={draft.commit}
          onClose={() => setAuthor(false)}
        />
      ) : null}
      {requirementModal ? (
        <RequirementForm
          systemId={requirementModal.systemId}
          systemName={
            config.systems.find((s) => s.id === requirementModal.systemId)!.kind
          }
          initial={requirementModal.initial}
          onClose={() => setRequirementModal(undefined)}
          onApply={(r) =>
            draft.commit({
              ...config,
              requirements: [
                ...config.requirements.filter((old) => old.id !== r.id),
                r,
              ],
            })
          }
        />
      ) : null}

      <ProjectImportDialog editor={editor} />
    </div>
  );
}
