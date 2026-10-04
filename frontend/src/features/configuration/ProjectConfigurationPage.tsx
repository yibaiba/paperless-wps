import { ReferenceCasePanel } from "./referenceCases/ReferenceCasePanel";
import { DeviceInspector } from "./projects/DeviceInspector";
import { requirementDeviceIds } from "./projects/roleAllocations";
import { ProposalPanel } from "./projects/ProposalPanel";
import { AssignDeviceDialog } from "./projects/AssignDeviceDialog";
import { DraftRecovery } from "./projects/drafts/DraftRecovery";
import { DraftPreviewContext } from "./projects/drafts/context";
import type { Workspace } from "./projects/drafts/transport";
import { preloadQuotationSheet } from './quotation/loadSheet';
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, Modal, Space, Tabs, Typography } from "antd";
import { api } from "../../shared/api";
import type { ProjectConfiguration } from "./types";
import { ROOT } from "./shared";
import { businessKey, useProjectEditor } from "./projects/useProjectEditor";
import {
  ProjectAuthor,
  RequirementForm,
  SystemForm,
} from "./ProjectForms";
import { ProjectCandidates } from "./ProjectCandidates";
import { ConfigurationDrawing } from "./ConfigurationDrawing";
import { ProjectReviewDrawer } from "./projects/ProjectReviewDrawer";
import "./configuration.css";
import { ProjectImportDialog } from "./projects/ProjectImportDialog";
import { ProjectDeviceTable } from "./projects/ProjectDeviceTable";
import { configurationKeys } from "./queryKeys";
import { ProjectToolbar } from "./projects/ProjectToolbar";
import { ProjectSystemPanel } from "./projects/ProjectSystemPanel";
import { ProjectWorkflowStatus } from "./projects/ProjectWorkflowStatus";
import { ProjectOutputPanel } from "./projects/ProjectOutputPanel";
import { SupplyPanel } from "./projects/SupplyPanel";
import { ProjectDefinitionPanel } from "./projects/ProjectDefinitionPanel";
import { ProjectChangePanel } from "./projects/ProjectChangePanel";
import { ProjectConfirmation } from "./projects/ProjectConfirmation";
import { QuotationPanel } from "./quotation/QuotationPanel";
import { requestedRole } from "./projects/definitionSelection";
import { SystemInputsForm } from "./projects/forms/SystemInputsForm";

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
    <DraftRecovery key={projectId} projectId={projectId!}>{(workspace) => <ConfigurationEditor
      projectId={projectId!} initial={query.data!} workspace={workspace}
    />}</DraftRecovery>
  ) : (
    <Card loading />
  );
}
function ConfigurationEditor({
  projectId,
  initial,
  workspace,
}: {
  projectId: string;
  initial: ProjectConfiguration;
  workspace?: Workspace;
}) {
  const [inputSystemChoices, setInputSystemChoices] = useState<string[]>([]);
  const [inputsSystemId, setInputsSystemId] = useState<string>();
  const [customInputsSystemId, setCustomInputsSystemId] = useState<string>();
  const [resourceRoles, setResourceRoles] = useState<string[]>([]);
  const [assignDevice, setAssignDevice] = useState<string>();
  const navigate = useNavigate();
  const [returnParams] = useSearchParams();
  const [sheetPending, setSheetPending] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewTab, setReviewTab] = useState("todo");
  const editor = useProjectEditor({ projectId, initial, workspace });
  const [changeRequest, setChangeRequest] = useState<{ refresh: boolean; cleanup: boolean }>();
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
  const checkedStale =
    !checked || businessKey(checked.configuration) !== businessKey(config);
  const savedProjectionStale = checked ? checkedStale : dirty;
  const selecting = tab === "list" || tab === "drawing";
  const showInspector = selecting && (!!requirement || !!editingDevice);
  const openMaintenance = (query: Record<string, string>, context?: { systemId?: string; requirementId?: string }) => navigate('/knowledge?' + new URLSearchParams({ ...query,
    return_project: projectId, return_draft: editor.persistence.id ?? '', return_system: context?.systemId ?? selectedSystem ?? '',
    return_requirement: context?.requirementId ?? requirement?.id ?? '' }));
  return (
    <DraftPreviewContext.Provider value={editor.persistence.preview}><div className="configuration-page">
      {editor.persistence.error ? <Alert type="error" title={editor.persistence.error} action={<Space>
        {editor.persistence.canDiscardRejected ? <Button onClick={editor.persistence.discardRejected}>撤回未通过校验的修改</Button> : null}
        <Button onClick={editor.persistence.retry}>重试同步</Button>
      </Space>} /> : <Typography.Text type="secondary" role="status">
        {editor.persistence.syncing || editor.persistence.unsynced ? "草稿同步中…" : editor.persistence.id ? "工作草稿已同步；保存版本后可导出" : "修改会自动保存为工作草稿"}
      </Typography.Text>}
      {returnParams.get('from_knowledge') ? <Alert type="info" title="已返回原项目草稿，维护后的资料尚未应用" action={<Button onClick={() => setChangeRequest({ refresh: true, cleanup: false })}>预览资料升级差异</Button>} /> : null}
      {assignDevice && config.devices.some((d) => d.id === assignDevice) ? <AssignDeviceDialog deviceId={assignDevice} configuration={config} onApply={draft.commit} onClose={() => setAssignDevice(undefined)} /> : null}
      <Modal open={inputSystemChoices.length > 0} title="选择需要核对规模的系统" footer={null} onCancel={() => setInputSystemChoices([])}><Space orientation="vertical">{config.systems.filter((s) => inputSystemChoices.includes(s.id)).map((s) => <Button key={s.id} onClick={() => { setInputsSystemId(s.id); setInputSystemChoices([]); }}>{s.name}</Button>)}</Space></Modal>
      <Modal open={resourceRoles.length > 0} title="选择需要补充资源需求的角色" footer={null} onCancel={() => setResourceRoles([])}>
        <Space orientation="vertical">{config.requirements.filter((r) => resourceRoles.includes(r.id)).map((r) => <Button key={r.id} onClick={() => { setRequirementModal({ systemId: r.system_id, initial: r }); setResourceRoles([]); }}>{config.systems.find((s) => s.id === r.system_id)?.name} / {r.role}</Button>)}</Space>
      </Modal>
      <ReferenceCasePanel configuration={config} checked={checked} busy={busy} onChange={draft.commit}
        onDevice={id => { setDeviceModal(id); setSelectedRequirement(undefined); setTab("list"); }}
        onRole={id => { setDeviceModal(undefined); setSelectedRequirement(id); setTab("list"); }}
        onReview={() => setReviewOpen(true)} />
      <ProjectToolbar
        projectId={projectId}
        name={initial.name}
        revision={saved.revision}
        dirty={dirty}
        busy={busy || sheetPending}
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
        onView={setTab}
        proposalAction={<ProposalPanel disabled={busy || sheetPending} readyWorkspace={editor.persistence.readyWorkspace} execute={editor.persistence.execute} onApply={editor.acceptChecked} />}
        secondaryActions={<>
          <Button disabled={!selectedSystem || busy} onClick={() => setCustomInputsSystemId(selectedSystem)}>高级：系统自定义输入</Button>
          <Button onClick={() => setChangeRequest({ refresh: false, cleanup: false })}>预览本次改单</Button>
          <Button onClick={() => setChangeRequest({ refresh: false, cleanup: true })}>预览失效配套关联清理</Button>
          <ProjectConfirmation projectId={projectId} saved={saved} dirty={dirty} onConfirmed={editor.reloadSaved} />
        </>}
      />
      {initial.legacy_items && !saved.revision ? (
        <Alert
          type="warning"
          title={`原项目有 ${initial.legacy_items} 条清单，请先预览导入。原清单未改动。`}
        />
      ) : null}
      <ProjectWorkflowStatus
        readiness={checked?.readiness ?? saved.readiness}
        stale={savedProjectionStale}
        onViewChecks={() => setReviewOpen(true)}
        onCheck={() => check.mutate(false)}
        busy={busy || sheetPending}
        checking={check.isPending}
      />
      <div className={`config-workspace${!selecting ? " quotation-workspace" : showInspector ? " has-inspector" : ""}`} inert={drawing.isPending || save.isPending || apply.isPending}>
        {selecting ? <ProjectSystemPanel
          tree={tree}
          requirement={requirement}
          selectedSystem={selectedSystem}
          onSystemInputs={(id) => setInputsSystemId(id)}
          busy={busy}
          onAddSystem={() => setSystemModal(true)}
          onAddRequirement={(systemId) => setRequirementModal({ systemId })}
          onSelectSystem={(id) => {
            setDeviceModal(undefined);
            setSelectedSystem(id);
            setSelectedRequirement(undefined);
          }}
          onSelectRequirement={(id) => {
            setDeviceModal(undefined);
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
                  ? { ...requirementItem, device_id: null, allocations: [] }
                  : requirementItem,
              ),
            })
          }
        /> : null}
        <Card>
          <Tabs
            onMouseOver={(event) => {
              if ((event.target as HTMLElement).closest('[role="tab"]')?.id.endsWith('-tab-quotation')) preloadQuotationSheet();
            }}
            onFocus={(event) => {
              if ((event.target as HTMLElement).closest('[role="tab"]')?.id.endsWith('-tab-quotation')) preloadQuotationSheet();
            }}
            activeKey={tab}
            onChange={setTab}
            items={[
              { key: "quotation", label: "报价与导出", children: <QuotationPanel configuration={config} output={checked?.quotation_output ?? saved.quotation_output} saved={saved} dirty={dirty} stale={checkedStale} busy={busy || sheetPending} checking={check.isPending} onApply={draft.commit} onCheck={() => check.mutate(false)} sheetControls={{ configuration: config, saved, draftVersion: draft.version,
                onChecked: editor.acceptChecked, onPending: setSheetPending, onUndo: draft.undo, onRedo: draft.redo, canUndo: draft.canUndo, canRedo: draft.canRedo,
              }} /> },
              { key: "definitions", label: "系统版本与角色", children: <ProjectDefinitionPanel configuration={config} onApply={draft.commit} /> },
              { key: "supply", label: "供货分配", children: <SupplyPanel configuration={config} onApply={draft.commit} /> },
              {
                key: "list",
                label: `产品清单 ${config.devices.length}`,
                children: (
                  <ProjectDeviceTable
                    configuration={config}
                    stale={checkedStale}
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
                key: "output",
                label: `设备与采购清单`,
                children: (
                  <ProjectOutputPanel
                    output={checked?.project_output ?? saved.project_output}
                    stale={savedProjectionStale}
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
                    saved={!dirty}
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
            ].filter((item) => !["definitions", "output"].includes(item.key) || item.key === tab)
              .sort((a, b) => ["list", "supply", "quotation", "drawing", "definitions", "output"].indexOf(a.key) - ["list", "supply", "quotation", "drawing", "definitions", "output"].indexOf(b.key))}
          />
        </Card>
        {showInspector ? <aside className="project-inspector" aria-label="选型与产品属性">
          <Button className="project-inspector-close" onClick={() => { setDeviceModal(undefined); setSelectedRequirement(undefined); }}>收起选型面板</Button>
        {editingDevice ? (
          <DeviceInspector device={editingDevice} context={config} requiresSupply={config.calculation_version === 3}
            execute={editor.persistence.execute} onApply={editor.acceptChecked}
            onClose={() => setDeviceModal(undefined)} />
        ) : (
          <ProjectCandidates
            configuration={config}
            requirement={requirement}
            busy={busy}
            onSelect={selectDevice}
          />
        )}</aside> : null}
      </div>
      <ProjectReviewDrawer
        open={reviewOpen}
        activeTab={reviewTab}
        onClose={() => setReviewOpen(false)}
        onTabChange={setReviewTab}
        checked={checked}
        configuration={config}
        stale={checkedStale}
        busy={busy}
        onCheck={(refresh) => refresh ? setChangeRequest({ refresh: true, cleanup: false }) : check.mutate(false)}
        onIncludedChange={(next) => draft.commit(next)}
        onChoice={(demandId, selected) => draft.commit({ ...config, accessory_choices: [
          ...(config.accessory_choices ?? []).filter((c) => c.demand_id !== demandId), { demand_id: demandId, selected },
        ] })}
        onApply={(suggestion, choice) =>
          apply.mutate({ suggestion, choice })
        }
        onAction={(action) => {
        if (action.type === 'edit_accessory') { setReviewTab('accessories'); return; }
        setReviewOpen(false);
        if (action.type === 'edit_resources' && action.requirement_ids?.length) { setResourceRoles(action.requirement_ids); return; }
        if (action.type === 'assign_device' && action.device_id) { setAssignDevice(action.device_id); return; }
        if (action.type === 'add_system') { setSystemModal(true); return; }
        if (action.type === 'add_requirement' && action.system_id) { setRequirementModal({ systemId: action.system_id, requestedRole: requestedRole(action) }); return; }
        if (action.type === 'edit_price') { setTab('quotation'); return; }
        if (action.type === 'edit_supply') { setTab('supply'); return; }
        if (action.type === 'edit_system_inputs') { if (action.system_id) setInputsSystemId(action.system_id); else setInputSystemChoices(action.system_ids ?? []); return; }
        if (action.type === 'edit_inspection') { openMaintenance({ view: 'inspections', ...(action.profile_id ? { profile: action.profile_id } : {}) }); return; }
        if (action.type === 'edit_definition') { openMaintenance({ view: 'systems', system: config.systems.find(s => s.id === action.system_id)?.definition_id ?? '' }, { systemId: action.system_id, requirementId: action.requirement_id }); return; }
        if (action.type === 'edit_knowledge') { openMaintenance(action.rule_id ? { rule: action.rule_id, variant: action.variant_id ?? '' } : { variant: action.variant_id ?? '' }); return; }
        setTab('list');
        const role = config.requirements.find((r) => r.id === action.requirement_id);
        if (['edit_resources', 'edit_requirement'].includes(action.type) && role) setRequirementModal({ systemId: role.system_id, initial: role });
        else if (role) { setDeviceModal(undefined); setSelectedRequirement(role.id); setSelectedSystem(role.system_id); }
        else if (action.device_id) { const related = config.requirements.filter((r) => requirementDeviceIds(r).includes(action.device_id!)); if (related.length === 1) setRequirementModal({ systemId: related[0].system_id, initial: related[0] }); else setAssignDevice(action.device_id); }
      }} />
      {customInputsSystemId && config.systems.some(s => s.id === customInputsSystemId) ? <SystemInputsForm system={config.systems.find(s => s.id === customInputsSystemId)!} configuration={config} onClose={() => setCustomInputsSystemId(undefined)} onApply={inputs => draft.commit({ ...config, systems: config.systems.map(s => s.id === customInputsSystemId ? { ...s, inputs } : s) })} /> : null}
      {inputsSystemId && config.systems.find((s) => s.id === inputsSystemId) ? <SystemForm
        configuration={config} systemId={inputsSystemId} onClose={() => setInputsSystemId(undefined)} onApply={draft.commit} /> : null}
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
          devices={config.devices}
          systemId={requirementModal.systemId}
          definitionId={config.systems.find((s) => s.id === requirementModal.systemId)?.definition_id}
          definitionSnapshotId={config.definition_snapshot_id}
          knowledgePackageId={config.systems.find((s) => s.id === requirementModal.systemId)?.knowledge_package_id}
          requestedRole={requirementModal.requestedRole}
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
      {changeRequest ? <ProjectChangePanel projectId={projectId} revision={saved.revision} configuration={config}
        refresh={changeRequest.refresh} cleanup={changeRequest.cleanup} current={() => draft.current.current}
        onClose={() => setChangeRequest(undefined)} onApply={editor.acceptChecked} /> : null}
    </div></DraftPreviewContext.Provider>
  );
}
