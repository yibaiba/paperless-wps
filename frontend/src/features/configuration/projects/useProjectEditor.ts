import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { App } from "antd";
import { api } from "../../../shared/api";
import type {
  Checked,
  Configuration,
  Deployment,
  ProjectConfiguration,
  Requirement,
} from "../types";
import { ROOT } from "../shared";
import { useConfigurationDraft } from "../useConfigurationDraft";
import { buildProjectTree } from "./projectTree";
import { useProjectRequests } from "./useProjectRequests";
import type { SupplyChoice } from "./NewSupplyDialog";
import { usePersistentDraft } from "./drafts/usePersistentDraft";
import type { Workspace } from "./drafts/transport";
export function businessKey(c: Configuration) {
  const { drawing_xml, ...data } = c;
  void drawing_xml;
  return JSON.stringify(data);
}

export function useProjectEditor({
  projectId,
  initial,
  workspace,
}: {
  projectId: string;
  initial: ProjectConfiguration;
  workspace?: Workspace;
}) {
  const draft = useConfigurationDraft(workspace?.configuration ?? initial.configuration),
    config = draft.present;
  const [saved, setSaved] = useState(initial);
  const savedJson = useRef(JSON.stringify(initial.configuration));
  const serialized = useMemo(() => JSON.stringify(config), [config]);
  const dirty = serialized !== savedJson.current;
  const [checkHistory, setCheckHistory] = useState<{ latest?: Checked; results: Map<string, Checked> }>(() => ({
    latest: workspace?.checked ?? (initial.fingerprint ? initial : undefined),
    results: new Map(workspace ? [[businessKey(workspace.configuration), workspace.checked]] : initial.fingerprint ? [[businessKey(initial.configuration), initial]] : []),
  }));
  const checked = checkHistory.results.get(businessKey(config)) ?? checkHistory.latest;
  const setChecked = (result: Checked | undefined) => setCheckHistory((previous) => ({
    latest: result,
    results: result ? new Map(previous.results).set(businessKey(result.configuration), result) : previous.results,
  }));
  const [systemModal, setSystemModal] = useState(false),
    [author, setAuthor] = useState(false),
    [requirementModal, setRequirementModal] = useState<{
      systemId: string;
      requestedRole?: { id: string; name: string };
      initial?: Requirement;
    }>();
  const [params] = useSearchParams();
  const [selectedSystem, setSelectedSystem] = useState<string | undefined>(params.get("system") || undefined),
    [selectedRequirement, setSelectedRequirement] = useState<string | undefined>(params.get("requirement") || undefined),
    [deviceModal, setDeviceModal] = useState<string>();
  const [preview, setPreview] = useState<{
      configuration: Configuration;
      unmapped: { id: string; source_id: string; reason: string }[];
      warning: string;
    }>(),
    [importOpen, setImportOpen] = useState(false),
    [topologyId, setTopologyId] = useState<string>();
  const [tab, setTab] = useState("list");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const topologies = useQuery({
    queryKey: ["topologies"],
    enabled: importOpen,
    queryFn: () => api<{ id: string; name: string }[]>("/topologies"),
  });
  const persistence = usePersistentDraft({ projectId, saved, configuration: config, initialWorkspace: workspace,
    accept: (result) => { setChecked(result); draft.replaceCurrent(result.configuration); },
    acceptOperation: (result) => { setChecked(result); draft.commit(result.configuration); },
  });
  const { drawing, check, save, apply, acceptChecked, reloadSaved } = useProjectRequests({
    projectId, draft, saved, checked, setSaved, setChecked, savedJson, saveWorkspace: persistence.save,
  });
  const importing = useMutation({
    mutationFn: () =>
      api<typeof preview>(
        ROOT +
          `/projects/${projectId}/import-preview` +
          (topologyId ? "?topology_id=" + encodeURIComponent(topologyId) : ""),
      ),
    onSuccess: setPreview,
    onError: (e) => message.error(e.message),
  });
  const busy =
    drawing.isPending || check.isPending || save.isPending || apply.isPending || persistence.syncing || persistence.unsynced;
  const requirement = config.requirements.find(
      (r) => r.id === selectedRequirement,
    ),
    editingDevice = config.devices.find((d) => d.id === deviceModal);
  const selectDevice = (device: Deployment, existing: boolean, supply?: SupplyChoice) => {
    if (!requirement) return;
    const previous = config.devices.find((d) => d.id === requirement.device_id);
    const replacing =
      !existing &&
      previous &&
      config.requirements.filter((r) => r.device_id === previous.id).length ===
        1 && !config.accessory_allocations.some((a) => a.device_id === previous.id);
    const chosen = replacing ? { ...device, id: previous.id } : device;
    const devices = existing
      ? config.devices
      : replacing
        ? config.devices.map((d) => (d.id === previous.id ? chosen : d))
        : [...config.devices, chosen];
    const allocations = replacing ? (config.supply_allocations ?? []).filter((a) => a.device_id !== previous!.id) : (config.supply_allocations ?? []);
    drawing.mutate({
      next: {
        ...config,
        devices,
        supply_allocations: supply && !existing ? [...allocations, { id: crypto.randomUUID(), device_id: chosen.id, quantity: chosen.quantity, ...supply }] : allocations,
        requirements: config.requirements.map((r) =>
          r.id === requirement.id ? { ...r, device_id: chosen.id } : r,
        ),
      },
      addIds: existing || replacing ? [] : [chosen.id],
    });
  };
  const saveProject = () => {
    if (!config.actor.trim() || !config.evidence.trim()) {
      setAuthor(true);
      return;
    }
    save.mutate();
  };
  const close = () => navigate("/projects/" + projectId);
  const tree = useMemo(
    () => buildProjectTree(config),
    [config.requirements, config.rooms, config.systems],
  );
  return {
    persistence,
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
    preview,
    setPreview,
    importOpen,
    setImportOpen,
    topologyId,
    setTopologyId,
    tab,
    setTab,
    topologies,
    drawing,
    acceptChecked,
    reloadSaved,
    check,
    save,
    apply,
    importing,
    busy,
    requirement,
    editingDevice,
    selectDevice,
    saveProject,
    close,
    tree,
  };
}
