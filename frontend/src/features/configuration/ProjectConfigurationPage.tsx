import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Alert, Card, Tabs } from "antd";
import { api } from "../../shared/api";
import type { ProjectConfiguration } from "./types";
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
import { ProjectImportDialog } from "./projects/ProjectImportDialog";
import { ProjectDeviceTable } from "./projects/ProjectDeviceTable";
import { ProjectOpenItems } from "./projects/ProjectOpenItems";
import { configurationKeys } from "./queryKeys";
import { ProjectToolbar } from "./projects/ProjectToolbar";
import { ProjectSystemPanel } from "./projects/ProjectSystemPanel";
export default function ProjectConfigurationPage() {
  const { projectId } = useParams();
  const query = useQuery({
    queryKey: configurationKeys.project(projectId),
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
      <ProjectToolbar
        name={initial.name}
        revision={saved.revision}
        dirty={dirty}
        busy={busy}
        saving={save.isPending}
        canUndo={draft.canUndo}
        canRedo={draft.canRedo}
        entityId={saved.id}
        onClose={close}
        onSave={saveProject}
        onAuthor={() => setAuthor(true)}
        onUndo={draft.undo}
        onRedo={draft.redo}
        onImport={() => setImportOpen(true)}
      />
      {initial.legacy_items && !saved.revision ? (
        <Alert
          type="warning"
          title={`原项目有 ${initial.legacy_items} 条清单，请先预览导入。原清单未改动。`}
        />
      ) : null}
      <div className="config-workspace" inert={busy}>
        <ProjectSystemPanel
          tree={tree}
          requirement={requirement}
          selectedSystem={selectedSystem}
          busy={busy}
          onAddSystem={() => setSystemModal(true)}
          onAddRequirement={(systemId) => setRequirementModal({ systemId })}
          onSelectSystem={(id) => {
            setSelectedSystem(id);
            setSelectedRequirement(undefined);
          }}
          onSelectRequirement={(id) => {
            setSelectedRequirement(id);
            setSelectedSystem(
              config.requirements.find((item) => item.id === id)?.system_id,
            );
          }}
          onEditRequirement={(item) =>
            setRequirementModal({ systemId: item.system_id, initial: item })
          }
          onUnlinkRequirement={(item) =>
            draft.commit({
              ...config,
              requirements: config.requirements.map((requirementItem) =>
                requirementItem.id === item.id
                  ? { ...requirementItem, device_id: null }
                  : requirementItem,
              ),
            })
          }
        />
        <Card>
          <Tabs
            activeKey={tab}
            onChange={setTab}
            items={[
              {
                key: "list",
                label: `实际配置 ${config.devices.length}`,
                children: (
                  <ProjectDeviceTable
                    configuration={config}
                    usages={
                      checked &&
                      businessKey(checked.configuration) === businessKey(config)
                        ? checked.device_usages
                        : []
                    }
                    onEdit={setDeviceModal}
                    onAddToDrawing={(id) =>
                      drawing.mutate({ next: config, addIds: [id] })
                    }
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
              const removedDemandIds = new Set(
                (checked?.suggestions ?? [])
                  .filter(
                    (item) =>
                      item.scope === "device" &&
                      item.scope_id === editingDevice.id,
                  )
                  .map((item) => item.id),
              );
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
                    (item) =>
                      item.device_id !== editingDevice.id &&
                      !removedDemandIds.has(item.demand_id),
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
      <ProjectOpenItems checked={checked} configuration={config} />
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
