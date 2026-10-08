import { useMutation, useQueryClient } from "@tanstack/react-query";
import { App } from "antd";
import type { Dispatch, SetStateAction, RefObject } from "react";
import { api } from "../../../shared/api";
import { ROOT } from "../shared";
import { configurationKeys } from "../queryKeys";
import type { ApplyChoice, Checked, Configuration, ProjectConfiguration, Suggestion } from "../types";
import type { useConfigurationDraft } from "../useConfigurationDraft";
import { configurationKey } from "./configurationIdentity";

type Draft = ReturnType<typeof useConfigurationDraft>;
interface Options {
  projectId: string;
  draft: Draft;
  saved: ProjectConfiguration;
  checked?: Checked;
  setSaved: Dispatch<SetStateAction<ProjectConfiguration>>;
  setChecked: (value: Checked | undefined) => void;
  savedJson: RefObject<string>;
  saveWorkspace: () => Promise<ProjectConfiguration>;
  checkWorkspace: (refresh: boolean) => Promise<Checked>;
  onSaved: (historyKey: string) => void;
}
export function useProjectRequests(options: Options) {
  const { projectId, draft, checked, setSaved, setChecked, savedJson } = options;
  const { message } = App.useApp(), client = useQueryClient();
  const capture = () => ({ configuration: structuredClone(draft.current.current),
    before: configurationKey(draft.current.current), historyKey: draft.currentHistoryKey.current });
  const currentMatches = (before: string, historyKey: string) => {
    if (configurationKey(draft.current.current) === before && draft.currentHistoryKey.current === historyKey) return true;
    message.warning("等待期间草稿已有变化，返回结果未覆盖当前修改，请重新操作。");
    return false;
  };
  const acceptChecked = (result: Checked, recordHistory = true) => {
    setChecked(result);
    // Normalization belongs to the originating edit, not a separate undo step.
    if (recordHistory) draft.commit(result.configuration);
    else draft.replaceCurrent(result.configuration);
  };
  const drawing = useMutation({
    mutationFn: async ({ next, addIds = [], removeId }: { next: Configuration; addIds?: string[]; removeId?: string }) => {
      const { before, historyKey } = capture();
      const value = await updateDrawing(next, { addIds, removeId });
      return { before, historyKey, value };
    },
    onSuccess: ({ before, historyKey, value }) => { if (currentMatches(before, historyKey)) draft.commit(value); },
    onError: (e) => message.error(e.message),
  });
  const check = useMutation({
    mutationFn: options.checkWorkspace,
    onError: (e) => message.error(e.message),
  });
  const save = useMutation({
    mutationFn: async () => {
      const { before, historyKey } = capture();
      const result = await options.saveWorkspace();
      return { before, historyKey, result };
    },
    onSuccess: ({ before, historyKey, result }) => {
      setSaved(result); savedJson.current = configurationKey(result.configuration);
      options.onSaved(historyKey);
      client.setQueryData(configurationKeys.project(projectId), result);
      if (currentMatches(before, historyKey)) acceptChecked(result, false);
      client.invalidateQueries({ queryKey: ["project", projectId] });
      message.success("项目修订已保存");
    },
    onError: (e) => message.error(e.message),
  });
  const apply = useMutation({
    mutationFn: async ({ suggestion, choice }: { suggestion: Suggestion; choice: ApplyChoice }) => {
      const { configuration, before, historyKey } = capture();
      if (!checked) throw new Error("请先检查当前配置");
      const result = await api<Checked>(ROOT + "/apply", { method: "POST", body: JSON.stringify({
        configuration, refresh_knowledge: false, fingerprint: checked.fingerprint, suggestion_id: suggestion.id,
        ...("variantId" in choice ? { supply_source: choice.supplySource ?? "unknown", supply_evidence: choice.supplyEvidence ?? "" } : {}),
        ...("existingDeviceId" in choice ? { existing_device_id: choice.existingDeviceId, quantity: choice.quantity } : { variant_id: choice.variantId, source_id: choice.sourceId, quantity: choice.quantity }),
      }) });
      const addIds = result.configuration.devices.filter((d) => !configuration.devices.some((old) => old.id === d.id)).map((d) => d.id);
      const withDrawing = await updateDrawing(result.configuration, { addIds });
      return { before, historyKey, result: { ...result, configuration: withDrawing } };
    },
    onSuccess: ({ before, historyKey, result }) => { if (currentMatches(before, historyKey)) acceptChecked(result); },
    onError: (e) => message.error(e.message),
  });
  const reloadSaved = async () => {
    const result = await api<ProjectConfiguration>(ROOT + "/projects/" + projectId);
    setSaved(result); savedJson.current = configurationKey(result.configuration);
    client.setQueryData(configurationKeys.project(projectId), result);
    if (configurationKey(draft.current.current) === savedJson.current) setChecked(result);
  };
  return { drawing, check, save, apply, acceptChecked, reloadSaved };
}

async function updateDrawing(next: Configuration, options: { addIds?: string[]; removeId?: string }) {
  const result = await api<{ xml: string }>(ROOT + "/drawing", { method: "POST", body: JSON.stringify({ xml: next.drawing_xml, devices: next.devices, add_ids: options.addIds ?? [], remove_device_id: options.removeId ?? null }) });
  return { ...next, drawing_xml: result.xml };
}
