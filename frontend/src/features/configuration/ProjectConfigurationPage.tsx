import { ReferenceCasePanel } from "./referenceCases/ReferenceCasePanel";
import { DeviceInspector } from "./projects/DeviceInspector";
import { ProposalPanel } from "./projects/ProposalPanel";
import { DraftRecovery } from "./projects/drafts/DraftRecovery";
import { DraftPreviewContext } from "./projects/drafts/context";
import type { Workspace } from "./projects/drafts/transport";
import { preloadQuotationSheet } from './quotation/loadSheet';
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Alert, Button, Card, Space, Tabs, Typography } from "antd";
import { api } from "../../shared/api";
import type { ProjectConfiguration } from "./types";
import { ROOT } from "./shared";
import { businessKey, useProjectEditor } from "./projects/useProjectEditor";
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
import { ProjectStageNav, type ProjectStage } from "./projects/ProjectStageNav";
import { ProjectRequirementsOverview } from "./projects/ProjectRequirementsOverview";
import { useProjectInteractions } from "./projects/useProjectInteractions";
import { ProjectDialogHost } from "./projects/ProjectDialogHost";

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
  const editor = useProjectEditor({ projectId, initial, workspace });
  const interactions = useProjectInteractions(projectId, editor);
  const {
    draft,
    config,
    saved,
    dirty,
    checked,
    setSystemModal,
    setAuthor,
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
  const {
    sheetPending, setSheetPending, reviewOpen, setReviewOpen, reviewTab, setReviewTab,
    changeRequest, setChangeRequest, returnedFromKnowledge, handleIssueAction,
  } = interactions;
  const checkedStale =
    !checked || businessKey(checked.configuration) !== businessKey(config) ||
    (config.calculation_version === 3 && (!checked.usage_projection?.version || checked.usage_projection.current === false));
  const savedProjectionStale = checked ? checkedStale : dirty;
  const recheck = () => {
    const outdatedUsage = config.calculation_version === 3 &&
      (!checked?.usage_projection?.version || checked.usage_projection.current === false);
    if (outdatedUsage) setChangeRequest({ refresh: false, cleanup: false });
    else check.mutate(false);
  };
  const stage: ProjectStage = tab === "requirements" ? "requirements"
    : tab === "quotation" || tab === "output" ? "quotation" : "configuration";
  const selectStage = (next: ProjectStage) => setTab(next === "requirements" ? "requirements" : next === "quotation" ? "quotation" : "list");
  const selecting = stage !== "quotation";
  const showInspector = stage === "configuration" && (tab === "list" || tab === "drawing") && (!!requirement || !!editingDevice);
  return (
    <DraftPreviewContext.Provider value={editor.persistence.preview}><div className="configuration-page">
      {editor.persistence.error ? <Alert type="error" title={editor.persistence.phase === 'conflict' ? '草稿版本冲突' : editor.persistence.error}
        description={editor.persistence.phase === 'conflict' ? editor.persistence.error : undefined} action={<Space>
        {editor.persistence.canDiscardRejected ? <Button onClick={editor.persistence.discardRejected}>撤回未通过校验的修改</Button> : null}
        <Button onClick={editor.persistence.retry}>重试同步</Button>
      </Space>} /> : <Typography.Text type="secondary" role="status">
        {editor.persistence.phase === 'creating' ? "正在建立工作草稿…" : editor.persistence.syncing || editor.persistence.unsynced ? "草稿同步中…" : editor.persistence.id ? "工作草稿已同步；保存版本后可导出" : "修改会自动保存为工作草稿"}
      </Typography.Text>}
      {returnedFromKnowledge ? <Alert type="info" title="已返回原项目草稿，维护后的资料尚未应用" action={<Button onClick={() => setChangeRequest({ refresh: true, cleanup: false })}>预览资料升级差异</Button>} /> : null}
      <ProjectDialogHost editor={editor} dialogs={interactions} />
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
          <Button disabled={!selectedSystem || busy} onClick={() => interactions.setCustomInputsSystemId(selectedSystem)}>高级：系统自定义输入</Button>
          <Button onClick={() => setChangeRequest({ refresh: false, cleanup: false })}>预览本次改单</Button>
          <Button onClick={() => setChangeRequest({ refresh: false, cleanup: true })}>预览失效配套关联清理</Button>
          <ProjectConfirmation projectId={projectId} saved={saved} dirty={dirty} onConfirmed={editor.reloadSaved} />
        </>}
      />
      <ProjectStageNav value={stage} onChange={selectStage} onPreloadQuotation={preloadQuotationSheet} />
      {stage === 'configuration' ? <div className="project-stage-views">
        <Button type={tab === 'list' ? 'primary' : 'default'} onClick={() => setTab('list')}>产品清单</Button>
        <Button type={tab === 'supply' ? 'primary' : 'default'} onClick={() => setTab('supply')}>供货分配</Button>
        <Button type={tab === 'drawing' ? 'primary' : 'default'} onClick={() => setTab('drawing')}>拓扑图纸</Button>
      </div> : null}
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
        onCheck={recheck}
        busy={busy || sheetPending}
        checking={check.isPending}
      />
      <div className={`config-workspace${!selecting ? " quotation-workspace" : showInspector ? " has-inspector" : ""}`} inert={drawing.isPending || save.isPending || apply.isPending}>
        {selecting ? <ProjectSystemPanel
          tree={tree}
          requirement={requirement}
          selectedSystem={selectedSystem}
          onSystemInputs={(id) => interactions.setInputsSystemId(id)}
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
            tabBarStyle={{ display: 'none' }}
            activeKey={tab}
            onChange={setTab}
            items={[
              { key: "requirements", label: "需求与系统", children: <ProjectRequirementsOverview
                configuration={config} selectedSystemId={selectedSystem}
                onEditInputs={interactions.setInputsSystemId}
                onAddRequirement={(systemId) => setRequirementModal({ systemId })} /> },
              { key: "quotation", label: "报价与导出", children: <QuotationPanel configuration={config} output={checked?.quotation_output ?? saved.quotation_output} saved={saved} dirty={dirty} stale={checkedStale} busy={busy || sheetPending} checking={check.isPending} onApply={draft.commit} onCheck={recheck} sheetControls={{ configuration: config, saved, draftVersion: draft.version,
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
            ]}
          />
        </Card>
        {showInspector ? <aside className="project-inspector" aria-label="选型与产品属性">
          <Button className="project-inspector-close" onClick={() => { setDeviceModal(undefined); setSelectedRequirement(undefined); }}>收起选型面板</Button>
        {editingDevice ? (
          <DeviceInspector device={editingDevice} context={config} requiresSupply={config.calculation_version === 3}
            execute={editor.persistence.execute} onApply={editor.acceptChecked}
            draftId={editor.persistence.id} draftRevision={editor.persistence.revision}
            checked={checked} stale={checkedStale} onAction={handleIssueAction}
            onRecheck={() => setChangeRequest({ refresh: false, cleanup: false })}
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
        onCheck={(refresh) => refresh ? setChangeRequest({ refresh: true, cleanup: false }) : recheck()}
        onIncludedChange={(next) => draft.commit(next)}
        onChoice={(demandId, selected) => draft.commit({ ...config, accessory_choices: [
          ...(config.accessory_choices ?? []).filter((c) => c.demand_id !== demandId), { demand_id: demandId, selected },
        ] })}
        onApply={(suggestion, choice) =>
          apply.mutate({ suggestion, choice })
        }
        onAction={handleIssueAction} />
      <ProjectImportDialog editor={editor} />
      {changeRequest ? <ProjectChangePanel projectId={projectId} revision={saved.revision} configuration={config}
        refresh={changeRequest.refresh} cleanup={changeRequest.cleanup} current={() => draft.current.current}
        onClose={() => setChangeRequest(undefined)} onApply={editor.persistence.recheck} /> : null}
    </div></DraftPreviewContext.Provider>
  );
}
