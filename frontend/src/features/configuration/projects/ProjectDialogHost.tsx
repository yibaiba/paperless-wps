import { Button, Modal, Space } from "antd";
import { QuantityInputsForm } from "./forms/QuantityInputsForm";
import { AssignDeviceDialog } from "./AssignDeviceDialog";
import { ProjectAuthor, RequirementForm, SystemForm } from "../ProjectForms";
import { SystemInputsForm } from "./forms/SystemInputsForm";
import type { useProjectEditor } from "./useProjectEditor";
import type { ProjectInteractions } from "./useProjectInteractions";

type Editor = ReturnType<typeof useProjectEditor>;

export function ProjectDialogHost({ editor, dialogs }: { editor: Editor; dialogs: ProjectInteractions }) {
  const { config, draft, requirementModal } = editor;
  return <>
    {dialogs.assignDevice && config.devices.some((d) => d.id === dialogs.assignDevice) ? (
      <AssignDeviceDialog deviceId={dialogs.assignDevice} configuration={config} onApply={draft.commit}
        onClose={() => dialogs.setAssignDevice(undefined)} />
    ) : null}
    <Modal open={dialogs.inputSystemChoices.length > 0} title="选择需要核对规模的系统" footer={null}
      onCancel={() => dialogs.setInputSystemChoices([])}>
      <Space orientation="vertical">{config.systems.filter((s) => dialogs.inputSystemChoices.includes(s.id)).map((s) => (
        <Button key={s.id} onClick={() => { dialogs.setInputsSystemId(s.id); dialogs.setInputSystemChoices([]); }}>{s.name}</Button>
      ))}</Space>
    </Modal>
    <Modal open={dialogs.resourceRoles.length > 0} title="选择需要补充资源需求的角色" footer={null}
      onCancel={() => dialogs.setResourceRoles([])}>
      <Space orientation="vertical">{config.requirements.filter((r) => dialogs.resourceRoles.includes(r.id)).map((r) => (
        <Button key={r.id} onClick={() => { editor.setRequirementModal({ systemId: r.system_id, initial: r }); dialogs.setResourceRoles([]); }}>
          {config.systems.find((s) => s.id === r.system_id)?.name} / {r.role}
        </Button>
      ))}</Space>
    </Modal>
    {dialogs.customInputsSystemId && config.systems.some(s => s.id === dialogs.customInputsSystemId) ? (
      <SystemInputsForm system={config.systems.find(s => s.id === dialogs.customInputsSystemId)!} configuration={config}
        onClose={() => dialogs.setCustomInputsSystemId(undefined)}
        onApply={inputs => draft.commit({ ...config, systems: config.systems.map(s => s.id === dialogs.customInputsSystemId ? { ...s, inputs } : s) })} />
    ) : null}
    {dialogs.inputsSystemId && config.systems.some((s) => s.id === dialogs.inputsSystemId) ? (
      <SystemForm configuration={config} systemId={dialogs.inputsSystemId}
        onClose={() => dialogs.setInputsSystemId(undefined)} onApply={draft.commit} />
    ) : null}
    {editor.systemModal ? <SystemForm configuration={config} onApply={draft.commit} onClose={() => editor.setSystemModal(false)} /> : null}
    {dialogs.quantityInputs ? <QuantityInputsForm configuration={config} inputs={dialogs.quantityInputs}
      onClose={() => dialogs.setQuantityInputs(undefined)} onApply={draft.commit} /> : null}
    {editor.author ? <ProjectAuthor configuration={config} onApply={draft.commit} onClose={() => editor.setAuthor(false)} /> : null}
    {requirementModal ? <RequirementForm
      devices={config.devices}
      systemId={requirementModal.systemId}
      definitionId={config.systems.find((s) => s.id === requirementModal.systemId)?.definition_id}
      definitionSnapshotId={config.definition_snapshot_id}
      knowledgePackageId={config.systems.find((s) => s.id === requirementModal.systemId)?.knowledge_package_id}
      requestedRole={requirementModal.requestedRole}
      systemName={config.systems.find((s) => s.id === requirementModal.systemId)!.kind}
      initial={requirementModal.initial}
      onClose={() => editor.setRequirementModal(undefined)}
      onApply={(requirement) => draft.commit({
        ...config,
        requirements: [...config.requirements.filter((old) => old.id !== requirement.id), requirement],
      })}
    /> : null}
  </>;
}
