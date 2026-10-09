import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { IssueAction, QuantityInputIssue, Requirement } from "../types";
import { requirementDeviceIds } from "./roleAllocations";
import { requestedRole } from "./definitionSelection";
import type { useProjectEditor } from "./useProjectEditor";

type Editor = ReturnType<typeof useProjectEditor>;

export function useProjectInteractions(projectId: string, editor: Editor) {
  const [inputSystemChoices, setInputSystemChoices] = useState<string[]>([]);
  const [inputsSystemId, setInputsSystemId] = useState<string>();
  const [quantityInputs, setQuantityInputs] = useState<QuantityInputIssue[]>();
  const [customInputsSystemId, setCustomInputsSystemId] = useState<string>();
  const [resourceRoles, setResourceRoles] = useState<string[]>([]);
  const [assignDevice, setAssignDevice] = useState<string>();
  const [sheetPending, setSheetPending] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewTab, setReviewTab] = useState("todo");
  const [changeRequest, setChangeRequest] = useState<{ refresh: boolean; cleanup: boolean }>();
  const [returnParams] = useSearchParams();
  const navigate = useNavigate();

  const openMaintenance = (
    query: Record<string, string>,
    context?: { systemId?: string; requirementId?: string },
  ) => navigate('/knowledge?' + new URLSearchParams({
    ...query,
    return_project: projectId,
    return_draft: editor.persistence.id ?? '',
    return_system: context?.systemId ?? editor.selectedSystem ?? '',
    return_requirement: context?.requirementId ?? editor.requirement?.id ?? '',
  }));

  const editRequirement = (role: Requirement) =>
    editor.setRequirementModal({ systemId: role.system_id, initial: role });

  const handleIssueAction = (action: IssueAction) => {
    if (action.type === 'edit_accessory') {
      setReviewTab('accessories');
      setReviewOpen(true);
      return;
    }
    setReviewOpen(false);
    if (action.type === 'edit_quantity_inputs' && action.quantity_inputs?.length) return setQuantityInputs(action.quantity_inputs);
    if (action.type === 'edit_resources' && action.requirement_ids?.length) return setResourceRoles(action.requirement_ids);
    if (action.type === 'assign_device' && action.device_id) return setAssignDevice(action.device_id);
    if (action.type === 'add_system') return editor.setSystemModal(true);
    if (action.type === 'add_requirement' && action.system_id) return editor.setRequirementModal({ systemId: action.system_id, requestedRole: requestedRole(action) });
    if (action.type === 'edit_price') return editor.setTab('quotation');
    if (action.type === 'edit_supply') return editor.setTab('supply');
    if (action.type === 'edit_system_inputs') {
      if (action.system_id) setInputsSystemId(action.system_id);
      else setInputSystemChoices(action.system_ids ?? []);
      return;
    }
    if (action.type === 'edit_inspection') return openMaintenance({ view: 'inspections', ...(action.profile_id ? { profile: action.profile_id } : {}) });
    if (action.type === 'edit_definition') return openMaintenance(
      { view: 'systems', system: editor.config.systems.find(s => s.id === action.system_id)?.definition_id ?? '' },
      { systemId: action.system_id, requirementId: action.requirement_id },
    );
    if (action.type === 'edit_knowledge') return openMaintenance(
      action.rule_id ? { rule: action.rule_id, variant: action.variant_id ?? '' } : { variant: action.variant_id ?? '' },
    );
    editor.setTab('list');
    const role = editor.config.requirements.find((item) => item.id === action.requirement_id);
    if (['edit_resources', 'edit_requirement'].includes(action.type) && role) return editRequirement(role);
    if (role) {
      editor.setDeviceModal(undefined);
      editor.setSelectedRequirement(role.id);
      editor.setSelectedSystem(role.system_id);
      return;
    }
    if (!action.device_id) return;
    const related = editor.config.requirements.filter((item) => requirementDeviceIds(item).includes(action.device_id!));
    if (related.length === 1) editRequirement(related[0]);
    else setAssignDevice(action.device_id);
  };

  return {
    inputSystemChoices, setInputSystemChoices, inputsSystemId, setInputsSystemId,
    quantityInputs, setQuantityInputs, customInputsSystemId, setCustomInputsSystemId,
    resourceRoles, setResourceRoles, assignDevice, setAssignDevice,
    sheetPending, setSheetPending, reviewOpen, setReviewOpen, reviewTab, setReviewTab,
    changeRequest, setChangeRequest, returnedFromKnowledge: Boolean(returnParams.get('from_knowledge')),
    handleIssueAction,
  };
}

export type ProjectInteractions = ReturnType<typeof useProjectInteractions>;
